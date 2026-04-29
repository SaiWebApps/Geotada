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
from typing import Iterable

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
from .glue_client import GlueClient, MockGlueClient, NO_GLUE_SENTINEL
from .routing import compute_dwell_seconds

# ---------------------------------------------------------------------------
# Whitelisted glue labels — §3.5 of phase-1-design
# ---------------------------------------------------------------------------

GLUE_NAV: str = "GLUE_NAV"
GLUE_STAGING: str = "GLUE_STAGING"
GLUE_PACING: str = "GLUE_PACING"
GLUE_CALLBACK: str = "GLUE_CALLBACK"
GLUE_CLOSING: str = "GLUE_CLOSING"
ARITH: str = "ARITH"
SYNTHESIZED_OPENER: str = "SYNTHESIZED_OPENER"

GLUE_LABELS: frozenset[str] = frozenset(
    {GLUE_NAV, GLUE_STAGING, GLUE_PACING, GLUE_CALLBACK, GLUE_CLOSING, ARITH, SYNTHESIZED_OPENER}
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
    tail = s.rstrip(".!?\"'»)").rstrip().split()
    if not tail:
        return False
    return tail[-1].lower().rstrip(".") in _ABBREVIATIONS


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
    from .validation import validate_script  # avoid import cycle

    client = glue_client or MockGlueClient()
    sentences: list[Sentence] = []

    poi_beats = beat_sequence.poi_beats
    consumed_in_cold_open: set[str] = set()
    if poi_beats:
        cold_open_sents, consumed_in_cold_open = _build_cold_open(
            poi_beats[0], client, stop_idx=0
        )
        sentences.extend(cold_open_sents)

    for stop_idx, current in enumerate(poi_beats):
        if stop_idx > 0:
            previous = poi_beats[stop_idx - 1]
            sentences.extend(
                _build_transit(previous, current, route, client, stop_idx=stop_idx)
            )
        skip = consumed_in_cold_open if stop_idx == 0 else set()
        sentences.extend(_build_anchor_block(current, stop_idx, skip_beat_ids=skip))

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
        generated_at=(now or _dt.datetime.now(_dt.timezone.utc)).isoformat(),
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
    first_stop: POIBeats, client: GlueClient, *, stop_idx: int
) -> tuple[list[Sentence], set[str]]:
    """Cold open: prefer a stop_orientation beat; otherwise synthesize.

    Returns ``(sentences, consumed_beat_ids)``. The anchor-block stage
    skips any beat in ``consumed_beat_ids`` so cold-open content isn't
    emitted twice.
    """
    orientation = _find_orientation_beat(first_stop)
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
        # SYNTHESIZED_OPENER fallback per Q7: use the first beat's
        # physical anchoring without inventing claims. Marked
        # explicitly so the user can audit gap-fill priority.
        first_beat = next((b for b in first_stop.beats if b.script_body), None)
        sentences.append(
            Sentence(
                text=f"You're standing at {first_stop.poi_name}.",
                source_id=SYNTHESIZED_OPENER,
                source_type="glue",
                stop_idx=stop_idx,
            )
        )
        sentences.append(
            Sentence(
                text="Look around. Take it in.",
                source_id=GLUE_STAGING,
                source_type="glue",
                stop_idx=stop_idx,
            )
        )
        if first_beat is not None:
            sentences.extend(_beat_to_sentences(first_beat, stop_idx))
            consumed.add(first_beat.id)

    return sentences, consumed


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


def _build_anchor_block(
    stop: POIBeats,
    stop_idx: int,
    *,
    skip_beat_ids: set[str] | None = None,
) -> list[Sentence]:
    """Stream the pre-ordered beats; skip ones already emitted by cold-open."""
    skip = skip_beat_ids or set()
    out: list[Sentence] = []
    for beat in stop.beats:
        if beat.id in skip:
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
) -> list[Sentence]:
    """Insert a corpus transit beat when present; otherwise a single glue nav."""
    transit_beat = _find_transit_beat(previous) or _find_transit_beat(current)
    if transit_beat is not None and transit_beat.script_body:
        return _beat_to_sentences(transit_beat, stop_idx)

    request = (
        f"Connect from {previous.poi_name} to {current.poi_name}. "
        f"Use only navigation language — no facts, no names, no dates."
    )
    context = _format_glue_context(previous, current)
    out = client.stitch(GLUE_NAV, context, request)
    text = _coerce_glue_output(out, default=f"Walk on toward {current.poi_name}.")
    return [
        Sentence(
            text=text,
            source_id=GLUE_NAV,
            source_type="glue",
            stop_idx=stop_idx,
        )
    ]


def _find_transit_beat(stop: POIBeats) -> BeatRef | None:
    """Return the first beat whose narrative_function marks it as a transit."""
    for beat in stop.beats:
        nf = (beat.narrative_function or "").lower()
        if nf in {"transition", "transit", "navigation"}:
            return beat
    return None


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
    """Physical-closure phrase + optional callback beat. No thematic summary."""
    out: list[Sentence] = []
    last = beat_sequence.poi_beats[-1] if beat_sequence.poi_beats else None
    callback_beat: BeatRef | None = None
    if last is not None:
        for beat in last.beats:
            if (beat.narrative_function or "").lower() == "callback":
                callback_beat = beat
                break

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
    if callback_beat is not None and callback_beat.script_body:
        out.extend(_beat_to_sentences(callback_beat, stop_idx))
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
                area=route.spine_area if route.spine_area in poi.areas else (poi.areas[0] if poi.areas else None),
                dwell_seconds=compute_dwell_seconds(poi.tier),
                beat_ids=beat_ids,
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
    """
    cited_ids: set[str] = set()
    glue_count = 0
    for s in sentences:
        if s.source_type == "beat":
            cited_ids.add(s.source_id)
        else:
            glue_count += 1
    by_id = {b.id: b for plan in beat_sequence.poi_beats for b in plan.beats}
    total = 0
    for beat_id in cited_ids:
        beat = by_id.get(beat_id)
        if beat is None:
            continue
        if beat.est_spoken_seconds:
            total += beat.est_spoken_seconds
        elif beat.word_count:
            total += int(round(beat.word_count / 150 * 60))  # 150 wpm
    total += glue_count * 4
    return total


__all__ = [
    "generate",
    "split_sentences",
    "GLUE_LABELS",
    "GLUE_NAV",
    "GLUE_STAGING",
    "GLUE_PACING",
    "GLUE_CALLBACK",
    "GLUE_CLOSING",
    "ARITH",
    "SYNTHESIZED_OPENER",
    "FORBIDDEN_PHRASES",
]
