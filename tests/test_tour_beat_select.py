"""Phase 2 — beat_select.py: ordering + length-class fallback.

Phase 3.5 (2026-04-29) added B8-lite claim-dedup tests at the end.
"""

from __future__ import annotations

import pytest

from src.tour.beat_select import (
    B8_JACCARD_THRESHOLD,
    NARRATIVE_FUNCTION_ORDER,
    choose_ordering_strategy,
    select_poi_beats,
)
from src.tour.contract import POI, BeatRef
from src.tour.fixtures import NOTRE_DAME_SUB_LOCATION_ORDER


def _poi(name: str, tier: int = 5) -> POI:
    return POI(id=f"poi-{name}", name=name, tier=tier, poi_role="stop", lat=48.85, lng=2.35)


def _beat(
    bid: str,
    *,
    sub_location: str | None = None,
    trigger_address: str | None = None,
    narrative_function: str | None = None,
    emotional_register: str | None = "neutral",
    beat_length_class: str | None = None,
    word_count: int = 100,
    lenses: tuple[str, ...] = (),
    entities: tuple[str, ...] = (),
    subject_tag: str | None = None,
    script_body: str | None = None,
    poi_id: str = "poi",
) -> BeatRef:
    return BeatRef(
        id=bid,
        poi_id=poi_id,
        sub_location=sub_location,
        trigger_address=trigger_address,
        narrative_function=narrative_function,
        emotional_register=emotional_register,
        beat_length_class=beat_length_class,
        word_count=word_count,
        lenses=lenses,
        entities=entities,
        subject_tag=subject_tag,
        script_body=script_body,
    )


# ---------------------------------------------------------------------------
# Strategy choice
# ---------------------------------------------------------------------------


def test_strategy_sub_location_when_three_distinct():
    beats = [
        _beat("1", sub_location="parvis"),
        _beat("2", sub_location="nave"),
        _beat("3", sub_location="choir"),
    ]
    assert choose_ordering_strategy(beats) == "sub_location"


def test_strategy_trigger_address_when_five_distinct():
    beats = [_beat(str(i), trigger_address=f"no. {i}") for i in range(1, 6)]
    assert choose_ordering_strategy(beats) == "trigger_address"


def test_strategy_narrative_when_neither_dense():
    beats = [
        _beat("1", narrative_function="hook"),
        _beat("2", narrative_function="establishing"),
    ]
    assert choose_ordering_strategy(beats) == "narrative_function"


def test_strategy_dominant_primitive_wins():
    """Phase 4 calibration: when both primitives meet threshold, the one
    with more distinct values wins. With 3 sub_locs vs 5 trigger_addrs,
    triggers dominate so trigger_address strategy fires (matches the
    empirical PdV walk where 23 trigger_addresses outweigh 6 sub_locs).
    """
    beats = [
        _beat("a", sub_location="parvis", trigger_address="x1"),
        _beat("b", sub_location="nave", trigger_address="x2"),
        _beat("c", sub_location="choir", trigger_address="x3"),
        _beat("d", trigger_address="x4"),
        _beat("e", trigger_address="x5"),
    ]
    assert choose_ordering_strategy(beats) == "trigger_address"


def test_strategy_sub_location_wins_when_dominant():
    """Sub_location wins when it has at least as many distinct values
    as trigger_address (Notre-Dame / Conciergerie shape).
    """
    beats = [
        _beat("a", sub_location="parvis"),
        _beat("b", sub_location="nave"),
        _beat("c", sub_location="choir"),
        _beat("d", sub_location="towers"),
        _beat("e", sub_location="treasury"),
    ]
    assert choose_ordering_strategy(beats) == "sub_location"


def test_strategy_sub_location_when_triggers_below_threshold():
    """Sub_location still wins if trigger_address fails its threshold,
    even if sub_locs < trig_n by a small amount (4 sub_locs, 4 triggers
    where trigger threshold is 5).
    """
    beats = [
        _beat("a", sub_location="parvis", trigger_address="x1"),
        _beat("b", sub_location="nave", trigger_address="x2"),
        _beat("c", sub_location="choir", trigger_address="x3"),
        _beat("d", sub_location="towers", trigger_address="x4"),
    ]
    # 4 sub_locs ≥ 3, 4 triggers < 5 → sub_location.
    assert choose_ordering_strategy(beats) == "sub_location"


