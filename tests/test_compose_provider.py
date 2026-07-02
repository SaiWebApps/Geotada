"""Phase 4 Step 4.8 — COMPOSE_PROVIDER selects the compose client + checker.

Pure env-driven selection tests: constructions of the real clients are
stubbed so no SDK/network is ever touched.
"""

from __future__ import annotations

import pytest

from src.api.dependencies import get_compose_client, get_faithfulness_checker
from src.tour.compose import MockComposeClient


class _StubAnthropicCompose:
    pass


class _StubHaikuChecker:
    pass


@pytest.fixture()
def _stub_real_clients(monkeypatch):
    import src.tour.compose as compose_mod
    import src.tour.verify as verify_mod

    monkeypatch.setattr(compose_mod, "AnthropicComposeClient", _StubAnthropicCompose)
    monkeypatch.setattr(verify_mod, "HaikuFaithfulnessChecker", _StubHaikuChecker)


def test_default_is_mock_and_trusting_checker(monkeypatch):
    monkeypatch.delenv("COMPOSE_PROVIDER", raising=False)
    assert isinstance(get_compose_client(), MockComposeClient)
    assert get_faithfulness_checker() is None


def test_anthropic_pairs_real_compose_with_real_checker(monkeypatch, _stub_real_clients):
    monkeypatch.setenv("COMPOSE_PROVIDER", "anthropic")
    assert isinstance(get_compose_client(), _StubAnthropicCompose)
    assert isinstance(get_faithfulness_checker(), _StubHaikuChecker)


def test_unknown_provider_is_a_loud_error(monkeypatch):
    monkeypatch.setenv("COMPOSE_PROVIDER", "gpt")
    with pytest.raises(RuntimeError, match="Unknown COMPOSE_PROVIDER"):
        get_compose_client()
    with pytest.raises(RuntimeError, match="Unknown COMPOSE_PROVIDER"):
        get_faithfulness_checker()
