"""The AUTHOR ENGINE loop (src/tour/author.py): draft -> semantic fact-check -> repair,
bounded, with a grounded-stitch floor. Proven offline ($0) with the deterministic
substring-entailment checker: a dropped fact triggers a repair that RESTORES it; an
invented fact is STRIPPED; and if the drafter never converges, the stop falls back to the
fact-complete stitch — so fidelity is guaranteed while the author's flow is preferred.
"""

from __future__ import annotations

import types

from src.tour.author import LLMDrafter, author_compose_script, author_compose_stop
from src.tour.contract import (
    POI,
    BeatRef,
    BeatSequence,
    POIBeats,
    Route,
    TourInput,
    TransitSegment,
)
from src.tour.factcheck import FactCheckResult, SemanticFactChecker
from src.tour.generation import generate, split_sentences


# --- minimal Script/BeatSequence/Route builders for author_compose_script (mirror
# test_tour_compose.py; the stitched Script comes from the REAL generate()) ---
def _poi(pid: str) -> POI:
    return POI(id=pid, name=pid, tier=5, poi_role="stop", lat=48.85, lng=2.36)


def _beat(bid: str, poi_id: str, claim: str) -> BeatRef:
    return BeatRef(id=bid, poi_id=poi_id, script_body=claim,
                   word_count=len(claim.split()), key_claims=(claim,))


def _route_seq_stitched(stops: list[list[BeatRef]]):
    pois = tuple(_poi(f"p{i}") for i in range(len(stops)))
    transits = tuple(
        TransitSegment(from_poi_id=None if i == 0 else pois[i - 1].id, to_poi_id=p.id,
                       distance_m=100.0, walk_seconds=60)
        for i, p in enumerate(pois)
    )
    route = Route(pois=pois, transits=transits, total_walk_distance_m=100.0 * len(pois),
                  total_walk_seconds=60 * len(pois))
    seq = BeatSequence(poi_beats=tuple(
        POIBeats(poi_id=f"p{i}", poi_name=f"p{i}", ordering_strategy="sub_location",
                 beats=tuple(bs))
        for i, bs in enumerate(stops)
    ))
    ti = TourInput(start=(48.85, 2.36), duration_min=60, city_slug="paris")
    return route, seq, generate(seq, route, ti)


def test_money_guard_author_engine_clients_are_offline_stubs_in_suite():
    """MONEY-GUARD: inside the hermetic bar the author engine's FOUR billing clients
    (Opus drafter + 3 Haiku judges) must construct as OFFLINE stubs, never billing SDKs —
    else engine='author' would spend real money on every `make test`.
    UNDO: delete the author-engine arm of `_money_guard_no_live_compose` in conftest ->
    these build the real anthropic clients -> RED (and the bar would bill)."""
    from src.tour.author import LLMDrafter as _Drafter
    from src.tour.factcheck import HaikuClaimDecomposer as _Dec
    from src.tour.factcheck import HaikuCoverageJudge as _Cov
    from src.tour.factcheck import HaikuFaithfulnessJudge as _Faith

    assert type(_Drafter("m")).__name__ == "_OfflineDrafter"
    assert type(_Dec()).__name__ == "_OfflineDecomposer"
    assert type(_Cov()).__name__ == "_TrustingJudge"
    assert type(_Faith()).__name__ == "_TrustingJudge"


class _AlwaysPass:
    def check(self, narration, facts):
        return FactCheckResult((), ())


class _AlwaysFail:
    def check(self, narration, facts):
        return FactCheckResult(("unsupported",), ())


def test_author_compose_script_serves_author_prose_when_a_stop_converges():
    """A converged stop's served beat-sentences are the AUTHOR prose (not the stitch),
    cited to that stop's beats, and grounded_fallback is False for it."""
    route, seq, stitched = _route_seq_stitched([[_beat("b0", "p0", "the tower was built in 1250")]])
    drafter = _MockDrafter(write_out="AUTHORED PROSE about the tower.", rewrite_out="unused")
    script, fell_back = author_compose_script(
        stitched, seq, route, lens="dark_history", drafter=drafter, checker=_AlwaysPass())
    assert fell_back == {0: False}
    beat_sents = [s for s in script.script if s.source_type == "beat" and s.stop_idx == 0]
    assert beat_sents and all(s.source_id == "b0" for s in beat_sents)
    assert "AUTHORED PROSE" in " ".join(s.text for s in beat_sents)  # author prose, not stitch
    assert drafter.writes == 1


def test_author_compose_script_falls_back_to_exact_stitch_when_a_stop_wont_converge():
    """A stop the drafter can't make faithful+complete serves its EXACT grounded stitch,
    never a bad draft; grounded_fallback is True. UNDO: make author_compose_script keep the
    author draft on grounded_fallback -> the fact-dropping draft ships -> RED."""
    route, seq, stitched = _route_seq_stitched([[
        _beat("b0", "p0", "the tower was built in 1250"),
        _beat("b1", "p0", "the bell weighs thirteen tons"),
    ]])
    orig = [s.text for s in stitched.script if s.source_type == "beat" and s.stop_idx == 0]
    drafter = _MockDrafter(write_out="a bad draft that never passes", rewrite_out="still bad")
    script, fell_back = author_compose_script(
        stitched, seq, route, lens="x", drafter=drafter, checker=_AlwaysFail(), max_repairs=2)
    assert fell_back == {0: True}
    served = [s.text for s in script.script if s.source_type == "beat" and s.stop_idx == 0]
    assert served == orig  # exact grounded stitch preserved, not the fact-dropping draft


