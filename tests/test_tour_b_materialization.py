"""Step 2.4 — fixed-destination B-materialization (HYBRID) fed to ORDER.

When a tour carries a fixed end B and the routed A→B leg fits the walk budget
(so Step 2.2a does NOT refuse), ``select_route`` must pin a concrete POI as the
LAST ordered stop:

  - SNAP: if a selected (already in-corridor) POI sits within ~150m of B, the
    route's last stop is that real POI.
  - SYNTHESIZE: otherwise a sentinel POI at B's *exact* coordinate is added to
    the selected set and pinned last.

The ``end=None`` paths (open walk + round trip) must be LITERALLY unchanged —
the Step-2.0d ordered-id identity baseline (in test_tour_selection.py) still
guards that, and this module re-asserts the open-walk end and round-trip end
behaviour directly.

These are REAL ``select_route`` runs over synthetic corpora — the cost function
is never mocked. Expectations are derived from the live functions
(haversine_m, default_leg_seconds, walk_budget_seconds) so a test fails only if
the BEHAVIOUR is wrong, never against a hardcoded leg time.
"""

from __future__ import annotations

from src.tour.contract import POI, BeatRef, TourInput
from src.tour.routing import (
    default_leg_seconds,
    haversine_m,
    pace_corrected_walk_seconds,
    walk_budget_seconds,
)
from src.tour.selection import (
    B_SNAP_PROXIMITY_M,
    CorpusSnapshot,
    select_route,
)

PDV = (48.8555, 2.3656)


# ---------------------------------------------------------------------------
# Fixtures (mirroring the established feasibility-test helpers).
# ---------------------------------------------------------------------------


def _density_fillers(start: tuple[float, float]) -> list[POI]:
    """4 tier-5 anchor candidates clustered AT start.

    The Phase 6 density gate needs ≥4 rich-beat anchor candidates in a tight
    cluster to clear (avoid RED). They sit right on top of A so they are
    trivially inside the A→…→B corridor and never become the far endpoint.
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


def _anchor(poi_id: str, dlat: float, dlng: float, *, tier: int = 5, beats: int = 8) -> POI:
    """A tier-≥3 'stop' anchor offset (dlat, dlng) degrees from PdV."""
    return POI(
        id=poi_id,
        name=poi_id,
        tier=tier,
        poi_role="stop",
        lat=PDV[0] + dlat,
        lng=PDV[1] + dlng,
        areas=("Le Marais",),
        beat_count=beats,
    )


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


class _DeterministicRoutingClient:
    """Hermetic fake: routed leg times equal int(pace-corrected haversine).

    Mirrors the Step-2.0d baseline client. isochrone() returns None so REACH
    falls back to the analytic envelope; route() returns a None polyline.
    """

    def leg_seconds(self, from_lat: float, from_lng: float, to_lat: float, to_lng: float) -> int:
        return int(pace_corrected_walk_seconds(haversine_m(from_lat, from_lng, to_lat, to_lng)))

    def route(
        self, from_lat: float, from_lng: float, to_lat: float, to_lng: float
    ) -> tuple[int, float, None]:
        d = haversine_m(from_lat, from_lng, to_lat, to_lng)
        return (int(pace_corrected_walk_seconds(d)), d, None)

    def isochrone(self, lat: float, lng: float, minutes: int) -> None:
        return None

    def close(self) -> None:
        return None


# A duration whose walk budget comfortably covers a short east A→B leg, so the
# Step 2.2a feasibility refusal does NOT fire and the route reaches ORDER.
DURATION = 90


def _ab_in_budget(end: tuple[float, float], duration_min: int = DURATION) -> bool:
    """Live: does the routed A→B leg fit inside the walk budget (no 2.2a refusal)?"""
    return default_leg_seconds(PDV[0], PDV[1], end[0], end[1]) <= walk_budget_seconds(duration_min)


def _assert_not_red(inp: TourInput, snap: CorpusSnapshot) -> None:
    from src.tour.density import assess as assess_tourability

    assert assess_tourability(inp, snap.pois, snap.beats_by_poi).status != "RED"


# ---------------------------------------------------------------------------
# SNAP: B within ~150m of a selected in-corridor POI → last stop is that POI.
# ---------------------------------------------------------------------------


def test_fixed_end_snaps_to_nearby_selected_poi():
    """B placed within ~150m of a real selected anchor: the route's last stop
    is that anchor's id (no sentinel synthesized)."""
    # A real east anchor that is well inside the corridor and budget.
    east = _anchor("east-real", 0.0, 0.0040, tier=5, beats=12)  # ~290m east of PdV
    snap = _snap([east, *_density_fillers(PDV)])

    # B is ~30m east of the real anchor — comfortably inside B_SNAP_PROXIMITY_M.
    end = (east.lat, east.lng + 0.0004)
    snap_dist = haversine_m(end[0], end[1], east.lat, east.lng)
    assert 0.0 < snap_dist <= B_SNAP_PROXIMITY_M  # precondition, live distance

    inp = TourInput(start=PDV, end=end, duration_min=DURATION, city_slug="paris")
    assert _ab_in_budget(end)  # 2.2a does not refuse
    _assert_not_red(inp, snap)

    route = select_route(inp, snap)
    ids = tuple(p.id for p in route.pois)
    assert ids, "fixed-end route should not be empty"
    # SNAP: last stop is the real anchor; no synthesized sentinel anywhere.
    assert ids[-1] == east.id
    assert not any(p.id.startswith("__end_b__") for p in route.pois)
    assert end not in {(p.lat, p.lng) for p in route.pois}  # exact B coord NOT added


