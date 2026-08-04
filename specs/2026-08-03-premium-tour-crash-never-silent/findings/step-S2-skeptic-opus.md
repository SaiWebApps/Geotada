# Step S2 — hostile skeptic (negative space)

**Verified against:** commit `68c4f723` on `main`, working tree dirty with the S1/S2 work
(`M src/tour/degradations.py`, `M tests/test_degradations.py`, `?? tests/test_never_silent_failures.py`).
**Angle assigned:** negative space — states of the world NOT tested.
**Run concurrently with another skeptic**, so the only command executed here is `make lint`.

## Verdict

The AC-2 half of the claim survives everything I threw at it. The AC-3 half, and the
sentence "no gap in either criterion", do not: AC-3's assertions were never executed on
the mutated tree, and the test's own docstring concedes no mutation of this tree can turn
them red. Nothing below is a blocker — I have no reproduction for any of it.

## What I attacked and FAILED to break

1. **Is the forced overlap actually forced, or is it the deleted no-op test wearing a
   handshake?** It is real. `_OverlapForcingExecutor.execute` increments `_arrived` under a
   lock and every non-final worker blocks on `self._release.wait(timeout=3.0)` *inside*
   `executor.execute`, which is inside `invoke`, which is inside `_run`. A worker that was
   never released records `False`, and `_assert_genuine_overlap` requires `all(...)`. I
   constructed the partial-overlap case (workers 0 and 1 park, time out, worker 2 arrives
   last and records `True`): `shook_hands == {0: False, 1: False, 2: True}` → `all()` is
   False → the test fails. The gate is sound; it cannot pass vacuously.
2. **Can the pool starve the rendezvous and produce a false red on a healthy tree?** No.
   Both fan-outs size the pool `min(max_workers, len(plan.units))` with `max_workers=6`, so
   3 units get exactly 3 threads, and `Executor.map` submits all items eagerly, spawning a
   thread per submit up to the cap. All three threads exist before any of them blocks.
3. **Do the pasted numbers reconcile?** Yes, and this is the strongest single point in the
   claim's favour. The mutation run takes 3.10s, which is precisely worker 0's 3.0s
   handshake timeout: under the restored bug worker 0 enters the shared `Context` and parks
   while workers 1 and 2 raise before ever reaching the rendezvous, so `_arrived` never
   reaches 3 and worker 0 times out. A fabricated or hand-edited transcript would not have
   produced that specific duration. The green runs at 0.02–0.03s are equally consistent
   (instant rendezvous, no timeout).
4. **Is the mutation the real production defect or a strawman?** Real. It reverts
   `snapshot.copy().run` to `snapshot.run` in `src/tour/degradations.py` and the RuntimeError
   surfaces at `degradations.py:105` through `execute_premium_plan`, which is the actual
   function `src/api/routes/trips.py:1013` calls. Not a mock, not a direct call to `_run`.
5. **Does the fix leak state between calls or between requests?** No — the reverse. The old
   `ctx.run` reused ONE `Context`, so a `ContextVar.set` inside worker 1 was visible to
   worker 2. `snapshot.copy().run` isolates every call. `src/tour/degradations.py:37`
   `_ACTIVE` is the only `ContextVar` in `src/`, and nothing on either fan-out path calls
   `set` on it, so no behaviour depended on the old leak.
6. **Thread reuse when units exceed workers.** I could not construct a failure: each `_run`
   invocation takes its own `snapshot.copy()`, so a reused worker thread never re-enters a
   live context. (It remains untested — see gap 5.)
7. **`make lint`** — run here, real exit code 0 (captured to a file, not through a pipe):
   `All checks passed!`. AC-15 holds at this commit.

## Gaps — negative space the evidence does not cover

### G1. AC-3 was never executed under the mutation, and cannot be turned red
Under the reverted wrapper the test dies in the AC-2 block (the `except RuntimeError` →
`AssertionError` at the premium fan-out), so lines 393-435 — the whole AC-3 section — never
ran on the mutated tree. The module docstring states this plainly: "the AC-3 empty-list
assertion is a canary, not a guard. Nothing on the premium or authoring path calls `record`
today, so no mutation of the current tree turns it red." I confirmed that independently:
the only `record()` producer in `src/` is `src/tour/glue_client.py:145`, and glue stitching
runs in `src/tour/generation.py` during the stitch phase, *before* either fan-out — so no
production code can record from inside either pool. The claim's "AC-2 and AC-3 are both
fully exercised … no gap in either criterion" therefore overstates: AC-3 is asserted on
green only, and the QA verdict of REAL is evidence about AC-2 alone.
*Severity: low. Not a defect; a misdescribed proof.*

