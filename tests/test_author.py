"""The AUTHOR ENGINE loop (src/tour/author.py): draft -> semantic fact-check -> repair,
bounded, with a grounded-stitch floor. Proven offline ($0) with the deterministic
substring-entailment checker: a dropped fact triggers a repair that RESTORES it; an
invented fact is STRIPPED; and if the drafter never converges, the stop falls back to the
fact-complete stitch — so fidelity is guaranteed while the author's flow is preferred.
"""

from __future__ import annotations

import threading
import time
import types

from src.tour.author import LLMDrafter, StopContext, author_compose_script, author_compose_stop
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


# --- widen-retry fallback policy (Phase C fix #1; PHASE-C-RESULTS.md) ---

_WIDE_TEXT = ("The tower was built in 1250. The bell weighs thirteen tons. "
              "The clock was added in 1300.")
_WIDE_FACTS = (*_FACTS, "the clock was added in 1300")


def test_widen_retry_converges_when_wider_facts_support_the_draft():
    """Narrow facts make the drafter's bridging claim ('clock added in 1300') unsupported;
    the widened window contains it, so the SAME prose passes -> served authored, widened."""
    drafter = _MockDrafter(write_out=_WIDE_TEXT, rewrite_out=_WIDE_TEXT)
    r = author_compose_stop(
        _FACTS, "Tower", "dark_history", drafter=drafter, checker=_checker(),
        stitch_fallback=_STITCH, max_repairs=1, widen=lambda: _WIDE_FACTS)
    assert r.result.passed()
    assert not r.grounded_fallback
    assert r.widened
    assert r.text == _WIDE_TEXT


def test_widen_called_exactly_once_and_stitch_stays_narrow_on_wide_failure():
    """Widening that still fails must not loop, and the served floor is the ORIGINAL
    narrow stitch (never a wider stitch — the acceptance panel's killer diagnostic)."""
    calls = {"n": 0}

    def widen():
        calls["n"] += 1
        # wide set adds a fact the drafter's text never states -> still fails wide
        return (*_FACTS, "the spire burned in 1666")

    drafter = _MockDrafter(write_out="The tower was built in 1250.",
                           rewrite_out="The tower was built in 1250.")
    r = author_compose_stop(
        _FACTS, "Tower", "dark_history", drafter=drafter, checker=_checker(),
        stitch_fallback=_STITCH, max_repairs=1, widen=widen)
    assert calls["n"] == 1
    assert r.grounded_fallback and not r.widened
    assert r.text == _STITCH


def test_widen_never_called_when_narrow_loop_converges():
    def widen():
        raise AssertionError("widen must not be called on a converged narrow pass")

    drafter = _MockDrafter(write_out=_STITCH, rewrite_out=_STITCH)
    r = author_compose_stop(_FACTS, "Tower", "dark_history", drafter=drafter,
                           checker=_checker(), stitch_fallback=_STITCH, widen=widen)
    assert r.result.passed() and not r.grounded_fallback and not r.widened


def test_widen_returning_none_spends_nothing_extra():
    """The money guard: when the wider window adds too little, widen() returns None and
    the drafter sees zero additional calls beyond the narrow loop."""
    drafter = _MockDrafter(write_out="The tower was built in 1250.",
                           rewrite_out="The tower was built in 1250.")
    r = author_compose_stop(
        _FACTS, "Tower", "dark_history", drafter=drafter, checker=_checker(),
        stitch_fallback=_STITCH, max_repairs=2, widen=lambda: None)
    assert r.grounded_fallback and not r.widened
    assert drafter.writes == 1 and drafter.rewrites == 2  # narrow loop only


# --- cross-stop threading (StopContext; the essays-not-a-walk defect) ---
#
# author_compose_stop/_author_loop never call a drafter's write/rewrite WITH a `context=`
# kwarg unless a StopContext was actually supplied — so the pre-threading fakes above
# (_MockDrafter, _ScriptedDrafter, which declare no `context` parameter at all) keep working
# untouched wherever a test does not pass `context=`/`thread=True`. The recording fake below
# is a SEPARATE, additive fake used only by the threading tests.


