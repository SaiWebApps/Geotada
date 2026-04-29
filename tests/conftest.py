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
    with driver.session(database=get_database()) as session:
        session.run("MATCH (n) DETACH DELETE n")


@pytest.fixture(scope="module")
def clean_driver():
    """Create a driver with a clean DB + schema constraints."""
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
