"""Hermetic tests for the M1 RoutingClient (Valhalla pedestrian + haversine fallback).

No Docker, no network, no skips: the Valhalla side is an httpx.MockTransport
speaking the documented /route and /isochrone JSON shapes; the outage side is
a transport that raises ConnectError. The mock "road network" applies a 1.2x
detour at 4 km/h — deliberately different from the fallback's 1.35x at 3 km/h,
so routed and haversine numbers can never coincide on a non-zero leg.
"""

from __future__ import annotations

import json

import httpx
import pytest

from src.tour.routing import haversine_m, pace_corrected_walk_seconds
from src.tour.routing_client import RoutingClient

# Five real Paris points: Eiffel Tower, Louvre, Notre-Dame, Place des Vosges,
# Sacré-Cœur.
POINTS = [
    (48.8584, 2.2945),
    (48.8606, 2.3376),
    (48.8530, 2.3499),
    (48.8556, 2.3656),
    (48.8867, 2.3431),
]

SHAPE = "mock_polyline6_abc123"


def _routed_meters(d_m: float) -> float:
    return d_m * 1.2


def _routed_seconds(d_m: float) -> int:
    return round(_routed_meters(d_m) / (4000.0 / 3600.0))


def _valhalla_handler(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    if request.url.path == "/route":
        a, b = body["locations"]
        d = haversine_m(a["lat"], a["lon"], b["lat"], b["lon"])
        return httpx.Response(
            200,
            json={
                "trip": {
                    "legs": [
                        {
                            "summary": {
                                "time": _routed_seconds(d),
                                "length": _routed_meters(d) / 1000.0,  # km, per API
                            },
                            "shape": SHAPE,
                        }
                    ]
                }
            },
        )
    if request.url.path == "/isochrone":
        return httpx.Response(
            200,
            json={
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"metric": "time"},
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [
                                [[2.29, 48.85], [2.35, 48.85], [2.35, 48.89], [2.29, 48.85]]
                            ],
                        },
                    }
                ],
            },
        )
    return httpx.Response(404)


def _refusing_handler(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection refused", request=request)


def _client(handler) -> RoutingClient:
    http = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://valhalla.test")
    return RoutingClient(client=http)


# ---------------------------------------------------------------------------
# Routed path (mocked Valhalla up)
# ---------------------------------------------------------------------------


def test_matrix_diagonal_zero_and_routed_differs_from_haversine():
    """5x5 Paris matrix: diagonal is 0; every off-diagonal routed time/distance
    differs from the pure haversine fallback (the M1 PROVE asks for >=1)."""
    with _client(_valhalla_handler) as rc:
        differing = 0
        for i, (lat1, lng1) in enumerate(POINTS):
            for j, (lat2, lng2) in enumerate(POINTS):
                secs = rc.leg_seconds(lat1, lng1, lat2, lng2)
                fallback = pace_corrected_walk_seconds(haversine_m(lat1, lng1, lat2, lng2))
                if i == j:
                    assert secs == 0
                else:
                    assert secs > 0
                    if secs != fallback:
                        differing += 1
        assert differing == 20, "every non-zero leg should be visibly routed, not haversine"


def test_route_parses_documented_response_fields():
    """seconds <- trip.legs[0].summary.time; metres <- length (km) * 1000;
    polyline <- trip.legs[0].shape."""
    (lat1, lng1), (lat2, lng2) = POINTS[0], POINTS[1]
    d = haversine_m(lat1, lng1, lat2, lng2)
    with _client(_valhalla_handler) as rc:
        seconds, meters, shape = rc.route(lat1, lng1, lat2, lng2)
    assert seconds == _routed_seconds(d)
    assert meters == pytest.approx(_routed_meters(d))
    assert shape == SHAPE


def test_isochrone_returns_feature_collection():
    with _client(_valhalla_handler) as rc:
        iso = rc.isochrone(48.8584, 2.2945, 30)
    assert iso is not None
    assert iso["type"] == "FeatureCollection"
    assert iso["features"][0]["geometry"]["type"] == "Polygon"


def test_requests_use_documented_wire_format():
    """Pin the outgoing JSON: pedestrian costing, lat/lon keys, km units,
    minute contours with polygons=true."""
    seen: list[tuple[str, dict]] = []

    def recording_handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, json.loads(request.content)))
        return _valhalla_handler(request)

    with _client(recording_handler) as rc:
        rc.route(*POINTS[0], *POINTS[1])
        rc.isochrone(48.8584, 2.2945, 30)

    route_body = dict(seen)["/route"]
    assert route_body["costing"] == "pedestrian"
    assert route_body["units"] == "kilometers"
    assert route_body["locations"][0] == {"lat": POINTS[0][0], "lon": POINTS[0][1]}

    iso_body = dict(seen)["/isochrone"]
    assert iso_body["costing"] == "pedestrian"
    assert iso_body["contours"] == [{"time": 30.0}]
    assert iso_body["polygons"] is True


