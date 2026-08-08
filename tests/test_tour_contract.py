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
        target_dwell_seconds=1800,
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


def test_a_poi_without_visit_capacity_still_constructs_and_defaults_safely():
    """The three visit-capacity fields must be additive, or every corpus breaks.

    Step 2.7's whole safety argument rests on this: the fields land on the
    contract BEFORE the capacity pass has run over any city, so a POI that knows
    nothing about them has to construct and report values that reproduce today's
    behaviour exactly.

    The `0` default is load-bearing rather than a placeholder. Generation floors a
    stop at `max(planned_visit, planned_audio)`, so a visit time of 0 means the
    stop lasts exactly as long as its narration — which is what happens today.
    A `None` default here would raise instead, and a non-zero one would silently
    lengthen every stop in every unpriced city.
    """
    poi = POI(
        id="no-capacity",
        name="A place nobody has priced yet",
        tier=3,
        poi_role="stop",
        lat=48.8566,
        lng=2.3522,
    )
    assert poi.typical_duration_min == 0
    assert poi.visit_seconds_inside is None
    assert poi.visit_basis == ""

    # And a fully priced POI carries them through unchanged.
    priced = POI(
        id="priced",
        name="Sainte-Chapelle",
        tier=5,
        poi_role="stop",
        lat=48.8554,
        lng=2.3450,
        typical_duration_min=15,
        visit_seconds_inside=3960,
        visit_basis="Modest exterior; inside is a 28-minute queue plus 38 under the glass.",
    )
    assert priced.typical_duration_min == 15
    assert priced.visit_seconds_inside == 3960
    assert priced.visit_basis.startswith("Modest exterior")


def test_every_transit_segment_declares_its_mode():
    """Walking is the only mode Release 1 plans, and it must be SAID.

    The field exists so adding public transport later is an addition rather than a
    rewrite. Without it, "these seconds are walking seconds" is an unstated
    assumption baked into every leg calculation — the pace correction, the walk
    budget, the reach envelope — and a transit leg would silently inherit all of
    them.
    """
    seg = TransitSegment(
        from_poi_id=None, to_poi_id="a", distance_m=100.0, walk_seconds=120
    )
    assert seg.mode == "walk"
