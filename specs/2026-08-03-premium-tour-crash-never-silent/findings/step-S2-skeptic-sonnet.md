# S2 skeptic review — FIX CORRECTNESS angle

Verified against commit `68c4f7232983` on `main` (working tree has the uncommitted
S2 changes: `src/tour/degradations.py`, `tests/test_degradations.py`, new
`tests/test_never_silent_failures.py`).

## What I independently checked (not just re-read the pasted evidence)

1. **Read the actual diff.** `src/tour/degradations.py`'s `in_current_context`
   changed from `ctx = contextvars.copy_context(); ... ctx.run(fn, ...)` (one
   `Context` object, entered by every worker) to
   `snapshot = contextvars.copy_context(); ... snapshot.copy().run(fn, ...)`
   (a **fresh** `Context` copy taken on every call). `git diff --stat` matches the
   claimed shape exactly: `degradations.py | 22 ++++++++--`,
   `test_degradations.py | 107 ++++...`.

2. **Confirmed there are exactly two production call sites** of
   `in_current_context` (`grep -rn in_current_context src/`):
   `src/tour/premium_tour.py:443` (`pool.map(in_current_context(invoke), plan.units)`)
   and `src/tour/authoring.py:966`
   (`pool.map(in_current_context(executor.execute), plan.units)`). This matches
   D1's claim and matters for AC-1's "leaves the trap armed for a third" concern:
   the fix lives in the shared helper, not duplicated per call site, so a future
   third fan-out gets the fix for free — the right shape, not a local patch.

3. **Confirmed pool sizing matches the test's forced-overlap unit count.** Both
   call sites use `ThreadPoolExecutor(max_workers=min(6, len(plan.units)))`. The
   test forces exactly 3 units, so `min(6,3)=3` — all 3 run as genuinely
   concurrent OS threads, matching the rendezvous the test constructs. No
   mismatch that would make the "forced overlap" claim vacuous.

4. **Reproduced the underlying mechanism myself, outside the repo's Makefile, in
   a hermetic standalone Python snippet** (pure stdlib `contextvars` +
   `ThreadPoolExecutor`, no DB/containers touched) mirroring the exact old vs.
   new wrapper shapes with a real `threading.Event` handshake forcing two workers
   to be inside the wrapper simultaneously:
   - OLD shape (`ctx.run` on one shared `Context`): **5/5 runs raised**
     `RuntimeError: cannot enter context: ... is already entered`.
   - NEW shape (`snapshot.copy().run` per call): **5/5 runs succeeded**, and the
     caller's collected list correctly received both workers' contributions
     (`[1, 0]` — order varies, membership doesn't).
   This independently confirms the causal mechanism the claim describes, not
   just the pasted transcript.

5. **Confirmed the test's fixture path is genuinely offline/pure.**
   `plan_prebuilt_route_authoring`'s own docstring says "Pure and provider-free:
   no routing client, no corpus snapshot, no selection." — so the pinned test
   does not depend on live Neo4j/Valhalla/provider state, consistent with it
   being $0 and with the developer's claimed 0.02s/3.10s timings (a 3.10s
   mutation-failure runtime is exactly what you'd expect: the raising worker's
   exception surfaces almost instantly via `pool.map`'s lazy iteration, but
   `ThreadPoolExecutor.__exit__` still blocks on `shutdown(wait=True)` for the
   sibling worker(s) parked on a 3.0s `Event.wait` timeout before the `with`
   block can unwind — that's where the ~3s comes from, and it is consistent with
   a real repro rather than a fabricated number).

6. **Ran `make lint` myself** (the only command I was cleared to run given a
   concurrent sibling skeptic): exit 0, "All checks passed!" — matches AC-15 and
   the pasted evidence.

7. **Checked for a "plausible neighbouring input" that would still break it:**
   more units than `max_workers` (real premium tours can have up to 15 stops per
   AC-21, workers capped at 6) means threads get reused across sequential
   `pool.map` batches. This is not a problem for the fix: `snapshot.copy()` is
   taken **fresh on every call** to `_run`, so thread reuse across batches never
   shares a `Context` object — each call gets its own copy regardless of which
   OS thread executes it. I could not find a call shape in the current tree
   (checked via the same grep) where `in_current_context` is nested inside
   another pool worker, so the "nested fan-out" case D4 mentions verifying at
   plan time is currently moot in production, though nothing in the test proves
   it — that's a gap in *coverage*, not in *correctness* of the shipped fix.

## What I did NOT run myself (left for the serial verifier / trusted from the pasted transcript)

- The actual pinned command,
  `make test-file FILE="tests/test_never_silent_failures.py::test_both_fan_outs_run_units_concurrently_without_context_error"`,
  and the paired mutation run (`git stash push -- src/tour/degradations.py` then
  re-run) — these touch the shared PRE_PYTEST containers (7688 DB etc.), which I
  was explicitly told not to run concurrently with a sibling skeptic. I instead
  reproduced the causal mechanism hermetically in raw Python (step 4 above),
  which corroborates the claimed RED/GREEN transition without needing the
  shared infra.

## Verdict

**CONFIRMED** for fix correctness on this angle. The code change is the textbook-
correct fix for "a `contextvars.Context` cannot be entered by two threads at
once" (take a fresh `Context.copy()` per call rather than reusing one snapshot
across concurrent threads), it lives in the one shared helper both fan-outs use
(closing, not just patching, the AC-1 "third site" hole), the pool sizing in
both call sites is consistent with the test's forced-3-way overlap, and I
independently reproduced the exact RED/GREEN mechanism outside the pasted
transcript. The test reaches real production entry points
(`execute_premium_plan`, `author_prebuilt_route`) through an offline/pure data
path, not a mock of the wrapper itself, so it is not testing a strawman.

**Not fully closed by me:** whether the pinned `make test-file` command actually
passes/fails as claimed *on this machine, at this exact working tree state* — I
did not execute it myself (shared-container restriction). A serial verifier
should still run the exact pinned command and the stash/pop mutation to nail
that down as directly observed rather than inferred from an independent
hermetic repro.
