"""Pydantic models for audio generation endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AudioPreviewRequest(BaseModel):
    """Request body for generating a TTS audio preview."""

    text: str = Field(..., min_length=1, max_length=5000)
    provider: str = "mock"
    voice_id: str | None = None


class AudioStatusResponse(BaseModel):
    """Status of audio generation for a NarrativeBeat."""

    beat_id: str
    has_audio: bool
    audio_url: str | None = None
    duration_sec: float | None = None
    is_stale: bool = False


class ProviderInfo(BaseModel):
    """Metadata about an available TTS provider."""

    name: str
    available: bool


class ProviderListResponse(BaseModel):
    """List of registered TTS providers."""

    providers: list[ProviderInfo]


class CompareRequest(BaseModel):
    """Request body for comparing TTS output across providers."""

    text: str = Field(..., min_length=1, max_length=5000)
    providers: list[str] = Field(..., min_length=1, max_length=5)
    voice_ids: dict[str, str] = Field(
        default_factory=dict,
        description="Optional per-provider voice IDs, e.g. {'openai': 'nova'}",
    )


class CompareResultItem(BaseModel):
    """Result from a single provider in a comparison."""

    provider: str
    success: bool
    error: str | None = None
    size_bytes: int = 0
    duration_estimate_sec: float = 0.0
    download_path: str | None = None


class CompareResponse(BaseModel):
    """Side-by-side comparison results from multiple providers."""

    text: str
    results: list[CompareResultItem]


class EvalRequest(BaseModel):
    """Request body for evaluating TTS output against source text."""

    text: str = Field(..., min_length=1, max_length=5000)
    provider: str = "mock"
    voice_id: str | None = None


class EvalResponse(BaseModel):
    """Evaluation result — how well the audio matches the source text."""

    provider: str
    original_text: str
    transcribed_text: str
    similarity_score: float = Field(
        ..., description="0.0–1.0 Jaccard set similarity of words"
    )
    word_error_rate: float = Field(
        ..., description="0.0 = perfect, higher = worse"
    )
    missing_words: list[str]
    extra_words: list[str]
    verdict: str = Field(
        ..., description="PASS / REVIEW / FAIL based on WER thresholds"
    )


class GenerateRequest(BaseModel):
    """Request body for generating audio for a NarrativeBeat."""

    provider: str = "mock"
    voice_id: str | None = None
    force: bool = Field(
        False, description="Force regeneration even if audio already exists"
    )


class GenerateResponse(BaseModel):
    """Result of generating audio for a NarrativeBeat."""

    beat_id: str
    provider: str
    storage: str
    audio_url: str
    size_bytes: int


class BatchGenerateRequest(BaseModel):
    """Request body for batch audio generation."""

    provider: str = "mock"
    voice_id: str | None = None
    force: bool = False


class BatchResultItem(BaseModel):
    """Result for one beat in a batch generation."""

    beat_id: str
    success: bool
    audio_url: str | None = None
    size_bytes: int = 0
    error: str | None = None


class BatchGenerateResponse(BaseModel):
    """Results of batch audio generation."""

    total_found: int = Field(description="Total NarrativeBeats in the graph")
    total_processed: int
    succeeded: int
    failed: int
    skipped: int = Field(0, description="Beats that already had up-to-date audio")
    total_bytes: int = Field(0, description="Total bytes of audio generated")
    elapsed_sec: float = Field(0.0, description="Wall clock time in seconds")
    results: list[BatchResultItem]
