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
    import warnings

    warnings.warn(
        f"Test env file not found: {_test_env}. "
        "Tests will use production .env! Copy .env.test.example to .env.test.",
        stacklevel=1,
    )

import pytest

from src.connection import ConnectionError, create_driver

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


def _neo4j_available() -> bool:
    try:
        driver = create_driver()
        driver.close()
        return True
    except (ConnectionError, Exception):
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
    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")
