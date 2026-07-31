"""The typed rejection the preview route returns when a tour is not an LLM candidate.

A9 deleted the three script-inspecting predicates this module used to test
(``llm_candidate_rejection``/``llm_candidate_ineligibility``/``is_complete_llm_candidate``)
along with the ``Script.verify_report`` field they read: only the deleted whole-tour
``compose_script_per_chapter`` ever populated it, so on the one-engine tree every one of
them answered "missing composition trace" for every script. The four tests that drove
those predicates went with them; ``src/api/routes/trips.py`` names its own rejection codes
directly, and the shape it returns is what is still pinned here (and end-to-end by
tests/test_trip_preview_contract.py).
"""

from src.tour.candidate_eligibility import CandidateRejection, CandidateRejectionCode


def test_uncertified_provider_trace_is_a_typed_rejection_code() -> None:
    rejection = CandidateRejection(
        code=CandidateRejectionCode.UNCERTIFIED_PROVIDER_TRACE,
        detail="raw provider trace not certified",
    )

    assert rejection.model_dump(mode="json")["code"] == "uncertified_provider_trace"
