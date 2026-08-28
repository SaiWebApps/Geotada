"""Offline checks for the v2 batch receipt schema and cross-version validation."""

from __future__ import annotations

import hashlib
import json

import pytest

from src.tour.batch_transport import BatchUnitResult, build_batch_receipt, validate_receipt
from src.tour.certification_provider import PhysicalProviderResponse


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def _succeeded_unit_result() -> BatchUnitResult:
    response = PhysicalProviderResponse(
        body=b'{"sentences":[]}',
        input_tokens=11,
        output_tokens=7,
        latency_ms=0,
        model="frozen-model",
        provider_request_id="msg-one",
    )
    return BatchUnitResult(
        custom_id="stop:0",
        result_type="succeeded",
        response=response,
        batch_id="msgbatch_01",
    )


def _receipt(**overrides: object) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "unit_result": _succeeded_unit_result(),
        "request_id": "req-0",
        "request_sha256": "a" * 64,
        "response_sha256": "b" * 64,
        "parsed_payload_sha256": "c" * 64,
        "poi_name": "Louvre",
        "stop_index": 0,
        "raw_response": '{"sentences":[]}',
    }
    kwargs.update(overrides)
    return build_batch_receipt(**kwargs)


def test_build_batch_receipt_produces_valid_v2() -> None:
    receipt = _receipt()

    assert receipt["schema_version"] == "ondoway-text-candidate-stop-v2"
    assert receipt["batch_id"] == "msgbatch_01"
    assert receipt["result_type"] == "succeeded"
    assert "latency_ms" not in receipt
    core = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    assert receipt["receipt_sha256"] == _canonical_sha256(core)


def test_validate_receipt_accepts_v1() -> None:
    core = {
        "schema_version": "ondoway-text-candidate-stop-v1",
        "stop_index": 0,
        "poi_name": "Louvre",
        "request_id": "req-0",
        "request_sha256": "a" * 64,
        "response_sha256": "b" * 64,
        "parsed_payload_sha256": "c" * 64,
        "provider_request_id": "msg-one",
        "model": "frozen-model",
        "input_tokens": 11,
        "output_tokens": 7,
        "latency_ms": 842,
        "raw_response": '{"sentences":[]}',
    }
    receipt = {**core, "receipt_sha256": _canonical_sha256(core)}

    validate_receipt(receipt)


def test_validate_receipt_accepts_v2() -> None:
    validate_receipt(_receipt())


def test_validate_receipt_rejects_tampered_hash() -> None:
    tampered = {**_receipt(), "poi_name": "Eiffel Tower"}

    with pytest.raises(ValueError, match="receipt_sha256"):
        validate_receipt(tampered)


def test_validate_receipt_rejects_unknown_schema() -> None:
    core = {"schema_version": "ondoway-text-candidate-stop-v99", "stop_index": 0}
    receipt = {**core, "receipt_sha256": _canonical_sha256(core)}

    with pytest.raises(ValueError, match="schema_version"):
        validate_receipt(receipt)
