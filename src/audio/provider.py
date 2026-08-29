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
NOT REGISTERED: ``_PROVIDERS`` holds only implementations that GENUINELY
SYNTHESIZE SPEECH — the two vendors, and the local Kokoro model, which never
leaves the machine and is real narration all the same.

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
from pathlib import Path
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
    Default voice: "nova". 13 voices are available on the default model.

    WHY NOT ``tts-1-hd`` (measured 2026-08-28, and this is a BUG FIX)
    ----------------------------------------------------------------
    The owner reported intermittent 500s — "The server had an error while
    processing your request. Sorry about that!" — and it looked like an OpenAI
    outage. It was not. The trigger is the SCRIPT, not the server, and it is
    reproducible on demand: against a live key, in one minute, ``tts-1-hd``
    answered 500 on three of four attempts at this repo's own Café de Flore
    Occupation beat (``src/seed/narratives.py``) and 500 on each of that beat's
    sentences alone, while the Eiffel Tower beat voiced fine on the same key and
    network. Ordinary WWII history for a Paris walk — the Occupation, the Nazis,
    the resistance — and the model reports a SERVER error rather than saying it
    will not read it, which is exactly why it read as an outage.

    ``_post_with_retry`` can never fix that: it is not a blip, it is the same
    wall three times. ``gpt-4o-mini-tts`` voiced the identical paragraph 3/3.

    So the default is the 2025 model, which is also the cheaper one ($12 vs $30
    per million characters) and carries an ``instructions`` field for directing
    the narrator's tone — deliberately NOT used yet: how this narrator should
    sound is a writing decision, not a default to slip in here.

    ``MAX_TTS_CHARS`` (4000) stays well under this model's 2000-token input cap.
    """

    API_URL = "https://api.openai.com/v1/audio/speech"
    DEFAULT_VOICE = "nova"
    DEFAULT_MODEL = "gpt-4o-mini-tts"

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


# ── Kokoro, on our own machine ──


class KokoroTTSProvider:
    """Kokoro-82M speech, synthesized locally — the tier that needs no vendor.

    THE LAST RESORT, and the only one that survives "every cloud is
    unreachable". OpenAI and ElevenLabs are different companies but the same
    bet: that we can reach someone else's machine. This one is our machine.

    Runtime is ``sherpa-onnx``, not the ``kokoro-onnx`` package, and that choice
    is load-bearing. ``kokoro-onnx`` phonemizes through ``espeakng-loader``,
    whose bundled library is BROKEN on macOS arm64: proved by calling
    ``espeak_Initialize`` directly with an explicit, existing data directory —
    it ignores the argument, reports the build machine's path, and hard-exits
    the process. Rescuing it needs a system-wide espeak-ng. ``sherpa-onnx``
    compiles espeak into its own core and ships the data INSIDE the model
    bundle, so there is no system package to install here or in the image.

    Weights are never downloaded at generate time. A tier that exists for "the
    internet is failing" cannot begin by reaching the internet, so the bundle
    directory is named by ``KOKORO_MODEL_DIR`` and must already be on disk;
    ``scripts/check_audio_setup.py`` says so plainly when it is not.

    Measured on the owner's laptop (Apple silicon, 2 CPU threads): 9.4s of
    narration in 3.6s — 2.6x faster than real time — 53 voices, 24 kHz.

    Output is MP3 because every other provider returns MP3 and the whole
    pipeline assumes it (``_build_stop_storage_key`` names ``.mp3``,
    ``serve_audio_file`` types by suffix). Kokoro emits float32 PCM, so the
    samples are concatenated FIRST and encoded ONCE — one clean stream, not
    glued-together MP3s.
    """

    #: Directory holding model.onnx, voices.bin, tokens.txt and espeak-ng-data.
    MODEL_DIR_ENV = "KOKORO_MODEL_DIR"
    #: Which of the 53 built-in voices narrates. An integer, unlike the other
    #: providers' names — sherpa-onnx selects a Kokoro voice by speaker id.
    SPEAKER_ENV = "KOKORO_SPEAKER"
    DEFAULT_SPEAKER = 0
    #: Files the bundle must contain for the provider to be usable at all.
    REQUIRED_FILES = ("model.onnx", "voices.bin", "tokens.txt", "espeak-ng-data")

    MP3_BITRATE_KBPS = 64  # mono narration; ample for speech at 24 kHz

    @property
    def name(self) -> str:
        return "kokoro"

    @classmethod
    def model_dir(cls) -> str:
        """The configured bundle directory, or '' when unset."""
        return os.getenv(cls.MODEL_DIR_ENV, "").strip()

    @classmethod
    def missing_pieces(cls) -> list[str]:
        """What stops this provider speaking right now — empty when it can.

        Used by ``/audio/providers`` so the workbench reports a REAL probe
        rather than the presence of an env var: a directory that exists but
        lacks the weights cannot voice anything, and saying otherwise is the
        kind of quiet lie the fail-closed rules here exist to prevent.
        """
        directory = cls.model_dir()
        if not directory:
            return [f"{cls.MODEL_DIR_ENV} is not set"]
        base = Path(directory)
        if not base.is_dir():
            return [f"{cls.MODEL_DIR_ENV}={directory} is not a directory"]
        return [f"{directory}/{piece} is missing" for piece in cls.REQUIRED_FILES
                if not (base / piece).exists()]

    def _synthesize(self, text: str, speaker: int):
        """Build the offline engine and return sherpa-onnx's generated audio."""
        try:
            import sherpa_onnx
        except ImportError as exc:  # pragma: no cover - exercised by the doctor
            # "Not installed" and "installed but its native library will not
            # load" are different faults with different remedies, and saying
            # `make sync-local-tts` to someone who just ran it sends them in a
            # circle. A missing libonnxruntime means sherpa-onnx-core is absent
            # — which happened here, because sherpa-onnx declares that
            # dependency only in its wheel metadata and the lock dropped it.
            detail = str(exc)
            if "onnxruntime" in detail or "Library not loaded" in detail:
                raise TTSError(
                    "kokoro is installed but its native library is missing "
                    f"(sherpa-onnx-core): {detail[:160]}"
                ) from exc
            raise TTSError(
                "kokoro needs the local-tts extra: run `make sync-local-tts`"
            ) from exc

        directory = self.model_dir()
        config = sherpa_onnx.OfflineTtsConfig(
            model=sherpa_onnx.OfflineTtsModelConfig(
                kokoro=sherpa_onnx.OfflineTtsKokoroModelConfig(
                    model=f"{directory}/model.onnx",
                    voices=f"{directory}/voices.bin",
                    tokens=f"{directory}/tokens.txt",
                    data_dir=f"{directory}/espeak-ng-data",
                    dict_dir=f"{directory}/dict",
                    lexicon=f"{directory}/lexicon-us-en.txt,{directory}/lexicon-zh.txt",
                ),
                provider="cpu",
                num_threads=2,
            ),
            max_num_sentences=1,
        )
        return sherpa_onnx.OfflineTts(config).generate(text, sid=speaker, speed=1.0)

    def generate(self, text: str, *, voice_id: str | None = None) -> bytes:
        missing = self.missing_pieces()
        if missing:
            raise TTSError(
                "Kokoro cannot speak — " + "; ".join(missing) + ". "
                f"Point {self.MODEL_DIR_ENV} at an extracted sherpa-onnx Kokoro "
                "bundle (`make fetch-kokoro`)."
            )

        raw_speaker = voice_id or os.getenv(self.SPEAKER_ENV) or self.DEFAULT_SPEAKER
        try:
            speaker = int(raw_speaker)
        except (TypeError, ValueError) as exc:
            raise TTSError(
                f"Kokoro voices are speaker NUMBERS, not names; got {raw_speaker!r}. "
                f"Set {self.SPEAKER_ENV} to an integer."
            ) from exc

        import numpy as np

        sample_rate = 0
        pieces: list[object] = []
        for chunk in _split_for_tts(normalize_for_tts(text)):
            out = self._synthesize(chunk, speaker)
            sample_rate = int(out.sample_rate)
            pieces.append(np.asarray(out.samples, dtype=np.float32))
        if not pieces:
            raise TTSError("Kokoro was handed no speakable text")

        samples = np.concatenate(pieces) if len(pieces) > 1 else pieces[0]
        return _pcm_to_mp3(samples, sample_rate, self.MP3_BITRATE_KBPS)


