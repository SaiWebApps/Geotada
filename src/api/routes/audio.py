"""Audio generation routes — TTS preview, provider listing, and comparison."""

from __future__ import annotations

import hashlib
import os
import tempfile
import time
from collections import OrderedDict, deque
from pathlib import Path
from threading import Lock

from fastapi import APIRouter, Depends, HTTPException, Request
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
    KeepExploringAudioResponse,
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

# Reuse the ALREADY-HARDENED client-IP resolver from the feedback route rather
# than duplicating its X-Forwarded-For spoofing analysis (see feedback._client_ip).
from src.api.routes.feedback import _client_ip  # isort: skip

router = APIRouter(tags=["audio"])

# ── Admin gate for the spend/mutate audio surface ──────────────────────────
#
# The audio router is mounted UNCONDITIONALLY (mobile + the public tour-preview
# page need the playback/preview routes), but several of its routes are an
# unauthenticated *spend* and *write* surface:
#
#   POST /audio/generate-batch  -> paid TTS over EVERY NarrativeBeat in the
#                                  connected graph + overwrites every audio_url
#   POST /audio/generate/{id}   -> paid TTS + graph write
#   POST /audio/compare         -> up to 5 paid TTS calls + writes files to disk
#   GET  /audio/compare/download-> serves those files
#   POST /audio/eval            -> up to 3 paid TTS + 9 paid Whisper calls
#
# None of these has a product caller (mobile uses generate-trip*/keep-exploring;
# the web preview uses /audio/preview) — they are operator/workbench tools. Gate
# them behind the SAME fail-closed flag that already protects the workbench CRUD
# routers in src/api/app.py, so the public Render deployment (which pins
# WORKBENCH_API_ENABLED="false") never exposes them.
#
# The check runs per-REQUEST rather than at mount time because this module is
# imported once but ``create_app()`` may be called many times (tests) with a
# different env; a request-time gate can never be stale. A disabled route
# answers 404 so it is indistinguishable from an unmounted one.
_ADMIN_GATE_ENV = "WORKBENCH_API_ENABLED"


def _audio_admin_enabled_value(value: str | None) -> bool:
    """Fail-closed parse of the admin gate (mirrors app._workbench_api_enabled).

    ONLY an explicit truthy value opens the surface; unset, empty, or a typo
    ("flase", "disbaled") keeps it CLOSED. Split out from the env lookup so a
    manifest test can check what render.yaml pins with the SAME parser the
    runtime uses. Defined locally rather than imported from src.api.app to
    avoid a circular import (app imports this module).
    """
    return (value or "").strip().lower() in ("true", "1", "yes", "on")


def _audio_admin_enabled() -> bool:
    """Whether the audio spend/mutate surface is explicitly enabled."""
    return _audio_admin_enabled_value(os.getenv(_ADMIN_GATE_ENV))


def require_audio_admin() -> None:
    """Dependency: 404 unless the audio admin surface is explicitly enabled."""
    if not _audio_admin_enabled():
        raise HTTPException(404, "Not Found")


# ── Abuse guard for the PUBLIC paid-TTS routes ────────────────────────────
#
# /audio/preview must stay anonymous (frontend/tour-preview.html calls it with
# no credentials), but every call against a real provider spends the owner's
# OpenAI credit. Bound it the same way the feedback route bounds its Anthropic
# spend: a per-IP fixed window PLUS a global fixed window (per-IP alone is
# defeated by trivial IP rotation, and the global cap is what actually bounds
# the bill). The free mock provider is never limited.
_AUDIO_RATE_LIMIT_MAX = int(os.getenv("AUDIO_RATE_LIMIT_MAX", "20"))
_AUDIO_RATE_LIMIT_WINDOW_S = int(os.getenv("AUDIO_RATE_LIMIT_WINDOW_S", "60"))
_AUDIO_GLOBAL_RATE_LIMIT_MAX = int(os.getenv("AUDIO_GLOBAL_RATE_LIMIT_MAX", "120"))
_audio_rate_state: dict[str, deque[float]] = {}
_audio_global_hits: deque[float] = deque()
_audio_rate_lock = Lock()

# Cap on the text a single PUBLIC preview request may voice. The provider chunks
# at MAX_TTS_CHARS (4000) internally, so the old 20000 model cap meant ONE
# anonymous request fanned out into five billed calls by design. 20000 was
# chosen for the internal keep-exploring path, not this public one.
_PREVIEW_MAX_CHARS = int(os.getenv("AUDIO_PREVIEW_MAX_CHARS", "6000"))

