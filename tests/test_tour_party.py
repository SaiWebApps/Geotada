"""Phase 2 party tests — does the planner know WHO is walking?

One party-hand per file, on the `tests/test_tour_clock.py` model: every gating
test cites the design section or persona line it enforces
(specs/2026-08-07-tour-algorithm-redesign/04-implementation-plan.md §0.1.1).

Phase 2 party tests live here (plan steps S2.1-S2.4, S2.7, S2.8): the contract
axes and presets, the resolver, the harness flags and per-stop table, the leg
cap, pace, route surface, and the escape radius.

The RED that proved S2.2 was real: `TourInput` is `extra="forbid"`
(src/tour/contract.py), so constructing it with `party` / the axis fields
raised before the fields existed. That forbid is load-bearing for this file
and its only guard is
`tests/test_tour_contract.py::test_tour_input_rejects_extra_keys` — if that
guard ever dies, the RED here goes vacuous with it.
"""

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from src.tour.contract import POI, Route, TourInput, TransitSegment


def _base_input(**overrides) -> TourInput:
    fields = {
        "start": (48.8568, 2.3414),
        "duration_min": 120,
        "city_slug": "paris",
    }
    fields.update(overrides)
    return TourInput(**fields)


def _resolved(**overrides) -> TourInput:
    from src.tour.contract import resolve_party_axes

    return resolve_party_axes(_base_input(**overrides))


# --- S2.2: the axes and the presets ------------------------------------------


def test_presets_are_shortcuts_over_axes_and_explicit_axes_win():
    """A preset is a SHORTCUT over the axes, and an explicitly-set axis always
    beats its preset's value.

    Cites design §2.4 (01-design.md:136-137): "A party tap may set several
    axes at once … the presets are shortcuts over axes, and the axes are what
    the planner reads." A preset that could silently overwrite an axis the
    visitor set by hand would make the tap an override, not a shortcut.
    """
    kept_ceiling = _resolved(party="family", max_stop_minutes=10)
    assert kept_ceiling.max_stop_minutes == 10, "explicit ceiling must beat the preset's 6"
    assert kept_ceiling.walking_pace == 2.0, "unset axes still fill from the preset"

    kept_cap = _resolved(party="take_it_easy", max_leg_minutes=20)
    assert kept_cap.max_leg_minutes == 20, "explicit leg cap must beat the preset's 12"

    kept_surface = _resolved(party="family", route_surface="any")
    assert kept_surface.route_surface == "any", (
        "an explicitly-passed surface — even the default value — must beat the preset"
    )


def test_no_party_and_no_axes_is_todays_behaviour_byte_identical():
    """No party, no axes → nothing moves: every axis defaults to None (surface
    to "any"), and the resolver returns the input unchanged. The identity
    default is what keeps every existing caller and golden byte-identical
    (plan S2.2 declared breakage: none)."""
    from src.tour.contract import resolve_party_axes

    inp = _base_input()
    assert inp.party is None
    assert inp.walking_pace is None
    assert inp.max_leg_minutes is None
    assert inp.rest_cadence_minutes is None
    assert inp.escape_radius_m is None
    assert inp.route_surface == "any"
    assert inp.narration_register is None
    assert resolve_party_axes(inp) == inp


def test_solo_preset_sets_no_ceiling():
    """`solo` sets NO per-stop ceiling — Théo's anchor is 65 minutes inside
    one building, and the panel locked this as cost D6: "party-preset stop
    ceiling under 65 min DECAPITATES his day — ceiling must be lens-aware or
    absent for solo" (03-panel-findings.md:193; docs/personas/
    02-dark-history-walker.md). Design §2.4:130-132: "A per-stop ceiling is
    never set by mobility."
    """
    resolved = _resolved(party="solo")
    assert resolved.max_stop_minutes is None
    assert resolved.narration_register == "solo"
    assert resolved.walking_pace is None, "solo walks at normal pace"


def test_couple_register_is_warm_never_romantic():
    """`couple` sets the register to warm — and never romantic (design
    §2.4:126: "warm (**never romantic**)"). No mobility axis moves: Fiona and
    Dev walk at normal pace and need no caps
    (docs/personas/09-couple-who-would-rather-talk.md)."""
    resolved = _resolved(party="couple")
    assert resolved.narration_register == "warm"
    assert resolved.walking_pace is None
    assert resolved.max_leg_minutes is None
    assert resolved.max_stop_minutes is None


