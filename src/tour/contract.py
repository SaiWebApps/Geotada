"""Tour-builder data contracts.

INPUT: TourInput — the user-supplied request (§3.1 of phase-1-design).
INTERMEDIATE: POI, BeatRef, TransitSegment, Route, POIBeats, BeatSequence.
OUTPUT: Script + Sentence + ValidationReport (§3.6 of phase-1-design).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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
    end: tuple[float, float] | None = Field(
        default=None,
        description=(
            "(lat, lng) destination B; None = no fixed destination (open walk / loop). "
            "Mutually exclusive with round_trip. B-materialization for ORDER (Steps 2.3/2.4): "
            "snap to the nearest in-corridor corpus POI when one is within ~150m, otherwise "
            "synthesize a sentinel POI at this exact coordinate."
        ),
    )

    @field_validator("start", "end")
    @classmethod
    def _check_latlng(
        cls, v: tuple[float, float] | None
    ) -> tuple[float, float] | None:
        # `end` is optional; `start` is required so pydantic rejects None before here.
        if v is None:
            return v
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

    @model_validator(mode="after")
    def _end_round_trip_mutex(self) -> TourInput:
        # A user-given destination and "return to A" are contradictory (spec §1).
        # A field_validator can't see round_trip, so the cross-field check lives here.
        if self.end is not None and self.round_trip:
            raise ValueError("end and round_trip are mutually exclusive")
        return self


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


class PhysicalCue(BaseModel):
    """One physical_cue entry from a beat — Phase 7.5 uses cue + feature_type
    to compose synthesized openers and to gate the Area-cold-open hoist.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    cue: str
    direction: str | None = None
    feature_type: str | None = None


class BeatRef(BaseModel):
    """A NarrativeBeat reference carrying just what selection/ordering needs.

    Phase 3 added the optional ``script_body`` so generation can emit
    sentence-level traceable records without re-querying Neo4j. Phase 2
    selection/ordering ignores it; tests construct BeatRef without it.

    Phase 7.5 added optional ``physical_cues`` + ``pronunciation`` so the
    refined cold-open hoist (Fix 1) and synthesized opener (Fix 2) can
    compose deterministically without re-querying Neo4j.

    M7 added ``source_passage``/``source_chunk_slug``/``key_claims`` for the
    VERIFY layer: ``source_passage`` is the verbatim span the beat was
    extracted from (rapidfuzz-matched against the source chunk for
    provenance) and ``key_claims`` are the atomic facts a beat-cited
    sentence must follow from (the faithfulness entailment pass). All three
    are optional — the corpus extraction pipeline backfills them; until then
    the provenance/faithfulness checks skip beats that lack them.
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
    physical_cues: tuple[PhysicalCue, ...] = ()
    pronunciation: str | None = None
    source_passage: str | None = None
    source_chunk_slug: str | None = None
    key_claims: tuple[str, ...] = ()


class TransitSegment(BaseModel):
    """A walking segment between two ordered points along the route.

    M2: ``walk_seconds``/``distance_m`` stay the pace-corrected haversine
    numbers the budget math uses; ``leg_seconds``/``polyline`` carry the
    road-network values when a RoutingClient produced them (``source``
    records their provenance). M3 moves selection scoring onto leg_seconds.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    from_poi_id: str | None
    to_poi_id: str | None
    distance_m: float = Field(..., ge=0)
    walk_seconds: int = Field(..., ge=0)
    leg_seconds: int | None = Field(default=None, ge=0)
    polyline: str | None = None  # encoded polyline (6-digit precision), routed legs only
    source: Literal["valhalla", "haversine"] = "haversine"


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


