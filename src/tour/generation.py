"""Tour-builder generation — §3.4 of phase-1-design.

Turns a ``BeatSequence`` into a ``Script``: cold-open, anchor essays,
circumnavigation, transit, closing. Sentence-level traceable output —
every sentence carries either a NarrativeBeat UUID or a whitelisted
glue label.

The whole module is deterministic apart from the optional Haiku call,
which is bounded to glue boundaries that template-defaults can't fill.
For tests, pass a ``MockGlueClient``; the LLM is never invoked and the
test asserts the deterministic structural shape.

Design notes:

- Stage 1 (cold open) prefers the first stop's ``stop_orientation``
  beat. When absent (most tier-5 anchors per §1.4), falls back to a
  ``SYNTHESIZED_OPENER`` template per §3.4 / Q7. This documents the
  data gap honestly rather than masking it.
- Stages 2/3 (anchor essay + circumnavigation) just stream the
  pre-ordered beats from ``BeatSequence``. Beat ordering already
  encodes the spatial primitive (sub_location / trigger_address).
- Stage 4 (transit) picks a corpus transit beat for the segment when
  one exists at either endpoint POI; otherwise emits a single
  ``GLUE_NAV`` glue sentence (Haiku or template).
- Stage 5 (closing) emits a ``GLUE_CLOSING`` plus an optional callback
  beat at the final POI.

Glue is the only place generation invents text. The whitelist
categories below are the universe of valid glue ``source_id`` values;
``validation.py`` enforces this gate.
"""

from __future__ import annotations

import datetime as _dt
import re
from collections import Counter
from collections.abc import Iterable

from .contract import (
    BeatRef,
    BeatSequence,
    POIBeats,
    Route,
    Script,
    ScriptPOI,
    Sentence,
    TourInput,
    ValidationReport,
)
from .glue_client import NO_GLUE_SENTINEL, GlueClient, MockGlueClient
from .routing import beat_spoken_seconds, compute_dwell_seconds, planned_audio_seconds

# ---------------------------------------------------------------------------
# Whitelisted glue labels — §3.5 of phase-1-design
# ---------------------------------------------------------------------------

GLUE_NAV: str = "GLUE_NAV"
GLUE_STAGING: str = "GLUE_STAGING"
GLUE_PACING: str = "GLUE_PACING"
GLUE_CALLBACK: str = "GLUE_CALLBACK"
GLUE_CLOSING: str = "GLUE_CLOSING"
# Phase 4 (spec §6): a reflection synthesizes what has ALREADY been visited,
# spoken on a long leg. Placement is deterministic (reflection.py); the text is
# LLM-composed at COMPOSE time and gated fail-closed by VERIFY — the stitcher
# itself never writes one (a template cannot).
GLUE_REFLECTION: str = "GLUE_REFLECTION"
ARITH: str = "ARITH"
SYNTHESIZED_OPENER: str = "SYNTHESIZED_OPENER"

GLUE_LABELS: frozenset[str] = frozenset(
    {
        GLUE_NAV,
        GLUE_STAGING,
        GLUE_PACING,
        GLUE_CALLBACK,
        GLUE_CLOSING,
        GLUE_REFLECTION,
        ARITH,
        SYNTHESIZED_OPENER,
    }
)

# Phrases generation must never emit (rule 32 + feedback_tour_tone_default).
FORBIDDEN_PHRASES: tuple[str, ...] = ("imagine", "picture this", "envision", "visualize")


# ---------------------------------------------------------------------------
# Sentence splitting
# ---------------------------------------------------------------------------

