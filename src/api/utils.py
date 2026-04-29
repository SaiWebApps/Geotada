"""Shared utilities for the Travlr Graph API."""

from __future__ import annotations


def serialize_neo4j_props(props: dict) -> dict:
    """Convert Neo4j spatial points and temporal types to JSON-safe values.

    Handles:
    - Spatial points (objects with .latitude) -> {"lat": ..., "lng": ...}
    - Primitives (str, int, float, bool) -> pass through
    - Lists -> pass through
    - Everything else -> str(val)
    """
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
