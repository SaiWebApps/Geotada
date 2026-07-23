"""FastAPI dependency injection for Neo4j sessions."""

from __future__ import annotations

from collections.abc import Generator
from typing import TYPE_CHECKING

from src.connection import create_driver, get_database
from src.tour.compose import ComposeClient

if TYPE_CHECKING:
    from neo4j import Driver, Session

    from src.tour.claim_repetition import RedundancyJudge
    from src.tour.factcheck import CoverageJudge
    from src.tour.verify import FaithfulnessChecker

_driver: Driver | None = None


def init_driver() -> None:
    """Called during FastAPI lifespan startup.

    Builds the driver LAZILY (no eager connectivity check): the web service must
    start and open its port even when Neo4j is unreachable, or the Render deploy
    fails its health check and the whole release is rolled back. DB errors then
    surface per-request (and /api/v1/healthz reports ``neo4j_connected: false``)
    instead of crashing startup. If even constructing the driver fails (malformed
    URI / missing env), we log and leave it None so the app still starts —
    requests then 500 with the clear "Driver not initialized" assert.
    """
    global _driver
    try:
        _driver = create_driver(verify=False)
        _init_aura_resume()
    except Exception as exc:  # never let driver setup crash startup
        import logging

        logging.getLogger("ondoway.api").warning(
            "Neo4j driver init failed at startup (%s); starting anyway — DB calls "
            "will fail per-request until connectivity returns.",
            exc,
        )
        _driver = None


def _init_aura_resume() -> None:
    """Build the Aura resume coordinator and, if enabled, fire a wake in the
    background so a cold deploy against a PAUSED instance starts resuming it
    immediately — without blocking startup or crashing if Aura is unreachable.

    A NO-OP when AURA creds are unset (local dev + CI): build_coordinator()
    returns None and nothing runs.
    """
    import threading

    from src.aura_resume import get_coordinator, reset_coordinator

    # Re-read env in case this process was redeployed with newly-set creds.
    reset_coordinator()
    coordinator = get_coordinator()
    if coordinator is None:
        return

    def _wake() -> None:
        try:
            coordinator.ensure_resuming()
        except Exception as exc:  # ensure_resuming never raises, but be defensive
            import logging

            logging.getLogger("ondoway.aura").warning(
                "Background Aura wake failed at startup: %s", exc
            )

    threading.Thread(target=_wake, name="aura-resume-startup", daemon=True).start()


def get_resume_coordinator():
    """Return the process-wide Aura ResumeCoordinator, or None if disabled.

    The app.py ServiceUnavailable handler + degraded healthz call this to nudge a
    paused instance awake on a failed DB probe.
    """
    from src.aura_resume import get_coordinator

    return get_coordinator()


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


def get_compose_client() -> ComposeClient:
    """The legacy persisted-trip composer for POST /trips/{id}/compose.

    A REAL fire-once composer — Opus by default, or ChatGPT when
    ``COMPOSE_PROVIDER=openai`` (the Opus-vs-ChatGPT writing comparison). There is
    NO 'mock' provider in the product: a customer/comparison must never be served
    the deterministic stitcher passthrough as if it were the narrator. Opus needs
    ANTHROPIC_API_KEY; ChatGPT needs OPENAI_API_KEY (both in .env locally, Render for
    prod). The hermetic test suite NEVER reaches these live clients —
    ``tests/conftest.py`` patches BOTH ``AnthropicComposeClient`` and
    ``OpenAIComposeClient`` to offline stubs for the whole (non-``live``) bar, so
    ``make test`` can never bill either account; tests that assert on compose also
    override this dependency directly.
    """
    import os

    from src.tour.compose import compose_client_for

    return compose_client_for(os.getenv("COMPOSE_PROVIDER"))


def get_premium_compose_executor():
    """Zero-retry, receipt-preserving author for the Premium preview path."""

    import src.tour.premium_tour as premium_tour

    return premium_tour.AnthropicPremiumExecutor()


def get_faithfulness_checker() -> FaithfulnessChecker | None:
    """VERIFY's entailment checker for the compose paths — ALWAYS the real Haiku
    checker, paired with the real Opus composer (M-7: the real compose is never
    gated by the trusting Mock). The hermetic suite patches this to an offline
    stub (see ``get_compose_client``); tests override to inject rejecting checkers.
    """
    from src.tour.verify import HaikuFaithfulnessChecker

    return HaikuFaithfulnessChecker()


