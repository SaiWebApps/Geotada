"""Tour-builder data contracts.

INPUT: TourInput — the user-supplied request (§3.1 of phase-1-design).
INTERMEDIATE: POI, BeatRef, TransitSegment, Route, POIBeats, BeatSequence.
OUTPUT: Script + Sentence + ValidationReport (§3.6 of phase-1-design).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TourInput(BaseModel):
    """User-supplied tour request. Mirrors §3.1 of phase-1-design.md."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    start: tuple[float, float] = Field(..., description="(lat, lng) origin point")
    duration_min: int = Field(..., gt=0, le=600)
    city_slug: str = Field(..., min_length=1)
    lenses: list[str] | None = None
    round_trip: bool = False
    theme_hint: str | None = None
    start_label: str | None = None

    @field_validator("start")
    @classmethod
    def _check_latlng(cls, v: tuple[float, float]) -> tuple[float, float]:
        lat, lng = v
        if not (-90.0 <= lat <= 90.0):
            raise ValueError(f"lat out of range: {lat}")
        if not (-180.0 <= lng <= 180.0):
            raise ValueError(f"lng out of range: {lng}")
        return v

    @field_validator("lenses")
    @classmethod
    def _normalize_lenses(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        cleaned = [s.strip() for s in v if s and s.strip()]
        return cleaned or None


class POI(BaseModel):
    """A POI loaded from the Neo4j corpus, snapshot-frozen for selection."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    id: str
    name: str
    tier: int = Field(..., ge=1, le=5)
    poi_role: str
    lat: float
    lng: float
    areas: tuple[str, ...] = ()
    beat_count: int = 0
    matching_lens_beat_count: int = 0


class BeatRef(BaseModel):
    """A NarrativeBeat reference carrying just what selection/ordering needs.

    Phase 3 added the optional ``script_body`` so generation can emit
    sentence-level traceable records without re-querying Neo4j. Phase 2
    selection/ordering ignores it; tests construct BeatRef without it.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    id: str
    poi_id: str
    sub_location: str | None = None
    trigger_address: str | None = None
    narrative_function: str | None = None
    beat_type: str | None = None
    emotional_register: str | None = None
    beat_length_class: str | None = None
    est_spoken_seconds: int = 0
    word_count: int = 0
    entities: tuple[str, ...] = ()
    subject_tag: str | None = None
    lenses: tuple[str, ...] = ()
    active_status: str = "active"
    script_body: str | None = None


class TransitSegment(BaseModel):
    """A walking segment between two ordered points along the route."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    from_poi_id: str | None
    to_poi_id: str | None
    distance_m: float = Field(..., ge=0)
    walk_seconds: int = Field(..., ge=0)


class TourabilityAssessment(BaseModel):
    """Phase 6 density-gate result — §3.7 of phase-1-design.

    Lives on this contract module (not in ``density.py``) so ``Route``
    can carry it as an optional field without an import cycle. The
    formula and thresholds remain in ``src/tour/density.py``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: str  # "GREEN" | "YELLOW" | "RED"
    walk_radius_m: float
    fill_ratio: float
    audio_capacity_seconds: int
    target_audio_seconds: int
    reachable_poi_count: int
    reachable_beat_count: int
    anchor_candidate_count: int
    cluster_compactness: float
    duration_min: int
    round_trip: bool
    max_supportable_duration_min: int | None = None
    one_way_alternative_destination: str | None = None


class Route(BaseModel):
    """Selected POIs in walking order, with transit segments and budgets.

    Phase 6 added the optional ``tourability`` slot so selection can
    surface a YELLOW density assessment to the skill without raising.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    pois: tuple[POI, ...]
    transits: tuple[TransitSegment, ...]
    total_walk_distance_m: float = Field(..., ge=0)
    total_walk_seconds: int = Field(..., ge=0)
    audio_budget_seconds: int
    spine_area: str | None = None
    target_audio_seconds: int = 0
    err_short_total_seconds: int = 0
    tourability: TourabilityAssessment | None = None


OrderingStrategy = Literal["sub_location", "trigger_address", "narrative_function"]


class POIBeats(BaseModel):
    """Ordered beats for a single POI under one of the three strategies."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    poi_id: str
    poi_name: str
    ordering_strategy: OrderingStrategy
    beats: tuple[BeatRef, ...]


class BeatSequence(BaseModel):
    """The ordered beat plan for a Route — Phase 3 turns this into a Script."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    poi_beats: tuple[POIBeats, ...]


# ---------------------------------------------------------------------------
# Phase 3 — Script (final output) + validation
# ---------------------------------------------------------------------------


SourceType = Literal["beat", "glue", "arith"]


class Sentence(BaseModel):
    """A single audio sentence with full source attribution.

    ``source_id`` is either a NarrativeBeat UUID (when source_type=='beat')
    or a whitelisted glue/arith label (when source_type in {'glue','arith'}).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str
    source_id: str
    source_type: SourceType
    stop_idx: int = Field(..., ge=0)


class ScriptPOI(BaseModel):
    """A flattened POI record for the Script's selected_pois roster."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    name: str
    tier: int = Field(..., ge=1, le=5)
    lat: float
    lng: float
    area: str | None = None
    dwell_seconds: int = 0
    beat_ids: tuple[str, ...] = ()


class ValidationReport(BaseModel):
    """Source-traceability + forbidden-phrase scan result for a Script."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    untraceable_sentences: tuple[Sentence, ...] = ()
    forbidden_phrase_hits: tuple[tuple[Sentence, str], ...] = ()

    @property
    def passed(self) -> bool:
        return not self.untraceable_sentences and not self.forbidden_phrase_hits


class Script(BaseModel):
    """Final tour-builder output. §3.6 of phase-1-design."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    city_slug: str
    generated_at: str
    inputs: TourInput
    total_audio_seconds: int = Field(..., ge=0)
    total_walking_seconds: int = Field(..., ge=0)
    total_walk_distance_m: int = Field(..., ge=0)
    total_planned_seconds: int = Field(..., ge=0)
    selected_pois: tuple[ScriptPOI, ...]
    lens_coverage: dict[str, int]
    script: tuple[Sentence, ...]
    validation: ValidationReport