# Bounded in-memory cache of preview audio keyed by (provider, voice, text) so a
# replayed identical payload is never re-billed. Mirrors the narration_hash
# cache used by keep-exploring below.
_PREVIEW_CACHE_MAX_ENTRIES = int(os.getenv("AUDIO_PREVIEW_CACHE_ENTRIES", "16"))
_preview_cache: OrderedDict[str, bytes] = OrderedDict()
_preview_cache_lock = Lock()

# Directory for storing comparison audio files (survives across requests)
_COMPARE_DIR = Path(tempfile.gettempdir()) / "ondoway-audio-compare"
_COMPARE_DIR.mkdir(exist_ok=True)

# Maximum age (in seconds) for comparison files before cleanup
_COMPARE_MAX_AGE_SEC = 3600  # 1 hour
# Hard bounds on the comparison cache. Age-only cleanup let a caller fill the
# container's ephemeral disk within the retention window, breaking every other
# write the process needs (including audio storage).
_COMPARE_MAX_TOTAL_BYTES = int(os.getenv("AUDIO_COMPARE_MAX_TOTAL_BYTES", str(200 * 1024 * 1024)))
_COMPARE_MAX_FILES = int(os.getenv("AUDIO_COMPARE_MAX_FILES", "100"))

# Local audio URLs produced by LocalStorageProvider.upload().
_LOCAL_AUDIO_URL_PREFIX = "/api/v1/audio/files/"


def _audio_rate_limit(request: Request, provider_name: str) -> None:
    """Per-IP + global fixed-window guard for paid TTS. 429 when exceeded.

    Only applies to real (billed) providers — the deterministic mock costs
    nothing, so limiting it would only make the test/dev path flaky.
    """
    if provider_name == "mock":
        return
    client_ip = _client_ip(request)
    now = time.monotonic()
    cutoff = now - _AUDIO_RATE_LIMIT_WINDOW_S
    with _audio_rate_lock:
        if _AUDIO_GLOBAL_RATE_LIMIT_MAX > 0:
            while _audio_global_hits and _audio_global_hits[0] <= cutoff:
                _audio_global_hits.popleft()
            if len(_audio_global_hits) >= _AUDIO_GLOBAL_RATE_LIMIT_MAX:
                retry_after = max(1, int(_audio_global_hits[0] + _AUDIO_RATE_LIMIT_WINDOW_S - now))
                raise HTTPException(
                    status_code=429,
                    detail="Audio generation is temporarily rate limited, please retry later",
                    headers={"Retry-After": str(retry_after)},
                )

        if _AUDIO_RATE_LIMIT_MAX > 0:
            hits = _audio_rate_state.setdefault(client_ip, deque())
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= _AUDIO_RATE_LIMIT_MAX:
                retry_after = max(1, int(hits[0] + _AUDIO_RATE_LIMIT_WINDOW_S - now))
                raise HTTPException(
                    status_code=429,
                    detail="Too many audio requests, please retry later",
                    headers={"Retry-After": str(retry_after)},
                )
            hits.append(now)

        if _AUDIO_GLOBAL_RATE_LIMIT_MAX > 0:
            _audio_global_hits.append(now)


def _preview_cache_get(key: str) -> bytes | None:
    with _preview_cache_lock:
        hit = _preview_cache.get(key)
        if hit is not None:
            _preview_cache.move_to_end(key)
        return hit


def _preview_cache_put(key: str, data: bytes) -> None:
    if _PREVIEW_CACHE_MAX_ENTRIES <= 0:
        return
    with _preview_cache_lock:
        _preview_cache[key] = data
        _preview_cache.move_to_end(key)
        while len(_preview_cache) > _PREVIEW_CACHE_MAX_ENTRIES:
            _preview_cache.popitem(last=False)


def _artifact_missing(url: str | None) -> bool:
    """Whether a stored audio URL points at an artifact that no longer exists.

    Prod keeps the durable pointer in Neo4j but (with AUDIO_STORAGE=local) the
    bytes live on the container's ephemeral disk, so a redeploy leaves rows whose
    audio_url 404s forever — and every regeneration guard treats "has a url" as
    "has audio", so nothing self-heals. Treat a missing artifact as no-audio.

    Conservative by construction: returns False for anything we cannot verify
    (remote storage, unparseable URL, probe error), so this can never cause a
    spurious regeneration.
    """
    if not url or not url.startswith(_LOCAL_AUDIO_URL_PREFIX):
        return False
    key = url[len(_LOCAL_AUDIO_URL_PREFIX) :]
    if not key:
        return False
    try:
        storage = get_storage()
        if not isinstance(storage, LocalStorageProvider):
            return False
        return not storage.exists(key)
    except Exception:
        return False

