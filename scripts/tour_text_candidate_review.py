"""Durable semantic review of provider-authored Candidate A text.

The runner has no authoring, repair, retry, or fallback behavior.  It reviews only
the eight exact provider receipts produced by ``tour_text_candidate.py``.  Dry-run
prints a frozen, hash-bound plan and cannot construct an Anthropic client.
"""

from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from dotenv import load_dotenv

from scripts.tour_text_candidate import (
    _canonical_bytes,
    _file_sha256,
    _load_completed_receipt,
    _private_write_new,
    _sha256,
)
from scripts.tour_text_candidate import (
    _plan as candidate_plan,
)
from src.tour.anthropic_client import PAID_CALL_PERMISSION_ENV
from src.tour.candidate_authoring import AuthoringCandidateIdentity, AuthoringStopRequest
from src.tour.certification_provider import AnthropicCertificationProvider, CallPurpose
from src.tour.compose import (
    COMPOSE_MODEL,
    _sentences_from_json,
    candidate_compose_request_envelope,
    compose_input_sha256,
)
from src.tour.contract import Sentence
from src.tour.quality_certification import (
    ENJOY_AXIS_NAMES,
    ENJOY_RELEASE_THRESHOLD,
    EnjoymentItem,
    EnjoymentScoredReviewBatch,
    FactReviewBatch,
    _single_review_enjoyment_decision,
    enjoyment_below_gold_axes,
    enjoyment_reviewer_total,
    load_quality_calibration_inputs,
)
from src.tour.quality_requests import (
    ADJUDICATION_PROMPT_SHA256,
    CALIBRATION_PROMPT_SHA256,
    ENJOY_PROMPT_SHA256,
    FACT_PROMPT_SHA256,
    FactPayload,
    ProviderCalibrationPayload,
    ProviderEnjoyPayload,
    calibration_request_envelope,
    enjoyment_request_envelope,
    fact_request_envelope,
)
from src.tour.provider_text_review import (
    build_enjoyment_item,
    build_fact_input,
    candidate_narration_sha256,
    evidence_for_sentence,
    validate_calibration,
    validate_enjoyment,
    validate_fact,
)

# Kept as compatibility aliases for focused tests and existing internal callers.
_candidate_narration_sha256 = candidate_narration_sha256
_enjoyment_item = build_enjoyment_item
_evidence = evidence_for_sentence
_fact_input = build_fact_input
_validate_calibration = validate_calibration
_validate_enjoy = validate_enjoyment
_validate_fact = validate_fact

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "specs" / "2026-07-21-tour-certification"
CANDIDATE_DIR = ROOT / "data" / "certification" / "paris" / "text-candidate-A"
REVIEW_ROOT = ROOT / "data" / "certification" / "paris"
LIVE_APPROVAL_ENV = "ONDOWAY_TEXT_CANDIDATE_REVIEW_APPROVED"
REVIEW_MAX_WORKERS = 4


def _anthropic_review_client() -> object:
    if os.environ.get(PAID_CALL_PERMISSION_ENV) != "1":
        raise RuntimeError(
            f"paid LLM calls are locked; set {PAID_CALL_PERMISSION_ENV}=1 only after preflight"
        )
    import anthropic

    return anthropic.Anthropic(timeout=None, max_retries=0)


def _canonical_hash(value: object) -> str:
    return _sha256(_canonical_bytes(value))