# ---------------------------------------------------------------------------
# Notre-Dame fixture ordering
# ---------------------------------------------------------------------------


def test_notre_dame_sub_location_ordering_matches_fixture():
    # One beat per sub_location, intentionally provided in shuffled order.
    seen = ["interior-nave", "facade", "kilometre-zero", "towers", "parvis", "choir"]
    beats = [_beat(f"b-{s}", sub_location=s) for s in seen]
    poi = _poi("Notre-Dame Cathedral")

    plan = select_poi_beats(poi, beats)
    out_order = [b.sub_location for b in plan.beats]

    expected = [s for s in NOTRE_DAME_SUB_LOCATION_ORDER if s in seen]
    assert out_order == expected
    assert plan.ordering_strategy == "sub_location"


def test_notre_dame_picks_highest_scoring_beat_per_sub_location():
    # Two beats for parvis; one carries the matching lens, one doesn't.
    poi = _poi("Notre-Dame Cathedral")
    beats = [
        _beat(
            "low",
            sub_location="parvis",
            lenses=("tourism_culture",),
            word_count=100,
        ),
        _beat(
            "high",
            sub_location="parvis",
            lenses=("hidden_history",),
            word_count=100,
        ),
        _beat("nave", sub_location="nave"),
        _beat("choir", sub_location="choir"),
    ]
    plan = select_poi_beats(poi, beats, interest_lenses=["hidden_history"])
    parvis_beat = next(b for b in plan.beats if b.sub_location == "parvis")
    assert parvis_beat.id == "high"


def test_uncurated_poi_falls_back_to_alphabetical_sub_location_order():
    poi = _poi("Some New Anchor")
    beats = [
        _beat("zz", sub_location="zeta"),
        _beat("aa", sub_location="alpha"),
        _beat("mm", sub_location="mu"),
    ]
    plan = select_poi_beats(poi, beats)
    assert [b.sub_location for b in plan.beats] == ["alpha", "mu", "zeta"]


def test_no_sub_location_beat_appended_last():
    poi = _poi("Notre-Dame Cathedral")
    beats = [
        _beat("nave", sub_location="nave"),
        _beat("choir", sub_location="choir"),
        _beat("parvis", sub_location="parvis"),
        _beat("misc", sub_location=None),
    ]
    plan = select_poi_beats(poi, beats)
    assert plan.beats[-1].id == "misc"
    assert plan.beats[-1].sub_location is None


# ---------------------------------------------------------------------------
# Trigger address ordering
# ---------------------------------------------------------------------------


def test_trigger_address_orders_numerically():
    poi = _poi("Place des Vosges")
    beats = [
        _beat("b13", trigger_address="no. 13 place des Vosges"),
        _beat("b1", trigger_address="no. 1 place des Vosges"),
        _beat("b21", trigger_address="no. 21 place des Vosges"),
        _beat("b2", trigger_address="no. 2 place des Vosges"),
        _beat("b1bis", trigger_address="no. 1 bis place des Vosges"),
    ]
    plan = select_poi_beats(poi, beats)
    addrs = [b.trigger_address for b in plan.beats]
    # Numeric prefix sort: 1 (and 1 bis), 2, 13, 21.
    assert addrs[0].startswith("no. 1 ")
    assert addrs[2] == "no. 2 place des Vosges"
    assert addrs[3] == "no. 13 place des Vosges"
    assert addrs[4] == "no. 21 place des Vosges"
    assert plan.ordering_strategy == "trigger_address"


def test_trigger_address_deterministic_under_shuffle():
    poi = _poi("Place des Vosges")
    template = [_beat(f"b{i}", trigger_address=f"no. {i} place des Vosges") for i in range(1, 11)]

    import random

    rng = random.Random(0)
    seq_a = list(template)
    seq_b = list(template)
    rng.shuffle(seq_a)
    rng.shuffle(seq_b)

    plan_a = select_poi_beats(poi, seq_a)
    plan_b = select_poi_beats(poi, seq_b)
    assert [b.id for b in plan_a.beats] == [b.id for b in plan_b.beats]