# Max chars of narration handed to TTS for the on-demand keep-exploring deep
# dive. Mirrors AudioPreviewRequest's cap so a huge extra_narration can't fan
# out into unbounded TTS chunk requests (Defect 17).
_KEEP_EXPLORING_MAX_CHARS = 20000


def _cap_narration(text: str, max_chars: int = _KEEP_EXPLORING_MAX_CHARS) -> str:
    """Cap narration to ``max_chars``, preferring a sentence boundary.

    Text at or under the cap is returned unchanged. Over the cap, truncate to
    the last sentence-ender (``.``/``!``/``?``) within the window so the voiced
    deep dive still ends cleanly; if none exists, hard-truncate at the cap.
    """
    if len(text) <= max_chars:
        return text
    window = text[:max_chars]
    cut = max(window.rfind("."), window.rfind("!"), window.rfind("?"))
    if cut > 0:
        return window[: cut + 1]
    return window


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


def _enforce_compare_cache_bounds() -> None:
    """Evict oldest comparison files until BOTH the byte and count caps hold.

    Age-based cleanup alone bounds nothing within the retention window: a caller
    could write unbounded bytes for a full hour and exhaust the container's
    ephemeral disk. Run this AFTER every write so the cache is bounded at all
    times regardless of request rate.
    """
    try:
        entries = []
        for entry in _COMPARE_DIR.iterdir():
            if not entry.is_file():
                continue
            try:
                stat = entry.stat()
            except OSError:
                continue
            entries.append((stat.st_mtime, stat.st_size, entry))
    except OSError:
        return

    entries.sort(key=lambda e: e[0])  # oldest first
    total_bytes = sum(e[1] for e in entries)
    count = len(entries)
    for _mtime, size, entry in entries:
        if total_bytes <= _COMPARE_MAX_TOTAL_BYTES and count <= _COMPARE_MAX_FILES:
            break
        try:
            entry.unlink()
        except OSError:
            continue
        total_bytes -= size
        count -= 1


def _provider_available(name: str) -> bool:
    """Report whether a provider is actually usable, not merely instantiable.

    The real providers (openai/elevenlabs) have no ``__init__`` and defer their
    API-key checks to ``generate()``, so instantiation never raises even when no
    credentials are configured. Probe the required env vars per provider so a
    client can distinguish a usable provider from one that will 502 on first
    generate. Unknown providers fall back to instantiation success.
    """
    try:
        get_provider(name)
    except Exception:
        return False
    if name == "mock":
        return True
    if name == "openai":
        return bool(os.getenv("OPENAI_API_KEY"))
    if name == "elevenlabs":
        return bool(os.getenv("ELEVENLABS_API_KEY")) and bool(os.getenv("ELEVENLABS_VOICE_ID"))
    return True


@router.get("/audio/providers", response_model=ProviderListResponse)
def get_providers():
    """List all registered TTS providers and their availability."""
    providers = [
        ProviderInfo(name=name, available=_provider_available(name)) for name in list_providers()
    ]
    return ProviderListResponse(providers=providers)


@router.post("/audio/preview")
def preview_audio(body: AudioPreviewRequest, request: Request):
    """Generate a TTS audio preview from raw text.

    Returns audio bytes directly (audio/wav for mock, audio/mpeg for real providers).

    This route is deliberately anonymous — the public tour-preview page calls it
    with no credentials — so the spend it can cause is bounded three ways: a
    per-IP + global rate limit, a text cap well under the old 20000-char model
    limit, and a content-hash cache so a replayed payload is never re-billed.
    """
    try:
        provider = get_provider(body.provider)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None

    _audio_rate_limit(request, provider.name)

    # Bound the per-request fan-out: the provider chunks at 4000 chars, so an
    # uncapped 20000-char body becomes five billed calls.
    text = _cap_narration(body.text, _PREVIEW_MAX_CHARS)

    cache_key = hashlib.sha256(
        f"{provider.name}\x00{body.voice_id or ''}\x00{text}".encode()
    ).hexdigest()
    audio_bytes = _preview_cache_get(cache_key)
    if audio_bytes is None:
        try:
            audio_bytes = provider.generate(text, voice_id=body.voice_id)
        except TTSError as e:
            raise HTTPException(502, f"TTS generation failed ({provider.name}): {e}") from None
        _preview_cache_put(cache_key, audio_bytes)

    # Mock returns WAV, real providers return MP3
    media_type = "audio/wav" if provider.name == "mock" else "audio/mpeg"
    ext = "wav" if provider.name == "mock" else "mp3"

    return Response(
        content=audio_bytes,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="preview-{provider.name}.{ext}"'},
    )