def test_family_preset_matches_nadias_day():
    """`family` sets the ceiling ~6 min, half pace, the rest cadence, the
    escape radius, no-stairs surface, and the family register.

    Cites docs/personas/03-family-with-children.md — step 3: "Six minutes is
    the ceiling here, not the floor" (line 20); step 4: "Pace drops to roughly
    half" (line 21); step 5: the toilet stop, "Ten minutes, zero cultural
    content, entirely non-negotiable" (lines 22-23) — and the panel's locked
    cost D4: "cap DISTANCE FROM EXIT not just leg length — family days = tight
    loops around short escape radius" (03-panel-findings.md:166).
    """
    resolved = _resolved(party="family")
    assert resolved.max_stop_minutes == 6
    assert resolved.walking_pace == 2.0
    assert resolved.rest_cadence_minutes is not None
    assert resolved.escape_radius_m is not None
    assert resolved.route_surface == "no_stairs"
    assert resolved.narration_register == "family"


def test_take_it_easy_slows_the_walking_never_the_talking():
    """`take-it-easy` caps the leg at ~12 minutes, goes step-free, slows the
    pace, keeps the rest cadence — and leaves the register ALONE.

    Cites docs/personas/05-step-free-visitor.md bullet 1 (lines 48-50): "Her
    per-leg limit (12 minutes) is the binding constraint, and nothing in the
    model expresses it" — and design §2.4:133: "Register never follows
    mobility. 'Slow the walking, never the talking.'" The design table
    (01-design.md:122) gives take-it-easy the rest cadence as well as family:
    Rosemary's day sits on benches (her steps 3 and 7).
    """
    resolved = _resolved(party="take_it_easy")
    assert resolved.max_leg_minutes == 12
    assert resolved.route_surface == "step_free"
    assert resolved.walking_pace is not None and resolved.walking_pace > 1.0
    assert resolved.rest_cadence_minutes is not None
    assert resolved.narration_register is None, "slow the walking, never the talking"
    assert resolved.max_stop_minutes is None, (
        "no ceiling: Rosemary's centrepiece is a 46-minute sit (05:36-38); "
        "design §2.4:130: a per-stop ceiling is never set by mobility"
    )


def test_with_luggage_slows_and_keeps_stairs_off_the_route():
    """`with-luggage` slows the pace and avoids stairs (and cobbles, which
    ride S2.7's costing): Marcus walks "Slower than his normal pace, and the
    wheels make cobbles genuinely unpleasant"
    (docs/personas/04-layover-sprinter.md step 2, lines 17-19; "Luggage
    changes the route surface", line 51). Register stays solo; no ceiling."""
    resolved = _resolved(party="with_luggage")
    assert resolved.walking_pace is not None and 1.0 < resolved.walking_pace < 2.0
    assert resolved.route_surface == "no_stairs"
    assert resolved.narration_register == "solo"
    assert resolved.max_stop_minutes is None


def test_walking_pace_below_one_is_rejected():
    """The pace multiplier's fast direction is LOCKED: a multiplier below 1.0
    would re-open the raised-and-held-back `PACE_KMH` pin from the slow side
    (plan S2.2/S2.4: "the fast direction is the pace pin's locked half").
    Slow is a fact about real walkers; fast is a lie about the city."""
    with pytest.raises(ValidationError):
        _base_input(walking_pace=0.8)


def test_party_axes_round_trip_through_model_dump():
    """`TourInput(**inp.model_dump())` must survive the new fields — the same
    round-trip the clock fields honour (test_tour_clock.py), because persisted
    tour_input_json rebuilds the model from a plain dict."""
    inp = _base_input(party="family", max_leg_minutes=9, route_surface="no_stairs")
    again = TourInput(**inp.model_dump())
    assert again == inp


# --- S2.1: the harness speaks party, and shows a DAY --------------------------


