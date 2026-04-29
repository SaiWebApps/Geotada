"""Phase 3 — generation.py: deterministic structural assembly + glue routing.

Tests use a MockGlueClient — the LLM is never invoked. The point of
generation is the deterministic shape of the Script; the only LLM-driven
fragments are glue sentences whose category is asserted via mock calls.
"""

from __future__ import annotations

import pytest

from src.tour.contract import (
    BeatRef,
    BeatSequence,
    POI,
    POIBeats,
    Route,
    TourInput,
    TransitSegment,
)
from src.tour.generation import (
    ARITH,
    FORBIDDEN_PHRASES,
    GLUE_CLOSING,
    GLUE_LABELS,
    GLUE_NAV,
    GLUE_PACING,
    GLUE_STAGING,
    SYNTHESIZED_OPENER,
    generate,
    split_sentences,
)
from src.tour.glue_client import MockGlueClient, NO_GLUE_SENTINEL


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _poi(pid: str, name: str | None = None, *, tier: int = 5) -> POI:
    return POI(
        id=pid,
        name=name or pid,
        tier=tier,
        poi_role="stop",
        lat=48.8555,
        lng=2.3656,
        areas=("Le Marais",),
    )


def _beat(
    bid: str,
    poi_id: str,
    *,
    body: str = "",
    nf: str | None = None,
    sub: str | None = None,
    addr: str | None = None,
    lenses: tuple[str, ...] = (),
    word_count: int | None = None,
) -> BeatRef:
    return BeatRef(
        id=bid,
        poi_id=poi_id,
        sub_location=sub,
        trigger_address=addr,
        narrative_function=nf,
        word_count=word_count if word_count is not None else len(body.split()),
        lenses=lenses,
        script_body=body or None,
    )


def _input(round_trip: bool = True, duration: int = 60) -> TourInput:
    return TourInput(
        start=(48.8555, 2.3656),
        duration_min=duration,
        city_slug="paris",
        round_trip=round_trip,
    )


def _route(pois: tuple[POI, ...], duration_min: int = 60) -> Route:
    """Minimal Route: pretend each transit walks 60s for cap-budget arithmetic."""
    transits = tuple(
        TransitSegment(
            from_poi_id=None if i == 0 else pois[i - 1].id,
            to_poi_id=p.id,
            distance_m=100.0,
            walk_seconds=60,
        )
        for i, p in enumerate(pois)
    )
    walk = sum(t.walk_seconds for t in transits)
    return Route(
        pois=pois,
        transits=transits,
        total_walk_distance_m=100.0 * len(pois),
        total_walk_seconds=walk,
        audio_budget_seconds=max(0, duration_min * 60 - walk),
        spine_area="Le Marais",
        target_audio_seconds=duration_min * 30,
        err_short_total_seconds=int(duration_min * 60 * 0.83),
    )


# ---------------------------------------------------------------------------
# Sentence splitter
# ---------------------------------------------------------------------------


def test_split_sentences_basic():
    out = split_sentences("Henri IV built it. The square opened in 1612. Crowds came.")
    assert out == [
        "Henri IV built it.",
        "The square opened in 1612.",
        "Crowds came.",
    ]


def test_split_sentences_keeps_no_dot_address():
    out = split_sentences("Look at no. 6 across the way. Hugo lived there.")
    assert out == [
        "Look at no. 6 across the way.",
        "Hugo lived there.",
    ]


def test_split_sentences_handles_quoted_material():
    out = split_sentences(
        'He wrote "It has to hurt." That was 1752. Brice argued his case.'
    )
    assert "Brice argued his case." in out


def test_split_sentences_empty():
    assert split_sentences("") == []
    assert split_sentences("   ") == []


# ---------------------------------------------------------------------------
# Cold open
# ---------------------------------------------------------------------------


def test_cold_open_uses_stop_orientation_when_present():
    poi = _poi("p1", "Place des Vosges")
    orient = _beat(
        "orient-1",
        poi.id,
        body="Find a bench. Pronounced plass-day-voge.",
        nf="stop_orientation",
    )
    body = _beat("body-1", poi.id, body="Henri IV built the square.", nf="establishing")

    seq = BeatSequence(
        poi_beats=(
            POIBeats(
                poi_id=poi.id,
                poi_name=poi.name,
                ordering_strategy="narrative_function",
                beats=(orient, body),
            ),
        )
    )
    script = generate(seq, _route((poi,)), _input(), glue_client=MockGlueClient())
    cold_open_ids = [s.source_id for s in script.script if s.stop_idx == 0][:3]
    # Pacing glue first, then the orientation beat sentences.
    assert cold_open_ids[0] == GLUE_PACING
    assert orient.id in cold_open_ids
    # Body beat appears later, not consumed twice.
    body_count = sum(1 for s in script.script if s.source_id == body.id)
    assert body_count >= 1


