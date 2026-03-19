"""Unit tests for schema definitions — no Neo4j required."""

from src.schema.definitions import (
    DAG_CHILD_LENSES,
    INDEXES,
    MVP_LENSES,
    RELATIONSHIP_TYPES,
    TAGGABLE_LENSES,
    UNIQUE_CONSTRAINTS,
)


class TestUniqueConstraints:
    def test_count_matches_schema_v3(self):
        """Schema_v3 §3 defines 9 unique constraints."""
        assert len(UNIQUE_CONSTRAINTS) == 9

    def test_constraint_names_are_unique(self):
        names = [c.name for c in UNIQUE_CONSTRAINTS]
        assert len(names) == len(set(names))

    def test_user_has_id_and_email_constraints(self):
        user_props = {c.property for c in UNIQUE_CONSTRAINTS if c.label == "User"}
        assert user_props == {"id", "email"}

    def test_lens_has_id_and_name_constraints(self):
        lens_props = {c.property for c in UNIQUE_CONSTRAINTS if c.label == "Lens"}
        assert lens_props == {"id", "name"}


class TestIndexes:
    def test_poi_spatial_index_exists(self):
        poi_indexes = [i for i in INDEXES if i.label == "POI"]
        assert len(poi_indexes) == 1
        assert poi_indexes[0].index_type == "POINT"
        assert poi_indexes[0].properties == ("location",)

    def test_narrative_beat_composite_index(self):
        nb_indexes = [i for i in INDEXES if i.label == "NarrativeBeat"]
        assert len(nb_indexes) == 1
        assert nb_indexes[0].properties == ("active_status", "version")


class TestRelationships:
    def test_eleven_relationship_types(self):
        """Schema_v3 §4 defines exactly 11 relationships."""
        assert len(RELATIONSHIP_TYPES) == 11

    def test_all_expected_types_present(self):
        expected = {
            "HAS_PROFILE",
            "IS_CAPTAIN_OF",
            "IS_CREW_OF",
            "PREFERS_LENS",
            "HAS_STOP",
            "ASSIGNED_TO",
            "AT_POI",
            "PLAYS_BEAT",
            "HAS_BEAT",
            "TAGGED_WITH",
            "IS_PARENT_OF",
        }
        assert set(RELATIONSHIP_TYPES) == expected


class TestLenses:
    def test_eleven_mvp_lenses(self):
        """11 top-level lenses in the hybrid hierarchy."""
        assert len(MVP_LENSES) == 11

    def test_eight_dag_child_lenses(self):
        assert len(DAG_CHILD_LENSES) == 8

    def test_sixteen_taggable_lenses(self):
        assert len(TAGGABLE_LENSES) == 16

    def test_lens_names_are_unique(self):
        names = [lens["name"] for lens in MVP_LENSES]
        assert len(names) == len(set(names))

    def test_dag_child_references_existing_parent(self):
        parent_names = {lens["name"] for lens in MVP_LENSES}
        for child in DAG_CHILD_LENSES:
            assert child["parent_name"] in parent_names, (
                f"Child lens '{child['name']}' references unknown parent '{child['parent_name']}'"
            )

    def test_dag_child_parent_has_is_parent_true(self):
        parent_lookup = {l["name"]: l for l in MVP_LENSES}
        for child in DAG_CHILD_LENSES:
            parent = parent_lookup[child["parent_name"]]
            assert parent.get("is_parent") is True, (
                f"Parent '{child['parent_name']}' must have is_parent=True"
            )

    def test_no_parent_slug_in_taggable(self):
        parent_slugs = {l["name"] for l in MVP_LENSES if l.get("is_parent")}
        for slug in TAGGABLE_LENSES:
            assert slug not in parent_slugs, (
                f"Parent-only slug '{slug}' must not appear in TAGGABLE_LENSES"
            )

    def test_taggable_equals_children_plus_leaves(self):
        child_slugs = {c["name"] for c in DAG_CHILD_LENSES}
        leaf_slugs = {l["name"] for l in MVP_LENSES if not l.get("is_parent")}
        assert set(TAGGABLE_LENSES) == child_slugs | leaf_slugs
