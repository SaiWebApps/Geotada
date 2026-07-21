"""Regression guards for the /trips spend + authorization defects (2026-07-19).

Four confirmed defects, all on ``src/api/routes/trips.py``:

1. POST /trips/preview was unauthenticated AND un-rate-limited while spending
   dollars of Opus/Haiku per call (best-of-2 compose per stop + the Opus
   correction ladder + Haiku judges), against the owner's ANTHROPIC_API_KEY on a
   public Render service. An anonymous loop drained the balance at ~$1/request.
   /feedback already had exactly this guard over ONE Haiku call.
2. GET /trips and POST /trips/{id}/compose had NO authentication — a classic
   IDOR: any profile's trips were readable, and /compose destroyed a victim's
   stop ids and one-shot compose budget, by guessing a profile_id / trip_id.
3. (same endpoint as 1, reported twice) the burst hole: N simultaneous callers
   each starting a ~$1 compose while the fixed-window counter is still low.
4. Anthropic provider failures (429/529/timeout) escaped the compose routes as
   raw HTTP 500s with no Retry-After, so clients could not distinguish a
   transient upstream throttle from a server bug or back off correctly.

Everything here is hermetic and $0: the compose SDK is a counting fake that
never reaches the network, and the assertions are on the fake's call count, so
the tests prove NO SPEND happened rather than merely observing a status code.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.auth.tokens import create_access_token
from src.api.dependencies import get_compose_client, get_driver, get_session
from src.api.routes import trips as trips_route
from src.tour.compose import COMPOSE_MODEL, AnthropicComposeClient

# Reuse the proven hermetic corpus fakes rather than re-deriving them.
from tests.test_trip_preview_contract import (
    START,
    _FakeDriver,
    _FakeRoutingClient,
    _green_cluster_records,
)

PREVIEW_BODY = {
    "center_lat": START[0],
    "center_lng": START[1],
    "duration_min": 60,
    "city_slug": "paris",
}


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _SpendError(RuntimeError):
    """Raised by the fake SDK. Reaching it at all means money WOULD have moved."""


class _CountingSDK:
    """Stands in for the Anthropic SDK inside a REAL AnthropicComposeClient.

    Using the real client class matters: the spend guard arms itself on the
    cost-bearing client types, so a plain stub would (correctly) not be limited.
    """

    def __init__(self) -> None:
        self.calls = 0
        self.messages = self

    def stream(self, **kwargs):
        # AnthropicComposeClient.compose() opens `self._client.messages.stream(...)`
        # as a context manager — counting HERE is counting the billable request.
        self.calls += 1
        return self

    def __enter__(self):
        raise _SpendError("a paid compose call was made")

    def __exit__(self, *exc):
        return False


class _RaisingComposeClient:
    """Non-billing stub whose compose() raises a given provider exception."""

    def __init__(self, exc: BaseException):
        self.exc = exc

    def compose(self, request, attempt, prev_report):
        raise self.exc


class _FakeAuthSession:
    """Neo4j session double for the auth/ownership Cypher only.

    ``owns`` False makes the ownership MATCH miss, which is the foreign-profile /
    foreign-trip case the IDOR fix must turn into a 404.
    """

    def __init__(self, user_id: str, *, owns: bool):
        self.user_id = user_id
        self.owns = owns

    def run(self, query: str, **params):
        if "HAS_PROFILE" in query or "IS_CAPTAIN_OF" in query:
            return _Single({"id": params.get("pid") or params.get("tid")} if self.owns else None)
        if "MATCH (u:User" in query:
            return _Single(
                {"u": {"id": self.user_id, "email": "a@example.com", "created_at": None}}
            )
        raise AssertionError(f"unexpected query in the auth path:\n{query}")

    def close(self) -> None:
        return None


class _Single:
    def __init__(self, record):
        self._record = record

    def single(self):
        return self._record


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_spend_guard():
    """The guard's counters are module-global; never let them leak between tests."""
    trips_route.reset_spend_guard()
    yield
    trips_route.reset_spend_guard()


@pytest.fixture()
def preview_client(monkeypatch):
    """(compose_client) -> TestClient for POST /trips/preview, fully hermetic."""

    def _make(compose_client) -> TestClient:
        monkeypatch.setattr(trips_route, "RoutingClient", _FakeRoutingClient)
        app = create_app()
        app.dependency_overrides[get_driver] = lambda: _FakeDriver(_green_cluster_records())
        app.dependency_overrides[get_compose_client] = lambda: compose_client
        # raise_server_exceptions=False so an unmapped 500 is observable as a
        # status code — that is exactly what defect 4 is about.
        return TestClient(app, raise_server_exceptions=False)

    return _make


