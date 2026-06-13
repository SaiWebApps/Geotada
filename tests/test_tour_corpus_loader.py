"""Hermetic tests for _snapshot_from_records — the Neo4j → CorpusSnapshot
parse, including the M7 provenance fields. No DB."""

from __future__ import annotations

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
