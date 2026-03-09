"""Cypher query functions for edge/relationship CRUD operations."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from neo4j import Session


def _serialize_props(props: dict) -> dict:
    """Convert Neo4j spatial points and temporal types to JSON-safe values."""
    serialized = {}
    for key, val in props.items():
        if hasattr(val, "latitude"):
            serialized[key] = {"lat": val.latitude, "lng": val.longitude}
        elif isinstance(val, (str, int, float, bool)):
            serialized[key] = val
        elif isinstance(val, list):
            serialized[key] = val
        else:
            serialized[key] = str(val)
    return serialized


def _record_to_edge(record) -> dict[str, Any]:
    """Convert a Neo4j record to an edge dict."""
    props = _serialize_props(dict(record["props"])) if record["props"] else {}
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
    if not properties:
        return get_edge(session, rel_type, edge_id)

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
    result = session.run(
        f"MATCH ()-[r:{rel_type} {{id: $edge_id}}]->() DELETE r "
        f"RETURN count(*) AS deleted",
        edge_id=edge_id,
    ).single()
    return result["deleted"] > 0