class _RecordingDrafter:
    """A Drafter that RECORDS the StopContext (or None) passed to each write/rewrite call, in
    call order (``write_contexts`` / ``rewrite_contexts``) — so one fake can drive every
    threading test (context arrival, position/next_poi/prev_summary correctness, and the
    anti-hallucination bite) without touching the pre-existing fakes above. Returns a fixed
    string, or the result of an injected callable keyed on (facts, poi, lens, context)."""

    def __init__(self, write_out="", rewrite_out="", write_fn=None, rewrite_fn=None):
        self._w, self._r = write_out, rewrite_out
        self._write_fn, self._rewrite_fn = write_fn, rewrite_fn
        self.writes = self.rewrites = 0
        self.write_contexts: list[StopContext | None] = []
        self.rewrite_contexts: list[StopContext | None] = []

    def write(self, facts, poi, lens, *, context=None):
        self.writes += 1
        self.write_contexts.append(context)
        return self._write_fn(facts, poi, lens, context) if self._write_fn else self._w

    def rewrite(self, facts, draft, result, poi, lens, *, context=None):
        self.rewrites += 1
        self.rewrite_contexts.append(context)
        if self._rewrite_fn:
            return self._rewrite_fn(facts, draft, result, poi, lens, context)
        return self._r


def test_context_threads_from_each_stop_to_the_next():
    """thread=True: a 3-stop script threads prev_summary/next_poi/position across stops,
    ascending, deriving the summary from the SERVED text (not the discarded draft).
    UNDO: stop passing context in author_compose_script -> every ctx is None -> RED."""
    route, seq, stitched = _route_seq_stitched([
        [_beat("b0", "p0", "the tower was built in 1250")],
        [_beat("b1", "p1", "the bell weighs thirteen tons")],
        [_beat("b2", "p2", "the clock was added in 1300")],
    ])

    def _write_fn(facts, poi, lens, context):
        return f"Something opens for {poi} here. This is the payoff for {poi}."

    drafter = _RecordingDrafter(write_fn=_write_fn)
    _script, fell_back = author_compose_script(
        stitched, seq, route, lens="x", drafter=drafter, checker=_AlwaysPass(), thread=True)

    assert fell_back == {0: False, 1: False, 2: False}
    assert len(drafter.write_contexts) == 3
    c0, c1, c2 = drafter.write_contexts

    assert c0.position == "opening" and c0.prev_summary == ""
    assert c0.next_poi == "p1"

    assert c1.position == "middle"
    assert c1.prev_summary == "This is the payoff for p0."  # the LAST sentence stop 0 served
    assert c1.next_poi == "p2"

    assert c2.position == "finale"
    assert c2.next_poi == ""
    assert c2.prev_summary == "This is the payoff for p1."


def test_thread_disabled_passes_no_context_kwarg_to_legacy_drafter():
    """thread unset (False): the pre-threading 3-arg _MockDrafter (no `context` parameter at
    all) still works unmodified, proving the call site never passes `context=` when there is
    none. This proves the NO-KWARG guard only -- it does NOT prove prompt byte-identity (a
    3-arg fake has no `system` prompt to inspect at all); byte-identity of the actual SDK
    prompt is proven separately by test_default_author_system_prompt_is_pinned plus
    test_llmdrafter_write_omits_threading_addendum_when_context_absent, which assert the real
    `system` string sent to the SDK. UNDO: always pass context= at the call site -> TypeError
    on this 3-arg fake -> RED. Guards the production API path too (src/api/dependencies.py
    never sets thread=)."""
    route, seq, stitched = _route_seq_stitched(
        [[_beat("b0", "p0", "the tower was built in 1250")]])
    drafter = _MockDrafter(write_out="AUTHORED PROSE about the tower.", rewrite_out="unused")
    _script, fell_back = author_compose_script(
        stitched, seq, route, lens="dark_history", drafter=drafter, checker=_AlwaysPass())
    assert fell_back == {0: False}
    assert drafter.writes == 1