@pytest.fixture()
def auth_client():
    """(user_id, owns) -> TestClient whose session double answers the auth Cypher."""

    def _make(user_id: str, *, owns: bool) -> TestClient:
        app = create_app()
        app.dependency_overrides[get_session] = lambda: _FakeAuthSession(user_id, owns=owns)
        app.dependency_overrides[get_driver] = lambda: _FakeDriver(_green_cluster_records())
        app.dependency_overrides[get_compose_client] = lambda: _RaisingComposeClient(
            AssertionError("compose must never run for an unauthorized caller")
        )
        return TestClient(app, raise_server_exceptions=False)

    return _make


# ---------------------------------------------------------------------------
# Defects 1/3/5 — the preview spend guard
# ---------------------------------------------------------------------------


def test_anonymous_preview_burst_is_429_before_a_second_compose_is_ever_billed(
    preview_client, monkeypatch
):
    """An anonymous loop must be refused BEFORE the provider is touched again.

    UNDO: delete the ``_spend_precheck(request, compose_client)`` call at the top
    of preview_trip -> the second POST composes again and this goes RED on both
    the status code AND the call count.
    """
    monkeypatch.setattr(trips_route, "_PREVIEW_RATE_LIMIT_MAX", 1)
    sdk = _CountingSDK()
    client = preview_client(AnthropicComposeClient(COMPOSE_MODEL, client=sdk))

    first = client.post("/api/v1/trips/preview", json=PREVIEW_BODY)
    assert first.status_code != 429, "the FIRST call must be allowed through"
    billed_once = sdk.calls
    assert billed_once > 0, "fixture never reached the compose path — the test is vacuous"

    second = client.post("/api/v1/trips/preview", json=PREVIEW_BODY)
    assert second.status_code == 429, "an over-limit anonymous preview must be refused"
    assert second.headers.get("Retry-After"), "a 429 must tell the client when to retry"
    assert sdk.calls == billed_once, (
        "the refused request still reached the provider — the guard is not "
        "preventing spend, only decorating the response"
    )


def test_spoofed_x_forwarded_for_cannot_win_a_fresh_rate_limit_bucket(
    preview_client, monkeypatch
):
    """X-Forwarded-For is client-controllable on the LEFT.

    Trusting the leftmost hop would land every request in a new bucket and fully
    defeat the limiter. Only the entry _TRUSTED_PROXY_HOPS from the RIGHT (what
    our own edge observed) may be trusted.
    UNDO: change ``idx = max(0, len(parts) - _TRUSTED_PROXY_HOPS)`` to ``0`` -> RED.
    """
    monkeypatch.setattr(trips_route, "_PREVIEW_RATE_LIMIT_MAX", 1)
    monkeypatch.setattr(trips_route, "_TRUSTED_PROXY_HOPS", 1)
    sdk = _CountingSDK()
    client = preview_client(AnthropicComposeClient(COMPOSE_MODEL, client=sdk))

    first = client.post(
        "/api/v1/trips/preview",
        json=PREVIEW_BODY,
        headers={"X-Forwarded-For": "1.1.1.1, 203.0.113.7"},
    )
    assert first.status_code != 429
    second = client.post(
        "/api/v1/trips/preview",
        json=PREVIEW_BODY,
        headers={"X-Forwarded-For": "2.2.2.2, 203.0.113.7"},
    )
    assert second.status_code == 429, "a spoofed leftmost hop bought a fresh bucket"


def test_global_cap_bounds_spend_even_under_ip_rotation(preview_client, monkeypatch):
    """Per-IP limits fall to IP rotation; the global cap is the load-bearing one.

    UNDO: remove the _global_hits block from _spend_precheck -> RED.
    """
    monkeypatch.setattr(trips_route, "_PREVIEW_RATE_LIMIT_MAX", 100)
    monkeypatch.setattr(trips_route, "_PREVIEW_GLOBAL_RATE_LIMIT_MAX", 1)
    sdk = _CountingSDK()
    client = preview_client(AnthropicComposeClient(COMPOSE_MODEL, client=sdk))

    client.post(
        "/api/v1/trips/preview", json=PREVIEW_BODY, headers={"X-Forwarded-For": "203.0.113.1"}
    )
    billed = sdk.calls
    rotated = client.post(
        "/api/v1/trips/preview", json=PREVIEW_BODY, headers={"X-Forwarded-For": "198.51.100.9"}
    )
    assert rotated.status_code == 429, "a rotated source IP bypassed the spend bound"
    assert sdk.calls == billed, "the rotated request still billed the provider"


def test_daily_ceiling_is_a_hard_spend_stop(preview_client, monkeypatch):
    """A rate is not a ceiling. The daily cap fails closed on total spend.

    UNDO: remove the _daily_hits block from _spend_precheck -> RED.
    """
    monkeypatch.setattr(trips_route, "_PREVIEW_RATE_LIMIT_MAX", 100)
    monkeypatch.setattr(trips_route, "_PREVIEW_GLOBAL_RATE_LIMIT_MAX", 100)
    monkeypatch.setattr(trips_route, "_PREVIEW_DAILY_MAX", 1)
    sdk = _CountingSDK()
    client = preview_client(AnthropicComposeClient(COMPOSE_MODEL, client=sdk))

    client.post("/api/v1/trips/preview", json=PREVIEW_BODY)
    billed = sdk.calls
    over = client.post("/api/v1/trips/preview", json=PREVIEW_BODY)
    assert over.status_code == 429
    assert sdk.calls == billed


