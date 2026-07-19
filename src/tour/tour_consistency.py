"""Cross-stop consistency + dedup — REPORT ONLY (src/tour/tour_consistency.py).

Two live defects the Phase-C acceptance panels caught, both invisible to any PER-STOP
check because they only exist ACROSS stops (specs/2026-07-18-tour-qa-campaign/
PHASE-C-RESULTS.md):

- CONTRADICTION: NYC stop 2 (National Museum of the American Indian) says Broadway "runs
  thirteen miles"; stop 3 (Bowling Green, ~100m away) says "that avenue runs twelve miles".
  Both are faithfully grounded in DIFFERENT corpus beats that disagree with each other
  (Frommer's vs Big Onion) — the defect is in the corpus, not the narration.
- REPEAT: Paris Ile stop 4 (Square du Vert-Galant) mentions in passing that "the Pont Neuf
  ... is the oldest bridge in Paris"; stop 5 (Pont Neuf itself) reveals the SAME fact as its
  headline moment — "yet it's the oldest bridge in Paris". The reveal lands dead because it
  was already said.

This module never rewrites narration and never picks a winner for a contradiction (CLAUDE.md
Pipeline Guardrail #4: never auto-resolve a superlative/factual disagreement) — it PRODUCES a
structured report; a human or a later track decides what, if anything, to change. It never
imports ``author.py`` and never mutates a ``Script``/``Sentence`` — a plain, decoupled
``AuthoredStop`` value object is the only input, so this same code can serve the
``scripts/author_tour.py`` harness today and an assembled ``Script`` later via a one-line
adapter.

COST ARCHITECTURE (load-bearing): the judge is called ONCE PER STOP PAIR — O(S^2) in the
number of STOPS — never once per CLAIM pair. A 6-stop tour is C(6,2)=15 judge calls + 6
decompose calls = 21 total; judging at the claim-pair level instead (the naive reading of
"compare every claim against every other claim") would be ~2,400 claim pairs on a 6-stop tour
with ~12 claims/stop, i.e. ~4,800 Haiku calls — nearly 2500x more, dwarfing the tour's own
compose spend. ``judge.compare`` receives BOTH stops' full claim lists and returns every
issue between them (repeats AND contradictions) in that single call, so no relation requires
a second pass.

Every claim string a judge returns is verified to be an EXACT member of the claim list it was
handed for that stop; anything else (a paraphrase, a claim from the wrong stop) is silently
discarded. This is a provenance/identity check on strings the model was explicitly instructed
to copy verbatim — the same category as this repo's existing traceability checks — NOT a
meaning-level lexical heuristic (the "is this the same fact" / "do these contradict" judgement,
AND "which stop's POI is this fact actually about" for a repeat's keep recommendation, are made
entirely by the injected semantic ``CrossStopJudge`` via its ``owner`` verdict — never by
string/substring matching; see ``_owning_stop_idx``).

Note on the decision primitive: this module does NOT reuse ``FaithfulnessChecker.entails``.
Entailment is not equivalence and its negation is not contradiction — "the bell weighs
thirteen tons" entails "the bell has a weight" without those being the same fact (a false
"repeat" if judged by entailment), and two unrelated claims simply fail to entail each other
in EITHER direction, which would fire a naive non-entailment-implies-contradiction detector on
nearly every cross-stop pair. ``CrossStopJudge`` is a purpose-built protocol for exactly two
questions — "same fact, voiced twice?" and "mutually incompatible?" — still fully
semantic/model-based and dependency-injected, never a lexical/regex shortcut.

UNCALIBRATED JUDGE — flagged explicitly, not hidden: unlike ``factcheck.py``'s coverage and
faithfulness judges (each shipped only after a labeled bake-off), ``HaikuCrossStopJudge``'s
prompt has no measured FP/FN rate yet. Harm is bounded here because the module is
report-only — nothing ships or gets rewritten off an unverified verdict — but a noisy report
would get ignored, so a bake-off is still owed before this feeds any auto-action.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from itertools import combinations
from typing import Protocol

from .factcheck import ClaimDecomposer
from .verify import FAITHFULNESS_MODEL


@dataclass(frozen=True)
class AuthoredStop:
    """One authored stop's served narration — a plain value object, deliberately NOT
    ``contract.Script``, so this module has zero coupling to ``author.py``. ``beat_ids`` are
    the source beat ids the stop cites (empty if unknown); ``grounded_fallback`` marks a
    stitch-floor stop (corpus-verbatim, not rewritable at the narration layer — see
    ``_stitch_note``)."""

    stop_idx: int
    poi: str
    text: str
    grounded_fallback: bool = False
    beat_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class CrossStopIssue:
    """One detected cross-stop issue. ``keep`` is the recommended-survivor stop index for a
    ``repeat`` — decided by the semantic judge's own ``owner`` verdict for the pair (see
    ``_owning_stop_idx``), never by POI-name string matching; always ``None`` for a
    ``contradiction`` — this module never picks a winner between two disagreeing facts."""

    kind: str  # 'repeat' | 'contradiction'
    stop_a: int
    stop_b: int
    claim_a: str
    claim_b: str
    keep: int | None
    rationale: str
    beats_a: tuple[str, ...]
    beats_b: tuple[str, ...]


@dataclass(frozen=True)
class CrossStopReport:
    """``skipped`` is True when there were fewer than 2 stops to compare — a tour that short
    was never actually checked, so ``clean()`` deliberately returns False for it (a caller
    must not read "skipped" as "verified clean", the false-all-clear the ``--stop``
    single-POI validation path would otherwise produce). ``failed_pairs`` counts stop pairs
    where the judge's response could not be parsed (empty or malformed content) — the SAME
    false-all-clear risk as ``skipped``, just per-pair instead of whole-report: a judge parse
    failure must never render as "verified clean" (see ``HaikuCrossStopJudge.compare`` and
    ``cross_stop_report``)."""

    repeats: tuple[CrossStopIssue, ...] = ()
    contradictions: tuple[CrossStopIssue, ...] = ()
    skipped: bool = False
    failed_pairs: int = 0

    def clean(self) -> bool:
        return (
            not self.skipped
            and not self.failed_pairs
            and not self.repeats
            and not self.contradictions
        )

    def issue_count(self) -> int:
        return len(self.repeats) + len(self.contradictions)


class CrossStopJudge(Protocol):
    """Fully semantic/model-based judge over ONE STOP PAIR's claim lists at a time — never a
    lexical/regex heuristic. Returns every issue found between the two stops in a single call
    (both 'repeat' and 'contradiction' relations together), as
    ``(kind, claim_a_verbatim, claim_b_verbatim, rationale, owner)`` tuples. ``claim_a``/
    ``claim_b`` MUST be copied verbatim from the lists they were handed — any that is not an
    exact member of its input list is discarded by the caller (see ``cross_stop_report``).
    ``owner`` is ``'A'``, ``'B'``, or ``'neither'`` — for a ``repeat``, which stop's POI the
    fact is actually ABOUT, decided by the judge itself (never a string match, see
    ``_owning_stop_idx``); meaningless for a ``contradiction`` (always ``'neither'`` there).
    Returns ``None`` — NOT an empty tuple — when the pair could not be judged at all (a
    parse/empty-response failure): an empty tuple means "judged, genuinely no issues"; ``None``
    means "not judged" and must never be read as verified-clean (see ``CrossStopReport.
    failed_pairs``)."""

    def compare(
        self, a_label: str, a_claims: tuple[str, ...], b_label: str, b_claims: tuple[str, ...]
    ) -> tuple[tuple[str, str, str, str, str], ...] | None: ...


def _owning_stop_idx(a_stop_idx: int, b_stop_idx: int, owner: str) -> int:
    """Keep-recommendation for a REPEAT: the stop whose POI the fact is actually ABOUT, not
    keep-first (the ``claim_dedup.py`` precedent, which is wrong here — see module docstring
    and PHASE-C-RESULTS.md: applied to the Pont Neuf/Vert-Galant repeat, keep-first survives
    the throwaway Vert-Galant mention and kills the Pont Neuf headline reveal, the exact
    opposite of what the acceptance panel wants).

    Ownership is decided ENTIRELY by the semantic ``CrossStopJudge``'s own ``owner`` verdict
    for this pair — "which entity is this claim about" is a meaning-level referent-attribution
    judgement, the same category this repo already solves semantically elsewhere (factcheck.py
    ``_FAITHFULNESS_JUDGE_USER`` TEST 1's referent-binding rule), so it is never decided here by
    a POI-name substring/lexical match. A prior version of this function did exactly that and
    was refuted: it silently degraded to keep-first whenever a claim named the POI in a
    different form than the POI's own stored name — a disambiguating suffix, a shortened name,
    or a different Unicode normalization of an accented name — which is common on this corpus.

    Falls back to first-occurrence (``a_stop_idx`` — ``a`` always precedes ``b`` in stop order,
    see ``cross_stop_report``) ONLY when the judge answers ``'neither'`` (indifferent/unclear)
    or returns any other unrecognized value. This fallback is a STRUCTURAL tiebreak (stop index
    order alone) — it never looks at claim or POI text, so it stays outside the banned
    lexical-shortcut category even though it is not itself model-based."""
    if owner == "B":
        return b_stop_idx
    return a_stop_idx  # owner == 'A', 'neither', or unrecognized -> first occurrence (structural)


def _stitch_note(stop_idx: int, stop: AuthoredStop) -> str:
    """Flags a stitch-sourced issue as unfixable at the narration layer (a grounded-stitch
    fallback is corpus-verbatim by construction and cannot be rewritten without breaking the
    fidelity guarantee) — so a reviewer triages it as a corpus/engine issue, not narration
    noise. Empty string for an authored (non-fallback) stop."""
    if not stop.grounded_fallback:
        return ""
    return (
        f" [STOP {stop_idx} IS A GROUNDED-STITCH FALLBACK — its narration is corpus-verbatim "
        "and cannot be rewritten at the narration layer; unfixable here, triage as a corpus/"
        "engine issue instead.]"
    )


def cross_stop_report(
    stops, *, decomposer: ClaimDecomposer, judge: CrossStopJudge
) -> CrossStopReport:
    """Decompose each stop's served text ONCE, then judge every STOP PAIR once (both
    relations in the same call) — see the module docstring's cost architecture. Pure: never
    mutates ``stops`` or any ``AuthoredStop.text``. Fewer than 2 stops is SKIPPED (not
    reported clean — see ``CrossStopReport.skipped``). A pair the judge could not parse
    (``compare`` returns ``None``) is counted in ``failed_pairs``, NOT silently treated as
    zero issues — see ``CrossStopReport.failed_pairs``."""
    ordered = sorted(stops, key=lambda s: s.stop_idx)
    if len(ordered) < 2:
        return CrossStopReport(skipped=True)

    claims_by_idx = {s.stop_idx: decomposer.decompose(s.text) for s in ordered}

    repeats: list[CrossStopIssue] = []
    contradictions: list[CrossStopIssue] = []
    failed_pairs = 0
    for a, b in combinations(ordered, 2):
        a_claims = claims_by_idx[a.stop_idx]
        b_claims = claims_by_idx[b.stop_idx]
        if not a_claims or not b_claims:
            continue  # nothing checkworthy at one side -> nothing to compare, no spend
        result = judge.compare(a.poi, a_claims, b.poi, b_claims)
        if result is None:
            failed_pairs += 1  # judge could not be parsed for this pair -> NOT verified clean
            continue
        for kind, claim_a, claim_b, rationale, owner in result:
            # Hallucinated-pair guard: the judge was instructed to copy claims VERBATIM from
            # the lists it was handed; anything else (a paraphrase, a claim from neither
            # list) is discarded outright rather than reported as citing text no stop said.
            if claim_a not in a_claims or claim_b not in b_claims:
                continue
            note = _stitch_note(a.stop_idx, a) + _stitch_note(b.stop_idx, b)
            if kind == "repeat":
                keep = _owning_stop_idx(a.stop_idx, b.stop_idx, owner)
                repeats.append(
                    CrossStopIssue(
                        kind="repeat", stop_a=a.stop_idx, stop_b=b.stop_idx,
                        claim_a=claim_a, claim_b=claim_b, keep=keep,
                        rationale=rationale + note, beats_a=a.beat_ids, beats_b=b.beat_ids,
                    )
                )
            elif kind == "contradiction":
                # Never pick a winner (CLAUDE.md Pipeline Guardrail #4: never auto-resolve a
                # factual disagreement) — name both source beats so the fix is an actionable
                # corpus repair, not a narration edit.
                contradictions.append(
                    CrossStopIssue(
                        kind="contradiction", stop_a=a.stop_idx, stop_b=b.stop_idx,
                        claim_a=claim_a, claim_b=claim_b, keep=None,
                        rationale=(
                            f"{rationale} — source beats {a.beat_ids or '(none)'} vs "
                            f"{b.beat_ids or '(none)'}; corpus repair required, never "
                            "auto-resolved." + note
                        ),
                        beats_a=a.beat_ids, beats_b=b.beat_ids,
                    )
                )
            # any other kind value is ignored defensively -> a malformed live judge reply
            # never crashes the report, it just contributes nothing.
    return CrossStopReport(
        repeats=tuple(repeats), contradictions=tuple(contradictions), failed_pairs=failed_pairs
    )


def find_cross_stop_repeats(
    stops, *, decomposer: ClaimDecomposer, judge: CrossStopJudge
) -> tuple[CrossStopIssue, ...]:
    """The 'repeat' half of ``cross_stop_report`` (delegates + filters by kind)."""
    return cross_stop_report(stops, decomposer=decomposer, judge=judge).repeats


def find_cross_stop_contradictions(
    stops, *, decomposer: ClaimDecomposer, judge: CrossStopJudge
) -> tuple[CrossStopIssue, ...]:
    """The 'contradiction' half of ``cross_stop_report`` (delegates + filters by kind)."""
    return cross_stop_report(stops, decomposer=decomposer, judge=judge).contradictions


def format_cross_stop_report(report: CrossStopReport) -> str:
    """ALL presentation lives here, so the ``scripts/author_tour.py`` call site stays a
    single ``print(...)`` line."""
    lines = ["CROSS-STOP ISSUES"]
    if report.skipped:
        lines.append("  skipped (<2 stops)")
        return "\n".join(lines)
    if report.clean():
        lines.append("  none")
        return "\n".join(lines)
    if report.failed_pairs:
        lines.append(
            f"  WARNING: {report.failed_pairs} stop pair(s) could not be judged (empty/"
            "malformed judge response) — NOT verified clean, re-run or investigate."
        )
    if report.repeats:
        lines.append(f"  REPEATS ({len(report.repeats)}):")
        for issue in report.repeats:
            keep_note = f"keep stop {issue.keep}" if issue.keep is not None else "keep: n/a"
            lines.append(f"    stop {issue.stop_a} vs stop {issue.stop_b} — {keep_note}")
            lines.append(f"      A: {issue.claim_a}")
            lines.append(f"      B: {issue.claim_b}")
            lines.append(f"      why: {issue.rationale}")
    if report.contradictions:
        lines.append(f"  CONTRADICTIONS ({len(report.contradictions)}):")
        for issue in report.contradictions:
            lines.append(f"    stop {issue.stop_a} vs stop {issue.stop_b} — NO auto-keep")
            lines.append(f"      A: {issue.claim_a}")
            lines.append(f"      B: {issue.claim_b}")
            lines.append(f"      why: {issue.rationale}")
    return "\n".join(lines)


# --- the live judge prompt (report-only; UNCALIBRATED — see module docstring) ---
_CROSS_STOP_JUDGE_SYSTEM = (
    "You compare the CHECKWORTHY claims of TWO stops on the same walking tour and report "
    "only genuine cross-stop issues. Two relations, and only these:\n"
    "REPEAT — the SAME fact is stated in both claim lists (perhaps in different words): the "
    "same subject, the same property/relationship, the same value. A callback that "
    "deliberately restates an earlier fact is STILL a repeat (report it; a human decides "
    "whether the threading was intentional) — but two DIFFERENT facts about the same subject "
    "(e.g. one claim gives a bridge's age-rank, another its building material) are NOT a "
    "repeat.\n"
    "CONTRADICTION — the two claims are about the SAME subject and property but assert "
    "MUTUALLY INCOMPATIBLE values (a different number, date, name, or 'the only/first/"
    "oldest X' claimed for two different things). Two claims that are merely unrelated, or "
    "that entail one another without being the identical fact, are NEITHER a repeat NOR a "
    "contradiction — do not report them.\n"
    "For every REPEAT, also decide owner — which stop's POI the fact is ACTUALLY ABOUT (its "
    "true subject), regardless of which stop's claim text happens to name it, uses a "
    "different form of its name, or names it not at all: answer 'A' or 'B'. If the fact is "
    "not really about either POI specifically, or you genuinely cannot tell, answer "
    "'neither'. For a CONTRADICTION, always set owner to 'neither' — this repo never "
    "auto-resolves a factual disagreement, so ownership does not apply.\n"
    "For every issue you report, COPY claim_a and claim_b VERBATIM, character-for-character, "
    "from the CLAIMS A / CLAIMS B lists you were given — never paraphrase, shorten, or "
    "combine them; a claim you invent or reword cannot be verified and will be discarded. "
    "If you find no genuine repeat or contradiction, return an empty issues list — do not "
    "force a match. Output ONLY the JSON object described by the schema."
)
_CROSS_STOP_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "kind": {"type": "string", "enum": ["repeat", "contradiction"]},
                    "claim_a": {"type": "string"},
                    "claim_b": {"type": "string"},
                    "rationale": {"type": "string"},
                    "owner": {"type": "string", "enum": ["A", "B", "neither"]},
                },
                "required": ["kind", "claim_a", "claim_b", "rationale", "owner"],
            },
        }
    },
    "required": ["issues"],
}


class HaikuCrossStopJudge:
    """Real Haiku cross-stop judgement (deterministic: temp=0, JSON-schema output). Defers
    the anthropic import so unit tests never need the SDK; only constructed on the live path.
    Mirrors ``HaikuCoverageJudge``'s shape (factcheck.py:192-222). UNCALIBRATED — see module
    docstring; report-only, so the bounded blast radius is a noisy (not a harmful) report."""

    def __init__(self, model: str = FAITHFULNESS_MODEL, *, client: object = None) -> None:
        if client is None:
            import anthropic

            client = anthropic.Anthropic()
        self._client = client
        self.model = model
        self.calls = 0

    def compare(
        self, a_label: str, a_claims: tuple[str, ...], b_label: str, b_claims: tuple[str, ...]
    ) -> tuple[tuple[str, str, str, str, str], ...] | None:
        if not a_claims or not b_claims:
            return ()  # nothing checkworthy -> genuinely zero issues, no call made, no spend
        self.calls += 1
        user = (
            f"STOP A — {a_label}\nCLAIMS A:\n- " + "\n- ".join(a_claims)
            + f"\n\nSTOP B — {b_label}\nCLAIMS B:\n- " + "\n- ".join(b_claims)
        )
        resp = self._client.messages.create(  # type: ignore[attr-defined]
            model=self.model,
            max_tokens=1024,
            temperature=0,  # deterministic: a stop-pair verdict must not flip between runs
            system=_CROSS_STOP_JUDGE_SYSTEM,
            output_config={"format": {"type": "json_schema", "schema": _CROSS_STOP_SCHEMA}},
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(
            getattr(b, "text", "") for b in (getattr(resp, "content", []) or [])
        ).strip()
        if not text:
            return None  # empty response -> judge FAILURE, never masquerade as zero issues
        try:
            issues = json.loads(text).get("issues", [])
        except (json.JSONDecodeError, AttributeError):
            return None  # malformed/truncated -> judge FAILURE (see CrossStopReport.failed_pairs)
        out: list[tuple[str, str, str, str, str]] = []
        for it in issues:
            if not isinstance(it, dict):
                continue
            kind, claim_a, claim_b = it.get("kind"), it.get("claim_a"), it.get("claim_b")
            rationale, owner = it.get("rationale"), it.get("owner")
            if (
                kind in ("repeat", "contradiction")
                and isinstance(claim_a, str)
                and isinstance(claim_b, str)
            ):
                rat = rationale if isinstance(rationale, str) else ""
                own = owner if owner in ("A", "B", "neither") else "neither"
                out.append((kind, claim_a, claim_b, rat, own))
        return tuple(out)


__all__ = [
    "AuthoredStop",
    "CrossStopIssue",
    "CrossStopJudge",
    "CrossStopReport",
    "HaikuCrossStopJudge",
    "cross_stop_report",
    "find_cross_stop_contradictions",
    "find_cross_stop_repeats",
    "format_cross_stop_report",
]
