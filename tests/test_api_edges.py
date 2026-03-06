"""Integration tests for edge/relationship CRUD endpoints.

Tests POST/GET/PUT/DELETE /api/v1/edges/{rel_type}.
Requires a running Neo4j instance.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.schema.constraints import apply_all
from tests.conftest import needs_neo4j


@pytest.fixture(scope="module")
def clean_driver():
    """Create a driver with a clean DB + schema constraints."""
    from src.connection import create_driver

    d = create_driver()
    with d.session() as s:
        s.run("MATCH (n) DETACH DELETE n")
    apply_all(d)
    yield d
    d.close()


@pytest.fixture(scope="module")
def client(clean_driver):
    """TestClient backed by a clean Neo4j database (no seed data)."""
    app = create_app()
    with TestClient(app) as c:
        yield c


def _create_user(client, email: str) -> dict:
    """Helper: create a User and return the response JSON."""
    resp = client.post("/api/v1/nodes/User", json={"email": email})
    assert resp.status_code == 201
    return resp.json()


def _create_profile(client, display_name: str) -> dict:
    """Helper: create a Profile and return the response JSON."""
    resp = client.post("/api/v1/nodes/Profile", json={"display_name": display_name})
    assert resp.status_code == 201
    return resp.json()


def _create_lens(client, name: str, display_label: str) -> dict:
    """Helper: create a Lens and return the response JSON."""
    resp = client.post(
        "/api/v1/nodes/Lens", json={"name": name, "display_label": display_label}
    )
    assert resp.status_code == 201
    return resp.json()


def _create_edge(client, rel_type: str, source: dict, target: dict, props=None) -> dict:
    """Helper: create an edge and return the response JSON."""
    body = {
        "source": {"label": source["labels"][0], "id": source["id"]},
        "target": {"label": target["labels"][0], "id": target["id"]},
    }
    if props:
        body["properties"] = props
    resp = client.post(f"/api/v1/edges/{rel_type}", json=body)
    assert resp.status_code == 201
    return resp.json()


# ── Create edge ──


@needs_neo4j
class TestCreateEdge:
    def test_returns_201(self, client):
        user = _create_user(client, "edge-create-201@test.com")
        profile = _create_profile(client, "Edge Creator")
        resp = client.post("/api/v1/edges/HAS_PROFILE", json={
            "source": {"label": "User", "id": user["id"]},
            "target": {"label": "Profile", "id": profile["id"]},
        })
        assert resp.status_code == 201

    def test_response_has_generated_id(self, client):
        user = _create_user(client, "edge-id@test.com")
        profile = _create_profile(client, "ID Test")
        edge = _create_edge(client, "HAS_PROFILE", user, profile)
        assert "id" in edge
        assert len(edge["id"]) > 10  # UUID

    def test_response_has_correct_type(self, client):
        user = _create_user(client, "edge-type@test.com")
        profile = _create_profile(client, "Type Test")
        edge = _create_edge(client, "HAS_PROFILE", user, profile)
        assert edge["type"] == "HAS_PROFILE"

    def test_response_has_source_and_target(self, client):
        user = _create_user(client, "edge-src-tgt@test.com")
        profile = _create_profile(client, "Src Tgt Test")
        edge = _create_edge(client, "HAS_PROFILE", user, profile)
        assert edge["source_id"] == user["id"]
        assert edge["target_id"] == profile["id"]

    def test_edge_properties_are_stored(self, client):
        user = _create_user(client, "edge-props@test.com")
        profile = _create_profile(client, "Props Test")
        edge = _create_edge(
            client, "HAS_PROFILE", user, profile, props={"role": "primary"}
        )
        assert edge["properties"]["role"] == "primary"

    def test_created_at_is_set(self, client):
        user = _create_user(client, "edge-time@test.com")
        profile = _create_profile(client, "Time Test")
        edge = _create_edge(client, "HAS_PROFILE", user, profile)
        assert "created_at" in edge["properties"]

    def test_source_not_found_returns_404(self, client):
        profile = _create_profile(client, "Orphan Target")
        resp = client.post("/api/v1/edges/HAS_PROFILE", json={
            "source": {"label": "User", "id": "does-not-exist"},
            "target": {"label": "Profile", "id": profile["id"]},
        })
        assert resp.status_code == 404

    def test_target_not_found_returns_404(self, client):
        user = _create_user(client, "edge-no-target@test.com")
        resp = client.post("/api/v1/edges/HAS_PROFILE", json={
            "source": {"label": "User", "id": user["id"]},
            "target": {"label": "Profile", "id": "does-not-exist"},
        })
        assert resp.status_code == 404

    def test_invalid_rel_type_returns_422(self, client):
        resp = client.post("/api/v1/edges/FAKE_REL", json={
            "source": {"label": "User", "id": "x"},
            "target": {"label": "Profile", "id": "y"},
        })
        assert resp.status_code == 422


# ── List edges ──


@needs_neo4j
class TestListEdges:
    def test_list_returns_created_edges(self, client):
        user = _create_user(client, "edge-list@test.com")
        profile1 = _create_profile(client, "List P1")
        profile2 = _create_profile(client, "List P2")
        _create_edge(client, "PREFERS_LENS", user, profile1)
        # Use a different rel type to isolate test
        lens1 = _create_lens(client, "list_lens_1", "List Lens 1")
        lens2 = _create_lens(client, "list_lens_2", "List Lens 2")
        _create_edge(client, "TAGGED_WITH", profile1, lens1)
        _create_edge(client, "TAGGED_WITH", profile2, lens2)

        resp = client.get("/api/v1/edges/TAGGED_WITH")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 2

    def test_pagination_limit(self, client):
        resp = client.get("/api/v1/edges/HAS_PROFILE?limit=1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) <= 1
        assert data["limit"] == 1

    def test_pagination_skip(self, client):
        resp = client.get("/api/v1/edges/HAS_PROFILE?skip=1000")
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    def test_response_shape(self, client):
        resp = client.get("/api/v1/edges/HAS_PROFILE")
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "skip" in data
        assert "limit" in data
        if data["items"]:
            item = data["items"][0]
            assert "id" in item
            assert "type" in item
            assert "source_id" in item
            assert "target_id" in item
            assert "properties" in item


# ── Get edge ──


@needs_neo4j
class TestGetEdge:
    def test_get_existing_edge(self, client):
        user = _create_user(client, "edge-get@test.com")
        profile = _create_profile(client, "Get Test")
        edge = _create_edge(client, "HAS_PROFILE", user, profile)
        resp = client.get(f"/api/v1/edges/HAS_PROFILE/{edge['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == edge["id"]

    def test_get_nonexistent_returns_404(self, client):
        resp = client.get("/api/v1/edges/HAS_PROFILE/does-not-exist")
        assert resp.status_code == 404

    def test_404_message_includes_type_and_id(self, client):
        resp = client.get("/api/v1/edges/HAS_PROFILE/nonexistent-id")
        assert resp.status_code == 404
        assert "HAS_PROFILE" in resp.json()["detail"]
        assert "nonexistent-id" in resp.json()["detail"]


# ── Update edge ──


@needs_neo4j
class TestUpdateEdge:
    def test_update_property(self, client):
        user = _create_user(client, "edge-update@test.com")
        profile = _create_profile(client, "Update Test")
        edge = _create_edge(client, "HAS_PROFILE", user, profile)
        resp = client.put(
            f"/api/v1/edges/HAS_PROFILE/{edge['id']}",
            json={"properties": {"weight": 0.8}},
        )
        assert resp.status_code == 200
        assert resp.json()["properties"]["weight"] == 0.8

    def test_update_preserves_other_fields(self, client):
        user = _create_user(client, "edge-preserve@test.com")
        profile = _create_profile(client, "Preserve Test")
        edge = _create_edge(
            client, "HAS_PROFILE", user, profile, props={"role": "primary"}
        )
        resp = client.put(
            f"/api/v1/edges/HAS_PROFILE/{edge['id']}",
            json={"properties": {"weight": 0.5}},
        )
        assert resp.status_code == 200
        props = resp.json()["properties"]
        assert props["role"] == "primary"
        assert props["weight"] == 0.5

    def test_update_nonexistent_returns_404(self, client):
        resp = client.put(
            "/api/v1/edges/HAS_PROFILE/does-not-exist",
            json={"properties": {"weight": 1.0}},
        )
        assert resp.status_code == 404

    def test_update_empty_properties_is_noop(self, client):
        user = _create_user(client, "edge-noop@test.com")
        profile = _create_profile(client, "Noop Test")
        edge = _create_edge(client, "HAS_PROFILE", user, profile)
        resp = client.put(
            f"/api/v1/edges/HAS_PROFILE/{edge['id']}",
            json={"properties": {}},
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == edge["id"]


# ── Delete edge ──


@needs_neo4j
class TestDeleteEdge:
    def test_delete_returns_success(self, client):
        user = _create_user(client, "edge-del@test.com")
        profile = _create_profile(client, "Del Test")
        edge = _create_edge(client, "HAS_PROFILE", user, profile)
        resp = client.delete(f"/api/v1/edges/HAS_PROFILE/{edge['id']}")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        assert resp.json()["id"] == edge["id"]

    def test_deleted_edge_is_gone(self, client):
        user = _create_user(client, "edge-gone@test.com")
        profile = _create_profile(client, "Gone Test")
        edge = _create_edge(client, "HAS_PROFILE", user, profile)
        client.delete(f"/api/v1/edges/HAS_PROFILE/{edge['id']}")
        resp = client.get(f"/api/v1/edges/HAS_PROFILE/{edge['id']}")
        assert resp.status_code == 404

    def test_delete_nonexistent_returns_404(self, client):
        resp = client.delete("/api/v1/edges/HAS_PROFILE/does-not-exist")
        assert resp.status_code == 404

    def test_delete_does_not_remove_nodes(self, client):
        user = _create_user(client, "edge-keep-nodes@test.com")
        profile = _create_profile(client, "Keep Nodes")
        edge = _create_edge(client, "HAS_PROFILE", user, profile)
        client.delete(f"/api/v1/edges/HAS_PROFILE/{edge['id']}")
        # Both nodes should still exist
        assert client.get(f"/api/v1/nodes/User/{user['id']}").status_code == 200
        assert client.get(f"/api/v1/nodes/Profile/{profile['id']}").status_code == 200


# ── Full edge lifecycle ──


@needs_neo4j
class TestFullEdgeLifecycle:
    def test_edge_lifecycle(self, client):
        """Create nodes → Create edge → Read → Update → Read → Delete → Read (404)."""
        # Create nodes
        user = _create_user(client, "lifecycle-edge@test.com")
        profile = _create_profile(client, "Lifecycle Edge")

        # Create edge
        edge = _create_edge(client, "HAS_PROFILE", user, profile)
        edge_id = edge["id"]
        assert edge["type"] == "HAS_PROFILE"
        assert edge["source_id"] == user["id"]
        assert edge["target_id"] == profile["id"]

        # Read
        fetched = client.get(f"/api/v1/edges/HAS_PROFILE/{edge_id}").json()
        assert fetched["id"] == edge_id

        # Update
        updated = client.put(
            f"/api/v1/edges/HAS_PROFILE/{edge_id}",
            json={"properties": {"role": "primary", "weight": 1.0}},
        ).json()
        assert updated["properties"]["role"] == "primary"
        assert updated["properties"]["weight"] == 1.0

        # Read again — confirm update persisted
        fetched2 = client.get(f"/api/v1/edges/HAS_PROFILE/{edge_id}").json()
        assert fetched2["properties"]["role"] == "primary"

        # Delete
        del_resp = client.delete(f"/api/v1/edges/HAS_PROFILE/{edge_id}")
        assert del_resp.json()["deleted"] is True

        # Read again — confirm gone
        assert client.get(f"/api/v1/edges/HAS_PROFILE/{edge_id}").status_code == 404
