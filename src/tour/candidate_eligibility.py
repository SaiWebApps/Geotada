"""Provenance eligibility for customer-quality tour grading.

Grounded deterministic narration remains useful as a Basic Tour, but it is not
an LLM candidate and must never receive a quality score.  This module keeps that
decision independent from prose-quality heuristics.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from .contract import Script


class CandidateRejectionCode(StrEnum):
    GENERATION_FAILED = "generation_failed"
    UNCERTIFIED_PROVIDER_TRACE = "uncertified_provider_trace"
    MISSING_COMPOSITION_TRACE = "missing_composition_trace"
    FALLBACK_PRESENT = "fallback_present"
    SENTENCE_FLOOR_PRESENT = "sentence_floor_present"
    QUALITY_REJECTED = "quality_rejected"
    CANCELLED = "cancelled"


class CandidateRejection(BaseModel):
    """Stable machine code plus human-readable provenance failure detail."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: CandidateRejectionCode
    detail: str


def llm_candidate_rejection(script: Script) -> CandidateRejection | None:
    """Return the typed reason a script cannot enter the LLM grading lane."""
    if not script.verify_report:
        return CandidateRejection(
            code=CandidateRejectionCode.MISSING_COMPOSITION_TRACE,
            detail="missing per-stop LLM composition provenance",
        )

    traced_stops = [item.stop_idx for item in script.verify_report]
    if sorted(traced_stops) != list(range(len(script.selected_pois))):
        return CandidateRejection(
            code=CandidateRejectionCode.MISSING_COMPOSITION_TRACE,
            detail=(
                "per-stop LLM composition provenance does not cover every selected "
                "stop exactly once"
            ),
        )

    degraded = tuple(
        item.stop_idx for item in script.verify_report if item.status != "composed"
    )
    if degraded:
        return CandidateRejection(
            code=CandidateRejectionCode.FALLBACK_PRESENT,
            detail="non-LLM fallback present at stop(s): "
            + ", ".join(map(str, degraded)),
        )

    floored = tuple(
        stop_idx
        for stop_idx, counts in script.validation.stop_correction_counts
        if counts.floored > 0 or counts.floored_audio_seconds > 0
    )
    if floored:
        return CandidateRejection(
            code=CandidateRejectionCode.SENTENCE_FLOOR_PRESENT,
            detail="grounded sentences floored at stop(s): "
            + ", ".join(map(str, floored)),
        )

    return None


def llm_candidate_ineligibility(script: Script) -> str | None:
    """Return why a composed script is not complete provider-authored output.

    ``compose_script_per_chapter`` records both whole/surgical reverts and the
    corrector's sentence-level floors.  Both signals are required: checking only
    whether a whole stop byte-matches the scaffold misses mixed fallback output.
    """

    rejection = llm_candidate_rejection(script)
    return rejection.detail if rejection is not None else None


def is_complete_llm_candidate(script: Script) -> bool:
    return llm_candidate_ineligibility(script) is None


__all__ = [
    "CandidateRejection",
    "CandidateRejectionCode",
    "is_complete_llm_candidate",
    "llm_candidate_ineligibility",
    "llm_candidate_rejection",
]