### G2. The phone on-ramp is exercised with a configuration the phone never uses
`tests/test_never_silent_failures.py:378` calls `author_prebuilt_route(authoring_plan,
executor=...)` with all three gate arguments at their defaults
(`faithfulness_checker=None`, `enforce_claim_coverage=False`, `scan_glue_for_invention=False`).
The real phone route, `src/api/routes/trips.py:630`, passes a live checker and turns both
booleans ON. So the function name matches production but the call shape does not, and the
gated shape is the one that actually produced the tourist-facing HTTP 500 in D7.
*Severity: medium (coverage). The wrapper fix is configuration-independent, so I do not
predict a failure — but AC-2's proof for the phone surface is one argument list away from
the surface it claims to prove.*

### G3. A THIRD fan-out exists on the served tour path, unwrapped and unpinned
`src/tour/verify.py:238` opens `ThreadPoolExecutor(max_workers=min(8, ...))` and submits
`checker.entails` per sentence. It has no `in_current_context` at all. It is reachable only
on the gated path — i.e. exactly the phone configuration G2 skips — via
`compose_gate.py:124 → verify_faithfulness`. Consequences: (a) AC-2's "both fan-out sites"
and the `degradations.py` docstring's "the two compose fan-outs" are not the whole set of
tour-path thread pools, there are three; (b) any degradation recorded inside an entailment
call is dropped on the floor, which is precisely the invisibility that module exists to
prevent; (c) D4's stated reason for fixing the wrapper rather than the call sites — "leaves
the trap armed for a third" — is already realised, just in the opposite direction (this
site was never armed, so the wrapper fix does not reach it).
*Severity: medium, advisory. Out of S2's acceptance criteria, in scope for AC-10/S8's
"stop the CLASS of bug".*

### G4. A live data race inside that third pool
`src/tour/verify.py:120` `self.calls += 1` in `HaikuFaithfulnessChecker.entails` is a
non-atomic read-modify-write executed by up to 8 pool workers, so the reported call count
can undercount. Pre-existing, untouched by this step, and only cosmetic unless that number
is used for spend accounting.
*Severity: low.*

### G5. Empty and oversized plans are both untested
- **Zero units.** Both fan-outs compute `ThreadPoolExecutor(max_workers=min(max_workers,
  len(plan.units)))`. The guard above it, `if not 1 <= max_workers <= 8`, validates the
  *argument*, never the computed value, so an empty `plan.units` yields `max_workers=0` and
  CPython raises `ValueError: max_workers must be greater than 0` — a message that names
  nothing about tours. On the workbench that lands in the `except Exception` at
  `trips.py:1026` (silent HTTP 200 Basic fallback); on the phone the `except ValueError`
  at `trips.py:648` relabels it "a shape it cannot author". I did not establish that a
  zero-stop plan is reachable (upstream selection may guarantee ≥1), so this is a lead, not
  a defect. AC-2 covers 3 units, AC-3 covers 1, nothing covers 0.
- **Units greater than workers.** Production default is 6 workers; AC-21 records the
  workbench capping at 8 stops and the phone allowing up to 15. A 15-stop compose therefore
  runs 9 of its 15 calls on a REUSED worker thread — a state neither the 3-unit nor the
  1-unit case reaches. I believe the fix holds (see attack 6) but it is unproven. Note for
  whoever is tempted to "just raise N" in the test: the rendezvous requires N threads for N
  units, so raising the unit count past `max_workers` makes the test time out and go red for
  a reason that has nothing to do with the bug.
*Severity: low-medium, advisory.*

### G6. The test is wall-clock-timed on a machine this repo documents as shared
Passing requires all N workers to reach the rendezvous within `_HANDSHAKE_TIMEOUT_SECONDS
= 3.0`. `CLAUDE.md` warns that sibling sessions share this machine and that the `/team`
engine assumes exclusive use of the local containers. Under heavy load the test can go RED
for scheduling reasons, and its failure text ("the workers never overlapped … proves
nothing about the fan-out's re-entrancy") reads like a real defect. It fails closed, which
is the right direction, and 3s is a generous budget for three thread starts — but the repo's
own "no flake dismissal" rule means a future red here must not be re-run for green.
*Severity: low.*

### G7. Evidence-chain: the stash round trip cannot see the S2 artifact, and it ran on a shared tree
`tests/test_never_silent_failures.py` is UNTRACKED (`git status --short` → `??`). So the
claim's restore check — "`git diff --stat` matches the developer's original diff exactly
(degradations.py +22/-, test_degradations.py +107/-)" — is structurally blind to the file
step S2 actually delivers; `git diff` never reports untracked content. The restore of the
*tracked* fix is properly evidenced; the S2 test file's integrity across the stash window is
evidenced only by the test passing again afterwards. Separately, `git stash push` mutates
the shared working tree: for the ~3 seconds of the mutation run the repository on disk
contained the known-broken wrapper, so any sibling session or concurrent skeptic reading or
testing the tree in that window would have seen a phantom failure.
*Severity: low.*

## Bottom line

Nothing here blocks. The concurrency proof for AC-2 is genuine, the mutation is the real
production defect reached through the real call site, and the timings reconcile with the
mechanism rather than merely being plausible. What should be corrected is the claim's
scope: it proves AC-2, and it *asserts* AC-3 without proving it, and "both fan-out sites"
is two of the three thread pools a served tour can open.
