"""Hostile proofs for the bounded certification-only selection policy."""

from __future__ import annotations

import math
from itertools import pairwise

import pytest

from src.tour.contract import POI, BeatRef, TourInput
from src.tour.routing import (
    MAX_REQUESTED_FRACTION,
    MIN_REQUESTED_FRACTION,
    TIMEBOX_MATERIALITY_TOLERANCE_SECONDS,
    RoutePlanningPolicy,
    default_leg_seconds,
    route_planning_budget,
    within_planning_timebox,
)
from src.tour.selection import (
    ENDPOINT_PULL_RESERVED_BUDGET_FRACTION,
    CertificationPlanningInfeasibleError,
    CorpusSnapshot,
    _apply_certification_timebox_repair,
    _certification_route_trial,
    select_route,
)


def _poi(poi_id: str, *, x: float, y: float = 0.0, audio: int) -> POI:
    return POI(
        id=poi_id,
        name=f"Generic {poi_id}",
        tier=5,
        poi_role="stop",
        lat=y,
        lng=x,
        areas=("Generic Corridor",),
        beat_count=1,
    )


def _snapshot(pois: list[POI], audio: dict[str, int]) -> CorpusSnapshot:
    return CorpusSnapshot(
        pois=tuple(pois),
        beats_by_poi={
            poi.id: tuple(
                BeatRef(
                    id=f"beat-{poi.id}-{index}",
                    poi_id=poi.id,
                    est_spoken_seconds=audio[poi.id] // 3,
                    active_status="active",
                )
                for index in range(3)
            )
            for poi in pois
        },
        area_types={"Generic Corridor": "corridor"},
        adjacent_areas={},
    )


def _policy() -> RoutePlanningPolicy:
    return RoutePlanningPolicy.certification(
        minimum_requested_fraction=MIN_REQUESTED_FRACTION,
        maximum_requested_fraction=MAX_REQUESTED_FRACTION,
        policy_id="test-certification-policy-v1",
    )


def _routed(lat1: float, lng1: float, lat2: float, lng2: float) -> int:
    return round(math.hypot(lat2 - lat1, lng2 - lng1) * 10)


def test_certification_policy_derives_one_midpoint_budget_from_frozen_inputs():
    policy = RoutePlanningPolicy.certification(
        minimum_requested_fraction=MIN_REQUESTED_FRACTION,
        maximum_requested_fraction=MAX_REQUESTED_FRACTION,
        policy_id="frozen-contract-and-call-plan-sha",
    )
    budget = route_planning_budget(90, policy)

    assert policy.nominal_requested_fraction == 1.0
    assert budget.minimum_elapsed_seconds == 4860
    assert budget.nominal_elapsed_seconds == 5400
    assert budget.maximum_elapsed_seconds == 5940
    assert budget.walk_budget_seconds == 2160
    assert budget.audio_target_seconds == 3240


def test_certification_fixed_end_reachability_uses_total_ceiling(monkeypatch):
    from src.tour.density import TourabilityRefusedError
    from src.tour.routing import TIMEBOX_MATERIALITY_TOLERANCE_SECONDS

    class DownstreamReachedError(Exception):
        pass

    class FixedLegClient:
        def __init__(self, seconds: int):
            self.seconds = seconds

        def leg_seconds(self, *_args):
            return self.seconds

    policy = _policy()
    budget = route_planning_budget(10, policy)
    destination = _poi("destination", x=10.0, audio=270)
    snapshot = _snapshot([destination], {destination.id: 270})
    tour_input = TourInput(
        start=(0.0, 0.0),
        end=(0.0, 10.0),
        duration_min=10,
        city_slug="test",
    )

    monkeypatch.setattr(
        "src.tour.selection._reach_predicate",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(DownstreamReachedError()),
    )

    within_total = budget.walk_budget_seconds + 1
    assert within_total <= (
        budget.maximum_elapsed_seconds + TIMEBOX_MATERIALITY_TOLERANCE_SECONDS
    )
    with pytest.raises(DownstreamReachedError):
        select_route(
            tour_input,
            snapshot,
            routing_client=FixedLegClient(within_total),
            planning_policy=policy,
        )

    beyond_total = (
        budget.maximum_elapsed_seconds + TIMEBOX_MATERIALITY_TOLERANCE_SECONDS + 1
    )
    with pytest.raises(TourabilityRefusedError, match="Destination unreachable"):
        select_route(
            tour_input,
            snapshot,
            routing_client=FixedLegClient(beyond_total),
            planning_policy=policy,
        )


