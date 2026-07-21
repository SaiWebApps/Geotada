"""OMISSION DETECTION — the ADVISORY coverage-direction wiring in compose.py.

PROVEN, not suspected: the production coverage gate (claim_dedup.verify_claim_coverage)
is an overlap COEFFICIENT (|a∩b| / min(|a|,|b|)). Once compose DELETES material, the
composed signature becomes a SUBSET of the claim signature, so ``min()`` is the composed
side and the ratio reads 1.000 BY CONSTRUCTION — no threshold fixes this. This module
proves it on the REAL London ``Trafalgar Square`` beat (data/london/beats.json,
beat_id="london_trafalgar_square_wikipedia_1", KEYLESS — key_claims=()):

    script_body = "The area around Trafalgar Square has been a significant landmark
    since the 1200s, as distances from London are measured from Charing Cross."

then proves ``find_dropped_facts`` (src/tour/compose.py), wired opt-in into
``compose_script_per_chapter`` via ``omission_checker``/``omission_findings``, DOES
catch the drop the lexical gate misses — using ONLY the coverage direction (no
decomposer call), $0 in this suite (offline stub judge, never the real Haiku SDK).
"""

from __future__ import annotations

from src.tour.claim_dedup import claims_realized_by, verify_claim_coverage
from src.tour.compose import (
    MockComposeClient,
    OmissionFinding,
    compose_script_per_chapter,
    find_dropped_facts,
    keyless_affected_stops,
)
from src.tour.contract import (
    POI,
    BeatRef,
    BeatSequence,
    POIBeats,
    Route,
    TourInput,
    TransitSegment,
)
from src.tour.generation import generate

# --- money-guard pinning: get_omission_checker() must NEVER bill in the suite ---


def test_money_guard_omission_checker_is_offline_stub_in_suite() -> None:
    """MONEY-GUARD: ``get_omission_checker()`` (src/api/dependencies.py) must return
    an OFFLINE stub in the hermetic suite, never the real billing ``HaikuCoverageJudge``
    — it constructs the checker via ``factcheck.HaikuCoverageJudge()`` (module
    attribute, client=None), which conftest.py's existing autouse money-guard arm
    (added for the author-engine path) already intercepts; this pins that contract
    for THIS call site too.
    UNDO: make ``get_omission_checker`` bind ``HaikuCoverageJudge`` via a top-level
    ``from src.tour.factcheck import HaikuCoverageJudge`` (invisible to the
    monkeypatch, the exact breach test_trips_route_holds_no_unpatchable_corrector_
    binding guards against for the corrector) -> the assertion below goes RED
    because the returned object no longer offline-trusts."""
    from src.api.dependencies import get_omission_checker

    checker = get_omission_checker()
    # The offline stub (_TrustingJudge in conftest.py) always says "conveyed" —
    # never bills, never flags an omission. A real HaikuCoverageJudge would try to
    # construct the Anthropic SDK client and fail/spend in this environment.
    assert checker.conveys("anything", "anything") is True


def test_trips_route_holds_no_unpatchable_omission_checker_binding() -> None:
    """Structural guard against the same breach ``get_correction_client`` documents:
    a module-level ``from X import Y`` in the route would be invisible to a
    monkeypatch of X, so the money guard could not reach it. The omission checker
    must be resolved through ``get_omission_checker`` (a FastAPI dependency), never
    bound at import time in the route module."""
    import src.api.routes.trips as trips_route

    assert not hasattr(trips_route, "HaikuCoverageJudge"), (
        "src/api/routes/trips.py binds HaikuCoverageJudge at import time — the "
        "conftest money guard cannot patch it; inject it via get_omission_checker instead"
    )

# The REAL London beat (data/london/beats.json, beat_id
# "london_trafalgar_square_wikipedia_1") — copied verbatim, KEYLESS (key_claims=()),
# exactly the corpus shape where the blind spot is proven worst (100% of London).
TRAFALGAR_BODY = (
    "The area around Trafalgar Square has been a significant landmark since the "
    "1200s, as distances from London are measured from Charing Cross."
)
TRAFALGAR_BEAT_ID = "london_trafalgar_square_wikipedia_1"
TRAFALGAR_POI_ID = "trafalgar_square"

# A second, KEYED beat for a different stop, so the keyless-only cost-bounding scope
# has something real to exclude.
KEYED_BODY = "Nelson's Column was completed in 1843 to honour Admiral Horatio Nelson."
KEYED_BEAT_ID = "keyed_beat_1"
KEYED_POI_ID = "keyed_poi"