def get_correction_client():
    """The correct-don't-reject repair client — part of THE ONE ALGORITHM, used by
    BOTH compose paths (``POST /trips/preview`` and ``POST /trips/{id}/compose``).

    When a composed sentence fails the faithfulness gate, this attempts up to two Opus
    repairs (trim, then narrator-voice rewrite) before the sentence is allowed to
    degrade to raw grounded stitch.

    Imported INSIDE the function and referenced as a module ATTRIBUTE so the conftest
    money-guard's monkeypatch swaps it for an offline stub in the (non-``live``) bar —
    exactly like ``get_compose_client``. This is not stylistic: the route previously
    held its own ``from src.tour.compose_correct import AnthropicCorrectionClient``
    binding, which monkeypatch could not reach, so the suite built the REAL Opus client
    (CORRECTION_MODEL="claude-opus-4-8", the priciest in the tree) on every preview and
    every compose — and compose_correct swallows client exceptions, so it billed
    silently and never turned a test red. Guarded by
    tests/test_compose_corrector_optin.py::test_trips_route_holds_no_unpatchable_corrector_binding.
    """
    import src.tour.compose_correct as compose_correct

    return compose_correct.AnthropicCorrectionClient()


def get_omission_checker() -> CoverageJudge:
    """The ADVISORY coverage-direction checker for the workbench preview's
    omission-detection report (``src.tour.compose.find_dropped_facts`` — strictly
    opt-in, called by the route AFTER a Script is already served; it never touches
    VERIFY's pass/fail or the compose ladder). Catches the blind spot the
    production coverage gate (``claim_dedup.verify_claim_coverage``'s overlap
    COEFFICIENT) structurally cannot: once compose deletes material the composed
    signature is a SUBSET of the claim signature, so the ratio is 1.000 by
    construction and no threshold fixes it.

    Deliberately just the ``CoverageJudge`` half of ``factcheck.SemanticFactChecker``
    — NOT the decomposer: faithfulness (invention) is already checked by
    ``get_faithfulness_checker``'s Haiku entailer, so decomposing the narration again
    here would double that cost for zero new signal. This wires ONLY the coverage
    judgements the compose path was missing.

    Imported INSIDE the function and referenced as a module ATTRIBUTE — exactly
    like ``get_correction_client`` — so the conftest money-guard's existing
    ``HaikuCoverageJudge`` arm (tests/conftest.py, added for the author-engine path)
    swaps this for an offline stub (always 'conveyed', never bills) in the
    (non-``live``) bar.
    """
    import src.tour.factcheck as factcheck

    return factcheck.HaikuCoverageJudge()


def get_claim_repetition_judge() -> RedundancyJudge:
    """G4's semantic judge (specs/2026-07-19-tour-quality-standard/01-standard.md §4) —
    an ADVISORY, UNCALIBRATED check: does any two narration sentences, anywhere in the
    tour, restate the same underlying fact in new words. NEVER folds into
    ``quality["passed"]`` (formerly tracked as failure-ledger entry FL-2026-111, now
    removed: this judge "has never executed against a live model" — every test in
    tests/test_claim_repetition.py injects a hand-labelled stub. Closing that gap is
    a prerequisite for any BLOCKER-severity use).
    ALWAYS the real Haiku judge in production, run alongside — never gating — the
    rubric on every COMPOSED/STITCHED preview (``src/api/routes/trips.py`` skips this
    entirely on the ComposeVerificationError "refused" path, where there is no served
    script yet worth spending the judge budget on). Findings surface in
    ``quality["g4"]``, severity WARN, separate from the rubric's blockers/warnings.

    Imported INSIDE the function and referenced as a module ATTRIBUTE — exactly like
    ``get_correction_client`` — so the conftest money-guard's monkeypatch (tests/
    conftest.py, the "REPETITION-JUDGE money-guard" arm already in place before this
    dependency existed) swaps it for an offline stub in the (non-``live``) bar. Stage-1
    candidate generation is $0 and deterministic and runs unconditionally either way;
    only this judge is ever billing, and it is never constructed with ``client=None``
    inside pytest.
    """
    import src.tour.claim_repetition as claim_repetition

    return claim_repetition.HaikuRedundancyJudge()
