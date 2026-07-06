"""Phase 3 — generation.py: deterministic structural assembly + glue routing.

Tests use a MockGlueClient — the LLM is never invoked. The point of
generation is the deterministic shape of the Script; the only LLM-driven
fragments are glue sentences whose category is asserted via mock calls.
"""

from __future__ import annotations

import pytest

from src.tour.contract import (
    POI,
    BeatRef,
    BeatSequence,
    PhysicalCue,
    POIBeats,
    Route,
    Sentence,
    TourInput,
    TransitSegment,
)
from src.tour.generation import (
    FORBIDDEN_PHRASES,
    GLUE_CLOSING,
    GLUE_LABELS,
    GLUE_NAV,
    GLUE_PACING,
    SYNTHESIZED_OPENER,
    _area_article,
    _sum_audio,
    _synth_first_leg_text,
    generate,
    split_sentences,
)
from src.tour.glue_client import NO_GLUE_SENTINEL, MockGlueClient

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
    out = split_sentences('He wrote "It has to hurt." That was 1752. Brice argued his case.')
    assert "Brice argued his case." in out


def test_split_sentences_keeps_name_initials():
    """Personal-name initials (J.-B., J. M. W.) are not sentence boundaries — the
    splitter must not read "…a portrait by J.-B." as a stuttered sentence (TTS
    artifact, User-agent finding)."""
    assert split_sentences("A portrait by J.-B. Vanloo hangs here.") == [
        "A portrait by J.-B. Vanloo hangs here."
    ]
    assert split_sentences("Boileau, Racine, and J.-B. Lully rehearsed here.") == [
        "Boileau, Racine, and J.-B. Lully rehearsed here."
    ]
    assert split_sentences("She met J. M. W. Turner in London.") == [
        "She met J. M. W. Turner in London."
    ]
    # A real boundary AFTER an initials phrase still splits.
    assert split_sentences("A work by J.-B. Vanloo. It hangs upstairs.") == [
        "A work by J.-B. Vanloo.",
        "It hangs upstairs.",
    ]


def test_split_sentences_terminal_abbreviations_still_split():
    """Dotted-caps abbreviations that legitimately END a sentence (U.S., A.D.,
    P.M.) must NOT be re-glued to the next sentence — the mirror of the initials
    bug. They share the shape of name-initials, so an over-broad re-glue would
    fuse two real sentences (TTS runs them together with no pause)."""
    assert split_sentences("He is from the U.S. The trip was long.") == [
        "He is from the U.S.",
        "The trip was long.",
    ]
    assert split_sentences("We saw the U.K. It was raining.") == [
        "We saw the U.K.",
        "It was raining.",
    ]
    assert split_sentences("It happened in 1914 A.D. The war began.") == [
        "It happened in 1914 A.D.",
        "The war began.",
    ]
    assert split_sentences("The exhibit runs A.M. to P.M. Come early.") == [
        "The exhibit runs A.M. to P.M.",
        "Come early.",
    ]


def test_split_sentences_empty():
    assert split_sentences("") == []
    assert split_sentences("   ") == []


# ---------------------------------------------------------------------------
# Cold open
# ---------------------------------------------------------------------------


