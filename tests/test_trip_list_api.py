"""Unit tests for GET /api/v1/trips endpoint.

These tests use the FastAPI TestClient with mocked Neo4j interactions
via seeded data. Integration tests that need real Neo4j are skipped
when the database is unavailable.
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
class TestListTripsEndpoint:
    """Integration tests for GET /api/v1/trips endpoint."""

    def test_list_trips_for_profile_returns_trips(self, client, mom_profile_id):
        """After generating a trip, GET /trips returns it."""
        # Generate a trip first
        body = _make_request_body(mom_profile_id)
        gen_resp = client.post("/api/v1/trips/generate", json=body)
        assert gen_resp.status_code == 201

        # List trips
        resp = client.get(f"/api/v1/trips?profile_id={mom_profile_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1

        # Verify the generated trip is in the list
        trip_ids = [t["trip_id"] for t in data]
        assert gen_resp.json()["trip_id"] in trip_ids

    def test_list_trips_for_profile_empty(self, client, seeded_driver):
        """A profile with no trips returns an empty list."""
        # Create a fresh profile with no trips
        with seeded_driver.session(database=get_database()) as s:
            s.run(
                """
                CREATE (p:Profile {
                    id: 'profile-no-trips',
                    display_name: 'Empty User'
                })
                """
            )

        resp = client.get("/api/v1/trips?profile_id=profile-no-trips")
        assert resp.status_code == 200
        data = resp.json()
        assert data == []

    def test_list_trips_includes_stops_with_poi_and_lens(self, client, mom_profile_id):
        """Trips in the list include full stop details with POI and lens data."""
        # Generate a trip to ensure at least one exists
        body = _make_request_body(mom_profile_id)
        gen_resp = client.post("/api/v1/trips/generate", json=body)
        assert gen_resp.status_code == 201
        generated_trip_id = gen_resp.json()["trip_id"]

        # List and find this trip
        resp = client.get(f"/api/v1/trips?profile_id={mom_profile_id}")
        assert resp.status_code == 200
        data = resp.json()

        trip = next((t for t in data if t["trip_id"] == generated_trip_id), None)
        assert trip is not None
        assert trip["total_stops"] > 0
        assert len(trip["stops"]) == trip["total_stops"]

        # Verify stop fields
        stop = trip["stops"][0]
        assert "sort_order" in stop
        assert "poi_id" in stop
        assert "poi_name" in stop
        assert "lat" in stop
        assert "lng" in stop
        assert "beat_id" in stop
        assert "lens_name" in stop
        assert "lens_display" in stop
        assert "duration_min" in stop
        assert "importance_tier" in stop
        assert "start_time" in stop

    def test_list_trips_requires_valid_profile_id(self, client):
        """A nonexistent profile returns 404."""
        resp = client.get("/api/v1/trips?profile_id=nonexistent-profile-999")
        assert resp.status_code == 404