def _candidate_inputs() -> tuple[
    dict[str, object],
    dict[int, dict[str, object]],
    dict[int, dict[str, object]],
    dict[int, tuple[Sentence, ...]],
]:
    """Reload and prove Candidate A against the exact current authoring boundary."""
    frozen_plan = json.loads((CANDIDATE_DIR / "plan.json").read_text(encoding="utf-8"))
    frozen_core = {key: value for key, value in frozen_plan.items() if key != "plan_sha256"}
    if frozen_plan.get("plan_sha256") != _canonical_hash(frozen_core):
        raise ValueError("Candidate A frozen authoring plan has an invalid self-hash")

    current_plan, current_runtime = candidate_plan("A")
    frozen_candidate = AuthoringCandidateIdentity.model_validate(frozen_plan["candidate"])
    current_units = {unit["stop_index"]: unit for unit in current_plan["units"]}
    rebuilt_units: list[dict[str, object]] = []
    runtime: dict[int, dict[str, object]] = {}
    for stop_index, current in sorted(current_runtime.items()):
        request = current["request"]
        authoring = AuthoringStopRequest.create(
            candidate=frozen_candidate,
            stop_index=stop_index,
            compose_input_sha256=compose_input_sha256(request),
        )
        envelope, sdk_request = candidate_compose_request_envelope(
            request, authoring, model=COMPOSE_MODEL
        )
        current_unit = current_units[stop_index]
        unit = {
            "stop_index": stop_index,
            "poi_name": current_unit["poi_name"],
            "request_id": authoring.request_id,
            "request_sha256": _sha256(envelope.encode("utf-8")),
            "input_byte_count": len(envelope.encode("utf-8")),
            "output_token_ceiling": current_unit["output_token_ceiling"],
        }
        rebuilt_units.append(unit)
        runtime[stop_index] = {
            "unit": {**unit, "sdk_request": sdk_request},
            "request": request,
            "authoring": authoring,
        }
    rebuilt_core = {
        **{key: value for key, value in current_plan.items() if key != "plan_sha256"},
        "candidate": frozen_candidate.model_dump(mode="json"),
        "units": rebuilt_units,
    }
    rebuilt_plan = {**rebuilt_core, "plan_sha256": _canonical_hash(rebuilt_core)}
    if frozen_plan != rebuilt_plan:
        raise ValueError("Candidate A plan differs from its reconstructed request plan")
    receipts: dict[int, dict[str, object]] = {}
    sentences: dict[int, tuple[Sentence, ...]] = {}
    for stop_index, item in runtime.items():
        receipt = _load_completed_receipt(CANDIDATE_DIR / f"stop-{stop_index}.json", item)
        receipts[stop_index] = receipt
        raw = json.loads(str(receipt["raw_response"]))
        sentences[stop_index] = _sentences_from_json(raw["sentences"], item["request"])
    return frozen_plan, runtime, receipts, sentences


def _route_summary() -> tuple[dict[str, object], str]:
    path = SPEC / "live-route-summary.json"
    return json.loads(path.read_text(encoding="utf-8")), _file_sha256(path)


def _review_plan(
    review_attempt: str,
) -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    candidate, candidate_runtime, receipts, sentences = _candidate_inputs()
    route, route_sha256 = _route_summary()
    inputs = load_quality_calibration_inputs(
        repo_root=ROOT,
        calibration_manifest_path=SPEC / "calibration-manifest.json",
        reference_manifest_path=SPEC / "investigation-reference-manifest.json",
    )
    candidate_sha = _candidate_narration_sha256(sentences)
    fact_inputs = {
        stop_index: _fact_input(
            stop_index=stop_index,
            sentences=stop_sentences,
            request=candidate_runtime[stop_index]["request"],
            route_summary=route,
            candidate_sha256=candidate_sha,
        )
        for stop_index, stop_sentences in sentences.items()
    }
    enjoy_item = _enjoyment_item(sentences, candidate_sha)

    calibration_envelope, calibration_sdk = calibration_request_envelope(
        inputs.fact_cases, inputs.enjoyment_anchors, model=COMPOSE_MODEL
    )
    runtime: dict[str, dict[str, object]] = {
        "calibration": {
            "purpose": CallPurpose.CALIBRATION,
            "sdk_request": calibration_sdk,
            "envelope": calibration_envelope,
            "payload_type": ProviderCalibrationPayload,
            "input": inputs,
        }
    }
    for stop_index, fact_input in fact_inputs.items():
        envelope, sdk_request = fact_request_envelope(fact_input, model=COMPOSE_MODEL)
        runtime[f"fact-{stop_index}"] = {
            "purpose": CallPurpose.FACT_REVIEW,
            "sdk_request": sdk_request,
            "envelope": envelope,
            "payload_type": FactPayload,
            "input": fact_input,
        }
    enjoy_envelope, enjoy_sdk = enjoyment_request_envelope(
        (enjoy_item,), inputs.enjoyment_anchors, model=COMPOSE_MODEL
    )
    runtime["enjoy"] = {
        "purpose": CallPurpose.ENJOY_REVIEW,
        "sdk_request": enjoy_sdk,
        "envelope": enjoy_envelope,
        "payload_type": ProviderEnjoyPayload,
        "input": enjoy_item,
        "anchors": inputs.enjoyment_anchors,
    }

    units = []
    for unit_id, item in runtime.items():
        sdk_request = item["sdk_request"]
        units.append(
            {
                "unit_id": unit_id,
                "purpose": item["purpose"].value,
                "request_sha256": _sha256(str(item["envelope"]).encode("utf-8")),
                "input_byte_count": len(str(item["envelope"]).encode("utf-8")),
                "output_token_ceiling": sdk_request["max_tokens"],
            }
        )
    plan_core = {
        "schema_version": "ondoway-text-candidate-review-plan-v1",
        "candidate_slot": "A",
        "review_attempt": review_attempt,
        "candidate_plan_sha256": candidate["plan_sha256"],
        "candidate_narration_sha256": candidate_sha,
        "candidate_receipt_sha256s": {
            str(index): receipt["receipt_sha256"] for index, receipt in sorted(receipts.items())
        },
        "route_summary_sha256": route_sha256,
        "calibration_manifest_sha256": inputs.calibration_manifest_sha256,
        "reference_manifest_sha256": inputs.reference_manifest_sha256,
        "calibration_bundle_sha256": inputs.bundle_sha256,
        "model": COMPOSE_MODEL,
        "thinking": {"type": "adaptive"},
        "sdk_max_retries": 0,
        "provider_timeout_seconds": None,
        "max_concurrent_calls": REVIEW_MAX_WORKERS,
        "coverage": "provider_text_only",
        "runner_sha256": _file_sha256(Path(__file__)),
        "candidate_runner_sha256": _file_sha256(ROOT / "scripts/tour_text_candidate.py"),
        "provider_boundary_sha256": _file_sha256(ROOT / "src/tour/certification_provider.py"),
        "quality_request_sha256": _file_sha256(ROOT / "src/tour/quality_requests.py"),
        "quality_policy_sha256": _file_sha256(ROOT / "src/tour/quality_certification.py"),
        "prompt_sha256s": {
            "calibration": CALIBRATION_PROMPT_SHA256,
            "fact": FACT_PROMPT_SHA256,
            "enjoy": ENJOY_PROMPT_SHA256,
        },
        "units": units,
    }
    plan = {**plan_core, "plan_sha256": _canonical_hash(plan_core)}
    return plan, runtime


