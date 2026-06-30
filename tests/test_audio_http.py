"""Unit tests for the shared bounded-retry POST (src/audio/_http.py).

Hermetic — no real network. Uses httpx.MockTransport via the injectable
client_factory and a no-op sleep, so the retry mechanics are proven offline.
"""

from __future__ import annotations

import httpx
import pytest

from src.audio._http import RETRYABLE_STATUSES, post_with_retry


def _factory(handler):
    """A client_factory returning a fresh MockTransport-backed client per attempt."""
    return lambda: httpx.Client(transport=httpx.MockTransport(handler))


def test_retries_transient_404_then_succeeds():
    # The exact observed failure: a Cloudflare 404 "Invalid URL" (note the
    # non-OpenAI {detail, error} body shape) on attempt 1, healthy on attempt 2.
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(404, json={"detail": {"message": "Invalid URL"}, "error": {}})
        return httpx.Response(200, json={"text": "ok"})

    resp = post_with_retry(
        "https://api.openai.com/v1/audio/transcriptions",
        client_factory=_factory(handler),
        sleep=lambda _s: None,
    )
    assert resp.status_code == 200
    assert calls["n"] == 2


def test_retries_transient_503_then_succeeds():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(503) if calls["n"] == 1 else httpx.Response(200, json={"ok": True})

    resp = post_with_retry("https://x", client_factory=_factory(handler), sleep=lambda _s: None)
    assert resp.status_code == 200
    assert calls["n"] == 2


def test_persistent_retryable_status_returns_final_after_attempts():
    # A genuinely persistent 404 still surfaces (returned, not masked) after the
    # bounded attempts — the caller raises on it.
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(404, json={"detail": "always"})

    resp = post_with_retry(
        "https://x", client_factory=_factory(handler), sleep=lambda _s: None, max_attempts=3
    )
    assert resp.status_code == 404
    assert calls["n"] == 3


def test_terminal_status_not_retried():
    # 401 (auth) is NOT in the retryable set — one attempt, surfaced immediately.
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(401, json={"error": "auth"})

    resp = post_with_retry("https://x", client_factory=_factory(handler), sleep=lambda _s: None)
    assert resp.status_code == 401
    assert calls["n"] == 1


def test_retries_network_timeout_then_succeeds():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] < 2:
            raise httpx.TimeoutException("transient")
        return httpx.Response(200)

    resp = post_with_retry("https://x", client_factory=_factory(handler), sleep=lambda _s: None)
    assert resp.status_code == 200
    assert calls["n"] == 2


def test_raises_after_all_attempts_network_error():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        raise httpx.ConnectError("down")

    with pytest.raises(httpx.ConnectError):
        post_with_retry(
            "https://x", client_factory=_factory(handler), sleep=lambda _s: None, max_attempts=3
        )
    assert calls["n"] == 3


def test_cloudflare_404_is_in_the_retryable_set():
    # Guards the deliberate decision that the transient Cloudflare 404 is retried.
    assert 404 in RETRYABLE_STATUSES