# ---------------------------------------------------------------------------
# Narrative-function fallback (length-class)
# ---------------------------------------------------------------------------


def test_narrative_function_ordering_when_no_spatial_primitive():
    poi = _poi("Sainte-Chapelle")
    beats = [
        _beat("b-deepen", narrative_function="deepen"),
        _beat("b-hook", narrative_function="hook"),
        _beat("b-climax", narrative_function="climax"),
        _beat("b-est", narrative_function="establishing"),
    ]
    plan = select_poi_beats(poi, beats)
    fns = [b.narrative_function for b in plan.beats]
    expected = [fn for fn in NARRATIVE_FUNCTION_ORDER if fn in fns]
    assert fns[: len(expected)] == expected


def test_narrative_function_caps_at_default_flat_max_for_anchor():
    """Phase 4 calibration: DEFAULT_FLAT_MAX bumped 6→8 to recover empirical
    Sainte-Chapelle / Île de la Cité deepens that lost the prior 6-beat trim.
    """
    poi = _poi("Sainte-Chapelle")  # tier 5
    beats = [_beat(f"b{i}", narrative_function="deepen") for i in range(10)]
    plan = select_poi_beats(poi, beats)
    assert len(plan.beats) == 8


def test_narrative_function_pause_tier3_caps_at_pause_max():
    """Phase 4 calibration: PAUSE_BEATS_MAX bumped 2→3 to match the empirical
    Vert-Galant pause carrying establishing + view + tarnished beats.
    """
    poi = _poi("Some Pause", tier=3)
    beats = [_beat(f"b{i}", narrative_function="deepen") for i in range(5)]
    plan = select_poi_beats(poi, beats)
    assert len(plan.beats) == 3


def test_narrative_function_walkby_tier1_caps_at_one():
    poi = _poi("Walk-by", tier=1)
    beats = [_beat(f"b{i}", narrative_function="hook") for i in range(3)]
    plan = select_poi_beats(poi, beats)
    assert len(plan.beats) == 1


def test_inactive_beats_filtered():
    poi = _poi("Notre-Dame Cathedral")
    beats = [
        _beat("alive", sub_location="parvis"),
        _beat("dead", sub_location="choir").model_copy(update={"active_status": "deprecated"}),
        _beat("alive2", sub_location="nave"),
    ]
    plan = select_poi_beats(poi, beats)
    assert all(b.active_status == "active" for b in plan.beats)
    assert {b.id for b in plan.beats} == {"alive", "alive2"}


def test_length_class_breaks_ties_when_present():
    # Two beats tied on lens-match and word_count → length_class wins.
    poi = _poi("Notre-Dame Cathedral")
    beats = [
        _beat("seasoning", sub_location="parvis", beat_length_class="seasoning", word_count=150),
        _beat("anchor", sub_location="parvis", beat_length_class="anchor", word_count=150),
        _beat("nave", sub_location="nave"),
        _beat("choir", sub_location="choir"),
    ]
    plan = select_poi_beats(poi, beats)
    parvis = next(b for b in plan.beats if b.sub_location == "parvis")
    assert parvis.id == "anchor"


def test_length_class_falls_back_to_word_count_when_missing():
    # No length_class on either beat — wider one wins.
    poi = _poi("Notre-Dame Cathedral")
    beats = [
        _beat("short", sub_location="parvis", beat_length_class=None, word_count=50),
        _beat("long", sub_location="parvis", beat_length_class=None, word_count=300),
        _beat("nave", sub_location="nave"),
        _beat("choir", sub_location="choir"),
    ]
    plan = select_poi_beats(poi, beats)
    parvis = next(b for b in plan.beats if b.sub_location == "parvis")
    assert parvis.id == "long"


