"""Contracts for loading the sealed provider-authored 4+4 review batch."""

from __future__ import annotations

import copy
import hashlib
import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.tour.certification_provider import PhysicalProviderResponse
from src.tour.contract import BeatRef, Sentence
from src.tour.provider_text_review import validate_fact
from src.tour.quality_certification import FactFinding, load_quality_calibration_inputs
from src.tour.quality_requests import (
    QUALITY_POLICY_SHA256,
    ProviderFactPayload,
    ProviderFactSentenceVerdict,
    _provider_schema,
)

ROOT = Path(__file__).resolve().parents[1]
BATCH_ROOT = ROOT / "data" / "certification" / "tour-batch-v1"
QUALITY_SPEC = ROOT / "specs" / "2026-07-21-tour-certification"


def _sealed_documents() -> tuple[dict, dict[str, dict], dict[tuple[str, int], dict]]:
    plan = json.loads((BATCH_ROOT / "plan.json").read_text(encoding="utf-8"))
    tours: dict[str, dict] = {}
    receipts: dict[tuple[str, int], dict] = {}
    for tour_plan in plan["tours"]:
        case_id = tour_plan["case_id"]
        city_slug = tour_plan["tour_input"]["city_slug"]
        case_dir = BATCH_ROOT / city_slug / case_id
        tours[case_id] = json.loads((case_dir / "tour.json").read_text(encoding="utf-8"))
        for unit in tour_plan["units"]:
            stop_index = unit["stop_index"]
            receipts[(case_id, stop_index)] = json.loads(
                (case_dir / f"stop-{stop_index}.json").read_text(encoding="utf-8")
            )
    return plan, tours, receipts


def _authoring_requests(loaded: object) -> dict[tuple[str, int], SimpleNamespace]:
    requests: dict[tuple[str, int], SimpleNamespace] = {}
    for tour in loaded.tours:
        for receipt in tour.receipts:
            stop_index = receipt["stop_index"]
            payload = json.loads(receipt["raw_response"])
            beat_ids = {
                beat_id
                for sentence in payload["sentences"]
                if sentence["source_type"] == "beat"
                for beat_id in (sentence["source_id"], *sentence.get("also_cites", ()))
            }
            requests[(tour.case_id, stop_index)] = SimpleNamespace(
                beats_by_id={
                    beat_id: SimpleNamespace(
                        key_claims=(f"Authorized claim for {beat_id}",),
                        script_body=f"Authorized script for {beat_id}",
                        source_passage=f"Authorized source passage for {beat_id}",
                    )
                    for beat_id in beat_ids
                },
                visited_claims_by_slot={stop_index: ()},
            )
    return requests


def _review_runtime(runner: object) -> dict[str, object]:
    plan, tours, receipts = _sealed_documents()
    loaded = runner.load_batch_review_inputs(
        batch_plan=plan,
        tour_artifacts=tours,
        stop_receipts=receipts,
    )
    material = runner.build_batch_review_material(
        inputs=loaded,
        authoring_requests=_authoring_requests(loaded),
    )
    calibration = load_quality_calibration_inputs(
        repo_root=ROOT,
        calibration_manifest_path=QUALITY_SPEC / "calibration-manifest.json",
        reference_manifest_path=QUALITY_SPEC / "investigation-reference-manifest.json",
    )
    return runner.build_batch_review_runtime(
        material=material,
        calibration_inputs=calibration,
    )


def test_load_batch_review_inputs_accepts_exact_sealed_eight_tours_and_45_receipts() -> None:
    runner = importlib.import_module("scripts.tour_batch_review")
    plan, tours, receipts = _sealed_documents()

    loaded = runner.load_batch_review_inputs(
        batch_plan=plan,
        tour_artifacts=tours,
        stop_receipts=receipts,
    )

    assert len(loaded.tours) == 8
    assert sum(len(tour.receipts) for tour in loaded.tours) == 45


def test_load_batch_review_inputs_rejects_structurally_non_provider_provenance() -> None:
    runner = importlib.import_module("scripts.tour_batch_review")
    plan, tours, receipts = _sealed_documents()
    altered = copy.deepcopy(tours)
    first_case_id = plan["tours"][0]["case_id"]
    altered[first_case_id]["provenance"] = "not_provider_response"

    with pytest.raises(ValueError):
        runner.load_batch_review_inputs(
            batch_plan=plan,
            tour_artifacts=altered,
            stop_receipts=receipts,
        )


