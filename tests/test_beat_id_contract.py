"""NarrativeBeat id contract: ids are ALWAYS server-generated (2026-07-19).

`NarrativeBeatCreate` has no `id` field and pydantic ignores extras, so a
client-supplied id can never reach `crud.create_node` through the API — which
made the old `MERGE (n:NarrativeBeat {id: $_beat_id})` branch unreachable and
its docstring ("An explicit id ... is honoured") false. The branch is gone;
these tests pin the contract that replaced it, at both layers.

Red-first: against the pre-fix code, `test_crud_ignores_supplied_id` returns
the caller's id (MERGE branch) and `test_crud_supplied_id_never_upserts`
upserts onto a single node instead of creating two.

Requires a running Neo4j instance (port 7688 — `make db-test-up`).
"""

from __future__ import annotations

from src.api.crud import nodes as crud
from tests.conftest import needs_neo4j


@needs_neo4j
class TestBeatIdIsServerGenerated:
    def test_crud_ignores_supplied_id(self, clean_driver):
        """crud.create_node must drop a caller-supplied id, not adopt it as
        the node's primary key."""
        with clean_driver.session() as session:
            node = crud.create_node(
                session,
                "NarrativeBeat",
                {"id": "client-chosen-id", "script_body": "A caller-supplied id."},
            )

        assert node["id"] != "client-chosen-id"
        assert node["properties"]["id"] == node["id"]
        assert node["properties"].get("script_body") == "A caller-supplied id."

    def test_crud_supplied_id_never_upserts(self, clean_driver):
        """Two creates with the same supplied id must yield two distinct
        nodes — the id is not a MERGE key."""
        props = {"id": "repeat-id", "script_body": "Posted twice with one id."}
        with clean_driver.session() as session:
            first = crud.create_node(session, "NarrativeBeat", dict(props))
            second = crud.create_node(session, "NarrativeBeat", dict(props))

            assert first["id"] != second["id"]
            count = session.run(
                "MATCH (n:NarrativeBeat) WHERE n.id IN $ids RETURN count(n) AS c",
                ids=[first["id"], second["id"]],
            ).single()["c"]
            assert count == 2

            leaked = session.run(
                "MATCH (n:NarrativeBeat {id: 'repeat-id'}) RETURN count(n) AS c"
            ).single()["c"]
            assert leaked == 0

    def test_api_drops_id_and_generates_one(self, client):
        """POST /nodes/NarrativeBeat with an id is accepted, but the stored id
        is server-generated (documents why the MERGE branch was unreachable)."""
        body = {"id": "posted-id", "script_body": "An id posted over HTTP."}
        first = client.post("/api/v1/nodes/NarrativeBeat", json=body)
        second = client.post("/api/v1/nodes/NarrativeBeat", json=body)

        assert first.status_code == 201, first.text
        assert second.status_code == 201, second.text
        assert first.json()["id"] != "posted-id"
        assert first.json()["id"] != second.json()["id"]
