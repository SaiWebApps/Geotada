"""Step 2.2a — fixed-destination feasibility refusal.

When a tour carries a fixed end B, the routed A→B leg alone must fit inside
the walk budget. If it does not, ``select_route`` raises
``TourabilityRefusedError`` BEFORE the greedy, carrying:

- ``gap_minutes`` (int): how many minutes the routed A→B leg overshoots the
  walk budget.
- a ``"loop"`` alternative (drop B, walk an open loop from A at the requested
  duration).
- an ``"extend"`` alternative (keep B, lengthen the tour to the A→B-correct
  smallest duration whose walk budget covers the routed A→B leg).

These are REAL ``select_route`` runs over synthetic corpora — the cost
function is never mocked. ``end=None`` never enters the branch, so the
Step-2.0d ordered-POI identity baseline is untouched.
"""

from __future__ import annotations

import math

import pytest

from src.tour.contract import POI, BeatRef, TourInput
from src.tour.density import FeasibilityAlternative, TourabilityRefusedError
from src.tour.routing import (
    default_leg_seconds,
    smallest_duration_min_for_walk_seconds,
    walk_budget_seconds,
)
from src.tour.selection import CorpusSnapshot, select_k_routes, select_route

PDV = (48.8555, 2.3656)


def _density_fillers(start: tuple[float, float]) -> list[POI]:
    """4 tier-5 anchor candidates clustered near `start`.

    The Phase 6 density gate requires >=4 rich-beat anchor candidates in a
    tight cluster to clear (avoid RED), so feasibility tests reach the Step
    2.2a branch instead of tripping the RED raise. Colocated near start, so
    they don't perturb spine/envelope/distance behaviour.
    """
    return [
        POI(
            id=f"filler-{i}",
            name=f"filler-{i}",
            tier=5,
            poi_role="stop",
            lat=start[0] + 0.00005 * i,
            lng=start[1] + 0.00005 * i,
            areas=("Le Marais",),
            beat_count=8,
        )
        for i in range(4)
    ]


def _snap(pois: list[POI]) -> CorpusSnapshot:
    """CorpusSnapshot with rich synthetic beats per POI (clears fill_ratio)."""
    beats: dict[str, tuple[BeatRef, ...]] = {
        p.id: tuple(
            BeatRef(
                id=f"{p.id}-b{i}",
                poi_id=p.id,
                est_spoken_seconds=240,
                active_status="active",
            )
            for i in range(max(0, p.beat_count or 0))
        )
        for p in pois
    }
    return CorpusSnapshot(
        pois=tuple(pois),
        beats_by_poi=beats,
        area_types={"Paris": "city", "Le Marais": "neighborhood"},
        adjacent_areas={},
        lens_neighbors={},
    )


# A destination far enough east of PdV that the routed (pace-corrected
# haversine) A→B leg dwarfs the walk budget of any short tour. We never
# hardcode the leg seconds — every assertion derives from the live
# routing functions so the test fails only if the BEHAVIOUR is wrong.
FAR_EAST_END = (PDV[0], PDV[1] + 0.060)  # ~4.4 km east; far beyond a 30-min budget
NEAR_END = (PDV[0], PDV[1] + 0.0004)  # ~30 m east; trivially inside any budget


def _green_snapshot():
    return _snap(_density_fillers(PDV))


# ---------------------------------------------------------------------------
# The helper itself (pure inverse of walk_budget_seconds).
# ---------------------------------------------------------------------------


def test_smallest_duration_is_least_minute_covering_target():
    """The helper returns the LEAST integer minute whose budget covers target."""
    target = walk_budget_seconds(50)  # an exact budget value for d=50
    d = smallest_duration_min_for_walk_seconds(target)
    # d covers target, and one minute less does NOT (true minimality).
    assert walk_budget_seconds(d) >= target
    assert walk_budget_seconds(d - 1) < target


def test_smallest_duration_floor_is_one():
    """A target inside the 1-minute budget still returns at least 1 minute."""
    assert smallest_duration_min_for_walk_seconds(0) == 1
    assert smallest_duration_min_for_walk_seconds(walk_budget_seconds(1)) == 1


def test_smallest_duration_is_monotonic_and_sufficient():
    """For an arbitrary leg time, the returned duration's budget covers it."""
    t = default_leg_seconds(PDV[0], PDV[1], FAR_EAST_END[0], FAR_EAST_END[1])
    d = smallest_duration_min_for_walk_seconds(t)
    assert walk_budget_seconds(d) >= t
    assert walk_budget_seconds(d - 1) < t


# ---------------------------------------------------------------------------
# Far A→B + short budget RAISES, carrying gap + loop + extend.
# ---------------------------------------------------------------------------


