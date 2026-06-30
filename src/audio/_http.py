"""Shared bounded-retry POST for the live OpenAI audio calls (TTS + Whisper).

Both OpenAI endpoints sit behind Cloudflare, which can return TRANSIENT gateway
errors during edge route-flaps — a ``404 "Invalid URL"`` (a Cloudflare/gateway
artifact, not OpenAI's own ``{"error": ...}`` shape) or a 5xx — even though the
endpoint is healthy. A single blip must not fail a user's audio or the test bar,
so live calls retry with bounded exponential backoff on transient network errors
AND transient gateway statuses.

``404`` is treated as transient ONLY because every caller posts to a HARDCODED,
verified-correct OpenAI URL — a 404 there cannot be a real "wrong path" bug, only
an edge artifact; the bounded attempt count means a (hypothetical) persistent 404
still surfaces to the caller after the retries are exhausted.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import httpx

# Transient gateway statuses worth retrying on hardcoded, verified URLs.
RETRYABLE_STATUSES: frozenset[int] = frozenset({404, 408, 409, 425, 429, 500, 502, 503, 504})

# Network-layer transients (server overload, packet loss, reset, half-closed conn).
TRANSIENT_NETWORK_EXC = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.ReadError,
    httpx.RemoteProtocolError,
)

MAX_ATTEMPTS = 3
INITIAL_BACKOFF_SEC = 0.5


def _default_client(timeout: float) -> httpx.Client:
    # proxy=None bypasses any ambient HTTPS_PROXY (corp/VPN) for these direct calls.
    return httpx.Client(transport=httpx.HTTPTransport(proxy=None), timeout=timeout)


def post_with_retry(
    url: str,
    *,
    timeout: float = 60.0,
    max_attempts: int = MAX_ATTEMPTS,
    initial_backoff: float = INITIAL_BACKOFF_SEC,
    retryable_statuses: frozenset[int] = RETRYABLE_STATUSES,
    client_factory: Callable[[], httpx.Client] | None = None,
    sleep: Callable[[float], None] | None = None,
    **post_kwargs: object,
) -> httpx.Response:
    """POST ``url`` with bounded exponential-backoff retry on transient failures.

    Retries transient network errors (``_TRANSIENT_EXC``) and transient gateway
    statuses (``retryable_statuses``) up to ``max_attempts`` (backoff doubles from
    ``initial_backoff``). Returns the FINAL response — including a non-2xx status
    after the attempts are exhausted — so the caller still interprets terminal
    statuses (401 auth, 400 validation) itself; those are never retried. Raises the
    last network exception only when EVERY attempt raised one. ``client_factory``
    and ``sleep`` are injectable so the retry path is unit-testable without real
    network calls or real delays.
    """
    do_sleep = sleep if sleep is not None else time.sleep
    make_client = (
        client_factory if client_factory is not None else (lambda: _default_client(timeout))
    )
    backoff = initial_backoff
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            with make_client() as client:
                resp = client.post(url, **post_kwargs)
        except TRANSIENT_NETWORK_EXC as exc:
            last_exc = exc
            if attempt < max_attempts - 1:
                do_sleep(backoff)
                backoff *= 2
            continue
        if resp.status_code in retryable_statuses and attempt < max_attempts - 1:
            do_sleep(backoff)
            backoff *= 2
            continue
        return resp
    # Only reached when every attempt raised a network transient.
    raise last_exc  # type: ignore[misc]