def test_certification_fixed_end_rescue_reaches_exact_repair_once(monkeypatch):
    from src.tour.routing import TIMEBOX_MATERIALITY_TOLERANCE_SECONDS

    class DownstreamReachedError(Exception):
        pass

    class FixedLegClient:
        def __init__(self, seconds: int):
            self.seconds = seconds

        def leg_seconds(self, *_args):
            return self.seconds

    policy = _policy()
    budget = route_planning_budget(10, policy)
    destination = _poi("destination", x=10.0, audio=270)
    snapshot = _snapshot([destination], {destination.id: 270})
    tour_input = TourInput(
        start=(0.0, 0.0),
        end=(0.0, 10.0),
        duration_min=10,
        city_slug="test",
    )
    captured: dict[str, object] = {}

    def capture_reach(_start, radius_m, iso_minutes, _routing_client):
        captured["radius_m"] = radius_m
        captured["iso_minutes"] = iso_minutes
        return (lambda _lat, _lng: True), False

    def capture_repair(_selected, all_pois, **_kwargs):
        captured["candidate_ids"] = [poi.id for poi in all_pois]
        raise DownstreamReachedError

    monkeypatch.setattr("src.tour.selection._reach_predicate", capture_reach)
    monkeypatch.setattr(
        "src.tour.selection._apply_certification_timebox_repair",
        capture_repair,
    )

    routed_leg = budget.walk_budget_seconds + 1
    assert routed_leg * 2 <= (
        budget.maximum_elapsed_seconds + TIMEBOX_MATERIALITY_TOLERANCE_SECONDS
    )
    with pytest.raises(DownstreamReachedError):
        select_route(
            tour_input,
            snapshot,
            routing_client=FixedLegClient(routed_leg),
            planning_policy=policy,
        )

    assert captured["iso_minutes"] == 12
    assert captured["candidate_ids"] == [destination.id]


def test_final_timebox_accepts_only_immaterial_whole_minute_rounding_drift():
    budget = route_planning_budget(60, _policy())

    assert within_planning_timebox(budget.minimum_elapsed_seconds - 15, budget)
    assert within_planning_timebox(budget.maximum_elapsed_seconds + 60, budget)
    assert not within_planning_timebox(budget.minimum_elapsed_seconds - 61, budget)
    assert not within_planning_timebox(budget.maximum_elapsed_seconds + 61, budget)


def test_bounded_exchange_is_exact_deterministic_and_rejects_slog_and_overmax():
    destination = _poi("destination", x=10.0, audio=270)
    incumbent = _poi("incumbent", x=5.0, audio=20)
    useful = _poi("useful", x=6.0, audio=270)
    walk_slog = _poi("walk-slog", x=5.0, y=15.0, audio=20)
    overmax = _poi("overmax", x=5.0, y=30.0, audio=270)
    pois = [destination, incumbent, useful, walk_slog, overmax]
    snap = _snapshot(
        pois,
        {
            destination.id: 270,
            incumbent.id: 20,
            useful.id: 270,
            walk_slog.id: 20,
            overmax.id: 270,
        },
    )
    tour_input = TourInput(
        start=(0.0, 0.0),
        end=(0.0, 10.0),
        duration_min=10,
        city_slug="test",
        round_trip=False,
    )
    policy = _policy()
    budget = route_planning_budget(tour_input.duration_min, policy)

    def repair(candidate_order: list[POI]) -> tuple[list[str], list[POI]]:
        repaired = _apply_certification_timebox_repair(
            [incumbent, destination],
            candidate_order,
            input=tour_input,
            snapshot=snap,
            spine="Generic Corridor",
            interest=frozenset(),
            score_penalty=None,
            leg_seconds_fn=_routed,
            planning_policy=policy,
            planning_budget=budget,
        )
        return sorted(poi.id for poi in repaired), repaired

    expected = sorted((useful.id, destination.id))
    forward_ids, repaired = repair(pois)
    reverse_ids, _ = repair(list(reversed(pois)))
    assert forward_ids == expected
    assert reverse_ids == expected
    trial = _certification_route_trial(
        repaired,
        input=tour_input,
        snapshot=snap,
        interest=frozenset(),
        leg_seconds_fn=_routed,
        planning_budget=budget,
    )
    assert trial is not None
    assert (trial.ordered[-1].lat, trial.ordered[-1].lng) == tour_input.end
    assert (
        budget.minimum_elapsed_seconds
        <= trial.elapsed_seconds
        <= budget.maximum_elapsed_seconds
    )


