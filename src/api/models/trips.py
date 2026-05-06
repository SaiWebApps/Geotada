"""Pydantic models for trip generation endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class TripGenerateRequest(BaseModel):
    """Input model for POST /trips/generate."""

    profile_id: str = Field(..., description="Profile node whose PREFERS_LENS edges select beats")
    center_lat: float = Field(..., ge=-90, le=90, description="Latitude of search center")
    center_lng: float = Field(..., ge=-180, le=180, description="Longitude of search center")
    radius_m: int = Field(default=3000, le=10000, description="Search radius in meters")
    max_stops: int = Field(default=10, le=30, description="Cap on itinerary items")
    duration_min: int | None = Field(default=None, description="Total trip budget in minutes")
    start_date: str = Field(..., description="ISO date for the trip start")
    end_date: str = Field(..., description="ISO date for the trip end")
    start_time: str = Field(default="09:00", description="Daily start time (HH:MM)")
    kid_friendly_only: bool = Field(default=False, description="Filter for kid-friendly POIs")
    trip_name: str | None = Field(
        default=None, description="Optional trip name; auto-generated if omitted"
    )

    @field_validator("start_time")
    @classmethod
    def validate_start_time(cls, v: str) -> str:
        """Validate HH:MM format."""
        parts = v.split(":")
        if len(parts) != 2:
            raise ValueError("start_time must be in HH:MM format")
        try:
            hour, minute = int(parts[0]), int(parts[1])
        except ValueError:
            raise ValueError("start_time must be in HH:MM format") from None
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("start_time must be a valid time (00:00 - 23:59)")
        return v


class GeneratedStop(BaseModel):
    """Output model for each stop in a generated trip."""

    sort_order: int
    poi_id: str
    poi_name: str
    lat: float
    lng: float
    beat_id: str
    lens_name: str
    lens_display: str
    duration_min: int
    importance_tier: int
    start_time: str
    script_body: str | None = None
    audio_url: str | None = None
    audio_duration_sec: float | None = None


class TripGenerateResponse(BaseModel):
    """Output model for POST /trips/generate."""

    trip_id: str
    trip_name: str
    profile_id: str
    total_stops: int
    total_duration_min: int
    anchor_count: int = Field(description="Number of gravity-5 POIs")
    flavour_count: int = Field(description="Number of gravity 1-4 POIs")
    stops: list[GeneratedStop]