# Split on .?! followed by whitespace, but never inside common abbreviations.
# Best-effort — corpus is well-edited prose. Validation catches invention.
_ABBREVIATIONS: frozenset[str] = frozenset(
    {"mr", "mrs", "ms", "dr", "st", "no", "vs", "etc", "e.g", "i.e", "mme", "mlle"}
)
_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀ-ÖØ-Þ«„(\"'])")
# Personal-name initials — a single capital letter + period, optionally chained
# with '-' or more initials: "J.", "J.-B.", "J.B.". These end in a period but are
# NEVER a sentence boundary, so the splitter must re-glue them (else TTS reads
# "…a portrait by J.-B." as its own stuttered sentence — the User-agent finding).
_INITIALS_RE = re.compile(r"^[A-ZÀ-ÖØ-Þ]\.(-?[A-ZÀ-ÖØ-Þ]\.)*$")
# ...but these dotted-caps tokens have the SAME shape as name-initials yet DO
# legitimately end a sentence ("the U.S.", "1914 A.D.", "by 5 P.M."). They must
# NOT be re-glued, or two real sentences fuse (the mirror of the stutter bug).
# Keyed by lowercased, trailing-period-stripped form.
_TERMINAL_ABBREVS: frozenset[str] = frozenset(
    {"u.s", "u.k", "u.s.a", "u.n", "e.u", "a.d", "b.c", "a.m", "p.m", "d.c"}
)


def split_sentences(text: str) -> list[str]:
    """Split a beat's script_body into audio-sentence units.

    Emits sentence strings (no trailing whitespace); preserves inline
    French phrases and quoted material verbatim. Empty/whitespace-only
    input yields ``[]``.
    """
    if not text or not text.strip():
        return []
    raw = _SPLIT_RE.split(text.strip())
    # Re-glue accidentally-split abbreviation pieces ("Mme.", "no. 6").
    out: list[str] = []
    for piece in raw:
        piece = piece.strip()
        if not piece:
            continue
        if out and _last_word_is_abbrev(out[-1]):
            out[-1] = f"{out[-1]} {piece}"
        else:
            out.append(piece)
    return out


def _last_word_is_abbrev(s: str) -> bool:
    words = s.split()
    if not words:
        return False
    last = words[-1].rstrip("\"'»)")  # keep the periods; drop a trailing quote/paren
    norm = last.lower().rstrip(".")
    # A personal-name initial (J., J.-B.) is never a sentence end — but a dotted-
    # caps abbreviation that CAN end a sentence (U.S., A.D., P.M.) is excluded.
    if _INITIALS_RE.match(last) and norm not in _TERMINAL_ABBREVS:
        return True
    return norm in _ABBREVIATIONS


# ---------------------------------------------------------------------------
# Top-level entrypoint
# ---------------------------------------------------------------------------


def generate(
    beat_sequence: BeatSequence,
    route: Route,
    tour_input: TourInput,
    *,
    glue_client: GlueClient | None = None,
    now: _dt.datetime | None = None,
) -> Script:
    """Build the Script from a planned BeatSequence + Route.

    Validation runs at the end and is attached to the returned Script.
    No exception is raised on validation failure — the caller (skill
    orchestrator) decides whether to block on a non-empty report.
    """
    from .beat_select import reorder_final_stop_for_closing  # avoid cycles
    from .validation import validate_script  # avoid import cycle

    client = glue_client or MockGlueClient()
    sentences: list[Sentence] = []

    # Phase 7 Fix 5: ensure the final stop's last beat is closing-friendly
    # (callback > climax > longest body). Closing glue lands after this.
    beat_sequence = reorder_final_stop_for_closing(beat_sequence)
    poi_beats = beat_sequence.poi_beats
    # consumed_beat_ids tracks every beat already emitted across the
    # whole script, so transit + anchor stages never emit the same
    # beat twice. Without this, a transit beat picked from `current`'s
    # pool (or a transit beat shared by adjacent POIs) re-appeared in
    # `_build_anchor_block` after the transit stage.
    consumed_beat_ids: set[str] = set()
    if poi_beats:
        cold_open_sents, consumed_in_cold_open = _build_cold_open(
            beat_sequence, route, client, tour_input=tour_input, stop_idx=0
        )
        sentences.extend(cold_open_sents)
        consumed_beat_ids |= consumed_in_cold_open

    for stop_idx, current in enumerate(poi_beats):
        if stop_idx > 0:
            previous = poi_beats[stop_idx - 1]
            transit_sents = _build_transit(
                previous,
                current,
                route,
                client,
                stop_idx=stop_idx,
                consumed_beat_ids=consumed_beat_ids,
                vignette_beats=beat_sequence.vignette_beats.get(stop_idx, ()),
            )
            sentences.extend(transit_sents)
            for s in transit_sents:
                if s.source_type == "beat":
                    consumed_beat_ids.add(s.source_id)
        anchor_sents = _build_anchor_block(current, stop_idx, skip_beat_ids=consumed_beat_ids)
        sentences.extend(anchor_sents)
        for s in anchor_sents:
            if s.source_type == "beat":
                consumed_beat_ids.add(s.source_id)

    if poi_beats:
        sentences.extend(
            _build_closing(
                beat_sequence,
                tour_input,
                route,
                client,
                stop_idx=max(0, len(poi_beats) - 1),
            )
        )

    selected_pois = _flatten_pois(beat_sequence, route)
    lens_coverage = _lens_coverage(beat_sequence)
    total_audio = _sum_audio(sentences, beat_sequence)
    walking = int(route.total_walk_seconds)
    distance = int(route.total_walk_distance_m)
    planned = int(route.err_short_total_seconds)

    script = Script(
        city_slug=tour_input.city_slug,
        generated_at=(now or _dt.datetime.now(_dt.UTC)).isoformat(),
        inputs=tour_input,
        total_audio_seconds=total_audio,
        total_walking_seconds=walking,
        total_walk_distance_m=distance,
        total_planned_seconds=planned,
        selected_pois=selected_pois,
        lens_coverage=lens_coverage,
        script=tuple(sentences),
        validation=ValidationReport(),  # placeholder — replaced below
    )
    report = validate_script(script, beat_sequence)
    return script.model_copy(update={"validation": report})


