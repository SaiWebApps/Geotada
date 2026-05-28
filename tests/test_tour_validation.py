"""Phase 3 — validation.py: source-traceability + forbidden-phrase scan."""

from __future__ import annotations

import datetime as _dt

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
from src.tour.generation import (
    GLUE_CLOSING,
    GLUE_NAV,
    GLUE_PACING,
    SYNTHESIZED_OPENER,
)
from src.tour.validation import validate_script

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _beat(bid: str, *, body: str, lenses: tuple[str, ...] = ()) -> BeatRef:
    return BeatRef(
        id=bid,
        poi_id="p1",
        word_count=len(body.split()),
        lenses=lenses,
        script_body=body,
    )


def _seq(beats: list[BeatRef]) -> BeatSequence:
    return BeatSequence(
        poi_beats=(
            POIBeats(
                poi_id="p1",
                poi_name="Place des Vosges",
                ordering_strategy="trigger_address",
                beats=tuple(beats),
            ),
        )
    )


def _input() -> TourInput:
    return TourInput(
        start=(48.8555, 2.3656),
        duration_min=60,
        city_slug="paris",
        round_trip=True,
    )


def _script(sentences: list[Sentence]) -> Script:
    return Script(
        city_slug="paris",
        generated_at=_dt.datetime(2026, 4, 28, tzinfo=_dt.UTC).isoformat(),
        inputs=_input(),
        total_audio_seconds=0,
        total_walking_seconds=0,
        total_walk_distance_m=0,
        total_planned_seconds=0,
        selected_pois=(
            ScriptPOI(
                id="p1", name="Place des Vosges", tier=5, lat=48.85, lng=2.36, area="Le Marais"
            ),
        ),
        lens_coverage={},
        script=tuple(sentences),
        validation=ValidationReport(),
    )


# ---------------------------------------------------------------------------
# Source-traceability
# ---------------------------------------------------------------------------


def test_traceable_beat_sentence_passes():
    beat = _beat("b1", body="Henri IV built it.")
    seq = _seq([beat])
    s = Sentence(text="Henri IV built it.", source_id=beat.id, source_type="beat", stop_idx=0)
    report = validate_script(_script([s]), seq)
    assert report.untraceable_sentences == ()
    assert report.passed


def test_unknown_beat_id_is_untraceable():
    beat = _beat("real", body="Real beat.")
    seq = _seq([beat])
    bad = Sentence(text="Spurious.", source_id="not-a-real-id", source_type="beat", stop_idx=0)
    report = validate_script(_script([bad]), seq)
    assert any(s.source_id == "not-a-real-id" for s in report.untraceable_sentences)


def test_glue_with_unknown_label_is_untraceable():
    beat = _beat("b1", body="Cite this.")
    seq = _seq([beat])
    bad = Sentence(text="Walk on.", source_id="GLUE_BOGUS", source_type="glue", stop_idx=0)
    report = validate_script(_script([bad]), seq)
    assert any(s.source_id == "GLUE_BOGUS" for s in report.untraceable_sentences)


def test_glue_with_whitelisted_label_passes():
    beat = _beat("b1", body="Cite this.")
    seq = _seq([beat])
    ok = [
        Sentence(text="Walk on.", source_id=GLUE_NAV, source_type="glue", stop_idx=0),
        Sentence(text="Settle in.", source_id=GLUE_PACING, source_type="glue", stop_idx=0),
        Sentence(text="End the walk here.", source_id=GLUE_CLOSING, source_type="glue", stop_idx=0),
    ]
    report = validate_script(_script(ok), seq)
    assert report.untraceable_sentences == ()


# ---------------------------------------------------------------------------
# Forbidden phrases — only scan glue, not beats
# ---------------------------------------------------------------------------


def test_imagine_in_glue_is_flagged():
    beat = _beat("b1", body="A history beat.")
    seq = _seq([beat])
    bad = Sentence(
        text="Imagine the river flowing here.",
        source_id=GLUE_NAV,
        source_type="glue",
        stop_idx=0,
    )
    report = validate_script(_script([bad]), seq)
    hit_codes = [code for _, code in report.forbidden_phrase_hits]
    assert any(c == "forbidden_phrase:imagine" for c in hit_codes)
    assert not report.passed


def test_picture_this_in_glue_is_flagged():
    beat = _beat("b1", body="A history beat.")
    seq = _seq([beat])
    bad = Sentence(
        text="Picture this scene.",
        source_id=GLUE_NAV,
        source_type="glue",
        stop_idx=0,
    )
    report = validate_script(_script([bad]), seq)
    codes = [code for _, code in report.forbidden_phrase_hits]
    assert any(c == "forbidden_phrase:picture this" for c in codes)


