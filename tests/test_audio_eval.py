"""Unit tests for audio evaluation (speech-to-text comparison).

Tests the pure logic (WER, similarity, normalization) without requiring API keys.
Whisper transcription is tested with mocks.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.audio.eval import (
    EvalError,
    EvalResult,
    _normalize,
    _set_similarity,
    _word_error_rate,
    evaluate,
    transcribe,
)


class TestNormalize:
    def test_lowercases(self):
        assert _normalize("Hello World") == "hello world"

    def test_strips_punctuation(self):
        assert _normalize("Hello, World!") == "hello world"

    def test_collapses_whitespace(self):
        assert _normalize("hello   world") == "hello world"

    def test_strips_leading_trailing(self):
        assert _normalize("  hello  ") == "hello"

    def test_handles_dashes(self):
        # Punctuation is a word boundary, not a word-join. The eval compares a
        # spaced em-dash in the script ("hub — the") against Whisper's unspaced
        # "hub—the"; deleting the dash would yield "hubthe" and inflate WER, so
        # both must normalize to "hub the".
        assert _normalize("hub — the") == "hub the"
        assert _normalize("hub—the") == "hub the"
        assert _normalize("Look up — 2.5 million") == "look up 2 5 million"

    def test_folds_accents(self):
        # Whisper strips diacritics; the reference must too, or French proper
        # nouns inflate WER spuriously ("café" vs "cafe").
        assert _normalize("Café") == "cafe"
        assert _normalize("Café de Flore") == "cafe de flore"
        assert _normalize("Élève à Étretat") == "eleve a etretat"
        assert _normalize("Café, c'est bon!") == "cafe c est bon"


class TestWordErrorRate:
    def test_exact_match(self):
        words = ["hello", "world", "this", "is", "a", "test"]
        assert _word_error_rate(words, words) == 0.0

    def test_one_substitution(self):
        ref = ["hello", "world", "this", "is", "a", "test"]
        hyp = ["hello", "world", "this", "is", "a", "toast"]
        wer = _word_error_rate(ref, hyp)
        assert abs(wer - 1 / 6) < 0.01

    def test_deletions(self):
        ref = ["hello", "world", "this", "is", "a", "test"]
        hyp = ["hello", "world"]
        wer = _word_error_rate(ref, hyp)
        assert abs(wer - 4 / 6) < 0.01

    def test_insertions(self):
        ref = ["hello", "world"]
        hyp = ["hello", "beautiful", "world", "today"]
        wer = _word_error_rate(ref, hyp)
        assert wer == 1.0  # 2 insertions / 2 reference words

    def test_empty_reference(self):
        assert _word_error_rate([], []) == 0.0
        assert _word_error_rate([], ["hello"]) == 1.0


class TestSetSimilarity:
    def test_exact_match(self):
        words = ["hello", "world"]
        assert _set_similarity(words, words) == 1.0

    def test_no_overlap(self):
        assert _set_similarity(["a", "b"], ["c", "d"]) == 0.0

    def test_partial_overlap(self):
        sim = _set_similarity(["a", "b", "c"], ["a", "b", "d"])
        assert abs(sim - 0.5) < 0.01  # 2/4

    def test_empty_sets(self):
        assert _set_similarity([], []) == 1.0
        assert _set_similarity([], ["a"]) == 0.0


class TestTranscribe:
    def test_missing_api_key_raises(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(EvalError, match="OPENAI_API_KEY not set"):
            transcribe(b"fake audio")


class TestEvaluate:
    def test_end_to_end_with_mock_transcription(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "fake")

        # Mock the transcribe function to return known text
        with patch("src.audio.eval.transcribe", return_value="hello world this is a test"):
            result = evaluate("Hello, world! This is a test.", b"fake audio")

        assert isinstance(result, EvalResult)
        assert result.word_error_rate == 0.0
        assert result.similarity_score == 1.0
        assert result.missing_words == []
        assert result.extra_words == []

    def test_detects_missing_words(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "fake")

        with patch("src.audio.eval.transcribe", return_value="hello world"):
            result = evaluate("Hello world this is a test", b"fake audio")

        assert result.word_error_rate > 0
        assert "is" in result.missing_words or "test" in result.missing_words

    def test_detects_extra_words(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "fake")

        with patch("src.audio.eval.transcribe", return_value="hello beautiful amazing world"):
            result = evaluate("Hello world", b"fake audio")

        assert "beautiful" in result.extra_words
        assert "amazing" in result.extra_words
