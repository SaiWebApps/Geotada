"""Neo4j connection management.

Provides a context-managed driver factory that reads credentials
from environment variables and fails loudly with human-readable errors.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from typing import TYPE_CHECKING

from dotenv import load_dotenv
from neo4j import GraphDatabase
from neo4j.exceptions import AuthError, ServiceUnavailable

if TYPE_CHECKING:
    from collections.abc import Generator

    from neo4j import Driver

load_dotenv()


class ConnectionError(RuntimeError):
    """Raised when Neo4j is unreachable or credentials are wrong."""


def _read_env() -> tuple[str, str, str]:
    """Return (uri, user, password) from environment, or die trying."""
    import os

    uri = os.getenv("NEO4J_URI", "")
    user = os.getenv("NEO4J_USER", "")
    password = os.getenv("NEO4J_PASSWORD", "")

    missing = [
        k
        for k, v in [("NEO4J_URI", uri), ("NEO4J_USER", user), ("NEO4J_PASSWORD", password)]
        if not v
    ]
    if missing:
        raise ConnectionError(
            f"Missing environment variables: {', '.join(missing)}. "
            "Copy .env.example to .env and fill in your credentials."
        )
    return uri, user, password


def create_driver() -> Driver:
    """Create and verify a Neo4j driver. Raises ConnectionError on failure."""
    uri, user, password = _read_env()
    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        driver.verify_connectivity()
        return driver
    except ServiceUnavailable as exc:
        raise ConnectionError(
            f"Cannot reach Neo4j at {uri}. Is the server running?\n"
            "  Start it with: make db-up\n"
            f"  Original error: {exc}"
        ) from exc
    except AuthError as exc:
        raise ConnectionError(
            f"Authentication failed for user '{user}' at {uri}.\n"
            "  Check NEO4J_USER and NEO4J_PASSWORD in your .env file.\n"
            f"  Original error: {exc}"
        ) from exc


@contextmanager
def get_driver() -> Generator[Driver]:
    """Context manager that yields a verified Neo4j driver and cleans up."""
    driver = create_driver()
    try:
        yield driver
    finally:
        driver.close()


def abort_on_connection_error(func):
    """Decorator for CLI entry points — converts ConnectionError to sys.exit(1)."""

    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ConnectionError as exc:
            print(f"\n✗ CONNECTION FAILED\n  {exc}", file=sys.stderr)
            sys.exit(1)

    return wrapper
