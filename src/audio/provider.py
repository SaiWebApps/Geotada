"""TTS provider protocol and implementations.

All providers implement the TTSProvider protocol. Real providers use httpx
for HTTP calls (no SDK dependencies required).

Usage:
    provider = get_provider("openai")   # or "elevenlabs"
    audio_bytes = provider.generate("Hello, welcome to Paris.")

OWNER RULING, 2026-07-31 — NO FAKE PROVIDER IS EVER SERVED
----------------------------------------------------------
``MockTTSProvider`` returns a silent WAV. It exists so the test suite can drive
the whole audio pipeline for $0. It is therefore DEFINED here but deliberately
NOT REGISTERED: ``_PROVIDERS`` holds only implementations that send the text to
a real speech service.

That single fact is what makes the workbench honest. The editorial workbench
builds its provider dropdown from ``GET /audio/providers`` -> ``list_providers()``
(``frontend/review.html``'s ``loadTtsProviders`` wipes the static markup and
repopulates it), so anything in this registry is one click away from a human who
is trying to judge what a TOURIST will hear. A silent WAV offered there is the
exact lie the never-mock-in-the-workbench rule exists to prevent — and hiding it
in the page instead of here would leave ``POST /audio/preview {"provider":
"mock"}`` answering with canned bytes anyway.

The ONLY way a fake becomes resolvable is ``register_provider()``, called
in-process. ``tests/conftest.py`` is its one caller, so the fake is present in a
pytest interpreter and absent from every uvicorn one (the workbench server, the
Playwright test server, and Render). No environment variable, no request body and
no config layer can put it back.
"""

from __future__ import annotations

import os
import re
import wave
from io import BytesIO
from typing import Protocol, runtime_checkable

import httpx

from src.audio._http import TRANSIENT_NETWORK_EXC, post_with_retry
from src.audio.tts_normalize import normalize_for_tts


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


# ── Transient-error retry (shared by the real HTTP providers) ──

_MAX_TTS_RETRIES = 3
_TTS_INITIAL_BACKOFF_SEC = 0.5


def _post_with_retry(
    url: str,
    *,
    headers: dict[str, str],
    json: dict[str, object],
    timeout: float = 60.0,
) -> httpx.Response:
    """POST a TTS request with bounded retry on transient failures.

    Delegates to the shared :func:`post_with_retry`, which retries transient
    network errors AND transient Cloudflare/gateway statuses (incl. the 404
    "Invalid URL" edge artifact) up to ``_MAX_TTS_RETRIES`` attempts. The HTTP
    response is returned unexamined — the caller interprets status codes
    (auth/validation are NOT retried). Raises ``TTSError`` only after every
    attempt raised a network transient: a single blip can't fail a user's audio.
    """
    try:
        return post_with_retry(
            url,
            headers=headers,
            json=json,
            timeout=timeout,
            max_attempts=_MAX_TTS_RETRIES,
            initial_backoff=_TTS_INITIAL_BACKOFF_SEC,
        )
    except TRANSIENT_NETWORK_EXC as exc:
        raise TTSError(
            f"TTS request failed after {_MAX_TTS_RETRIES} attempts: {exc}"
        ) from exc


# ── Long-text chunking (real TTS APIs cap input length) ──

MAX_TTS_CHARS = 4000  # OpenAI tts-1 caps input at ~4096 chars; stay safely under.


def _split_for_tts(text: str, max_chars: int = MAX_TTS_CHARS) -> list[str]:
    """Split text into TTS-sized chunks on sentence boundaries.

    Real TTS APIs cap input length, so a long per-stop narration must be voiced
    in pieces and concatenated. Splits on sentence enders, greedily packing
    sentences up to ``max_chars``; an over-long single sentence is hard-split as
    a last resort. Text already under the cap returns ``[text]`` (single call —
    unchanged behavior). Concatenated MP3 chunks play back-to-back in browsers
    and players.
    """
    text = text.strip()
    if len(text) <= max_chars:
        return [text] if text else []
    chunks: list[str] = []
    current = ""
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if len(sentence) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            for i in range(0, len(sentence), max_chars):
                chunks.append(sentence[i : i + max_chars])
            continue
        if current and len(current) + 1 + len(sentence) > max_chars:
            chunks.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}" if current else sentence
    if current:
        chunks.append(current)
    return chunks


# ── Mock Provider ──


