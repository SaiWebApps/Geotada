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

from collections import defaultdict
from collections.abc import Callable

from .claim_dedup import verify_claim_coverage
from .contract import BeatRef, BeatSequence, Script, Sentence, ValidationReport
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
            f"{len(report.faithfulness_failures)} faithfulness, "
            f"{len(report.coverage_failures)} coverage"
        )


def drop_failing_sentences(script: Script, report: ValidationReport) -> Script:
    """Remove ONLY the individual sentences VERIFY flagged (unfaithful, untraceable,
    or forbidden), keeping the rest of the stop's fusion. The finest-grained
    repair: a stop whose one bad sentence is an embellished reflection keeps all
    its fused beat prose. Dropping a fact-carrying sentence may then leave a claim
    uncovered — the caller falls back to a whole-stop revert for that residue."""
    keys: set[tuple[int, str, str]] = set()
    for s, _reason in report.faithfulness_failures:
        keys.add((s.stop_idx, s.source_id, s.text))
    for s in report.untraceable_sentences:
        keys.add((s.stop_idx, s.source_id, s.text))
    for s, _code in report.forbidden_phrase_hits:
        keys.add((s.stop_idx, s.source_id, s.text))
    if not keys:
        return script
    kept = tuple(s for s in script.script if (s.stop_idx, s.source_id, s.text) not in keys)
    return script.model_copy(update={"script": kept})


def _bad_stops(report: ValidationReport, stitched: Script) -> set[int]:
    """Stop indices whose composed narration failed VERIFY — an unfaithful,
    forbidden, or untraceable sentence, or a beat that dropped a fact."""
    bad: set[int] = set()
    for s in report.untraceable_sentences:
        bad.add(s.stop_idx)
    for s, _code in report.forbidden_phrase_hits:
        bad.add(s.stop_idx)
    for s, _code in report.faithfulness_failures:
        bad.add(s.stop_idx)
    beat_stop = {s.source_id: s.stop_idx for s in stitched.script if s.source_type == "beat"}
    for beat_id, _claim in report.coverage_failures:
        if beat_id in beat_stop:
            bad.add(beat_stop[beat_id])
    return bad


def repair_composed(composed: Script, stitched: Script, report: ValidationReport) -> Script:
    """Per-stop graceful repair: revert ONLY the stops that failed VERIFY to their
    grounded STITCHED narration, keeping the composed (fused) narration for every
    stop that passed. A reverted stop restores every fact and drops any embellished
    reflection, so the result is faithful AND loses nothing — the honest middle
    between refusing the whole tour and shipping unverified prose."""
    bad = _bad_stops(report, stitched)
    if not bad:
        return composed
    stitched_by_stop: dict[int, list[Sentence]] = defaultdict(list)
    for s in stitched.script:
        stitched_by_stop[s.stop_idx].append(s)
    composed_by_stop: dict[int, list[Sentence]] = defaultdict(list)
    for s in composed.script:
        composed_by_stop[s.stop_idx].append(s)
    out: list[Sentence] = []
    for stop_idx in sorted(set(stitched_by_stop) | set(composed_by_stop)):
        out.extend(stitched_by_stop[stop_idx] if stop_idx in bad else composed_by_stop[stop_idx])
    return composed.model_copy(update={"script": tuple(out)})


def compose_and_verify(
    compose: ComposeFn,
    verify: VerifyFn,
    *,
    max_attempts: int = MAX_COMPOSE_ATTEMPTS,
    repair: Callable[[Script, ValidationReport], Script] | None = None,
) -> Script:
    """Return the first Script whose merged report passes (with that report
    attached); raise ``ComposeVerificationError`` after ``max_attempts``.

    ``compose`` is called with (attempt_number, previous_failing_report) so a
    recompose can steer away from the prior failure; ``verify`` produces the
    merged ValidationReport. If ``repair`` is given and every attempt fails, it
    is called once with the last failing (script, report) to produce a repaired
    script (e.g. per-stop revert to stitched); if THAT verifies, it is served —
    so a partly-embellished compose still ships its good stops instead of a
    whole-tour refusal.
    """
    prev: ValidationReport | None = None
    last: Script | None = None
    for attempt in range(1, max_attempts + 1):
        script = compose(attempt, prev)
        report = verify(script)
        if report.passed:
            return script.model_copy(update={"validation": report})
        prev = report
        last = script
    assert prev is not None
    if repair is not None and last is not None:
        repaired = repair(last, prev)
        rep_report = verify(repaired)
        if rep_report.passed:
            return repaired.model_copy(update={"validation": rep_report})
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
    expected_claim_ids: set[tuple[str, int]] | None = None,
) -> VerifyFn:
    """A ``verify(script)`` that merges the VERIFY checks into one report.

    ``chunk_text_by_slug`` empty → provenance is a no-op (corpus not
    backfilled); ``faithfulness_checker`` None → the offline Mock (trusts the
    corpus). ``expected_claim_ids`` (from ``claims_realized_by`` on the PRE-compose
    stitch) enables the content-loss / coverage check — omit it and coverage is a
    no-op. All keep the gate runnable and ``make test`` offline.
    """
    checker = faithfulness_checker or MockFaithfulnessChecker()
    chunks = chunk_text_by_slug or {}

    def verify(script: Script) -> ValidationReport:
        base = validate_script(script, beat_sequence)
        # No chunk library loaded -> provenance is a genuine no-op. Since the
        # Step-4.0 backfill, live beats DO carry source_passage/chunk_slug;
        # without this guard every one of them would fail at 0.0 against an
        # empty dict. A missing slug only means something when chunks exist.
        provenance = tuple(verify_provenance(beat_sequence, chunks)) if chunks else ()
        coverage = (
            verify_claim_coverage(script, expected_claim_ids, beats_by_id)
            if expected_claim_ids
            else ()
        )
        return base.model_copy(
            update={
                "provenance_failures": provenance,
                "faithfulness_failures": tuple(
                    verify_faithfulness(script, beats_by_id, checker)
                ),
                "coverage_failures": coverage,
            }
        )

    return verify