# ---------------------------------------------------------------------------
# Stage 1 — cold open
# ---------------------------------------------------------------------------


def _build_cold_open(
    beat_sequence: BeatSequence,
    route: Route,
    client: GlueClient,
    *,
    tour_input: TourInput,
    stop_idx: int,
) -> tuple[list[Sentence], set[str]]:
    """Cold open: prefer a stop_orientation beat; otherwise synthesize.

    Phase 7 (2026-04-29) added Area-level fallback: when the start POI
    has no stop_orientation beat, search the rest of the Route for a
    sibling POI that shares an Area with the start POI and carries one.
    The found beat is hoisted to the cold-open and added to
    ``consumed_beat_ids`` so it doesn't double-fire at its original
    stop. Falls through to SYNTHESIZED_OPENER only when no Area-mate
    carries an orientation beat either.

    Returns ``(sentences, consumed_beat_ids)``. The anchor-block stage
    skips any beat in ``consumed_beat_ids`` so cold-open content isn't
    emitted twice.
    """
    from .beat_select import find_area_orientation_beat  # avoid cycles

    poi_beats = beat_sequence.poi_beats
    first_stop = poi_beats[stop_idx]
    orientation = _find_orientation_beat(first_stop)
    if orientation is None:
        orientation = find_area_orientation_beat(beat_sequence, route, start_idx=stop_idx)
    sentences: list[Sentence] = []
    consumed: set[str] = set()

    # Pacing cue first: settle in.
    sentences.append(
        Sentence(
            text="Settle in.",
            source_id=GLUE_PACING,
            source_type="glue",
            stop_idx=stop_idx,
        )
    )

    if orientation is not None and orientation.script_body:
        sentences.extend(_beat_to_sentences(orientation, stop_idx))
        consumed.add(orientation.id)
    else:
        # SYNTHESIZED_OPENER fallback per Q7. Phase 7.5 (Fix 2)
        # composes the opener from real corpus data at the start POI:
        # Area name + pronunciation + a single physical_cue + an
        # optional sensory invitation if any beat has feature_type='view'.
        # Every phrase traces to a glue-whitelist token or an extracted
        # corpus field — no Haiku invention. Marked SYNTHESIZED_OPENER
        # so audits can prioritise stop_orientation back-fill.
        sentences.extend(_build_synthesized_opener(first_stop, route, tour_input, stop_idx))
        first_beat = next((b for b in first_stop.beats if b.script_body), None)
        if first_beat is not None:
            sentences.extend(_beat_to_sentences(first_beat, stop_idx))
            consumed.add(first_beat.id)

    return sentences, consumed


