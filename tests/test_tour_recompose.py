"""M7 — recompose-once-then-block gate. Hermetic, no LLM.

PROVE (IMPLEMENTATION-PLAN M7): a stub that emits one untraceable sentence
on attempt 1 and a clean Script on attempt 2 → COMPOSE called exactly 2x,
audio invoked 0 while failing and 1 after pass; a stub that always fails →
trip blocked (raises) and audio invoked 0.
"""

from __future__ import annotations

import pytest

from src.tour.compose_gate import (
    MAX_COMPOSE_ATTEMPTS,
    ComposeVerificationError,
    build_full_verifier,
    compose_and_verify,
    serve_or_block,
)
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

BEAT = BeatRef(id="b1", poi_id="p1", script_body="Henri IV built it.")
SEQ = BeatSequence(
    poi_beats=(
        POIBeats(poi_id="p1", poi_name="Place des Vosges",
                 ordering_strategy="trigger_address", beats=(BEAT,)),
    )
)
BEATS_BY_ID = {"b1": BEAT}


def _script(sentences: list[Sentence]) -> Script:
    return Script(
        city_slug="paris", generated_at="2026-06-12T00:00:00Z",
        inputs=TourInput(start=(48.85, 2.36), duration_min=60, city_slug="paris"),
        total_audio_seconds=0, total_walking_seconds=0, total_walk_distance_m=0,
        total_planned_seconds=0,
        selected_pois=(ScriptPOI(id="p1", name="PdV", tier=5, lat=48.85, lng=2.36),),
        lens_coverage={}, script=tuple(sentences), validation=ValidationReport(),
    )


_CLEAN = _script([Sentence(text="Henri IV built it.", source_id="b1",
                           source_type="beat", stop_idx=0)])
_DIRTY = _script([Sentence(text="Spurious.", source_id="ghost-beat",
                           source_type="beat", stop_idx=0)])  # untraceable id


def _verify():
    return build_full_verifier(SEQ, BEATS_BY_ID)


def test_recompose_once_then_serves():
    composes: list[int] = []
    audio: list[Script] = []

    def compose(attempt, prev):
        composes.append(attempt)
        assert (prev is None) == (attempt == 1)  # prior report handed to recompose
        return _DIRTY if attempt == 1 else _CLEAN

    result = serve_or_block(compose, _verify(), on_serve=audio.append)

    assert composes == [1, 2]          # exactly one recompose
    assert len(audio) == 1             # audio invoked once, only after the pass
    assert result.validation.passed
    assert audio[0] is result


def test_still_failing_blocks_audio_and_refuses():
    composes: list[int] = []
    audio: list[Script] = []

    def compose(attempt, prev):
        composes.append(attempt)
        return _DIRTY  # never recovers

    with pytest.raises(ComposeVerificationError) as exc:
        serve_or_block(compose, _verify(), on_serve=audio.append)

    assert composes == [1, 2]                       # bounded: exactly 2 attempts
    assert len(composes) == MAX_COMPOSE_ATTEMPTS
    assert audio == []                              # audio NEVER invoked while failing
    assert exc.value.attempts == MAX_COMPOSE_ATTEMPTS
    assert len(exc.value.report.untraceable_sentences) == 1


def test_first_attempt_clean_does_not_recompose():
    composes: list[int] = []
    audio: list[Script] = []

    def compose(attempt, prev):
        composes.append(attempt)
        return _CLEAN

    serve_or_block(compose, _verify(), on_serve=audio.append)
    assert composes == [1]   # no needless recompose
    assert len(audio) == 1


def test_gate_recovers_from_a_provenance_failure_on_recompose():
    """The recompose path covers VERIFY's teeth too, not just traceability:
    attempt 1 cites a beat whose stored passage isn't in the chunk; attempt 2
    drops it."""
    chunk = {"vosges": "Henri IV commissioned the square, completed in 1612."}
    prov_beat = BeatRef(id="bp", poi_id="p1", script_body="x",
                        source_passage="Fabricated coronation of Napoleon in 1804",
                        source_chunk_slug="vosges")
    seq = BeatSequence(
        poi_beats=(POIBeats(poi_id="p1", poi_name="PdV",
                            ordering_strategy="trigger_address", beats=(prov_beat,)),)
    )
    verify = build_full_verifier(seq, {"bp": prov_beat}, chunk_text_by_slug=chunk)
    clean = _script([Sentence(text="A line.", source_id="GLUE_NAV",
                              source_type="glue", stop_idx=0)])

    # First verify sees the provenance failure regardless of the script's
    # sentences (provenance is over the beat_sequence).
    report = verify(clean)
    assert not report.passed
    assert report.provenance_failures and report.provenance_failures[0][0] == "bp"

    # A recompose that swaps to a clean sequence (no bad-provenance beat) passes.
    clean_verify = build_full_verifier(SEQ, BEATS_BY_ID)
    composes: list[int] = []

    def compose(attempt, prev):
        composes.append(attempt)
        return clean  # the script; the verifier swap models dropping the bad beat

    def verify_switch(script):
        return (verify if composes[-1] == 1 else clean_verify)(script)

    result = compose_and_verify(compose, verify_switch)
    assert composes == [1, 2]
    assert result.validation.passed
