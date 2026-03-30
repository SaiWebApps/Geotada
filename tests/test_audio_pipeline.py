"""Unit tests for the audio generation pipeline.

Uses mocked Neo4j sessions — does NOT require a running database.
"""

from __future__ import annotations

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from src.audio.pipeline import (
    GenerationResult,
    PipelineError,
    _build_storage_key,
    _get_duration,
    generate_batch,
    generate_beat_audio,
)


@pytest.fixture(autouse=True)
def _temp_storage(monkeypatch, tmp_path):
    """Use a temp directory for audio storage in all tests."""
    monkeypatch.setenv("AUDIO_STORAGE_PATH", str(tmp_path))


def _mock_beat(beat_id="beat-001", script_body="Test script.", audio_url="s3://placeholder/test.mp3"):
    return {
        "id": beat_id,
        "labels": ["NarrativeBeat"],
        "properties": {
            "id": beat_id,
            "script_body": script_body,
            "audio_url": audio_url,
        },
    }


def _mock_session_with_poi(poi_name="Test POI"):
    session = MagicMock()
    poi_record = MagicMock()
    poi_record.__getitem__ = lambda self, key: poi_name
    session.run.return_value.single.return_value = poi_record
    return session


class TestBuildStorageKey:
    def test_with_poi_name(self):
        assert _build_storage_key("abc", "Eiffel Tower") == "beats/eiffel_tower/abc.mp3"

    def test_without_poi_name(self):
        assert _build_storage_key("abc", None) == "beats/unknown/abc.mp3"

    def test_strips_apostrophes(self):
        assert "'" not in _build_storage_key("abc", "Shakespeare's Book")


class TestGenerateBeatAudio:
    def test_generates_and_stores(self):
        session = _mock_session_with_poi("Eiffel Tower")
        with patch("src.audio.pipeline.get_node", return_value=_mock_beat()), \
             patch("src.audio.pipeline.update_node") as mock_update:
            result = generate_beat_audio(session, "beat-001", provider_name="mock")

        assert isinstance(result, GenerationResult)
        assert result.beat_id == "beat-001"
        assert result.provider == "mock"
        assert result.storage == "local"
        assert result.size_bytes > 0
        assert "eiffel_tower" in result.audio_url
        mock_update.assert_called_once()

    def test_skips_existing_audio(self):
        with patch("src.audio.pipeline.get_node", return_value=_mock_beat(
            audio_url="/api/v1/audio/files/real.mp3"
        )):
            with pytest.raises(PipelineError, match="already has audio"):
                generate_beat_audio(MagicMock(), "beat-001", provider_name="mock")

    def test_force_regenerates(self):
        session = _mock_session_with_poi()
        with patch("src.audio.pipeline.get_node", return_value=_mock_beat(
            audio_url="/api/v1/audio/files/real.mp3"
        )), patch("src.audio.pipeline.update_node"):
            result = generate_beat_audio(session, "beat-001", provider_name="mock", force=True)
        assert result.size_bytes > 0

    def test_missing_beat_raises(self):
        with patch("src.audio.pipeline.get_node", return_value=None):
            with pytest.raises(PipelineError, match="not found"):
                generate_beat_audio(MagicMock(), "nonexistent")

    def test_empty_script_body_raises(self):
        with patch("src.audio.pipeline.get_node", return_value=_mock_beat(script_body="")):
            with pytest.raises(PipelineError, match="no script_body"):
                generate_beat_audio(MagicMock(), "beat-001")

    def test_placeholder_url_is_regenerated(self):
        session = _mock_session_with_poi()
        with patch("src.audio.pipeline.get_node", return_value=_mock_beat(
            audio_url="s3://travlr-audio/placeholder/test.mp3"
        )), patch("src.audio.pipeline.update_node"):
            result = generate_beat_audio(session, "beat-001", provider_name="mock")
        assert result.size_bytes > 0


class TestGenerateBatch:
    def test_processes_placeholder_beats(self):
        class FakeRecord:
            def __init__(self, bid, url):
                self._data = {"id": bid, "audio_url": url}
            def __getitem__(self, key):
                return self._data[key]

        session = MagicMock()
        call_count = [0]

        def smart_run(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return [FakeRecord("b1", "s3://placeholder/a.mp3")]
            result = MagicMock()
            poi = MagicMock()
            poi.__getitem__ = lambda self, k: "Test POI"
            result.single.return_value = poi
            return result

        session.run = smart_run

        with patch("src.audio.pipeline.get_node", return_value=_mock_beat(beat_id="b1")), \
             patch("src.audio.pipeline.update_node"):
            results = generate_batch(session, provider_name="mock")

        successes = [r for r in results if isinstance(r, GenerationResult)]
        assert len(successes) == 1
        assert successes[0].beat_id == "b1"


class TestGetDuration:
    def test_wav_duration(self):
        """Mock provider generates WAV — duration should match expected."""
        from src.audio.provider import MockTTSProvider

        provider = MockTTSProvider()
        # "one two three four five" = 5 words → 5/2.5 = 2.0 seconds
        audio = provider.generate("one two three four five")
        duration = _get_duration(audio)
        assert abs(duration - 2.0) < 0.1

    def test_wav_minimum_duration(self):
        """Short text should still produce at least 1 second."""
        from src.audio.provider import MockTTSProvider

        provider = MockTTSProvider()
        audio = provider.generate("hi")
        duration = _get_duration(audio)
        assert abs(duration - 1.0) < 0.1

    def test_unknown_format_returns_zero(self):
        """Garbage bytes should return 0.0, not crash."""
        assert _get_duration(b"not audio data at all") == 0.0

    def test_empty_bytes_returns_zero(self):
        assert _get_duration(b"") == 0.0

    def test_result_includes_duration(self):
        """generate_beat_audio should populate duration_sec in the result."""
        session = _mock_session_with_poi("Test POI")
        with patch("src.audio.pipeline.get_node", return_value=_mock_beat()), \
             patch("src.audio.pipeline.update_node") as mock_update:
            result = generate_beat_audio(session, "beat-001", provider_name="mock")

        assert result.duration_sec > 0
        # Verify duration_sec was persisted to Neo4j
        update_call = mock_update.call_args
        props = update_call[0][3]  # 4th positional arg is the properties dict
        assert "duration_sec" in props
        assert props["duration_sec"] > 0
