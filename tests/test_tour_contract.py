"""Phase 2 — contract.py: input validation + dataclass roundtrip."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.tour.contract import (
    POI,
    BeatRef,
    BeatSequence,
    POIBeats,
    Route,
    TourInput,
    TransitSegment,
)


def test_tour_input_minimal_valid():
    inp = TourInput(start=(48.8553, 2.3653), duration_min=60, city_slug="paris")
    assert inp.start == (48.8553, 2.3653)
    assert inp.round_trip is False
    assert inp.lenses is None


def test_tour_input_full_payload():
    inp = TourInput(
        start=(48.85675, 2.341033),
        duration_min=90,
        city_slug="paris",
        lenses=["historic_arch", "famous_residents"],
        round_trip=True,
        theme_hint="kings",
        start_label="Pont Neuf metro",
    )
    assert inp.lenses == ["historic_arch", "famous_residents"]
    assert inp.round_trip is True


def test_tour_input_strips_empty_lenses():
    inp = TourInput(
        start=(48.0, 2.0),
        duration_min=60,
        city_slug="paris",
        lenses=["historic_arch", "", "  "],
    )
    assert inp.lenses == ["historic_arch"]


def test_tour_input_empty_lens_list_normalized_to_none():
    inp = TourInput(start=(48.0, 2.0), duration_min=60, city_slug="paris", lenses=["", "  "])
    assert inp.lenses is None


def test_tour_input_rejects_bad_lat():
    with pytest.raises(ValidationError):
        TourInput(start=(120.0, 2.0), duration_min=60, city_slug="paris")


def test_tour_input_rejects_bad_lng():
    with pytest.raises(ValidationError):
        TourInput(start=(48.0, 200.0), duration_min=60, city_slug="paris")


def test_tour_input_rejects_zero_duration():
    with pytest.raises(ValidationError):
        TourInput(start=(48.0, 2.0), duration_min=0, city_slug="paris")


def test_tour_input_rejects_extra_keys():
    with pytest.raises(ValidationError):
        TourInput(
            start=(48.0, 2.0),
            duration_min=60,
            city_slug="paris",
            magic_field="oops",
        )


def test_tour_input_is_frozen():
    inp = TourInput(start=(48.0, 2.0), duration_min=60, city_slug="paris")
    with pytest.raises(ValidationError):
        inp.duration_min = 90


def test_tour_input_requires_city_slug():
    with pytest.raises(ValidationError):
        TourInput(start=(48.0, 2.0), duration_min=60, city_slug="")


def test_tour_input_accepts_end_destination():
    inp = TourInput(
        start=(48.8553, 2.3653), end=(48.8738, 2.2950), duration_min=90, city_slug="paris"
    )
    assert inp.end == (48.8738, 2.2950)


def test_tour_input_end_defaults_to_none():
    inp = TourInput(start=(48.8553, 2.3653), duration_min=60, city_slug="paris")
    assert inp.end is None


def test_tour_input_rejects_bad_end_lat():
    with pytest.raises(ValidationError):
        TourInput(start=(48.0, 2.0), end=(120.0, 2.0), duration_min=60, city_slug="paris")


def test_tour_input_rejects_bad_end_lng():
    with pytest.raises(ValidationError):
        TourInput(start=(48.0, 2.0), end=(48.0, 200.0), duration_min=60, city_slug="paris")


def test_tour_input_end_and_round_trip_are_mutually_exclusive():
    with pytest.raises(ValidationError):
        TourInput(
            start=(48.0, 2.0),
            end=(48.87, 2.29),
            duration_min=60,
            city_slug="paris",
            round_trip=True,
        )


def test_tour_input_round_trip_without_end_ok():
    inp = TourInput(start=(48.0, 2.0), duration_min=60, city_slug="paris", round_trip=True)
    assert inp.round_trip is True
    assert inp.end is None


def test_tour_input_end_round_trips_through_model_dump():
    inp = TourInput(start=(48.0, 2.0), end=(48.87, 2.29), duration_min=60, city_slug="paris")
    revived = TourInput(**inp.model_dump())
    assert revived.end == (48.87, 2.29)
    assert revived == inp


def test_poi_dataclass_roundtrip():
    p = POI(
        id="poi-1",
        name="Place des Vosges",
        tier=5,
        poi_role="setting",
        lat=48.8555,
        lng=2.3656,
        areas=("Le Marais", "Paris"),
        beat_count=59,
        matching_lens_beat_count=12,
    )
    dumped = p.model_dump()
    revived = POI(**dumped)
    assert revived == p


def test_beat_ref_defaults():
    b = BeatRef(id="b1", poi_id="p1")
    assert b.sub_location is None
    assert b.entities == ()
    assert b.lenses == ()


def test_route_holds_segments_and_budgets():
    poi = POI(id="p1", name="X", tier=5, poi_role="stop", lat=48.85, lng=2.35)
    seg = TransitSegment(from_poi_id=None, to_poi_id="p1", distance_m=120, walk_seconds=144)
    r = Route(
        pois=(poi,),
        transits=(seg,),
        total_walk_distance_m=120.0,
        total_walk_seconds=144,
        spine_area="Le Marais",
        target_audio_seconds=1800,
        err_short_total_seconds=2988,
    )
    assert r.pois[0].name == "X"
    assert r.spine_area == "Le Marais"


def test_beat_sequence_holds_strategies():
    pb = POIBeats(
        poi_id="p1",
        poi_name="X",
        ordering_strategy="sub_location",
        beats=(BeatRef(id="b1", poi_id="p1"),),
    )
    seq = BeatSequence(poi_beats=(pb,))
    assert seq.poi_beats[0].ordering_strategy == "sub_location"


def test_beat_sequence_rejects_invalid_strategy():
    with pytest.raises(ValidationError):
        POIBeats(
            poi_id="p",
            poi_name="X",
            ordering_strategy="random",  # type: ignore[arg-type]
            beats=(),
        )