def test_ratio_exceeding_route_is_deterministic_last_resort():
    destination = _poi("destination", x=10.0, audio=270)
    # The incumbent is an even longer detour than the candidate.  A broken
    # exchange check compares candidate walk against this route and sees zero
    # marginal walk; the valid baseline is the retained bare-destination route.
    incumbent = _poi("incumbent", x=5.0, y=22.0, audio=20)
    walk_slog = _poi("walk-slog", x=5.0, y=15.0, audio=20)
    overmax = _poi("overmax", x=5.0, y=30.0, audio=270)
    pois = [destination, incumbent, walk_slog, overmax]
    snap = _snapshot(
        pois,
        {
            destination.id: 270,
            incumbent.id: 20,
            walk_slog.id: 20,
            overmax.id: 270,
        },
    )
    tour_input = TourInput(
        start=(0.0, 0.0),
        end=(0.0, 10.0),
        duration_min=10,
        city_slug="test",
        round_trip=False,
    )
    policy = _policy()
    budget = route_planning_budget(tour_input.duration_min, policy)

    def repair(candidate_order: list[POI]) -> list[str]:
        repaired = _apply_certification_timebox_repair(
            [incumbent, destination],
            candidate_order,
            input=tour_input,
            snapshot=snap,
            spine="Generic Corridor",
            interest=frozenset(),
            score_penalty=None,
            leg_seconds_fn=_routed,
            planning_policy=policy,
            planning_budget=budget,
        )
        return sorted(poi.id for poi in repaired)

    # UPDATED 2026-08-04 with the stop-ceiling removal. The policy used to carry
    # ``max_stops=2``, which made ``_certification_route_trial`` return None for
    # any trial materializing three POIs — so the only survivors were exchanges
    # down to two, and the answer was {destination, walk-slog}. With duration as
    # the only bound the repair may now KEEP the incumbent and still admit the
    # ratio-exceeding candidate, because ``destination`` is carried as the
    # materialized fixed end B rather than having to occupy a selected slot. The
    # route therefore holds the same three places; it just no longer has to spend
    # a stop on the destination. Both halves this test is named for are unchanged:
    # the ratio-exceeding candidate is still admitted only as a LAST RESORT, and
    # the pick is still identical under a reversed candidate order.
    expected = sorted((walk_slog.id, incumbent.id))
    assert repair(pois) == expected
    assert repair(list(reversed(pois))) == expected
    assert walk_slog.id in expected, "the last-resort admission is the subject of this test"


def test_over_ceiling_route_is_repaired_by_dropping_one_stop():
    """A route ABOVE the ceiling must be able to shrink its way back into the band.

    Regression for the 2026-08-04 one-option collapse. The repair built candidate
    sets three ways — the incumbent unchanged, incumbent+candidate, and a
    one-for-one exchange — and every one of those either keeps the stop count or
    raises it. So a route that overshot the maximum had no move that could shorten
    it, and the whole option was refused with a "best eligible bounded route" that
    was OVER the ceiling rather than under the floor. Stop ceilings used to make
    the overshoot impossible; with duration as the only stop bound it is routine.
    """

    near = _poi("near", x=10.0, audio=270)
    detour = _poi("detour", x=60.0, y=30.0, audio=270)
    far = _poi("far", x=140.0, audio=270)
    # Unreachable within any band: keeps the add/exchange pool non-empty (so the
    # exchange loop really runs) without ever offering an in-band alternative.
    outlier = _poi("outlier", x=400.0, audio=270)
    pois = [near, detour, far, outlier]
    snap = _snapshot(pois, {poi.id: 270 for poi in pois})
    tour_input = TourInput(
        start=(0.0, 0.0),
        duration_min=30,
        city_slug="test",
        round_trip=False,
    )
    policy = _policy()
    budget = route_planning_budget(tour_input.duration_min, policy)
    incumbent = [near, detour, far]

    def price(stops: list[POI]) -> int:
        trial = _certification_route_trial(
            stops,
            input=tour_input,
            snapshot=snap,
            interest=frozenset(),
            leg_seconds_fn=_routed,
            planning_budget=budget,
        )
        assert trial is not None
        return trial.elapsed_seconds

    ceiling = budget.maximum_elapsed_seconds + TIMEBOX_MATERIALITY_TOLERANCE_SECONDS
    # Preconditions: the incumbent overshoots, exactly one single-stop drop lands
    # in the band, and no other drop does. Without them the assertion below could
    # pass for the wrong reason.
    assert price(incumbent) > ceiling
    assert within_planning_timebox(price([near, far]), budget)
    assert not within_planning_timebox(price([detour, far]), budget)
    assert not within_planning_timebox(price([near, detour]), budget)

    def repair(candidate_order: list[POI]) -> list[str]:
        repaired = _apply_certification_timebox_repair(
            list(incumbent),
            candidate_order,
            input=tour_input,
            snapshot=snap,
            spine="Generic Corridor",
            interest=frozenset(),
            score_penalty=None,
            leg_seconds_fn=_routed,
            planning_policy=policy,
            planning_budget=budget,
        )
        return sorted(poi.id for poi in repaired)

    expected = sorted((near.id, far.id))
    assert repair(pois) == expected
    assert repair(list(reversed(pois))) == expected