def _mk_beat(bid: str, poi_id: str, body: str, *, key_claims: tuple[str, ...] = ()) -> BeatRef:
    return BeatRef(
        id=bid,
        poi_id=poi_id,
        script_body=body,
        word_count=len(body.split()),
        key_claims=key_claims,
        est_spoken_seconds=15,
    )


def _mk_route(n_stops: int) -> Route:
    pois = tuple(
        POI(id=f"p{i}", name=f"p{i}", tier=5, poi_role="stop", lat=51.50, lng=-0.12)
        for i in range(n_stops)
    )
    transits = tuple(
        TransitSegment(
            from_poi_id=None if i == 0 else pois[i - 1].id,
            to_poi_id=p.id,
            distance_m=100.0,
            walk_seconds=10 if i == 0 else 30,
        )
        for i, p in enumerate(pois)
    )
    return Route(
        pois=pois,
        transits=transits,
        total_walk_distance_m=100.0 * n_stops,
        total_walk_seconds=sum(10 if i == 0 else 30 for i in range(n_stops)),
    )


def _mk_tour(stop_beats: list[list[BeatRef]]):
    seq = BeatSequence(
        poi_beats=tuple(
            POIBeats(
                poi_id=f"p{i}", poi_name=f"p{i}",
                ordering_strategy="sub_location", beats=tuple(beats),
            )
            for i, beats in enumerate(stop_beats)
        ),
    )
    route = _mk_route(len(stop_beats))
    stitched = generate(
        seq, route, TourInput(start=(51.50, -0.12), duration_min=60, city_slug="london")
    )
    assert stitched.validation.passed  # the pre-compose baseline is clean
    return seq, route, stitched


class _AnchorCoverageJudge:
    """Offline stand-in for the calibrated HaikuCoverageJudge: says NO iff a fixed
    ANCHOR phrase (a proper noun the real bake-off's prompt treats as a "specific
    element the narration never states in any form" — see factcheck.py's
    _COVERAGE_JUDGE_USER) is absent from the narration; YES otherwise. Not a
    realistic paraphrase model — a deterministic double that reproduces the ONE
    verdict this suite needs to prove, matching the SAME offline-substring-fake
    convention already used for the entailer in tests/test_factcheck.py."""

    def __init__(self, anchor: str = "Charing Cross"):
        self.anchor = anchor
        self.calls: list[tuple[str, str]] = []

    def conveys(self, fact: str, narration: str) -> bool:
        self.calls.append((fact, narration))
        return self.anchor in narration


class _RaisingCoverageJudge:
    """A checker that fails the test the instant it is called — used to prove a
    code path makes ZERO judge calls (the byte-identical / zero-cost guarantee)."""

    def conveys(self, fact: str, narration: str) -> bool:  # pragma: no cover - assertion path
        raise AssertionError("CoverageJudge.conveys called when it must not be")


def _trafalgar_tour():
    """One-stop tour: the real, KEYLESS Trafalgar Square beat."""
    beat = _mk_beat(TRAFALGAR_BEAT_ID, TRAFALGAR_POI_ID, TRAFALGAR_BODY)
    return _mk_tour([[beat]])


def _drop_charing_cross(stitched):
    """Simulate exactly the measured compose failure (specs/2026-07-16-tour-craft/
    DECOMP-PLAN.md): the composed sentence keeps 'landmark since the 1200s' but
    drops the Charing Cross clause. Still ONE beat-cited sentence, same source_id —
    a realistic bold-fusion rewrite, not a synthetic mutilation."""
    dropped_text = (
        "The area around Trafalgar Square has been a significant landmark since the 1200s."
    )
    new_script = tuple(
        s.model_copy(update={"text": dropped_text}) if s.source_id == TRAFALGAR_BEAT_ID else s
        for s in stitched.script
    )
    return stitched.model_copy(update={"script": new_script})


# --- 1. Ground the premise on REAL production code (no new code under test here) ---


def test_lexical_coverage_gate_is_structurally_blind_to_the_real_charing_cross_drop() -> None:
    """PROVES the premise, using the REAL claim_dedup.verify_claim_coverage gate
    (unchanged by this task) against the REAL Trafalgar beat: dropping the Charing
    Cross clause from the composed sentence is NOT caught. This is the gap
    find_dropped_facts exists to close — never fixed by touching this gate itself.
    """
    seq, _route, stitched = _trafalgar_tour()
    beats_by_id = {b.id: b for plan in seq.poi_beats for b in plan.beats}
    composed = _drop_charing_cross(stitched)

    expected = claims_realized_by(stitched, beats_by_id)
    assert expected, "the pre-compose stitch must voice >=1 realized claim"
    failures = verify_claim_coverage(composed, expected, beats_by_id)
    assert failures == (), (
        "if this fails, the lexical gate started catching the drop — re-check the "
        "premise before touching find_dropped_facts"
    )