def test_finale_gets_finale_position_and_empty_next_poi():
    """UNDO: always populate next_poi (even on the finale) -> RED."""
    route, seq, stitched = _route_seq_stitched([
        [_beat("b0", "p0", "fact zero")],
        [_beat("b1", "p1", "fact one")],
    ])
    drafter = _RecordingDrafter(write_fn=lambda f, p, l, c: f"Closing line for {p}.")
    author_compose_script(
        stitched, seq, route, lens="x", drafter=drafter, checker=_AlwaysPass(), thread=True)
    assert drafter.write_contexts[-1].position == "finale"
    assert drafter.write_contexts[-1].next_poi == ""


def test_single_content_stop_gets_finale_not_opening():
    """EDGE CASE: a tour with exactly ONE content-bearing stop is the LAST thing the walker
    hears and must get the closing instruction, not be mislabelled "opening" (which would
    tell the drafter to plant a forward pull toward a next stop that does not exist, and
    deny the walker any actual close). UNDO: revert the ladder to check `i == 0` (opening)
    BEFORE `i == len(content_stops) - 1` (finale) -> a lone stop (i == 0 == len-1) matches
    the opening branch first -> RED."""
    route, seq, stitched = _route_seq_stitched([[_beat("b0", "p0", "the only fact")]])
    drafter = _RecordingDrafter(write_fn=lambda f, p, l, c: "Just this once.")
    author_compose_script(
        stitched, seq, route, lens="x", drafter=drafter, checker=_AlwaysPass(), thread=True)
    assert len(drafter.write_contexts) == 1
    assert drafter.write_contexts[0].position == "finale"
    assert drafter.write_contexts[0].next_poi == ""


def test_position_is_opening_on_the_first_authored_stop_when_stop0_is_glue_only():
    """A glue/vignette-only stop 0 (no beat sentences at all) must not steal the "opening"
    label -- the first stop that actually gets AUTHORED is opening. UNDO: index position from
    the raw ``stops`` list (which includes the glue-only stop) instead of from content-bearing
    stops -> stop 1 (the real first content stop) is mislabelled -> RED."""
    route, seq, stitched = _route_seq_stitched([
        [],  # stop 0: zero beats -> glue-only, invisible to threading
        [_beat("b1", "p1", "fact one")],
        [_beat("b2", "p2", "fact two")],
    ])
    stop0_has_beat_content = any(
        s.stop_idx == 0 and s.source_type == "beat" for s in stitched.script
    )
    assert not stop0_has_beat_content  # sanity: stop 0 really has no beat content to author

    drafter = _RecordingDrafter(write_fn=lambda f, p, l, c: f"Line for {p}.")
    author_compose_script(
        stitched, seq, route, lens="x", drafter=drafter, checker=_AlwaysPass(), thread=True)
    assert len(drafter.write_contexts) == 2  # only the 2 content stops are ever authored
    assert drafter.write_contexts[0].position == "opening"
    assert drafter.write_contexts[0].prev_summary == ""  # nothing content-bearing served yet
    assert drafter.write_contexts[1].position == "finale"


def test_threaded_bridge_that_invents_still_falls_back():
    """A bridge that asserts a claim absent from THIS stop's facts still fails to converge and
    the stop falls back to the grounded stitch -- threading buys ZERO leniency. The bridge
    sentence is crafted so it would ONLY be fully entailed if context.prev_summary were ever
    merged into the checker's source facts (it is exactly ``fact + " " + prev_summary``) --
    proving the checker never sees it. UNDO: append context.prev_summary to the facts passed
    into checker.check -> the bridge sentence becomes fully entailed -> the stop wrongly
    converges (grounded_fallback flips to False) -> RED."""
    fact = "the bell weighs thirteen tons"
    prev_summary = "you just crossed the old stone bridge"
    bridge_text = f"{fact} {prev_summary}"  # one claim: the real fact + invented bridge material
    ctx = StopContext(prev_summary=prev_summary, position="middle", next_poi="p2")
    drafter = _RecordingDrafter(write_out=bridge_text, rewrite_out=bridge_text)
    r = author_compose_stop(
        (fact,), "Tower", "dark_history", drafter=drafter, checker=_checker(),
        stitch_fallback="The bell weighs thirteen tons.", max_repairs=1, context=ctx)
    assert r.grounded_fallback
    assert r.threaded  # attributed to the threading track even though it still fell back


