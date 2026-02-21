"""Unit tests for schema definitions — no Neo4j required."""

from src.schema.definitions import (
    DAG_CHILD_LENSES,
    INDEXES,
    MVP_LENSES,
    RELATIONSHIP_TYPES,
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
    def test_twelve_mvp_lenses(self):
        """Living Doc §08 defines exactly 12 MVP lenses."""
        assert len(MVP_LENSES) == 12

    def test_lens_names_are_unique(self):
        names = [lens["name"] for lens in MVP_LENSES]
        assert len(names) == len(set(names))

    def test_dag_child_references_existing_parent(self):
        parent_names = {lens["name"] for lens in MVP_LENSES}
        for child in DAG_CHILD_LENSES:
            assert child["parent_name"] in parent_names, (
                f"Child lens '{child['name']}' references unknown parent '{child['parent_name']}'"
            )
