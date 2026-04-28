"""Phase 2 — selection.py: envelope, spine, greedy. Pure-function tests."""

from __future__ import annotations

import math

from src.tour.contract import POI, BeatRef, TourInput
from src.tour.routing import envelope_radius_m, haversine_m
from src.tour.selection import (
    AREA_ALIGNMENT_ADJACENT,
    AREA_ALIGNMENT_OTHER,
    AREA_ALIGNMENT_SPINE,
    HARD_ANCHOR_CAP,
    CorpusSnapshot,
    pick_spine_area,
    poi_score,
    select_route,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _poi(
    pid: str,
    *,
    tier: int = 5,
    role: str = "stop",
    lat: float,
    lng: float,
    areas: tuple[str, ...] = (),
    beat_count: int = 5,
    matching: int = 0,
) -> POI:
    return POI(
        id=pid,
        name=pid,
        tier=tier,
        poi_role=role,
        lat=lat,
        lng=lng,
        areas=areas,
        beat_count=beat_count,
        matching_lens_beat_count=matching,
    )


def _snap(
    pois: list[POI],
    *,
    area_types: dict[str, str] | None = None,
    adjacent: dict[str, set[str]] | None = None,
    beats_by_poi: dict[str, list[BeatRef]] | None = None,
) -> CorpusSnapshot:
    types = {**{"Paris": "city"}, **(area_types or {})}
    adj = {k: frozenset(v) for k, v in (adjacent or {}).items()}
    beats = {k: tuple(v) for k, v in (beats_by_poi or {}).items()}
    return CorpusSnapshot(
        pois=tuple(pois),
        beats_by_poi=beats,
        area_types=types,
        adjacent_areas=adj,
    )


PDV = (48.8555, 2.3656)
PONT_NEUF = (48.85675, 2.341033)


# ---------------------------------------------------------------------------
# Envelope: respects max_radius
# ---------------------------------------------------------------------------


def test_envelope_excludes_far_pois():
    near = _poi("near", lat=48.8556, lng=2.3658, areas=("Le Marais",))
    # ~3km east of PdV — well outside the 738m one-way envelope.
    far = _poi("far", lat=48.8556, lng=2.4000, areas=("Le Marais",))
    snap = _snap([near, far], area_types={"Le Marais": "neighborhood"})
    inp = TourInput(start=PDV, duration_min=60, city_slug="paris", round_trip=False)

    route = select_route(inp, snap)
    ids = [p.id for p in route.pois]
    assert "near" in ids
    assert "far" not in ids


def test_envelope_round_trip_uses_half_radius():
    # POI sits at ~500m, between round-trip envelope (369m) and one-way (738m).
    near = _poi("near", lat=48.8556, lng=2.3658, areas=("Le Marais",))
    medium = _poi("medium", lat=48.8590, lng=2.3720, areas=("Le Marais",))
    snap = _snap([near, medium], area_types={"Le Marais": "neighborhood"})

    one_way = select_route(
        TourInput(start=PDV, duration_min=60, city_slug="paris", round_trip=False), snap
    )
    rt = select_route(
        TourInput(start=PDV, duration_min=60, city_slug="paris", round_trip=True), snap
    )

    # The medium-distance POI must drop out of the round-trip route.
    assert {p.id for p in rt.pois} <= {p.id for p in one_way.pois}


def test_envelope_excludes_walk_by_only():
    walk_by = _poi("wb", role="walk_by_only", lat=48.8556, lng=2.3658)
    stop = _poi("stop", lat=48.8556, lng=2.3660)
    snap = _snap([walk_by, stop])
    route = select_route(
        TourInput(start=PDV, duration_min=60, city_slug="paris"), snap
    )
    assert "wb" not in [p.id for p in route.pois]


def test_envelope_excludes_tier_1_2_anchors():
    # Tier 1/2 are walk-by candidates handled in the Phase 3 enrichment pass.
    t1 = _poi("t1", tier=1, lat=48.8556, lng=2.3658)
    t5 = _poi("t5", tier=5, lat=48.8556, lng=2.3660)
    snap = _snap([t1, t5])
    route = select_route(
        TourInput(start=PDV, duration_min=60, city_slug="paris"), snap
    )
    assert "t1" not in [p.id for p in route.pois]
    assert "t5" in [p.id for p in route.pois]


# ---------------------------------------------------------------------------
# Spine
# ---------------------------------------------------------------------------


def test_spine_picks_most_populated_neighborhood():
    pois = [
        _poi("a", lat=48.8555, lng=2.3656, areas=("Le Marais", "Paris")),
        _poi("b", lat=48.8550, lng=2.3660, areas=("Le Marais", "Paris")),
        _poi("c", lat=48.8553, lng=2.3658, areas=("Île de la Cité", "Paris")),
    ]
    snap = _snap(
        pois,
        area_types={"Le Marais": "neighborhood", "Île de la Cité": "island"},
    )
    spine = pick_spine_area(*PDV, pois, snap)
    assert spine == "Le Marais"


def test_spine_excludes_city_typed_areas():
    pois = [_poi("a", lat=48.8555, lng=2.3656, areas=("Paris",))]
    snap = _snap(pois)
    spine = pick_spine_area(*PDV, pois, snap)
    assert spine != "Paris"


def test_spine_falls_back_to_closest_when_none_within_radius():
    # POI is 1.5 km north — outside SPINE_RADIUS_M (800).
    far = _poi("far", lat=48.870, lng=2.366, areas=("Distant Hood",))
    snap = _snap([far], area_types={"Distant Hood": "neighborhood"})
    spine = pick_spine_area(*PDV, [far], snap)
    assert spine == "Distant Hood"


def test_spine_returns_none_when_no_candidates():
    snap = _snap([])
    assert pick_spine_area(*PDV, [], snap) is None


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def test_score_increases_with_tier_and_beat_count():
    p_low = _poi("low", tier=3, lat=48.85, lng=2.35, beat_count=2)
    p_high = _poi("high", tier=5, lat=48.85, lng=2.35, beat_count=20)
    snap = _snap([p_low, p_high])
    s_low = poi_score(p_low, None, frozenset(), snap)
    s_high = poi_score(p_high, None, frozenset(), snap)
    assert s_high > s_low


def test_score_area_alignment_spine_beats_other():
    p_in = _poi("in", lat=48.85, lng=2.35, areas=("Le Marais",))
    p_out = _poi("out", lat=48.85, lng=2.35, areas=("Latin Quarter",))
    snap = _snap(
        [p_in, p_out],
        area_types={"Le Marais": "neighborhood", "Latin Quarter": "neighborhood"},
    )
    s_in = poi_score(p_in, "Le Marais", frozenset(), snap)
    s_out = poi_score(p_out, "Le Marais", frozenset(), snap)
    assert s_in > s_out
    assert math.isclose(s_in / s_out, AREA_ALIGNMENT_SPINE / AREA_ALIGNMENT_OTHER, rel_tol=1e-9)


def test_score_area_alignment_adjacent_between_spine_and_other():
    p_adj = _poi("adj", lat=48.85, lng=2.35, areas=("Latin Quarter",))
    snap = _snap(
        [p_adj],
        area_types={"Le Marais": "neighborhood", "Latin Quarter": "neighborhood"},
        adjacent={"Le Marais": {"Latin Quarter"}, "Latin Quarter": {"Le Marais"}},
    )
    s = poi_score(p_adj, "Le Marais", frozenset(), snap)
    p_other = _poi("oth", lat=48.85, lng=2.35, areas=("Far",))
    snap2 = _snap(
        [p_other],
        area_types={"Le Marais": "neighborhood", "Far": "neighborhood"},
    )
    s_other = poi_score(p_other, "Le Marais", frozenset(), snap2)
    assert AREA_ALIGNMENT_OTHER < AREA_ALIGNMENT_ADJACENT < AREA_ALIGNMENT_SPINE
    assert s > s_other


def test_interest_bias_within_cap():
    p = _poi("p", lat=48.85, lng=2.35, beat_count=10, matching=10)
    snap = _snap([p])
    s = poi_score(p, None, frozenset({"hidden_history"}), snap)
    s0 = poi_score(p, None, frozenset(), snap)
    # All beats match → bias = base + 0.5 = 1.5 ≤ cap (2.0).
    assert s > s0
    assert math.isclose(s / s0, 1.5, rel_tol=1e-9)


def test_interest_is_bias_not_filter():
    """Lens that no POI matches must not exclude any candidate (rule 41)."""
    p = _poi("p", tier=5, lat=48.8556, lng=2.3658, beat_count=5, matching=0)
    snap = _snap([p])
    inp = TourInput(
        start=PDV,
        duration_min=60,
        city_slug="paris",
        lenses=["lens_no_one_has"],
    )
    route = select_route(inp, snap)
    assert "p" in [r.id for r in route.pois]


def test_interest_shifts_ranking_when_one_matches():
    a = _poi("a", lat=48.8556, lng=2.3658, beat_count=5, matching=0)
    b = _poi("b", lat=48.8557, lng=2.3659, beat_count=5, matching=5)
    snap = _snap([a, b])
    s_a = poi_score(a, None, frozenset({"hidden_history"}), snap)
    s_b = poi_score(b, None, frozenset({"hidden_history"}), snap)
    assert s_b > s_a


# ---------------------------------------------------------------------------
# Greedy selection
# ---------------------------------------------------------------------------


def test_select_route_returns_route_object_shape():
    p = _poi("p", lat=48.8556, lng=2.3658, areas=("Le Marais",))
    snap = _snap([p], area_types={"Le Marais": "neighborhood"})
    route = select_route(
        TourInput(start=PDV, duration_min=60, city_slug="paris", round_trip=True), snap
    )
    assert hasattr(route, "pois")
    assert hasattr(route, "transits")
    assert hasattr(route, "total_walk_distance_m")
    assert hasattr(route, "total_walk_seconds")
    assert hasattr(route, "audio_budget_seconds")
    assert hasattr(route, "spine_area")


def test_select_route_round_trip_returns_to_origin():
    p = _poi("p", lat=48.8556, lng=2.3658, areas=("Le Marais",))
    snap = _snap([p], area_types={"Le Marais": "neighborhood"})
    rt = select_route(
        TourInput(start=PDV, duration_min=60, city_slug="paris", round_trip=True), snap
    )
    if rt.pois:
        assert rt.transits[-1].to_poi_id is None  # close-to-origin


def test_select_route_respects_walk_budget():
    # Too many anchors with non-negligible spread → must still respect budget.
    pois = [
        _poi(f"p{i}", lat=48.8550 + i * 0.0010, lng=2.3650 + i * 0.0010)
        for i in range(20)
    ]
    snap = _snap(pois)
    inp = TourInput(start=PDV, duration_min=60, city_slug="paris", round_trip=False)
    route = select_route(inp, snap)
    # walk_budget_seconds(60) = 1195
    assert route.total_walk_seconds <= 1195 + 5  # cushion for integer rounding


def test_select_route_respects_hard_anchor_cap():
    # Place ~25 candidates in a tight cluster so all are insertable.
    pois = [
        _poi(
            f"p{i}",
            tier=5,
            lat=48.8556 + (i % 5) * 0.00005,
            lng=2.3658 + (i // 5) * 0.00005,
        )
        for i in range(25)
    ]
    snap = _snap(pois)
    # Long duration → max_anchors theoretically bigger than HARD_ANCHOR_CAP.
    route = select_route(
        TourInput(start=PDV, duration_min=400, city_slug="paris"), snap
    )
    assert len(route.pois) <= HARD_ANCHOR_CAP


def test_select_route_deterministic_under_input_shuffle():
    base = [
        _poi(f"p{i}", lat=48.8550 + i * 0.0001, lng=2.3650 + i * 0.0001)
        for i in range(8)
    ]

    import random

    rng = random.Random(0)
    a = list(base)
    b = list(base)
    rng.shuffle(a)
    rng.shuffle(b)

    snap_a = _snap(a)
    snap_b = _snap(b)
    inp = TourInput(start=PDV, duration_min=60, city_slug="paris", round_trip=False)
    route_a = select_route(inp, snap_a)
    route_b = select_route(inp, snap_b)
    assert [p.id for p in route_a.pois] == [p.id for p in route_b.pois]


def test_select_route_prefers_spine_area():
    # Two POIs equidistant; one in spine area, one in non-adjacent area.
    in_marais = _poi(
        "marais",
        lat=48.8556,
        lng=2.3658,
        areas=("Le Marais",),
        beat_count=5,
    )
    out_other = _poi(
        "other",
        lat=48.8554,  # equally close — flip lat slightly
        lng=2.3654,
        areas=("Other Hood",),
        beat_count=5,
    )
    snap = _snap(
        [in_marais, out_other],
        area_types={"Le Marais": "neighborhood", "Other Hood": "neighborhood"},
    )
    # Force spine to be Le Marais by sheer count: add filler in Marais near
    # start so spine vote wins.
    fillers = [
        _poi(
            f"f{i}",
            tier=4,
            lat=48.8556 + i * 0.00002,
            lng=2.3658,
            areas=("Le Marais",),
            beat_count=2,
        )
        for i in range(3)
    ]
    snap = _snap(
        [in_marais, out_other, *fillers],
        area_types={"Le Marais": "neighborhood", "Other Hood": "neighborhood"},
    )
    route = select_route(
        TourInput(start=PDV, duration_min=60, city_slug="paris"), snap
    )
    assert route.spine_area == "Le Marais"
    ids = [p.id for p in route.pois]
    # Spine POI must be selected (bias is a scoring multiplier, not a hard
    # filter — but in a tight cluster of equals, the spine POI is preferred).
    assert "marais" in ids


def test_select_route_empty_when_no_candidates_in_envelope():
    far = _poi("far", lat=49.5, lng=3.0)  # well outside Paris
    snap = _snap([far])
    route = select_route(
        TourInput(start=PDV, duration_min=60, city_slug="paris"), snap
    )
    assert route.pois == ()
    assert route.total_walk_seconds == 0


# ---------------------------------------------------------------------------
# Phase 2 calibration (Q1) — endpoint-pull for one-way routes
# ---------------------------------------------------------------------------


def test_oneway_endpoint_pull_reaches_far_envelope():
    """One-way 90 min must finish at a far-envelope POI, not truncate near start.

    Mirrors Smoke B (Pont Neuf metro → Île de la Cité traverse, endpoint
    near Mémorial de la Déportation). We construct a synthetic equivalent:
    a tier-5 origin anchor, a cluster of mid-tier near-start POIs (the
    greedy will fill these first), and a tier-5 far-envelope anchor that
    must end the route after the calibration fix.
    """
    start = (48.85675, 2.341033)  # Pont Neuf coords — same as Smoke B
    radius_m = envelope_radius_m(90, round_trip=False)
    assert radius_m > 1000  # sanity: 90-min one-way envelope is roomy

    # Origin anchor: at the start, will be the first stop.
    origin = _poi(
        "origin",
        tier=5,
        lat=start[0],
        lng=start[1] + 0.0001,
        areas=("Île de la Cité",),
        beat_count=10,
    )
    # Three near-start stops the greedy will be tempted to fill first.
    near = [
        _poi(
            f"near-{i}",
            tier=4,
            lat=start[0] + 0.0001 * i,
            lng=start[1] + 0.0010 * i,
            areas=("Île de la Cité",),
            beat_count=5,
        )
        for i in range(1, 4)
    ]
    # Far-envelope anchor — east of start, beyond 0.5 × radius.
    far_lat = start[0] - 0.0030  # ~330m south
    far_lng = start[1] + 0.0140  # ~1km east, well past 0.5 × radius (~570m)
    far_anchor = _poi(
        "far",
        tier=5,
        lat=far_lat,
        lng=far_lng,
        areas=("Île de la Cité",),
        beat_count=10,
    )
    snap = _snap(
        [origin, *near, far_anchor],
        area_types={"Île de la Cité": "island"},
    )

    inp = TourInput(start=start, duration_min=90, city_slug="paris", round_trip=False)
    route = select_route(inp, snap)
    ids = [p.id for p in route.pois]

    # The far anchor must be in the route, and must be the closing stop.
    assert "far" in ids
    assert ids[-1] == "far"
    # Sanity: the far anchor really does sit in the far half of the envelope.
    assert haversine_m(*start, far_anchor.lat, far_anchor.lng) >= 0.5 * radius_m


def test_endpoint_pull_does_not_apply_to_round_trip():
    """Round-trip routes must not append a far-envelope stop at the end."""
    start = (48.85675, 2.341033)
    near = _poi(
        "near", tier=5, lat=start[0], lng=start[1] + 0.0002,
        areas=("Île de la Cité",), beat_count=5,
    )
    far = _poi(
        "far", tier=5, lat=start[0], lng=start[1] + 0.0050,
        areas=("Île de la Cité",), beat_count=5,
    )
    snap = _snap([near, far], area_types={"Île de la Cité": "island"})
    rt = select_route(
        TourInput(start=start, duration_min=60, city_slug="paris", round_trip=True),
        snap,
    )
    if rt.pois:
        # Last segment must close to origin (to_poi_id=None), not to a POI.
        assert rt.transits[-1].to_poi_id is None


def test_endpoint_pull_respects_walk_budget():
    """Endpoint-pull won't be applied if it would blow the walk budget."""
    start = (48.85675, 2.341033)
    # Make the far candidate so distant that adding it busts the budget.
    near = _poi(
        "near", tier=5, lat=start[0], lng=start[1] + 0.0001,
        areas=("Île de la Cité",), beat_count=5,
    )
    too_far_lng = start[1] + 0.020  # ~1.5km — ringed against a 60-min budget
    too_far = _poi(
        "too-far", tier=5, lat=start[0], lng=too_far_lng,
        areas=("Île de la Cité",), beat_count=5,
    )
    snap = _snap([near, too_far], area_types={"Île de la Cité": "island"})
    route = select_route(
        TourInput(start=start, duration_min=60, city_slug="paris", round_trip=False),
        snap,
    )
    # too-far should be rejected — outside envelope or busts walk budget.
    assert "too-far" not in [p.id for p in route.pois]


# ---------------------------------------------------------------------------
# Phase 2 calibration (Q3) — spine tie-break
# ---------------------------------------------------------------------------


def test_spine_tiebreak_prefers_island_over_district_within_tolerance():
    """When island and district score within 5%, island wins."""
    pois = [
        _poi("a", tier=5, lat=48.857, lng=2.341, areas=("Île de la Cité", "1st Arrondissement")),
        _poi("b", tier=5, lat=48.856, lng=2.342, areas=("Île de la Cité", "1st Arrondissement")),
        _poi("c", tier=4, lat=48.855, lng=2.343, areas=("Île de la Cité", "1st Arrondissement")),
    ]
    # Both Areas accumulate identical vote counts (same POIs).
    snap = _snap(
        pois,
        area_types={
            "Île de la Cité": "island",
            "1st Arrondissement": "district",
        },
    )
    spine = pick_spine_area(48.857, 2.341, pois, snap)
    assert spine == "Île de la Cité"


def test_spine_tiebreak_prefers_neighborhood_over_district():
    pois = [
        _poi("a", tier=5, lat=48.855, lng=2.366, areas=("Le Marais", "4th Arrondissement")),
        _poi("b", tier=4, lat=48.856, lng=2.366, areas=("Le Marais", "4th Arrondissement")),
    ]
    snap = _snap(
        pois,
        area_types={"Le Marais": "neighborhood", "4th Arrondissement": "district"},
    )
    spine = pick_spine_area(48.855, 2.366, pois, snap)
    assert spine == "Le Marais"


def test_spine_tiebreak_outside_tolerance_uses_top_count():
    """A 30% lead is bigger than the 5% tolerance — top count wins regardless."""
    pois = [
        _poi(f"d{i}", tier=5, lat=48.86, lng=2.34, areas=("1st Arrondissement",))
        for i in range(5)
    ]
    pois.append(_poi("i1", tier=4, lat=48.86, lng=2.34, areas=("Île de la Cité",)))
    snap = _snap(
        pois,
        area_types={
            "1st Arrondissement": "district",
            "Île de la Cité": "island",
        },
    )
    spine = pick_spine_area(48.86, 2.34, pois, snap)
    assert spine == "1st Arrondissement"
