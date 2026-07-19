"""Pydantic models for trip generation endpoints."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from src import city_registry
from src.tour.contract import RouteOption


def _validate_city_slug(v: str) -> str:
    """Reject an unknown city at the edge (clear 422) instead of loading an
    empty corpus and emitting a broken/thin tour.

    Validates against ``servable_cities()`` (evaluated per-request, not the
    import-time ``SUPPORTED_CITIES``) so the prod cloud-filter takes effect: a
    locally-onboarded but not-yet-deployed city is rejected by the public prod
    /trips API while still being tourable by the local workbench."""
    slug = (v or "").strip().lower()
    allowed = city_registry.servable_cities()
    if slug not in allowed:
        raise ValueError(f"city_slug must be one of {sorted(allowed)}, got {v!r}")
    return slug


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
    city_slug: str = Field(
        default="paris",
        description="City corpus to tour; validated against city_registry.servable_cities()",
    )

    _validate_city = field_validator("city_slug")(_validate_city_slug)

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
    extra_beat_ids: list[str] = Field(
        default_factory=list,
        description="KE: ordered ids of this stop's beats the tour did NOT voice — the "
        "'keep exploring here' extras (uncapped plan minus voiced), most-important first",
    )
    extra_narration: str | None = Field(
        default=None,
        description="KE: composed 'keep exploring here' narration for this stop's extra beats, "
        "voiced on demand off the tour's time budget; null until /compose has run.",
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


class TripComposeRequest(BaseModel):
    """Input for POST /trips/{trip_id}/compose (Phase 4 Step 4.7)."""

    route_id: str = Field(
        description="The picked flavour: '<trip_id>-optN' from the generate response options"
    )


class TripComposeResponse(BaseModel):
    """Output for POST /trips/{trip_id}/compose: the re-persisted, composed stops.

    stop_id values are FRESH (the pick replaces the trip's items) and audio
    fields are null — per-stop audio is generated afterwards by the existing
    /audio/generate-trip-stops flow, which only ever voices narration that
    passed the compose VERIFY gate.
    """

    trip_id: str
    route_id: str
    attempts: int = Field(description="Compose attempts consumed (1 clean, 2 after recompose)")
    stops: list[GeneratedStop]


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
    city_slug: str = Field(
        default="paris",
        description="City corpus to tour; validated against city_registry.servable_cities()",
    )

    _validate_city = field_validator("city_slug")(_validate_city_slug)
    # Opt in to the LLM "AI voice" layer: rewrite the stitched narration into one
    # flowing, de-duplicated story (fusing repeated facts), behind the faithfulness
    # + content-loss gates with graceful per-stop repair. Off = the fast
    # deterministic stitch. The workbench sends true to preview the real app voice.
    compose: bool = False
    # Which REAL narrator writes the tour when compose=true: None/'anthropic'/'opus'
    # = Claude Opus (default); 'openai'/'chatgpt' = ChatGPT — the workbench's
    # Opus-vs-ChatGPT writing comparison. There is NO 'mock' provider (a comparison
    # is never served the stitcher passthrough). Unknown values fall back to Opus.
    provider: str | None = None
    # Opt in to the AUTHOR ENGINE (off by default): instead of fusing stitched
    # beat-sentences (compose), write each stop FRESH from its facts, then a semantic
    # fact-check-and-repair loop restores dropped / strips invented facts, falling back
    # to the grounded stitch when a stop won't converge. Strictly OPT-IN and strictly
    # costlier than compose (an Opus draft per stop) — an env default could never flip
    # it on, so it is a per-request field only. ``engine="author"`` turns it on; anything
    # else (None/'compose') is today's behavior, byte-identical.
    engine: str | None = None
    # Opt in to the CORRECT-DON'T-REJECT corrector (off by default, compose-only).
    # When a composed sentence fails the faithfulness gate, the default path replaces
    # it immediately with grounded stitch; with this on, the corrector first attempts
    # up to two Opus repairs (trim, then narrator-voice rewrite) and only floors if
    # both fail — on the source branch's 9-stop acceptance run that rescued ~23% of
    # flagged sentences from degrading to raw stitch. Strictly OPT-IN and strictly
    # costlier (an extra Opus call per flagged sentence), so like ``engine`` it is a
    # per-request field with NO env default — a deployment can never flip everyone
    # onto the pricier path. Ignored unless ``compose`` is true.
    correct: bool = False


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
    # KE9: this dwell stop has "keep exploring here" EXTRAS — beats the tour's
    # time budget capped out (poi_id present in overflow_by_poi with non-empty
    # overflow). A bool flag, not the extra_beat_ids list: the workbench only
    # needs to render a badge, and the preview must not leak full beat-id lists.
    # Always False for vignette (walk-past) stops. Default False is
    # behavior-preserving.
    has_deeper_dive: bool = False


class TripPreviewTourability(BaseModel):
    """Density / delivery disclosure shipped alongside a generated preview.

    Phase 6: YELLOW = "generate but WARN". C11a adds GREEN-but-``delivered_thin``:
    a GREEN-density pool that still delivers thin (audio far under the request or
    a single dominating stop) — the engine-side answer to the 2026-07-02
    pool-vs-delivered gap. A fully-GREEN rich tour still ships tourability=null."""

    status: Literal["GREEN", "YELLOW"]
    delivered_thin: bool = False
    fill_ratio: float
    # Lens-specific fill (audio matching the requested lenses / target). None when
    # no lenses were requested. Lets the surface disclose "thin FOR your interest"
    # distinctly from the lens-agnostic overall fill_ratio.
    on_lens_fill_ratio: float | None = None
    anchor_candidates: int
    reachable_poi_count: int
    max_supportable_duration_min: int | None = None
    one_way_alternative_destination: str | None = None


class TripPreviewResponse(BaseModel):
    """Per-stop narration for a generated tour — no audio, no persistence. The
    client fetches audio per stop via POST /audio/preview on the narration text."""

    spine_area: str | None = None
    total_audio_min: int
    stops: list[TripPreviewStop]
    # Phase 3 spotlight model (spec s7): per-corridor lens density surfaced to
    # the user. None until REACH measures and fills it (later in Phase 3).
    lens_coverage_note: str | None = None
    # None = GREEN (no warning needed). RED never reaches a 200 response.
    tourability: TripPreviewTourability | None = None
    # compose outcome when the request opted in: 'composed' (fully AI-voiced),
    # 'composed_partial' (some stops fell back to the grounded stitch via repair),
    # 'refused' (compose failed even after repair — stitched shown), or 'stitched'
    # (compose not requested). None only on legacy paths.
    compose_status: str | None = None
    # Which narrator actually wrote this tour ('anthropic' | 'openai'), so the
    # workbench can label an Opus-vs-ChatGPT comparison. None when not composed.
    provider: str | None = None
    # Objective spoken-narration quality signals for the composed tour (stilted vs
    # engagement scores + the per-100-word tells), so the comparison is MEASURED,
    # not vibes. None when not composed. See tour.narration_quality.
    narration_quality: dict | None = None
