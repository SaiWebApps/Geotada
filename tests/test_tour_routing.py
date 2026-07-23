"""Phase 2 — routing.py: pace + haversine + dwell math."""

from __future__ import annotations

import math

import pytest

from src.tour.contract import POI, BeatRef
from src.tour.routing import (
    AUDIO_FRACTION,
    ERR_SHORT,
    HAVERSINE_CORRECTION,
    PACE_KMH,
    WALK_FRACTION,
    beat_spoken_seconds,
    compute_dwell_seconds,
    envelope_radius_m,
    err_short_total_seconds,
    governor_allowance_seconds,
    haversine_m,
    insertion_cost_seconds,
    pace_corrected_walk_seconds,
    planned_audio_seconds,
    summarise_route,
    target_audio_seconds,
    walk_budget_seconds,
)

# ---------------------------------------------------------------------------
# Haversine
# ---------------------------------------------------------------------------


def test_haversine_zero_when_same_point():
    assert haversine_m(48.85, 2.35, 48.85, 2.35) == 0.0


def test_haversine_symmetric():
    a = haversine_m(48.85, 2.35, 48.86, 2.36)
    b = haversine_m(48.86, 2.36, 48.85, 2.35)
    assert math.isclose(a, b, abs_tol=1e-6)


def test_haversine_paris_known_distance():
    # 0.01° latitude at Paris ≈ 1112 m. Reference value ±5m.
    d = haversine_m(48.85, 2.35, 48.86, 2.35)
    assert 1107 < d < 1117


def test_haversine_pdv_to_notre_dame():
    # Place des Vosges → Notre-Dame: roughly 1.1 km haversine.
    d = haversine_m(48.8555, 2.3656, 48.852966, 2.349902)
    assert 1100 < d < 1300


# ---------------------------------------------------------------------------
# Pace math
# ---------------------------------------------------------------------------


def test_pace_corrected_zero_distance():
    assert pace_corrected_walk_seconds(0) == 0


def test_pace_corrected_negative_clamps_to_zero():
    assert pace_corrected_walk_seconds(-100) == 0


def test_pace_corrected_1km_haversine():
    # 1000m x 1.35 = 1350m at 3 km/h (50 m/min) → 27 min = 1620s.
    secs = pace_corrected_walk_seconds(1000)
    assert secs == 1620


def test_pace_corrected_500m_haversine():
    # 500m x 1.35 = 675m at 50 m/min → 13.5 min = 810s.
    assert pace_corrected_walk_seconds(500) == 810


def test_pace_constants_lock():
    assert PACE_KMH == 3.0
    assert HAVERSINE_CORRECTION == 1.35
    assert ERR_SHORT == 0.83
    assert math.isclose(WALK_FRACTION + AUDIO_FRACTION, 1.0)


# ---------------------------------------------------------------------------
# Budgets
# ---------------------------------------------------------------------------


def test_err_short_60min():
    # 60 x 0.83 = 49.8 min x 60 = 2988s.
    assert err_short_total_seconds(60) == 2988


def test_walk_budget_60min():
    # 60 x 0.83 x 0.40 x 60 = 1195.2s → 1195.
    assert walk_budget_seconds(60) == 1195


def test_audio_budget_60min():
    # 60 x 0.83 x 0.60 x 60 = 1792.8s → 1793.
    assert target_audio_seconds(60) == 1793


def test_envelope_round_trip_is_half_of_one_way():
    one_way = envelope_radius_m(60, round_trip=False)
    rt = envelope_radius_m(60, round_trip=True)
    assert math.isclose(rt, one_way / 2, rel_tol=1e-9)


def test_envelope_60min_one_way_paris():
    # walk_min ≈ 19.92, x3 km/h / 1.35 → ~738m.
    r = envelope_radius_m(60, round_trip=False)
    assert 730 < r < 745


def test_envelope_zero_duration():
    assert envelope_radius_m(0, round_trip=False) == 0.0


# ---------------------------------------------------------------------------
# Dwell
# ---------------------------------------------------------------------------


def test_dwell_anchor_tiers_use_5min():
    assert compute_dwell_seconds(5) == 300
    assert compute_dwell_seconds(4) == 300


def test_dwell_pause_tier_3():
    assert compute_dwell_seconds(3) == 150


def test_dwell_walkby_tier_1_zero():
    assert compute_dwell_seconds(1) == 0


def test_dwell_unknown_tier_zero():
    assert compute_dwell_seconds(99) == 0


# ---------------------------------------------------------------------------
# summarise_route
# ---------------------------------------------------------------------------


def _poi(pid: str, lat: float, lng: float) -> POI:
    return POI(id=pid, name=pid, tier=5, poi_role="stop", lat=lat, lng=lng)


def test_summarise_route_empty():
    r = summarise_route(
        (), start_lat=48.0, start_lng=2.0, round_trip=False, duration_min=60, spine_area=None
    )
    assert r.pois == ()
    assert r.transits == ()
    assert r.total_walk_seconds == 0


def test_summarise_route_single_one_way_has_one_segment():
    r = summarise_route(
        [_poi("a", 48.86, 2.35)],
        start_lat=48.85,
        start_lng=2.35,
        round_trip=False,
        duration_min=60,
        spine_area="Le Marais",
    )
    assert len(r.transits) == 1
    assert r.transits[0].from_poi_id is None
    assert r.transits[0].to_poi_id == "a"
    assert r.spine_area == "Le Marais"


