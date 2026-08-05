"""Integration tests for POST /api/v1/trips/generate — real engine, live corpus.

Since M0b the endpoint runs the real tour engine (src/tour), whose density
gate refuses sparse areas (needs >=4 anchor candidates). The conftest test
instance (port 7688) only carries toy seed data (3 POIs / 5 beats), so these
tests run against the LIVE local Paris dev graph (port 7687) the way
tests/test_tour_golden_*.py do—through a separate, localhost-only dev-graph
profile and overridden app session/driver dependencies.

Unlike the goldens these tests WRITE to the dev graph: a disposable test
Profile and the Trips/ItineraryItems the endpoint persists. Setup and
teardown both delete them, so a crashed run never accumulates residue.

The tour input mirrors fixtures/tour_golden/ile_oneway_90min.json (Pont Neuf
metro, 90 min, one-way) — a known-GREEN multi-stop start on the live corpus.
"""

from __future__ import annotations

import inspect
import json
import os
import threading

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.auth.tokens import create_access_token
from src.api.dependencies import get_driver, get_session
from src.api.routes import trips
from src.tour.authoring import COMPOSE_MODEL
from src.tour.certification_provider import PhysicalProviderResponse
from src.tour.contract import TourInput
from src.tour.degradations import degradation_scope, record
from src.tour.density import TourabilityRefusedError
from src.tour.options import build_route_option
from src.tour.premium_tour import ALLOW_DIRTY_LOCAL_BUILD_ENV, plan_premium_options
from src.tour.routing import haversine_m, pace_corrected_walk_seconds
from src.tour.routing_client import RoutingClient
from src.tour.selection import load_paris_corpus, select_k_routes, select_route
from tests.conftest import needs_neo4j
from tests.live_graph import open_dev_driver

LENSED_PROFILE_ID = "m0b-trip-api-test-profile-lensed"
NOLENS_PROFILE_ID = "m0b-trip-api-test-profile-nolens"
PROFILE_IDS = [LENSED_PROFILE_ID, NOLENS_PROFILE_ID]
# The trip routes are ownership-scoped (2026-07-19 IDOR fix): they require a bearer
# token AND the profile must hang off the calling User. Own both disposable profiles
# with one disposable User so these tests exercise the authorized path.
TEST_USER_ID = "m0b-trip-api-test-user"
TEST_USER_EMAIL = "m0b-trip-api@example.test"
PROFILE_LENSES = ["hidden_history", "literary_heritage"]

# Same input as fixtures/tour_golden/ile_oneway_90min.json.
ILE_START = (48.8568, 2.3414)
ILE_DURATION_MIN = 90


def _live_driver():
    """Open only the localhost:7687 graph; this module writes disposable data."""
    return open_dev_driver()


def _delete_test_artifacts(driver) -> None:
    """Remove the disposable profiles and any trips/items they captain."""
    with driver.session() as s:
        s.run(
            "MATCH (p:Profile) WHERE p.id IN $pids "
            "OPTIONAL MATCH (p)-[:IS_CAPTAIN_OF]->(t:Trip) "
            "OPTIONAL MATCH (t)-[:HAS_STOP]->(i:ItineraryItem) "
            "DETACH DELETE t, i",
            pids=PROFILE_IDS,
        )
        s.run("MATCH (p:Profile) WHERE p.id IN $pids DETACH DELETE p", pids=PROFILE_IDS)
        s.run("MATCH (u:User {id: $uid}) DETACH DELETE u", uid=TEST_USER_ID)


@pytest.fixture(scope="module")
def live_neo4j():
    d = _live_driver()
    if d is None:
        pytest.skip(
            "Local Paris dev Neo4j unreachable. These tests write disposable "
            "records and refuse anything but localhost:7687. Run through "
            "`make test` or `make test-file FILE=tests/test_trip_api.py`."
        )
    yield d
    d.close()


@pytest.fixture(scope="module")
def test_profiles(live_neo4j):
    """Disposable profiles on the live graph: one lensed, one without lenses."""
    _delete_test_artifacts(live_neo4j)  # clear residue from any crashed prior run
    with live_neo4j.session() as s:
        s.run(
            "MERGE (u:User {id: $uid}) SET u.email = $email",
            uid=TEST_USER_ID,
            email=TEST_USER_EMAIL,
        )
        for pid in PROFILE_IDS:
            s.run(
                "MERGE (p:Profile {id: $pid}) SET p.display_name = 'M0b API Test' "
                "WITH p MATCH (u:User {id: $uid}) MERGE (u)-[:HAS_PROFILE]->(p)",
                pid=pid,
                uid=TEST_USER_ID,
            )
        linked = s.run(
            "MATCH (p:Profile {id: $pid}) "
            "UNWIND $lenses AS lname "
            "MATCH (l:Lens {name: lname}) "
            "MERGE (p)-[:PREFERS_LENS]->(l) "
            "RETURN count(l) AS linked",
            pid=LENSED_PROFILE_ID,
            lenses=PROFILE_LENSES,
        ).single()["linked"]
        assert linked == len(PROFILE_LENSES), (
            f"Live graph is missing Lens nodes for {PROFILE_LENSES} — "
            f"linked only {linked}. Re-sync the dev corpus (make db-up + upload)."
        )
    yield
    _delete_test_artifacts(live_neo4j)


@pytest.fixture(scope="module")
def client(live_neo4j, test_profiles):
    """TestClient whose request sessions AND engine corpus driver hit the live graph."""
    app = create_app()

    def _live_session():
        with live_neo4j.session() as s:
            yield s

    app.dependency_overrides[get_session] = _live_session
    app.dependency_overrides[get_driver] = lambda: live_neo4j

    def _mint_fresh_bearer(request):
        """Sign EVERY request with a token minted just now.

        Ownership-scoped routes: authenticate as the User owning both profiles.

        Minted per REQUEST, not once per module, and that is load-bearing rather than
        fastidious. `ACCESS_TOKEN_EXPIRE_MINUTES` is 60 (src/api/auth/config.py:121) and
        this fixture is module-scoped, so a single token used to cover the whole file.
        On 2026-08-05 this module's runtime passed that hour — the planner explores far
        more since the stop ceilings were removed and the fixtures were enriched to fill
        a real hour — and every test after the 60-minute mark got 401 "Invalid or expired
        token" while asserting a 422. That surfaced as 3 failures and 11 fixture errors
        in a full-suite run, and NONE of them was a product fault: a 60-minute access
        token is correct in production. A per-request token cannot expire mid-module no
        matter how slow the suite becomes.
        """
        request.headers["Authorization"] = (
            f"Bearer {create_access_token(TEST_USER_ID, TEST_USER_EMAIL)}"
        )

    with TestClient(app) as c:
        c.event_hooks["request"] = [_mint_fresh_bearer]
        yield c


@pytest.fixture(scope="module")
def snapshot(live_neo4j):
    return load_paris_corpus(live_neo4j, city_slug="paris")


@pytest.fixture(scope="module")
def ile_engine_route(snapshot):
    """The engine's own answer for the Île input — the reference the API must match."""
    tour_input = TourInput(
        start=ILE_START,
        duration_min=ILE_DURATION_MIN,
        city_slug="paris",
        lenses=None,
        round_trip=False,
    )
    # Same routing mode as the endpoint (RoutingClient; falls back to
    # haversine when local Valhalla is down) or stop-order comparisons
    # diverge whenever Valhalla is up.
    with RoutingClient() as rc:
        return select_route(tour_input, snapshot, routing_client=rc)


def _body(profile_id: str, **overrides) -> dict:
    body = {
        "profile_id": profile_id,
        "center_lat": ILE_START[0],
        "center_lng": ILE_START[1],
        "duration_min": ILE_DURATION_MIN,
        "round_trip": False,
        "start_date": "2026-06-12",
        "end_date": "2026-06-13",
        "start_time": "09:00",
    }
    body.update(overrides)
    return body


@pytest.fixture(scope="module")
def ile_response(client):
    """One engine-backed generation, shared by the response-shape assertions.

    Uses the no-lens profile so the engine input (lenses=None) matches
    ile_engine_route exactly.
    """
    resp = client.post("/api/v1/trips/generate", json=_body(NOLENS_PROFILE_ID))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    return resp.json()