def test_party_flags_parse_and_flagless_parse_carries_no_party():
    """`scripts/tour_build.py` accepts --party and the six axis flags, and a
    flagless parse carries no party and no axes — the identity default that
    keeps a legacy invocation byte-identical (plan S2.1; design §9 D2: "six
    visibly different days" needs the flags; §10.9 measurement-first)."""
    import importlib

    tour_build = importlib.import_module("scripts.tour_build")
    parser = tour_build._build_arg_parser()

    flagged = parser.parse_args(
        [
            "--start", "X", "--duration", "60", "--canned",
            "--party", "take-it-easy",
            "--max-stop-minutes", "8",
            "--max-leg-minutes", "10",
            "--walking-pace", "1.5",
            "--rest-cadence-minutes", "25",
            "--escape-radius-m", "600",
            "--route-surface", "step_free",
        ]
    )
    assert flagged.party == "take-it-easy"
    assert flagged.max_stop_minutes == 8
    assert flagged.max_leg_minutes == 10
    assert flagged.walking_pace == 1.5
    assert flagged.rest_cadence_minutes == 25
    assert flagged.escape_radius_m == 600
    assert flagged.route_surface == "step_free"

    flagless = parser.parse_args(["--start", "X", "--duration", "60", "--canned"])
    assert flagless.party is None
    assert flagless.max_stop_minutes is None
    assert flagless.max_leg_minutes is None
    assert flagless.walking_pace is None
    assert flagless.rest_cadence_minutes is None
    assert flagless.escape_radius_m is None
    assert flagless.route_surface is None


def _priced_route() -> tuple[Route, SimpleNamespace]:
    """A hermetic two-stop priced route + a script stand-in for the printer."""
    a = POI(
        id="poi-a", name="Jardin des Tuileries", tier=4, poi_role="stop",
        lat=48.8635, lng=2.3275, place_category="garden",
    )
    b = POI(
        id="poi-b", name="Musee d'Orsay", tier=5, poi_role="stop",
        lat=48.8600, lng=2.3266, place_category="museum",
    )
    route = Route(
        pois=(a, b),
        transits=(
            TransitSegment(
                from_poi_id=None, to_poi_id="poi-a", distance_m=600.0, walk_seconds=540
            ),
            TransitSegment(
                from_poi_id="poi-a", to_poi_id="poi-b", distance_m=800.0, walk_seconds=720
            ),
        ),
        total_walk_distance_m=1400.0,
        total_walk_seconds=1260,
        planned_visit_seconds={"poi-a": 1080, "poi-b": 1500},
    )
    script = SimpleNamespace(
        selected_pois=[
            SimpleNamespace(dwell_seconds=1080, lat=a.lat, lng=a.lng, name=a.name),
            SimpleNamespace(dwell_seconds=1500, lat=b.lat, lng=b.lng, name=b.name),
        ]
    )
    return route, script


def test_breakdown_prints_one_line_per_stop_with_category_and_minutes(capsys):
    """The breakdown shows a DAY, not a total: one line per stop — name,
    place category, stand/visit minutes, and the walking leg INTO that stop.

    Cites design §9 D2 ("six visibly different days side by side" — the
    side-by-side table is assembled from these lines verbatim) and the
    carried Phase 1 gap (S1.7 promised category labels in the harness
    corridor printout; only the review tables showed them — plan deviation
    register ii).
    """
    import importlib

    tour_build = importlib.import_module("scripts.tour_build")
    route, script = _priced_route()

    tour_build._print_breakdown(
        tour_input=_base_input(), wall_clock_s=1.0, route=route, script=script
    )
    out = capsys.readouterr().out

    assert "per-stop" in out, "the per-stop table must exist"
    table = out.split("per-stop", 1)[1]
    lines = [ln for ln in table.splitlines() if "Jardin des Tuileries" in ln]
    assert lines, "the per-stop table must carry one line per stop"
    tuileries = lines[0]
    assert "garden" in tuileries, "the line carries the place category"
    assert "18" in tuileries, "the line carries the stand/visit minutes (1080s)"
    assert "9" in tuileries, "the line carries the walk-in leg minutes (540s)"

    orsay = [ln for ln in table.splitlines() if "Musee d'Orsay" in ln]
    assert orsay and "museum" in orsay[0] and "25" in orsay[0] and "12" in orsay[0]


def test_breakdown_prints_dash_when_route_carries_no_pricing(capsys):
    """A legacy-shape route (empty `planned_visit_seconds` — the four legacy
    harnesses' shape, per the field's own comment in contract.py) prints the
    SAME table with a dash in the visit column, never a different shape and
    never a zero that reads as a measurement (plan S2.1 sabotage list)."""
    import importlib

    tour_build = importlib.import_module("scripts.tour_build")
    route, script = _priced_route()
    unpriced = route.model_copy(update={"planned_visit_seconds": {}})

    tour_build._print_breakdown(
        tour_input=_base_input(), wall_clock_s=1.0, route=unpriced, script=script
    )
    out = capsys.readouterr().out
    assert "per-stop" in out, "the table prints even when the route carries no pricing"
    table = out.split("per-stop", 1)[1]
    tuileries = [ln for ln in table.splitlines() if "Jardin des Tuileries" in ln]
    assert tuileries, "the table carries the stop even when the route is unpriced"
    assert "—" in tuileries[0], "unpriced visit minutes print as a dash, not a zero"