@router.post(
    "/audio/compare",
    response_model=CompareResponse,
    dependencies=[Depends(require_audio_admin)],
)
def compare_providers(body: CompareRequest, request: Request):
    """Generate the same text with multiple providers for A/B comparison.

    Returns metadata and download paths for each provider's output.
    Use GET /audio/compare/download/{filename} to fetch individual files.

    Operator/workbench tool: gated by require_audio_admin (404 on the public
    deployment), rate-limited, and bounded on disk.
    """
    # Clean up stale comparison files (older than 1 hour)
    _cleanup_old_comparisons()

    # Create a hash for this comparison batch
    text_hash = hashlib.sha256(body.text.encode()).hexdigest()[:12]
    results: list[CompareResultItem] = []

    # The model caps the list at 5 but does NOT require uniqueness, so
    # ["openai"] * 5 multiplied the bill 5x for one text. Dedupe, preserving
    # the caller's order.
    for provider_name in dict.fromkeys(body.providers):
        _audio_rate_limit(request, provider_name)
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
        _enforce_compare_cache_bounds()

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


@router.get(
    "/audio/compare/download/{filename}",
    dependencies=[Depends(require_audio_admin)],
)
def download_comparison(filename: str):
    """Download a previously generated comparison audio file."""
    # Sanitize filename to prevent path traversal. Path(...).name does NOT strip
    # a bare ".." or "." (both are their own `name`), so the old exists() check
    # passed for a DIRECTORY and FileResponse then raised RuntimeError -> HTTP
    # 500 with the server's temp path in the trace. is_file() rejects both, and
    # the containment check is defense in depth.
    safe_name = Path(filename).name
    filepath = (_COMPARE_DIR / safe_name).resolve()
    if not filepath.is_file() or filepath.parent != _COMPARE_DIR.resolve():
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


@router.post(
    "/audio/eval",
    response_model=EvalResponse,
    dependencies=[Depends(require_audio_admin)],
)
def eval_audio(body: EvalRequest, request: Request):
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

    # One eval request costs up to 3 paid TTS syntheses AND 3 paid Whisper
    # transcriptions, so it is limited even though it is admin-gated.
    _audio_rate_limit(request, provider.name)

    # Steps 1-2: Generate audio then transcribe + evaluate, retrying past a
    # transient degraded generation (see _EVAL_DEGRADED_WER above).
    ext = "wav" if provider.name == "mock" else "mp3"
    max_attempts = 1 if provider.name == "mock" else _EVAL_MAX_ATTEMPTS
    result = None
    for _ in range(max_attempts):
        # A transient failure on a LATER attempt must not discard a good result
        # already captured on an earlier one: only surface a 502 while we still
        # have no successful attempt (result is None). Otherwise stop retrying
        # and fall through to verdict assignment using the best result so far.
        try:
            audio_bytes = provider.generate(body.text, voice_id=body.voice_id)
        except TTSError as e:
            if result is not None:
                break
            raise HTTPException(502, f"TTS generation failed ({provider.name}): {e}") from None
        try:
            attempt = evaluate(body.text, audio_bytes, filename=f"eval.{ext}")
        except AudioEvalError as e:
            if result is not None:
                break
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

    # is_file(), not exists(): an empty key resolves to the storage ROOT and any
    # directory under it also "exists", so exists() let a directory through to
    # FileResponse, which raised RuntimeError -> HTTP 500 leaking the absolute
    # server-side storage path. is_file() routes both cases into this 404.
    if not filepath.is_file():
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