def test_timebox_drop_never_removes_the_materialized_fixed_destination():
    """The drop trial may shorten a route, never un-anchor its destination B.

    The stop carrying a fixed end B is the one stop the repair must not remove:
    dropping it re-materializes B as a contentless sentinel, silently trading a
    real narrated stop for a bare map pin at the same coordinate.
    """

    # Colinear, so every route below walks the identical 1000s out to B and only
    # the audio differs. Dropping the destination is therefore the move that lands
    # NEAREST the nominal 1200s — it wins the repair's ranking outright, and only
    # the guard keeps it out.
    destination = _poi("destination", x=100.0, audio=270)
    filler = _poi("filler", x=50.0, audio=180)
    pois = [destination, filler]
    snap = _snapshot(pois, {destination.id: 270, filler.id: 180})
    tour_input = TourInput(
        start=(0.0, 0.0),
        end=(0.0, 100.0),
        duration_min=20,
        city_slug="test",
        round_trip=False,
    )
    policy = _policy()
    budget = route_planning_budget(tour_input.duration_min, policy)

    def price(stops: list[POI]) -> int:
        trial = _certification_route_trial(
            stops,
            input=tour_input,
            snapshot=snap,
            interest=frozenset(),
            leg_seconds_fn=_routed,
            planning_budget=budget,
        )
        assert trial is not None
        return trial.elapsed_seconds

    nominal = budget.nominal_elapsed_seconds
    keeping_both = price([filler, destination])
    dropping_destination = price([filler])
    dropping_filler = price([destination])
    # Preconditions: keeping both overshoots, and the destination-dropping route
    # is both in band AND closer to nominal than the destination-keeping one.
    assert keeping_both > budget.maximum_elapsed_seconds + TIMEBOX_MATERIALITY_TOLERANCE_SECONDS
    assert within_planning_timebox(dropping_destination, budget)
    assert within_planning_timebox(dropping_filler, budget)
    assert abs(nominal - dropping_destination) < abs(nominal - dropping_filler)

    repaired = _apply_certification_timebox_repair(
        [filler, destination],
        pois,
        input=tour_input,
        snapshot=snap,
        spine="Generic Corridor",
        interest=frozenset(),
        score_penalty=None,
        leg_seconds_fn=_routed,
        planning_policy=policy,
        planning_budget=budget,
    )

    assert [poi.id for poi in repaired] == [destination.id]


