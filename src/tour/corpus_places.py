"""Trusted, corpus-side place semantics used before tour selection.

These contracts deliberately live outside :mod:`src.tour.artifact`.  Corpus
annotations describe source sentences and the places at which their narration
is valid; artifact evidence describes the *final*, potentially composed text.
Keeping the two layers separate prevents a source annotation from being
silently treated as authority for text that a model later changed.

Every aggregate is immutable and hash-bound.  A hash proves replay identity,
not trust: the certification coordinator must still allow-list ``authority_id``
from the frozen corpus build.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

SHA256_PATTERN = r"^[0-9a-f]{64}$"

PlaceResolutionState = Literal["resolved", "unresolved", "ambiguous"]
PerceivabilityState = Literal[
    "perceivable", "not_perceivable", "unresolved", "not_applicable"
]
ExperientialPlaceRelation = Literal[
    "primary", "feature_of", "off_site", "directional"
]
ManifestResolutionState = Literal["resolved", "contains_unresolved"]


def canonical_json(value: object) -> str:
    """Return the one JSON representation accepted by corpus hashes."""

    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def canonical_sha256(value: object) -> str:
    """SHA-256 of :func:`canonical_json`."""

    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _valid_coordinates(value: tuple[float, float]) -> tuple[float, float]:
    lat, lng = value
    if not math.isfinite(lat) or not -90.0 <= lat <= 90.0:
        raise ValueError(f"lat out of range: {lat}")
    if not math.isfinite(lng) or not -180.0 <= lng <= 180.0:
        raise ValueError(f"lng out of range: {lng}")
    return value


def _model_payload(model: BaseModel, *, excluded_hash: str) -> dict[str, object]:
    return model.model_dump(mode="json", exclude={excluded_hash})


class CoordinateProvenance(BaseModel):
    """Exact authority and source payload behind one coordinate pair."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    authority_kind: Literal[
        "corpus_record", "calibrated_provider", "human_authority"
    ]
    authority_id: str = Field(..., min_length=1)
    source_record_id: str = Field(..., min_length=1)
    coordinates: tuple[float, float]
    payload_json: str = Field(..., min_length=2)
    payload_sha256: str = Field(..., pattern=SHA256_PATTERN)

    _coordinates_are_valid = field_validator("coordinates")(_valid_coordinates)

    @model_validator(mode="after")
    def _payload_is_exact(self) -> CoordinateProvenance:
        try:
            parsed = json.loads(self.payload_json)
        except json.JSONDecodeError as exc:
            raise ValueError("coordinate provenance payload is not JSON") from exc
        if not isinstance(parsed, dict) or canonical_json(parsed) != self.payload_json:
            raise ValueError("coordinate provenance payload is not a canonical JSON object")
        if text_sha256(self.payload_json) != self.payload_sha256:
            raise ValueError("coordinate provenance hash does not match payload")
        if parsed.get("source_record_id") != self.source_record_id:
            raise ValueError("coordinate provenance source record differs from payload")
        if parsed.get("coordinates") != list(self.coordinates):
            raise ValueError("coordinate provenance coordinates differ from payload")
        return self

    @classmethod
    def build(
        cls,
        *,
        authority_kind: Literal[
            "corpus_record", "calibrated_provider", "human_authority"
        ],
        authority_id: str,
        source_record_id: str,
        coordinates: tuple[float, float],
        source_payload: dict[str, object] | None = None,
    ) -> CoordinateProvenance:
        payload = dict(source_payload or {})
        payload["source_record_id"] = source_record_id
        payload["coordinates"] = list(coordinates)
        payload_json = canonical_json(payload)
        return cls(
            authority_kind=authority_kind,
            authority_id=authority_id,
            source_record_id=source_record_id,
            coordinates=coordinates,
            payload_json=payload_json,
            payload_sha256=text_sha256(payload_json),
        )


