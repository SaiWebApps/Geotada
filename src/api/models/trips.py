"""Pydantic models for trip generation endpoints."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from src.tour.contract import RouteOption


class TripGenerateRequest(BaseModel):
    """Input model for POST /trips/generate."""

    profile_id: str = Field(..., description="Profile node whose PREFERS_LENS edges select beats")
    center_lat: float = Field(..., ge=-90, le=90, description="Latitude of search center")
    center_lng: float = Field(..., ge=-180, le=180, description="Longitude of search center")
    end_lat: float | None = Field(
        default=None,
        ge=-90,
        le=90,
        description="Optional fixed-destination latitude (B). With end_lng, threads into "
        "TourInput.end; mutually exclusive with round_trip (rejected by the engine).",
    )
    end_lng: float | None = Field(
        default=None,
        ge=-180,
        le=180,
        description="Optional fixed-destination longitude (B). Pairs with end_lat.",
    )
    radius_m: int = Field(default=3000, le=10000, description="Search radius in meters")
    max_stops: int = Field(default=10, le=30, description="Cap on itinerary items")
    duration_min: int | None = Field(
        default=None,
        ge=1,
        le=600,
        description="Total trip budget in minutes (engine cap: 600)",
    )
    start_date: str = Field(..., description="ISO date for the trip start")
    end_date: str = Field(..., description="ISO date for the trip end")
    start_time: str = Field(default="09:00", description="Daily start time (HH:MM)")
    kid_friendly_only: bool = Field(default=False, description="Filter for kid-friendly POIs")
    trip_name: str | None = Field(
        default=None, description="Optional trip name; auto-generated if omitted"
    )
    lenses: list[str] | None = Field(
        default=None,
        description="Lens slugs to bias selection; precedence: request -> profile -> city default",
    )
    round_trip: bool = Field(
        default=False, description="Return to the start point (loops the route)"
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

    @field_validator("lenses")
    @classmethod
    def normalize_lenses(cls, v: list[str] | None) -> list[str] | None:
        """Drop blanks/whitespace; empty -> None. Mirrors TourInput in src/tour/contract.py."""
        if v is None:
            return None
        cleaned = [s.strip() for s in v if s and s.strip()]
        return cleaned or None


class GeneratedStop(BaseModel):
    """Output model for each stop in a generated trip."""

    sort_order: int
    stop_id: str | None = Field(
        default=None,
        description="ItineraryItem id — addresses this stop for per-stop narration audio (Phase 1)",
    )
    poi_id: str
    poi_name: str
    lat: float
    lng: float
    beat_id: str
    lens_name: str | None = None
    lens_display: str | None = None
    duration_min: int
    importance_tier: int
    start_time: str
    script_body: str | None = None
    narration: str | None = Field(
        default=None,
        description="Stitched per-stop narration (cold-open, beats, transit, closing) voiced as "
        "this stop's audio (Phase 1); exposed for web verification (Phase 1.5).",
    )
    audio_url: str | None = None
    audio_duration_sec: float | None = None
    beat_ids: list[str] = Field(
        default_factory=list,
        description="All beats narrated at this stop (engine output); beat_id is the primary/first",
    )
    dwell_seconds: int = Field(default=0, description="Engine-computed time spent at this stop")
    transit_polyline: str | None = Field(
        default=None,
        description="Encoded polyline (6-digit precision) of the walking leg INTO this stop; "
        "null when routing fell back to haversine (Valhalla not running)",
    )


class TripGenerateResponse(BaseModel):
    """Output model for POST /trips/generate."""

    trip_id: str
    trip_name: str
    profile_id: str
    total_stops: int
    total_duration_min: int
    anchor_count: int = Field(description="Number of gravity-5 POIs")
    flavour_count: int = Field(description="Number of gravity 1-4 POIs")
    lens_coverage: dict[str, int] = Field(
        default_factory=dict,
        description="Engine lens_coverage: lens slug -> beat count across the tour",
    )
    stops: list[GeneratedStop]
    options: list[RouteOption] = Field(
        default_factory=list,
        description="M6 k-flavours (§2.8): up to 3 distinct tour options; options[0] "
        "is the persisted trip. Computed per request, not persisted.",
    )


class TripPreviewRequest(BaseModel):
    """Web-first preview (Phase 1.5): generate a tour's per-stop narration WITHOUT
    a profile and WITHOUT persisting anything."""

    center_lat: float = Field(..., ge=-90, le=90)
    center_lng: float = Field(..., ge=-180, le=180)
    end_lat: float | None = Field(default=None, ge=-90, le=90)
    end_lng: float | None = Field(default=None, ge=-180, le=180)
    duration_min: int | None = Field(default=None, ge=1, le=600)
    lenses: list[str] | None = None
    round_trip: bool = False


class TripPreviewStop(BaseModel):
    """One stop in a preview: ordered, with its stitched narration text."""

    sort_order: int
    poi_name: str
    lat: float
    lng: float
    narration: str
    minutes: int
    # Phase 3 spotlight model (spec s7). Additive with behavior-preserving
    # defaults: a full dwell stop with a zero score until Step 3.5 wires the
    # spotlight effect into selection.
    band: Literal["dwell", "vignette"] = "dwell"
    spotlight: float = 0.0


class TripPreviewResponse(BaseModel):
    """Per-stop narration for a generated tour — no audio, no persistence. The
    client fetches audio per stop via POST /audio/preview on the narration text."""

    spine_area: str | None = None
    total_audio_min: int
    stops: list[TripPreviewStop]
    # Phase 3 spotlight model (spec s7): per-corridor lens density surfaced to
    # the user. None until REACH measures and fills it (later in Phase 3).
    lens_coverage_note: str | None = None