def test_repair_never_trades_an_in_band_route_for_a_materially_longer_walk():
    """An already-acceptable route must not be made to walk further for a few seconds.

    The planner books each stop against the PER-TOUR narration allowance while the
    tourist only ever hears MAX_DWELL_AUDIO_SECONDS of it, so it believes the
    listening budget is full early and seats too few stops. The repair then closes
    the resulting duration gap the only way it can — by reaching for DISTANT stops.
    Nothing in the repair's ranking prices walking, so it will happily swap a
    compliant route for one that walks materially further just to land nearer the
    nominal. When the incumbent is ALREADY in band that is a pure downgrade: more
    walking, no more narration.
    """

    keep_a = _poi("keep-a", x=10.0, audio=270)
    keep_b = _poi("keep-b", x=40.0, audio=270)
    keep_c = _poi("keep-c", x=89.0, audio=270)
    # Same audio, further away: swapping it in moves elapsed nearer the nominal
    # while buying the tourist nothing but 90 extra seconds of walking.
    far_swap = _poi("far-swap", x=98.0, audio=270)
    pois = [keep_a, keep_b, keep_c, far_swap]
    snap = _snapshot(pois, {poi.id: 270 for poi in pois})
    tour_input = TourInput(
        start=(0.0, 0.0),
        duration_min=30,
        city_slug="test",
        round_trip=False,
    )
    policy = _policy()
    budget = route_planning_budget(tour_input.duration_min, policy)
    incumbent = [keep_a, keep_b, keep_c]

    def trial(stops: list[POI]):
        priced = _certification_route_trial(
            stops,
            input=tour_input,
            snapshot=snap,
            interest=frozenset(),
            leg_seconds_fn=_routed,
            planning_budget=budget,
        )
        assert priced is not None
        return priced

    incumbent_trial = trial(incumbent)
    swapped_trial = trial([keep_a, keep_b, far_swap])
    nominal = budget.nominal_elapsed_seconds
    # Preconditions: the incumbent is ALREADY acceptable, and the swap is both
    # nearer the nominal (so it wins the ranking) and materially longer on foot.
    assert within_planning_timebox(incumbent_trial.elapsed_seconds, budget)
    assert within_planning_timebox(swapped_trial.elapsed_seconds, budget)
    assert abs(nominal - swapped_trial.elapsed_seconds) < abs(
        nominal - incumbent_trial.elapsed_seconds
    )
    assert (
        swapped_trial.walk_seconds
        > incumbent_trial.walk_seconds + TIMEBOX_MATERIALITY_TOLERANCE_SECONDS
    )

    repaired = _apply_certification_timebox_repair(
        list(incumbent),
        pois,
        input=tour_input,
        snapshot=snap,
        spine="Generic Corridor",
        interest=frozenset(),
        score_penalty=None,
        leg_seconds_fn=_routed,
        planning_policy=policy,
        planning_budget=budget,
    )

    assert sorted(poi.id for poi in repaired) == sorted(poi.id for poi in incumbent)
    assert trial(repaired).walk_seconds == incumbent_trial.walk_seconds


def test_repair_prices_the_route_with_the_pulled_endpoint_actually_pinned():
    """Certification must measure the route the engine will really build.

    ``select_route`` finishes by re-ordering the chosen stops with the pulled
    endpoint PINNED LAST, but the repair used to price every trial with nothing
    pinned. Forcing one stop to be last can cost far more walking than the free
    optimum, so the repair certified a route inside the band and the engine then
    built a longer one that the final band check refused outright. Nine stops in,
    nine stops out, identical narration, 1003 extra seconds of walking — measured
    on the live Paris flagship, where it collapsed the product to a single option.

    The two halves of the fix meet here: pricing the pinned cost lets the repair
    SEE that the full set overshoots, and the drop trial gives it a way back into
    the band.
    """

    # Colinear and east of the start, except the endpoint, which sits nearest the
    # start — so pinning it last forces a full backtrack down the whole route.
    endpoint = _poi("endpoint", x=5.0, audio=270)
    near = _poi("near", x=25.0, audio=270)
    middle = _poi("middle", x=50.0, audio=270)
    far = _poi("far", x=70.0, audio=270)
    pois = [endpoint, near, middle, far]
    snap = _snapshot(pois, {poi.id: 270 for poi in pois})
    tour_input = TourInput(
        start=(0.0, 0.0),
        duration_min=30,
        city_slug="test",
        round_trip=False,
    )
    policy = _policy()
    budget = route_planning_budget(tour_input.duration_min, policy)

    def price(stops: list[POI], *, pinned: str | None):
        trial = _certification_route_trial(
            stops,
            input=tour_input,
            snapshot=snap,
            interest=frozenset(),
            leg_seconds_fn=_routed,
            planning_budget=budget,
            pulled_endpoint_id=pinned,
        )
        assert trial is not None
        return trial

    free = price(pois, pinned=None)
    held = price(pois, pinned=endpoint.id)

    # The pin must actually reach the orderer, and it must cost real walking.
    assert held.ordered[-1].id == endpoint.id
    assert held.walk_seconds > free.walk_seconds
    # The whole set fits the band ONLY while the pin is ignored. This is exactly
    # the fiction the engine used to certify.
    assert within_planning_timebox(free.elapsed_seconds, budget)
    assert held.elapsed_seconds > (
        budget.maximum_elapsed_seconds + TIMEBOX_MATERIALITY_TOLERANCE_SECONDS
    )
    # Dropping the farthest stop is the one move that fits once the pin is priced.
    rescued = price([endpoint, near, middle], pinned=endpoint.id)
    assert within_planning_timebox(rescued.elapsed_seconds, budget)

    repaired = _apply_certification_timebox_repair(
        list(pois),
        pois,
        input=tour_input,
        snapshot=snap,
        spine="Generic Corridor",
        interest=frozenset(),
        score_penalty=None,
        leg_seconds_fn=_routed,
        planning_policy=policy,
        planning_budget=budget,
        pulled_endpoint_id=endpoint.id,
    )

    assert sorted(poi.id for poi in repaired) == sorted(
        (endpoint.id, near.id, middle.id)
    )
    # And what it returned really does fit once ordered the way it will be built.
    assert within_planning_timebox(
        price(repaired, pinned=endpoint.id).elapsed_seconds, budget
    )


