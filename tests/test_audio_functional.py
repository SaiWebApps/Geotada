"""Functional smoke tests — real OpenAI TTS + Whisper round-trip.

These tests hit live APIs and cost ~$0.02 per run.
They are SKIPPED automatically when:
  - OPENAI_API_KEY is not set
  - OpenAI API is unreachable (corporate proxy, no internet)

Run explicitly (off VPN/proxy):
    make test-functional
"""

from __future__ import annotations

import os

import httpx
import pytest

from src.audio.eval import evaluate
from src.audio.provider import get_provider
from src.seed.narratives import BEATS

# This module makes real paid OpenAI TTS and transcription calls.  The repository's
# default test bar excludes the ``live`` marker; keeping the marker at module scope
# prevents a configured developer machine from spending money during ``make test``.
pytestmark = pytest.mark.live


def _openai_reachable() -> bool:
    """Quick check: can we reach the OpenAI API from this network?"""
    if not os.getenv("OPENAI_API_KEY"):
        return False
    try:
        import urllib.error
        import urllib.request

        handler = urllib.request.ProxyHandler({})
        opener = urllib.request.build_opener(handler)
        resp = opener.open("https://api.openai.com/v1/models", timeout=5)
        return resp.status in (200, 401)
    except urllib.error.HTTPError as exc:
        return exc.code == 401
    except Exception:
        try:
            resp = httpx.get("https://api.openai.com/v1/models", timeout=5.0)
            return resp.status_code in (200, 401)
        except (httpx.ProxyError, httpx.ConnectError, httpx.TimeoutException):
            return False


@pytest.fixture(scope="module", autouse=True)
def _require_explicit_live_openai() -> None:
    """Probe only when live test execution starts, never during collection."""
    if os.getenv("ONDOWAY_LIVE_TESTS") != "1":
        pytest.fail("use `make test-functional` to authorize live OpenAI calls")
    if not _openai_reachable():
        pytest.fail("OpenAI API is unreachable or OPENAI_API_KEY is unset")

# Extract scripts from seed data
SCRIPTS = [beat["script_body"] for beat in BEATS]


class TestOpenAIGeneratesValidMP3:
    """Verify that OpenAI TTS returns valid, non-empty MP3 for each seed script."""

    @pytest.fixture(scope="class")
    def provider(self):
        return get_provider("openai")

    @pytest.mark.parametrize("script", SCRIPTS, ids=[b["poi_name"] for b in BEATS])
    def test_generates_non_empty_mp3(self, provider, script):
        audio = provider.generate(script)

        # Non-empty
        assert len(audio) > 1000, f"Audio too small: {len(audio)} bytes"
        assert len(audio) < 5_000_000, f"Audio too large: {len(audio)} bytes"

        # Valid MP3: starts with ID3 tag or MP3 frame sync
        assert audio[:3] == b"ID3" or audio[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"), (
            f"Not a valid MP3 — first bytes: {audio[:4].hex()}"
        )


class TestOpenAIAudioMatchesScript:
    """Generate audio, transcribe it back with Whisper, and verify low WER."""

    @pytest.fixture(scope="class")
    def provider(self):
        return get_provider("openai")

    @pytest.mark.parametrize("script", SCRIPTS, ids=[b["poi_name"] for b in BEATS])
    def test_word_error_rate_below_threshold(self, provider, script):
        audio = provider.generate(script)
        result = evaluate(script, audio, filename="functional_test.mp3")

        # Print for manual review (visible with pytest -s)
        print(f"\n  WER: {result.word_error_rate:.3f}")
        print(f"  Similarity: {result.similarity_score:.3f}")
        if result.missing_words:
            print(f"  Missing: {result.missing_words}")
        if result.extra_words:
            print(f"  Extra: {result.extra_words}")

        assert result.word_error_rate < 0.15, (
            f"WER {result.word_error_rate:.3f} exceeds 0.15 threshold.\n"
            f"Original:    {result.original_text[:100]}...\n"
            f"Transcribed: {result.transcribed_text[:100]}..."
        )


class TestEvalEndpoint:
    """Verify the /audio/eval API endpoint works end-to-end with real APIs."""

    def test_eval_returns_pass_or_review(self):
        from fastapi.testclient import TestClient

        from src.api.app import create_app

        client = TestClient(create_app())

        resp = client.post(
            "/api/v1/audio/eval",
            json={
                "text": SCRIPTS[0],
                "provider": "openai",
            },
        )

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

        data = resp.json()
        print(f"\n  Provider: {data['provider']}")
        print(f"  WER: {data['word_error_rate']:.3f}")
        print(f"  Verdict: {data['verdict']}")

        assert data["verdict"] in ("PASS", "REVIEW"), (
            f"Verdict is FAIL — WER {data['word_error_rate']:.3f} is too high.\n"
            f"Transcribed: {data['transcribed_text'][:100]}..."
        )
