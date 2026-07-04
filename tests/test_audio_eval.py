"""Unit tests for audio evaluation (speech-to-text comparison).

Tests the pure logic (WER, similarity, normalization) without requiring API keys.
Whisper transcription is tested with mocks.
"""

from __future__ import annotations

from unittest.mock import patch

import httpx
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


class _FakeResp:
    """Minimal httpx.Response stand-in for transcribe's status/json/text use."""

    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload

    @property
    def text(self):
        return str(self._payload)


class TestTranscribe:
    def test_missing_api_key_raises(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(EvalError, match="OPENAI_API_KEY not set"):
            transcribe(b"fake audio")

    def test_transient_cloudflare_404_is_retried_then_succeeds(self, monkeypatch):
        # Reproduces the observed flake: a Cloudflare 404 "Invalid URL" on the
        # first Whisper attempt, healthy on the second — transcribe must retry,
        # not fail the live audio bar.
        monkeypatch.setenv("OPENAI_API_KEY", "fake")
        monkeypatch.setattr("src.audio._http.time.sleep", lambda *_: None)
        calls = {"n": 0}

        def fake_post(self, *args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                return _FakeResp(404, {"detail": {"message": "Invalid URL"}, "error": {}})
            return _FakeResp(200, {"text": "hello world"})

        monkeypatch.setattr(httpx.Client, "post", fake_post)
        out = transcribe(b"audio-bytes", filename="x.mp3")
        assert out == "hello world"
        assert calls["n"] == 2

    def test_persistent_404_raises_evalerror(self, monkeypatch):
        # A genuinely persistent 404 still surfaces as an EvalError after retries.
        monkeypatch.setenv("OPENAI_API_KEY", "fake")
        monkeypatch.setattr("src.audio._http.time.sleep", lambda *_: None)

        def always_404(self, *args, **kwargs):
            return _FakeResp(404, {"detail": "nope"})

        monkeypatch.setattr(httpx.Client, "post", always_404)
        with pytest.raises(EvalError, match="Whisper API failed"):
            transcribe(b"audio-bytes")


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

    def test_re_transcribes_on_degenerate_output_and_keeps_best(self, monkeypatch):
        """A degenerate Whisper result (near-empty 'you' for a paragraph) triggers
        a bounded re-transcribe; the good attempt wins. Guards the live-audio-bar
        flake root cause (WER 1.0 'you' on Shakespeare & Company)."""
        monkeypatch.setenv("OPENAI_API_KEY", "fake")
        ref = "Sylvia Beach opened the original shop in nineteen nineteen and published Ulysses"
        # First call degenerates to 'you'; the retry returns the true text.
        with patch("src.audio.eval.transcribe", side_effect=["you", ref]) as m:
            result = evaluate(ref, b"fake audio")
        assert m.call_count == 2, "must re-transcribe once past the degenerate result"
        assert result.word_error_rate == 0.0, "keeps the good retry, not the 'you' garbage"
        assert result.transcribed_text == ref

    def test_no_retry_on_complete_transcription(self, monkeypatch):
        """A complete-but-imperfect transcription (word count near the reference)
        is accepted immediately — no wasted re-transcribe on ordinary accent miss."""
        monkeypatch.setenv("OPENAI_API_KEY", "fake")
        ref = "hello world this is a longer reference sentence for the count check"
        hyp = "hello world this is a longer reference sentence for the count chek"  # 1 typo
        with patch("src.audio.eval.transcribe", side_effect=[hyp, ref]) as m:
            result = evaluate(ref, b"fake audio")
        assert m.call_count == 1, "a near-complete transcription must not re-transcribe"
        assert 0.0 < result.word_error_rate < 0.15

    def test_degenerate_retries_bounded_and_returns_best(self, monkeypatch):
        """If every attempt degenerates, the loop is bounded (3) and still returns
        the least-bad result — never an infinite retry."""
        monkeypatch.setenv("OPENAI_API_KEY", "fake")
        ref = "one two three four five six seven eight nine ten eleven twelve"
        with patch("src.audio.eval.transcribe", side_effect=["you", "you", "you", ref]) as m:
            result = evaluate(ref, b"fake audio")
        assert m.call_count == 3, "bounded at _MAX_TRANSCRIBE_ATTEMPTS"
        assert result.word_error_rate == 1.0  # all attempts were 'you'
