"""Audio pipeline — orchestrates TTS generation, storage, and Neo4j updates.

Pipeline: NarrativeBeat.script_body → TTS Provider → Storage → update audio_url

Usage:
    from src.audio.pipeline import generate_beat_audio
    result = generate_beat_audio(session, beat_id)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

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
    script_body: str


def _build_storage_key(beat_id: str, poi_name: str | None = None) -> str:
    """Build a deterministic storage key for a beat's audio file.

    Format: beats/{poi_slug}/{beat_id}.mp3
    """
    slug = "unknown"
    if poi_name:
        slug = poi_name.lower().replace(" ", "_").replace("'", "")
    return f"beats/{slug}/{beat_id}.mp3"


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

    # Step 2: Check if audio already exists
    existing_url = props.get("audio_url", "")
    if existing_url and "placeholder" not in existing_url and not force:
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
    update_node(session, "NarrativeBeat", beat_id, {"audio_url": audio_url})

    return GenerationResult(
        beat_id=beat_id,
        provider=provider.name,
        storage=storage.name,
        audio_url=audio_url,
        size_bytes=len(audio_bytes),
        script_body=script_body,
    )


def generate_batch(
    session: Session,
    *,
    provider_name: str | None = None,
    storage_name: str | None = None,
    voice_id: str | None = None,
    force: bool = False,
) -> list[GenerationResult | PipelineError]:
    """Generate audio for all NarrativeBeats that need it.

    Returns a list of results (GenerationResult for success, PipelineError for failure).
    """
    # Find all beats
    result = session.run(
        "MATCH (b:NarrativeBeat) "
        "RETURN b.id AS id, b.audio_url AS audio_url"
    )

    beat_ids = []
    for record in result:
        url = record["audio_url"] or ""
        # Include beats with no audio, placeholder URLs, or if force=True
        if force or not url or "placeholder" in url:
            beat_ids.append(record["id"])

    results: list[GenerationResult | PipelineError] = []
    for beat_id in beat_ids:
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
        except PipelineError as e:
            results.append(e)

    return results
