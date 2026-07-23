"""Pure, fail-closed corpus place materialization before tour selection.

The input is an ordinary :class:`CorpusSnapshot` plus a frozen place manifest.
The output is the *only* typed snapshot admitted to density/selection: a
deep-immutable :class:`MaterializedCorpusSnapshot` in which every eligible beat
has one valid playback context.  This step runs before density, greedy
selection, Held--Karp ordering, vignette selection, or generation.

No geocoding or semantic guessing occurs here.  Unresolved, ambiguous,
multi-destination, mixed host/off-site, and out-of-budget off-site beats are
omitted.  Historical context never changes playback location.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from .contract import POI, BeatRef
from .corpus_places import (
    CanonicalPlaceIdentity,
    CorpusBeatPlacePlan,
    CorpusMaterializationPlan,
    CorpusPlaceManifest,
    MaterializationDecision,
    StableBeatIdentity,
    canonical_json,
    canonical_sha256,
    text_sha256,
)
from .generation import SENTENCE_SPLITTER_VERSION, split_sentences
from .selection import (
    _MATERIALIZED_SNAPSHOT_TOKEN,
    CorpusSnapshot,
    MaterializedCorpusSnapshot,
)


@dataclass(frozen=True)
class PlaceMaterializationResult:
    """Validated snapshot plus the exact, hash-bound beat dispositions."""

    snapshot: MaterializedCorpusSnapshot
    plan: CorpusMaterializationPlan


def _frozen_mapping(values: Mapping) -> MappingProxyType:
    return MappingProxyType(dict(values))


def _canonical_poi_id(canonical_place_id: str) -> str:
    digest = hashlib.sha256(canonical_place_id.encode("utf-8")).hexdigest()[:24]
    return f"__canonical_place__{digest}"


def _source_selection_payload(snapshot: CorpusSnapshot) -> dict[str, object]:
    """Canonical source fields that can affect selection or narration.

    Graph UUIDs, dictionary insertion order, and database row order are
    intentionally excluded.  POIs are keyed by canonical ID and beats by
    stable beat ID; all other model fields are retained.  The manifest binds
    this payload, so changing tier, coordinates, prose, active status, lenses,
    provenance, areas, or any future additive model field invalidates it.
    """

    raw_pois = tuple(snapshot.pois)
    poi_by_raw_id: dict[str, POI] = {}
    for poi in raw_pois:
        if poi.id in poi_by_raw_id:
            raise ValueError("source snapshot repeats a raw POI identity")
        poi_by_raw_id[poi.id] = poi

    pois: list[dict[str, object]] = []
    for poi in raw_pois:
        if poi.canonical_place_id is None:
            raise ValueError("typed source POI lacks canonical_place_id")
        payload = poi.model_dump(mode="json", exclude={"id"})
        payload["aliases"] = sorted(
            payload.get("aliases", ()), key=lambda value: (value.casefold(), value)
        )
        payload["areas"] = sorted(payload.get("areas", ()))
        pois.append(payload)

    beats: list[dict[str, object]] = []
    for source_poi_id, refs in snapshot.beats_by_poi.items():
        host = poi_by_raw_id.get(source_poi_id)
        if host is None:
            raise ValueError("source snapshot has beats for an unknown POI")
        for beat in tuple(refs):
            if beat.poi_id != source_poi_id:
                raise ValueError("beat mapping key differs from BeatRef.poi_id")
            if beat.stable_beat_id is None:
                raise ValueError("typed source beat lacks stable_beat_id")
            payload = beat.model_dump(mode="json", exclude={"id", "poi_id"})
            payload["lenses"] = sorted(payload.get("lenses", ()))
            payload["host_canonical_place_id"] = host.canonical_place_id
            beats.append(payload)

    return {
        "pois": sorted(pois, key=canonical_json),
        "beats": sorted(beats, key=lambda item: str(item["stable_beat_id"])),
        "area_types": sorted((str(k), str(v)) for k, v in snapshot.area_types.items()),
        "adjacent_areas": sorted(
            (str(k), sorted(str(item) for item in values))
            for k, values in snapshot.adjacent_areas.items()
        ),
        "lens_neighbors": sorted(
            (str(k), sorted(str(item) for item in values))
            for k, values in snapshot.lens_neighbors.items()
        ),
    }


def selection_payload_sha256(snapshot: CorpusSnapshot) -> str:
    """Digest used by ``CorpusPlaceManifest.selection_payload_sha256``."""

    return canonical_sha256(_source_selection_payload(snapshot))


def _manifest_indexes(
    manifest: CorpusPlaceManifest,
) -> tuple[
    dict[str, CanonicalPlaceIdentity],
    dict[str, StableBeatIdentity],
    dict[str, CorpusBeatPlacePlan],
]:
    return (
        manifest.places_by_id,
        {item.stable_beat_id: item for item in manifest.beat_identities},
        manifest.plans_by_id,
    )


def _validate_manifest_coverage(
    snapshot: CorpusSnapshot,
    manifest: CorpusPlaceManifest,
    *,
    places_by_id: dict[str, CanonicalPlaceIdentity],
    identities_by_id: dict[str, StableBeatIdentity],
    plans_by_id: dict[str, CorpusBeatPlacePlan],
) -> None:
    if manifest.sentence_splitter_version != SENTENCE_SPLITTER_VERSION:
        raise ValueError("place manifest uses a different sentence splitter version")
    actual_payload_sha256 = selection_payload_sha256(snapshot)
    if actual_payload_sha256 != manifest.selection_payload_sha256:
        raise ValueError("place manifest was built for different selection source data")

    pois_by_raw_id = {poi.id: poi for poi in snapshot.pois}
    raw_poi_ids = set(pois_by_raw_id)
    source_place_ids = {poi.canonical_place_id for poi in snapshot.pois}
    known_place_ids = set(places_by_id)
    if None in source_place_ids or not source_place_ids.issubset(known_place_ids):
        raise ValueError("source snapshot contains a canonical place absent from manifest")

    source_beats = tuple(
        beat for beats in snapshot.beats_by_poi.values() for beat in tuple(beats)
    )
    if any(beat.poi_id not in raw_poi_ids for beat in source_beats):
        raise ValueError("source beat names an unknown POI")
    stable_ids = tuple(beat.stable_beat_id for beat in source_beats)
    plan_ids = tuple(beat.place_plan_id for beat in source_beats)
    if None in stable_ids or len(stable_ids) != len(set(stable_ids)):
        raise ValueError("typed source beats require unique stable identities")
    if None in plan_ids or len(plan_ids) != len(set(plan_ids)):
        raise ValueError("typed source beats require unique place plan identities")

    manifest_beat_ids = set(identities_by_id)
    manifest_plan_ids = set(plans_by_id)
    if set(stable_ids) != manifest_beat_ids:
        raise ValueError("manifest stable beat coverage is missing or contains extras")
    if set(plan_ids) != manifest_plan_ids:
        raise ValueError("manifest place plan coverage is missing or contains extras")

    for beat in source_beats:
        assert beat.stable_beat_id is not None
        assert beat.place_plan_id is not None
        identity = identities_by_id[beat.stable_beat_id]
        plan = plans_by_id[beat.place_plan_id]
        if plan.stable_beat_id != beat.stable_beat_id:
            raise ValueError("place plan is attached to a different stable beat")
        host = pois_by_raw_id[beat.poi_id]
        if plan.host_canonical_place_id != host.canonical_place_id:
            raise ValueError("beat place plan is bound to a different canonical host")
        if identity.source_span_sha256 is not None:
            if beat.source_passage is None:
                raise ValueError("source-bound beat is missing source_passage")
            if text_sha256(beat.source_passage) != identity.source_span_sha256:
                raise ValueError("stable beat source span hash does not match")
        source_sentences = split_sentences(beat.script_body or "")
        assessments = plan.sentence_assessments
        if len(source_sentences) != len(assessments):
            raise ValueError("beat place plan does not cover every source sentence")
        for index, (sentence, assessment) in enumerate(
            zip(source_sentences, assessments, strict=True)
        ):
            if assessment.sentence_index != index:
                raise ValueError("beat place assessment indexes are incomplete")
            if assessment.sentence_sha256 != text_sha256(sentence):
                raise ValueError("beat place assessment sentence hash does not match")

    # A resolved source POI must use the manifest's exact coordinate authority;
    # otherwise a swapped graph location could pass while the sidecar remains
    # unchanged.  Alias rows may differ in display name but not in place facts.
    for poi in snapshot.pois:
        assert poi.canonical_place_id is not None
        place = places_by_id[poi.canonical_place_id]
        if place.resolution_state == "resolved":
            if poi.coordinate_provenance != place.coordinate_provenance:
                raise ValueError("source POI coordinate provenance differs from manifest")
            if place.coordinates != (poi.lat, poi.lng):
                raise ValueError("source POI coordinates differ from canonical authority")


def _canonical_source_pois(
    snapshot: CorpusSnapshot,
    places_by_id: dict[str, CanonicalPlaceIdentity],
) -> tuple[dict[str, POI], dict[str, str]]:
    """Collapse aliases by canonical ID and return raw-id -> canonical-id."""

    grouped: dict[str, list[POI]] = {}
    raw_to_canonical: dict[str, str] = {}
    for poi in snapshot.pois:
        assert poi.canonical_place_id is not None
        grouped.setdefault(poi.canonical_place_id, []).append(poi)
        raw_to_canonical[poi.id] = poi.canonical_place_id

    canonical: dict[str, POI] = {}
    for canonical_id, rows in grouped.items():
        place = places_by_id[canonical_id]
        if place.resolution_state != "resolved" or place.coordinates is None:
            # The record remains in the manifest for review but cannot enter a
            # route or density calculation.
            continue
        selection_shapes = set()
        for row in rows:
            shape = row.model_dump(
                mode="json",
                exclude={
                    "id",
                    "name",
                    "aliases",
                    "beat_count",
                    "matching_lens_beat_count",
                },
            )
            shape["areas"] = sorted(row.areas)
            selection_shapes.add(canonical_json(shape))
        if len(selection_shapes) != 1:
            raise ValueError(
                "canonical alias rows disagree on tier, role, or area membership"
            )
        # Alias collapse is deterministic and independent of raw graph UUIDs.
        # Tier/role come from the best existing record; synthetic destinations
        # use fixed neutral values in _synthetic_destination instead.
        exemplar = min(
            rows,
            key=lambda row: (
                -row.tier,
                row.poi_role,
                row.name.casefold(),
                row.lat,
                row.lng,
            ),
        )
        alias_candidates = {
            alias
            for row in rows
            for alias in (*row.aliases, row.name)
            if alias and alias != place.display_name
        }
        aliases_by_casefold: dict[str, str] = {}
        for alias in sorted(alias_candidates, key=lambda value: (value.casefold(), value)):
            aliases_by_casefold.setdefault(alias.casefold(), alias)
        canonical[canonical_id] = exemplar.model_copy(
            update={
                "id": _canonical_poi_id(canonical_id),
                "name": place.display_name,
                "lat": place.coordinates[0],
                "lng": place.coordinates[1],
                "aliases": tuple(aliases_by_casefold.values()),
                "areas": tuple(sorted(exemplar.areas)),
                "coordinate_provenance": place.coordinate_provenance,
                "beat_count": 0,
                "matching_lens_beat_count": 0,
                "requires_dwell": False,
                "vignette_eligible": True,
            }
        )
    return canonical, raw_to_canonical


def _synthetic_destination(place: CanonicalPlaceIdentity) -> POI:
    if place.resolution_state != "resolved" or place.coordinates is None:
        raise ValueError("cannot synthesize an unresolved canonical destination")
    # Never inherit gravity, tier, role, or area from the beat's source host.
    # Dwell eligibility comes only from the explicit off-site decision.
    return POI(
        id=_canonical_poi_id(place.canonical_place_id),
        canonical_place_id=place.canonical_place_id,
        name=place.display_name,
        aliases=place.aliases,
        coordinate_provenance=place.coordinate_provenance,
        tier=1,
        poi_role="stop",
        lat=place.coordinates[0],
        lng=place.coordinates[1],
        areas=(),
        beat_count=0,
        matching_lens_beat_count=0,
        requires_dwell=True,
        vignette_eligible=False,
    )


def _decision_for_beat(
    *,
    beat: BeatRef,
    source_canonical_id: str,
    source_destination_poi_id: str | None,
    plan: CorpusBeatPlacePlan,
    identity: StableBeatIdentity,
    places_by_id: dict[str, CanonicalPlaceIdentity],
    admitted_canonical_place_ids: frozenset[str] | None,
) -> MaterializationDecision:
    assert beat.stable_beat_id is not None
    assert beat.place_plan_id is not None
    if plan.stable_beat_id != beat.stable_beat_id:
        return MaterializationDecision(
            stable_beat_id=beat.stable_beat_id,
            place_plan_id=beat.place_plan_id,
            source_poi_id=_canonical_poi_id(source_canonical_id),
            source_canonical_place_id=source_canonical_id,
            disposition="omitted",
            reason="stable_beat_mismatch",
        )

    experiential = tuple(
        reference
        for assessment in plan.sentence_assessments
        for reference in assessment.references
        if reference.reference_kind == "experiential"
    )
    off_site = tuple(reference for reference in experiential if reference.relation == "off_site")
    host_semantics = tuple(
        reference for reference in experiential if reference.relation != "off_site"
    )
    off_site_ids = {
        reference.canonical_place_id
        for reference in off_site
        if reference.canonical_place_id is not None
    }
    if off_site and host_semantics:
        reason = "mixed_host_and_off_site"
    elif len(off_site_ids) > 1:
        reason = "multiple_off_site_destinations"
    else:
        reason = None
    if reason is not None:
        return MaterializationDecision(
            stable_beat_id=beat.stable_beat_id,
            place_plan_id=beat.place_plan_id,
            source_poi_id=_canonical_poi_id(source_canonical_id),
            source_canonical_place_id=source_canonical_id,
            disposition="omitted",
            reason=reason,
        )

    if identity.resolution_state != "resolved" or plan.resolution_state != "resolved":
        return MaterializationDecision(
            stable_beat_id=beat.stable_beat_id,
            place_plan_id=beat.place_plan_id,
            source_poi_id=_canonical_poi_id(source_canonical_id),
            source_canonical_place_id=source_canonical_id,
            disposition="omitted",
            reason="unresolved_plan",
        )
    if any(
        reference.resolution_state != "resolved"
        or reference.perceivability_state in {"unresolved", "not_perceivable"}
        for reference in experiential
    ):
        return MaterializationDecision(
            stable_beat_id=beat.stable_beat_id,
            place_plan_id=beat.place_plan_id,
            source_poi_id=_canonical_poi_id(source_canonical_id),
            source_canonical_place_id=source_canonical_id,
            disposition="omitted",
            reason="unresolved_reference",
        )

    if not off_site:
        # Context-only, primary, feature_of, and directional narration all play
        # at the host.  Validate the relations that explicitly identify it.
        invalid_host = any(
            (
                reference.relation == "primary"
                and reference.canonical_place_id != source_canonical_id
            )
            or (
                reference.relation == "feature_of"
                and reference.feature_of_canonical_place_id != source_canonical_id
            )
            for reference in host_semantics
        )
        if invalid_host or source_destination_poi_id is None:
            return MaterializationDecision(
                stable_beat_id=beat.stable_beat_id,
                place_plan_id=beat.place_plan_id,
                source_poi_id=_canonical_poi_id(source_canonical_id),
                source_canonical_place_id=source_canonical_id,
                disposition="omitted",
                reason="unresolved_reference",
            )
        return MaterializationDecision(
            stable_beat_id=beat.stable_beat_id,
            place_plan_id=beat.place_plan_id,
            source_poi_id=_canonical_poi_id(source_canonical_id),
            source_canonical_place_id=source_canonical_id,
            disposition="host",
            destination_poi_id=source_destination_poi_id,
            destination_canonical_place_id=source_canonical_id,
            reason="host_semantics" if experiential else "context_only",
        )

    destination_id = next(iter(off_site_ids), None)
    place = places_by_id.get(destination_id or "")
    if (
        destination_id is None
        or place is None
        or place.resolution_state != "resolved"
        or place.coordinates is None
    ):
        return MaterializationDecision(
            stable_beat_id=beat.stable_beat_id,
            place_plan_id=beat.place_plan_id,
            source_poi_id=_canonical_poi_id(source_canonical_id),
            source_canonical_place_id=source_canonical_id,
            disposition="omitted",
            destination_canonical_place_id=destination_id,
            reason="destination_unresolved",
        )
    if (
        admitted_canonical_place_ids is not None
        and destination_id not in admitted_canonical_place_ids
    ):
        return MaterializationDecision(
            stable_beat_id=beat.stable_beat_id,
            place_plan_id=beat.place_plan_id,
            source_poi_id=_canonical_poi_id(source_canonical_id),
            source_canonical_place_id=source_canonical_id,
            disposition="omitted",
            destination_canonical_place_id=destination_id,
            reason="destination_out_of_budget",
        )
    return MaterializationDecision(
        stable_beat_id=beat.stable_beat_id,
        place_plan_id=beat.place_plan_id,
        source_poi_id=_canonical_poi_id(source_canonical_id),
        source_canonical_place_id=source_canonical_id,
        disposition="relocated",
        destination_poi_id=_canonical_poi_id(destination_id),
        destination_canonical_place_id=destination_id,
        reason="off_site_resolved",
        requires_dwell=True,
        vignette_eligible=False,
    )


def _materialized_snapshot_sha256(
    *,
    snapshot: CorpusSnapshot,
    manifest_sha256: str,
    plan_sha256: str,
) -> str:
    return canonical_sha256(
        {
            "selection_payload": _source_selection_payload(snapshot),
            "manifest_sha256": manifest_sha256,
            "materialization_plan_sha256": plan_sha256,
        }
    )


def validate_materialized_corpus_snapshot(
    snapshot: MaterializedCorpusSnapshot,
) -> None:
    """Recompute materialized coherence before any selection consumer runs."""

    manifest = snapshot.place_manifest
    plan = snapshot.materialization_plan
    if manifest is None or plan is None:
        raise ValueError("materialized snapshot is missing its manifest or plan")
    if plan.source_manifest_sha256 != manifest.manifest_sha256:
        raise ValueError("materialized snapshot plan belongs to another manifest")
    places_by_id, identities_by_id, plans_by_id = _manifest_indexes(manifest)

    pois_by_id = {poi.id: poi for poi in snapshot.pois}
    if len(pois_by_id) != len(snapshot.pois):
        raise ValueError("materialized snapshot repeats a POI identity")
    canonical_ids = tuple(poi.canonical_place_id for poi in snapshot.pois)
    if None in canonical_ids or len(canonical_ids) != len(set(canonical_ids)):
        raise ValueError("materialized snapshot must contain unique canonical POIs")
    for poi in snapshot.pois:
        assert poi.canonical_place_id is not None
        if poi.id != _canonical_poi_id(poi.canonical_place_id):
            raise ValueError("materialized POI identity is not canonical and deterministic")
        place = places_by_id.get(poi.canonical_place_id)
        if place is None or place.resolution_state != "resolved":
            raise ValueError("materialized snapshot contains an unresolved place")
        if place.coordinates != (poi.lat, poi.lng):
            raise ValueError("materialized POI moved away from canonical coordinates")
        if place.coordinate_provenance != poi.coordinate_provenance:
            raise ValueError("materialized POI lost coordinate provenance")

    decisions = {decision.stable_beat_id: decision for decision in plan.decisions}
    manifest_beats = set(identities_by_id)
    if set(decisions) != manifest_beats:
        raise ValueError("materialization decisions do not cover the manifest beats")

    actual_beats: dict[str, tuple[str, BeatRef]] = {}
    for poi_id, beats in snapshot.beats_by_poi.items():
        if poi_id not in pois_by_id:
            raise ValueError("materialized beats target an absent POI")
        for beat in tuple(beats):
            if beat.poi_id != poi_id or beat.stable_beat_id is None:
                raise ValueError("materialized beat has an invalid playback identity")
            if beat.id != beat.stable_beat_id:
                raise ValueError("materialized beat still uses a graph UUID")
            if beat.stable_beat_id in actual_beats:
                raise ValueError("materialized snapshot repeats a stable beat")
            actual_beats[beat.stable_beat_id] = (poi_id, beat)

    for stable_beat_id, decision in decisions.items():
        manifest_place_plan = plans_by_id.get(decision.place_plan_id)
        if (
            manifest_place_plan is None
            or manifest_place_plan.stable_beat_id != stable_beat_id
        ):
            raise ValueError("materialization decision is bound to the wrong place plan")
        actual = actual_beats.get(stable_beat_id)
        if decision.source_poi_id != _canonical_poi_id(
            decision.source_canonical_place_id or ""
        ):
            raise ValueError("materialization decision retains a raw source UUID")
        if decision.disposition == "omitted":
            if actual is not None:
                raise ValueError("omitted beat remains in materialized content")
            continue
        if actual is None:
            raise ValueError("retained materialization decision lost its beat")
        poi_id, beat = actual
        if beat.place_plan_id != decision.place_plan_id:
            raise ValueError("materialized BeatRef differs from its decision place plan")
        if poi_id != decision.destination_poi_id:
            raise ValueError("materialized beat is at the wrong destination")
        destination = pois_by_id[poi_id]
        if destination.canonical_place_id != decision.destination_canonical_place_id:
            raise ValueError("materialized beat destination identity differs from decision")
        if (
            beat.requires_dwell != decision.requires_dwell
            or beat.vignette_eligible != decision.vignette_eligible
        ):
            raise ValueError("materialized beat playback flags differ from decision")

    for poi in snapshot.pois:
        beats = tuple(snapshot.beats_by_poi.get(poi.id, ()))
        if poi.beat_count != len(beats):
            raise ValueError("materialized POI beat_count differs from eligible content")
        has_relocated = any(beat.requires_dwell for beat in beats)
        if has_relocated and (not poi.requires_dwell or poi.vignette_eligible):
            raise ValueError("off-site destination is not centrally dwell-only")

    expected_snapshot_sha256 = _materialized_snapshot_sha256(
        snapshot=snapshot,
        manifest_sha256=manifest.manifest_sha256,
        plan_sha256=plan.plan_sha256,
    )
    if snapshot.snapshot_sha256 != expected_snapshot_sha256:
        raise ValueError("materialized snapshot hash does not match its content")


def materialize_corpus_snapshot(
    snapshot: CorpusSnapshot,
    *,
    admitted_canonical_place_ids: Iterable[str] | None = None,
) -> PlaceMaterializationResult:
    """Validate and materialize one corpus snapshot before density/selection.

    ``admitted_canonical_place_ids`` is an optional precomputed route-envelope
    allow-list.  A resolved off-site target outside it is omitted; its narration
    is never left at the source host.  Omitting the allow-list preserves all
    resolved targets so the ordinary REACH/corridor stages can exclude them.
    """

    if isinstance(snapshot, MaterializedCorpusSnapshot):
        validate_materialized_corpus_snapshot(snapshot)
        assert snapshot.materialization_plan is not None
        return PlaceMaterializationResult(
            snapshot=snapshot,
            plan=snapshot.materialization_plan,
        )
    manifest = snapshot.place_manifest
    if manifest is None:
        raise ValueError("place materialization requires a corpus place manifest")

    places_by_id, identities_by_id, plans_by_id = _manifest_indexes(manifest)
    _validate_manifest_coverage(
        snapshot,
        manifest,
        places_by_id=places_by_id,
        identities_by_id=identities_by_id,
        plans_by_id=plans_by_id,
    )
    canonical_pois, raw_to_canonical = _canonical_source_pois(
        snapshot, places_by_id
    )
    admitted = (
        frozenset(admitted_canonical_place_ids)
        if admitted_canonical_place_ids is not None
        else None
    )

    source_beats = sorted(
        (
            beat
            for beats in snapshot.beats_by_poi.values()
            for beat in tuple(beats)
        ),
        key=lambda beat: beat.stable_beat_id or "",
    )
    decisions: list[MaterializationDecision] = []
    retained: dict[str, list[BeatRef]] = {}
    for beat in source_beats:
        source_canonical_id = raw_to_canonical[beat.poi_id]
        source_poi = canonical_pois.get(source_canonical_id)
        assert beat.stable_beat_id is not None
        assert beat.place_plan_id is not None
        decision = _decision_for_beat(
            beat=beat,
            source_canonical_id=source_canonical_id,
            source_destination_poi_id=source_poi.id if source_poi is not None else None,
            plan=plans_by_id[beat.place_plan_id],
            identity=identities_by_id[beat.stable_beat_id],
            places_by_id=places_by_id,
            admitted_canonical_place_ids=admitted,
        )
        decisions.append(decision)
        if decision.disposition == "omitted":
            continue
        assert decision.destination_poi_id is not None
        assert decision.destination_canonical_place_id is not None
        if decision.disposition == "relocated":
            if decision.destination_canonical_place_id not in canonical_pois:
                canonical_pois[decision.destination_canonical_place_id] = (
                    _synthetic_destination(
                        places_by_id[decision.destination_canonical_place_id]
                    )
                )
            else:
                target = canonical_pois[decision.destination_canonical_place_id]
                canonical_pois[decision.destination_canonical_place_id] = target.model_copy(
                    update={"requires_dwell": True, "vignette_eligible": False}
                )
        retained.setdefault(decision.destination_poi_id, []).append(
            beat.model_copy(
                update={
                    "id": beat.stable_beat_id,
                    "poi_id": decision.destination_poi_id,
                    "lenses": tuple(sorted(beat.lenses)),
                    "requires_dwell": decision.requires_dwell,
                    "vignette_eligible": decision.vignette_eligible,
                }
            )
        )

    # Recompute richness only from eligible, correctly placed content.  An
    # unresolved beat therefore contributes zero to density, scoring, extras,
    # vignettes, and generation.
    materialized_pois: list[POI] = []
    for poi in canonical_pois.values():
        beats = tuple(retained.get(poi.id, ()))
        materialized_pois.append(
            poi.model_copy(
                update={
                    "beat_count": len(beats),
                    "matching_lens_beat_count": 0,
                }
            )
        )
    materialized_pois.sort(key=lambda poi: (poi.canonical_place_id or "", poi.id))
    frozen_beats = _frozen_mapping(
        {
            poi.id: tuple(
                sorted(
                    retained.get(poi.id, ()),
                    key=lambda beat: beat.stable_beat_id or "",
                )
            )
            for poi in materialized_pois
            if retained.get(poi.id)
        }
    )
    plan = CorpusMaterializationPlan.build(
        source_manifest_sha256=manifest.manifest_sha256,
        decisions=tuple(decisions),
    )

    base_values = dict(
        pois=tuple(materialized_pois),
        beats_by_poi=frozen_beats,
        area_types=_frozen_mapping(snapshot.area_types),
        adjacent_areas=_frozen_mapping(
            {key: frozenset(values) for key, values in snapshot.adjacent_areas.items()}
        ),
        lens_neighbors=_frozen_mapping(
            {key: frozenset(values) for key, values in snapshot.lens_neighbors.items()}
        ),
        place_manifest=manifest,
        materialization_plan=plan,
    )
    provisional = CorpusSnapshot(
        pois=base_values["pois"],
        beats_by_poi=base_values["beats_by_poi"],
        area_types=base_values["area_types"],
        adjacent_areas=base_values["adjacent_areas"],
        lens_neighbors=base_values["lens_neighbors"],
        place_manifest=manifest,
    )
    snapshot_sha256 = _materialized_snapshot_sha256(
        snapshot=provisional,
        manifest_sha256=manifest.manifest_sha256,
        plan_sha256=plan.plan_sha256,
    )
    materialized = MaterializedCorpusSnapshot(
        **base_values,
        snapshot_sha256=snapshot_sha256,
        _validation_token=_MATERIALIZED_SNAPSHOT_TOKEN,
    )
    validate_materialized_corpus_snapshot(materialized)
    return PlaceMaterializationResult(snapshot=materialized, plan=plan)


__all__ = [
    "PlaceMaterializationResult",
    "materialize_corpus_snapshot",
    "selection_payload_sha256",
    "validate_materialized_corpus_snapshot",
]
