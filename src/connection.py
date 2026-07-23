"""Neo4j connection management.

Provides a context-managed driver factory that reads credentials
from environment variables and fails loudly with human-readable errors.
"""

from __future__ import annotations

import functools
import sys
from contextlib import contextmanager
from typing import TYPE_CHECKING

from neo4j import GraphDatabase
from neo4j.exceptions import AuthError, ServiceUnavailable

if TYPE_CHECKING:
    from collections.abc import Generator

    from neo4j import Driver


class Neo4jConnectionError(RuntimeError):
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
        raise Neo4jConnectionError(
            f"Missing environment variables: {', '.join(missing)}. "
            "Run the command through its Make target so the validated profile is injected."
        )
    return uri, user, password


def get_database() -> str | None:
    """Return the configured database name, or None for server default."""
    import os

    return os.getenv("NEO4J_DATABASE") or None


def create_driver(*, verify: bool = True) -> Driver:
    """Create a Neo4j driver, optionally verifying connectivity.

    ``verify=True`` (default, for CLI/scripts) eagerly checks the connection and
    raises Neo4jConnectionError on failure — fail loud, fail fast.

    ``verify=False`` returns the LAZY driver without touching the network. A
    long-lived web service must start even when the database is briefly
    unreachable (a paused Aura instance, DNS blip, or transient outage): the
    neo4j driver connects on first query, so DB errors become a per-request
    concern (handled/surfaced there) instead of a startup crash that fails the
    whole deploy. See src/api/dependencies.init_driver.
    """
    uri, user, password = _read_env()
    if not verify:
        return GraphDatabase.driver(uri, auth=(user, password))
    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        driver.verify_connectivity()
        return driver
    except ServiceUnavailable as exc:
        raise Neo4jConnectionError(
            f"Cannot reach Neo4j at {uri}. Is the server running?\n"
            "  Start it with: make db-up\n"
            f"  Original error: {exc}"
        ) from exc
    except AuthError as exc:
        raise Neo4jConnectionError(
            f"Authentication failed for user '{user}' at {uri}.\n"
            "  Run `make config-status` and retry through the owning Make target.\n"
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
    """Decorator for CLI entry points — converts Neo4jConnectionError to sys.exit(1)."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Neo4jConnectionError as exc:
            print(f"\n✗ CONNECTION FAILED\n  {exc}", file=sys.stderr)
            sys.exit(1)

    return wrapper
