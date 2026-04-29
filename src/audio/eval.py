"""Audio evaluation — transcribe TTS output and compare against source text.

Uses OpenAI Whisper API for speech-to-text, then computes a similarity
score between the original script and the transcription.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

import httpx


class EvalError(Exception):
    """Raised when audio evaluation fails."""


@dataclass
class EvalResult:
    """Result of evaluating a TTS audio sample against its source text."""

    original_text: str
    transcribed_text: str
    similarity_score: float  # 0.0 to 1.0
    word_error_rate: float  # 0.0 = perfect, 1.0 = all wrong
    missing_words: list[str]
    extra_words: list[str]


def _normalize(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _word_error_rate(reference: list[str], hypothesis: list[str]) -> float:
    """Compute word error rate using Levenshtein distance on word sequences.

    WER = (substitutions + insertions + deletions) / len(reference)
    Returns 0.0 for perfect match, >1.0 possible if hypothesis is much longer.
    """
    r, h = reference, hypothesis
    n = len(r)
    m = len(h)

    # DP table
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        d[i][0] = i
    for j in range(m + 1):
        d[0][j] = j

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = 0 if r[i - 1] == h[j - 1] else 1
            d[i][j] = min(
                d[i - 1][j] + 1,  # deletion
                d[i][j - 1] + 1,  # insertion
                d[i - 1][j - 1] + cost,  # substitution
            )

    if n == 0:
        return 0.0 if m == 0 else 1.0
    return d[n][m] / n


def _set_similarity(ref_words: list[str], hyp_words: list[str]) -> float:
    """Simple set-based similarity (Jaccard-like) as a quick sanity metric."""
    ref_set = set(ref_words)
    hyp_set = set(hyp_words)
    if not ref_set:
        return 1.0 if not hyp_set else 0.0
    intersection = ref_set & hyp_set
    union = ref_set | hyp_set
    return len(intersection) / len(union)


def transcribe(audio_bytes: bytes, *, filename: str = "audio.mp3") -> str:
    """Transcribe audio bytes using OpenAI Whisper API.

    Requires OPENAI_API_KEY env var.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise EvalError("OPENAI_API_KEY not set — needed for Whisper transcription")

    resp = httpx.post(
        "https://api.openai.com/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {api_key}"},
        data={"model": "whisper-1"},
        files={"file": (filename, audio_bytes)},
        timeout=120.0,
    )

    if resp.status_code != 200:
        raise EvalError(f"Whisper API failed ({resp.status_code}): {resp.text[:200]}")

    return resp.json().get("text", "")


def evaluate(original_text: str, audio_bytes: bytes, *, filename: str = "audio.mp3") -> EvalResult:
    """Full eval pipeline: transcribe audio, then compare against original.

    Returns an EvalResult with similarity score, WER, and word diffs.
    """
    transcribed = transcribe(audio_bytes, filename=filename)

    ref_norm = _normalize(original_text)
    hyp_norm = _normalize(transcribed)

    ref_words = ref_norm.split()
    hyp_words = hyp_norm.split()

    wer = _word_error_rate(ref_words, hyp_words)
    similarity = _set_similarity(ref_words, hyp_words)

    ref_set = set(ref_words)
    hyp_set = set(hyp_words)
    missing = sorted(ref_set - hyp_set)
    extra = sorted(hyp_set - ref_set)

    return EvalResult(
        original_text=original_text,
        transcribed_text=transcribed,
        similarity_score=round(similarity, 4),
        word_error_rate=round(wer, 4),
        missing_words=missing,
        extra_words=extra,
    )
