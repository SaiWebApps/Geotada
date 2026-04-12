"""Pydantic models for node CRUD operations."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, field_validator


class NodeLabel(str, Enum):
    """Valid node labels from Schema_v3."""

    User = "User"
    Profile = "Profile"
    Lens = "Lens"
    Trip = "Trip"
    ItineraryItem = "ItineraryItem"
    POI = "POI"
    NarrativeBeat = "NarrativeBeat"
    Area = "Area"


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
    importance_tier: int  # REQUIRED — no default. Silent default of 1 caused
                           # famous landmarks to be demoted in earlier pipeline runs.
                           # See tests/test_export_consistency.py for the regression guard.
    trigger_radius: int = 10
    typical_duration_min: int = 30
    kid_friendly: str = "yes"
    name_variations: list[str] = []
    poi_role: str = "stop"
    force_create: bool = False

    @field_validator("importance_tier")
    @classmethod
    def importance_tier_in_range(cls, v: int) -> int:
        if not 1 <= v <= 5:
            raise ValueError("importance_tier must be between 1 and 5")
        return v

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
    script_body: str
    version: int = 1
    active_status: str = "active"
    audio_url: str = ""
    duration_sec: int = 60
    kid_friendly: str = "yes"
    entities: list[str] = []
    sensory_anchor: bool | None = None
    est_spoken_seconds: int | None = None
    narrative_function: str = ""
    beat_type: str = ""
    emotional_register: str = ""


class AreaCreate(BaseModel):
    name: str
    area_type: Literal["city", "district", "neighborhood", "island", "corridor"]
    city_name: str
    boundary: str  # WKT POLYGON string
    centroid_lat: float
    centroid_lng: float
    short_description: str = ""

    @field_validator("centroid_lat")
    @classmethod
    def centroid_lat_in_range(cls, v: float) -> float:
        if not -90 <= v <= 90:
            raise ValueError("centroid_lat must be between -90 and 90")
        return v

    @field_validator("centroid_lng")
    @classmethod
    def centroid_lng_in_range(cls, v: float) -> float:
        if not -180 <= v <= 180:
            raise ValueError("centroid_lng must be between -180 and 180")
        return v

    @field_validator("boundary")
    @classmethod
    def boundary_is_wkt_polygon(cls, v: str) -> str:
        if not v.startswith("POLYGON((") or not v.endswith("))"):
            raise ValueError("boundary must be a WKT POLYGON string starting with 'POLYGON((' and ending with '))'")
        return v


CREATE_MODELS: dict[NodeLabel, type[BaseModel]] = {
    NodeLabel.User: UserCreate,
    NodeLabel.Profile: ProfileCreate,
    NodeLabel.Lens: LensCreate,
    NodeLabel.Trip: TripCreate,
    NodeLabel.ItineraryItem: ItineraryItemCreate,
    NodeLabel.POI: POICreate,
    NodeLabel.NarrativeBeat: NarrativeBeatCreate,
    NodeLabel.Area: AreaCreate,
}


# ── UPDATE model ──


class NodeUpdate(BaseModel):
    """Partial update — only provided fields are SET."""

    properties: dict[str, Any]
