"""Audio generation routes — TTS preview, provider listing, and comparison."""

from __future__ import annotations

import hashlib
import os
import tempfile
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from neo4j import Session

from src.api.dependencies import get_session
from src.api.models.audio import (
    AudioPreviewRequest,
    AudioStatusResponse,
    BatchGenerateRequest,
    BatchGenerateResponse,
    BatchResultItem,
    CompareRequest,
    CompareResponse,
    CompareResultItem,
    EvalRequest,
    EvalResponse,
    GenerateRequest,
    GenerateResponse,
    ProviderInfo,
    ProviderListResponse,
    StopAudioResultItem,
    StopAudioStatusResponse,
    TripAudioGenerateResponse,
    TripAudioResultItem,
    TripStopAudioGenerateResponse,
)
from src.audio.eval import EvalError as AudioEvalError
from src.audio.eval import evaluate
from src.audio.pipeline import (
    PipelineError,
    check_audio_status,
    generate_batch,
    generate_beat_audio,
    generate_stop_audio,
)
from src.audio.provider import TTSError, get_provider, list_providers
from src.audio.storage import LocalStorageProvider, get_storage

router = APIRouter(tags=["audio"])

# Directory for storing comparison audio files (survives across requests)
_COMPARE_DIR = Path(tempfile.gettempdir()) / "ondoway-audio-compare"
_COMPARE_DIR.mkdir(exist_ok=True)

# Maximum age (in seconds) for comparison files before cleanup
_COMPARE_MAX_AGE_SEC = 3600  # 1 hour


def _cleanup_old_comparisons() -> None:
    """Remove comparison files older than _COMPARE_MAX_AGE_SEC."""
    try:
        now = time.time()
        for entry in _COMPARE_DIR.iterdir():
            if entry.is_file():
                try:
                    age = now - os.path.getmtime(entry)
                    if age > _COMPARE_MAX_AGE_SEC:
                        entry.unlink()
                except OSError:
                    pass  # File may have been removed concurrently
    except OSError:
        pass  # Directory may not exist yet


@router.get("/audio/providers", response_model=ProviderListResponse)
def get_providers():
    """List all registered TTS providers and their availability."""
    providers = []
    for name in list_providers():
        try:
            get_provider(name)
            providers.append(ProviderInfo(name=name, available=True))
        except Exception:
            providers.append(ProviderInfo(name=name, available=False))
    return ProviderListResponse(providers=providers)


@router.post("/audio/preview")
def preview_audio(body: AudioPreviewRequest):
    """Generate a TTS audio preview from raw text.

    Returns audio bytes directly (audio/wav for mock, audio/mpeg for real providers).
    """
    try:
        provider = get_provider(body.provider)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None

    try:
        audio_bytes = provider.generate(body.text, voice_id=body.voice_id)
    except TTSError as e:
        raise HTTPException(502, f"TTS generation failed ({provider.name}): {e}") from None

    # Mock returns WAV, real providers return MP3
    media_type = "audio/wav" if provider.name == "mock" else "audio/mpeg"
    ext = "wav" if provider.name == "mock" else "mp3"

    return Response(
        content=audio_bytes,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="preview-{provider.name}.{ext}"'},
    )


