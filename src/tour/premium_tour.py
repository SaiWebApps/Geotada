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
import logging
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from src.audio.provider import OpenAITTSProvider
from src.tour.degradations import in_current_context, record

from .artifact import (
    BuildFingerprint,
    FinalTourBlueprint,
    build_final_blueprint,
    derive_playback_assignments,
    remap_provider_playback_assignments,
    sentences_payload_sha256,
    validate_llm_composed_blueprint,
)
from .authoring import (
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
from .contract import BeatSequence, Route, Script, TourInput
from .generation import CONCURRENT_GLUE_LABELS, generate
from .glue_client import NO_GLUE_SENTINEL, GlueClient
from .premium_authorities import PREMIUM_AUTHORITIES, PremiumAuthorityHashes
from .routing import MAX_REQUESTED_FRACTION, MIN_REQUESTED_FRACTION, RoutePlanningPolicy
from .routing_client import VALHALLA_ROUTING_CONFIG_SHA256, RoutingClient
from .selection import (
    CorpusSnapshot,
    MaterializedCorpusSnapshot,
    build_poi_beat_plans_capped,
    choose_discrete_route,
    route_has_container_identity_stop,
    select_k_routes,
)
from .verify import FaithfulnessChecker

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


def plan_premium_authoring(
    source: Script,
    beat_sequence: BeatSequence,
    route: Route,
    *,
    snapshot: CorpusSnapshot,
    snapshot_sha256: str,
    routing_version: str,
    policy_version: str,
    authorities: PremiumAuthorityHashes = PREMIUM_AUTHORITIES,
) -> PremiumTourPlan:
    """Build every per-stop authoring request for an ALREADY-PLANNED route.

    THE ONE Block-2 plan builder. Pure and provider-free: no routing client, no
    selection, no LLM. It is called by ``plan_premium_tour`` (which plans the route
    first) and by ``POST /trips/{trip_id}/compose`` (whose route is already persisted),
    so the two surfaces cannot drift into separate per-stop request shapes again.

    ``tour_input`` is taken from ``source.inputs`` rather than accepted separately:
    ``generate`` writes it there verbatim (src/tour/generation.py:424), and
    ``FinalTourBlueprint`` refuses a script whose inputs differ from the blueprint's
    tour_input (src/tour/artifact.py:677-678), so a separate parameter could only ever
    introduce a mismatch.
    """

    _beats_by_id, stops, requests = _certification_compose_requests(source, beat_sequence, route)
    if stops[-1] >= len(route.pois):
        raise ValueError("the stitched script names a stop the prebuilt route lacks")
    # Exactly ONE unit per dwell stop. ``stops`` comes from the stitched script's
    # sentences, so a stop the stitch dropped simply would not appear — and a
    # missing TAIL stop passes every other bar: it is in order, it starts at 0,
    # and its highest index is in range. The plan would then hold fewer units
    # than the route has stops, a caller would reserve and spend for those, and
    # the trip would persist with its last stop never authored at all.
    if len(stops) != len(route.pois):
        raise ValueError("the prebuilt route needs one authoring unit per dwell stop")
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
        tour_input=source.inputs,
        snapshot=snapshot,
        snapshot_sha256=snapshot_sha256,
        route=route,
        route_record=summary,
        sequence=beat_sequence,
        source=source,
        candidate=candidate,
        authoring=authoring,
        units=tuple(units),
        routing_version=routing_version,
        policy_version=policy_version,
        authorities=authorities,
    )


def certification_planning_policy(*, policy_id: str) -> RoutePlanningPolicy:
    return RoutePlanningPolicy.certification(
        minimum_requested_fraction=MIN_REQUESTED_FRACTION,
        maximum_requested_fraction=MAX_REQUESTED_FRACTION,
        policy_id=policy_id,
    )


class SilentGlueClient:
    """The glue client BLOCK 1 plans with: it writes nothing and calls nobody.

    OWNER RULING 1, 2026-08-04: during route planning, on both surfaces, the options show
    THE PLACES ALONE — POI names, order, walking times, ETA. No descriptive text of any
    kind. All prose arrives only at script generation, after a route has been picked.

    This is what makes Block 1 genuinely free. ``generate`` defaults to the REAL, paid
    ``HaikuGlueClient`` (src/tour/generation.py), so planning three route options would
    otherwise make three tours' worth of Haiku calls on an endpoint whose whole value
    proposition is that it costs nothing. Returning the NO_GLUE sentinel for every
    category makes ``generate`` fall back to its own deterministic connective template,
    so the stitched source is still complete — it simply contains no LLM-written line.

    NOT a mock and not a test double: it is never substituted for anything, and nothing
    else is standing behind it. It is the literal expression of "planning writes no
    words", and it is what the PRODUCT uses. A caller that wants prose passes a real
    client explicitly, which is what AUTHOR does for the one option the traveller picked.
    """

    def stitch(self, category: str, context: str, request: str) -> str:
        del category, context, request
        return NO_GLUE_SENTINEL


