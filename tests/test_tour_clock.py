"""Phase 1 clock tests — does the planner know what time it is?

One clock-hand per file, on the `tests/test_tour_visit_time.py` model: every
gating test cites the design section or persona line it enforces
(specs/2026-08-07-tour-algorithm-redesign/04-implementation-plan.md §0.1.1).

All Phase 1 clock tests live here (plan step S1.2): the contract fields, the
API-model carry, the persisted-inputs round trip, the harness flags, and the
clock filter.

The RED that proved S1.2 was real: `TourInput` is `extra="forbid"`
(src/tour/contract.py), so constructing it with `start_datetime` /
`end_hardness` raised before the fields existed. That forbid is load-bearing
for this file and its only guard is
`tests/test_tour_contract.py::test_tour_input_rejects_extra_keys` — if that
guard ever dies, the RED here goes vacuous with it.
"""

import pytest
from pydantic import ValidationError

from src.tour.contract import POI, TourInput


def _base_input(**overrides) -> TourInput:
    fields = {
        "start": (48.8568, 2.3414),
        "duration_min": 90,
        "city_slug": "paris",
    }
    fields.update(overrides)
    return TourInput(**fields)


def test_tour_input_carries_the_clock_and_end_hardness():
    """The request carries a real clock and says how hard its end is.

    Cites design §2.2 — the start is soft: "Fiona & Dev stood reading a menu
    for twelve minutes" (docs/personas/09-couple-who-would-rather-talk.md,
    step 1) — and §2.3: Marcus's 16:40 wall
    (docs/personas/04-layover-sprinter.md), Camille's "is 15:00 a wall or a
    wish?" (03-panel-findings.md), and Julien's leavable-blank clock
    (03-panel-findings.md). A planner that cannot be told the date and the
    hardness of its end cannot serve any of the four.
    """
    inp = _base_input(start_datetime="2026-08-11T10:00:00", end_hardness="wall")
    assert inp.start_datetime == "2026-08-11T10:00:00"
    assert inp.end_hardness == "wall"


def test_tour_input_clock_defaults_keep_todays_behaviour():
    """No datetime and `firm` are the defaults, so every existing caller and
    golden stays byte-identical (plan S1.2: "None = today's dateless
    behaviour"; design §2.3: `firm` is byte-identical to today)."""
    inp = _base_input()
    assert inp.start_datetime is None
    assert inp.end_hardness == "firm"


def test_tour_input_rejects_a_malformed_datetime_with_a_plain_message():
    """A malformed datetime is refused in plain words (plan S1.2: "A validator
    rejects a malformed datetime with a plain message"), not with a parser
    traceback — the API surfaces this text to the person who typed it."""
    with pytest.raises(ValidationError, match="not a valid date and time"):
        _base_input(start_datetime="next tuesday-ish")


def test_tour_input_rejects_an_unknown_end_hardness():
    """`end_hardness` is exactly wall | firm | open (design §2.3) — a typo'd
    hardness must not silently plan as `firm`."""
    with pytest.raises(ValidationError):
        _base_input(end_hardness="soft")


def test_api_request_models_carry_the_clock_and_end_hardness():
    """Both API request models CARRY the two fields rather than dropping them.

    Neither `TripGenerateRequest` nor `TripPreviewRequest` declares
    `model_config`, so both inherit pydantic's default `extra="ignore"`: an
    undeclared field is SILENTLY DROPPED and the layer above still looks fine
    (the `max_stop_minutes` comment in src/api/models/trips.py records the
    same trap verbatim). This test is what proves the declaration exists.
    Cites design §2.2/§2.3 via plan step S1.3a.
    """
    from src.api.models.trips import TripGenerateRequest, TripPreviewRequest

    gen = TripGenerateRequest(
        profile_id="p1",
        center_lat=48.8568,
        center_lng=2.3414,
        start_date="2026-08-11",
        end_date="2026-08-11",
        start_datetime="2026-08-11T10:00:00",
        end_hardness="wall",
    )
    assert gen.start_datetime == "2026-08-11T10:00:00"
    assert gen.end_hardness == "wall"

    prev = TripPreviewRequest(
        center_lat=48.8568,
        center_lng=2.3414,
        start_datetime="2026-08-11T10:00:00",
        end_hardness="open",
    )
    assert prev.start_datetime == "2026-08-11T10:00:00"
    assert prev.end_hardness == "open"


