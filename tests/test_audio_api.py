"""TestClient-based tests for audio API routes using the MOCK provider.

No API keys, no Neo4j — all external dependencies are mocked or use the
mock TTS provider. These tests cover the audio route handlers at the HTTP level.
"""

from __future__ import annotations

from unittest.mock import patch

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
        resp = client.post(
            "/api/v1/audio/preview",
            json={
                "text": "Hello, welcome to Paris.",
                "provider": "mock",
            },
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "audio/wav"
        assert len(resp.content) > 100  # Should be a non-trivial WAV

    def test_unknown_provider_400(self, client):
        resp = client.post(
            "/api/v1/audio/preview",
            json={
                "text": "Hello",
                "provider": "nonexistent",
            },
        )
        assert resp.status_code == 400

    def test_empty_text_422(self, client):
        resp = client.post(
            "/api/v1/audio/preview",
            json={
                "text": "",
                "provider": "mock",
            },
        )
        assert resp.status_code == 422

    def test_content_disposition_header(self, client):
        resp = client.post(
            "/api/v1/audio/preview",
            json={
                "text": "Test text",
                "provider": "mock",
            },
        )
        assert resp.status_code == 200
        assert "content-disposition" in resp.headers
        assert "preview-mock.wav" in resp.headers["content-disposition"]


# ── POST /audio/compare ──


class TestCompareProviders:
    def test_mock_returns_results(self, client):
        resp = client.post(
            "/api/v1/audio/compare",
            json={
                "text": "Hello, welcome to the Eiffel Tower.",
                "providers": ["mock"],
            },
        )
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
        resp = client.post(
            "/api/v1/audio/compare",
            json={
                "text": "Test",
                "providers": ["nonexistent"],
            },
        )
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


# ── POST /audio/eval — regenerate-on-degraded resilience ──


class TestEvalRegeneratesOnDegradedAudio:
    """A transient degraded TTS generation (implausibly high WER, e.g. a
    near-silent 200 response Whisper reads as "you") is retried; the endpoint
    keeps the best result rather than failing an otherwise-good voice. The mock
    provider (deterministically silent) is evaluated once, never looped."""

    def test_retries_past_a_degraded_generation(self, client, monkeypatch):
        from src.api.routes import audio as audio_routes
        from src.audio.eval import EvalResult

        class _FakeOpenAI:
            name = "openai"

            def generate(self, text, *, voice_id=None):
                return b"audio-bytes"

        monkeypatch.setattr(audio_routes, "get_provider", lambda name: _FakeOpenAI())
        calls = {"n": 0}

        def fake_evaluate(text, audio, *, filename="x"):
            calls["n"] += 1
            if calls["n"] == 1:  # first generation is degraded (WER ~1.0)
                return EvalResult(
                    original_text=text, transcribed_text="you", similarity_score=0.0,
                    word_error_rate=0.98, missing_words=["a", "b"], extra_words=[],
                )
            return EvalResult(  # regeneration is clean
                original_text=text, transcribed_text=text, similarity_score=1.0,
                word_error_rate=0.0, missing_words=[], extra_words=[],
            )

        monkeypatch.setattr(audio_routes, "evaluate", fake_evaluate)

        resp = client.post(
            "/api/v1/audio/eval", json={"text": "A grounded line.", "provider": "openai"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert calls["n"] == 2, "the endpoint must regenerate once past a degraded result"
        assert data["verdict"] == "PASS"
        assert data["word_error_rate"] == 0.0

    def test_persistent_degradation_still_surfaces(self, client, monkeypatch):
        """If EVERY generation is degraded (a real bad voice), the retries
        exhaust and the FAIL verdict still surfaces — resilience never masks a
        genuine quality failure."""
        from src.api.routes import audio as audio_routes
        from src.audio.eval import EvalResult

        class _FakeOpenAI:
            name = "openai"

            def generate(self, text, *, voice_id=None):
                return b"audio-bytes"

        monkeypatch.setattr(audio_routes, "get_provider", lambda name: _FakeOpenAI())
        calls = {"n": 0}

        def always_degraded(text, audio, *, filename="x"):
            calls["n"] += 1
            return EvalResult(
                original_text=text, transcribed_text="you", similarity_score=0.0,
                word_error_rate=0.98, missing_words=["a"], extra_words=[],
            )

        monkeypatch.setattr(audio_routes, "evaluate", always_degraded)

        resp = client.post(
            "/api/v1/audio/eval", json={"text": "A grounded line.", "provider": "openai"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert calls["n"] == 3, "a persistently degraded voice exhausts the bounded retries"
        assert data["verdict"] == "FAIL", "a genuine quality failure must still surface"