@needs_neo4j
def test_generate_plans_through_the_shared_block_one(ile_response, snapshot):
    """AC-4/AC-7: the phone's route options ARE Block 1's plans, not a second planner.

    The generate endpoint used to call ``select_k_routes`` itself, take flavour one, and
    then re-run the whole beat-planning and script-stitching pass by hand — so it never
    applied the Premium route bar and never went through the one shared planner the
    workbench uses. Two halves of proof, because on a corpus where both paths happen to
    agree the behavioural half alone would pass without the fix:

    * STRUCTURAL — the handler calls the shared planner and no longer contains a second
      route-selection or script-generation pass of its own. This is AC-4's own wording:
      "select_k_routes is no longer reached at trips.py:325 with no planning_policy".
    * BEHAVIOURAL — every option the endpoint publishes is byte-identical to the flavour
      the shared planner produced for the identical input (AC-7).
    """
    planner_source = inspect.getsource(trips.generate_trip)
    assert "plan_premium_options(" in planner_source, (
        "generate_trip must plan through the one shared planner"
    )
    for second_pass in (
        "select_k_routes(",
        "build_poi_beat_plans_capped(",
        "select_vignette_beats(",
        "generate(",
    ):
        assert second_pass not in planner_source, (
            f"generate_trip still runs its own {second_pass.rstrip('(')} pass — "
            "that is the duplicate algorithm this slice removes"
        )

    body = ile_response
    tour_input = TourInput(
        start=ILE_START,
        duration_min=ILE_DURATION_MIN,
        city_slug="paris",
        lenses=None,
        round_trip=False,
    )
    with RoutingClient() as rc:
        plans = plan_premium_options(tour_input, snapshot, routing_client=rc)

    assert plans, "the shared planner produced no flavour at all for the Île input"
    assert len(body["options"]) == len(plans), (
        f"the endpoint published {len(body['options'])} options for "
        f"{len(plans)} planned flavours — it is still planning for itself"
    )

    beats_by_id = {ref.id: ref for refs in snapshot.beats_by_poi.values() for ref in refs}
    for i, plan in enumerate(plans):
        option = body["options"][i]
        expected = build_route_option(
            plan.route,
            plan.source,
            beats_by_id,
            route_id=option["route_id"],
            snapshot=snapshot,
            sequence=plan.sequence,
        ).model_dump(mode="json")
        assert [s["poi_id"] for s in option["stops"] if s["band"] == "dwell"] == [
            p.id for p in plan.route.pois
        ], f"option {i + 1} visits different places from planned flavour {i + 1}"
        assert option["eta_seconds"] > 0
        assert option["eta_seconds"] == expected["eta_seconds"], (
            f"option {i + 1} declares an arrival time the planned flavour did not"
        )
        assert [s["narration"] for s in option["stops"]] == [
            s["narration"] for s in expected["stops"]
        ], f"option {i + 1} was written by a second pass over the same route"
        # Catch-all: nothing at all about the published option may differ from the
        # flavour the shared planner produced.
        assert option == expected, f"option {i + 1} diverged from planned flavour {i + 1}"

    # The trip actually saved is flavour one, not some other flavour.
    assert [s["poi_id"] for s in body["stops"]] == [p.id for p in plans[0].route.pois]

    # Diversity survived the change (JACCARD_OVERLAP_MAX, src/tour/selection.py).
    id_sets = [{p.id for p in plan.route.pois} for plan in plans]
    for i in range(len(id_sets)):
        for j in range(i + 1, len(id_sets)):
            overlap = len(id_sets[i] & id_sets[j]) / len(id_sets[i] | id_sets[j])
            assert overlap < 0.60, f"flavours {i},{j} share {overlap:.0%} of their stops"


@needs_neo4j
class TestTripGenerateEngine:
    """The endpoint must surface the real engine's selection, order, and beats."""

    def test_response_shape(self, ile_response):
        data = ile_response
        assert isinstance(data["trip_id"], str) and data["trip_id"]
        assert data["profile_id"] == NOLENS_PROFILE_ID
        assert data["total_stops"] == len(data["stops"]) > 0
        assert data["anchor_count"] + data["flavour_count"] == data["total_stops"]
        assert isinstance(data["lens_coverage"], dict)
        for stop in data["stops"]:
            assert stop["beat_ids"], "every engine stop narrates at least one beat"
            assert stop["beat_id"] == stop["beat_ids"][0]
            assert stop["dwell_seconds"] >= 0
        # Primary-beat passthrough: the corpus' active beats carry script
        # bodies, so a generated trip must surface them (mobile's
        # audio-already-exists fast path reads these fields).
        assert any(s["script_body"] for s in data["stops"])

    def test_options_surface_k_flavours(self, ile_response):
        """M6: the response carries 1-3 RouteOptions; options[0]'s DWELL stops
        mirror the persisted trip; pairwise Jaccard over dwell sets < 0.60.

        Track B (B.3) interleaves band="vignette" walk-past stops into
        RouteOption.stops — additive annotations, not itinerary stops — so
        the mirror and diversity assertions are dwell-scoped (the persisted
        trip and the selection-time diversity filter are both dwell-only).
        """
        options = ile_response["options"]
        assert 1 <= len(options) <= 3

        def dwell_ids(option):
            return [s["poi_id"] for s in option["stops"] if s["band"] == "dwell"]

        assert dwell_ids(options[0]) == [s["poi_id"] for s in ile_response["stops"]]
        id_sets = [set(dwell_ids(o)) for o in options]
        for i in range(len(id_sets)):
            for j in range(i + 1, len(id_sets)):
                overlap = len(id_sets[i] & id_sets[j]) / len(id_sets[i] | id_sets[j])
                assert overlap < 0.60, f"options {i},{j} share {overlap:.0%}"
        for option in options:
            assert option["route_id"].startswith(ile_response["trip_id"])
            assert option["eta_seconds"] > 0
            assert option["stops"], "an option without stops is not an option"
            for stop in option["stops"]:
                # Three kinds of card: a stop you stand at, a sight you pass, and the
                # narration you hear on the way to the next stop.
                assert stop["band"] in ("dwell", "vignette", "leg")

    def test_stop_order_matches_select_route(self, ile_response, ile_engine_route):
        expected = [p.id for p in ile_engine_route.pois]
        got = [s["poi_id"] for s in ile_response["stops"]]
        assert got == expected, (
            f"API stop order diverged from select_route. "
            f"Engine: {[p.name for p in ile_engine_route.pois]}; API poi_ids: {got}."
        )

    def test_beat_ids_traceable_to_route_pois(self, ile_response, ile_engine_route, snapshot):
        allowed = {
            poi.id: (
                {b.id for b in snapshot.beats_for(poi.id)}
                | {b.id for b in ile_engine_route.demoted_beats.get(poi.id, ())}
            )
            for poi in ile_engine_route.pois
        }
        for stop in ile_response["stops"]:
            orphans = set(stop["beat_ids"]) - allowed[stop["poi_id"]]
            assert not orphans, (
                f"Stop {stop['poi_name']} returned beat_ids not traceable to its "
                f"POI (or its demoted pool): {sorted(orphans)}"
            )

    def test_persists_multi_beat_graph(self, ile_response, live_neo4j):
        """Each ItineraryItem stores beat_ids + primary and one PLAYS_BEAT per beat."""
        with live_neo4j.session() as s:
            records = s.run(
                """
                MATCH (t:Trip {id: $tid})-[:HAS_STOP]->(item:ItineraryItem)
                MATCH (item)-[:PLAYS_BEAT]->(beat:NarrativeBeat)
                WITH item, collect(beat.id) AS edge_beats
                RETURN item.sort_order AS sort_order,
                       item.beat_ids AS beat_ids,
                       item.primary_beat_id AS primary_beat_id,
                       edge_beats
                ORDER BY item.sort_order
                """,
                tid=ile_response["trip_id"],
            ).data()
        assert len(records) == ile_response["total_stops"]
        for item in records:
            assert item["beat_ids"], "item must store the engine's beat_ids"
            assert item["primary_beat_id"] == item["beat_ids"][0]
            assert sorted(item["edge_beats"]) == sorted(item["beat_ids"]), (
                "PLAYS_BEAT edges must cover exactly the stored beat_ids"
            )

    def test_persists_extra_beat_ids_for_keep_exploring(self, ile_response, live_neo4j):
        """KE1: each ItineraryItem persists its 'keep exploring here' extras
        (extra_beat_ids) and a null extra_narration (composed later at /compose).
        On the dense Île walk the per-tier cap (R1) always overflows at least one
        marquee stop, so the extras are genuinely non-empty."""
        with live_neo4j.session() as s:
            items = s.run(
                """
                MATCH (t:Trip {id: $tid})-[:HAS_STOP]->(item:ItineraryItem)
                RETURN item.beat_ids AS beat_ids,
                       item.extra_beat_ids AS extra_beat_ids,
                       item.extra_narration AS extra_narration
                ORDER BY item.sort_order
                """,
                tid=ile_response["trip_id"],
            ).data()
        assert len(items) == ile_response["total_stops"]
        for it in items:
            assert it["extra_beat_ids"] is not None, "extra_beat_ids persisted (possibly empty)"
            assert it["extra_narration"] is None, "extra_narration is null until /compose"
            # extras never overlap the voiced beats (they are the un-voiced remainder)
            assert set(it["extra_beat_ids"]).isdisjoint(it["beat_ids"])
        assert any(it["extra_beat_ids"] for it in items), (
            "the dense Île walk must overflow the per-tier cap at ≥1 stop -> non-empty extras"
        )
        # and the API GET surfaces the same persisted extras
        for stop in ile_response["stops"]:
            assert "extra_beat_ids" in stop and stop.get("extra_narration") is None