# Feature types whose cues are safe to read aloud as physical staging.
# 'view' and 'architectural_detail' are the strongest direct anchors;
# 'plaque' and 'adjacent_landmark' fall back when the stronger types
# are absent. 'interior' is excluded — it usually requires the listener
# to already be inside, which the cold-open can't guarantee.
_SYNTH_PRIMARY_FEATURE_TYPES: tuple[str, ...] = ("view", "architectural_detail")
_SYNTH_FALLBACK_FEATURE_TYPES: tuple[str, ...] = ("plaque", "adjacent_landmark")
_SYNTH_VIEW_FEATURE_TYPE: str = "view"


def _build_synthesized_opener(
    first_stop: POIBeats,
    route: Route,
    tour_input: TourInput,
    stop_idx: int,
) -> list[Sentence]:
    """Compose the Phase 7.5 SYNTHESIZED_OPENER block.

    Order:
      1. Area-anchored location line ("You're starting in the Marais.")
         from `route.spine_area`. Falls back to the POI name when
         spine_area is missing.
      2. Pronunciation, if any beat at the start POI carries one
         ("That's pronounced X.").
      3. A single physical_cue staging line. Picks the strongest cue
         (view / architectural_detail; plaque / adjacent_landmark
         fallback). "Look up at X." for view; "Notice X." otherwise.
      4. Sensory invitation if any beat has feature_type='view':
         "Take a moment to take it in."; otherwise the duration
         primer "We're going to walk for about N minutes."

    All composed sentences are marked with SYNTHESIZED_OPENER for
    source attribution; staging-style sentences additionally trace to
    GLUE_STAGING in the glue whitelist.
    """
    out: list[Sentence] = []
    poi_beats = list(first_stop.beats)

    # 1. Location anchor.
    location_text = _synth_location_anchor(first_stop, route)
    out.append(
        Sentence(
            text=location_text,
            source_id=SYNTHESIZED_OPENER,
            source_type="glue",
            stop_idx=stop_idx,
        )
    )

    # 2. Pronunciation if present.
    pronunciation_text = _synth_pronunciation(poi_beats, first_stop.poi_name)
    if pronunciation_text:
        out.append(
            Sentence(
                text=pronunciation_text,
                source_id=SYNTHESIZED_OPENER,
                source_type="glue",
                stop_idx=stop_idx,
            )
        )

    # 3. Physical staging from the strongest available cue.
    chosen_cue = _synth_pick_cue(poi_beats)
    has_view_cue = any(
        (cue.feature_type or "").lower() == _SYNTH_VIEW_FEATURE_TYPE
        for beat in poi_beats
        for cue in beat.physical_cues
    )
    if chosen_cue is not None:
        feature = (chosen_cue.feature_type or "").lower()
        cue_phrase = chosen_cue.cue.strip()
        if cue_phrase:
            staging_verb = "Look up at" if feature == _SYNTH_VIEW_FEATURE_TYPE else "Notice"
            out.append(
                Sentence(
                    text=f"{staging_verb} {cue_phrase}.",
                    source_id=GLUE_STAGING,
                    source_type="glue",
                    stop_idx=stop_idx,
                )
            )

    # 4. Sensory invitation OR duration primer.
    if has_view_cue:
        out.append(
            Sentence(
                text="Take a moment to take it in.",
                source_id=GLUE_STAGING,
                source_type="glue",
                stop_idx=stop_idx,
            )
        )
    else:
        out.append(
            Sentence(
                text=f"We're going to walk for about {tour_input.duration_min} minutes.",
                source_id=GLUE_PACING,
                source_type="glue",
                stop_idx=stop_idx,
            )
        )

    return out


def _synth_location_anchor(first_stop: POIBeats, route: Route) -> str:
    """Pick the Area-name line for the synthesized opener.

    Prefers `route.spine_area`. Falls back to the POI name when no
    spine has been computed (test fixtures without an Area).
    """
    spine = (route.spine_area or "").strip()
    if spine:
        article = _area_article(spine)
        return f"You're starting in {article}{spine}."
    return f"You're standing at {first_stop.poi_name}."