def test_hermetic_suite_stubs_are_not_rate_limited(preview_client, monkeypatch):
    """The guard arms on the COST-BEARING client types only.

    This is why the bar's many previews still work without an env backdoor that
    could also disarm the guard on the public deploy: a stub spends nothing, so
    it is not limited. UNDO: make _spend_precheck limit every client -> RED.
    """
    monkeypatch.setattr(trips_route, "_PREVIEW_RATE_LIMIT_MAX", 1)
    client = preview_client(_RaisingComposeClient(_SpendError("stub")))
    for _ in range(4):
        assert client.post("/api/v1/trips/preview", json=PREVIEW_BODY).status_code != 429


# ---------------------------------------------------------------------------
# Defect 4 — provider failures map to 503/502, never a raw 500
# ---------------------------------------------------------------------------


def _http_request() -> httpx.Request:
    return httpx.Request("POST", "https://api.anthropic.com/v1/messages")


def test_provider_throttle_is_503_with_retry_after(preview_client):
    """anthropic.RateLimitError must not surface as a 500.

    UNDO: drop the ``_upstream_provider_errors()`` wrapper from the
    compose_script_per_chapter call -> RED at 500 with no Retry-After.
    """
    anthropic = pytest.importorskip("anthropic")
    exc = anthropic.RateLimitError(
        "throttled",
        response=httpx.Response(429, request=_http_request()),
        body=None,
    )
    resp = preview_client(_RaisingComposeClient(exc)).post(
        "/api/v1/trips/preview", json=PREVIEW_BODY
    )
    assert resp.status_code == 503, f"expected 503 for an upstream throttle, got {resp.status_code}"
    assert resp.headers.get("Retry-After") == "30"


def test_provider_timeout_is_502(preview_client):
    """anthropic.APITimeoutError (an APIError subclass) -> a clean 502.

    UNDO: drop the ``_upstream_provider_errors()`` wrapper -> RED at 500.
    """
    anthropic = pytest.importorskip("anthropic")
    exc = anthropic.APITimeoutError(request=_http_request())
    resp = preview_client(_RaisingComposeClient(exc)).post(
        "/api/v1/trips/preview", json=PREVIEW_BODY
    )
    assert resp.status_code == 502, f"expected 502 for a provider fault, got {resp.status_code}"


# ---------------------------------------------------------------------------
# Defect 2 — authentication + ownership on the user-facing trip surface
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("get", "/api/v1/trips?profile_id=victim-profile", None),
        (
            "post",
            "/api/v1/trips/victim-trip/compose",
            {"route_id": "victim-trip-opt1"},
        ),
        (
            "post",
            "/api/v1/trips/generate",
            {
                "profile_id": "victim-profile",
                "start_date": "2026-08-01",
                "end_date": "2026-08-01",
                "center_lat": START[0],
                "center_lng": START[1],
            },
        ),
    ],
)
def test_trip_routes_reject_an_unauthenticated_caller(auth_client, method, path, payload):
    """No bearer token -> no access to anyone's trips.

    UNDO: remove ``Depends(get_current_user)`` from the route -> RED (the call
    succeeds or fails on something other than authentication).
    """
    client = auth_client("attacker", owns=False)
    resp = getattr(client, method)(path, json=payload) if payload else getattr(client, method)(path)
    assert resp.status_code in (401, 403), (
        f"{method.upper()} {path} answered {resp.status_code} without a token — "
        "the endpoint is unauthenticated"
    )


def test_listing_another_profiles_trips_is_404_not_a_leak(auth_client):
    """Profile A's token must not read profile B's trips — and must not confirm
    that B exists (404, never 403).

    UNDO: revert the ownership MATCH to the existence-only
    ``MATCH (p:Profile {id: $pid})`` -> RED (the trips come back 200).
    """
    client = auth_client("user-a", owns=False)
    token = create_access_token("user-a", "a@example.com")
    resp = client.get(
        "/api/v1/trips?profile_id=victim-profile",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404, f"foreign profile leaked with {resp.status_code}"


def test_composing_another_users_trip_is_404_and_never_mutates(auth_client):
    """/compose replaces stops and burns the one-shot compose budget, so a
    foreign trip must be refused BEFORE any write or any compose call.

    UNDO: remove the IS_CAPTAIN_OF ownership MATCH from compose_trip -> RED (the
    request proceeds and the injected compose client's AssertionError fires).
    """
    client = auth_client("user-a", owns=False)
    token = create_access_token("user-a", "a@example.com")
    resp = client.post(
        "/api/v1/trips/victim-trip/compose",
        json={"route_id": "victim-trip-opt1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404, f"foreign trip was composable ({resp.status_code})"