def test_tone_variety_breaks_three_somber_run():
    poi = _poi("Sainte-Chapelle")
    # All five share narrative_function so default ordering is by score
    # (all equal). Rely on tone-variety to swap a non-somber in.
    beats = [
        _beat("a", narrative_function="hook", emotional_register="somber"),
        _beat("b", narrative_function="hook", emotional_register="reverent"),
        _beat("c", narrative_function="hook", emotional_register="somber"),
        _beat("d", narrative_function="hook", emotional_register="playful"),
    ]
    plan = select_poi_beats(poi, beats)
    registers = [b.emotional_register for b in plan.beats]
    # No three SOMBER in a row.
    for i in range(2, len(registers)):
        triplet = {registers[i - 2], registers[i - 1], registers[i]}
        assert triplet != {"somber"} | {"reverent"} - {"reverent"}
        assert not (
            registers[i - 2] in {"somber", "reverent"}
            and registers[i - 1] in {"somber", "reverent"}
            and registers[i] in {"somber", "reverent"}
        )


# ---------------------------------------------------------------------------
# B8-lite claim dedup (Phase 3.5)
# ---------------------------------------------------------------------------


def test_b8_lite_drops_overlapping_entities():
    # Two beats sharing 4-of-5 entities (Jaccard 0.8) at the same lens →
    # the longer body wins, the shorter is dropped.
    poi = _poi("Hotel de Sully")
    long_body = "Voltaire was beaten by the Prince de Rohan's lackeys here. " * 6
    short_body = "Voltaire was beaten by Rohan's lackeys."
    long_beat = _beat(
        "long-voltaire",
        sub_location="courtyard",
        narrative_function="deepen",
        lenses=("literary_heritage",),
        entities=("Bastille", "Letters", "Prince de Rohan", "Upon", "Voltaire"),
        script_body=long_body,
        word_count=80,
    )
    short_beat = _beat(
        "short-voltaire",
        sub_location="courtyard",
        narrative_function="deepen",
        lenses=("literary_heritage",),
        entities=("Bastille", "Prince de Rohan", "Upon", "Voltaire"),
        script_body=short_body,
        word_count=8,
    )
    other = _beat(
        "other",
        sub_location="garden",
        narrative_function="establishing",
        lenses=("famous_residents",),
        entities=("Sully",),
        script_body="Independent fact.",
        word_count=3,
    )
    plan = select_poi_beats(poi, [long_beat, short_beat, other])
    ids = [b.id for b in plan.beats]
    assert "long-voltaire" in ids
    assert "short-voltaire" not in ids
    assert "other" in ids


def test_b8_lite_keeps_complementary_when_overlap_below_threshold():
    # Two beats sharing only 1-of-3 entities (Jaccard 0.33) at the same
    # lens are NOT collapsed — complementary detail is preserved.
    poi = _poi("Notre-Dame Cathedral")
    a = _beat(
        "a",
        sub_location="parvis",
        narrative_function="establishing",
        lenses=("hidden_history",),
        entities=("Notre-Dame", "Hugo", "Quasimodo"),
        script_body="Hugo wrote about Quasimodo at Notre-Dame.",
        word_count=10,
    )
    b = _beat(
        "b",
        sub_location="nave",
        narrative_function="establishing",
        lenses=("hidden_history",),
        entities=("Notre-Dame", "Pilier des Nautes", "Pillars"),
        script_body="The Pilier des Nautes was found beneath Notre-Dame.",
        word_count=10,
    )
    plan = select_poi_beats(poi, [a, b])
    ids = {beat.id for beat in plan.beats}
    assert ids == {"a", "b"}


def test_b8_lite_skips_pairs_with_no_lens_overlap():
    # Same entities, but disjoint lenses → no collision.
    poi = _poi("Place des Vosges")
    a = _beat(
        "a",
        trigger_address="no. 6 place des Vosges",
        narrative_function="establishing",
        lenses=("famous_residents",),
        entities=("Hugo", "Place des Vosges"),
        script_body="Hugo lived at no. 6.",
        word_count=5,
    )
    b = _beat(
        "b",
        trigger_address="no. 8 place des Vosges",
        narrative_function="establishing",
        lenses=("literary_heritage",),
        entities=("Hugo", "Place des Vosges"),
        script_body="Hugo's writings name the square repeatedly.",
        word_count=6,
    )
    # Add 3 more addresses so we hit the trigger_address strategy.
    fillers = [
        _beat(
            f"f{i}",
            trigger_address=f"no. {i} place des Vosges",
            narrative_function="establishing",
            lenses=("famous_residents",),
            entities=("Filler",),
            script_body=f"Filler {i}.",
            word_count=2,
        )
        for i in (1, 2, 3)
    ]
    plan = select_poi_beats(poi, [a, b, *fillers])
    ids = {beat.id for beat in plan.beats}
    assert {"a", "b"}.issubset(ids)


