"""M5 REACH — isochrone membership + ReachVerdict mode mapping. Hermetic.

Extends the density-gate coverage (tests/test_tour_density.py): the gate's
GREEN/YELLOW/RED statuses map to ReachVerdict.mode standard/ambient|redirect/
refuse, and the candidate filter switches from the analytic haversine circle
to the (mocked) Valhalla walking isochrone, radius fallback when degraded.

Fixture math (one-way 60 min): target_audio = 60 x 0.83 x 0.6 x 60 = 1793s,
so 4 anchors x 3 beats x 100s = 1200s puts fill at 0.67 — YELLOW by fill.
Round-trip 60 min envelopes: 369m (round-trip) vs 738m (one-way equivalent).
"""

from __future__ import annotations

import json

import httpx
import pytest

from src.tour.contract import BeatRef, TourInput
from src.tour.density import TourabilityRefusedError
from src.tour.routing_client import RoutingClient
from src.tour.selection import _isochrone_walk_minutes, select_route
from tests.test_tour_selection import PDV, _density_fillers, _poi, _snap


def _beats(poi_id: str, n: int, spoken_s: int) -> list[BeatRef]:
    return [
        BeatRef(
            id=f"{poi_id}-b{i}",
            poi_id=poi_id,
            est_spoken_seconds=spoken_s,
            active_status="active",
        )
        for i in range(n)
    ]


def _thin_cluster(prefix: str = "thin") -> tuple[list, dict]:
    """4 colocated anchors, 3x100s beats each → fill ≈ 0.67 (YELLOW)."""
    pois = [
        _poi(f"{prefix}-{i}", lat=PDV[0] + 0.00005 * i, lng=PDV[1], areas=("Le Marais",))
        for i in range(4)
    ]
    beats = {p.id: _beats(p.id, 3, 100) for p in pois}
    return pois, beats


# Isochrone box: generous to the west of PdV, cut off ~150m east of it.
_BOX_W, _BOX_E = PDV[1] - 0.02, PDV[1] + 0.002
_BOX_S, _BOX_N = PDV[0] - 0.01, PDV[0] + 0.01


def _box_isochrone_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/isochrone":
        ring = [
            [_BOX_W, _BOX_S],
            [_BOX_E, _BOX_S],
            [_BOX_E, _BOX_N],
            [_BOX_W, _BOX_N],
            [_BOX_W, _BOX_S],
        ]
        return httpx.Response(
            200,
            json={
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"metric": "time"},
                        "geometry": {"type": "Polygon", "coordinates": [ring]},
                    }
                ],
            },
        )
    if request.url.path == "/route":
        # Plausible routed legs so M3's divisor works during these tests.
        body = json.loads(request.content)
        a, b = body["locations"]
        from src.tour.routing import haversine_m

        d = haversine_m(a["lat"], a["lon"], b["lat"], b["lon"])
        return httpx.Response(
            200,
            json={
                "trip": {
                    "legs": [
                        {"summary": {"time": round(d * 1.3), "length": d / 1000.0},
                         "shape": "iso_mock_shape"}
                    ]
                }
            },
        )
    return httpx.Response(404)


def _client(handler) -> RoutingClient:
    http = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://valhalla.test")
    return RoutingClient(client=http)


