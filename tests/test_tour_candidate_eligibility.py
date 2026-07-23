"""The LLM grading lane must reject every grounded-fallback shape."""

from src.tour.candidate_eligibility import (
    CandidateRejection,
    CandidateRejectionCode,
    llm_candidate_ineligibility,
)
from src.tour.contract import (
    Script,
    ScriptPOI,
    StopCorrectionCounts,
    StopVerifyStatus,
    TourInput,
    ValidationReport,
)


def _script(*, status: str = "composed", floored: int = 0) -> Script:
    return Script(
        city_slug="paris",
        generated_at="2026-07-21T00:00:00Z",
        inputs=TourInput(start=(48.8568, 2.3414), duration_min=90, city_slug="paris"),
        total_audio_seconds=0,
        total_walking_seconds=0,
        total_walk_distance_m=0,
        total_planned_seconds=0,
        selected_pois=(
            ScriptPOI(id="p0", name="Stop", tier=1, lat=48.8568, lng=2.3414),
        ),
        lens_coverage={},
        script=(),
        validation=ValidationReport(
            stop_correction_counts=(
                (0, StopCorrectionCounts(floored=floored, floored_audio_seconds=floored)),
            )
        ),
        verify_report=(StopVerifyStatus(stop_idx=0, status=status),),
    )


def test_complete_provider_composition_is_eligible() -> None:
    assert llm_candidate_ineligibility(_script()) is None


def test_uncertified_provider_trace_is_a_typed_rejection_code() -> None:
    rejection = CandidateRejection(
        code=CandidateRejectionCode.UNCERTIFIED_PROVIDER_TRACE,
        detail="raw provider trace not certified",
    )

    assert rejection.model_dump(mode="json")["code"] == "uncertified_provider_trace"


def test_surgical_or_whole_stop_fallback_is_ineligible() -> None:
    assert "fallback" in llm_candidate_ineligibility(
        _script(status="partially_reverted")
    )
    assert "fallback" in llm_candidate_ineligibility(
        _script(status="reverted_to_stitched")
    )


def test_sentence_floor_is_ineligible_even_when_stop_status_says_composed() -> None:
    assert "floored" in llm_candidate_ineligibility(_script(floored=1))


def test_uncomposed_basic_script_is_ineligible_not_low_scoring() -> None:
    basic = _script().model_copy(update={"verify_report": ()})
    assert "missing" in llm_candidate_ineligibility(basic)
