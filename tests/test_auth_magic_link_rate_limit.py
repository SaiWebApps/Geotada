"""Regression tests for the /auth/magic-link/request abuse guard.

The endpoint is unauthenticated and sends a real (billed) email on every call,
so an attacker could email-bomb any address / drain the Resend quota. These
tests pin the per-IP and per-email fixed-window rate limit. RED without the
guard in src/api/auth/routes.py (all calls would 200); GREEN with it.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    """The per-IP/per-email limiter keeps module-level in-process state that
    would otherwise bleed across tests (all use the same 'testclient' IP)."""
    from src.api.auth import routes as auth_routes

    state = getattr(auth_routes, "_magic_link_rate_state", None)
    if state is not None:
        state.clear()
    yield
    if state is not None:
        state.clear()


@pytest.fixture()
def client():
    """TestClient with the Neo4j driver patched out — magic-link/request never
    touches the DB, so this avoids requiring a live test Neo4j instance."""
    with patch("src.api.app.init_driver"), patch("src.api.app.close_driver"):
        from src.api.app import create_app

        app = create_app()
        with TestClient(app) as c:
            yield c


@patch("src.api.auth.routes.send_magic_link", new_callable=AsyncMock)
def test_excess_requests_from_one_ip_are_rate_limited_429(mock_send, client, monkeypatch):
    monkeypatch.setattr("src.api.auth.routes._MAGIC_LINK_RATE_LIMIT_MAX", 3)

    # Vary the email so this exercises the per-IP cap, not the per-email cap.
    statuses = [
        client.post(
            "/api/v1/auth/magic-link/request",
            json={"email": f"user{i}@example.com"},
        ).status_code
        for i in range(4)
    ]

    assert statuses[:3] == [200, 200, 200]
    assert statuses[3] == 429
    # The throttled call never reached the (billed) email send.
    assert mock_send.call_count == 3


@patch("src.api.auth.routes.send_magic_link", new_callable=AsyncMock)
def test_bombing_one_victim_is_rate_limited_even_across_ips(mock_send, client, monkeypatch):
    monkeypatch.setattr("src.api.auth.routes._MAGIC_LINK_RATE_LIMIT_MAX", 3)

    victim = "victim@example.com"
    # Same target email from "different" callers — the per-email cap must trip
    # even though each IP is under its own limit.
    statuses = []
    for i in range(4):
        resp = client.post(
            "/api/v1/auth/magic-link/request",
            json={"email": victim},
            headers={"X-Forwarded-For": f"10.0.0.{i}"},
        )
        statuses.append(resp.status_code)

    assert statuses[:3] == [200, 200, 200]
    assert statuses[3] == 429
    assert mock_send.call_count == 3


@patch("src.api.auth.routes.send_magic_link", new_callable=AsyncMock)
def test_distinct_forwarded_clients_do_not_share_one_ip_bucket(mock_send, client, monkeypatch):
    """Login-availability DoS regression.

    Behind Render's reverse proxy every request arrives from the same proxy
    peer, so keying the per-IP limiter on ``request.client.host`` collapses ALL
    external users into one bucket. Once a handful of magic-link requests occur
    in the window, an unrelated first-time user (whose own per-email bucket is
    empty) is wrongly 429'd — passwordless login goes down for everyone.

    The limiter must instead key on the real client from ``X-Forwarded-For``.
    With that, N distinct clients each making one request (distinct emails, so
    the per-email cap never trips) must ALL succeed even when N exceeds the cap.
    RED with ``request.client.host`` (7th+ call is 429); GREEN with the header.
    """
    monkeypatch.setattr("src.api.auth.routes._MAGIC_LINK_RATE_LIMIT_MAX", 5)

    statuses = []
    for i in range(12):
        resp = client.post(
            "/api/v1/auth/magic-link/request",
            json={"email": f"legit{i}@example.com"},
            headers={"X-Forwarded-For": f"203.0.113.{i}"},
        )
        statuses.append(resp.status_code)

    # Each distinct client is under its own per-IP cap and has a distinct email,
    # so every request must succeed — no shared-bucket lockout.
    assert statuses == [200] * 12
    assert mock_send.call_count == 12


@patch("src.api.auth.routes.send_magic_link", new_callable=AsyncMock)
def test_forwarded_for_client_still_capped_after_exceeding_window(mock_send, client, monkeypatch):
    """A single real client (fixed X-Forwarded-For) is still throttled — the
    fix must not disable per-IP enforcement, only stop the proxy-collapse."""
    monkeypatch.setattr("src.api.auth.routes._MAGIC_LINK_RATE_LIMIT_MAX", 3)

    statuses = [
        client.post(
            "/api/v1/auth/magic-link/request",
            json={"email": f"user{i}@example.com"},
            headers={"X-Forwarded-For": "198.51.100.7"},
        ).status_code
        for i in range(4)
    ]

    assert statuses[:3] == [200, 200, 200]
    assert statuses[3] == 429
    assert mock_send.call_count == 3


@patch("src.api.auth.routes.send_magic_link", new_callable=AsyncMock)
def test_429_carries_retry_after_header(mock_send, client, monkeypatch):
    monkeypatch.setattr("src.api.auth.routes._MAGIC_LINK_RATE_LIMIT_MAX", 1)

    client.post("/api/v1/auth/magic-link/request", json={"email": "a@example.com"})
    resp = client.post("/api/v1/auth/magic-link/request", json={"email": "a@example.com"})

    assert resp.status_code == 429
    assert int(resp.headers["Retry-After"]) >= 1