class MockTTSProvider:
    """Returns a short silent WAV for testing without API keys.

    NOT REGISTERED in ``_PROVIDERS`` (see the module docstring). A process that
    wants it must call ``register_provider()`` itself; ``tests/conftest.py``
    does, so the whole pytest suite keeps its $0 audio path while no server
    process can offer or serve it.
    """

    # Ceiling on the synthesized silent-WAV duration, independent of input size.
    # The mock is NOT run through _split_for_tts, so without this the WAV grows
    # linearly with word count (10k words -> ~700 MB) and a few concurrent
    # /audio/preview or /audio/eval requests OOM the API process. A silent test
    # WAV need not be honestly sized, so we clamp to a small, bounded duration.
    _MAX_DURATION_SEC = 30.0

    @property
    def name(self) -> str:
        return "mock"

    def generate(self, text: str, *, voice_id: str | None = None) -> bytes:
        """Generate a silent WAV whose duration approximates the text length.

        Rough heuristic: ~150 words/min speaking rate, clamped to
        ``_MAX_DURATION_SEC`` so the output size is bounded regardless of input.
        """
        word_count = len(text.split())
        duration_sec = min(max(1.0, word_count / 2.5), self._MAX_DURATION_SEC)

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

        audio = bytearray()
        for chunk in _split_for_tts(normalize_for_tts(text)):
            resp = _post_with_retry(
                self.API_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": self.DEFAULT_MODEL,
                    "input": chunk,
                    "voice": voice,
                    "response_format": "mp3",
                },
            )
            if resp.status_code != 200:
                raise TTSError(f"OpenAI TTS failed ({resp.status_code}): {resp.text[:200]}")
            audio += resp.content

        return bytes(audio)


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

        audio = bytearray()
        for chunk in _split_for_tts(normalize_for_tts(text)):
            resp = _post_with_retry(
                url,
                headers={
                    "xi-api-key": api_key,
                    "Content-Type": "application/json",
                    "Accept": "audio/mpeg",
                },
                json={
                    "text": chunk,
                    "model_id": self.DEFAULT_MODEL,
                    "voice_settings": {
                        "stability": 0.5,
                        "similarity_boost": 0.75,
                    },
                },
            )
            if resp.status_code != 200:
                raise TTSError(f"ElevenLabs TTS failed ({resp.status_code}): {resp.text[:200]}")
            audio += resp.content

        return bytes(audio)


# ── Provider registry ──

# Only implementations that actually send the text to a speech service. See the
# module docstring: this registry IS the workbench's dropdown and the set of
# values POST /audio/preview will honour, so a fake in here is a fake in front of
# a human. MockTTSProvider is deliberately absent.
_PROVIDERS: dict[str, type] = {
    "openai": OpenAITTSProvider,
    "elevenlabs": ElevenLabsTTSProvider,
}


def register_provider(name: str, cls: type) -> None:
    """Register a TTS provider class in THIS interpreter only.

    This is the one door through which a non-serving implementation (the silent
    ``MockTTSProvider``) can be reached, and it can only be opened by code that
    runs inside the process — never by an env var, a config profile, a request
    body or a deploy manifest. ``tests/conftest.py`` calls it so the pytest
    suite has a $0 audio path; no server startup path calls it, so no server can
    offer or serve a fake.
    """
    _PROVIDERS[name] = cls


def get_provider(name: str | None = None) -> TTSProvider:
    """Return an instantiated provider by name, else by the TTS_PROVIDER pin.

    FAILS CLOSED. There is deliberately no default provider: an unset
    TTS_PROVIDER raises instead of quietly selecting something. The old default
    was ``"mock"``, which is how the workbench server spent months answering
    every unpinned /audio request with a SILENT WAV that an editor could mistake
    for real narration (owner-found, 2026-07-31). A misconfigured server must
    now say so loudly rather than sound fine and be fake.
    """
    provider_name = name or os.getenv("TTS_PROVIDER")
    available = ", ".join(sorted(_PROVIDERS))
    if not provider_name:
        raise ValueError(
            "No TTS provider selected: pass a name or set TTS_PROVIDER. "
            f"Available: {available}. (There is no default — a silent fallback "
            f"provider is exactly the defect this fail-closed check replaces.)"
        )
    cls = _PROVIDERS.get(provider_name)
    if cls is None:
        msg = f"Unknown TTS provider '{provider_name}'. Available: {available}"
        raise ValueError(msg)
    return cls()


def list_providers() -> list[str]:
    """Return names of all registered providers."""
    return sorted(_PROVIDERS)
