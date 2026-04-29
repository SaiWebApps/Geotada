"""TestClient-based tests for audio API routes using the MOCK provider.

No API keys, no Neo4j — all external dependencies are mocked or use the
mock TTS provider. These tests cover the audio route handlers at the HTTP level.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app


@pytest.fixture(autouse=True)
def _temp_audio_storage(monkeypatch, tmp_path):
    """Point audio storage at a temp dir for all tests."""
    monkeypatch.setenv("AUDIO_STORAGE_PATH", str(tmp_path))
    monkeypatch.setenv("AUDIO_STORAGE", "local")


@pytest.fixture()
def client():
    """TestClient that skips Neo4j initialization.

    Audio routes that don't need a session (providers, preview, compare, download,
    serve files) work without a real driver. We mock init_driver/close_driver
    so the lifespan doesn't try to connect to Neo4j.
    """
    with patch("src.api.app.init_driver"), patch("src.api.app.close_driver"):
        app = create_app()
        with TestClient(app) as c:
            yield c


# ── GET /audio/providers ──


class TestGetProviders:
    def test_returns_provider_list(self, client):
        resp = client.get("/api/v1/audio/providers")
        assert resp.status_code == 200
        data = resp.json()
        assert "providers" in data
        names = [p["name"] for p in data["providers"]]
        assert "mock" in names

    def test_mock_is_available(self, client):
        resp = client.get("/api/v1/audio/providers")
        data = resp.json()
        mock_info = next(p for p in data["providers"] if p["name"] == "mock")
        assert mock_info["available"] is True


# ── POST /audio/preview ──


class TestPreviewAudio:
    def test_mock_returns_wav(self, client):
        resp = client.post("/api/v1/audio/preview", json={
            "text": "Hello, welcome to Paris.",
            "provider": "mock",
        })
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "audio/wav"
        assert len(resp.content) > 100  # Should be a non-trivial WAV

    def test_unknown_provider_400(self, client):
        resp = client.post("/api/v1/audio/preview", json={
            "text": "Hello",
            "provider": "nonexistent",
        })
        assert resp.status_code == 400

    def test_empty_text_422(self, client):
        resp = client.post("/api/v1/audio/preview", json={
            "text": "",
            "provider": "mock",
        })
        assert resp.status_code == 422

    def test_content_disposition_header(self, client):
        resp = client.post("/api/v1/audio/preview", json={
            "text": "Test text",
            "provider": "mock",
        })
        assert resp.status_code == 200
        assert "content-disposition" in resp.headers
        assert "preview-mock.wav" in resp.headers["content-disposition"]


# ── POST /audio/compare ──


class TestCompareProviders:
    def test_mock_returns_results(self, client):
        resp = client.post("/api/v1/audio/compare", json={
            "text": "Hello, welcome to the Eiffel Tower.",
            "providers": ["mock"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["text"] == "Hello, welcome to the Eiffel Tower."
        assert len(data["results"]) == 1
        result = data["results"][0]
        assert result["provider"] == "mock"
        assert result["success"] is True
        assert result["size_bytes"] > 0
        assert result["download_path"] is not None

    def test_unknown_provider_in_compare_reports_error(self, client):
        resp = client.post("/api/v1/audio/compare", json={
            "text": "Test",
            "providers": ["nonexistent"],
        })
        assert resp.status_code == 200  # Partial failures are not HTTP errors
        data = resp.json()
        result = data["results"][0]
        assert result["success"] is False
        assert result["error"] is not None


# ── GET /audio/compare/download ──


class TestDownloadComparison:
    def test_missing_file_404(self, client):
        resp = client.get("/api/v1/audio/compare/download/nonexistent.wav")
        assert resp.status_code == 404

    def test_path_traversal_blocked(self, client):
        resp = client.get("/api/v1/audio/compare/download/../../etc/passwd")
        assert resp.status_code == 404  # Path.name strips traversal, file won't exist


# ── GET /audio/files/{key} ──


class TestServeAudioFile:
    def test_missing_file_404(self, client):
        resp = client.get("/api/v1/audio/files/nonexistent.mp3")
        assert resp.status_code == 404

    def test_path_traversal_blocked(self, client):
        """Path traversal attempts should not succeed — they get either 400 or 404."""
        resp = client.get("/api/v1/audio/files/../../etc/passwd")
        # Starlette normalizes URL path segments, so the handler may see a
        # sanitized key. Either way, no file content should be returned.
        assert resp.status_code in (400, 404)
        assert b"root:" not in resp.content  # No /etc/passwd content leaked

    def test_serve_existing_file(self, client, tmp_path):
        """Upload a file via local storage, then serve it via the API."""
        from src.audio.storage import LocalStorageProvider

        storage = LocalStorageProvider()
        key = "test/hello.wav"
        storage.upload(b"RIFF" + b"\x00" * 100, key)

        resp = client.get(f"/api/v1/audio/files/{key}")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "audio/wav"