class ReachVerdict(BaseModel):
    """REACH output (§2.1, M5): how the reachable area was computed and which
    mode the tour operates in.

    ``mode`` maps the density gate's status: GREEN → standard; YELLOW →
    ambient (thin) or redirect (a denser one-way destination exists); RED →
    refuse (selection raises before a Route exists, so a Route never carries
    refuse in practice). ``degraded`` is True when the Valhalla isochrone was
    unavailable and REACH fell back to the analytic haversine envelope.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: Literal["standard", "ambient", "redirect", "refuse"]
    degraded: bool = False
    walk_minutes: int = Field(..., ge=1)
    reachable_poi_count: int = Field(default=0, ge=0)
    alternative_destination: str | None = None


class Route(BaseModel):
    """Selected POIs in walking order, with transit segments and budgets.

    Phase 6 added the optional ``tourability`` slot so selection can
    surface a YELLOW density assessment to the skill without raising.

    Phase 7.5 (Fix 3) added ``demoted_beats``: when two selected POIs
    sit within ~15m of each other and share an address-overlap signal,
    selection demotes the smaller-tier POI and merges its beats into
    the larger POI's pool. The mapping ``host_poi_id -> tuple[BeatRef]``
    lets the harness pull the demoted beats without re-querying.
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
    demoted_beats: dict[str, tuple[BeatRef, ...]] = Field(default_factory=dict)
    # M2 routed-metadata slots. ``routed`` is True iff every transit leg came
    # from Valhalla. ``route_polyline`` (stitched whole-route shape) and
    # ``backtrack_ratio``/``flow_score`` keep their defaults until the
    # milestones that compute them (M3/M4) land.
    routed: bool = False
    route_polyline: str | None = None
    backtrack_ratio: float = Field(default=0.0, ge=0)
    flow_score: float = Field(default=0.0, ge=0)
    # M5: the REACH verdict for the request that produced this route.
    reach: ReachVerdict | None = None


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


class RouteOptionStop(BaseModel):
    """One ordered stop inside a RouteOption (§2.8)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    poi_id: str
    name: str
    lat: float
    lng: float
    lens: str | None = None  # dominant lens of the stop's beats; None if unlensed
    visit_or_walk_past: Literal["visit", "walk_past"] = "visit"
    minutes: int = Field(default=0, ge=0)
    # Phase 3 spotlight model (spec s7). Additive with behavior-preserving
    # defaults: until Step 3.5 wires the spotlight effect into selection, every
    # stop is a full dwell with a zero score, so nothing downstream changes.
    band: Literal["dwell", "vignette"] = "dwell"  # spotlight output band (spec s3)
    spotlight: float = Field(default=0.0, ge=0)  # the computed spotlight score


class RouteOption(BaseModel):
    """§2.8 output contract — one per flavour, 2-3 per request (M6).

    Fields owned by later milestones keep honest defaults until they land:
    ``stop_audio`` and ``why_this_works`` are M7 (COMPOSE/VERIFY);
    ``route_polyline``/``flow_score``/``backtrack_ratio`` pass through the
    Route slots M3/M4 left default; ``profiles`` is §4 multi-profile;
    ``offline_package`` is the offline-replay bundle, post-MVP-core.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    route_id: str
    stops: tuple[RouteOptionStop, ...]
    stop_audio: dict[int, str] = Field(default_factory=dict)
    route_polyline: str | None = None
    eta_seconds: int = Field(..., ge=0)  # honest routed legs + dwell
    why_this_works: str | None = None
    lens_summary: dict[str, int] = Field(default_factory=dict)
    flow_score: float = Field(default=0.0, ge=0)
    backtrack_ratio: float = Field(default=0.0, ge=0)
    degraded: bool = False
    profiles: tuple[str, ...] = ()
    offline_package: dict | None = None
    # Phase 3 spotlight model (spec s7): per-corridor lens density surfaced to
    # the user. None until REACH measures and fills it (later in Phase 3), so
    # the default preserves today's behavior.
    lens_coverage_note: str | None = None


class ValidationReport(BaseModel):
    """Source-traceability + forbidden-phrase + (M7) provenance/faithfulness
    result for a Script. ``passed`` gates serving — a failing report blocks
    audio (§2.6).

    M7 added two independent VERIFY "teeth":
    - ``provenance_failures``: (beat_id, rapidfuzz_score) for beats whose
      ``source_passage`` did not match its source chunk above threshold.
    - ``faithfulness_failures``: (sentence, reason) for beat-cited sentences
      that the entailment pass found unsupported by the beat's ``key_claims``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    untraceable_sentences: tuple[Sentence, ...] = ()
    forbidden_phrase_hits: tuple[tuple[Sentence, str], ...] = ()
    provenance_failures: tuple[tuple[str, float], ...] = ()
    faithfulness_failures: tuple[tuple[Sentence, str], ...] = ()

    @property
    def passed(self) -> bool:
        return not (
            self.untraceable_sentences
            or self.forbidden_phrase_hits
            or self.provenance_failures
            or self.faithfulness_failures
        )


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