@router.post("/audio/compare", response_model=CompareResponse)
def compare_providers(body: CompareRequest):
    """Generate the same text with multiple providers for A/B comparison.

    Returns metadata and download paths for each provider's output.
    Use GET /audio/compare/download/{filename} to fetch individual files.
    """
    # Clean up stale comparison files (older than 1 hour)
    _cleanup_old_comparisons()

    # Create a hash for this comparison batch
    text_hash = hashlib.sha256(body.text.encode()).hexdigest()[:12]
    results: list[CompareResultItem] = []

    for provider_name in body.providers:
        try:
            provider = get_provider(provider_name)
        except ValueError as e:
            results.append(
                CompareResultItem(
                    provider=provider_name,
                    success=False,
                    error=str(e),
                )
            )
            continue

        try:
            voice_id = body.voice_ids.get(provider_name)
            audio_bytes = provider.generate(body.text, voice_id=voice_id)
        except TTSError as e:
            results.append(
                CompareResultItem(
                    provider=provider_name,
                    success=False,
                    error=str(e),
                )
            )
            continue

        ext = "wav" if provider_name == "mock" else "mp3"
        filename = f"{text_hash}-{provider_name}.{ext}"
        filepath = _COMPARE_DIR / filename
        filepath.write_bytes(audio_bytes)

        # Estimate duration from word count (~150 wpm)
        word_count = len(body.text.split())
        duration_est = word_count / 2.5

        results.append(
            CompareResultItem(
                provider=provider_name,
                success=True,
                size_bytes=len(audio_bytes),
                duration_estimate_sec=round(duration_est, 1),
                download_path=f"/api/v1/audio/compare/download/{filename}",
            )
        )

    return CompareResponse(text=body.text, results=results)


@router.get("/audio/compare/download/{filename}")
def download_comparison(filename: str):
    """Download a previously generated comparison audio file."""
    # Sanitize filename to prevent path traversal
    safe_name = Path(filename).name
    filepath = _COMPARE_DIR / safe_name
    if not filepath.exists():
        raise HTTPException(404, f"File '{safe_name}' not found. Run /audio/compare first.")

    media_type = "audio/wav" if safe_name.endswith(".wav") else "audio/mpeg"
    return FileResponse(filepath, media_type=media_type, filename=safe_name)


# A real TTS occasionally returns a 200 with degraded/near-silent audio (Whisper
# transcribes it as "you", WER ~1.0) -- transient output degradation, NOT a real
# quality regression. Regenerate a bounded number of times and keep the best
# (lowest-WER) result so a one-off bad generation can't fail an otherwise-good
# voice. WER this high never comes from a legitimate script, so this cannot mask
# a real quality issue (a genuinely bad voice fails every attempt and still
# surfaces). The deterministic mock provider's silent WAV is "degraded" by
# design, so it is evaluated once (retrying it would loop pointlessly).
_EVAL_DEGRADED_WER: float = 0.6  # far above the FAIL cut (0.25) -- only garbage output
_EVAL_MAX_ATTEMPTS: int = 3


@router.post("/audio/eval", response_model=EvalResponse)
def eval_audio(body: EvalRequest):
    """Generate TTS audio, then transcribe it back and compare against the source.

    This is the end-to-end quality check: text → TTS → audio → Whisper STT → diff.
    Requires OPENAI_API_KEY for Whisper transcription.

    Verdict thresholds:
    - PASS: WER < 0.10 (less than 10% word errors)
    - REVIEW: WER 0.10-0.25
    - FAIL: WER > 0.25
    """
    try:
        provider = get_provider(body.provider)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None

    # Steps 1-2: Generate audio then transcribe + evaluate, retrying past a
    # transient degraded generation (see _EVAL_DEGRADED_WER above).
    ext = "wav" if provider.name == "mock" else "mp3"
    max_attempts = 1 if provider.name == "mock" else _EVAL_MAX_ATTEMPTS
    result = None
    for _ in range(max_attempts):
        try:
            audio_bytes = provider.generate(body.text, voice_id=body.voice_id)
        except TTSError as e:
            raise HTTPException(502, f"TTS generation failed ({provider.name}): {e}") from None
        try:
            attempt = evaluate(body.text, audio_bytes, filename=f"eval.{ext}")
        except AudioEvalError as e:
            raise HTTPException(502, f"Transcription failed: {e}") from None
        if result is None or attempt.word_error_rate < result.word_error_rate:
            result = attempt
        if result.word_error_rate < _EVAL_DEGRADED_WER:
            break  # a plausible (non-degraded) generation -- stop retrying

    # Step 3: Assign verdict
    if result.word_error_rate < 0.10:
        verdict = "PASS"
    elif result.word_error_rate < 0.25:
        verdict = "REVIEW"
    else:
        verdict = "FAIL"

    return EvalResponse(
        provider=provider.name,
        original_text=result.original_text,
        transcribed_text=result.transcribed_text,
        similarity_score=result.similarity_score,
        word_error_rate=result.word_error_rate,
        missing_words=result.missing_words,
        extra_words=result.extra_words,
        verdict=verdict,
    )


