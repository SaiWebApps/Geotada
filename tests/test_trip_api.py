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
from src.tour.routing_client import RoutingClient
from src.tour.selection import load_paris_corpus, select_route
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
        """The density gate's RED refusal maps to 422 (replaces the old
        'no POIs in radius' check). Sydney is far from every Paris POI."""
        body = _body(NOLENS_PROFILE_ID, center_lat=-33.8688, center_lng=151.2093)
        resp = client.post("/api/v1/trips/generate", json=body)
        assert resp.status_code == 422
        assert "sparse" in resp.json()["detail"].lower()