def _pcm_to_mp3(samples, sample_rate: int, bitrate_kbps: int) -> bytes:
    """Encode mono float32 samples in [-1, 1] to MP3 bytes.

    LAME through ``lameenc`` rather than ffmpeg or libsndfile: it is a wheel, so
    there is no system binary to install and no libsndfile version to depend on,
    and the bitrate is set explicitly instead of inherited from a default.
    """
    import numpy as np

    try:
        import lameenc
    except ImportError as exc:  # pragma: no cover - exercised by the doctor
        raise TTSError(
            "local TTS needs an MP3 encoder: run `make sync-local-tts`"
        ) from exc

    pcm16 = np.clip(np.asarray(samples, dtype=np.float32) * 32767.0, -32768, 32767)
    encoder = lameenc.Encoder()
    encoder.set_bit_rate(bitrate_kbps)
    encoder.set_in_sample_rate(sample_rate)
    encoder.set_channels(1)
    encoder.set_quality(2)
    return bytes(encoder.encode(pcm16.astype(np.int16).tobytes())) + bytes(encoder.flush())


# ── Failover across speech services ──


class FailoverTTSProvider:
    """Speaks through the FIRST provider in ``providers`` that answers.

    A vendor that will not speak is ours to survive, whatever the reason. The
    2026-08-28 case that prompted this was first read as an OpenAI outage and was
    not one: ``tts-1-hd`` answered 500 on a PARTICULAR script three times out of
    four while another script voiced fine on the same key in the same minute (see
    ``OpenAITTSProvider``). That instance is fixed by the model default; the class
    is not. A vendor can refuse a legitimate script, and ``_post_with_retry``'s
    three attempts over ~1.5 seconds cannot help when all three hit one wall —
    only a DIFFERENT voice can.

    Whole-text, never mid-text. A fallback re-voices the ENTIRE narration from
    the start, because a stop that switches narrator mid-paragraph is worse than
    one voiced by the understudy throughout. Only ``TTSError`` moves us down the
    chain — a bad request or an empty script fails everywhere and must surface.

    ``voice_id`` is deliberately passed to the PRIMARY ALONE. A voice name
    belongs to one vendor ("nova" is OpenAI's; ElevenLabs wants its own id), so
    forwarding it would ask the understudy for a voice it has never heard of.
    Each fallback uses its own configured default instead.

    ``name`` reports WHO ACTUALLY SPOKE once someone has, so the caller records
    the real narrator rather than the one it hoped for. Instances are built per
    call by :func:`get_provider_with_fallback`, so that state is never shared.
    """

    def __init__(self, providers: list[TTSProvider]) -> None:
        if not providers:
            raise ValueError("A failover chain needs at least one provider")
        self._providers = providers
        self._spoke: str | None = None

    @property
    def name(self) -> str:
        """The provider that spoke, or the primary's name before anyone has."""
        return self._spoke or self._providers[0].name

    def generate(self, text: str, *, voice_id: str | None = None) -> bytes:
        failures: list[str] = []
        for index, provider in enumerate(self._providers):
            try:
                audio = provider.generate(text, voice_id=voice_id if index == 0 else None)
            except TTSError as exc:
                failures.append(f"{provider.name}: {exc}")
                continue
            self._spoke = provider.name
            return audio
        raise TTSError("every TTS provider in the chain failed — " + "; ".join(failures))


