"""Tests for upload_paris hardening: city geofence, disputed-exclusion, and the
pre-upload validate_beats gate. The full DB upload path needs Neo4j and is not
exercised here — these cover the pure guards that decide what is allowed up."""

from __future__ import annotations

import json

import pytest

from scripts.upload_paris import _assert_beats_valid, _beat_blocked, _in_city_bounds


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