def test_c9g_overflow_surfaces_on_scriptpoi():
    """C9g: BeatSequence.overflow_by_poi flows onto ScriptPOI.overflow_beat_ids so
    the governor's trimmed beats are SURFACED (keep-exploring extras), never
    silently dropped — the panel's blocking bug 3."""
    poi = _poi("p1", "Place des Vosges")
    kept = _beat("kept-1", poi.id, body="Henri IV built the square.", nf="establishing")
    seq = BeatSequence(
        poi_beats=(
            POIBeats(
                poi_id=poi.id,
                poi_name=poi.name,
                ordering_strategy="narrative_function",
                beats=(kept,),
            ),
        ),
        overflow_by_poi={poi.id: ("trimmed-a", "trimmed-b")},
    )
    script = generate(seq, _route((poi,)), _input(), glue_client=MockGlueClient())
    sp = {p.id: p for p in script.selected_pois}[poi.id]
    assert sp.overflow_beat_ids == ("trimmed-a", "trimmed-b"), "overflow surfaced, not dropped"
    assert sp.beat_ids == ("kept-1",), "kept beats unchanged"


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
    body = _beat(
        "body-1", poi.id, body="The cathedral rears up like a great ship.", nf="establishing"
    )
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
    script = generate(
        seq, _route((poi,), duration_min=60), _input(round_trip=False), glue_client=MockGlueClient()
    )
    sources = [s.source_id for s in script.script]
    assert SYNTHESIZED_OPENER in sources
    # Phase 7.5 (Fix 2): synthesized opener anchors on the spine Area name
    # when present (corpus-honest "you're starting in the Marais"), and
    # falls back to the POI name only when no spine_area exists. Either
    # way the opener fires and writes traceable glue tokens.
    synth = next(s for s in script.script if s.source_id == SYNTHESIZED_OPENER)
    # The route fixture sets spine_area="Le Marais", so the location
    # anchor should reference the Marais.
    assert "Marais" in synth.text or "Notre-Dame Cathedral" in synth.text


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
    # Phase 7: transit beat must reference the previous stop (Pont Neuf)
    # so the direction-awareness check accepts it.
    p2_transit = _beat(
        "p2-transit",
        p2.id,
        body=(
            "From the Pont Neuf, cross the road into place Dauphine "
            "and walk around the Conciergerie."
        ),
        nf="transition",
    )
    p2_body = _beat("p2-body", p2.id, body="The Conciergerie is Paris's oldest prison.")
    seq = BeatSequence(
        poi_beats=(
            POIBeats(
                poi_id=p1.id,
                poi_name=p1.name,
                ordering_strategy="narrative_function",
                beats=(orient, p1_body),
            ),
            POIBeats(
                poi_id=p2.id,
                poi_name=p2.name,
                ordering_strategy="narrative_function",
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


def test_phase7_transit_rejects_wrong_direction_beat():
    """Transit beat at `current` whose origin doesn't match `previous` must be rejected.

    Mirrors the phase-6-rerun Tour 4 stop 3 failure: the corpus transit
    beat at Pont Alexandre III says "Starting at Invalides Metro
    station…" but the user is arriving from Pont de la Concorde. The
    Phase 7 direction check must reject it and fall through to GLUE_NAV
    with explicit ``from previous, walk to current`` context.
    """
    p1 = _poi("p1", "Pont de la Concorde")
    p2 = _poi("p2", "Pont Alexandre III")
    orient = _beat("orient-1", p1.id, body="Stand at the parapet.", nf="stop_orientation")
    p1_body = _beat("p1-body", p1.id, body="The bridge dates to 1791.")
    # Wrong-direction transit: origin is Invalides Metro, not Pont de la Concorde.
    p2_transit = _beat(
        "p2-transit",
        p2.id,
        body="Starting at Invalides Metro station, walk to Pont Alexandre III.",
        nf="transition",
    )
    p2_body = _beat("p2-body", p2.id, body="The Beaux-Arts span opened in 1900.")
    seq = BeatSequence(
        poi_beats=(
            POIBeats(
                poi_id=p1.id,
                poi_name=p1.name,
                ordering_strategy="narrative_function",
                beats=(orient, p1_body),
            ),
            POIBeats(
                poi_id=p2.id,
                poi_name=p2.name,
                ordering_strategy="narrative_function",
                beats=(p2_transit, p2_body),
            ),
        )
    )
    client = MockGlueClient(responses={"GLUE_NAV": "Walk along the embankment."})
    script = generate(seq, _route((p1, p2)), _input(round_trip=False), glue_client=client)
    sources = [s.source_id for s in script.script]
    # The wrong-direction transit beat must NOT be cited — Haiku glue replaces it.
    assert p2_transit.id not in sources
    nav_sentences = [s for s in script.script if s.source_id == GLUE_NAV]
    assert len(nav_sentences) == 1
    # The nav request to Haiku carried the explicit "from previous, walk to current" context.
    assert client.calls and client.calls[0][0] == GLUE_NAV
    nav_request = client.calls[0][2].lower()
    assert "pont de la concorde" in nav_request
    assert "pont alexandre iii" in nav_request


def test_phase7_transit_accepts_directionally_consistent_beat():
    """Transit beat whose origin substring matches `previous` is accepted."""
    p1 = _poi("p1", "Place du Tertre")
    p2 = _poi("p2", "Saint-Pierre")
    orient = _beat("orient-1", p1.id, body="Stand by the easels.", nf="stop_orientation")
    # Direction-consistent: body explicitly mentions Place du Tertre.
    p2_transit = _beat(
        "p2-transit",
        p2.id,
        body="Leave Place du Tertre by the southwest corner and step into Saint-Pierre.",
        nf="transition",
    )
    p2_body = _beat("p2-body", p2.id, body="The little church is older than Sacré-Cœur.")
    seq = BeatSequence(
        poi_beats=(
            POIBeats(
                poi_id=p1.id,
                poi_name=p1.name,
                ordering_strategy="narrative_function",
                beats=(orient,),
            ),
            POIBeats(
                poi_id=p2.id,
                poi_name=p2.name,
                ordering_strategy="narrative_function",
                beats=(p2_transit, p2_body),
            ),
        )
    )
    client = MockGlueClient()
    script = generate(seq, _route((p1, p2)), _input(round_trip=False), glue_client=client)
    sources = [s.source_id for s in script.script]
    assert p2_transit.id in sources
    assert not any(c[0] == GLUE_NAV for c in client.calls)


def test_phase7_transit_falls_back_when_origin_mismatch():
    """Even when the previous-POI side has a transit beat, mismatched
    direction → fall through to GLUE_NAV. Both sides must satisfy the
    direction check before a corpus transit beat is reused.
    """
    p1 = _poi("p1", "A Random Start")
    p2 = _poi("p2", "Saint-Pierre")
    p1_body = _beat("p1-body", p1.id, body="Some setup.", nf="establishing")
    p2_transit = _beat(
        "p2-transit",
        p2.id,
        body="From the Sacré-Cœur, walk down rue du Mont-Cenis to Saint-Pierre.",
        nf="transition",
    )
    p2_body = _beat("p2-body", p2.id, body="The little church.")
    seq = BeatSequence(
        poi_beats=(
            POIBeats(
                poi_id=p1.id,
                poi_name=p1.name,
                ordering_strategy="narrative_function",
                beats=(p1_body,),
            ),
            POIBeats(
                poi_id=p2.id,
                poi_name=p2.name,
                ordering_strategy="narrative_function",
                beats=(p2_transit, p2_body),
            ),
        )
    )
    client = MockGlueClient(responses={"GLUE_NAV": "Walk down the street."})
    script = generate(seq, _route((p1, p2)), _input(round_trip=False), glue_client=client)
    sources = [s.source_id for s in script.script]
    assert p2_transit.id not in sources  # rejected — origin doesn't match prev
    assert any(s == GLUE_NAV for s in sources)


def test_transit_falls_back_to_glue_when_no_corpus_beat():
    p1 = _poi("p1", "Place des Vosges")
    p2 = _poi("p2", "Hôtel de Sully")
    p1_orient = _beat("p1-orient", p1.id, body="Find a bench.", nf="stop_orientation")
    p1_body = _beat("p1-body", p1.id, body="Henri IV built the square.")
    p2_body = _beat("p2-body", p2.id, body="The Hôtel de Sully sits just south.")
    seq = BeatSequence(
        poi_beats=(
            POIBeats(
                poi_id=p1.id,
                poi_name=p1.name,
                ordering_strategy="narrative_function",
                beats=(p1_orient, p1_body),
            ),
            POIBeats(
                poi_id=p2.id,
                poi_name=p2.name,
                ordering_strategy="narrative_function",
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
            POIBeats(
                poi_id=p1.id, poi_name=p1.name, ordering_strategy="narrative_function", beats=(o, a)
            ),
            POIBeats(
                poi_id=p2.id, poi_name=p2.name, ordering_strategy="narrative_function", beats=(b,)
            ),
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
                poi_id=poi.id,
                poi_name=poi.name,
                ordering_strategy="trigger_address",
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
            POIBeats(
                poi_id=p1.id, poi_name=p1.name, ordering_strategy="narrative_function", beats=(o,)
            ),
            POIBeats(
                poi_id=p2.id,
                poi_name=p2.name,
                ordering_strategy="sub_location",
                beats=(_beat("nd", p2.id, body="The cathedral, a Gothic masterpiece, rears up."),),
            ),
        )
    )
    script = generate(seq, _route((p1, p2)), _input(round_trip=False), glue_client=MockGlueClient())
    closing = next(s for s in script.script if s.source_id == GLUE_CLOSING)
    assert "End the walk here" in closing.text


# ---------------------------------------------------------------------------
# Glue whitelist enforcement
# ---------------------------------------------------------------------------


def test_glue_label_set_matches_design_doc():
    # GLUE_REFLECTION joined the whitelist in Phase 4 Step 4.1 (canonical
    # spec §6: "a new whitelisted glue token GLUE_REFLECTION").
    expected = {
        "GLUE_NAV",
        "GLUE_STAGING",
        "GLUE_PACING",
        "GLUE_CALLBACK",
        "GLUE_CLOSING",
        "GLUE_REFLECTION",
        "ARITH",
        "SYNTHESIZED_OPENER",
    }
    assert set(GLUE_LABELS) == expected


def test_every_glue_sentence_has_whitelisted_source_id():
    poi = _poi("p1", "Place des Vosges")
    orient = _beat("o", poi.id, body="Find a bench.", nf="stop_orientation")
    body = _beat("b", poi.id, body="Henri IV built the square.")
    seq = BeatSequence(
        poi_beats=(
            POIBeats(
                poi_id=poi.id,
                poi_name=poi.name,
                ordering_strategy="trigger_address",
                beats=(orient, body),
            ),
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
            POIBeats(
                poi_id=p1.id, poi_name=p1.name, ordering_strategy="narrative_function", beats=(o, a)
            ),
            POIBeats(
                poi_id=p2.id, poi_name=p2.name, ordering_strategy="narrative_function", beats=(b,)
            ),
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
            POIBeats(
                poi_id=poi.id,
                poi_name=poi.name,
                ordering_strategy="trigger_address",
                beats=(orient, body),
            ),
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
            POIBeats(
                poi_id=poi.id,
                poi_name=poi.name,
                ordering_strategy="trigger_address",
                beats=(orient, body),
            ),
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
    o = _beat(
        "o", poi.id, body="Find a bench.", nf="stop_orientation", lenses=("famous_residents",)
    )
    a = _beat("a", poi.id, body="A fact.", lenses=("famous_residents", "literary_heritage"))
    b = _beat("b", poi.id, body="Another fact.", lenses=("famous_residents",))
    seq = BeatSequence(
        poi_beats=(
            POIBeats(
                poi_id=poi.id,
                poi_name=poi.name,
                ordering_strategy="trigger_address",
                beats=(o, a, b),
            ),
        ),
    )
    script = generate(seq, _route((poi,)), _input(), glue_client=MockGlueClient())
    assert script.lens_coverage["famous_residents"] == 3
    assert script.lens_coverage["literary_heritage"] == 1


def test_selected_pois_carry_beat_ids_in_order():
    poi = _poi("p1", "Place des Vosges")
    o = _beat("o", poi.id, body="x.", nf="stop_orientation")
    a = _beat("a", poi.id, body="y.")
    seq = BeatSequence(
        poi_beats=(
            POIBeats(
                poi_id=poi.id, poi_name=poi.name, ordering_strategy="trigger_address", beats=(o, a)
            ),
        ),
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


# ---------------------------------------------------------------------------
# Phase 7.5 Fix 2 — improved SYNTHESIZED_OPENER
# ---------------------------------------------------------------------------


def _beat_with_cues(
    bid: str,
    poi_id: str,
    *,
    cues: tuple[PhysicalCue, ...] = (),
    pronunciation: str | None = None,
    body: str = "",
    nf: str = "establishing",
) -> BeatRef:
    return BeatRef(
        id=bid,
        poi_id=poi_id,
        narrative_function=nf,
        word_count=len(body.split()) or 1,
        script_body=body or None,
        physical_cues=cues,
        pronunciation=pronunciation,
    )


def test_synthesized_opener_uses_physical_cues():
    """Synthesized opener references the start POI's strongest cue + Area name."""
    poi = _poi("p1", "Hotel de Sully")
    body = _beat_with_cues(
        "body",
        poi.id,
        cues=(
            PhysicalCue(
                cue="the wrought-iron balconies",
                direction="up",
                feature_type="architectural_detail",
            ),
        ),
        body="A square fact.",
    )
    seq = BeatSequence(
        poi_beats=(
            POIBeats(
                poi_id=poi.id,
                poi_name=poi.name,
                ordering_strategy="narrative_function",
                beats=(body,),
            ),
        )
    )
    script = generate(seq, _route((poi,)), _input(round_trip=True), glue_client=MockGlueClient())
    cold_open = [s for s in script.script if s.stop_idx == 0]
    texts = [s.text for s in cold_open]
    # Area-anchored location line.
    assert any("Marais" in t for t in texts)
    # Architectural-detail cue surfaces via "Notice X."
    # (not "Look up at" - that's the view feature_type).
    assert any("the wrought-iron balconies" in t for t in texts)


def test_synthesized_opener_uses_pronunciation_when_present():
    poi = _poi("p1", "Place des Vosges")
    body = _beat_with_cues(
        "body",
        poi.id,
        pronunciation="plass-day-voge",
        body="A square fact.",
    )
    seq = BeatSequence(
        poi_beats=(
            POIBeats(
                poi_id=poi.id,
                poi_name=poi.name,
                ordering_strategy="narrative_function",
                beats=(body,),
            ),
        )
    )
    script = generate(seq, _route((poi,)), _input(round_trip=True), glue_client=MockGlueClient())
    cold_open = [s for s in script.script if s.stop_idx == 0]
    texts = [s.text for s in cold_open]
    assert any("plass-day-voge" in t for t in texts)
    assert any("That's pronounced" in t for t in texts)


def test_synthesized_opener_falls_back_gracefully_with_no_cues():
    poi = _poi("p1", "Some New Anchor")
    body = _beat_with_cues("body", poi.id, body="A fact.")
    seq = BeatSequence(
        poi_beats=(
            POIBeats(
                poi_id=poi.id,
                poi_name=poi.name,
                ordering_strategy="narrative_function",
                beats=(body,),
            ),
        )
    )
    script = generate(
        seq,
        _route((poi,), duration_min=60),
        _input(round_trip=True, duration=60),
        glue_client=MockGlueClient(),
    )
    cold_open = [s for s in script.script if s.stop_idx == 0]
    texts = [s.text for s in cold_open]
    # Minimal but readable: pacing + location anchor + first-stop walk grounding.
    assert any("Settle in" in t for t in texts)
    assert any("Marais" in t for t in texts)  # spine_area anchor
    # #20: the first stop is named and framed as a walk ahead (honest — en route),
    # replacing the old generic "we're going to walk for N minutes" primer.
    assert any("head for Some New Anchor" in t for t in texts)


def test_synthesized_opener_view_cue_uses_look_up_verb():
    """A 'view' feature_type cue uses 'Look up at...' staging."""
    poi = _poi("p1", "Some Square")
    body = _beat_with_cues(
        "body",
        poi.id,
        cues=(PhysicalCue(cue="the gilded statue", direction="up", feature_type="view"),),
        body="A fact.",
    )
    seq = BeatSequence(
        poi_beats=(
            POIBeats(
                poi_id=poi.id,
                poi_name=poi.name,
                ordering_strategy="narrative_function",
                beats=(body,),
            ),
        )
    )
    script = generate(seq, _route((poi,)), _input(round_trip=True), glue_client=MockGlueClient())
    cold_open_texts = [s.text for s in script.script if s.stop_idx == 0]
    assert any("Look up at the gilded statue" in t for t in cold_open_texts)
    # View cues also unlock the "Take a moment to take it in." invitation.
    assert any("Take a moment" in t for t in cold_open_texts)


# ---------------------------------------------------------------------------
# 2026-07-03 — per-stop emission guards (the "thin single-beat-feeling
# narration" half of the 2026-07-02 regression).
#
# validate_script checks only traceability + forbidden phrases, and
# ScriptPOI.beat_ids reflects the PLAN, not emissions — so a stop can ship
# glue-only narration while every existing check stays green. The first test
# below is the per-stop emitted-beat floor for healthy pools; the two
# "current_contract_pin" tests make BOTH known zero-emission holes executable
# and version-controlled. The per-stop floor/disclosure for those holes is
# deferred design owned by specs/2026-07-02-dwell-audio-reconciliation/ —
# when it lands, flip the pinned assertions DELIBERATELY, don't delete them.
# ---------------------------------------------------------------------------


def _poi_beats(poi: POI, beats: tuple[BeatRef, ...]) -> POIBeats:
    return POIBeats(
        poi_id=poi.id,
        poi_name=poi.name,
        ordering_strategy="narrative_function",
        beats=beats,
    )


@pytest.mark.parametrize("n_stops", (2, 3, 4, 5))
def test_every_stop_with_dwellworthy_pool_emits_own_beat_sentence(n_stops: int):
    """Every stop whose plan holds real (non-transit) beats emits >= 1 of them.

    Fails if (a) the anchor block's transit-class filter broadens to swallow
    establishing beats, (b) consumed_beat_ids leaks so an earlier stop
    consumes a later stop's pool, (c) reorder_final_stop_for_closing or
    _beat_to_sentences starts dropping bodies, or (d) a future dedupe pass
    empties a stop's emissions while ScriptPOI.beat_ids stays populated —
    every one of which reproduces glue-only stop narration that passes ALL
    existing generation checks.

    Fixture notes: stop 0 carries its OWN stop_orientation beat, so the cold
    open is satisfied locally and never raids a sibling stop's pool (the
    Area hoist fires only when stop 0 lacks one). Later stops carry
    'establishing' beats — outside the transit-class set — with no
    trigger_address, so the transit stage's direction check never adopts
    them. POIs get real multi-word names so the direction check's substring
    premise never hinges on short-name luck.
    """
    from src.tour.render_md import stop_narration_text

    pois = tuple(_poi(f"p{k}", f"Waypoint Number {k}") for k in range(n_stops))
    plans = [
        _poi_beats(
            pois[0],
            (
                _beat("p0-orient", "p0", body="Find the corner bench.", nf="stop_orientation"),
                _beat(
                    "p0-body-a",
                    "p0",
                    body="Story A at stop 0. It happened here.",
                    nf="establishing",
                ),
                _beat("p0-body-b", "p0", body="Story B at stop 0.", nf="establishing"),
            ),
        )
    ]
    bodies_by_stop: dict[int, list[str]] = {
        0: ["Find the corner bench.", "Story A at stop 0.", "Story B at stop 0."]
    }
    for k in range(1, n_stops):
        beats = (
            _beat(f"p{k}-est-a", f"p{k}", body=f"First tale at waypoint {k}.", nf="establishing"),
            _beat(f"p{k}-est-b", f"p{k}", body=f"Second tale at waypoint {k}.", nf="establishing"),
        )
        plans.append(_poi_beats(pois[k], beats))
        bodies_by_stop[k] = [f"First tale at waypoint {k}.", f"Second tale at waypoint {k}."]

    seq = BeatSequence(poi_beats=tuple(plans))
    script = generate(seq, _route(pois), _input(), glue_client=MockGlueClient())
    per_stop = stop_narration_text(script)

    for k in range(n_stops):
        plan_ids = set(script.selected_pois[k].beat_ids)
        assert plan_ids, f"stop {k}: plan lost its beats"
        assert any(
            s.source_type == "beat" and s.stop_idx == k and s.source_id in plan_ids
            for s in script.script
        ), f"stop {k} emitted ZERO of its own beats — glue-only narration"
        # The same floor at the render level the preview wire serves.
        narration = per_stop.get(k, "")
        assert narration, f"stop {k}: empty narration"
        assert any(body in narration for body in bodies_by_stop[k]), (
            f"stop {k}: narration carries none of its beat bodies"
        )


def test_transit_only_stop_emits_zero_beat_sentences_current_contract_pin():
    """CURRENT-CONTRACT PIN: a stop whose whole pool is transit-class ships
    glue-only narration, invisibly.

    The per-stop emitted-beat floor is owned by
    specs/2026-07-02-dwell-audio-reconciliation/; when a floor/disclosure
    lands, flip assertions (2)-(4) DELIBERATELY. This test exists so the
    known hole is DETECTED and version-controlled rather than latent: it is
    the reproducible seed of the "thin single-beat-feeling narration"
    complaint — a dwell stop whose only beat is transit-class AND
    directionally rejected emits zero beat sentences while its
    ScriptPOI.beat_ids stays non-empty and validate_script passes. It also
    guards the inverse regression: if the anchor block's transit-class
    filter is ever DROPPED, assertion (2) fails, preventing out-of-place
    navigation sentences from leaking back into anchor blocks (the original
    Phase 7 bug the filter exists for).
    """
    p1 = _poi("p1", "Place des Vosges")
    p2 = _poi("p2", "Saint-Pierre")
    p1_orient = _beat("p1-orient", "p1", body="Find the corner bench.", nf="stop_orientation")
    p1_body = _beat("p1-body", "p1", body="Henri IV built the square in 1612.", nf="establishing")
    # Transit-class AND directionally rejected: neither the trigger_address
    # nor the body mentions p1's name, so _build_transit's Phase-7 direction
    # check refuses it and falls through to GLUE_NAV without consuming it;
    # the anchor block then filters it as transit-class -> zero emission.
    p2_transit = _beat(
        "p2-transit",
        "p2",
        body="Leave the Old Mill and cross toward the gate.",
        nf="transition",
        addr="Rue Imaginaire 12",
    )
    # Precondition: the rejection premise is explicit, not accidental — a
    # helper-default or body edit that lets p1's name slip in would flip the
    # beat into an ACCEPTED transit beat and fail this loudly.
    haystack = f"{p2_transit.trigger_address or ''} {p2_transit.script_body or ''}".lower()
    assert p1.name.lower() not in haystack, "fixture drifted: transit beat now matches p1"

    seq = BeatSequence(poi_beats=(_poi_beats(p1, (p1_orient, p1_body)),
                                  _poi_beats(p2, (p2_transit,))))
    script = generate(seq, _route((p1, p2)), _input(), glue_client=MockGlueClient())

    # (1) The PLAN still carries the beat (beat_ids reflect the plan, not
    # emissions).
    assert script.selected_pois[1].beat_ids == ("p2-transit",)
    # (2) The zero-emission condition, detected.
    assert not any(s.source_type == "beat" and s.stop_idx == 1 for s in script.script), (
        "stop 1 emitted a beat sentence — the transit-class filter changed; "
        "update this pin consciously (specs/2026-07-02-dwell-audio-reconciliation/)"
    )
    # (3) Stop 1's narration is non-empty but consists ONLY of glue — exactly
    # what the preview renders as a story-less stop.
    stop1 = [s for s in script.script if s.stop_idx == 1]
    assert stop1, "stop 1 must still get glue narration"
    assert all(s.source_type in ("glue", "arith") for s in stop1)
    # (4) validate_script does NOT catch this today.
    assert script.validation.passed is True


def test_cold_open_area_hoist_strips_donor_stop_current_contract_pin():
    """CURRENT-CONTRACT PIN: the cold open's Area hoist can strip its donor
    stop down to zero beat emissions.

    The Area-level fallback hoists a sibling stop's stop_orientation beat
    into the opener (emitted with stop_idx=0) and adds it to
    consumed_beat_ids so it never fires at its own stop; when it was the
    donor's ONLY beat, the donor emits zero beat sentences while its
    ScriptPOI.beat_ids stays non-empty — the second known glue-only-stop
    path. The per-stop floor is owned by
    specs/2026-07-02-dwell-audio-reconciliation/; flip assertion (2)
    DELIBERATELY when it lands. Assertion (3) simultaneously guards the
    CROSS-stop double-fire regression (the same-stop case is covered by
    test_orientation_beat_not_emitted_twice above).
    """
    # Both _poi() POIs share the helper's default area ('Le Marais') and the
    # same coordinates, so the hoist's Area-match and proximity gates pass;
    # the beat carries no physical_cues, so the honesty gate passes too.
    p1 = _poi("p1", "Hotel de Sully")
    p2 = _poi("p2", "Place des Vosges")
    p1_est_a = _beat("p1-est-a", "p1", body="The facade dates to 1624.", nf="establishing")
    p1_est_b = _beat("p1-est-b", "p1", body="Sully bought it in 1634.", nf="establishing")
    # p1 has NO stop_orientation beat — forces the Area-fallback search.
    p2_orient = _beat(
        "p2-orient", "p2", body="Stand where the two lanes meet.", nf="stop_orientation"
    )

    seq = BeatSequence(poi_beats=(_poi_beats(p1, (p1_est_a, p1_est_b)),
                                  _poi_beats(p2, (p2_orient,))))
    script = generate(seq, _route((p1, p2)), _input(), glue_client=MockGlueClient())

    # Precondition: the hoist actually happened. If the fallback ever stops
    # hoisting, this test's premise is gone — fail HERE, loudly, instead of
    # passing vacuously.
    hoisted = [
        s for s in script.script if s.source_type == "beat" and s.source_id == "p2-orient"
    ]
    assert any(s.stop_idx == 0 for s in hoisted), (
        "the Area hoist no longer fires — this pin's premise is gone; rewrite it"
    )
    # (1) The donor's plan is unchanged.
    assert script.selected_pois[1].beat_ids == ("p2-orient",)
    # (2) The donor stop is stripped to zero beat emissions (the pinned hole).
    assert not any(s.source_type == "beat" and s.stop_idx == 1 for s in script.script), (
        "donor stop emitted a beat — the hoist/consumed contract changed; "
        "update this pin consciously (specs/2026-07-02-dwell-audio-reconciliation/)"
    )
    # (3) No double emission: the consumed-set contract that motivated
    # consumed_beat_ids — the orientation beat is spoken exactly ONCE.
    assert len(hoisted) == 1


# ---------------------------------------------------------------------------
# C8 — honest REPORTED per-stop minutes (dwell_seconds = max(tier floor,
# planned voiced audio)). Reporting surface only; routes are unchanged.
# The hermetic fixtures elsewhere carry no word_count, so max() == the tier
# floor there; these two tests exercise the honest path that C8 changes.
# ---------------------------------------------------------------------------


def test_reported_dwell_is_planned_audio_when_a_stop_is_beat_rich():
    # Two 500-word beats @150wpm = 200s + 200s = 400s of voiced narration at a
    # tier-5 stop whose tier floor is only 300s -> the stop card must report the
    # REAL 400s, not the fictional 300s (the pool-vs-delivered honesty fix).
    poi = _poi("rich", "Place des Vosges", tier=5)
    beats = (
        _beat("b1", poi.id, body="Henri IV built the square.", word_count=500),
        _beat("b2", poi.id, body="The arcades run all around.", word_count=500),
    )
    seq = BeatSequence(
        poi_beats=(
            POIBeats(
                poi_id=poi.id,
                poi_name=poi.name,
                ordering_strategy="narrative_function",
                beats=beats,
            ),
        )
    )
    script = generate(seq, _route((poi,)), _input(), glue_client=MockGlueClient())
    sp = next(s for s in script.selected_pois if s.id == poi.id)
    assert sp.dwell_seconds == 400  # planned voiced audio, NOT the 300s tier floor


def test_reported_dwell_floors_at_tier_when_a_stop_is_beat_thin():
    # A 100-word beat @150wpm = 40s of narration at a tier-5 stop -> the card
    # still reports the 300s tier floor (a stop takes look-around time even when
    # the audio is short). max(tier_floor, planned) keeps the floor.
    poi = _poi("thin", "Small Chapel", tier=5)
    beats = (_beat("b1", poi.id, body="A brief note here.", word_count=100),)
    seq = BeatSequence(
        poi_beats=(
            POIBeats(
                poi_id=poi.id,
                poi_name=poi.name,
                ordering_strategy="narrative_function",
                beats=beats,
            ),
        )
    )
    script = generate(seq, _route((poi,)), _input(), glue_client=MockGlueClient())
    sp = next(s for s in script.selected_pois if s.id == poi.id)
    assert sp.dwell_seconds == 300  # tier-5 floor wins over the 40s planned audio


# ---------------------------------------------------------------------------
# #20 — grounded, honest cold-open (area article + first-stop walk framing)
# ---------------------------------------------------------------------------

def test_area_article_covers_english_descriptive_areas():
    assert _area_article("Latin Quarter") == "the "
    assert _area_article("Left Bank") == "the "
    assert _area_article("Île de la Cité") == "the "
    assert _area_article("4th Arrondissement") == "the "
    # French place-names take no article.
    assert _area_article("Montmartre") == ""
    assert _area_article("Saint-Germain-des-Prés") == ""
    # "Le Marais" already carries its article.
    assert _area_article("Le Marais") == ""


def _stop(name: str) -> POIBeats:
    return POIBeats(poi_id="p", poi_name=name, ordering_strategy="narrative_function", beats=())


def _route_with_first_leg(secs: int) -> Route:
    poi = _poi("p", "x")
    return Route(
        pois=(poi,),
        transits=(TransitSegment(from_poi_id=None, to_poi_id="p", distance_m=100.0,
                                 walk_seconds=secs),),
        total_walk_distance_m=100.0, total_walk_seconds=secs,
        spine_area="Le Marais",
        target_audio_seconds=1800, err_short_total_seconds=2988,
    )


def test_first_leg_text_names_stop_and_walk_minutes():
    text = _synth_first_leg_text(_stop("Pantheon"), _route_with_first_leg(300))  # 5 min
    assert text == "When you're ready, head for Pantheon — about a 5-minute walk from here."


def test_first_leg_text_uses_an_before_vowel_minutes():
    text = _synth_first_leg_text(_stop("Pantheon"), _route_with_first_leg(480))  # 8 min
    assert "about an 8-minute walk" in text


def test_first_leg_text_lowercases_leading_the():
    text = _synth_first_leg_text(_stop("The Sorbonne"), _route_with_first_leg(300))
    assert "head for the Sorbonne" in text
    assert "The Sorbonne" not in text


def test_first_leg_text_short_leg_is_just_ahead():
    text = _synth_first_leg_text(_stop("Pantheon"), _route_with_first_leg(40))  # <1 min
    assert text == "When you're ready, head for Pantheon — it's just ahead."


def test_first_leg_text_none_without_stop_name():
    assert _synth_first_leg_text(_stop(""), _route_with_first_leg(300)) is None


def test_sum_audio_scales_by_surviving_sentence_fraction():
    """#8: a claim-dedup-trimmed beat reports only its SURVIVING sentences' share
    of audio, not the whole beat — an honest tour-minutes total."""
    beat = _beat("b1", "p", body="First fact here. Second fact here. Third fact here.")
    beat = beat.model_copy(update={"est_spoken_seconds": 90})
    seq = BeatSequence(
        poi_beats=(POIBeats(poi_id="p", poi_name="P", ordering_strategy="narrative_function",
                            beats=(beat,)),)
    )

    def _s(text: str) -> Sentence:
        return Sentence(text=text, source_id="b1", source_type="beat", stop_idx=0)

    all_three = [_s("First fact here."), _s("Second fact here."), _s("Third fact here.")]
    assert _sum_audio(all_three, seq) == 90  # nothing dropped -> full beat audio

    # dedup dropped the middle sentence: 2 of 3 survive -> 2/3 of the audio.
    two = [_s("First fact here."), _s("Third fact here.")]
    assert _sum_audio(two, seq) == round(90 * 2 / 3)  # 60, not 90
