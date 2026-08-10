"""Tests for the public read-only product API — GET /api/v1/lenses.

This endpoint is the mobile client's lens-taxonomy read surface: unlike the
workbench CRUD routers, it is mounted unconditionally (outside
`_workbench_api_enabled()`).
"""

from __future__ import annotations

import pytest

from src.connection import get_database
from src.schema.definitions import DAG_CHILD_LENSES, MVP_LENSES
from src.seed.lenses import seed_lenses


@pytest.fixture(scope="module")
def seeded_client(client, clean_driver):
    """The shared `client` fixture with the canonical lens taxonomy seeded."""
    seed_lenses(clean_driver)
    return client


class TestLensesEndpoint:
    def test_returns_200_non_empty_without_auth(self, seeded_client):
        """AC-1: no Authorization header -> 200, non-empty body (a [] fails)."""
        response = seeded_client.get("/api/v1/lenses")
        assert response.status_code == 200
        body = response.json()
        assert body != []
        assert len(body) > 0

    def test_all_eight_parents_with_fields(self, seeded_client):
        """AC-2: all 8 parent lenses by name (== MVP_LENSES), each carrying
        id, name, display_label, is_parent:true.
        """
        response = seeded_client.get("/api/v1/lenses")
        assert response.status_code == 200
        body = response.json()

        parents = [item for item in body if item.get("is_parent") is True]
        assert len(parents) == 8

        expected_names = {lens["name"] for lens in MVP_LENSES}
        actual_names = {parent["name"] for parent in parents}
        assert actual_names == expected_names

        expected_by_name = {lens["name"]: lens for lens in MVP_LENSES}
        for parent in parents:
            assert set(parent.keys()) >= {"id", "name", "display_label", "is_parent"}
            assert isinstance(parent["id"], str) and parent["id"]
            assert parent["display_label"] == expected_by_name[parent["name"]]["display_label"]
            assert parent["is_parent"] is True

    def test_nested_children_all_21_under_correct_parent(self, seeded_client):
        """AC-3/AC-4: all 21 universal child lenses (id, name, display_label,
        is_parent:false) nested under their correct parent's `children` key,
        per DAG_CHILD_LENSES.parent_name.

        AC-4 (pinned contract): the parent and child key sets are asserted as
        an EXACT snapshot (``==``), not a floor (``>=``). An undocumented extra
        key on any parent or child object fails this test, so the client
        repoint slice has a fixed target. Superset of canonical children is
        tolerated via the ``in expected`` guard below;
        ``test_superset_extra_city_child_tolerated`` exercises that path with a
        real non-canonical node.
        """
        response = seeded_client.get("/api/v1/lenses")
        assert response.status_code == 200
        body = response.json()

        expected_by_child_name = {child["name"]: child for child in DAG_CHILD_LENSES}
        assert len(expected_by_child_name) == 21

        # AC-4 pinned key snapshot — EXACT, not a floor.
        expected_parent_keys = {"id", "name", "display_label", "is_parent", "children"}
        expected_child_keys = {"id", "name", "display_label", "is_parent"}

        seen_children: dict[str, dict] = {}
        for parent in body:
            assert set(parent.keys()) == expected_parent_keys
            assert isinstance(parent["children"], list)
            for child in parent["children"]:
                assert set(child.keys()) == expected_child_keys
                assert child["is_parent"] is False
                if child["name"] in expected_by_child_name:
                    seen_children[child["name"]] = {**child, "_under_parent": parent["name"]}

        assert set(seen_children.keys()) == set(expected_by_child_name.keys())

        for child_name, expected in expected_by_child_name.items():
            actual = seen_children[child_name]
            assert isinstance(actual["id"], str) and actual["id"]
            assert actual["display_label"] == expected["display_label"]
            assert actual["_under_parent"] == expected["parent_name"]

    def test_superset_extra_city_child_tolerated(self, seeded_client, clean_driver):
        """AC-3 tail clause: a non-canonical (city-specific) child lens under a
        real parent must NOT break the endpoint. Exercises the superset path
        directly — seed_lenses forbids non-canonical nodes, so this test injects
        one after seeding. Expect: 200, all 21 canonical children still present
        (none dropped), and the extra child represented honestly (correct real
        parent, no fabricated parent, same 4-key child shape). Cleans up after
        itself so the module DB stays canonical for order-independent runs.
        """
        with clean_driver.session(database=get_database()) as s:
            s.run(
                "MERGE (child:Lens {name: $name}) "
                "SET child.id = coalesce(child.id, randomUUID()), "
                "    child.display_label = $label, child.is_parent = false "
                "WITH child "
                "MATCH (parent:Lens {name: $parent}) "
                "MERGE (parent)-[r:IS_PARENT_OF]->(child) "
                "SET r.id = coalesce(r.id, randomUUID())",
                name="film_locations_paris",
                label="Paris Film Locations",
                parent="arts_culture",
            )
        try:
            response = seeded_client.get("/api/v1/lenses")
            assert response.status_code == 200
            body = response.json()

            children_by_parent = {parent["name"]: parent["children"] for parent in body}

            # All 21 canonical children still present — the extra node did not
            # cause any canonical child to be dropped or a 500.
            canonical_child_names = {child["name"] for child in DAG_CHILD_LENSES}
            all_child_names = {
                child["name"] for kids in children_by_parent.values() for child in kids
            }
            assert canonical_child_names <= all_child_names

            # The extra city child appears under its real parent, honestly shaped,
            # not under a fabricated one.
            arts_children = {c["name"]: c for c in children_by_parent["arts_culture"]}
            assert "film_locations_paris" in arts_children
            extra = arts_children["film_locations_paris"]
            assert set(extra.keys()) == {"id", "name", "display_label", "is_parent"}
            assert extra["is_parent"] is False
            assert extra["display_label"] == "Paris Film Locations"
        finally:
            with clean_driver.session(database=get_database()) as s:
                s.run(
                    "MATCH (l:Lens {name: $name}) DETACH DELETE l",
                    name="film_locations_paris",
                )

    def test_degraded_data_returns_200_and_honest(self, seeded_client, clean_driver):
        """AC-5 (negative): degraded graph -> 200, no 500, honest representation.

        Two degraded conditions injected directly (bypassing seed_lenses, which
        forbids non-canonical nodes):
          - an orphan child Lens with NO IS_PARENT_OF edge from any parent
          - a childless (but real, is_parent:true) parent Lens with zero children

        Expect: 200 (not a 500); the childless parent is present with
        children: [] (not dropped, not crashed); the orphan child is not
        fabricated under any parent's children (no invented relationship);
        and an existing canonical parent's child count is unaffected by the
        orphan's mere presence in the graph (rules out a Cartesian-product
        bug where an unrelated OPTIONAL MATCH duplicates children).
        """
        with clean_driver.session(database=get_database()) as s:
            before = s.run(
                "MATCH (p:Lens {name: 'arts_culture'})-[:IS_PARENT_OF]->(c:Lens) "
                "RETURN count(c) AS n"
            ).single()["n"]

            s.run(
                "MERGE (child:Lens {name: $name}) "
                "SET child.id = coalesce(child.id, randomUUID()), "
                "    child.display_label = $label, child.is_parent = false",
                name="orphan_child_test",
                label="Orphan Child",
            )
            s.run(
                "MERGE (parent:Lens {name: $name}) "
                "SET parent.id = coalesce(parent.id, randomUUID()), "
                "    parent.display_label = $label, parent.is_parent = true",
                name="childless_parent_test",
                label="Childless Parent",
            )

        try:
            response = seeded_client.get("/api/v1/lenses")
            assert response.status_code == 200
            body = response.json()

            by_name = {item["name"]: item for item in body}

            # Childless parent: present, honestly empty — not dropped, not a 500.
            assert "childless_parent_test" in by_name
            assert by_name["childless_parent_test"]["children"] == []

            # Orphan child: never fabricated under any parent.
            for parent in body:
                child_names = {c["name"] for c in parent["children"]}
                assert "orphan_child_test" not in child_names

            # Canonical taxonomy unaffected — no Cartesian-product duplication
            # caused by the orphan's presence in the graph.
            assert len(by_name["arts_culture"]["children"]) == before
        finally:
            with clean_driver.session(database=get_database()) as s:
                s.run(
                    "MATCH (l:Lens) WHERE l.name IN $names DETACH DELETE l",
                    names=["orphan_child_test", "childless_parent_test"],
                )