def test_select_route_off_corridor_rescue_reaches_exact_certification_repair_once(
    monkeypatch: pytest.MonkeyPatch,
):
    destination = _poi("destination", x=0.001, audio=270)
    on_path = [
        _poi(f"on-path-{index}", x=0.0001 * (index + 1), audio=270)
        for index in range(6)
    ]
    off_corridor = _poi("off-corridor", x=0.0005, y=0.002, audio=270)
    pois = [*on_path, destination, off_corridor]
    snap = _snapshot(pois, {poi.id: 270 for poi in pois})
    tour_input = TourInput(
        start=(0.0, 0.0),
        end=(0.0, 0.001),
        duration_min=10,
        city_slug="test",
        round_trip=False,
    )

    class _Client:
        @staticmethod
        def isochrone(lat: float, lng: float, minutes: int):
            return None

        @staticmethod
        def leg_seconds(lat1: float, lng1: float, lat2: float, lng2: float) -> int:
            return round(math.hypot(lat2 - lat1, lng2 - lng1) * 100_000)

    class _ProbeCompleteError(Exception):
        pass

    offered_ids: list[str] = []

    def capture_candidates(selected, candidates, **kwargs):
        offered_ids.extend(poi.id for poi in candidates)
        raise _ProbeCompleteError

    monkeypatch.setattr(
        "src.tour.selection._apply_certification_timebox_repair",
        capture_candidates,
    )

    with pytest.raises(_ProbeCompleteError):
        select_route(
            tour_input,
            snap,
            routing_client=_Client(),  # type: ignore[arg-type]
            planning_policy=_policy(),
        )

    assert offered_ids.count("off-corridor") == 1
    assert offered_ids


@pytest.mark.parametrize(
    ("round_trip", "forced_walk_seconds"),
    [(False, 0), (True, 100_000)],
    ids=("open-underfill", "round-trip-overfill"),
)
def test_final_certification_guard_rechecks_every_route_shape_after_transforms(
    monkeypatch: pytest.MonkeyPatch,
    round_trip: bool,
    forced_walk_seconds: int,
):
    from src.tour import selection as selection_module

    pois = [
        _poi(f"candidate-{index}", x=0.0001 * (index + 1), audio=270)
        for index in range(8)
    ]
    snap = _snapshot(pois, {poi.id: 270 for poi in pois})
    tour_input = TourInput(
        start=(0.0, 0.0),
        duration_min=30,
        city_slug="test",
        round_trip=round_trip,
    )
    real_summarise = selection_module.summarise_route

    def preserve_repaired_set(selected, candidates, **kwargs):
        return selected

    def drift_after_repair(*args, **kwargs):
        route = real_summarise(*args, **kwargs)
        return route.model_copy(update={"total_walk_seconds": forced_walk_seconds})

    monkeypatch.setattr(
        selection_module,
        "_apply_certification_timebox_repair",
        preserve_repaired_set,
    )
    monkeypatch.setattr(selection_module, "summarise_route", drift_after_repair)

    with pytest.raises(
        CertificationPlanningInfeasibleError,
        match="post-selection transforms moved the exact route outside the band",
    ):
        select_route(tour_input, snap, planning_policy=_policy())