@needs_neo4j
class TestTripGenerateLensPrecedence:
    """Request lenses win; else the profile's PREFERS_LENS; else unbiased."""

    def test_profile_lenses_feed_engine(self, client, snapshot):
        resp = client.post("/api/v1/trips/generate", json=_body(LENSED_PROFILE_ID))
        assert resp.status_code == 201, resp.text
        with RoutingClient() as rc:
            engine_route = select_route(
                TourInput(
                    start=ILE_START,
                    duration_min=ILE_DURATION_MIN,
                    city_slug="paris",
                    lenses=sorted(PROFILE_LENSES),  # the route sorts profile lenses
                    round_trip=False,
                ),
                snapshot,
                routing_client=rc,
            )
        got = [s["poi_id"] for s in resp.json()["stops"]]
        assert got == [p.id for p in engine_route.pois]

    def test_request_lenses_override_profile(self, client, snapshot):
        request_lenses = ["dark_history"]
        resp = client.post(
            "/api/v1/trips/generate",
            json=_body(LENSED_PROFILE_ID, lenses=request_lenses),
        )
        assert resp.status_code == 201, resp.text
        with RoutingClient() as rc:
            engine_route = select_route(
                TourInput(
                    start=ILE_START,
                    duration_min=ILE_DURATION_MIN,
                    city_slug="paris",
                    lenses=request_lenses,
                    round_trip=False,
                ),
                snapshot,
                routing_client=rc,
            )
        got = [s["poi_id"] for s in resp.json()["stops"]]
        assert got == [p.id for p in engine_route.pois]


