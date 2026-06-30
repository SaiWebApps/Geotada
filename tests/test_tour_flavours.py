"""M6 k-flavours — select_k_routes + RouteOption assembly. Hermetic.

PROVE (IMPLEMENTATION-PLAN M6): dense GREEN fixture with mocked routing,
k=3 → flavour count in {2,3}; every pair under 0.60 Jaccard; ordered paths
pairwise differ; each flavour's Script passes validation.
"""

from __future__ import annotations

import json

import httpx
import pytest

from src.tour.beat_select import select_poi_beats
from src.tour.contract import (
    POI,
    BeatRef,
    BeatSequence,
    Route,
    RouteOption,
    RouteOptionStop,
    Script,
    ScriptPOI,
    TourInput,
    TransitSegment,
    ValidationReport,
)
from src.tour.density import TourabilityRefusedError
from src.tour.generation import generate
from src.tour.options import build_route_option
from src.tour.routing_client import RoutingClient
from src.tour.selection import _jaccard, select_k_routes, select_route
from tests.test_tour_selection import PDV, _poi, _snap

# ---------------------------------------------------------------------------
# Dense GREEN fixture: 4 directional clusters x 3 rich POIs, all inside the
# 60-min one-way envelope (738m). Rich-pool GREEN (fill ~8, 12 anchors).
# ---------------------------------------------------------------------------


def _grid_pois() -> list[POI]:
    out = []
    directions = [(0.003, 0.0), (0.0, 0.0045), (-0.003, 0.0), (0.0, -0.0045)]
    for d, (dlat, dlng) in enumerate(directions):
        for i in range(3):
            scale = 1.0 + 0.15 * i
            out.append(
                _poi(
                    f"poi-{d}-{i}",
                    lat=PDV[0] + dlat * scale,
                    lng=PDV[1] + dlng * scale,
                    areas=("Le Marais",),
                )
            )
    return out


def _rich_beats(pois) -> dict[str, list[BeatRef]]:
    return {
        p.id: [
            BeatRef(
                id=f"{p.id}-b{i}",
                poi_id=p.id,
                est_spoken_seconds=240,
                active_status="active",
                script_body=f"Story {i} about {p.id}.",
                lenses=("hidden_history",) if i % 2 == 0 else ("historic_arch",),
            )
            for i in range(5)
        ]
        for p in pois
    }


def _dense_snap():
    pois = _grid_pois()
    return _snap(
        pois,
        area_types={"Le Marais": "neighborhood"},
        beats_by_poi=_rich_beats(pois),
    )


def _mock_handler(request: httpx.Request) -> httpx.Response:
    """Generous isochrone + haversine-proportional routed legs."""
    if request.url.path == "/isochrone":
        ring = [[2.20, 48.80], [2.45, 48.80], [2.45, 48.92], [2.20, 48.92], [2.20, 48.80]]
        return httpx.Response(
            200,
            json={
                "type": "FeatureCollection",
                "features": [
                    {"type": "Feature", "properties": {},
                     "geometry": {"type": "Polygon", "coordinates": [ring]}}
                ],
            },
        )
    if request.url.path == "/route":
        from src.tour.routing import haversine_m

        body = json.loads(request.content)
        a, b = body["locations"]
        d = haversine_m(a["lat"], a["lon"], b["lat"], b["lon"])
        return httpx.Response(
            200,
            json={"trip": {"legs": [{"summary": {"time": round(d * 1.3), "length": d / 1000.0},
                                     "shape": "flavour_mock_shape"}]}},
        )
    return httpx.Response(404)


def _client() -> RoutingClient:
    http = httpx.Client(
        transport=httpx.MockTransport(_mock_handler), base_url="http://valhalla.test"
    )
    return RoutingClient(client=http)


_INPUT = TourInput(start=PDV, duration_min=60, city_slug="paris", round_trip=False)


# ---------------------------------------------------------------------------
# The M6 PROVE
# ---------------------------------------------------------------------------


