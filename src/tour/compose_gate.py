"""COMPOSE → VERIFY → recompose-once → serve-or-block (§2.5/§2.6, M7).

The gate between a generated Script and audio/serving. A failing
ValidationReport blocks audio; the engine does EXACTLY ONE bounded
recompose (re-run COMPOSE with the failing report in hand); still failing
→ refuse the flavour (raise). This is pure control flow over two injected
callables, so it is exercised end-to-end with deterministic stubs — no LLM.

``verify`` merges all four checks into one report: validation.validate_script
(traceability + forbidden) + verify.verify_provenance (rapidfuzz) +
verify.verify_faithfulness (entailment). Build it with ``build_full_verifier``.
"""

from __future__ import annotations

from collections.abc import Callable

from .contract import BeatRef, BeatSequence, Script, ValidationReport
from .validation import validate_script
from .verify import (
    FaithfulnessChecker,
    MockFaithfulnessChecker,
    verify_faithfulness,
    verify_provenance,
)

# Initial compose + exactly one bounded recompose (§2.6 "one bounded recompose").
MAX_COMPOSE_ATTEMPTS = 2

# compose(attempt, prev_report) -> Script ; verify(script) -> ValidationReport
ComposeFn = Callable[[int, ValidationReport | None], Script]
VerifyFn = Callable[[Script], ValidationReport]


class ComposeVerificationError(Exception):
    """Raised when a Script still fails VERIFY after the bounded recompose.

    Carries the final report and the attempt count so the caller can surface
    why the flavour was refused.
    """

    def __init__(self, report: ValidationReport, attempts: int):
        self.report = report
        self.attempts = attempts
        super().__init__(
            f"Script failed VERIFY after {attempts} compose attempt(s): "
            f"{len(report.untraceable_sentences)} untraceable, "
            f"{len(report.forbidden_phrase_hits)} forbidden, "
            f"{len(report.provenance_failures)} provenance, "
            f"{len(report.faithfulness_failures)} faithfulness"
        )


def compose_and_verify(
    compose: ComposeFn,
    verify: VerifyFn,
    *,
    max_attempts: int = MAX_COMPOSE_ATTEMPTS,
) -> Script:
    """Return the first Script whose merged report passes (with that report
    attached); raise ``ComposeVerificationError`` after ``max_attempts``.

    ``compose`` is called with (attempt_number, previous_failing_report) so a
    recompose can steer away from the prior failure; ``verify`` produces the
    merged ValidationReport.
    """
    prev: ValidationReport | None = None
    for attempt in range(1, max_attempts + 1):
        script = compose(attempt, prev)
        report = verify(script)
        if report.passed:
            return script.model_copy(update={"validation": report})
        prev = report
    assert prev is not None
    raise ComposeVerificationError(prev, max_attempts)


def serve_or_block(
    compose: ComposeFn,
    verify: VerifyFn,
    on_serve: Callable[[Script], object],
    *,
    max_attempts: int = MAX_COMPOSE_ATTEMPTS,
) -> Script:
    """Run the gate and call ``on_serve`` (e.g. audio generation) EXACTLY
    once iff a verified Script is produced. If the gate blocks, ``on_serve``
    is never called and ``ComposeVerificationError`` propagates."""
    script = compose_and_verify(compose, verify, max_attempts=max_attempts)
    on_serve(script)
    return script


def build_full_verifier(
    beat_sequence: BeatSequence,
    beats_by_id: dict[str, BeatRef],
    *,
    chunk_text_by_slug: dict[str, str] | None = None,
    faithfulness_checker: FaithfulnessChecker | None = None,
) -> VerifyFn:
    """A ``verify(script)`` that merges all four VERIFY checks into one report.

    ``chunk_text_by_slug`` empty → provenance is a no-op (corpus not
    backfilled); ``faithfulness_checker`` None → the offline Mock (trusts the
    corpus). Both keep the gate runnable and ``make test`` offline.
    """
    checker = faithfulness_checker or MockFaithfulnessChecker()
    chunks = chunk_text_by_slug or {}

    def verify(script: Script) -> ValidationReport:
        base = validate_script(script, beat_sequence)
        return base.model_copy(
            update={
                "provenance_failures": tuple(verify_provenance(beat_sequence, chunks)),
                "faithfulness_failures": tuple(
                    verify_faithfulness(script, beats_by_id, checker)
                ),
            }
        )

    return verify