def _summary(plan: dict[str, object]) -> dict[str, object]:
    return {
        "candidate_slot": plan["candidate_slot"],
        "review_attempt": plan["review_attempt"],
        "plan_sha256": plan["plan_sha256"],
        "candidate_narration_sha256": plan["candidate_narration_sha256"],
        "model": plan["model"],
        "thinking": plan["thinking"],
        "physical_call_count": len(plan["units"]),
        "sdk_max_retries": plan["sdk_max_retries"],
        "provider_timeout_seconds": plan["provider_timeout_seconds"],
        "max_concurrent_calls": plan["max_concurrent_calls"],
        "coverage": plan["coverage"],
        "units": plan["units"],
    }


def _invoke(*, client: object, unit_id: str, item: dict[str, object]) -> dict[str, object]:
    provider = AnthropicCertificationProvider(compose_client=client, judge_client=client)
    response = provider.invoke(
        purpose=item["purpose"],
        unit_id=unit_id,
        request=item["sdk_request"],
    )
    core: dict[str, object] = {
        "schema_version": "ondoway-text-candidate-review-response-v1",
        "unit_id": unit_id,
        "request_sha256": _sha256(str(item["envelope"]).encode("utf-8")),
        "response_sha256": _sha256(response.body),
        "provider_request_id": response.provider_request_id,
        "model": response.model,
        "input_tokens": response.input_tokens,
        "output_tokens": response.output_tokens,
        "latency_ms": response.latency_ms,
        "raw_response": response.body.decode("utf-8"),
    }
    try:
        payload = item["payload_type"].model_validate_json(response.body)
    except Exception as exc:
        core["parse_failure_type"] = type(exc).__name__
        core["parse_failure_message_sha256"] = _sha256(str(exc).encode("utf-8"))
    else:
        core["parsed_payload_sha256"] = _canonical_hash(payload.model_dump(mode="json"))
    return {**core, "receipt_sha256": _canonical_hash(core)}


def _load_response(
    path: Path, unit_id: str, item: dict[str, object]
) -> tuple[dict[str, object], object]:
    receipt = json.loads(path.read_text(encoding="utf-8"))
    core = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    raw = receipt.get("raw_response")
    if (
        receipt.get("schema_version") != "ondoway-text-candidate-review-response-v1"
        or receipt.get("unit_id") != unit_id
        or receipt.get("request_sha256") != _sha256(str(item["envelope"]).encode("utf-8"))
        or receipt.get("model") != COMPOSE_MODEL
        or receipt.get("receipt_sha256") != _canonical_hash(core)
        or not isinstance(raw, str)
        or receipt.get("response_sha256") != _sha256(raw.encode("utf-8"))
    ):
        raise ValueError(f"altered or plan-mismatched review response: {unit_id}")
    payload = item["payload_type"].model_validate_json(raw)
    if receipt.get("parsed_payload_sha256") != _canonical_hash(payload.model_dump(mode="json")):
        raise ValueError(f"altered parsed review payload: {unit_id}")
    return receipt, payload


