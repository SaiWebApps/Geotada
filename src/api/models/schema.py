"""Pydantic models for schema introspection responses."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class PropertySchema(BaseModel):
    """Describes a single property of a node or relationship type."""

    name: str
    type: str
    required: bool
    default: Any | None


class NodeTypeSchema(BaseModel):
    """Schema description for one node label."""

    label: str
    properties: list[PropertySchema]
    constraints: list[str]
    indexes: list[str]


class NodeTypeListResponse(BaseModel):
    """All node type schemas."""

    items: list[NodeTypeSchema]
    total: int


class RelTypeSchema(BaseModel):
    """Schema description for one relationship type."""

    type: str
    properties: list[PropertySchema]


class RelTypeListResponse(BaseModel):
    """All relationship type schemas."""

    items: list[RelTypeSchema]
    total: int
