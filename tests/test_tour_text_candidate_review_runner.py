"""Guards for the provider-only Candidate A semantic review lane."""

from __future__ import annotations

import json
from hashlib import sha256
from types import SimpleNamespace

import pytest

from scripts import tour_text_candidate_review as runner
from src.tour.contract import Sentence
from src.tour.quality_certification import (
    ENJOY_AXIS_NAMES,
    EnjoymentAxisAssessment,
    EnjoymentAxisScores,
    EnjoymentEvidenceSpan,
    EnjoymentItem,
    EnjoymentScoredAssessment,
    EnjoymentSegment,
    resolve_enjoyment_evidence_offsets,
)
from src.tour.quality_requests import SHARED_POLICY


def _request() -> SimpleNamespace:
    beat = SimpleNamespace(
        key_claims=("A square was destroyed.",),
        script_body="The square was destroyed.",
        source_passage="Contemporary records say the square was destroyed.",
    )
    return SimpleNamespace(
        beats_by_id={"beat-1": beat},
        visited_claims_by_slot={0: ("The route begins here.",)},
    )


def test_fact_input_exposes_only_provider_text_and_exact_authorized_evidence() -> None:
    provider_sentence = Sentence(
        text="The square came down.",
        source_id="beat-1",
        source_type="beat",
        stop_idx=0,
    )
    request = _request()
    route_receipt = {"legs": [{"request_sha256": "a" * 64, "response_sha256": "b" * 64}]}

    review = runner._fact_input(
        stop_index=0,
        sentences=(provider_sentence,),
        request=request,
        route_summary=route_receipt,
        candidate_sha256="c" * 64,
    )

    assert tuple(sentence.text for sentence in review.sentences) == ("The square came down.",)
    assert len(review.evidence_table) == 1
    evidence = review.evidence_table[0]
    assert json.loads(evidence.derivation_payload_json) == {
        "beat_id": "beat-1",
        "key_claims": ["A square was destroyed."],
        "script_body": "The square was destroyed.",
        "source_passage": "Contemporary records say the square was destroyed.",
    }
    assert "stitched" not in runner.fact_request_envelope(review, model=runner.COMPOSE_MODEL)[0]


def test_glue_evidence_is_route_receipt_and_request_bound_claim_context() -> None:
    sentence = Sentence(
        text="You're at the first stop.",
        source_id="opaque-derived-source",
        source_type="glue",
        stop_idx=0,
    )
    route_receipt = {"pois": [{"name": "First Stop"}], "legs": []}

    evidence = runner._evidence(
        stop_index=0,
        sentence=sentence,
        request=_request(),
        route_summary=route_receipt,
        candidate_sha256="d" * 64,
    )

    assert len(evidence) == 1
    assert json.loads(evidence[0].derivation_payload_json) == {
        "route_receipt": route_receipt,
        "stop_index": 0,
        "visited_claims_before_stop": ["The route begins here."],
    }


def test_dry_run_never_constructs_a_paid_client(monkeypatch, capsys) -> None:
    plan = {
        "candidate_slot": "A",
        "review_attempt": "B",
        "plan_sha256": "e" * 64,
        "candidate_narration_sha256": "f" * 64,
        "model": runner.COMPOSE_MODEL,
        "thinking": {"type": "adaptive"},
        "sdk_max_retries": 0,
        "provider_timeout_seconds": None,
        "max_concurrent_calls": runner.REVIEW_MAX_WORKERS,
        "coverage": "provider_text_only",
        "units": [],
    }
    monkeypatch.setattr(runner, "_review_plan", lambda _attempt: (plan, {}))
    monkeypatch.setattr(
        runner,
        "_anthropic_review_client",
        lambda: pytest.fail("dry run constructed a paid client"),
    )

    assert runner.main([]) == 0
    assert json.loads(capsys.readouterr().out)["plan_sha256"] == "e" * 64