def test_review_requests_recover_only_vignette_evidence_cited_by_stitch_and_provider() -> None:
    runner = importlib.import_module("scripts.tour_batch_review")
    cited = BeatRef(id="cited", poi_id="walk-past")
    uncited = BeatRef(id="uncited", poi_id="walk-past")
    existing = BeatRef(id="existing", poi_id="anchor")
    sentence = Sentence(
        text="Look across the street.",
        source_id="cited",
        source_type="beat",
        stop_idx=1,
    )
    request = SimpleNamespace(
        stitched=SimpleNamespace(script=(sentence,)),
        beats_by_id={"existing": existing},
    )
    request.model_copy = lambda *, update: SimpleNamespace(
        stitched=request.stitched,
        beats_by_id=update["beats_by_id"],
    )
    inputs = runner.BatchReviewInputs(
        batch_plan_sha256="plan",
        tours=(
            runner.BatchReviewTourInputs(
                case_id="case",
                tour_plan={},
                tour_artifact={},
                receipts=(
                    {
                        "stop_index": 1,
                        "raw_response": json.dumps(
                            {"sentences": [sentence.model_dump(mode="json")]}
                        ),
                    },
                ),
            ),
        ),
    )
    runtime = {
        "case": {
            "sequence": SimpleNamespace(vignette_beats={1: (cited, uncited)}),
            "units": {1: {"request": request}},
        }
    }

    copied = runner._review_authoring_requests(inputs=inputs, runtime=runtime)[("case", 1)]

    assert copied.beats_by_id == {"existing": existing, "cited": cited}
    assert request.beats_by_id == {"existing": existing}


def test_build_batch_review_material_uses_exact_full_provider_narration_and_evidence() -> None:
    runner = importlib.import_module("scripts.tour_batch_review")
    plan, tours, receipts = _sealed_documents()
    loaded = runner.load_batch_review_inputs(
        batch_plan=plan,
        tour_artifacts=tours,
        stop_receipts=receipts,
    )

    material = runner.build_batch_review_material(
        inputs=loaded,
        authoring_requests=_authoring_requests(loaded),
    )

    assert len(material.fact_inputs) == 8
    assert len(material.enjoyment_items) == 8
    for tour in loaded.tours:
        fact_input = material.fact_inputs[tour.case_id]
        enjoyment_item = material.enjoyment_items[tour.case_id]
        expected_stops = sorted(tour.tour_artifact["stops"], key=lambda stop: stop["stop_index"])
        expected_sentences = tuple(
            sentence for stop in expected_stops for sentence in stop["sentences"]
        )
        assert tuple(sentence.text for sentence in fact_input.sentences) == expected_sentences
        assert all(sentence.evidence_ids for sentence in fact_input.sentences)
        assert fact_input.provider_narration_sha256 == fact_input.blueprint_sha256
        assert enjoyment_item.source_payload_sha256 == fact_input.provider_narration_sha256
        assert enjoyment_item.narration == "\n".join(
            " ".join(stop["sentences"]) for stop in expected_stops
        )


def test_build_batch_review_plan_seals_17_adaptive_zero_retry_units_and_policy_hashes() -> None:
    runner = importlib.import_module("scripts.tour_batch_review")
    plan, tours, receipts = _sealed_documents()
    loaded = runner.load_batch_review_inputs(
        batch_plan=plan,
        tour_artifacts=tours,
        stop_receipts=receipts,
    )
    material = runner.build_batch_review_material(
        inputs=loaded,
        authoring_requests=_authoring_requests(loaded),
    )
    calibration = load_quality_calibration_inputs(
        repo_root=ROOT,
        calibration_manifest_path=QUALITY_SPEC / "calibration-manifest.json",
        reference_manifest_path=QUALITY_SPEC / "investigation-reference-manifest.json",
    )

    review_plan = runner.build_batch_review_plan(
        inputs=loaded,
        material=material,
        calibration_inputs=calibration,
    )

    assert len(review_plan["units"]) == 17
    assert [unit["purpose"] for unit in review_plan["units"]].count("calibration") == 1
    assert [unit["purpose"] for unit in review_plan["units"]].count("fact_review") == 8
    assert [unit["purpose"] for unit in review_plan["units"]].count("enjoy_review") == 8
    assert review_plan["thinking"] == {"type": "adaptive"}
    assert review_plan["sdk_max_retries"] == 0
    assert review_plan["application_deadline_seconds"] is None
    assert review_plan["calibration_manifest_sha256"] == calibration.calibration_manifest_sha256
    assert review_plan["reference_manifest_sha256"] == calibration.reference_manifest_sha256
    assert review_plan["calibration_bundle_sha256"] == calibration.bundle_sha256
    assert review_plan["quality_policy_sha256"] == QUALITY_POLICY_SHA256
    assert review_plan["tour_artifact_sha256s"] == {
        tour.case_id: tour.tour_artifact["artifact_sha256"] for tour in loaded.tours
    }


