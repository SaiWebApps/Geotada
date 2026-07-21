"""Regression: beat lookup must be scoped by POI node id, not by name.

``force_create`` deliberately allows two distinct POI nodes to share
(name, city_name). The name-keyed ``/graph/poi/{name}/beats`` route therefore
returns the UNION of both nodes' beats, which made the workbench's conflict
detection deprecate an unrelated POI's beat and made the merge preview try to
delete a HAS_BEAT edge that never existed on the source node.

``/graph/poi/by-id/{poi_id}/beats`` returns only the queried node's beats.
"""

from __future__ import annotations

import uuid

import pytest

from tests.conftest import needs_neo4j


@pytest.fixture
def twin_name() -> str:
    """A name unique per test — the DB is only cleaned per-module."""
    return f"Twin Name POI {uuid.uuid4().hex[:8]}"


@pytest.fixture
def twin_pois(client, twin_name):
    """Two force_create'd POIs sharing a name, each with its own active beat."""
    base = {
        "name": twin_name,
        "city_name": "paris",
        "latitude": 48.8600,
        "longitude": 2.3400,
        "importance_tier": 1,
        "force_create": True,
    }
    poi_a = client.post("/api/v1/nodes/POI", json=base).json()
    poi_b = client.post(
        "/api/v1/nodes/POI",
        json={**base, "latitude": 48.8700, "longitude": 2.3500},
    ).json()
    assert poi_a["id"] != poi_b["id"], "force_create must yield two distinct nodes"

    beats = {}
    for key, poi in (("a", poi_a), ("b", poi_b)):
        beat = client.post(
            "/api/v1/nodes/NarrativeBeat",
            json={
                "script_body": f"Beat belonging to twin {key}.",
                "version": 1,
                "active_status": "active",
                "duration_sec": 60,
            },
        ).json()
        resp = client.post(
            "/api/v1/edges/HAS_BEAT",
            json={
                "source": {"label": "POI", "id": poi["id"]},
                "target": {"label": "NarrativeBeat", "id": beat["id"]},
            },
        )
        assert resp.status_code == 201
        beats[key] = beat

    return poi_a, poi_b, beats["a"], beats["b"]


@needs_neo4j
class TestPoiBeatsById:
    def test_id_scoped_lookup_returns_only_that_nodes_beats(self, client, twin_pois):
        poi_a, poi_b, beat_a, beat_b = twin_pois

        resp_a = client.get(f"/api/v1/graph/poi/by-id/{poi_a['id']}/beats")
        assert resp_a.status_code == 200
        ids_a = {b["id"] for b in resp_a.json()["beats"]}
        assert ids_a == {beat_a["id"]}, f"leaked the twin's beat: {ids_a}"

        resp_b = client.get(f"/api/v1/graph/poi/by-id/{poi_b['id']}/beats")
        assert resp_b.status_code == 200
        ids_b = {b["id"] for b in resp_b.json()["beats"]}
        assert ids_b == {beat_b["id"]}, f"leaked the twin's beat: {ids_b}"

    def test_name_keyed_route_conflates_the_twins(self, client, twin_pois, twin_name):
        """Documents the defect the id route exists to avoid (back-compat path)."""
        _poi_a, _poi_b, beat_a, beat_b = twin_pois

        resp = client.get(f"/api/v1/graph/poi/{twin_name}/beats?city_name=paris")
        assert resp.status_code == 200
        ids = {b["id"] for b in resp.json()["beats"]}
        assert ids == {beat_a["id"], beat_b["id"]}

    def test_unknown_id_returns_empty(self, client):
        resp = client.get("/api/v1/graph/poi/by-id/no-such-poi-id/beats")
        assert resp.status_code == 200
        assert resp.json()["beats"] == []

    def test_response_shape_matches_name_keyed_route(self, client, twin_pois):
        poi_a, _poi_b, _beat_a, _beat_b = twin_pois
        beat = client.get(f"/api/v1/graph/poi/by-id/{poi_a['id']}/beats").json()["beats"][0]
        for key in (
            "id",
            "script_body",
            "version",
            "active_status",
            "duration_sec",
            "lens_slugs",
            "lens_slug",
            "sort_order",
        ):
            assert key in beat, f"missing {key} in id-scoped beat payload"
