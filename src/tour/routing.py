"""Tour-builder routing math.

Constants and pure functions used by selection.py:

- haversine: great-circle distance in metres between (lat, lng) points.
- pace_corrected_walk_seconds: applies the ×1.35 Paris haversine correction
  on top of the 3 km/h walking pace.
- envelope_radius_m: the radius around `start` reachable inside the
  err-short walk budget.
- compute_dwell_seconds: per-tier expected stop dwell.
- order_route_greedy_nn: best-insertion ordering used by the greedy
  selection step (§3.2 marginal_route_cost).
- summarise_route: rolls up an ordered POI list into a Route shell with
  transit segments, walk distance, and walk-time totals.

Constants are exported as module-level so tests can pin them and so
selection.py reads identical values.
"""

from __future__ import annotations

import math
from typing import Iterable

from .contract import POI, Route, TransitSegment

# §3.2 / phase-1-design rule ledger 20–25.
PACE_KMH: float = 3.0
HAVERSINE_CORRECTION: float = 1.35
ERR_SHORT: float = 0.83
WALK_FRACTION: float = 0.40  # of err-short total
AUDIO_FRACTION: float = 0.60  # of err-short total
EARTH_RADIUS_M: float = 6_371_000.0

# Per-tier dwell defaults (§3.2 + rule 22). Values in seconds.
DWELL_SECONDS_BY_TIER: dict[int, int] = {
    5: 5 * 60,  # 4–6 min anchor → midpoint
    4: 5 * 60,
    3: 150,  # 2–3 min pause
    2: 60,  # walk-by gets a brief pause
    1: 0,  # pure walk-by
}


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in metres."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return EARTH_RADIUS_M * c


def pace_corrected_walk_seconds(haversine_distance_m: float) -> int:
    """Walking time in seconds for a haversine straight-line distance.

    Applies the ×1.35 correction so that a 1km haversine line takes
    1350m / (3000m/h) ≈ 27 minutes worth of walking.
    """
    if haversine_distance_m <= 0:
        return 0
    actual_distance_m = haversine_distance_m * HAVERSINE_CORRECTION
    speed_m_per_s = (PACE_KMH * 1000.0) / 3600.0
    return int(round(actual_distance_m / speed_m_per_s))


def envelope_radius_m(duration_min: int, *, round_trip: bool) -> float:
    """Reachable straight-line radius from the origin under the err-short budget.

    Derivation: walk_min = duration × 0.83 × 0.40. Effective straight-line
    distance is walk_min × (3 km/h) ÷ 1.35. Halve for round trips.
    """
    if duration_min <= 0:
        return 0.0
    walk_min = duration_min * ERR_SHORT * WALK_FRACTION
    straight_m = (walk_min * PACE_KMH * 1000.0) / 60.0 / HAVERSINE_CORRECTION
    return straight_m / 2.0 if round_trip else straight_m


def err_short_total_seconds(duration_min: int) -> int:
    return int(round(duration_min * ERR_SHORT * 60))


def target_audio_seconds(duration_min: int) -> int:
    return int(round(duration_min * ERR_SHORT * AUDIO_FRACTION * 60))


def walk_budget_seconds(duration_min: int) -> int:
    return int(round(duration_min * ERR_SHORT * WALK_FRACTION * 60))


def compute_dwell_seconds(tier: int) -> int:
    return DWELL_SECONDS_BY_TIER.get(tier, 0)


def insertion_cost_seconds(
    candidate: POI,
    ordered: list[POI],
    *,
    start_lat: float,
    start_lng: float,
    round_trip: bool,
) -> tuple[int, int]:
    """Return (best_extra_walk_seconds, best_insertion_index) for a candidate.

    Considers every position in the existing ordered list (start → … → end).
    For round-trip routes the path returns to the origin, so the closing leg
    is part of every cost evaluation.

    Used by routing-aware greedy selection (§3.2).
    """
    coords: list[tuple[float, float]] = [(start_lat, start_lng), *((p.lat, p.lng) for p in ordered)]
    if round_trip:
        coords.append((start_lat, start_lng))

    base_seconds = _path_walk_seconds(coords)
    best_extra: int | None = None
    best_idx: int = 0

    # Insertion positions: after each existing waypoint (including start),
    # but never after the closing-return-to-origin segment.
    insertable_positions = len(ordered) + 1
    for idx in range(insertable_positions):
        new_coords = coords[: idx + 1] + [(candidate.lat, candidate.lng)] + coords[idx + 1 :]
        extra = _path_walk_seconds(new_coords) - base_seconds
        if best_extra is None or extra < best_extra:
            best_extra = extra
            best_idx = idx

    return (best_extra if best_extra is not None else 0, best_idx)


def _path_walk_seconds(coords: list[tuple[float, float]]) -> int:
    total = 0
    for (lat1, lng1), (lat2, lng2) in zip(coords, coords[1:]):
        total += pace_corrected_walk_seconds(haversine_m(lat1, lng1, lat2, lng2))
    return total


def summarise_route(
    pois: Iterable[POI],
    *,
    start_lat: float,
    start_lng: float,
    round_trip: bool,
    duration_min: int,
    spine_area: str | None,
) -> Route:
    """Build a Route from an ordered POI list."""
    ordered = tuple(pois)
    transits: list[TransitSegment] = []
    prev_lat, prev_lng = start_lat, start_lng
    prev_id: str | None = None
    total_distance = 0.0

    for poi in ordered:
        d = haversine_m(prev_lat, prev_lng, poi.lat, poi.lng)
        secs = pace_corrected_walk_seconds(d)
        transits.append(
            TransitSegment(
                from_poi_id=prev_id,
                to_poi_id=poi.id,
                distance_m=d,
                walk_seconds=secs,
            )
        )
        total_distance += d
        prev_lat, prev_lng = poi.lat, poi.lng
        prev_id = poi.id

    if round_trip and ordered:
        d = haversine_m(prev_lat, prev_lng, start_lat, start_lng)
        secs = pace_corrected_walk_seconds(d)
        transits.append(
            TransitSegment(
                from_poi_id=prev_id,
                to_poi_id=None,
                distance_m=d,
                walk_seconds=secs,
            )
        )
        total_distance += d

    total_walk_seconds = sum(t.walk_seconds for t in transits)
    audio_budget = max(0, err_short_total_seconds(duration_min) - total_walk_seconds)
    return Route(
        pois=ordered,
        transits=tuple(transits),
        total_walk_distance_m=total_distance,
        total_walk_seconds=total_walk_seconds,
        audio_budget_seconds=audio_budget,
        spine_area=spine_area,
        target_audio_seconds=target_audio_seconds(duration_min),
        err_short_total_seconds=err_short_total_seconds(duration_min),
    )