def test_api_request_models_reject_a_bad_end_hardness():
    """A typo'd hardness is a 422 at the edge (plan S1.3a: "a bad
    `end_hardness` is a 422"), never a silently-firm plan. ValidationError
    here is exactly what FastAPI surfaces as the 422."""
    from src.api.models.trips import TripGenerateRequest, TripPreviewRequest

    with pytest.raises(ValidationError):
        TripGenerateRequest(
            profile_id="p1",
            center_lat=48.8568,
            center_lng=2.3414,
            start_date="2026-08-11",
            end_date="2026-08-11",
            end_hardness="soft",
        )
    with pytest.raises(ValidationError):
        TripPreviewRequest(center_lat=48.8568, center_lng=2.3414, end_hardness="soft")


def _trips_route_source() -> str:
    from pathlib import Path

    return (
        Path(__file__).resolve().parent.parent / "src" / "api" / "routes" / "trips.py"
    ).read_text()


def test_every_tour_input_construction_site_threads_the_clock():
    """All THREE construction sites pass the clock through — never one or two.

    `generate_trip`, `preview_trip` and `_author_preview_impl` each build the
    engine input via `_build_tour_input`; a site that omits `start_datetime` /
    `end_hardness` degrades silently (the request accepts the field, the plan
    ignores it). Plan S1.3b names exactly this sabotage. Source-scanning in the
    `test_golden_diff_cli_reads_the_durable_key` genre, because a behaviour
    test through the full engine cannot see a missed site hermetically.
    Also: `compose_trip`'s rebuild passes them (restored, not defaulted), so
    four `_build_tour_input` calls carry them in total.
    """
    import ast

    tree = ast.parse(_trips_route_source())
    call_sites = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_build_tour_input"
    ]
    assert len(call_sites) == 4, (
        "expected the generate/compose/preview/author _build_tour_input sites, "
        f"found {len(call_sites)}"
    )
    for call in call_sites:
        keywords = {kw.arg for kw in call.keywords}
        assert "start_datetime" in keywords, f"line {call.lineno} drops start_datetime"
        assert "end_hardness" in keywords, f"line {call.lineno} drops end_hardness"


def test_generate_persists_the_clock_and_compose_restores_it_fail_open():
    """The clock survives the save: persisted at generate, restored at compose.

    Persist: the `tour_input_json` dict in `generate_trip` carries both keys.
    Restore: `compose_trip` reads them with the fail-open `.get(...)` shape
    `max_stop_minutes` already uses — a direct key access would 500 every trip
    saved before the key existed (plan S1.3b sabotage list).
    """
    source = _trips_route_source()
    assert '"start_datetime": tour_input.start_datetime' in source, (
        "generate_trip's tour_input_json does not persist start_datetime"
    )
    assert '"end_hardness": tour_input.end_hardness' in source, (
        "generate_trip's tour_input_json does not persist end_hardness"
    )
    assert 'tour_input_dict.get("start_datetime")' in source, (
        "compose_trip does not restore start_datetime with the fail-open .get shape"
    )
    assert 'tour_input_dict.get("end_hardness")' in source, (
        "compose_trip does not restore end_hardness with the fail-open .get shape"
    )


