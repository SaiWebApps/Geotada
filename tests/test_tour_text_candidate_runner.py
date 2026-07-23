"""Operational guards for the bounded provider-authored text runner."""

from __future__ import annotations

import time

from scripts.tour_text_candidate import _AbsoluteCallScope


class _Stream:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_deadline_starts_before_stream_registration() -> None:
    scope = _AbsoluteCallScope(deadline_seconds=0.01)
    deadline = time.monotonic() + 0.5
    while not scope.expired and time.monotonic() < deadline:
        time.sleep(0.001)
    stream = _Stream()

    scope.register(stream)
    scope.finish()

    assert scope.expired
    assert stream.closed


def test_finishing_a_call_disarms_its_deadline() -> None:
    scope = _AbsoluteCallScope(deadline_seconds=0.05)
    scope.finish()
    time.sleep(0.1)

    assert not scope.expired
