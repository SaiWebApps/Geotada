"""Tour-builder routing math.

Constants and pure functions used by selection.py:

- haversine: great-circle distance in metres between (lat, lng) points.
- pace_corrected_walk_seconds: applies the x1.35 Paris haversine correction
  on top of the 3 km/h walking pace.
- envelope_radius_m: the radius around `start` reachable inside the
  err-short walk budget.
- insertion_cost_seconds: best-insertion marginal cost used by the greedy
  selection step (§3.2 marginal_route_cost). Final ordering is exact —
  see src/tour/ordering.py (M4 Held-Karp).
- summarise_route: rolls up an ordered POI list into a Route shell with
  transit segments, walk distance, and walk-time totals.

Constants are exported as module-level so tests can pin them and so
selection.py reads identical values.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .contract import (
    POI,
    BeatRef,
    Route,
    TourabilityAssessment,
    TransitSegment,
    ValhallaLegReceipt,
)

if TYPE_CHECKING:
    # routing_client imports from this module; type-only import avoids the cycle.
    from .routing_client import RoutingClient

# M3: walking seconds for one leg, (from_lat, from_lng, to_lat, to_lng) -> int.
# The default is the pace-corrected haversine; selection builds a memoized
# routed version from a RoutingClient.
LegSecondsFn = Callable[[float, float, float, float], int]

# §3.2 / phase-1-design rule ledger 20-25.
#: How fast a walker is assumed to move. A MEASUREMENT, and a wrong one: people walk
#: about 4.5 km/h, so every leg time this product reports is inflated by about half.
#:
#: RAISED TO 4.5 AND HELD BACK AT 3.0 (owner decision, 2026-08-06). Measured on the
#: 300-minute Rue Royale -> Notre-Dame case, the rise moves the furthest stop off the
#: direct line from 527 m to 2,122 m — Montmartre — and total walking from 4.2 km to
#: 7.6 km. The mechanism is NOT the reach radius, which `REACH_PACE_KMH` below pins
#: successfully; it is the corridor test, which compares `walk(A->p) + walk(p->B)`
#: against a budget in SECONDS, so a faster walker affords a wider detour in the same
#: time. That is arithmetically correct and is the reported bug's shape at a third of
#: its size.
#:
#: The fix is a detour bound measured in METRES rather than minutes, which PLAN.md
#: defers to Release 2 / Phase 5. Until it lands, an honest walking speed buys a
#: dishonest route, so this stays at 3.0 and the separation below is what makes
#: raising it a one-line change when the discipline arrives.
PACE_KMH: float = 3.0
#: HOW FAR TO SEND SOMEONE, which is not the same question as how fast they walk.
#:
#: The same number as `PACE_KMH` today, and NOT the same constant, deliberately. The
#: reach radius is a product choice about how far a tour may range; the pace is a
#: measurement. While they were one constant, raising the pace would have scaled the
#: search region by 1.5x — at a 300-minute request, 4,444 m becomes 6,667 m, and
#: Parc de la Villette sits 5,614 m from Rue Royale, so it would have re-entered the
#: circle Phase 1 shrank to exclude it. Phase 1 undone through a constant that has
#: nothing to do with it.
#:
#: Two equal numbers with one name is a coincidence waiting to be mistaken for a
#: rule. `test_pace_constants_lock` proves the radius does not follow the pace.
REACH_PACE_KMH: float = 3.0
HAVERSINE_CORRECTION: float = 1.35
WALK_FRACTION: float = 0.40  # of err-short total
# Was AUDIO_FRACTION until 2026-08-06. The split is between WALKING and STANDING
# STILL, and the standing-still half is not narration: Camille stands twenty
# minutes at Concorde for four minutes of audio. Naming this half "audio" made the
# planner budget in narration seconds while the tourist spent visit seconds, so a
# 120-minute request served 157 minutes and reported 120. See src/tour/visit_time.py.
DWELL_FRACTION: float = 0.60  # of err-short total
EARTH_RADIUS_M: float = 6_371_000.0
MIN_REQUESTED_FRACTION: float = 0.90
MAX_REQUESTED_FRACTION: float = 1.10
# Customer durations are selected in whole minutes.  Final ordering/demotion can
# move a route by a few rounded seconds after the exact bounded repair.  A route
# within one displayed minute of the frozen band is materially in the same
# customer timebox; larger misses remain infeasible.
TIMEBOX_MATERIALITY_TOLERANCE_SECONDS: int = 60


@dataclass(frozen=True)
class RoutePlanningPolicy:
    """One immutable time currency for every route-selection phase.

    There is exactly ONE band since 2026-08-04: certification's 0.90-1.10, nominal
    1.00 (``DEFAULT_ROUTE_PLANNING_POLICY``). The flat 0.83 "err-short" policy that
    used to be the default was DELETED, not made optional, because two currencies
    meant the same request produced tours of different declared length depending on
    which surface asked. A certification caller still constructs its policy from its
    already-frozen contract and provider-call authorization; selection deliberately
    does not import or duplicate those authorities.
    """

    policy_id: str
    minimum_requested_fraction: float
    maximum_requested_fraction: float

    def __post_init__(self) -> None:
        values = (self.minimum_requested_fraction, self.maximum_requested_fraction)
        if not all(math.isfinite(value) and value > 0 for value in values):
            raise ValueError("planning fractions must be finite and positive")
        if self.minimum_requested_fraction > self.maximum_requested_fraction:
            raise ValueError("minimum planning fraction exceeds maximum")

    @property
    def nominal_requested_fraction(self) -> float:
        return (
            self.minimum_requested_fraction + self.maximum_requested_fraction
        ) / 2.0

    @classmethod
    def certification(
        cls,
        *,
        minimum_requested_fraction: float,
        maximum_requested_fraction: float,
        policy_id: str,
    ) -> RoutePlanningPolicy:
        """Build from the frozen TIME band. Duration is the only stop bound."""

        if not policy_id:
            raise ValueError("certification planning requires its frozen policy id")
        return cls(
            policy_id=policy_id,
            minimum_requested_fraction=minimum_requested_fraction,
            maximum_requested_fraction=maximum_requested_fraction,
        )


@dataclass(frozen=True)
class RoutePlanningBudget:
    """Duration-specific values derived once from a planning policy."""

    minimum_elapsed_seconds: int
    nominal_elapsed_seconds: int
    maximum_elapsed_seconds: int
    walk_envelope_minutes: float
    walk_budget_seconds: int
    #: Seconds the tour aims to spend NOT walking — standing at places, going
    #: inside them, listening. Narration is one thing that happens inside this
    #: budget, never the budget itself.
    dwell_target_seconds: int


#: THE planning policy. Nominal fraction (0.90 + 1.10) / 2 = exactly 1.00, so a
#: 60-minute request is planned to 60 minutes of active time. It replaced
#: LEGACY_ROUTE_PLANNING_POLICY (flat 0.83) as the default of every helper on
#: 2026-08-04; the legacy object is deleted rather than deprecated so no caller can
#: reach the old currency by omitting an argument.
DEFAULT_ROUTE_PLANNING_POLICY = RoutePlanningPolicy(
    policy_id="certification-nominal-v1",
    minimum_requested_fraction=MIN_REQUESTED_FRACTION,
    maximum_requested_fraction=MAX_REQUESTED_FRACTION,
)


#: Under `wall` the plan aims at this fraction of the asked time, and may not
#: exceed it — the spare minutes are VISIBLE and deliberate, never a hard
#: truncation at the asked number. Marcus's request verbatim: "2h40 of tour
#: with 20 minutes of slack" beats "3h00 exactly"
#: (docs/personas/04-layover-sprinter.md; redesign §2.3 — he currently lies to
#: the product about his end time to manufacture exactly this margin).
WALL_PLANNING_CEILING_FRACTION: float = 0.95


def route_planning_budget(
    duration_min: int,
    policy: RoutePlanningPolicy = DEFAULT_ROUTE_PLANNING_POLICY,
    *,
    end_hardness: str = "firm",
) -> RoutePlanningBudget:
    """THE one home of the request's time arithmetic (redesign §2.3).

    `end_hardness` bends the band without forking it:
    - "firm" (default): byte-identical to the policy's own band — every caller
      that does not thread a hardness plans exactly as before this existed.
    - "open": the minimum-elapsed floor drops to ZERO. The duration was a
      rough intent, so a shorter honest day is never padded toward a number
      nobody defended (Julien; Camille's "is 15:00 a wall or a wish?" —
      design 8.3 finishes the fill-the-requested-time deletion here).
    - "wall": nominal and maximum cap at WALL_PLANNING_CEILING_FRACTION of the
      request, so the plan itself carries visible spare minutes (Marcus).
    """
    requested_seconds = duration_min * 60
    minimum_fraction = policy.minimum_requested_fraction
    nominal_fraction = policy.nominal_requested_fraction
    maximum_fraction = policy.maximum_requested_fraction
    if end_hardness == "open":
        minimum_fraction = 0.0
    elif end_hardness == "wall":
        nominal_fraction = min(nominal_fraction, WALL_PLANNING_CEILING_FRACTION)
        maximum_fraction = min(maximum_fraction, WALL_PLANNING_CEILING_FRACTION)
    return RoutePlanningBudget(
        minimum_elapsed_seconds=round(requested_seconds * minimum_fraction),
        nominal_elapsed_seconds=round(requested_seconds * nominal_fraction),
        maximum_elapsed_seconds=round(requested_seconds * maximum_fraction),
        walk_envelope_minutes=(
            duration_min * nominal_fraction * WALK_FRACTION
        ),
        walk_budget_seconds=round(
            requested_seconds * nominal_fraction * WALK_FRACTION
        ),
        dwell_target_seconds=round(
            requested_seconds * nominal_fraction * DWELL_FRACTION
        ),
    )


def within_planning_timebox(
    elapsed_seconds: int,
    budget: RoutePlanningBudget,
) -> bool:
    """Whether final active time materially fits the whole-minute product band."""

    return (
        budget.minimum_elapsed_seconds - TIMEBOX_MATERIALITY_TOLERANCE_SECONDS
        <= elapsed_seconds
        <= budget.maximum_elapsed_seconds + TIMEBOX_MATERIALITY_TOLERANCE_SECONDS
    )

# DELETED 2026-08-06: DWELL_SECONDS_BY_TIER / compute_dwell_seconds.
#
# A flat per-tier dwell said a stop's length is a property of how FAMOUS a place
# is. It is not: it is what the place absorbs, what this visitor's interest
# justifies, and what the party will sit still for. All three now live in
# src/tour/visit_time.py and ride on Route.planned_visit_seconds.
#
# The table also could not be right. Every tier-5 anchor got the same 300 s,
# which is simultaneously far too little for the Louvre and far too much for a
# bridge, and nothing in it could express Camille and Theo spending 33 and 8
# minutes at the same courtyard.


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in metres."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return EARTH_RADIUS_M * c


def pace_corrected_walk_seconds(
    haversine_distance_m: float, *, pace_multiplier: float = 1.0
) -> int:
    """Walking time in seconds for a haversine straight-line distance.

    Applies the x1.35 correction so that a 1km haversine line takes
    1350m / (3000m/h) ≈ 27 minutes worth of walking.

    `pace_multiplier` (redesign §2.4; plan S2.4) divides the walking speed —
    2.0 = half speed, Nadia's "Pace drops to roughly half"
    (docs/personas/03-family-with-children.md step 4). 1.0 is the identity
    default: byte-identical to every caller before this parameter existed.
    The fast direction (< 1.0) is not this function's job to police — the
    contract field that feeds it (`TourInput.walking_pace`) is the one place
    that rejects it, so a caller handing a bad multiplier straight to this
    function is a caller that bypassed validation, not a case this function
    silently accepts.
    """
    if haversine_distance_m <= 0:
        return 0
    actual_distance_m = haversine_distance_m * HAVERSINE_CORRECTION
    speed_m_per_s = (PACE_KMH * 1000.0) / 3600.0 / pace_multiplier
    return round(actual_distance_m / speed_m_per_s)


def envelope_radius_m(
    duration_min: int,
    *,
    round_trip: bool,
    planning_policy: RoutePlanningPolicy = DEFAULT_ROUTE_PLANNING_POLICY,
    pace_multiplier: float = 1.0,
) -> float:
    """Reachable straight-line radius from the origin under the planning budget.

    Derivation: walk_min = duration x the policy's nominal fraction x WALK_FRACTION
    (0.40). Effective straight-line distance is walk_min x REACH_PACE_KMH / 1.35.
    Halve for round trips. At the default policy the nominal fraction is 1.00, so a
    60-minute one-way request reaches 888.9 m; it was 737.8 m under the deleted flat
    0.83.

    USES `REACH_PACE_KMH`, NOT `PACE_KMH`, and the two are different numbers on
    purpose — see the constant. This radius is how far a tour may range, and it must
    not move because people were re-measured as walking faster.

    `pace_multiplier` (redesign §2.4; plan S2.4) SHRINKS the circle — a slow
    party covers less ground in the same walking budget, so they are offered a
    smaller world, never the same one at a pace they cannot keep. 1.0 is the
    identity default. Density's own `assess` call (src/tour/density.py) and
    the planner's `select_route` (via `reach_envelope_searched`) both read
    this from the SAME `TourInput.walking_pace` field, so the tourability
    gate and the planner never disagree about how far this party can walk.
    """
    if duration_min <= 0:
        return 0.0
    walk_min = route_planning_budget(
        duration_min, planning_policy
    ).walk_envelope_minutes
    straight_m = (
        (walk_min * REACH_PACE_KMH * 1000.0) / 60.0 / HAVERSINE_CORRECTION / pace_multiplier
    )
    return straight_m / 2.0 if round_trip else straight_m


def planned_total_seconds(
    duration_min: int,
    policy: RoutePlanningPolicy = DEFAULT_ROUTE_PLANNING_POLICY,
) -> int:
    """Total active seconds the planner aims at.

    Was ``err_short_total_seconds``; renamed because it is no longer err-SHORT — the
    nominal fraction is 1.00. It now DELEGATES to the budget rather than restating an
    arithmetic of its own, so no caller can obtain a fraction the policy does not have.
    """
    return route_planning_budget(duration_min, policy).nominal_elapsed_seconds


def target_dwell_seconds(
    duration_min: int,
    policy: RoutePlanningPolicy = DEFAULT_ROUTE_PLANNING_POLICY,
) -> int:
    """Seconds this tour aims to spend standing still, at places.

    Was ``target_audio_seconds``. The number never changed; what it is a budget
    FOR did. It bounds time at stops, of which narration is a part.
    """
    return route_planning_budget(duration_min, policy).dwell_target_seconds


def governor_allowance_seconds(
    duration_min: int,
    policy: RoutePlanningPolicy = DEFAULT_ROUTE_PLANNING_POLICY,
) -> int:
    """Per-stop audio allowance for the C9 share-governor (ratified 2026-07-03).

    An INCIDENTAL stop's emitted narration is capped to this many voiced
    seconds; the ordered overflow beats become the keep-exploring extras. The
    start-anchor and the fixed-end-B / pulled endpoint are EXEMPT (no cap).

    = ``target_dwell_seconds(d) // min(3, d // 10)`` — i.e. budget / 3 for
    d>=30 (~5 min @30min, ~15 min @90min): an incidental may speak for up to
    ~1/3 of the tour's standing-still time. The divisor floors at 1 so very
    short tours (which seat ~1 stop) impose no cap.

    THIS IS STILL AN AUDIO CAP and deliberately so: it bounds how long one
    ordinary stop may TALK. What moved under it is the base it takes a share
    of, which is now the whole standing-still budget rather than a budget that
    pretended narration was the only way to spend it. The number is unchanged
    at every duration, because the two budgets were always the same seconds.
    """
    return target_dwell_seconds(duration_min, policy) // max(1, min(3, duration_min // 10))


def walk_budget_seconds(
    duration_min: int,
    policy: RoutePlanningPolicy = DEFAULT_ROUTE_PLANNING_POLICY,
) -> int:
    return route_planning_budget(duration_min, policy).walk_budget_seconds


def beat_spoken_seconds(beat: BeatRef) -> int:
    """Voiced seconds for one beat — the single source of truth for the tour's
    audio clock.

    ``est_spoken_seconds`` when populated (> 0), else ``word_count`` at 150 wpm.
    Generation, reflection, and density all defer here so selection's dwell/audio
    accounting and the density gate speak in the same units. A non-positive
    ``est_spoken_seconds`` falls through to ``word_count`` (the live corpus has
    none; the ``> 0`` guard matches density's historical rule). The 150 wpm
    fallback is exactly density's ``word_count / 2.5`` (both are ``2·wc/5``).
    """
    if beat.est_spoken_seconds and beat.est_spoken_seconds > 0:
        return int(beat.est_spoken_seconds)
    if beat.word_count and beat.word_count > 0:
        return round(beat.word_count / 150 * 60)
    return 0


def planned_audio_seconds(beats: Iterable[BeatRef]) -> int:
    """Total voiced seconds a beat plan would speak (glue/vignette one-liners
    excluded — selection never sees those). Sums :func:`beat_spoken_seconds`.
    """
    return sum(beat_spoken_seconds(b) for b in beats)


def leg_walk_seconds(transit: TransitSegment) -> int:
    """How long ONE leg's walking takes — THE ONE EXPRESSION, per leg.

    PROVENANCE decides, not nullness. A leg carries a routed duration only when
    Valhalla produced it; a client that answered with seconds but no shape did
    not route that leg, and its number must not outrank the honest fallback the
    leg already carries.

    Four sites spelled this independently until 2026-08-06 — the route total,
    the served clock, the announced leg in generation, and reflection's per-leg
    walk — and three of the four asked whether ``leg_seconds`` was set. They
    agreed only because the client's fallback and ``_transit`` both compute
    ``pace_corrected_walk_seconds`` of the same haversine distance, so the two
    readings land on the same number by coincidence rather than by construction.
    """
    return int(
        transit.leg_seconds
        if transit.source == "valhalla" and transit.leg_seconds is not None
        else transit.walk_seconds
    )


def total_walk_seconds(transits: Iterable[TransitSegment]) -> int:
    """How long a route's walking takes — THE ONE EXPRESSION.

    Two spellings of this existed until 2026-08-06, and they were different
    expressions rather than different formattings: ``summarise_route`` branched on
    ``source == "valhalla"`` and the served clock in options.py branched on
    ``leg_seconds is not None``. They agreed numerically only by coincidence — a
    leg carrying a non-None ``leg_seconds`` with ``source == "haversine"`` lands on
    the same number solely because the routing client's fallback and ``_transit``
    both compute ``pace_corrected_walk_seconds`` of the same haversine distance.
    Any injected client, or a client that degrades mid-route, breaks the
    coincidence, and then the planned tour and the served tour disagree about how
    far the traveller walked.

    Provenance, not nullness, decides: a leg is routed when Valhalla said so.
    """
    return sum(leg_walk_seconds(t) for t in transits)


def default_leg_seconds(lat1: float, lng1: float, lat2: float, lng2: float) -> int:
    """The haversine LegSecondsFn — the M3 routed divisor's fallback."""
    return pace_corrected_walk_seconds(haversine_m(lat1, lng1, lat2, lng2))


def insertion_extra_at_index(
    candidate: POI,
    ordered: list[POI],
    idx: int,
    *,
    start_lat: float,
    start_lng: float,
    round_trip: bool,
    leg_seconds_fn: LegSecondsFn | None = None,
    fixed_end: tuple[float, float] | None = None,
) -> int:
    """Walk-time delta from inserting `candidate` at exactly position `idx`.

    THE one single-index insertion-cost computation (dedup-review 2026-08-07):
    ``insertion_cost_seconds``'s per-position loop below and every single-index
    recompute in selection.py (the one-way pull-clamp case, and the pinned
    A→selected→B chain) independently rebuilt this same splice-and-diff before
    this consolidation. This is now the one definition all three call.
    """
    base_coords: list[tuple[float, float]] = [
        (start_lat, start_lng), *((p.lat, p.lng) for p in ordered)
    ]
    if fixed_end is not None:
        base_coords.append(fixed_end)
    elif round_trip:
        base_coords.append((start_lat, start_lng))
    base = path_walk_seconds(base_coords, leg_seconds_fn)

    new_pois = [*ordered[:idx], candidate, *ordered[idx:]]
    new_coords: list[tuple[float, float]] = [
        (start_lat, start_lng), *((p.lat, p.lng) for p in new_pois)
    ]
    if fixed_end is not None:
        new_coords.append(fixed_end)
    elif round_trip:
        new_coords.append((start_lat, start_lng))
    return path_walk_seconds(new_coords, leg_seconds_fn) - base


def insertion_cost_seconds(
    candidate: POI,
    ordered: list[POI],
    *,
    start_lat: float,
    start_lng: float,
    round_trip: bool,
    leg_seconds_fn: LegSecondsFn | None = None,
) -> tuple[int, int]:
    """Return (best_extra_walk_seconds, best_insertion_index) for a candidate.

    Considers every position in the existing ordered list (start → … → end).
    For round-trip routes the path returns to the origin, so the closing leg
    is part of every cost evaluation.

    Used by routing-aware greedy selection (§3.2). M3: ``leg_seconds_fn``
    supplies routed leg times (the §3 divisor); default is haversine.
    """
    best_extra: int | None = None
    best_idx: int = 0

    # Insertion positions: after each existing waypoint (including start),
    # but never after the closing-return-to-origin segment.
    insertable_positions = len(ordered) + 1
    for idx in range(insertable_positions):
        extra = insertion_extra_at_index(
            candidate,
            ordered,
            idx,
            start_lat=start_lat,
            start_lng=start_lng,
            round_trip=round_trip,
            leg_seconds_fn=leg_seconds_fn,
        )
        if best_extra is None or extra < best_extra:
            best_extra = extra
            best_idx = idx

    return (best_extra if best_extra is not None else 0, best_idx)


def path_walk_seconds(
    coords: list[tuple[float, float]], leg_seconds_fn: LegSecondsFn | None = None
) -> int:
    """How long is it to walk this chain of points? THE ONE SUM.

    Every route measurement in the planner is this: build a list of coordinates
    — start, the stops in order, sometimes a fixed end or a return to the start —
    and add up the legs between them.

    THAT SUM WAS WRITTEN FIVE TIMES until 2026-08-06: here, in the greedy's
    insertion cost twice, and in two route-total helpers. All five paired the same
    way and defaulted to the same estimator, so what varied was only how the coords
    list was BUILT — which is the part that genuinely differs per caller and the
    part they should each keep. Swapping the estimator, or handling a leg the
    router cannot answer, is one edit here rather than five.
    """
    return sum(path_leg_seconds(coords, leg_seconds_fn))


def path_leg_seconds(
    coords: list[tuple[float, float]], leg_seconds_fn: LegSecondsFn | None = None
) -> list[int]:
    """Each leg of this chain, separately.

    ``path_walk_seconds`` is the sum of this. They are one function split in two
    because a route's TOTAL walk and its LONGEST single walk are different
    questions with different answers, and both are needed: a walking budget is not
    one number. Rosemary's 54-minute total is unremarkable while her twelve-minute
    per-leg limit is the binding constraint, so "a route with one 25-minute leg and
    one 5-minute leg has the same total and is unusable"
    (``docs/personas/05-step-free-visitor.md``).
    """
    fn = leg_seconds_fn or default_leg_seconds
    return [
        fn(lat1, lng1, lat2, lng2)
        for (lat1, lng1), (lat2, lng2) in itertools.pairwise(coords)
    ]


def _transit(
    from_id: str | None,
    to_id: str | None,
    from_lat: float,
    from_lng: float,
    to_lat: float,
    to_lng: float,
    routing_client: RoutingClient | None,
    *,
    costing_options_override: dict | None = None,
) -> TransitSegment:
    """Build one leg while retaining planning and routed measurements.

    ``costing_options_override`` (plan S2.7) carries the route-surface axis's
    Valhalla costing when set — ``None`` is today's request, byte-identical.
    """
    d = haversine_m(from_lat, from_lng, to_lat, to_lng)
    secs = pace_corrected_walk_seconds(d)
    leg_seconds: int | None = None
    leg_distance_m: float | None = None
    polyline: str | None = None
    receipt: ValhallaLegReceipt | None = None
    source = "haversine"
    if routing_client is not None:
        route_with_receipt = getattr(routing_client, "route_with_receipt", None)
        if callable(route_with_receipt):
            leg_seconds, routed_m, polyline, receipt = route_with_receipt(
                from_lat,
                from_lng,
                to_lat,
                to_lng,
                costing_options_override=costing_options_override,
            )
        else:
            # Explicit route-only compatibility for injected legacy clients.
            leg_seconds, routed_m, polyline = routing_client.route(
                from_lat, from_lng, to_lat, to_lng
            )
        source = "valhalla" if polyline is not None else "haversine"
        if source == "valhalla":
            leg_distance_m = routed_m
    return TransitSegment(
        from_poi_id=from_id,
        to_poi_id=to_id,
        distance_m=d,
        walk_seconds=secs,
        leg_seconds=leg_seconds,
        leg_distance_m=leg_distance_m,
        polyline=polyline,
        source=source,
        valhalla_receipt=receipt,
    )


def summarise_route(
    pois: Iterable[POI],
    *,
    start_lat: float,
    start_lng: float,
    round_trip: bool,
    duration_min: int,
    spine_area: str | None,
    routing_client: RoutingClient | None = None,
    planning_policy: RoutePlanningPolicy = DEFAULT_ROUTE_PLANNING_POLICY,
    vignettes: dict[int, tuple[POI, ...]] | None = None,
    tourability: TourabilityAssessment | None = None,
    start_anchor_poi_id: str | None = None,
    fixed_end_poi_id: str | None = None,
    planned_visit_seconds: Mapping[str, int] | None = None,
    elapsed_shortfall_seconds: int = 0,
    costing_options_override: dict | None = None,
) -> Route:
    """Build a Route from an ordered POI list.

    Selection already scores with routed leg seconds when a routing client is
    available. The final Route therefore reports those same road-network times
    and distances; haversine remains the explicit fallback when routing degrades.

    ``costing_options_override`` (plan S2.7) carries the route-surface axis's
    Valhalla costing to every leg this route contains, so the shipped route's
    times and shapes are the SAME step-avoiding request selection priced —
    never a route selected under one costing and reported under another.
    ``None`` (the default) is today's request, byte-identical.

    The six keyword extras exist so a caller REBUILDING a route it has already
    decided on can hand back the parts this function cannot recompute — the
    walk-past sights, the thin-area disclosure, which stops were the marquee ones,
    how long this visitor spends at each, and how far short of the request the
    tour honestly runs. Their defaults are exactly what an ordinary caller got
    before they existed, so nothing changes for anyone who omits them.

    Building the route right ONCE is the point. The alternative, which this
    replaces, was to build it wrong and then patch each piece back on afterwards
    with a copy-and-update per piece — four chances for the rebuilt tour to
    quietly stop being the tour the traveller chose.

    ``planned_visit_seconds`` is the newest of them and the one that cannot be
    recomputed at all: it is priced against a CorpusSnapshot and this function
    has none. A rebuild that omits it silently collapses every stop to the length
    of its own narration.
    """
    ordered = tuple(pois)
    transits: list[TransitSegment] = []
    prev_lat, prev_lng = start_lat, start_lng
    prev_id: str | None = None
    total_distance = 0.0

    for poi in ordered:
        seg = _transit(
            prev_id,
            poi.id,
            prev_lat,
            prev_lng,
            poi.lat,
            poi.lng,
            routing_client,
            costing_options_override=costing_options_override,
        )
        transits.append(seg)
        total_distance += (
            seg.leg_distance_m if seg.source == "valhalla" else seg.distance_m
        )
        prev_lat, prev_lng = poi.lat, poi.lng
        prev_id = poi.id

    if round_trip and ordered:
        seg = _transit(
            prev_id,
            None,
            prev_lat,
            prev_lng,
            start_lat,
            start_lng,
            routing_client,
            costing_options_override=costing_options_override,
        )
        transits.append(seg)
        total_distance += (
            seg.leg_distance_m if seg.source == "valhalla" else seg.distance_m
        )

    walk_seconds = total_walk_seconds(transits)
    budget = route_planning_budget(duration_min, planning_policy)
    return Route(
        pois=ordered,
        transits=tuple(transits),
        total_walk_distance_m=total_distance,
        total_walk_seconds=walk_seconds,
        spine_area=spine_area,
        target_dwell_seconds=budget.dwell_target_seconds,
        err_short_total_seconds=budget.nominal_elapsed_seconds,
        routed=bool(transits) and all(t.source == "valhalla" for t in transits),
        vignettes=vignettes if vignettes is not None else {},
        tourability=tourability,
        start_anchor_poi_id=start_anchor_poi_id,
        fixed_end_poi_id=fixed_end_poi_id,
        planned_visit_seconds=(
            planned_visit_seconds if planned_visit_seconds is not None else {}
        ),
        elapsed_shortfall_seconds=elapsed_shortfall_seconds,
    )
