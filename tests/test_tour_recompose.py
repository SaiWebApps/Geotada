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
    drop_failing_sentences,
    repair_composed,
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


def test_full_verifier_without_chunks_skips_provenance_for_backfilled_beats():
    """Step 4.0 backfilled source_passage onto live beats; with NO chunk
    library loaded the provenance check must be a no-op (as documented),
    not a 0.0 failure for every provenanced beat."""
    beat = BeatRef(
        id="b1",
        poi_id="p1",
        script_body="A fact.",
        source_passage="A fact from the book.",
        source_chunk_slug="book-chunk-01",
    )
    seq = BeatSequence(
        poi_beats=(
            POIBeats(
                poi_id="p1", poi_name="P1", ordering_strategy="sub_location", beats=(beat,)
            ),
        )
    )
    script = _script([Sentence(text="A fact.", source_id="b1", source_type="beat", stop_idx=0)])

    no_chunks = build_full_verifier(seq, {"b1": beat})
    assert no_chunks(script).provenance_failures == ()

    # With a chunk library loaded, a slug it cannot confirm still fails.
    wrong_chunks = build_full_verifier(seq, {"b1": beat}, chunk_text_by_slug={"other": "text"})
    assert wrong_chunks(script).provenance_failures == (("b1", 0.0),)


# ---------------------------------------------------------------------------
# Graceful per-stop repair: a partly-embellished compose still ships its good
# stops (grounded fallback for the failed ones) instead of a whole-tour refusal.
# ---------------------------------------------------------------------------

_B2 = BeatRef(id="b2", poi_id="p2", script_body="Hugo lived here.")
_SEQ2 = BeatSequence(
    poi_beats=(
        POIBeats(poi_id="p1", poi_name="A", ordering_strategy="trigger_address", beats=(BEAT,)),
        POIBeats(poi_id="p2", poi_name="B", ordering_strategy="trigger_address", beats=(_B2,)),
    )
)
_BEATS2 = {"b1": BEAT, "b2": _B2}


def _s(text: str, sid: str, stop: int, stype: str = "beat") -> Sentence:
    return Sentence(text=text, source_id=sid, source_type=stype, stop_idx=stop)


def test_repair_reverts_only_the_failed_stop():
    stitched = _script([_s("Henri IV built it.", "b1", 0), _s("Hugo lived here.", "b2", 1)])
    composed = _script([_s("Grandly, Henri IV built it.", "b1", 0), _s("Spurious.", "ghost", 1)])
    verify = build_full_verifier(_SEQ2, _BEATS2)
    report = verify(composed)
    assert not report.passed  # stop 1 cites an untraceable id
    repaired = repair_composed(composed, stitched, report)
    texts = {s.text for s in repaired.script}
    assert "Grandly, Henri IV built it." in texts  # good stop 0: composed (fused) KEPT
    assert "Hugo lived here." in texts              # bad stop 1: reverted to stitched
    assert "Spurious." not in texts                 # the failing sentence is gone
    assert verify(repaired).passed                  # the repaired tour verifies


def test_repair_is_a_noop_when_nothing_failed():
    composed = _script([_s("Henri IV built it.", "b1", 0)])
    verify = build_full_verifier(SEQ, BEATS_BY_ID)
    report = verify(composed)
    assert report.passed
    assert repair_composed(composed, composed, report) is composed


def test_compose_and_verify_repairs_a_bad_stop_and_serves():
    stitched = _script([_s("Henri IV built it.", "b1", 0), _s("Hugo lived here.", "b2", 1)])

    def compose(attempt, prev):  # never recovers stop 1 on its own
        return _script([_s("Grandly, Henri IV built it.", "b1", 0), _s("Spurious.", "ghost", 1)])

    verify = build_full_verifier(_SEQ2, _BEATS2)
    result = compose_and_verify(
        compose, verify, repair=lambda comp, rep: repair_composed(comp, stitched, rep)
    )
    assert result.validation.passed  # SERVED via repair, not refused
    texts = {s.text for s in result.script}
    assert "Grandly, Henri IV built it." in texts  # fused good stop kept
    assert "Hugo lived here." in texts and "Spurious." not in texts  # bad stop grounded


def test_compose_and_verify_still_refuses_when_repair_cannot_help():
    # No repair callback -> a persistently failing compose still refuses (bounded).
    def compose(attempt, prev):
        return _DIRTY

    with pytest.raises(ComposeVerificationError):
        compose_and_verify(compose, _verify())


def test_drop_failing_sentences_removes_only_the_flagged():
    keep = _s("A grounded, faithful fact.", "b1", 0)
    bad_reflection = Sentence(text="An embellished aside.", source_id="GLUE_REFLECTION",
                              source_type="glue", stop_idx=0)
    kept_glue = Sentence(text="Walk on.", source_id="GLUE_NAV", source_type="glue", stop_idx=0)
    script = _script([keep, bad_reflection, kept_glue])
    report = ValidationReport(faithfulness_failures=((bad_reflection, "unfaithful_reflection"),))
    out = drop_failing_sentences(script, report)
    texts = [s.text for s in out.script]
    assert "A grounded, faithful fact." in texts  # good beat prose kept
    assert "Walk on." in texts                    # unrelated glue kept
    assert "An embellished aside." not in texts   # only the flagged one dropped


def test_drop_failing_sentences_is_a_noop_when_clean():
    script = _script([_s("A grounded fact.", "b1", 0)])
    assert drop_failing_sentences(script, ValidationReport()) is script
