"""Tests for upload_paris hardening: city geofence, disputed-exclusion, the
pre-upload validate_beats gate, and (Step 4.0) the provenance fields —
source_passage / source_chunk_slug / key_claims — on both the upload path and
the targeted backfill (which must never run the audio_url-wiping full upload)."""

from __future__ import annotations

import json

import pytest

from scripts.upload_paris import (
    _assert_beats_valid,
    _backfill_provenance,
    _beat_blocked,
    _in_city_bounds,
    _provenance_fields,
    _upload_beats,
)
from src.connection import get_database
from tests.conftest import needs_neo4j


def test_in_city_bounds_accepts_paris():
    assert _in_city_bounds(48.8566, 2.3522)


@pytest.mark.parametrize("lat,lon", [(42.36, -71.06), (0.0, 0.0), (48.85, 3.50), (51.5, 2.3)])
def test_in_city_bounds_rejects_out_of_city(lat, lon):
    assert not _in_city_bounds(lat, lon)


def _beat(status: str) -> dict:
    return {"poi_name": "X", "script_body": "b", "fact_check": {"status": status}}


def test_beat_blocked_disputed():
    assert _beat_blocked(_beat("disputed"))


def test_beat_not_blocked_verified_or_unverified():
    assert not _beat_blocked(_beat("verified"))
    assert not _beat_blocked(_beat("unverified"))


def test_beat_blocked_missing_essentials():
    assert _beat_blocked({"poi_name": "X", "script_body": ""})
    assert _beat_blocked({"poi_name": "", "script_body": "b"})


def _min_beat(beat_id: str, topic: str, body_hash: str) -> dict:
    return {
        "beat_id": beat_id,
        "city_name": "paris",
        "poi_name": "X",
        "lens": "historic_arch",
        "book_slug": "legacy_unknown",
        "topic_slug": topic,
        "source_chunk_slug": "legacy_ambiguous",
        "script_body_hash": body_hash,
    }


def test_assert_beats_valid_passes(tmp_path):
    p = tmp_path / "beats.json"
    p.write_text(json.dumps([_min_beat("a", "t", "h1")]))
    _assert_beats_valid(p)  # must not raise


def test_assert_beats_valid_raises_on_invalid(tmp_path):
    """A dup script_body_hash trips validate_beats → upload is refused."""
    p = tmp_path / "beats.json"
    p.write_text(json.dumps([_min_beat("a", "t1", "dup"), _min_beat("b", "t2", "dup")]))
    with pytest.raises(RuntimeError):
        _assert_beats_valid(p)


# ---------------------------------------------------------------------------
# Step 4.0 — provenance fields (source_passage / source_chunk_slug / key_claims)
# ---------------------------------------------------------------------------


def test_provenance_fields_present():
    beat = {
        "source_passage": "  The bridge was completed in 1607.  ",
        "source_chunk_slug": "pariswalks-chunk-03",
        "key_claims": ["Pont Neuf completed 1607", "  ", "Oldest standing bridge in Paris"],
    }
    fields = _provenance_fields(beat)
    assert fields["source_passage"] == "The bridge was completed in 1607."
    assert fields["source_chunk_slug"] == "pariswalks-chunk-03"
    assert fields["key_claims"] == ["Pont Neuf completed 1607", "Oldest standing bridge in Paris"]


def test_provenance_fields_absent_normalize_to_none():
    """Missing / empty / whitespace-only inputs all map to None so Neo4j's
    SET-null-removes-property semantics keep the keys absent, never null."""
    for beat in ({}, {"source_passage": "", "source_chunk_slug": "  ", "key_claims": []},
                 {"key_claims": ["", "   "]}):
        fields = _provenance_fields(beat)
        assert fields == {
            "source_passage": None,
            "source_chunk_slug": None,
            "key_claims": None,
        }


def _provenance_beat(beat_id: str, poi_name: str, *, with_fields: bool) -> dict:
    beat = {
        "beat_id": beat_id,
        "poi_name": poi_name,
        "script_body": "A fact. Another fact.",
        "fact_check": {"status": "verified"},
    }
    if with_fields:
        beat.update(
            source_passage="A fact from the source book.",
            source_chunk_slug="test-book-chunk-01",
            key_claims=["claim one", "claim two"],
        )
    return beat


@needs_neo4j
class TestProvenanceUploadAndBackfill:
    POI_NAME = "Provenance Test POI"

    def _seed_poi(self, driver) -> None:
        with driver.session(database=get_database()) as s:
            s.run(
                "MERGE (p:POI {name: $name}) SET p.id = 'prov-test-poi'",
                name=self.POI_NAME,
            )

    def _beat_props(self, driver, beat_id: str) -> dict:
        with driver.session(database=get_database()) as s:
            rec = s.run(
                "MATCH (b:NarrativeBeat {beat_id: $bid}) RETURN properties(b) AS props",
                bid=beat_id,
            ).single()
            return rec["props"] if rec else {}

    def test_upload_writes_provenance_and_absence_stays_absent(self, clean_driver):
        self._seed_poi(clean_driver)
        beats = [
            _provenance_beat("prov-b1", self.POI_NAME, with_fields=True),
            _provenance_beat("prov-b2", self.POI_NAME, with_fields=False),
        ]
        with clean_driver.session(database=get_database()) as s:
            stats = _upload_beats(s, beats)
        assert stats["linked"] == 2

        b1 = self._beat_props(clean_driver, "prov-b1")
        assert b1["source_passage"] == "A fact from the source book."
        assert b1["source_chunk_slug"] == "test-book-chunk-01"
        assert list(b1["key_claims"]) == ["claim one", "claim two"]

        b2 = self._beat_props(clean_driver, "prov-b2")
        assert "source_passage" not in b2
        assert "source_chunk_slug" not in b2
        assert "key_claims" not in b2

    def test_backfill_sets_only_provenance_on_existing_beats(self, clean_driver):
        """The targeted backfill sets the three fields by beat_id and leaves
        every other property (esp. audio_url) untouched."""
        with clean_driver.session(database=get_database()) as s:
            s.run(
                "MERGE (b:NarrativeBeat {beat_id: 'prov-b3'}) "
                "SET b.id = 'prov-b3-id', b.script_body = 'Body.', "
                "    b.audio_url = 'https://example.com/existing.mp3'"
            )
            stats = _backfill_provenance(
                s,
                [
                    _provenance_beat("prov-b3", self.POI_NAME, with_fields=True),
                    _provenance_beat("prov-missing", self.POI_NAME, with_fields=True),
                    _provenance_beat("prov-no-fields", self.POI_NAME, with_fields=False),
                ],
            )
        # prov-missing has no node (MATCH skips); prov-no-fields has nothing to set.
        assert stats == {"updated": 1, "candidates": 2}
        b3 = self._beat_props(clean_driver, "prov-b3")
        assert list(b3["key_claims"]) == ["claim one", "claim two"]
        assert b3["source_passage"] == "A fact from the source book."
        assert b3["audio_url"] == "https://example.com/existing.mp3"