def _fake_anthropic(*texts: str):
    """A stand-in client that returns ``texts`` in order (one per create call), each as a
    single text block; records each request's kwargs. Lets us exercise LLMDrafter's
    retry-on-empty offline (no SDK, no spend)."""
    calls: list[dict] = []
    seq = list(texts)

    def create(**kw):
        calls.append(kw)
        reply = seq[min(len(calls) - 1, len(seq) - 1)]
        block = types.SimpleNamespace(type="text", text=reply)
        return types.SimpleNamespace(content=[block])

    return types.SimpleNamespace(messages=types.SimpleNamespace(create=create)), calls


def test_llmdrafter_retries_without_thinking_when_first_call_returns_empty():
    """The empty-collapse guard: if adaptive-thinking consumes the budget and returns no
    text, LLMDrafter retries once WITHOUT thinking and returns that prose. UNDO: remove the
    `if not text:` retry -> write() returns '' -> RED."""
    client, calls = _fake_anthropic("", "Recovered prose from the facts.")
    drafter = LLMDrafter("m", client=client)
    out = drafter.write(("a fact",), "Stop", "dark_history")
    assert out == "Recovered prose from the facts."
    assert len(calls) == 2  # first (adaptive) empty, second retry
    assert calls[0].get("thinking") == {"type": "adaptive"}
    assert "thinking" not in calls[1]  # retry drops extended thinking to spend budget on text


def test_llmdrafter_does_not_retry_when_first_call_has_text():
    client, calls = _fake_anthropic("Good prose first time.", "should-not-be-used")
    out = LLMDrafter("m", client=client).write(("a fact",), "Stop", "dark_history")
    assert out == "Good prose first time." and len(calls) == 1


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


class _ScriptedDrafter:
    """Returns ``write_out`` first, then pops ``rewrites`` in order (last value repeats), and
    RECORDS the draft each rewrite was handed (``given_drafts``) — so a test can prove the
    loop rewrites from the BEST draft, not the last."""

    def __init__(self, write_out: str, rewrites: list[str]) -> None:
        self._w, self._rw = write_out, list(rewrites)
        self.writes = self.rewrite_calls = 0
        self.given_drafts: list[str] = []

    def write(self, facts, poi, lens):
        self.writes += 1
        return self._w

    def rewrite(self, facts, draft, result, poi, lens):
        self.given_drafts.append(draft)
        out = self._rw[min(self.rewrite_calls, len(self._rw) - 1)]
        self.rewrite_calls += 1
        return out


def test_each_repair_rewrites_from_the_best_draft_not_the_last():
    """A rewrite that REGRESSES (more failures) must be discarded, and the NEXT repair must
    rewrite from the retained best draft — never from the regression. The write is faithful
    but 1-missing; every rewrite returns a worse draft, so the loop keeps handing the drafter
    the ORIGINAL best draft each time. UNDO: rewrite from `draft` (last) / adopt every
    candidate -> the 2nd rewrite is handed the regressed draft -> given_drafts differ -> RED."""
    best = "The tower was built in 1250."  # 1 missing (bell)
    drafter = _ScriptedDrafter(write_out=best, rewrites=["A dragon lives here."])  # worse: 1u+2m
    r = author_compose_stop(_FACTS, "Tower", "dark_history", drafter=drafter,
                            checker=_checker(), stitch_fallback=_STITCH, max_repairs=2)
    # both repairs were handed the BEST draft, never the regressed "A dragon lives here."
    assert drafter.given_drafts == [best, best], drafter.given_drafts
    assert r.grounded_fallback  # best never reached 0/0
    assert "dragon" not in r.text.lower()  # the regression was never served


def test_empty_rewrite_is_discarded_and_loop_recovers():
    """A rewrite that collapses to empty is never adopted and never crashes the loop; the
    next repair retries from the best draft and converges. UNDO: remove the `if cand.strip()`
    guard -> the empty draft is checked and (being all-missing) recorded as an attempt, and a
    ``\"\".join`` on it can no longer be distinguished -> the recovery assertion below (needing
    a 2nd rewrite after the empty) still holds, but the guard keeps us from a wasted check."""
    drafter = _ScriptedDrafter(
        write_out="The tower was built in 1250.",  # 1 missing (bell)
        rewrites=["",  # rewrite #1 collapses to empty -> discarded
                  "The tower was built in 1250. The bell weighs thirteen tons."],  # #2 fixes
    )
    r = author_compose_stop(_FACTS, "Tower", "dark_history", drafter=drafter,
                            checker=_checker(), stitch_fallback=_STITCH, max_repairs=3)
    assert r.result.passed() and not r.grounded_fallback
    assert "thirteen tons" in r.text.lower()
    assert drafter.rewrite_calls == 2  # the empty forced a second rewrite


def test_trace_records_each_author_attempt_and_its_verdict():
    """The optional ``trace`` out-param must capture EACH author attempt as (draft, verdict)
    in order — so a fallback is diagnosable (which claims stayed unsupported / facts missing
    on the final author draft), not just the grounded floor's verdict. UNDO: stop appending
    to trace in author_compose_stop -> the trace is empty -> RED."""
    drafter = _MockDrafter(
        write_out="The tower was built in 1250.",  # always drops the bell -> never converges
        rewrite_out="The tower was built in 1250.",
    )
    trace: list = []
    r = author_compose_stop(_FACTS, "Tower", "dark_history", drafter=drafter,
                            checker=_checker(), stitch_fallback=_STITCH, max_repairs=2, trace=trace)
    assert r.grounded_fallback
    # one entry per author attempt: initial write + 2 rewrites = 3 (the stitch floor is NOT
    # an author attempt, so it is not traced)
    assert len(trace) == 3, trace
    for draft, verdict in trace:
        assert draft == "The tower was built in 1250."
        assert any("thirteen tons" in m.lower() for m in verdict.missing_facts)
