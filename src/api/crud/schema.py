"""Schema introspection functions — derives property metadata from Pydantic models.

Pure Python module — no database calls.
"""

from __future__ import annotations

from typing import Any

from src.api.models.nodes import CREATE_MODELS, NodeLabel
from src.schema.definitions import (
    INDEXES,
    RELATIONSHIP_SCHEMAS,
    RELATIONSHIP_TYPES,
    UNIQUE_CONSTRAINTS,
)


def _pydantic_type_name(annotation: Any) -> str:
    """Convert a Python type annotation to a simple string name."""
    if annotation is str:
        return "str"
    if annotation is int:
        return "int"
    if annotation is float:
        return "float"
    if annotation is bool:
        return "bool"
    return str(annotation)


def get_node_type_schema(label: str) -> dict:
    """Return property schema for a single node label."""
    node_label = NodeLabel(label)
    model_cls = CREATE_MODELS[node_label]

    properties: list[dict] = [
        {
            "name": "id",
            "type": "str",
            "required": False,
            "default": "(auto-generated UUID)",
        },
    ]

    for field_name, field_info in model_cls.model_fields.items():
        properties.append(
            {
                "name": field_name,
                "type": _pydantic_type_name(field_info.annotation),
                "required": field_info.is_required(),
                "default": None if field_info.is_required() else field_info.default,
            }
        )

    properties.append(
        {
            "name": "created_at",
            "type": "str",
            "required": False,
            "default": "(auto-generated datetime)",
        }
    )

    constraints = [f"unique:{c.property}" for c in UNIQUE_CONSTRAINTS if c.label == label]

    indexes = [
        f"{idx.index_type}:{','.join(idx.properties)}" for idx in INDEXES if idx.label == label
    ]

    return {
        "label": label,
        "properties": properties,
        "constraints": constraints,
        "indexes": indexes,
    }


def list_node_type_schemas() -> list[dict]:
    """Return schema for all node types."""
    return [get_node_type_schema(label.value) for label in NodeLabel]


def get_rel_type_schema(rel_type: str) -> dict:
    """Return property schema for a single relationship type."""
    prop_defs = RELATIONSHIP_SCHEMAS.get(rel_type, [])

    properties: list[dict] = [
        {
            "name": "id",
            "type": "str",
            "required": False,
            "default": "(auto-generated UUID)",
        },
        {
            "name": "created_at",
            "type": "str",
            "required": False,
            "default": "(auto-generated datetime)",
        },
    ]

    for prop_def in prop_defs:
        properties.append(
            {
                "name": prop_def.name,
                "type": prop_def.type,
                "required": prop_def.required,
                "default": prop_def.default,
            }
        )

    return {
        "type": rel_type,
        "properties": properties,
    }


def list_rel_type_schemas() -> list[dict]:
    """Return schema for all relationship types."""
    return [get_rel_type_schema(rt) for rt in RELATIONSHIP_TYPES]