class _SpyChecker:
    """Records the exact ``source_facts`` tuple every ``check`` call is made with; fails
    once then passes (forcing exactly one write + one rewrite, so BOTH call sites are
    exercised) — used to prove the fact-checker NEVER sees anything beyond the caller's
    own ``facts``."""

    def __init__(self):
        self.calls: list[tuple[str, tuple]] = []

    def check(self, narration_text, source_facts):
        self.calls.append((narration_text, source_facts))
        return FactCheckResult((), ()) if len(self.calls) > 1 else FactCheckResult(("x",), ())


def test_prev_summary_is_never_admitted_as_a_source_fact():
    """The fact-checker must be called with EXACTLY this stop's ``facts`` on every attempt --
    ``context.prev_summary`` must never be appended to, or otherwise merged into, the
    checker's source facts, or unverified narration would become uncheckable "evidence" for
    a later claim. UNDO: pass context.prev_summary into checker.check's source facts -> the
    recorded source_facts tuple contains it -> RED. (Guards the laundering hole.)"""
    ctx = StopContext(prev_summary="The old bridge collapsed in 1800.", position="middle",
                      next_poi="p2")
    facts = ("the bell weighs thirteen tons",)
    checker = _SpyChecker()
    drafter = _RecordingDrafter(write_out="draft one", rewrite_out="draft two")
    author_compose_stop(facts, "Tower", "dark_history", drafter=drafter, checker=checker,
                        stitch_fallback="The bell weighs thirteen tons.", max_repairs=1,
                        context=ctx)
    assert len(checker.calls) == 2  # write-check + rewrite-check, both exercised
    for _, source_facts in checker.calls:
        assert source_facts == facts
        assert ctx.prev_summary not in source_facts


def test_fallback_stop_still_supplies_context_to_the_next_stop():
    """stop 0 falls back to its grounded stitch; stop 1's context.prev_summary must derive
    from the SERVED stitch, not the discarded draft. UNDO: only set prev_summary on converged
    (non-fallback) stops -> stop 1 sees an empty prev_summary -> RED."""
    route, seq, stitched = _route_seq_stitched([
        [_beat("b0", "p0", "the tower was built in 1250")],
        [_beat("b1", "p1", "the bell weighs thirteen tons")],
    ])

    def _write_fn(facts, poi, lens, context):
        if poi == "p0":
            return "a bad draft that never passes"  # always unsupported -> falls back
        return "The bell weighs thirteen tons."  # p1: matches its fact exactly -> converges

    drafter = _RecordingDrafter(
        write_fn=_write_fn, rewrite_fn=lambda f, d, r, p, ln, c: "still bad")
    _script, fell_back = author_compose_script(
        stitched, seq, route, lens="x", drafter=drafter, checker=_checker(), thread=True,
        max_repairs=1)

    assert fell_back == {0: True, 1: False}
    orig_stop0_text = " ".join(
        s.text for s in stitched.script if s.stop_idx == 0 and s.source_type == "beat"
    )
    from src.tour.author import _one_sentence_summary
    assert drafter.write_contexts[1].prev_summary == _one_sentence_summary(orig_stop0_text)
    assert "bad draft" not in drafter.write_contexts[1].prev_summary


