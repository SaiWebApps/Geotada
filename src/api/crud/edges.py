"""Cypher query functions for edge/relationship CRUD operations."""

from __future__ import annotations

import re
from typing import Any, TYPE_CHECKING

from src.api.models.edges import RelType
from src.api.models.nodes import NodeLabel
from src.api.utils import serialize_neo4j_props

if TYPE_CHECKING:
    from neo4j import Session

_VALID_PROPERTY_NAME = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _validate_rel_type(rel_type: str) -> None:
    """Validate that rel_type is a known RelType. Raises ValueError if not."""
    RelType(rel_type)


def _validate_label(label: str) -> None:
    """Validate that label is a known NodeLabel. Raises ValueError if not."""
    NodeLabel(label)


def _validate_property_keys(properties: dict) -> None:
    """Validate that all property keys are safe identifiers."""
    for key in properties:
        if not _VALID_PROPERTY_NAME.match(key):
            raise ValueError(
                f"Invalid property name: {key!r}. "
                "Property names must match ^[a-zA-Z_][a-zA-Z0-9_]*$"
            )


def _record_to_edge(record) -> dict[str, Any]:
    """Convert a Neo4j record to an edge dict."""
    props = serialize_neo4j_props(dict(record["props"])) if record["props"] else {}
    return {
        "id": record["id"],
        "type": record["type"],
        "source_id": record["source_id"],
        "target_id": record["target_id"],
        "properties": props,
    }


def list_edges(
    session: Session, rel_type: str, skip: int, limit: int
) -> tuple[list[dict], int]:
    """Return paginated edges of a type and total count."""
    _validate_rel_type(rel_type)
    count_result = session.run(
        f"MATCH ()-[r:{rel_type}]->() RETURN count(r) AS total"
    ).single()
    total = count_result["total"]

    result = session.run(
        f"MATCH (a)-[r:{rel_type}]->(b) "
        f"RETURN r.id AS id, type(r) AS type, "
        f"a.id AS source_id, b.id AS target_id, properties(r) AS props "
        f"ORDER BY r.id SKIP $skip LIMIT $limit",
        skip=skip,
        limit=limit,
    )
    edges = [_record_to_edge(record) for record in result]
    return edges, total


def get_edge(session: Session, rel_type: str, edge_id: str) -> dict | None:
    """Return a single edge by type and id property, or None."""
    _validate_rel_type(rel_type)
    result = session.run(
        f"MATCH (a)-[r:{rel_type} {{id: $edge_id}}]->(b) "
        f"RETURN r.id AS id, type(r) AS type, "
        f"a.id AS source_id, b.id AS target_id, properties(r) AS props",
        edge_id=edge_id,
    ).single()
    if result is None:
        return None
    return _record_to_edge(result)


def create_edge(
    session: Session,
    rel_type: str,
    source_label: str,
    source_id: str,
    target_label: str,
    target_id: str,
    properties: dict[str, Any],
) -> dict | None:
    """Create a relationship with a generated UUID id.

    Returns the created edge, or None if source/target not found.
    """
    _validate_rel_type(rel_type)
    _validate_label(source_label)
    _validate_label(target_label)
    _validate_property_keys(properties)

    params: dict[str, Any] = {
        "source_id": source_id,
        "target_id": target_id,
    }

    for key, val in properties.items():
        params[key] = val

    use_merge = rel_type in ("HAS_BEAT", "TAGGED_WITH")

    if use_merge:
        set_parts = [
            "r.id = coalesce(r.id, randomUUID())",
            "r.created_at = coalesce(r.created_at, datetime())",
        ]
    else:
        set_parts = [
            "r.id = randomUUID()",
            "r.created_at = datetime()",
        ]

    for key in properties:
        set_parts.append(f"r.{key} = ${key}")

    verb = "MERGE" if use_merge else "CREATE"
    query = (
        f"MATCH (a:{source_label} {{id: $source_id}}) "
        f"MATCH (b:{target_label} {{id: $target_id}}) "
        f"{verb} (a)-[r:{rel_type}]->(b) "
        f"SET {', '.join(set_parts)} "
        f"RETURN r.id AS id, type(r) AS type, "
        f"a.id AS source_id, b.id AS target_id, properties(r) AS props"
    )
    result = session.run(query, **params).single()
    if result is None:
        return None
    return _record_to_edge(result)


def update_edge(
    session: Session, rel_type: str, edge_id: str, properties: dict[str, Any]
) -> dict | None:
    """Update edge properties. Returns updated edge or None if not found."""
    _validate_rel_type(rel_type)
    if not properties:
        return get_edge(session, rel_type, edge_id)

    _validate_property_keys(properties)

    params: dict[str, Any] = {"edge_id": edge_id}
    set_parts: list[str] = []

    for key, val in properties.items():
        set_parts.append(f"r.{key} = ${key}")
        params[key] = val

    query = (
        f"MATCH (a)-[r:{rel_type} {{id: $edge_id}}]->(b) "
        f"SET {', '.join(set_parts)} "
        f"RETURN r.id AS id, type(r) AS type, "
        f"a.id AS source_id, b.id AS target_id, properties(r) AS props"
    )
    result = session.run(query, **params).single()
    if result is None:
        return None
    return _record_to_edge(result)


def delete_edge(session: Session, rel_type: str, edge_id: str) -> bool:
    """Delete a relationship. Returns True if found and deleted."""
    _validate_rel_type(rel_type)
    result = session.run(
        f"MATCH ()-[r:{rel_type} {{id: $edge_id}}]->() DELETE r "
        f"RETURN count(*) AS deleted",
        edge_id=edge_id,
    ).single()
    return result["deleted"] > 0