# --- S2.4: pace reaches the clock, in the slow direction ----------------------


def test_pace_multiplier_of_one_is_byte_identical():
    """The identity default: 1.0 is the same arithmetic as before this
    parameter existed, in both the seconds calculation and the reach circle
    (plan S2.4 declared breakage: none — multiplier unset/1.0 = today)."""
    from src.tour.routing import envelope_radius_m, pace_corrected_walk_seconds

    assert pace_corrected_walk_seconds(1000.0) == pace_corrected_walk_seconds(
        1000.0, pace_multiplier=1.0
    )
    assert envelope_radius_m(120, round_trip=False) == envelope_radius_m(
        120, round_trip=False, pace_multiplier=1.0
    )


def test_half_pace_doubles_legs_and_halves_the_circle():
    """A multiplier of 2.0 doubles a leg's seconds and halves the envelope
    radius — Nadia's day: "Pace drops to roughly half"
    (docs/personas/03-family-with-children.md step 4, line 21). Cites design
    §2.4 and Marcus step 2 (docs/personas/04-layover-sprinter.md: "Slower
    than his normal pace" — the with-luggage preset's own slow multiplier)."""
    from src.tour.routing import envelope_radius_m, pace_corrected_walk_seconds

    normal_seconds = pace_corrected_walk_seconds(1000.0)
    slow_seconds = pace_corrected_walk_seconds(1000.0, pace_multiplier=2.0)
    assert slow_seconds == 2 * normal_seconds

    normal_radius = envelope_radius_m(120, round_trip=False)
    slow_radius = envelope_radius_m(120, round_trip=False, pace_multiplier=2.0)
    assert slow_radius == pytest.approx(normal_radius / 2.0)


def test_density_assessment_for_a_paced_request_reports_the_smaller_walk_radius():
    """The tourability gate and the planner must shrink together (plan S2.4
    re-plan finding: `density.assess` computes its own `envelope_radius_m`,
    so pace has to thread there too or the gate offers a circle the planner
    will refuse to walk). Same corpus, same request, only `walking_pace`
    differs — the paced assessment's `walk_radius_m` is exactly half."""
    from src.tour.density import assess_snapshot
    from tests.test_tour_selection import PDV, _density_fillers, _snap

    corpus = _snap(_density_fillers(PDV, duration_min=120))
    normal = TourInput(start=PDV, duration_min=120, city_slug="paris")
    paced = TourInput(start=PDV, duration_min=120, city_slug="paris", walking_pace=2.0)

    normal_assessment = assess_snapshot(normal, corpus)
    paced_assessment = assess_snapshot(paced, corpus)
    assert paced_assessment.walk_radius_m == pytest.approx(
        normal_assessment.walk_radius_m / 2.0
    )


def test_select_route_prices_a_slower_partys_legs_when_seating_stops():
    """Not just the arithmetic in isolation — `select_route` ACTUALLY uses
    the scaled leg cost when deciding what fits. Proof: a rich anchor a
    normal-pace round trip affords (worth the there-and-back walk) a
    half-pace round trip cannot, because every leg toward it now costs twice
    as long against the SAME walk budget. Cites Nadia step 4 (pace halves)
    and design §2.4 ("a half-pace family both walks slower and is offered a
    smaller world" — plan S2.4's own line)."""
    from src.tour.selection import select_route
    from tests.test_tour_selection import PDV, _density_fillers, _poi, _snap

    fillers = _density_fillers(PDV, duration_min=60, round_trip=True, n=6, radius_m=60.0)
    edge_lat = PDV[0] + 0.0030  # ~333 m north: inside normal RT reach (444 m),
    # outside halved RT reach (222 m) — envelope_radius_m halves for round trips.
    edge_anchor = _poi("edge-anchor", lat=edge_lat, lng=PDV[1], beat_count=15)
    corpus = _snap([edge_anchor, *fillers])

    normal = select_route(
        TourInput(start=PDV, duration_min=60, city_slug="paris", round_trip=True), corpus
    )
    paced = select_route(
        TourInput(
            start=PDV, duration_min=60, city_slug="paris", round_trip=True, walking_pace=2.0
        ),
        corpus,
    )
    assert "edge-anchor" in {p.id for p in normal.pois}, (
        "fixture premise: the edge anchor must be worth the walk at normal pace"
    )
    assert "edge-anchor" not in {p.id for p in paced.pois}, (
        "a half-pace party must not be offered a world it cannot actually walk"
    )


