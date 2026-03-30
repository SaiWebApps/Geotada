"""Audio pipeline — orchestrates TTS generation, storage, and Neo4j updates.

Pipeline: NarrativeBeat.script_body → TTS Provider → Storage → update audio_url

Usage:
    from src.audio.pipeline import generate_beat_audio
    result = generate_beat_audio(session, beat_id)
"""

from __future__ import annotations

import hashlib
import struct
import time
import wave
from dataclasses import dataclass, field
from io import BytesIO
from typing import TYPE_CHECKING, Callable

from src.api.crud.nodes import get_node, update_node
from src.audio.provider import TTSError, get_provider
from src.audio.storage import StorageError, get_storage

if TYPE_CHECKING:
    from neo4j import Session


class PipelineError(Exception):
    """Raised when the audio generation pipeline fails."""


@dataclass
class GenerationResult:
    """Result of generating audio for a single NarrativeBeat."""

    beat_id: str
    provider: str
    storage: str
    audio_url: str
    size_bytes: int
    duration_sec: float
    script_body: str


def _get_duration(audio_bytes: bytes) -> float:
    """Extract duration in seconds from audio bytes (WAV or MP3).

    WAV: parsed exactly via stdlib wave module.
    MP3: decoded from the first valid frame header (bitrate + total size).
    Returns 0.0 if the format cannot be determined.
    """
    # Try WAV first (starts with RIFF header)
    if audio_bytes[:4] == b"RIFF":
        try:
            with wave.open(BytesIO(audio_bytes), "rb") as wf:
                return wf.getnframes() / wf.getframerate()
        except Exception:
            return 0.0

    # Try MP3 — find first valid frame sync (0xFF 0xE0+ bits)
    return _mp3_duration(audio_bytes)


# ── MP3 bitrate tables (MPEG1 Layer III) ──
_BITRATES_V1_L3 = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0]
_SAMPLE_RATES_V1 = [44100, 48000, 32000, 0]


def _mp3_duration(data: bytes) -> float:
    """Estimate MP3 duration from the first valid frame header and file size.

    Scans for the frame sync word (11 set bits), extracts bitrate from the
    header, then computes duration = (file_size * 8) / bitrate_bps.
    Only handles MPEG1 Layer III (the common case for TTS output).
    """
    for i in range(min(len(data) - 4, 8192)):
        if data[i] != 0xFF:
            continue
        hdr = struct.unpack(">I", data[i : i + 4])[0]

        # Check sync: 11 bits set
        if (hdr >> 21) != 0x7FF:
            continue

        version = (hdr >> 19) & 0x3  # 0x3 = MPEG1
        layer = (hdr >> 17) & 0x3  # 0x1 = Layer III
        bitrate_idx = (hdr >> 12) & 0xF
        sr_idx = (hdr >> 10) & 0x3

        if version != 3 or layer != 1:  # Only MPEG1 Layer III
            continue
        if bitrate_idx == 0 or bitrate_idx == 15 or sr_idx == 3:
            continue

        bitrate_kbps = _BITRATES_V1_L3[bitrate_idx]
        if bitrate_kbps == 0:
            continue

        # Duration = total bits / bitrate
        return (len(data) * 8) / (bitrate_kbps * 1000)

    return 0.0


def _build_storage_key(beat_id: str, poi_name: str | None = None) -> str:
    """Build a deterministic storage key for a beat's audio file.

    Format: beats/{poi_slug}/{beat_id}.mp3
    """
    slug = "unknown"
    if poi_name:
        slug = poi_name.lower().replace(" ", "_").replace("'", "")
    return f"beats/{slug}/{beat_id}.mp3"


def _script_hash(text: str) -> str:
    """SHA-256 hash of script_body, used to detect stale audio."""
    return hashlib.sha256(text.encode()).hexdigest()


@dataclass
class AudioStatus:
    """Status of a beat's audio, including staleness detection."""

    beat_id: str
    has_audio: bool
    audio_url: str | None
    duration_sec: float | None
    is_stale: bool


def check_audio_status(session: Session, beat_id: str) -> AudioStatus:
    """Check audio status for a beat, including whether the audio is stale.

    Audio is stale when the script_body has changed since audio was generated
    (i.e. the stored hash no longer matches the current script_body).
    """
    beat = get_node(session, "NarrativeBeat", beat_id)
    if beat is None:
        raise PipelineError(f"NarrativeBeat '{beat_id}' not found")

    props = beat["properties"]
    audio_url = props.get("audio_url", "")
    has_audio = bool(audio_url) and "placeholder" not in audio_url
    duration_sec = props.get("duration_sec")

    # Check staleness
    is_stale = False
    if has_audio:
        stored_hash = props.get("audio_script_hash", "")
        current_body = props.get("script_body", "")
        if stored_hash and current_body:
            is_stale = stored_hash != _script_hash(current_body)
        elif not stored_hash and current_body:
            # Audio exists but no hash stored (generated before this feature)
            is_stale = True

    return AudioStatus(
        beat_id=beat_id,
        has_audio=has_audio,
        audio_url=audio_url if has_audio else None,
        duration_sec=duration_sec,
        is_stale=is_stale,
    )