class CanonicalPlaceIdentity(BaseModel):
    """Write-once corpus identity for a real place, independent of graph UUIDs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    canonical_place_id: str = Field(..., min_length=1)
    display_name: str = Field(..., min_length=1)
    aliases: tuple[str, ...] = ()
    source_identity_ids: tuple[str, ...] = ()
    resolution_state: PlaceResolutionState
    coordinate_provenance: CoordinateProvenance | None = None

    @model_validator(mode="after")
    def _resolved_place_has_coordinates(self) -> CanonicalPlaceIdentity:
        aliases = tuple(alias.strip() for alias in self.aliases)
        if aliases != self.aliases:
            raise ValueError("place aliases cannot have surrounding whitespace")
        if any(not alias for alias in aliases):
            raise ValueError("place aliases cannot be blank")
        if len({alias.casefold() for alias in aliases}) != len(aliases):
            raise ValueError("place aliases must be unique")
        if aliases != tuple(sorted(aliases, key=lambda value: (value.casefold(), value))):
            raise ValueError("place aliases must be in canonical order")
        if len(set(self.source_identity_ids)) != len(self.source_identity_ids):
            raise ValueError("place source identities must be unique")
        if self.source_identity_ids != tuple(sorted(self.source_identity_ids)):
            raise ValueError("place source identities must be in canonical order")
        if self.resolution_state == "resolved" and self.coordinate_provenance is None:
            raise ValueError("resolved canonical place requires coordinate provenance")
        if (
            self.coordinate_provenance is not None
            and self.coordinate_provenance.source_record_id not in self.source_identity_ids
        ):
            raise ValueError("coordinate source is absent from place source identities")
        return self

    @property
    def coordinates(self) -> tuple[float, float] | None:
        evidence = self.coordinate_provenance
        return evidence.coordinates if evidence is not None else None


class StableBeatIdentity(BaseModel):
    """Corpus-stable beat identity bound to its source document span."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    stable_beat_id: str = Field(..., min_length=1)
    source_document_id: str | None = Field(default=None, min_length=1)
    source_revision: str | None = Field(default=None, min_length=1)
    source_span_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    resolution_state: PlaceResolutionState

    @model_validator(mode="after")
    def _resolved_identity_has_a_source_span(self) -> StableBeatIdentity:
        source_fields = (
            self.source_document_id,
            self.source_revision,
            self.source_span_sha256,
        )
        if self.resolution_state == "resolved" and any(v is None for v in source_fields):
            raise ValueError("resolved stable beat identity requires a source revision and span")
        return self


class CorpusPlaceReference(BaseModel):
    """Typed material place claim in one exact corpus sentence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reference_id: str = Field(..., min_length=1)
    reference_kind: Literal["experiential", "contextual_historical"]
    relation: ExperientialPlaceRelation | None = None
    canonical_place_id: str | None = Field(default=None, min_length=1)
    feature_of_canonical_place_id: str | None = Field(default=None, min_length=1)
    resolution_state: PlaceResolutionState
    perceivability_state: PerceivabilityState

    @model_validator(mode="after")
    def _reference_lane_is_consistent(self) -> CorpusPlaceReference:
        if self.reference_kind == "contextual_historical":
            if self.relation is not None or self.feature_of_canonical_place_id is not None:
                raise ValueError("historical context cannot carry experiential semantics")
            if self.perceivability_state != "not_applicable":
                raise ValueError("historical context must mark perceivability not applicable")
            return self

        if self.relation is None:
            raise ValueError("experiential reference requires a typed relation")
        if self.perceivability_state == "not_applicable":
            raise ValueError("experiential reference requires a perceivability decision")
        if self.resolution_state == "resolved" and self.canonical_place_id is None:
            raise ValueError("resolved experiential reference requires a canonical place")
        if self.relation == "feature_of":
            if self.feature_of_canonical_place_id is None:
                raise ValueError("feature reference requires its canonical parent")
        elif self.feature_of_canonical_place_id is not None:
            raise ValueError("only a feature reference may name a canonical parent")
        return self


class CorpusSentencePlaceAssessment(BaseModel):
    """Complete classification for one exact sentence in a stable beat."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    stable_beat_id: str = Field(..., min_length=1)
    sentence_index: int = Field(..., ge=0)
    sentence_sha256: str = Field(..., pattern=SHA256_PATTERN)
    assessment: Literal[
        "unreviewed", "no_material_place_claim", "place_references"
    ]
    references: tuple[CorpusPlaceReference, ...] = ()
    resolution_state: PlaceResolutionState
    provenance_record_id: str = Field(..., min_length=1)

    @model_validator(mode="after")
    def _assessment_is_complete(self) -> CorpusSentencePlaceAssessment:
        if self.assessment == "unreviewed":
            if self.references or self.resolution_state == "resolved":
                raise ValueError("unreviewed assessment must be unresolved and reference-free")
            return self
        if self.assessment == "no_material_place_claim" and self.references:
            raise ValueError("no-place-claim assessment cannot contain references")
        if (
            self.assessment == "no_material_place_claim"
            and self.resolution_state != "resolved"
        ):
            raise ValueError("no-place-claim is a resolved review decision")
        if self.assessment == "place_references" and not self.references:
            raise ValueError("place-reference assessment cannot be empty")
        reference_ids = tuple(reference.reference_id for reference in self.references)
        if len(reference_ids) != len(set(reference_ids)):
            raise ValueError("sentence place assessment repeats a reference identity")
        if reference_ids != tuple(sorted(reference_ids)):
            raise ValueError("sentence place references must be in canonical order")
        if self.resolution_state == "resolved" and any(
            reference.resolution_state != "resolved" for reference in self.references
        ):
            raise ValueError("resolved sentence assessment contains unresolved references")
        return self