def test_far_end_short_budget_raises_with_gap_and_alternatives():
    snap = _green_snapshot()
    inp = TourInput(
        start=PDV, end=FAR_EAST_END, duration_min=30, city_slug="paris"
    )
    # Precondition for the test to be meaningful: the routed A→B leg really
    # does exceed the walk budget (derived, not assumed).
    t_ab = default_leg_seconds(PDV[0], PDV[1], FAR_EAST_END[0], FAR_EAST_END[1])
    budget = walk_budget_seconds(30)
    assert t_ab > budget

    with pytest.raises(TourabilityRefusedError) as excinfo:
        select_route(inp, snap)
    exc = excinfo.value

    # gap_minutes is a positive int equal to the ceil-overshoot in minutes.
    assert isinstance(exc.gap_minutes, int)
    assert exc.gap_minutes >= 1
    assert exc.gap_minutes == math.ceil((t_ab - budget) / 60)

    # Exactly a loop and an extend alternative, both structured.
    kinds = {alt.kind for alt in exc.alternatives}
    assert kinds == {"loop", "extend"}
    by_kind = {alt.kind: alt for alt in exc.alternatives}

    loop = by_kind["loop"]
    assert isinstance(loop, FeasibilityAlternative)
    assert loop.drop_end is True
    assert loop.duration_min == 30  # loop at the requested duration

    extend = by_kind["extend"]
    assert extend.drop_end is False
    # The extend duration is the A→B-correct smallest duration: its budget
    # covers the routed leg, and it is genuinely longer than requested.
    assert extend.duration_min > 30
    assert walk_budget_seconds(extend.duration_min) >= t_ab
    assert walk_budget_seconds(extend.duration_min - 1) < t_ab


def test_extend_alternative_is_not_density_max_supportable():
    """The extend duration is derived from the A→B leg, independent of
    density.max_supportable_duration_min (which is None on a non-RED,
    fill-healthy corpus)."""
    snap = _green_snapshot()
    inp = TourInput(start=PDV, end=FAR_EAST_END, duration_min=30, city_slug="paris")
    with pytest.raises(TourabilityRefusedError) as excinfo:
        select_route(inp, snap)
    exc = excinfo.value
    # The corpus is fill-healthy near A, so assessment is not RED and the
    # diagnostic max_supportable is None — yet extend is a concrete int.
    assert exc.assessment.status != "RED"
    assert exc.assessment.max_supportable_duration_min is None
    extend = next(a for a in exc.alternatives if a.kind == "extend")
    assert isinstance(extend.duration_min, int)
    t_ab = default_leg_seconds(PDV[0], PDV[1], FAR_EAST_END[0], FAR_EAST_END[1])
    assert extend.duration_min == smallest_duration_min_for_walk_seconds(t_ab)


# ---------------------------------------------------------------------------
# Within-budget A→B does NOT raise.
# ---------------------------------------------------------------------------


def test_near_end_within_budget_does_not_raise():
    snap = _green_snapshot()
    inp = TourInput(start=PDV, end=NEAR_END, duration_min=60, city_slug="paris")
    # The near leg is comfortably inside the budget.
    t_ab = default_leg_seconds(PDV[0], PDV[1], NEAR_END[0], NEAR_END[1])
    assert t_ab <= walk_budget_seconds(60)
    # No raise — a Route is returned.
    route = select_route(inp, snap)
    assert route is not None


# ---------------------------------------------------------------------------
# select_k_routes: an over-budget A→B raises on the FIRST flavour, not [].
# ---------------------------------------------------------------------------


def test_select_k_routes_raises_on_first_flavour_for_over_budget_end():
    snap = _green_snapshot()
    inp = TourInput(start=PDV, end=FAR_EAST_END, duration_min=30, city_slug="paris")
    # Mirrors RED density: the refusal propagates through the first
    # select_route call, so select_k_routes raises rather than returning [].
    with pytest.raises(TourabilityRefusedError) as excinfo:
        select_k_routes(inp, snap, 3)
    assert excinfo.value.gap_minutes is not None


# ---------------------------------------------------------------------------
# end=None NEVER enters the branch (Step-2.0d invariance baseline holds).
# ---------------------------------------------------------------------------


def test_end_none_never_raises_even_when_corpus_spans_far():
    """A far POI in the corpus must NOT trigger the feasibility refusal when
    there is no fixed end — the branch is guarded on input.end is not None."""
    far_poi = POI(
        id="far-corner",
        name="Far Corner",
        tier=5,
        poi_role="stop",
        lat=FAR_EAST_END[0],
        lng=FAR_EAST_END[1],
        areas=("Le Marais",),
        beat_count=8,
    )
    snap = _snap([*_density_fillers(PDV), far_poi])
    inp = TourInput(start=PDV, duration_min=30, city_slug="paris")  # end=None
    assert inp.end is None
    # No raise: open walk never consults the A→B feasibility branch.
    route = select_route(inp, snap)
    assert route is not None


def test_end_none_and_within_budget_end_produce_routes_no_refusal():
    """Both end=None and an in-budget end return Routes; neither refuses. The
    end=None path must be untouched by the Step 2.2a branch."""
    snap = _green_snapshot()
    open_route = select_route(
        TourInput(start=PDV, duration_min=60, city_slug="paris"), snap
    )
    near_route = select_route(
        TourInput(start=PDV, end=NEAR_END, duration_min=60, city_slug="paris"), snap
    )
    assert open_route is not None
    assert near_route is not None
