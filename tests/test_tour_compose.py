"""Phase 4 Step 4.3 — ComposeRequest + MockComposeClient.

The stitched Script comes from the REAL generate() (MockGlueClient), so the
mock composer is exercised against actual stitcher shapes: cold-open, GLUE_NAV
transits, corpus transit beats, anchor blocks.
"""

from __future__ import annotations

from src.tour.compose import MockComposeClient, build_compose_request
from src.tour.compose_gate import build_full_verifier
from src.tour.contract import (
    POI,
    BeatRef,
    BeatSequence,
    POIBeats,
    Route,
    TourInput,
    TransitSegment,
)
from src.tour.generation import GLUE_NAV, GLUE_REFLECTION, generate

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _poi(pid: str) -> POI:
    return POI(id=pid, name=pid, tier=5, poi_role="stop", lat=48.85, lng=2.36)


def _claim_beat(bid: str, poi_id: str, claim: str | None, **kwargs) -> BeatRef:
    """A beat whose script_body IS its key claim — so a strict verbatim
    checker can entail both the beat sentence and a reflection quoting it."""
    body = kwargs.pop("body", claim or "A plain fact with no claim.")
    return BeatRef(
        id=bid,
        poi_id=poi_id,
        script_body=body,
        word_count=len(body.split()),
        key_claims=(claim,) if claim else (),
        **kwargs,
    )


def _route(walks: list[int]) -> Route:
    pois = tuple(_poi(f"p{i}") for i in range(len(walks)))
    transits = tuple(
        TransitSegment(
            from_poi_id=None if i == 0 else pois[i - 1].id,
            to_poi_id=p.id,
            distance_m=100.0,
            walk_seconds=walks[i],
        )
        for i, p in enumerate(pois)
    )
    return Route(
        pois=pois,
        transits=transits,
        total_walk_distance_m=100.0 * len(pois),
        total_walk_seconds=sum(walks),
        audio_budget_seconds=3600,
    )


def _seq(stops: list[list[BeatRef]]) -> BeatSequence:
    return BeatSequence(
        poi_beats=tuple(
            POIBeats(
                poi_id=f"p{i}",
                poi_name=f"p{i}",
                ordering_strategy="sub_location",
                beats=tuple(beats),
            )
            for i, beats in enumerate(stops)
        )
    )


def _input() -> TourInput:
    return TourInput(start=(48.85, 2.36), duration_min=60, city_slug="paris")


CLAIM_A = "Henri IV completed the square in 1612"
CLAIM_B = "Victor Hugo lived at number 6"


def _five_stop_setup() -> tuple:
    """5 stops; legs into 1 and 3 are long -> slots (1, 3). Claims at stops
    0 (A) and 1 (B); stops 2-4 claimless."""
    seq = _seq(
        [
            [_claim_beat("b0", "p0", CLAIM_A)],
            [_claim_beat("b1", "p1", CLAIM_B)],
            [_claim_beat("b2", "p2", None)],
            [_claim_beat("b3", "p3", None)],
            [_claim_beat("b4", "p4", None)],
        ]
    )
    route = _route([10, 400, 10, 400, 10])
    stitched = generate(seq, route, _input())
    assert stitched.validation.passed  # sanity: the baseline is clean
    return seq, route, stitched


# ---------------------------------------------------------------------------
# build_compose_request
# ---------------------------------------------------------------------------


def test_request_computes_slots_and_visited_claim_unions():
    seq, route, stitched = _five_stop_setup()
    request = build_compose_request(stitched, seq, route)
    assert request.slots == (1, 3)
    assert request.visited_claims_by_slot[1] == (CLAIM_A,)
    assert request.visited_claims_by_slot[3] == (CLAIM_A, CLAIM_B)


