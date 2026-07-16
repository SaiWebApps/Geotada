"""The narration composer is ALWAYS the real Opus client in the PRODUCT — there
is no 'mock' provider any more. A customer (the app via POST /trips/{id}/compose,
the workbench via /trips/preview) must never be served the deterministic stitcher
passthrough as if it were the narrator.

The hermetic test suite is protected from billing by the autouse
``_money_guard_no_live_compose`` fixture in conftest.py, which patches the real
Opus/Haiku classes to their offline stubs — so ``make test`` can never make a
paid Anthropic call. These tests pin BOTH halves of that contract.
"""

from __future__ import annotations

from src.api.dependencies import get_compose_client, get_faithfulness_checker


def test_money_guard_compose_client_is_offline_stub_in_suite() -> None:
    """MONEY-GUARD: inside the hermetic suite, ``get_compose_client()`` must return
    the OFFLINE stub, never the billing client — otherwise ``make test`` would spend
    real money on every run.
    UNDO: delete the ``_money_guard_no_live_compose`` conftest fixture -> this
    returns the real ``AnthropicComposeClient`` -> RED."""
    assert type(get_compose_client()).__name__ == "MockComposeClient", (
        "MONEY-GUARD FAILED: the hermetic suite would construct a LIVE billing "
        f"compose client ({type(get_compose_client()).__name__})"
    )


def test_money_guard_blocks_the_openai_provider_too(monkeypatch) -> None:
    """MONEY-GUARD, OpenAI half: with ``COMPOSE_PROVIDER=openai`` the hermetic suite
    must STILL return the offline stub, never the billing ChatGPT client — so the
    Opus-vs-ChatGPT feature can never make ``make test`` spend on OpenAI.
    UNDO: drop the OpenAI arm of ``_money_guard_no_live_compose`` -> RED."""
    monkeypatch.setenv("COMPOSE_PROVIDER", "openai")
    assert type(get_compose_client()).__name__ == "MockComposeClient", (
        "MONEY-GUARD FAILED: COMPOSE_PROVIDER=openai would construct a LIVE billing "
        f"OpenAI client ({type(get_compose_client()).__name__})"
    )


def test_provider_toggle_selects_real_opus_or_real_chatgpt(monkeypatch) -> None:
    """``get_compose_client()`` defaults to the real Opus composer and switches to
    the real ChatGPT composer on ``COMPOSE_PROVIDER=openai`` — the two REAL narrators
    the workbench comparison picks between. Proven by re-patching both classes to
    markers (overriding the money-guard stub; the later setattr wins).
    UNDO: hardcode one provider in ``compose_client_for`` -> RED."""
    import src.tour.compose as _compose_mod

    class _OpusMarker:
        pass

    class _GptMarker:
        pass

    monkeypatch.setattr(_compose_mod, "AnthropicComposeClient", _OpusMarker)
    monkeypatch.setattr(_compose_mod, "OpenAIComposeClient", _GptMarker)

    monkeypatch.delenv("COMPOSE_PROVIDER", raising=False)
    assert isinstance(get_compose_client(), _OpusMarker)  # default = Opus
    monkeypatch.setenv("COMPOSE_PROVIDER", "openai")
    assert isinstance(get_compose_client(), _GptMarker)  # toggle = ChatGPT
    monkeypatch.setenv("COMPOSE_PROVIDER", "chatgpt")
    assert isinstance(get_compose_client(), _GptMarker)  # alias


def test_unknown_or_mock_provider_falls_back_to_real_opus_never_a_stub(monkeypatch) -> None:
    """No 'mock' provider survives in the product: an unknown or legacy ``mock``
    value falls back to the REAL Opus composer, never the stitcher passthrough.
    UNDO: add ``if provider == 'mock': return MockComposeClient()`` to
    ``compose_client_for`` -> the real Opus marker is not returned -> RED."""
    import src.tour.compose as _compose_mod

    class _OpusMarker:
        pass

    monkeypatch.setattr(_compose_mod, "AnthropicComposeClient", _OpusMarker)
    for bad in ("mock", "garbage", ""):
        monkeypatch.setenv("COMPOSE_PROVIDER", bad)
        assert isinstance(get_compose_client(), _OpusMarker), bad


def test_faithfulness_checker_is_always_the_paired_real_checker(monkeypatch) -> None:
    """``get_faithfulness_checker()`` unconditionally builds the real
    ``HaikuFaithfulnessChecker`` (paired with the real composer per M-7 — the real
    compose is never gated by the trusting Mock). No toggle, no ``None`` branch.
    UNDO: return ``None`` unconditionally, or add a mock branch -> RED."""
    import src.tour.verify as _verify_mod

    sentinel = object()
    monkeypatch.setattr(_verify_mod, "HaikuFaithfulnessChecker", lambda *a, **k: sentinel)
    assert get_faithfulness_checker() is sentinel