def test_cold_open_synthesizes_when_no_orientation():
    poi = _poi("p1", "Notre-Dame Cathedral")
    body = _beat("body-1", poi.id, body="The cathedral rears up like a great ship.", nf="establishing")
    seq = BeatSequence(
        poi_beats=(
            POIBeats(
                poi_id=poi.id,
                poi_name=poi.name,
                ordering_strategy="sub_location",
                beats=(body,),
            ),
        )
    )
    script = generate(seq, _route((poi,), duration_min=60), _input(round_trip=False), glue_client=MockGlueClient())
    sources = [s.source_id for s in script.script]
    assert SYNTHESIZED_OPENER in sources
    # The synthesized opener mentions the POI name (sentence-start, not flagged).
    synth = next(s for s in script.script if s.source_id == SYNTHESIZED_OPENER)
    assert "Notre-Dame Cathedral" in synth.text


# ---------------------------------------------------------------------------
# Anchor block — orientation not consumed twice
# ---------------------------------------------------------------------------


def test_orientation_beat_not_emitted_twice():
    poi = _poi("p1", "Place des Vosges")
    orient = _beat("orient-1", poi.id, body="Find a bench.", nf="stop_orientation")
    body = _beat("body-1", poi.id, body="Henri IV.", nf="establishing")
    seq = BeatSequence(
        poi_beats=(
            POIBeats(
                poi_id=poi.id,
                poi_name=poi.name,
                ordering_strategy="narrative_function",
                beats=(orient, body),
            ),
        )
    )
    script = generate(seq, _route((poi,)), _input(), glue_client=MockGlueClient())
    orient_count = sum(1 for s in script.script if s.source_id == orient.id)
    # Orientation appears once (during cold open), not in the anchor block again.
    assert orient_count == 1


# ---------------------------------------------------------------------------
# Multi-stop transit routing
# ---------------------------------------------------------------------------


def test_transit_uses_corpus_beat_when_present():
    p1 = _poi("p1", "Pont Neuf")
    p2 = _poi("p2", "Conciergerie")
    orient = _beat("orient-1", p1.id, body="Stand on the bridge.", nf="stop_orientation")
    p1_body = _beat("p1-body", p1.id, body="The Pont Neuf is the oldest stone bridge.")
    p2_transit = _beat(
        "p2-transit",
        p2.id,
        body="Cross the road into place Dauphine. Walk around the Conciergerie.",
        nf="transition",
    )
    p2_body = _beat("p2-body", p2.id, body="The Conciergerie is Paris's oldest prison.")
    seq = BeatSequence(
        poi_beats=(
            POIBeats(
                poi_id=p1.id, poi_name=p1.name, ordering_strategy="narrative_function",
                beats=(orient, p1_body),
            ),
            POIBeats(
                poi_id=p2.id, poi_name=p2.name, ordering_strategy="narrative_function",
                beats=(p2_transit, p2_body),
            ),
        )
    )
    client = MockGlueClient()
    script = generate(seq, _route((p1, p2)), _input(round_trip=False), glue_client=client)
    sources = [s.source_id for s in script.script]
    # The corpus transit beat got cited; Haiku was NOT called for nav glue.
    assert p2_transit.id in sources
    assert not any(c[0] == GLUE_NAV for c in client.calls)


def test_transit_falls_back_to_glue_when_no_corpus_beat():
    p1 = _poi("p1", "Place des Vosges")
    p2 = _poi("p2", "Hôtel de Sully")
    p1_orient = _beat("p1-orient", p1.id, body="Find a bench.", nf="stop_orientation")
    p1_body = _beat("p1-body", p1.id, body="Henri IV built the square.")
    p2_body = _beat("p2-body", p2.id, body="The Hôtel de Sully sits just south.")
    seq = BeatSequence(
        poi_beats=(
            POIBeats(
                poi_id=p1.id, poi_name=p1.name, ordering_strategy="narrative_function",
                beats=(p1_orient, p1_body),
            ),
            POIBeats(
                poi_id=p2.id, poi_name=p2.name, ordering_strategy="narrative_function",
                beats=(p2_body,),
            ),
        )
    )
    client = MockGlueClient(responses={"GLUE_NAV": "Walk south for two minutes."})
    script = generate(seq, _route((p1, p2)), _input(round_trip=False), glue_client=client)
    nav_sentences = [s for s in script.script if s.source_id == GLUE_NAV]
    assert len(nav_sentences) == 1
    assert nav_sentences[0].text == "Walk south for two minutes."
    assert nav_sentences[0].stop_idx == 1
    assert client.calls and client.calls[0][0] == GLUE_NAV


