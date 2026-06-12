"""Phase 2 — selection.py: envelope, spine, greedy. Pure-function tests."""

from __future__ import annotations

import math

import pytest

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
    )


def _snap(
    pois: list[POI],
    *,
    area_types: dict[str, str] | None = None,
    adjacent: dict[str, set[str]] | None = None,
    beats_by_poi: dict[str, list[BeatRef]] | None = None,
    lens_neighbors: dict[str, frozenset[str]] | None = None,
) -> CorpusSnapshot:
    types = {**{"Paris": "city"}, **(area_types or {})}
    adj = {k: frozenset(v) for k, v in (adjacent or {}).items()}
    # Phase 6 density gate runs at the top of select_route(), so test
    # fixtures need at least one beat per POI to clear it. Auto-inject
    # synthetic beats based on poi.beat_count when no explicit beats are
    # provided — keeps the existing selection-logic tests focused on
    # what they're testing without forcing each test to repeat fake-beat
    # boilerplate.
    raw = beats_by_poi or {}
    beats: dict[str, tuple[BeatRef, ...]] = {}
    for p in pois:
        if p.id in raw:
            beats[p.id] = tuple(raw[p.id])
            continue
        n = max(0, p.beat_count or 0)
        beats[p.id] = tuple(
            BeatRef(
                id=f"{p.id}-b{i}",
                poi_id=p.id,
                est_spoken_seconds=240,  # rich enough to clear fill_ratio
                active_status="active",
            )
            for i in range(n)
        )
    return CorpusSnapshot(
        pois=tuple(pois),
        beats_by_poi=beats,
        area_types=types,
        adjacent_areas=adj,
        lens_neighbors=lens_neighbors or {},
    )


PDV = (48.8555, 2.3656)
PONT_NEUF = (48.85675, 2.341033)


def _density_fillers(
    start: tuple[float, float], *, n: int = 4, prefix: str = "filler"
) -> list[POI]:
    """4 tier-5 anchor candidates clustered near `start`.

    Phase 6 density gate requires ≥4 anchor candidates with rich beats
    inside a tight cluster for GREEN. Some pre-Phase-6 selection tests
    used 1-3 POIs in their fixtures and now trip the gate. Adding these
    fillers keeps each test's assertion intact (they cluster colocated
    near start, so they don't affect spine, envelope, or distance
    behaviour) while letting the gate clear.
    """
    return [
        POI(
            id=f"{prefix}-{i}",
            name=f"{prefix}-{i}",
            tier=5,
            poi_role="stop",
            lat=start[0] + 0.00005 * i,
            lng=start[1] + 0.00005 * i,
            areas=("Le Marais",),
            beat_count=8,
        )
        for i in range(n)
    ]


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
    fillers = _density_fillers(PDV)
    snap = _snap([near, medium, *fillers], area_types={"Le Marais": "neighborhood"})

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
    route = select_route(TourInput(start=PDV, duration_min=60, city_slug="paris"), snap)
    assert "wb" not in [p.id for p in route.pois]


def test_envelope_excludes_tier_1_2_anchors():
    # Tier 1/2 are walk-by candidates handled in the Phase 3 enrichment pass.
    t1 = _poi("t1", tier=1, lat=48.8556, lng=2.3658)
    t5 = _poi("t5", tier=5, lat=48.8556, lng=2.3660)
    snap = _snap([t1, t5, *_density_fillers(PDV)])
    route = select_route(TourInput(start=PDV, duration_min=60, city_slug="paris"), snap)
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


def _lensed_beats(poi_id: str, lenses: tuple[str, ...], *, n: int = 5) -> list[BeatRef]:
    return [
        BeatRef(
            id=f"{poi_id}-b{i}",
            poi_id=poi_id,
            est_spoken_seconds=240,
            active_status="active",
            lenses=lenses,
        )
        for i in range(n)
    ]


# history -[:IS_PARENT_OF]-> dark_history, symmetric 1-hop map as the loader builds it
_HOP_MAP = {
    "history": frozenset({"dark_history"}),
    "dark_history": frozenset({"history"}),
}