#: A route whose leg times are estimated rather than measured. ONE kind for the whole
#: outage — ``summarize`` collapses repeats into one row with a count
#: (src/tour/degradations.py:152-166), and nobody needs it per leg or per flavour.
ESTIMATED_LEGS_DEGRADATION = "walking_times_estimated"
#: The routing service answered, but with a setup this build was not compiled against.
ROUTING_CONFIG_DEGRADATION = "routing_setup_unexpected"
#: The routing service would not say which version it is running.
ROUTING_VERSION_DEGRADATION = "routing_version_unavailable"
#: Stamped into the build fingerprint when the version above could not be read. It is a
#: deliberately unmistakable word: ``BuildFingerprint.routing_version`` only requires a
#: non-empty string (src/tour/artifact.py:428), so a plausible-looking placeholder would
#: read back years later as a real engine version. Per-leg provenance is unaffected —
#: every measured leg carries its own request, response and config hash in its receipt.
ROUTING_VERSION_UNAVAILABLE = "unavailable"


def _premium_route_refusal(route: Route) -> str | None:
    """Why this route is STRUCTURALLY unplannable, or None.

    Only the two faults in the plan's own shape refuse. A route with no stops is not a
    tour, and a leg count that does not match the stop count breaks the index alignment
    every consumer downstream assumes (``route_summary``'s ``enumerate`` below, and the
    leg-walk map in ``build_route_option``).

    MISSING ROUTE MEASUREMENTS DO NOT REFUSE (owner ruling 2026-08-04). The walking
    engine is a real production service that can cold-start, restart or rebuild its map
    (render.yaml:98-124), and a refusal here would take tour generation down for every
    user for the duration of that. It is labelled instead — see
    ``record_routing_degradations`` — so the silent substitution is gone without the
    outage taking the product with it.

    Still a predicate rather than a raise, so a NON-CHOSEN flavour can be dropped from
    the options tuple while the CHOSEN one refuses the whole request.
    """

    if not route.pois:
        return "Premium planning requires a route with at least one stop"
    if len(route.transits) != len(route.pois):
        return "Premium planning requires one walking leg per stop"
    return None


def record_routing_degradations(
    route: Route, *, component: str = "premium_tour.plan_premium_options"
) -> None:
    """Label a route whose walking times were estimated rather than measured.

    A no-op outside a degradation scope (src/tour/degradations.py:137-139), so the batch
    runner and unit tests are unaffected; the API surfaces open one per request.

    PUBLIC because planning is not the only place a receiptless route reaches a person.
    Composing a saved trip rebuilds its route directly through ``summarise_route`` and
    never comes back through here, so it must call this itself or ship an unlabelled
    estimate — which AC-18 forbids on EITHER surface. ``component`` names the caller,
    since that is what the field is for (src/tour/degradations.py:50-51).
    """

    estimated = [
        index for index, transit in enumerate(route.transits) if transit.valhalla_receipt is None
    ]
    if estimated or not route.routed:
        record(
            kind=ESTIMATED_LEGS_DEGRADATION,
            human=(
                "Walking times between stops are estimates, not measured routes, so "
                "the tour may run a little longer or shorter than it says."
            ),
            component=component,
            cause=(
                f"The routing service returned no measured route for {len(estimated)} "
                f"of {len(route.transits)} legs. Those legs fell back to straight-line "
                "distance scaled by HAVERSINE_CORRECTION at PACE_KMH "
                "(src/tour/routing.py:41-53), which cannot see rivers, walls or closed "
                "streets, so a leg across an unbridged gap is understated. Check that "
                "ondoway-valhalla is up and has finished building its tiles."
            ),
            estimated_legs=str(len(estimated)),
            total_legs=str(len(route.transits)),
            fully_measured=str(route.routed).lower(),
        )
    # GUARDED ON A NON-EMPTY SET, and that guard is the whole point. This set is empty
    # when NO transit has a receipt, and an empty set is not equal to the expected one —
    # so an unguarded comparison would report a total outage as a routing-SETUP mismatch
    # as well, two rows describing one fault, one of them wrong.
    receipt_configs = {
        transit.valhalla_receipt.routing_config_sha256
        for transit in route.transits
        if transit.valhalla_receipt is not None
    }
    if receipt_configs and receipt_configs != {VALHALLA_ROUTING_CONFIG_SHA256}:
        record(
            kind=ROUTING_CONFIG_DEGRADATION,
            human=(
                "Walking times for this tour were worked out with different settings "
                "than this version expects, so they may be a little off."
            ),
            component=component,
            cause=(
                f"Leg receipts carry {len(receipt_configs)} distinct routing-config "
                "hashes; this build expects exactly VALHALLA_ROUTING_CONFIG_SHA256 "
                "(src/tour/routing_client.py). The deployed Valhalla configuration and "
                "the one compiled into this build have diverged."
            ),
            expected_setups="1",
            observed_setups=str(len(receipt_configs)),
        )


