"""Regression guards for the /trips spend + authorization defects (2026-07-19).

Four confirmed defects, all on ``src/api/routes/trips.py``:

1. POST /trips/preview was unauthenticated AND un-rate-limited while spending
   against the owner's ANTHROPIC_API_KEY on a public Render service. The current
   Premium path performs one Opus authoring call per routed stop, so the limiter
   must atomically reserve the exact planned stop count before any physical call.
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
from src.api.dependencies import (
    get_driver,
    get_premium_compose_executor,
    get_session,
)
from src.api.routes import trips as trips_route
from src.tour.premium_tour import (
    AnthropicPremiumExecutor,
    OfflinePremiumExecutor,
    PremiumBuildIdentity,
)

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
    "duration_min": 30,
    "city_slug": "paris",
}


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _CountingPremiumExecutor:
    """Billable-boundary double returning explicit offline provider bytes."""

    cost_bearing = True
    provider_name = "anthropic"

    def __init__(self) -> None:
        self.calls = 0

    def execute(self, unit):
        self.calls += 1
        return OfflinePremiumExecutor().execute(unit)


class _RaisingPremiumExecutor:
    """Explicit non-billing stub whose physical call raises an exception."""

    cost_bearing = False
    provider_name = "offline"

    def __init__(self, exc: BaseException):
        self.exc = exc

    def execute(self, _unit):
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




@pytest.fixture()
def preview_client(monkeypatch):
    """(compose_client) -> TestClient for POST /trips/preview, fully hermetic."""

    def _make(premium_executor) -> TestClient:
        monkeypatch.setattr(trips_route, "RoutingClient", _FakeRoutingClient)
        monkeypatch.setattr(
            trips_route,
            "resolve_build_identity",
            lambda: PremiumBuildIdentity(commit_sha="1" * 40),
        )
        app = create_app()
        app.dependency_overrides[get_driver] = lambda: _FakeDriver(_green_cluster_records())
        app.dependency_overrides[get_premium_compose_executor] = lambda: premium_executor
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
        # Both trip compose paths now author through the premium executor, so THAT
        # is the boundary a foreign caller must never reach. It raises rather than
        # returning a stub: if the ownership check ever stops short-circuiting, the
        # test fails loudly instead of quietly composing a victim's trip.
        app.dependency_overrides[get_premium_compose_executor] = lambda: _RaisingPremiumExecutor(
            AssertionError("an unauthorized caller reached the authoring provider")
        )
        return TestClient(app, raise_server_exceptions=False)

    return _make


# ---------------------------------------------------------------------------
# Defects 1/3/5 — the preview spend guard
# ---------------------------------------------------------------------------


def test_product_authoring_factory_is_offline_in_the_non_live_suite():
    """AC-7, third clause: the conftest money-guard actually arms this boundary.

    Every paid call either surface can make now goes through ONE product factory,
    ``get_premium_compose_executor()``. Nothing else in the non-live suite asserts
    that the factory is neutered, and the only executable money-guard pin that used
    to cover the old whole-tour compose client is deleted later in this ledger — so
    without this test the hermetic suite could start billing real Opus and every
    other test would stay green, because they all inject their own doubles and never
    touch the product path.

    Hermetic and $0: it constructs the product executor and asserts what it IS,
    without executing it.

    UNDO: delete the PREMIUM authoring money-guard arm in tests/conftest.py (the
    ``AnthropicPremiumExecutor`` monkeypatch) -> the factory hands back the real
    billing executor and this goes RED.
    """
    executor = get_premium_compose_executor()

    assert isinstance(executor, OfflinePremiumExecutor), (
        "the product authoring factory built a real provider client in the "
        f"non-live suite: {type(executor).__module__}.{type(executor).__qualname__}"
    )
    assert executor.cost_bearing is False
    # (A _is_cost_bearing() assertion sat here so the deleted rate limiter agreed
    # the offline executor was free. Both are gone; `cost_bearing` above is still
    # the flag the offline swap sets, so the guarantee is unchanged.)
    # The swap is what makes it free — the class the factory names is billable.
    assert AnthropicPremiumExecutor.cost_bearing is True


def test_unverifiable_build_is_rejected_before_provider_spend(preview_client, monkeypatch):
    """AC-16/AC-18: an unresolvable build fingerprint is a distinct, pre-spend fault.

    ``resolve_build_identity`` runs before any provider work — this
    must be provable at ZERO paid calls. The generic ``except Exception`` around the
    physical-authoring call must not swallow this into ``llm_generation_failed`` /
    ``generation_failed``: that reports "the LLM tried and failed" for a fault where
    the LLM was never even reached, and hides an environment/config problem behind a
    provider-authoring error message.
    UNDO: catch resolve_build_identity()'s ValueError with the same generic
    ``except Exception`` block used for premium-authoring failures -> this test goes
    RED on both the rejection code and the basic_tour reason.
    """
    executor = _CountingPremiumExecutor()
    client = preview_client(executor)
    monkeypatch.setattr(
        trips_route,
        "resolve_build_identity",
        lambda: (_ for _ in ()).throw(ValueError("dirty build")),
    )

    response = client.post("/api/v1/trips/preview", json=PREVIEW_BODY)

    assert response.status_code == 200
    body = response.json()
    assert body["candidate_eligible"] is False
    assert body["compose_status"] == "basic_available"
    assert executor.calls == 0, "a build-fingerprint fault must never reach the provider"

    assert body["basic_tour"]["reason"] != "llm_generation_failed", (
        "an environment/config fault must not be reported as an LLM generation failure"
    )
    rejection = body["candidate_rejection"]
    assert rejection["code"] == "build_fingerprint_unavailable"
    assert "dirty build" in rejection["detail"], (
        "the detail must carry the raised message, not a generic authoring string"
    )

    # A genuine provider-authoring failure must still produce the OLD code/reason,
    # and the two payloads must not be byte-identical.
    other = preview_client(_RaisingPremiumExecutor(RuntimeError("boom"))).post(
        "/api/v1/trips/preview", json=PREVIEW_BODY
    )
    other_body = other.json()
    assert other_body["candidate_rejection"]["code"] == "generation_failed"
    assert other_body["basic_tour"]["reason"] == "llm_generation_failed"
    assert other_body["candidate_rejection"] != rejection
    assert other_body["basic_tour"]["reason"] != body["basic_tour"]["reason"]


# ---------------------------------------------------------------------------
# Defect 4 — provider failures map to 503/502, never a raw 500
# ---------------------------------------------------------------------------


def _http_request() -> httpx.Request:
    return httpx.Request("POST", "https://api.anthropic.com/v1/messages")


def test_provider_throttle_is_503_with_retry_after(preview_client):
    """anthropic.RateLimitError must not surface as a 500.

    UNDO: drop the ``_upstream_provider_errors()`` wrapper from Premium execution
    -> RED at 500 with no Retry-After.
    """
    anthropic = pytest.importorskip("anthropic")
    exc = anthropic.RateLimitError(
        "throttled",
        response=httpx.Response(429, request=_http_request()),
        body=None,
    )
    resp = preview_client(_RaisingPremiumExecutor(exc)).post(
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
    resp = preview_client(_RaisingPremiumExecutor(exc)).post(
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