def test_batch_review_execution_gate_keeps_dry_and_wrong_hash_live_paths_client_free() -> None:
    runner = importlib.import_module("scripts.tour_batch_review")
    plan, tours, receipts = _sealed_documents()
    loaded = runner.load_batch_review_inputs(
        batch_plan=plan,
        tour_artifacts=tours,
        stop_receipts=receipts,
    )
    material = runner.build_batch_review_material(
        inputs=loaded,
        authoring_requests=_authoring_requests(loaded),
    )
    calibration = load_quality_calibration_inputs(
        repo_root=ROOT,
        calibration_manifest_path=QUALITY_SPEC / "calibration-manifest.json",
        reference_manifest_path=QUALITY_SPEC / "investigation-reference-manifest.json",
    )
    review_plan = runner.build_batch_review_plan(
        inputs=loaded,
        material=material,
        calibration_inputs=calibration,
    )
    factory_calls = 0

    def client_factory() -> object:
        nonlocal factory_calls
        factory_calls += 1
        return object()

    dry_result = runner.gate_batch_review_execution(
        inputs=loaded,
        material=material,
        review_plan=review_plan,
        live=False,
        approved_review_plan_sha256=None,
        client_factory=client_factory,
    )
    assert dry_result["review_plan_sha256"] == review_plan["review_plan_sha256"]
    assert factory_calls == 0

    with pytest.raises(ValueError):
        runner.gate_batch_review_execution(
            inputs=loaded,
            material=material,
            review_plan=review_plan,
            live=True,
            approved_review_plan_sha256="wrong",
            client_factory=client_factory,
        )
    assert factory_calls == 0


def test_build_batch_review_runtime_exactly_matches_all_17_sealed_plan_units() -> None:
    runner = importlib.import_module("scripts.tour_batch_review")
    plan, tours, receipts = _sealed_documents()
    loaded = runner.load_batch_review_inputs(
        batch_plan=plan,
        tour_artifacts=tours,
        stop_receipts=receipts,
    )
    material = runner.build_batch_review_material(
        inputs=loaded,
        authoring_requests=_authoring_requests(loaded),
    )
    calibration = load_quality_calibration_inputs(
        repo_root=ROOT,
        calibration_manifest_path=QUALITY_SPEC / "calibration-manifest.json",
        reference_manifest_path=QUALITY_SPEC / "investigation-reference-manifest.json",
    )
    review_plan = runner.build_batch_review_plan(
        inputs=loaded,
        material=material,
        calibration_inputs=calibration,
    )

    runtime = runner.build_batch_review_runtime(
        material=material,
        calibration_inputs=calibration,
    )

    assert len(runtime) == 17
    assert list(runtime) == [unit["unit_id"] for unit in review_plan["units"]]
    for planned in review_plan["units"]:
        unit = runtime[planned["unit_id"]]
        assert unit.unit_id == planned["unit_id"]
        assert unit.purpose == planned["purpose"]
        assert runner.request_envelope_sha256(unit.envelope) == planned["request_sha256"]
        assert json.loads(unit.envelope) == unit.sdk_request
        assert unit.sdk_request["thinking"] == {"type": "adaptive"}