def test_transit_glue_falls_back_to_default_on_no_glue_sentinel():
    p1 = _poi("p1", "Stop A")
    p2 = _poi("p2", "Stop B")
    o = _beat("o", p1.id, body="Settle in.", nf="stop_orientation")
    a = _beat("a", p1.id, body="A history beat.")
    b = _beat("b", p2.id, body="A second history beat.")
    seq = BeatSequence(
        poi_beats=(
            POIBeats(poi_id=p1.id, poi_name=p1.name, ordering_strategy="narrative_function", beats=(o, a)),
            POIBeats(poi_id=p2.id, poi_name=p2.name, ordering_strategy="narrative_function", beats=(b,)),
        )
    )
    client = MockGlueClient(responses={"GLUE_NAV": NO_GLUE_SENTINEL})
    script = generate(seq, _route((p1, p2)), _input(round_trip=False), glue_client=client)
    nav = next(s for s in script.script if s.source_id == GLUE_NAV)
    # Default carries the next-stop name; no factual claim invented.
    assert "Stop B" in nav.text


# ---------------------------------------------------------------------------
# Closing
# ---------------------------------------------------------------------------


def test_closing_round_trip_single_stop_uses_circled_phrase():
    poi = _poi("p1", "Place des Vosges")
    orient = _beat("o", poi.id, body="Find a bench.", nf="stop_orientation")
    body = _beat("b", poi.id, body="Henri IV built it.")
    seq = BeatSequence(
        poi_beats=(
            POIBeats(
                poi_id=poi.id, poi_name=poi.name, ordering_strategy="trigger_address",
                beats=(orient, body),
            ),
        )
    )
    script = generate(seq, _route((poi,)), _input(round_trip=True), glue_client=MockGlueClient())
    closing = next(s for s in script.script if s.source_id == GLUE_CLOSING)
    assert closing.text == "You've now circled Place des Vosges."


def test_closing_oneway_no_thematic_summary():
    p1 = _poi("p1", "Pont Neuf")
    p2 = _poi("p2", "Notre-Dame Cathedral")
    o = _beat("o", p1.id, body="Stand on the bridge.", nf="stop_orientation")
    seq = BeatSequence(
        poi_beats=(
            POIBeats(poi_id=p1.id, poi_name=p1.name, ordering_strategy="narrative_function", beats=(o,)),
            POIBeats(poi_id=p2.id, poi_name=p2.name, ordering_strategy="sub_location",
                     beats=(_beat("nd", p2.id, body="The cathedral, a Gothic masterpiece, rears up."),)),
        )
    )
    script = generate(seq, _route((p1, p2)), _input(round_trip=False), glue_client=MockGlueClient())
    closing = next(s for s in script.script if s.source_id == GLUE_CLOSING)
    assert "End the walk here" in closing.text


# ---------------------------------------------------------------------------
# Glue whitelist enforcement
# ---------------------------------------------------------------------------


def test_glue_label_set_matches_design_doc():
    expected = {
        "GLUE_NAV", "GLUE_STAGING", "GLUE_PACING", "GLUE_CALLBACK",
        "GLUE_CLOSING", "ARITH", "SYNTHESIZED_OPENER",
    }
    assert set(GLUE_LABELS) == expected


def test_every_glue_sentence_has_whitelisted_source_id():
    poi = _poi("p1", "Place des Vosges")
    orient = _beat("o", poi.id, body="Find a bench.", nf="stop_orientation")
    body = _beat("b", poi.id, body="Henri IV built the square.")
    seq = BeatSequence(
        poi_beats=(
            POIBeats(poi_id=poi.id, poi_name=poi.name, ordering_strategy="trigger_address",
                     beats=(orient, body)),
        )
    )
    script = generate(seq, _route((poi,)), _input(), glue_client=MockGlueClient())
    for s in script.script:
        if s.source_type in ("glue", "arith"):
            assert s.source_id in GLUE_LABELS


