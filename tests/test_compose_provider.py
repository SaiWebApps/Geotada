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


def test_product_compose_client_is_always_the_real_opus_client(monkeypatch) -> None:
    """The product has NO mock branch and NO env toggle: ``get_compose_client()``
    unconditionally builds ``AnthropicComposeClient``. Proven by re-patching that
    class to a marker (overriding the money-guard's stub — the later ``setattr``
    on the shared function-scoped monkeypatch wins) and confirming the marker is
    what gets built. If a ``mock`` fallback branch were reintroduced, the marker
    would not be returned.
    UNDO: add back ``if provider == 'mock': return MockComposeClient()`` -> RED."""
    import src.tour.compose as _compose_mod

    class _RealMarker:
        pass

    monkeypatch.setattr(_compose_mod, "AnthropicComposeClient", _RealMarker)
    assert isinstance(get_compose_client(), _RealMarker)


def test_faithfulness_checker_is_always_the_paired_real_checker(monkeypatch) -> None:
    """``get_faithfulness_checker()`` unconditionally builds the real
    ``HaikuFaithfulnessChecker`` (paired with the real composer per M-7 — the real
    compose is never gated by the trusting Mock). No toggle, no ``None`` branch.
    UNDO: return ``None`` unconditionally, or add a mock branch -> RED."""
    import src.tour.verify as _verify_mod

    sentinel = object()
    monkeypatch.setattr(_verify_mod, "HaikuFaithfulnessChecker", lambda *a, **k: sentinel)
    assert get_faithfulness_checker() is sentinel
