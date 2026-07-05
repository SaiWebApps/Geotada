"""Unit tests for audio TTS providers.

These tests do NOT require API keys or external services — all real providers
are tested for graceful failure, and the mock provider is tested for correctness.
"""

from __future__ import annotations

import wave
from io import BytesIO

import httpx
import pytest

from src.api.models.audio import AudioPreviewRequest
from src.audio.provider import (
    MAX_TTS_CHARS,
    ElevenLabsTTSProvider,
    MockTTSProvider,
    OpenAITTSProvider,
    TTSError,
    TTSProvider,
    _split_for_tts,
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
        monkeypatch.setattr("src.audio._http.time.sleep", lambda *_: None)
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
        monkeypatch.setattr("src.audio._http.time.sleep", lambda *_: None)

        def always_timeout(self, *args, **kwargs):
            raise httpx.TimeoutException("transient")

        monkeypatch.setattr(httpx.Client, "post", always_timeout)
        with pytest.raises(TTSError, match="after 3 attempts"):
            OpenAITTSProvider().generate("hello")

    def test_elevenlabs_retries_then_succeeds(self, monkeypatch):
        monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
        monkeypatch.setenv("ELEVENLABS_VOICE_ID", "v")
        monkeypatch.setattr("src.audio._http.time.sleep", lambda *_: None)
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


class TestSplitForTts:
    """Long narration is chunked under the TTS input cap (Fix: the 422 on long stops)."""

    def test_short_text_is_one_chunk(self):
        assert _split_for_tts("Hello there.") == ["Hello there."]

    def test_empty_text_is_no_chunks(self):
        assert _split_for_tts("   ") == []

    def test_long_text_splits_on_sentences_under_cap(self):
        text = "A sentence about Paris and its long history. " * 200  # ~9000 chars
        chunks = _split_for_tts(text, max_chars=1000)
        assert len(chunks) > 1
        assert all(len(c) <= 1000 for c in chunks)
        # no sentences lost across the split
        assert sum(c.count("Paris") for c in chunks) == 200

    def test_overlong_single_sentence_is_hard_split(self):
        text = "x" * 2500  # no sentence boundary to split on
        chunks = _split_for_tts(text, max_chars=1000)
        assert len(chunks) == 3
        assert all(len(c) <= 1000 for c in chunks)
        assert "".join(chunks) == text


class TestTTSChunking:
    def test_openai_chunks_long_text_and_concatenates(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
        inputs: list[str] = []

        def fake_post(self, *args, **kwargs):
            inputs.append(kwargs["json"]["input"])

            class _R:
                status_code = 200
                content = f"<{len(inputs)}>".encode()

            return _R()

        monkeypatch.setattr(httpx.Client, "post", fake_post)
        long_text = "A sentence about Paris and its remarkable history. " * 120  # ~6000 chars

        out = OpenAITTSProvider().generate(long_text)

        assert len(inputs) >= 2, "long text must be chunked into multiple TTS calls"
        assert all(len(t) <= MAX_TTS_CHARS for t in inputs), "each chunk under the cap"
        assert out == b"".join(f"<{i + 1}>".encode() for i in range(len(inputs)))


def test_audio_preview_request_accepts_long_narration():
    # A long stop (6000 chars) was rejected at the old 5000 cap (the 422 bug).
    AudioPreviewRequest(text="x" * 6000, provider="mock")  # must not raise


class TestTTSNormalizationWiring:
    """The real providers must normalize pronunciation BEFORE calling the API
    (backlog #23): the bytes the listener hears come from the normalized text.
    """

    def _capture_input(self, monkeypatch) -> list[str]:
        captured: list[str] = []

        def fake_post(self, *args, **kwargs):
            payload = kwargs["json"]
            captured.append(payload.get("input") or payload.get("text"))

            class _R:
                status_code = 200
                content = b"\xff\xfbaudio"

            return _R()

        monkeypatch.setattr(httpx.Client, "post", fake_post)
        return captured

    def test_openai_normalizes_regnal_numerals(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
        sent = self._capture_input(monkeypatch)

        OpenAITTSProvider().generate("Louis XIV met J.-B. Colbert under Napoleon III.")

        assert sent == ["Louis the fourteenth met J. B. Colbert under Napoleon the third."]

    def test_elevenlabs_normalizes_regnal_numerals(self, monkeypatch):
        monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
        monkeypatch.setenv("ELEVENLABS_VOICE_ID", "v")
        sent = self._capture_input(monkeypatch)

        ElevenLabsTTSProvider().generate("Charles V and Henri IV.")

        assert sent == ["Charles the fifth and Henri the fourth."]

    def test_non_regnal_text_reaches_api_unchanged(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
        sent = self._capture_input(monkeypatch)

        text = "World War II shaped Chapter IV, whom I admire."
        OpenAITTSProvider().generate(text)

        assert sent == [text]
