"""Count nodes and relationships in the graph for verification."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from neo4j import Driver

from src.connection import get_database


def count_nodes_by_label(driver: Driver) -> dict[str, int]:
    """Return {label: count} for every node label in the database."""
    query = """
    CALL db.labels() YIELD label
    CALL (label) {
        MATCH (n)
        WHERE label IN labels(n)
        RETURN count(n) AS cnt
    }
    RETURN label, cnt ORDER BY label
    """
    with driver.session(database=get_database()) as session:
        result = session.run(query)
        return {record["label"]: record["cnt"] for record in result}


def count_relationships_by_type(driver: Driver) -> dict[str, int]:
    """Return {type: count} for every relationship type in the database."""
    query = """
    CALL db.relationshipTypes() YIELD relationshipType AS type
    CALL (type) {
        MATCH ()-[r]->()
        WHERE type(r) = type
        RETURN count(r) AS cnt
    }
    RETURN type, cnt ORDER BY type
    """
    with driver.session(database=get_database()) as session:
        result = session.run(query)
        return {record["type"]: record["cnt"] for record in result}


def total_counts(driver: Driver) -> dict[str, int]:
    """Return total node and relationship counts."""
    with driver.session(database=get_database()) as session:
        nodes = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        rels = session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
    return {"total_nodes": nodes, "total_relationships": rels}
