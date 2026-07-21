"""Regression tests for three auth hardening defects in src/api/auth/routes.py.

1. The magic-link per-IP limiter trusted the LEFTMOST X-Forwarded-For hop, which
   is attacker-controlled — every spoofed value landed in a fresh bucket, so the
   per-IP cap never fired and one host could email-bomb unlimited addresses
   through the (billed) Resend account.
2. The limiter leaked two permanent dict entries per request on
   attacker-controlled keys — an unauthenticated memory-exhaustion DoS.
3. Refresh tokens were neither recorded, rotated, nor revocable, so a stolen
   token minted access tokens for 14 days with no way to invalidate it short of
   rotating JWT_SECRET_KEY for every user.

Each test is RED without the corresponding fix (see the per-test docstrings for
the undo-test) and GREEN with it.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.auth import routes as auth_routes
from src.api.auth.tokens import create_refresh_token, verify_token
from tests.conftest import needs_neo4j

REQUEST_URL = "/api/v1/auth/magic-link/request"


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    """The limiter keeps module-level in-process state that would otherwise bleed
    across tests (and across test files — they share one worker)."""
    auth_routes._magic_link_rate_state.clear()
    auth_routes._magic_link_global_hits.clear()
    auth_routes._magic_link_last_sweep = 0.0
    yield
    auth_routes._magic_link_rate_state.clear()
    auth_routes._magic_link_global_hits.clear()
    auth_routes._magic_link_last_sweep = 0.0


@pytest.fixture()
def nodb_client():
    """TestClient with the Neo4j driver patched out — magic-link/request never
    touches the DB, so these tests need no live Neo4j.

    Deliberately NOT named ``client``: that name belongs to the DB-backed
    module-scoped fixture in conftest, which the refresh-rotation tests below use.
    """
    with patch("src.api.app.init_driver"), patch("src.api.app.close_driver"):
        from src.api.app import create_app

        app = create_app()
        with TestClient(app) as c:
            yield c


# --- Defect 1: spoofable X-Forwarded-For -------------------------------------


@patch("src.api.auth.routes.send_magic_link", new_callable=AsyncMock)
def test_spoofed_forwarded_for_cannot_bypass_the_per_ip_cap(mock_send, nodb_client, monkeypatch):
    """One host rotating a fake LEFTMOST hop must still be capped.

    The header is ``<rotating spoof>, <fixed real edge-observed IP>``. Only the
    rightmost entry was appended by our own edge, so that is the identity.

    Undo-test: restore the leftmost-hop scan in ``_client_ip`` and every request
    lands in a fresh bucket — all 6 return 200 and 6 real Resend emails go out.
    """
    monkeypatch.setattr(auth_routes, "_MAGIC_LINK_RATE_LIMIT_MAX", 3)

    statuses = []
    for i in range(6):
        resp = nodb_client.post(
            REQUEST_URL,
            json={"email": f"victim{i}@example.com"},
            headers={"X-Forwarded-For": f"198.51.100.{i}, 203.0.113.9"},
        )
        statuses.append(resp.status_code)

    assert statuses == [200, 200, 200, 429, 429, 429]
    # The throttled calls never reached the billed email send.
    assert mock_send.call_count == 3


@patch("src.api.auth.routes.send_magic_link", new_callable=AsyncMock)
def test_global_cap_bounds_total_sends_under_genuine_ip_rotation(
    mock_send, nodb_client, monkeypatch
):
    """Per-IP limits are bypassable at scale by rotating GENUINE source IPs, so a
    global fixed-window cap must bound total sends.

    Every request here has a distinct real client IP and a distinct target email,
    so both per-key buckets are empty — only the global cap can stop it.

    Undo-test: set ``_MAGIC_LINK_GLOBAL_RATE_LIMIT_MAX`` to 0 (or remove the
    global check) and all 20 return 200.
    """
    monkeypatch.setattr(auth_routes, "_MAGIC_LINK_RATE_LIMIT_MAX", 5)
    monkeypatch.setattr(auth_routes, "_MAGIC_LINK_GLOBAL_RATE_LIMIT_MAX", 8)

    statuses = []
    for i in range(20):
        resp = nodb_client.post(
            REQUEST_URL,
            json={"email": f"rotate{i}@example.com"},
            headers={"X-Forwarded-For": f"203.0.113.{i}"},
        )
        statuses.append(resp.status_code)

    assert statuses.count(200) == 8
    assert statuses[8:] == [429] * 12
    assert mock_send.call_count == 8
    # The global 429 carries a usable Retry-After, like the per-key one.
    throttled = nodb_client.post(REQUEST_URL, json={"email": "x@example.com"})
    assert int(throttled.headers["Retry-After"]) >= 1


# --- Defect 2: unbounded limiter state ---------------------------------------


@patch("src.api.auth.routes.send_magic_link", new_callable=AsyncMock)
def test_rejected_requests_do_not_leak_rate_limit_keys(mock_send, nodb_client, monkeypatch):
    """Bombing ONE victim from many client IPs must not grow the limiter forever.

    Each request mints a fresh ``ip:`` key, then trips the ``email:`` cap and is
    rejected — leaving that ``ip:`` bucket empty. Without reclaim those empty
    entries are never revisited and accumulate permanently in the worker.

    The global cap is disabled here on purpose so the test isolates the RECLAIM
    mechanism rather than passing because the flood was short-circuited.

    Undo-test: drop the ``finally:`` reclaim block in ``_magic_link_rate_limit``
    and the state grows to 2001 entries (2000 empty ip: keys + 1 email: key).
    """
    monkeypatch.setattr(auth_routes, "_MAGIC_LINK_RATE_LIMIT_MAX", 3)
    monkeypatch.setattr(auth_routes, "_MAGIC_LINK_GLOBAL_RATE_LIMIT_MAX", 0)

    victim = "victim@example.com"
    for i in range(2000):
        nodb_client.post(
            REQUEST_URL,
            json={"email": victim},
            headers={"X-Forwarded-For": f"10.{i // 256}.{i % 256}.1"},
        )

    # Bounded by the CAP, not by the request count: the 3 accepted requests
    # legitimately keep their own ip: bucket, plus the victim's email: bucket.
    # Every one of the other 1997 rejected requests must leave nothing behind.
    assert len(auth_routes._magic_link_rate_state) <= 4
    assert mock_send.call_count == 3


@patch("src.api.auth.routes.send_magic_link", new_callable=AsyncMock)
def test_periodic_sweep_drops_stale_non_empty_keys(mock_send, nodb_client, monkeypatch):
    """A one-shot caller leaves a NON-empty bucket that the per-request reclaim
    can never free (it only revisits the current request's two keys). A periodic
    full sweep must drop those once their window has elapsed.

    Undo-test: remove the ``_sweep_magic_link_state_locked`` call and the state
    stays at 120 entries forever.
    """
    monkeypatch.setattr(auth_routes, "_MAGIC_LINK_RATE_LIMIT_MAX", 5)
    monkeypatch.setattr(auth_routes, "_MAGIC_LINK_GLOBAL_RATE_LIMIT_MAX", 0)

    for i in range(60):
        nodb_client.post(
            REQUEST_URL,
            json={"email": f"oneshot{i}@example.com"},
            headers={"X-Forwarded-For": f"192.0.2.{i}"},
        )
    # 60 ip: keys + 60 email: keys, each holding one live hit.
    assert len(auth_routes._magic_link_rate_state) == 120

    # Collapse the window so every recorded hit is now stale, and re-arm the sweep.
    monkeypatch.setattr(auth_routes, "_MAGIC_LINK_RATE_LIMIT_WINDOW_S", 0)
    monkeypatch.setattr(auth_routes, "_magic_link_last_sweep", 0.0)

    nodb_client.post(
        REQUEST_URL,
        json={"email": "later@example.com"},
        headers={"X-Forwarded-For": "192.0.2.200"},
    )

    # Everything stale was reclaimed; only the final request's own keys remain.
    assert len(auth_routes._magic_link_rate_state) <= 2


# --- Defect 3: refresh tokens are not rotated or revocable -------------------


def _login(client, email: str) -> dict:
    """Complete a magic-link login and return the token pair."""
    from src.api.auth.tokens import create_magic_token

    resp = client.post("/api/v1/auth/magic-link/verify", json={"token": create_magic_token(email)})
    assert resp.status_code == 200, resp.text
    return resp.json()


@needs_neo4j
class TestRefreshTokenRotationAndRevocation:
    def test_refresh_returns_a_rotated_token_not_the_submitted_one(self, client, clean_driver):
        """Undo-test: return ``body.refresh_token`` again and this goes RED — one
        long-lived secret stays in flight for the full 14 days."""
        tokens = _login(client, "rotate@ondoway.app")
        submitted = tokens["refresh_token"]

        resp = client.post("/api/v1/auth/refresh", json={"refresh_token": submitted})

        assert resp.status_code == 200
        rotated = resp.json()["refresh_token"]
        assert rotated != submitted

        old = verify_token(submitted, "refresh")
        new = verify_token(rotated, "refresh")
        # Rotation keeps the session identity but mints a fresh jti.
        assert new["jti"] != old["jti"]
        assert new["family"] == old["family"]
        assert new["sid"] == old["sid"]

    def test_replaying_a_consumed_refresh_token_401s_and_kills_the_family(
        self, client, clean_driver
    ):
        """A stolen token replayed after the victim already used it must 401 AND
        revoke the whole family, so the thief's rotated copy dies too.

        Undo-test: drop the ``record["used"]`` branch in /refresh and the replay
        succeeds with 200.
        """
        tokens = _login(client, "replay@ondoway.app")
        stolen = tokens["refresh_token"]

        first = client.post("/api/v1/auth/refresh", json={"refresh_token": stolen})
        assert first.status_code == 200
        rotated = first.json()["refresh_token"]

        # Replay of the consumed token.
        replay = client.post("/api/v1/auth/refresh", json={"refresh_token": stolen})
        assert replay.status_code == 401

        # ...and the family is now dead, including the token minted from it.
        after = client.post("/api/v1/auth/refresh", json={"refresh_token": rotated})
        assert after.status_code == 401

    def test_logout_revokes_the_refresh_token(self, client, clean_driver):
        """Undo-test: remove the /logout route (or its family revoke) and the
        post-logout refresh returns 200."""
        tokens = _login(client, "logout@ondoway.app")
        refresh_token = tokens["refresh_token"]

        out = client.post("/api/v1/auth/logout", json={"refresh_token": refresh_token})
        assert out.status_code == 200

        resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
        assert resp.status_code == 401

    def test_logout_is_idempotent_and_never_401s(self, client, clean_driver):
        """A client clearing local state must be able to fire-and-forget."""
        tokens = _login(client, "idem@ondoway.app")
        for _ in range(2):
            resp = client.post(
                "/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]}
            )
            assert resp.status_code == 200
        junk = client.post("/api/v1/auth/logout", json={"refresh_token": "garbage"})
        assert junk.status_code == 200

    def test_logout_all_revokes_every_session_for_the_user(self, client, clean_driver):
        """Stolen-device case: one call kills all outstanding refresh tokens."""
        email = "logoutall@ondoway.app"
        first = _login(client, email)
        second = _login(client, email)
        assert first["refresh_token"] != second["refresh_token"]

        resp = client.post(
            "/api/v1/auth/logout-all",
            headers={"Authorization": f"Bearer {second['access_token']}"},
        )
        assert resp.status_code == 200

        for tokens in (first, second):
            assert (
                client.post(
                    "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
                ).status_code
                == 401
            )

    def test_unrecorded_refresh_token_is_rejected(self, client, clean_driver):
        """A well-formed, correctly-signed token that was never issued through the
        store (e.g. minted before the store existed, or forged with a leaked
        secret) has no denylist entry and must not be honoured.

        Undo-test: drop the ``record is None`` branch and this returns 200.
        """
        resp = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": create_refresh_token("ghost-user", "sid", "fam")},
        )
        assert resp.status_code == 401