def test_live_requires_exact_separate_review_approval_before_client(monkeypatch) -> None:
    plan = {
        "candidate_slot": "A",
        "review_attempt": "B",
        "plan_sha256": "e" * 64,
        "candidate_narration_sha256": "f" * 64,
        "model": runner.COMPOSE_MODEL,
        "thinking": {"type": "adaptive"},
        "sdk_max_retries": 0,
        "provider_timeout_seconds": None,
        "max_concurrent_calls": runner.REVIEW_MAX_WORKERS,
        "coverage": "provider_text_only",
        "units": [],
    }
    monkeypatch.setattr(runner, "_review_plan", lambda _attempt: (plan, {}))
    monkeypatch.delenv(runner.LIVE_APPROVAL_ENV, raising=False)
    monkeypatch.setattr(
        runner,
        "_anthropic_review_client",
        lambda: pytest.fail("approval guard did not run first"),
    )

    with pytest.raises(ValueError, match=runner.LIVE_APPROVAL_ENV):
        runner.main(["--live", "--approve-plan-sha256", "e" * 64])


def test_attempt_marker_is_durable_and_request_bound(tmp_path) -> None:
    runner._write_attempt(tmp_path, "fact-0", "a" * 64)
    path = tmp_path / "attempt-fact-0.json"

    marker = runner._load_attempt(path, "fact-0", "a" * 64)
    assert marker["request_sha256"] == "a" * 64

    with pytest.raises(ValueError, match="plan-mismatched"):
        runner._load_attempt(path, "fact-0", "b" * 64)


def test_runner_has_no_pattern_based_semantic_engine() -> None:
    source = runner.Path(runner.__file__).read_text(encoding="utf-8")

    assert "import re" not in source
    assert "re.compile" not in source


def _enjoyment_fixture(
    narration: str, exact_passage: str
) -> tuple[EnjoymentItem, EnjoymentScoredAssessment]:
    digest = sha256(narration.encode("utf-8")).hexdigest()
    item = EnjoymentItem(
        item_id="opaque-item",
        source_payload_sha256="a" * 64,
        narration=narration,
        narration_sha256=digest,
        segments=(
            EnjoymentSegment(
                segment_id="opaque-segment",
                stop_index=0,
                placement="stop",
                narration=narration,
                narration_sha256=digest,
            ),
        ),
    )
    axis = EnjoymentAxisAssessment(
        score=2,
        evidence=(
            EnjoymentEvidenceSpan(
                segment_id="opaque-segment",
                passage_byte_start=999,
                passage_byte_end=1000,
                exact_passage=exact_passage,
            ),
        ),
        explanation="Exact evidence supports this score.",
    )
    assessment = EnjoymentScoredAssessment(
        item_id=item.item_id,
        axes=EnjoymentAxisScores(**{name: axis for name in ENJOY_AXIS_NAMES}),
    )
    return item, assessment


def test_enjoyment_offsets_are_derived_from_unique_exact_utf8_passage() -> None:
    narration = "Café listeners pause — then discover the doorway."
    exact_passage = "then discover the doorway"
    item, assessment = _enjoyment_fixture(narration, exact_passage)

    normalized = resolve_enjoyment_evidence_offsets((assessment,), items=(item,))

    span = normalized[0].axes.narrative_motion.evidence[0]
    expected_start = narration.encode("utf-8").find(exact_passage.encode("utf-8"))
    assert span.passage_byte_start == expected_start
    assert span.passage_byte_end == expected_start + len(exact_passage.encode("utf-8"))


@pytest.mark.parametrize(
    ("narration", "exact_passage", "message"),
    [
        ("One exact passage.", "not present", "absent"),
        ("Repeat this. Repeat this.", "Repeat this.", "not unique"),
    ],
)
def test_enjoyment_offset_derivation_rejects_unbound_quotes(
    narration: str, exact_passage: str, message: str
) -> None:
    item, assessment = _enjoyment_fixture(narration, exact_passage)

    with pytest.raises(ValueError, match=message):
        resolve_enjoyment_evidence_offsets((assessment,), items=(item,))


def test_general_fact_policy_and_calibration_accept_supported_compression() -> None:
    manifest = json.loads((runner.SPEC / "calibration-manifest.json").read_text("utf-8"))
    cases = manifest["fact_policy_calibration"]["cases"]

    assert cases[4]["expected_fact"] == "PASS"
    assert cases[5]["expected_fact"] == "PASS"
    assert "The square was torn down" not in SHARED_POLICY
    assert "possible connotations" in SHARED_POLICY