def resolve_routing_version(routing_client: RoutingClient) -> str:
    """The routing engine's version, or a labelled admission that it could not be read.

    THE ONE CALL AN OUTAGE CAN HARD-FAIL, on both the planning and the compose paths.
    Every walking leg independently degrades to a straight-line estimate when the
    container is unreachable (src/tour/routing_client.py:175-181), but
    ``routing_version`` deliberately has no fallback of its own: it does a live
    GET /status and treats a missing or malformed answer as an error
    (src/tour/routing_client.py:183-200).

    Left bare, that escapes as a transport error — a generic 500 on the planning path,
    and on the compose path it used to be swept up and relabelled
    ``compose_verification_failed``, a code meaning "the narrator wrote something
    untraceable", which blames the writer for a container that is merely still booting.

    RESOLVED 2026-08-05 TO A DEGRADATION, NOT A REFUSAL, which is the same answer the
    receipt bar above now gives to the same outage. A hard refusal here would take tour
    generation down app-wide for a cold start, which is exactly what the owner ruled
    against; and the provenance a refusal would be protecting does not exist during an
    outage, because unmeasured legs were measured by no engine. Recording
    ``unavailable`` states that plainly, and the traveller is told on the wire rather
    than in a log file nobody opens.
    """

    try:
        return routing_client.routing_version()
    except Exception as exc:
        record(
            kind=ROUTING_VERSION_DEGRADATION,
            human=(
                "We could not record which version of the map worked out this tour's "
                "walking times, so its record of how it was built is incomplete."
            ),
            component="premium_tour.resolve_routing_version",
            error=exc,
            cause=(
                "A live status read against the routing engine failed or answered "
                "without a version, so the build fingerprint records "
                f"routing_version={ROUTING_VERSION_UNAVAILABLE!r} instead of a real "
                "one. Per-leg provenance is unaffected: every measured leg still "
                "carries its own request, response and routing-config hash. Check that "
                "ondoway-valhalla is up and answering /status."
            ),
        )
        return ROUTING_VERSION_UNAVAILABLE


def _plan_one_premium_route(
    tour_input: TourInput,
    snapshot: CorpusSnapshot,
    route: Route,
    *,
    policy: RoutePlanningPolicy,
    routing_version: str,
    generation_time: dt.datetime | None,
    authorities: PremiumAuthorityHashes,
    glue_client: GlueClient | None,
) -> PremiumTourPlan:
    """Everything one already-chosen route needs to become an authorable plan."""

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
        glue_client=glue_client,
        now=generation_time or dt.datetime.now(dt.UTC),
        validate_output=False,
    )
    return plan_premium_authoring(
        source,
        sequence,
        route,
        snapshot=snapshot,
        snapshot_sha256=exact_snapshot_sha256(snapshot),
        routing_version=routing_version,
        policy_version=policy.policy_id,
        authorities=authorities,
    )