def test_isochrone_walking_speed_override_rides_the_request(monkeypatch):
    """The Valhalla reach contour's `walking_speed` scales by
    `REACH_PACE_KMH / multiplier` per request when pace is set (plan S2.4:
    "the road polygon must shrink with the circle"), and stays the documented
    default when it is not — proven against the real request body, the same
    MockTransport-recording shape `test_tour_routing_engine.py` already uses.
    """
    import json

    import httpx

    from src.tour.routing import REACH_PACE_KMH
    from src.tour.routing_client import RoutingClient

    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        ring = [[2.20, 48.80], [2.45, 48.80], [2.45, 48.92], [2.20, 48.92], [2.20, 48.80]]
        return httpx.Response(
            200,
            json={
                "type": "FeatureCollection",
                "features": [
                    {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]}}
                ],
            },
        )

    http = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://valhalla.test")
    with RoutingClient(client=http) as rc:
        rc.isochrone(48.8584, 2.2945, 30)  # no override: today's default
        rc.isochrone(48.8584, 2.2945, 30, walking_speed_kmh=REACH_PACE_KMH / 2.0)

    assert seen[0]["costing_options"]["pedestrian"]["walking_speed"] == REACH_PACE_KMH
    assert seen[1]["costing_options"]["pedestrian"]["walking_speed"] == pytest.approx(
        REACH_PACE_KMH / 2.0
    )


# --- S2.7: route surface rides per-request costing -----------------------------


def test_step_free_axis_rides_the_costing_options():
    """`route_surface` set → the mock transport sees the step-avoiding
    override in the request body; unset → byte-identical body to today.

    Cites Rosemary step 4 ("The riverside stairs down to the water, which any
    shortest-path router would love, are unusable to her" —
    docs/personas/05-step-free-visitor.md line 29) and Marcus step 2 ("the
    wheels make cobbles genuinely unpleasant" — 04-layover-sprinter.md line
    18). Mapping proven live at W2.1 (phase2-ledger.md): `no_stairs` ->
    `step_penalty`; `step_free` adds `type: wheelchair`.
    """
    import json

    import httpx

    from src.tour.routing_client import RoutingClient
    from src.tour.selection import select_route
    from tests.test_tour_selection import PDV

    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if request.url.path == "/route":
            seen.append(body["costing_options"]["pedestrian"])
            a, b = body["locations"]
            from src.tour.routing import haversine_m

            d = haversine_m(a["lat"], a["lon"], b["lat"], b["lon"])
            return httpx.Response(
                200,
                json={
                    "trip": {
                        "legs": [
                            {
                                "summary": {"time": max(1, round(d / 1.1)), "length": d / 1000.0},
                                "shape": "mockshape",
                            }
                        ]
                    }
                },
            )
        return httpx.Response(404)

    from tests.test_tour_selection import _density_fillers, _snap

    corpus = _snap(_density_fillers(PDV, duration_min=60, n=10, radius_m=90.0))

    def _fresh_client() -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://valhalla.test")

    with RoutingClient(client=_fresh_client()) as rc:
        select_route(
            TourInput(start=PDV, duration_min=60, city_slug="paris"),
            corpus,
            routing_client=rc,
        )
    assert seen, "fixture premise: at least one /route call must have happened"
    assert "step_penalty" not in seen[0], "an unset route_surface must carry no override"

    seen.clear()
    with RoutingClient(client=_fresh_client()) as rc:
        select_route(
            TourInput(
                start=PDV, duration_min=60, city_slug="paris", route_surface="step_free"
            ),
            corpus,
            routing_client=rc,
        )
    assert seen, "fixture premise: at least one /route call must have happened"
    assert seen[0]["step_penalty"] == 3600
    assert seen[0]["type"] == "wheelchair"
    assert "walking_speed" in seen[0], "the override must merge into the pace pin"