def test_dispatch_reserves_before_invoke_resumes_without_duplicates_and_blocks_attempt_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = importlib.import_module("scripts.tour_batch_review")
    runtime = _review_runtime(runner)
    store = runner.DirectoryReviewReceiptStore(tmp_path / "completed")
    calls: list[str] = []

    monkeypatch.setattr(
        runner,
        "_parse_review_response",
        lambda unit, _receipt: {"unit_id": unit.unit_id},
    )

    def invoke(
        _purpose: str,
        unit_id: str,
        sdk_request: dict[str, object],
    ) -> PhysicalProviderResponse:
        assert store.load_attempt(unit_id) is not None
        calls.append(unit_id)
        return PhysicalProviderResponse(
            body=b"{}",
            input_tokens=1,
            output_tokens=1,
            latency_ms=1,
            model=str(sdk_request["model"]),
            provider_request_id=f"provider-{unit_id}",
        )

    first = runner.dispatch_batch_review(
        runtime=runtime,
        store=store,
        invoke=invoke,
        max_workers=4,
    )
    assert first.evaluation_status == "COMPLETE"
    assert len(calls) == 17
    assert calls[:2] == ["calibration", runner.FACT_CANARY_UNIT_ID]
    last_fact = max(index for index, unit_id in enumerate(calls) if unit_id.startswith("fact:"))
    first_enjoy = min(index for index, unit_id in enumerate(calls) if unit_id.startswith("enjoy:"))
    assert last_fact < first_enjoy

    calls.clear()
    resumed = runner.dispatch_batch_review(
        runtime=runtime,
        store=store,
        invoke=invoke,
        max_workers=4,
    )
    assert resumed.evaluation_status == "COMPLETE"
    assert calls == []

    blocked_store = runner.DirectoryReviewReceiptStore(tmp_path / "attempt-only")
    calibration = runtime["calibration"]
    blocked_store.write_attempt("calibration", runner._attempt_record(calibration))
    blocked = runner.dispatch_batch_review(
        runtime=runtime,
        store=blocked_store,
        invoke=invoke,
        max_workers=4,
    )
    assert blocked.evaluation_status == "INFRA_ERROR"
    assert blocked.infrastructure_errors == {
        "calibration": "indeterminate prior paid attempt"
    }
    assert calls == []