def plan_premium_options(
    tour_input: TourInput,
    snapshot: CorpusSnapshot,
    *,
    routing_client: RoutingClient,
    planning_policy: RoutePlanningPolicy | None = None,
    generation_time: dt.datetime | None = None,
    authorities: PremiumAuthorityHashes = PREMIUM_AUTHORITIES,
    glue_client: GlueClient | None = None,
) -> tuple[PremiumTourPlan, ...]:
    """BLOCK 1 — every flavour of one request, planned, with no per-stop authoring.

    Returns one plan per surviving flavour, CHOSEN FIRST. The chosen flavour is exactly
    what ``choose_discrete_route`` picks, so ``plan_premium_options(...)[0]`` is the plan
    ``plan_premium_tour`` has always returned for the same input. A flavour after the
    first that cannot clear the Premium route bar is DROPPED from the tuple; the chosen
    one refuses the whole request, as before.

    FREE, and free BY DEFAULT. ``glue_client=None`` here means ``SilentGlueClient``, not
    ``generate``'s paid Haiku default: planning a route is a places-and-times question
    and makes no provider call at all (OWNER RULING 1). The DEFAULT is the part that
    matters — a free path that is only free when a caller remembers to ask is one
    refactor away from being paid again, on an endpoint Phase 1 leaves anonymous.
    """

    policy = planning_policy or certification_planning_policy(policy_id=PREMIUM_MODULE_VERSION)
    routing_version = resolve_routing_version(routing_client)
    routes = select_k_routes(
        tour_input,
        snapshot,
        3,
        routing_client=routing_client,
        planning_policy=policy,
    )
    chosen = choose_discrete_route(routes)
    ordered = [
        chosen,
        *(
            route
            for route in routes
            if route is not chosen and not route_has_container_identity_stop(route)
        ),
    ]
    plans: list[PremiumTourPlan] = []
    for index, route in enumerate(ordered):
        refusal = _premium_route_refusal(route)
        if refusal is not None:
            if index == 0:
                raise PremiumRouteInfeasibleError(refusal)
            continue
        record_routing_degradations(route)
        plans.append(
            _plan_one_premium_route(
                tour_input,
                snapshot,
                route,
                policy=policy,
                routing_version=routing_version,
                generation_time=generation_time,
                authorities=authorities,
                glue_client=glue_client if glue_client is not None else SilentGlueClient(),
            )
        )
    return tuple(plans)


def plan_premium_tour(
    tour_input: TourInput,
    snapshot: CorpusSnapshot,
    *,
    routing_client: RoutingClient,
    planning_policy: RoutePlanningPolicy | None = None,
    generation_time: dt.datetime | None = None,
    authorities: PremiumAuthorityHashes = PREMIUM_AUTHORITIES,
    glue_client: GlueClient | None = None,
) -> PremiumTourPlan:
    """The ONE plan a single-route caller wants: the chosen flavour of Block 1.

    Deliberately a one-line delegate. The selection rule (``choose_discrete_route`` over
    the K=3 flavours) lives in ``plan_premium_options`` and nowhere else, so the batch
    runner and the two API surfaces cannot drift into different definitions of "the"
    route.
    """

    return plan_premium_options(
        tour_input,
        snapshot,
        routing_client=routing_client,
        planning_policy=planning_policy,
        generation_time=generation_time,
        authorities=authorities,
        glue_client=glue_client,
    )[0]


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
        # AC-4: a unit that fails inside the fan-out must be recorded — exception
        # type, message and stop index, in the CALLER's scope — before it is
        # re-raised. A partial premium tour must abort, never ship
        # half-narrated, so this never swallows the exception.
        try:
            response = executor.execute(unit)
        except Exception as exc:
            record(
                kind="premium_unit_failed",
                human=(
                    "A stop failed to compose, so the tour was stopped rather than "
                    "shipped half-narrated."
                ),
                component="execute_premium_plan.invoke",
                error=exc,
                stop_index=str(unit.stop_index),
            )
            raise
        receipt_sink.after_call(unit, response)
        return response

    # in_current_context: contextvars do NOT cross into pool workers, so without
    # this a degradation recorded inside a compose call is silently dropped.
    with ThreadPoolExecutor(max_workers=min(max_workers, len(plan.units))) as pool:
        return tuple(pool.map(in_current_context(invoke), plan.units))


def finalize_premium_composition(
    plan: PremiumTourPlan,
    responses: tuple[PhysicalProviderResponse, ...],
    *,
    faithfulness_checker: FaithfulnessChecker | None = None,
    enforce_claim_coverage: bool = False,
    scan_glue_for_invention: bool = False,
) -> CertificationComposition:
    """Purely bind physical response bytes and run the certification finalizer.

    THE THREE GATES ARE FORWARDED, and the defaults are for the CERTIFICATION REPLAY
    ONLY (``scripts/tour_batch_candidate.py``), whose judgement of prose is semantic and
    owned by factual review. Every LIVE surface must pass all three — see
    ``finalize_premium_tour``, which requires the checker and hard-codes both booleans.

    MEASURED 2026-08-03: this function called the shared finalizer with only
    ``completed_units`` and ``model``, so ``/trips/preview`` ran NO entailment check, NO
    coverage baseline and NO invented-noun/year scan, while ``POST /trips/{id}/compose``
    ran all three. ``authoring.py`` then set ``allow_unverified_faithfulness=True`` and
    ``compose_gate.py`` substituted ``MockFaithfulnessChecker``, which approves every
    sentence. The editorial workbench — the instrument used to judge tour quality — was
    reviewing narration nothing had checked, and hiding refusals the phone would raise.
    """

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
        faithfulness_checker=faithfulness_checker,
        enforce_claim_coverage=enforce_claim_coverage,
        scan_glue_for_invention=scan_glue_for_invention,
    )