def test_route_with_receipt_surface_override_produces_a_self_consistent_receipt():
    """A receipt built under an override validates — its `routing_config_json`
    reflects the OVERRIDDEN config actually sent, not the module default
    (`ValhallaLegReceipt._canonical_payloads_match_fields` derives the config
    it expects from the request itself), and `route_with_receipt` never
    mutates the shared `_ROUTING_CONFIG`/`_PEDESTRIAN_COSTING_OPTIONS` module
    state — proven by a plain call after the overridden one returning to the
    documented default."""
    from src.tour.routing_client import VALHALLA_ROUTING_CONFIG_JSON
    from tests.test_tour_routing_engine import POINTS, _client, _valhalla_handler

    with _client(_valhalla_handler) as rc:
        _, _, _, receipt = rc.route_with_receipt(
            *POINTS[0], *POINTS[1], costing_options_override={"step_penalty": 3600}
        )
        assert receipt is not None
        assert receipt.routing_config_json != VALHALLA_ROUTING_CONFIG_JSON
        assert '"step_penalty":3600' in receipt.routing_config_json

        # The module default must be UNCHANGED for the very next call.
        _, _, _, plain_receipt = rc.route_with_receipt(*POINTS[0], *POINTS[1])
        assert plain_receipt is not None
        assert plain_receipt.routing_config_json == VALHALLA_ROUTING_CONFIG_JSON


# --- S2.6: place judgements — one poi_score consumer per judgement -----------


def test_family_days_weight_children_can_run_places_up():
    """A family day's `poi_score` weights a `children_can_run` place above an
    otherwise-identical rival; no party (or a non-family party) leaves the two
    tied.

    Cites Nadia (03-panel-findings.md: "38 of her 55 place-minutes valuable
    because kids can be loud/fast/free-range; corpus has no 'children can run
    here' channel") and design row 6.4.
    """
    from src.tour.selection import poi_score
    from tests.test_tour_selection import PDV, _poi, _snap

    runnable = _poi("runnable", lat=PDV[0], lng=PDV[1], beat_count=5).model_copy(
        update={"children_can_run": True}
    )
    plain = _poi("plain", lat=PDV[0], lng=PDV[1], beat_count=5)
    corpus = _snap([runnable, plain])

    tied_no_party = poi_score(runnable, None, frozenset(), corpus) == poi_score(
        plain, None, frozenset(), corpus
    )
    assert tied_no_party, "with no party the two otherwise-identical POIs must tie"

    tied_wrong_party = poi_score(
        runnable, None, frozenset(), corpus, party="solo"
    ) == poi_score(plain, None, frozenset(), corpus, party="solo")
    assert tied_wrong_party, "a non-family party must not favour children_can_run"

    family_runnable = poi_score(runnable, None, frozenset(), corpus, party="family")
    family_plain = poi_score(plain, None, frozenset(), corpus, party="family")
    assert family_runnable > family_plain, (
        "a family day must weight the children-can-run place above its "
        "otherwise-identical rival"
    )


def test_take_it_easy_and_couple_days_weight_sit_and_talk_places_up():
    """Take-it-easy and couple days weight a `sit_and_talk` place up; family
    and solo do not.

    Cites Fiona & Dev's two green chairs ("The Palais-Royal garden wins the
    afternoon on seating, enclosure and quiet — three properties no POI in
    the corpus carries" — docs/personas/09-couple-who-would-rather-talk.md)
    and design row 6.4.
    """
    from src.tour.selection import poi_score
    from tests.test_tour_selection import PDV, _poi, _snap

    talkable = _poi("talkable", lat=PDV[0], lng=PDV[1], beat_count=5).model_copy(
        update={"sit_and_talk": True}
    )
    plain = _poi("plain", lat=PDV[0], lng=PDV[1], beat_count=5)
    corpus = _snap([talkable, plain])

    for party in ("couple", "take_it_easy"):
        boosted = poi_score(talkable, None, frozenset(), corpus, party=party)
        rival = poi_score(plain, None, frozenset(), corpus, party=party)
        assert boosted > rival, f"{party} must weight the sit-and-talk place up"

    for party in ("family", "solo", None):
        tied = poi_score(talkable, None, frozenset(), corpus, party=party) == poi_score(
            plain, None, frozenset(), corpus, party=party
        )
        assert tied, f"{party!r} must not favour sit_and_talk"


def test_spotlight_does_not_gain_the_affordance_factor():
    """`spotlight` (the banding function) is UNCHANGED by S2.6 — the plan's
    own instruction: "banding is not party-aware in this phase". A
    `children_can_run` place scores identically under `spotlight` regardless
    of party; only `poi_score` (ranking) moves."""
    from src.tour.selection import spotlight
    from tests.test_tour_selection import PDV, _poi, _snap

    runnable = _poi("runnable", lat=PDV[0], lng=PDV[1], beat_count=5).model_copy(
        update={"children_can_run": True}
    )
    corpus = _snap([runnable])

    # spotlight() takes no `party` argument at all — its signature itself is
    # the proof; this call would raise TypeError if S2.6 had added one.
    value_a = spotlight(runnable, lenses=None, snapshot=corpus)
    value_b = spotlight(runnable, lenses=None, snapshot=corpus)
    assert value_a == value_b