@router.get("/audio/files/{key:path}")
def serve_audio_file(key: str):
    """Serve a locally stored audio file.

    Only works when AUDIO_STORAGE=local (default for development).
    In production, audio is served directly from S3/CDN.
    """
    storage = get_storage()
    if not isinstance(storage, LocalStorageProvider):
        raise HTTPException(404, "Local file serving only available with local storage")

    filepath = storage.base_path / key
    # Prevent path traversal
    try:
        filepath.resolve().relative_to(storage.base_path.resolve())
    except ValueError:
        raise HTTPException(400, "Invalid file path") from None

    if not filepath.exists():
        raise HTTPException(404, f"Audio file '{key}' not found")

    media_type = "audio/wav" if key.endswith(".wav") else "audio/mpeg"
    return FileResponse(filepath, media_type=media_type, filename=Path(key).name)


# ── Pipeline endpoints (require Neo4j) ──


@router.get("/audio/status/{beat_id}", response_model=AudioStatusResponse)
def get_audio_status(beat_id: str, session: Session = Depends(get_session)):
    """Check audio status for a beat, including staleness detection.

    Returns whether audio exists, its URL, duration, and whether the
    script_body has changed since the audio was last generated (is_stale).
    """
    try:
        status = check_audio_status(session, beat_id)
    except PipelineError as e:
        raise HTTPException(404, str(e)) from None

    return AudioStatusResponse(
        beat_id=status.beat_id,
        has_audio=status.has_audio,
        audio_url=status.audio_url,
        duration_sec=status.duration_sec,
        is_stale=status.is_stale,
    )


@router.post("/audio/generate/{beat_id}", response_model=GenerateResponse)
def generate_audio(
    beat_id: str,
    body: GenerateRequest,
    session: Session = Depends(get_session),
):
    """Generate audio for a single NarrativeBeat.

    Fetches the beat's script_body from Neo4j, runs TTS, uploads to storage,
    and updates the beat's audio_url.
    """
    try:
        result = generate_beat_audio(
            session,
            beat_id,
            provider_name=body.provider,
            voice_id=body.voice_id,
            force=body.force,
        )
    except PipelineError as e:
        raise HTTPException(400, str(e)) from None

    return GenerateResponse(
        beat_id=result.beat_id,
        provider=result.provider,
        storage=result.storage,
        audio_url=result.audio_url,
        size_bytes=result.size_bytes,
    )


@router.post("/audio/generate-batch", response_model=BatchGenerateResponse)
def generate_audio_batch(
    body: BatchGenerateRequest,
    session: Session = Depends(get_session),
):
    """Generate audio for all NarrativeBeats that need it.

    Processes all beats without audio, with placeholder URLs, or with stale audio.
    Returns summary stats including timing and total bytes generated.
    """
    summary = generate_batch(
        session,
        provider_name=body.provider,
        voice_id=body.voice_id,
        force=body.force,
    )

    items: list[BatchResultItem] = []
    for r in summary.results:
        if isinstance(r, PipelineError):
            items.append(
                BatchResultItem(
                    beat_id="unknown",
                    success=False,
                    error=str(r),
                )
            )
        else:
            items.append(
                BatchResultItem(
                    beat_id=r.beat_id,
                    success=True,
                    audio_url=r.audio_url,
                    size_bytes=r.size_bytes,
                )
            )

    return BatchGenerateResponse(
        total_found=summary.total_found,
        total_processed=summary.succeeded + summary.failed,
        succeeded=summary.succeeded,
        failed=summary.failed,
        skipped=summary.skipped,
        total_bytes=summary.total_bytes,
        elapsed_sec=summary.elapsed_sec,
        results=items,
    )