def _area_article(spine: str) -> str:
    """A small, deterministic article-prefix table for Paris Areas.

    "the Marais" / "the Île de la Cité" feel native; arrondissement
    numbers ("the 4th Arrondissement") want "the" too. Bare proper
    nouns ("Montmartre", "Saint-Germain-des-Prés") take no article.
    """
    s = spine.lower()
    if s.startswith("île ") or s.startswith("ile "):
        return "the "
    if "arrondissement" in s:
        return "the "
    if s.startswith("le ") or s.startswith("la ") or s.startswith("les "):
        return ""  # already carries the article
    if s in {"marais"}:
        return "the "
    return ""


def _synth_pronunciation(beats: list[BeatRef], poi_name: str) -> str | None:
    """Return a pronunciation glue line if any beat carries the field.

    Picks the longest non-empty pronunciation (richer phonetic detail
    is more useful aloud) and prefixes it with the POI-name target.
    """
    pronunciations = [
        (b.pronunciation or "").strip() for b in beats if (b.pronunciation or "").strip()
    ]
    if not pronunciations:
        return None
    chosen = max(pronunciations, key=len)
    # If the pronunciation already names the target, just emit it.
    if chosen.lower().startswith("that's pronounced"):
        if not chosen.endswith("."):
            chosen = chosen + "."
        return chosen
    return f"That's pronounced {chosen}."


def _synth_pick_cue(beats: list[BeatRef]):
    """Return the strongest physical_cue from a stop's beats, or None.

    Preference: view ≻ architectural_detail ≻ plaque ≻ adjacent_landmark.
    Within a category, the first cue encountered wins (stable order
    follows beat order, which is already deterministic).
    """
    for tier in (_SYNTH_PRIMARY_FEATURE_TYPES, _SYNTH_FALLBACK_FEATURE_TYPES):
        for ftype in tier:
            for beat in beats:
                for cue in beat.physical_cues:
                    if (cue.feature_type or "").lower() == ftype and cue.cue.strip():
                        return cue
    return None


def _find_orientation_beat(stop: POIBeats) -> BeatRef | None:
    """Return the first beat keyed as ``beat_type='stop_orientation'``.

    Phase 1 §1.4 inventoried 13 such beats in the live corpus and
    Phase 3.5 confirmed them: the field is ``beat_type`` (not
    ``narrative_function``). The lookup checks both for resilience —
    older corpus dumps used ``narrative_function`` for the same role.
    """
    for beat in stop.beats:
        if (beat.beat_type or "").lower() == "stop_orientation":
            return beat
        if (beat.narrative_function or "").lower() == "stop_orientation":
            return beat
    return None


# ---------------------------------------------------------------------------
# Stages 2-3 — anchor essay + circumnavigation
# ---------------------------------------------------------------------------


_TRANSIT_NARRATIVE_FUNCTIONS: frozenset[str] = frozenset({"transition", "transit", "navigation"})


def _build_anchor_block(
    stop: POIBeats,
    stop_idx: int,
    *,
    skip_beat_ids: set[str] | None = None,
) -> list[Sentence]:
    """Stream the pre-ordered beats; skip cold-open and transit-class beats.

    Phase 7: transit-class beats are routed only through ``_build_transit``
    after a direction check. When the check rejects a beat, it must NOT
    leak back into the anchor block (where the listener would hear an
    out-of-place navigation sentence). Always filter transit-class beats
    at the anchor stage; the transit stage is the only legitimate place
    for them.
    """
    skip = skip_beat_ids or set()
    out: list[Sentence] = []
    for beat in stop.beats:
        if beat.id in skip:
            continue
        if (beat.narrative_function or "").lower() in _TRANSIT_NARRATIVE_FUNCTIONS:
            continue
        out.extend(_beat_to_sentences(beat, stop_idx))
    return out


# ---------------------------------------------------------------------------
# Stage 4 — transit
# ---------------------------------------------------------------------------


