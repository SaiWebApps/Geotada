"""Shared utilities for the Ondoway Graph API."""

from __future__ import annotations

import json


def serialize_neo4j_props(props: dict) -> dict:
    """Convert Neo4j spatial points and temporal types to JSON-safe values.

    Handles:
    - Spatial points (objects with .latitude) -> {"lat": ..., "lng": ...}
    - JSON-encoded list[dict] strings (round-tripped from
      `_encode_complex_props` for fields like ``physical_cues``,
      ``inline_foreign_phrases``) -> decoded back to list[dict]
    - Primitives (str, int, float, bool) -> pass through
    - Lists -> pass through
    - Everything else -> str(val)
    """
    serialized = {}
    for key, val in props.items():
        if hasattr(val, "latitude"):
            serialized[key] = {"lat": val.latitude, "lng": val.longitude}
        elif isinstance(val, str) and val.startswith("[") and val.endswith("]"):
            try:
                decoded = json.loads(val)
                serialized[key] = decoded if isinstance(decoded, list) else val
            except (json.JSONDecodeError, ValueError):
                serialized[key] = val
        elif isinstance(val, (str, int, float, bool, list)):
            serialized[key] = val
        else:
            serialized[key] = str(val)
    return serialized
