# S3 skeptic review — fix correctness (Sonnet)

Verified against commit `68c4f72329830c2faf90a495d30233a0daa35cc2` (working tree,
uncommitted changes to `src/tour/premium_tour.py`, `src/tour/authoring.py`,
`src/tour/degradations.py`, `tests/test_degradations.py`, and untracked
`tests/test_never_silent_failures.py`).

## What I checked myself

- Read the full diff of all three touched source files (`git diff -- src/tour/premium_tour.py
  src/tour/authoring.py src/tour/degradations.py`) directly, not from the pasted evidence.
- Read the full pinned test (`tests/test_never_silent_failures.py::test_a_unit_failure_inside_a_fan_out_reaches_the_caller`,
  lines 440-533) and its fixture (`_FailingUnitExecutor`, lines 444-484).
- Traced the call chain for `record()`'s context propagation:
  `degradation_scope()` sets `_ACTIVE` on the caller's thread → `in_current_context(fn)`
  takes `snapshot = contextvars.copy_context()` at wrap time (after the scope is entered) →
  each pool worker runs `snapshot.copy().run(fn, ...)`, which preserves the *same* `list`
  object bound to `_ACTIVE` inside the copy. `record()`'s `active.append(...)` is then a
  plain `list.append`, safe under the GIL even with concurrent workers.
- Confirmed `receipt_sink.after_call` is unconditionally a no-op in the only production
  implementation (`EphemeralReceiptSink`, `src/tour/premium_tour.py:370-376`), and that it is
  the only `PremiumReceiptSink` implementation referenced anywhere in `src/`
  (`grep -rn "ReceiptSink\b" src/`).
- Ran `make lint` myself: exit 0, "All checks passed!" (matches the pinned baseline).
- Parsed `tests/test_never_silent_failures.py` with `ast.parse` to confirm it is syntactically
  sound (ruff already implied this via F401/F821 checks passing with 0 errors).

## Fix-correctness verdict: the change does what AC-4 asks, scoped correctly

`invoke` (premium_tour.py) and the new `_execute_unit` (authoring.py) wrap
`executor.execute(unit)` in `try/except Exception as exc: record(...); raise`. Both:

- record `error_type=type(exc).__name__`, `error_message=str(exc)`,
  `context={"stop_index": str(unit.stop_index)}` — matching what the test asserts
  field-for-field.
- re-raise the *original* exception object via a bare `raise`, so `pytest.raises(...,
  match=...)` at the test's outer scope sees the same instance/traceback.
- run *inside* the per-call context copy (the S1/S2 fix), so `record()` sees the
  caller's `_ACTIVE` list even though it executes on a pool thread.

AC-4's wording is "a degradation ... reaches the **caller's scope**" — the caller here is
the direct caller of `execute_premium_plan`/`author_prebuilt_route`, which is exactly what
the test exercises (`with degradation_scope() as collected: ... pytest.raises(...):
execute_premium_plan(...)`). It deliberately does NOT test the outer API-route
`except Exception:` blindfold (`trips.py:1021`) that currently swallows this into an
HTTP 200 Basic fallback — that is explicitly S4/S5's job (AC-5/AC-6), not S3's. So the test
is correctly scoped to its own AC, not a strawman for the wider outage (AC-1/AC-2, which is
S1/S2's job and a genuinely different failure mode — concurrent context entry, not a unit
throwing).

## Attacks tried against the fix (all failed to break it, by static/structural analysis)

1. **Multiple simultaneous failures** (not exercised by the pinned test, which fails only
   stop_index 1 of 3). Reasoned through the code: each failing worker independently calls
   `record()` before raising, so N failures would produce N degradations and `pool.map`
   would surface whichever failure sits first in submission order when `tuple()` is
   consumed. This is more degradations than the single-failure test proves, but it is not a
   broken behaviour — it is a stronger, untested case, not a contradicted one.
2. **Failure at index 0 or the last index** — the fix does not branch on `stop_index` value,
   only reads it generically, so there is no reason to expect index-1-specific behaviour;
   nothing in the diff special-cases it.
3. **BaseException (not Exception) escaping unrecorded** (e.g. `KeyboardInterrupt`) — true
   in theory (`except Exception` does not catch `BaseException` subclasses), but this is not
   a realistic production path (SDK/provider code does not raise those) and is not what
   AC-4 or the ledger's D1-D5 decisions describe as the threat model. Advisory only, no
   repro attempted.
4. **`with ThreadPoolExecutor(...) as pool: return tuple(pool.map(...))` exception timing**
   — traced that `pool.__exit__` calls `shutdown(wait=True)` even when leaving via
   exception, so no dangling background work; the raised exception is the same instance
   asserted by `pytest.raises`. Confirmed by reading `concurrent.futures` semantics against
   the code shape, not by executing (would need a live run to fully confirm scheduling, see
   below).

## One structural gap found, NOT blocking

In `premium_tour.py`'s `invoke`, `receipt_sink.after_call(unit, response)` runs **after**
the `try/except`, not inside it. If a future, non-no-op `PremiumReceiptSink` implementation
raised in `after_call`, that exception would propagate un-recorded (though it would still
abort the tour, satisfying the "never ship half-narrated" half of AC-4 but not the "record"
half). Today this is inert: `EphemeralReceiptSink.after_call` just does `del unit, response`
and is the only implementation used anywhere in `src/` (confirmed by grep). `authoring.py`'s
`_execute_unit` has no equivalent call, so this asymmetry is specific to the premium-tour
site. Not filed as a blocking finding — no live code path exercises it, it isn't covered by
any AC in this ledger, and I have no reproduction. Worth a one-line follow-up note if a
persisting receipt sink is ever added.

## What I could NOT verify myself (concurrency rules)

Per the concurrent-skeptic constraint, `make test-file
FILE="tests/test_never_silent_failures.py::test_a_unit_failure_inside_a_fan_out_reaches_the_caller"`
touches the shared `PRE_PYTEST` prerequisite set (7688/7687/Valhalla), so I did not run it —
proposed below for the serial verifier. My review is therefore a static/structural
verification (full diff read, control-flow trace, contextvars semantics check) plus the one
command safe to run standalone (`make lint`), not an independent test execution. The
evidence chain's own undo-test (stash premium_tour.py + authoring.py only, leaving
degradations.py's S1/S2 fix and the test file in place) is a sound methodology — it isolates
S3's own causal contribution rather than the whole ticket's — and its pasted RED output
(`assert 0 == 1`, `got []`) is exactly what the pre-fix code (`invoke = executor.execute`
with no try/except) would produce, since the exception would already propagate without
being recorded.

## Verdict

CONFIRMED, from the fix-correctness angle: the change is the minimal, correctly-scoped
implementation of AC-4, the red-first test encodes the literal AC-4 requirement (not the
AC-1/AC-2 crash mode), and no plausible neighbouring input broke it under static analysis.
One non-blocking structural gap noted above (receipt-sink `after_call` uncaught) for the
record, not for rework.

## Proposed command (not run by me — shared container state)

`make test-file FILE="tests/test_never_silent_failures.py::test_a_unit_failure_inside_a_fan_out_reaches_the_caller"`