@router.post(
    "/audio/generate/{beat_id}",
    response_model=GenerateResponse,
    dependencies=[Depends(require_audio_admin)],
)
def generate_audio(
    beat_id: str,
    body: GenerateRequest,
    session: Session = Depends(get_session),
):
    """Generate audio for a single NarrativeBeat.

    Fetches the beat's script_body from Neo4j, runs TTS, uploads to storage,
    and updates the beat's audio_url.

    Operator/workbench tool (mobile drives audio through /audio/generate-trip*),
    so it is admin-gated: paid TTS + a graph write must never be anonymous on
    the public deployment.
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


@router.post(
    "/audio/generate-batch",
    response_model=BatchGenerateResponse,
    dependencies=[Depends(require_audio_admin)],
)
def generate_audio_batch(
    body: BatchGenerateRequest,
    session: Session = Depends(get_session),
):
    """Generate audio for all NarrativeBeats that need it.

    Processes all beats without audio, with placeholder URLs, or with stale audio.
    Returns summary stats including timing and total bytes generated.

    THE highest-blast-radius route in this module: generate_batch matches EVERY
    NarrativeBeat in the connected graph (Paris alone is ~1539) and, with
    force=true, re-voices and overwrites all of them through a paid provider.
    It is an operator tool with no product caller, so it is admin-gated and must
    never be mounted on the public deployment.
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
    # property and exactly one PLAYS_BEAT edge.
    #
    # The list-index projection (`[...][0]`) replaces an UNWIND: when
    # primary_beat_id names a beat with no PLAYS_BEAT edge, UNWIND over the
    # resulting EMPTY list deleted the row outright, so the stop was neither
    # generated NOR reported — the caller saw a fully successful run while that
    # stop shipped silently with no audio. Indexing yields a NULL beat instead,
    # keeping the row alive so it can be classified (and reported) in Python.
    query = """
        MATCH (t:Trip {id: $trip_id})-[:HAS_STOP]->(item:ItineraryItem)
        MATCH (item)-[:PLAYS_BEAT]->(beat:NarrativeBeat)
        WITH item, collect(beat) AS beats
        WITH item, beats, coalesce(item.primary_beat_id, beats[0].id) AS primary_id
        WITH item, primary_id, [b IN beats WHERE b.id = primary_id][0] AS beat
        WHERE beat IS NULL OR beat.audio_url IS NULL OR beat.audio_url = ''
        RETURN item.id AS stop_id, primary_id AS primary_id,
               beat.id AS beat_id, beat.script_body AS script_body
    """
    records = session.run(query, trip_id=trip_id)
    rows = [dict(r) for r in records]

    # The old query used DISTINCT to guard against two items sharing a primary
    # beat (generate it once, not once per item). Rows are now per-ITEM, so
    # dedupe on beat_id here instead. Orphan rows (beat_id is null) are reported
    # rather than generated.
    beats_to_generate: list[dict] = []
    orphans: list[dict] = []
    seen_beat_ids: set[str] = set()
    for row in rows:
        if row["beat_id"] is None:
            orphans.append(row)
            continue
        if row["beat_id"] in seen_beat_ids:
            continue
        seen_beat_ids.add(row["beat_id"])
        beats_to_generate.append(row)

    if not beats_to_generate and not orphans:
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
    for orphan in orphans:
        results.append(
            TripAudioResultItem(
                beat_id=orphan["primary_id"] or orphan["stop_id"],
                status="failed",
                error=(
                    f"primary beat {orphan['primary_id']!r} has no PLAYS_BEAT edge "
                    f"from stop {orphan['stop_id']!r}"
                ),
            )
        )
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
        # "Has a url" is not "has audio": with AUDIO_STORAGE=local the bytes sit
        # on the container's ephemeral disk while the url persists in Neo4j, so
        # after a redeploy every stop skips here forever and the tour plays
        # silence. Treat a verifiably-missing artifact as no-audio so a plain
        # (non-force) regeneration self-heals.
        if stop["audio_url"] and not force and not _artifact_missing(stop["audio_url"]):
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


