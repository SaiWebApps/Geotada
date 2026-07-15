"""$0 offline reproduction of the compose-revert asymmetry bug + its SURGICAL fix.

Bug (from the workbench): "only stop 0 keeps the AI narrator voice; stops 1..N
revert to the flat stitched baseline." This mimics the LIVE strictness offline
with (a) a rewriting compose client and (b) a STRICT stateless entailment checker
that over-rejects paraphrase the way live Haiku does (entails ONLY a near-verbatim
claim quote). It runs the REAL compose_script_per_chapter and pinpoints the gate.

Root cause: the FAITHFULNESS entailment gate (src/tour/verify.py:172) over-rejects
a bold, faithful FUSION; drop_failing_sentences then removes the fused
fact-carrying line, which trips COVERAGE. The OLD repair reverted the WHOLE stop
(src/tour/compose_gate.py:repair_composed), so a dense stop lost every one of its
good AI-voiced sentences for one bad fusion.

Fix (candidate c): repair is now SURGICAL — repair_composed_surgical keeps every
composed sentence that passed and splices back ONLY the failing beat's grounded
stitch, in place. A dense interior stop keeps its solo AI-voiced sentences and is
marked ``partially_reverted``; only the specific failing fusion falls back to
stitch. Stop 0 still composes cleanly (its lightly-reworded beat entails).
"""

from __future__ import annotations

from collections import defaultdict

from src.tour.claim_dedup import claims_realized_by
from src.tour.compose import build_compose_request, compose_script_per_chapter
from src.tour.compose_gate import _bad_stops, build_full_verifier, drop_failing_sentences
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


def _poi(pid):
    return POI(id=pid, name=pid, tier=5, poi_role="stop", lat=48.85, lng=2.36)


def _beat(bid, poi_id, claim):
    return BeatRef(id=bid, poi_id=poi_id, script_body=claim,
                   word_count=len(claim.split()), key_claims=(claim,))


def _route(walks):
    pois = tuple(_poi(f"p{i}") for i in range(len(walks)))
    transits = tuple(
        TransitSegment(from_poi_id=None if i == 0 else pois[i - 1].id, to_poi_id=p.id,
                       distance_m=100.0, walk_seconds=walks[i])
        for i, p in enumerate(pois))
    return Route(pois=pois, transits=transits,
                 total_walk_distance_m=100.0 * len(pois), total_walk_seconds=sum(walks))


def _seq(stops):
    return BeatSequence(poi_beats=tuple(
        POIBeats(poi_id=f"p{i}", poi_name=f"p{i}", ordering_strategy="sub_location",
                 beats=tuple(beats))
        for i, beats in enumerate(stops)))


STOP0_CLAIM = "Henri IV completed the Place des Vosges in 1612"


def _uclaim(k: int) -> str:
    """A terse claim whose salient tokens (Figure{k}, Estate{k}, and the 4-digit
    year) are globally UNIQUE, so one stop's claim is never accidentally 'covered'
    by another stop's surviving sentence — cross-claim coverage overlap stays well
    below COVERAGE_MATCH_MIN (the only shared token, 'chartered', gives ~0.25)."""
    return f"Figure{k} chartered Estate{k} in {1500 + k}"


class _StrictHaikuLikeChecker:
    """Entails ONLY when a claim appears near-verbatim (substring) in the
    sentence — the realistic over-rejection of valid paraphrase/fusion."""

    def __init__(self):
        self.calls = []

    def entails(self, key_claims, sentence_text):
        self.calls.append((tuple(key_claims), sentence_text))
        return any(c in sentence_text for c in key_claims)


def _fusing_setup():
    # stop 0: ONE beat (glue-heavy cold open, lightly reworded -> entails).
    # interior stops 1..4: a bold FUSION of two beats (b{i}a + b{i}b) the strict
    # checker over-rejects, PLUS two SOLO beats (b{i}s1, b{i}s2) the compose rewords
    # cleanly (claim kept as a substring -> entails, survive). The surgical repair
    # must restore ONLY the fused pair and KEEP both solos' AI-voiced sentences.
    stops = [[_beat("b0", "p0", STOP0_CLAIM)]]
    for i in range(1, 5):
        stops.append([
            _beat(f"b{i}a", f"p{i}", _uclaim(10 * i + 1)),
            _beat(f"b{i}b", f"p{i}", _uclaim(10 * i + 2)),
            _beat(f"b{i}s1", f"p{i}", _uclaim(10 * i + 3)),
            _beat(f"b{i}s2", f"p{i}", _uclaim(10 * i + 4)),
        ])
    seq = _seq(stops)
    route = _route([10, 400, 400, 400, 400])
    stitched = generate(seq, route, TourInput(start=(48.85, 2.36), duration_min=90,
                                              city_slug="paris"))
    assert stitched.validation.passed
    return seq, route, stitched


class _FusingClient:
    """Stop 0: light reword (claim substring kept -> entails). Interior stops:
    FUSE the first two beats into ONE reworded sentence citing both via also_cites,
    quoting no claim verbatim (a bold fusion the strict checker over-rejects), and
    reword each remaining SOLO beat keeping its claim as a substring (-> entails,
    survives). So a dense interior stop has ONE failing fusion + several passing
    composed sentences — exactly the shape the surgical repair must preserve."""

    def compose(self, request, attempt, prev_report):
        stop = next(iter({s.stop_idx for s in request.stitched.script}))
        beat_sents = [s for s in request.stitched.script if s.source_type == "beat"]
        out = [s for s in request.stitched.script if s.source_type != "beat"]
        if stop == 0:
            out += [s.model_copy(update={"text": f"And here: {s.text}"}) for s in beat_sents]
        else:
            a, b, *solos = beat_sents
            out.append(a.model_copy(update={
                "text": f"A bold fused telling at stop {stop}, in fresh words.",
                "source_id": a.source_id, "also_cites": (b.source_id,)}))
            out += [s.model_copy(update={"text": f"Notably, {s.text}."}) for s in solos]
        return tuple(out)


