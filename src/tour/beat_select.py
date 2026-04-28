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