@router.post(
    "/audio/stops/{stop_id}/keep-exploring",
    response_model=KeepExploringAudioResponse,
)
def keep_exploring_stop_audio(
    stop_id: str,
    request: Request,
    body: GenerateRequest | None = None,
    session: Session = Depends(get_session),
):
    """KE3: voice a stop's "keep exploring here" extra narration on demand.

    Reads the ItineraryItem's persisted ``extra_narration`` (the deterministic
    stitch of the stop's overflow corpus beats, composed at /compose) and voices
    it via the SAME TTS path the tour audio uses (``generate_stop_audio``). This
    is an ON-DEMAND deep dive served OFF the tour's time budget, so nothing is
    auto-advanced and no itinerary time is accounted (that is a mobile concern).

    - 404 if the stop doesn't exist.
    - 409 if the stop has no extra_narration (nothing more to explore here).
    - On TTS failure, returns 200 with ``status='failed'`` — mirroring
      /audio/generate-trip-stops, this never raises a 500 for a flaky provider.

    The audio is NOT persisted on the item's ``audio_url`` (that field holds the
    scheduled per-stop tour audio); the fresh artifact url is returned for the
    client to play directly.
    """
    rec = session.run(
        "MATCH (i:ItineraryItem {id: $sid}) "
        "OPTIONAL MATCH (i)-[:AT_POI]->(poi:POI) "
        "RETURN i.extra_narration AS extra_narration, poi.name AS poi_name, "
        "       i.keep_exploring_audio_url AS ke_url, "
        "       i.keep_exploring_audio_duration_sec AS ke_dur, "
        "       i.keep_exploring_audio_hash AS ke_hash",
        sid=stop_id,
    ).single()
    if rec is None:
        raise HTTPException(404, f"Stop '{stop_id}' not found")

    narration = rec["extra_narration"]
    if not narration or not narration.strip():
        raise HTTPException(409, f"Stop '{stop_id}' has no keep-exploring extras")

    # Defect 17: cap the input before TTS so a huge extra_narration can't fan out
    # into unbounded TTS chunk requests. Mirror AudioPreviewRequest's 20000-char
    # cap; truncate on a sentence boundary so the deep dive still voices cleanly.
    narration = _cap_narration(narration)

    provider_name = body.provider if body else None
    voice_id = body.voice_id if body else None
    force = body.force if body else False

    # Defect 11: cache the artifact on the ItineraryItem keyed by a hash of the
    # (capped) extra_narration. A repeat call with the same narration returns the
    # cached url WITHOUT re-running paid TTS; force=True or a changed narration
    # (hash mismatch) regenerates.
    # Defect 1: the cache key must also discriminate on provider/voice — otherwise
    # a client requesting a different voice/provider silently gets audio generated
    # with the ORIGINAL voice. Mix provider_name and voice_id into the hash so a
    # voice/provider change yields a mismatch and regenerates.
    narration_hash = hashlib.sha256(
        f"{provider_name or ''}\x00{voice_id or ''}\x00{narration}".encode()
    ).hexdigest()
    # Mobile calls this anonymously (KE5), so a cache MISS spends real TTS money
    # for an anonymous caller: bound the paid path the same way /audio/preview
    # is bounded. Checked after the cache lookup below would be too late, but
    # before it would rate-limit free cache hits — so limit only on the miss.
    if not force and rec["ke_url"] and rec["ke_hash"] == narration_hash:
        return KeepExploringAudioResponse(
            stop_id=stop_id,
            status="generated",
            audio_url=rec["ke_url"],
            duration_sec=rec["ke_dur"],
        )

    # Resolve the provider NAME only to decide whether this is a billed path.
    # An unknown provider must keep its existing soft-fail contract (200 with
    # status='failed' from generate_stop_audio below), never a 400 from here.
    try:
        resolved_provider = get_provider(provider_name).name
    except ValueError:
        resolved_provider = "mock"
    _audio_rate_limit(request, resolved_provider)

    try:
        gen = generate_stop_audio(
            narration,
            stop_key=f"{stop_id}-keep-exploring",
            poi_name=rec["poi_name"],
            provider_name=provider_name,
            voice_id=voice_id,
        )
    except PipelineError as e:
        return KeepExploringAudioResponse(stop_id=stop_id, status="failed", error=str(e))

    # Persist the cache on the item. This is separate from item.audio_url (the
    # scheduled per-stop tour audio) so the on-demand deep dive never masquerades
    # as the tour audio.
    session.run(
        "MATCH (i:ItineraryItem {id: $sid}) "
        "SET i.keep_exploring_audio_url = $url, "
        "    i.keep_exploring_audio_duration_sec = $dur, "
        "    i.keep_exploring_audio_hash = $hash",
        sid=stop_id,
        url=gen.audio_url,
        dur=gen.duration_sec,
        hash=narration_hash,
    )

    return KeepExploringAudioResponse(
        stop_id=stop_id,
        status="generated",
        audio_url=gen.audio_url,
        duration_sec=gen.duration_sec,
    )
