"""Hostile guards for durable, provider-free certification compose replay."""

from __future__ import annotations

import hashlib

import pytest

from src.tour.artifact import sentences_payload_sha256
from src.tour.authoring import (
    COMPOSE_MODEL,
    CompletedCertificationComposeUnit,
    ComposeRequest,
    candidate_compose_request_envelope,
    compose_input_sha256,
    finalize_certification_composition,
)
from src.tour.candidate_authoring import AuthoringCandidateIdentity, AuthoringStopRequest
from src.tour.contract import (
    POI,
    BeatSequence,
    Route,
    Script,
    ScriptPOI,
    Sentence,
    TourInput,
    TransitSegment,
    ValidationReport,
)

RESPONSE_SHA256 = "c" * 64


def _source() -> tuple[Script, Route, BeatSequence, ComposeRequest]:
    stitched = Script(
        city_slug="paris",
        generated_at="2026-07-21T00:00:00Z",
        inputs=TourInput(
            start=(48.85, 2.35), duration_min=10, city_slug="paris"
        ),
        total_audio_seconds=5,
        total_walking_seconds=0,
        total_walk_distance_m=0,
        total_planned_seconds=600,
        selected_pois=(
            ScriptPOI(
                id="p0", name="Square", tier=5, lat=48.85, lng=2.35
            ),
        ),
        lens_coverage={},
        script=(
            Sentence(
                text="And that brings our walk to a close.",
                source_id="GLUE_CLOSING",
                source_type="glue",
                stop_idx=0,
            ),
        ),
        validation=ValidationReport(),
    )
    route = Route(
        pois=(
            POI(
                id="p0",
                name="Square",
                tier=5,
                poi_role="anchor",
                lat=48.85,
                lng=2.35,
            ),
        ),
        transits=(
            TransitSegment(
                from_poi_id=None,
                to_poi_id="p0",
                distance_m=0,
                walk_seconds=0,
            ),
        ),
        total_walk_distance_m=0,
        total_walk_seconds=0,
    )
    request = ComposeRequest(stitched=stitched, tour_context=("Square",))
    return stitched, route, BeatSequence(poi_beats=()), request


def _completed(
    request: ComposeRequest,
    parsed: tuple[Sentence, ...] | None = None,
    *,
    stop_index: int = 0,
) -> CompletedCertificationComposeUnit:
    parsed = parsed or request.stitched.script
    candidate = AuthoringCandidateIdentity.create(
        candidate_slot="A",
        contract_sha256="1" * 64,
        reference_manifest_sha256="2" * 64,
        calibration_manifest_sha256="3" * 64,
        grounded_source_sha256="4" * 64,
        route_sha256="5" * 64,
        authoring_policy_sha256="6" * 64,
    )
    authoring_request = AuthoringStopRequest.create(
        candidate=candidate,
        stop_index=stop_index,
        compose_input_sha256=compose_input_sha256(request),
    )
    envelope, _ = candidate_compose_request_envelope(request, authoring_request)
    return CompletedCertificationComposeUnit(
        unit_id=f"stop:{stop_index}",
        stop_index=stop_index,
        model=COMPOSE_MODEL,
        authorized_request=request,
        authoring_request=authoring_request,
        parsed_provider_sentences=parsed,
        request_sha256=hashlib.sha256(envelope.encode("utf-8")).hexdigest(),
        response_sha256=RESPONSE_SHA256,
        parsed_payload_sha256=sentences_payload_sha256(parsed),
    )


def test_replay_rejects_alternate_request_hash() -> None:
    stitched, route, beats, request = _source()
    unit = _completed(request).model_copy(update={"request_sha256": "b" * 64})

    with pytest.raises(ValueError, match="request hash is inconsistent"):
        finalize_certification_composition(
            stitched,
            beats,
            route,
            completed_units=(unit,),
        )


def test_replay_rejects_alternate_authorized_request_even_with_matching_hash() -> None:
    stitched, route, beats, request = _source()
    alternate_request = request.model_copy(update={"tour_context": ("Elsewhere",)})
    unit = _completed(alternate_request)

    with pytest.raises(ValueError, match="request differs from grounded source"):
        finalize_certification_composition(
            stitched,
            beats,
            route,
            completed_units=(unit,),
        )


@pytest.mark.parametrize("case", ["missing", "extra"])
def test_replay_rejects_missing_or_extra_stop(case: str) -> None:
    stitched, route, beats, request = _source()
    units = [_completed(request)]
    if case == "missing":
        units.clear()
    else:
        extra_sentence = request.stitched.script[0].model_copy(update={"stop_idx": 1})
        extra_script = request.stitched.model_copy(update={"script": (extra_sentence,)})
        extra_request = request.model_copy(update={"stitched": extra_script})
        units.append(_completed(extra_request, stop_index=1))

    with pytest.raises(
        ValueError, match="completed compose responses differ from candidate stops"
    ):
        finalize_certification_composition(
            stitched,
            beats,
            route,
            completed_units=tuple(units),
        )


def test_replay_rejects_parsed_payload_hash_mismatch() -> None:
    stitched, route, beats, request = _source()
    unit = _completed(request).model_copy(update={"parsed_payload_sha256": "d" * 64})

    with pytest.raises(ValueError, match="parsed payload hash is inconsistent"):
        finalize_certification_composition(
            stitched,
            beats,
            route,
            completed_units=(unit,),
        )


def test_replay_preserves_provider_authored_prose_without_editorial_rewrite() -> None:
    stitched, route, beats, request = _source()
    provider_authored = (
        request.stitched.script[0].model_copy(
            update={"text": "The museum closes at five."}
        ),
    )
    unit = _completed(request, provider_authored)

    result = finalize_certification_composition(
        stitched,
        beats,
        route,
        completed_units=(unit,),
    )

    assert result.script.script == provider_authored
    assert result.composition_trace[0].source_sentences == provider_authored
    assert result.composition_trace[0].source_sentence_indexes == (0,)
