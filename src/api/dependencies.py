"""FastAPI dependency injection for Neo4j sessions."""

from __future__ import annotations

from collections.abc import Generator
from typing import TYPE_CHECKING

from src.connection import create_driver, get_database

if TYPE_CHECKING:
    from neo4j import Driver, Session

_driver: Driver | None = None


def init_driver() -> None:
    """Called during FastAPI lifespan startup."""
    global _driver
    _driver = create_driver()


def close_driver() -> None:
    """Called during FastAPI lifespan shutdown."""
    global _driver
    if _driver:
        _driver.close()
        _driver = None


def get_session() -> Generator[Session]:
    """Yield a Neo4j session for the duration of one request."""
    assert _driver is not None, "Driver not initialized — is the app running?"
    session = _driver.session(database=get_database())
    try:
        yield session
    finally:
        session.close()


def get_driver() -> Driver:
    """Return the process-wide driver (the tour engine's corpus loader opens
    its own sessions, so it needs the driver rather than a request session)."""
    assert _driver is not None, "Driver not initialized — is the app running?"
    return _driver
