"""Within-POI beat ordering — §3.3 of phase-1-design.

Given a POI and its active beats, pick an ordering strategy and emit a
deterministic ordered list:

- "sub_location": building walk. Use fixtures.SUB_LOCATION_ORDER if
  curated; otherwise fall back to the (alphabetically stable) order of
  distinct sub_locations seen on the beats. Pick at most one beat per
  sub_location bucket. A trailing "no sub_location" beat may close.
- "trigger_address": square circumnavigation. Stable order by trigger
  address; one beat per address.
- "narrative_function": flat fallback. hook → establishing → deepen →
  climax → callback (and any remaining), 4–6 beats.

Branch thresholds match phase-1-design.md: sub_location active when
≥3 distinct values populated on tier-5/4 anchors; trigger_address active
when ≥5 distinct values; otherwise flat.

Pure functions. No Neo4j. The Neo4j loader lives in selection.py.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from .contract import POI, BeatRef, OrderingStrategy, POIBeats
from .fixtures import sub_location_order_for

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
DEFAULT_FLAT_MAX: int = 6
PAUSE_BEATS_MAX: int = 2  # tier-3 stop

# B8-lite (Phase 3.5) — claim-level dedup. Runs after the per-strategy
# ordering and before tone-variety. Only beats that share at least one
# lens are eligible to collide; ``J`` is Jaccard on the tokenised set.
B8_JACCARD_THRESHOLD: float = 0.8

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
    """Pick the spatial primitive to sequence by, per §3.3."""
    sub_locs = {b.sub_location for b in beats if b.sub_location}
    triggers = {b.trigger_address for b in beats if b.trigger_address}
    if len(sub_locs) >= SUB_LOCATION_THRESHOLD:
        return "sub_location"
    if len(triggers) >= TRIGGER_ADDRESS_THRESHOLD:
        return "trigger_address"
    return "narrative_function"


def select_poi_beats(
    poi: POI,
    beats: Iterable[BeatRef],
    *,
    interest_lenses: Iterable[str] | None = None,
) -> POIBeats:
    """Order and trim a POI's beats per §3.3, returning the chosen plan."""
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
        ordered = _order_by_narrative_function(poi, active, interest)

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
) -> list[BeatRef]:
    """Flat tier-5/4 fallback or tier-3 pause selection."""
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
    orientations = [
        b for b in active if (b.beat_type or "").lower() == "stop_orientation"
    ]
    if not orientations:
        return ordered
    chosen = _pick_best(orientations, interest)
    rest = [b for b in ordered if b.id != chosen.id]
    return [chosen, *rest]


def _apply_b8_lite_dedup(
    beats: list[BeatRef], interest: frozenset[str]
) -> list[BeatRef]:
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
    return False


def _entities_jaccard(a: BeatRef, b: BeatRef) -> float:
    set_a = {e.strip().lower() for e in a.entities if e and e.strip()}
    set_b = {e.strip().lower() for e in b.entities if e and e.strip()}
    return _jaccard(set_a, set_b)


def _subject_tag_jaccard(a: BeatRef, b: BeatRef) -> float:
    tokens_a = _tokenise(a.subject_tag)
    tokens_b = _tokenise(b.subject_tag)
    return _jaccard(tokens_a, tokens_b)


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


def _pick_dedup_loser(
    a: BeatRef, b: BeatRef, interest: frozenset[str]
) -> BeatRef:
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
    SOMBER = {"somber", "reverent"}

    def is_somber(b: BeatRef) -> bool:
        return (b.emotional_register or "").lower() in SOMBER

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
            (j for j, b in enumerate(out) if not is_somber(b) and j not in {violation - 2, violation - 1, violation}),
            None,
        )
        if swap_with is None:
            return out  # honest length — no relief available

        target = violation - 1
        out[target], out[swap_with] = out[swap_with], out[target]
    return out