def test_a_trip_saved_before_the_clock_existed_composes_exactly_as_it_always_did():
    """The fail-open restore, exercised: a legacy stored dict (no clock keys)
    lands on the identity defaults — dateless, `firm` — so a trip saved before
    this key existed composes exactly as it always did (plan S1.3b)."""
    legacy_stored = {
        "start": [48.8568, 2.3414],
        "end": None,
        "duration_min": 90,
        "city_slug": "paris",
        "lenses": None,
        "round_trip": False,
    }
    restored = TourInput(
        start=tuple(legacy_stored["start"]),
        duration_min=legacy_stored["duration_min"],
        city_slug=legacy_stored["city_slug"],
        lenses=legacy_stored["lenses"],
        round_trip=legacy_stored["round_trip"],
        start_datetime=legacy_stored.get("start_datetime"),
        end_hardness=legacy_stored.get("end_hardness") or "firm",
    )
    assert restored.start_datetime is None
    assert restored.end_hardness == "firm"


def test_harness_flags_parse_and_a_dateless_run_stays_dateless():
    """`scripts/tour_build.py` accepts --date/--time/--end-hardness, and
    omitting them leaves the run exactly as today (plan S1.3c: "a dateless run
    is byte-identical to today's" — the flags default to no clock and `firm`,
    so the TourInput built is byte-identical to the pre-clock one)."""
    import importlib

    tour_build = importlib.import_module("scripts.tour_build")
    parser = tour_build._build_arg_parser()

    dated = parser.parse_args(
        ["--start", "X", "--duration", "60", "--canned",
         "--date", "2026-08-11", "--time", "10:00", "--end-hardness", "wall"]
    )
    assert dated.date == "2026-08-11"
    assert dated.time == "10:00"
    assert dated.end_hardness == "wall"

    dateless = parser.parse_args(["--start", "X", "--duration", "60", "--canned"])
    assert dateless.date is None
    assert dateless.end_hardness == "firm"


def test_breakdown_prints_clock_exclusions_only_on_a_dated_run(capsys):
    """The clock-exclusions section appears iff the run has a clock.

    Dateless → NO section, so today's output (and W1.1's before-picture) stays
    byte-identical. Dated with no exclusions → the section prints "none", so a
    Monday and a Tuesday run keep the same shape and read side by side (plan
    S1.3c sabotage list: omitting the empty section makes the D1 pair
    incomparable)."""
    import importlib

    tour_build = importlib.import_module("scripts.tour_build")

    dateless_input = _base_input()
    tour_build._print_breakdown(tour_input=dateless_input, wall_clock_s=1.0)
    dateless_out = capsys.readouterr().out
    assert "clock exclusions" not in dateless_out

    dated_input = _base_input(start_datetime="2026-08-11T10:00:00")
    tour_build._print_breakdown(tour_input=dated_input, wall_clock_s=1.0)
    dated_out = capsys.readouterr().out
    assert "clock exclusions" in dated_out
    assert "none" in dated_out.split("clock exclusions", 1)[1]


def test_route_records_clock_exclusions_additively():
    """The Route carries WHO the clock excluded and WHY, on the Route itself.

    Cites plan S1.6a and the `elapsed_shortfall_seconds` lesson recorded in
    src/tour/contract.py: a disclosure that rides a channel which is null in
    its own case discloses nothing — `tourability` is None on a GREEN route,
    which is exactly the route that must still say "the museum is closed
    today". Additive metadata in the `vignettes` mould: default empty, so
    every existing Route is byte-identical.
    """
    from src.tour.contract import ClockExclusion, Route

    excl = ClockExclusion(
        poi_id="musee-x",
        name="Musée X",
        reason="closed all day Tuesday (hours: OSM); would otherwise have been seated",
    )
    bare = Route(pois=(), transits=(), total_walk_distance_m=0.0, total_walk_seconds=0)
    assert bare.clock_exclusions == ()
    carrying = bare.model_copy(update={"clock_exclusions": (excl,)})
    assert carrying.clock_exclusions[0].name == "Musée X"
    assert "Tuesday" in carrying.clock_exclusions[0].reason