def _build_transit(
    previous: POIBeats,
    current: POIBeats,
    route: Route,
    client: GlueClient,
    *,
    stop_idx: int,
    consumed_beat_ids: set[str] | None = None,
    vignette_beats: tuple[BeatRef, ...] = (),
) -> list[Sentence]:
    """Insert a corpus transit beat when present; otherwise a single glue nav.

    Phase 7 (2026-04-29) adds direction-awareness. Pre-existing transit
    beats encode an origin → destination direction inferred from their
    ``trigger_address`` + opening prose. Reusing them on routes that run
    the opposite direction (or start at unrelated POIs) produced
    geographically-broken openings in phase-6-rerun:

    - Tour 4 stop 3 opened "Starting at Invalides Metro station…" when
      the user was arriving from Pont de la Concorde.
    - Tour 3 stop 3 opened "Leave the Sacré-Cœur…" before the user had
      visited Sacré-Cœur.

    Phase 7 only accepts a corpus transit beat when the previous stop
    appears in its trigger_address or body (the beat "knows" we're
    coming from there). When no directional match exists, falls through
    to GLUE_NAV with explicit ``from X, walk to Y, distance approx Nm``
    context so the runtime can synthesize a coherent navigation
    instruction without inventing facts.

    ``consumed_beat_ids`` filters transit candidates so a beat already
    emitted earlier in the script (e.g. by `current`'s prior anchor
    block, or by a previous transit) isn't picked again. Without this,
    multi-anchor tours emitted the same transit beat 2-3 times.

    Track B (Step B.4): ``vignette_beats`` — the chosen walk-past beats for
    this leg (``BeatSequence.vignette_beats[stop_idx]``) — are voiced AFTER
    the transit beat/glue, one beat-cited one-liner each (the FIRST sentence
    of the beat's ``script_body``; corpus text, so no invention issue).
    Vignette beats are not POIBeats entries, so anchor blocks never see them.
    """
    consumed = consumed_beat_ids or set()
    # Prefer a transit beat at `current` whose origin matches `previous`
    # (the most common shape — transit beats describe arriving at their
    # POI from a named origin). Fall back to one at `previous` whose
    # destination matches `current` (less common; some guidebooks
    # attach the transit at the leaving POI).
    transit_beat = _find_directional_transit_beat(
        current, prev_name=previous.poi_name, consumed=consumed
    )
    if transit_beat is None:
        transit_beat = _find_directional_transit_beat(
            previous, dest_name=current.poi_name, consumed=consumed
        )
    if transit_beat is not None and transit_beat.script_body:
        out_sentences = _beat_to_sentences(transit_beat, stop_idx)
    else:
        distance_m = _segment_distance_m(route, stop_idx)
        distance_clause = f", distance approx {round(distance_m)}m" if distance_m else ""
        request = (
            f"From {previous.poi_name}, walk to {current.poi_name}{distance_clause}. "
            f"Use only navigation language — no facts, no names, no dates."
        )
        context = _format_glue_context(previous, current)
        out = client.stitch(GLUE_NAV, context, request)
        text = _coerce_glue_output(out, default=f"Walk on toward {current.poi_name}.")
        out_sentences = [
            Sentence(
                text=text,
                source_id=GLUE_NAV,
                source_type="glue",
                stop_idx=stop_idx,
            )
        ]
    out_sentences.extend(_vignette_one_liners(vignette_beats, stop_idx))
    return out_sentences


def _vignette_one_liners(
    vignette_beats: tuple[BeatRef, ...], stop_idx: int
) -> list[Sentence]:
    """One beat-cited sentence per walk-past vignette beat (Track B B.4).

    The FIRST sentence of the beat's ``script_body`` — verbatim corpus text
    attributed to the beat's own id, at the leg's ``stop_idx``. Beats with no
    body (callers should have filtered them — ``select_vignette_beats`` only
    picks voiceable beats) contribute nothing.
    """
    out: list[Sentence] = []
    for beat in vignette_beats:
        if not beat.script_body:
            continue
        sents = split_sentences(beat.script_body)
        if not sents:
            continue
        out.append(
            Sentence(
                text=sents[0],
                source_id=beat.id,
                source_type="beat",
                stop_idx=stop_idx,
            )
        )
    return out


