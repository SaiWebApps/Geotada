"""Hermetic unit tests for route_script_to_stops (M0b adapter).

Pure-function tests: hand-built engine contract objects, NO database, NO engine
run, NO corpus. See specs/2026-06-12-tour-algorithm-decision/M0b-DESIGN.md.
"""

from __future__ import annotations

from src.api.crud.trips import route_script_to_stops
from src.tour.contract import BeatRef, Script, ScriptPOI, Sentence, TourInput, ValidationReport


def _poi(pid: str, name: str, *, tier: int, beat_ids: tuple[str, ...], dwell: int) -> ScriptPOI:
    return ScriptPOI(
        id=pid, name=name, tier=tier, lat=48.85, lng=2.35, dwell_seconds=dwell, beat_ids=beat_ids
    )


def _beat(bid: str, poi_id: str, lenses: tuple[str, ...]) -> BeatRef:
    return BeatRef(id=bid, poi_id=poi_id, lenses=lenses)


def test_stops_preserve_route_order_and_sort_order():
    pois = [
        _poi("p1", "Eiffel Tower", tier=5, beat_ids=("b1",), dwell=600),
        _poi("p2", "Notre-Dame", tier=4, beat_ids=("b2",), dwell=300),
    ]
    stops = route_script_to_stops(pois, {}, {})
    assert [s["poi_id"] for s in stops] == ["p1", "p2"]
    assert [s["sort_order"] for s in stops] == [1, 2]


def test_all_beats_kept_with_primary():
    beats = {
        "b1": _beat("b1", "p1", ("dark_history",)),
        "b2": _beat("b2", "p1", ("dark_history",)),
        "b3": _beat("b3", "p1", ("architecture",)),
    }
    pois = [_poi("p1", "Louvre", tier=5, beat_ids=("b1", "b2", "b3"), dwell=600)]
    stops = route_script_to_stops(pois, beats, {})
    assert stops[0]["beat_ids"] == ["b1", "b2", "b3"]
    assert stops[0]["primary_beat_id"] == "b1"
    assert stops[0]["dwell_seconds"] == 600  # raw engine dwell passes through


def test_dominant_lens_is_most_common():
    beats = {
        "b1": _beat("b1", "p1", ("dark_history",)),
        "b2": _beat("b2", "p1", ("dark_history",)),
        "b3": _beat("b3", "p1", ("architecture",)),
    }
    pois = [_poi("p1", "Louvre", tier=5, beat_ids=("b1", "b2", "b3"), dwell=600)]
    stops = route_script_to_stops(pois, beats, {})
    assert stops[0]["lens_name"] == "dark_history"


def test_dominant_lens_tie_breaks_by_name():
    beats = {
        "b1": _beat("b1", "p1", ("zeta",)),
        "b2": _beat("b2", "p1", ("alpha",)),
    }
    pois = [_poi("p1", "Square", tier=3, beat_ids=("b1", "b2"), dwell=120)]
    stops = route_script_to_stops(pois, beats, {})
    assert stops[0]["lens_name"] == "alpha"  # tie -> lexicographically smallest


def test_no_lensed_beat_gives_none_lens():
    beats = {"b1": _beat("b1", "p1", ())}
    pois = [_poi("p1", "Plaque", tier=2, beat_ids=("b1",), dwell=60)]
    stops = route_script_to_stops(pois, beats, {})
    assert stops[0]["lens_name"] is None


def test_the_adapter_never_spells_a_clock_it_writes_the_one_it_is_handed():
    """Phase 5 S5.10 (design §4.6, the session clock seam): the server has ONE
    re-timing expression — `src.tour.contingency.stop_clocks`, walks and priced
    visits — and the wire's per-stop `start_time` is a view of it. This adapter
    used to run a second, walk-less clock (dwell only) that the phone showed as
    arrival times; it now writes exactly the HH:MM the caller hands it, per stop,
    and "" for a stop nobody clocked. `duration_min` is still its own reading of
    the stop's dwell."""
    pois = [
        _poi("p1", "A", tier=5, beat_ids=("b1",), dwell=3000),  # 50 min
        _poi("p2", "B", tier=4, beat_ids=("b2",), dwell=1800),  # 30 min
    ]
    stops = route_script_to_stops(pois, {}, {"p1": "09:00", "p2": "10:04"})
    assert stops[0]["start_time"] == "09:00"
    assert stops[0]["duration_min"] == 50
    # 09:00 + 50 min dwell would be 09:50 on the old dwell-only clock; the walk
    # in between is the caller's expression's business, and it said 10:04.
    assert stops[1]["start_time"] == "10:04"
    assert stops[1]["duration_min"] == 30
    assert route_script_to_stops(pois, {}, {})[1]["start_time"] == ""


def test_empty_selection_yields_no_stops():
    assert route_script_to_stops([], {}, {}) == []


def _script(pois: list[ScriptPOI], sentences: list[Sentence]) -> Script:
    return Script(
        city_slug="paris",
        generated_at="2026-06-13T00:00:00+00:00",
        inputs=TourInput(start=(48.85, 2.35), duration_min=60, city_slug="paris"),
        total_audio_seconds=0,
        total_walking_seconds=0,
        total_walk_distance_m=0,
        total_planned_seconds=0,
        selected_pois=tuple(pois),
        lens_coverage={},
        script=tuple(sentences),
        validation=ValidationReport(),
    )


def test_narration_attached_per_stop_when_script_passed():
    pois = [
        _poi("p1", "Eiffel Tower", tier=5, beat_ids=("b1",), dwell=600),
        _poi("p2", "Notre-Dame", tier=4, beat_ids=("b2",), dwell=300),
    ]
    script = _script(
        pois,
        [
            Sentence(text="Settle in.", source_id="GLUE_PACING", source_type="glue", stop_idx=0),
            Sentence(
                text="The tower opened in 1889.", source_id="b1", source_type="beat", stop_idx=0
            ),
            Sentence(
                text="The cathedral began in 1160.", source_id="b2", source_type="beat", stop_idx=1
            ),
        ],
    )
    stops = route_script_to_stops(pois, {}, {}, script=script)
    assert stops[0]["narration"] == "Settle in. The tower opened in 1889."
    assert stops[1]["narration"] == "The cathedral began in 1160."


def test_narration_empty_when_no_script():
    pois = [_poi("p1", "A", tier=5, beat_ids=("b1",), dwell=600)]
    stops = route_script_to_stops(pois, {}, {})
    assert stops[0]["narration"] == ""


def test_stops_carry_extra_beat_ids_when_provided():
    pois = [
        _poi("p1", "Eiffel Tower", tier=5, beat_ids=("b1", "b2"), dwell=600),
        _poi("p2", "Notre-Dame", tier=4, beat_ids=("b3",), dwell=300),
    ]
    stops = route_script_to_stops(pois, {}, {}, extra_by_poi={"p1": ("x1", "x2"), "p2": ()})
    assert stops[0]["extra_beat_ids"] == ["x1", "x2"]
    assert stops[1]["extra_beat_ids"] == []


def test_stops_extra_beat_ids_default_empty_without_map():
    pois = [_poi("p1", "Eiffel Tower", tier=5, beat_ids=("b1",), dwell=600)]
    stops = route_script_to_stops(pois, {}, {})
    assert stops[0]["extra_beat_ids"] == []
