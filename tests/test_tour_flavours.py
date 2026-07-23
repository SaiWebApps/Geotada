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
from src.tour.selection import (
    DIVERSITY_PENALTY,
    CertificationPlanningInfeasibleError,
    _jaccard,
    select_k_routes,
    select_route,
)
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


def test_optional_infeasible_flavour_preserves_valid_primary(
    monkeypatch: pytest.MonkeyPatch,
):
    from src.tour import selection as selection_module

    primary = Route(
        pois=(_poi("primary", lat=PDV[0], lng=PDV[1]),),
        transits=(),
        total_walk_distance_m=0,
        total_walk_seconds=0,
    )
    calls = 0

    def fake_select_route(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return primary
        raise CertificationPlanningInfeasibleError(
            policy_id="test-policy",
            minimum_elapsed_seconds=3240,
            maximum_elapsed_seconds=3960,
            best_elapsed_seconds=3207,
            reason="optional penalized flavour cannot reach the band",
        )

    monkeypatch.setattr(selection_module, "select_route", fake_select_route)

    assert selection_module.select_k_routes(_INPUT, _dense_snap(), 3) == [primary]
    assert calls == 2


def test_overlapping_penalized_flavour_gets_one_strict_exclusion_rerun(
    monkeypatch: pytest.MonkeyPatch,
):
    from src.tour import selection as selection_module

    primary = Route(
        pois=tuple(_poi(poi_id, lat=PDV[0], lng=PDV[1]) for poi_id in ("a", "b", "c")),
        transits=(),
        total_walk_distance_m=0,
        total_walk_seconds=0,
    )
    distinct = Route(
        pois=tuple(_poi(poi_id, lat=PDV[0], lng=PDV[1]) for poi_id in ("d", "e")),
        transits=(),
        total_walk_distance_m=0,
        total_walk_seconds=0,
    )
    penalties = []

    def fake_select_route(*_args, **kwargs):
        penalty = kwargs.get("score_penalty")
        penalties.append(penalty)
        if penalty is None:
            return primary
        if set(penalty.values()) == {DIVERSITY_PENALTY}:
            return primary
        assert set(penalty.values()) == {0.0}
        return distinct

    monkeypatch.setattr(selection_module, "select_route", fake_select_route)

    assert selection_module.select_k_routes(_INPUT, _dense_snap(), 2) == [primary, distinct]
    assert penalties == [None, {"a": 0.3, "b": 0.3, "c": 0.3}, {"a": 0.0, "b": 0.0, "c": 0.0}]


def test_flavours_are_deterministic():
    snap = _dense_snap()
    with _client() as rc:
        first = select_k_routes(_INPUT, snap, 3, routing_client=rc)
    with _client() as rc:
        second = select_k_routes(_INPUT, snap, 3, routing_client=rc)
    assert [[p.id for p in f.pois] for f in first] == [[p.id for p in f.pois] for f in second]


@pytest.mark.parametrize("duration_min", (30, 60, 90, 120))
def test_all_flavours_multi_stop_when_primary_is_multi_stop(duration_min: int):
    """2026-07-03 single-stop class guard: NO flavour may collapse to one stop.

    DIVERSITY_PENALTY (0.3) multiplies used-POI scores on re-runs and feeds
    THREE ranking sites — the greedy value, the endpoint-pull far ranking and
    the fill-pass ranking. A re-run can therefore pick a pathological far
    first anchor (the penalty flips the near/far value ordering), lose the
    endpoint-pull that saved flavour 1, or starve the fill pass — collapsing
    flavour 2/3 to one stop while flavour 1 stays healthy. Today that ships
    as a 1-stop RouteOption card in /trips/generate options[] with zero test
    coverage; the existing tests here check distinctness/validation/
    determinism but never a stop count on the penalized re-runs.

    The duration sweep matters because the penalty interacts with the
    per-duration budgets: at d=30 the budgets are tightest (flavours reach
    2-3 stops only via the pull/fill rescue); at d=120 flavour 1 uses most of
    the grid so the re-run is near-uniformly penalized (an implementation
    that divides by the penalty, or floors it at 0, collapses there first).
    """
    from src.tour.routing import walk_budget_seconds

    snap = _dense_snap()
    inp = TourInput(start=PDV, duration_min=duration_min, city_slug="paris", round_trip=False)
    with _client() as rc:
        flavours = select_k_routes(inp, snap, 3, routing_client=rc)

    # Precondition: the dense fixture must yield a multi-stop primary. If
    # THIS fails, the fixture broke (recalibrate it) — not the invariant.
    assert len(flavours[0].pois) >= 2, (
        f"fixture drifted: primary flavour is {[p.id for p in flavours[0].pois]}"
    )
    # At d=120 a near-uniformly penalized re-run may legitimately reproduce
    # flavour 1's stop set (Jaccard >= 0.60 ends the search), so the flavour
    # COUNT is only pinned on the cells verified multi-flavour at HEAD.
    if duration_min in (30, 60, 90):
        assert len(flavours) >= 2, f"d={duration_min}: expected >=2 flavours"

    budget = walk_budget_seconds(duration_min)
    for i, flavour in enumerate(flavours):
        # The single-stop floor — the actual class guard.
        assert len(flavour.pois) >= 2, (
            f"d={duration_min} flavour {i} collapsed to "
            f"{[p.id for p in flavour.pois]} — a 1-stop RouteOption card"
        )
        # Budget sanity on the divisor the engine actually enforces: with a
        # routing client, greedy/pull/fill budget checks run on ROUTED leg
        # seconds (the mock's 1.3 s/m), while Route.total_walk_seconds stays
        # the pace-corrected haversine metadata (1.62 s/m, deliberately NOT
        # budget-bounded under a faster routed divisor — see routing.py M2).
        routed_walk = sum(
            t.leg_seconds if t.leg_seconds is not None else t.walk_seconds
            for t in flavour.transits
        )
        assert routed_walk <= budget + 5, (
            f"d={duration_min} flavour {i}: routed walk {routed_walk}s > budget {budget}s"
        )


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
    # Step 3.4: build_route_option now scores spotlight/band, so it needs the
    # snapshot (POI tiers for gravity, beat lenses for lens_relevance). Mirror
    # the route's POIs and their beats exactly.
    snapshot = _snap(
        list(pois),
        beats_by_poi={pid: [b for b in beats_by_id.values() if b.poi_id == pid]
                      for pid in ("p1", "p2")},
    )
    return route, script, beats_by_id, snapshot


def test_build_route_option_maps_engine_outputs():
    route, script, beats_by_id, snapshot = _hand_built_route_and_script()
    opt = build_route_option(
        route, script, beats_by_id, route_id="trip-1-opt1", snapshot=snapshot
    )

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
    route, script, beats_by_id, snapshot = _hand_built_route_and_script()
    opt = build_route_option(route, script, beats_by_id, route_id="rt", snapshot=snapshot)
    assert RouteOption.model_validate(opt.model_dump()) == opt


def test_build_route_option_populates_spotlight_and_band_per_stop():
    """Step 3.4 (spec s3.1/s7): every selected stop carries a strictly positive
    spotlight score and a band. The fixture requests no lens, so lens_relevance
    is uniform 1.0 and on-corridor proximity is 1.0, giving spotlight == gravity
    == tier: p1 (tier 5) = 5.0 -> headline -> dwell; p2 (tier 3) = 3.0 -> full ->
    dwell. The score must be computed, not the 0.0 default."""
    route, script, beats_by_id, snapshot = _hand_built_route_and_script()
    opt = build_route_option(route, script, beats_by_id, route_id="rt", snapshot=snapshot)
    assert opt.stops, "fixture must produce at least one stop"
    for stop in opt.stops:
        assert stop.spotlight > 0.0
        assert stop.band in ("dwell", "vignette")
    by_id = {s.poi_id: s for s in opt.stops}
    # No lens requested -> spotlight collapses to gravity (tier).
    assert by_id["p1"].spotlight == pytest.approx(5.0)
    assert by_id["p2"].spotlight == pytest.approx(3.0)
    # tier-5 (5.0 >= 4.0 headline) and tier-3 (3.0 >= 2.0 full) are both dwell.
    assert by_id["p1"].band == "dwell"
    assert by_id["p2"].band == "dwell"


def test_build_route_option_lens_dims_off_genre_stop_to_vignette():
    """Step 3.4: a requested lens DIMS an off-genre stop via lens_relevance.
    A tier-3 stop whose beats miss the lens scores 3 x LENS_FLOOR (0.25) = 0.75,
    below the short/full cuts -> vignette band; the on-genre tier-5 anchor stays
    a headline dwell. Proves the spotlight (not a fixed default) drives the band."""
    route, script, beats_by_id, snapshot = _hand_built_route_and_script()
    # Request a lens that only p1's beats carry; p2's beat is unlensed (a miss).
    lensed_script = script.model_copy(
        update={
            "inputs": TourInput(
                start=(48.85, 2.35), duration_min=60, city_slug="paris",
                lenses=["hidden_history"],
            )
        }
    )
    opt = build_route_option(
        route, lensed_script, beats_by_id, route_id="rt", snapshot=snapshot
    )
    by_id = {s.poi_id: s for s in opt.stops}
    assert by_id["p1"].spotlight == pytest.approx(5.0)  # tier 5 x direct hit 1.0
    assert by_id["p1"].band == "dwell"
    assert by_id["p2"].spotlight == pytest.approx(0.75)  # tier 3 x LENS_FLOOR 0.25
    assert by_id["p2"].band == "vignette"


def test_route_option_lens_coverage_note_none_without_lens():
    """Step 3.4 (s3.1): no lens requested -> nothing to surface -> note is None."""
    route, script, beats_by_id, snapshot = _hand_built_route_and_script()
    opt = build_route_option(route, script, beats_by_id, route_id="rt", snapshot=snapshot)
    assert opt.lens_coverage_note is None


def test_route_option_lens_coverage_note_reflects_corridor_density():
    """Step 3.4 (s3.1): with a lens requested, the note reports how many route
    POIs speak to it. p1's beats hit hidden_history; p2's beat is unlensed (a
    miss). So 1 of 2 places speak to the lens."""
    route, script, beats_by_id, snapshot = _hand_built_route_and_script()
    lensed_script = script.model_copy(
        update={
            "inputs": TourInput(
                start=(48.85, 2.35), duration_min=60, city_slug="paris",
                lenses=["hidden_history"],
            )
        }
    )
    opt = build_route_option(
        route, lensed_script, beats_by_id, route_id="rt", snapshot=snapshot
    )
    assert opt.lens_coverage_note == "1 of 2 places on this route speak to the chosen lens(es)."


# ---------------------------------------------------------------------------
# Track B Step B.3 — vignettes interleaved into RouteOption.stops
# ---------------------------------------------------------------------------


def _route_script_with_vignette():
    """The hand-built fixture plus one walk-past vignette POI on leg 1
    (the p1 → p2 walk): stops must interleave as [p1, v1, p2]."""
    route, script, beats_by_id, _ = _hand_built_route_and_script()
    v = POI(id="v1", name="Fountain", tier=2, poi_role="stop", lat=48.855, lng=2.355)
    vbeat = BeatRef(
        id="vb1",
        poi_id="v1",
        lenses=("hidden_history",),
        active_status="active",
        script_body="A quiet fountain from another century. It still runs.",
    )
    route = route.model_copy(update={"vignettes": {1: (v,)}})
    snapshot = _snap(
        [*route.pois, v],
        beats_by_poi={
            "p1": [beats_by_id["b1"], beats_by_id["b2"]],
            "p2": [beats_by_id["b3"]],
            "v1": [vbeat],
        },
    )
    return route, script, beats_by_id, snapshot


def test_route_option_interleaves_vignette_after_leg_origin():
    """The vignette on leg 1 (the walk INTO stop 1) sits between stop 0 and
    stop 1, as a minutes=0 walk_past band="vignette" stop with its score."""
    route, script, beats_by_id, snapshot = _route_script_with_vignette()
    opt = build_route_option(route, script, beats_by_id, route_id="rt", snapshot=snapshot)

    assert [s.poi_id for s in opt.stops] == ["p1", "v1", "p2"]
    v_stop = opt.stops[1]
    assert v_stop.band == "vignette"
    assert v_stop.visit_or_walk_past == "walk_past"
    assert v_stop.minutes == 0
    assert v_stop.spotlight == pytest.approx(2.0)  # tier-2, no lens -> gravity
    assert v_stop.lens == "hidden_history"  # dominant lens of its own beats
    assert (v_stop.name, v_stop.lat, v_stop.lng) == ("Fountain", 48.855, 2.355)


def test_route_option_dwell_stops_and_eta_unchanged_by_vignettes():
    """Vignettes are additive: the dwell stops (and eta, which counts routed
    legs + dwell only) are byte-identical with and without them."""
    route_v, script, beats_by_id, snapshot = _route_script_with_vignette()
    route_plain = route_v.model_copy(update={"vignettes": {}})

    opt_v = build_route_option(route_v, script, beats_by_id, route_id="rt", snapshot=snapshot)
    opt_plain = build_route_option(
        route_plain, script, beats_by_id, route_id="rt", snapshot=snapshot
    )

    dwell_only = tuple(s for s in opt_v.stops if s.poi_id != "v1")
    assert dwell_only == opt_plain.stops
    assert opt_v.eta_seconds == opt_plain.eta_seconds
    assert opt_v.lens_summary == opt_plain.lens_summary


def test_route_option_empty_vignettes_is_todays_output():
    """route.vignettes == {} -> exactly today's stop list (no vignette rows)."""
    route, script, beats_by_id, snapshot = _hand_built_route_and_script()
    assert route.vignettes == {}
    opt = build_route_option(route, script, beats_by_id, route_id="rt", snapshot=snapshot)
    assert [s.poi_id for s in opt.stops] == ["p1", "p2"]
    assert all(s.band == "dwell" for s in opt.stops)


def test_route_option_leg0_and_closing_leg_vignette_positions():
    """Contract-general placement: a leg-0 vignette precedes stop 0; a
    closing-leg (index len(stops)) vignette follows the last stop."""
    route, script, beats_by_id, _ = _hand_built_route_and_script()
    v0 = POI(id="v0", name="Gate", tier=2, poi_role="stop", lat=48.849, lng=2.349)
    v_end = POI(id="v9", name="Bridge", tier=2, poi_role="stop", lat=48.861, lng=2.361)
    route = route.model_copy(update={"vignettes": {0: (v0,), 2: (v_end,)}})
    snapshot = _snap(
        [*route.pois, v0, v_end],
        beats_by_poi={
            "p1": [beats_by_id["b1"], beats_by_id["b2"]],
            "p2": [beats_by_id["b3"]],
            "v0": [BeatRef(id="vb0", poi_id="v0", script_body="An old gate.")],
            "v9": [BeatRef(id="vb9", poi_id="v9", script_body="An old bridge.")],
        },
    )
    opt = build_route_option(route, script, beats_by_id, route_id="rt", snapshot=snapshot)
    assert [s.poi_id for s in opt.stops] == ["v0", "p1", "p2", "v9"]
    assert opt.stops[0].band == "vignette" and opt.stops[-1].band == "vignette"


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
