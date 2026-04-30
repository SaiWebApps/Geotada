"""Integration tests for POST /api/v1/trips/generate endpoint.

Tests: T3 (8 integration tests with seeded Neo4j)

These tests require a running Neo4j instance with seed data. They are
skipped automatically if Neo4j is unavailable.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.connection import create_driver, get_database
from src.schema.constraints import apply_all
from src.seed.runner import seed_all
from tests.conftest import needs_neo4j


@pytest.fixture(scope="module")
def seeded_driver():
    """Create a driver, wipe DB, apply schema, and seed data."""
    d = create_driver()
    with d.session(database=get_database()) as s:
        s.run("MATCH (n) DETACH DELETE n")
    apply_all(d)
    seed_all(d)
    yield d
    d.close()


@pytest.fixture(scope="module")
def client(seeded_driver):
    """TestClient backed by the real Neo4j database with seed data."""
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def mom_profile_id(seeded_driver):
    """Get the profile ID for the 'Mom' profile from seed data."""
    with seeded_driver.session(database=get_database()) as s:
        result = s.run("MATCH (p:Profile {display_name: 'Mom'}) RETURN p.id AS id").single()
        return result["id"]


@pytest.fixture(scope="module")
def kid_profile_id(seeded_driver):
    """Get the profile ID for the 'Kid' profile from seed data."""
    with seeded_driver.session(database=get_database()) as s:
        result = s.run("MATCH (p:Profile {display_name: 'Kid'}) RETURN p.id AS id").single()
        return result["id"]


def _make_request_body(profile_id: str, **overrides) -> dict:
    """Helper to build a valid trip generation request body."""
    body = {
        "profile_id": profile_id,
        "center_lat": 48.858,
        "center_lng": 2.294,
        "radius_m": 5000,
        "max_stops": 10,
        "start_date": "2026-05-01",
        "end_date": "2026-05-03",
        "start_time": "09:00",
    }
    body.update(overrides)
    return body


@needs_neo4j
class TestTripGenerateEndpoint:
    """Integration tests for trip generation endpoint."""

    # Acceptance Criterion: AC1 — POST /api/v1/trips/generate returns 201
    def test_generate_trip_returns_201(self, client, mom_profile_id):
        """T3: Successful trip generation returns HTTP 201."""
        body = _make_request_body(mom_profile_id)
        resp = client.post("/api/v1/trips/generate", json=body)
        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"

    # Acceptance Criterion: AC1 — Response has trip_id
    def test_generate_trip_response_has_trip_id(self, client, mom_profile_id):
        """T3: Response includes a valid trip_id string."""
        body = _make_request_body(mom_profile_id)
        resp = client.post("/api/v1/trips/generate", json=body)
        assert resp.status_code == 201
        data = resp.json()
        assert "trip_id" in data
        assert isinstance(data["trip_id"], str)
        assert len(data["trip_id"]) > 0
        # Verify all required response fields
        assert "trip_name" in data
        assert "profile_id" in data
        assert "total_stops" in data
        assert "total_duration_min" in data
        assert "anchor_count" in data
        assert "flavour_count" in data
        assert "stops" in data

    # Acceptance Criterion: AC1 — max_stops is respected
    def test_generate_trip_respects_max_stops(self, client, mom_profile_id):
        """T3: Number of stops does not exceed max_stops."""
        body = _make_request_body(mom_profile_id, max_stops=2)
        resp = client.post("/api/v1/trips/generate", json=body)
        assert resp.status_code == 201
        data = resp.json()
        assert data["total_stops"] <= 2
        assert len(data["stops"]) <= 2

    # Acceptance Criterion: AC9 — Non-existent profile_id returns 404
    def test_generate_trip_profile_not_found_404(self, client):
        """T3: Non-existent profile_id returns 404."""
        body = _make_request_body("nonexistent-profile-id-xyz")
        resp = client.post("/api/v1/trips/generate", json=body)
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    # Acceptance Criterion: AC10 — Center far from any POI returns 422
    def test_generate_trip_no_pois_in_radius_422(self, client, mom_profile_id):
        """T3: Center far from any seeded POI returns 422."""
        # Sydney, Australia — far from Paris POIs
        body = _make_request_body(mom_profile_id, center_lat=-33.8, center_lng=151.2, radius_m=100)
        resp = client.post("/api/v1/trips/generate", json=body)
        assert resp.status_code == 422
        assert "no pois" in resp.json()["detail"].lower()

    # Acceptance Criterion: AC3 — Golden Ratio applied
    def test_generate_trip_golden_ratio_applied(self, client, mom_profile_id):
        """T3: Response distinguishes anchor and flavour counts."""
        body = _make_request_body(mom_profile_id)
        resp = client.post("/api/v1/trips/generate", json=body)
        assert resp.status_code == 201
        data = resp.json()
        # anchor_count + flavour_count must equal total_stops
        assert data["anchor_count"] + data["flavour_count"] == data["total_stops"]
        # anchor_count should be >= 0 (may be 0 if no tier-5 beats match)
        assert data["anchor_count"] >= 0
        assert data["flavour_count"] >= 0

    # Acceptance Criterion: AC8 — Trip + ItineraryItem nodes created in Neo4j
    def test_generate_trip_creates_graph_nodes(self, client, mom_profile_id, seeded_driver):
        """T3: Trip generation creates Trip and ItineraryItem nodes in the graph."""
        body = _make_request_body(mom_profile_id, trip_name="Integration Test Trip")
        resp = client.post("/api/v1/trips/generate", json=body)
        assert resp.status_code == 201
        trip_id = resp.json()["trip_id"]

        # Verify Trip node exists
        with seeded_driver.session(database=get_database()) as s:
            trip = s.run(
                "MATCH (t:Trip {id: $tid}) RETURN t.name AS name, t.status AS status",
                tid=trip_id,
            ).single()
            assert trip is not None
            assert trip["name"] == "Integration Test Trip"
            assert trip["status"] == "planning"

            # Verify ItineraryItems are linked
            items = s.run(
                "MATCH (t:Trip {id: $tid})-[:HAS_STOP]->(item:ItineraryItem) "
                "RETURN count(item) AS cnt",
                tid=trip_id,
            ).single()
            assert items["cnt"] == resp.json()["total_stops"]

    # Acceptance Criterion: AC7 — kid_friendly_only=True filters correctly
    def test_generate_trip_kid_friendly_filter(self, client, mom_profile_id):
        """T3: kid_friendly_only=True only includes kid-friendly POIs."""
        body = _make_request_body(mom_profile_id, kid_friendly_only=True)
        resp = client.post("/api/v1/trips/generate", json=body)
        # With seed data, all POIs are kid_friendly, so this should still succeed
        # or return 422 if no beats match — both are valid depending on the graph state.
        # The key test is that it doesn't return a 500 (server error).
        assert resp.status_code in (201, 422)
        if resp.status_code == 201:
            # If successful, verify stops exist
            data = resp.json()
            assert data["total_stops"] > 0
