"""Integration tests for data seeding."""

import pytest

from src.schema.constraints import apply_all
from src.seed.runner import seed_all
from tests.conftest import needs_neo4j


@needs_neo4j
class TestSeeding:
    @pytest.fixture(autouse=True)
    def _setup(self, driver):
        """Wipe and re-seed before each test in this class."""
        with driver.session() as s:
            s.run("MATCH (n) DETACH DELETE n")
        apply_all(driver)
        seed_all(driver)

    def test_seed_returns_expected_counts(self, driver):
        with driver.session() as s:
            s.run("MATCH (n) DETACH DELETE n")
        apply_all(driver)
        result = seed_all(driver)
        assert result["lenses"] == 13  # 12 MVP + 1 child
        assert result["users"] == 1
        assert result["profiles"] == 2
        assert result["pois"] == 3
        assert result["beats"] == 4
        assert result["trips"] == 1
        assert result["stops"] == 3

    def test_twelve_plus_one_lenses_exist(self, driver):
        with driver.session() as session:
            count = session.run("MATCH (l:Lens) RETURN count(l) AS c").single()["c"]
        assert count == 13

    def test_user_has_two_profiles(self, driver):
        with driver.session() as session:
            count = session.run(
                "MATCH (u:User)-[:HAS_PROFILE]->(p:Profile) RETURN count(p) AS c"
            ).single()["c"]
        assert count == 2

    def test_pois_have_geopoint_locations(self, driver):
        with driver.session() as session:
            result = session.run(
                "MATCH (p:POI) WHERE p.location IS NOT NULL RETURN count(p) AS c"
            ).single()["c"]
        assert result == 3

    def test_cafe_de_flore_has_two_beats(self, driver):
        with driver.session() as session:
            count = session.run(
                "MATCH (p:POI {name: 'Café de Flore'})-[:HAS_BEAT]->(b) RETURN count(b) AS c"
            ).single()["c"]
        assert count == 2

    def test_trip_has_captain_and_crew(self, driver):
        with driver.session() as session:
            captain = session.run(
                "MATCH (p:Profile)-[:IS_CAPTAIN_OF]->(t:Trip) RETURN p.display_name AS name"
            ).single()["name"]
            crew = session.run(
                "MATCH (p:Profile)-[:IS_CREW_OF]->(t:Trip) RETURN p.display_name AS name"
            ).single()["name"]
        assert captain == "Mom"
        assert crew == "Kid"

    def test_all_eleven_relationship_types_present(self, driver):
        with driver.session() as session:
            result = session.run(
                "CALL db.relationshipTypes() YIELD relationshipType "
                "RETURN collect(relationshipType) AS types"
            ).single()["types"]
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
        assert expected.issubset(set(result))


@needs_neo4j
class TestIdempotency:
    def test_double_seed_produces_no_duplicates(self, driver):
        """Running seed_all twice should not create duplicate nodes."""
        with driver.session() as s:
            s.run("MATCH (n) DETACH DELETE n")
        apply_all(driver)
        seed_all(driver)

        with driver.session() as session:
            count_before = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]

        seed_all(driver)

        with driver.session() as session:
            count_after = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]

        assert count_before == count_after
