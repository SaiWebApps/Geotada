"""Shared test fixtures for Neo4j integration tests.

Tests that need a live Neo4j mark themselves with @pytest.mark.integration.
If Neo4j is unreachable, integration tests are skipped automatically.

Tests connect to a dedicated test Neo4j instance (bolt://localhost:7688)
so that production data in the dev instance is never touched.
Start it with: make db-test-up
"""

from __future__ import annotations

from pathlib import Path

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
    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")