# --- the clock filter (S1.6b), on a hermetic constructed snapshot -----------

#: 2026-08-11 is a Tuesday; 2026-08-10 the Monday before it.
_TUESDAY_10AM = "2026-08-11T10:00:00"
_MONDAY_10AM = "2026-08-10T10:00:00"

_CLOSED_TUESDAY_TABLE = {
    "mon": [["09:00", "18:00"]],
    "tue": [],
    "wed": [["09:00", "18:00"]],
    "thu": [["09:00", "18:00"]],
    "fri": [["09:00", "18:00"]],
    "sat": [["09:00", "18:00"]],
    "sun": [["09:00", "18:00"]],
}


def _tuesday_closed_museum():
    import json as _json

    from tests.test_tour_selection import PDV

    return POI(
        id="musee-ferme-mardi",
        name="Musée Fermé le Mardi",
        tier=5,
        poi_role="stop",
        lat=PDV[0],
        lng=PDV[1],
        areas=("Paris",),
        beat_count=5,
        opening_hours=_json.dumps(_CLOSED_TUESDAY_TABLE),
        opening_hours_source="osm",
        opening_hours_basis="Museum; OSM tag 'Mo,We-Su 09:00-18:00; Tu off'.",
    )


def _clock_corpus(museum):
    from tests.test_tour_selection import PDV, _density_fillers, _snap

    return _snap([museum, *_density_fillers(PDV)])


def _clock_request(start_datetime):
    from tests.test_tour_selection import PDV

    return TourInput(
        start=PDV,
        duration_min=60,
        city_slug="paris",
        start_datetime=start_datetime,
    )


def test_a_poi_closed_for_the_whole_visit_window_is_excluded_and_recorded():
    """A place closed for the ENTIRE visit window leaves the dwell pool, and
    the day says why.

    Cites docs/personas/05-step-free-visitor.md (final bullet: the identical
    request one day earlier spends 24 of her 54 walking minutes reaching a
    locked door), docs/personas/07-rainy-tuesday.md step 6, and design 6.1
    ("Aiko's locked door, Rosemary's Tuesday").
    """
    from src.tour.selection import select_route

    museum = _tuesday_closed_museum()
    route = select_route(_clock_request(_TUESDAY_10AM), _clock_corpus(museum))

    assert museum.id not in {p.id for p in route.pois}
    recorded = {e.poi_id: e for e in route.clock_exclusions}
    assert museum.id in recorded, "the exclusion must be RECORDED, not silent"
    assert "Tuesday" in recorded[museum.id].reason
    assert "OSM" in recorded[museum.id].reason


def test_the_same_poi_is_seated_on_a_day_it_is_open():
    """The identical request on Monday seats the museum — the exclusion is the
    clock's, not the place's (design 6.1; 07-rainy-tuesday.md step 6)."""
    from src.tour.selection import select_route

    museum = _tuesday_closed_museum()
    route = select_route(_clock_request(_MONDAY_10AM), _clock_corpus(museum))

    assert museum.id in {p.id for p in route.pois}
    assert route.clock_exclusions == ()


def test_no_datetime_means_no_filtering_and_a_byte_identical_pool():
    """No clock → no filtering: the dateless pool is byte-identical to today's,
    which is the identity default that keeps every existing test and golden
    green (plan S1.6b: "No datetime → no filtering, byte-identical pool")."""
    from src.tour.selection import select_route

    museum = _tuesday_closed_museum()
    dateless = select_route(_clock_request(None), _clock_corpus(museum))
    monday = select_route(_clock_request(_MONDAY_10AM), _clock_corpus(museum))

    assert museum.id in {p.id for p in dateless.pois}
    assert dateless.clock_exclusions == ()
    assert [p.id for p in dateless.pois] == [p.id for p in monday.pois]


# --- end hardness reaches the budget (S1.6c) ---------------------------------


