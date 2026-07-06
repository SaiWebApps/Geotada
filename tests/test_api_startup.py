"""API startup resilience — the Render deploy fix.

Regression guard for the 2026-07 outage: the app EAGERLY verified the Neo4j
connection during FastAPI lifespan startup (`init_driver` -> `create_driver()`),
so when the Aura instance became unreachable (DNS `Cannot resolve address ...`)
the whole process crashed on startup, never opened its port, and every Render
deploy failed its health check -> daily "deploy failed" emails.

The app must START even when the database is unreachable: build the driver
lazily, and let DB errors surface per-request. `/api/v1/healthz` then returns
200 with ``neo4j_connected: false`` so the deploy stays green while the outage
is visible.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.app import create_app

_DEAD_AURA_URI = "neo4j+s://deadbeef-nonexistent-ondoway.databases.neo4j.io:7687"


def test_app_starts_and_healthz_degraded_when_db_unreachable(monkeypatch):
    """Constructing TestClient runs the lifespan (init_driver). With an
    unreachable DB it must NOT raise, and /api/v1/healthz must return 200."""
    monkeypatch.setenv("NEO4J_URI", _DEAD_AURA_URI)
    monkeypatch.setenv("NEO4J_USER", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "wrong-or-gone")

    # If startup weren't lazy, TestClient(create_app()) would raise here.
    with TestClient(create_app()) as client:
        resp = client.get("/api/v1/healthz")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["neo4j_connected"] is False, "an unreachable DB must report not-connected"
    assert body["status"] == "degraded"


def test_init_driver_never_crashes_startup(monkeypatch):
    """init_driver swallows any driver-construction failure so the port still opens."""
    import src.api.dependencies as dep

    monkeypatch.setenv("NEO4J_URI", _DEAD_AURA_URI)
    monkeypatch.setenv("NEO4J_USER", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "x")
    try:
        dep.init_driver()  # must not raise / SystemExit
        assert dep._driver is not None  # lazy driver was built
    finally:
        dep.close_driver()