def _segment_distance_m(route: Route, stop_idx: int) -> float:
    """Walking-segment distance (m) for the transit into stop ``stop_idx``.

    The Route carries a TransitSegment for every leg; the segment
    arriving at stop ``stop_idx`` is at index ``stop_idx`` because the
    first transit (idx 0) is start → first stop.
    """
    if 0 <= stop_idx < len(route.transits):
        return float(route.transits[stop_idx].distance_m)
    return 0.0


def _find_directional_transit_beat(
    stop: POIBeats,
    *,
    prev_name: str | None = None,
    dest_name: str | None = None,
    consumed: set[str] | None = None,
) -> BeatRef | None:
    """Return the first transit-class beat whose direction matches the segment.

    A transit beat at ``stop`` is acceptable iff at least one of
    ``prev_name`` / ``dest_name`` appears in its ``trigger_address`` or
    ``script_body`` (case-insensitive substring). Otherwise the beat's
    encoded direction does not match the actual route segment and
    using it would produce a geographically wrong opener.
    """
    skip = consumed or set()
    needles = [s for s in (prev_name, dest_name) if s]
    for beat in stop.beats:
        if beat.id in skip:
            continue
        nf = (beat.narrative_function or "").lower()
        if nf not in {"transition", "transit", "navigation"}:
            continue
        if not needles:
            return beat  # caller didn't ask for direction-awareness
        haystack = (f"{beat.trigger_address or ''} {beat.script_body or ''}").lower()
        if any(n.lower() in haystack for n in needles):
            return beat
    return None


def _find_transit_beat(stop: POIBeats, consumed: set[str] | None = None) -> BeatRef | None:
    """Phase 7 deprecated alias — kept for backward import compat."""
    return _find_directional_transit_beat(stop, consumed=consumed)


# ---------------------------------------------------------------------------
# Stage 5 — closing
# ---------------------------------------------------------------------------


def _build_closing(
    beat_sequence: BeatSequence,
    tour_input: TourInput,
    route: Route,
    client: GlueClient,
    *,
    stop_idx: int,
) -> list[Sentence]:
    """Physical-closure phrase. No thematic summary.

    Phase 7 (2026-04-29) removed the post-closing callback re-emission.
    ``reorder_final_stop_for_closing`` now lifts the closing-friendly
    beat to be the LAST beat at the final stop (preference order:
    callback > climax > longest body), and the anchor block emits it
    naturally at that position. The closing glue follows. Re-emitting
    the callback beat *after* the closing glue duplicated content.
    """
    out: list[Sentence] = []
    last = beat_sequence.poi_beats[-1] if beat_sequence.poi_beats else None

    if tour_input.round_trip and len(beat_sequence.poi_beats) == 1:
        # PdV-style square circumnavigation: the canonical Pariswalks closing.
        text = f"You've now circled {last.poi_name}." if last else "You've now finished the walk."
    elif tour_input.round_trip:
        text = "You've now completed the loop and are back where you started."
    else:
        text = "End the walk here, or carry on at your own pace."

    out.append(
        Sentence(
            text=text,
            source_id=GLUE_CLOSING,
            source_type="glue",
            stop_idx=stop_idx,
        )
    )
    return out


# ---------------------------------------------------------------------------
# Beat → sentences
# ---------------------------------------------------------------------------


def _beat_to_sentences(beat: BeatRef, stop_idx: int) -> list[Sentence]:
    if not beat.script_body:
        return []
    return [
        Sentence(text=s, source_id=beat.id, source_type="beat", stop_idx=stop_idx)
        for s in split_sentences(beat.script_body)
    ]


# ---------------------------------------------------------------------------
# Glue helpers
# ---------------------------------------------------------------------------


def _format_glue_context(previous: POIBeats, current: POIBeats) -> str:
    """A short context window for Haiku: last sentence of previous + first of next."""
    pieces: list[str] = []
    last_text = _tail_sentence(previous)
    if last_text:
        pieces.append(f"PREVIOUS STOP — {previous.poi_name}: {last_text}")
    head_text = _head_sentence(current)
    if head_text:
        pieces.append(f"NEXT STOP — {current.poi_name}: {head_text}")
    return "\n".join(pieces)


