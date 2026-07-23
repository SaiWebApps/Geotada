"""Hermetic tests for _snapshot_from_records — the Neo4j → CorpusSnapshot
parse, including the M7 provenance fields. No DB."""

from __future__ import annotations

import pytest

from src.tour.corpus_places import CoordinateProvenance
from src.tour.selection import _snapshot_from_records


def _beat_record(**overrides) -> dict:
    base = {
        "id": "b1",
        "poi_id": "p1",
        "script_body": "Henri IV built the square.",
        "entities": ["Henri IV"],
        "active_status": "active",
        "lenses": ["hidden_history"],
    }
    base.update(overrides)
    return base


_POI_RECORD = {"id": "p1", "name": "Place des Vosges", "tier": 5, "poi_role": "stop",
               "lat": 48.85, "lng": 2.36, "areas": ["Le Marais"]}


def test_provenance_fields_parse_when_present():
    rec = _beat_record(
        source_passage="Henri IV built the square in 1612.",
        source_chunk_slug="vosges-ch3",
        key_claims=["Henri IV built it", "completed 1612"],
    )
    snap = _snapshot_from_records([_POI_RECORD], [rec], [], [], [])
    beat = snap.beats_for("p1")[0]
    assert beat.source_passage == "Henri IV built the square in 1612."
    assert beat.source_chunk_slug == "vosges-ch3"
    assert beat.key_claims == ("Henri IV built it", "completed 1612")


def test_provenance_fields_default_empty_when_absent():
    """The current corpus has no provenance props; the loader must not choke —
    Cypher returns null for a missing property, and the fields default."""
    snap = _snapshot_from_records([_POI_RECORD], [_beat_record()], [], [], [])
    beat = snap.beats_for("p1")[0]
    assert beat.source_passage is None
    assert beat.source_chunk_slug is None
    assert beat.key_claims == ()
    # existing fields still parse
    assert beat.script_body == "Henri IV built the square."
    assert beat.lenses == ("hidden_history",)


def test_key_claims_drops_blank_entries():
    rec = _beat_record(key_claims=["real claim", "", "  ", "another"])
    snap = _snapshot_from_records([_POI_RECORD], [rec], [], [], [])
    assert snap.beats_for("p1")[0].key_claims == ("real claim", "another")


def test_optional_stable_place_fields_round_trip_without_replacing_graph_ids():
    coordinates = CoordinateProvenance.build(
        authority_kind="corpus_record",
        authority_id="manifest:fixture",
        source_record_id="wikidata:Q1",
        coordinates=(48.85, 2.36),
        source_payload={"label": "Place des Vosges"},
    )
    poi_record = {
        **_POI_RECORD,
        "canonical_place_id": "paris:place-des-vosges",
        "aliases": ["Vosges", "Place Royale"],
        "coordinate_provenance": coordinates.model_dump_json(),
    }
    beat_record = _beat_record(
        stable_beat_id="paris:beat:vosges:1",
        place_plan_id="paris:place-plan:vosges:1",
        lenses=["history", "architecture"],
    )
    snap = _snapshot_from_records([poi_record], [beat_record], [], [], [])
    poi = snap.pois[0]
    beat = snap.beats_for("p1")[0]
    assert poi.id == "p1"  # D2 migrates graph/API identity; D1 is additive.
    assert poi.canonical_place_id == "paris:place-des-vosges"
    assert poi.aliases == ("Place Royale", "Vosges")
    assert poi.coordinate_provenance == coordinates
    assert beat.id == "b1"
    assert beat.stable_beat_id == "paris:beat:vosges:1"
    assert beat.place_plan_id == "paris:place-plan:vosges:1"
    assert beat.lenses == ("architecture", "history")


def test_present_malformed_coordinate_provenance_is_not_silently_dropped():
    with pytest.raises(ValueError, match="coordinate_provenance"):
        _snapshot_from_records(
            [{**_POI_RECORD, "coordinate_provenance": "not-json"}],
            [_beat_record()],
            [],
            [],
            [],
        )
