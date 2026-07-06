"""Within-POI beat ordering — §3.3 of phase-1-design.

Given a POI and its active beats, pick an ordering strategy and emit a
deterministic ordered list.

Phase 7.5 (2026-04-29) tightened the Area cold-open hoist
(`find_area_orientation_beat`): a sibling-POI orientation beat may only
hoist when (a) it is the start POI's own beat, (b) the beat carries no
physical_cues at all, or (c) the beat's source POI is within
`HOIST_PROXIMITY_M` of the start stop. Otherwise the cues describe a
different physical location and would land geographically dishonest at
the cold-open. Falls through to SYNTHESIZED_OPENER instead.

- "sub_location": building walk. Use fixtures.SUB_LOCATION_ORDER if
  curated; otherwise fall back to the (alphabetically stable) order of
  distinct sub_locations seen on the beats. Pick at most one beat per
  sub_location bucket. A trailing "no sub_location" beat may close.
- "trigger_address": square circumnavigation. Stable order by trigger
  address; one beat per address.
- "narrative_function": flat fallback. hook → establishing → deepen →
  climax -> callback (and any remaining), 4-6 beats.

Branch thresholds match phase-1-design.md: sub_location active when
≥3 distinct values populated on tier-5/4 anchors; trigger_address active
when ≥5 distinct values; otherwise flat.

Pure functions. No Neo4j. The Neo4j loader lives in selection.py.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable

from .contract import POI, BeatRef, BeatSequence, OrderingStrategy, POIBeats, Route
from .fixtures import sub_location_order_for
from .routing import beat_spoken_seconds

NARRATIVE_FUNCTION_ORDER: tuple[str, ...] = (
    "hook",
    "establishing",
    "deepen",
    "climax",
    "callback",
)

SUB_LOCATION_THRESHOLD: int = 3  # ≥3 distinct values → building walk
TRIGGER_ADDRESS_THRESHOLD: int = 5  # ≥5 distinct values → square circumnav
DEFAULT_FLAT_MIN: int = 4
# Phase 4 calibration (2026-04-29): bumped from 6 to 8. The empirical Île
# walk's Sainte-Chapelle (5 beats) + Île de la Cité (4 beats) lost
# fixture deepens to the 6-beat trim. 8 keeps all empirical anchor-flat
# beats while staying under the audio budget for 90-min tours
# (Île 8 anchors x ~4 extra-beat seconds is well within the 44-min budget).
DEFAULT_FLAT_MAX: int = 8
# Phase 4 calibration (2026-04-29): bumped from 2 to 3. The empirical
# Vert-Galant pause stop carries 3 beats (establishing + view + tarnished);
# the prior cap dropped the 'tarnished' deepen.
PAUSE_BEATS_MAX: int = 3  # tier-3 stop

# Phase 4 calibration (2026-04-29): when both sub_location and
# trigger_address meet their thresholds, pick the dominant primitive.
# §3.3 spec defined the two threshold tests but didn't prescribe a
# tie-break; the empirical Place des Vosges walk (6 sub_locs, 23
# trigger_addresses) demonstrated trigger should win when the address
# pool is much richer. Without this rule, sub_loc fires first and PdV
# emits ~8 beats instead of ~25. Conciergerie (6 sub_locs, 0 triggers)
# still uses sub_location because triggers don't meet threshold.

# B8-lite (Phase 3.5) — claim-level dedup. Runs after the per-strategy
# ordering and before tone-variety. Only beats that share at least one
# lens are eligible to collide; ``J`` is Jaccard on the tokenised set.
B8_JACCARD_THRESHOLD: float = 0.8

# Phase 7 (2026-04-29) recall-recalibration. Three known phase-6-rerun dup
# pairs all evaded the 0.8 entities/subject_tag thresholds:
#   Mesme Gallet  (de1377b4 / bf668074): entities J=0.500, subject_tag empty
#   Hugo affair   (b41d4c77 / a1833622): entities J=0.667, subject_tag empty
#   Pantheon-vow  (ee115ca8 / 142060a7): entities J=0.125 (Saint vs St.),
#                                        subject_tag empty
# Mesme/Hugo are paraphrases — caught by char-5-gram body Jaccard at 0.30.
# Pantheon entities don't canonicalize to a high Jaccard (the supporting
# casts diverge: Soufflot/Chateauroux vs Voltaire/Rousseau) but both leads
# carry the same year + lead-entity signature — caught by year-overlap +
# canonical-entity-overlap ≥ 2.
B8_CHAR_NGRAM_N: int = 5
B8_CHAR_NGRAM_THRESHOLD: float = 0.30
B8_CANONICAL_ENTITY_PAIR_MIN: int = 2  # min canonical-entity overlap for the year+entity signal

# Tie-breaker priority when two beats collide and beat-score is equal.
# Higher index wins (climax beats deepen, etc.).
_NARRATIVE_FUNCTION_PRIORITY: dict[str, int] = {
    "transition": 1,
    "callback": 2,
    "scene_setter": 3,
    "hook": 4,
    "establishing": 5,
    "deepen": 6,
    "climax": 7,
}


def choose_ordering_strategy(beats: Iterable[BeatRef]) -> OrderingStrategy:
    """Pick the spatial primitive to sequence by, per §3.3.

    Phase 4 calibration: when both primitives meet threshold, the one
    with more distinct values wins. PdV (6 sub_locs, 23 trigger_addrs)
    requires trigger_address to reproduce the empirical address-by-address
    circumnavigation; Conciergerie (6 sub_locs, 0 triggers) keeps
    sub_location because triggers fail the threshold gate.
    """
    sub_n = len({b.sub_location for b in beats if b.sub_location})
    trig_n = len({b.trigger_address for b in beats if b.trigger_address})
    if sub_n >= SUB_LOCATION_THRESHOLD and (trig_n < TRIGGER_ADDRESS_THRESHOLD or sub_n >= trig_n):
        return "sub_location"
    if trig_n >= TRIGGER_ADDRESS_THRESHOLD:
        return "trigger_address"
    if sub_n >= SUB_LOCATION_THRESHOLD:
        return "sub_location"
    return "narrative_function"


def select_poi_beats(
    poi: POI,
    beats: Iterable[BeatRef],
    *,
    interest_lenses: Iterable[str] | None = None,
    apply_cap: bool = True,
) -> POIBeats:
    """Order and trim a POI's beats per §3.3, returning the chosen plan.

    ``apply_cap=False`` (KE0, via :func:`select_poi_beats_full`) skips the flat
    per-tier trim so the FULL ordered plan is returned; the ordering is otherwise
    identical, so the capped plan is a prefix of the full one.
    """
    active = [b for b in beats if b.active_status == "active"]
    if not active:
        return POIBeats(
            poi_id=poi.id,
            poi_name=poi.name,
            ordering_strategy="narrative_function",
            beats=(),
        )

    interest = frozenset(s.lower() for s in (interest_lenses or []))
    strategy = choose_ordering_strategy(active)

    if strategy == "sub_location":
        ordered = _order_by_sub_location(poi, active, interest)
    elif strategy == "trigger_address":
        ordered = _order_by_trigger_address(active, interest)
    else:
        ordered = _order_by_narrative_function(poi, active, interest, apply_cap=apply_cap)

    # Phase 3.5: orientation is a cold-open primitive that competes
    # with anchor-class beats in the no_loc / no_addr slot under the
    # spatial strategies. When an orientation beat exists at the POI,
    # prepend the highest-scoring one so the cold-open lookup can find
    # it. Generation's consumed_in_cold_open set keeps it from being
    # double-emitted at stop 0.
    ordered = _hoist_orientation(ordered, active, interest)

    ordered = _apply_b8_lite_dedup(ordered, interest)
    ordered = _enforce_tone_variety(ordered)

    return POIBeats(
        poi_id=poi.id,
        poi_name=poi.name,
        ordering_strategy=strategy,
        beats=tuple(ordered),
    )


def select_poi_beats_full(
    poi: POI,
    beats: Iterable[BeatRef],
    *,
    interest_lenses: Iterable[str] | None = None,
) -> POIBeats:
    """KE0: the UNCAPPED beat plan — every active beat, ordered, no per-tier trim.

    Identical ordering/dedup/tone-variety to :func:`select_poi_beats` but without
    the flat cap, so ``select_poi_beats(...).beats`` is a PREFIX of this plan's
    beats. The tail beyond the capped output is a stop's "keep exploring here"
    extras — the beats the tour budget did not have room to voice.
    """
    return select_poi_beats(poi, beats, interest_lenses=interest_lenses, apply_cap=False)


def extra_beat_ids(
    poi: POI,
    beats: Iterable[BeatRef],
    voiced_ids: Iterable[str],
    *,
    interest_lenses: Iterable[str] | None = None,
) -> tuple[str, ...]:
    """KE1: the ordered ids of a stop's beats the tour did NOT voice.

    A stop's "keep exploring here" extras: the uncapped plan
    (:func:`select_poi_beats_full`) minus the beats already voiced in the tour
    (its ScriptPOI ``beat_ids``), in the SAME priority order — so the first
    extra is the most-important beat the budget had no room for. Empty when the
    tour voiced everything the stop had.
    """
    voiced = set(voiced_ids)
    full = select_poi_beats_full(poi, beats, interest_lenses=interest_lenses)
    return tuple(b.id for b in full.beats if b.id not in voiced)


def govern_poi_beats(
    plan: POIBeats, allowance_seconds: int | None
) -> tuple[POIBeats, tuple[str, ...]]:
    """Cap a POI's emitted plan to a per-stop audio allowance (C9 governor).

    ``allowance_seconds is None`` marks an EXEMPT stop (the start-anchor or the
    fixed-end-B / pulled endpoint): the plan passes through untouched with no
    overflow. Otherwise keep a PREFIX of the ordered beats whose cumulative
    voiced seconds (``routing.beat_spoken_seconds``) stay within the allowance;
    the FIRST beat is always kept (a stop must speak at least once, even if
    ``beats[0]`` alone exceeds the allowance — the ratified bounded one-beat
    overshoot). The remaining ordered beats are the keep-exploring overflow.
    Pure; does not re-order (preserves the cold-open -> body -> closer arc up to
    the cut).
    """
    if allowance_seconds is None or not plan.beats:
        return plan, ()
    cut = len(plan.beats)
    consumed = 0
    for i, beat in enumerate(plan.beats):
        secs = beat_spoken_seconds(beat)
        if i > 0 and consumed + secs > allowance_seconds:
            cut = i
            break
        consumed += secs
    if cut >= len(plan.beats):
        return plan, ()
    capped = plan.model_copy(update={"beats": plan.beats[:cut]})
    return capped, tuple(b.id for b in plan.beats[cut:])


# --- ordering strategies ----------------------------------------------------


def _order_by_sub_location(
    poi: POI,
    beats: list[BeatRef],
    interest: frozenset[str],
) -> list[BeatRef]:
    """Group by sub_location, pick best in each, sequence per fixture order."""
    by_loc: dict[str, list[BeatRef]] = defaultdict(list)
    no_loc: list[BeatRef] = []
    for b in beats:
        (no_loc if not b.sub_location else by_loc[b.sub_location]).append(b)

    curated = sub_location_order_for(poi.name)
    seen_locs = list(by_loc.keys())
    if curated is not None:
        # Order: curated entries that exist, in fixture order, then any
        # uncurated keys alphabetically. Stable + deterministic.
        ordered_keys = [k for k in curated if k in by_loc]
        leftover = sorted(k for k in seen_locs if k not in ordered_keys)
        ordered_keys.extend(leftover)
    else:
        ordered_keys = sorted(seen_locs)

    out: list[BeatRef] = []
    for key in ordered_keys:
        bucket = by_loc[key]
        out.append(_pick_best(bucket, interest))

    # Trailing "no sub_location" closer (§3.3 step 1, single closing thought).
    if no_loc:
        out.append(_pick_best(no_loc, interest))

    return out


def _order_by_trigger_address(
    beats: list[BeatRef],
    interest: frozenset[str],
) -> list[BeatRef]:
    """One beat per trigger_address, addresses in stable order."""
    by_addr: dict[str, list[BeatRef]] = defaultdict(list)
    no_addr: list[BeatRef] = []
    for b in beats:
        (no_addr if not b.trigger_address else by_addr[b.trigger_address]).append(b)

    ordered_keys = sorted(by_addr.keys(), key=_address_sort_key)

    out: list[BeatRef] = [_pick_best(by_addr[k], interest) for k in ordered_keys]
    if no_addr:
        out.append(_pick_best(no_addr, interest))
    return out


def _order_by_narrative_function(
    poi: POI,
    beats: list[BeatRef],
    interest: frozenset[str],
    *,
    apply_cap: bool = True,
) -> list[BeatRef]:
    """Flat tier-5/4 fallback or tier-3 pause selection.

    ``apply_cap=False`` (KE0) returns EVERY ordered beat with no per-tier trim —
    the uncapped plan whose tail beyond the capped output is the "keep exploring"
    extras. Ordering/scoring is identical, so ``capped == full[:cap]``.
    """
    by_fn: dict[str, list[BeatRef]] = defaultdict(list)
    for b in beats:
        by_fn[(b.narrative_function or "establishing")].append(b)

    out: list[BeatRef] = []
    for fn in NARRATIVE_FUNCTION_ORDER:
        bucket = by_fn.pop(fn, None)
        if bucket:
            bucket.sort(key=lambda b: _beat_score(b, interest), reverse=True)
            out.extend(bucket)

    # Anything with a non-canonical narrative_function falls in last.
    leftover: list[BeatRef] = []
    for bucket in by_fn.values():
        bucket.sort(key=lambda b: _beat_score(b, interest), reverse=True)
        leftover.extend(bucket)
    out.extend(leftover)

    if not apply_cap:
        return out  # KE0: uncapped — the full ordered plan

    if poi.tier == 3:
        out = out[:PAUSE_BEATS_MAX]
    elif poi.tier in (1, 2):
        # Walk-by: emit a single beat (selection.py decides whether to use it).
        out = out[:1]
    else:  # tier-5/4 flat fallback
        if len(out) > DEFAULT_FLAT_MAX:
            out = out[:DEFAULT_FLAT_MAX]
        elif out and len(out) < DEFAULT_FLAT_MIN:
            pass  # honest length — corpus is thin, deliver what's there

    return out


# --- scoring + helpers ------------------------------------------------------


def _pick_best(bucket: list[BeatRef], interest: frozenset[str]) -> BeatRef:
    return max(bucket, key=lambda b: _beat_score(b, interest))


def _beat_score(beat: BeatRef, interest: frozenset[str]) -> tuple:
    """Stable, deterministic beat score for tie-breaking.

    Returns a tuple sorted high→low: lens-match, length-class quality,
    word-count, and lastly id to break ties.
    """
    lens_match = 1 if interest and any(lens.lower() in interest for lens in beat.lenses) else 0
    length_rank = _length_class_rank(beat.beat_length_class)
    return (lens_match, length_rank, beat.word_count or beat.est_spoken_seconds, beat.id)


def _length_class_rank(value: str | None) -> int:
    return {
        "anchor": 4,
        "mid": 3,
        "seasoning": 2,
        "micro": 1,
    }.get((value or "").lower(), 0)


def _address_sort_key(addr: str) -> tuple:
    """Sort 'no. 1', 'no. 2', 'no. 13' numerically when prefix matches.

    Falls back to alphabetic for free-form addresses (e.g. '62 rue Saint-Antoine').
    """
    head_digits: list[str] = []
    for ch in addr:
        if ch.isdigit():
            head_digits.append(ch)
        elif head_digits or ch in (".", " "):
            if head_digits and not ch.isdigit():
                break
        else:
            continue
    n = int("".join(head_digits)) if head_digits else 10**9
    return (n, addr.lower())


def reorder_final_stop_for_closing(beat_sequence: BeatSequence) -> BeatSequence:
    """Move a closing-friendly beat to the last position at the final stop.

    Phase 7 (2026-04-29): the closing glue ("End the walk here, or carry
    on…") fires after the last beat of the last stop regardless of what
    that beat is. phase-6-rerun outputs ended mid-Tour-de-France-jersey
    (Tour 4) and mid-Mme-de-Motteville-zinger (Tour 1) because the
    closing glue followed whichever beat happened to land last in the
    spatial / narrative ordering.

    Preference: ``narrative_function='callback'`` > ``'climax'`` >
    longest beat by ``script_body`` length. The first match becomes the
    new closing slot; everything else preserves its order.

    No-op when the final stop has fewer than two beats or when the
    closing-friendly beat is already last.
    """
    if not beat_sequence.poi_beats:
        return beat_sequence
    last_plan = beat_sequence.poi_beats[-1]
    if len(last_plan.beats) < 2:
        return beat_sequence
    closing_idx = _find_closing_friendly_index(last_plan.beats)
    if closing_idx is None or closing_idx == len(last_plan.beats) - 1:
        return beat_sequence
    beats = list(last_plan.beats)
    moved = beats.pop(closing_idx)
    beats.append(moved)
    new_last = last_plan.model_copy(update={"beats": tuple(beats)})
    new_poi_beats = (*beat_sequence.poi_beats[:-1], new_last)
    return beat_sequence.model_copy(update={"poi_beats": new_poi_beats})


def _find_closing_friendly_index(beats: tuple[BeatRef, ...]) -> int | None:
    """Index of the most closing-friendly beat per Phase 7 preference.

    ``stop_orientation`` beats are excluded — they're cold-open
    primitives the per-POI hoist places at position 0; relocating one
    to the closing slot would land it after the cold open already
    emitted it AND give the close a "let me orient you" feel rather
    than a wrap-up.
    """
    eligible_indices = [
        i
        for i, b in enumerate(beats)
        if (b.beat_type or "").lower() != "stop_orientation"
        and (b.narrative_function or "").lower() != "stop_orientation"
    ]
    if not eligible_indices:
        return None
    for target in ("callback", "climax"):
        for i in eligible_indices:
            if (beats[i].narrative_function or "").lower() == target:
                return i
    # Fallback: longest body among eligibles. Avoids landing closing
    # glue on a one-line factoid and gives the close narrative weight.
    best_idx = eligible_indices[0]
    best_len = -1
    for i in eligible_indices:
        body_len = len(beats[i].script_body or "")
        if body_len > best_len:
            best_len = body_len
            best_idx = i
    return best_idx


HOIST_PROXIMITY_M: float = 100.0
"""Phase 7.5 cold-open hoist proximity gate (Fix 1).

A sibling-POI orientation beat may only hoist to the start stop when
the source POI is within this radius — otherwise the beat's
physical_cues describe somewhere else (Pariswalks PdV "children's
play area" landing at Hotel de Sully). 100 m matches the v3 schema's
geofence trigger radius, which is the natural notion of "same place".
"""


def select_vignette_beats(
    vignettes: dict[int, tuple[POI, ...]],
    beats_by_poi_id: dict[str, tuple[BeatRef, ...]],
    *,
    lenses: Iterable[str] | None = None,
) -> dict[int, tuple[BeatRef, ...]]:
    """Track B (Step B.4): ONE best voiceable beat per walk-past vignette POI.

    Builds ``BeatSequence.vignette_beats`` from ``Route.vignettes`` (Step B.2)
    + the corpus snapshot's ``beats_by_poi`` mapping. Per vignette POI: the
    first ACTIVE beat with a ``script_body``, preferring — when lenses are
    requested — one that carries a requested lens (the one-liner should speak
    to the user's genre when the corpus allows). A POI with no voiceable beat
    contributes nothing; a leg whose POIs all lack one is dropped. Beat order
    follows the vignette POI order (spotlight desc, then id — Step B.1).
    """
    interest = frozenset(s.lower() for s in (lenses or []))
    out: dict[int, tuple[BeatRef, ...]] = {}
    for leg_idx, pois in vignettes.items():
        chosen: list[BeatRef] = []
        for poi in pois:
            voiceable = [
                b
                for b in beats_by_poi_id.get(poi.id, ())
                if (b.active_status or "active") == "active" and b.script_body
            ]
            if not voiceable:
                continue
            lensed = next(
                (b for b in voiceable if any(ln.lower() in interest for ln in b.lenses)),
                None,
            )
            chosen.append(lensed if lensed is not None else voiceable[0])
        if chosen:
            out[leg_idx] = tuple(chosen)
    return out


def find_area_orientation_beat(
    beat_sequence: BeatSequence,
    route: Route,
    *,
    start_idx: int = 0,
    interest_lenses: Iterable[str] | None = None,
) -> BeatRef | None:
    """Search the Route for a stop_orientation beat that can hoist to cold-open.

    Phase 7 (2026-04-29): the per-POI hoist in ``select_poi_beats`` only
    surfaces an orientation beat when one exists at the start POI. Most
    tier-5 anchors (per phase-1-design §1.4) lack one, so the cold-open
    falls back to the SYNTHESIZED_OPENER even when a sibling POI in the
    same Area carries the canonical Pariswalks-format opener.

    Phase 7.5 (Fix 1, 2026-04-29) added a geographic-honesty guard. The
    Phase 7 hoist promoted any orientation beat from the same Area as
    the start stop, which produced Tour 1 stop 1 emitting the Pariswalks
    "find a bench in the garden, near the children's play area" beat at
    Hotel de Sully — those features exist at Place des Vosges (the
    sibling POI), not at the start. The refined rule accepts a
    candidate only when:

    - (a) the beat's POI matches the start POI (Phase 5 behaviour;
      preferred), OR
    - (b) the beat has no physical_cues at all (treat as Area-generic), OR
    - (c) the beat's source POI is within ``HOIST_PROXIMITY_M`` of the
      start stop (cues describe nearby features the listener can see).

    When no candidate passes, returns ``None`` — generation falls
    through to the SYNTHESIZED_OPENER, which is the geographically
    honest answer.
    """
    poi_beats = beat_sequence.poi_beats
    if not poi_beats or start_idx >= len(poi_beats):
        return None
    pois_by_id = {p.id: p for p in route.pois}
    start_poi = pois_by_id.get(poi_beats[start_idx].poi_id)
    if start_poi is None:
        return None
    start_areas = {a for a in start_poi.areas if a}
    if not start_areas:
        return None
    interest = frozenset(s.lower() for s in (interest_lenses or []))

    from .routing import haversine_m  # local import; no cycle risk

    candidates: list[BeatRef] = []
    for idx, plan in enumerate(poi_beats):
        if idx == start_idx:
            continue  # already searched per-POI; this is the cross-POI path
        peer = pois_by_id.get(plan.poi_id)
        if peer is None:
            continue
        if not (start_areas & {a for a in peer.areas if a}):
            continue
        peer_distance_m = haversine_m(start_poi.lat, start_poi.lng, peer.lat, peer.lng)
        for beat in plan.beats:
            is_orientation = (beat.beat_type or "").lower() == "stop_orientation" or (
                beat.narrative_function or ""
            ).lower() == "stop_orientation"
            if not is_orientation:
                continue
            if not _hoist_geographically_honest(
                beat,
                beat_poi_id=peer.id,
                start_poi_id=start_poi.id,
                peer_distance_m=peer_distance_m,
            ):
                continue
            candidates.append(beat)
    if not candidates:
        return None
    return _pick_best(candidates, interest)


def _hoist_geographically_honest(
    beat: BeatRef,
    *,
    beat_poi_id: str,
    start_poi_id: str,
    peer_distance_m: float,
) -> bool:
    """Phase 7.5 Fix 1 gate. See ``find_area_orientation_beat`` docstring."""
    if beat_poi_id == start_poi_id:
        return True  # same POI — original Phase 5 behaviour
    if not beat.physical_cues:
        return True  # no cues → Area-generic; safe to hoist
    return peer_distance_m <= HOIST_PROXIMITY_M


def _hoist_orientation(
    ordered: list[BeatRef],
    active: list[BeatRef],
    interest: frozenset[str],
) -> list[BeatRef]:
    """Surface a stop_orientation beat at the head when one exists.

    The cold-open in generation.py looks for a beat with
    ``beat_type='stop_orientation'``. Under the sub_location and
    trigger_address strategies, those beats land in the no-spatial-key
    bucket and lose the single closing slot to anchor-class beats.
    This hoist preserves the orientation beat as a head primitive so
    the cold-open lookup actually finds it. If the orientation beat is
    already in ``ordered``, it's moved (not duplicated) to position 0.
    """
    orientations = [b for b in active if (b.beat_type or "").lower() == "stop_orientation"]
    if not orientations:
        return ordered
    chosen = _pick_best(orientations, interest)
    rest = [b for b in ordered if b.id != chosen.id]
    return [chosen, *rest]


def _apply_b8_lite_dedup(beats: list[BeatRef], interest: frozenset[str]) -> list[BeatRef]:
    """Drop near-duplicate beats per phase-1-design §3.3.

    Two beats collide when they share at least one lens (or are both
    lensless) AND either entities Jaccard ≥ B8_JACCARD_THRESHOLD or
    subject_tag-token Jaccard ≥ threshold. On collision the loser is:

    1. lower beat-select score (the existing tuple);
    2. then shorter ``script_body``;
    3. then lower narrative_function priority
       (climax > deepen > establishing > hook > scene_setter
        > callback > transition).

    Survives in original order; this is paraphrase removal, not
    re-ordering.

    Logs a debug line via ``_DEDUP_TRACE`` when a drop fires so the
    smoke harness can audit which beats lost.
    """
    if len(beats) < 2:
        return beats

    drop_ids: set[str] = set()
    for i, a in enumerate(beats):
        if a.id in drop_ids:
            continue
        for b in beats[i + 1 :]:
            if b.id in drop_ids:
                continue
            if not _share_lens(a, b):
                continue
            if not _claims_collide(a, b):
                continue
            loser = _pick_dedup_loser(a, b, interest)
            drop_ids.add(loser.id)
            _DEDUP_TRACE.append(
                {
                    "kept": (a.id if loser is b else b.id),
                    "dropped": loser.id,
                    "entities_jaccard": _entities_jaccard(a, b),
                    "subject_tag_jaccard": _subject_tag_jaccard(a, b),
                }
            )

    return [b for b in beats if b.id not in drop_ids]


# Optional debug trace (per-process, cleared by ``reset_dedup_trace``).
# The smoke harness reads this so the user can see which paraphrase
# pairs collapsed without parsing logs.
_DEDUP_TRACE: list[dict] = []


def reset_dedup_trace() -> None:
    _DEDUP_TRACE.clear()


def get_dedup_trace() -> list[dict]:
    return list(_DEDUP_TRACE)


def _share_lens(a: BeatRef, b: BeatRef) -> bool:
    """Beats with no lens collide with each other; otherwise need an overlap."""
    set_a = {x.lower() for x in a.lenses if x}
    set_b = {x.lower() for x in b.lenses if x}
    if not set_a and not set_b:
        return True
    return bool(set_a & set_b)


def _claims_collide(a: BeatRef, b: BeatRef) -> bool:
    if _entities_jaccard(a, b) >= B8_JACCARD_THRESHOLD:
        return True
    if _subject_tag_jaccard(a, b) >= B8_JACCARD_THRESHOLD:
        return True
    # Phase 7: char-5-gram body Jaccard catches paraphrase pairs that
    # the entity threshold misses (Mesme Gallet, Hugo affair).
    if _char_ngram_jaccard(a, b) >= B8_CHAR_NGRAM_THRESHOLD:
        return True
    # Phase 7: same year + ≥2 shared canonical entities catches
    # "same founding story, divergent prose" pairs (Pantheon vow).
    return bool(_shares_year_and_canonical_entities(a, b))


def _entities_jaccard(a: BeatRef, b: BeatRef) -> float:
    set_a = {e.strip().lower() for e in a.entities if e and e.strip()}
    set_b = {e.strip().lower() for e in b.entities if e and e.strip()}
    return _jaccard(set_a, set_b)


def _subject_tag_jaccard(a: BeatRef, b: BeatRef) -> float:
    tokens_a = _tokenise(a.subject_tag)
    tokens_b = _tokenise(b.subject_tag)
    return _jaccard(tokens_a, tokens_b)


def _char_ngram_jaccard(a: BeatRef, b: BeatRef) -> float:
    """Character n-gram Jaccard on script_body.

    Catches paraphrases the entity-Jaccard misses — e.g., the Mesme
    Gallet / Hugo affair pairs where two extractors paraphrased the
    same anecdote at different lengths.
    """
    body_a = a.script_body or ""
    body_b = b.script_body or ""
    if not body_a or not body_b:
        return 0.0
    return _jaccard(_char_ngrams(body_a), _char_ngrams(body_b))


def _char_ngrams(s: str) -> set[str]:
    s = re.sub(r"\s+", " ", s.lower()).strip()
    n = B8_CHAR_NGRAM_N
    if len(s) < n:
        return {s} if s else set()
    return {s[i : i + n] for i in range(len(s) - n + 1)}


def _shares_year_and_canonical_entities(a: BeatRef, b: BeatRef) -> bool:
    """True iff both beats share at least one 4-digit year token in their
    script_body AND at least ``B8_CANONICAL_ENTITY_PAIR_MIN`` canonicalized
    entities. Targets the Pantheon-vow case where divergent supporting
    casts swamp the entity Jaccard but the lede ("In 1744, Louis XV …
    Saint Genevieve") is identical.

    Canonicalization: lowercase + ASCII-fold + strip leading sentence-
    starter words ("Built", "The") + normalise "Saint X" / "St. X" /
    "St X" to a single form so "Saint Genevieve" and "St. Geneviève"
    collide.
    """
    canon_a = _canonical_entities(a)
    canon_b = _canonical_entities(b)
    if len(canon_a & canon_b) < B8_CANONICAL_ENTITY_PAIR_MIN:
        return False
    years_a = _year_tokens(a.script_body)
    years_b = _year_tokens(b.script_body)
    return bool(years_a & years_b)


_LEADING_SENTENCE_STARTERS: frozenset[str] = frozenset(
    {"built", "the", "a", "an", "during", "by", "after", "upon", "since", "founded"}
)
_SAINT_TOKEN_NORMALISATION: dict[str, str] = {"st": "saint", "st.": "saint"}


def _canonical_entities(beat: BeatRef) -> set[str]:
    out: set[str] = set()
    for entity in beat.entities or ():
        canon = _canonicalise_entity(entity)
        if canon:
            out.add(canon)
    return out


def _canonicalise_entity(s: str | None) -> str | None:
    if not s:
        return None
    folded = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    folded = folded.lower().strip(" .,;:\"'")
    if not folded:
        return None
    parts = [p for p in folded.split() if p]
    # Strip a single leading sentence-starter (e.g., "Built" leaked from
    # an extractor's first-word capitalisation), but only when there's a
    # real entity word after it — never reduce a multi-token entity to nothing.
    if len(parts) > 1 and parts[0] in _LEADING_SENTENCE_STARTERS:
        parts = parts[1:]
    parts = [_SAINT_TOKEN_NORMALISATION.get(p, p) for p in parts]
    return " ".join(parts) if parts else None


def _year_tokens(text: str | None) -> set[str]:
    if not text:
        return set()
    return set(re.findall(r"\b(1[0-9]{3}|20[0-2][0-9])\b", text))


def _tokenise(s: str | None) -> set[str]:
    if not s:
        return set()
    return {t for t in (chunk.strip().lower() for chunk in s.split()) if t}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0  # neither has data → not a collision
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def _pick_dedup_loser(a: BeatRef, b: BeatRef, interest: frozenset[str]) -> BeatRef:
    """Return the beat to drop. Tie-breakers per §3.3 docstring above."""
    score_a = _beat_score(a, interest)
    score_b = _beat_score(b, interest)
    if score_a > score_b:
        return b
    if score_b > score_a:
        return a

    len_a = len(a.script_body or "")
    len_b = len(b.script_body or "")
    if len_a > len_b:
        return b
    if len_b > len_a:
        return a

    nf_a = _NARRATIVE_FUNCTION_PRIORITY.get((a.narrative_function or "").lower(), 0)
    nf_b = _NARRATIVE_FUNCTION_PRIORITY.get((b.narrative_function or "").lower(), 0)
    if nf_a > nf_b:
        return b
    if nf_b > nf_a:
        return a

    # Final stable fallback: drop the lexicographically-greater id so the
    # outcome is deterministic for tests.
    return b if a.id < b.id else a


def _enforce_tone_variety(beats: list[BeatRef]) -> list[BeatRef]:
    """Avoid 3 consecutive somber/reverent beats (rule 19).

    On a violation at position i (i, i-1, i-2 all somber/reverent),
    swap any non-somber beat from outside the violation window into
    position i-1 (the middle), which breaks the run regardless of which
    direction the relief comes from.
    """
    somber_registers = {"somber", "reverent"}

    def is_somber(b: BeatRef) -> bool:
        return (b.emotional_register or "").lower() in somber_registers

    out = list(beats)
    for _ in range(len(out) + 1):  # bounded fixpoint
        violation = None
        for i in range(2, len(out)):
            if is_somber(out[i - 2]) and is_somber(out[i - 1]) and is_somber(out[i]):
                violation = i
                break
        if violation is None:
            return out

        # Find any non-somber beat outside the violation window.
        swap_with = next(
            (
                j
                for j, b in enumerate(out)
                if not is_somber(b) and j not in {violation - 2, violation - 1, violation}
            ),
            None,
        )
        if swap_with is None:
            return out  # honest length — no relief available

        target = violation - 1
        out[target], out[swap_with] = out[swap_with], out[target]
    return out