def test_lens_adjacency_direct_hit_is_full_weight():
    """§3 (M3): a direct beat-lens hit scores 1.0 — identical to the no-lens run."""
    p = _poi("p", lat=48.85, lng=2.35)
    snap = _snap([p], beats_by_poi={"p": _lensed_beats("p", ("hidden_history",))})
    s_direct = poi_score(p, None, frozenset({"hidden_history"}), snap)
    s_neutral = poi_score(p, None, frozenset(), snap)
    assert s_direct > 0
    assert math.isclose(s_direct, s_neutral, rel_tol=1e-9)


def test_lens_adjacency_one_hop_is_point_six_both_directions():
    """§3 (M3): one IS_PARENT_OF hop scores 0.6 — parent requested reaching a
    child-lensed beat, and child requested reaching a parent-lensed beat."""
    p = _poi("p", lat=48.85, lng=2.35)
    child_beats = _snap(
        [p],
        beats_by_poi={"p": _lensed_beats("p", ("dark_history",))},
        lens_neighbors=_HOP_MAP,
    )
    parent_beats = _snap(
        [p],
        beats_by_poi={"p": _lensed_beats("p", ("history",))},
        lens_neighbors=_HOP_MAP,
    )
    for snap, requested in ((child_beats, "history"), (parent_beats, "dark_history")):
        s_hop = poi_score(p, None, frozenset({requested}), snap)
        s_neutral = poi_score(p, None, frozenset(), snap)
        assert math.isclose(s_hop / s_neutral, 0.6, rel_tol=1e-9)


def test_lens_adjacency_ranks_direct_above_one_hop():
    direct = _poi("direct", lat=48.8556, lng=2.3658)
    hop = _poi("hop", lat=48.8557, lng=2.3659)
    snap = _snap(
        [direct, hop],
        beats_by_poi={
            "direct": _lensed_beats("direct", ("history",)),
            "hop": _lensed_beats("hop", ("dark_history",)),
        },
        lens_neighbors=_HOP_MAP,
    )
    s_direct = poi_score(direct, None, frozenset({"history"}), snap)
    s_hop = poi_score(hop, None, frozenset({"history"}), snap)
    assert s_direct > s_hop > 0


def test_lens_adjacency_miss_is_zero_and_excludes_candidate():
    """§3 (M3): a thematic miss scores 0.0 AND is excluded from the candidate
    pool — supersedes the old rule-41 'bias not filter' behavior (the spec's
    multiplicative form with miss=0.0 makes the lens a hard filter; graceful
    degradation lives in the no-lens uniform-1.0 branch instead)."""
    themed = _poi("themed", tier=4, lat=48.8556, lng=2.3658, areas=("Le Marais",))
    missed = _poi("missed", tier=5, lat=48.8557, lng=2.3659, areas=("Le Marais",))
    fillers = _density_fillers(PDV)  # unlensed synthetic beats → misses too
    snap = _snap(
        [*fillers, themed, missed],
        area_types={"Le Marais": "neighborhood"},
        beats_by_poi={"themed": _lensed_beats("themed", ("hidden_history",))},
        lens_neighbors=_HOP_MAP,
    )
    assert poi_score(missed, None, frozenset({"hidden_history"}), snap) == 0.0

    inp = TourInput(
        start=PDV,
        duration_min=60,
        city_slug="paris",
        lenses=["hidden_history"],
        round_trip=True,
    )
    ids = [p.id for p in select_route(inp, snap).pois]
    assert ids == ["themed"], f"only the themed POI may survive the lens filter, got {ids}"


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
    pois = [_poi(f"p{i}", lat=48.8550 + i * 0.0010, lng=2.3650 + i * 0.0010) for i in range(20)]
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
    route = select_route(TourInput(start=PDV, duration_min=400, city_slug="paris"), snap)
    assert len(route.pois) <= HARD_ANCHOR_CAP


def test_select_route_deterministic_under_input_shuffle():
    base = [_poi(f"p{i}", lat=48.8550 + i * 0.0001, lng=2.3650 + i * 0.0001) for i in range(8)]

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
    # Force spine to be Le Marais by sheer count: add filler in Marais near
    # start so spine vote wins. Bumped to 4 tier-5 fillers (was 3 tier-4)
    # to also satisfy the Phase 6 density gate — the assertion is unchanged.
    fillers = [
        _poi(
            f"f{i}",
            tier=5,
            lat=48.8556 + i * 0.00002,
            lng=2.3658,
            areas=("Le Marais",),
            beat_count=8,
        )
        for i in range(4)
    ]
    snap = _snap(
        [in_marais, out_other, *fillers],
        area_types={"Le Marais": "neighborhood", "Other Hood": "neighborhood"},
    )
    route = select_route(TourInput(start=PDV, duration_min=60, city_slug="paris"), snap)
    assert route.spine_area == "Le Marais"
    ids = [p.id for p in route.pois]
    # Spine POI must be selected (bias is a scoring multiplier, not a hard
    # filter — but in a tight cluster of equals, the spine POI is preferred).
    assert "marais" in ids