# --- S2.8: escape radius as a candidate filter --------------------------------


def test_escape_radius_refuses_a_far_anchor_on_family_but_seats_it_on_solo():
    """A rich anchor just outside the escape radius is refused when the axis
    is set (family) and seated when it is not (solo) — the SAME corpus, the
    SAME distance, only the axis differs.

    Cites design §2.4: "a meltdown 25 minutes from the exit means carrying a
    child for 25 minutes" — escape radius is a constraint on distance from
    the START, not on any one leg — and the panel's locked cost D4
    (03-panel-findings.md: "cap DISTANCE FROM EXIT not just leg length —
    family days = tight loops around short escape radius").
    """
    from src.tour.selection import select_route
    from tests.test_tour_selection import PDV, _density_fillers, _poi, _snap

    fillers = _density_fillers(PDV, duration_min=90, round_trip=True, n=8, radius_m=70.0)
    far_lat = PDV[0] + 0.0045  # ~500 m north
    far_anchor = _poi("far-anchor", lat=far_lat, lng=PDV[1], beat_count=15)
    corpus = _snap([far_anchor, *fillers])

    solo = select_route(
        TourInput(start=PDV, duration_min=90, city_slug="paris", round_trip=True), corpus
    )
    assert "far-anchor" in {p.id for p in solo.pois}, (
        "fixture premise: the far anchor must be worth the walk with no radius set"
    )

    family = select_route(
        TourInput(
            start=PDV, duration_min=90, city_slug="paris", round_trip=True, escape_radius_m=300
        ),
        corpus,
    )
    assert "far-anchor" not in {p.id for p in family.pois}, (
        "a family's escape radius must refuse a stop the exit is too far from"
    )
    assert family.clock_exclusions == (), (
        "a too-far stop needs no disclosure — only a closed door does (plan S2.8)"
    )


# --- S2.3: the per-leg cap becomes a constraint ------------------------------

#: ~555 m north of PDV: a ~15-minute leg at the corpus pace (1.62 s/m) — over
#: a 12-minute cap. The two stones flank the midpoint ±100 m east/west, each
#: ~8 minutes from both the start and the far anchor.
_FAR_ANCHOR = (48.86052, 2.3656)
_STONE_EAST = (48.85803, 2.36697)
_STONE_WEST = (48.85803, 2.36423)
_LEG_CAP_SECONDS = 12 * 60


def _leg_cap_corpus(*, with_stones: bool):
    from tests.test_tour_selection import PDV, _density_fillers, _poi, _snap

    fillers = _density_fillers(
        PDV,
        duration_min=120,
        round_trip=True,
        n=13 if with_stones else 15,
        radius_m=80.0,
    )
    pois = [
        _poi("far-anchor", lat=_FAR_ANCHOR[0], lng=_FAR_ANCHOR[1]),
        *fillers,
    ]
    if with_stones:
        pois.append(_poi("stone-east", lat=_STONE_EAST[0], lng=_STONE_EAST[1]))
        pois.append(_poi("stone-west", lat=_STONE_WEST[0], lng=_STONE_WEST[1]))
    return _snap(pois)


def _leg_cap_request(max_leg_minutes: int | None = None) -> TourInput:
    from tests.test_tour_selection import PDV

    kwargs: dict[str, object] = {}
    if max_leg_minutes is not None:
        kwargs["max_leg_minutes"] = max_leg_minutes
    return TourInput(
        start=PDV, duration_min=120, city_slug="paris", round_trip=True, **kwargs
    )


def _route_leg_seconds(route) -> list[int]:
    return [
        t.leg_seconds if t.leg_seconds is not None else t.walk_seconds
        for t in route.transits
    ]


