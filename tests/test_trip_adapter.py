"""Hermetic unit tests for route_script_to_stops (M0b adapter).

Pure-function tests: hand-built engine contract objects, NO database, NO engine
run, NO corpus. See specs/2026-06-12-tour-algorithm-decision/M0b-DESIGN.md.
"""

from __future__ import annotations

from src.api.crud.trips import route_script_to_stops
from src.tour.contract import BeatRef, ScriptPOI


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
    stops = route_script_to_stops(pois, {}, "09:00")
    assert [s["poi_id"] for s in stops] == ["p1", "p2"]
    assert [s["sort_order"] for s in stops] == [1, 2]


def test_all_beats_kept_with_primary():
    beats = {
        "b1": _beat("b1", "p1", ("dark_history",)),
        "b2": _beat("b2", "p1", ("dark_history",)),
        "b3": _beat("b3", "p1", ("architecture",)),
    }
    pois = [_poi("p1", "Louvre", tier=5, beat_ids=("b1", "b2", "b3"), dwell=600)]
    stops = route_script_to_stops(pois, beats, "09:00")
    assert stops[0]["beat_ids"] == ["b1", "b2", "b3"]
    assert stops[0]["primary_beat_id"] == "b1"


def test_dominant_lens_is_most_common():
    beats = {
        "b1": _beat("b1", "p1", ("dark_history",)),
        "b2": _beat("b2", "p1", ("dark_history",)),
        "b3": _beat("b3", "p1", ("architecture",)),
    }
    pois = [_poi("p1", "Louvre", tier=5, beat_ids=("b1", "b2", "b3"), dwell=600)]
    stops = route_script_to_stops(pois, beats, "09:00")
    assert stops[0]["lens_name"] == "dark_history"


def test_dominant_lens_tie_breaks_by_name():
    beats = {
        "b1": _beat("b1", "p1", ("zeta",)),
        "b2": _beat("b2", "p1", ("alpha",)),
    }
    pois = [_poi("p1", "Square", tier=3, beat_ids=("b1", "b2"), dwell=120)]
    stops = route_script_to_stops(pois, beats, "09:00")
    assert stops[0]["lens_name"] == "alpha"  # tie -> lexicographically smallest


def test_no_lensed_beat_gives_none_lens():
    beats = {"b1": _beat("b1", "p1", ())}
    pois = [_poi("p1", "Plaque", tier=2, beat_ids=("b1",), dwell=60)]
    stops = route_script_to_stops(pois, beats, "09:00")
    assert stops[0]["lens_name"] is None


def test_clock_advances_by_dwell():
    pois = [
        _poi("p1", "A", tier=5, beat_ids=("b1",), dwell=3000),  # 50 min
        _poi("p2", "B", tier=4, beat_ids=("b2",), dwell=1800),  # 30 min
    ]
    stops = route_script_to_stops(pois, {}, "09:00")
    assert stops[0]["start_time"] == "09:00"
    assert stops[0]["duration_min"] == 50
    assert stops[1]["start_time"] == "09:50"
    assert stops[1]["duration_min"] == 30


def test_empty_selection_yields_no_stops():
    assert route_script_to_stops([], {}, "09:00") == []
