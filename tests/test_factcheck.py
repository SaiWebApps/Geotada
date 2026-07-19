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

import types

from src.tour.factcheck import (
    FactCheckResult,
    HaikuFaithfulnessJudge,
    SemanticFactChecker,
)
from src.tour.generation import split_sentences


def _fake_haiku(reply: str):
    """A stand-in anthropic client that records the last request and returns ``reply`` as the
    model's text — lets us exercise HaikuFaithfulnessJudge's prompt-formatting + verdict
    parsing offline (no SDK, no network, no spend)."""
    box: dict = {}

    def create(**kw):
        box["kw"] = kw
        return types.SimpleNamespace(content=[types.SimpleNamespace(text=reply)])

    return types.SimpleNamespace(messages=types.SimpleNamespace(create=create)), box


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


class _ParaphraseCoverageJudge:
    """Fake CoverageJudge: paraphrase-tolerant (always 'conveyed'), and records every
    (fact, narration) call so we can prove the coverage direction routed THROUGH it and
    not through the strict entailer."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def conveys(self, fact: str, narration: str) -> bool:
        self.calls.append((fact, narration))
        return True


# A paraphrase the STRICT substring entailer rejects but a real listener plainly learns —
# the exact shape (negation reworded) that false-negatived at 62% and blocked convergence.
_PARAPHRASE_FACT = ("the kings of france never returned to the island",)
_PARAPHRASE_NARRATION = "No king of France ever came back to this island again."


def test_injected_coverage_judge_routes_coverage_and_accepts_paraphrase():
    """The coverage direction must use the injected CoverageJudge, NOT the strict entailer.
    The judge is called once, with the SOURCE FACT and the WHOLE narration, and its verdict
    controls missing_facts — so a paraphrase the entailer would reject is NOT flagged
    missing. This is the author-engine convergence fix.
    UNDO: drop the `elif self._coverage is not None` branch in check() (route coverage back
    through the entailer) -> the paraphrase is wrongly flagged missing -> RED."""
    judge = _ParaphraseCoverageJudge()
    checker = SemanticFactChecker(
        entailer=_SubstringEntailer(), decomposer=_RuleDecomposer(), coverage_judge=judge
    )
    r = checker.check(_PARAPHRASE_NARRATION, _PARAPHRASE_FACT)
    assert len(judge.calls) == 1, judge.calls
    called_fact, called_narration = judge.calls[0]
    assert called_fact == _PARAPHRASE_FACT[0]
    assert "came back to this island" in called_narration  # the WHOLE narration, not a fact
    assert _PARAPHRASE_FACT[0] not in r.missing_facts, r  # judge accepted the paraphrase


def test_coverage_falls_back_to_entailer_without_judge():
    """Backward-compat + proves the fix IS the judge: with no coverage_judge injected, the
    SAME paraphrase is flagged missing by the strict substring entailer (the pre-fix
    behavior the offline substring-fake tests rely on)."""
    r = SemanticFactChecker(
        entailer=_SubstringEntailer(), decomposer=_RuleDecomposer()
    ).check(_PARAPHRASE_NARRATION, _PARAPHRASE_FACT)
    assert _PARAPHRASE_FACT[0] in r.missing_facts, r


def test_faithfulness_judge_formats_prompt_and_parses_verdict():
    """HaikuFaithfulnessJudge conforms to the FaithfulnessChecker protocol: it renders the
    key_claims as a bulleted {facts} block and the sentence as {claim}, and maps YES->True /
    anything-else->False. Exercised with a fake client (no SDK/network/spend)."""
    client, box = _fake_haiku("YES")
    judge = HaikuFaithfulnessJudge(client=client)
    assert judge.entails(("the bell weighs thirteen tons",), "The bell weighs thirteen tons.")
    assert judge.calls == 1
    sent = box["kw"]["messages"][0]["content"]
    assert "- the bell weighs thirteen tons" in sent  # facts bulleted
    assert "The bell weighs thirteen tons." in sent  # claim substituted
    assert "{facts}" not in sent and "{claim}" not in sent  # template fully resolved

    no_client, _ = _fake_haiku("NO")
    assert not HaikuFaithfulnessJudge(client=no_client).entails(("x",), "The bell is bronze.")


def test_faithfulness_judge_fails_closed_on_empty_input():
    """No claim or no facts -> False WITHOUT a model call (nothing to entail, and a bare YES
    must never pass an empty check)."""
    client, box = _fake_haiku("YES")
    judge = HaikuFaithfulnessJudge(client=client)
    assert not judge.entails((), "some claim")
    assert not judge.entails(("a fact",), "   ")
    assert judge.calls == 0 and "kw" not in box  # never called the model


# --- full-corpus RECHECK + EXCISION primitives (2026-07-18, PHASE-C tour-killer fix) ---


class _StrictNoEntailer:
    """Always says NO — the strict faithfulness head, for pinning which primitive
    ``unsupported_against`` must route through."""

    def entails(self, key_claims: tuple[str, ...], sentence_text: str) -> bool:
        return False


class _AlwaysYesCoverageJudge:
    """Always says the fact IS conveyed — records every call so a test can prove
    ``unsupported_against`` never touches it."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def conveys(self, fact: str, narration: str) -> bool:
        self.calls.append((fact, narration))
        return True


