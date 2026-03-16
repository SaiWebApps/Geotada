"""Integration tests for upload-related API changes.

Test 13: MERGE idempotency for POI creation.
Test 14: Beat traversal endpoint GET /graph/poi/{name}/beats.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.schema.constraints import apply_all
from src.seed.lenses import seed_lenses
from tests.conftest import needs_neo4j


@pytest.fixture(scope="module")
def clean_driver():
    """Create a driver with a clean DB + schema constraints + lenses."""
    from src.connection import create_driver

    d = create_driver()
    with d.session() as s:
        s.run("MATCH (n) DETACH DELETE n")
    apply_all(d)
    seed_lenses(d)
    yield d
    d.close()


@pytest.fixture(scope="module")
def client(clean_driver):
    """TestClient backed by a clean Neo4j database with lenses seeded."""
    app = create_app()
    with TestClient(app) as c:
        yield c


# ── Test 13: MERGE idempotency ──


@needs_neo4j
class TestMergeIdempotency:
    """POST same POI twice → second call returns same ID, no duplicate."""

    def test_poi_merge_returns_same_id(self, client):
        payload = {
            "name": "Merge Test POI",
            "latitude": 42.3601,
            "longitude": -71.0589,
            "short_description": "Test",
            "importance_tier": 1,
            "trigger_radius": 10,
            "typical_duration_min": 30,
            "kid_friendly": "yes",
        }
        resp1 = client.post("/api/v1/nodes/POI", json=payload)
        assert resp1.status_code == 201
        id1 = resp1.json()["id"]

        resp2 = client.post("/api/v1/nodes/POI", json=payload)
        assert resp2.status_code == 201
        id2 = resp2.json()["id"]

        assert id1 == id2, "MERGE should return the same node ID on duplicate POI name"

    def test_no_duplicate_poi_nodes(self, client):
        """After two POSTs with same name, only one POI node exists."""
        resp = client.get("/api/v1/nodes/POI?limit=200")
        items = resp.json()["items"]
        names = [i["properties"]["name"] for i in items]
        assert names.count("Merge Test POI") == 1

    def test_has_beat_edge_merge_idempotent(self, client):
        """POST same HAS_BEAT edge twice → same ID returned."""
        # Create a POI and a beat first
        poi_resp = client.post("/api/v1/nodes/POI", json={
            "name": "Edge Merge POI",
            "latitude": 42.36,
            "longitude": -71.06,
        })
        poi_id = poi_resp.json()["id"]

        beat_resp = client.post("/api/v1/nodes/NarrativeBeat", json={
            "script_body": "Edge merge test beat.",
        })
        beat_id = beat_resp.json()["id"]

        edge_payload = {
            "source": {"label": "POI", "id": poi_id},
            "target": {"label": "NarrativeBeat", "id": beat_id},
        }
        e1 = client.post("/api/v1/edges/HAS_BEAT", json=edge_payload)
        assert e1.status_code == 201
        eid1 = e1.json()["id"]

        e2 = client.post("/api/v1/edges/HAS_BEAT", json=edge_payload)
        assert e2.status_code == 201
        eid2 = e2.json()["id"]

        assert eid1 == eid2, "MERGE should return the same edge ID on duplicate HAS_BEAT"


# ── Test 14: Beat traversal endpoint ──


@needs_neo4j
class TestBeatTraversal:
    """GET /graph/poi/{name}/beats returns correct beat+lens data."""

    def test_returns_beats_for_seeded_poi(self, client):
        # Create POI
        client.post("/api/v1/nodes/POI", json={
            "name": "Traversal Test POI",
            "latitude": 42.36,
            "longitude": -71.06,
        })

        # Create 2 beats with different lenses
        beat1 = client.post("/api/v1/nodes/NarrativeBeat", json={
            "script_body": "Traversal beat one about history.",
            "version": 1,
            "active_status": "active",
            "duration_sec": 60,
        }).json()

        beat2 = client.post("/api/v1/nodes/NarrativeBeat", json={
            "script_body": "Traversal beat two about food.",
            "version": 1,
            "active_status": "active",
            "duration_sec": 180,
        }).json()

        # Get POI ID
        poi_list = client.get("/api/v1/nodes/POI?limit=200").json()
        poi = next(p for p in poi_list["items"] if p["properties"]["name"] == "Traversal Test POI")

        # Get lens IDs
        lens_list = client.get("/api/v1/nodes/Lens?limit=20").json()
        hh_lens = next(l for l in lens_list["items"] if l["properties"]["name"] == "hidden_history")
        fc_lens = next(l for l in lens_list["items"] if l["properties"]["name"] == "food_culinary")

        # Create HAS_BEAT edges
        client.post("/api/v1/edges/HAS_BEAT", json={
            "source": {"label": "POI", "id": poi["id"]},
            "target": {"label": "NarrativeBeat", "id": beat1["id"]},
        })
        client.post("/api/v1/edges/HAS_BEAT", json={
            "source": {"label": "POI", "id": poi["id"]},
            "target": {"label": "NarrativeBeat", "id": beat2["id"]},
        })

        # Create TAGGED_WITH edges
        client.post("/api/v1/edges/TAGGED_WITH", json={
            "source": {"label": "NarrativeBeat", "id": beat1["id"]},
            "target": {"label": "Lens", "id": hh_lens["id"]},
        })
        client.post("/api/v1/edges/TAGGED_WITH", json={
            "source": {"label": "NarrativeBeat", "id": beat2["id"]},
            "target": {"label": "Lens", "id": fc_lens["id"]},
        })

        # Now test the traversal endpoint
        resp = client.get("/api/v1/graph/poi/Traversal Test POI/beats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["poi_name"] == "Traversal Test POI"
        assert len(data["beats"]) == 2

        slugs = {b["lens_slug"] for b in data["beats"]}
        assert "hidden_history" in slugs
        assert "food_culinary" in slugs

    def test_returns_empty_for_unknown_poi(self, client):
        resp = client.get("/api/v1/graph/poi/NonExistentPOI/beats")
        assert resp.status_code == 200
        assert resp.json()["beats"] == []


# ── Test 15: name_variations on POI creation ──


@needs_neo4j
class TestNameVariations:
    """POST /nodes/POI with name_variations field."""

    def test_poi_with_name_variations(self, client):
        payload = {
            "name": "Name Var Test POI",
            "latitude": 42.361,
            "longitude": -71.059,
            "name_variations": ["Alt Name 1", "Alt Name 2"],
        }
        resp = client.post("/api/v1/nodes/POI", json=payload)
        assert resp.status_code == 201
        props = resp.json()["properties"]
        assert props["name_variations"] == ["Alt Name 1", "Alt Name 2"]

        # Confirm persistence via GET
        poi_list = client.get("/api/v1/nodes/POI?limit=200").json()
        match = next(
            p for p in poi_list["items"]
            if p["properties"]["name"] == "Name Var Test POI"
        )
        assert match["properties"]["name_variations"] == ["Alt Name 1", "Alt Name 2"]

    def test_poi_without_name_variations(self, client):
        payload = {
            "name": "No Var Test POI",
            "latitude": 42.362,
            "longitude": -71.058,
        }
        resp = client.post("/api/v1/nodes/POI", json=payload)
        assert resp.status_code == 201
        # Should not error — name_variations defaults to []

    def test_poi_with_invalid_name_variations(self, client):
        payload = {
            "name": "Invalid Var Test POI",
            "latitude": 42.363,
            "longitude": -71.057,
            "name_variations": [123, "valid"],
        }
        resp = client.post("/api/v1/nodes/POI", json=payload)
        assert resp.status_code == 422, "Non-string items in name_variations should be rejected"


# ── Existing tests continued ──


@needs_neo4j
class TestBeatTraversalDeprecated:
    """Test deprecated beat exclusion."""

    def test_excludes_deprecated_beats(self, client):
        # Create a POI with a deprecated beat
        client.post("/api/v1/nodes/POI", json={
            "name": "Deprecated Test POI",
            "latitude": 42.37,
            "longitude": -71.07,
        })

        beat = client.post("/api/v1/nodes/NarrativeBeat", json={
            "script_body": "This beat is deprecated.",
            "version": 1,
            "active_status": "deprecated",
            "duration_sec": 60,
        }).json()

        poi_list = client.get("/api/v1/nodes/POI?limit=200").json()
        poi = next(p for p in poi_list["items"] if p["properties"]["name"] == "Deprecated Test POI")

        lens_list = client.get("/api/v1/nodes/Lens?limit=20").json()
        lens = lens_list["items"][0]

        client.post("/api/v1/edges/HAS_BEAT", json={
            "source": {"label": "POI", "id": poi["id"]},
            "target": {"label": "NarrativeBeat", "id": beat["id"]},
        })
        client.post("/api/v1/edges/TAGGED_WITH", json={
            "source": {"label": "NarrativeBeat", "id": beat["id"]},
            "target": {"label": "Lens", "id": lens["id"]},
        })

        resp = client.get("/api/v1/graph/poi/Deprecated Test POI/beats")
        assert resp.status_code == 200
        assert len(resp.json()["beats"]) == 0, "Deprecated beats should be excluded"
