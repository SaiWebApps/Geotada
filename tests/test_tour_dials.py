"""Phase 4 dial tests — the W4.2 panel's dials, carried and obeyed. Hermetic.

One hand per file (the test_tour_clock.py model): this file is the DIALS hand.
Every gating test cites its source — the W4.2 panel's locked semantics
(specs/2026-08-07-tour-algorithm-redesign/phase4-ledger.md, "LOCKED DIAL
SEMANTICS", all eleven personas, 2026-08-11) and design §8.1/§9 Phase 4.

The four dials and their engine meanings, as the panel ruled them:
- stop_density   — "Fewer stops, longer at each" / "More stops, shorter at each"
- narration_density — "Less talking / More talking" (supply, never topic)
- avoid_queues   — "Skip the queues" (the retired "quieter", named plainly)
- category_minus — "Less of THIS today" (Greta's kind chips; swap, never starve)
"""

from __future__ import annotations

from itertools import pairwise

import pytest
from pydantic import ValidationError

from src.tour.contract import POI, BeatRef, Route, TourInput, TransitSegment, resolve_party_axes
from tests.test_tour_selection import PDV, _density_fillers, _poi, _snap


def _categorised(poi: POI, category: str) -> POI:
    return poi.model_copy(update={"place_category": category})


def _queued(poi: POI, minutes_peak: int) -> POI:
    return poi.model_copy(
        update={
            "queue_class": "long",
            "queue_minutes_peak": minutes_peak,
            "queue_minutes_offpeak": max(5, minutes_peak // 4),
        }
    )


def test_tour_input_carries_the_four_dials():
    """W4.2 locked semantics: the four dials are request axes (deviation iv —
    existing axes preferred; these four are the genuinely new ones, S3.2 mould).
    RED before the fields existed: TourInput is extra="forbid", so construction
    raised (the guard on that forbid is
    tests/test_tour_contract.py::test_tour_input_rejects_extra_keys)."""
    inp = TourInput(
        start=PDV,
        duration_min=120,
        city_slug="paris",
        stop_density="fewer",
        narration_density="less",
        avoid_queues=True,
        category_minus=("museum", "church"),
    )
    assert inp.stop_density == "fewer"
    assert inp.narration_density == "less"
    assert inp.avoid_queues is True
    assert inp.category_minus == ("museum", "church")
    # The defaults are today's behaviour, byte-identical.
    plain = TourInput(start=PDV, duration_min=120, city_slug="paris")
    assert plain.stop_density is None
    assert plain.narration_density is None
    assert plain.avoid_queues is False
    assert plain.category_minus == ()
    # A value outside the vocabulary is rejected loudly, not absorbed.
    with pytest.raises(ValidationError):
        TourInput(start=PDV, duration_min=120, city_slug="paris", stop_density="fewest")


def test_stop_density_more_resolves_to_the_short_stop_ceiling():
    """W4.2 ruling 4: the "more" direction is the proven short-stop shape (the
    measured a-stop20 cell); an explicitly-set ceiling always wins (the
    resolver's one rule)."""
    resolved = resolve_party_axes(
        TourInput(start=PDV, duration_min=120, city_slug="paris", stop_density="more")
    )
    assert resolved.max_stop_minutes == 20
    explicit = resolve_party_axes(
        TourInput(
            start=PDV,
            duration_min=120,
            city_slug="paris",
            stop_density="more",
            max_stop_minutes=45,
        )
    )
    assert explicit.max_stop_minutes == 45
    fewer = resolve_party_axes(
        TourInput(start=PDV, duration_min=120, city_slug="paris", stop_density="fewer")
    )
    assert fewer.max_stop_minutes is None, "the fewer direction has no axis mapping"


def test_category_minus_swaps_the_kind_out():
    """W4.2 ruling 7 (Greta: "not what I did yesterday"; Julien: "zero museums
    today, and it must behave like the lens — swap in different places, not
    starve them"): an excluded kind leaves the dwell pool; the day still plans.
    """
    from src.tour.selection import select_route

    # Categorise members of the calibrated corpus itself (a bolt-on stop loses
    # to duration-calibrated fillers), so the premise is structural.
    fillers = _density_fillers(PDV, duration_min=60, round_trip=True)
    pois = [
        _categorised(fillers[0], "museum"),
        _categorised(fillers[1], "church"),
        *fillers[2:],
    ]
    snap = _snap(pois)
    museum_id = fillers[0].id
    inp = TourInput(start=PDV, duration_min=60, city_slug="paris", round_trip=True)

    control = select_route(inp, snap)
    assert museum_id in {p.id for p in control.pois}, (
        "fixture premise: the museum must be worth seating undialed"
    )

    dialed = select_route(
        inp.model_copy(update={"category_minus": ("museum",)}),
        snap,
    )
    seated = {p.id for p in dialed.pois}
    assert museum_id not in seated, "the excluded kind was still seated"
    assert len(dialed.pois) >= 2, "the exclusion starved the day instead of swapping"


def test_avoid_queues_prefers_the_queue_free_rival():
    """W4.2 ruling 6 ("Skip the queues" — Théo: "the darkest thing in the day
    was the queue"; Sofia: a 40-minute outdoor stand-still): a peak-queue-heavy
    stop is dimmed so its queue-free rival wins; without the dial the heavier
    stop is seated (the premise that makes the flip real)."""
    from src.tour.selection import select_route

    # Queue a member of the calibrated corpus (guaranteed worth seating), and
    # add ONE extra rival so a seat is genuinely contested — with no scarcity
    # the dimmed stop keeps its seat and the dial has nothing visible to do.
    fillers = _density_fillers(PDV, duration_min=60, round_trip=True)
    queued = _queued(fillers[0], 40)
    rival = _poi(
        "free-door", lat=fillers[0].lat + 0.0002, lng=fillers[0].lng + 0.0002
    )
    snap = _snap([queued, rival, *fillers[1:]])
    inp = TourInput(start=PDV, duration_min=60, city_slug="paris", round_trip=True)

    control = select_route(inp, snap)
    assert queued.id in {p.id for p in control.pois}, (
        "fixture premise: the queued place must be worth seating undialed"
    )

    dialed = select_route(inp.model_copy(update={"avoid_queues": True}), snap)
    assert queued.id not in {p.id for p in dialed.pois}, (
        "the dial did not dim the queue-heavy stop"
    )
    assert len(dialed.pois) >= 2, "avoiding queues starved the day"


def test_stop_density_fewer_concentrates_the_day():
    """W4.2 ruling 4 (Camille's label: "Fewer stops, longer at each" — count
    down, anchors kept whole): the concentrate pass drops the weakest stops,
    never below three, never below the concentrate floor — a dial must not
    steer the day into its own underfill refusal."""
    from src.tour.selection import select_route

    snap = _snap(_density_fillers(PDV, duration_min=60, round_trip=True))
    base = TourInput(start=PDV, duration_min=60, city_slug="paris", round_trip=True)

    control = select_route(base, snap)
    assert len(control.pois) >= 5, (
        f"fixture premise: the undialed day must be busy, got {len(control.pois)}"
    )

    fewer = select_route(base.model_copy(update={"stop_density": "fewer"}), snap)
    assert len(fewer.pois) < len(control.pois), "the dial dropped nothing"
    assert len(fewer.pois) >= 3, "the dial concentrated below the stop floor"
    # The concentrated day keeps its strongest stops whole — no shaving here.
    control_visits = dict(control.planned_visit_seconds)
    for poi in fewer.pois:
        if poi.id in control_visits:
            assert fewer.planned_visit_seconds.get(poi.id, 0) >= control_visits[poi.id], (
                f"{poi.id} was shaved by the fewer dial; freed minutes must flow "
                "to the anchors, never out of them"
            )


def test_narration_density_scales_the_one_emission_ceiling():
    """W4.2 ruling 5 (Fiona & Dev's dial, Paulo's label "Less talking / More
    talking" — narration SUPPLY, never topic): the per-stop ceiling scales at
    the ONE emission choke point; trimmed beats land in keep-exploring
    overflow, never on the floor."""
    from src.tour.selection import (
        MAX_DWELL_AUDIO_SECONDS,
        build_poi_beat_plans_capped,
        planned_audio_seconds,
    )

    talker = _poi("talker", lat=PDV[0] + 0.0004, lng=PDV[1])
    # Six genuinely DISTINCT stories (the picker's paraphrase dedup collapses
    # near-identical bodies to one beat, which hides every ceiling): 360s raw,
    # past the default 270s ceiling, so all three densities separate.
    stories = (
        "The gate was cut in 1607 for a royal procession that never came.",
        "A fire in 1871 hollowed the upper floor and spared the stair.",
        "The fountain ran wine for one night in 1660, by decree.",
        "Two duellists met on the roof in 1832; both survived, embarrassed.",
        "The cellar held a printing press through the Occupation.",
        "A resident kept a leopard here until the neighbours petitioned.",
    )
    beats = [
        BeatRef(
            id=f"talker-b{i}",
            poi_id="talker",
            est_spoken_seconds=60,
            active_status="active",
            script_body=body,
        )
        for i, body in enumerate(stories)
    ]
    snap = _snap([talker], beats_by_poi={"talker": beats})
    route = Route(
        pois=(talker,),
        transits=(
            TransitSegment(
                from_poi_id=None, to_poi_id="talker", distance_m=50, walk_seconds=81
            ),
        ),
        total_walk_distance_m=50,
        total_walk_seconds=81,
    )

    def voiced(density):
        capped = build_poi_beat_plans_capped(
            route, snapshot=snap, lenses=None, end_is_none=True, narration_density=density
        )
        (plan, overflow) = capped[0]
        return planned_audio_seconds(plan.beats), overflow

    default_audio, default_overflow = voiced(None)
    less_audio, less_overflow = voiced("less")
    more_audio, _ = voiced("more")

    assert default_audio <= MAX_DWELL_AUDIO_SECONDS
    assert less_audio <= MAX_DWELL_AUDIO_SECONDS // 2, "'less' did not halve the ceiling"
    assert less_audio < default_audio
    assert more_audio > default_audio, "'more' did not raise the ceiling"
    # Whole-beat caps: what 'less' trims lands in keep-exploring overflow.
    assert len(less_overflow) > len(default_overflow), (
        "trimmed beats must become keep-exploring overflow, never vanish"
    )

def test_the_dials_ride_both_request_models_and_normalize_the_wire_forms():
    """W4.2 + the S4.7 workbench build: the page sends hyphenated presets
    ("take-it-easy") and weather "auto"; the engine spells presets with
    underscores and knows dry/rain. Normalized at the API edge — declared on
    BOTH request models (the S1.3a precedent: neither sets model_config, so an
    undeclared field would be silently dropped, and the caller would get an
    undialed tour with no error saying why)."""
    from src.api.models.trips import TripGenerateRequest, TripPreviewRequest

    preview = TripPreviewRequest(
        center_lat=48.85,
        center_lng=2.35,
        duration_min=120,
        party="take-it-easy",
        weather="auto",
        stop_density="fewer",
        narration_density="less",
        avoid_queues=True,
        category_minus=["museum"],
        max_leg_minutes=9,
        rest_cadence_minutes=40,
        walking_pace=1.5,
        pinned_poi_ids=["poi-1"],
    )
    assert preview.party == "take_it_easy", "the hyphen wire form must normalize"
    assert preview.weather == "auto"
    assert preview.stop_density == "fewer"
    assert preview.narration_density == "less"
    assert preview.avoid_queues is True
    assert preview.category_minus == ["museum"]
    assert preview.pinned_poi_ids == ["poi-1"]

    generate = TripGenerateRequest(
        profile_id="p1",
        center_lat=48.85,
        center_lng=2.35,
        duration_min=120,
        start_date="2026-08-12",
        end_date="2026-08-12",
        party="with-luggage",
        stop_density="more",
        avoid_queues=True,
    )
    assert generate.party == "with_luggage"
    assert generate.stop_density == "more"

    with pytest.raises(ValidationError):
        TripPreviewRequest(
            center_lat=48.85, center_lng=2.35, duration_min=60, party="marching-band"
        )


# --- the day notes are statements about the BUILT day, never the request -----
# (W4.12 closing panel — Julien, Greta, Théo, Camille, Marcus, Nadia, Aiko, Sofia:
# "Left out today, as asked: museum." printed on a day byte-identical to the
# un-dialled one; "Places with long waits were left out, as asked." printed above
# a stop whose wait had gone UP from 3 to 10 minutes; "we will see it from the
# outside" printed for a Montmartre cabaret on a Tuileries→Notre-Dame day.)


def _wire_day(*pois: POI, queue_seconds: dict[str, int] | None = None, **updates) -> Route:
    """A Route the wire's note writer can read: stops, legs, waits, closures."""
    legs = tuple(
        TransitSegment(from_poi_id=a.id, to_poi_id=b.id, distance_m=300, walk_seconds=240)
        for a, b in pairwise(pois)
    )
    return Route(
        pois=tuple(pois),
        transits=legs,
        total_walk_distance_m=300.0 * len(legs),
        total_walk_seconds=240 * len(legs),
        planned_queue_seconds=dict(queue_seconds or {}),
        **updates,
    )


def _dial_body(**dials):
    from src.api.models.trips import TripPreviewRequest

    return TripPreviewRequest(center_lat=PDV[0], center_lng=PDV[1], duration_min=180, **dials)


def test_a_kind_exclusion_note_describes_the_day_not_the_request():
    """The note is TRUE of the built day in both arms, and never a receipt for
    work not done. When the dial had nothing to remove it says so; when a
    place of the excluded kind is nonetheless in the day (a pin can outrank
    the dial) it names it rather than claiming an exclusion the list beneath
    disproves.

    UNDO TEST: restore `notes.append(f"Left out today, as asked: {kinds}.")`
    and the first arm asserts a sentence that claims an action -> RED.
    """
    from src.api.routes.trips import _preview_day_notes

    church = _categorised(_poi("Saint-Paul", lat=PDV[0], lng=PDV[1] + 0.001), "church")
    square = _poi("Place des Vosges", lat=PDV[0] + 0.001, lng=PDV[1])
    museum = _categorised(_poi("Musee Carnavalet", lat=PDV[0] + 0.002, lng=PDV[1]), "museum")

    no_museum = _preview_day_notes(_wire_day(church, square), _dial_body(category_minus=["museum"]))
    (note,) = [n for n in no_museum if "museum" in n]
    assert note == "No museum stops in this day, as asked.", note
    assert "left out" not in note.lower(), "a claim of removal on a day nothing was removed from"

    still_there = _preview_day_notes(
        _wire_day(church, museum, square), _dial_body(category_minus=["museum"])
    )
    (note,) = [n for n in still_there if "museum" in n]
    assert note == "You asked for no museum stops; still in this day: Musee Carnavalet.", note


def test_the_queue_note_names_the_longest_wait_that_remains():
    """"Skip the queues" states the RULE it applied (true whether or not it
    changed anything) and then the longest wait actually left in the day, by
    name — so a wait that went UP on the replan (arrival-hour repricing) is
    on the screen, not contradicted by it.

    UNDO TEST: restore "Places with long waits were left out, as asked." ->
    the residual-wait sentence is gone -> RED.
    """
    from src.api.routes.trips import _preview_day_notes
    from src.tour.selection import AVOID_QUEUES_EXCLUDE_PEAK_MINUTES

    a = _poi("Hotel de Sully", lat=PDV[0], lng=PDV[1] + 0.001)
    b = _poi("La Samaritaine", lat=PDV[0] + 0.001, lng=PDV[1])
    c = _poi("Place des Vosges", lat=PDV[0] + 0.002, lng=PDV[1])

    with_waits = _preview_day_notes(
        _wire_day(a, b, c, queue_seconds={a.id: 60, b.id: 600}),
        _dial_body(avoid_queues=True),
    )
    (note,) = [n for n in with_waits if "wait" in n]
    assert note.startswith(
        f"Nothing with a wait over {AVOID_QUEUES_EXCLUDE_PEAK_MINUTES} minutes at its busiest "
        "was considered, as asked"
    ), note
    assert note.endswith("the longest wait left in this day is 10 min, at La Samaritaine."), note
    assert "left out" not in note.lower()

    quiet = _preview_day_notes(_wire_day(a, c), _dial_body(avoid_queues=True))
    (note,) = [n for n in quiet if "wait" in n]
    assert note.endswith("no waits in this day."), note


def test_a_closure_note_only_promises_the_outside_of_a_place_that_is_on_the_route():
    """The planner records the closure FACT and its pool DECISION as a flag
    (ClockExclusion.kept_outside); the traveller's sentence is composed at the
    wire from whether the place actually ended up ON the route. A closed
    facade the greedy never picked is "not in your day" — never "we will see it
    from the outside".

    UNDO TEST: make the wire print `f"{ex.name} — {ex.reason}"` for every
    exclusion (the old code) -> the off-route arm loses "not in your day" -> RED.
    """
    from src.api.routes.trips import _preview_day_notes
    from src.tour.contract import ClockExclusion

    market = _poi("Marche Bastille", lat=PDV[0], lng=PDV[1] + 0.001)
    square = _poi("Place des Vosges", lat=PDV[0] + 0.001, lng=PDV[1])
    cabaret_id = "Lapin Agile"  # closed, kept in the pool at outside price, never picked

    exclusions = (
        ClockExclusion(
            poi_id=market.id, name=market.name, reason="closed all day Wednesday",
            kept_outside=True,
        ),
        ClockExclusion(
            poi_id=cabaret_id, name=cabaret_id, reason="closed all day Wednesday",
            kept_outside=True,
        ),
        ClockExclusion(
            poi_id="Crypte", name="Crypte", reason="closed all day Wednesday",
            kept_outside=False,
        ),
    )
    notes = _preview_day_notes(
        _wire_day(market, square, clock_exclusions=exclusions), _dial_body()
    )
    assert "Marche Bastille — closed all day Wednesday — we will see it from the outside" in notes
    assert "Lapin Agile — closed all day Wednesday, so it is not in your day" in notes
    assert "Crypte — closed all day Wednesday, so it is not in your day" in notes
    assert not any("Lapin Agile" in n and "outside" in n for n in notes), (
        "a place that is not on the route was promised from the outside"
    )


def test_the_api_resolves_presets_and_the_more_dial_exactly_as_the_harness_does():
    """ONE ENGINE (memory: workbench and app share ONE path). `resolve_party_axes`
    expands presets and the "more stops" dial into the axes the planner reads —
    and it was called by scripts/tour_build.py ALONE. Through the API the Party
    dropdown never expanded and `stop_density="more"` never became its stop
    ceiling. MEASURED at the W4.12 close on the live wire: the "More stops" day
    was byte-identical to base and kept a 47-minute museum, while an explicit
    20-minute ceiling on the identical request reshaped the day. Every API
    request goes through `_build_tour_input`, so that is where the resolve
    lives; this pins it.

    UNDO TEST: make `_build_tour_input` return `TourInput(**kwargs)` bare -> RED
    on both arms.
    """
    from src.api.routes.trips import _build_tour_input

    more = _build_tour_input(
        start=PDV, duration_min=180, city_slug="paris", round_trip=True, stop_density="more"
    )
    assert more.max_stop_minutes == 20, (
        "the More-stops dial did not resolve to its stop ceiling on the API path"
    )
    easy = _build_tour_input(
        start=PDV, duration_min=180, city_slug="paris", round_trip=True, party="take_it_easy"
    )
    assert easy.max_leg_minutes == 12 and easy.rest_cadence_minutes == 20, (
        "the take-it-easy preset did not expand into its axes on the API path"
    )
    # Explicit wins, on the wire as in the harness.
    explicit = _build_tour_input(
        start=PDV, duration_min=180, city_slug="paris", round_trip=True,
        stop_density="more", max_stop_minutes=45,
    )
    assert explicit.max_stop_minutes == 45


def test_promise_windows_are_coarse_on_the_wire_and_contain_the_planned_minute():
    """F&D own the coarse-window ruling (W4.2 deviation v) and re-judged the built
    thing at W4.12: "11:32-12:02" is minute-fiction — the width is the stop's
    duration, not uncertainty, and 11:32 is not a time anybody says. The planner
    keeps the exact minute (Phase 5's replan needs it); the WIRE rounds arrival
    DOWN and departure UP to five-minute marks, so the spoken window always
    contains the planned one. A zero-length window (the A→B finish point) stays
    one time — it must never widen into a stay that does not exist. Dateless
    days ("" / "") pass through untouched.

    UNDO TEST: make `_preview_promises` copy `promise.arrives_hhmm` verbatim ->
    "11:32" reaches the wire -> RED.
    """
    from src.api.routes.trips import _coarse_window

    assert _coarse_window("11:32", "12:02") == ("11:30", "12:05")
    assert _coarse_window("10:18", "10:58") == ("10:15", "11:00")
    assert _coarse_window("13:10", "14:30") == ("13:10", "14:30"), "already on the marks"
    assert _coarse_window("12:50", "12:50") == ("12:50", "12:50"), "a finish point is one time"
    assert _coarse_window("12:52", "12:52") == ("12:50", "12:50")
    assert _coarse_window("23:58", "00:03") == ("23:55", "00:05"), "midnight wraps, never 24:05"
    assert _coarse_window("", "") == ("", ""), "a dateless day carries no window"


def test_the_wire_promise_carries_the_coarse_window_not_the_planners_minute():
    """The rounding is applied where the person reads it. UNDO TEST: make
    `_preview_promises` copy the planner's minute verbatim -> RED."""
    from src.api.routes.trips import _preview_promises
    from src.tour.contract import Promise, PromiseShape

    square = _poi("Place des Vosges", lat=PDV[0], lng=PDV[1])
    promise = Promise(
        kind="anchor",
        poi_id=square.id,
        shape=PromiseShape(
            outside_seconds=1800, inside_seconds=0, queue_seconds=0,
            goes_inside=False, closed_today=False,
        ),
        arrives_hhmm="11:32",
        departs_hhmm="12:02",
    )
    route = _wire_day(square, promises=(promise,))
    (wire,) = _preview_promises(route)
    assert (wire.arrives_hhmm, wire.departs_hhmm) == ("11:30", "12:05"), (
        f"the wire shows the planner's minute: {wire.arrives_hhmm}-{wire.departs_hhmm}"
    )
    assert wire.name == "Place des Vosges"