def test_fixed_end_snaps_to_nearest_of_two_in_range_pois():
    """When two selected POIs are within ~150m of B, the route ends at the
    geometrically NEAREST one (derived live from haversine_m)."""
    near = _anchor("snap-near", 0.0, 0.0040, tier=5, beats=10)
    farther = _anchor("snap-far", 0.0, 0.0046, tier=5, beats=10)
    snap = _snap([near, farther, *_density_fillers(PDV)])

    # B sits between them but closer to `near`.
    end = (near.lat, near.lng + 0.0002)
    d_near = haversine_m(end[0], end[1], near.lat, near.lng)
    d_far = haversine_m(end[0], end[1], farther.lat, farther.lng)
    assert d_near < d_far <= B_SNAP_PROXIMITY_M  # both in range; near is closer

    inp = TourInput(start=PDV, end=end, duration_min=DURATION, city_slug="paris")
    assert _ab_in_budget(end)
    _assert_not_red(inp, snap)

    route = select_route(inp, snap)
    ids = tuple(p.id for p in route.pois)
    assert near.id in ids and farther.id in ids  # both got selected
    assert ids[-1] == near.id  # nearest wins the snap


# ---------------------------------------------------------------------------
# SYNTHESIZE: B far from every selected POI → sentinel at exact B coord, last.
# ---------------------------------------------------------------------------


def test_fixed_end_synthesizes_sentinel_when_b_is_far_from_every_poi():
    """B with no selected POI within ~150m: a sentinel POI is synthesized at
    B's EXACT coordinate and pinned as the last stop."""
    # An east anchor that is in-corridor but a clear, > ~150m gap from B, so B
    # cannot snap onto it.
    east = _anchor("east-real", 0.0, 0.0040, tier=5, beats=12)
    snap = _snap([east, *_density_fillers(PDV)])

    # B is ~440m further east than the real anchor — beyond the snap radius of
    # every selected POI, but A→B still fits the 90-min budget.
    end = (east.lat, east.lng + 0.0060)
    inp = TourInput(start=PDV, end=end, duration_min=DURATION, city_slug="paris")
    assert _ab_in_budget(end)
    _assert_not_red(inp, snap)

    route = select_route(inp, snap)
    ids = tuple(p.id for p in route.pois)
    assert ids, "fixed-end route should not be empty"

    last = route.pois[-1]
    # The last stop is the synthesized sentinel AT B's exact coordinate.
    assert last.id.startswith("__end_b__")
    assert (last.lat, last.lng) == end
    assert last.poi_role == "stop"
    # Every nearest selected POI was genuinely farther than the snap radius,
    # proving synthesis (not snap) was the correct branch — live distances.
    for poi in route.pois:
        if poi is last:
            continue
        assert haversine_m(end[0], end[1], poi.lat, poi.lng) > B_SNAP_PROXIMITY_M


