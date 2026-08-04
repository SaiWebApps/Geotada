# Step S3 — hostile skeptic (negative space), opus

**Stamped against:** HEAD `68c4f723` plus the uncommitted working tree carrying S1/S2/S3.
Working-tree diffstat re-derived by me: `src/tour/authoring.py` +25, `src/tour/degradations.py` +22/-8,
`src/tour/premium_tour.py` +21/-1, `tests/test_degradations.py` +107/-19, plus untracked
`tests/test_never_silent_failures.py` (532 lines).

**Claim under test:** S3 ("record a unit failure inside both fan-outs, then re-raise") satisfies AC-4,
proven by `make test-file FILE="tests/test_never_silent_failures.py::test_a_unit_failure_inside_a_fan_out_reaches_the_caller"`
plus a QA mutation verdict of REAL.

**Angle assigned:** negative space — untested states of the world.

**Verdict:** the AC-4 unit-level claim SURVIVED every attack I could mount. But the claim's
*usefulness* has three untested holes and the change ships one self-contradicting doc.

---

## What I could execute myself

Per the concurrency constraint I ran only `make lint` (pure ruff, no shared state) plus read-only
`git`/`grep`/file reads. Every container-touching command below is PROPOSED, never run by me.

- `make lint` → exit 0, `All checks passed!`. AC-15 re-derived, not taken on faith.

---

## F1 — The authoring half of S3 is a no-op in production (medium)

`record()` returns immediately when no scope is active (`src/tour/degradations.py:137-139`).
I enumerated every `degradation_scope` in `src/`:

```
src/api/routes/trips.py:55:from src.tour.degradations import degradation_scope, summarize
src/api/routes/trips.py:914:    with degradation_scope() as collected:
```

That is the `POST /trips/preview` wrapper only. The sole production caller of the authoring fan-out is
`src/api/routes/trips.py:630` inside `compose_trip` (`POST /trips/{id}/compose`, the phone on-ramp),
and it opens no scope. So the block S3 added at `src/tour/authoring.py:964-980` records into nothing
today: a stop that fails inside the phone's fan-out produces zero degradations anywhere.

The pinned test is green because the **test itself** opens the scope. That is a legitimate unit-level
proof of AC-4's wording ("reaches the caller's scope"), and AC-24 explicitly owns the missing scope
(step B8, `pending`). So this does not refute S3. It does mean S3's green must never be reported as
evidence that a phone-side compose failure is visible — it is not, on either channel, except as
whatever uvicorn logs from the bare 500.

**Carry-forward:** B8 must add `degradation_scope` around `compose_trip`, or half of S3 stays dead code.

## F2 — Heterogeneous multi-unit failures collapse to one wire row, and the survivor is a thread race (medium)

Both new call sites use a **constant** `kind` (`"premium_unit_failed"` / `"authoring_unit_failed"`).
`summarize` (`src/tour/degradations.py:152-166`) groups by `kind` alone and keeps the **first** row as
the example, discarding every later row's `error_type`, `error_message` and `stop_index` behind a count.

`Executor.map` submits every unit eagerly, so in a real outage all N stops run and all N record. If two
stops fail with *different* exceptions — a poisoned payload on stop 3 while stop 0 times out — the
operator sees exactly one row, and **which** one depends on which pool thread wins the `list.append`.
Nondeterministic diagnosis of a multi-fault tour.

The pinned test injects exactly one failure (`_FailingUnitExecutor(fail_stop_index=1)`), so this state
is never touched. AC-6 ("at least one row") still holds; AC-4's "the exception type, message and stop
index" does not, once more than one unit fails.

**Proposed test (does not exist yet, so no runnable repro):** two units failing with distinct exception
types; assert both types and both stop indices survive to `summarize`. Fix shape: key the summary on
`(kind, error_type)`, or fold the stop index into the kind.

## F3 — The preview wrapper throws away every degradation when the impl raises HTTPException (medium)

`src/api/routes/trips.py:914-917`:

```python
with degradation_scope() as collected:
    result = _preview_trip_impl(request, body, driver, premium_executor)
    rows = summarize(collected)
return result.model_copy(update={"degradations": rows}) if rows else result
```

`summarize` is inside the `with` **body**, not a `finally`. `_upstream_provider_errors`
(`trips.py:112-129`) maps provider throttling → `HTTPException(503)` and provider error/`TimeoutError`
→ `HTTPException(502)`, and `trips.py:1023` re-raises `HTTPException` untouched. So for exactly the
fault family AC-9 enumerates (`anthropic.RateLimitError`, `anthropic.APIError`, `TimeoutError`), S3's
freshly recorded degradation — including the stop index, which nothing else carries — is collected and
then dropped on the floor. The 502/503 detail string carries the message, so the cause is not fully
invisible; the stop index and the structured row are.