ALLOW_DIRTY_LOCAL_BUILD_ENV = "ONDOWAY_ALLOW_DIRTY_LOCAL_BUILD"


@dataclass(frozen=True)
class PremiumBuildIdentity:
    commit_sha: str
    tts_provider: str = "openai"
    tts_model: str = OpenAITTSProvider.DEFAULT_MODEL
    tts_voice: str = OpenAITTSProvider.DEFAULT_VOICE
    # True only for a LOCAL workbench build authored off a dirty tree. commit_sha then
    # names HEAD, which the working tree does NOT match — so this build is reproducible
    # only by whoever ran it, and is never certification-eligible.
    local_dirty_tree: bool = False


def resolve_build_identity() -> PremiumBuildIdentity:
    """Resolve a deploy commit or a clean local HEAD; reject dirty local trees.

    One narrow local concession: with ``ONDOWAY_ALLOW_DIRTY_LOCAL_BUILD=1`` a dirty tree
    yields HEAD's sha tagged ``local_dirty_tree=True`` instead of raising. Without it the
    editorial workbench is unusable during normal development — every developer tree has
    uncommitted work, so EVERY local Premium preview degraded to the Basic lane, and the
    reason was reported as an LLM failure. See scripts/workbench.sh.

    Deliberately NOT reusing GIT_COMMIT_SHA for this: that variable means "the deploy is
    this commit" (its own error message below calls it a deployment fingerprint), so
    setting it locally would assert clean provenance process-wide and silently. A
    separate, explicitly-named opt-in keeps the lie from being told at all. It is fenced
    to refuse whenever RENDER_GIT_COMMIT is present, so it can never fire on Render.
    """

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
        if os.getenv(ALLOW_DIRTY_LOCAL_BUILD_ENV, "").strip() != "1":
            raise ValueError("Premium fingerprint requires a clean local git tree")
        if os.getenv("RENDER_GIT_COMMIT"):
            raise ValueError("dirty-tree local builds are never permitted on a deployment")
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if not re.fullmatch(r"[0-9a-f]{40}", head):
            raise ValueError("local commit fingerprint is not a full lowercase SHA")
        logging.getLogger("ondoway.api").warning(
            "Premium build authored from a DIRTY local tree at %s — %s=1 is set. "
            "This build is not reproducible from the commit and is not certifiable.",
            head,
            ALLOW_DIRTY_LOCAL_BUILD_ENV,
        )
        return PremiumBuildIdentity(commit_sha=head, local_dirty_tree=True)
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
    faithfulness_checker: FaithfulnessChecker,
    build_identity: PremiumBuildIdentity | None = None,
) -> PremiumTourResult:
    """Pure finalization into a validated, certification-eligible blueprint.

    ``faithfulness_checker`` is REQUIRED and deliberately has NO default. This is the
    function ``/trips/preview`` calls, and an optional checker is exactly how the
    workbench came to run no entailment gate at all for three days while the phone ran
    one: nothing at the call site had to say "skip the fact-checking", it simply never
    mentioned it, and an omission is invisible to code review. Making it required means
    the divergence cannot come back silently — a caller that forgets fails loudly at the
    call, not quietly in the output.

    The two boolean gates are NOT parameters here for the same reason: a live surface
    does not get to choose whether facts are checked. They are hard-coded ON.
    """

    composition = finalize_premium_composition(
        plan,
        responses,
        faithfulness_checker=faithfulness_checker,
        enforce_claim_coverage=True,
        scan_glue_for_invention=True,
    )
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
    "ESTIMATED_LEGS_DEGRADATION",
    "ROUTING_CONFIG_DEGRADATION",
    "ROUTING_VERSION_DEGRADATION",
    "ROUTING_VERSION_UNAVAILABLE",
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
    "plan_premium_authoring",
    "plan_premium_options",
    "plan_premium_tour",
    "premium_authoring_policy_sha256",
    "record_routing_degradations",
    "resolve_build_identity",
    "resolve_routing_version",
    "route_summary",
]