def _aggregate(
    *,
    plan: dict[str, object],
    calibration: object,
    facts: dict[int, FactReviewBatch],
    enjoy: EnjoymentScoredReviewBatch,
    item: EnjoymentItem,
    anchors: tuple,
    responses: dict[str, dict[str, object]],
) -> dict[str, object]:
    candidate = next(value for value in enjoy.assessments if value.item_id == item.item_id)
    positive_ids = tuple(anchor.item.item_id for anchor in anchors if anchor.expected == "PASS")
    below_gold = enjoyment_below_gold_axes(
        enjoy,
        candidate_item_id=item.item_id,
        positive_gold_item_ids=positive_ids,
    )
    concerns = [
        {
            "stop_index": stop_index,
            "sentence_index": finding.sentence_index,
            "code": finding.code,
            "severity": finding.severity,
            "exact_passage": finding.exact_passage,
            "explanation": finding.explanation,
        }
        for stop_index, batch in sorted(facts.items())
        for verdict in batch.verdicts
        for finding in verdict.findings
    ]
    axes = {
        axis: {
            "score": getattr(candidate.axes, axis).score,
            "explanation": getattr(candidate.axes, axis).explanation,
        }
        for axis in ENJOY_AXIS_NAMES
    }
    enjoyment_decision = _single_review_enjoyment_decision(candidate)
    grade = "PASS" if not concerns and enjoyment_decision == "PASS" else "INCONCLUSIVE"
    core = {
        "schema_version": "ondoway-text-candidate-grade-v1",
        "candidate_slot": "A",
        "candidate_narration_sha256": plan["candidate_narration_sha256"],
        "review_plan_sha256": plan["plan_sha256"],
        "coverage": "provider_text_only",
        "product_certification": False,
        "audio_certification": False,
        "calibration_state": calibration.state,
        "fact": {
            "reviewed_stop_count": len(facts),
            "all_stops_without_material_concerns": not concerns,
            "material_concerns": concerns,
        },
        "enjoyment": {
            "axes": axes,
            "total": enjoyment_reviewer_total(candidate),
            "threshold": ENJOY_RELEASE_THRESHOLD,
            "single_review_decision": enjoyment_decision,
            "below_every_positive_gold_axes": list(below_gold),
        },
        "text_grade": grade,
        "response_receipt_sha256s": {
            unit_id: receipt["receipt_sha256"] for unit_id, receipt in sorted(responses.items())
        },
        "notice": (
            "One reviewer cannot issue a final factual rejection, and a single "
            "below-gold axis is advisory. This is not product, audio, release, "
            "or two-reviewer quality certification."
        ),
    }
    return {**core, "grade_sha256": _canonical_hash(core)}


def _write_attempt(review_dir: Path, unit_id: str, request_sha256: str) -> None:
    core = {
        "schema_version": "ondoway-text-candidate-review-attempt-v1",
        "unit_id": unit_id,
        "request_sha256": request_sha256,
    }
    _private_write_new(
        review_dir / f"attempt-{unit_id}.json",
        {**core, "marker_sha256": _canonical_hash(core)},
    )


def _load_attempt(path: Path, unit_id: str, request_sha256: str) -> dict[str, object]:
    marker = json.loads(path.read_text(encoding="utf-8"))
    core = {key: value for key, value in marker.items() if key != "marker_sha256"}
    if (
        marker.get("schema_version") != "ondoway-text-candidate-review-attempt-v1"
        or marker.get("unit_id") != unit_id
        or marker.get("request_sha256") != request_sha256
        or marker.get("marker_sha256") != _canonical_hash(core)
    ):
        raise ValueError(f"altered or plan-mismatched review attempt: {unit_id}")
    return marker


