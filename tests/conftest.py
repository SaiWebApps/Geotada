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

import json
import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

# Collection happens before per-test fixtures.  On an ordinary test run, reserve
# paid-provider credentials with empty values BEFORE importing the API or any
# module that calls ``load_dotenv()``.  An explicit Makefile live target is the
# only supported way to preserve real credentials in the test process.
_LIVE_PROVIDER_TESTS = os.getenv("ONDOWAY_LIVE_TESTS") == "1"
if not _LIVE_PROVIDER_TESTS:
    for _paid_key in (
        "ANTHROPIC_API_KEY",
        "ELEVENLABS_API_KEY",
        "OPENAI_API_KEY",
        "RESEND_API_KEY",
    ):
        os.environ[_paid_key] = ""

# Load test-specific Neo4j connection BEFORE importing src.connection.
# connection.py calls load_dotenv() at import time without override=True,
# so these values will be preserved.
_test_env = Path(__file__).resolve().parent.parent / ".env.test"
if _test_env.exists():
    load_dotenv(dotenv_path=_test_env, override=True)
    # Scrub again after loading the test file so a future accidental provider
    # key in .env.test cannot reopen collection-time spend.
    if not _LIVE_PROVIDER_TESTS:
        for _paid_key in (
            "ANTHROPIC_API_KEY",
            "ELEVENLABS_API_KEY",
            "OPENAI_API_KEY",
            "RESEND_API_KEY",
        ):
            os.environ[_paid_key] = ""
    # (The compose LLM wall is now enforced by the ``_money_guard_no_live_compose``
    # autouse fixture below — get_compose_client() ALWAYS builds the real Opus
    # client in the product, so an env toggle can no longer make it offline.)
    # Force the mock onboarding beat-drafter so the bar
    # (and src/onboard/cli.py) can NEVER make a live Anthropic call.
    os.environ["ONBOARD_PROVIDER"] = "mock"
    # The workbench API gate is now FAIL-CLOSED (src/api/app.py: mounts the
    # unauthenticated graph-CRUD + onboard routers ONLY on an explicit truthy
    # value). Opt the suite in so every in-process TestClient test — and the
    # uvicorn subprocess that tests/test_workbench_ui.py launches with
    # env={**os.environ, ...} — sees the workbench routers mounted. setdefault
    # (not plain assignment) so a shell `WORKBENCH_API_ENABLED=` export can still
    # force fail-closed for a run (CLAUDE.md: shell env wins).
    os.environ.setdefault("WORKBENCH_API_ENABLED", "true")
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
from src.api.auth.config import MAGIC_LINK_PROVIDER, RESEND_API_KEY
from src.connection import Neo4jConnectionError, create_driver, get_database
from src.schema.constraints import apply_all