@router.post("/audio/generate-trip/{trip_id}", response_model=TripAudioGenerateResponse)
def generate_audio_for_trip(
    trip_id: str,
    body: GenerateRequest | None = None,
    session: Session = Depends(get_session),
):
    """Generate audio for each stop's primary beat that doesn't have audio yet.

    Finds each ItineraryItem's primary beat (HAS_STOP -> ItineraryItem ->
    PLAYS_BEAT, filtered to `item.primary_beat_id`), filters to those without
    audio, and runs TTS generation for each. Non-primary PLAYS_BEAT beats are
    deliberately excluded: mobile plays only the primary beat, and M7's COMPOSE
    layer replaces per-beat audio with one composed MP3 per stop
    (specs/2026-06-12-tour-algorithm-decision/ALGORITHM-SPEC.md §2.5).
    """
    # Verify trip exists
    trip_check = session.run(
        "MATCH (t:Trip {id: $tid}) RETURN t.id AS id",
        tid=trip_id,
    ).single()
    if trip_check is None:
        raise HTTPException(404, f"Trip '{trip_id}' not found")

    # Find each item's primary beat without audio. The coalesce fallback
    # mirrors list_trips_for_profile (src/api/crud/trips.py): legacy items
    # that predate M0b's multi-beat persistence have no primary_beat_id
    # property and exactly one PLAYS_BEAT edge. DISTINCT guards against two
    # items sharing a primary beat (generate it once, not once per item).
    query = """
        MATCH (t:Trip {id: $trip_id})-[:HAS_STOP]->(item:ItineraryItem)
        MATCH (item)-[:PLAYS_BEAT]->(beat:NarrativeBeat)
        WITH item, collect(beat) AS beats
        WITH beats, coalesce(item.primary_beat_id, beats[0].id) AS primary_id
        UNWIND [b IN beats WHERE b.id = primary_id] AS beat
        WITH DISTINCT beat
        WHERE beat.audio_url IS NULL OR beat.audio_url = ''
        RETURN beat.id AS beat_id, beat.script_body AS script_body
    """
    records = session.run(query, trip_id=trip_id)
    beats_to_generate = [dict(r) for r in records]

    if not beats_to_generate:
        return TripAudioGenerateResponse(
            trip_id=trip_id,
            generated=0,
            skipped=0,
            failed=0,
            results=[],
        )

    provider_name = body.provider if body else None
    voice_id = body.voice_id if body else None
    force = body.force if body else False

    results: list[TripAudioResultItem] = []
    for beat in beats_to_generate:
        if not beat["script_body"]:
            results.append(
                TripAudioResultItem(
                    beat_id=beat["beat_id"],
                    status="skipped",
                    reason="no script_body",
                )
            )
            continue
        try:
            gen_result = generate_beat_audio(
                session,
                beat["beat_id"],
                provider_name=provider_name,
                voice_id=voice_id,
                force=force,
            )
            results.append(
                TripAudioResultItem(
                    beat_id=beat["beat_id"],
                    status="generated",
                    audio_url=gen_result.audio_url,
                )
            )
        except PipelineError as e:
            results.append(
                TripAudioResultItem(
                    beat_id=beat["beat_id"],
                    status="failed",
                    error=str(e),
                )
            )

    return TripAudioGenerateResponse(
        trip_id=trip_id,
        generated=sum(1 for r in results if r.status == "generated"),
        skipped=sum(1 for r in results if r.status == "skipped"),
        failed=sum(1 for r in results if r.status == "failed"),
        results=results,
    )