def test_firm_hardness_is_byte_identical_to_today():
    """`firm` is the default and must change NOTHING (design §2.3: "the
    default. Honest planning to the clock; the ceiling behaviour the in-flight
    work already built")."""
    from src.tour.routing import route_planning_budget

    assert route_planning_budget(60, end_hardness="firm") == route_planning_budget(60)


def test_open_hardness_drops_the_minimum_elapsed_floor_to_zero():
    """Under `open`, a two-ish-hours request is never padded toward a number
    nobody defended: the minimum-elapsed floor goes to zero and nothing else
    moves. Cites design §2.3 (Julien's two-ish hours; Camille's "is 15:00 a
    wall or a wish?" — "a hard end time is a preference enforced as a fact")
    and design 8.3 (this finishes the fill-the-requested-time deletion)."""
    from src.tour.routing import route_planning_budget

    firm = route_planning_budget(120)
    open_ended = route_planning_budget(120, end_hardness="open")

    assert open_ended.minimum_elapsed_seconds == 0
    assert open_ended.nominal_elapsed_seconds == firm.nominal_elapsed_seconds
    assert open_ended.maximum_elapsed_seconds == firm.maximum_elapsed_seconds
    assert open_ended.walk_budget_seconds == firm.walk_budget_seconds
    assert open_ended.dwell_target_seconds == firm.dwell_target_seconds


def test_wall_hardness_plans_to_a_095_ceiling_with_visible_slack():
    """Under `wall` the plan aims at 95% of the asked time and may not exceed
    it, so the plan carries VISIBLE spare minutes — never a hard truncation at
    the asked number. Cites docs/personas/04-layover-sprinter.md bullet 2
    (Marcus: "2h40 of tour with 20 minutes of slack" beats "3h00 exactly") and
    design §2.3 (his 16:40 train; he currently lies about his end time to
    manufacture margin)."""
    from src.tour.routing import (
        DWELL_FRACTION,
        WALK_FRACTION,
        route_planning_budget,
    )

    firm = route_planning_budget(180)
    wall = route_planning_budget(180, end_hardness="wall")
    requested = 180 * 60

    assert wall.maximum_elapsed_seconds == round(requested * 0.95)
    assert wall.nominal_elapsed_seconds == round(requested * 0.95)
    assert wall.minimum_elapsed_seconds == firm.minimum_elapsed_seconds
    assert wall.walk_budget_seconds == round(requested * 0.95 * WALK_FRACTION)
    assert wall.dwell_target_seconds == round(requested * 0.95 * DWELL_FRACTION)
    assert wall.maximum_elapsed_seconds < firm.maximum_elapsed_seconds


def test_select_route_threads_the_hardness_into_its_budget():
    """The one budget `select_route` derives for the request carries the
    request's own hardness (plan S1.6c: "Threading from `TourInput` via
    `select_route`'s existing `planning_policy` derivation"). Source-scanning,
    because every helper call site legitimately keeps the firm default and a
    behaviour test cannot tell which call built the budget the repair used."""
    import ast
    from pathlib import Path

    source = (
        Path(__file__).resolve().parent.parent / "src" / "tour" / "selection.py"
    ).read_text()
    tree = ast.parse(source)
    threaded = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "route_planning_budget"
        and any(kw.arg == "end_hardness" for kw in node.keywords)
    ]
    assert threaded, (
        "no route_planning_budget call in selection.py passes end_hardness — "
        "the request's hardness never reaches the time arithmetic"
    )


def test_tour_input_clock_round_trips_through_model_dump():
    """`start_datetime` is an ISO STRING, not a datetime object:
    `tests/test_tour_contract.py::test_tour_input_end_round_trips_through_model_dump`
    does `TourInput(**inp.model_dump())`, and only a string round-trips
    (plan S1.2 sabotage list)."""
    inp = _base_input(start_datetime="2026-08-11T10:00:00", end_hardness="open")
    again = TourInput(**inp.model_dump())
    assert again == inp
