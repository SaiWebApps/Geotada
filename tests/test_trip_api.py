"""Integration tests for POST /api/v1/trips/generate — real engine, live corpus.

Since M0b the endpoint runs the real tour engine (src/tour), whose density
gate refuses sparse areas (needs >=4 anchor candidates). The conftest test
instance (port 7688) only carries toy seed data (3 POIs / 5 beats), so these
tests run against the LIVE local Paris dev graph (port 7687) the way
tests/test_tour_golden_*.py do — parsing .env read-only (never mutating
os.environ) and overriding the app's session/driver dependencies.

Unlike the goldens these tests WRITE to the dev graph: a disposable test
Profile and the Trips/ItineraryItems the endpoint persists. Setup and
teardown both delete them, so a crashed run never accumulates residue.

The tour input mirrors fixtures/tour_golden/ile_oneway_90min.json (Pont Neuf
metro, 90 min, one-way) — a known-GREEN multi-stop start on the live corpus.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from neo4j import GraphDatabase
from neo4j.exceptions import AuthError, ServiceUnavailable

from src.api.app import create_app
from src.api.dependencies import get_driver, get_session
from src.tour.contract import TourInput
from src.tour.density import TourabilityRefusedError
from src.tour.routing_client import RoutingClient
from src.tour.selection import load_paris_corpus, select_k_routes, select_route
from tests.conftest import needs_neo4j
from tests.test_tour_golden_pdv import _parse_env_file  # same .env-read-only pattern

LENSED_PROFILE_ID = "m0b-trip-api-test-profile-lensed"
NOLENS_PROFILE_ID = "m0b-trip-api-test-profile-nolens"
PROFILE_IDS = [LENSED_PROFILE_ID, NOLENS_PROFILE_ID]
PROFILE_LENSES = ["hidden_history", "literary_heritage"]

# Same input as fixtures/tour_golden/ile_oneway_90min.json.
ILE_START = (48.8568, 2.3414)
ILE_DURATION_MIN = 90


def _live_driver():
    """Driver to the .env Neo4j (port 7687); None if unreachable.

    Bypasses the conftest test-instance fixture so the live Paris corpus is
    queried, not the toy-seeded test instance.
    """
    from pathlib import Path
    from urllib.parse import urlparse

    project_root = Path(__file__).resolve().parent.parent
    env = _parse_env_file(project_root / ".env")
    uri = env.get("NEO4J_URI", "")
    user = env.get("NEO4J_USER", "")
    password = env.get("NEO4J_PASSWORD", "")
    if not (uri and user and password):
        return None
    # Unlike the read-only goldens, this module WRITES through the driver.
    # If .env is in cloud mode (make use-cloud -> Aura), refuse: these tests
    # may only ever touch the local dev instance.
    if urlparse(uri).hostname not in ("localhost", "127.0.0.1"):
        return None
    try:
        d = GraphDatabase.driver(uri, auth=(user, password))
        d.verify_connectivity()
        return d
    except (ServiceUnavailable, AuthError, Exception):
        return None


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


@pytest.fixture(scope="module")
def live_neo4j():
    d = _live_driver()
    if d is None:
        pytest.skip(
            "Local Paris dev Neo4j unreachable (or .env points at a non-local "
            "database — these tests write, so they refuse anything but "
            "localhost). Start the dev instance with `make db-up`."
        )
    yield d
    d.close()


@pytest.fixture(scope="module")
def test_profiles(live_neo4j):
    """Disposable profiles on the live graph: one lensed, one without lenses."""
    _delete_test_artifacts(live_neo4j)  # clear residue from any crashed prior run
    with live_neo4j.session() as s:
        for pid in PROFILE_IDS:
            s.run(
                "MERGE (p:Profile {id: $pid}) SET p.display_name = 'M0b API Test'",
                pid=pid,
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
    with TestClient(app) as c:
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
                assert stop["band"] in ("dwell", "vignette")

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
    """POST /trips/preview (Phase 1.5d): engine narration, no profile, no persistence."""

    def test_preview_returns_per_stop_narration(self, client):
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
        assert data["stops"], "preview should return at least one stop"
        for stop in data["stops"]:
            assert stop["poi_name"]
            assert stop["narration"].strip(), "each stop must carry narration text"
        assert data["total_audio_min"] >= 1

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


class _MarkerComposeClient:
    """Deterministic composer: prepends a recognizable glue sentence —
    route-independent proof that the COMPOSED output was persisted."""

    def compose(self, request, attempt, prev_report):
        from src.tour.contract import Sentence
        from src.tour.generation import GLUE_PACING

        marker = Sentence(
            text=COMPOSE_MARKER, source_id=GLUE_PACING, source_type="glue", stop_idx=0
        )
        return (marker, *request.stitched.script)


class _RejectAllChecker:
    """Fails every entailment — forces the gate to refuse the flavour."""

    def entails(self, key_claims, sentence_text):
        return False


@needs_neo4j
class TestComposeTripEndpoint:
    @pytest.fixture()
    def fresh_trip(self, client):
        resp = client.post("/api/v1/trips/generate", json=_body(NOLENS_PROFILE_ID))
        assert resp.status_code == 201, resp.text
        return resp.json()

    def _override(self, client, dep, value):
        from src.api import dependencies

        target = getattr(dependencies, dep)
        client.app.dependency_overrides[target] = lambda: value
        return target

    def _clear(self, client, target):
        client.app.dependency_overrides.pop(target, None)

    def test_compose_persists_marker_narration_with_fresh_stop_ids(
        self, client, live_neo4j, fresh_trip
    ):
        trip_id = fresh_trip["trip_id"]
        target = self._override(client, "get_compose_client", _MarkerComposeClient())
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
        trip_id = fresh_trip["trip_id"]

        def narrations():
            with live_neo4j.session() as s:
                return s.run(
                    "MATCH (t:Trip {id: $tid})-[:HAS_STOP]->(i:ItineraryItem) "
                    "RETURN i.id AS id, i.narration AS narration ORDER BY i.sort_order",
                    tid=trip_id,
                ).data()

        before = narrations()
        target = self._override(client, "get_faithfulness_checker", _RejectAllChecker())
        try:
            resp = client.post(
                f"/api/v1/trips/{trip_id}/compose", json={"route_id": f"{trip_id}-opt1"}
            )
        finally:
            self._clear(client, target)
        assert resp.status_code == 422, resp.text
        detail = resp.json()["detail"]
        assert detail["reason"] == "compose_verification_failed"
        assert detail["attempts"] == 2
        assert detail["faithfulness"] > 0
        # The refusal left the trip exactly as generated — same items, same
        # narration, and no composed_route_id (another flavour can be tried).
        assert narrations() == before
        with live_neo4j.session() as s:
            rid = s.run(
                "MATCH (t:Trip {id: $tid}) RETURN t.composed_route_id AS rid", tid=trip_id
            ).single()["rid"]
        assert rid is None

    def test_second_option_composes_its_stored_pick(self, client, live_neo4j, fresh_trip):
        trip_id = fresh_trip["trip_id"]
        with live_neo4j.session() as s:
            from src.api.crud.trips import get_trip_compose_inputs

            stored = get_trip_compose_inputs(s, trip_id)
        options = stored["options"]
        if len(options) < 2:
            pytest.skip("this generation produced a single flavour — nothing to pick")
        resp = client.post(
            f"/api/v1/trips/{trip_id}/compose", json={"route_id": f"{trip_id}-opt2"}
        )
        assert resp.status_code == 200, resp.text
        assert [st["poi_id"] for st in resp.json()["stops"]] == options[1]