def test_empty_union_slot_is_dropped_fail_closed():
    # Only eligible leg is into stop 1, but stop 0 carries NO claims.
    seq = _seq(
        [
            [_claim_beat("b0", "p0", None)],
            [_claim_beat("b1", "p1", None)],
        ]
    )
    route = _route([10, 400])
    stitched = generate(seq, route, _input())
    request = build_compose_request(stitched, seq, route)
    assert request.slots == ()
    composed = MockComposeClient().compose(request, 1, None)
    assert composed == stitched.script  # nothing added, nothing lost


# ---------------------------------------------------------------------------
# MockComposeClient
# ---------------------------------------------------------------------------


def test_mock_preserves_every_stitched_sentence_in_order():
    seq, route, stitched = _five_stop_setup()
    request = build_compose_request(stitched, seq, route)
    composed = MockComposeClient().compose(request, 1, None)
    without_reflections = tuple(s for s in composed if s.source_id != GLUE_REFLECTION)
    assert without_reflections == stitched.script


def test_mock_inserts_one_reflection_per_slot_after_the_transit_glue():
    seq, route, stitched = _five_stop_setup()
    request = build_compose_request(stitched, seq, route)
    composed = list(MockComposeClient().compose(request, 1, None))

    reflections = [s for s in composed if s.source_id == GLUE_REFLECTION]
    assert [s.stop_idx for s in reflections] == [1, 3]
    for r in reflections:
        i = composed.index(r)
        before, after = composed[i - 1], composed[i + 1]
        # Right after the leg's GLUE_NAV line...
        assert before.source_id == GLUE_NAV and before.stop_idx == r.stop_idx
        # ...and before the stop's anchor beats.
        assert after.source_type == "beat" and after.stop_idx == r.stop_idx
    # The slot-1 reflection quotes the visited claim verbatim.
    assert CLAIM_A in reflections[0].text


def test_mock_inserts_after_a_corpus_transit_beat_run():
    """When the leg's opener is a corpus transit BEAT (not glue), the
    reflection lands after its sentences, before the anchor block."""
    transit = _claim_beat(
        "t1",
        "p1",
        None,
        body="Leave p0 and follow the quay toward p1.",
        narrative_function="transition",
        trigger_address="from p0",
    )
    seq = _seq(
        [
            [_claim_beat("b0", "p0", CLAIM_A)],
            [transit, _claim_beat("b1", "p1", None)],
        ]
    )
    route = _route([10, 400])
    stitched = generate(seq, route, _input())
    request = build_compose_request(stitched, seq, route)
    composed = list(MockComposeClient().compose(request, 1, None))

    (reflection,) = [s for s in composed if s.source_id == GLUE_REFLECTION]
    i = composed.index(reflection)
    assert composed[i - 1].source_id == "t1"  # the transit beat's last sentence
    assert composed[i + 1].source_id == "b1"  # the anchor block follows


def test_composed_script_passes_the_full_verifier_with_a_strict_checker():
    """End-to-end tooth: validate_script + provenance + a STRICT verbatim
    entailment checker all pass on the mock-composed output."""

    class StrictVerbatimChecker:
        def entails(self, key_claims, sentence_text):
            return any(c in sentence_text for c in key_claims)

    seq, route, stitched = _five_stop_setup()
    request = build_compose_request(stitched, seq, route)
    composed = MockComposeClient().compose(request, 1, None)
    script = stitched.model_copy(update={"script": composed})

    verify = build_full_verifier(
        seq, request.beats_by_id, faithfulness_checker=StrictVerbatimChecker()
    )
    report = verify(script)
    assert report.passed, (
        report.untraceable_sentences,
        report.forbidden_phrase_hits,
        report.faithfulness_failures,
    )


def test_mock_records_attempt_and_prev_report():
    seq, route, stitched = _five_stop_setup()
    request = build_compose_request(stitched, seq, route)
    client = MockComposeClient()
    client.compose(request, 1, None)
    marker = stitched.validation
    client.compose(request, 2, marker)
    assert client.calls == [(1, None), (2, marker)]
