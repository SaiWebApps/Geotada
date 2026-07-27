"""One Premium planning and finalization seam for batch and workbench tours.

Planning is deterministic and provider-free. Execution is injected and returns
opaque physical response bytes. Finalization is pure: it reconstructs every
authorized request, verifies the response set, and freezes an immutable
``FinalTourBlueprint``. Paid semantic reviewers are intentionally absent; they
belong to the separate certification workflow.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from src.audio.provider import OpenAITTSProvider

from .artifact import (
    BuildFingerprint,
    FinalTourBlueprint,
    build_final_blueprint,
    derive_playback_assignments,
    remap_provider_playback_assignments,
    sentences_payload_sha256,
    validate_llm_composed_blueprint,
)
from .beat_select import select_vignette_beats
from .candidate_authoring import (
    AuthoringCandidateIdentity,
    AuthoringCandidatePlan,
    AuthoringCandidateResponseSet,
    AuthoringStopRequest,
    AuthoringStopResponse,
)
from .certification_provider import (
    AnthropicCertificationProvider,
    CallPurpose,
    PhysicalProviderResponse,
)
from .compose import (
    _COMPOSE_OUTPUT_SCHEMA,
    _COMPOSE_SYSTEM,
    CERTIFICATION_COMPOSE_MAX_OUTPUT_TOKENS,
    COMPOSE_MODEL,
    CertificationComposition,
    CompletedCertificationComposeUnit,
    ComposeRequest,
    _certification_compose_requests,
    _sentences_from_json,
    candidate_compose_request_envelope,
    compose_input_sha256,
    finalize_certification_composition,
)
from .contract import BeatSequence, Route, Script, TourInput
from .generation import CONCURRENT_GLUE_LABELS, generate
from .premium_authorities import PREMIUM_AUTHORITIES, PremiumAuthorityHashes
from .routing import MAX_REQUESTED_FRACTION, MIN_REQUESTED_FRACTION, RoutePlanningPolicy
from .routing_client import VALHALLA_ROUTING_CONFIG_SHA256, RoutingClient
from .selection import (
    CorpusSnapshot,
    MaterializedCorpusSnapshot,
    build_poi_beat_plans_capped,
    choose_discrete_route,
    select_k_routes,
)

PREMIUM_MODULE_VERSION = "ondoway-premium-tour-v1"
REPO_ROOT = Path(__file__).resolve().parents[2]


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def premium_authoring_policy_sha256() -> str:
    """Hash the exact physical authoring policy shared by every caller."""

    return _sha256(
        _canonical_bytes(
            {
                "model": COMPOSE_MODEL,
                "max_tokens": CERTIFICATION_COMPOSE_MAX_OUTPUT_TOKENS,
                "thinking": {"type": "adaptive"},
                "system": _COMPOSE_SYSTEM,
                "output_schema": _COMPOSE_OUTPUT_SCHEMA,
            }
        )
    )


def exact_snapshot_sha256(snapshot: CorpusSnapshot) -> str:
    """Bind the exact selection input, using the materializer hash when present."""

    if isinstance(snapshot, MaterializedCorpusSnapshot):
        return snapshot.snapshot_sha256
    payload = {
        "pois": sorted(
            (poi.model_dump(mode="json") for poi in snapshot.pois),
            key=lambda item: (str(item.get("canonical_place_id") or ""), str(item["id"])),
        ),
        "beats": sorted(
            (
                beat.model_dump(mode="json")
                for beats in snapshot.beats_by_poi.values()
                for beat in beats
            ),
            key=lambda item: (str(item.get("stable_beat_id") or ""), str(item["id"])),
        ),
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
    return _sha256(_canonical_bytes(payload))


def route_summary(route: Route) -> dict[str, object]:
    """Canonical public route record used by Premium plan identities."""

    return {
        "route_sha256": _sha256(_canonical_bytes(route.model_dump(mode="json"))),
        "routed": route.routed,
        "total_walk_seconds": route.total_walk_seconds,
        "total_walk_distance_m": route.total_walk_distance_m,
        "pois": [
            {"id": poi.id, "name": poi.name, "lat": poi.lat, "lng": poi.lng} for poi in route.pois
        ],
        "legs": [
            {
                "index": index,
                "seconds": transit.leg_seconds,
                "distance_m": transit.leg_distance_m,
                "request_sha256": transit.valhalla_receipt.request_sha256,
                "response_sha256": transit.valhalla_receipt.response_sha256,
            }
            for index, transit in enumerate(route.transits)
            if transit.valhalla_receipt is not None
        ],
    }


class PremiumRouteInfeasibleError(ValueError):
    """A Premium route lacks complete physical Valhalla evidence."""


@dataclass(frozen=True)
class PremiumComposeUnit:
    stop_index: int
    poi_name: str
    authorized_request: ComposeRequest
    authoring_request: AuthoringStopRequest
    request_sha256: str
    input_byte_count: int
    output_token_ceiling: int
    sdk_request: dict[str, object]

    def public_payload(self) -> dict[str, object]:
        return {
            "stop_index": self.stop_index,
            "poi_name": self.poi_name,
            "request_id": self.authoring_request.request_id,
            "request_sha256": self.request_sha256,
            "input_byte_count": self.input_byte_count,
            "output_token_ceiling": self.output_token_ceiling,
        }


@dataclass(frozen=True)
class PremiumTourPlan:
    tour_input: TourInput
    snapshot: CorpusSnapshot
    snapshot_sha256: str
    route: Route
    route_record: dict[str, object]
    sequence: BeatSequence
    source: Script
    candidate: AuthoringCandidateIdentity
    authoring: AuthoringCandidatePlan
    units: tuple[PremiumComposeUnit, ...]
    routing_version: str
    policy_version: str
    authorities: PremiumAuthorityHashes

    def batch_payload(
        self, *, case_id: str, archetype: str, request_sha256: str
    ) -> dict[str, object]:
        core = {
            "schema_version": "ondoway-tour-batch-tour-plan-v1",
            "case_id": case_id,
            "archetype": archetype,
            "request_sha256": request_sha256,
            "tour_input": self.tour_input.model_dump(mode="json"),
            "candidate": self.candidate.model_dump(mode="json"),
            "route": self.route_record,
            "grounded_source_sha256": sentences_payload_sha256(self.source.script),
            "model": COMPOSE_MODEL,
            "thinking": {"type": "adaptive"},
            "sdk_max_retries": 0,
            "application_deadline_seconds": None,
            "units": [unit.public_payload() for unit in self.units],
        }
        return {**core, "tour_plan_sha256": _sha256(_canonical_bytes(core))}


def certification_planning_policy(*, policy_id: str) -> RoutePlanningPolicy:
    return RoutePlanningPolicy.certification(
        minimum_requested_fraction=MIN_REQUESTED_FRACTION,
        maximum_requested_fraction=MAX_REQUESTED_FRACTION,
        max_stops=8,
        policy_id=policy_id,
    )


def plan_premium_tour(
    tour_input: TourInput,
    snapshot: CorpusSnapshot,
    *,
    routing_client: RoutingClient,
    planning_policy: RoutePlanningPolicy | None = None,
    generation_time: dt.datetime | None = None,
    authorities: PremiumAuthorityHashes = PREMIUM_AUTHORITIES,
) -> PremiumTourPlan:
    """Pure/provider-free plan through the full certification route algorithm."""

    policy = planning_policy or certification_planning_policy(policy_id=PREMIUM_MODULE_VERSION)
    routing_version = routing_client.routing_version()
    routes = select_k_routes(
        tour_input,
        snapshot,
        3,
        routing_client=routing_client,
        planning_policy=policy,
    )
    route = choose_discrete_route(routes)
    if (
        not route.pois
        or not route.routed
        or len(route.transits) != len(route.pois)
        or any(transit.valhalla_receipt is None for transit in route.transits)
    ):
        raise PremiumRouteInfeasibleError(
            "Premium planning requires a complete receipt-backed Valhalla route"
        )
    receipt_configs = {
        transit.valhalla_receipt.routing_config_sha256
        for transit in route.transits
        if transit.valhalla_receipt is not None
    }
    if receipt_configs != {VALHALLA_ROUTING_CONFIG_SHA256}:
        raise PremiumRouteInfeasibleError("route receipts use an unexpected routing config")

    capped = build_poi_beat_plans_capped(
        route,
        snapshot,
        lenses=tour_input.lenses,
        end_is_none=tour_input.end is None,
    )
    vignette_beats = select_vignette_beats(
        route.vignettes,
        snapshot.beats_by_poi,
        lenses=tour_input.lenses,
    )
    sequence = BeatSequence(
        poi_beats=tuple(plan for plan, _overflow in capped),
        vignette_beats=vignette_beats,
        overflow_by_poi={plan.poi_id: overflow for plan, overflow in capped if overflow},
    )
    source = generate(
        sequence,
        route,
        tour_input,
        now=generation_time or dt.datetime.now(dt.UTC),
        validate_output=False,
    )
    _beats, stops, requests = _certification_compose_requests(source, sequence, route)
    summary = route_summary(route)
    candidate = AuthoringCandidateIdentity.create(
        candidate_slot="A",
        contract_sha256=authorities.contract_sha256,
        reference_manifest_sha256=authorities.reference_manifest_sha256,
        calibration_manifest_sha256=authorities.calibration_manifest_sha256,
        grounded_source_sha256=sentences_payload_sha256(source.script),
        route_sha256=str(summary["route_sha256"]),
        authoring_policy_sha256=premium_authoring_policy_sha256(),
    )
    authoring = AuthoringCandidatePlan(
        candidate=candidate,
        stop_requests=tuple(
            AuthoringStopRequest.create(
                candidate=candidate,
                stop_index=stop_index,
                compose_input_sha256=compose_input_sha256(requests[stop_index]),
            )
            for stop_index in stops
        ),
    )
    units: list[PremiumComposeUnit] = []
    for stop_request in authoring.stop_requests:
        stop_index = stop_request.stop_index
        envelope, sdk_request = candidate_compose_request_envelope(
            requests[stop_index], stop_request, model=COMPOSE_MODEL
        )
        encoded = envelope.encode("utf-8")
        units.append(
            PremiumComposeUnit(
                stop_index=stop_index,
                poi_name=route.pois[stop_index].name,
                authorized_request=requests[stop_index],
                authoring_request=stop_request,
                request_sha256=_sha256(encoded),
                input_byte_count=len(encoded),
                output_token_ceiling=CERTIFICATION_COMPOSE_MAX_OUTPUT_TOKENS,
                sdk_request=sdk_request,
            )
        )
    return PremiumTourPlan(
        tour_input=tour_input,
        snapshot=snapshot,
        snapshot_sha256=exact_snapshot_sha256(snapshot),
        route=route,
        route_record=summary,
        sequence=sequence,
        source=source,
        candidate=candidate,
        authoring=authoring,
        units=tuple(units),
        routing_version=routing_version,
        policy_version=policy.policy_id,
        authorities=authorities,
    )


class PremiumComposeExecutor(Protocol):
    cost_bearing: bool
    provider_name: str

    def execute(self, unit: PremiumComposeUnit) -> PhysicalProviderResponse: ...


class PremiumReceiptSink(Protocol):
    def before_call(self, unit: PremiumComposeUnit) -> None: ...

    def after_call(self, unit: PremiumComposeUnit, response: PhysicalProviderResponse) -> None: ...


class EphemeralReceiptSink:
    """Explicit workbench policy: retain receipts only for this response."""

    def before_call(self, unit: PremiumComposeUnit) -> None:
        del unit

    def after_call(self, unit: PremiumComposeUnit, response: PhysicalProviderResponse) -> None:
        del unit, response


class AnthropicPremiumExecutor:
    cost_bearing = True
    provider_name = "anthropic"

    def __init__(self, provider: AnthropicCertificationProvider | None = None) -> None:
        self._provider = provider or AnthropicCertificationProvider()

    def execute(self, unit: PremiumComposeUnit) -> PhysicalProviderResponse:
        return self._provider.invoke(
            purpose=CallPurpose.COMPOSE,
            unit_id=f"stop:{unit.stop_index}",
            request=unit.sdk_request,
        )


class OfflinePremiumExecutor:
    """Explicit $0 adapter for hermetic tests; never selected by product code."""

    cost_bearing = False
    provider_name = "offline"

    def execute(self, unit: PremiumComposeUnit) -> PhysicalProviderResponse:
        body = _canonical_bytes(
            {
                "sentences": [
                    sentence.model_dump(mode="json")
                    for sentence in unit.authorized_request.stitched.script
                ]
            }
        )
        return PhysicalProviderResponse(
            body=body,
            input_tokens=0,
            output_tokens=0,
            latency_ms=0,
            model=COMPOSE_MODEL,
            provider_request_id=f"offline-{unit.stop_index}",
            stop_reason="end_turn",
        )


def execute_premium_plan(
    plan: PremiumTourPlan,
    *,
    executor: PremiumComposeExecutor,
    receipt_sink: PremiumReceiptSink,
    max_workers: int = 6,
) -> tuple[PhysicalProviderResponse, ...]:
    """Execute each immutable stop request once around an injected receipt sink."""

    if not 1 <= max_workers <= 8:
        raise ValueError("Premium execution supports one to eight workers")
    for unit in plan.units:
        receipt_sink.before_call(unit)

    def invoke(unit: PremiumComposeUnit) -> PhysicalProviderResponse:
        response = executor.execute(unit)
        receipt_sink.after_call(unit, response)
        return response

    with ThreadPoolExecutor(max_workers=min(max_workers, len(plan.units))) as pool:
        return tuple(pool.map(invoke, plan.units))


def finalize_premium_composition(
    plan: PremiumTourPlan,
    responses: tuple[PhysicalProviderResponse, ...],
) -> CertificationComposition:
    """Purely bind physical response bytes and run the certification finalizer."""

    if len(responses) != len(plan.units):
        raise ValueError("physical responses differ from the planned stop count")
    authoring_responses: list[AuthoringStopResponse] = []
    completed: list[CompletedCertificationComposeUnit] = []
    for unit, response in zip(plan.units, responses, strict=True):
        if response.model != COMPOSE_MODEL:
            raise ValueError("provider response model differs from the authorized model")
        if response.stop_reason == "max_tokens":
            raise ValueError("provider response hit the fixed output ceiling")
        try:
            payload = json.loads(response.body)
            raw_sentences = payload["sentences"]
            if not isinstance(raw_sentences, list):
                raise TypeError("sentences is not a list")
            sentences = _sentences_from_json(raw_sentences, unit.authorized_request)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ValueError("provider response is not a valid Premium sentence payload") from exc
        parsed_sha256 = sentences_payload_sha256(sentences)
        response_sha256 = _sha256(response.body)
        authoring_responses.append(
            AuthoringStopResponse(
                request=unit.authoring_request,
                raw_response=response.body,
                raw_response_sha256=response_sha256,
                parsed_payload_sha256=parsed_sha256,
                provider_request_id=response.provider_request_id,
            )
        )
        completed.append(
            CompletedCertificationComposeUnit(
                unit_id=f"stop:{unit.stop_index}",
                stop_index=unit.stop_index,
                model=response.model,
                authorized_request=unit.authorized_request,
                authoring_request=unit.authoring_request,
                parsed_provider_sentences=sentences,
                request_sha256=unit.request_sha256,
                response_sha256=response_sha256,
                parsed_payload_sha256=parsed_sha256,
            )
        )
    AuthoringCandidateResponseSet(
        plan=plan.authoring,
        responses=tuple(authoring_responses),
    )
    return finalize_certification_composition(
        plan.source,
        plan.sequence,
        plan.route,
        completed_units=tuple(completed),
        model=COMPOSE_MODEL,
    )


@dataclass(frozen=True)
class PremiumBuildIdentity:
    commit_sha: str
    tts_provider: str = "openai"
    tts_model: str = OpenAITTSProvider.DEFAULT_MODEL
    tts_voice: str = OpenAITTSProvider.DEFAULT_VOICE


def resolve_build_identity() -> PremiumBuildIdentity:
    """Resolve a deploy commit or a clean local HEAD; reject dirty local trees."""

    deployed = os.getenv("RENDER_GIT_COMMIT") or os.getenv("GIT_COMMIT_SHA")
    if deployed:
        if not re.fullmatch(r"[0-9a-f]{40}", deployed):
            raise ValueError("deployment commit fingerprint is not a full lowercase SHA")
        return PremiumBuildIdentity(commit_sha=deployed)
    status = subprocess.run(
        ["git", "status", "--porcelain=v1"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if status.strip():
        raise ValueError("Premium fingerprint requires a clean local git tree")
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("local commit fingerprint is not a full lowercase SHA")
    return PremiumBuildIdentity(commit_sha=commit)


@dataclass(frozen=True)
class PremiumTourResult:
    blueprint: FinalTourBlueprint
    candidate: AuthoringCandidateIdentity


def finalize_premium_tour(
    plan: PremiumTourPlan,
    responses: tuple[PhysicalProviderResponse, ...],
    *,
    build_identity: PremiumBuildIdentity | None = None,
) -> PremiumTourResult:
    """Pure finalization into a validated, certification-eligible blueprint."""

    composition = finalize_premium_composition(plan, responses)
    identity = build_identity or resolve_build_identity()
    vignette_beat_ids = frozenset(
        beat.id for beats in plan.sequence.vignette_beats.values() for beat in beats
    )
    source_assignments = derive_playback_assignments(
        plan.source,
        vignette_beat_ids=vignette_beat_ids,
    )
    # The composer legitimately emits a transition sentence the frozen stitch did not
    # contain. Placement for a RECOGNISED source_id is a pure function of that id, so
    # it is derived rather than discarding the whole authored tour; an unrecognised or
    # invented id still fails closed. Certification never reaches this function (it
    # calls finalize_premium_composition directly), so the strict default stands there.
    assignments = remap_provider_playback_assignments(
        source_script=plan.source,
        source_assignments=source_assignments,
        provider_script=composition.script,
        derivable_leg_source_ids=CONCURRENT_GLUE_LABELS | vignette_beat_ids,
    )
    build = BuildFingerprint(
        commit_sha=identity.commit_sha,
        corpus_sha256=plan.snapshot_sha256,
        module_version=PREMIUM_MODULE_VERSION,
        prompt_sha256=premium_authoring_policy_sha256(),
        compose_model=COMPOSE_MODEL,
        policy_version=plan.policy_version,
        routing_engine="valhalla",
        routing_version=plan.routing_version,
        routing_config_sha256=VALHALLA_ROUTING_CONFIG_SHA256,
        tts_provider=identity.tts_provider,
        tts_model=identity.tts_model,
        tts_voice=identity.tts_voice,
    )
    vignette_ids = tuple(
        beat.id for beats in plan.sequence.vignette_beats.values() for beat in beats
    )
    blueprint = build_final_blueprint(
        contract_sha256=plan.authorities.contract_sha256,
        reference_manifest_sha256=plan.authorities.reference_manifest_sha256,
        calibration_manifest_sha256=plan.authorities.calibration_manifest_sha256,
        build=build,
        tour_input=plan.tour_input,
        route=plan.route,
        script=composition.script,
        vignette_beat_ids=vignette_ids,
        playback_assignments=assignments,
        composition_trace=composition.composition_trace,
    )
    ineligibility = validate_llm_composed_blueprint(blueprint)
    if ineligibility is not None:
        raise ValueError(ineligibility)
    return PremiumTourResult(blueprint=blueprint, candidate=plan.candidate)


__all__ = [
    "AnthropicPremiumExecutor",
    "EphemeralReceiptSink",
    "OfflinePremiumExecutor",
    "PremiumBuildIdentity",
    "PremiumComposeExecutor",
    "PremiumComposeUnit",
    "PremiumReceiptSink",
    "PremiumRouteInfeasibleError",
    "PremiumTourPlan",
    "PremiumTourResult",
    "certification_planning_policy",
    "exact_snapshot_sha256",
    "execute_premium_plan",
    "finalize_premium_composition",
    "finalize_premium_tour",
    "plan_premium_tour",
    "premium_authoring_policy_sha256",
    "resolve_build_identity",
    "route_summary",
]
