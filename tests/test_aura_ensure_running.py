"""Hermetic proof for scripts/aura_ensure_running — no live Aura.

Burns in the 2026-07-12 lesson (paused != dead): a paused instance is resumed and
awaited to `running`, an already-running one is a no-op, and a stuck one times out
loudly instead of being mistaken for dead.
"""

from __future__ import annotations

import pytest

from scripts.aura_ensure_running import ensure_running
from src.aura_resume import AuraResumeError


class _FakeClient:
    """Yields a scripted status sequence; records resume() calls."""

    def __init__(self, statuses):
        self._statuses = list(statuses)
        self.resumed = 0

    def get_status(self):
        return self._statuses.pop(0)

    def resume(self):
        self.resumed += 1


def _noop(*_a, **_k):
    pass


def test_paused_is_resumed_and_awaited():
    c = _FakeClient(["paused", "resuming", "running"])
    assert ensure_running(c, poll=0, sleep=_noop, echo=_noop) == "running"
    assert c.resumed == 1  # resume fired exactly once


def test_already_running_is_a_noop():
    c = _FakeClient(["running"])
    assert ensure_running(c, poll=0, sleep=_noop, echo=_noop) == "running"
    assert c.resumed == 0  # never resume a healthy instance


def test_stuck_instance_times_out_not_declared_dead():
    # Never resolves — a real infra problem must SURFACE as a timeout, never be
    # silently swallowed or mistaken for a deletion.
    c = _FakeClient(["paused"] + ["resuming"] * 50)
    clock = iter([0.0, 1.0, 2.0, 3.0, 4.0])  # exceeds a 2s timeout on the 3rd tick
    with pytest.raises(TimeoutError):
        ensure_running(c, timeout=2.0, poll=0, sleep=_noop, clock=lambda: next(clock), echo=_noop)


def test_unrecoverable_state_raises():
    c = _FakeClient(["paused", "destroying"])
    with pytest.raises(AuraResumeError, match="unrecoverable"):
        ensure_running(c, poll=0, sleep=_noop, echo=_noop)
