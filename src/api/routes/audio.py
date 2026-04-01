"""Audio generation routes — TTS preview, provider listing, and comparison."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from neo4j import Session

from src.api.dependencies import get_session
from src.api.models.audio import (
    AudioPreviewRequest,
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
)
from src.audio.eval import EvalError as AudioEvalError
from src.audio.eval import evaluate
from src.audio.pipeline import PipelineError, generate_batch, generate_beat_audio
from src.audio.provider import TTSError, get_provider, list_providers
from src.audio.storage import LocalStorageProvider, get_storage

router = APIRouter(tags=["audio"])

# Directory for storing comparison audio files (survives across requests)
_COMPARE_DIR = Path(tempfile.gettempdir()) / "travlr-audio-compare"
_COMPARE_DIR.mkdir(exist_ok=True)


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
        raise HTTPException(400, str(e))

    try:
        audio_bytes = provider.generate(body.text, voice_id=body.voice_id)
    except TTSError as e:
        raise HTTPException(502, f"TTS generation failed ({provider.name}): {e}")

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
    # Create a hash for this comparison batch
    text_hash = hashlib.sha256(body.text.encode()).hexdigest()[:12]
    results: list[CompareResultItem] = []

    for provider_name in body.providers:
        try:
            provider = get_provider(provider_name)
        except ValueError as e:
            results.append(CompareResultItem(
                provider=provider_name, success=False, error=str(e),
            ))
            continue

        try:
            voice_id = body.voice_ids.get(provider_name)
            audio_bytes = provider.generate(body.text, voice_id=voice_id)
        except TTSError as e:
            results.append(CompareResultItem(
                provider=provider_name, success=False, error=str(e),
            ))
            continue

        ext = "wav" if provider_name == "mock" else "mp3"
        filename = f"{text_hash}-{provider_name}.{ext}"
        filepath = _COMPARE_DIR / filename
        filepath.write_bytes(audio_bytes)

        # Estimate duration from word count (~150 wpm)
        word_count = len(body.text.split())
        duration_est = word_count / 2.5

        results.append(CompareResultItem(
            provider=provider_name,
            success=True,
            size_bytes=len(audio_bytes),
            duration_estimate_sec=round(duration_est, 1),
            download_path=f"/api/v1/audio/compare/download/{filename}",
        ))

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


@router.post("/audio/eval", response_model=EvalResponse)
def eval_audio(body: EvalRequest):
    """Generate TTS audio, then transcribe it back and compare against the source.

    This is the end-to-end quality check: text → TTS → audio → Whisper STT → diff.
    Requires OPENAI_API_KEY for Whisper transcription.

    Verdict thresholds:
    - PASS: WER < 0.10 (less than 10% word errors)
    - REVIEW: WER 0.10–0.25
    - FAIL: WER > 0.25
    """
    try:
        provider = get_provider(body.provider)
    except ValueError as e:
        raise HTTPException(400, str(e))

    # Step 1: Generate audio
    try:
        audio_bytes = provider.generate(body.text, voice_id=body.voice_id)
    except TTSError as e:
        raise HTTPException(502, f"TTS generation failed ({provider.name}): {e}")

    # Step 2: Transcribe + evaluate
    ext = "wav" if provider.name == "mock" else "mp3"
    try:
        result = evaluate(body.text, audio_bytes, filename=f"eval.{ext}")
    except AudioEvalError as e:
        raise HTTPException(502, f"Transcription failed: {e}")

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
        raise HTTPException(400, "Invalid file path")

    if not filepath.exists():
        raise HTTPException(404, f"Audio file '{key}' not found")

    media_type = "audio/wav" if key.endswith(".wav") else "audio/mpeg"
    return FileResponse(filepath, media_type=media_type, filename=Path(key).name)


# ── Pipeline endpoints (require Neo4j) ──


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
        raise HTTPException(400, str(e))

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

    Processes all beats without audio or with placeholder URLs.
    """
    raw_results = generate_batch(
        session,
        provider_name=body.provider,
        voice_id=body.voice_id,
        force=body.force,
    )

    items: list[BatchResultItem] = []
    succeeded = 0
    failed = 0

    for r in raw_results:
        if isinstance(r, PipelineError):
            failed += 1
            items.append(BatchResultItem(
                beat_id="unknown", success=False, error=str(r),
            ))
        else:
            succeeded += 1
            items.append(BatchResultItem(
                beat_id=r.beat_id,
                success=True,
                audio_url=r.audio_url,
                size_bytes=r.size_bytes,
            ))

    return BatchGenerateResponse(
        total_processed=len(raw_results),
        succeeded=succeeded,
        failed=failed,
        results=items,
    )
