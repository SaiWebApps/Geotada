"""Raw authoring candidates have immutable, non-interchangeable identities."""

import hashlib

import pytest
from pydantic import ValidationError

from src.tour.candidate_authoring import (
    AuthoringCandidateIdentity,
    AuthoringCandidatePlan,
    AuthoringCandidateResponseSet,
    AuthoringStopRequest,
    AuthoringStopResponse,
)


def _identity(slot: str) -> AuthoringCandidateIdentity:
    return AuthoringCandidateIdentity.create(
        candidate_slot=slot,
        contract_sha256="1" * 64,
        reference_manifest_sha256="2" * 64,
        calibration_manifest_sha256="3" * 64,
        grounded_source_sha256="4" * 64,
        route_sha256="5" * 64,
        authoring_policy_sha256="6" * 64,
    )


def test_candidate_slots_have_distinct_deterministic_identities() -> None:
    first_a = _identity("A")
    second_a = _identity("A")
    candidate_b = _identity("B")

    assert first_a == second_a
    assert first_a.candidate_id != candidate_b.candidate_id


def test_candidate_identity_cannot_be_forged_or_relabelled() -> None:
    candidate = _identity("A")
    forged = candidate.model_dump(mode="json")
    forged["candidate_slot"] = "B"

    with pytest.raises(ValidationError, match="differs from its frozen authoring inputs"):
        AuthoringCandidateIdentity.model_validate(forged)


def test_each_stop_request_is_immutable_and_candidate_bound() -> None:
    candidate_a = _identity("A")
    candidate_b = _identity("B")
    request_a = AuthoringStopRequest.create(
        candidate=candidate_a,
        stop_index=2,
        compose_input_sha256="7" * 64,
    )
    request_b = AuthoringStopRequest.create(
        candidate=candidate_b,
        stop_index=2,
        compose_input_sha256="7" * 64,
    )

    assert request_a.request_id != request_b.request_id
    forged = request_a.model_dump(mode="json")
    forged["compose_input_sha256"] = "8" * 64
    with pytest.raises(ValidationError, match="differs from its candidate and input"):
        AuthoringStopRequest.model_validate(forged)


def test_stop_response_retains_and_hashes_exact_provider_bytes() -> None:
    request = AuthoringStopRequest.create(
        candidate=_identity("A"),
        stop_index=0,
        compose_input_sha256="7" * 64,
    )
    raw = b'{"sentences":[{"text":"Look up."}]}'
    response = AuthoringStopResponse(
        request=request,
        raw_response=raw,
        raw_response_sha256=hashlib.sha256(raw).hexdigest(),
        parsed_payload_sha256="8" * 64,
    )

    assert response.raw_response == raw
    tampered = response.model_dump(mode="python")
    tampered["raw_response"] = raw + b" "
    with pytest.raises(ValidationError, match="differs from exact provider bytes"):
        AuthoringStopResponse.model_validate(tampered)


def _plan(slot: str) -> AuthoringCandidatePlan:
    candidate = _identity(slot)
    return AuthoringCandidatePlan(
        candidate=candidate,
        stop_requests=tuple(
            AuthoringStopRequest.create(
                candidate=candidate,
                stop_index=index,
                compose_input_sha256=str(index + 7) * 64,
            )
            for index in range(2)
        ),
    )


def test_candidate_a_and_b_have_complete_independent_call_plans() -> None:
    plan_a = _plan("A")
    plan_b = _plan("B")

    assert tuple(item.stop_index for item in plan_a.stop_requests) == (0, 1)
    assert tuple(item.stop_index for item in plan_b.stop_requests) == (0, 1)
    assert {item.request_id for item in plan_a.stop_requests}.isdisjoint(
        item.request_id for item in plan_b.stop_requests
    )


def test_candidate_plan_rejects_one_request_from_another_candidate() -> None:
    plan_a = _plan("A")
    plan_b = _plan("B")

    with pytest.raises(ValidationError, match="request from another candidate"):
        AuthoringCandidatePlan(
            candidate=plan_a.candidate,
            stop_requests=(plan_a.stop_requests[0], plan_b.stop_requests[1]),
        )


def _response(request: AuthoringStopRequest) -> AuthoringStopResponse:
    raw = ('{"stop":' + str(request.stop_index) + '}').encode()
    return AuthoringStopResponse(
        request=request,
        raw_response=raw,
        raw_response_sha256=hashlib.sha256(raw).hexdigest(),
        parsed_payload_sha256="9" * 64,
    )


def test_candidate_response_set_assembles_only_one_complete_plan() -> None:
    plan = _plan("A")
    response_set = AuthoringCandidateResponseSet(
        plan=plan,
        responses=tuple(_response(request) for request in plan.stop_requests),
    )

    assert response_set.plan.candidate.candidate_slot == "A"


def test_candidate_response_set_rejects_missing_or_cross_candidate_stops() -> None:
    plan_a = _plan("A")
    plan_b = _plan("B")

    with pytest.raises(ValidationError, match="exact single-candidate plan"):
        AuthoringCandidateResponseSet(
            plan=plan_a,
            responses=(_response(plan_a.stop_requests[0]),),
        )
    with pytest.raises(ValidationError, match="exact single-candidate plan"):
        AuthoringCandidateResponseSet(
            plan=plan_a,
            responses=(
                _response(plan_a.stop_requests[0]),
                _response(plan_b.stop_requests[1]),
            ),
        )