def test_haiku_invented_forbidden_phrase_is_replaced_with_default():
    # If the LLM tries to inject "imagine", coercion should drop the
    # output and use the default safe glue.
    p1 = _poi("p1", "A")
    p2 = _poi("p2", "B")
    o = _beat("o", p1.id, body="Find a bench.", nf="stop_orientation")
    a = _beat("a", p1.id, body="A fact.")
    b = _beat("b", p2.id, body="Another fact.")
    seq = BeatSequence(
        poi_beats=(
            POIBeats(poi_id=p1.id, poi_name=p1.name, ordering_strategy="narrative_function", beats=(o, a)),
            POIBeats(poi_id=p2.id, poi_name=p2.name, ordering_strategy="narrative_function", beats=(b,)),
        )
    )
    client = MockGlueClient(responses={"GLUE_NAV": "Imagine the river. Picture this scene."})
    script = generate(seq, _route((p1, p2)), _input(round_trip=False), glue_client=client)
    nav = next(s for s in script.script if s.source_id == GLUE_NAV)
    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in nav.text.lower()


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_generation_is_deterministic_under_mock():
    poi = _poi("p1", "Place des Vosges")
    orient = _beat("o", poi.id, body="Find a bench.", nf="stop_orientation")
    body = _beat("b", poi.id, body="Henri IV built the square.")
    seq = BeatSequence(
        poi_beats=(
            POIBeats(poi_id=poi.id, poi_name=poi.name, ordering_strategy="trigger_address",
                     beats=(orient, body)),
        )
    )
    a = generate(seq, _route((poi,)), _input(), glue_client=MockGlueClient())
    b = generate(seq, _route((poi,)), _input(), glue_client=MockGlueClient())
    # `generated_at` will differ; everything else must match.
    assert tuple(s.text for s in a.script) == tuple(s.text for s in b.script)
    assert tuple(s.source_id for s in a.script) == tuple(s.source_id for s in b.script)


# ---------------------------------------------------------------------------
# Source attribution
# ---------------------------------------------------------------------------


def test_every_beat_sentence_carries_beat_id():
    poi = _poi("p1", "Place des Vosges")
    orient = _beat("o", poi.id, body="Find a bench.", nf="stop_orientation")
    body = _beat("b", poi.id, body="Henri IV built it. Crowds came.")
    seq = BeatSequence(
        poi_beats=(
            POIBeats(poi_id=poi.id, poi_name=poi.name, ordering_strategy="trigger_address",
                     beats=(orient, body)),
        )
    )
    script = generate(seq, _route((poi,)), _input(), glue_client=MockGlueClient())
    for s in script.script:
        if s.source_type == "beat":
            assert s.source_id in {orient.id, body.id}


# ---------------------------------------------------------------------------
# Output rollup
# ---------------------------------------------------------------------------


def test_lens_coverage_counts_beats_per_lens():
    poi = _poi("p1", "Place des Vosges")
    o = _beat("o", poi.id, body="Find a bench.", nf="stop_orientation",
              lenses=("famous_residents",))
    a = _beat("a", poi.id, body="A fact.", lenses=("famous_residents", "literary_heritage"))
    b = _beat("b", poi.id, body="Another fact.", lenses=("famous_residents",))
    seq = BeatSequence(
        poi_beats=(POIBeats(poi_id=poi.id, poi_name=poi.name,
                            ordering_strategy="trigger_address", beats=(o, a, b)),),
    )
    script = generate(seq, _route((poi,)), _input(), glue_client=MockGlueClient())
    assert script.lens_coverage["famous_residents"] == 3
    assert script.lens_coverage["literary_heritage"] == 1


def test_selected_pois_carry_beat_ids_in_order():
    poi = _poi("p1", "Place des Vosges")
    o = _beat("o", poi.id, body="x.", nf="stop_orientation")
    a = _beat("a", poi.id, body="y.")
    seq = BeatSequence(
        poi_beats=(POIBeats(poi_id=poi.id, poi_name=poi.name,
                            ordering_strategy="trigger_address", beats=(o, a)),),
    )
    script = generate(seq, _route((poi,)), _input(), glue_client=MockGlueClient())
    assert script.selected_pois[0].beat_ids == ("o", "a")


def test_empty_beat_sequence_produces_empty_script():
    seq = BeatSequence(poi_beats=())
    route = _route(())
    script = generate(seq, route, _input(), glue_client=MockGlueClient())
    assert script.script == ()
    assert script.selected_pois == ()
    assert script.validation.passed