# ---------------------------------------------------------------------------
# Fallback path (Valhalla down or broken)
# ---------------------------------------------------------------------------


def test_connect_error_falls_back_to_exact_haversine():
    """The M1 PROVE: ConnectionError -> exactly
    pace_corrected_walk_seconds(haversine_m(...)), polyline None."""
    with _client(_refusing_handler) as rc:
        for lat1, lng1 in POINTS:
            for lat2, lng2 in POINTS:
                d = haversine_m(lat1, lng1, lat2, lng2)
                expected = pace_corrected_walk_seconds(d)
                assert rc.leg_seconds(lat1, lng1, lat2, lng2) == expected
                seconds, meters, shape = rc.route(lat1, lng1, lat2, lng2)
                assert (seconds, shape) == (expected, None)
                assert meters == pytest.approx(d)


def test_http_500_falls_back():
    with _client(lambda request: httpx.Response(500, text="boom")) as rc:
        (lat1, lng1), (lat2, lng2) = POINTS[0], POINTS[4]
        d = haversine_m(lat1, lng1, lat2, lng2)
        assert rc.leg_seconds(lat1, lng1, lat2, lng2) == pace_corrected_walk_seconds(d)


def test_garbage_response_falls_back():
    with _client(lambda request: httpx.Response(200, json={"unexpected": True})) as rc:
        (lat1, lng1), (lat2, lng2) = POINTS[1], POINTS[3]
        d = haversine_m(lat1, lng1, lat2, lng2)
        seconds, meters, shape = rc.route(lat1, lng1, lat2, lng2)
        assert seconds == pace_corrected_walk_seconds(d)
        assert meters == pytest.approx(d)
        assert shape is None


def test_isochrone_none_on_connect_error_and_on_garbage():
    with _client(_refusing_handler) as rc:
        assert rc.isochrone(48.8584, 2.2945, 30) is None
    with _client(lambda request: httpx.Response(200, json={"type": "nope"})) as rc:
        assert rc.isochrone(48.8584, 2.2945, 30) is None


def test_default_construction_owns_a_client():
    """RoutingClient() with no injected client builds (and closes) its own —
    no network call is made by construction."""
    rc = RoutingClient()
    rc.close()


# ---------------------------------------------------------------------------
# M2 — routed leg_seconds/polyline on the contract; summarise_route/select_route
# ---------------------------------------------------------------------------

from src.tour.contract import Route, TourInput, TransitSegment
from src.tour.routing import summarise_route
from src.tour.selection import select_route
from tests.test_tour_selection import PDV, _density_fillers, _poi, _snap


def test_transit_segment_m2_fields_round_trip_and_default():
    routed = TransitSegment(
        from_poi_id=None,
        to_poi_id="p1",
        distance_m=500.0,
        walk_seconds=810,
        leg_seconds=540,
        polyline=SHAPE,
        source="valhalla",
    )
    assert TransitSegment.model_validate(routed.model_dump()) == routed
    # Pre-M2 construction still works; new fields default to the haversine era.
    legacy = TransitSegment(from_poi_id=None, to_poi_id="p1", distance_m=500.0, walk_seconds=810)
    assert (legacy.leg_seconds, legacy.polyline, legacy.source) == (None, None, "haversine")
    assert TransitSegment.model_validate(legacy.model_dump()) == legacy


