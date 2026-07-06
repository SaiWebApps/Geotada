"""Unit tests for automatic Aura resume (no live network, no Neo4j).

The Aura HTTP surface is faked by monkeypatching ``requests.post`` / ``requests.get``
on the ``src.aura_resume`` module. The feature is a safe NO-OP when creds are unset,
so we assert both the enabled paths (token/status/resume, single-resume guarantee,
error swallowing) and the disabled path (coordinator None, healthz unchanged).
"""

from __future__ import annotations

import base64
import threading

import pytest

import src.aura_resume as ar
from src.aura_resume import (
    AuraClient,
    AuraConfig,
    ResumeCoordinator,
    build_coordinator,
)

# ── fake requests plumbing ────────────────────────────────────────────────────


class _FakeResponse:
    def __init__(self, status_code: int, payload=None, text: str = ""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json body")
        return self._payload


class _FakeHTTP:
    """Records calls and returns queued/canned responses; thread-safe counters."""

    def __init__(self, status_value: str = "paused"):
        self.status_value = status_value
        self.lock = threading.Lock()
        self.post_calls: list[dict] = []
        self.get_calls: list[dict] = []
        self.token_error: Exception | None = None
        self.status_error: Exception | None = None
        self.resume_error: Exception | None = None
        # allow tests to slow the status check so concurrency actually overlaps
        self.status_delay = 0.0

    def post(self, url, headers=None, data=None, json=None, timeout=None):
        with self.lock:
            self.post_calls.append(
                {"url": url, "headers": headers or {}, "data": data or {}, "json": json}
            )
        if url == ar._TOKEN_URL:
            if self.token_error is not None:
                raise self.token_error
            return _FakeResponse(
                200, {"access_token": "tok-123", "token_type": "bearer", "expires_in": 3600}
            )
        # resume endpoint
        if self.resume_error is not None:
            raise self.resume_error
        return _FakeResponse(202)

    def get(self, url, headers=None, timeout=None):
        import time as _time

        if self.status_delay:
            _time.sleep(self.status_delay)
        with self.lock:
            self.get_calls.append({"url": url, "headers": headers or {}})
        if self.status_error is not None:
            raise self.status_error
        return _FakeResponse(200, {"data": {"status": self.status_value}})

    @property
    def resume_post_count(self) -> int:
        return sum(1 for c in self.post_calls if c["url"].endswith("/resume"))

    @property
    def token_post_count(self) -> int:
        return sum(1 for c in self.post_calls if c["url"] == ar._TOKEN_URL)


@pytest.fixture
def fake_http(monkeypatch):
    http = _FakeHTTP()
    monkeypatch.setattr(ar.requests, "post", http.post)
    monkeypatch.setattr(ar.requests, "get", http.get)
    return http


def _cfg() -> AuraConfig:
    return AuraConfig(client_id="cid", client_secret="csecret", instance_id="8a37bbaf")


# ── AuraConfig.from_env ───────────────────────────────────────────────────────


def test_from_env_none_when_creds_unset(monkeypatch):
    monkeypatch.delenv("AURA_CLIENT_ID", raising=False)
    monkeypatch.delenv("AURA_CLIENT_SECRET", raising=False)
    monkeypatch.setenv("NEO4J_URI", "neo4j+s://8a37bbaf.databases.neo4j.io")
    assert AuraConfig.from_env() is None


def test_from_env_none_when_only_id_set(monkeypatch):
    monkeypatch.setenv("AURA_CLIENT_ID", "cid")
    monkeypatch.delenv("AURA_CLIENT_SECRET", raising=False)
    assert AuraConfig.from_env() is None


def test_from_env_derives_instance_id_from_neo4j_uri_host(monkeypatch):
    monkeypatch.setenv("AURA_CLIENT_ID", "cid")
    monkeypatch.setenv("AURA_CLIENT_SECRET", "csecret")
    monkeypatch.delenv("AURA_INSTANCE_ID", raising=False)
    monkeypatch.setenv("NEO4J_URI", "neo4j+s://8a37bbaf.databases.neo4j.io")
    cfg = AuraConfig.from_env()
    assert cfg is not None
    assert cfg.instance_id == "8a37bbaf"


def test_from_env_instance_id_override(monkeypatch):
    monkeypatch.setenv("AURA_CLIENT_ID", "cid")
    monkeypatch.setenv("AURA_CLIENT_SECRET", "csecret")
    monkeypatch.setenv("AURA_INSTANCE_ID", "override-id")
    monkeypatch.setenv("NEO4J_URI", "neo4j+s://8a37bbaf.databases.neo4j.io")
    cfg = AuraConfig.from_env()
    assert cfg is not None
    assert cfg.instance_id == "override-id"


def test_from_env_none_when_no_instance_id_derivable(monkeypatch):
    monkeypatch.setenv("AURA_CLIENT_ID", "cid")
    monkeypatch.setenv("AURA_CLIENT_SECRET", "csecret")
    monkeypatch.delenv("AURA_INSTANCE_ID", raising=False)
    monkeypatch.setenv("NEO4J_URI", "")  # no host to parse
    assert AuraConfig.from_env() is None


# ── token: Basic auth + client_credentials + caching ──────────────────────────


def test_token_uses_basic_auth_and_client_credentials(fake_http):
    client = AuraClient(_cfg())
    client.get_status()  # triggers a token POST then a status GET

    token_calls = [c for c in fake_http.post_calls if c["url"] == ar._TOKEN_URL]
    assert len(token_calls) == 1
    call = token_calls[0]
    expected = base64.b64encode(b"cid:csecret").decode("ascii")
    assert call["headers"]["Authorization"] == f"Basic {expected}"
    assert call["data"] == {"grant_type": "client_credentials"}


def test_token_is_cached_across_calls(fake_http):
    client = AuraClient(_cfg())
    client.get_status()
    client.get_status()
    # two status GETs, but the token is fetched exactly once
    assert fake_http.token_post_count == 1
    assert len(fake_http.get_calls) == 2
    # the bearer token from the cache is sent on the status GETs
    assert fake_http.get_calls[0]["headers"]["Authorization"] == "Bearer tok-123"


# ── ResumeCoordinator: single-resume guarantee + statuses + error swallowing ──


def test_ensure_resuming_running_does_not_resume(fake_http):
    fake_http.status_value = "running"
    coord = ResumeCoordinator(AuraClient(_cfg()))
    assert coord.ensure_resuming() == "running"
    assert fake_http.resume_post_count == 0


def test_ensure_resuming_paused_fires_resume_once(fake_http):
    fake_http.status_value = "paused"
    coord = ResumeCoordinator(AuraClient(_cfg()))
    assert coord.ensure_resuming() == "resuming"
    assert fake_http.resume_post_count == 1


def test_resume_post_sends_json_content_type(fake_http):
    """The live Aura API rejects the resume POST with 415 unless it carries a JSON
    content-type (proven against the real instance 8a37bbaf). requests sets
    ``Content-Type: application/json`` when ``json=`` is passed — so the resume
    call MUST pass json, not a bare body-less POST. Guards that 415 regression."""
    AuraClient(_cfg()).resume()
    resume_calls = [c for c in fake_http.post_calls if c["url"].endswith("/resume")]
    assert len(resume_calls) == 1
    assert resume_calls[0]["json"] is not None, (
        "resume() must POST with json= so Content-Type is application/json (else Aura 415)"
    )


def test_ensure_resuming_single_resume_under_concurrency(fake_http):
    """GUARANTEE: at most ONE POST /resume per wake cycle under N threads."""
    fake_http.status_value = "paused"
    fake_http.status_delay = 0.02  # force real overlap in the status check
    coord = ResumeCoordinator(AuraClient(_cfg()))

    results: list[str] = []
    results_lock = threading.Lock()

    def worker():
        r = coord.ensure_resuming()
        with results_lock:
            results.append(r)

    threads = [threading.Thread(target=worker) for _ in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == 16
    assert all(r == "resuming" for r in results)
    # The lock + cooldown guarantee exactly one resume POST for the whole burst.
    assert fake_http.resume_post_count == 1


def test_cooldown_prevents_second_resume_without_api_call(fake_http):
    fake_http.status_value = "paused"
    coord = ResumeCoordinator(AuraClient(_cfg()), cooldown=1000.0)
    assert coord.ensure_resuming() == "resuming"
    getcount_after_first = len(fake_http.get_calls)
    # second call is inside the cooldown → returns 'resuming' with NO further API hit
    assert coord.ensure_resuming() == "resuming"
    assert fake_http.resume_post_count == 1
    assert len(fake_http.get_calls) == getcount_after_first  # no extra status GET


def test_network_error_in_status_returns_unknown(fake_http):
    fake_http.status_error = ar.requests.ConnectionError("dns down")
    coord = ResumeCoordinator(AuraClient(_cfg()))
    assert coord.ensure_resuming() == "unknown"  # never raises
    assert fake_http.resume_post_count == 0


def test_network_error_in_resume_returns_unknown(fake_http):
    fake_http.status_value = "paused"
    fake_http.resume_error = ar.requests.ConnectionError("resume timeout")
    coord = ResumeCoordinator(AuraClient(_cfg()))
    assert coord.ensure_resuming() == "unknown"  # never raises


# ── build_coordinator / disabled path ─────────────────────────────────────────


def test_build_coordinator_none_when_disabled(monkeypatch):
    monkeypatch.delenv("AURA_CLIENT_ID", raising=False)
    monkeypatch.delenv("AURA_CLIENT_SECRET", raising=False)
    assert build_coordinator() is None


def test_build_coordinator_enabled(monkeypatch):
    monkeypatch.setenv("AURA_CLIENT_ID", "cid")
    monkeypatch.setenv("AURA_CLIENT_SECRET", "csecret")
    monkeypatch.setenv("AURA_INSTANCE_ID", "8a37bbaf")
    coord = build_coordinator()
    assert isinstance(coord, ResumeCoordinator)


# ── API wiring: ServiceUnavailable handler + disabled getter ──────────────────


def test_service_unavailable_handler_returns_503_retry_after(monkeypatch):
    """A route that raises ServiceUnavailable → clean 503 + Retry-After + aura
    status, with a fake coordinator injected (no live Aura)."""
    from fastapi.testclient import TestClient
    from neo4j.exceptions import ServiceUnavailable

    import src.api.dependencies as dep
    from src.api.app import create_app

    class _FakeCoordinator:
        def ensure_resuming(self):
            return "resuming"

    monkeypatch.setattr(dep, "get_resume_coordinator", lambda: _FakeCoordinator())
    # app.py imported the name at module load — patch it there too.
    import src.api.app as app_module

    monkeypatch.setattr(app_module, "get_resume_coordinator", lambda: _FakeCoordinator())

    monkeypatch.setenv("NEO4J_URI", "neo4j+s://deadbeef.databases.neo4j.io:7687")
    monkeypatch.setenv("NEO4J_USER", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "x")

    app = create_app()

    @app.get("/api/v1/_boom")
    async def _boom():
        raise ServiceUnavailable("db gone")

    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get("/api/v1/_boom")

    assert resp.status_code == 503, resp.text
    assert resp.headers["Retry-After"] == "30"
    body = resp.json()
    assert body["detail"] == "Database is waking up, retry shortly"
    assert body["aura"] == "resuming"


def test_service_unavailable_handler_clean_503_when_aura_disabled(monkeypatch):
    """Aura disabled → handler still returns a clean 503 (not a raw 500)."""
    from fastapi.testclient import TestClient
    from neo4j.exceptions import ServiceUnavailable

    import src.api.app as app_module
    import src.api.dependencies as dep
    from src.api.app import create_app

    monkeypatch.setattr(dep, "get_resume_coordinator", lambda: None)
    monkeypatch.setattr(app_module, "get_resume_coordinator", lambda: None)

    monkeypatch.setenv("NEO4J_URI", "neo4j+s://deadbeef.databases.neo4j.io:7687")
    monkeypatch.setenv("NEO4J_USER", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "x")

    app = create_app()

    @app.get("/api/v1/_boom")
    async def _boom():
        raise ServiceUnavailable("db gone")

    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get("/api/v1/_boom")

    assert resp.status_code == 503, resp.text
    assert resp.headers["Retry-After"] == "30"
    assert resp.json()["aura"] == "disabled"


def test_get_resume_coordinator_none_when_creds_unset(monkeypatch):
    """Disabled path: with creds unset, the getter is None and healthz is
    unchanged (no 'aura' key), matching the existing test_api_startup contract."""
    from fastapi.testclient import TestClient

    from src.api.app import create_app
    from src.aura_resume import reset_coordinator

    monkeypatch.delenv("AURA_CLIENT_ID", raising=False)
    monkeypatch.delenv("AURA_CLIENT_SECRET", raising=False)
    reset_coordinator()

    monkeypatch.setenv("NEO4J_URI", "neo4j+s://deadbeef.databases.neo4j.io:7687")
    monkeypatch.setenv("NEO4J_USER", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "x")

    from src.api.dependencies import get_resume_coordinator

    assert get_resume_coordinator() is None

    with TestClient(create_app()) as client:
        resp = client.get("/api/v1/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["neo4j_connected"] is False
    assert body["status"] == "degraded"
    assert "aura" not in body  # disabled → body is exactly the pre-existing shape
    reset_coordinator()