class CorpusBeatPlacePlan(BaseModel):
    """Hash-bound playback-location semantics for all sentences in one beat."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    place_plan_id: str = Field(..., min_length=1)
    stable_beat_id: str = Field(..., min_length=1)
    host_canonical_place_id: str | None = Field(default=None, min_length=1)
    sentence_assessments: tuple[CorpusSentencePlaceAssessment, ...] = Field(
        ..., min_length=1
    )
    resolution_state: PlaceResolutionState
    provenance_record_id: str = Field(..., min_length=1)
    plan_sha256: str = Field(..., pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def _plan_is_complete_and_bound(self) -> CorpusBeatPlacePlan:
        if any(
            assessment.stable_beat_id != self.stable_beat_id
            for assessment in self.sentence_assessments
        ):
            raise ValueError("beat plan contains an assessment for a different beat")
        indexes = tuple(item.sentence_index for item in self.sentence_assessments)
        if indexes != tuple(range(len(indexes))):
            raise ValueError("beat place assessments must cover contiguous sentence indexes")
        if self.resolution_state == "resolved":
            if self.host_canonical_place_id is None:
                raise ValueError("resolved beat plan requires a canonical host")
            if any(
                assessment.resolution_state != "resolved"
                for assessment in self.sentence_assessments
            ):
                raise ValueError("resolved beat plan contains unresolved assessments")

        experiential = tuple(
            reference
            for assessment in self.sentence_assessments
            for reference in assessment.references
            if reference.reference_kind == "experiential"
        )
        has_off_site = any(reference.relation == "off_site" for reference in experiential)
        has_host_semantics = any(reference.relation != "off_site" for reference in experiential)
        off_site_ids = {
            reference.canonical_place_id
            for reference in experiential
            if reference.relation == "off_site" and reference.canonical_place_id is not None
        }
        if self.resolution_state == "resolved" and (
            (has_off_site and has_host_semantics) or len(off_site_ids) > 1
        ):
            raise ValueError(
                "mixed or multi-destination experiential beat must remain unresolved"
            )
        if self.plan_sha256 != canonical_sha256(
            _model_payload(self, excluded_hash="plan_sha256")
        ):
            raise ValueError("beat place plan hash does not match its payload")
        return self

    @classmethod
    def build(cls, **values: object) -> CorpusBeatPlacePlan:
        payload = dict(values)
        payload.pop("plan_sha256", None)
        provisional = cls.model_construct(**payload, plan_sha256="0" * 64)
        return cls(**payload, plan_sha256=canonical_sha256(
            _model_payload(provisional, excluded_hash="plan_sha256")
        ))


class CorpusPlaceManifest(BaseModel):
    """Frozen allow-list of places, beat identities, and sentence place plans."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["ondoway-corpus-places-v1"] = "ondoway-corpus-places-v1"
    sentence_splitter_version: Literal["ondoway-sentence-splitter-v1"] = (
        "ondoway-sentence-splitter-v1"
    )
    manifest_id: str = Field(..., min_length=1)
    authority_id: str = Field(..., min_length=1)
    # Canonical digest of every selection-affecting source field.  It excludes
    # graph UUIDs and row order, and is re-derived by the materializer before a
    # typed snapshot is admitted.  This prevents a valid place sidecar from
    # being swapped onto different POI/beat content.
    selection_payload_sha256: str = Field(..., pattern=SHA256_PATTERN)
    resolution_state: ManifestResolutionState
    places: tuple[CanonicalPlaceIdentity, ...]
    beat_identities: tuple[StableBeatIdentity, ...]
    beat_place_plans: tuple[CorpusBeatPlacePlan, ...]
    manifest_sha256: str = Field(..., pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def _manifest_is_consistent_and_bound(self) -> CorpusPlaceManifest:
        place_ids = tuple(place.canonical_place_id for place in self.places)
        beat_ids = tuple(beat.stable_beat_id for beat in self.beat_identities)
        plan_ids = tuple(plan.place_plan_id for plan in self.beat_place_plans)
        planned_beat_ids = tuple(plan.stable_beat_id for plan in self.beat_place_plans)
        if place_ids != tuple(sorted(place_ids)):
            raise ValueError("manifest places must be in canonical order")
        if beat_ids != tuple(sorted(beat_ids)):
            raise ValueError("manifest beat identities must be in canonical order")
        if plan_ids != tuple(sorted(plan_ids)):
            raise ValueError("manifest beat plans must be in canonical order")
        for label, values in (
            ("canonical place", place_ids),
            ("stable beat", beat_ids),
            ("place plan", plan_ids),
            ("planned stable beat", planned_beat_ids),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"manifest repeats {label} identity")
        if not set(planned_beat_ids).issubset(beat_ids):
            raise ValueError("manifest contains a plan for an unknown stable beat")

        claimed_source_ids = [
            (source_id, place.canonical_place_id)
            for place in self.places
            for source_id in place.source_identity_ids
        ]
        source_owners: dict[str, str] = {}
        for source_id, canonical_place_id in claimed_source_ids:
            previous = source_owners.setdefault(source_id, canonical_place_id)
            if previous != canonical_place_id:
                raise ValueError(
                    "one source place identity is claimed by multiple canonical places"
                )

        known_places = set(place_ids)
        for plan in self.beat_place_plans:
            if (
                plan.resolution_state == "resolved"
                and plan.host_canonical_place_id not in known_places
            ):
                raise ValueError("resolved beat plan has an unknown canonical host")
            for assessment in plan.sentence_assessments:
                for reference in assessment.references:
                    if reference.reference_kind != "experiential":
                        continue
                    if (
                        reference.resolution_state == "resolved"
                        and reference.canonical_place_id not in known_places
                    ):
                        raise ValueError(
                            "resolved experiential reference targets an unknown place"
                        )
                    if (
                        reference.feature_of_canonical_place_id is not None
                        and reference.feature_of_canonical_place_id not in known_places
                    ):
                        raise ValueError("feature reference has an unknown canonical parent")

        contains_unresolved = any(
            item.resolution_state != "resolved"
            for item in (*self.places, *self.beat_identities, *self.beat_place_plans)
        )
        expected_state: ManifestResolutionState = (
            "contains_unresolved" if contains_unresolved else "resolved"
        )
        if self.resolution_state != expected_state:
            raise ValueError("manifest resolution state does not describe its records")
        if self.manifest_sha256 != canonical_sha256(
            _model_payload(self, excluded_hash="manifest_sha256")
        ):
            raise ValueError("corpus place manifest hash does not match its payload")
        return self

    @classmethod
    def build(cls, **values: object) -> CorpusPlaceManifest:
        payload = dict(values)
        payload.pop("manifest_sha256", None)
        payload["places"] = tuple(
            sorted(payload.get("places", ()), key=lambda item: item.canonical_place_id)
        )
        payload["beat_identities"] = tuple(
            sorted(
                payload.get("beat_identities", ()),
                key=lambda item: item.stable_beat_id,
            )
        )
        payload["beat_place_plans"] = tuple(
            sorted(
                payload.get("beat_place_plans", ()),
                key=lambda item: item.place_plan_id,
            )
        )
        provisional = cls.model_construct(**payload, manifest_sha256="0" * 64)
        return cls(**payload, manifest_sha256=canonical_sha256(
            _model_payload(provisional, excluded_hash="manifest_sha256")
        ))

    @property
    def places_by_id(self) -> dict[str, CanonicalPlaceIdentity]:
        return {place.canonical_place_id: place for place in self.places}

    @property
    def plans_by_id(self) -> dict[str, CorpusBeatPlacePlan]:
        return {plan.place_plan_id: plan for plan in self.beat_place_plans}


MaterializationReason = Literal[
    "host_semantics",
    "context_only",
    "off_site_resolved",
    "missing_manifest",
    "missing_place_plan",
    "stable_beat_mismatch",
    "unresolved_plan",
    "unresolved_reference",
    "mixed_host_and_off_site",
    "multiple_off_site_destinations",
    "destination_unresolved",
    "destination_out_of_budget",
]


class MaterializationDecision(BaseModel):
    """Replayable disposition for one typed beat before route selection."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    stable_beat_id: str = Field(..., min_length=1)
    place_plan_id: str = Field(..., min_length=1)
    source_poi_id: str = Field(..., min_length=1)
    source_canonical_place_id: str | None = Field(default=None, min_length=1)
    disposition: Literal["host", "relocated", "omitted"]
    destination_poi_id: str | None = Field(default=None, min_length=1)
    destination_canonical_place_id: str | None = Field(default=None, min_length=1)
    reason: MaterializationReason
    requires_dwell: bool = False
    vignette_eligible: bool = True

    @model_validator(mode="after")
    def _disposition_is_consistent(self) -> MaterializationDecision:
        success_reasons = {"host_semantics", "context_only", "off_site_resolved"}
        if self.disposition == "omitted":
            if self.destination_poi_id is not None:
                raise ValueError("omitted beat cannot have a destination POI")
            if self.requires_dwell or not self.vignette_eligible:
                raise ValueError("omitted beat cannot carry playback flags")
            if self.reason in success_reasons:
                raise ValueError("omitted beat cannot carry a success reason")
        else:
            if self.destination_poi_id is None:
                raise ValueError("retained beat requires a destination POI")
        if self.disposition == "relocated":
            if self.destination_canonical_place_id is None:
                raise ValueError("relocated beat requires a canonical destination")
            if not self.requires_dwell or self.vignette_eligible:
                raise ValueError("relocated off-site beat must be dwell-only")
            if self.reason != "off_site_resolved":
                raise ValueError("relocated beat requires the off-site success reason")
        if self.disposition == "host":
            if self.reason not in {"host_semantics", "context_only"}:
                raise ValueError("host beat requires a host success reason")
            if self.requires_dwell or not self.vignette_eligible:
                raise ValueError("host beat cannot carry off-site playback flags")
            if self.destination_canonical_place_id != self.source_canonical_place_id:
                raise ValueError("host beat destination must equal its canonical source")
        return self


class CorpusMaterializationPlan(BaseModel):
    """Hash-bound output of corpus place materialization for one snapshot."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_manifest_sha256: str = Field(..., pattern=SHA256_PATTERN)
    decisions: tuple[MaterializationDecision, ...]
    plan_sha256: str = Field(..., pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def _plan_hash_is_exact(self) -> CorpusMaterializationPlan:
        identities = tuple(decision.stable_beat_id for decision in self.decisions)
        if len(identities) != len(set(identities)):
            raise ValueError("materialization plan repeats a stable beat")
        if identities != tuple(sorted(identities)):
            raise ValueError("materialization decisions must be in canonical order")
        if self.plan_sha256 != canonical_sha256(
            _model_payload(self, excluded_hash="plan_sha256")
        ):
            raise ValueError("materialization plan hash does not match its payload")
        return self

    @classmethod
    def build(cls, **values: object) -> CorpusMaterializationPlan:
        payload = dict(values)
        payload.pop("plan_sha256", None)
        payload["decisions"] = tuple(
            sorted(
                payload.get("decisions", ()),
                key=lambda item: item.stable_beat_id,
            )
        )
        provisional = cls.model_construct(**payload, plan_sha256="0" * 64)
        return cls(**payload, plan_sha256=canonical_sha256(
            _model_payload(provisional, excluded_hash="plan_sha256")
        ))


__all__ = [
    "CanonicalPlaceIdentity",
    "CoordinateProvenance",
    "CorpusBeatPlacePlan",
    "CorpusMaterializationPlan",
    "CorpusPlaceManifest",
    "CorpusPlaceReference",
    "CorpusSentencePlaceAssessment",
    "ExperientialPlaceRelation",
    "ManifestResolutionState",
    "MaterializationDecision",
    "PerceivabilityState",
    "PlaceResolutionState",
    "StableBeatIdentity",
    "canonical_json",
    "canonical_sha256",
    "text_sha256",
]