This is pre-existing in the wrapper, not introduced by S3, but S3 is the first thing to feed it.
`src/api/routes/trips.py` is S4's file — S4 should move the summarize into a `finally` (or an
`except HTTPException` that attaches rows) rather than leave AC-5/AC-6 resting on a channel that
disappears under the most common production fault.

## F4 — S3 left a docstring in its own file that contradicts the code it just wrote (low)

`tests/test_never_silent_failures.py:1` still opens `"""AC-2 / AC-3 — both premium fan-out sites…"""`
while the file now also holds the AC-4 test. Worse, lines 46-47 read:

> Nothing on the premium or authoring path calls ``record`` today, so no mutation of the current tree
> turns it red

S3 made that literally false in the same change — both fan-outs now call `record`. The project rule is
explicit ("A doc that contradicts the code gets corrected or deleted. Never left."), and the sentence
is the kind a future session acts on. One-line fix; must not ship as-is.

## F5 — Untested state: S3's new code has never run through a real HTTP entry point (low)

The whole S3 proof is a direct call to the two functions. Exactly one existing test drives a failing
executor through the real `/trips/preview` route —
`tests/test_trip_preview_contract.py::test_preview_never_scores_or_returns_mixed_fallback_as_an_llm_candidate`
(a `FailingExecutor` raising `ValueError` on every unit). After S3 that route now records one
degradation per unit and the response gains a `degradations` array it did not have before. The test
asserts named fields only and never asserts the array is absent, so I expect it green — but nobody has
run it. It is the cheapest available proof that S3's premium half works end-to-end and did not change
the wire contract.

**Proposed for the serial verifier (I did not run these):**
1. `make test-file FILE="tests/test_trip_preview_contract.py::test_preview_never_scores_or_returns_mixed_fallback_as_an_llm_candidate"`
2. `make test-file FILE="tests/test_never_silent_failures.py"` — whole file, proving S3's append did not
   disturb S2's pinned test living in the same module.

---

## Attacks that FAILED (why the AC-4 claim stands)

Each of these was a real attempt to break S3, traced through the source:

1. **Cross-request leakage under concurrent previews.** Two simultaneous `/trips/preview` calls each
   get their own `collected` list; `in_current_context` snapshots per call to `execute_premium_plan`,
   inside that request's scope; `snapshot.copy()` is shallow, so each worker shares only *its own*
   request's list. No path for request A's degradation to land in request B's response.
2. **Race between a worker's `record` and the scope closing.** `Executor.__exit__` is
   `shutdown(wait=True)` and runs even when the body raises, so every worker has finished before the
   exception leaves `execute_premium_plan`, and long before `degradation_scope.__exit__`. The
   `len(...) == 1` assertion is not flaky, and no record is lost.
3. **`record` masking the original exception.** `record` can only stringify and append; it has no
   raise path. The bare `raise` re-raises the original exception object with its original traceback,
   so `pytest.raises(_MarkerFailureError)` is not testing a rewrapped strawman.
4. **Adding `record` to the phone path crashing production.** `record` outside a scope returns, it does
   not raise (`degradations.py:137-139`). The new authoring block is inert, not fatal. (See F1.)
5. **Self-inflicted AC-10 violation.** S3 adds two broad `except Exception` blocks to the tour path —
   exactly what AC-10/S8 hunts. Both record AND re-raise, so both satisfy the criterion.
6. **Existing-test regression.** The only tests touching these fan-outs are
   `tests/test_tour_authoring_from_route.py`, `tests/test_tour_authoring_gates.py`,
   `tests/test_degradations.py` and the new file. Every failure-path test in the first is a
   *planning-time* `ValueError` raised before the fan-out, so none reaches the new code.
   No `scripts/` or `tools/` entry point calls either fan-out.
7. **Empty / oversized input.** Zero units already dies at `ThreadPoolExecutor(max_workers=0)` before
   any record — pre-existing, unchanged by S3. Oversized: `error_message` is untruncated by documented
   design, so N failing stops hold N full provider messages; documented, not introduced here.
8. **`contextvars.Context.copy()` availability.** Part of PEP 567 since 3.7; this machine runs 3.13.12
   (from the lint preflight banner). Not a version trap.
9. **Evidence-chain reconciliation.** The stash-scoped mutation (`premium_tour.py` + `authoring.py`
   only) leaves the degradations.py S1 fix in place, so the RED it produced is S3's absence and nothing
   else. `tests/test_never_silent_failures.py` is untracked, so a pathspec stash could not have taken
   it — consistent with the reported RED being the `len == 1` assertion rather than a collection error.
   The reported diffstat matches the tree I measured.

## Residual risk not covered by any S3 evidence

- A unit failure inside the premium fan-out that comes from `receipt_sink.after_call`
  (`src/tour/premium_tour.py:454`) is **outside** the new `try`, so it is unrecorded. Harmless today —
  the only sink on the live path is `EphemeralReceiptSink`, whose two methods are `del` statements —
  but the guard is narrower than AC-4's words ("a unit that fails INSIDE either fan-out").
