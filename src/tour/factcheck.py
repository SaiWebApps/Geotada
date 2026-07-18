"""Semantic fact-checker for tour narration — the ROBUST, fully model-based replacement
for the refuted lexical coverage gate. NO regex, NO word-lists, NO string-overlap: every
judgement is an entailment call (see specs/2026-07-16-tour-craft/FACTCHECK-DESIGN.md,
grounded in FActScore / VeriScore / QuestEval / MiniCheck / TRUE).

Given a stop's composed NARRATION (free prose) and its KNOWN source FACTS (the cited
beats' key_claims + verbatim body sentences — closed-book, the evidence is the beats),
it emits a repair signal:

    FactCheckResult(unsupported_claims=[...], missing_facts=[...])

- FAITHFULNESS (output -> source): decompose the narration into atomic CHECKWORTHY
  claims, then entail each against the source facts. A claim the facts don't support is
  an invention/distortion.
- COVERAGE (source -> output): entail each source fact against the whole narration. A
  fact the narration doesn't convey was dropped.

Both directions are the SAME primitive (``FaithfulnessChecker.entails``) with premise and
hypothesis roles swapped. The only new model call is decomposing the narration, and only
CHECKWORTHY facts are extracted — evocative/second-person/opinion framing yields ZERO
claims, so legitimate narration voice is never flagged as hallucination. The checker is
an ADVISORY gate with a deterministic grounded floor downstream (surgical splice / stitch
revert), never treated as an oracle.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Protocol

from .generation import split_sentences
from .verify import FAITHFULNESS_MODEL, FaithfulnessChecker

_MAX_WORKERS = 8


@dataclass(frozen=True)
class FactCheckResult:
    """The repair signal. ``unsupported_claims`` = atomic narration claims NOT entailed by
    the source facts (invention/distortion). ``missing_facts`` = source facts NOT conveyed
    by the narration (omission). Empty + empty = the narration is faithful and complete."""

    unsupported_claims: tuple[str, ...]
    missing_facts: tuple[str, ...]

    def passed(self) -> bool:
        return not self.unsupported_claims and not self.missing_facts


class ClaimDecomposer(Protocol):
    """Splits a narration into atomic, CHECKWORTHY factual claims (evocative/opinion/
    second-person framing excluded). The one genuinely new model call in the pipeline."""

    def decompose(self, narration: str) -> tuple[str, ...]: ...


# --- the decomposition prompt (VeriScore checkworthy-only, CoT-then-JSON) ---
_DECOMPOSE_SYSTEM = (
    "You split a walking-tour narration into its ATOMIC, CHECKWORTHY factual claims. A "
    "claim states EXACTLY ONE verifiable fact (one date, person, place, measure, or "
    "relationship) and stands alone — resolve every 'it/there/this/he/she' to the named "
    "subject. EXCLUDE, always: second-person address ('you stand here'), sensory or "
    "imaginative framing ('imagine what carried across the water', 'picture the crowds'), "
    "opinions, mood, and rhetorical questions — these are narration craft, NOT facts to "
    "check, and must yield no claim. Do NOT split a compound fact that loses meaning when "
    "split. Keep each claim FAITHFUL to what the narration actually said — never ADD, "
    "STRENGTHEN, or WEAKEN a qualifier of time, place, scope, or degree the narration did "
    "not state (write 'the kings never returned to the island', NOT 'did not return after "
    "this period'; write 'the bell was forged in 1685', NOT 'the bell, one of Europe's "
    "oldest, was forged around 1685'). First, in a 'reasoning' field, walk the narration "
    "and mark each span factual-versus-framing; THEN list the atomic claims."
)
_DECOMPOSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "reasoning": {"type": "string"},
        "claims": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["reasoning", "claims"],
}


class HaikuClaimDecomposer:
    """Real Haiku decomposition (deterministic: temp=0). Defers the anthropic import so
    unit tests never need the SDK; only constructed on the live path."""

    def __init__(self, model: str = FAITHFULNESS_MODEL, *, client: object = None) -> None:
        if client is None:
            import anthropic

            client = anthropic.Anthropic()
        self._client = client
        self.model = model
        self.calls = 0

    def decompose(self, narration: str) -> tuple[str, ...]:
        if not narration.strip():
            return ()
        self.calls += 1
        resp = self._client.messages.create(  # type: ignore[attr-defined]
            model=self.model,
            max_tokens=2048,
            temperature=0,
            system=_DECOMPOSE_SYSTEM,
            output_config={"format": {"type": "json_schema", "schema": _DECOMPOSE_SCHEMA}},
            messages=[{"role": "user", "content": narration}],
        )
        text = "".join(
            getattr(b, "text", "") for b in (getattr(resp, "content", []) or [])
        ).strip()
        if not text:
            return ()
        try:
            claims = json.loads(text).get("claims", [])
        except (json.JSONDecodeError, AttributeError):
            return ()  # malformed/truncated -> no claims (fail-open; coverage still runs)
        return tuple(c.strip() for c in claims if isinstance(c, str) and c.strip())


class SemanticFactChecker:
    """Bidirectional entailment fact-check on top of an ``entails`` primitive + a
    decomposer. Pure orchestration — the intelligence is in the injected models, so this
    class is fully testable offline with a substring-entailment fake + a rule decomposer."""

    def __init__(self, entailer: FaithfulnessChecker, decomposer: ClaimDecomposer) -> None:
        self._entail = entailer
        self._decompose = decomposer

    def check(self, narration_text: str, source_facts: tuple[str, ...]) -> FactCheckResult:
        claims = self._decompose.decompose(narration_text)
        narration_sents = tuple(
            s for s in (p.strip() for p in split_sentences(narration_text)) if s
        )
        # FAITHFULNESS: is each narration claim supported by the source facts?
        # COVERAGE: is each source fact conveyed by the whole narration?
        # Both are the SAME entails(premise, hypothesis) with roles swapped; run all the
        # independent calls concurrently (they are pure YES/NO lookups).
        jobs: list[tuple[str, str]] = [("F", c) for c in claims] + [("C", f) for f in source_facts]
        if not jobs:
            return FactCheckResult((), ())

        def _run(job: tuple[str, str]) -> tuple[str, str, bool]:
            kind, item = job
            if kind == "F":
                ok = self._entail.entails(source_facts, item)
            else:
                ok = self._entail.entails(narration_sents, item)
            return kind, item, ok

        with ThreadPoolExecutor(max_workers=max(1, min(_MAX_WORKERS, len(jobs)))) as pool:
            verdicts = list(pool.map(_run, jobs))

        unsupported = tuple(item for kind, item, ok in verdicts if kind == "F" and not ok)
        missing = tuple(item for kind, item, ok in verdicts if kind == "C" and not ok)
        return FactCheckResult(unsupported_claims=unsupported, missing_facts=missing)


__all__ = [
    "ClaimDecomposer",
    "FactCheckResult",
    "HaikuClaimDecomposer",
    "SemanticFactChecker",
]