# --- 2. find_dropped_facts: the new semantic coverage-direction check -----------


def test_find_dropped_facts_catches_the_real_charing_cross_drop() -> None:
    """The core finding: find_dropped_facts flags the Charing Cross drop that the
    production coverage gate (proven above) lets through GREEN."""
    seq, _route, stitched = _trafalgar_tour()
    beats_by_id = {b.id: b for plan in seq.poi_beats for b in plan.beats}
    composed = _drop_charing_cross(stitched)
    judge = _AnchorCoverageJudge("Charing Cross")

    findings = find_dropped_facts(composed, beats_by_id, judge)

    assert len(findings) == 1
    finding = findings[0]
    assert isinstance(finding, OmissionFinding)
    assert finding.beat_id == TRAFALGAR_BEAT_ID
    assert finding.stop_idx == 0
    assert "Charing Cross" in finding.fact
    assert judge.calls, "the judge must actually have been asked"


def test_find_dropped_facts_empty_when_the_fact_is_paraphrased_not_dropped() -> None:
    """A reworded-but-complete composed sentence (still contains the anchor, in any
    form) is NOT a finding — the paraphrase-tolerant direction this feature exists
    to preserve (never a false positive on legitimate bold fusion)."""
    seq, _route, stitched = _trafalgar_tour()
    beats_by_id = {b.id: b for plan in seq.poi_beats for b in plan.beats}
    # Unchanged: still conveys everything, including "Charing Cross".
    judge = _AnchorCoverageJudge("Charing Cross")

    findings = find_dropped_facts(stitched, beats_by_id, judge)

    assert findings == ()


def test_find_dropped_facts_respects_fact_cap_per_stop() -> None:
    """Cost bound: at most ``fact_cap_per_stop`` facts are judged for one stop, even
    when a stop's cited beats carry more pseudo-claims than that."""
    body = "Sentence one is here. Sentence two is here. Sentence three is here."
    beat = _mk_beat("many_facts_beat", "p0", body)  # keyless -> 3 pseudo-claims
    seq, _route, stitched = _mk_tour([[beat]])
    beats_by_id = {b.id: b for plan in seq.poi_beats for b in plan.beats}
    judge = _AnchorCoverageJudge("nonexistent-anchor")  # NO on everything -> all flagged

    findings = find_dropped_facts(stitched, beats_by_id, judge, fact_cap_per_stop=2)

    assert len(judge.calls) == 2
    assert len(findings) == 2


def test_find_dropped_facts_only_stops_filter_makes_zero_calls_outside_scope() -> None:
    """``only_stops`` bounds cost structurally: a stop excluded from the set is
    never even looked at (zero judge calls), not merely filtered post-hoc."""
    seq, _route, stitched = _trafalgar_tour()
    beats_by_id = {b.id: b for plan in seq.poi_beats for b in plan.beats}
    composed = _drop_charing_cross(stitched)

    findings = find_dropped_facts(
        composed, beats_by_id, _RaisingCoverageJudge(), only_stops=frozenset()
    )

    assert findings == ()


def test_keyless_affected_stops_scopes_to_keyless_beats_only() -> None:
    """The cost-bounding scope: a stop citing only a KEYED beat is excluded, a stop
    citing a KEYLESS beat (the proven-worst blind spot) is included."""
    keyless_beat = _mk_beat(TRAFALGAR_BEAT_ID, TRAFALGAR_POI_ID, TRAFALGAR_BODY)
    keyed_beat = _mk_beat(KEYED_BEAT_ID, KEYED_POI_ID, KEYED_BODY, key_claims=(KEYED_BODY,))
    seq, _route, stitched = _mk_tour([[keyless_beat], [keyed_beat]])
    beats_by_id = {b.id: b for plan in seq.poi_beats for b in plan.beats}

    scope = keyless_affected_stops(stitched, beats_by_id)

    assert scope == frozenset({0})


# --- 3. Opt-in wiring into compose_script_per_chapter ---------------------------


def test_compose_accepts_omission_checker_and_defaults_to_none() -> None:
    """UNDO: remove ``omission_checker``/``omission_findings`` from
    compose_script_per_chapter's signature -> RED. Both must default to None so no
    existing caller changes behaviour."""
    import inspect

    sig = inspect.signature(compose_script_per_chapter)
    assert "omission_checker" in sig.parameters
    assert sig.parameters["omission_checker"].default is None
    assert "omission_findings" in sig.parameters
    assert sig.parameters["omission_findings"].default is None