# ── Provider registry ──

# Only implementations that GENUINELY SYNTHESIZE SPEECH. See the module
# docstring: this registry IS the workbench's dropdown and the set of values POST
# /audio/preview will honour, so a fake in here is a fake in front of a human.
# MockTTSProvider is deliberately absent.
#
# "kokoro" belongs here even though it never leaves the machine — the rule being
# protected is that nothing silently serves a human a non-voice, and a local
# model produces real narration. The wording used to say "sends the text to a
# real speech service", which was the same rule stated in terms of the two
# vendors that happened to exist at the time.
_PROVIDERS: dict[str, type] = {
    "openai": OpenAITTSProvider,
    "elevenlabs": ElevenLabsTTSProvider,
    "kokoro": KokoroTTSProvider,
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


_FALLBACK_ENV = "TTS_FALLBACK"


def _configured_fallback_names() -> list[str]:
    """The ordered understudy names from ``TTS_FALLBACK`` (comma-separated)."""
    return [part.strip() for part in os.getenv(_FALLBACK_ENV, "").split(",") if part.strip()]


def get_provider_with_fallback(name: str | None = None) -> TTSProvider:
    """THE door for a tourist's audio: the pinned voice, plus its understudies.

    Two rules, both deliberate:

    * **A named provider is honoured exactly.** ``get_provider_with_fallback("openai")``
      returns OpenAI and nothing else. The operator tools that name one — the
      workbench's A/B compare, the Whisper eval, an explicit per-request override —
      are asking "how does THIS voice sound", and answering with a different one
      would make the comparison a lie.
    * **An unnamed provider gets the chain.** With no name the pin (``TTS_PROVIDER``)
      leads, followed by every name in ``TTS_FALLBACK``. Mobile and the scheduled
      voicing pass never name a provider, so the tourist's audio is what survives a
      vendor outage.

    With ``TTS_FALLBACK`` unset this returns exactly what :func:`get_provider`
    returns — the single pinned provider, unchanged. A typo'd understudy raises
    ``ValueError`` HERE, while the primary is still healthy, rather than lying
    dormant until the day the chain is finally needed; that is the same
    fail-closed rule :func:`get_provider` documents. The chain is deduped
    (preserving order) and drops a fallback naming the primary, so a copy-paste
    cannot quietly double the outage window.
    """
    if name:
        return get_provider(name)

    primary = get_provider()
    understudies = [n for n in dict.fromkeys(_configured_fallback_names()) if n != primary.name]
    if not understudies:
        return primary
    return FailoverTTSProvider([primary, *(get_provider(n) for n in understudies)])


def list_providers() -> list[str]:
    """Return names of all registered providers."""
    return sorted(_PROVIDERS)
