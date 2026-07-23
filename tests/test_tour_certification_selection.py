"""Hostile proofs for the bounded certification-only selection policy."""

from __future__ import annotations

import math

import pytest

from src.tour.contract import POI, BeatRef, TourInput
from src.tour.routing import (
    MAX_REQUESTED_FRACTION,
    MIN_REQUESTED_FRACTION,
    RoutePlanningPolicy,
    route_planning_budget,
    within_planning_timebox,
)
from src.tour.selection import (
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
        max_stops=2,
        policy_id="test-certification-policy-v1",
    )


def _routed(lat1: float, lng1: float, lat2: float, lng2: float) -> int:
    return round(math.hypot(lat2 - lat1, lng2 - lng1) * 10)


def test_certification_policy_derives_one_midpoint_budget_from_frozen_inputs():
    policy = RoutePlanningPolicy.certification(
        minimum_requested_fraction=MIN_REQUESTED_FRACTION,
        maximum_requested_fraction=MAX_REQUESTED_FRACTION,
        max_stops=8,
        policy_id="frozen-contract-and-call-plan-sha",
    )
    budget = route_planning_budget(90, policy)

    assert policy.nominal_requested_fraction == 1.0
    assert budget.minimum_elapsed_seconds == 4860
    assert budget.nominal_elapsed_seconds == 5400
    assert budget.maximum_elapsed_seconds == 5940
    assert budget.walk_budget_seconds == 2160
    assert budget.audio_target_seconds == 3240
    assert budget.max_stops == 8
    with pytest.raises(ValueError, match="one to eight stops"):
        RoutePlanningPolicy.certification(
            minimum_requested_fraction=MIN_REQUESTED_FRACTION,
            maximum_requested_fraction=MAX_REQUESTED_FRACTION,
            max_stops=9,
            policy_id="invalid-call-plan",
        )


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
    assert len(trial.ordered) <= policy.max_stops
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

    expected = sorted((walk_slog.id, destination.id))
    assert repair(pois) == expected
    assert repair(list(reversed(pois))) == expected


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
