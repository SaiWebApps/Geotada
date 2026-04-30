"""Cypher query functions for node CRUD operations."""

from __future__ import annotations

import json
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from neo4j import Session


def _encode_complex_props(props: dict) -> dict:
    """JSON-encode list-of-dict values so Neo4j can store them as strings.

    Neo4j refuses `SET n.x = $x` when $x is a list of maps. Pydantic models
    such as `physical_cues: list[PhysicalCue]` and
    `inline_foreign_phrases: list[InlineForeignPhrase]` arrive as list[dict]
    after model_dump(). Encode them here; `_serialize_props` decodes on read.
    """
    encoded = {}
    for key, val in props.items():
        if isinstance(val, list) and val and all(isinstance(item, dict) for item in val):
            encoded[key] = json.dumps(val)
        else:
            encoded[key] = val
    return encoded


def _serialize_props(props: dict) -> dict:
    """Convert Neo4j spatial points and temporal types to JSON-safe values.

    Strings that round-trip from `_encode_complex_props` (JSON arrays of
    objects) are decoded back to list[dict] for the API response.
    """
    serialized = {}
    for key, val in props.items():
        if hasattr(val, "latitude"):
            serialized[key] = {"lat": val.latitude, "lng": val.longitude}
        elif isinstance(val, str) and val.startswith("[") and val.endswith("]"):
            try:
                decoded = json.loads(val)
                serialized[key] = decoded if isinstance(decoded, list) else val
            except json.JSONDecodeError:
                serialized[key] = val
        elif isinstance(val, (str, int, float, bool)):
            serialized[key] = val
        elif isinstance(val, list):
            serialized[key] = val
        else:
            serialized[key] = str(val)
    return serialized


def _record_to_node(record) -> dict[str, Any]:
    """Convert a Neo4j record to a node dict."""
    props = _serialize_props(dict(record["props"]))
    return {
        "id": record["id"],
        "labels": record["labels"],
        "properties": props,
    }


def list_nodes(
    session: Session, label: str, skip: int, limit: int
) -> tuple[list[dict], int]:
    """Return paginated nodes of a label and total count."""
    count_result = session.run(
        f"MATCH (n:{label}) RETURN count(n) AS total"
    ).single()
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
    result = session.run(
        f"MATCH (n:{label} {{id: $node_id}}) "
        f"RETURN n.id AS id, labels(n) AS labels, properties(n) AS props",
        node_id=node_id,
    ).single()
    if result is None:
        return None
    return _record_to_node(result)


def create_node(
    session: Session, label: str, properties: dict[str, Any]
) -> dict:
    """Create a node with a generated UUID id. Returns the created node.

    For POI and NarrativeBeat, uses MERGE for idempotent upserts.
    """
    params = _encode_complex_props(dict(properties))

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
            if key not in ("lat", "lng", "name", "city_name"):
                set_parts.append(f"n.{key} = ${key}")

        if force_create:
            # CREATE forces a new node even if (name, city_name) matches — used when
            # editor confirms "different place" for a proximity match with same name.
            query = (
                f"CREATE (n:POI {{name: $name, city_name: $city_name}}) "
                f"SET {', '.join(set_parts)} "
                f"RETURN n.id AS id, labels(n) AS labels, properties(n) AS props"
            )
        else:
            # MERGE on (name, city_name) for idempotent POI creation (default path).
            # Multi-city safe — Notre-Dame Paris vs Notre-Dame Reims won't collide.
            query = (
                f"MERGE (n:POI {{name: $name, city_name: $city_name}}) "
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
    elif label == "Area":
        # MERGE on compound key (name, area_type, city_name) for idempotent Area creation
        lat = params.pop("centroid_lat")
        lng = params.pop("centroid_lng")
        params["lat"] = lat
        params["lng"] = lng

        set_parts = [
            "n.id = coalesce(n.id, randomUUID())",
            "n.created_at = coalesce(n.created_at, datetime())",
            "n.centroid = point({latitude: $lat, longitude: $lng, srid: 4326})",
        ]
        for key in params:
            if key not in ("lat", "lng", "name", "area_type", "city_name"):
                set_parts.append(f"n.{key} = ${key}")

        query = (
            f"MERGE (n:Area {{name: $name, area_type: $area_type, city_name: $city_name}}) "
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
    if not properties:
        return get_node(session, label, node_id)

    properties = _encode_complex_props(dict(properties))
    params: dict[str, Any] = {"node_id": node_id}
    set_parts: list[str] = []

    # POI: convert latitude/longitude to spatial point
    if label == "POI" and ("latitude" in properties or "longitude" in properties):
        lat = properties.pop("latitude", None)
        lng = properties.pop("longitude", None)
        if lat is not None and lng is not None:
            set_parts.append(
                "n.location = point({latitude: $lat, longitude: $lng, srid: 4326})"
            )
            params["lat"] = lat
            params["lng"] = lng

    # Area: convert centroid_lat/centroid_lng to spatial point
    if label == "Area" and ("centroid_lat" in properties or "centroid_lng" in properties):
        lat = properties.pop("centroid_lat", None)
        lng = properties.pop("centroid_lng", None)
        if lat is not None and lng is not None:
            set_parts.append(
                "n.centroid = point({latitude: $lat, longitude: $lng, srid: 4326})"
            )
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
    result = session.run(
        f"MATCH (n:{label} {{id: $node_id}}) DETACH DELETE n "
        f"RETURN count(*) AS deleted",
        node_id=node_id,
    ).single()
    return result["deleted"] > 0