@needs_neo4j
class TestTripGenerateErrors:
    def test_profile_not_found_404(self, client):
        resp = client.post(
            "/api/v1/trips/generate", json=_body("nonexistent-profile-id-xyz")
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_sparse_origin_refused_422(self, client):
        """The density gate's RED refusal maps to a structured 422 body. Sydney
        is far from every Paris POI, so there is no fixed-destination overshoot:
        gap_minutes is None and alternatives is empty (those only appear for an
        A→B feasibility refusal, exercised in TestTripGenerateFixedDestination)."""
        body = _body(NOLENS_PROFILE_ID, center_lat=-33.8688, center_lng=151.2093)
        resp = client.post("/api/v1/trips/generate", json=body)
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert isinstance(detail, dict)
        assert isinstance(detail["reason"], str) and detail["reason"]
        assert detail["gap_minutes"] is None
        assert detail["alternatives"] == []


# Versailles palace — a real Paris-region coordinate ~14km SW of the Île start.
# The routed A→B leg (or its haversine fallback) is hours long, dwarfing any
# tour walk budget, so a fixed-end A→B request from the Île GREEN start lands in
# the Step-2.2 fixed-destination feasibility refusal — never density-RED (the
# Île start stays GREEN at 90 min). Far enough that no selected POI snaps within
# B_SNAP_PROXIMITY_M, so the engine synthesizes a sentinel at B's exact coord.
VERSAILLES_END = (48.8049, 2.1204)


@needs_neo4j
class TestTripGenerateFixedDestination:
    """Step 2.6: end_lat/end_lng thread into TourInput.end; the route ends at B,
    and an unreachable B yields a structured 422 mirroring the Step-2.2 error."""

    def test_no_end_request_unchanged(self, ile_response, ile_engine_route):
        """A request WITHOUT end_lat/end_lng is the legacy open-walk path: the
        engine's end=None route is unchanged, so its last stop is unchanged."""
        engine_last = ile_engine_route.pois[-1].id
        api_last = ile_response["stops"][-1]["poi_id"]
        assert api_last == engine_last

    def test_ab_request_route_ends_at_b(self, client, snapshot, ile_engine_route):
        """An in-budget A→B request returns a route ending at B. B is the coord
        of a real POI the open Île route selected, so B-materialization snaps B
        onto a selected anchor: the API's final stop is the engine's fixed-end
        route's final POI (derived live, both via RoutingClient)."""
        # A selected anchor from the open route → guaranteed in-corridor and
        # reachable, so the A→B request is feasible (no refusal).
        b_poi = ile_engine_route.pois[-1]
        b_end = (b_poi.lat, b_poi.lng)
        with RoutingClient() as rc:
            engine_route = select_route(
                TourInput(
                    start=ILE_START,
                    duration_min=ILE_DURATION_MIN,
                    city_slug="paris",
                    lenses=None,
                    round_trip=False,
                    end=b_end,
                ),
                snapshot,
                routing_client=rc,
            )
        resp = client.post(
            "/api/v1/trips/generate",
            json=_body(NOLENS_PROFILE_ID, end_lat=b_end[0], end_lng=b_end[1]),
        )
        assert resp.status_code == 201, resp.text
        got = [s["poi_id"] for s in resp.json()["stops"]]
        expected = [p.id for p in engine_route.pois]
        assert got == expected, (
            f"API order diverged from fixed-end select_route: {got} vs {expected}"
        )
        # The route literally ends at B (the materialized fixed_end).
        assert got[-1] == engine_route.pois[-1].id

    def test_over_budget_ab_returns_structured_422(self, client, snapshot):
        """An A→B request whose routed A→B leg exceeds the walk budget returns a
        422 whose JSON body matches the live Step-2.2 TourabilityRefusedError:
        {reason, gap_minutes, alternatives:[{kind,...}]} with the kind enum
        (loop/extend, plus closer_b when an anchor fits the budget)."""
        # Reproduce the endpoint's own engine call to derive the truth live —
        # robust whether Valhalla is up (routed leg) or down (haversine).
        tour_input = TourInput(
            start=ILE_START,
            duration_min=ILE_DURATION_MIN,
            city_slug="paris",
            lenses=None,
            round_trip=False,
            end=VERSAILLES_END,
        )
        with (
            RoutingClient() as rc,
            pytest.raises(TourabilityRefusedError) as caught,
        ):
            select_k_routes(tour_input, snapshot, 3, routing_client=rc)
        exc = caught.value
        # Guard: this must be the FIXED-DESTINATION feasibility refusal (carries
        # gap_minutes + alternatives), not a plain density-RED refusal.
        assert exc.gap_minutes is not None and exc.gap_minutes > 0
        assert exc.alternatives, "fixed-destination refusal must offer alternatives"
        expected_kinds = [a.kind for a in exc.alternatives]
        assert {"loop", "extend"} <= set(expected_kinds)
        assert set(expected_kinds) <= {"loop", "extend", "closer_b"}

        resp = client.post(
            "/api/v1/trips/generate",
            json=_body(NOLENS_PROFILE_ID, end_lat=VERSAILLES_END[0], end_lng=VERSAILLES_END[1]),
        )
        assert resp.status_code == 422, resp.text
        detail = resp.json()["detail"]
        assert isinstance(detail, dict)
        assert detail["reason"] == str(exc)
        assert detail["gap_minutes"] == exc.gap_minutes
        # The structured alternatives mirror the engine's FeasibilityAlternative
        # tuple field-for-field (kind enum + duration_min/drop_end/poi_id/lat/lng).
        assert [a["kind"] for a in detail["alternatives"]] == expected_kinds
        assert detail["alternatives"] == [
            {
                "kind": a.kind,
                "duration_min": a.duration_min,
                "drop_end": a.drop_end,
                "poi_id": a.poi_id,
                "lat": a.lat,
                "lng": a.lng,
            }
            for a in exc.alternatives
        ]


class TestPreviewTrip:
    """POST /trips/preview: route options over the live corpus, no profile, nothing saved."""

    def test_preview_returns_choosable_routes_and_no_words(self, client):
        """What comes back is a set of real walks to choose between, and nothing else.

        Each stop is a named place with a position and a time; none of them carries a
        written line, because nothing has been written yet. The words arrive from
        POST /trips/preview/author once one of these walks has been picked.
        """
        resp = client.post(
            "/api/v1/trips/preview",
            json={
                "center_lat": ILE_START[0],
                "center_lng": ILE_START[1],
                "duration_min": ILE_DURATION_MIN,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["options"], "a plan with no walks to choose between is not a plan"
        for option in data["options"]:
            assert option["eta_seconds"] > 0
            dwell = [s for s in option["stops"] if s["band"] == "dwell"]
            assert dwell, "a walk with nowhere to stand is not a walk"
            for stop in option["stops"]:
                assert stop["name"], "a stop with no name is not a place anyone can choose"
                assert stop["narration"] == "", "planning writes nothing"
                assert stop["band"] in ("dwell", "vignette")

    def test_preview_sparse_origin_422(self, client):
        resp = client.post(
            "/api/v1/trips/preview",
            json={"center_lat": -33.8688, "center_lng": 151.2093, "duration_min": 90},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Phase 4 Step 4.7 — POST /trips/{trip_id}/compose
# ---------------------------------------------------------------------------

COMPOSE_MARKER = "COMPOSED-MARKER: the story, retold for you."


class _MarkerAuthoringExecutor:
    """Deterministic author: opens the first stop with a recognizable phrase —
    route-independent proof that the AUTHORED output (not the stitch) was persisted.

    It edits sentence TEXT only and leaves every citation alone, so the marker is
    the single variable: anything that fails afterwards is a real gate finding, not
    the double inventing an untraceable sentence.
    """

    cost_bearing = False
    provider_name = "offline"

    def execute(self, unit) -> PhysicalProviderResponse:
        sentences = [s.model_dump(mode="json") for s in unit.authorized_request.stitched.script]
        if unit.stop_index == 0:
            sentences[0] = {
                **sentences[0],
                "text": f"{COMPOSE_MARKER} {sentences[0]['text']}",
            }
        return _offline_response(unit, sentences)


def _provider_bytes(sentences: list[dict]) -> bytes:
    """The exact JSON envelope the per-stop authoring seam parses back."""
    return json.dumps(
        {"sentences": sentences},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _offline_response(unit, sentences: list[dict]) -> PhysicalProviderResponse:
    return PhysicalProviderResponse(
        body=_provider_bytes(sentences),
        input_tokens=0,
        output_tokens=0,
        latency_ms=0,
        model=COMPOSE_MODEL,
        provider_request_id=f"offline-{unit.stop_index}",
        stop_reason="end_turn",
    )


class _PerStopCountingExecutor:
    """A COST-BEARING physical-boundary double for the per-stop authoring seam.

    It records which dwell stop each physical call was made for and echoes the
    grounded stitch straight back, so the assertions are on the number of calls the
    endpoint actually made — not on a status code that could be green with the old
    whole-tour composer still doing the work. ``cost_bearing`` is True on purpose:
    the spend guard only arms for billable providers, so a $0 stub could never
    prove the reservation.
    """

    cost_bearing = True
    provider_name = "anthropic"

    def __init__(self) -> None:
        self.stop_calls: list[int] = []
        self._lock = threading.Lock()

    def execute(self, unit) -> PhysicalProviderResponse:
        with self._lock:
            self.stop_calls.append(unit.stop_index)
        return _offline_response(
            unit,
            [s.model_dump(mode="json") for s in unit.authorized_request.stitched.script],
        )


class _HallucinatingExecutor:
    """Authors one sentence citing a beat that is not in the grounded source.

    That is the untraceable-citation half of VERIFY, so the per-stop finalizer must
    refuse the whole tour. $0 and non-billing, so it reserves nothing and the spend
    assertions in the same test stay about the paid path.
    """

    cost_bearing = False
    provider_name = "offline"

    def execute(self, unit) -> PhysicalProviderResponse:
        sentences = [s.model_dump(mode="json") for s in unit.authorized_request.stitched.script]
        sentences[0] = {
            **sentences[0],
            "source_id": "beat-that-was-never-in-the-corpus",
            "source_type": "beat",
            "also_cites": [],
        }
        return _offline_response(unit, sentences)


class _RewritingCountingExecutor(_PerStopCountingExecutor):
    """Counts physical calls like its parent, but REWRITES instead of echoing.

    The corpus is canonical: a sentence copied verbatim out of the beat it cites is
    trivially faithful and never reaches the entailment checker at all
    (src/tour/verify.py:181-187, 217). A pure echo therefore proves nothing about
    whether the fact-checking gate ran. Prefixing each stop's first beat-cited
    sentence — the same edit ``_MarkerAuthoringExecutor`` makes — is what gives the
    gate a question to ask, and it leaves every citation alone so any later refusal
    is a real finding rather than this double inventing an untraceable sentence.
    """

    def execute(self, unit) -> PhysicalProviderResponse:
        with self._lock:
            self.stop_calls.append(unit.stop_index)
        sentences = [s.model_dump(mode="json") for s in unit.authorized_request.stitched.script]
        for i, sentence in enumerate(sentences):
            if sentence.get("source_type") == "beat":
                sentences[i] = {**sentence, "text": f"{COMPOSE_MARKER} {sentence['text']}"}
                break
        return _offline_response(unit, sentences)


class _CountingChecker:
    """Records every entailment question asked, and approves all of them.

    It changes no verdict, so it cannot make a failing tour pass; it only proves the
    gate CONSULTED a checker. Mirrors src/tour/verify.py's FaithfulnessChecker
    protocol exactly — ``entails(key_claims, sentence_text)``.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], str]] = []

    def entails(self, key_claims: tuple[str, ...], sentence_text: str) -> bool:
        self.calls.append((key_claims, sentence_text))
        return True


class _ColdStartingRoutingClient:
    """``ondoway-valhalla`` while it cold-starts or rebuilds tiles (render.yaml:98-124).

    Every request to it fails, and it fails the two DIFFERENT ways the real client
    fails, which is the whole point of the stub:

    - walking legs fall back to a straight-line estimate with no polyline and no
      receipt, never raising — src/tour/routing_client.py:175-181;
    - the version read RAISES, because that one call deliberately has no fallback of
      its own — src/tour/routing_client.py:183-200.

    Standing in for the class rather than stopping the container keeps the shared
    :8002 instance every other test and every sibling session depends on completely
    untouched.
    """

    def __init__(self, *args, **kwargs) -> None:
        return None

    def __enter__(self):
        return self

    def __exit__(self, *exc_info) -> bool:
        return False

    def routing_version(self) -> str:
        raise RuntimeError("valhalla is cold-starting")

    def route_with_receipt(self, from_lat, from_lng, to_lat, to_lng):
        seconds, distance_m, shape = self.route(from_lat, from_lng, to_lat, to_lng)
        return seconds, distance_m, shape, None

    def route(self, from_lat, from_lng, to_lat, to_lng):
        d = haversine_m(from_lat, from_lng, to_lat, to_lng)
        return int(pace_corrected_walk_seconds(d)), d, None

    def leg_seconds(self, from_lat, from_lng, to_lat, to_lng) -> int:
        return self.route(from_lat, from_lng, to_lat, to_lng)[0]

    def isochrone(self, lat: float, lng: float, minutes: int) -> None:
        return None

    def close(self) -> None:
        return None


def _override_dep(client, dep: str, value):
    """Swap a FastAPI dependency for a test double; returns the override key."""
    from src.api import dependencies

    target = getattr(dependencies, dep)
    client.app.dependency_overrides[target] = lambda: value
    return target


def _clear_dep(client, target) -> None:
    client.app.dependency_overrides.pop(target, None)


@pytest.fixture()
def cutover_trip(client):
    """One freshly generated, not-yet-composed trip on the live corpus."""
    resp = client.post("/api/v1/trips/generate", json=_body(NOLENS_PROFILE_ID))
    assert resp.status_code == 201, resp.text
    return resp.json()


@needs_neo4j
def test_compose_hands_back_the_flavour_that_was_saved(
    client, live_neo4j, cutover_trip, monkeypatch
) -> None:
    """AC-8, saved-trip half: composing gives back the walk that was offered.

    A saved trip stores which places its chosen walk visits, but composing has to
    rebuild the walk itself — the walking times are re-measured live, because a tour
    composed days later must reflect today's streets and must still work when the
    routing service is down. Everything ELSE about the walk was being re-derived too,
    which is where it could quietly stop being the walk that was chosen: the walk-past
    sights were re-picked by a second, differently-configured picker, the marquee
    stops were copied back on afterwards, and the thin-area warning was lost entirely.

    All four now come back from what was saved, handed into the rebuild in one go.

    NOT bit-identical walking times, and deliberately so: those are re-measured, which
    is the whole reason a tour composed later is still walkable. What is guaranteed is
    that the elapsed time the walk was OFFERED as was recorded at the time, so the two
    can always be compared.

    UNDO: drop the ``vignettes=`` argument from the rebuild in ``compose_trip``, or
    the ``tourability=`` one, and the matching assertion below goes RED.
    """
    from src.api.crud.trips import get_trip_compose_inputs

    trip_id = cutover_trip["trip_id"]
    with live_neo4j.session() as s:
        stored = get_trip_compose_inputs(s, trip_id)
    saved = stored["options"][0]
    assert isinstance(saved, dict), "a saved flavour must record more than a list of places"

    # The elapsed time the walk was offered as was written down, and it is the same
    # number the traveller was shown.
    assert saved["eta_seconds"] == cutover_trip["options"][0]["eta_seconds"]
    assert saved["eta_seconds"] > 0

    rebuilt = {}
    real_summarise = trips.summarise_route

    def _capture(*args, **kwargs):
        route = real_summarise(*args, **kwargs)
        rebuilt["route"] = route
        return route

    monkeypatch.setattr(trips, "summarise_route", _capture)
    resp = client.post(
        f"/api/v1/trips/{trip_id}/compose", json={"route_id": f"{trip_id}-opt1"}
    )
    assert resp.status_code == 200, resp.text
    route = rebuilt["route"]

    assert [p.id for p in route.pois] == saved["poi_ids"], "composed a different set of places"
    assert {
        str(leg): [p.id for p in pois] for leg, pois in route.vignettes.items()
    } == saved["vignette_poi_ids"], "the walk-past sights were re-picked, not carried over"
    assert (
        route.tourability.model_dump(mode="json") if route.tourability is not None else None
    ) == saved["tourability"], "the thin-area warning did not survive composing"
    assert route.start_anchor_poi_id == saved["start_anchor_poi_id"]
    assert route.fixed_end_poi_id == saved["fixed_end_poi_id"]

    # And the places the traveller is finally given are those same places, in order.
    assert [s["poi_id"] for s in resp.json()["stops"]] == saved["poi_ids"]


@needs_neo4j
def test_compose_plans_and_authors_through_the_shared_premium_seam(
    client, live_neo4j, cutover_trip, monkeypatch
) -> None:
    """AC-10 — the saved-trip compose path rebuilds no route without a stated policy.

    Composing a saved trip used to run a second, separate authoring engine of its
    own. It now goes through the single shared seam the workbench preview and the
    batch runner already use: build the per-stop requests, fire exactly one call per
    stop, finalize. Four things are checked, each with its own one-line undo:

    1. the handler names the shared seam and no longer names the second one, and the
       route it rebuilds is measured against the certification walking-time budget
       (0.90-1.10 of the requested duration, nominal 1.00) rather than the old flat
       0.83 one -- which is AC-10's whole reason;
    2. the suite declares itself a local build, so authoring off a developer tree
       with uncommitted work is not mistaken for a broken product;
    3. the two environment dependencies the shared seam newly adds are each handled by
       name rather than escaping -- a build fingerprint that cannot be resolved is a
       NAMED 503 the caller can retry, and a routing-engine version that cannot be read
       is a labelled degradation. Neither is ever a bare 500 and neither is ever
       ``compose_verification_failed`` (which means "the narrator wrote something
       untraceable" and would blame the writer for a container that is cold-starting);
    4. the fact-checking gate is consulted, which only the shared finalizer makes
       impossible to omit.

    ON 3b, WHICH CHANGED ON 2026-08-05. The routing-version read used to be a 503 as
    well. It is now a degradation, because a refusal there is the same hard "no" to a
    cold-starting container that PLANNING gives up, and it lands after the traveller has
    already picked a route -- so it took tour writing down app-wide for as long as the
    container took to come back. It is checked in-process here, on the exact function
    this handler calls, so that this test does not spend its one-shot compose budget
    before block 4 needs it; the end-to-end 200-with-a-row is proven by
    test_generate_and_compose_report_what_degraded.

    NOT AC-8, deliberately. AC-8 wants the authored route's ids, order, eta_seconds,
    vignettes and tourability to be IDENTICAL to the option the traveller chose, with
    no re-derivation. This endpoint cannot deliver that and never could: generate
    persists a chosen option's POI ids and anchor ids only (``trips.py`` route_id
    lookup), never its eta_seconds, vignettes or tourability, so compose has to
    rebuild a route -- which is the same concession AC-10's own note records. The
    surface where a chosen option is genuinely handed over intact is the anonymous
    author endpoint, and that endpoint plus the response field AC-8 needs
    (``tourability`` on the compose/author response model) are step 11's, which is
    scoped to ``src/api/models/trips.py``. Claiming AC-8 here would be claiming a
    check this test does not make.

    UNDO -- each turns exactly one numbered block RED, and all four were run:
      * delete the ``ONDOWAY_ALLOW_DIRTY_LOCAL_BUILD`` line from tests/conftest.py -> 2
      * collapse the build-fingerprint ``503`` branch to a bare ``raise`` -> 3a
      * make ``resolve_routing_version`` re-raise instead of recording -> 3b
      * change ``faithfulness_checker=faithfulness_checker`` to ``=None`` -> 4
    """
    # 1. STRUCTURAL: the handler's own source names the shared seam and nothing else.
    source = inspect.getsource(trips.compose_trip)
    assert "plan_premium_authoring(" in source
    assert "execute_premium_plan(" in source
    assert "finalize_premium_tour(" in source
    assert "author_prebuilt_route(" not in source
    assert "plan_prebuilt_route_authoring(" not in source

    # AC-10 proper: the rebuild is handed a policy explicitly, and that policy is
    # really the certification one. The two greps say a policy is passed; the value
    # assertions below say WHICH, so swapping in the flat legacy budget behind the
    # same argument name cannot pass. 0.83 is the legacy figure this must never be.
    assert "planning_policy=planning_policy" in source
    assert "certification_planning_policy(" in source
    policy = trips.certification_planning_policy(policy_id=trips.PREMIUM_MODULE_VERSION)
    # There is only one walking-time budget left in the codebase, so there is no
    # "which one is this" flag to read any more — the three fractions below ARE the
    # identity of the certification band, and the legacy flat 0.83 one is deleted.
    assert policy.minimum_requested_fraction == pytest.approx(0.90)
    assert policy.maximum_requested_fraction == pytest.approx(1.10)
    assert policy.nominal_requested_fraction == pytest.approx(1.00)

    # 2. The suite says out loud that it is a local build, ONCE, for every module.
    #    conftest.py has to spell the variable as a literal (it runs before the tour
    #    package is importable), so bind that literal to the constant here: rename the
    #    constant without updating conftest and this goes RED, instead of every compose
    #    test in the suite going RED with a 503 that looks like a product bug.
    assert os.environ.get(ALLOW_DIRTY_LOCAL_BUILD_ENV) == "1", (
        "the test suite has not declared itself a local build, so authoring a tour "
        "off any tree with uncommitted work will fail as an environment fault"
    )

    trip_id = cutover_trip["trip_id"]
    n_stops = len(cutover_trip["stops"])
    assert n_stops > 1

    # 3a. The seam demands a build fingerprint the old compose path never needed. When
    #     it cannot be resolved that is an ENVIRONMENT fault — 503 with a name a caller
    #     can branch on, never a generic 500 and never compose_verification_failed.
    #     Checked BEFORE the successful compose below, because this refusal happens
    #     before any write and leaves the trip composable.
    unreachable = _PerStopCountingExecutor()
    exec_target = _override_dep(client, "get_premium_compose_executor", unreachable)
    monkeypatch.setattr(
        trips,
        "resolve_build_identity",
        lambda: (_ for _ in ()).throw(ValueError("dirty build")),
    )
    try:
        refused = client.post(
            f"/api/v1/trips/{trip_id}/compose", json={"route_id": f"{trip_id}-opt1"}
        )
    finally:
        _clear_dep(client, exec_target)
    assert refused.status_code == 503, refused.text
    detail = refused.json()["detail"]
    assert detail["reason"] == "build_fingerprint_unavailable", detail
    assert "dirty build" in detail["detail"], detail
    assert unreachable.stop_calls == [], (
        "a build-fingerprint fault must be raised before any paid authoring call"
    )
    monkeypatch.undo()

    # 3b. The seam's OTHER new environment dependency, and the one nothing else on
    #     this path has: it stamps the tour with the routing engine's version, which
    #     is a live GET /status against ondoway-valhalla. Every walking leg already
    #     degrades to a straight-line estimate when that container is down, so this
    #     one call is the only thing on the compose path an outage can hard-fail —
    #     and left bare it surfaces as a 500 (transport error) or, worse, as a 422
    #     compose_verification_failed via the malformed-status ValueError.
    #     It does NEITHER: the failure is caught and labelled, the tour is stamped with
    #     an unmistakable placeholder rather than a plausible-looking version, and the
    #     traveller is told on the wire. The routing client is stubbed IN-PROCESS; the
    #     shared container is untouched.
    assert "resolve_routing_version(" in source
    with degradation_scope() as collected:
        stamped = trips.resolve_routing_version(_ColdStartingRoutingClient())
    assert stamped == "unavailable", stamped
    assert [d.kind for d in collected] == ["routing_version_unavailable"], collected
    assert collected[0].error_message == "valhalla is cold-starting"
    assert collected[0].human and "valhalla" not in collected[0].human.lower()

    # 4. BEHAVIOURAL: composing consults the injected faithfulness checker. Only
    #    finalize_premium_tour makes that non-optional, so this is what proves the
    #    endpoint went through it rather than round a gate-optional seam.
    checker = _CountingChecker()
    executor = _RewritingCountingExecutor()
    exec_target = _override_dep(client, "get_premium_compose_executor", executor)
    check_target = _override_dep(client, "get_faithfulness_checker", checker)
    try:
        resp = client.post(
            f"/api/v1/trips/{trip_id}/compose", json={"route_id": f"{trip_id}-opt1"}
        )
    finally:
        _clear_dep(client, exec_target)
        _clear_dep(client, check_target)
    assert resp.status_code == 200, resp.text
    assert sorted(executor.stop_calls) == list(range(n_stops))
    assert checker.calls, (
        "compose never consulted the injected faithfulness checker — it is not "
        "going through finalize_premium_tour, which is the only thing that makes "
        "the checker impossible to omit"
    )
    assert len(resp.json()["stops"]) == n_stops


@needs_neo4j
def test_compose_authors_per_stop_and_keeps_the_wire_contract(client, live_neo4j, cutover_trip):
    """AC-3 + AC-7 — the pinned gate for the compose cutover.

    Every clause lives in this one node id on purpose, because each of them is
    a way the cutover could go wrong while the endpoint still looked healthy:

    * the ENGINE is the per-stop authoring seam — proven by counting physical
      calls at the injected provider boundary (one per dwell stop), not by the
      status code, which the old whole-tour composer would also return 200 for;
    * the WIRE CONTRACT the phone parses is unchanged — 200 with fresh stop ids
      and persisted extra_narration, 409 already_composed, 404 for an unknown
      trip and for an unknown route_id, and a 422 whose detail carries BOTH
      ``reason == "compose_verification_failed"`` and ``attempts``
      (mobile/lib/services/trip_service.dart:201-203 reads exactly those two);
    * the SPEND PRECHECK reserves the real call count (n_stops, not 1) and runs
      AFTER the already-composed check, so a duplicate compose is a 409 that
      reserves nothing and calls nobody.
    """
    trip_id = cutover_trip["trip_id"]
    n_stops = len(cutover_trip["stops"])
    assert n_stops > 1, "a one-stop trip cannot tell per-stop authoring from whole-tour"
    generated_stop_ids = {st["stop_id"] for st in cutover_trip["stops"]}

    def trip_row():
        with live_neo4j.session() as s:
            items = s.run(
                "MATCH (t:Trip {id: $tid})-[:HAS_STOP]->(i:ItineraryItem) "
                "RETURN i.id AS id, i.narration AS narration, "
                "i.extra_narration AS extra_narration, i.audio_url AS audio "
                "ORDER BY i.sort_order",
                tid=trip_id,
            ).data()
            composed_route = s.run(
                "MATCH (t:Trip {id: $tid}) RETURN t.composed_route_id AS rid", tid=trip_id
            ).single()["rid"]
        return items, composed_route

    # --- 404: unknown trip, and an unknown route_id on a real trip ---------
    assert (
        client.post(
            "/api/v1/trips/no-such-trip/compose", json={"route_id": "no-such-trip-opt1"}
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/trips/{trip_id}/compose", json={"route_id": f"{trip_id}-opt99"}
        ).status_code
        == 404
    )

    # --- 422: an unauthorable flavour is refused, and nothing is persisted --
    before_items, before_route = trip_row()
    assert before_route is None
    target = _override_dep(client, "get_premium_compose_executor", _HallucinatingExecutor())
    try:
        refused = client.post(
            f"/api/v1/trips/{trip_id}/compose", json={"route_id": f"{trip_id}-opt1"}
        )
    finally:
        _clear_dep(client, target)
    assert refused.status_code == 422, refused.text
    detail = refused.json()["detail"]
    assert detail["reason"] == "compose_verification_failed"
    assert detail["attempts"] >= 1, "the phone reads detail['attempts'] and must find it"
    assert detail["untraceable"] > 0, "the hallucinated citation must be the named cause"
    assert trip_row() == (before_items, None), "a refusal must leave the trip untouched"

    # --- 200: one physical call per dwell stop ----------------------------
    # (A reset_spend_guard() call sat here to clear the rate limiter's counters
    # between phases. The limiter was deleted 2026-07-31 by owner order, so there
    # is nothing to reset.)
    executor = _PerStopCountingExecutor()
    target = _override_dep(client, "get_premium_compose_executor", executor)
    try:
        resp = client.post(
            f"/api/v1/trips/{trip_id}/compose", json={"route_id": f"{trip_id}-opt1"}
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        # THE CUTOVER ITSELF: one authoring call per dwell stop, at the seam.
        assert sorted(executor.stop_calls) == list(range(n_stops)), (
            "compose did not author the persisted route stop-by-stop through the "
            f"injected seam (calls: {sorted(executor.stop_calls)})"
        )
        # (AC-7 asserted here that the rate limiter reserved one unit per dwell
        # stop rather than a flat 1. The limiter was DELETED 2026-07-31 by owner
        # order, so there is no reservation to check. The per-stop authoring
        # itself is still proven, by the stop_calls assertion directly above.)

        # The wire contract the phone and the workbench read.
        assert data["trip_id"] == trip_id
        assert data["route_id"] == f"{trip_id}-opt1"
        assert data["attempts"] >= 1
        assert len(data["stops"]) == n_stops
        assert not ({st["stop_id"] for st in data["stops"]} & generated_stop_ids), (
            "compose must re-persist the stops under FRESH item ids"
        )
        items, composed_route = trip_row()
        assert composed_route == f"{trip_id}-opt1"
        assert [i["id"] for i in items] == [st["stop_id"] for st in data["stops"]]
        assert all(i["audio"] is None for i in items), "compose voices nothing"
        assert all(st["narration"] for st in data["stops"]), "every stop is narrated"
        # extra_narration is persisted, and exactly for the stops that have extras.
        assert any(i["extra_narration"] for i in items), (
            "the dense Île walk overflows at least one stop, so /compose must "
            "persist its keep-exploring narration"
        )
        for stop, item in zip(data["stops"], items, strict=True):
            assert stop["extra_narration"] == item["extra_narration"]
            assert bool(item["extra_narration"]) == bool(stop["extra_beat_ids"])

        # --- 409: a duplicate compose costs nothing ------------------------
        calls_after_success = list(executor.stop_calls)
        second = client.post(
            f"/api/v1/trips/{trip_id}/compose", json={"route_id": f"{trip_id}-opt1"}
        )
        assert second.status_code == 409
        assert second.json()["detail"]["reason"] == "already_composed"
        assert executor.stop_calls == calls_after_success, (
            "the already-composed trip still reached the provider"
        )
    finally:
        _clear_dep(client, target)


@needs_neo4j
def test_generate_and_compose_report_what_degraded(client, live_neo4j, cutover_trip) -> None:
    """AC-18 — the phone's two endpoints say what quietly went wrong, like the web does.

    OWNER RULING 2026-07-31: "Don't just log errors. Actually show them in the workbench
    UI. Otherwise, they're invisible." The workbench preview has carried that list since
    then. The phone's own two calls collected the same facts and threw them away, so a
    tour planned on estimated walking times looked, on a phone, exactly like one planned
    on measured ones.

    The fault injected is the real one rather than a synthetic marker: the walking
    service is unreachable, so every leg falls back to a straight-line estimate and the
    version read fails. Both must travel, and NEITHER may become a refusal — the service
    is a real dependency that cold-starts and rebuilds tiles, and refusing would take
    tour generation down for every user while it does.

    Three things the already-shipped phone build depends on are asserted literally,
    because a mismatch on any of them shows the traveller NOTHING, with no error and no
    crash: the list is at the TOP level of the body, it is a JSON array, and every row
    is an object carrying a ``human`` string. ``human`` is the only key the production
    Dart reads.

    WHY GENERATE IS PROVEN WITH A PLANTED ROW AND COMPOSE WITH THE REAL OUTAGE. Both
    halves were first written against the real outage. Compose passes that way and is
    kept that way. Generate does not, and NOT because of anything this change does: with
    estimated legs the live 90-minute walk comes out at 6009s against a 4860-5940s band,
    and the planner refuses it 422 — the over-ceiling refusal a separate lane is fixing,
    which the timebox repair cannot bring back down because it can add or swap a stop
    but not drop one. Asserting generate's routing row on the live corpus would import
    that unrelated bug into this test and make it fail for a reason it is not about. A
    planted row proves what this step actually changed — that a degradation recorded
    anywhere inside the request reaches the top level of the reply instead of the floor
    — with no dependence on which route the planner happens to pick. The routing row's
    own content is proven end-to-end twice over: on compose below, and on the planning
    surface generate shares by
    test_trip_preview_contract.py::test_estimated_legs_are_labelled_not_silently_shipped.
    """
    # 1. A CLEAN RUN SAYS SO. An empty list is a real statement — "nothing degraded" —
    #    and it is not the same as a missing key, which a client cannot distinguish
    #    from an old server.
    assert "degradations" in cutover_trip, sorted(cutover_trip)
    assert cutover_trip["degradations"] == [], cutover_trip["degradations"]

    # 2. GENERATE: a degradation recorded from inside the request reaches the caller.
    real_loader = trips.load_paris_corpus

    def _loader_that_degrades(*args, **kwargs):
        record(
            kind="test_probe",
            human="A probe recorded one degradation so the channel can be seen.",
            component="tests.test_trip_api",
        )
        return real_loader(*args, **kwargs)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(trips, "load_paris_corpus", _loader_that_degrades)
        degraded = client.post("/api/v1/trips/generate", json=_body(NOLENS_PROFILE_ID))
    assert degraded.status_code == 201, degraded.text

    rows = degraded.json()["degradations"]
    assert isinstance(rows, list), type(rows)
    assert [row["kind"] for row in rows] == ["test_probe"], rows
    row = rows[0]
    assert isinstance(row, dict), row
    assert isinstance(row.get("human"), str) and row["human"], row
    # The six keys ``summarize`` emits — including the count that collapses repeats, or
    # a fan-out of identical failures prints the same line once per occurrence.
    assert set(row) == {
        "kind",
        "human",
        "component",
        "error_type",
        "error_message",
        "context",
        "count",
    }, sorted(row)
    assert row["count"] == 1, row

    # 3. COMPOSE under a real outage: a 200 that says what it lost, NOT a refusal.
    #    This is the half that used to answer differently — the version read was a hard
    #    503, so the identical outage degraded when planning and refused when writing.
    trip_id = cutover_trip["trip_id"]
    executor = _PerStopCountingExecutor()
    target = _override_dep(client, "get_premium_compose_executor", executor)
    try:
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(trips, "RoutingClient", _ColdStartingRoutingClient)
            composed = client.post(
                f"/api/v1/trips/{trip_id}/compose", json={"route_id": f"{trip_id}-opt1"}
            )
    finally:
        _clear_dep(client, target)

    assert composed.status_code == 200, composed.text
    composed_body = composed.json()
    assert composed_body["stops"], "the outage produced a tour with no stops"
    assert executor.stop_calls, "compose refused instead of writing on estimated legs"

    composed_rows = {r["kind"]: r for r in composed_body["degradations"]}
    for row in composed_body["degradations"]:
        assert isinstance(row.get("human"), str) and row["human"], row

    # THE TRAVELLER'S SENTENCE, pinned verbatim. The phone itinerary and the workbench
    # panel both render it straight from here, so it must read alone and name nothing
    # internal. This route rebuilds its walk itself instead of planning one, so it is a
    # genuinely separate chance to ship an unlabelled estimate.
    assert "walking_times_estimated" in composed_rows, composed_body["degradations"]
    assert composed_rows["walking_times_estimated"]["human"] == (
        "Walking times between stops are estimates, not measured routes, so the tour "
        "may run a little longer or shorter than it says."
    )
    assert composed_rows["walking_times_estimated"]["component"] == "trips.compose_trip"

    # And the one call an outage can hard-fail is labelled rather than refusing. A 503
    # here would be the two-answers-to-one-outage this resolves: it arrives AFTER the
    # traveller has chosen a route, so refusing takes tour writing down app-wide for as
    # long as the container takes to come back.
    assert "routing_version_unavailable" in composed_rows, composed_body["degradations"]
    assert composed_rows["routing_version_unavailable"]["error_type"] == "RuntimeError"


@needs_neo4j
class TestComposeTripEndpoint:
    @pytest.fixture()
    def fresh_trip(self, client):
        resp = client.post("/api/v1/trips/generate", json=_body(NOLENS_PROFILE_ID))
        assert resp.status_code == 201, resp.text
        return resp.json()

    def _override(self, client, dep, value):
        return _override_dep(client, dep, value)

    def _clear(self, client, target):
        _clear_dep(client, target)


    def test_compose_persists_marker_narration_with_fresh_stop_ids(
        self, client, live_neo4j, fresh_trip
    ):
        trip_id = fresh_trip["trip_id"]
        target = self._override(
            client, "get_premium_compose_executor", _MarkerAuthoringExecutor()
        )
        try:
            resp = client.post(
                f"/api/v1/trips/{trip_id}/compose", json={"route_id": f"{trip_id}-opt1"}
            )
        finally:
            self._clear(client, target)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["trip_id"] == trip_id
        assert data["route_id"] == f"{trip_id}-opt1"
        assert data["attempts"] == 1
        assert len(data["stops"]) == len(fresh_trip["stops"])
        # The composed marker landed in the persisted stop-0 narration...
        assert data["stops"][0]["narration"].startswith(COMPOSE_MARKER)
        # ...and the DB agrees: fresh items, marker narration, NO audio fields.
        with live_neo4j.session() as s:
            rows = s.run(
                "MATCH (t:Trip {id: $tid})-[:HAS_STOP]->(i:ItineraryItem) "
                "RETURN i.id AS id, i.narration AS narration, i.audio_url AS audio "
                "ORDER BY i.sort_order",
                tid=trip_id,
            ).data()
            composed_route = s.run(
                "MATCH (t:Trip {id: $tid}) RETURN t.composed_route_id AS rid", tid=trip_id
            ).single()["rid"]
        assert [r["id"] for r in rows] == [st["stop_id"] for st in data["stops"]]
        assert rows[0]["narration"].startswith(COMPOSE_MARKER)
        assert all(r["audio"] is None for r in rows)
        assert composed_route == f"{trip_id}-opt1"

    def test_compose_persists_extra_narration_traceable_to_extra_beats(
        self, client, live_neo4j, fresh_trip, snapshot
    ):
        """KE2: /compose stitches each stop's overflow corpus beats into
        ``extra_narration`` DETERMINISTICALLY (no LLM/VERIFY — the extras are
        faithful curated beats). The persisted ItineraryItems must carry:
        non-empty extra_narration exactly for stops WITH extra_beat_ids, None for
        stops without, and text drawn ONLY from those extra beats' script_body."""
        trip_id = fresh_trip["trip_id"]
        from src.tour.generation import split_sentences

        resp = client.post(
            f"/api/v1/trips/{trip_id}/compose", json={"route_id": f"{trip_id}-opt1"}
        )
        assert resp.status_code == 200, resp.text

        with live_neo4j.session() as s:
            items = s.run(
                """
                MATCH (t:Trip {id: $tid})-[:HAS_STOP]->(item:ItineraryItem)
                RETURN item.beat_ids AS beat_ids,
                       item.extra_beat_ids AS extra_beat_ids,
                       item.extra_narration AS extra_narration
                ORDER BY item.sort_order
                """,
                tid=trip_id,
            ).data()

        beats_by_id = {
            ref.id: ref for refs in snapshot.beats_by_poi.values() for ref in refs
        }

        def _stitch(beat_ids):
            # Same deterministic stitch the endpoint uses: each extra beat's body
            # split into sentences and space-joined, in extra_beat_ids order.
            sents: list[str] = []
            for bid in beat_ids:
                ref = beats_by_id.get(bid)
                if ref and ref.script_body:
                    sents.extend(split_sentences(ref.script_body))
            return " ".join(sents)

        saw_extras = False
        for it in items:
            extras = it["extra_beat_ids"] or []
            if extras:
                saw_extras = True
                assert it["extra_narration"], (
                    "a stop WITH extra_beat_ids must carry a non-empty extra_narration"
                )
                # extra_narration is EXACTLY the deterministic stitch of THIS stop's
                # extra beats' script_body — no LLM invention, only corpus text, and
                # consistent with the persisted extra_beat_ids order.
                assert it["extra_narration"] == _stitch(extras), (
                    "extra_narration must be the deterministic stitch of its extra beats"
                )
                # Traceability, the human-readable way: each contributing extra beat's
                # (normalized) body is a substring of the narration.
                for bid in extras:
                    ref = beats_by_id.get(bid)
                    if ref and ref.script_body:
                        body = " ".join(split_sentences(ref.script_body))
                        assert body in it["extra_narration"], (
                            f"extra beat {bid} body not found verbatim in extra_narration"
                        )
            else:
                assert it["extra_narration"] is None, (
                    "a stop with NO extra_beat_ids must have a null extra_narration"
                )
        assert saw_extras, "the dense Île walk must overflow ≥1 stop -> extras to voice"
        # The compose response surfaces the same extra_narration it persisted.
        for stop in resp.json()["stops"]:
            if stop.get("extra_beat_ids"):
                assert stop.get("extra_narration")

    def test_second_compose_is_conflict(self, client, fresh_trip):
        trip_id = fresh_trip["trip_id"]
        first = client.post(
            f"/api/v1/trips/{trip_id}/compose", json={"route_id": f"{trip_id}-opt1"}
        )
        assert first.status_code == 200, first.text
        second = client.post(
            f"/api/v1/trips/{trip_id}/compose", json={"route_id": f"{trip_id}-opt1"}
        )
        assert second.status_code == 409
        assert second.json()["detail"]["reason"] == "already_composed"

    def test_unknown_route_id_and_trip_are_404(self, client, fresh_trip):
        trip_id = fresh_trip["trip_id"]
        bad_opt = client.post(
            f"/api/v1/trips/{trip_id}/compose", json={"route_id": f"{trip_id}-opt99"}
        )
        assert bad_opt.status_code == 404
        no_trip = client.post(
            "/api/v1/trips/no-such-trip/compose", json={"route_id": "no-such-trip-opt1"}
        )
        assert no_trip.status_code == 404

    def test_refused_flavour_is_422_and_leaves_trip_untouched(
        self, client, live_neo4j, fresh_trip
    ):
        """A flavour VERIFY refuses must never reach Neo4j.

        The refusal is triggered through the gate the per-stop path runs TODAY —
        source traceability, via an authored sentence citing a beat that is not in
        the grounded source. It used to be triggered through the entailment checker,
        which the whole-tour composer took as an injected dependency; the per-stop
        finalizer does not accept one yet, so injecting a rejecting checker here
        would assert nothing at all. Restoring the real faithfulness entailment and
        the coverage baseline on this path is the NEXT step of the ledger (A4,
        AC-5), and until it lands the persisted path's anti-hallucination gate is
        the structural half only. What this test pins either way is the part that
        matters most: a refusal costs the trip nothing.
        """
        trip_id = fresh_trip["trip_id"]

        def narrations():
            with live_neo4j.session() as s:
                return s.run(
                    "MATCH (t:Trip {id: $tid})-[:HAS_STOP]->(i:ItineraryItem) "
                    "RETURN i.id AS id, i.narration AS narration ORDER BY i.sort_order",
                    tid=trip_id,
                ).data()

        before = narrations()
        target = self._override(
            client, "get_premium_compose_executor", _HallucinatingExecutor()
        )
        try:
            resp = client.post(
                f"/api/v1/trips/{trip_id}/compose", json={"route_id": f"{trip_id}-opt1"}
            )
        finally:
            self._clear(client, target)
        assert resp.status_code == 422, resp.text
        detail = resp.json()["detail"]
        assert detail["reason"] == "compose_verification_failed"
        # One physical call per stop and no retry, so the count the phone reads is 1.
        assert detail["attempts"] == 1
        assert detail["untraceable"] > 0
        # The refusal left the trip exactly as generated — same items, same
        # narration, and no composed_route_id (another flavour can be tried).
        assert narrations() == before
        with live_neo4j.session() as s:
            rid = s.run(
                "MATCH (t:Trip {id: $tid}) RETURN t.composed_route_id AS rid", tid=trip_id
            ).single()["rid"]
        assert rid is None

    def test_generate_persists_per_flavour_anchor_identity(self, live_neo4j, fresh_trip):
        """C9f-i: options_json entries are per-flavour dicts carrying the C9
        exempt-anchor identity ({poi_ids, start_anchor_poi_id, fixed_end_poi_id}),
        so /compose restores the SAME exempt set the greedy used (pois[0] is not
        the start-anchor after Held-Karp). fresh_trip is an open walk, so at least
        one flavour records a positional start-anchor."""
        trip_id = fresh_trip["trip_id"]
        with live_neo4j.session() as s:
            from src.api.crud.trips import get_trip_compose_inputs

            options = get_trip_compose_inputs(s, trip_id)["options"]
        assert options and all(isinstance(e, dict) for e in options)
        for e in options:
            assert set(e) >= {"poi_ids", "start_anchor_poi_id", "fixed_end_poi_id"}
            if e["start_anchor_poi_id"] is not None:
                assert e["start_anchor_poi_id"] in e["poi_ids"]
            if e["fixed_end_poi_id"] is not None:
                assert e["fixed_end_poi_id"] in e["poi_ids"]
        # Not vacuously all-None: an open walk seats a positional start-anchor.
        assert any(e["start_anchor_poi_id"] is not None for e in options)

    def test_composing_a_numbered_option_uses_that_option(self, client, live_neo4j, fresh_trip):
        """The number in the request picks the walk, and an absent number is refused.

        Composes the LAST walk that was offered, so "always composed the first one"
        cannot pass whenever more than one is offered, and asks for one past the end
        to prove a number nobody was given is refused rather than quietly rounded down
        to a walk the traveller did not pick.
        """
        trip_id = fresh_trip["trip_id"]
        with live_neo4j.session() as s:
            from src.api.crud.trips import get_trip_compose_inputs

            stored = get_trip_compose_inputs(s, trip_id)
        options = stored["options"]
        assert options, "a saved trip must record the walks it offered"

        past_the_end = client.post(
            f"/api/v1/trips/{trip_id}/compose",
            json={"route_id": f"{trip_id}-opt{len(options) + 1}"},
        )
        assert past_the_end.status_code == 404, past_the_end.text

        resp = client.post(
            f"/api/v1/trips/{trip_id}/compose",
            json={"route_id": f"{trip_id}-opt{len(options)}"},
        )
        assert resp.status_code == 200, resp.text
        # options entries are per-flavour dicts of everything generate decided.
        assert [st["poi_id"] for st in resp.json()["stops"]] == options[-1]["poi_ids"]
