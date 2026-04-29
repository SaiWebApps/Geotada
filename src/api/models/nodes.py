"""Pydantic models for node CRUD operations."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class NodeLabel(str, Enum):
    """Valid node labels from Schema_v3."""

    User = "User"
    Profile = "Profile"
    Lens = "Lens"
    Trip = "Trip"
    ItineraryItem = "ItineraryItem"
    POI = "POI"
    NarrativeBeat = "NarrativeBeat"


class NodeResponse(BaseModel):
    """Returned from all node endpoints."""

    id: str
    labels: list[str]
    properties: dict[str, Any]


class NodeListResponse(BaseModel):
    """Paginated list of nodes."""

    items: list[NodeResponse]
    total: int
    skip: int
    limit: int


# ── Per-label CREATE models ──


class UserCreate(BaseModel):
    email: str = Field(max_length=320)


class ProfileCreate(BaseModel):
    display_name: str = Field(max_length=500)


class LensCreate(BaseModel):
    name: str = Field(max_length=500)
    display_label: str = Field(max_length=500)


class TripCreate(BaseModel):
    name: str = Field(max_length=500)
    start_date: str = Field(max_length=50)
    end_date: str = Field(max_length=50)
    cover_image_url: str = Field(default="", max_length=2000)
    status: str = Field(default="planning", max_length=50)


class ItineraryItemCreate(BaseModel):
    sort_order: int
    scheduled_date: str = Field(max_length=50)
    start_time: str = Field(max_length=50)
    duration_min: int


class POICreate(BaseModel):
    name: str = Field(max_length=500)
    short_description: str = Field(default="", max_length=2000)
    latitude: float
    longitude: float
    importance_tier: int = 1
    trigger_radius: int = 10
    typical_duration_min: int = 30
    kid_friendly: str = Field(default="yes", max_length=50)
    name_variations: list[str] = []
    force_create: bool = False

    @field_validator("latitude")
    @classmethod
    def latitude_in_range(cls, v: float) -> float:
        if not -90 <= v <= 90:
            raise ValueError("latitude must be between -90 and 90")
        return v

    @field_validator("longitude")
    @classmethod
    def longitude_in_range(cls, v: float) -> float:
        if not -180 <= v <= 180:
            raise ValueError("longitude must be between -180 and 180")
        return v


class NarrativeBeatCreate(BaseModel):
    script_body: str = Field(max_length=10000)
    version: int = 1
    active_status: str = Field(default="active", max_length=50)
    audio_url: str = Field(default="", max_length=2000)
    duration_sec: int = 60
    kid_friendly: str = Field(default="yes", max_length=50)


CREATE_MODELS: dict[NodeLabel, type[BaseModel]] = {
    NodeLabel.User: UserCreate,
    NodeLabel.Profile: ProfileCreate,
    NodeLabel.Lens: LensCreate,
    NodeLabel.Trip: TripCreate,
    NodeLabel.ItineraryItem: ItineraryItemCreate,
    NodeLabel.POI: POICreate,
    NodeLabel.NarrativeBeat: NarrativeBeatCreate,
}


# ── UPDATE model ──


class NodeUpdate(BaseModel):
    """Partial update — only provided fields are SET."""

    properties: dict[str, Any]
