"""Integration tests for Step 3: node CREATE endpoint.

Tests POST /api/v1/nodes/{label} for creating nodes.
Requires a running Neo4j instance.
"""

from __future__ import annotations

import pytest

from tests.conftest import needs_neo4j


# ── Create User ──


@needs_neo4j
class TestCreateUser:
    def test_returns_201(self, client):
        resp = client.post("/api/v1/nodes/User", json={"email": "new@test.com"})
        assert resp.status_code == 201

    def test_response_has_generated_id(self, client):
        resp = client.post("/api/v1/nodes/User", json={"email": "id-test@test.com"})
        data = resp.json()
        assert "id" in data
        assert len(data["id"]) > 10  # UUID

    def test_response_has_correct_label(self, client):
        resp = client.post("/api/v1/nodes/User", json={"email": "label@test.com"})
        assert "User" in resp.json()["labels"]

    def test_email_is_stored(self, client):
        resp = client.post("/api/v1/nodes/User", json={"email": "stored@test.com"})
        assert resp.json()["properties"]["email"] == "stored@test.com"

    def test_created_at_is_set(self, client):
        resp = client.post("/api/v1/nodes/User", json={"email": "time@test.com"})
        assert "created_at" in resp.json()["properties"]

    def test_node_is_retrievable_after_create(self, client):
        create_resp = client.post("/api/v1/nodes/User", json={"email": "fetch@test.com"})
        node_id = create_resp.json()["id"]
        get_resp = client.get(f"/api/v1/nodes/User/{node_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["properties"]["email"] == "fetch@test.com"


# ── Create POI (spatial point handling) ──


@needs_neo4j
class TestCreatePOI:
    def test_create_poi_with_lat_lng(self, client):
        resp = client.post("/api/v1/nodes/POI", json={
            "name": "Test Place",
            "latitude": 40.7128,
            "longitude": -74.0060,
        })
        assert resp.status_code == 201
        props = resp.json()["properties"]
        assert props["name"] == "Test Place"

    def test_poi_location_is_serialized(self, client):
        resp = client.post("/api/v1/nodes/POI", json={
            "name": "Geo Test",
            "latitude": 51.5074,
            "longitude": -0.1278,
        })
        loc = resp.json()["properties"]["location"]
        assert abs(loc["lat"] - 51.5074) < 0.001
        assert abs(loc["lng"] - (-0.1278)) < 0.001

    def test_poi_defaults_are_applied(self, client):
        resp = client.post("/api/v1/nodes/POI", json={
            "name": "Default Test",
            "latitude": 0.0,
            "longitude": 0.0,
        })
        props = resp.json()["properties"]
        assert props["kid_friendly"] == "yes"
        assert props["importance_tier"] == 1


# ── Create other node types ──


@needs_neo4j
class TestCreateOtherTypes:
    def test_create_profile(self, client):
        resp = client.post("/api/v1/nodes/Profile", json={"display_name": "Dad"})
        assert resp.status_code == 201
        assert resp.json()["properties"]["display_name"] == "Dad"

    def test_create_lens(self, client):
        resp = client.post("/api/v1/nodes/Lens", json={
            "name": "test_lens",
            "display_label": "Test Lens",
        })
        assert resp.status_code == 201

    def test_create_trip(self, client):
        resp = client.post("/api/v1/nodes/Trip", json={
            "name": "Rome 2026",
            "start_date": "2026-06-01",
            "end_date": "2026-06-07",
        })
        assert resp.status_code == 201
        assert resp.json()["properties"]["status"] == "planning"

    def test_create_narrative_beat(self, client):
        resp = client.post("/api/v1/nodes/NarrativeBeat", json={
            "script_body": "Once upon a time...",
        })
        assert resp.status_code == 201
        assert resp.json()["properties"]["version"] == 1


# ── Error cases ──


@needs_neo4j
class TestCreateErrors:
    def test_missing_required_field_returns_422(self, client):
        resp = client.post("/api/v1/nodes/User", json={})
        assert resp.status_code == 422

    def test_invalid_label_returns_422(self, client):
        resp = client.post("/api/v1/nodes/FakeLabel", json={"x": 1})
        assert resp.status_code == 422

    def test_node_count_increases(self, client):
        before = client.get("/api/v1/nodes/User").json()["total"]
        client.post("/api/v1/nodes/User", json={"email": "count@test.com"})
        after = client.get("/api/v1/nodes/User").json()["total"]
        assert after == before + 1