def test_sentinel_route_ends_at_b_on_routed_cost_path_too():
    """Synthesis + endpoint pinning holds on the deterministic routed cost
    path, not only the no-client haversine path."""
    east = _anchor("east-real", 0.0, 0.0040, tier=5, beats=12)
    snap = _snap([east, *_density_fillers(PDV)])
    end = (east.lat, east.lng + 0.0060)
    inp = TourInput(start=PDV, end=end, duration_min=DURATION, city_slug="paris")
    assert _ab_in_budget(end)
    _assert_not_red(inp, snap)

    route = select_route(inp, snap, routing_client=_DeterministicRoutingClient())
    last = route.pois[-1]
    assert last.id.startswith("__end_b__")
    assert (last.lat, last.lng) == end


# ---------------------------------------------------------------------------
# end=None invariance: open walk and round trip are LITERALLY unchanged.
# ---------------------------------------------------------------------------


def test_open_walk_end_none_still_ends_at_far_far_anchor():
    """end=None open walk: ORDER still ends at the far anchor (no B-materialize
    branch runs). The endpoint-pull-derived fixed_end path is untouched."""
    far = _anchor("far-east", 0.0, 0.0090, tier=5, beats=30)  # far envelope, rich
    snap = _snap([far, *_density_fillers(PDV)])
    inp = TourInput(start=PDV, duration_min=DURATION, city_slug="paris")  # end=None

    route = select_route(inp, snap)
    ids = tuple(p.id for p in route.pois)
    assert far.id in ids
    assert ids[-1] == far.id  # endpoint-pull pins the far anchor last
    assert not any(p.id.startswith("__end_b__") for p in route.pois)  # no sentinel


def test_round_trip_still_returns_to_start():
    """round_trip=True (end is None): ORDER optimizes a closed tour, the last
    transit returns to A, and no B sentinel is ever synthesized."""
    far = _anchor("far-east", 0.0, 0.0050, tier=5, beats=20)
    snap = _snap([far, *_density_fillers(PDV)])
    inp = TourInput(start=PDV, duration_min=DURATION, city_slug="paris", round_trip=True)

    route = select_route(inp, snap)
    assert route.pois, "round-trip route should not be empty"
    assert not any(p.id.startswith("__end_b__") for p in route.pois)  # no sentinel
    # round_trip closes the loop: the final transit goes back to start (to_poi None).
    assert route.transits[-1].to_poi_id is None


# ---------------------------------------------------------------------------
# 2026-07-03 — single-stop regression class guards on the fixed-end (A→B) path.
#
# The end != None pipeline composes the corridor gate, the endpoint pull
# (which still runs BEFORE B-materialization supersedes its fixed_end), the
# fill pass and _materialize_fixed_end_b in an order nothing else tests.
# Universal invariant for every fixture below: a delivered route has >= 2
# beat-bearing stops OR carries a non-None tourability disclosure.
# ---------------------------------------------------------------------------


