"""Pydantic models for node CRUD operations."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel


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
    email: str


class ProfileCreate(BaseModel):
    display_name: str


class LensCreate(BaseModel):
    name: str
    display_label: str


class TripCreate(BaseModel):
    name: str
    start_date: str
    end_date: str
    cover_image_url: str = ""
    status: str = "planning"


class ItineraryItemCreate(BaseModel):
    sort_order: int
    scheduled_date: str
    start_time: str
    duration_min: int


class POICreate(BaseModel):
    name: str
    short_description: str = ""
    latitude: float
    longitude: float
    importance_tier: int = 1
    trigger_radius: int = 10
    typical_duration_min: int = 30
    kid_friendly: str = "yes"
    name_variations: list[str] = []


class NarrativeBeatCreate(BaseModel):
    script_body: str
    version: int = 1
    active_status: str = "active"
    audio_url: str = ""
    duration_sec: int = 60
    kid_friendly: str = "yes"


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