def generate_beat_audio(
    session: Session,
    beat_id: str,
    *,
    provider_name: str | None = None,
    storage_name: str | None = None,
    voice_id: str | None = None,
    force: bool = False,
) -> GenerationResult:
    """Generate audio for a single NarrativeBeat and store it.

    1. Fetch the beat from Neo4j
    2. Skip if audio_url already exists (unless force=True)
    3. Generate audio via TTS provider
    4. Upload to storage
    5. Update the beat's audio_url in Neo4j
    """
    # Step 1: Fetch the beat
    beat = get_node(session, "NarrativeBeat", beat_id)
    if beat is None:
        raise PipelineError(f"NarrativeBeat '{beat_id}' not found")

    props = beat["properties"]
    script_body = props.get("script_body")
    if not script_body:
        raise PipelineError(f"Beat '{beat_id}' has no script_body")

    # Step 2: Check if audio already exists (skip stale audio — regenerate it)
    existing_url = props.get("audio_url", "")
    stored_hash = props.get("audio_script_hash", "")
    current_hash = _script_hash(script_body)
    is_stale = stored_hash and stored_hash != current_hash

    if existing_url and "placeholder" not in existing_url and not force and not is_stale:
        raise PipelineError(
            f"Beat '{beat_id}' already has audio at '{existing_url}'. "
            "Use force=True to regenerate."
        )

    # Fetch POI name for the storage key
    poi_result = session.run(
        "MATCH (p:POI)-[:HAS_BEAT]->(b:NarrativeBeat {id: $beat_id}) "
        "RETURN p.name AS poi_name",
        beat_id=beat_id,
    ).single()
    poi_name = poi_result["poi_name"] if poi_result else None

    # Step 3: Generate audio
    provider = get_provider(provider_name)
    try:
        audio_bytes = provider.generate(script_body, voice_id=voice_id)
    except TTSError as e:
        raise PipelineError(f"TTS failed for beat '{beat_id}': {e}")

    # Step 4: Upload to storage
    storage = get_storage(storage_name)
    key = _build_storage_key(beat_id, poi_name)
    try:
        audio_url = storage.upload(audio_bytes, key)
    except StorageError as e:
        raise PipelineError(f"Storage failed for beat '{beat_id}': {e}")

    # Step 5: Update Neo4j
    duration = round(_get_duration(audio_bytes), 2)
    update_node(session, "NarrativeBeat", beat_id, {
        "audio_url": audio_url,
        "duration_sec": duration,
        "audio_script_hash": current_hash,
    })

    return GenerationResult(
        beat_id=beat_id,
        provider=provider.name,
        storage=storage.name,
        audio_url=audio_url,
        size_bytes=len(audio_bytes),
        duration_sec=duration,
        script_body=script_body,
    )


@dataclass
class BatchSummary:
    """Summary statistics for a batch generation run."""

    results: list[GenerationResult | PipelineError]
    total_found: int
    skipped: int = 0
    succeeded: int = 0
    failed: int = 0
    total_bytes: int = 0
    elapsed_sec: float = 0.0


def generate_batch(
    session: Session,
    *,
    provider_name: str | None = None,
    storage_name: str | None = None,
    voice_id: str | None = None,
    force: bool = False,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> BatchSummary:
    """Generate audio for all NarrativeBeats that need it.

    Args:
        progress_callback: Optional callback(current, total, beat_id) called
            after each beat is processed.

    Returns a BatchSummary with results and stats.
    """
    start = time.monotonic()

    # Find all beats
    result = session.run(
        "MATCH (b:NarrativeBeat) "
        "RETURN b.id AS id, b.audio_url AS audio_url, b.audio_script_hash AS hash, "
        "       b.script_body AS script_body"
    )

    all_beats = list(result)
    total_found = len(all_beats)

    beat_ids = []
    for record in all_beats:
        url = record["audio_url"] or ""
        if force or not url or "placeholder" in url:
            beat_ids.append(record["id"])
        elif record["script_body"] and record["hash"]:
            # Also include stale beats
            if record["hash"] != _script_hash(record["script_body"]):
                beat_ids.append(record["id"])

    skipped = total_found - len(beat_ids)

    results: list[GenerationResult | PipelineError] = []
    succeeded = 0
    failed = 0
    total_bytes = 0

    for i, beat_id in enumerate(beat_ids):
        try:
            r = generate_beat_audio(
                session,
                beat_id,
                provider_name=provider_name,
                storage_name=storage_name,
                voice_id=voice_id,
                force=force,
            )
            results.append(r)
            succeeded += 1
            total_bytes += r.size_bytes
        except PipelineError as e:
            results.append(e)
            failed += 1

        if progress_callback:
            progress_callback(i + 1, len(beat_ids), beat_id)

    elapsed = round(time.monotonic() - start, 2)

    return BatchSummary(
        results=results,
        total_found=total_found,
        skipped=skipped,
        succeeded=succeeded,
        failed=failed,
        total_bytes=total_bytes,
        elapsed_sec=elapsed,
    )
