"""TTS provider protocol and implementations.

All providers implement the TTSProvider protocol. Real providers use httpx
for HTTP calls (no SDK dependencies required).

Usage:
    provider = get_provider("openai")   # or "elevenlabs", "mock"
    audio_bytes = provider.generate("Hello, welcome to Boston.")
"""

from __future__ import annotations

import os
import wave
from io import BytesIO
from typing import Protocol, runtime_checkable

import httpx


class TTSError(Exception):
    """Raised when a TTS provider fails to generate audio."""


@runtime_checkable
class TTSProvider(Protocol):
    """Interface that all TTS providers must implement."""

    @property
    def name(self) -> str:
        """Short identifier for this provider (e.g. 'openai', 'elevenlabs')."""
        ...

    def generate(self, text: str, *, voice_id: str | None = None) -> bytes:
        """Convert text to audio. Returns raw audio bytes (MP3 or WAV)."""
        ...


# ── Mock Provider ──


class MockTTSProvider:
    """Returns a short silent WAV for testing without API keys."""

    @property
    def name(self) -> str:
        return "mock"

    def generate(self, text: str, *, voice_id: str | None = None) -> bytes:
        """Generate a silent WAV whose duration approximates the text length.

        Rough heuristic: ~150 words/min speaking rate.
        """
        word_count = len(text.split())
        duration_sec = max(1.0, word_count / 2.5)

        sample_rate = 44100
        channels = 2  # stereo per NORTHSTAR spec
        sample_width = 2  # 16-bit
        n_frames = int(sample_rate * duration_sec)

        buf = BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(sample_width)
            wf.setframerate(sample_rate)
            wf.writeframes(b"\x00" * n_frames * channels * sample_width)

        return buf.getvalue()


# ── OpenAI TTS Provider ──


class OpenAITTSProvider:
    """OpenAI TTS API — good quality, cheap, no SDK required.

    Requires OPENAI_API_KEY env var.
    Default voice: "alloy". Options: alloy, echo, fable, onyx, nova, shimmer.
    """

    API_URL = "https://api.openai.com/v1/audio/speech"
    DEFAULT_VOICE = "nova"
    DEFAULT_MODEL = "tts-1-hd"

    @property
    def name(self) -> str:
        return "openai"

    def generate(self, text: str, *, voice_id: str | None = None) -> bytes:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise TTSError("OPENAI_API_KEY not set")

        voice = voice_id or os.getenv("OPENAI_VOICE", self.DEFAULT_VOICE)

        resp = httpx.post(
            self.API_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": self.DEFAULT_MODEL,
                "input": text,
                "voice": voice,
                "response_format": "mp3",
            },
            timeout=60.0,
        )

        if resp.status_code != 200:
            raise TTSError(f"OpenAI TTS failed ({resp.status_code}): {resp.text[:200]}")

        return resp.content


# ── ElevenLabs TTS Provider ──


class ElevenLabsTTSProvider:
    """ElevenLabs TTS API — best quality for storytelling, no SDK required.

    Requires ELEVENLABS_API_KEY env var.
    Requires ELEVENLABS_VOICE_ID env var (or pass voice_id to generate).
    """

    API_BASE = "https://api.elevenlabs.io/v1"
    DEFAULT_MODEL = "eleven_multilingual_v2"

    @property
    def name(self) -> str:
        return "elevenlabs"

    def generate(self, text: str, *, voice_id: str | None = None) -> bytes:
        api_key = os.getenv("ELEVENLABS_API_KEY")
        if not api_key:
            raise TTSError("ELEVENLABS_API_KEY not set")

        vid = voice_id or os.getenv("ELEVENLABS_VOICE_ID")
        if not vid:
            raise TTSError("ELEVENLABS_VOICE_ID not set and no voice_id provided")

        url = f"{self.API_BASE}/text-to-speech/{vid}"

        resp = httpx.post(
            url,
            headers={
                "xi-api-key": api_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            json={
                "text": text,
                "model_id": self.DEFAULT_MODEL,
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.75,
                },
            },
            timeout=60.0,
        )

        if resp.status_code != 200:
            raise TTSError(f"ElevenLabs TTS failed ({resp.status_code}): {resp.text[:200]}")

        return resp.content


# ── Provider registry ──

_PROVIDERS: dict[str, type] = {
    "mock": MockTTSProvider,
    "openai": OpenAITTSProvider,
    "elevenlabs": ElevenLabsTTSProvider,
}


def register_provider(name: str, cls: type) -> None:
    """Register a new TTS provider class."""
    _PROVIDERS[name] = cls


def get_provider(name: str | None = None) -> TTSProvider:
    """Return an instantiated provider by name.

    Falls back to TTS_PROVIDER env var, then to 'mock'.
    """
    provider_name = name or os.getenv("TTS_PROVIDER", "mock")
    cls = _PROVIDERS.get(provider_name)
    if cls is None:
        available = ", ".join(sorted(_PROVIDERS))
        msg = f"Unknown TTS provider '{provider_name}'. Available: {available}"
        raise ValueError(msg)
    return cls()


def list_providers() -> list[str]:
    """Return names of all registered providers."""
    return sorted(_PROVIDERS)
