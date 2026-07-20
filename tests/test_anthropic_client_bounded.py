"""Every Anthropic client in the tour engine must be BOUNDED.

FOUNDING CASE (measured 2026-07-19): a workbench ``POST /trips/preview`` held 128
sockets to api.anthropic.com (91 CLOSE_WAIT, 34 ESTABLISHED and unmoving) and had
not returned after 32 MINUTES, against a UI promising "~1 min". The Anthropic API
was healthy throughout (a direct Haiku call answered in 1.2 s). The cause was
local: every client was constructed bare, inheriting the SDK's 600 s timeout with
2 retries — up to 30 minutes of silent waiting for ONE stalled call.

These tests are the guard. They fail if a future change reintroduces a bare
``anthropic.Anthropic()`` anywhere in the tour engine, or drops the explicit
timeout/retry ceiling from the shared factory.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from src.tour import anthropic_client

REPO = pathlib.Path(__file__).resolve().parents[1]
TOUR_DIR = REPO / "src" / "tour"

#: EVERY directory that may construct an Anthropic client, not just src/tour.
#:
#: The first version of this guard globbed ``src/tour/*.py`` only. An adversarial
#: review found two bare clients it structurally COULD NOT SEE:
#: ``src/api/routes/feedback.py`` (a live, request-blocking user route) and
#: ``src/onboard/beat_draft.py`` (bulk city onboarding) — both carrying the identical
#: 30-minute exposure the guard was written to eliminate, while the claim "the
#: 30-minute hang is closed" was being made. A guard whose scope is narrower than
#: the defect is a false assurance, so this now sweeps all of ``src/``.
SRC_DIR = REPO / "src"

#: The factory module itself names the bare constructor in its docstring (that is
#: the whole point of the docstring); no other tour module may CALL it.
_FACTORY = "anthropic_client.py"


def _bare_anthropic_calls(path: pathlib.Path) -> list[int]:
    """Line numbers of any ``anthropic.Anthropic(...)`` CALL in ``path``.

    Parsed with ``ast`` rather than grepped: a docstring mentioning the pattern
    (as the factory's does, deliberately) must not count as a violation. Only a
    real call node does.
    """
    tree = ast.parse(path.read_text(), filename=str(path))
    hits: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "Anthropic"
            and isinstance(func.value, ast.Name)
            and func.value.id == "anthropic"
        ):
            hits.append(node.lineno)
    return hits


def test_no_bare_anthropic_client_anywhere_in_src() -> None:
    """NO module under src/ may construct an unbounded client directly.

    Swept across ALL of src/, not just src/tour — see SRC_DIR's comment: the
    tour-only version of this guard missed a live user-facing route and the
    onboarding path, both with the same 30-minute exposure.

    UNDO TEST: revert any one call site (e.g. src/tour/verify.py:117,
    src/api/routes/feedback.py, src/onboard/beat_draft.py) to
    ``anthropic.Anthropic()`` and this goes RED, naming the file and line.
    """
    offenders: dict[str, list[int]] = {}
    for path in sorted(SRC_DIR.rglob("*.py")):
        if path.name == _FACTORY:
            continue
        hits = _bare_anthropic_calls(path)
        if hits:
            offenders[str(path.relative_to(REPO))] = hits

    assert not offenders, (
        "Bare anthropic.Anthropic() found under src/ — these inherit the SDK's "
        "600s x 2-retry default and can hang a request for 30 minutes. "
        f"Use src.tour.anthropic_client.judge_client()/compose_client(). Offenders: {offenders}"
    )


def test_the_guard_actually_sweeps_beyond_src_tour() -> None:
    """The guard's SCOPE is itself load-bearing and must not silently narrow.

    A scope regression is invisible: the suite stays green while the defect walks
    back in somewhere the glob no longer looks. This asserts the sweep really does
    reach the two directories the original tour-only guard missed.
    """
    swept = {str(p.relative_to(REPO)) for p in SRC_DIR.rglob("*.py")}
    for required in ("src/api/routes/feedback.py", "src/onboard/beat_draft.py"):
        assert required in swept, (
            f"{required} is not covered by the guard's sweep — it was a real "
            "offender once and must stay in scope"
        )


def test_factory_sets_an_explicit_ceiling() -> None:
    """The factory must pass BOTH timeout and max_retries, not rely on defaults."""
    captured: dict[str, object] = {}

    class _FakeAnthropic:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    import sys
    import types

    stub = types.ModuleType("anthropic")
    stub.Anthropic = _FakeAnthropic  # type: ignore[attr-defined]
    saved = sys.modules.get("anthropic")
    sys.modules["anthropic"] = stub
    try:
        anthropic_client.judge_client()
        assert captured["timeout"] == anthropic_client.JUDGE_TIMEOUT_S
        assert captured["max_retries"] == anthropic_client.JUDGE_MAX_RETRIES

        captured.clear()
        anthropic_client.compose_client()
        assert captured["timeout"] == anthropic_client.COMPOSE_TIMEOUT_S
        assert captured["max_retries"] == anthropic_client.COMPOSE_MAX_RETRIES
    finally:
        if saved is None:
            sys.modules.pop("anthropic", None)
        else:
            sys.modules["anthropic"] = saved


@pytest.mark.parametrize(
    ("name", "value", "ceiling"),
    [
        ("JUDGE_TIMEOUT_S", anthropic_client.JUDGE_TIMEOUT_S, 120.0),
        ("COMPOSE_TIMEOUT_S", anthropic_client.COMPOSE_TIMEOUT_S, 300.0),
    ],
)
def test_timeouts_are_well_under_the_sdk_default(
    name: str, value: float, ceiling: float
) -> None:
    """A ceiling that drifts back toward the 600 s SDK default defeats the purpose."""
    assert 0 < value <= ceiling, (
        f"{name}={value} is not a meaningful bound (SDK default is 600s; "
        f"this must stay <= {ceiling}s)"
    )


def test_retry_counts_bound_worst_case_wall_clock() -> None:
    """timeout x (1 + retries) is the real worst case a user waits on one call."""
    judge_worst = anthropic_client.JUDGE_TIMEOUT_S * (1 + anthropic_client.JUDGE_MAX_RETRIES)
    compose_worst = anthropic_client.COMPOSE_TIMEOUT_S * (1 + anthropic_client.COMPOSE_MAX_RETRIES)
    # The bare-client worst case was 600 * 3 = 1800s. Both must be far below it.
    assert judge_worst <= 300, f"judge worst case {judge_worst}s is too long"
    assert compose_worst <= 600, f"compose worst case {compose_worst}s is too long"