def test_threaded_script_authors_each_stop_serially_never_concurrently():
    """thread=True must author each stop ONE AT A TIME, never concurrently -- proven
    DIRECTLY, not by timing luck. Each write() takes a non-reentrant lock with timeout=0
    (a genuinely concurrent second call fails to acquire it and the assert inside fires) and
    holds it across a short sleep (widening the window a race would need to slip through) so
    the max observed concurrency is recorded. A plain `order == [p0, p1, p2]` check alone does
    NOT prove this: a ThreadPoolExecutor handed 3 trivially-fast tasks in submission order
    commonly completes them in that same order too. UNDO: swap the `for stop_idx in stops:`
    walk back to `ThreadPoolExecutor(...).map(_author_stop, stops)` under thread=True -> two
    write() calls overlap -> the lock-acquire assert fires / max_concurrent > 1 -> RED. Also
    proves the content-derived property the old test only checked loosely: each stop's
    prev_summary EXACTLY equals what the immediately preceding write() returned, which is only
    possible if that call had already returned."""
    lock = threading.Lock()
    state = {"concurrent": 0, "max_concurrent": 0}

    def _write_fn(facts, poi, lens, context):
        acquired = lock.acquire(timeout=0)
        assert acquired, f"write() for {poi} started while a previous write() was still running"
        try:
            state["concurrent"] += 1
            state["max_concurrent"] = max(state["max_concurrent"], state["concurrent"])
            time.sleep(0.02)
            state["concurrent"] -= 1
        finally:
            lock.release()
        return f"Closing line for {poi}."

    drafter = _RecordingDrafter(write_fn=_write_fn)
    route, seq, stitched = _route_seq_stitched([
        [_beat("b0", "p0", "fact zero")],
        [_beat("b1", "p1", "fact one")],
        [_beat("b2", "p2", "fact two")],
    ])
    author_compose_script(
        stitched, seq, route, lens="x", drafter=drafter, checker=_AlwaysPass(), thread=True)
    assert state["max_concurrent"] == 1
    assert drafter.write_contexts[1].prev_summary == "Closing line for p0."
    assert drafter.write_contexts[2].prev_summary == "Closing line for p1."


def test_threading_addendum_forbids_new_connective_facts():
    """Structural pin: the threading addendum states the no-new-connective-fact constraint,
    constrains a bridge/pull to the forms factcheck.py's decomposer provably yields ZERO
    claims for (second-person, question, sensory framing), and drops the ambiguous "call
    back to something this tour already said" phrasing that could ALSO be satisfied by a
    flat declarative restatement (the exact prompt/checker conflict this fix closes). It is
    also textually ABSENT from the default (context=None) _AUTHOR_SYSTEM -- so a context=None
    call keeps today's exact production prompt. UNDO: delete the constraint clause from
    _THREADING_ADDENDUM -> RED. (Structural assertion on a constant, not a meaning-level
    judgement.)"""
    from src.tour.author import _AUTHOR_SYSTEM, _THREADING_ADDENDUM

    addendum_lower = _THREADING_ADDENDUM.lower()
    assert "rhetorical only" in addendum_lower
    assert "never assert a new fact" in addendum_lower
    assert "second person" in addendum_lower or "second-person" in addendum_lower
    assert "question" in addendum_lower
    # the fixed defect: this exact phrase let a bridge satisfy "callback to what was said"
    # AND "no new fact" only by contradiction -- it must not reappear.
    assert "call back to something this tour already said" not in addendum_lower
    assert "cross-stop continuity" not in _AUTHOR_SYSTEM.lower()


def test_threading_addendum_bridge_clause_present_when_prev_summary_given():
    """Direct unit test of the bridge branch: when ``prev_summary`` is non-empty, the
    addendum surfaces it as CONTEXT for the model but constrains its use to a rhetorical
    gesture, never a restatement. UNDO: stop formatting ``bridge_clause`` into the returned
    string -> the prev_summary text and the restatement ban both vanish -> RED."""
    from src.tour.author import _threading_addendum

    ctx = StopContext(prev_summary="the old bell tolled once.", position="middle", next_poi="p2")
    out = _threading_addendum(ctx)
    assert "the old bell tolled once." in out
    assert "never restate" in out.lower() or "never repeat" in out.lower()


def test_threading_addendum_bridge_clause_absent_when_no_prev_summary():
    """The opening stop (no previous content-bearing stop, so ``prev_summary`` is empty) gets
    no bridge instruction at all -- only the fixed structural preamble (which legitimately
    always says the narration is heard after "the previous stop", tour-structure framing, not
    referenced content) and the shared closing constraint remain. UNDO: unconditionally emit
    the bridge clause regardless of ``prev_summary`` -> the "for context only" gesture
    instruction appears with nothing to gesture at -> RED."""
    from src.tour.author import _threading_addendum

    ctx = StopContext(prev_summary="", position="opening", next_poi="p1")
    out = _threading_addendum(ctx)
    assert "for context only" not in out.lower()
    assert "gesture at that moment" not in out.lower()


