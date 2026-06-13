"""Unit tests for audio TTS providers.

These tests do NOT require API keys or external services — all real providers
are tested for graceful failure, and the mock provider is tested for correctness.
"""

from __future__ import annotations

import wave
from io import BytesIO

import httpx
import pytest

from src.audio.provider import (
    ElevenLabsTTSProvider,
    MockTTSProvider,
    OpenAITTSProvider,
    TTSError,
    TTSProvider,
    get_provider,
    list_providers,
)


class _Resp:
    """Minimal stand-in for an httpx.Response with a 200 + content."""

    status_code = 200
    content = b"audio-bytes"


class TestProviderRegistry:
    def test_list_providers_returns_all(self):
        names = list_providers()
        assert "mock" in names
        assert "openai" in names
        assert "elevenlabs" in names

    def test_get_provider_mock(self):
        p = get_provider("mock")
        assert isinstance(p, MockTTSProvider)
        assert isinstance(p, TTSProvider)

    def test_get_provider_openai(self):
        p = get_provider("openai")
        assert isinstance(p, OpenAITTSProvider)
        assert isinstance(p, TTSProvider)

    def test_get_provider_elevenlabs(self):
        p = get_provider("elevenlabs")
        assert isinstance(p, ElevenLabsTTSProvider)
        assert isinstance(p, TTSProvider)

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown TTS provider"):
            get_provider("nonexistent")

    def test_default_provider_is_mock(self, monkeypatch):
        monkeypatch.delenv("TTS_PROVIDER", raising=False)
        p = get_provider()
        assert p.name == "mock"

    def test_env_var_selects_provider(self, monkeypatch):
        monkeypatch.setenv("TTS_PROVIDER", "openai")
        p = get_provider()
        assert p.name == "openai"


class TestMockProvider:
    def test_name(self):
        assert MockTTSProvider().name == "mock"

    def test_generates_valid_wav(self):
        audio = MockTTSProvider().generate("Hello world")
        with wave.open(BytesIO(audio), "rb") as wf:
            assert wf.getnchannels() == 2  # stereo
            assert wf.getframerate() == 44100
            assert wf.getsampwidth() == 2  # 16-bit

    def test_duration_scales_with_text(self):
        short = MockTTSProvider().generate("Hi")
        long = MockTTSProvider().generate("This is a much longer piece of text " * 10)
        assert len(long) > len(short)

    def test_minimum_duration(self):
        audio = MockTTSProvider().generate("Hi")
        with wave.open(BytesIO(audio), "rb") as wf:
            duration = wf.getnframes() / wf.getframerate()
            assert duration >= 1.0

    def test_voice_id_accepted(self):
        # voice_id is ignored but shouldn't error
        audio = MockTTSProvider().generate("Hello", voice_id="test-voice")
        assert len(audio) > 0


class TestOpenAIProvider:
    def test_name(self):
        assert OpenAITTSProvider().name == "openai"

    def test_missing_api_key_raises(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(TTSError, match="OPENAI_API_KEY not set"):
            OpenAITTSProvider().generate("test")


class TestElevenLabsProvider:
    def test_name(self):
        assert ElevenLabsTTSProvider().name == "elevenlabs"

    def test_missing_api_key_raises(self, monkeypatch):
        monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
        with pytest.raises(TTSError, match="ELEVENLABS_API_KEY not set"):
            ElevenLabsTTSProvider().generate("test")

    def test_missing_voice_id_raises(self, monkeypatch):
        monkeypatch.setenv("ELEVENLABS_API_KEY", "fake-key")
        monkeypatch.delenv("ELEVENLABS_VOICE_ID", raising=False)
        with pytest.raises(TTSError, match="ELEVENLABS_VOICE_ID not set"):
            ElevenLabsTTSProvider().generate("test")


class TestTTSRetry:
    """Transient timeouts are retried with backoff (Fix A — offline, mocked)."""

    def test_openai_retries_then_succeeds(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
        monkeypatch.setattr("src.audio.provider.time.sleep", lambda *_: None)
        calls = {"n": 0}

        def fake_post(self, *args, **kwargs):
            calls["n"] += 1
            if calls["n"] < 3:  # fail twice, then succeed
                raise httpx.TimeoutException("transient")
            return _Resp()

        monkeypatch.setattr(httpx.Client, "post", fake_post)
        out = OpenAITTSProvider().generate("hello")
        assert out == b"audio-bytes"
        assert calls["n"] == 3

    def test_openai_raises_ttserror_after_exhausting_retries(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
        monkeypatch.setattr("src.audio.provider.time.sleep", lambda *_: None)

        def always_timeout(self, *args, **kwargs):
            raise httpx.TimeoutException("transient")

        monkeypatch.setattr(httpx.Client, "post", always_timeout)
        with pytest.raises(TTSError, match="after 3 attempts"):
            OpenAITTSProvider().generate("hello")

    def test_elevenlabs_retries_then_succeeds(self, monkeypatch):
        monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
        monkeypatch.setenv("ELEVENLABS_VOICE_ID", "v")
        monkeypatch.setattr("src.audio.provider.time.sleep", lambda *_: None)
        calls = {"n": 0}

        def fake_post(self, *args, **kwargs):
            calls["n"] += 1
            if calls["n"] < 2:  # one ConnectError, then succeed
                raise httpx.ConnectError("transient")
            return _Resp()

        monkeypatch.setattr(httpx.Client, "post", fake_post)
        out = ElevenLabsTTSProvider().generate("hello")
        assert out == b"audio-bytes"
        assert calls["n"] == 2