def test_imagine_inside_beat_body_is_not_flagged():
    # Corpus is canonical; only glue is scanned for forbidden phrases.
    beat = _beat("b1", body="Hugo asked the reader to imagine the cathedral aflame.")
    seq = _seq([beat])
    s = Sentence(
        text="Hugo asked the reader to imagine the cathedral aflame.",
        source_id=beat.id,
        source_type="beat",
        stop_idx=0,
    )
    report = validate_script(_script([s]), seq)
    assert report.forbidden_phrase_hits == ()


# ---------------------------------------------------------------------------
# Proper-noun + year leakage in glue
# ---------------------------------------------------------------------------


def test_glue_introducing_proper_noun_not_in_beats_is_flagged():
    # Beats don't mention "Napoleon" — glue tries to.
    beat = _beat("b1", body="Henri IV built it.")
    seq = _seq([beat])
    bad = Sentence(
        text="Walk past the statue of Napoleon ahead.",
        source_id=GLUE_NAV,
        source_type="glue",
        stop_idx=0,
    )
    report = validate_script(_script([bad]), seq)
    codes = [code for _, code in report.forbidden_phrase_hits]
    assert any(c == "new_proper_noun:Napoleon" for c in codes)


def test_glue_naming_a_proper_noun_already_in_beats_is_ok():
    beat = _beat("b1", body="Hugo lived at no. 6 from 1832.")
    seq = _seq([beat])
    s = Sentence(text="Hugo's house was here.", source_id=GLUE_NAV, source_type="glue", stop_idx=0)
    cited_beat_sentence = Sentence(
        text="Hugo lived at no. 6 from 1832.", source_id=beat.id, source_type="beat", stop_idx=0
    )
    report = validate_script(_script([cited_beat_sentence, s]), seq)
    # No new_proper_noun hits — Hugo is in cited corpus.
    codes = [c for _, c in report.forbidden_phrase_hits]
    assert not any(c == "new_proper_noun:Hugo" for c in codes)


def test_glue_introducing_new_year_is_flagged():
    beat = _beat("b1", body="Henri IV built it in 1612.")
    seq = _seq([beat])
    cited = Sentence(
        text="Henri IV built it in 1612.", source_id=beat.id, source_type="beat", stop_idx=0
    )
    bad = Sentence(text="That was 1789.", source_id=GLUE_NAV, source_type="glue", stop_idx=0)
    report = validate_script(_script([cited, bad]), seq)
    codes = [c for _, c in report.forbidden_phrase_hits]
    assert any(c == "new_year:1789" for c in codes)


def test_glue_referring_to_year_already_in_beats_passes():
    beat = _beat("b1", body="Henri IV built it in 1612.")
    seq = _seq([beat])
    cited = Sentence(
        text="Henri IV built it in 1612.", source_id=beat.id, source_type="beat", stop_idx=0
    )
    glue = Sentence(text="That was 1612.", source_id="ARITH", source_type="arith", stop_idx=0)
    report = validate_script(_script([cited, glue]), seq)
    codes = [c for _, c in report.forbidden_phrase_hits]
    assert not any(c.startswith("new_year:") for c in codes)


# ---------------------------------------------------------------------------
# Realistic mixed cases
# ---------------------------------------------------------------------------


def test_clean_script_passes_both_gates():
    beat = _beat("b1", body="Henri IV built the square. The inauguration was in 1612.")
    seq = _seq([beat])
    sentences = [
        Sentence(text="Settle in.", source_id=GLUE_PACING, source_type="glue", stop_idx=0),
        Sentence(
            text="Henri IV built the square.", source_id=beat.id, source_type="beat", stop_idx=0
        ),
        Sentence(
            text="The inauguration was in 1612.", source_id=beat.id, source_type="beat", stop_idx=0
        ),
        Sentence(
            text="You've now circled the square.",
            source_id=GLUE_CLOSING,
            source_type="glue",
            stop_idx=0,
        ),
    ]
    report = validate_script(_script(sentences), seq)
    assert report.passed


def test_synthesized_opener_pointing_at_poi_name_is_traceable():
    beat = _beat("b1", body="The cathedral is Gothic.")
    seq = _seq([beat])
    syn = Sentence(
        text="You're standing at Place des Vosges.",
        source_id=SYNTHESIZED_OPENER,
        source_type="glue",
        stop_idx=0,
    )
    report = validate_script(_script([syn]), seq)
    # POI name itself is canonical — included via _cited_beat_corpus_text
    # so "Place" / "Vosges" are not flagged.
    codes = [c for _, c in report.forbidden_phrase_hits]
    assert not any("new_proper_noun" in c for c in codes)
    assert syn not in report.untraceable_sentences
