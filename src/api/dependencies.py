"""FastAPI dependency injection for Neo4j sessions."""

from __future__ import annotations

import os
from collections.abc import Generator
from typing import TYPE_CHECKING

from src.connection import create_driver, get_database
from src.tour.compose import ComposeClient, MockComposeClient

if TYPE_CHECKING:
    from neo4j import Driver, Session

    from src.tour.verify import FaithfulnessChecker

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


def _compose_provider() -> str:
    provider = os.getenv("COMPOSE_PROVIDER", "mock").strip().lower()
    if provider not in ("mock", "anthropic"):
        raise RuntimeError(
            f"Unknown COMPOSE_PROVIDER {provider!r} — use 'mock' or 'anthropic'"
        )
    return provider


def get_compose_client() -> ComposeClient:
    """The narration composer for POST /trips/{id}/compose (Phase 4 Step 4.8).

    COMPOSE_PROVIDER selects it: 'mock' (default — `make test` never sees an
    LLM) or 'anthropic' (the real fire-once client; Render sets this). Tests
    override this dependency to inject deterministic or failing composers.
    """
    if _compose_provider() == "anthropic":
        from src.tour.compose import AnthropicComposeClient

        return AnthropicComposeClient()
    return MockComposeClient()


def get_faithfulness_checker() -> FaithfulnessChecker | None:
    """VERIFY's entailment checker for /compose, PAIRED with the provider:
    the real compose is never gated by the trusting Mock (M-7). None -> the
    offline Mock inside build_full_verifier; 'anthropic' -> the real Haiku
    entailment. Tests override to inject rejecting checkers."""
    if _compose_provider() == "anthropic":
        from src.tour.verify import HaikuFaithfulnessChecker

        return HaikuFaithfulnessChecker()
    return None
