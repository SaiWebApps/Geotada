"""M7 VERIFY — rapidfuzz provenance + faithfulness entailment. Hermetic.

PROVE: a beat whose source_passage is verbatim in its chunk passes; a
fabricated/wrong-chunk passage fails with its score; beats without
provenance are skipped (corpus not backfilled). Faithfulness: a stub that
rejects a claim flags exactly that beat-cited sentence; the Mock default
trusts the corpus.
"""

from __future__ import annotations

from src.tour.contract import (
    BeatRef,
    BeatSequence,
    POIBeats,
    Script,
    ScriptPOI,
    Sentence,
    TourInput,
    ValidationReport,
)
from src.tour.verify import (
    PROVENANCE_MATCH_THRESHOLD,
    MockFaithfulnessChecker,
    verify_faithfulness,
    verify_provenance,
)

CHUNK = (
    "The square was commissioned by Henri IV and completed in 1612. "
    "It was the first planned square in Paris, originally the Place Royale, "
    "and Victor Hugo lived at number 6 from 1832 to 1848."
)


def _beat(bid: str, **overrides) -> BeatRef:
    base = {"id": bid, "poi_id": "p1"}
    base.update(overrides)
    return BeatRef(**base)


def _seq(beats: list[BeatRef]) -> BeatSequence:
    return BeatSequence(
        poi_beats=(
            POIBeats(poi_id="p1", poi_name="Place des Vosges",
                     ordering_strategy="trigger_address", beats=tuple(beats)),
        )
    )


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


def test_verbatim_passage_passes_provenance():
    beat = _beat("b1", source_passage="completed in 1612", source_chunk_slug="vosges")
    fails = verify_provenance(_seq([beat]), {"vosges": CHUNK})
    assert fails == []


def test_lightly_drifted_passage_still_passes():
    # punctuation/whitespace drift — partial_ratio is substring-tolerant
    beat = _beat("b1", source_passage="completed  in 1612.", source_chunk_slug="vosges")
    fails = verify_provenance(_seq([beat]), {"vosges": CHUNK})
    assert fails == []


def test_fabricated_passage_fails_with_low_score():
    beat = _beat(
        "b1",
        source_passage="Napoleon was crowned emperor on this very spot in 1804",
        source_chunk_slug="vosges",
    )
    fails = verify_provenance(_seq([beat]), {"vosges": CHUNK})
    assert len(fails) == 1
    bid, score = fails[0]
    assert bid == "b1"
    assert score < PROVENANCE_MATCH_THRESHOLD


def test_missing_chunk_fails_at_zero():
    beat = _beat("b1", source_passage="anything", source_chunk_slug="not-loaded")
    fails = verify_provenance(_seq([beat]), {"vosges": CHUNK})
    assert fails == [("b1", 0.0)]


def test_beat_without_provenance_is_skipped():
    # The current corpus state: no source_passage → nothing to check.
    plain = _beat("b1", script_body="Henri IV built it.")
    fails = verify_provenance(_seq([plain]), {"vosges": CHUNK})
    assert fails == []


# ---------------------------------------------------------------------------
# Faithfulness
# ---------------------------------------------------------------------------


def _script(sentences: list[Sentence]) -> Script:
    return Script(
        city_slug="paris", generated_at="2026-06-12T00:00:00Z",
        inputs=TourInput(start=(48.85, 2.36), duration_min=60, city_slug="paris"),
        total_audio_seconds=0, total_walking_seconds=0, total_walk_distance_m=0,
        total_planned_seconds=0,
        selected_pois=(ScriptPOI(id="p1", name="PdV", tier=5, lat=48.85, lng=2.36),),
        lens_coverage={}, script=tuple(sentences), validation=ValidationReport(),
    )


class _RejectingChecker:
    """Rejects any sentence containing a banned token."""

    def __init__(self, banned: str):
        self.banned = banned
        self.calls = 0

    def entails(self, key_claims, sentence_text):
        self.calls += 1
        return self.banned not in sentence_text


def test_unfaithful_sentence_is_flagged():
    beat = _beat("b1", key_claims=("Henri IV built it", "completed 1612"))
    beats_by_id = {"b1": beat}
    good = Sentence(text="Henri IV built the square.", source_id="b1",
                    source_type="beat", stop_idx=0)
    bad = Sentence(text="Aliens built the square.", source_id="b1",
                   source_type="beat", stop_idx=0)
    fails = verify_faithfulness(_script([good, bad]), beats_by_id,
                                _RejectingChecker("Aliens"))
    assert len(fails) == 1
    assert fails[0][0] is bad
    assert fails[0][1] == "unfaithful:b1"


def test_mock_checker_trusts_corpus_and_records_calls():
    beat = _beat("b1", key_claims=("a claim",))
    checker = MockFaithfulnessChecker()
    s = Sentence(text="A beat sentence.", source_id="b1", source_type="beat", stop_idx=0)
    fails = verify_faithfulness(_script([s]), {"b1": beat}, checker)
    assert fails == []
    assert len(checker.calls) == 1  # one entailment call for the one beat sentence


def test_glue_sentences_and_claimless_beats_skip_entailment():
    beat_no_claims = _beat("b1")  # no key_claims
    checker = MockFaithfulnessChecker()
    sentences = [
        Sentence(text="Walk on.", source_id="GLUE_NAV", source_type="glue", stop_idx=0),
        Sentence(text="A beat sentence.", source_id="b1", source_type="beat", stop_idx=0),
    ]
    fails = verify_faithfulness(_script(sentences), {"b1": beat_no_claims}, checker)
    assert fails == []
    assert checker.calls == []  # glue skipped, claimless beat skipped


def test_validation_report_passed_gates_on_new_teeth():
    base = ValidationReport()
    assert base.passed
    assert not ValidationReport(provenance_failures=(("b1", 12.0),)).passed
    s = Sentence(text="x", source_id="b1", source_type="beat", stop_idx=0)
    assert not ValidationReport(faithfulness_failures=((s, "unfaithful:b1"),)).passed