def test_threading_addendum_finale_branch_gives_a_close_not_a_pull():
    """The finale branch tells the drafter to close the tour, and (unlike the next_poi
    branch) there is no "next stop" to avoid naming since none exists. UNDO: fall through to
    the next_poi branch on the finale -> the closing instruction vanishes -> RED."""
    from src.tour.author import _threading_addendum

    ctx = StopContext(prev_summary="", position="finale", next_poi="")
    out = _threading_addendum(ctx)
    assert "final stop" in out.lower()
    assert "close" in out.lower()


def test_threading_addendum_next_poi_branch_never_names_the_next_poi():
    """KILLER-DEFECT regression: the forward-pull instruction must NEVER splice the next
    POI's literal name into the prompt -- naming it invites a declarative sentence with a
    proper noun absent from THIS stop's FACTS, which factcheck.py's TEST 3 rejects outright
    (adds a name the facts never give). UNDO: reintroduce an f-string that interpolates
    ``context.next_poi`` into the pull-clause text -> "Sainte-Chapelle" appears in `out` ->
    RED."""
    from src.tour.author import _threading_addendum

    ctx = StopContext(prev_summary="", position="middle", next_poi="Sainte-Chapelle")
    out = _threading_addendum(ctx)
    assert "Sainte-Chapelle" not in out
    assert "forward pull" in out.lower()


def test_threading_addendum_neither_finale_nor_next_poi_yields_no_pull_instruction():
    """A middle stop with no known next content stop (e.g. it is the last authored stop but
    was never marked finale) gets no forward-pull instruction fabricated from nothing. UNDO:
    emit a generic pull clause even when next_poi is empty and position isn't finale -> RED."""
    from src.tour.author import _threading_addendum

    ctx = StopContext(prev_summary="", position="middle", next_poi="")
    out = _threading_addendum(ctx)
    assert "final stop" not in out.lower()
    assert "forward pull" not in out.lower()


def test_llmdrafter_write_omits_threading_addendum_when_context_absent():
    """UNTESTED LIVE WIRING fix: no test previously asserted the real SDK-bound `system`
    prompt LLMDrafter.write sends. With no context, it must be BYTE-IDENTICAL to the
    production prompt -- no threading text at all. UNDO: make `write()` always append
    `_threading_addendum(...)` (e.g. build a default StopContext when context is None) ->
    calls[0]['system'] gains threading text -> RED."""
    from src.tour.author import _AUTHOR_SYSTEM

    client, calls = _fake_anthropic("Some prose.")
    LLMDrafter("m", client=client).write(("a fact",), "Tower", "dark_history")
    assert calls[0]["system"] == _AUTHOR_SYSTEM.format(poi="Tower", lens="dark_history")


def test_llmdrafter_write_appends_threading_addendum_when_context_present():
    """UNTESTED LIVE WIRING fix: the entire production-facing effect of threading was
    unpinned -- no test asserted LLMDrafter.write actually appends the addendum to the real
    prompt sent to the SDK. UNDO: delete `system += _threading_addendum(context)` at
    author.py's write() -> the addendum text vanishes from calls[0]['system'] -> RED."""
    from src.tour.author import _AUTHOR_SYSTEM, _threading_addendum

    ctx = StopContext(prev_summary="", position="opening", next_poi="p1")
    client, calls = _fake_anthropic("Some prose.")
    LLMDrafter("m", client=client).write(("a fact",), "Tower", "dark_history", context=ctx)
    expected = _AUTHOR_SYSTEM.format(poi="Tower", lens="dark_history") + _threading_addendum(ctx)
    assert calls[0]["system"] == expected
    assert "CROSS-STOP CONTINUITY" in calls[0]["system"]