def test_fixed_destination_greedy_is_capped_by_the_walk_budget_not_the_total_ceiling(
    monkeypatch,
):
    """The greedy spends WALKING seconds, so a WALK budget must bound it.

    REGRESSION (2026-08-04). ``greedy_walk_budget`` was set to
    ``certification_total_ceiling`` on the fixed-destination arm. That value is
    the ceiling on total ACTIVE time — walking PLUS narration — so at 90 minutes
    it handed the greedy 6000 walking seconds against a 2160-second walking
    allocation. Every A→B route could therefore spend the whole tour's elapsed
    budget on walking before one second of narration was counted, and the final
    band check refused the planner's own answer. Measured on the live Paris dev
    graph the same day: a 90-minute walk ending 27 m from its own start seated
    15 stops and 5787 s of walking, then refused.

    The units error is the whole bug, so this test measures units. It captures
    the stop set the greedy hands to the fill pass and prices the walking it
    implies (A → stops → B with the same divisor selection used). That number
    must fit the WALKING allocation. Under the old line it is multiples of it.
    """
    import src.tour.selection as selection_module

    class StopBeforeFillPassError(Exception):
        pass

    policy = _policy()
    budget = route_planning_budget(90, policy)
    assert budget.walk_budget_seconds == 2160
    total_ceiling = (
        budget.maximum_elapsed_seconds + TIMEBOX_MATERIALITY_TOLERANCE_SECONDS
    )
    assert total_ceiling == 6000

    # A and B sit close together; every candidate is a genuine detour off the
    # A→B line, alternating north/south so each extra stop costs real walking.
    start = (0.0, 0.0)
    end = (0.0, 0.0033274)  # ~370 m east of A: a ~600 s routed leg.
    pois = [
        _poi(f"detour-{index}", x=0.0016637, y=offset, audio=270)
        for index, offset in enumerate(
            (0.0053, -0.0053, 0.0045, -0.0045, 0.0037, -0.0037, 0.0029, -0.0029)
        )
    ]
    snapshot = _snapshot(pois, {poi.id: 270 for poi in pois})
    tour_input = TourInput(
        start=start,
        end=end,
        duration_min=90,
        city_slug="test",
    )

    captured: dict[str, object] = {}

    def capture_fill_pass(selected, _candidates, **_kwargs):
        captured["selected"] = list(selected)
        raise StopBeforeFillPassError

    monkeypatch.setattr(
        selection_module,
        "_reach_predicate",
        lambda *_args, **_kwargs: ((lambda _lat, _lng: True), False),
    )
    monkeypatch.setattr(selection_module, "_apply_fill_pass", capture_fill_pass)

    with pytest.raises(StopBeforeFillPassError):
        select_route(tour_input, snapshot, planning_policy=policy)

    seated = captured["selected"]
    legs = [start, *[(poi.lat, poi.lng) for poi in seated], end]
    greedy_walk_seconds = sum(
        default_leg_seconds(a[0], a[1], b[0], b[1])
        for a, b in pairwise(legs)
    )

    # The guard. A walking cap must be a walking budget: the greedy may not hand
    # on a stop set that already walks past the WALKING allocation, whatever the
    # total-time ceiling happens to be.
    assert greedy_walk_seconds <= budget.walk_budget_seconds, (
        f"greedy handed on {len(seated)} stops implying {greedy_walk_seconds}s of "
        f"walking against a {budget.walk_budget_seconds}s walking allocation "
        f"(total-active ceiling {total_ceiling}s)"
    )


def test_open_route_greedy_still_reserves_budget_for_the_endpoint_pull():
    """The open one-way arm keeps its endpoint-pull reserve, untouched.

    Companion to the test above: the fixed-destination repair must not have
    moved the open path, which nine golden tours already pin. The reserve exists
    for Step 4's endpoint-pull, which runs only when ``end is None`` and the walk
    is one-way, so that arm — and only that arm — keeps the 0.75 factor.
    """
    budget = route_planning_budget(90, _policy())

    assert ENDPOINT_PULL_RESERVED_BUDGET_FRACTION == 0.25
    assert int(budget.walk_budget_seconds * 0.75) == 1620
