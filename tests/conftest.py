"""Shared test fixtures for Neo4j integration tests.

Tests that need a live Neo4j mark themselves with @pytest.mark.integration.
If Neo4j is unreachable, integration tests are skipped automatically.
"""

from __future__ import annotations

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
