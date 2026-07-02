"""Track B Step B.1 — select_vignettes: pure walk-past vignette selection.

Locked rules under test (IMPLEMENTATION-PLAN Track B deferred clarifications):
eligible iff on-path band == "vignette"; perpendicular distance to the leg
segment <= VIGNETTE_MAX_DETOUR_M (50 m); never a dwell stop of the route;
dedup across legs (first emitting leg wins); cap VIGNETTE_MAX_PER_LEG (2)
per leg; deterministic order (spotlight desc, then id). Plus the Phase 6
engine invariant: a POI with no active beats is never a vignette.

Pure — no Neo4j. Geometry uses a local flat-earth scale around Paris:
1 degree of latitude ~ 111,195 m, so 30 m ~ 0.00027 deg.
"""

from __future__ import annotations

from src.tour.contract import POI, BeatRef, Route
from src.tour.routing import summarise_route
from src.tour.selection import (
    VIGNETTE_MAX_DETOUR_M,
    VIGNETTE_MAX_PER_LEG,
    CorpusSnapshot,
    select_vignettes,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Degrees of latitude per metre (R = 6,371,000 m -> 1 deg lat = 111,194.9 m).
_DEG_PER_M_LAT = 1.0 / 111_194.9

# A west→east baseline at constant latitude: start, then stops A, B, C.
_LAT = 48.85
_START = (_LAT, 2.3450)
_A = (_LAT, 2.3500)
_B = (_LAT, 2.3600)
_C = (_LAT, 2.3700)


def _poi(
    pid: str,
    *,
    tier: int = 2,
    lat: float,
    lng: float,
    role: str = "stop",
) -> POI:
    return POI(id=pid, name=pid, tier=tier, poi_role=role, lat=lat, lng=lng)


def _beats(poi_id: str, *, lenses: tuple[str, ...] = (), active: str = "active") -> list[BeatRef]:
    return [
        BeatRef(
            id=f"{poi_id}-b0",
            poi_id=poi_id,
            active_status=active,
            script_body="A line worth hearing as you pass. And one more.",
            lenses=lenses,
        )
    ]


def _snap(pois: list[POI], beats_by_poi: dict[str, list[BeatRef]]) -> CorpusSnapshot:
    return CorpusSnapshot(
        pois=tuple(pois),
        beats_by_poi={k: tuple(v) for k, v in beats_by_poi.items()},
        area_types={},
        adjacent_areas={},
    )


def _route(stops: list[POI], *, round_trip: bool = False) -> Route:
    return summarise_route(
        stops,
        start_lat=_START[0],
        start_lng=_START[1],
        round_trip=round_trip,
        duration_min=60,
        spine_area=None,
    )


def _stops_ab() -> list[POI]:
    """Two tier-5 dwell stops A → B (leg 1 = A → B)."""
    return [
        _poi("stop-a", tier=5, lat=_A[0], lng=_A[1]),
        _poi("stop-b", tier=5, lat=_B[0], lng=_B[1]),
    ]


def _stops_abc() -> list[POI]:
    return [*_stops_ab(), _poi("stop-c", tier=5, lat=_C[0], lng=_C[1])]


def _mid(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
    return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)


# ---------------------------------------------------------------------------
# Admission: on-leg vs far, band gates, active beats
# ---------------------------------------------------------------------------


def test_on_leg_vignette_admitted():
    """A tier-2 (vignette band, no lens) POI 30 m off the A→B leg is picked."""
    mid = _mid(_A, _B)
    v = _poi("v-near", tier=2, lat=mid[0] + 30 * _DEG_PER_M_LAT, lng=mid[1])
    stops = _stops_ab()
    snap = _snap([*stops, v], {"v-near": _beats("v-near")})
    result = select_vignettes(_route(stops), snap)
    assert result == {1: (v,)}


def test_far_vignette_rejected():
    """The same POI 200 m off the leg (> 50 m) never surfaces."""
    mid = _mid(_A, _B)
    v = _poi("v-far", tier=2, lat=mid[0] + 200 * _DEG_PER_M_LAT, lng=mid[1])
    stops = _stops_ab()
    snap = _snap([*stops, v], {"v-far": _beats("v-far")})
    assert select_vignettes(_route(stops), snap) == {}


def test_beyond_segment_endpoint_measures_to_endpoint():
    """A POI past B along the line measures to B (segment, not infinite line)."""
    # 200 m east of B on the same latitude: on the infinite line (perp = 0)
    # but 200 m from the SEGMENT's nearest endpoint.
    v = _poi("v-past-end", tier=2, lat=_B[0], lng=_B[1] + 200 * _DEG_PER_M_LAT / 0.658)
    stops = _stops_ab()
    snap = _snap([*stops, v], {"v-past-end": _beats("v-past-end")})
    assert select_vignettes(_route(stops), snap) == {}


def test_dwell_stop_never_a_vignette():
    """A route POI is never emitted, even when its own band is vignette."""
    # Manual Route whose stops are tier-2 (on-path band == vignette) — the
    # dwell-stop exclusion must fire before any band consideration.
    stops = [
        _poi("stop-a", tier=2, lat=_A[0], lng=_A[1]),
        _poi("stop-b", tier=2, lat=_B[0], lng=_B[1]),
    ]
    snap = _snap(stops, {"stop-a": _beats("stop-a"), "stop-b": _beats("stop-b")})
    assert select_vignettes(_route(stops), snap) == {}


def test_zero_active_beat_poi_excluded():
    """No beats, or only inactive beats → nothing to voice → never a vignette."""
    mid = _mid(_A, _B)
    v_none = _poi("v-none", tier=2, lat=mid[0] + 20 * _DEG_PER_M_LAT, lng=mid[1])
    v_retired = _poi("v-retired", tier=2, lat=mid[0] - 20 * _DEG_PER_M_LAT, lng=mid[1])
    stops = _stops_ab()
    snap = _snap(
        [*stops, v_none, v_retired],
        {"v-retired": _beats("v-retired", active="retired")},
    )
    assert select_vignettes(_route(stops), snap) == {}


# ---------------------------------------------------------------------------
# Band gates: silent stays out, dwell-band stays out, lens dims into vignette
# ---------------------------------------------------------------------------


def test_silent_band_excluded():
    """Tier-1 lens miss (spotlight 0.25 < 0.5) is silent — never a vignette."""
    mid = _mid(_A, _B)
    v = _poi("v-silent", tier=1, lat=mid[0] + 20 * _DEG_PER_M_LAT, lng=mid[1])
    stops = _stops_ab()
    snap = _snap([*stops, v], {"v-silent": _beats("v-silent", lenses=("food",))})
    assert select_vignettes(_route(stops), snap, lenses=frozenset({"history"})) == {}


def test_dwell_band_poi_not_a_vignette_no_lens():
    """A tier-3 no-lens POI (spotlight 3.0, short = dwell band) is not vignette
    material — it belongs to the dwell pool, not the walk-past track."""
    mid = _mid(_A, _B)
    v = _poi("v-dwell-band", tier=3, lat=mid[0] + 20 * _DEG_PER_M_LAT, lng=mid[1])
    stops = _stops_ab()
    snap = _snap([*stops, v], {"v-dwell-band": _beats("v-dwell-band")})
    assert select_vignettes(_route(stops), snap) == {}


def test_lens_dims_off_genre_landmark_into_vignette():
    """Lens case: a tier-4 off-genre POI (4 x 0.25 = 1.0 → vignette) is
    admitted under the lens, but is dwell-band (4.0 → full) with no lens."""
    mid = _mid(_A, _B)
    v = _poi("v-offgenre", tier=4, lat=mid[0] + 20 * _DEG_PER_M_LAT, lng=mid[1])
    stops = _stops_ab()
    snap = _snap([*stops, v], {"v-offgenre": _beats("v-offgenre", lenses=("food",))})
    route = _route(stops)
    assert select_vignettes(route, snap, lenses=frozenset({"history"})) == {1: (v,)}
    assert select_vignettes(route, snap) == {}  # no lens → full band → dwell track


# ---------------------------------------------------------------------------
# Dedup, cap, determinism
# ---------------------------------------------------------------------------


def test_dedup_across_legs_first_leg_wins():
    """A POI within 50 m of both leg 1 and leg 2 (near shared stop B) is
    emitted on leg 1 only."""
    v = _poi("v-shared", tier=2, lat=_B[0] + 20 * _DEG_PER_M_LAT, lng=_B[1])
    stops = _stops_abc()
    snap = _snap([*stops, v], {"v-shared": _beats("v-shared")})
    result = select_vignettes(_route(stops), snap)
    assert result == {1: (v,)}
    assert 2 not in result


def test_cap_two_per_leg():
    """Three eligible on one leg → the top-2 by (spotlight desc, id) win."""
    assert VIGNETTE_MAX_PER_LEG == 2
    mid = _mid(_A, _B)
    v_high = _poi("v-z-high", tier=2, lat=mid[0] + 20 * _DEG_PER_M_LAT, lng=mid[1])
    v_low1 = _poi("v-a-low", tier=1, lat=mid[0] - 20 * _DEG_PER_M_LAT, lng=mid[1])
    v_low2 = _poi("v-b-low", tier=1, lat=mid[0] + 40 * _DEG_PER_M_LAT, lng=mid[1])
    stops = _stops_ab()
    snap = _snap(
        [*stops, v_low2, v_low1, v_high],  # deliberately shuffled snapshot order
        {
            "v-z-high": _beats("v-z-high"),
            "v-a-low": _beats("v-a-low"),
            "v-b-low": _beats("v-b-low"),
        },
    )
    result = select_vignettes(_route(stops), snap)
    # Spotlight desc first (tier-2 beats tier-1 despite the later id), then id.
    assert result == {1: (v_high, v_low1)}


def test_cap_cut_candidate_still_available_on_a_later_leg():
    """Dedup applies to EMITTED POIs only: a candidate cut by the cap on leg 1
    is picked up by leg 2 when it is also within 50 m of that leg."""
    mid1 = _mid(_A, _B)
    w1 = _poi("w-1", tier=2, lat=mid1[0] + 20 * _DEG_PER_M_LAT, lng=mid1[1])
    w2 = _poi("w-2", tier=2, lat=mid1[0] - 20 * _DEG_PER_M_LAT, lng=mid1[1])
    # Lower-ranked (tier-1) near shared stop B: within 50 m of both legs.
    cut = _poi("v-cut", tier=1, lat=_B[0] + 20 * _DEG_PER_M_LAT, lng=_B[1])
    stops = _stops_abc()
    snap = _snap(
        [*stops, w1, w2, cut],
        {"w-1": _beats("w-1"), "w-2": _beats("w-2"), "v-cut": _beats("v-cut")},
    )
    result = select_vignettes(_route(stops), snap)
    assert result == {1: (w1, w2), 2: (cut,)}


def test_deterministic_order_spotlight_desc_then_id():
    """Equal spotlight ties break on id, ascending."""
    mid = _mid(_A, _B)
    v_b = _poi("v-b", tier=2, lat=mid[0] + 20 * _DEG_PER_M_LAT, lng=mid[1])
    v_a = _poi("v-a", tier=2, lat=mid[0] - 20 * _DEG_PER_M_LAT, lng=mid[1])
    stops = _stops_ab()
    snap = _snap([*stops, v_b, v_a], {"v-b": _beats("v-b"), "v-a": _beats("v-a")})
    result = select_vignettes(_route(stops), snap)
    assert result == {1: (v_a, v_b)}


# ---------------------------------------------------------------------------
# Leg coverage: no start coordinate on the Route contract
# ---------------------------------------------------------------------------


def test_empty_and_single_stop_routes_yield_nothing():
    mid = _mid(_A, _B)
    v = _poi("v-near", tier=2, lat=mid[0] + 20 * _DEG_PER_M_LAT, lng=mid[1])
    one_stop = [_poi("stop-a", tier=5, lat=_A[0], lng=_A[1])]
    snap = _snap([*one_stop, v], {"v-near": _beats("v-near")})
    assert select_vignettes(_route(one_stop), snap) == {}
    assert select_vignettes(_route([]), snap) == {}


def test_round_trip_closing_leg_never_yields():
    """The closing leg (last stop → start) has no coordinate on the Route
    contract; a vignette near ONLY that segment never surfaces."""
    start_below = (48.8450, 2.3500)  # 2D geometry so the closing leg is distinct
    stops = _stops_ab()
    closing_mid = _mid(_B, start_below)
    v = _poi("v-closing", tier=2, lat=closing_mid[0], lng=closing_mid[1])
    snap = _snap([*stops, v], {"v-closing": _beats("v-closing")})
    route = summarise_route(
        stops,
        start_lat=start_below[0],
        start_lng=start_below[1],
        round_trip=True,
        duration_min=60,
        spine_area=None,
    )
    assert len(route.transits) == 3  # start→A, A→B, B→start (closing)
    assert select_vignettes(route, snap) == {}


def test_max_detour_constant_locked():
    assert VIGNETTE_MAX_DETOUR_M == 50.0


# ---------------------------------------------------------------------------
# Step B.2 — Route carries vignettes (additive contract field)
# ---------------------------------------------------------------------------


def test_route_contract_vignettes_defaults_empty():
    """The contract field is additive: a plain summarised Route carries {}."""
    assert _route(_stops_ab()).vignettes == {}


def _corpus_poi(
    pid: str,
    *,
    tier: int = 5,
    lat: float,
    lng: float,
    beat_count: int = 8,
) -> POI:
    return POI(
        id=pid,
        name=pid,
        tier=tier,
        poi_role="stop",
        lat=lat,
        lng=lng,
        areas=("Le Marais",),
        beat_count=beat_count,
    )


def _corpus_snap(pois: list[POI]) -> CorpusSnapshot:
    """Auto-inject rich active beats per POI (test_tour_selection pattern) so
    the Phase 6 density gate clears and every POI has something to say."""
    beats = {
        p.id: tuple(
            BeatRef(
                id=f"{p.id}-b{i}",
                poi_id=p.id,
                est_spoken_seconds=240,
                active_status="active",
                script_body="A line worth hearing as you pass. And one more.",
            )
            for i in range(max(0, p.beat_count))
        )
        for p in pois
    }
    return CorpusSnapshot(
        pois=tuple(pois),
        beats_by_poi=beats,
        area_types={"Paris": "city", "Le Marais": "neighborhood"},
        adjacent_areas={},
    )


_PDV = (48.8555, 2.3656)


def _select_route_fixture() -> tuple[list[POI], POI]:
    """Dwell anchors (density fillers + two east anchors) and a tier-2
    vignette POI 20 m off the anchor-to-anchor leg."""
    fillers = [
        _corpus_poi(f"filler-{i}", lat=_PDV[0] + 0.00005 * i, lng=_PDV[1] + 0.00005 * i)
        for i in range(4)
    ]
    a1 = _corpus_poi("anchor-1", lat=48.8555, lng=2.3690)
    a2 = _corpus_poi("anchor-2", lat=48.8555, lng=2.3730)
    leg_mid_lng = (2.3690 + 2.3730) / 2.0
    v = _corpus_poi("v-walkpast", tier=2, lat=48.8555 + 20 * _DEG_PER_M_LAT, lng=leg_mid_lng)
    return [*fillers, a1, a2], v


def test_select_route_populates_vignettes_after_ordering():
    from src.tour.contract import TourInput
    from src.tour.selection import select_route

    dwell_pool, v = _select_route_fixture()
    snap = _corpus_snap([*dwell_pool, v])
    inp = TourInput(start=_PDV, duration_min=60, city_slug="paris", round_trip=False)
    route = select_route(inp, snap)

    assert "v-walkpast" not in [p.id for p in route.pois]  # never a dwell stop
    assert route.vignettes, "vignette POI on a leg must be surfaced"
    hits = [(leg, p.id) for leg, pois in route.vignettes.items() for p in pois]
    assert len(hits) == 1 and hits[0][1] == "v-walkpast"  # exactly once, one leg
    leg_idx = hits[0][0]
    # The leg carrying it is the anchor-1 → anchor-2 walk (its 50 m corridor).
    assert {route.pois[leg_idx - 1].id, route.pois[leg_idx].id} == {"anchor-1", "anchor-2"}


def test_select_route_identity_vignettes_are_additive_metadata():
    """IDENTITY: adding a vignette-band POI to the corpus changes NOTHING
    about the dwell route — pois, order, and transits are byte-identical;
    the vignette arrives as additive metadata only."""
    from src.tour.contract import TourInput
    from src.tour.selection import select_route

    dwell_pool, v = _select_route_fixture()
    inp = TourInput(start=_PDV, duration_min=60, city_slug="paris", round_trip=False)
    route_without = select_route(inp, _corpus_snap(dwell_pool))
    route_with = select_route(inp, _corpus_snap([*dwell_pool, v]))

    assert route_with.pois == route_without.pois
    assert route_with.transits == route_without.transits
    assert route_without.vignettes == {}
    assert route_with.vignettes != {}