def _tail_sentence(stop: POIBeats) -> str:
    for beat in reversed(stop.beats):
        if beat.script_body:
            sents = split_sentences(beat.script_body)
            if sents:
                return sents[-1]
    return ""


def _head_sentence(stop: POIBeats) -> str:
    for beat in stop.beats:
        if beat.script_body:
            sents = split_sentences(beat.script_body)
            if sents:
                return sents[0]
    return ""


def _coerce_glue_output(raw: str, *, default: str) -> str:
    """Defang the LLM output: empty / sentinel → default; trim quotes."""
    if not raw:
        return default
    text = raw.strip().strip('"').strip("'").strip()
    if not text or NO_GLUE_SENTINEL in text:
        return default
    # Take only the first sentence in case Haiku emitted multiple.
    parts = split_sentences(text)
    candidate = parts[0] if parts else text
    if any(p in candidate.lower() for p in FORBIDDEN_PHRASES):
        return default
    return candidate


# ---------------------------------------------------------------------------
# Output rollup
# ---------------------------------------------------------------------------


def _flatten_pois(beat_sequence: BeatSequence, route: Route) -> tuple[ScriptPOI, ...]:
    """Build the selected_pois roster aligning Route POIs with their beats."""
    by_id = {pb.poi_id: pb for pb in beat_sequence.poi_beats}
    out: list[ScriptPOI] = []
    for poi in route.pois:
        plan = by_id.get(poi.id)
        beat_ids = tuple(b.id for b in plan.beats) if plan else ()
        out.append(
            ScriptPOI(
                id=poi.id,
                name=poi.name,
                tier=poi.tier,
                lat=poi.lat,
                lng=poi.lng,
                area=route.spine_area
                if route.spine_area in poi.areas
                else (poi.areas[0] if poi.areas else None),
                # C8: honest REPORTED minutes — tier dwell is a display floor
                # only; a beat-rich stop reports its real voiced length. Zero
                # route change (selection still books tier dwell until C9).
                dwell_seconds=max(
                    compute_dwell_seconds(poi.tier),
                    planned_audio_seconds(plan.beats) if plan else 0,
                ),
                beat_ids=beat_ids,
                # C9g: the governor's trimmed-off beats, surfaced for
                # keep-exploring (never silently dropped). Empty unless the cap
                # fired on this stop.
                overflow_beat_ids=beat_sequence.overflow_by_poi.get(poi.id, ()),
            )
        )
    return tuple(out)


def _lens_coverage(beat_sequence: BeatSequence) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for plan in beat_sequence.poi_beats:
        for beat in plan.beats:
            for lens in beat.lenses:
                counter[lens] += 1
    return dict(counter)


def _sum_audio(sentences: Iterable[Sentence], beat_sequence: BeatSequence) -> int:
    """Sum est_spoken_seconds across cited beats (deduped by beat_id),
    and add a flat 4 seconds per glue sentence (≈10 spoken words).

    Track B (B.4): a vignette voices only the FIRST sentence of its beat, so
    counting the whole beat's est_spoken_seconds would overcount — each
    vignette one-liner gets the same flat per-sentence estimate as glue.
    """
    vignette_ids = {b.id for beats in beat_sequence.vignette_beats.values() for b in beats}
    cited_ids: set[str] = set()
    glue_count = 0
    for s in sentences:
        if s.source_type == "beat" and s.source_id not in vignette_ids:
            cited_ids.add(s.source_id)
        else:
            glue_count += 1
    by_id = {b.id: b for plan in beat_sequence.poi_beats for b in plan.beats}
    total = 0
    for beat_id in cited_ids:
        beat = by_id.get(beat_id)
        if beat is None:
            continue
        total += beat_spoken_seconds(beat)
    total += glue_count * 4
    return total


__all__ = [
    "ARITH",
    "FORBIDDEN_PHRASES",
    "GLUE_CALLBACK",
    "GLUE_CLOSING",
    "GLUE_LABELS",
    "GLUE_NAV",
    "GLUE_PACING",
    "GLUE_REFLECTION",
    "GLUE_STAGING",
    "SYNTHESIZED_OPENER",
    "generate",
    "split_sentences",
]