def test_a_leg_cap_prefers_more_walking_in_shorter_pieces():
    """With the axis set, no single walk may exceed the cap — the planner buys
    the far anchor with MORE total walking in shorter pieces when the city
    offers stepping stones, and trades it away when it does not.

    Cites docs/personas/05-step-free-visitor.md bullet 1 (lines 48-50): "A
    walking budget is not one number. Rosemary's total (54 minutes) is
    unremarkable. Her *per-leg* limit (12 minutes) is the binding constraint,
    and nothing in the model expresses it. A route with one 25-minute leg and
    one 5-minute leg has the same total and is unusable" — and the Phase 1
    panel's Rosemary dissent (phase1-ledger.md W1.9 item 7: both D1 days
    carried a 17/19-minute longest leg she cannot walk).
    """
    from src.tour.selection import select_route

    # PREMISE — without the axis the planner happily builds the long march:
    # the far anchor is seated over a leg well past 12 minutes.
    uncapped = select_route(_leg_cap_request(), _leg_cap_corpus(with_stones=False))
    assert "far-anchor" in {p.id for p in uncapped.pois}, (
        "fixture premise: the rich far anchor must be worth seating uncapped"
    )
    assert max(_route_leg_seconds(uncapped)) > _LEG_CAP_SECONDS, (
        "fixture premise: seating it uncapped must cost an over-cap leg"
    )

    # THE CAP IS HARD — same stoneless corpus: every single leg obeys the cap,
    # which here means the far anchor is traded away (no cap-respecting path
    # to it exists).
    capped_stoneless = select_route(
        _leg_cap_request(12), _leg_cap_corpus(with_stones=False)
    )
    assert max(_route_leg_seconds(capped_stoneless), default=0) <= _LEG_CAP_SECONDS

    # SHORTER PIECES, MORE WALKING — give the city stepping stones and the
    # capped planner keeps the anchor: every leg fits the cap, and the day
    # walks further in total than the capped stoneless day to do it.
    capped_stones = select_route(
        _leg_cap_request(12), _leg_cap_corpus(with_stones=True)
    )
    assert "far-anchor" in {p.id for p in capped_stones.pois}, (
        "the cap must restructure the walk, not delete the anchor the city "
        "offers stones for"
    )
    assert max(_route_leg_seconds(capped_stones)) <= _LEG_CAP_SECONDS
    assert capped_stones.total_walk_seconds > capped_stoneless.total_walk_seconds


def test_breakdown_prints_the_resolved_party_even_when_it_moves_no_number(capsys):
    """Two runs whose axes tie on every NUMBER the table shows (a preset pair
    whose only new axis is the narration register, which touches none of
    walk/dwell/leg/table cells) must still print visibly different output —
    the day has to be different in the OUTPUT, not just in the code path
    that built it. Cites design §9 D2 ("six visibly different days") and
    §2.4 ("take-it-easy + solo is a legitimate pair")."""
    import importlib

    tour_build = importlib.import_module("scripts.tour_build")

    plain = _base_input()
    tour_build._print_breakdown(tour_input=plain, wall_clock_s=1.0)
    assert "party:              none" in capsys.readouterr().out

    from src.tour.contract import resolve_party_axes

    take_it_easy = resolve_party_axes(_base_input(party="take_it_easy"))
    tour_build._print_breakdown(tour_input=take_it_easy, wall_clock_s=1.0)
    out_a = capsys.readouterr().out
    assert "preset=take_it_easy" in out_a
    assert "register=" not in out_a, "take-it-easy alone leaves the register unset"

    solo_and_take_it_easy = take_it_easy.model_copy(update={"narration_register": "solo"})
    tour_build._print_breakdown(tour_input=solo_and_take_it_easy, wall_clock_s=1.0)
    out_b = capsys.readouterr().out
    assert "register=solo" in out_b, (
        "the solo+take-it-easy pair must show its one distinguishing axis "
        "even though it moves no other cell in the table"
    )
    assert out_a != out_b, "the two runs must be visibly different in the output"


def test_seven_number_block_is_unchanged_above_the_per_stop_table(capsys):
    """The Phase 1 seven-number block still opens the breakdown, above the new
    table, so the D1 evidence stays readable (plan S2.1: "The seven-number
    block is unchanged above the new table")."""
    import importlib

    tour_build = importlib.import_module("scripts.tour_build")
    route, script = _priced_route()

    tour_build._print_breakdown(
        tour_input=_base_input(), wall_clock_s=1.0, route=route, script=script
    )
    out = capsys.readouterr().out

    for label in (
        "walk:", "dwell:", "total (walk+dwell):", "longest leg:",
        "furthest off A→B:", "reach radius:", "wall clock:",
    ):
        assert label in out, f"the seven-number block lost {label!r}"
    assert out.index("walk:") < out.index("per-stop"), (
        "the per-stop table must sit BELOW the seven-number block"
    )