def test_k3_yields_2_or_3_distinct_flavours():
    snap = _dense_snap()
    with _client() as rc:
        flavours = select_k_routes(_INPUT, snap, 3, routing_client=rc)

    assert 2 <= len(flavours) <= 3, f"got {len(flavours)} flavours"
    id_sets = [{p.id for p in f.pois} for f in flavours]
    id_seqs = [[p.id for p in f.pois] for f in flavours]
    for i in range(len(flavours)):
        for j in range(i + 1, len(flavours)):
            assert _jaccard(id_sets[i], id_sets[j]) < 0.60, (
                f"flavours {i},{j} overlap too much: {sorted(id_sets[i] & id_sets[j])}"
            )
            assert id_seqs[i] != id_seqs[j], "ordered paths must pairwise differ"


def test_each_flavour_passes_validation():
    snap = _dense_snap()
    with _client() as rc:
        flavours = select_k_routes(_INPUT, snap, 3, routing_client=rc)
    assert flavours
    for flavour in flavours:
        plans = [select_poi_beats(p, snap.beats_for(p.id)) for p in flavour.pois]
        script = generate(BeatSequence(poi_beats=tuple(plans)), flavour, _INPUT)
        assert script.validation.passed, (
            f"untraceable={[s.text[:60] for s in script.validation.untraceable_sentences]}"
        )
        assert any(s.source_type == "beat" for s in script.script)


def test_k1_is_the_select_route_delegate():
    snap = _dense_snap()
    with _client() as rc:
        only = select_k_routes(_INPUT, snap, 1, routing_client=rc)
    with _client() as rc:
        direct = select_route(_INPUT, snap, routing_client=rc)
    assert len(only) == 1
    assert [p.id for p in only[0].pois] == [p.id for p in direct.pois]


def test_flavours_are_deterministic():
    snap = _dense_snap()
    with _client() as rc:
        first = select_k_routes(_INPUT, snap, 3, routing_client=rc)
    with _client() as rc:
        second = select_k_routes(_INPUT, snap, 3, routing_client=rc)
    assert [[p.id for p in f.pois] for f in first] == [[p.id for p in f.pois] for f in second]


def test_red_density_raises_through_k_routes():
    lone = _poi("lone", lat=PDV[0], lng=PDV[1])
    snap = _snap([lone], beats_by_poi={"lone": []})
    with pytest.raises(TourabilityRefusedError):
        select_k_routes(_INPUT, snap, 3)


def test_jaccard_basics():
    assert _jaccard(set(), set()) == 0.0
    assert _jaccard({"a"}, {"a"}) == 1.0
    assert _jaccard({"a"}, {"b"}) == 0.0
    assert _jaccard({"a", "b", "c"}, {"b", "c", "d"}) == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# RouteOption assembly
# ---------------------------------------------------------------------------


def _hand_built_route_and_script():
    pois = (
        POI(id="p1", name="Anchor", tier=5, poi_role="stop", lat=48.85, lng=2.35),
        POI(id="p2", name="Passby", tier=3, poi_role="walk_by_only", lat=48.86, lng=2.36),
    )
    transits = (
        TransitSegment(from_poi_id=None, to_poi_id="p1", distance_m=500, walk_seconds=810,
                       leg_seconds=600, polyline="shape1", source="valhalla"),
        TransitSegment(from_poi_id="p1", to_poi_id="p2", distance_m=300, walk_seconds=486),
    )
    route = Route(
        pois=pois, transits=transits, total_walk_distance_m=800, total_walk_seconds=1296,
        audio_budget_seconds=1000,
    )
    script = Script(
        city_slug="paris", generated_at="2026-06-12T00:00:00Z",
        inputs=TourInput(start=(48.85, 2.35), duration_min=60, city_slug="paris"),
        total_audio_seconds=600, total_walking_seconds=1296, total_walk_distance_m=800,
        total_planned_seconds=2000,
        selected_pois=(
            ScriptPOI(id="p1", name="Anchor", tier=5, lat=48.85, lng=2.35,
                      dwell_seconds=300, beat_ids=("b1", "b2")),
            ScriptPOI(id="p2", name="Passby", tier=3, lat=48.86, lng=2.36,
                      dwell_seconds=60, beat_ids=("b3",)),
        ),
        lens_coverage={"hidden_history": 2, "historic_arch": 1},
        script=(), validation=ValidationReport(),
    )
    beats_by_id = {
        "b1": BeatRef(id="b1", poi_id="p1", lenses=("hidden_history",)),
        "b2": BeatRef(id="b2", poi_id="p1", lenses=("hidden_history",)),
        "b3": BeatRef(id="b3", poi_id="p2", lenses=()),
    }
    return route, script, beats_by_id


