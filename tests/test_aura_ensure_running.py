"""Hermetic proof for scripts/aura_ensure_running — no live Aura.

Burns in the 2026-07-12 lesson (paused != dead): a paused instance is resumed and
awaited, a serving one is a no-op, and a stuck one times out loudly instead of
being mistaken for dead.

And the readiness question itself: THE DATABASE ANSWERING is the only green
light. Aura reports a control-plane lifecycle status and a Bolt endpoint
independently, and they disagree by design — an instance under a rolling
`updating` serves queries throughout — so a gate that reads the status string
refuses a database that works. `updating` is not even in the vocabulary
``src/aura_resume`` documents, so it was neither accepted nor terminal: it was
polled to a 300 s timeout while the database answered a full parity check.
The two tests naming that are exact inverses of each other.
"""

from __future__ import annotations

import pytest

from scripts.aura_ensure_running import ensure_running
from src.aura_resume import AuraResumeError


class _FakeClient:
    """Yields a scripted status sequence; records resume() and status calls."""

    def __init__(self, statuses):
        self._statuses = list(statuses)
        self.resumed = 0
        self.status_calls = 0

    def get_status(self):
        self.status_calls += 1
        return self._statuses.pop(0)

    def resume(self):
        self.resumed += 1


def _noop(*_a, **_k):
    pass


def _answers(*results):
    """A scripted database probe: yields each result, then repeats the last."""
    seq = list(results)
    return lambda: seq.pop(0) if len(seq) > 1 else seq[0]


def test_an_instance_that_answers_is_ready_whatever_the_status_says():
    """THE readiness question, asked of the database instead of a status string.

    Measured 2026-09-03: the instance reported `updating` while
    `make db-parity TARGET=cloud` passed against it completely (370 POIs, 1541
    beats, every city matching the repo). The old gate demanded the literal
    string `running`, so it polled a working database for 300 s and failed the
    cloud shard. A status the control plane never documented must not be able to
    refuse a database that is serving.

    UNDO: gate on `status == "running"` again -> this times out -> RED.
    """
    c = _FakeClient(["updating"])
    assert ensure_running(c, answers=_answers(True), poll=0, sleep=_noop, echo=_noop) == "serving"
    assert c.resumed == 0, "a serving instance must never be resumed"
    assert c.status_calls == 0, (
        "the control plane was asked a question the database had already answered"
    )


def test_a_status_string_alone_never_certifies_readiness():
    """The exact inverse, and the direction that protects a caller.

    `running` is the control plane's opinion; it is not evidence the database
    will answer. A gate that returns on the string alone hands a `-cloud` target
    a database it cannot query — the silent-success failure this repo's preflight
    rule bans ("a probe reports evidence it observed itself").

    UNDO: return early on `status == "running"` -> this returns instead of
    timing out -> RED.
    """
    c = _FakeClient(["running"] * 50)
    clock = iter([0.0, 1.0, 2.0, 3.0, 4.0])
    with pytest.raises(TimeoutError):
        ensure_running(
            c,
            answers=_answers(False),
            timeout=2.0,
            poll=0,
            sleep=_noop,
            clock=lambda: next(clock),
            echo=_noop,
        )


def test_paused_is_resumed_and_awaited():
    # A paused instance withdraws its DNS, so the database cannot answer: this is
    # the case the status/resume path exists for, and it is unchanged.
    c = _FakeClient(["paused"])
    assert (
        ensure_running(c, answers=_answers(False, True), poll=0, sleep=_noop, echo=_noop)
        == "serving"
    )
    assert c.resumed == 1  # resume fired exactly once


def test_a_serving_instance_is_a_noop():
    c = _FakeClient([])
    assert ensure_running(c, answers=_answers(True), poll=0, sleep=_noop, echo=_noop) == "serving"
    assert c.resumed == 0  # never resume a healthy instance


def test_stuck_instance_times_out_not_declared_dead():
    # Never resolves — a real infra problem must SURFACE as a timeout, never be
    # silently swallowed or mistaken for a deletion.
    c = _FakeClient(["paused"] + ["resuming"] * 50)
    clock = iter([0.0, 1.0, 2.0, 3.0, 4.0])  # exceeds a 2s timeout on the 3rd tick
    with pytest.raises(TimeoutError):
        ensure_running(
            c,
            answers=_answers(False),
            timeout=2.0,
            poll=0,
            sleep=_noop,
            clock=lambda: next(clock),
            echo=_noop,
        )


def test_unrecoverable_state_raises():
    c = _FakeClient(["paused", "destroying"])
    with pytest.raises(AuraResumeError, match="unrecoverable"):
        ensure_running(c, answers=_answers(False), poll=0, sleep=_noop, echo=_noop)
