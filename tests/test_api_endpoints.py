"""Integration tests for Steps 1+2: graph endpoint + node read endpoints.

These tests use FastAPI's TestClient and require a running Neo4j instance
with seeded data. They are skipped automatically if Neo4j is unavailable.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.schema.constraints import apply_all
from src.seed.runner import seed_all
from tests.conftest import needs_neo4j


@pytest.fixture(scope="module")
def seeded_driver():
    """Create a driver, wipe DB, apply schema, and seed data."""
    from src.connection import create_driver

    d = create_driver()
    with d.session() as s:
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


# ── Graph endpoint ──


@needs_neo4j
class TestGraphEndpoint:
    def test_returns_200(self, client):
        resp = client.get("/api/v1/graph")
        assert resp.status_code == 200

    def test_response_has_nodes_and_edges(self, client):
        data = client.get("/api/v1/graph").json()
        assert "nodes" in data
        assert "edges" in data

    def test_contains_seeded_nodes(self, client):
        data = client.get("/api/v1/graph").json()
        assert len(data["nodes"]) == 43

    def test_contains_seeded_edges(self, client):
        data = client.get("/api/v1/graph").json()
        assert len(data["edges"]) == 53

    def test_nodes_have_required_fields(self, client):
        node = client.get("/api/v1/graph").json()["nodes"][0]
        assert "id" in node
        assert "label" in node
        assert "group" in node
        assert "properties" in node

    def test_edges_have_required_fields(self, client):
        edge = client.get("/api/v1/graph").json()["edges"][0]
        assert "id" in edge
        assert "from" in edge
        assert "to" in edge
        assert "label" in edge


# ── List nodes ──


@needs_neo4j
class TestListNodes:
    def test_list_users_returns_one(self, client):
        data = client.get("/api/v1/nodes/User").json()
        assert data["total"] == 1
        assert len(data["items"]) == 1

    def test_list_pois_returns_three(self, client):
        data = client.get("/api/v1/nodes/POI").json()
        assert data["total"] == 3

    def test_list_lenses_returns_twentynine(self, client):
        data = client.get("/api/v1/nodes/Lens").json()
        assert data["total"] == 29

    def test_pagination_limit(self, client):
        data = client.get("/api/v1/nodes/Lens?limit=2").json()
        assert data["total"] == 29
        assert len(data["items"]) == 2

    def test_pagination_skip(self, client):
        data = client.get("/api/v1/nodes/Lens?skip=10&limit=50").json()
        assert len(data["items"]) == 19  # 29 total, skip 10 = 19 left

    def test_response_shape(self, client):
        data = client.get("/api/v1/nodes/User").json()
        item = data["items"][0]
        assert "id" in item
        assert "labels" in item
        assert "properties" in item
        assert "User" in item["labels"]

    def test_user_has_email_property(self, client):
        item = client.get("/api/v1/nodes/User").json()["items"][0]
        assert item["properties"]["email"] == "testuser@ondoway.app"

    def test_poi_has_location_as_lat_lng(self, client):
        items = client.get("/api/v1/nodes/POI").json()["items"]
        eiffel = next(i for i in items if i["properties"]["name"] == "Eiffel Tower")
        loc = eiffel["properties"]["location"]
        assert "lat" in loc
        assert "lng" in loc


# ── Get single node ──


@needs_neo4j
class TestGetNode:
    def test_get_existing_user(self, client):
        user_id = client.get("/api/v1/nodes/User").json()["items"][0]["id"]
        resp = client.get(f"/api/v1/nodes/User/{user_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == user_id

    def test_get_existing_poi(self, client):
        items = client.get("/api/v1/nodes/POI").json()["items"]
        poi_id = items[0]["id"]
        resp = client.get(f"/api/v1/nodes/POI/{poi_id}")
        assert resp.status_code == 200
        assert "POI" in resp.json()["labels"]


# ── Error cases ──


@needs_neo4j
class TestErrorCases:
    def test_invalid_label_returns_422(self, client):
        resp = client.get("/api/v1/nodes/FakeLabel")
        assert resp.status_code == 422

    def test_nonexistent_id_returns_404(self, client):
        resp = client.get("/api/v1/nodes/User/does-not-exist")
        assert resp.status_code == 404

    def test_404_message_includes_label_and_id(self, client):
        resp = client.get("/api/v1/nodes/User/does-not-exist")
        detail = resp.json()["detail"]
        assert "User" in detail
        assert "does-not-exist" in detail