def test_summarise_route_round_trip_appends_return_segment():
    r = summarise_route(
        [_poi("a", 48.86, 2.35), _poi("b", 48.87, 2.36)],
        start_lat=48.85,
        start_lng=2.35,
        round_trip=True,
        duration_min=90,
        spine_area=None,
    )
    assert r.transits[-1].to_poi_id is None
    # 3 transits: start→a, a→b, b→start.
    assert len(r.transits) == 3


def test_summarise_route_totals_use_routed_time_and_distance_when_available():
    class _Routed:
        def route(self, *_coords):
            return (321, 456.5, "encoded-shape")

    r = summarise_route(
        [_poi("a", 48.86, 2.35)],
        start_lat=48.85,
        start_lng=2.35,
        round_trip=False,
        duration_min=60,
        spine_area=None,
        routing_client=_Routed(),
    )

    assert r.routed is True
    assert r.transits[0].leg_seconds == 321
    assert r.transits[0].leg_distance_m == 456.5
    assert r.total_walk_seconds == 321
    assert r.total_walk_distance_m == 456.5


# ---------------------------------------------------------------------------
# insertion_cost_seconds
# ---------------------------------------------------------------------------


def test_insertion_cost_picks_cheapest_position():
    # ordered: A (north), B (south). Candidate C is east of B → best to insert
    # after B (idx 2).
    a = _poi("A", 48.870, 2.350)
    b = _poi("B", 48.850, 2.350)
    c = _poi("C", 48.851, 2.380)
    extra, idx = insertion_cost_seconds(
        c, [a, b], start_lat=48.860, start_lng=2.350, round_trip=False
    )
    assert idx == 2
    assert extra > 0


def test_insertion_cost_empty_route_inserts_at_zero():
    extra, idx = insertion_cost_seconds(
        _poi("A", 48.86, 2.36),
        [],
        start_lat=48.85,
        start_lng=2.35,
        round_trip=False,
    )
    assert idx == 0
    assert extra > 0


# ---------------------------------------------------------------------------
# beat_spoken_seconds / planned_audio_seconds — the shared audio clock (C7)
# The single source of truth generation, reflection, and density now defer to.
# ---------------------------------------------------------------------------


def _beat(est: int = 0, wc: int = 0) -> BeatRef:
    return BeatRef(id="b", poi_id="p", est_spoken_seconds=est, word_count=wc)


def test_beat_spoken_seconds_prefers_positive_est_override():
    # est_spoken_seconds wins when > 0, even against a large word_count.
    assert beat_spoken_seconds(_beat(est=300, wc=100000)) == 300


def test_beat_spoken_seconds_word_count_fallback_150wpm():
    # est == 0 -> word_count at 150 wpm: 150 words = 60s; 375 words = 150s.
    assert beat_spoken_seconds(_beat(est=0, wc=150)) == 60
    assert beat_spoken_seconds(_beat(est=0, wc=375)) == 150


def test_beat_spoken_seconds_nonpositive_est_falls_through_to_word_count():
    # A non-positive est must NOT be used (density's historical > 0 guard, now
    # shared): it falls through to word_count. The live corpus has no negatives;
    # this pins the guard so a future negative never ships as spoken seconds.
    assert beat_spoken_seconds(_beat(est=-5, wc=150)) == 60
    assert beat_spoken_seconds(_beat(est=0, wc=150)) == 60


def test_beat_spoken_seconds_zero_when_both_empty():
    assert beat_spoken_seconds(_beat(est=0, wc=0)) == 0
    assert beat_spoken_seconds(_beat(est=-9, wc=0)) == 0


@pytest.mark.parametrize(
    "wc", [0, 1, 2, 3, 5, 7, 10, 37, 149, 150, 151, 999, 2042, 2286, 3154, 5000]
)
def test_beat_spoken_seconds_word_count_form_matches_density_2point5(wc: int):
    # BYTE-IDENTITY GUARD: the shared 150 wpm fallback (round(wc/150*60)) must
    # equal density's historical round(wc/2.5) for every word_count, or the
    # density gate (audio_capacity_s) would shift and reshape routes. Both are
    # 2*wc/5, which is never a rounding tie for integer wc.
    assert beat_spoken_seconds(_beat(est=0, wc=wc)) == round(wc / 2.5)


def test_planned_audio_seconds_sums_the_plan():
    beats = [_beat(est=300, wc=0), _beat(est=0, wc=150), _beat(est=0, wc=0)]
    assert planned_audio_seconds(beats) == 360  # 300 + 60 + 0
    assert planned_audio_seconds([]) == 0


# ---------------------------------------------------------------------------
# governor_allowance_seconds — the C9 per-stop share-governor allowance
# (ratified 2026-07-03: budget / min(3, d//10) = budget/3 for d>=30).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("d", [30, 45, 60, 90, 120])
def test_governor_allowance_is_budget_over_three_for_normal_durations(d: int):
    # d>=30 -> min(3, d//10)=3 -> allowance = target_audio_seconds(d)//3.
    assert governor_allowance_seconds(d) == target_audio_seconds(d) // 3


def test_governor_allowance_concrete_values():
    # 30-min budget 896 -> 298s (~5 min); 90-min budget 2689 -> 896s (~15 min).
    assert governor_allowance_seconds(30) == 298
    assert governor_allowance_seconds(90) == 896


def test_governor_allowance_divisor_floors_for_short_durations():
    # d<20 -> d//10 in {0,1} -> divisor floored at 1 -> allowance == full budget
    # (very short tours seat ~1 stop; no incidental cap needed). No ZeroDivision.
    assert governor_allowance_seconds(15) == target_audio_seconds(15)
    assert governor_allowance_seconds(5) == target_audio_seconds(5)
    # d in [20,29] -> d//10=2 -> budget/2.
    assert governor_allowance_seconds(25) == target_audio_seconds(25) // 2
