"""Phase 2 — beat_select.py: ordering + length-class fallback."""

from __future__ import annotations

import pytest

from src.tour.beat_select import (
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


def test_strategy_sub_location_wins_over_trigger_address():
    # 3 sub_locs + 5 trigger_addrs → sub_location (building-walk wins).
    beats = [
        _beat("a", sub_location="parvis", trigger_address="x1"),
        _beat("b", sub_location="nave", trigger_address="x2"),
        _beat("c", sub_location="choir", trigger_address="x3"),
        _beat("d", trigger_address="x4"),
        _beat("e", trigger_address="x5"),
    ]
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


def test_narrative_function_caps_at_six_for_anchor():
    poi = _poi("Sainte-Chapelle")  # tier 5
    beats = [_beat(f"b{i}", narrative_function="deepen") for i in range(10)]
    plan = select_poi_beats(poi, beats)
    assert len(plan.beats) == 6


def test_narrative_function_pause_tier3_caps_at_two():
    poi = _poi("Some Pause", tier=3)
    beats = [_beat(f"b{i}", narrative_function="deepen") for i in range(5)]
    plan = select_poi_beats(poi, beats)
    assert len(plan.beats) == 2


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
