"""Cypher query functions for node CRUD operations."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from src.api.models.nodes import NodeLabel
from src.api.utils import serialize_neo4j_props

if TYPE_CHECKING:
    from neo4j import Session

_VALID_PROPERTY_NAME = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


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


def _record_to_node(record) -> dict[str, Any]:
    """Convert a Neo4j record to a node dict."""
    props = serialize_neo4j_props(dict(record["props"]))
    return {
        "id": record["id"],
        "labels": record["labels"],
        "properties": props,
    }


def list_nodes(session: Session, label: str, skip: int, limit: int) -> tuple[list[dict], int]:
    """Return paginated nodes of a label and total count."""
    _validate_label(label)
    count_result = session.run(f"MATCH (n:{label}) RETURN count(n) AS total").single()
    total = count_result["total"]

    result = session.run(
        f"MATCH (n:{label}) "
        f"RETURN n.id AS id, labels(n) AS labels, properties(n) AS props "
        f"ORDER BY n.id SKIP $skip LIMIT $limit",
        skip=skip,
        limit=limit,
    )
    nodes = [_record_to_node(record) for record in result]
    return nodes, total


def get_node(session: Session, label: str, node_id: str) -> dict | None:
    """Return a single node by label and id property, or None."""
    _validate_label(label)
    result = session.run(
        f"MATCH (n:{label} {{id: $node_id}}) "
        f"RETURN n.id AS id, labels(n) AS labels, properties(n) AS props",
        node_id=node_id,
    ).single()
    if result is None:
        return None
    return _record_to_node(result)


def create_node(session: Session, label: str, properties: dict[str, Any]) -> dict:
    """Create a node with a generated UUID id. Returns the created node.

    For POI and NarrativeBeat, uses MERGE for idempotent upserts.
    """
    _validate_label(label)
    _validate_property_keys(properties)
    params = dict(properties)

    if label == "POI" and "latitude" in params and "longitude" in params:
        lat = params.pop("latitude")
        lng = params.pop("longitude")
        params["lat"] = lat
        params["lng"] = lng
        force_create = params.pop("force_create", False)

        set_parts = [
            "n.id = coalesce(n.id, randomUUID())",
            "n.created_at = coalesce(n.created_at, datetime())",
            "n.location = point({latitude: $lat, longitude: $lng, srid: 4326})",
        ]
        for key in params:
            if key not in ("lat", "lng", "name"):
                set_parts.append(f"n.{key} = ${key}")

        if force_create:
            # CREATE forces a new node even if name matches — used when editor
            # confirms "different place" for a proximity match with same name.
            query = (
                f"CREATE (n:POI {{name: $name}}) "
                f"SET {', '.join(set_parts)} "
                f"RETURN n.id AS id, labels(n) AS labels, properties(n) AS props"
            )
        else:
            # MERGE on name for idempotent POI creation (default path)
            query = (
                f"MERGE (n:POI {{name: $name}}) "
                f"SET {', '.join(set_parts)} "
                f"RETURN n.id AS id, labels(n) AS labels, properties(n) AS props"
            )
    elif label == "NarrativeBeat":
        # MERGE on script_body for idempotent beat creation
        set_parts = [
            "n.id = coalesce(n.id, randomUUID())",
            "n.created_at = coalesce(n.created_at, datetime())",
        ]
        for key in params:
            if key != "script_body":
                set_parts.append(f"n.{key} = ${key}")

        query = (
            f"MERGE (n:NarrativeBeat {{script_body: $script_body}}) "
            f"SET {', '.join(set_parts)} "
            f"RETURN n.id AS id, labels(n) AS labels, properties(n) AS props"
        )
    else:
        set_parts = [
            "n.id = randomUUID()",
            "n.created_at = datetime()",
        ]
        for key in params:
            set_parts.append(f"n.{key} = ${key}")

        query = (
            f"CREATE (n:{label}) "
            f"SET {', '.join(set_parts)} "
            f"RETURN n.id AS id, labels(n) AS labels, properties(n) AS props"
        )

    result = session.run(query, **params).single()
    return _record_to_node(result)


def update_node(
    session: Session, label: str, node_id: str, properties: dict[str, Any]
) -> dict | None:
    """Update node properties. Returns updated node or None if not found."""
    _validate_label(label)
    if not properties:
        return get_node(session, label, node_id)

    _validate_property_keys(properties)
    properties = dict(properties)  # Don't mutate caller's dict

    params: dict[str, Any] = {"node_id": node_id}
    set_parts: list[str] = []

    # POI: convert latitude/longitude to spatial point
    if label == "POI" and ("latitude" in properties or "longitude" in properties):
        lat = properties.pop("latitude", None)
        lng = properties.pop("longitude", None)
        if lat is not None and lng is not None:
            set_parts.append("n.location = point({latitude: $lat, longitude: $lng, srid: 4326})")
            params["lat"] = lat
            params["lng"] = lng

    for key, val in properties.items():
        set_parts.append(f"n.{key} = ${key}")
        params[key] = val

    query = (
        f"MATCH (n:{label} {{id: $node_id}}) "
        f"SET {', '.join(set_parts)} "
        f"RETURN n.id AS id, labels(n) AS labels, properties(n) AS props"
    )
    result = session.run(query, **params).single()
    if result is None:
        return None
    return _record_to_node(result)


def delete_node(session: Session, label: str, node_id: str) -> bool:
    """DETACH DELETE a node. Returns True if found and deleted."""
    _validate_label(label)
    result = session.run(
        f"MATCH (n:{label} {{id: $node_id}}) DETACH DELETE n RETURN count(*) AS deleted",
        node_id=node_id,
    ).single()
    return result["deleted"] > 0
