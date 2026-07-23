"""Safe access to the populated local dev graph from pytest shards.

Pytest's destructive fixtures use ``NEO4J_*`` and are hard-pinned to port
7688.  Live-corpus tests use this separate prefix and can only open localhost
port 7687, so neither environment can silently fall through to Aura.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse

from neo4j import GraphDatabase
from neo4j.exceptions import AuthError, ServiceUnavailable


def dev_graph_environment() -> dict[str, str]:
    return {
        "NEO4J_URI": os.getenv("ONDOWAY_DEV_NEO4J_URI", ""),
        "NEO4J_USER": os.getenv("ONDOWAY_DEV_NEO4J_USER", ""),
        "NEO4J_PASSWORD": os.getenv("ONDOWAY_DEV_NEO4J_PASSWORD", ""),
        "NEO4J_DATABASE": os.getenv("ONDOWAY_DEV_NEO4J_DATABASE", "neo4j"),
    }


def open_dev_driver():
    """Return a verified localhost:7687 driver, or ``None`` when unavailable."""
    env = dev_graph_environment()
    uri = env["NEO4J_URI"]
    parsed = urlparse(uri)
    if (
        parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
        or parsed.port != 7687
        or not env["NEO4J_USER"]
        or not env["NEO4J_PASSWORD"]
        or env["NEO4J_DATABASE"] != "neo4j"
    ):
        return None
    try:
        driver = GraphDatabase.driver(
            uri,
            auth=(env["NEO4J_USER"], env["NEO4J_PASSWORD"]),
        )
        driver.verify_connectivity()
        return driver
    except (ServiceUnavailable, AuthError, Exception):
        return None
