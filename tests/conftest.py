"""Shared test fixtures for Neo4j integration tests.

Tests that need a live Neo4j mark themselves with @pytest.mark.integration.
If Neo4j is unreachable, integration tests are skipped automatically.

Tests connect to a dedicated test Neo4j instance (bolt://localhost:7688)
so that production data in the dev instance is never touched.
Start it with: make db-test-up

Phase 4.5 hardening (2026-04-29): _wipe() hard-asserts the connected URI's
port belongs to _TEST_PORT_ALLOWLIST before running DETACH DELETE. Stops a
recurrence of the Phase 4 incident where load_dotenv(override=True) inside
a test mutated NEO4J_URI to the dev port and the conftest fixture wiped
the production corpus. See data/paris/.pipeline-state.json →
backlog.conftest_test_isolation for context.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

# Load test-specific Neo4j connection BEFORE importing src.connection.
# connection.py calls load_dotenv() at import time without override=True,
# so these values will be preserved.
_test_env = Path(__file__).resolve().parent.parent / ".env.test"
if _test_env.exists():
    load_dotenv(dotenv_path=_test_env, override=True)
else:
    import pytest as _pytest

    _pytest.exit(
        f"FATAL: {_test_env} not found. "
        "Tests would fall back to production .env and could destroy data. "
        "Copy .env.test.example to .env.test first."
    )

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.connection import Neo4jConnectionError, create_driver, get_database
from src.schema.constraints import apply_all


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Project policy: a skipped test counts as a FAILURE — no silent non-runs.

    Any skip outcome is flipped to 'failed' (the original skip reason is shown
    as the failure detail). Explicit xfail is preserved, since that is an
    asserted expected-failure, not a silent skip.
    """
    outcome = yield
    report = outcome.get_result()
    if report.skipped and not getattr(report, "wasxfail", False):
        report.outcome = "failed"


# Ports the conftest is allowed to wipe. Update this if your local test
# instance runs on a different port. Dev/production must NEVER be in here.
_TEST_PORT_ALLOWLIST: set[int] = {7688}


def _assert_test_port() -> None:
    """Hard-block if NEO4J_URI is pointed at a non-test port.

    Read at call time (not at fixture instantiation) so a test that
    mutates os.environ between fixture creation and _wipe() can't slip
    a destructive Cypher past the guard.
    """
    uri = os.getenv("NEO4J_URI", "")
    parsed = urlparse(uri)
    port = parsed.port
    if port not in _TEST_PORT_ALLOWLIST:
        raise RuntimeError(
            f"Refusing to _wipe() against non-test Neo4j. "
            f"NEO4J_URI={uri!r} (port={port}). "
            f"Test database must run on port {sorted(_TEST_PORT_ALLOWLIST)}. "
            f"If your local test instance uses a different port, "
            f"update tests/conftest.py:_TEST_PORT_ALLOWLIST."
        )


def pytest_configure(config):
    """Refuse to run the whole suite against any non-test database.

    Many fixtures across the suite issue ``MATCH (n) DETACH DELETE n`` via their
    own ``create_driver()``, bypassing ``_wipe()``'s per-call guard. Rather than
    guard each one, we hard-stop the entire run when ``NEO4J_URI`` is not an
    allowlisted test port. The cloud (Aura) database is the single persistent
    store and must NEVER be wiped by tests — cloud connectivity is checked
    read-only via ``make test-cloud`` (which does not invoke pytest).
    """
    uri = os.getenv("NEO4J_URI", "")
    port = urlparse(uri).port
    if port not in _TEST_PORT_ALLOWLIST:
        pytest.exit(
            f"Refusing to run the test suite against NEO4J_URI={uri!r} (port={port}). "
            f"The suite contains destructive fixtures; it may only run against the test "
            f"database on port {sorted(_TEST_PORT_ALLOWLIST)}. The cloud DB is the single "
            f"persistent store and is never wiped by tests — use the read-only "
            f"`make test-cloud` smoke for a cloud check."
        )


def _neo4j_available() -> bool:
    try:
        driver = create_driver()
        driver.close()
        return True
    except (Neo4jConnectionError, Exception):
        return False


needs_neo4j = pytest.mark.skipif(
    not _neo4j_available(),
    reason="Neo4j not available — start it with `make db-up`",
)


@pytest.fixture(scope="session")
def driver():
    """Session-scoped Neo4j driver. Wipes DB before and after all tests."""
    d = create_driver()
    _wipe(d)
    yield d
    _wipe(d)
    d.close()


def _wipe(driver) -> None:
    """DETACH DELETE every node, but ONLY against an allowlisted test port.

    The port assertion runs every call so env mutation between fixture
    creation and wipe (the Phase 4 incident vector) cannot bypass it.
    """
    _assert_test_port()
    with driver.session(database=get_database()) as session:
        session.run("MATCH (n) DETACH DELETE n")


@pytest.fixture(scope="module")
def clean_driver():
    """Create a driver with a clean DB + schema constraints."""
    _assert_test_port()
    d = create_driver()
    with d.session(database=get_database()) as s:
        s.run("MATCH (n) DETACH DELETE n")
    apply_all(d)
    yield d
    d.close()


@pytest.fixture(scope="module")
def client(clean_driver):
    """TestClient backed by a clean Neo4j database (no seed data)."""
    app = create_app()
    with TestClient(app) as c:
        yield c