def test_asymmetry_stop0_composed_interior_stops_partially_reverted():
    """The FIXED behavior: stop 0 keeps its AI voice, and every interior stop is now
    PARTIALLY reverted (keeps its solo AI-voiced sentences), NOT wholly flattened.
    The original whole-stop-revert asymmetry is gone."""
    seq, route, stitched = _fusing_setup()
    composed = compose_script_per_chapter(
        stitched, seq, route, client=_FusingClient(),
        faithfulness_checker=_StrictHaikuLikeChecker(), candidates=1)
    status = {r.stop_idx: r.status for r in composed.verify_report}
    assert status[0] == "composed"  # glue-heavy cold open, light reword -> entails
    # The bug (every interior stop reverted_to_stitched) is GONE: each interior stop
    # keeps its solo AI-voiced sentences; only the failing fusion falls back.
    assert all(status[k] == "partially_reverted" for k in range(1, 5)), status


def test_surgical_repair_keeps_passing_sentences_and_covers_failing_beats():
    """THE fix (candidate c), end to end through the REAL compose_script_per_chapter:
    a dense interior stop has ONE bad fusion (dropped) PLUS solo sentences the compose
    voiced cleanly. The surgical repair KEEPS the solos' AI-voiced sentences, restores
    ONLY the failing fused beats to their grounded stitch, and the whole tour still
    PASSES verify. Under the OLD whole-stop revert the solos were lost — so the
    surviving-solo assertions fail RED before the fix and pass after it."""
    seq, route, stitched = _fusing_setup()
    beats_by_id = {b.id: b for plan in seq.poi_beats for b in plan.beats}
    served = compose_script_per_chapter(
        stitched, seq, route, client=_FusingClient(),
        faithfulness_checker=_StrictHaikuLikeChecker(), candidates=1)

    # 1) the served tour verifies — the surgical result is itself verified, not assumed.
    assert served.validation.passed

    # 2) every SOLO's AI-voiced (reworded) sentence SURVIVES: 2 per interior stop.
    notably = [s for s in served.script if s.text.startswith("Notably,")]
    assert len(notably) == 8, [s.text for s in notably]
    for i in range(1, 5):
        assert sum(1 for s in notably if s.stop_idx == i) == 2
    solo_ids = {s.source_id for s in notably}  # the beats kept in the AI voice
    # ...and the failing fusion is gone (never served as ungrounded prose).
    assert not any("bold fused telling" in s.text for s in served.script)

    # 3) NOTHING was lost: every beat's claim is still COVERED — the fused pair via
    #    its restored grounded stitch, the solos via their surviving reworded line.
    realized = claims_realized_by(served, beats_by_id)
    for bid in beats_by_id:
        assert (bid, 0) in realized, bid

    # 4) each interior stop is marked partially_reverted, restoring exactly its 2
    #    fused beats and NOT the solos it kept composed; stop 0 stays fully composed.
    status = {r.stop_idx: r for r in served.verify_report}
    assert status[0].status == "composed"
    for i in range(1, 5):
        st = status[i]
        assert st.status == "partially_reverted"
        assert len(st.restored_beats) == 2
        assert set(st.restored_beats).isdisjoint(solo_ids), st.restored_beats


def test_which_gate_fires_faithfulness_then_coverage_over_rejects_the_fusion():
    """Pinpoints the gate order on the assembled attempt-1 compose:
    FAITHFULNESS rejects each fusion; after drop_failing_sentences the dropped fused
    facts trip COVERAGE. (The surgical repair then restores ONLY those beats' stitch,
    per-beat, instead of reverting the whole stop.)"""
    seq, route, stitched = _fusing_setup()
    beats_by_id = {b.id: b for plan in seq.poi_beats for b in plan.beats}
    client = _FusingClient()
    by_stop = defaultdict(list)
    for s in stitched.script:
        by_stop[s.stop_idx].append(s)
    csents = []
    for k in sorted(by_stop):
        mini = stitched.model_copy(update={"script": tuple(by_stop[k])})
        csents.extend(client.compose(build_compose_request(mini, seq, route), 1, None))
    composed = stitched.model_copy(update={"script": tuple(csents)})

    verify = build_full_verifier(
        seq, beats_by_id, faithfulness_checker=_StrictHaikuLikeChecker(),
        expected_claim_ids=claims_realized_by(stitched, beats_by_id))
    report = verify(composed)

    # 1) faithfulness fires at every interior stop; stop 0 is clean.
    faith_stops = {s.stop_idx for s, _ in report.faithfulness_failures}
    assert faith_stops == {1, 2, 3, 4}
    assert _bad_stops(report, stitched) == {1, 2, 3, 4}

    # 2) dropping the failing fused sentences uncovers the fused pair's claims ->
    #    coverage fails; the surgical repair keys off exactly these uncovered beats.
    trimmed = drop_failing_sentences(composed, report)
    tr = verify(trimmed)
    assert not tr.passed
    assert tr.coverage_failures  # the dropped facts are now uncovered
    # EXACTLY the fused pair at each stop is uncovered — the solos' reworded
    # sentences still cover them (generate may reorder beats within a stop, so read
    # the fused pair off the compose's also_cites rather than assuming an order).
    uncovered = {bid for bid, _c in tr.coverage_failures}
    fused = {bid for s in composed.script if s.also_cites for bid in s.cited_beat_ids}
    assert uncovered == fused
    assert len(uncovered) == 8  # 2 fused beats x 4 interior stops
