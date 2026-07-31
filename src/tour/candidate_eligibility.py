"""Provenance eligibility for customer-quality tour grading.

Grounded deterministic narration remains useful as a Basic Tour, but it is not
an LLM candidate and must never receive a quality score.  This module keeps that
decision independent from prose-quality heuristics.

Only the TYPED REJECTION is left. The three script-inspecting predicates that used
to live here (``llm_candidate_rejection``/``llm_candidate_ineligibility``/
``is_complete_llm_candidate``) read ``Script.verify_report``, a per-stop diagnostic
only the deleted whole-tour ``compose_script_per_chapter`` ever populated; on the
one-engine tree they answered "missing composition trace" for every script, so the
preview route names its own rejection codes directly instead.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class CandidateRejectionCode(StrEnum):
    GENERATION_FAILED = "generation_failed"
    UNCERTIFIED_PROVIDER_TRACE = "uncertified_provider_trace"
    MISSING_COMPOSITION_TRACE = "missing_composition_trace"
    FALLBACK_PRESENT = "fallback_present"
    SENTENCE_FLOOR_PRESENT = "sentence_floor_present"
    QUALITY_REJECTED = "quality_rejected"
    CANCELLED = "cancelled"
    BUILD_FINGERPRINT_UNAVAILABLE = "build_fingerprint_unavailable"


class CandidateRejection(BaseModel):
    """Stable machine code plus human-readable provenance failure detail."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: CandidateRejectionCode
    detail: str


__all__ = [
    "CandidateRejection",
    "CandidateRejectionCode",
]