def test_fixed_end_corridor_rich_route_keeps_multiple_beat_bearing_stops():
    """A rich on-corridor A→B pool must deliver multiple beat-bearing stops.

    The corridor gate (t(A,poi) + t(poi,B) <= walk_budget) is the newest
    pool-shrinking filter; an over-tight gate (comparing against the greedy
    walk budget instead of the full budget, or a haversine/routed mixup)
    empties the pool down to one anchor and delivers a 1-story A→B tour with
    NO warning (the fixture is GREEN). Engine walk-through at HEAD: the
    greedy (one-way budget 1344s of 1793s) seats all 7 candidates (~736s
    chain) and ends by POOL EXHAUSTION at 2100s dwell-audio — the audio
    break (target 2689s) never fires; the fill pass DOES run (2100 < 0.8 x
    2689 = 2151) but no-ops on the empty pool; the endpoint pull finds no
    far candidate (far floor ~553m > east-3's ~439m); B then SNAPs onto
    east-3 (~15m away).
    """
    from src.tour.routing import envelope_radius_m

    east1 = _anchor("east-1", 0.0, 0.0020, tier=5, beats=8)  # ~146m east
    east2 = _anchor("east-2", 0.0, 0.0040, tier=5, beats=8)  # ~293m east
    east3 = _anchor("east-3", 0.0, 0.0060, tier=5, beats=8)  # ~439m east
    snap = _snap([east1, east2, east3, *_density_fillers(PDV)])
    end = (PDV[0], PDV[1] + 0.0062)  # ~15m past east-3 — inside the snap radius

    inp = TourInput(start=PDV, end=end, duration_min=DURATION, city_slug="paris")

    # Preconditions, derived live (module house style).
    assert _ab_in_budget(end)  # no Step-2.2a refusal
    assert haversine_m(*end, east3.lat, east3.lng) <= B_SNAP_PROXIMITY_M  # SNAP branch
    budget = walk_budget_seconds(DURATION)
    for poi in (east1, east2, east3, *_density_fillers(PDV)):
        detour = default_leg_seconds(PDV[0], PDV[1], poi.lat, poi.lng) + default_leg_seconds(
            poi.lat, poi.lng, *end
        )
        assert detour <= budget, f"corridor must admit {poi.id}: {detour}s > {budget}s"
    # No far candidate for the pull: everything sits inside the far floor.
    far_floor = 0.5 * envelope_radius_m(DURATION, round_trip=False)
    assert haversine_m(PDV[0], PDV[1], east3.lat, east3.lng) < far_floor
    _assert_not_red(inp, snap)

    route = select_route(inp, snap)
    ids = [p.id for p in route.pois]

    assert ids[-1] == east3.id, f"route must literally end at B's snap; got {ids}"
    beatful = [p for p in route.pois if snap.beats_for(p.id)]
    assert len(beatful) >= 2, f"1-story A→B delivery: beat-bearing stops = {ids}"
    assert not any(p.id.startswith("__end_b__") for p in route.pois)
    # GREEN fixture: a thin delivery here would be SILENT — exactly the
    # guarded class.
    assert route.tourability is None
    assert len(beatful) >= 2 or route.tourability is not None


