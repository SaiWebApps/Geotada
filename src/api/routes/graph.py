"""Graph data endpoint for vis.js visualization."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from neo4j import Session
from pydantic import BaseModel

from src.api.dependencies import get_session

router = APIRouter(tags=["graph"])


def _serialize_props(props: dict) -> dict:
    """Convert Neo4j spatial points and temporal types to JSON-safe values."""
    serialized = {}
    for key, val in props.items():
        if hasattr(val, "latitude"):
            serialized[key] = {"lat": val.latitude, "lng": val.longitude}
        else:
            serialized[key] = str(val) if not isinstance(val, (str, int, float, bool, list)) else val
    return serialized


@router.get("/graph")
def get_full_graph(session: Session = Depends(get_session)):
    """Fetch all nodes and relationships formatted for vis.js."""
    nodes_result = session.run(
        "MATCH (n) RETURN n.id AS id, labels(n) AS labels, properties(n) AS props"
    )
    nodes = []
    for record in nodes_result:
        props = _serialize_props(dict(record["props"]))
        primary_label = record["labels"][0] if record["labels"] else "Unknown"
        display = (
            props.get("display_name")
            or props.get("name")
            or props.get("display_label")
            or props.get("email")
            or primary_label
        )
        nodes.append(
            {
                "id": record["id"],
                "label": display,
                "group": primary_label,
                "labels": record["labels"],
                "properties": props,
            }
        )

    rels_result = session.run(
        "MATCH (a)-[r]->(b) "
        "RETURN elementId(r) AS eid, type(r) AS type, "
        "a.id AS source_id, b.id AS target_id, properties(r) AS props"
    )
    edges = [
        {
            "id": r["eid"],
            "from": r["source_id"],
            "to": r["target_id"],
            "label": r["type"],
            "properties": _serialize_props(dict(r["props"])) if r["props"] else {},
        }
        for r in rels_result
    ]

    return {"nodes": nodes, "edges": edges}


@router.get("/graph/poi/{poi_name}/beats")
def get_poi_beats(poi_name: str, session: Session = Depends(get_session)):
    """Fetch active beats and their lens tags for a POI by name."""
    result = session.run(
        "MATCH (p:POI {name: $name})-[r:HAS_BEAT]->(b:NarrativeBeat)"
        "-[:TAGGED_WITH]->(l:Lens) "
        'WHERE b.active_status = "active" '
        "RETURN b.id AS id, b.script_body AS script_body, "
        "b.version AS version, b.active_status AS active_status, "
        "b.duration_sec AS duration_sec, l.name AS lens_slug, "
        "r.sort_order AS sort_order "
        "ORDER BY r.sort_order",
        name=poi_name,
    )
    beats = [
        {
            "id": r["id"],
            "script_body": r["script_body"],
            "version": r["version"],
            "active_status": r["active_status"],
            "duration_sec": r["duration_sec"],
            "lens_slug": r["lens_slug"],
            "sort_order": r["sort_order"],
        }
        for r in result
    ]
    return {"poi_name": poi_name, "beats": beats}