def test_route_m2_fields_round_trip_and_default():
    route = Route(
        pois=(),
        transits=(),
        total_walk_distance_m=0.0,
        total_walk_seconds=0,
        audio_budget_seconds=0,
        routed=False,
        route_polyline=None,
    )
    assert (route.routed, route.route_polyline) == (False, None)
    assert (route.backtrack_ratio, route.flow_score) == (0.0, 0.0)
    assert Route.model_validate(route.model_dump()) == route


def _two_stop_pois():
    return [
        _poi("a", lat=PDV[0] + 0.0030, lng=PDV[1], areas=("Le Marais",)),  # ~330m N
        _poi("b", lat=PDV[0], lng=PDV[1] + 0.0045, areas=("Le Marais",)),  # ~330m E
    ]


def test_summarise_route_with_client_populates_routed_legs():
    with _client(_valhalla_handler) as rc:
        route = summarise_route(
            _two_stop_pois(),
            start_lat=PDV[0],
            start_lng=PDV[1],
            round_trip=True,
            duration_min=60,
            spine_area="Le Marais",
            routing_client=rc,
        )
    assert route.routed is True
    assert len(route.transits) == 3  # start->a, a->b, b->start
    for seg in route.transits:
        assert seg.source == "valhalla"
        assert seg.polyline == SHAPE
        expected = _routed_seconds(seg.distance_m)
        assert seg.leg_seconds == expected
        # budgets stay haversine: walk_seconds untouched by the client
        assert seg.walk_seconds == pace_corrected_walk_seconds(seg.distance_m)
        assert seg.leg_seconds != seg.walk_seconds  # 1.2x@4km/h vs 1.35x@3km/h


def test_summarise_route_without_client_keeps_haversine_defaults():
    route = summarise_route(
        _two_stop_pois(),
        start_lat=PDV[0],
        start_lng=PDV[1],
        round_trip=False,
        duration_min=60,
        spine_area="Le Marais",
    )
    assert route.routed is False
    for seg in route.transits:
        assert (seg.leg_seconds, seg.polyline, seg.source) == (None, None, "haversine")


def test_summarise_route_client_down_marks_haversine_source():
    with _client(_refusing_handler) as rc:
        route = summarise_route(
            _two_stop_pois(),
            start_lat=PDV[0],
            start_lng=PDV[1],
            round_trip=False,
            duration_min=60,
            spine_area="Le Marais",
            routing_client=rc,
        )
    assert route.routed is False
    for seg in route.transits:
        assert seg.source == "haversine"
        assert seg.polyline is None
        # the client's fallback equals the budget math exactly
        assert seg.leg_seconds == seg.walk_seconds


def test_select_route_same_pois_with_and_without_client():
    """The M2 PROVE: a routing client changes NO selection decision (Jaccard
    1.0, same order) — it only enriches the final transits."""
    pois = [*_density_fillers(PDV), *_two_stop_pois()]
    snap = _snap(pois, area_types={"Le Marais": "neighborhood"})
    tour_input = TourInput(start=PDV, duration_min=60, city_slug="paris", round_trip=False)

    bare = select_route(tour_input, snap)
    with _client(_valhalla_handler) as rc:
        routed = select_route(tour_input, snap, routing_client=rc)

    assert [p.id for p in routed.pois] == [p.id for p in bare.pois]  # Jaccard == 1.0
    assert routed.pois, "GREEN fixture must select something"
    assert routed.routed is True
    assert all(seg.leg_seconds is not None for seg in routed.transits)
    assert any(
        seg.leg_seconds != seg.walk_seconds for seg in routed.transits
    ), "at least one leg must be visibly routed"
    # budgets identical with/without the client
    assert routed.total_walk_seconds == bare.total_walk_seconds