def test_fixed_end_far_mountain_does_not_evict_greedy_cluster():
    """The pull's no-collapse guard, exercised under end != None for the first time.

    The pull still runs before B-materialization supersedes its fixed_end
    (selection.py: pull, then the end-is-not-None branch reassigns
    ``fixed_end``). Opposite-side eviction geometry is corridor-impossible
    under a fixed end (the ellipse rejects it), so eviction pressure needs
    OFF-AXIS incumbents: two north anchors the greedy seats, one on-axis
    39-beat far mountain the pull tries. Every trial order busts the walk
    budget by a few seconds, the drops run down to the LAST incumbent, and
    the guard (len(incumbents) <= 1 -> abandon) is the only thing standing
    between the user and a [far-mountain, sentinel] 1-story GREEN tour.

    A refactor that moves B-materialization BEFORE the pull, raises
    ENDPOINT_PULL_MAX_DROPS, or exempts fixed-end routes from the
    last-incumbent guard delivers exactly that collapse and fails here.
    The eviction geometry is margin-sensitive (~1502s trial vs 1494s
    budget), so EVERY premise is asserted live below — drift becomes a loud
    precondition failure, never a vacuous pass.
    """
    from src.tour.density import assess as assess_tourability
    from src.tour.routing import envelope_radius_m
    from src.tour.selection import ENDPOINT_PULL_FAR_FRACTION

    duration = 75  # walk budget 1494s, greedy 1120s, envelope ~922m, far floor ~461m
    n1 = _anchor("n-1", 0.0018, 0.0, tier=5, beats=6)  # ~200m north
    n2 = _anchor("n-2", 0.0027, 0.0, tier=5, beats=6)  # ~300m north
    mountain = _anchor("far-mountain", 0.0, 0.00753, tier=5, beats=39)  # ~551m east
    decoys = [
        _anchor("decoy-w", 0.0, -0.0082, tier=3, beats=3),  # ~600m west
        _anchor("decoy-nw", 0.0038, -0.0058, tier=3, beats=3),
        _anchor("decoy-sw", -0.0038, -0.0058, tier=3, beats=3),
    ]
    snap = _snap([n1, n2, mountain, *decoys])
    end = (PDV[0], PDV[1] + 0.00685)  # ~500m due east
    budget = walk_budget_seconds(duration)

    def leg(a, b) -> int:
        return default_leg_seconds(a[0], a[1], b[0], b[1])

    a = PDV
    p_n1, p_n2, p_mtn = (n1.lat, n1.lng), (n2.lat, n2.lng), (mountain.lat, mountain.lng)

    # (a) A→B fits the budget — no Step-2.2a refusal.
    assert _ab_in_budget(end, duration)
    # (b) The corridor admits n-1 / n-2 / mountain and REJECTS all three
    # decoys — the decoys pad the density gate (6 anchors) without ever
    # entering the greedy pool. They are dwell-band material (gravity(3) =
    # 3.0 == the SHORT floor), so the corridor gate genuinely is what
    # excludes them.
    for poi in (n1, n2, mountain):
        detour = leg(a, (poi.lat, poi.lng)) + leg((poi.lat, poi.lng), end)
        assert detour <= budget, f"corridor must admit {poi.id}: {detour}s"
    for poi in decoys:
        detour = leg(a, (poi.lat, poi.lng)) + leg((poi.lat, poi.lng), end)
        assert detour > budget, f"corridor must reject {poi.id}: {detour}s"
        # ... while the envelope still counts them for density.
        assert haversine_m(*a, poi.lat, poi.lng) <= envelope_radius_m(
            duration, round_trip=False
        )
    # (c) Eviction pressure is real at every drop level the pull explores:
    # both full-incumbent trial orders bust the budget, and so does the
    # post-drop trial (the weakest-drop tie-break removes n-1 first, so the
    # surviving trial is A→n-2→mountain).
    assert leg(a, p_n1) + leg(p_n1, p_n2) + leg(p_n2, p_mtn) > budget
    assert leg(a, p_n2) + leg(p_n2, p_n1) + leg(p_n1, p_mtn) > budget
    assert leg(a, p_n2) + leg(p_n2, p_mtn) > budget
    # (d) The solo collapse WOULD fit — the guard is the only prevention.
    assert leg(a, p_mtn) <= budget
    # (e) The mountain is the pull candidate (past the far floor); the
    # fixture is GREEN so a collapse would be silent.
    far_floor = envelope_radius_m(duration, round_trip=False) * ENDPOINT_PULL_FAR_FRACTION
    assert haversine_m(*a, mountain.lat, mountain.lng) >= far_floor
    inp = TourInput(start=PDV, end=end, duration_min=duration, city_slug="paris")
    assert assess_tourability(inp, snap.pois, snap.beats_by_poi).status == "GREEN"
    # (f) B snaps onto NOTHING (both survivors > 150m away) -> sentinel.
    assert haversine_m(*end, n1.lat, n1.lng) > B_SNAP_PROXIMITY_M
    assert haversine_m(*end, n2.lat, n2.lng) > B_SNAP_PROXIMITY_M

    route = select_route(inp, snap)
    ids = [p.id for p in route.pois]

    assert "n-1" in ids and "n-2" in ids, f"greedy cluster must survive the pull; got {ids}"
    assert "far-mountain" not in ids, f"pull must abandon, not evict; got {ids}"
    assert ids[-1].startswith("__end_b__"), f"route must end at the B sentinel; got {ids}"
    beatful = [p for p in route.pois if snap.beats_for(p.id)]
    assert len(beatful) >= 2
    assert route.tourability is None
    assert len(beatful) >= 2 or route.tourability is not None


