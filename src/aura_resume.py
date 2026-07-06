"""Automatic resume of a PAUSED Neo4j AuraDB instance.

Free/low-tier Aura instances auto-pause after inactivity. A cold Render deploy
(or the first request after a pause) then hits a database that is ``paused`` and
must be woken via the Aura Console API before it can serve queries. Waking is
ASYNC (paused -> resuming -> running takes tens of seconds to minutes), so this
module NEVER blocks a request waiting for ``running``: it fires the resume and
lets the caller return a fast 503 (with ``Retry-After``) while the wake proceeds.

The whole feature is a safe NO-OP when ``AURA_CLIENT_ID`` / ``AURA_CLIENT_SECRET``
are unset (local dev + CI), so nothing here can crash a request or startup.

Confirmed Aura API (v1):
- Token:  ``POST https://api.neo4j.io/oauth/token`` — ``Authorization: Basic
  base64(client_id:client_secret)``, body ``grant_type=client_credentials``.
  Response ``{access_token, token_type, expires_in}`` (~3600s).
- Status: ``GET https://api.neo4j.io/v1/instances/{id}`` -> ``{"data":{...,
  "status": creating|running|pausing|paused|resuming|destroying|loading}}``.
- Resume: ``POST https://api.neo4j.io/v1/instances/{id}/resume`` (no body) ->
  200/202 = initiated (async).
"""

from __future__ import annotations

import base64
import logging
import os
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import requests

logger = logging.getLogger("ondoway.aura")

_API_BASE = "https://api.neo4j.io"
_TOKEN_URL = f"{_API_BASE}/oauth/token"
_HTTP_TIMEOUT = 10.0
# Refresh the OAuth token a minute before it actually expires so an in-flight
# request never races a mid-call expiry.
_TOKEN_EXPIRY_SLACK = 60.0
# At most one POST /resume per this window across the whole process — a single
# wake takes far longer than this, so re-checking status every 30s is plenty
# while guaranteeing we never spam the Aura API under a burst of 503s.
_RESUME_COOLDOWN = 30.0


class AuraResumeError(RuntimeError):
    """Raised inside AuraClient when an Aura API call fails (4xx/5xx/network).

    ResumeCoordinator swallows this so it never escapes into the request path.
    """


@dataclass(frozen=True)
class AuraConfig:
    """Credentials + target instance for the Aura Console API."""

    client_id: str
    client_secret: str
    instance_id: str

    @classmethod
    def from_env(cls) -> AuraConfig | None:
        """Build config from the environment, or ``None`` if the feature is off.

        Disabled (returns ``None``) when either credential is unset. The instance
        id is ``AURA_INSTANCE_ID`` if set, else derived from the ``NEO4J_URI`` host
        (``neo4j+s://8a37bbaf.databases.neo4j.io`` -> ``8a37bbaf``). If no instance
        id can be determined, the feature is likewise disabled.
        """
        client_id = os.getenv("AURA_CLIENT_ID", "").strip()
        client_secret = os.getenv("AURA_CLIENT_SECRET", "").strip()
        if not client_id or not client_secret:
            return None

        instance_id = os.getenv("AURA_INSTANCE_ID", "").strip()
        if not instance_id:
            host = urlparse(os.getenv("NEO4J_URI", "")).hostname or ""
            instance_id = host.split(".")[0] if host else ""
        if not instance_id:
            return None

        return cls(
            client_id=client_id,
            client_secret=client_secret,
            instance_id=instance_id,
        )


