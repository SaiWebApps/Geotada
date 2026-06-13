"""GRADE — exemplar-calibrated tour rubric (§2.7, M8).

A pure, weighted multi-axis score of a generated tour against a golden
fixture. This is a CI REGRESSION gate, not the ≥90% golden-overlap ideal:
the baseline is set so the current corpus passes with margin and a genuine
regression (POIs lost, spine wrong, beats dropped, validation broken) drops
below it. Never self-tunes — changing a weight or the baseline is a
deliberate, reviewed edit (§2.7).

The scoring function is pure (no DB, no engine) so it is unit-tested in the
default bar; the live grading harness (``tests/test_tour_grade.py``, marked
``grade``) runs the real pipeline against the dev graph and grades it.
"""

from __future__ import annotations

from dataclasses import dataclass

# Axis weights (sum to 1.0). POI recall and beat overlap dominate — they are
# what "reproduces the human tour" most directly; spine and validation are
# structural guards.
W_POI_RECALL = 0.40
W_BEAT_OVERLAP = 0.30
W_SPINE_MATCH = 0.20
W_VALIDATION = 0.10

# A generated tour must grade at or above this to pass. Calibrated 2026-06-12
# against the live corpus (measured, not estimated): Île one-way 90min grades
# 0.86, PdV round-trip 60min grades 0.90 — baseline 0.65 leaves ~0.2 margin
# while catching a real regression (lost POIs/spine/beats grade well below it).
GRADE_BASELINE = 0.65


@dataclass(frozen=True)
class GradeResult:
    poi_recall: float
    beat_overlap: float
    spine_match: float
    validation: float
    score: float
    passed: bool

    def breakdown(self) -> str:
        return (
            f"score={self.score:.3f} "
            f"(poi_recall={self.poi_recall:.2f} beat_overlap={self.beat_overlap:.2f} "
            f"spine={self.spine_match:.0f} validation={self.validation:.0f}) "
            f"{'PASS' if self.passed else 'FAIL'} @ baseline {GRADE_BASELINE}"
        )


def _recall(expected: set[str], got: set[str]) -> float:
    """|expected ∩ got| / |expected|; 1.0 when nothing is expected."""
    if not expected:
        return 1.0
    return len(expected & got) / len(expected)


def grade_tour(
    *,
    generated_poi_names: list[str],
    generated_beat_ids: list[str],
    generated_spine_area: str | None,
    validation_passed: bool,
    fixture: dict,
    baseline: float = GRADE_BASELINE,
) -> GradeResult:
    """Score a generated tour against a golden ``fixture`` dict.

    Reads the fixture's ``expected_pois``/``expected_beat_ids``/
    ``expected_spine_area``; the engine output is passed in (the caller runs
    the pipeline), so this stays pure and unit-testable.
    """
    poi_recall = _recall(set(fixture.get("expected_pois", [])), set(generated_poi_names))
    beat_overlap = _recall(set(fixture.get("expected_beat_ids", [])), set(generated_beat_ids))
    spine_match = (
        1.0 if generated_spine_area == fixture.get("expected_spine_area") else 0.0
    )
    validation = 1.0 if validation_passed else 0.0

    score = (
        W_POI_RECALL * poi_recall
        + W_BEAT_OVERLAP * beat_overlap
        + W_SPINE_MATCH * spine_match
        + W_VALIDATION * validation
    )
    return GradeResult(
        poi_recall=poi_recall,
        beat_overlap=beat_overlap,
        spine_match=spine_match,
        validation=validation,
        score=score,
        passed=score >= baseline,
    )
