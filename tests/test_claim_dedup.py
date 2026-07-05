"""Unit tests for route-level claim-repetition suppression (backlog #22).

Fixtures mirror the live Île de la Cité case: three beats from three source books
each narrate the Parisii founding; a fourth (the Nanterre debate) merely mentions
the Parisii and must survive. Only a PURE restatement is dropped — a compound
sentence carrying a novel fact alongside a repeated one is kept whole (the
content-safety property the skeptic panel demanded).
"""

from __future__ import annotations

from src.tour.claim_dedup import _signature, suppress_repeated_claims
from src.tour.contract import BeatRef, BeatSequence, POIBeats, Sentence


def _beat(bid: str, claims: tuple[str, ...]) -> BeatRef:
    return BeatRef(id=bid, poi_id="ile", key_claims=claims)


def _seq(*beats: BeatRef) -> BeatSequence:
    return BeatSequence(
        poi_beats=(POIBeats(poi_id="ile", poi_name="Ile", ordering_strategy="narrative_function",
                            beats=tuple(beats)),)
    )


def _s(text: str, source_id: str, source_type: str = "beat") -> Sentence:
    return Sentence(text=text, source_id=source_id, source_type=source_type, stop_idx=0)


# Three founding beats + the distinct Nanterre-debate beat, faithful to the corpus.
B1 = _beat("f052", (
    "Parisii settled 3rd century BC",
    "Louis IX built Sainte-Chapelle 13th century for Crown of Thorns",
))
B2 = _beat("7492", (
    "Parisii Celtic tribe first settled the Île de la Cité in the 3rd century BC",
    "Romans invaded in 52 BC and renamed the city Lutetia, meaning born of the waters",
))
B3 = _beat("ab08", (
    "Settled c. 300 BC by Celtic Parisii",
    "Romans took it 52 BC and built a palace-fortress at the western end",
    "Frankish kings rebuilt palace in 10th century",
))
B4 = _beat("2b7c", (
    "Caesar described Lutetia as fortress of the Parisii situated on an island",
    "Some historians proposed Nanterre as the true Lutetia",
))


def _founding_narration() -> list[Sentence]:
    return [
        _s("Settle in near the Seine.", "GLUE_PACING", "glue"),
        # B1 — first to voice the founding.
        _s("The Ile de la Cite was the first part of Paris to be settled, occupied by the "
           "Celtic tribe of the Parisii in the 3rd century BC, making it the original nucleus.",
           "f052"),
        _s("Louis IX built the Sainte-Chapelle in the 13th century to house the Crown of Thorns.",
           "f052"),
        # B2 — a PURE founding restatement (dropped), then Roman + Lutetia (novel, kept).
        _s("Archaeological evidence suggests that a Celtic tribe called the Parisii first "
           "settled on the Île de la Cité during the 3rd century BC.", "7492"),
        _s("The island was a secure settlement, but no defence could protect the Celts from the "
           "Roman invasion in 52 BC.", "7492"),
        _s("The city, renamed Lutetia, meaning born of the waters, prospered.", "7492"),
        # B3 — a COMPOUND sentence: repeated founding clause + NOVEL palace-fortress fact.
        _s("It was settled around 300 BC by a Celtic tribe called the Parisii, and in 52 BC was "
           "overrun by the Romans, who built a palace-fortress at the western end.", "ab08"),
        _s("Frankish kings rebuilt the palace in the 10th century.", "ab08"),
        # B4 — Nanterre debate; mentions Parisii but is a distinct fact -> survives.
        _s("Others point to Caesar's description: Lutetia, fortress of the Parisii, on an island.",
           "2b7c"),
    ]


def test_pure_founding_restatement_dropped() -> None:
    out = suppress_repeated_claims(_founding_narration(), _seq(B1, B2, B3, B4))
    texts = [s.text for s in out]
    # B1's founding (first occurrence) survives; B2's PURE restatement is dropped.
    assert any("original nucleus" in t for t in texts)
    assert not any("Archaeological evidence" in t for t in texts)


def test_compound_sentence_keeps_novel_fact() -> None:
    # Skeptic-A regression: B3 fuses the repeated founding clause with the NOVEL
    # palace-fortress fact (voiced nowhere else) -> the whole sentence is KEPT.
    out = suppress_repeated_claims(_founding_narration(), _seq(B1, B2, B3, B4))
    texts = [s.text for s in out]
    assert any("palace-fortress" in t for t in texts), "novel compound fact must not be lost"


def test_all_distinct_content_preserved() -> None:
    out = suppress_repeated_claims(_founding_narration(), _seq(B1, B2, B3, B4))
    texts = [s.text for s in out]
    assert any("Crown of Thorns" in t for t in texts)          # B1 Louis IX
    assert any("renamed Lutetia" in t for t in texts)          # B2 Lutetia naming
    assert any("Roman invasion in 52 BC" in t for t in texts)  # B2 Roman conquest
    assert any("Frankish kings" in t for t in texts)           # B3 Frankish palace
    assert any("Caesar's description" in t for t in texts)     # B4 Nanterre debate
    assert any(s.source_type == "glue" for s in out)           # glue untouched


def test_no_beat_is_emptied() -> None:
    out = suppress_repeated_claims(_founding_narration(), _seq(B1, B2, B3, B4))
    emitted = {s.source_id for s in out if s.source_type == "beat"}
    assert emitted == {"f052", "7492", "ab08", "2b7c"}


def test_single_sentence_repeat_beat_is_restored() -> None:
    # A beat whose ONLY sentence is a pure repeat must NOT vanish (first restored).
    b5 = _beat("dupe", ("Parisii settled 3rd century BC",))
    seq = _seq(B1, b5)
    sents = [
        _s("Parisii settled the Île de la Cité in the 3rd century BC as the city's nucleus.",
           "f052"),
        _s("The Parisii settled here in the 3rd century BC.", "dupe"),
    ]
    out = suppress_repeated_claims(sents, seq)
    assert {s.source_id for s in out if s.source_type == "beat"} == {"f052", "dupe"}


def test_distinct_claims_untouched() -> None:
    # No repeats -> the list is returned unchanged (same object identity).
    seq = _seq(B1, B4)
    sents = [
        _s("Louis IX built the Sainte-Chapelle for the Crown of Thorns.", "f052"),
        _s("Caesar called Lutetia a fortress of the Parisii on an island.", "2b7c"),
    ]
    out = suppress_repeated_claims(sents, seq)
    assert out is sents


def test_date_canonicalization_unifies_bc_forms() -> None:
    # "300 BC" and "3rd century BC" must land the same century token.
    assert "c3bc" in _signature("settled around 300 BC")
    assert "c3bc" in _signature("the 3rd century BC")
    assert "c1bc" in _signature("Romans invaded in 52 BC")  # 52 BC is the 1st century BC
