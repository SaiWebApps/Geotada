"""Phase 2 — selection.py: envelope, spine, greedy. Pure-function tests."""

from __future__ import annotations

import math

import pytest

from src.tour.contract import POI, BeatRef, TourInput
from src.tour.routing import envelope_radius_m, haversine_m, pace_corrected_walk_seconds
from src.tour.selection import (
    AREA_ALIGNMENT_ADJACENT,
    AREA_ALIGNMENT_OTHER,
    AREA_ALIGNMENT_SPINE,
    HARD_ANCHOR_CAP,
    CorpusSnapshot,
    build_poi_beat_plans,
    build_poi_beat_plans_capped,
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


def test_low_tier_no_lens_eligible_as_vignette_not_dwell():
    """Phase 3 re-baseline (Step 3.5, calibrated): the hard tier gate is GONE,
    but spotlight ALLOCATES scarce dwell-minutes (s3), it does not stop
    everywhere.

    Pre-3.5 a tier-1 POI was hard-EXCLUDED from the anchor pool
    (ANCHOR_TIERS = {3,4,5}). After the model switch it is ELIGIBLE -- its
    on-path spotlight gravity(1) x 1.0 x 1.0 = 1.0 is a VIGNETTE (a brief
    mention), not silent. But 1.0 is below the calibrated dwell floor
    (BAND_THRESHOLD_SHORT = 3.0 = tier-3 gravity), so it is NOT a dwell stop:
    the tier-5 anchor keeps the dwell slot and the tier-1 vignette does not
    crowd it out. This is what stops low-tier POIs from displacing the golden
    anchors (the pre-calibration bug that dropped the Ile golden 53.2->42.6).
    """
    from src.tour.selection import BAND_VIGNETTE, band_for_spotlight, spotlight

    t1 = _poi("t1", tier=1, lat=48.8556, lng=2.3658)
    t5 = _poi("t5", tier=5, lat=48.8556, lng=2.3660)
    snap = _snap([t1, t5, *_density_fillers(PDV)])
    # Eligible, not excluded: the tier-1 no-lens POI is a vignette, not silent.
    t1_band = band_for_spotlight(spotlight(t1, lenses=None, snapshot=snap), tier=1)
    assert t1_band == BAND_VIGNETTE, f"tier-1 no-lens should be an eligible vignette, got {t1_band}"
    # Allocation: the tier-5 anchor is a dwell stop; the tier-1 vignette is NOT
    # in the dwell route (route.pois are dwell stops).
    route = select_route(TourInput(start=PDV, duration_min=60, city_slug="paris"), snap)
    ids = [p.id for p in route.pois]
    # C9 governor (budget/3 floor): 5 tier-5 anchors compete (t5 + 4 density
    # fillers) for ~3 dwell slots, so a specific tier-5 (t5) may drop to the
    # closer fillers. The invariant that MUST survive: every dwell stop is a
    # tier-5 anchor — the tier-1 no-lens POI never displaces one into a slot.
    assert route.pois, f"anchors must still fill dwell slots, got {ids}"
    assert all(p.tier == 5 for p in route.pois), (
        f"every dwell stop must be a tier-5 anchor (no tier-1 crowd-in); got {ids}"
    )
    assert "t1" not in ids, (
        "a tier-1 no-lens POI is an eligible VIGNETTE, not a dwell stop -- it must "
        f"not consume a dwell slot from the anchors. Got {ids}"
    )


def test_low_tier_off_genre_goes_silent_only_when_both():
    """s3 silence invariant: silent ONLY when low-gravity AND off-genre.

    With a lens requested, a tier-1 POI whose beats MISS the lens scores
    gravity(1) x LENS_FLOOR(0.25) x proximity(1.0) = 0.25 -> below the vignette
    cut AND tier < BAND_LANDMARK_TIER -> SILENT, so it never enters the dwell
    pool. A tier-5 POI that MISSES the same lens scores 5 x 0.25 = 1.25 ->
    vignette-floored landmark, still eligible (lens alone never silences a
    landmark). A tier-4 POI that HITS the lens is a full dwell stop. So with the
    lens active, the silent tier-1 miss drops out while the lens-hit themed POI
    is selected.
    """
    from src.tour.selection import (
        BAND_SILENT,
        band_for_spotlight,
        spotlight,
    )

    lens = frozenset({"hidden_history"})
    t1_miss = _poi("t1-miss", tier=1, lat=48.8556, lng=2.3661, areas=("Le Marais",))
    t5_miss = _poi("t5-miss", tier=5, lat=48.8557, lng=2.3662, areas=("Le Marais",))
    themed = _poi("themed", tier=4, lat=48.8556, lng=2.3658, areas=("Le Marais",))
    snap = _snap(
        [t1_miss, t5_miss, themed, *_density_fillers(PDV)],
        area_types={"Le Marais": "neighborhood"},
        beats_by_poi={"themed": _lensed_beats("themed", ("hidden_history",))},
        lens_neighbors=_HOP_MAP,
    )
    # Unit-level proof of the invariant at the band classifier.
    assert (
        band_for_spotlight(spotlight(t1_miss, lenses=lens, snapshot=snap), tier=1) == BAND_SILENT
    )
    assert (
        band_for_spotlight(spotlight(t5_miss, lenses=lens, snapshot=snap), tier=5) != BAND_SILENT
    ), "a tier-5 landmark that misses the lens is dimmed to vignette, never silenced"

    inp = TourInput(
        start=PDV, duration_min=60, city_slug="paris", lenses=["hidden_history"], round_trip=True
    )
    ids = [p.id for p in select_route(inp, snap).pois]
    assert "t1-miss" not in ids, (
        f"low-gravity off-genre POI must be silent (excluded), got {ids}"
    )
    assert "themed" in ids, f"the lens-hit POI must be a dwell stop, got {ids}"


def test_lens_dimmed_landmark_stays_a_dwell_stop_not_empty():
    """Landmark dwell-floor: a tier >= BAND_LANDMARK_TIER POI that a LENS dims to
    VIGNETTE must stay a DWELL stop — it discloses "thin for your interest", it
    never vanishes. Without this floor, a lensed thin area where every reachable
    POI is a lens-dimmed landmark (e.g. The Sorbonne under dark_history) empties
    the whole tour and silently drops a major landmark."""
    from src.tour.selection import BAND_VIGNETTE, band_for_spotlight, spotlight

    lens = frozenset({"hidden_history"})
    # Two tier-4 landmarks that MISS the lens; the density fillers (tier-5) also
    # miss it — so EVERY reachable POI is a lens-dimmed landmark and the ONLY way
    # to avoid an empty tour is the dwell-floor.
    lm1 = _poi("landmark-1", tier=4, lat=48.8556, lng=2.3658, areas=("Le Marais",))
    lm2 = _poi("landmark-2", tier=4, lat=48.8560, lng=2.3663, areas=("Le Marais",))
    snap = _snap(
        [lm1, lm2, *_density_fillers(PDV)],
        area_types={"Le Marais": "neighborhood"},
        lens_neighbors=_HOP_MAP,
    )
    # Precondition: the landmark is dimmed to VIGNETTE by the lens (pre-fix it was
    # dropped from the dwell pool at the candidate filter).
    assert band_for_spotlight(spotlight(lm1, lenses=lens, snapshot=snap), tier=4) == BAND_VIGNETTE

    inp = TourInput(
        start=PDV, duration_min=60, city_slug="paris", lenses=["hidden_history"], round_trip=True
    )
    route = select_route(inp, snap)
    ids = [p.id for p in route.pois]
    assert route.pois, "a lensed area of dimmed landmarks must NOT empty the tour"
    assert any(i.startswith("landmark-") or i.startswith("filler-") for i in ids), (
        f"a lens-dimmed landmark must survive as a dwell stop, got {ids}"
    )


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


def test_lens_miss_dims_but_does_not_zero_poi_score():
    """Phase 3 re-baseline (Step 3.5): the model switch made poi_score's lens
    factor the POSITIVE-floored lens_relevance (miss -> LENS_FLOOR = 0.25), NOT
    the legacy hard-filter _lens_adjacency (miss -> 0.0).

    A high-gravity (tier-5) POI that MISSES the requested lens must score a
    strictly positive, DIMMED value -- exactly LENS_FLOOR of its no-lens score,
    not zero. This is what lets a lens-miss landmark still earn a dwell stop
    ("lens promotes, never silences a landmark", s3) rather than vanishing.
    """
    from src.tour.selection import LENS_FLOOR

    missed = _poi("missed", tier=5, lat=48.8557, lng=2.3659, areas=("Le Marais",))
    snap = _snap(
        [missed],
        area_types={"Le Marais": "neighborhood"},
        beats_by_poi={"missed": _lensed_beats("missed", ("film_tv",))},
        lens_neighbors=_HOP_MAP,
    )
    s_miss = poi_score(missed, None, frozenset({"hidden_history"}), snap)
    s_neutral = poi_score(missed, None, frozenset(), snap)
    assert s_miss > 0.0, "a lens miss must DIM, not zero, the score (Step 3.5 model switch)"
    assert math.isclose(s_miss / s_neutral, LENS_FLOOR, rel_tol=1e-9), (
        f"a lens-miss score must be LENS_FLOOR of the no-lens score; "
        f"got ratio {s_miss / s_neutral}"
    )


def test_lens_miss_high_gravity_poi_survives_as_vignette():
    """Step 3.5 (calibrated): the lens-miss HARD exclusion is GONE -- a tier-5
    off-genre POI is no longer dropped; it is DIMMED to a vignette (5 x
    LENS_FLOOR = 1.25, below the 3.0 dwell floor; landmark-floored, never
    silent) -- a brief mention. Dimmed is NOT a dwell stop: the lens-hit
    anchors take the dwell slots; the off-genre landmark is an eligible
    vignette. (s3: lens alone never silences a landmark; off-genre dims it.)
    """
    from src.tour.selection import BAND_VIGNETTE, band_for_spotlight, spotlight

    missed = _poi("missed", tier=5, lat=48.8557, lng=2.3659, areas=("Le Marais",))
    # Lens-hit anchors so the dwell route is viable + dense enough to clear the gate.
    hits = [
        _poi(f"hit{i}", tier=5, lat=48.8556 + 0.0001 * i, lng=2.3658, areas=("Le Marais",))
        for i in range(4)
    ]
    snap = _snap(
        [*hits, missed],
        area_types={"Le Marais": "neighborhood"},
        beats_by_poi={
            **{h.id: _lensed_beats(h.id, ("hidden_history",)) for h in hits},
            "missed": _lensed_beats("missed", ("street_art",)),
        },
        lens_neighbors=_HOP_MAP,
    )
    lenses = frozenset({"hidden_history"})
    # Eligible + dimmed, not silenced: the tier-5 off-genre POI is a vignette.
    b = band_for_spotlight(spotlight(missed, lenses=lenses, snapshot=snap), tier=5)
    assert b == BAND_VIGNETTE, f"tier-5 off-genre must dim to a vignette, not silent/dwell; got {b}"
    # And it does NOT take a dwell slot: the lens-hit anchors are the route.
    inp = TourInput(
        start=PDV, duration_min=60, city_slug="paris", lenses=["hidden_history"], round_trip=True
    )
    ids = [p.id for p in select_route(inp, snap).pois]
    assert any(h.id in ids for h in hits), f"lens-hit dwell stops must be selected, got {ids}"
    assert "missed" not in ids, (
        "a tier-5 off-genre POI is an eligible VIGNETTE (a brief mention), not a dwell "
        f"stop -- it must not take a dwell slot. Got {ids}"
    )


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


def test_endpoint_pull_never_evicts_entire_route():
    """A far beat-mountain anchor must not evict every greedy incumbent.

    Regression for the 2026-07-02 Rue Cler collapse: a 60-min one-way
    preview near Invalides returned a ONE-stop tour. The greedy had seated
    a sane 2-stop near cluster, then the endpoint-pull ranked far-envelope
    candidates by raw poi_score — a tier-5 POI with an outlier beat count
    (39, inflated by a book-extraction campaign) won despite its leg eating
    ~90% of the walk budget — and dropped BOTH incumbents (exactly
    ENDPOINT_PULL_MAX_DROPS) because only the far anchor alone fit. A tour
    must never collapse to just the pulled endpoint: the pull abandons
    instead and the greedy cluster survives.

    Geometry (60-min one-way: walk budget 1195s, greedy budget 896s,
    envelope 738m, far floor 369m, 3km/h x1.35 pace => ~1.62 s/m): two
    cheap tier-5 anchors west (250m, 400m — the greedy seats both for
    ~650s and can afford nothing more), a 39-beat tier-5 anchor 600m east
    (solo leg ~970s <= 1195s: the collapse candidate; any trial keeping an
    incumbent busts the budget), and three tier-3 decoys 500-600m out in
    other directions so the density gate's rich-pool clause (fill >= 1.5,
    anchors >= 6) clears without adding anything the greedy can afford.
    """
    start = (48.8568, 2.3414)
    area = ("Île de la Cité",)
    near1 = _poi(
        "near-1", tier=5, lat=start[0], lng=start[1] - 0.003415, areas=area, beat_count=6
    )  # 250m W
    near2 = _poi(
        "near-2", tier=5, lat=start[0], lng=start[1] - 0.005464, areas=area, beat_count=6
    )  # 400m W
    far = _poi(
        "far-mountain", tier=5, lat=start[0], lng=start[1] + 0.008197, areas=area, beat_count=39
    )  # 600m E
    decoys = [
        _poi("decoy-n", tier=3, lat=start[0] + 0.004950, lng=start[1], areas=area, beat_count=3),
        _poi("decoy-s", tier=3, lat=start[0] - 0.005400, lng=start[1], areas=area, beat_count=3),
        _poi(
            "decoy-ne",
            tier=3,
            lat=start[0] + 0.003150,
            lng=start[1] + 0.004781,
            areas=area,
            beat_count=3,
        ),
    ]
    snap = _snap([near1, near2, far, *decoys], area_types={"Île de la Cité": "island"})

    inp = TourInput(start=start, duration_min=60, city_slug="paris", round_trip=False)
    route = select_route(inp, snap)
    ids = [p.id for p in route.pois]

    # Pre-fix this came back as exactly ["far-mountain"] — one stop.
    assert ids != ["far-mountain"], "endpoint-pull evicted the entire greedy route"
    assert len(ids) >= 2, f"one-stop tour emitted: {ids}"
    # The greedy's near cluster must survive the pull.
    assert "near-1" in ids and "near-2" in ids


def test_isolated_single_anchor_yields_one_stop_with_yellow_warning():
    """Greedy-seats-1 path (Père Lachaise pattern; hostile-panel finding 2026-07-02).

    When exactly ONE dwellable anchor is in reach, a single-stop route is the
    honest maximum — canon: the PdV golden is a human-blessed one-stop tour —
    and is NOT the endpoint-pull collapse (which the pull guard kills; that
    collapse abandoned a richer greedy route). The contract this test pins:
    such a route must carry the YELLOW tourability assessment (Phase 6:
    "generate but WARN") so surfaces can show the user WHY the tour has one
    stop instead of looking like a silent bug.

    Density arithmetic for the fixture (60-min one-way, target audio 1793s):
    one tier-4 anchor, 5 beats x 240s = 1200s -> fill 0.67 (YELLOW-by-fill,
    0.5 <= fill < 1.0); 1 anchor candidate (< 4, so not GREEN)."""
    start = (48.8568, 2.3414)
    lone = _poi(
        "lone-anchor",
        tier=4,
        lat=start[0],
        lng=start[1] + 0.002,
        areas=("Île de la Cité",),
        beat_count=5,
    )
    snap = _snap([lone], area_types={"Île de la Cité": "island"})

    route = select_route(
        TourInput(start=start, duration_min=60, city_slug="paris", round_trip=False),
        snap,
    )

    assert [p.id for p in route.pois] == ["lone-anchor"]
    assert route.tourability is not None, (
        "a one-stop tour must carry the YELLOW tourability assessment — "
        "without it, thin-area tours are indistinguishable from collapse bugs"
    )
    assert route.tourability.status == "YELLOW"
    assert route.tourability.anchor_candidate_count == 1


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


def test_phase7_fill_pass_under_floor_rescue_adds_nearby_stop():
    """#21: a 2nd nearby stop that busts walk_budget but fits total planned time
    is added while the tour is below the stop floor and the audio floor.

    Mirrors the live Latin Quarter 60-min loop: greedy seats one stop (Pantheon),
    the second (Sorbonne) round-trip detour busts walk_budget, yet audio is far
    under target and total time has ample slack. The under-fill rescue admits it.
    """
    from src.tour.routing import walk_budget_seconds
    from src.tour.selection import _apply_fill_pass, target_audio_seconds

    start = (48.8462, 2.3436)
    a = _poi("A", tier=4, lat=48.8478, lng=2.3436, areas=("Latin Quarter",), beat_count=3)
    b = _poi("B", tier=4, lat=48.8462, lng=2.3477, areas=("Latin Quarter",), beat_count=3)
    snap = _snap([a, b], area_types={"Latin Quarter": "neighborhood"})

    def capped(p, *, exempt):  # small audio -> well under the fill floor
        return 260 if p.id == "A" else 370

    common = dict(
        candidates=[a, b], spine="Latin Quarter", interest=frozenset(), snapshot=snap,
        start_lat=start[0], start_lng=start[1], round_trip=True,
        walk_budget=walk_budget_seconds(60), audio_budget=target_audio_seconds(60),
        hard_anchor_cap=12, capped_audio_fn=capped, exempt_anchor_id="A",
    )
    # rescue_floor=2 -> below floor -> rescue fires: the 2nd nearby stop is added.
    rescued = _apply_fill_pass([a], rescue_floor=2, **common)
    assert {p.id for p in rescued} == {"A", "B"}, "rescue must seat the 2nd nearby stop"

    # rescue_floor=0 -> no rescue -> the walk cap holds, 2nd stop stays out.
    control = _apply_fill_pass([a], rescue_floor=0, **common)
    assert {p.id for p in control} == {"A"}, "no rescue -> walk cap blocks the 2nd stop"


def test_phase7_fill_pass_rescue_rejects_far_walk_slog():
    """#21 guard (skeptic finding): the rescue must NOT trek to a FAR thin stop.

    A distant candidate whose round-trip detour exceeds RESCUE_WALK_MULTIPLE x
    walk_budget is a walk-slog (huge walk for tiny audio) — it stays OUT even
    though the tour is below the stop floor, so the fix can't make a tour worse.
    """
    from src.tour.routing import walk_budget_seconds
    from src.tour.selection import _apply_fill_pass, target_audio_seconds

    start = (48.8462, 2.3436)
    a = _poi("A", tier=4, lat=48.8478, lng=2.3436, areas=("Latin Quarter",), beat_count=3)
    far = _poi("FAR", tier=3, lat=48.8462, lng=2.3536, areas=("Latin Quarter",), beat_count=1)
    snap = _snap([a, far], area_types={"Latin Quarter": "neighborhood"})

    def capped(p, *, exempt):
        return 260 if p.id == "A" else 120  # far stop is thin

    out = _apply_fill_pass(
        [a], candidates=[a, far], spine="Latin Quarter", interest=frozenset(), snapshot=snap,
        start_lat=start[0], start_lng=start[1], round_trip=True,
        walk_budget=walk_budget_seconds(60), audio_budget=target_audio_seconds(60),
        hard_anchor_cap=12, capped_audio_fn=capped, exempt_anchor_id="A", rescue_floor=2,
    )
    assert {p.id for p in out} == {"A"}, "a far thin stop must not be trekked to"


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
    # Phase 7 fill pass builds a substantial multi-anchor tour. The 2026-07-04
    # filler-stub demotion moved the thin bridge stops (Pont de la Concorde, Pont
    # Alexandre III) to walk-by vignettes, so the roster is now ~5 SUBSTANTIAL
    # anchors (Concorde, Petit/Grand Palais, Champs-Elysees, Arc de Triomphe)
    # rather than 6 padded with thin bridges — a better tour, not a worse one.
    from src.tour.selection import _is_filler_stub

    assert len(route.pois) >= 5, (
        f"Phase 7 fill pass should build a substantial multi-anchor tour on "
        f"Concorde 180min. Got {len(route.pois)}: {[p.name for p in route.pois]}"
    )
    # Every SEATED dwell stop is substantial — no filler-stub survived into the route.
    fillers = [p.name for p in route.pois if _is_filler_stub(p, snapshot, None)]
    assert not fillers, f"seated dwell stops must not be filler-stubs; got {fillers}"


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
        beat_count=20,
    )
    hugo = _poi(
        # C9 governor: tier-5 + 12 beats so Hugo out-spotlights the 8-beat density
        # fillers and wins a greedy slot under the budget/3 stop floor (a low-value
        # sibling would be dropped before it could demote). Demotion still fires
        # via the beat_count host tiebreak — pdv (20 beats) hosts, hugo (12)
        # demotes — so this still exercises the merge end-to-end.
        "musee-victor-hugo",
        tier=5,
        lat=PDV[0] + 0.00003,
        lng=PDV[1] + 0.00003,  # ~4m offset
        areas=("Le Marais",),
        beat_count=12,
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


# ---------------------------------------------------------------------------
# Step 2.0d — FROZEN end=None ordered-POI-id identity baseline.
#
# This is a byte-for-byte guard for Steps 2.3/2.4 (B-materialization /
# endpoint handling). It pins the exact ordered POI ids select_route emits
# for a FIXED synthetic snapshot on BOTH cost paths:
#   (a) no routing client  → leg_fn=None, pace-corrected haversine divisor;
#   (b) a deterministic fake RoutingClient → routed divisor that returns
#       int(haversine_m(...)) and whose isochrone() returns None (forcing the
#       haversine reach fallback). route()/close() are no-ops/total fallback.
#
# Any future change to the selection pipeline that perturbs the end=None
# ordering for this snapshot must fail here, loudly, before it can reach the
# Step 2.3/2.4 B-materialization work that depends on this invariance.
# ---------------------------------------------------------------------------


class _DeterministicRoutingClient:
    """Hermetic fake: routed leg times equal int(pace-corrected haversine).

    - leg_seconds / route use the same deterministic, container-free math the
      selection greedy would see, so path (b) is fully reproducible offline.
    - isochrone() returns None → _reach_predicate falls back to the analytic
      haversine envelope (degraded=True), exactly like a Valhalla outage.
    - route() returns a None polyline so TransitSegment.source stays honest.
    - close() is a no-op.
    """

    def leg_seconds(self, from_lat: float, from_lng: float, to_lat: float, to_lng: float) -> int:
        return int(pace_corrected_walk_seconds(haversine_m(from_lat, from_lng, to_lat, to_lng)))

    def route(
        self, from_lat: float, from_lng: float, to_lat: float, to_lng: float
    ) -> tuple[int, float, None]:
        d = haversine_m(from_lat, from_lng, to_lat, to_lng)
        return (int(pace_corrected_walk_seconds(d)), d, None)

    def isochrone(self, lat: float, lng: float, minutes: int) -> None:
        return None

    def close(self) -> None:
        return None


def _frozen_end_none_snapshot() -> CorpusSnapshot:
    """A FIXED synthetic snapshot for the end=None ordering baseline.

    Deterministic POIs at hardcoded coords inside the 60-min one-way
    envelope around PDV: 4 density fillers (to clear the Phase 6 gate)
    plus two distinct tier-5 anchors — a near one and a medium one.
    """
    near = _poi(
        "baseline-near",
        tier=5,
        lat=48.8556,
        lng=2.3658,
        areas=("Le Marais",),
        beat_count=8,
    )
    medium = _poi(
        "baseline-medium",
        tier=5,
        lat=48.8580,
        lng=2.3700,
        areas=("Le Marais",),
        beat_count=8,
    )
    return _snap(
        [near, medium, *_density_fillers(PDV)],
        area_types={"Le Marais": "neighborhood"},
    )


# FROZEN literals — captured from a green run; see the docstring above.
# These are the byte-for-byte expected ordered POI ids for end=None.
#
# Phase 3 re-baseline (Step 3.5): gate removal WIDENS the eligible pool (the
# hard tier gate, the walk_by_only exclusion, and the lens-miss exclusion are
# gone). This snapshot was DELIBERATELY re-verified under the model switch and
# the ordered ids are UNCHANGED -- by construction: every POI here is a tier-5
# 'stop' with active beats and NO lens is requested, so (a) the removed tier
# gate excluded nothing (all tier 5), (b) there are no walk_by_only POIs, and
# (c) with no lenses, lens_relevance == _lens_adjacency == 1.0, so poi_score is
# byte-identical to its pre-3.5 value. The widened eligibility therefore admits
# the same six POIs in the same order; the ends are still correct (open walk
# closes on the far 'baseline-medium' via endpoint-pull) and no crash. The new
# eligibility is exercised separately by the tier-1 / lens-miss tests above.
# C9 governor (end=None, budget/3 floor): the Step-2.0d Phase-2 byte-identity is
# DELIBERATELY superseded (DESIGN-AND-CRITIQUE ADDENDUM — the goldens are the new
# gate). Re-captured 2026-07-03 from the green C9 run: this beat-rich synthetic
# corpus caps at the ~3-stop floor (the exempt anchor's audio clears the fill
# floor, so no fill-added 4th-6th stop). The real end=None gate (Ile golden) is
# BYTE-IDENTICAL to pre-C9 (16/47), so this re-baseline moves only the fixture.
_FROZEN_END_NONE_ORDER_HAVERSINE: tuple[str, ...] = (
    "filler-0",
    "filler-1",
    "filler-2",
    "baseline-medium",
)
_FROZEN_END_NONE_ORDER_ROUTED: tuple[str, ...] = (
    "filler-0",
    "filler-1",
    "filler-2",
    "baseline-medium",
)


def test_frozen_end_none_ordered_ids_haversine_path():
    """end=None ordering is frozen on the no-client (haversine) cost path."""
    snap = _frozen_end_none_snapshot()
    inp = TourInput(start=PDV, duration_min=60, city_slug="paris", round_trip=False)
    route = select_route(inp, snap)
    ids = tuple(p.id for p in route.pois)
    assert ids == _FROZEN_END_NONE_ORDER_HAVERSINE, (
        f"end=None haversine ordering drifted from the Step 2.0d frozen "
        f"baseline; expected {_FROZEN_END_NONE_ORDER_HAVERSINE}, got {ids}"
    )


def test_frozen_end_none_ordered_ids_routed_path():
    """end=None ordering is frozen on the deterministic routed cost path."""
    snap = _frozen_end_none_snapshot()
    inp = TourInput(start=PDV, duration_min=60, city_slug="paris", round_trip=False)
    route = select_route(inp, snap, routing_client=_DeterministicRoutingClient())
    ids = tuple(p.id for p in route.pois)
    assert ids == _FROZEN_END_NONE_ORDER_ROUTED, (
        f"end=None routed ordering drifted from the Step 2.0d frozen "
        f"baseline; expected {_FROZEN_END_NONE_ORDER_ROUTED}, got {ids}"
    )


def test_end_none_route_records_exempt_anchor_identity():
    """C9f-i: an end=None route persists the exempt-anchor ids the greedy used, so
    compose + the golden harnesses read the SAME exempt set (pois[0] is NOT the
    start-anchor after Held-Karp). Byte-identical to emission — additive metadata.
    """
    snap = _frozen_end_none_snapshot()
    # Open walk: the positional start-anchor AND the pulled endpoint are recorded.
    ow = select_route(
        TourInput(start=PDV, duration_min=60, city_slug="paris", round_trip=False), snap
    )
    ow_ids = {p.id for p in ow.pois}
    assert ow.start_anchor_poi_id is not None
    assert ow.start_anchor_poi_id in ow_ids, "start-anchor must be a seated POI"
    # This open walk closes on the far 'baseline-medium' via endpoint-pull, so that
    # pulled endpoint is the exempt fixed_end.
    assert ow.fixed_end_poi_id == "baseline-medium"
    assert ow.pois[-1].id == "baseline-medium"  # Held-Karp ends at the fixed_end
    # Round trip: a positional start-anchor is recorded, but round trips run no
    # endpoint-pull (one-way only), so fixed_end_poi_id stays None.
    rt = select_route(
        TourInput(start=PDV, duration_min=60, city_slug="paris", round_trip=True), snap
    )
    assert rt.start_anchor_poi_id is not None
    assert rt.start_anchor_poi_id in {p.id for p in rt.pois}
    assert rt.fixed_end_poi_id is None


def test_domination_caps():
    """Governor v4 core: caps a DOMINATING OUTLIER to ~1/3 of delivered, but leaves
    a BALANCED tour untouched (the v3 always-on cap over-trimmed balanced tours —
    the panel's bug 4)."""
    from src.tour.selection import _domination_caps

    # UC5 (exempt marquee 396; Ile 363 dominates its 74/56/42 peers).
    caps = _domination_caps([True, False, False, False, False], [396, 56, 74, 363, 42])
    assert caps[0] is None, "exempt marquee uncapped"
    total = 396 + caps[1] + caps[2] + caps[3] + caps[4]
    assert caps[3] < 363 and caps[3] <= total // 3 + 1, "the dominator capped to ~1/3"
    assert caps[1] == 56 and caps[2] == 74 and caps[4] == 42, "peers untouched"

    # BALANCED: two near-equal non-exempt (193 vs 162, within the 1.5x factor) →
    # NOT a drowning outlier → NOT capped.
    assert _domination_caps([True, False, False], [196, 193, 162]) == [None, 193, 162]

    # A single non-exempt stop cannot 'dominate' (no peer to drown) → no cap.
    assert _domination_caps([True, False], [400, 900]) == [None, 900]

    # CO-DOMINATORS: two near-equal huge stops drowning three small peers must
    # BOTH cap. Comparing to the next-largest would let them shield each other
    # (the panel gap) — comparing to the MEAN of the others catches both.
    co = _domination_caps([False, False, False, False, False], [1000, 950, 100, 80, 60])
    t = sum(co)
    assert co[0] <= t // 3 + 1 and co[1] <= t // 3 + 1, "both co-dominators capped, not shielded"
    assert (co[2], co[3], co[4]) == (100, 80, 60), "the drowned small peers are untouched"


def test_governor_v4_marquee_exempt_domination_gated():
    """Governor v4 wrapper: exempts the MARQUEE (highest-tier stop, not a proximity
    seed), caps only a dominating outlier (overflow returned, kept+overflow==full),
    leaves a balanced tour whole, and A→B stays uncapped. Explicit beats (select_
    poi_beats caps tier-3 to 3 beats, so we use tier-4/5 with controlled audio)."""
    from src.tour.routing import planned_audio_seconds, summarise_route

    def _b(pid, n, secs):
        return [
            BeatRef(id=f"{pid}-b{i}", poi_id=pid, est_spoken_seconds=secs, active_status="active")
            for i in range(n)
        ]

    def _route(pois):
        return summarise_route(
            pois, start_lat=48.8556, start_lng=2.3658, round_trip=True,
            duration_min=60, spine_area="Le Marais", routing_client=None,
        )

    # tier-5 marquee (exempt by TIER even though the tier-4 dump has more audio) +
    # a dominating tier-4 dump + a thin tier-4 peer.
    marquee = _poi("marquee", tier=5, lat=48.8556, lng=2.3658, areas=("Le Marais",))
    dump = _poi("dump", tier=4, lat=48.8560, lng=2.3665, areas=("Le Marais",))
    peer = _poi("peer", tier=4, lat=48.8564, lng=2.3670, areas=("Le Marais",))
    beats = {
        "marquee": _b("marquee", 3, 200),
        "dump": _b("dump", 6, 300),
        "peer": _b("peer", 2, 150),
    }
    snap = _snap(
        [marquee, dump, peer], area_types={"Le Marais": "neighborhood"}, beats_by_poi=beats
    )
    route = _route([marquee, dump, peer])

    capped = build_poi_beat_plans_capped(route, snap, lenses=None, end_is_none=True)
    by_id = {kept.poi_id: (kept, ov) for kept, ov in capped}
    delivered = sum(planned_audio_seconds(k.beats) for k, _ in capped)
    m_kept, m_ov = by_id["marquee"]
    assert len(m_kept.beats) == 3 and m_ov == (), "the tier-5 marquee is exempt (not the seed)"
    d_kept, d_ov = by_id["dump"]
    assert len(d_ov) > 0, "the lower-tier dominating dump overflows"
    assert planned_audio_seconds(d_kept.beats) <= delivered // 3 + 300, "dump within 1/3 (+1 beat)"
    assert len(by_id["peer"][0].beats) == 2, "thin peer untouched"
    plain = {p.poi_id: p for p in build_poi_beat_plans(route, snap, lenses=None)}
    assert {b.id for b in d_kept.beats} | set(d_ov) == {b.id for b in plain["dump"].beats}

    # BALANCED tour (3 near-equal stops) → NOTHING capped (the panel's bug-4 fix).
    bal = {"m": _b("m", 3, 200), "p1": _b("p1", 3, 190), "p2": _b("p2", 3, 180)}
    bp = [_poi(x, tier=4, lat=48.8556 + i * 0.0006, lng=2.3658, areas=("Le Marais",))
          for i, x in enumerate(("m", "p1", "p2"))]
    bsnap = _snap(bp, area_types={"Le Marais": "neighborhood"}, beats_by_poi=bal)
    bcap = build_poi_beat_plans_capped(_route(bp), bsnap, lenses=None, end_is_none=True)
    assert all(ov == () for _, ov in bcap), "a balanced tour is never capped"

    # A→B (end_is_none False) → byte-identical uncapped.
    ab = build_poi_beat_plans_capped(route, snap, lenses=None, end_is_none=False)
    assert tuple(pb for pb, _ in ab) == tuple(build_poi_beat_plans(route, snap, lenses=None))
    assert all(ov == () for _, ov in ab)


# ---------------------------------------------------------------------------
# Step 2.5 — open-walk B* == existing endpoint-pull far anchor.
#
# Assertion-only (no production change). On the open-walk path
# (end=None, round_trip=False) the route's closing stop is the same
# far-envelope anchor the existing _apply_endpoint_pull machinery pins via
# held_karp_open(fixed_end=...). We re-derive that anchor B* by replaying
# select_route's verbatim endpoint-pull contract (the far-radius filter at
# selection.py:944-951, the score/id ranking at :953-959, and the
# first-that-fits _apply_endpoint_pull accept at :960-977) on the route's
# own non-far prefix, then assert select_route's emitted last stop equals it.
# The test fails if any of that wiring (far filter, ranking, pull, or the
# fixed_end pin-through to held_karp_open at :1021-1029) breaks.
# ---------------------------------------------------------------------------


def test_open_walk_bstar_equals_endpoint_pull():
    """Open-walk (end=None) last stop == the _apply_endpoint_pull far anchor.

    A single tier-5 far-envelope anchor sits unambiguously beyond
    ENDPOINT_PULL_FAR_FRACTION x radius, east of a near-start cluster the
    greedy fills first. We:

      1. Run select_route (end=None, round_trip=False) and capture its
         ordered POIs.
      2. Independently rebuild B* by feeding the route's non-far prefix and
         the far candidate through the *same* production helper select_route
         uses — _apply_endpoint_pull with fixed_end pinned via
         held_karp_open — and confirm that helper returns the far anchor as
         its closing stop.
      3. Assert select_route's emitted last stop equals that re-derived B*,
         and that no fixed end / corridor gate was in play (end is None).
    """
    from src.tour.routing import (
        default_leg_seconds,
        walk_budget_seconds,
    )
    from src.tour.selection import (
        ENDPOINT_PULL_FAR_FRACTION,
        HARD_ANCHOR_CAP,
        _apply_endpoint_pull,
        pick_spine_area,
    )

    start = (48.85675, 2.341033)  # Pont Neuf coords
    duration_min = 90
    radius_m = envelope_radius_m(duration_min, round_trip=False)
    far_floor = radius_m * ENDPOINT_PULL_FAR_FRACTION

    # Near-start cluster: greedy fills these first (all well inside the far
    # floor, so none of them can be the endpoint-pull anchor).
    near = [
        _poi(
            f"near-{i}",
            tier=4,
            lat=start[0] + 0.0001 * i,
            lng=start[1] + 0.0008 * i,
            areas=("Île de la Cité",),
            beat_count=6,
        )
        for i in range(1, 4)
    ]
    # Exactly one far-envelope anchor, ~1km east — unambiguously the only POI
    # past the far floor, so the endpoint-pull candidate set is a singleton.
    far_anchor = _poi(
        "far",
        tier=5,
        lat=start[0] - 0.0030,
        lng=start[1] + 0.0140,
        areas=("Île de la Cité",),
        beat_count=10,
    )
    snap = _snap([*near, far_anchor], area_types={"Île de la Cité": "island"})

    inp = TourInput(start=start, duration_min=duration_min, city_slug="paris", round_trip=False)
    # Open walk: no fixed destination, so the §2.3 corridor gate never arms
    # and the §2.4 B-materialization branch is never taken — the only force
    # acting on the final stop is the endpoint-pull contract under test.
    assert inp.end is None
    route = select_route(inp, snap)
    ids = [p.id for p in route.pois]
    assert "far" in ids, f"far-envelope anchor must be selected; got {ids}"

    # Sanity: the far anchor really is the sole POI past the far floor (so the
    # endpoint-pull candidate ranking has a single, unambiguous winner).
    past_floor = [
        p for p in (*near, far_anchor) if haversine_m(*start, p.lat, p.lng) >= far_floor
    ]
    assert [p.id for p in past_floor] == ["far"], (
        f"test fixture invalid: expected only 'far' past {far_floor:.0f}m, "
        f"got {[p.id for p in past_floor]}"
    )

    # Re-derive B* with the verbatim production helper. The route's prefix
    # (everything before the closing far anchor) is the incumbent set the
    # endpoint-pull pins 'far' after; held_karp_open may reorder the prefix,
    # so compare against the set, not the order.
    prefix = [p for p in route.pois if p.id != "far"]
    spine = pick_spine_area(*start, [*near, far_anchor], snap)
    pulled = _apply_endpoint_pull(
        prefix,
        far_anchor,
        spine=spine,
        interest=frozenset(),
        snapshot=snap,
        start_lat=start[0],
        start_lng=start[1],
        walk_budget=walk_budget_seconds(duration_min),
        hard_anchor_cap=HARD_ANCHOR_CAP,
        leg_seconds_fn=None,  # open-walk haversine path → default_leg_seconds
    )
    # The helper must actually have pinned the far anchor (not abandoned the
    # pull), and that anchor is exactly what select_route emitted as the last
    # stop — i.e. the open-walk B* is the endpoint-pull far anchor, reused
    # verbatim. The prefix order matches too (both go through held_karp_open
    # with the same fixed_end and the same default_leg_seconds divisor).
    assert pulled[-1].id == "far"
    assert pulled is not prefix, "endpoint-pull must have applied, not no-op'd"
    bstar = pulled[-1].id
    assert ids[-1] == bstar, (
        f"open-walk last stop {ids[-1]!r} must equal the endpoint-pull far "
        f"anchor B* {bstar!r}"
    )
    assert [p.id for p in route.pois] == [p.id for p in pulled], (
        f"open-walk order must match the endpoint-pull/held_karp_open result; "
        f"route={ids} pulled={[p.id for p in pulled]}"
    )
    # Cross-check the divisor reuse claim explicitly: default_leg_seconds is
    # the open-walk cost fn, and the far anchor is reachable under the walk
    # budget through it (otherwise the pull would have abandoned).
    assert default_leg_seconds(*start, far_anchor.lat, far_anchor.lng) <= walk_budget_seconds(
        duration_min
    )


# ---------------------------------------------------------------------------
# 2026-07-03 — single-stop regression class guards.
#
# The 2026-07-02 regression: previews silently collapsing to a single
# location (endpoint-pull eviction near Rue Cler) plus thin single-beat-
# feeling narration. The point fixes are pinned above
# (test_endpoint_pull_never_evicts_entire_route,
# test_isolated_single_anchor_yields_one_stop_with_yellow_warning); the
# tests below guard the CLASS: every code path that can shrink a rich
# pool down to one stop must either keep >= 2 stops or carry the YELLOW
# tourability disclosure. Universal invariant, spelled out once:
#
#     len(route.pois) >= 2  OR  route.tourability is not None
#
# These pin CURRENT contracts (tier-dwell audio proxy, YELLOW-only
# tourability attach). The delivered-audio invariant is deferred design —
# specs/2026-07-02-dwell-audio-reconciliation/ owns it; do not import it here.
# ---------------------------------------------------------------------------


def _sweep_snap() -> CorpusSnapshot:
    """12 tier-5 anchors compact around PdV (20-55m), 5 x 240s lensed beats each.

    Rich-pool GREEN at every duration in the sweep: total beat audio is
    12 x 5 x 240 = 14400s, so even the largest target (d=120 -> 3586s) gives
    fill 4.0 >= 1.5 with 12 anchors >= 6 — the density gate can never be the
    reason a cell degrades. The cluster (<= ~55m) sits inside the tightest
    envelope in the sweep (30-min round trip: ~184m). Explicit lensed beats
    make the lensed arm a direct hit (lens_relevance 1.0, spotlight 5.0 ->
    headline dwell band), so the legacy hard lens filter can never empty the
    dwell pool if it were ever reintroduced.
    """
    directions = ((1.0, 0.0), (0.0, 1.0), (-1.0, 0.0), (0.0, -1.0))
    pois = []
    for i in range(12):
        dlat, dlng = directions[i % 4]
        magnitude = 0.0002 + 0.000025 * i  # 0.0002 .. 0.000475 deg (~20-55m)
        pois.append(
            _poi(
                f"sweep-{i}",
                tier=5,
                lat=PDV[0] + dlat * magnitude,
                lng=PDV[1] + dlng * magnitude,
                areas=("Le Marais",),
                beat_count=5,
            )
        )
    beats = {p.id: _lensed_beats(p.id, ("hidden_history",)) for p in pois}
    return _snap(pois, area_types={"Le Marais": "neighborhood"}, beats_by_poi=beats)


@pytest.mark.parametrize("lenses", (None, ["hidden_history"]), ids=("nolens", "lensed"))
@pytest.mark.parametrize("round_trip", (False, True), ids=("oneway", "roundtrip"))
@pytest.mark.parametrize("duration_min", (30, 45, 60, 75, 90, 105, 120))
def test_rich_corpus_duration_sweep_never_collapses_to_single_stop(
    duration_min: int, round_trip: bool, lenses: list[str] | None
):
    """Property sweep: a rich compact corpus never yields a 1-stop tour at ANY duration.

    Every prior collapse test is a fixed 60- or 90-min case; a budget or
    arithmetic change that collapses only at, say, 40 or 110 minutes (an
    off-by-one in walk_budget_seconds, an ENDPOINT_PULL_RESERVED_BUDGET_FRACTION
    change starving short durations, an audio-break unit error making the 300s
    dwell proxy >= target at small d, an ANCHOR_CAP_DIVISOR change) would ship
    unseen. This fails in at least one of the 28 cells. The round-trip arm
    covers the pull-free path; the one-way arm covers greedy + pull + fill
    jointly; the lensed arm catches any reintroduction of the legacy hard lens
    filter (LENS_ADJACENCY_MISS = 0.0) into the dwell pool.
    """
    from src.tour.routing import walk_budget_seconds

    snap = _sweep_snap()
    inp = TourInput(
        start=PDV,
        duration_min=duration_min,
        city_slug="paris",
        round_trip=round_trip,
        lenses=lenses,
    )
    route = select_route(inp, snap)
    ids = [p.id for p in route.pois]

    # Defensible floor: max_anchors = d // 10 (>= 3 for every d >= 30), the
    # compact cluster makes every insertion nearly free, and the tier-dwell
    # audio break (300s/anchor vs target 896s at d=30) cannot fire before 3.
    floor = min(3, duration_min // 10)
    assert len(ids) >= floor, f"d={duration_min} rt={round_trip} lens={lenses}: got {ids}"
    assert route.total_walk_seconds <= walk_budget_seconds(duration_min) + 5  # rounding cushion
    # The fixture is GREEN by construction, so a 1-stop regression here would
    # be exactly the SILENT class (no warning shown to the user).
    assert route.tourability is None, (
        f"rich fixture must be GREEN (tourability None); got {route.tourability}"
    )
    # The universal invariant this whole section guards.
    assert len(route.pois) >= 2 or route.tourability is not None


def test_round_trip_far_first_pick_cannot_starve_multi_anchor_pool():
    """Greedy-break collapse path — geometrically distinct from pull-eviction.

    round_trip=True, so the endpoint-pull never runs (selection.py's
    ``if not input.round_trip`` gate) and NOTHING downstream prevents a
    1-stop result: the greedy's value ranking is the only defence. The trap:
    a 39-beat tier-5 'mountain' 340m east (inside the 369m round-trip
    envelope, INDIVIDUALLY affordable: 2 x ~551s = ~1102s <= 1195s budget)
    versus six modest tier-4 anchors 60-110m west. The greedy value
    ``score / max(1, extra + 1)`` (selection.py) makes the cheap nears win
    (~7.17/195 = 0.037 vs 18.44/1103 = 0.017); after even one near pick the
    mountain's insertion busts the budget forever.

    If the greedy ranking ever regresses to score-first (exactly what the
    fill pass legitimately does — a plausible copy-paste unification), the
    mountain is picked FIRST, consuming ~1102s; every near insertion then
    costs ~220s more and busts 1195s; the fill pass cannot rescue (per-
    candidate extras push past the 0.95-budget cap). Result: a GREEN 1-stop
    route with tourability None — the exact 2026-07-02 user experience via a
    path no other test covers (test_endpoint_pull_never_evicts_entire_route
    is one-way pull geometry; this is the round-trip greedy break).
    """
    from src.tour.routing import walk_budget_seconds

    start = (48.8568, 2.3414)
    area = ("Île de la Cité",)
    nears = [
        _poi(
            f"near-{i}",
            tier=4,
            lat=start[0],
            lng=start[1] - (0.00082 + 0.000136 * i),  # 60-110m west
            areas=area,
            beat_count=5,
        )
        for i in range(6)
    ]
    mountain = _poi(
        "far-mountain",
        tier=5,
        lat=start[0],
        lng=start[1] + 0.004645,  # ~340m east — inside the 369m RT envelope
        areas=area,
        beat_count=39,
    )
    snap = _snap([*nears, mountain], area_types={"Île de la Cité": "island"})
    budget = walk_budget_seconds(60)

    # Preconditions derived live — the fixture self-proves the trap exists.
    # (a) The mountain is solo-affordable on a round trip: the tempting pick.
    mountain_rt = 2 * pace_corrected_walk_seconds(haversine_m(*start, mountain.lat, mountain.lng))
    assert mountain_rt <= budget, f"fixture drifted: mountain RT {mountain_rt}s > {budget}s"
    # (b) Every near anchor's round-trip leg fits too (pairwise affordable).
    for near in nears:
        near_rt = 2 * pace_corrected_walk_seconds(haversine_m(*start, near.lat, near.lng))
        assert near_rt <= budget, f"fixture drifted: {near.id} RT {near_rt}s > {budget}s"
    # (c) Mountain is inside the round-trip envelope (it IS a candidate).
    assert haversine_m(*start, mountain.lat, mountain.lng) <= envelope_radius_m(
        60, round_trip=True
    )

    inp = TourInput(start=start, duration_min=60, city_slug="paris", round_trip=True)
    route = select_route(inp, snap)
    ids = [p.id for p in route.pois]

    assert ids != ["far-mountain"], "greedy collapsed to the solo far mountain"
    assert len(ids) >= 2, f"one-stop tour emitted: {ids}"
    assert sum(1 for i in ids if i.startswith("near-")) >= 2, (
        f"the near cluster must survive; got {ids}"
    )
    # GREEN fixture (rich pool: fill 9.2, 7 anchors) — a 1-stop here would be
    # the silent class.
    assert route.tourability is None
    assert len(route.pois) >= 2 or route.tourability is not None


def test_tier_dwell_audio_break_cannot_fire_after_single_anchor():
    """Pins the CURRENT tier-dwell audio proxy against 1-stop greedy breaks.

    CURRENT-CONTRACT PIN. The greedy's audio break (``consumed_audio >=
    audio_budget``) counts DWELL_SECONDS_BY_TIER dwell, NOT real beat audio.
    The delivered-audio reconciliation is deferred design owned by
    specs/2026-07-02-dwell-audio-reconciliation/ — when it lands, the
    plausible bad implementation is ``consumed_audio += sum(beat seconds)``,
    under which one anchor's 1200s of real beat audio exceeds the 896s target
    at 30 min and the greedy breaks after ONE pick, emitting a GREEN 1-stop
    tour (tourability None -> silent). Rewrite this test consciously with
    that spec; do not delete it.
    """
    from src.tour.routing import DWELL_SECONDS_BY_TIER, target_audio_seconds

    # Part 1 — constant pin (pure arithmetic): at every supported duration,
    # a single anchor's dwell proxy can NEVER satisfy the audio break.
    for d in range(30, 121, 10):
        assert max(DWELL_SECONDS_BY_TIER.values()) < target_audio_seconds(d), (
            f"a single stop's dwell proxy satisfies the audio target at d={d} — "
            "the greedy can now break after ONE anchor (single-stop class)"
        )

    # Part 2 — behavioral: the tightest supported duration (30 min) with 4
    # compact tier-5 anchors. max_anchors = 30 // 10 = 3 and the audio break
    # fires at exactly the 3rd insert (900 >= 896), never earlier. Plain
    # canonical GREEN: 4 anchors, fill 4800/896 = 5.36, compactness ~0.
    cluster = [
        _poi(
            f"c-{i}",
            tier=5,
            lat=PDV[0] + 0.0002 * (i % 2),
            lng=PDV[1] + 0.0002 * (i // 2),
            areas=("Le Marais",),
            beat_count=5,
        )
        for i in range(4)
    ]
    snap = _snap(cluster, area_types={"Le Marais": "neighborhood"})
    route = select_route(
        TourInput(start=PDV, duration_min=30, city_slug="paris", round_trip=True), snap
    )
    # Sharp pin (== 3) plus the class invariant (>= 2).
    assert len(route.pois) == 3, f"expected exactly 3 stops at 30 min; got {len(route.pois)}"
    assert len(route.pois) >= 2
    assert route.tourability is None
