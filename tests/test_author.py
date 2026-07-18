"""The AUTHOR ENGINE loop (src/tour/author.py): draft -> semantic fact-check -> repair,
bounded, with a grounded-stitch floor. Proven offline ($0) with the deterministic
substring-entailment checker: a dropped fact triggers a repair that RESTORES it; an
invented fact is STRIPPED; and if the drafter never converges, the stop falls back to the
fact-complete stitch — so fidelity is guaranteed while the author's flow is preferred.
"""

from __future__ import annotations

from src.tour.author import author_compose_stop
from src.tour.factcheck import SemanticFactChecker
from src.tour.generation import split_sentences


class _SubstringEntailer:
    def entails(self, key_claims: tuple[str, ...], sentence_text: str) -> bool:
        return sentence_text.strip().lower().rstrip(".") in " ".join(key_claims).lower()


class _RuleDecomposer:
    _FRAMING = ("imagine", "picture", "you ", "you're", "you'll", "look ", "notice ")

    def decompose(self, narration: str) -> tuple[str, ...]:
        out = []
        for s in (p.strip() for p in split_sentences(narration)):
            low = s.lower()
            if s and not low.endswith("?") and not low.startswith(self._FRAMING):
                out.append(s)
        return tuple(out)


def _checker() -> SemanticFactChecker:
    return SemanticFactChecker(entailer=_SubstringEntailer(), decomposer=_RuleDecomposer())


class _MockDrafter:
    """Returns ``write_out`` first, then ``rewrite_out`` on each rewrite. Records counts."""

    def __init__(self, write_out: str, rewrite_out: str) -> None:
        self._w, self._r = write_out, rewrite_out
        self.writes = self.rewrites = 0

    def write(self, facts, poi, lens):
        self.writes += 1
        return self._w

    def rewrite(self, facts, draft, result, poi, lens):
        self.rewrites += 1
        return self._r


_FACTS = ("the tower was built in 1250", "the bell weighs thirteen tons")
_STITCH = "The tower was built in 1250. The bell weighs thirteen tons."


def test_repair_restores_a_dropped_fact():
    """The author drops the bell fact on the first draft; the fact-check flags it missing;
    the rewrite restores it -> the loop converges WITHOUT the grounded fallback."""
    drafter = _MockDrafter(
        write_out="The tower was built in 1250.",  # bell fact dropped
        rewrite_out="The tower was built in 1250. The bell weighs thirteen tons.",  # restored
    )
    r = author_compose_stop(_FACTS, "Tower", "dark_history", drafter=drafter,
                            checker=_checker(), stitch_fallback=_STITCH)
    assert r.result.passed()
    assert not r.grounded_fallback
    assert drafter.rewrites == 1
    assert "thirteen tons" in r.text.lower()


def test_repair_strips_an_invented_fact():
    """An invented claim is flagged unsupported and removed on rewrite; loop converges."""
    drafter = _MockDrafter(
        write_out="The tower was built in 1250. The bell weighs thirteen tons. "
        "A dragon lives inside.",
        rewrite_out="The tower was built in 1250. The bell weighs thirteen tons.",
    )
    r = author_compose_stop(_FACTS, "Tower", "dark_history", drafter=drafter,
                            checker=_checker(), stitch_fallback=_STITCH)
    assert r.result.passed() and not r.grounded_fallback
    assert "dragon" not in r.text.lower()


def test_falls_back_to_grounded_stitch_when_repair_never_converges():
    """If the drafter keeps dropping the fact through all repairs, the stop falls back to
    the fact-complete grounded stitch — fidelity guaranteed, termination guaranteed."""
    drafter = _MockDrafter(
        write_out="The tower was built in 1250.",  # always drops the bell
        rewrite_out="The tower was built in 1250.",  # rewrite never restores it
    )
    r = author_compose_stop(_FACTS, "Tower", "dark_history", drafter=drafter,
                            checker=_checker(), stitch_fallback=_STITCH, max_repairs=2)
    assert r.grounded_fallback
    assert r.result.passed()  # the stitch is fact-complete
    assert r.text == _STITCH
    assert drafter.rewrites == 2  # exhausted the bound before falling back


def test_clean_first_draft_needs_no_repair():
    drafter = _MockDrafter(write_out=_STITCH, rewrite_out=_STITCH)
    r = author_compose_stop(_FACTS, "Tower", "dark_history", drafter=drafter,
                            checker=_checker(), stitch_fallback=_STITCH)
    assert r.result.passed() and not r.grounded_fallback
    assert r.attempts == 1 and drafter.rewrites == 0
