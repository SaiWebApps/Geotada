"""Track B (API half) — _preview_stops interleaves walk-past vignettes."""

from __future__ import annotations

import datetime as dt

from src.api.routes.trips import _preview_stops
from src.tour.contract import (
    POI,
    BeatRef,
    Route,
    Script,
    ScriptPOI,
    Sentence,
    TourInput,
    TransitSegment,
    ValidationReport,
)
from src.tour.selection import CorpusSnapshot


def _poi(pid: str, tier: int = 2) -> POI:
    return POI(id=pid, name=pid, tier=tier, poi_role="walk_by_only", lat=48.85, lng=2.36)


def _script_two_stops() -> Script:
    return Script(
        city_slug="paris",
        generated_at=dt.datetime(2026, 7, 2, tzinfo=dt.UTC).isoformat(),
        inputs=TourInput(start=(48.85, 2.36), duration_min=60, city_slug="paris"),
        total_audio_seconds=60,
        total_walking_seconds=60,
        total_walk_distance_m=100,
        total_planned_seconds=120,
        selected_pois=(
            ScriptPOI(id="d0", name="Dwell Zero", tier=5, lat=48.85, lng=2.36,
                      dwell_seconds=600),
            ScriptPOI(id="d1", name="Dwell One", tier=5, lat=48.86, lng=2.37,
                      dwell_seconds=300),
        ),
        lens_coverage={},
        script=(
            Sentence(text="Stop zero story.", source_id="GLUE_PACING",
                     source_type="glue", stop_idx=0),
            Sentence(text="Stop one story.", source_id="GLUE_PACING",
                     source_type="glue", stop_idx=1),
        ),
        validation=ValidationReport(),
    )


def _route(vignettes) -> Route:
    pois = (POI(id="d0", name="Dwell Zero", tier=5, poi_role="stop", lat=48.85, lng=2.36),
            POI(id="d1", name="Dwell One", tier=5, poi_role="stop", lat=48.86, lng=2.37))
    transits = tuple(
        TransitSegment(from_poi_id=None, to_poi_id=p.id, distance_m=100.0, walk_seconds=60)
        for p in pois
    )
    return Route(
        pois=pois, transits=transits, total_walk_distance_m=200.0,
        total_walk_seconds=120, vignettes=vignettes,
    )


def _snapshot(vpoi: POI, beat: BeatRef) -> CorpusSnapshot:
    return CorpusSnapshot(
        pois=(vpoi,), beats_by_poi={vpoi.id: (beat,)}, area_types={}, adjacent_areas={}
    )


def test_vignette_interleaves_before_its_leg_destination():
    vpoi = _poi("v1")
    beat = BeatRef(id="vb1", poi_id="v1",
                   script_body="A tiny plaque marks the spot. More detail here.")
    stops = _preview_stops(
        _script_two_stops(),
        _route({1: (vpoi,)}),
        {1: (beat,)},
        _snapshot(vpoi, beat),
        {},
    )
    assert [s.band for s in stops] == ["dwell", "vignette", "dwell"]
    assert [s.sort_order for s in stops] == [1, 2, 3]
    vignette = stops[1]
    assert vignette.poi_name == "v1"
    assert vignette.minutes == 0
    assert vignette.narration == "A tiny plaque marks the spot."
    assert vignette.spotlight > 0
    # Dwell stops keep their narration blocks untouched.
    assert stops[0].narration == "Stop zero story."
    assert stops[2].narration == "Stop one story."


def test_no_vignettes_is_todays_shape():
    stops = _preview_stops(
        _script_two_stops(), _route({}), {}, _snapshot(_poi("vx"), BeatRef(id="b", poi_id="vx")), {}
    )
    assert [s.band for s in stops] == ["dwell", "dwell"]
    assert [s.sort_order for s in stops] == [1, 2]


def test_unvoiceable_vignette_is_not_shown():
    """A vignette POI with no voiceable beat is dropped from the cards —
    what is not voiced is not shown."""
    vpoi = _poi("v1")
    beat = BeatRef(id="vb1", poi_id="v1")  # no script_body
    stops = _preview_stops(
        _script_two_stops(), _route({1: (vpoi,)}), {}, _snapshot(vpoi, beat), {}
    )
    assert [s.band for s in stops] == ["dwell", "dwell"]


def test_deeper_dive_flag_reflects_overflow_by_poi():
    """KE9: a dwell stop gets has_deeper_dive=True iff its poi_id has non-empty
    overflow in overflow_by_poi; other dwell stops are False. Vignette stops are
    always False (walk-past has no 'keep exploring here' extras)."""
    vpoi = _poi("v1")
    beat = BeatRef(id="vb1", poi_id="v1",
                   script_body="A tiny plaque marks the spot. More detail here.")
    # d0 capped some beats out (extras exist); d1 did not. The vignette sits on
    # leg 1, between the two dwell stops.
    stops = _preview_stops(
        _script_two_stops(),
        _route({1: (vpoi,)}),
        {1: (beat,)},
        _snapshot(vpoi, beat),
        {"d0": ("extra-b1", "extra-b2")},
    )
    assert [s.band for s in stops] == ["dwell", "vignette", "dwell"]
    # d0: overflow present -> deeper-dive badge.
    assert stops[0].has_deeper_dive is True
    # The interleaved vignette never carries the flag.
    assert stops[1].has_deeper_dive is False
    # d1: no overflow -> no badge.
    assert stops[2].has_deeper_dive is False


def test_deeper_dive_flag_false_when_no_overflow():
    """KE9: with an empty overflow_by_poi every stop stays has_deeper_dive=False —
    behavior-preserving default."""
    stops = _preview_stops(
        _script_two_stops(), _route({}), {}, _snapshot(_poi("vx"), BeatRef(id="b", poi_id="vx")), {}
    )
    assert [s.band for s in stops] == ["dwell", "dwell"]
    assert all(s.has_deeper_dive is False for s in stops)