def test_sentinel_is_never_the_only_companion_of_a_silent_route():
    """A beatless B sentinel must not masquerade as a second story; the honest
    [one-real-POI, sentinel] delivery must carry the YELLOW disclosure.

    The sentinel (_materialize_fixed_end_b) carries NO beats, so preview
    narration for it is empty — any downstream "route has 2 POIs so it is
    fine" check that counts the sentinel as a companion story reproduces the
    thin single-beat-feeling delivery the user reported. This test makes the
    sentinel's beatlessness load-bearing AND pins that the lone-anchor
    YELLOW contract (test_tour_selection.py's isolated-anchor test) EXTENDS
    to the fixed-end path: the tourability attach happens AFTER
    _materialize_fixed_end_b rebuilds the model, an ordering a refactor of
    the end != None branch could easily break (silently stripping the
    warning from exactly the routes that need it most).
    """
    from src.tour.density import assess as assess_tourability

    duration = 60  # budget 1195s, envelope ~738m, far floor ~369m
    lone = _anchor("lone", 0.0, 0.00205, tier=4, beats=5)  # ~150m east
    snap = _snap([lone])
    end = (PDV[0], PDV[1] + 0.0055)  # ~400m east

    inp = TourInput(start=PDV, end=end, duration_min=duration, city_slug="paris")

    # Preconditions, derived live.
    assert _ab_in_budget(end, duration)  # no 2.2a refusal
    assert haversine_m(*end, lone.lat, lone.lng) > B_SNAP_PROXIMITY_M  # SYNTHESIZE branch
    corridor = default_leg_seconds(PDV[0], PDV[1], lone.lat, lone.lng) + default_leg_seconds(
        lone.lat, lone.lng, *end
    )
    assert corridor <= walk_budget_seconds(duration)  # lone is admitted
    # YELLOW-by-fill: 5 x 240s = 1200s vs target 1793s -> fill ~0.67, one
    # anchor candidate — same arithmetic as the pinned lone-anchor contract.
    assert assess_tourability(inp, snap.pois, snap.beats_by_poi).status == "YELLOW"

    route = select_route(inp, snap)

    # (1) The honest delivery shape: ONE story plus the beatless Destination.
    beatful = [p for p in route.pois if snap.beats_for(p.id)]
    assert len(beatful) == 1 and beatful[0].id == "lone"
    assert route.pois[-1].id.startswith("__end_b__")
    assert not snap.beats_for(route.pois[-1].id), "the B sentinel must carry no beats"
    # (2) The YELLOW disclosure survives B-materialization on the wire model.
    assert route.tourability is not None, (
        "a 1-story fixed-end tour must carry the YELLOW tourability assessment — "
        "without it the sentinel makes a silent thin delivery look multi-stop"
    )
    assert route.tourability.status == "YELLOW"
    assert route.tourability.anchor_candidate_count == 1
    # (3) The general invariant, spelled out for future fixtures: count
    # BEAT-BEARING stops, never raw POIs (the sentinel is not a story).
    assert len(beatful) >= 2 or route.tourability is not None