def pytest_collection_modifyitems(config, items):
    """Deselect provider-specific live tests when that provider is unconfigured."""
    if not _LIVE_PROVIDER_TESTS or (
        MAGIC_LINK_PROVIDER == "resend" and bool(RESEND_API_KEY)
    ):
        return

    selected = []
    deselected = []
    for item in items:
        if item.get_closest_marker("requires_resend"):
            deselected.append(item)
        else:
            selected.append(item)
    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = selected


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Project policy: a skipped test counts as a FAILURE — no silent non-runs.

    Any skip outcome is flipped to 'failed' (the original skip reason is shown
    as the failure detail). Explicit xfail is preserved, since that is an
    asserted expected-failure, not a silent skip.
    """
    outcome = yield
    report = outcome.get_result()
    if report.skipped and not getattr(report, "wasxfail", False):
        report.outcome = "failed"


@pytest.fixture(autouse=True)
def _money_guard_no_live_compose(request, monkeypatch):
    """HARD money-guard. The product now ALWAYS builds the real Opus composer +
    Haiku checker (``get_compose_client`` / ``get_faithfulness_checker`` — the mock
    provider was removed so a CUSTOMER can never be served the stitcher passthrough
    as if it were the narrator). The hermetic bar must therefore be prevented from
    ever CONSTRUCTING those billing clients: for every non-``live`` test, patch the
    real classes to their offline stubs. The hermetic ``test-local`` shard then
    physically cannot make a paid Anthropic call — the real clients are never
    instantiated (proven by
    ``test_compose_provider.test_money_guard_compose_client_is_offline_stub``).
    ``@pytest.mark.live`` tests run in ``make test`` through the dedicated
    ``test-live`` shard; they intentionally spend and bind the real client by direct
    import, so they are left untouched."""
    if request.node.get_closest_marker("live"):
        if not _LIVE_PROVIDER_TESTS:
            pytest.fail(
                "live provider test requires ONDOWAY_LIVE_TESTS=1; "
                "use the explicit Makefile live target"
            )
        return
    import src.tour.compose as _compose_mod
    import src.tour.verify as _verify_mod

    _real_compose = _compose_mod.AnthropicComposeClient

    def _guard_compose(model=_compose_mod.COMPOSE_MODEL, *, client=None):
        # client is None == the PRODUCT get_compose_client() path, which would build
        # the real billing SDK — hand back the offline stitcher stub instead. A
        # direct unit test that injects a FAKE sdk client (client=<fake>) is already
        # offline, so let it exercise the REAL composer class.
        if client is None:
            return _compose_mod.MockComposeClient()
        return _real_compose(model, client=client)

    monkeypatch.setattr(_compose_mod, "AnthropicComposeClient", _guard_compose)

    # Same guard for the OpenAI (ChatGPT) composer: the product path (client=None)
    # would build the billing OpenAI SDK, so hand back the offline stub; a unit test
    # that injects a FAKE sdk client (client=<fake>) stays offline and exercises the
    # real translation logic. So COMPOSE_PROVIDER=openai cannot bill in `test-local`.
    _real_openai = _compose_mod.OpenAIComposeClient

    def _guard_openai(model=None, *, client=None):
        if client is None:
            return _compose_mod.MockComposeClient()
        return _real_openai(model, client=client)

    monkeypatch.setattr(_compose_mod, "OpenAIComposeClient", _guard_openai)

    # PREMIUM authoring money-guard: the workbench now uses the same zero-retry,
    # receipt-preserving physical boundary as certification batches. Product
    # construction is replaced by the explicit $0 adapter; injected fake
    # providers still exercise the real executor in unit tests.
    import src.tour.premium_tour as _premium_mod

    _real_premium = _premium_mod.AnthropicPremiumExecutor

    def _guard_premium(provider=None):
        if provider is None:
            return _premium_mod.OfflinePremiumExecutor()
        return _real_premium(provider)

    monkeypatch.setattr(_premium_mod, "AnthropicPremiumExecutor", _guard_premium)
    # No non-live test constructs the real Haiku checker with a fake SDK, so the
    # billing checker is always swapped for the offline trusting stub.
    monkeypatch.setattr(
        _verify_mod, "HaikuFaithfulnessChecker", _verify_mod.MockFaithfulnessChecker
    )

    # CORRECTOR money-guard (mirror compose/author): AnthropicCorrectionClient runs
    # CORRECTION_MODEL="claude-opus-4-8" — the priciest client in the tree. The arms
    # above do not cover it, so a test constructing it with client=None would build the
    # real SDK and bill Opus rates. Product path (client is None) -> the module's own
    # offline MockCorrectionClient (affirms, returns input unchanged); an injected fake
    # SDK client stays offline and still exercises the real class.
    import src.tour.compose_correct as _corr_mod

    _real_corrector = _corr_mod.AnthropicCorrectionClient

    def _guard_corrector(model=None, *, client=None, **kwargs):
        if client is None:
            return _corr_mod.MockCorrectionClient()
        return _real_corrector(model or _corr_mod.CORRECTION_MODEL, client=client, **kwargs)

    monkeypatch.setattr(_corr_mod, "AnthropicCorrectionClient", _guard_corrector)

    # REPETITION-JUDGE money-guard (mirror compose/author): HaikuRedundancyJudge is a
    # FIFTH billing client and the arms above do not cover it, so a test constructing it
    # with client=None would build the real SDK and bill. Product path (client is None)
    # -> offline stub that never claims redundancy; an injected fake SDK client stays
    # offline and still exercises the real class.
    import src.tour.claim_repetition as _rep_mod

    _real_redundancy = _rep_mod.HaikuRedundancyJudge

    class _OfflineRedundancyJudge:
        """Never redundant: a stub must not invent verdicts the real judge would make."""

        def same_fact(self, a: str, b: str) -> bool:
            return False

    def _guard_redundancy(model=None, *, client=None, **kwargs):
        if client is None:
            return _OfflineRedundancyJudge()
        return _real_redundancy(model, client=client, **kwargs)

    monkeypatch.setattr(_rep_mod, "HaikuRedundancyJudge", _guard_redundancy)

    # AUTHOR-ENGINE money-guard (mirror compose): the opt-in engine='author' preview path
    # builds an Opus drafter + 3 Haiku judges via get_author_composer. Patch each so the
    # PRODUCT path (client is None) builds an OFFLINE stub, never a billing SDK — a unit
    # test that injects a fake SDK client (client=<fake>) stays offline and exercises the
    # real class. So `test-local` cannot bill the author path.
    import src.tour.author as _author_mod
    import src.tour.factcheck as _fc_mod

    class _OfflineDrafter:  # empty draft -> author_compose_stop falls back to the stitch
        def write(self, *a, **k):
            return ""

        def rewrite(self, *a, **k):
            return ""

    class _OfflineDecomposer:
        def decompose(self, narration):
            return ()

    class _TrustingJudge:  # offline; the guard only has to prevent billing
        def conveys(self, fact, narration):
            return True

        def entails(self, key_claims, sentence_text):
            return True

    _real_drafter = _author_mod.LLMDrafter

    def _guard_drafter(model, *, client=None, max_tokens=4000):
        return (
            _OfflineDrafter()
            if client is None
            else _real_drafter(model, client=client, max_tokens=max_tokens)
        )

    monkeypatch.setattr(_author_mod, "LLMDrafter", _guard_drafter)

    _real_dec = _fc_mod.HaikuClaimDecomposer

    def _guard_dec(model=_fc_mod.FAITHFULNESS_MODEL, *, client=None):
        return _OfflineDecomposer() if client is None else _real_dec(model, client=client)

    monkeypatch.setattr(_fc_mod, "HaikuClaimDecomposer", _guard_dec)

    for _judge_name in ("HaikuCoverageJudge", "HaikuFaithfulnessJudge"):
        _real_judge = getattr(_fc_mod, _judge_name)

        def _guard_judge(model=_fc_mod.FAITHFULNESS_MODEL, *, client=None, _real=_real_judge):
            return _TrustingJudge() if client is None else _real(model, client=client)

        monkeypatch.setattr(_fc_mod, _judge_name, _guard_judge)

    # CROSS-STOP CONSISTENCY money-guard (mirrors the author-engine arm above): the
    # tour_consistency module's HaikuCrossStopJudge is a SEPARATE billing client living in a
    # module the author-engine guard above never touches (it's report-only, wired only from
    # scripts/author_tour.py — specs/2026-07-18-tour-qa-campaign cross-stop track). Patch it
    # the same way: PRODUCT path (client is None) -> offline stub; a unit test that injects a
    # fake SDK client stays offline and exercises the real class. So `test-local` cannot
    # bill the cross-stop judge either.
    import src.tour.tour_consistency as _tc_mod

    class _OfflineCrossStopJudge:  # offline; the guard only has to prevent billing
        def compare(self, a_label, a_claims, b_label, b_claims):
            return ()

    _real_cross_stop_judge = _tc_mod.HaikuCrossStopJudge

    def _guard_cross_stop_judge(model=_fc_mod.FAITHFULNESS_MODEL, *, client=None):
        return (
            _OfflineCrossStopJudge()
            if client is None
            else _real_cross_stop_judge(model, client=client)
        )

    monkeypatch.setattr(_tc_mod, "HaikuCrossStopJudge", _guard_cross_stop_judge)


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


def pytest_configure(config):
    """Refuse to run the whole suite against any non-test database.

    Many fixtures across the suite issue ``MATCH (n) DETACH DELETE n`` via their
    own ``create_driver()``, bypassing ``_wipe()``'s per-call guard. Rather than
    guard each one, we hard-stop the entire run when ``NEO4J_URI`` is not an
    allowlisted test port. The cloud (Aura) database is the single persistent
    store and must NEVER be wiped by tests — cloud connectivity is checked
    read-only via ``make test-cloud`` (which does not invoke pytest).
    """
    uri = os.getenv("NEO4J_URI", "")
    port = urlparse(uri).port
    if port not in _TEST_PORT_ALLOWLIST:
        pytest.exit(
            f"Refusing to run the test suite against NEO4J_URI={uri!r} (port={port}). "
            f"The suite contains destructive fixtures; it may only run against the test "
            f"database on port {sorted(_TEST_PORT_ALLOWLIST)}. The cloud DB is the single "
            f"persistent store and is never wiped by tests — use the read-only "
            f"`make test-cloud` smoke for a cloud check."
        )


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
    """DETACH DELETE every node, but ONLY against an allowlisted test port.

    The port assertion runs every call so env mutation between fixture
    creation and wipe (the Phase 4 incident vector) cannot bypass it.
    """
    _assert_test_port()
    with driver.session(database=get_database()) as session:
        session.run("MATCH (n) DETACH DELETE n")


@pytest.fixture(scope="module")
def clean_driver():
    """Create a driver with a clean DB + schema constraints."""
    _assert_test_port()
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


def load_onboard_fixture(city: str, name: str) -> dict:
    """Load a Step-3 connector JSON fixture from tests/fixtures/onboard/{city}/{name}.

    Connectors are PURE — their ``parse`` maps a raw provider JSON payload to a
    typed ``ConnectorResult`` — so the bar drives them from these committed
    fixtures and never touches the network.
    """
    return json.loads((Path(__file__).parent / "fixtures" / "onboard" / city / name).read_text())