def test_failed_fact_canary_releases_no_other_review_units(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = importlib.import_module("scripts.tour_batch_review")
    runtime = _review_runtime(runner)
    store = runner.DirectoryReviewReceiptStore(tmp_path / "failed-canary")
    calls: list[str] = []

    def parse(unit: object, receipt: dict[str, object]) -> object:
        if receipt.get("stop_reason") == "max_tokens":
            raise ValueError("Anthropic certification response was truncated")
        return {"unit_id": unit.unit_id}

    monkeypatch.setattr(runner, "_parse_review_response", parse)

    def invoke(
        _purpose: str, unit_id: str, sdk_request: dict[str, object]
    ) -> PhysicalProviderResponse:
        calls.append(unit_id)
        return PhysicalProviderResponse(
            body=b"{}",
            input_tokens=1,
            output_tokens=1,
            latency_ms=1,
            model=str(sdk_request["model"]),
            provider_request_id=f"provider-{unit_id}",
            stop_reason=("max_tokens" if unit_id == runner.FACT_CANARY_UNIT_ID else "end_turn"),
        )

    result = runner.dispatch_batch_review(
        runtime=runtime, store=store, invoke=invoke, max_workers=4
    )

    assert calls == ["calibration", runner.FACT_CANARY_UNIT_ID]
    assert result.evaluation_status == "INFRA_ERROR"
    assert runner.FACT_CANARY_UNIT_ID in result.infrastructure_errors
    assert not any(unit_id.startswith("enjoy:") for unit_id in calls)


def test_exact_calibration_receipt_reuse_needs_zero_provider_invocations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = importlib.import_module("scripts.tour_batch_review")
    unit = _review_runtime(runner)["calibration"]
    source = runner.DirectoryReviewReceiptStore(tmp_path / "v1")
    target = runner.DirectoryReviewReceiptStore(tmp_path / "v2")
    source.write_attempt(unit.unit_id, runner._attempt_record(unit))
    source.write_response(
        unit.unit_id,
        runner._response_record(
            unit,
            PhysicalProviderResponse(
                body=b"{}",
                input_tokens=10,
                output_tokens=20,
                latency_ms=30,
                model=str(unit.sdk_request["model"]),
                provider_request_id="provider-calibration",
                stop_reason="end_turn",
            ),
        ),
    )

    assert runner.seed_exact_calibration_receipt(unit=unit, source=source, target=target)
    monkeypatch.setattr(runner, "_parse_review_response", lambda *_args: {"reused": True})
    calls = 0

    def invoke(*_args: object) -> PhysicalProviderResponse:
        nonlocal calls
        calls += 1
        raise AssertionError("exact calibration reuse must not invoke the provider")

    receipt, parsed, error = runner._run_review_unit(
        unit=unit, store=target, invoke=invoke
    )
    assert receipt == source.load_response(unit.unit_id)
    assert parsed == {"reused": True}
    assert error is None
    assert calls == 0


def test_calibration_reuse_refuses_model_mismatch(tmp_path: Path) -> None:
    runner = importlib.import_module("scripts.tour_batch_review")
    unit = _review_runtime(runner)["calibration"]
    source = runner.DirectoryReviewReceiptStore(tmp_path / "v1-mismatch")
    target = runner.DirectoryReviewReceiptStore(tmp_path / "v2-empty")
    source.write_attempt(unit.unit_id, runner._attempt_record(unit))
    source.write_response(
        unit.unit_id,
        runner._response_record(
            unit,
            PhysicalProviderResponse(
                body=b"{}",
                input_tokens=1,
                output_tokens=1,
                latency_ms=1,
                model="wrong-model",
                provider_request_id="wrong-model-response",
            ),
        ),
    )

    assert not runner.seed_exact_calibration_receipt(unit=unit, source=source, target=target)
    assert target.load_attempt(unit.unit_id) is None
    assert target.load_response(unit.unit_id) is None

def test_malformed_review_preserves_provider_receipt_without_creating_tour_status(
    tmp_path: Path,
) -> None:
    runner = importlib.import_module("scripts.tour_batch_review")
    runtime = _review_runtime(runner)
    store = runner.DirectoryReviewReceiptStore(tmp_path / "malformed")
    raw_response = b"{not-valid-json"

    def invoke(
        _purpose: str,
        unit_id: str,
        sdk_request: dict[str, object],
    ) -> PhysicalProviderResponse:
        return PhysicalProviderResponse(
            body=raw_response,
            input_tokens=7,
            output_tokens=3,
            latency_ms=11,
            model=str(sdk_request["model"]),
            provider_request_id=f"provider-{unit_id}",
        )

    result = runner.dispatch_batch_review(
        runtime=runtime,
        store=store,
        invoke=invoke,
        max_workers=4,
    )

    assert result.evaluation_status in {"INFRA_ERROR", "PARTIAL"}
    assert not hasattr(result, "tour_status")
    receipt = store.load_response("calibration")
    assert receipt is not None
    assert receipt["raw_response"] == raw_response.decode("utf-8")
    assert receipt["provider_request_id"] == "provider-calibration"
    assert result.response_receipts["calibration"] == receipt
    assert "calibration" in result.infrastructure_errors


def test_truncated_review_is_durable_infra_error_without_tour_status(tmp_path: Path) -> None:
    runner = importlib.import_module("scripts.tour_batch_review")
    runtime = _review_runtime(runner)
    store = runner.DirectoryReviewReceiptStore(tmp_path / "truncated")

    def invoke(
        _purpose: str,
        unit_id: str,
        sdk_request: dict[str, object],
    ) -> PhysicalProviderResponse:
        return PhysicalProviderResponse(
            body=b'{"partial":true}',
            input_tokens=123,
            output_tokens=64_000,
            latency_ms=456,
            model=str(sdk_request["model"]),
            provider_request_id=f"provider-{unit_id}",
            stop_reason="max_tokens",
        )

    result = runner.dispatch_batch_review(
        runtime=runtime,
        store=store,
        invoke=invoke,
        max_workers=4,
    )

    assert result.evaluation_status == "INFRA_ERROR"
    assert not hasattr(result, "tour_status")
    receipt = store.load_response("calibration")
    assert receipt is not None
    assert receipt["raw_response"] == '{"partial":true}'
    assert receipt["provider_request_id"] == "provider-calibration"
    assert (receipt["input_tokens"], receipt["output_tokens"]) == (123, 64_000)
    assert receipt["stop_reason"] == "max_tokens"
    assert result.response_receipts["calibration"] == receipt
    assert "calibration" in result.infrastructure_errors


def test_compact_fact_contract_is_exhaustive_and_binds_only_material_failures() -> None:
    runner = importlib.import_module("scripts.tour_batch_review")
    runtime = _review_runtime(runner)
    unit = next(item for key, item in runtime.items() if key.startswith("fact:"))
    request = unit.substantive_input
    compact = tuple(
        ProviderFactSentenceVerdict(
            sentence_index=sentence.sentence_index,
            sentence_sha256=sentence.sentence_sha256,
            decision="PASS",
        )
        for sentence in request.sentences
    )
    receipt = {
        "response_sha256": "a" * 64,
        "input_tokens": 1,
        "output_tokens": 1,
    }

    accepted = validate_fact(receipt, ProviderFactPayload(verdicts=compact), request)
    assert len(accepted.verdicts) == len(request.sentences)
    assert all(not verdict.claims for verdict in accepted.verdicts)
    with pytest.raises(ValueError, match="cover every sentence exactly once"):
        validate_fact(receipt, ProviderFactPayload(verdicts=compact[:-1]), request)

    sentence = request.sentences[0]
    finding = FactFinding(
        code="unsupported_material_claim",
        severity="blocker",
        sentence_index=sentence.sentence_index,
        sentence_sha256=sentence.sentence_sha256,
        passage_byte_start=0,
        passage_byte_end=len(sentence.text.encode("utf-8")),
        material_claim=sentence.text,
        material_type="specific_event",
        exact_passage=sentence.text,
        evidence_ids=(sentence.evidence_ids[0],),
        explanation="The supplied evidence contradicts this event.",
    )
    failed = list(compact)
    failed[0] = failed[0].model_copy(update={"decision": "FAIL", "findings": (finding,)})
    assert validate_fact(
        receipt, ProviderFactPayload(verdicts=tuple(failed)), request
    ).verdicts[0].findings
    wrong_offsets = finding.model_copy(
        update={
            "sentence_index": 999,
            "sentence_sha256": "b" * 64,
            "passage_byte_start": 1,
            "passage_byte_end": 2,
        }
    )
    failed[0] = failed[0].model_copy(
        update={"sentence_sha256": "b" * 64, "findings": (wrong_offsets,)}
    )
    normalized = validate_fact(
        receipt, ProviderFactPayload(verdicts=tuple(failed)), request
    )
    assert normalized.verdicts[0].sentence_sha256 == sentence.sentence_sha256
    assert normalized.verdicts[0].findings[0].passage_byte_start == 0
    assert normalized.verdicts[0].findings[0].passage_byte_end == len(
        sentence.text.encode("utf-8")
    )

    missing = finding.model_copy(update={"exact_passage": f"{sentence.text} missing"})
    failed[0] = failed[0].model_copy(update={"findings": (missing,)})
    with pytest.raises(ValueError, match="one unambiguous exact passage"):
        validate_fact(receipt, ProviderFactPayload(verdicts=tuple(failed)), request)

    repeated_text = f"{sentence.text} {sentence.text}"
    repeated_sentence = sentence.model_copy(
        update={
            "text": repeated_text,
            "sentence_sha256": hashlib.sha256(repeated_text.encode()).hexdigest(),
        }
    )
    repeated_request = request.model_copy(
        update={"sentences": (repeated_sentence, *request.sentences[1:])}
    )
    repeated_finding = finding.model_copy(
        update={
            "sentence_sha256": repeated_sentence.sentence_sha256,
            "passage_byte_end": len(sentence.text.encode("utf-8")),
        }
    )
    repeated = list(compact)
    repeated[0] = repeated[0].model_copy(
        update={"decision": "FAIL", "findings": (repeated_finding,)}
    )
    normalized_repeated = validate_fact(
        receipt, ProviderFactPayload(verdicts=tuple(repeated)), repeated_request
    )
    assert normalized_repeated.verdicts[0].findings[0].passage_byte_start == 0

    provider_schema = json.dumps(_provider_schema(ProviderFactPayload), sort_keys=True)
    assert '"claims"' not in provider_schema
    assert "no_material_assertion_reason" not in provider_schema