@router.post(
    "/audio/generate-trip-stops/{trip_id}",
    response_model=TripStopAudioGenerateResponse,
)
def generate_stop_audio_for_trip(
    trip_id: str,
    body: GenerateRequest | None = None,
    session: Session = Depends(get_session),
):
    """Generate one composed-narration MP3 per stop (Phase 1, Step 1.4a).

    Iterates the trip's ItineraryItems, voices each stop's stitched ``narration``
    (Step 1.2) via ``generate_stop_audio``, and stores the result ON THE ITEM
    (``audio_url``/``audio_duration_sec``), keyed by the item id. This is the
    per-stop replacement for the per-primary-beat ``/audio/generate-trip``;
    mobile switches to it in Step 1.4c and the per-beat path is retired later.
    Items with no narration are skipped; existing audio is skipped unless force.
    """
    trip_check = session.run(
        "MATCH (t:Trip {id: $tid}) RETURN t.id AS id", tid=trip_id
    ).single()
    if trip_check is None:
        raise HTTPException(404, f"Trip '{trip_id}' not found")

    rows = session.run(
        """
        MATCH (t:Trip {id: $trip_id})-[:HAS_STOP]->(item:ItineraryItem)
        OPTIONAL MATCH (item)-[:AT_POI]->(poi:POI)
        RETURN item.id AS stop_id,
               item.narration AS narration,
               item.audio_url AS audio_url,
               poi.name AS poi_name
        ORDER BY item.sort_order
        """,
        trip_id=trip_id,
    )
    stops = [dict(r) for r in rows]

    provider_name = body.provider if body else None
    voice_id = body.voice_id if body else None
    force = body.force if body else False

    results: list[StopAudioResultItem] = []
    for stop in stops:
        stop_id = stop["stop_id"]
        narration = stop["narration"]
        if not narration or not narration.strip():
            results.append(
                StopAudioResultItem(stop_id=stop_id, status="skipped", reason="no narration")
            )
            continue
        if stop["audio_url"] and not force:
            results.append(
                StopAudioResultItem(
                    stop_id=stop_id,
                    status="skipped",
                    reason="already has audio",
                    audio_url=stop["audio_url"],
                )
            )
            continue
        try:
            gen = generate_stop_audio(
                narration,
                stop_key=stop_id,
                poi_name=stop["poi_name"],
                provider_name=provider_name,
                voice_id=voice_id,
            )
        except PipelineError as e:
            results.append(StopAudioResultItem(stop_id=stop_id, status="failed", error=str(e)))
            continue
        session.run(
            "MATCH (item:ItineraryItem {id: $sid}) "
            "SET item.audio_url = $url, item.audio_duration_sec = $dur",
            sid=stop_id,
            url=gen.audio_url,
            dur=gen.duration_sec,
        )
        results.append(
            StopAudioResultItem(stop_id=stop_id, status="generated", audio_url=gen.audio_url)
        )

    return TripStopAudioGenerateResponse(
        trip_id=trip_id,
        generated=sum(1 for r in results if r.status == "generated"),
        skipped=sum(1 for r in results if r.status == "skipped"),
        failed=sum(1 for r in results if r.status == "failed"),
        results=results,
    )


@router.get("/audio/stop-status/{stop_id}", response_model=StopAudioStatusResponse)
def get_stop_audio_status(stop_id: str, session: Session = Depends(get_session)):
    """Per-stop audio status by ItineraryItem id (Phase 1, Step 1.4b).

    Additive to /audio/status/{beat_id}: reads the per-stop audio persisted by
    /audio/generate-trip-stops (Step 1.4a) so mobile can poll/play per stop.
    404 if the stop doesn't exist.
    """
    rec = session.run(
        "MATCH (i:ItineraryItem {id: $sid}) "
        "RETURN i.audio_url AS audio_url, i.audio_duration_sec AS duration_sec",
        sid=stop_id,
    ).single()
    if rec is None:
        raise HTTPException(404, f"Stop '{stop_id}' not found")

    audio_url = rec["audio_url"]
    has_audio = bool(audio_url)
    return StopAudioStatusResponse(
        stop_id=stop_id,
        has_audio=has_audio,
        audio_url=audio_url if has_audio else None,
        duration_sec=rec["duration_sec"] if has_audio else None,
    )