def _refusing(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("refused", request=request)


# ---------------------------------------------------------------------------
# Mode mapping
# ---------------------------------------------------------------------------


def test_green_maps_to_standard():
    snap = _snap(_density_fillers(PDV), area_types={"Le Marais": "neighborhood"})
    inp = TourInput(start=PDV, duration_min=60, city_slug="paris", round_trip=True)
    route = select_route(inp, snap)
    assert route.reach is not None
    assert route.reach.mode == "standard"
    assert route.reach.degraded is True  # no client → analytic envelope
    assert route.tourability is None  # GREEN attaches nothing


def test_thin_yellow_maps_to_ambient():
    pois, beats = _thin_cluster()
    snap = _snap(pois, area_types={"Le Marais": "neighborhood"}, beats_by_poi=beats)
    inp = TourInput(start=PDV, duration_min=60, city_slug="paris", round_trip=False)
    route = select_route(inp, snap)
    assert route.reach.mode == "ambient"
    assert route.reach.alternative_destination is None
    assert route.tourability is not None and route.tourability.status == "YELLOW"


def test_round_trip_yellow_with_gem_maps_to_redirect():
    pois, beats = _thin_cluster()
    # Tier-5 gem ~500m east: beyond the 369m round-trip envelope, inside the
    # 738m one-way equivalent → density suggests it as the one-way alternative.
    gem = _poi("faraway-gem", lat=PDV[0], lng=PDV[1] + 0.00683, areas=("Le Marais",))
    beats["faraway-gem"] = _beats("faraway-gem", 4, 200)
    snap = _snap([*pois, gem], area_types={"Le Marais": "neighborhood"}, beats_by_poi=beats)
    inp = TourInput(start=PDV, duration_min=60, city_slug="paris", round_trip=True)
    route = select_route(inp, snap)
    assert route.reach.mode == "redirect"
    assert route.reach.alternative_destination == "faraway-gem"


def test_red_still_refuses():
    lone = _poi("lone", lat=PDV[0], lng=PDV[1])
    snap = _snap([lone], beats_by_poi={"lone": _beats("lone", 3, 100)})
    inp = TourInput(start=PDV, duration_min=60, city_slug="paris", round_trip=False)
    with pytest.raises(TourabilityRefusedError):
        select_route(inp, snap)


# ---------------------------------------------------------------------------
# Isochrone membership vs the old radius
# ---------------------------------------------------------------------------


def test_out_of_isochrone_poi_rejected_but_radius_fallback_admits():
    """A POI inside the straight-line envelope but outside the walking
    isochrone (across the river, no bridge) is rejected — the exact case the
    analytic circle got wrong. Without the isochrone it is still admitted."""
    east = _poi("east-of-river", lat=PDV[0], lng=PDV[1] + 0.0055, areas=("Le Marais",))
    pois = [*_density_fillers(PDV), east]
    snap = _snap(pois, area_types={"Le Marais": "neighborhood"})
    inp = TourInput(start=PDV, duration_min=60, city_slug="paris", round_trip=False)

    with _client(_box_isochrone_handler) as rc:
        iso_route = select_route(inp, snap, routing_client=rc)
    fallback_route = select_route(inp, snap)

    assert iso_route.reach.degraded is False
    assert "east-of-river" not in [p.id for p in iso_route.pois]
    assert fallback_route.reach.degraded is True
    assert "east-of-river" in [p.id for p in fallback_route.pois]


def test_isochrone_refused_falls_back_degraded_with_same_roster():
    pois = _density_fillers(PDV)
    snap = _snap(pois, area_types={"Le Marais": "neighborhood"})
    inp = TourInput(start=PDV, duration_min=60, city_slug="paris", round_trip=True)

    with _client(_refusing) as rc:
        degraded_route = select_route(inp, snap, routing_client=rc)
    bare_route = select_route(inp, snap)

    assert degraded_route.reach.degraded is True
    assert [p.id for p in degraded_route.pois] == [p.id for p in bare_route.pois]


def test_reachable_poi_count_reflects_isochrone():
    east = _poi("east-of-river", lat=PDV[0], lng=PDV[1] + 0.0055, areas=("Le Marais",))
    pois = [*_density_fillers(PDV), east]
    snap = _snap(pois, area_types={"Le Marais": "neighborhood"})
    inp = TourInput(start=PDV, duration_min=60, city_slug="paris", round_trip=False)

    with _client(_box_isochrone_handler) as rc:
        iso_route = select_route(inp, snap, routing_client=rc)
    fallback_route = select_route(inp, snap)

    assert iso_route.reach.reachable_poi_count == 4  # fillers only
    assert fallback_route.reach.reachable_poi_count == 5  # circle admits east


# ---------------------------------------------------------------------------
# Contour minutes
# ---------------------------------------------------------------------------


def test_isochrone_contour_minutes_mirror_walk_budget():
    # 60 min: walk budget = 60 x 0.83 x 0.4 = 19.92 min one-way, half out-and-back.
    assert _isochrone_walk_minutes(60, round_trip=False) == 20
    assert _isochrone_walk_minutes(60, round_trip=True) == 10
    assert _isochrone_walk_minutes(1, round_trip=True) == 1  # floor


def test_reach_verdict_round_trips_on_contract():
    from src.tour.contract import ReachVerdict

    v = ReachVerdict(
        mode="redirect",
        degraded=True,
        walk_minutes=20,
        reachable_poi_count=7,
        alternative_destination="Notre-Dame Cathedral",
    )
    assert ReachVerdict.model_validate(v.model_dump()) == v
