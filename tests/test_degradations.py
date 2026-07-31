"""The visible-failure machinery, measured.

OWNER RULING 2026-07-31: *"Don't just log errors. Actually show them in the
workbench UI. Otherwise, they're invisible."* This file is the executable half of
that. It shipped once with NO tests at all, which a judge caught — a feature
whose entire purpose is "stop trusting that a problem was noticed" cannot itself
be taken on trust.

The thread test is the load-bearing one. The first version of
``degradations.py`` claimed in its docstring to be "safe to call from anywhere,
including threads". Measured, that was false: ``contextvars`` do not cross into
``ThreadPoolExecutor`` workers, so a degradation recorded inside the compose
fan-out was silently dropped — the exact invisibility this module exists to
prevent, in the module itself.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from src.tour.degradations import (
    degradation_scope,
    in_current_context,
    record,
    summarize,
)


def test_recording_outside_a_scope_is_a_no_op() -> None:
    """No scope, no state. A long-lived server must not accumulate rows forever."""
    record(kind="orphan", human="h", component="c")  # must not raise
    with degradation_scope() as collected:
        pass
    assert collected == []


def test_a_recorded_degradation_carries_both_registers() -> None:
    """One row must serve the human AND the engineer — that is the whole ruling."""
    with degradation_scope() as collected:
        record(
            kind="glue_call_failed",
            human="The walking directions were written from a template.",
            component="HaikuGlueClient.stitch",
            error=TypeError("Could not resolve authentication method"),
            glue_category="GLUE_NAV",
        )
    assert len(collected) == 1
    row = collected[0].as_dict()
    assert row["human"].startswith("The walking directions")
    assert row["component"] == "HaikuGlueClient.stitch"
    assert row["error_type"] == "TypeError"
    assert "authentication" in row["error_message"]
    assert row["context"] == {"glue_category": "GLUE_NAV"}


def test_scopes_do_not_leak_into_each_other() -> None:
    """Two requests in one process must not see each other's problems."""
    with degradation_scope() as first:
        record(kind="a", human="h", component="c")
        with degradation_scope() as second:
            record(kind="b", human="h", component="c")
        assert [d.kind for d in second] == ["b"]
    assert [d.kind for d in first] == ["a"]


def test_repeats_collapse_to_one_row_with_a_count() -> None:
    """A five-stop tour with an unreachable narrator yields four identical glue
    failures. Four rows bury the signal; one row saying "happened 4 times" is the
    same information a person can act on."""
    with degradation_scope() as collected:
        for _ in range(4):
            record(kind="glue_call_failed", human="h", component="c")
        record(kind="other", human="h", component="c")
    rows = {r["kind"]: r for r in summarize(collected)}
    assert rows["glue_call_failed"]["count"] == 4
    assert rows["other"]["count"] == 1


def test_a_degradation_recorded_in_a_worker_thread_is_not_lost() -> None:
    """THE regression. Compose fans out across a ThreadPoolExecutor, and
    ``contextvars`` do not propagate into pool workers — so a failure inside a
    compose call recorded nothing and the response looked clean.

    UNDO TEST: drop the ``in_current_context`` wrapper below and this goes RED
    with ``recorded kinds: ['main']``, which is exactly what the product did
    before the fix.
    """
    with degradation_scope() as collected:
        record(kind="main", human="h", component="c")

        def _work(_: int) -> None:
            record(kind="from_worker", human="h", component="c")

        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(in_current_context(_work), range(3)))

    kinds = sorted({d.kind for d in collected})
    assert "from_worker" in kinds, (
        f"a degradation recorded inside a pool worker was DROPPED (saw {kinds}); "
        f"the compose fan-out would report a clean tour while failing"
    )
    assert summarize(collected)  # and it survives the summariser


def test_an_unwrapped_worker_still_loses_it_so_the_wrapper_is_load_bearing() -> None:
    """Proves the wrapper is what fixes it, not something incidental.

    Without this, someone could delete ``in_current_context`` from the fan-out
    sites, the test above would still pass (it wraps explicitly), and the product
    would silently regress.
    """
    with degradation_scope() as collected:

        def _work(_: int) -> None:
            record(kind="unwrapped", human="h", component="c")

        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(_work, range(2)))

    assert "unwrapped" not in {d.kind for d in collected}, (
        "an UNWRAPPED worker recorded successfully — contextvars now propagate "
        "into pool workers on their own, so in_current_context is dead weight "
        "and the fan-out sites can drop it"
    )