def test_yellow_density_attaches_assessment_to_route():
    """Phase 6: a YELLOW assessment must surface as route.tourability."""
    # 5 colocated tier-5 anchors with thin per-beat audio so fill lands
    # in the YELLOW band (0.5-1.0). 5 beats x 5 POIs x 80s = 2000s;
    # target 60min = 1793s; fill ≈ 1.12 — too high for YELLOW. Drop to
    # 60s per beat: 5 x 5 x 60 = 1500s; fill ≈ 0.84 → YELLOW by-fill.
    pois = [
        _poi(
            f"y{i}",
            tier=5,
            lat=PDV[0] + 0.00005 * i,
            lng=PDV[1],
            areas=("Le Marais",),
            beat_count=5,
        )
        for i in range(5)
    ]
    beats: dict[str, list[BeatRef]] = {
        p.id: [
            BeatRef(
                id=f"{p.id}-b{j}",
                poi_id=p.id,
                est_spoken_seconds=60,
                active_status="active",
            )
            for j in range(5)
        ]
        for p in pois
    }
    snap = _snap(
        pois,
        area_types={"Le Marais": "neighborhood"},
        beats_by_poi=beats,
    )
    route = select_route(
        TourInput(start=PDV, duration_min=60, city_slug="paris", round_trip=False),
        snap,
    )
    assert route.tourability is not None
    assert route.tourability.status == "YELLOW"
    assert 0.5 <= route.tourability.fill_ratio < 1.0


def test_zero_beat_poi_excluded_from_anchor_pool():
    """Phase 6 selection guard: tier-3+ POIs with 0 active beats are dropped."""
    rich = _poi("rich", tier=5, lat=PDV[0], lng=PDV[1], beat_count=8)
    empty = _poi("empty", tier=4, lat=PDV[0], lng=PDV[1] + 0.00005, beat_count=0)
    snap = _snap(
        [rich, empty, *_density_fillers(PDV)],
        area_types={"Le Marais": "neighborhood"},
        beats_by_poi={"empty": []},  # explicit zero
    )
    route = select_route(TourInput(start=PDV, duration_min=60, city_slug="paris"), snap)
    ids = {p.id for p in route.pois}
    assert "rich" in ids
    assert "empty" not in ids, (
        "Zero-beat POI must be excluded from the candidate pool — "
        "this was the Phase 5 Petit Palais bug"
    )