class AuraClient:
    """Thin, thread-safe HTTP client for the three Aura endpoints we need.

    Caches the OAuth bearer token in memory until shortly before it expires.
    Every method raises :class:`AuraResumeError` on any failure so the caller
    (:class:`ResumeCoordinator`) can uniformly swallow it.
    """

    def __init__(self, cfg: AuraConfig) -> None:
        self._cfg = cfg
        self._lock = threading.Lock()
        self._token: str | None = None
        self._token_expiry: float = 0.0

    def _token_value(self) -> str:
        """Return a valid bearer token, refreshing (POST oauth/token) if needed."""
        with self._lock:
            now = time.monotonic()
            if self._token is not None and now < self._token_expiry:
                return self._token

            basic = base64.b64encode(
                f"{self._cfg.client_id}:{self._cfg.client_secret}".encode()
            ).decode("ascii")
            try:
                resp = requests.post(
                    _TOKEN_URL,
                    headers={
                        "Authorization": f"Basic {basic}",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    data={"grant_type": "client_credentials"},
                    timeout=_HTTP_TIMEOUT,
                )
            except requests.RequestException as exc:
                raise AuraResumeError(f"Aura token request failed: {exc}") from exc

            if resp.status_code != 200:
                raise AuraResumeError(
                    f"Aura token request returned {resp.status_code}: {resp.text[:200]}"
                )
            try:
                payload = resp.json()
                token = payload["access_token"]
                expires_in = float(payload.get("expires_in", 3600))
            except (ValueError, KeyError, TypeError) as exc:
                raise AuraResumeError(f"Malformed Aura token response: {exc}") from exc

            self._token = token
            self._token_expiry = now + max(expires_in - _TOKEN_EXPIRY_SLACK, 0.0)
            return token

    def _auth_header(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token_value()}"}

    def get_status(self) -> str:
        """Return the instance ``status`` enum from GET /v1/instances/{id}."""
        url = f"{_API_BASE}/v1/instances/{self._cfg.instance_id}"
        try:
            resp = requests.get(url, headers=self._auth_header(), timeout=_HTTP_TIMEOUT)
        except requests.RequestException as exc:
            raise AuraResumeError(f"Aura status request failed: {exc}") from exc

        if resp.status_code != 200:
            raise AuraResumeError(
                f"Aura status returned {resp.status_code}: {resp.text[:200]}"
            )
        try:
            return resp.json()["data"]["status"]
        except (ValueError, KeyError, TypeError) as exc:
            raise AuraResumeError(f"Malformed Aura status response: {exc}") from exc

    def resume(self) -> None:
        """POST /v1/instances/{id}/resume — 200/202 = initiated (async).

        The Aura API rejects the request with 415 unless it carries a JSON
        content-type, even though the endpoint takes no body; ``json={}`` sets
        ``Content-Type: application/json`` with an empty object body.
        """
        url = f"{_API_BASE}/v1/instances/{self._cfg.instance_id}/resume"
        try:
            resp = requests.post(
                url, headers=self._auth_header(), json={}, timeout=_HTTP_TIMEOUT
            )
        except requests.RequestException as exc:
            raise AuraResumeError(f"Aura resume request failed: {exc}") from exc

        if resp.status_code not in (200, 202):
            raise AuraResumeError(
                f"Aura resume returned {resp.status_code}: {resp.text[:200]}"
            )


class ResumeCoordinator:
    """Process-wide, single-in-flight guard around a paused-instance wake.

    GUARANTEE: under any number of concurrent :meth:`ensure_resuming` calls, at
    most ONE ``POST /resume`` is issued per wake cycle. A ``threading.Lock``
    serialises the status-check-then-resume decision, and a last-attempt
    timestamp cooldown short-circuits subsequent calls for :data:`_RESUME_COOLDOWN`
    seconds (returning ``"resuming"`` without any API call). No Aura/network error
    ever escapes: on failure :meth:`ensure_resuming` logs and returns ``"unknown"``.
    """

    def __init__(self, client: AuraClient, cooldown: float = _RESUME_COOLDOWN) -> None:
        self._client = client
        self._cooldown = cooldown
        self._lock = threading.Lock()
        self._last_resume_at: float | None = None

    def ensure_resuming(self) -> str:
        """Wake a paused instance if needed; return the (coarse) current status.

        Never raises. Returns one of the Aura status strings, ``"resuming"`` when
        a resume was just fired (or is within the cooldown), or ``"unknown"`` if
        the Aura API could not be reached.
        """
        with self._lock:
            now = time.monotonic()
            if (
                self._last_resume_at is not None
                and now - self._last_resume_at < self._cooldown
            ):
                # A resume fired very recently — don't hit the API again.
                return "resuming"

            try:
                status = self._client.get_status()
            except AuraResumeError as exc:
                logger.warning("Aura status check failed: %s", exc)
                return "unknown"

            if status == "paused":
                try:
                    self._client.resume()
                except AuraResumeError as exc:
                    logger.warning("Aura resume failed: %s", exc)
                    return "unknown"
                self._last_resume_at = now
                logger.info(
                    "Aura instance was paused — resume initiated (async wake in progress)."
                )
                return "resuming"

            # running / resuming / loading / creating / pausing / destroying:
            # nothing to do — report it as-is.
            return status


def build_coordinator() -> ResumeCoordinator | None:
    """Construct a :class:`ResumeCoordinator` from the env, or ``None`` if disabled."""
    cfg = AuraConfig.from_env()
    if cfg is None:
        return None
    return ResumeCoordinator(AuraClient(cfg))


_coordinator: ResumeCoordinator | None = None
_coordinator_built = False
_coordinator_lock = threading.Lock()


def get_coordinator() -> ResumeCoordinator | None:
    """Return the process-wide singleton coordinator (built once, lazily).

    ``None`` means the feature is disabled (no creds). Reads the environment on
    first call only; tests that need a fresh read call :func:`reset_coordinator`.
    """
    global _coordinator, _coordinator_built
    if _coordinator_built:
        return _coordinator
    with _coordinator_lock:
        if not _coordinator_built:
            _coordinator = build_coordinator()
            _coordinator_built = True
    return _coordinator


def reset_coordinator() -> None:
    """Drop the cached singleton so the next :func:`get_coordinator` re-reads env.

    Used by tests and by :func:`src.api.dependencies.init_driver` so a redeploy
    with newly-set creds picks them up.
    """
    global _coordinator, _coordinator_built
    with _coordinator_lock:
        _coordinator = None
        _coordinator_built = False
