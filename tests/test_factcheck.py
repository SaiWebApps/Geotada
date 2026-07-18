"""The SEMANTIC fact-checker (src/tour/factcheck.py) — the model-based replacement for
the refuted lexical coverage gate. Runs the WHOLE orchestration end-to-end offline with
a deterministic substring-entailment fake + a rule decomposer (no LLM, no spend), so the
bidirectional logic is exercised for real, not mocked away.

The properties that matter: an INVENTED claim lands in unsupported_claims (faithfulness);
a DROPPED fact lands in missing_facts (coverage); a faithful+complete narration is empty+
empty; and evocative/second-person framing yields NO claims (so legitimate voice is never
flagged). All $0.
"""

from __future__ import annotations

from src.tour.factcheck import FactCheckResult, SemanticFactChecker
from src.tour.generation import split_sentences


class _SubstringEntailer:
    """Deterministic stand-in for the Haiku entailment head, BOTH directions: the
    hypothesis is 'entailed' iff its normalized text appears in the joined premise. Not a
    realistic paraphrase model — it exercises the checker's orchestration deterministically
    (the real head is HaikuFaithfulnessChecker)."""

    def entails(self, key_claims: tuple[str, ...], sentence_text: str) -> bool:
        premise = " ".join(key_claims).lower()
        return sentence_text.strip().lower().rstrip(".") in premise


class _RuleDecomposer:
    """Deterministic stand-in for the Haiku decomposer: split into sentences and drop
    evocative / second-person / rhetorical-question framing (the checkworthy filter), so
    only fact-bearing sentences become claims."""

    _FRAMING = ("imagine", "picture", "you ", "you're", "you'll", "look ", "notice ")

    def decompose(self, narration: str) -> tuple[str, ...]:
        out = []
        for s in (p.strip() for p in split_sentences(narration)):
            low = s.lower()
            if not s or low.endswith("?") or low.startswith(self._FRAMING):
                continue
            out.append(s)
        return tuple(out)


def _checker() -> SemanticFactChecker:
    return SemanticFactChecker(entailer=_SubstringEntailer(), decomposer=_RuleDecomposer())


_FACTS = (
    "the cathedral was founded in 1163",
    "distances are measured from charing cross",
)


def test_faithful_and_complete_narration_passes():
    narration = ("The cathedral was founded in 1163. "
                 "Distances are measured from Charing Cross.")
    r = _checker().check(narration, _FACTS)
    assert r.passed(), r


def test_dropped_fact_is_caught_as_missing():
    """Coverage: a narration that OMITS a source fact must surface it in missing_facts —
    the exact within-narration drop the lexical 0.34-overlap gate passed (Charing Cross).
    UNDO: remove the coverage ('C') direction from SemanticFactChecker.check -> the drop
    is no longer caught -> RED."""
    narration = "The cathedral was founded in 1163."  # Charing Cross dropped
    r = _checker().check(narration, _FACTS)
    assert any("charing cross" in f for f in r.missing_facts), r
    assert not r.unsupported_claims, r  # nothing invented


def test_invented_claim_is_caught_as_unsupported():
    """Faithfulness: a narration claim the source facts don't support must land in
    unsupported_claims. UNDO: remove the faithfulness ('F') direction from
    SemanticFactChecker.check -> the invention is no longer caught -> RED."""
    narration = ("The cathedral was founded in 1163. "
                 "Distances are measured from Charing Cross. "
                 "The spire is five hundred feet tall.")  # invented
    r = _checker().check(narration, _FACTS)
    assert any("spire" in c.lower() for c in r.unsupported_claims), r


def test_evocative_framing_yields_no_false_unsupported():
    """The single most important property: evocative / second-person / imaginative framing
    is NARRATION CRAFT, not a fact — it must yield ZERO claims, so it is never flagged as
    hallucination. This is the semantic answer to the banned 'imagine' word-ban."""
    narration = ("The cathedral was founded in 1163. "
                 "Distances are measured from Charing Cross. "
                 "Imagine the medieval crowds pressing through the gate. "
                 "You can almost hear them.")
    r = _checker().check(narration, _FACTS)
    assert r.passed(), r  # both facts present, and the framing produced no unsupported claim


def test_partition_is_total_over_claims_and_facts():
    """Every source fact is judged covered-or-missing; every checkworthy claim is judged
    supported-or-unsupported. No item silently dropped."""
    narration = ("The cathedral was founded in 1163. "
                 "The spire is five hundred feet tall.")  # 1 supported, 1 invented; 1 fact missing
    dec = _RuleDecomposer()
    claims = dec.decompose(narration)
    r = _checker().check(narration, _FACTS)
    # every claim accounted for (supported xor unsupported)
    supported = [c for c in claims if c not in r.unsupported_claims]
    assert len(supported) + len(r.unsupported_claims) == len(claims)
    # every fact accounted for (covered xor missing)
    covered = [f for f in _FACTS if f not in r.missing_facts]
    assert len(covered) + len(r.missing_facts) == len(_FACTS)


def test_empty_when_no_claims_and_no_facts():
    assert _checker().check("You are standing here.", ()) == FactCheckResult((), ())