def test_build_route_option_maps_engine_outputs():
    route, script, beats_by_id = _hand_built_route_and_script()
    opt = build_route_option(route, script, beats_by_id, route_id="trip-1-opt1")

    assert opt.route_id == "trip-1-opt1"
    assert [s.poi_id for s in opt.stops] == ["p1", "p2"]
    assert opt.stops[0].lens == "hidden_history"
    assert opt.stops[0].visit_or_walk_past == "visit"
    assert opt.stops[0].minutes == 5  # 300s dwell
    assert opt.stops[1].lens is None  # unlensed beat
    assert opt.stops[1].visit_or_walk_past == "walk_past"
    # eta: routed leg (600) preferred over haversine (810); unrouted leg uses
    # its walk_seconds (486); plus dwells (300 + 60).
    assert opt.eta_seconds == 600 + 486 + 300 + 60
    assert opt.lens_summary == {"hidden_history": 2, "historic_arch": 1}
    assert opt.degraded is False  # no reach verdict on the hand-built route
    assert opt.stop_audio == {} and opt.why_this_works is None  # M7 slots


def test_route_option_contract_round_trips():
    route, script, beats_by_id = _hand_built_route_and_script()
    opt = build_route_option(route, script, beats_by_id, route_id="rt")
    assert RouteOption.model_validate(opt.model_dump()) == opt


def test_route_option_stop_spotlight_fields_default_behavior_preserving():
    """Step 3.3 (spec s7): RouteOptionStop gains band + spotlight with additive
    defaults — every stop is a full dwell at score 0.0 until Step 3.5 wires the
    spotlight effect. build_route_option does not set them yet, so it must emit
    the defaults."""
    route, script, beats_by_id = _hand_built_route_and_script()
    opt = build_route_option(route, script, beats_by_id, route_id="rt")
    assert opt.stops, "fixture must produce at least one stop"
    for stop in opt.stops:
        assert stop.band == "dwell"
        assert stop.spotlight == 0.0


def test_route_option_lens_coverage_note_defaults_none():
    """Step 3.3 (spec s7): RouteOption gains lens_coverage_note, defaulting None
    until REACH measures per-corridor lens density later in Phase 3."""
    route, script, beats_by_id = _hand_built_route_and_script()
    opt = build_route_option(route, script, beats_by_id, route_id="rt")
    assert opt.lens_coverage_note is None


def test_route_option_round_trips_with_explicit_spotlight_fields():
    """The new fields survive a full model_dump -> model_validate round-trip when
    set to non-default values, so the contract actually carries them."""
    stop = RouteOptionStop(
        poi_id="p1",
        name="Anchor",
        lat=48.85,
        lng=2.35,
        band="vignette",
        spotlight=0.42,
    )
    opt = RouteOption(
        route_id="rt",
        stops=(stop,),
        eta_seconds=600,
        lens_coverage_note="only 2 places on this route speak to film and TV",
    )
    rebuilt = RouteOption.model_validate(opt.model_dump())
    assert rebuilt == opt
    assert rebuilt.stops[0].band == "vignette"
    assert rebuilt.stops[0].spotlight == 0.42
    assert rebuilt.lens_coverage_note == "only 2 places on this route speak to film and TV"