def test_llmdrafter_rewrite_omits_threading_addendum_when_context_absent():
    """The rewrite() mirror of the write() no-context wiring test above."""
    from src.tour.author import _REWRITE_SYSTEM

    client, calls = _fake_anthropic("Revised prose.")
    result = FactCheckResult((), ())
    LLMDrafter("m", client=client).rewrite(
        ("a fact",), "draft text", result, "Tower", "dark_history")
    assert calls[0]["system"] == _REWRITE_SYSTEM.format(poi="Tower", lens="dark_history")


def test_llmdrafter_rewrite_appends_threading_addendum_when_context_present():
    """The rewrite() mirror of the write() with-context wiring test above -- rewrite is the
    OTHER call site the addendum must reach (author.py:574) and it had zero direct coverage.
    UNDO: delete `system += _threading_addendum(context)` at author.py's rewrite() -> the
    addendum text vanishes from calls[0]['system'] -> RED."""
    from src.tour.author import _REWRITE_SYSTEM, _threading_addendum

    ctx = StopContext(prev_summary="prior gist.", position="middle", next_poi="p2")
    client, calls = _fake_anthropic("Revised prose.")
    result = FactCheckResult(("bad claim",), ("missing fact",))
    LLMDrafter("m", client=client).rewrite(
        ("a fact",), "draft text", result, "Tower", "dark_history", context=ctx)
    expected = _REWRITE_SYSTEM.format(poi="Tower", lens="dark_history") + _threading_addendum(ctx)
    assert calls[0]["system"] == expected


# Verbatim copy of the CURRENT (pre-threading) _AUTHOR_SYSTEM — the production prompt for
# every context=None call (which is every caller today: the API path never sets thread=).
# tools/compose_snapshot.py's pinned fingerprint covers ONLY compose.py's constants, so
# nothing else in the suite would catch an accidental edit here.
_EXPECTED_AUTHOR_SYSTEM = (
    "You are a master audio walking-tour writer. Write ONE dwell-stop of narration for a "
    "walker standing at {poi} ({lens} lens).\n"
    "First, silently PLAN the arc: choose the strongest hook to open on, and order the "
    "material so tension BUILDS to a payoff late, not buried in the middle.\n"
    "Then WRITE flowing spoken prose: open on a MOMENT (never a label/date); CONNECT facts "
    "causally, each sentence handing off to the next (never a list of closed declaratives); "
    "vary rhythm HARD (a sentence under 8 words AND a longer line; never 3 of the same shape "
    "in a row); SAY EACH FACT ONCE; render dark material plainly, then move on. ~150 words, "
    "second person, warm, heard once.\n"
    "STRICT GROUNDING — this is non-negotiable and a fact-checker will verify it: use ONLY "
    "the facts below and keep EVERY one. Add NO name, date, number, material, place, or "
    "detail that is not in the facts — not even a plausible one (do NOT call a bell "
    "'bronze' or a figure someone's 'sister' unless the facts say so). Your vividness comes "
    "from RHYTHM, STRUCTURE, and how you CONNECT the facts — never from inventing detail. "
    "Rephrasing a fact is welcome; adding a new fact is forbidden.\n"
    "KEEP EACH FACT ON ITS OWN SUBJECT — this stop is {poi}, and it may contain or sit near "
    "other named things (a tower, a hall, a person). A fact the facts state about ONE subject "
    "must land on THAT subject: never let a property slide onto a different entity just "
    "because you named it in the last breath. If a fact is about {poi}, name {poi} (or a "
    "pronoun a listener cannot mishear); if it is about the tower, name the tower. A "
    "fact-checker will reject 'the tower is the oldest prison' when the facts say the PLACE "
    "is. When two things could be confused, name the one you mean. Return ONLY the narration."
)


def test_default_author_system_prompt_is_pinned():
    """No-context system prompt pin: nothing else in the suite catches an accidental edit to
    the PRODUCTION _AUTHOR_SYSTEM (tools/compose_snapshot.py's fingerprint covers only
    compose.py's constants). UNDO: mutate a word in _AUTHOR_SYSTEM -> mismatch -> RED."""
    from src.tour.author import _AUTHOR_SYSTEM

    assert _AUTHOR_SYSTEM == _EXPECTED_AUTHOR_SYSTEM