def test_b8_lite_subject_tag_overlap_triggers_dedup():
    # Empty entities, but identical subject_tag → collide.
    poi = _poi("Conciergerie")
    a = _beat(
        "long",
        sub_location="salle-des-gens-darmes",
        narrative_function="deepen",
        lenses=("dark_history",),
        entities=(),
        subject_tag="marie antoinette cell mockup",
        script_body="A long account of the cell mockup, " * 10,
        word_count=80,
    )
    b = _beat(
        "short",
        sub_location="salle-des-gens-darmes",
        narrative_function="deepen",
        lenses=("dark_history",),
        entities=(),
        subject_tag="marie antoinette cell mockup",
        script_body="Short version.",
        word_count=2,
    )
    other = _beat(
        "other",
        sub_location="tour-bonbec",
        narrative_function="establishing",
        lenses=("dark_history",),
        entities=("Tour Bonbec",),
        subject_tag="tower torture screams",
        script_body="The tower's name comes from screams.",
        word_count=7,
    )
    one_more = _beat(
        "more",
        sub_location="rue-de-paris-cells",
        narrative_function="establishing",
        lenses=("dark_history",),
        entities=("Sansons",),
        subject_tag="executioner dynasty",
        script_body="The Sanson family held the post for generations.",
        word_count=8,
    )
    plan = select_poi_beats(poi, [a, b, other, one_more])
    ids = {beat.id for beat in plan.beats}
    assert "long" in ids
    assert "short" not in ids


def test_b8_lite_threshold_constant_matches_design_doc():
    # Phase-1-design.md §3.3 specifies 0.8 — guard against silent drift.
    assert B8_JACCARD_THRESHOLD == 0.8


# ---------------------------------------------------------------------------
# Phase 3.5 — stop_orientation hoist (so cold-open can find it)
# ---------------------------------------------------------------------------


def test_orientation_beat_hoisted_to_head_under_sub_location_strategy():
    poi = _poi("Notre-Dame Cathedral")
    orient = BeatRef(
        id="orient",
        poi_id="poi",
        sub_location=None,           # orientation beats lack sub_location
        beat_type="stop_orientation",
        narrative_function="establishing",
        word_count=20,
    )
    parvis = _beat("parvis", sub_location="parvis", narrative_function="hook")
    nave = _beat("nave", sub_location="nave", narrative_function="deepen")
    choir = _beat("choir", sub_location="choir", narrative_function="climax")
    plan = select_poi_beats(poi, [parvis, nave, choir, orient])
    assert plan.beats[0].id == "orient"
    # Head + 3 sub_locations; orientation isn't double-counted as a closer.
    assert len(plan.beats) == 4


def test_orientation_beat_hoisted_under_trigger_address_strategy():
    poi = _poi("Place des Vosges")
    orient = BeatRef(
        id="orient",
        poi_id="poi",
        trigger_address=None,
        beat_type="stop_orientation",
        narrative_function="establishing",
        word_count=20,
    )
    addrs = [
        _beat(f"a{i}", trigger_address=f"no. {i} place des Vosges")
        for i in range(1, 6)
    ]
    plan = select_poi_beats(poi, [*addrs, orient])
    assert plan.beats[0].id == "orient"
    assert plan.ordering_strategy == "trigger_address"


def test_no_orientation_beat_means_no_change():
    poi = _poi("Notre-Dame Cathedral")
    parvis = _beat("parvis", sub_location="parvis")
    nave = _beat("nave", sub_location="nave")
    choir = _beat("choir", sub_location="choir")
    plan = select_poi_beats(poi, [parvis, nave, choir])
    assert {b.id for b in plan.beats} == {"parvis", "nave", "choir"}