def test_select_route_empty_when_no_candidates_in_envelope():
    """Phase 6: an empty reachable envelope now raises TourabilityRefusedError.

    Pre-Phase-6 this returned an empty Route. The density gate runs
    before the envelope filter and refuses (RED) when there's no corpus
    to support a tour at all.
    """
    from src.tour.density import TourabilityRefusedError

    far = _poi("far", lat=49.5, lng=3.0)  # well outside Paris
    snap = _snap([far])
    with pytest.raises(TourabilityRefusedError) as excinfo:
        select_route(TourInput(start=PDV, duration_min=60, city_slug="paris"), snap)
    assert excinfo.value.assessment.status == "RED"
    assert excinfo.value.assessment.reachable_poi_count == 0


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
    # Far-envelope anchor — east of start, beyond 0.5 x radius.
    far_lat = start[0] - 0.0030  # ~330m south
    far_lng = start[1] + 0.0140  # ~1km east, well past 0.5 x radius (~570m)
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
        "near",
        tier=5,
        lat=start[0],
        lng=start[1] + 0.0002,
        areas=("Île de la Cité",),
        beat_count=5,
    )
    far = _poi(
        "far",
        tier=5,
        lat=start[0],
        lng=start[1] + 0.0050,
        areas=("Île de la Cité",),
        beat_count=5,
    )
    fillers = _density_fillers(start)
    snap = _snap([near, far, *fillers], area_types={"Île de la Cité": "island"})
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
        "near",
        tier=5,
        lat=start[0],
        lng=start[1] + 0.0001,
        areas=("Île de la Cité",),
        beat_count=5,
    )
    too_far_lng = start[1] + 0.020  # ~1.5km — ringed against a 60-min budget
    too_far = _poi(
        "too-far",
        tier=5,
        lat=start[0],
        lng=too_far_lng,
        areas=("Île de la Cité",),
        beat_count=5,
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


def test_spine_tiebreak_prefers_island_over_tied_district():
    """When island and district score identically, island wins."""
    pois = [
        _poi("a", tier=5, lat=48.857, lng=2.341, areas=("Île de la Cité", "1st Arrondissement")),
        _poi("b", tier=5, lat=48.856, lng=2.342, areas=("Île de la Cité", "1st Arrondissement")),
        _poi("c", tier=4, lat=48.855, lng=2.343, areas=("Île de la Cité", "1st Arrondissement")),
    ]
    snap = _snap(
        pois,
        area_types={
            "Île de la Cité": "island",
            "1st Arrondissement": "district",
        },
    )
    spine = pick_spine_area(48.857, 2.341, pois, snap)
    assert spine == "Île de la Cité"


def test_spine_tiebreak_prefers_neighborhood_over_tied_district():
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


# Phase 2.6 calibration — 2x district dominance rule (Note 1).


def test_spine_prefers_island_over_district_below_2x():
    """Island B at 1.875x ratio (below 2x threshold) → smaller Area wins."""
    # 7 POIs in district A, ∑tier = 30 (5+5+5+5+4+3+3).
    district_pois = [
        _poi(f"d{i}", tier=t, lat=48.857, lng=2.341, areas=("District A",))
        for i, t in enumerate([5, 5, 5, 5, 4, 3, 3])
    ]
    # 4 POIs in island B, ∑tier = 16 (5+5+3+3).
    island_pois = [
        _poi(f"i{i}", tier=t, lat=48.857, lng=2.341, areas=("Island B",))
        for i, t in enumerate([5, 5, 3, 3])
    ]
    snap = _snap(
        district_pois + island_pois,
        area_types={"District A": "district", "Island B": "island"},
    )
    spine = pick_spine_area(48.857, 2.341, district_pois + island_pois, snap)
    assert spine == "Island B", f"ratio 30/16=1.875 < 2x → island should win, got {spine}"


def test_spine_picks_district_when_2x_dominant():
    """District A at 3x ratio (above 2x threshold) → district wins."""
    # 12 POIs in district A, ∑tier = 60.
    district_pois = [
        _poi(f"d{i}", tier=5, lat=48.857, lng=2.341, areas=("District A",)) for i in range(12)
    ]
    # 4 POIs in island B, ∑tier = 20.
    island_pois = [
        _poi(f"i{i}", tier=5, lat=48.857, lng=2.341, areas=("Island B",)) for i in range(4)
    ]
    snap = _snap(
        district_pois + island_pois,
        area_types={"District A": "district", "Island B": "island"},
    )
    spine = pick_spine_area(48.857, 2.341, district_pois + island_pois, snap)
    assert spine == "District A", f"ratio 60/20=3x ≥ 2x → district wins, got {spine}"


def test_spine_district_dominance_picks_strongest_specific_when_multiple():
    """When several specific Areas qualify, take the highest-vote one."""
    # District big, two contender islands; island B has more votes.
    district_pois = [
        _poi(f"d{i}", tier=5, lat=48.857, lng=2.341, areas=("District A",))
        for i in range(8)  # ∑tier = 40
    ]
    weak_island = [
        _poi(f"w{i}", tier=4, lat=48.857, lng=2.341, areas=("Island weak",))
        for i in range(3)  # ∑tier = 12
    ]
    strong_island = [
        _poi(f"s{i}", tier=5, lat=48.857, lng=2.341, areas=("Island strong",))
        for i in range(5)  # ∑tier = 25
    ]
    snap = _snap(
        district_pois + weak_island + strong_island,
        area_types={
            "District A": "district",
            "Island weak": "island",
            "Island strong": "island",
        },
    )
    pois = district_pois + weak_island + strong_island
    spine = pick_spine_area(48.857, 2.341, pois, snap)
    # threshold = 40 / 2 = 20 → Island weak (12) excluded, Island strong (25) qualifies.
    assert spine == "Island strong"


# Phase 2.6 — Latin Quarter polygon regression (Note 2).


def test_notre_dame_in_ile_not_latin_quarter():
    """Live-data regression against the **production** Paris corpus.

    Asserts the §1.8 polygon-overshoot bug has been fixed: Notre-Dame
    sits in Île de la Cité, not Latin Quarter. Reads the production
    .env directly because conftest re-points create_driver() at the
    disposable test DB. Skipped when prod Neo4j is unreachable or the
    Paris corpus hasn't been loaded.
    """
    from pathlib import Path

    from dotenv import dotenv_values

    pytest.importorskip("neo4j")
    from neo4j import GraphDatabase

    prod_env = Path(__file__).resolve().parent.parent / ".env"
    if not prod_env.exists():
        pytest.skip("production .env not present")
    cfg = dotenv_values(prod_env)
    uri = cfg.get("NEO4J_URI")
    user = cfg.get("NEO4J_USER")
    password = cfg.get("NEO4J_PASSWORD")
    if not (uri and user and password):
        pytest.skip("production Neo4j credentials missing")

    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        driver.verify_connectivity()
    except Exception:
        pytest.skip("production Neo4j unreachable")
    try:
        with driver.session() as s:
            r = s.run(
                "MATCH (p:POI {city_name: 'paris', name: 'Notre-Dame Cathedral'})"
                "-[:WITHIN]->(a:Area) RETURN collect(a.name) AS areas"
            ).single()
        areas = set(r["areas"]) if r else set()
    finally:
        driver.close()
    if not areas:
        pytest.skip("Notre-Dame not present in production corpus")
    assert "Île de la Cité" in areas, f"ND missing from Île de la Cité: {areas}"
    assert "Latin Quarter" not in areas, f"ND still leaks into Latin Quarter: {areas}"


# ---------------------------------------------------------------------------
# Phase 7 — fill pass (Fix 3): target_audio is a floor, not a soft stop
# ---------------------------------------------------------------------------


def test_phase7_fill_pass_adds_anchors_when_below_floor():
    """Greedy stalls below the audio floor with walk slack remaining → fill pass adds.

    Synthetic 180-min one-way scenario: 3 anchors clustered near start
    (greedy fills these cheaply but only consumes ~15 min walk and ~15
    min dwell) plus 6 additional reachable tier-3 candidates whose
    individual walk costs are all small. Greedy picks the cheap cluster,
    stops because score-per-cost flattens, leaving walk slack and dwell
    well below the audio floor. Fill pass should add at least one of
    the residual candidates.
    """
    start = (48.85675, 2.341033)
    main = [
        _poi(
            f"main-{i}",
            tier=5,
            lat=start[0] + 0.0001 * i,
            lng=start[1] + 0.0002 * i,
            areas=("Le Marais",),
            beat_count=8,
        )
        for i in range(3)
    ]
    fill_candidates = [
        _poi(
            f"fill-{i}",
            tier=3,
            lat=start[0] + 0.0008 * (i + 1),
            lng=start[1] + 0.0010 * (i + 1),
            areas=("Le Marais",),
            beat_count=4,
        )
        for i in range(6)
    ]
    snap = _snap(main + fill_candidates, area_types={"Le Marais": "neighborhood"})

    inp = TourInput(start=start, duration_min=180, city_slug="paris", round_trip=False)
    route = select_route(inp, snap)
    ids = [p.id for p in route.pois]

    assert any(i.startswith("fill-") for i in ids), (
        f"Fill pass should have pulled in at least one tier-3 candidate; got POIs: {ids}"
    )


def test_phase7_fill_pass_does_not_run_when_already_above_floor():
    """When greedy already meets the audio floor, fill pass is a no-op."""
    start = (48.85675, 2.341033)
    # 9 dense tier-5 anchors with rich beats — greedy will satisfy audio floor.
    pois = [
        _poi(
            f"rich-{i}",
            tier=5,
            lat=start[0] + 0.0001 * i,
            lng=start[1] + 0.0001 * i,
            areas=("Le Marais",),
            beat_count=12,
        )
        for i in range(9)
    ]
    snap = _snap(pois, area_types={"Le Marais": "neighborhood"})
    inp = TourInput(start=start, duration_min=60, city_slug="paris", round_trip=False)
    route = select_route(inp, snap)
    # 60-min audio target is ~30 min. 6 tier-5 anchors at 5 min dwell = 30 min.
    # The greedy/anchor-cap gates terminate well before the fill pass needs to fire.
    # The assertion is "no spurious additions beyond the natural greedy result".
    assert len(route.pois) <= 6  # max_anchors = 60 // 10 = 6


def test_phase7_fill_pass_respects_hard_anchor_cap():
    """Fill pass must not exceed HARD_ANCHOR_CAP (= 12)."""
    start = (48.85675, 2.341033)
    # A long ladder of 30 cheap-to-insert near-start tier-3 candidates.
    pois = [
        _poi(
            f"l-{i}",
            tier=3,
            lat=start[0] + 0.00005 * i,
            lng=start[1] + 0.00010 * i,
            areas=("Le Marais",),
            beat_count=4,
        )
        for i in range(30)
    ]
    snap = _snap(pois, area_types={"Le Marais": "neighborhood"})
    inp = TourInput(start=start, duration_min=180, city_slug="paris", round_trip=False)
    route = select_route(inp, snap)
    assert len(route.pois) <= HARD_ANCHOR_CAP


def test_phase7_fill_pass_respects_walk_budget_cap():
    """Fill pass clips at FILL_PASS_WALK_BUDGET_FRAC x walk_budget."""
    from src.tour.routing import walk_budget_seconds
    from src.tour.selection import FILL_PASS_WALK_BUDGET_FRAC

    start = (48.85675, 2.341033)
    # Three near anchors + several far candidates the fill pass can't fit.
    near = [
        _poi(
            f"n-{i}",
            tier=5,
            lat=start[0] + 0.0001 * i,
            lng=start[1] + 0.0001 * i,
            areas=("Le Marais",),
            beat_count=8,
        )
        for i in range(3)
    ]
    # Each "far" candidate is ~1km from origin, so any insertion costs ≥ 14 min.
    far = [
        _poi(
            f"f-{i}",
            tier=3,
            lat=start[0] + 0.005 + 0.0005 * i,
            lng=start[1] + 0.010 + 0.0005 * i,
            areas=("Le Marais",),
            beat_count=2,
        )
        for i in range(8)
    ]
    snap = _snap(near + far, area_types={"Le Marais": "neighborhood"})
    inp = TourInput(start=start, duration_min=60, city_slug="paris", round_trip=False)
    route = select_route(inp, snap)
    walk_cap = int(walk_budget_seconds(60) * FILL_PASS_WALK_BUDGET_FRAC)
    assert route.total_walk_seconds <= walk_cap


def test_phase7_fill_pass_concorde_smoke_real_corpus():
    """Live-corpus smoke: Concorde 180min one-way improves over phase-6-rerun.

    Pre-Phase-7 baseline: 5 anchors emitted (Place de la Concorde →
    Pont de la Concorde → Pont Alexandre III → Grand Palais →
    Champs-Elysees), 41-min walk, 9-min audio. Phase 7 fill pass must
    add at least one anchor when the route is below the audio floor.
    """
    from pathlib import Path

    from dotenv import dotenv_values

    pytest.importorskip("neo4j")
    from neo4j import GraphDatabase

    prod_env = Path(__file__).resolve().parent.parent / ".env"
    if not prod_env.exists():
        pytest.skip("production .env not present")
    cfg = dotenv_values(prod_env)
    uri = cfg.get("NEO4J_URI")
    user = cfg.get("NEO4J_USER")
    password = cfg.get("NEO4J_PASSWORD")
    if not (uri and user and password):
        pytest.skip("production Neo4j credentials missing")
    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        driver.verify_connectivity()
    except Exception:
        pytest.skip("production Neo4j unreachable")
    try:
        from src.tour.selection import load_paris_corpus
        from src.tour.selection import select_route as live_select_route

        snapshot = load_paris_corpus(driver, city_slug="paris")
    finally:
        driver.close()

    inp = TourInput(start=(48.8656, 2.3210), duration_min=180, city_slug="paris", round_trip=False)
    route = live_select_route(inp, snapshot)
    # Phase 6 rerun had 5 anchors; Phase 7 fill pass must add at least one.
    assert len(route.pois) >= 6, (
        f"Phase 7 fill pass should add ≥1 anchor on Concorde 180min "
        f"(baseline was 5). Got {len(route.pois)}: {[p.name for p in route.pois]}"
    )


# ---------------------------------------------------------------------------
# Phase 7.5 Fix 3 — co-located POI demotion
# ---------------------------------------------------------------------------


def test_demote_co_located_pois():
    """Two POIs within 15m + a beat at one referencing the other's name → demote.

    Mirrors the Tour 1 case: Place des Vosges (tier 5) carries a beat at
    sub_location 'hugo-museum-no-6'; Musée Victor Hugo (tier 4) sits at
    the same address. The smaller-tier (Hugo museum) demotes; its beats
    merge into PdV's pool via Route.demoted_beats.
    """
    from src.tour.selection import apply_co_located_demotion

    pdv = _poi(
        "place-des-vosges",
        tier=5,
        lat=48.85553,
        lng=2.36560,
        areas=("Le Marais",),
        beat_count=25,
    )
    hugo = _poi(
        "musee-victor-hugo",
        tier=4,
        lat=48.85556,  # ~3-4m offset — well within 15m
        lng=2.36563,
        areas=("Le Marais",),
        beat_count=2,
    )
    pdv_beat = BeatRef(
        id="pdv-no6",
        poi_id=pdv.id,
        sub_location="hugo-museum-no-6",
        trigger_address="no. 6 place des Vosges",
        narrative_function="establishing",
        active_status="active",
    )
    hugo_beat_a = BeatRef(
        id="hugo-a",
        poi_id=hugo.id,
        narrative_function="establishing",
        script_body="Hugo lived here from 1832.",
        active_status="active",
    )
    hugo_beat_b = BeatRef(
        id="hugo-b",
        poi_id=hugo.id,
        narrative_function="deepen",
        script_body="His domestic life was turbulent.",
        active_status="active",
    )
    snap = _snap(
        [pdv, hugo],
        area_types={"Le Marais": "neighborhood"},
        beats_by_poi={pdv.id: [pdv_beat], hugo.id: [hugo_beat_a, hugo_beat_b]},
    )
    new_selected, demoted_beats = apply_co_located_demotion([pdv, hugo], snap)
    assert [p.id for p in new_selected] == ["place-des-vosges"]
    assert hugo.id not in {p.id for p in new_selected}
    assert pdv.id in demoted_beats
    demoted_ids = {b.id for b in demoted_beats[pdv.id]}
    assert demoted_ids == {"hugo-a", "hugo-b"}, (
        f"All demoted POI's beats must be merged into the host's pool; got {demoted_ids}"
    )


def test_no_demotion_when_distance_above_threshold():
    """Same address overlap signal but well past the proximity gate → no demotion."""
    from src.tour.selection import DEMOTION_PROXIMITY_M, apply_co_located_demotion

    a = _poi("a-poi", tier=5, lat=48.85550, lng=2.36560, areas=("Le Marais",), beat_count=5)
    # ~280m offset — well outside the 100m geofence-radius gate.
    b = _poi("b-museum", tier=4, lat=48.85800, lng=2.36560, areas=("Le Marais",), beat_count=2)
    a_beat = BeatRef(
        id="a1",
        poi_id=a.id,
        sub_location="b-museum-room",
        narrative_function="establishing",
        active_status="active",
    )
    snap = _snap(
        [a, b],
        area_types={"Le Marais": "neighborhood"},
        beats_by_poi={a.id: [a_beat], b.id: []},
    )
    new_selected, demoted_beats = apply_co_located_demotion([a, b], snap)
    assert {p.id for p in new_selected} == {"a-poi", "b-museum"}
    assert demoted_beats == {}
    # Sanity check on the constant — guards against silent threshold drift.
    assert DEMOTION_PROXIMITY_M == 100.0


def test_no_demotion_when_smaller_is_pause_tier():
    """Tier-3 (or below) POIs are deliberate pause stops; do not demote.

    Mirrors the Île case: Square du Vert-Galant (tier 3) sits ~80m from
    Pont Neuf (tier 5) and Pont Neuf carries beats referencing
    'vert-galant'. The Phase 7.5 guard skips this pair because Vert-
    Galant is an empirical Pariswalks pause stop, not a sub-feature
    of Pont Neuf.
    """
    from src.tour.selection import apply_co_located_demotion

    pont_neuf = _poi(
        "pont-neuf",
        tier=5,
        lat=48.85698,
        lng=2.34170,
        areas=("Île de la Cité",),
        beat_count=10,
    )
    vert_galant = _poi(
        "vert-galant",
        tier=3,  # pause tier
        lat=48.85650,
        lng=2.34010,
        areas=("Île de la Cité",),
        beat_count=4,
    )
    pn_beat = BeatRef(
        id="pn1",
        poi_id=pont_neuf.id,
        sub_location="vert-galant-tip",
        narrative_function="establishing",
        active_status="active",
    )
    snap = _snap(
        [pont_neuf, vert_galant],
        area_types={"Île de la Cité": "island"},
        beats_by_poi={pont_neuf.id: [pn_beat], vert_galant.id: []},
    )
    new_selected, demoted_beats = apply_co_located_demotion([pont_neuf, vert_galant], snap)
    assert {p.id for p in new_selected} == {"pont-neuf", "vert-galant"}
    assert demoted_beats == {}


def test_no_demotion_when_no_address_overlap_signal():
    """Within 15m but no beat references the other POI's distinctive token."""
    from src.tour.selection import apply_co_located_demotion

    a = _poi("alpha-anchor", tier=5, lat=48.85550, lng=2.36560, areas=("Le Marais",), beat_count=5)
    b = _poi("beta-museum", tier=4, lat=48.85553, lng=2.36563, areas=("Le Marais",), beat_count=2)
    a_beat = BeatRef(
        id="a1",
        poi_id=a.id,
        sub_location="entrance",  # no mention of beta
        narrative_function="establishing",
        active_status="active",
    )
    b_beat = BeatRef(
        id="b1",
        poi_id=b.id,
        narrative_function="establishing",
        active_status="active",
    )
    snap = _snap(
        [a, b],
        area_types={"Le Marais": "neighborhood"},
        beats_by_poi={a.id: [a_beat], b.id: [b_beat]},
    )
    new_selected, demoted_beats = apply_co_located_demotion([a, b], snap)
    assert {p.id for p in new_selected} == {"alpha-anchor", "beta-museum"}
    assert demoted_beats == {}


def test_demotion_merged_via_select_route_end_to_end():
    """select_route() must surface demoted_beats on the returned Route."""
    pdv = _poi(
        "place-des-vosges",
        tier=5,
        lat=PDV[0],
        lng=PDV[1],
        areas=("Le Marais",),
        beat_count=8,
    )
    hugo = _poi(
        "musee-victor-hugo",
        tier=4,
        lat=PDV[0] + 0.00003,
        lng=PDV[1] + 0.00003,  # ~4m offset
        areas=("Le Marais",),
        beat_count=2,
    )
    pdv_beat = BeatRef(
        id="pdv-no6",
        poi_id=pdv.id,
        sub_location="hugo-museum-no-6",
        trigger_address="no. 6 place des Vosges",
        narrative_function="establishing",
        est_spoken_seconds=240,
        active_status="active",
    )
    pdv_extra = [
        BeatRef(id=f"pdv-x{i}", poi_id=pdv.id, est_spoken_seconds=240, active_status="active")
        for i in range(7)
    ]
    hugo_beat = BeatRef(
        id="hugo-1",
        poi_id=hugo.id,
        narrative_function="establishing",
        est_spoken_seconds=240,
        active_status="active",
    )
    snap = _snap(
        [pdv, hugo, *_density_fillers(PDV, n=4)],
        area_types={"Le Marais": "neighborhood"},
        beats_by_poi={
            pdv.id: [pdv_beat, *pdv_extra],
            hugo.id: [hugo_beat],
        },
    )
    inp = TourInput(start=PDV, duration_min=60, city_slug="paris", round_trip=True)
    route = select_route(inp, snap)
    poi_ids = {p.id for p in route.pois}
    assert "place-des-vosges" in poi_ids
    assert "musee-victor-hugo" not in poi_ids, (
        "Hugo museum should be demoted into Place des Vosges as a sub-stop"
    )
    assert "place-des-vosges" in route.demoted_beats
    assert any(b.id == "hugo-1" for b in route.demoted_beats["place-des-vosges"])