def test_unsupported_against_uses_the_strict_entailer_not_the_coverage_judge():
    """The FULL-CORPUS RECHECK primitive must route through the STRICT entailer, NEVER the
    paraphrase-tolerant coverage judge — using coverage here would rubber-stamp exactly the
    overstatement/mis-attribution the strict judge exists to reject. Build a checker whose
    entailer says NO and whose coverage judge says YES to everything: if
    ``unsupported_against`` still reports the claim as unsupported, it proves the strict
    path was used.
    UNDO: swap the implementation to ``self._coverage.conveys(claim, ' '.join(facts))`` (or
    any coverage-judge route) -> the always-YES coverage judge rescues the claim ->
    ``unsupported_against`` returns () -> RED."""
    coverage = _AlwaysYesCoverageJudge()
    checker = SemanticFactChecker(
        entailer=_StrictNoEntailer(), decomposer=_RuleDecomposer(), coverage_judge=coverage
    )
    still = checker.unsupported_against(("a claim",), ("some fact",))
    assert still == ("a claim",), still
    assert coverage.calls == []  # the coverage judge was NEVER consulted


def test_unsupported_against_empty_claims_returns_empty_without_calling_entailer():
    class _RaisingEntailer:
        def entails(self, key_claims, sentence_text):
            raise AssertionError("must not be called for an empty claim tuple")

    checker = SemanticFactChecker(entailer=_RaisingEntailer(), decomposer=_RuleDecomposer())
    assert checker.unsupported_against((), ("some fact",)) == ()


def test_locate_maps_a_claim_to_only_the_sentence_that_conveys_it():
    """EXCISION's attribution primitive: with a coverage judge injected, ``locate`` must
    call ``conveys(claim, sentence)`` per (claim, sentence) pair and return the INDICES of
    the sentences that convey each claim — not a blob-level or substring match.
    UNDO: pass the WHOLE joined narration instead of one ``sentence`` per call -> every
    claim maps to every sentence index -> this test's exact-index assertion goes RED."""

    class _ExactMatchCoverageJudge:
        def conveys(self, fact: str, narration: str) -> bool:
            return fact.strip().lower() in narration.strip().lower()

    checker = SemanticFactChecker(
        entailer=_SubstringEntailer(),
        decomposer=_RuleDecomposer(),
        coverage_judge=_ExactMatchCoverageJudge(),
    )
    sentences = (
        "The tower was built in 1250.",
        "A dragon lives inside.",
        "The bell weighs thirteen tons.",
    )
    located = checker.locate(("dragon lives inside",), sentences)
    assert located == {"dragon lives inside": (1,)}, located


def test_locate_falls_back_to_the_entailer_without_a_coverage_judge():
    """Backward-compat: with no coverage_judge injected, ``locate`` falls back to
    ``self._entail.entails((sentence,), claim)`` per sentence — the offline substring-fake
    path (mirrors ``test_coverage_falls_back_to_entailer_without_judge``)."""
    checker = _checker()  # no coverage_judge
    sentences = ("The tower was built in 1250.", "The bell weighs thirteen tons.")
    located = checker.locate(("the bell weighs thirteen tons",), sentences)
    assert located == {"the bell weighs thirteen tons": (1,)}, located


def test_locate_returns_the_empty_tuple_for_a_claim_no_sentence_conveys():
    """A claim that matches NO sentence (the decomposer's cross-sentence-merge shape) maps
    to ``()`` — the caller's signal to ABORT excision, never a fuzzy guess."""
    checker = _checker()
    sentences = ("The tower was built in 1250.", "The bell weighs thirteen tons.")
    located = checker.locate(("a dragon lives inside",), sentences)
    assert located == {"a dragon lives inside": ()}, located