def test_compose_script_per_chapter_makes_zero_omission_calls_when_checker_is_none() -> None:
    """The default (every existing caller): omission_checker=None must cost nothing
    and change nothing about the served Script. A _RaisingCoverageJudge is never
    constructed here at all — there is nothing to inject — so this test's only job
    is to prove the ladder does not require one."""
    seq, route, stitched = _trafalgar_tour()
    served = compose_script_per_chapter(stitched, seq, route, client=MockComposeClient())
    assert served.validation.passed


def test_compose_script_per_chapter_wires_omission_findings_into_sink() -> None:
    """End-to-end: a composer that drops the Charing Cross clause (exactly the
    measured real-world failure) still passes the production VERIFY ladder
    (MockComposeClient's stitched-passthrough baseline plus our drop is
    grounded/traceable — the lexical gate has no opinion on it either, per test 1
    above), but the omission_findings sink now carries the drop. Proves the
    wiring end-to-end through compose_script_per_chapter, not just
    find_dropped_facts in isolation."""

    class _DroppingClient:
        """Composes by dropping the Charing Cross clause from the Trafalgar
        sentence, passthrough otherwise — deterministic, single-attempt."""

        def compose(self, request, attempt, prev_report):
            out = []
            for s in request.stitched.script:
                if s.source_id == TRAFALGAR_BEAT_ID:
                    out.append(s.model_copy(update={
                        "text": (
                            "The area around Trafalgar Square has been a "
                            "significant landmark since the 1200s."
                        )
                    }))
                else:
                    out.append(s)
            return tuple(out)

    seq, route, stitched = _trafalgar_tour()
    sink: list[OmissionFinding] = []

    served = compose_script_per_chapter(
        stitched, seq, route,
        client=_DroppingClient(),
        omission_checker=_AnchorCoverageJudge("Charing Cross"),
        omission_findings=sink,
    )

    assert served.validation.passed, (
        "the omission checker must be ADVISORY ONLY — it must never fail the "
        "served script's VERIFY report"
    )
    assert len(sink) == 1
    assert sink[0].beat_id == TRAFALGAR_BEAT_ID
    assert "Charing Cross" in sink[0].fact


def test_compose_script_per_chapter_omission_checker_alone_is_safe_without_a_sink() -> None:
    """``omission_findings=None`` (the default) must not raise even when
    ``omission_checker`` IS supplied — findings are simply discarded."""
    seq, route, stitched = _trafalgar_tour()
    served = compose_script_per_chapter(
        stitched, seq, route,
        client=MockComposeClient(),
        omission_checker=_AnchorCoverageJudge("Charing Cross"),
    )
    assert served.validation.passed


class _TransientlyFailingCoverageJudge:
    """Simulates a real transient Anthropic failure (429/529/timeout) on every call.

    Deliberately NOT an AssertionError: ``_RaisingCoverageJudge`` above uses
    AssertionError to prove a path makes ZERO calls, and that path reaches its
    assertion because no jobs are built at all (``only_stops=frozenset()``), never
    because an exception escapes ``_run``.
    """

    def __init__(self) -> None:
        self.calls = 0

    def conveys(self, fact: str, narration: str) -> bool:
        self.calls += 1
        raise RuntimeError("overloaded_error: simulated Haiku 529")


def test_a_transient_judge_failure_never_kills_an_already_paid_compose() -> None:
    """FOUNDING CASE: an ADVISORY pass must not destroy work that already cost money.

    find_dropped_facts runs inside _assemble, inside compose_script_per_chapter —
    i.e. AFTER a 9-stop preview has already billed ~18 Opus best-of-2 compose calls
    (~$1). preview_trip catches ONLY ComposeVerificationError, so before this guard a
    transient Haiku 529 propagated out of pool.map and 500'd a request whose expensive
    compose had already SUCCEEDED and been billed. Trading an advisory finding for a
    paid, successful tour is never the right trade.

    Found by a judge simulating the 529, not by the author — the docstring asserted
    "never raises" while the code could. See [[founding-case-efficacy-rule]].

    UNDO-TEST: remove the try/except in find_dropped_facts' ``_run`` and this goes RED
    with RuntimeError instead of returning ().
    """
    seq, _route, stitched = _trafalgar_tour()
    beats_by_id = {b.id: b for plan in seq.poi_beats for b in plan.beats}
    composed = _drop_charing_cross(stitched)
    judge = _TransientlyFailingCoverageJudge()

    findings = find_dropped_facts(composed, beats_by_id, judge)

    assert judge.calls > 0, "the judge must actually have been invoked for this to prove anything"
    assert findings == (), (
        "a failed advisory judge call must yield NO finding — reporting an omission we "
        "could not verify would send an editor hunting a defect that does not exist"
    )