def _run_unit(
    *, review_dir: Path, client: object, unit_id: str, item: dict[str, object]
) -> tuple[dict[str, object], object]:
    response_path = review_dir / f"response-{unit_id}.json"
    attempt_path = review_dir / f"attempt-{unit_id}.json"
    failure_path = review_dir / f"failure-{unit_id}.json"
    request_sha = _sha256(str(item["envelope"]).encode("utf-8"))
    if response_path.exists():
        if not attempt_path.exists():
            raise ValueError(f"review response has no durable attempt marker: {unit_id}")
        _load_attempt(attempt_path, unit_id, request_sha)
        return _load_response(response_path, unit_id, item)
    if attempt_path.exists():
        _load_attempt(attempt_path, unit_id, request_sha)
        raise ValueError(
            f"review unit {unit_id} has an indeterminate paid attempt; no retry is allowed"
        )
    if failure_path.exists():
        raise ValueError(f"review unit {unit_id} already has a terminal failure receipt")
    _write_attempt(review_dir, unit_id, request_sha)
    try:
        receipt = _invoke(client=client, unit_id=unit_id, item=item)
    except BaseException as exc:
        failure_core = {
            "schema_version": "ondoway-text-candidate-review-failure-v1",
            "unit_id": unit_id,
            "request_sha256": request_sha,
            "failure_type": type(exc).__name__,
            "failure_message_sha256": _sha256(str(exc).encode("utf-8")),
        }
        _private_write_new(
            failure_path,
            {**failure_core, "failure_sha256": _canonical_hash(failure_core)},
        )
        raise
    _private_write_new(response_path, receipt)
    return _load_response(response_path, unit_id, item)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--approve-plan-sha256")
    parser.add_argument("--review-attempt", choices=("A", "B", "C", "D"), default="B")
    args = parser.parse_args(argv)
    load_dotenv(ROOT / ".env", override=False)
    plan, runtime = _review_plan(args.review_attempt)
    if not args.live:
        print(json.dumps(_summary(plan), indent=2, sort_keys=True))
        return 0
    if os.environ.get(LIVE_APPROVAL_ENV) != "1":
        raise ValueError(f"live review requires {LIVE_APPROVAL_ENV}=1")
    if args.approve_plan_sha256 != plan["plan_sha256"]:
        raise ValueError("--approve-plan-sha256 must match the exact dry plan")
    review_dir = REVIEW_ROOT / (
        "text-candidate-A-review"
        if args.review_attempt == "A"
        else f"text-candidate-A-review-{args.review_attempt}"
    )
    review_dir.mkdir(mode=0o700, parents=False, exist_ok=True)
    plan_path = review_dir / "plan.json"
    if plan_path.exists():
        if json.loads(plan_path.read_text(encoding="utf-8")) != plan:
            raise ValueError("existing review plan differs from this frozen plan")
    else:
        _private_write_new(plan_path, plan)

    client = _anthropic_review_client()
    responses: dict[str, dict[str, object]] = {}
    calibration_receipt, calibration_payload = _run_unit(
        review_dir=review_dir,
        client=client,
        unit_id="calibration",
        item=runtime["calibration"],
    )
    responses["calibration"] = calibration_receipt
    calibration = _validate_calibration(
        calibration_receipt, calibration_payload, runtime["calibration"]["input"]
    )

    review_unit_ids = (*tuple(f"fact-{index}" for index in range(8)), "enjoy")
    completed: dict[str, tuple[dict[str, object], object]] = {}
    with ThreadPoolExecutor(max_workers=REVIEW_MAX_WORKERS) as pool:
        unit_by_future = {
            pool.submit(
                _run_unit,
                review_dir=review_dir,
                client=client,
                unit_id=unit_id,
                item=runtime[unit_id],
            ): unit_id
            for unit_id in review_unit_ids
        }
        for future in as_completed(unit_by_future):
            unit_id = unit_by_future[future]
            completed[unit_id] = future.result()

    facts: dict[int, FactReviewBatch] = {}
    for stop_index in range(8):
        unit_id = f"fact-{stop_index}"
        receipt, payload = completed[unit_id]
        responses[unit_id] = receipt
        facts[stop_index] = _validate_fact(receipt, payload, runtime[unit_id]["input"])
    enjoy_receipt, enjoy_payload = completed["enjoy"]
    responses["enjoy"] = enjoy_receipt
    enjoy = _validate_enjoy(
        enjoy_receipt,
        enjoy_payload,
        runtime["enjoy"]["input"],
        runtime["enjoy"]["anchors"],
    )
    grade = _aggregate(
        plan=plan,
        calibration=calibration,
        facts=facts,
        enjoy=enjoy,
        item=runtime["enjoy"]["input"],
        anchors=runtime["enjoy"]["anchors"],
        responses=responses,
    )
    grade_path = review_dir / "grade.json"
    if grade_path.exists():
        if json.loads(grade_path.read_text(encoding="utf-8")) != grade:
            raise ValueError("existing grade differs from deterministic replay")
    else:
        _private_write_new(grade_path, grade)
    print(json.dumps(grade, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
