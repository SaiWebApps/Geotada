# Step S1 — hostile skeptic (negative space), re-run

**Verified against:** commit `68c4f72329830c2faf90a495d30233a0daa35cc2` (`68c4f723`, main),
plus the uncommitted working-tree change. `git diff --stat` at the moment of review:
`src/tour/degradations.py` +18/-4 and `tests/test_degradations.py` +87/-20, total
105 insertions / 24 deletions across two files — which reconciles EXACTLY with the
numbers in the handed evidence. No SHA, count or diff-stat in the evidence chain is off.

**Note on the previous version of this file:** it was written against a test file with
+68/-18 and its central complaint was that the test did not assert the overlap actually
happened. The tree has moved: the current test opens with
`assert shook_hands == {0: True, 1: True}` before any other assertion. That objection is
now closed and is not repeated below.

**Angle:** negative space — untested states of the world. Concurrency width, nested and
recursive entry, degraded/failing input, two requests in one process, the same code path
reached by a different entry point, the fix's own infrastructure side effects.

**What I executed myself:** `make lint` (exit 0), and a stdlib-only semantics probe run
under the project's exact interpreter (`cpython-3.13.12`, the same build `make lint`
reports). The probe imports NOTHING from the repo and touches no database, container,
port or `.dart_tool` — it re-implements the 20 lines of the wrapper and drives them
through states the pinned test never enters. A sibling skeptic is running concurrently,
so every container-touching target below is PROPOSED, never run by me.

---

## Verdict

**The mechanism is CONFIRMED. The claim is REFUTED as written**, because it claims AC-14.

- **AC-15 — CONFIRMED.** `make lint` re-run by me, exit 0, "All checks passed!". Not piped
  through `tail`/`head`; full output captured.
- **AC-1's mechanism — CONFIRMED.** I attacked it six ways on the real interpreter and
  failed to break it (list below). The `.copy()` is doing exactly what the docstring says.
- **AC-1's evidence — INCOMPLETE.** AC-1 names TWO required mutations. Only one was run.
- **AC-14 — REFUTED as a claim.** Nothing in the evidence is a live run of anything.

---

## F1 (blocking on the claim, not on the code) — S1 claims AC-14 with zero live evidence

`state.json` step S1 carries `criterion_ids: ["AC-1", "AC-15", "AC-14"]`.

AC-14 reads: *"Given real Render credentials and a real Paris start with 2+ routable
stops, when a tour is generated through the running workbench in a real browser, then
narration_kind is llm_candidate, compose_status is composed, every stop carries non-empty
narration, no blue 'Basic grounded guide' banner appears, and the string 'cannot enter
context' appears nowhere in the response or the API log. This is the founding case and the
ONLY thing that proves the fix."*

The handed evidence is: `make lint` twice, one hermetic node-id test, one revert, one
re-run. There is no browser, no credential, no Paris start, no tour, no API log. Not one
byte of AC-14's subject matter appears.

This is not a technicality. The same ledger's own `run-context.md` says so, in the section
titled **"Live acceptance runs (NOT engine steps)"**: *"THE FOUNDING CASE — a real Paris
premium tour composing end to end through `make workbench` (AC-14)."* The ledger already
knows AC-14 cannot be closed by an engine step, and S1 claims it anyway.

It is also structurally impossible for S1 alone to satisfy AC-14. AC-14 requires that no
blue Basic banner appears — and per decision D3, `src/api/routes/trips.py` catches
`except Exception:` and falls back to the Basic lane on ANY premium failure. So AC-14
passing depends on every other failure mode on that path being absent, which is what
S2–S9 exist to establish. And per AC-20 the workbench still substitutes
`MockFaithfulnessChecker`, so even a green live run would not yet be the phone's tour.

**Consequence if rubber-stamped:** the ledger records "the founding case is proven" when
nobody has generated a tour. That is the exact failure the project's own rules name — a
user-facing behaviour claim with no functional proof a human can see.

**Remedy:** drop `AC-14` from S1's `criterion_ids` and leave it where the run-context
already puts it, in the owner-watched live run. Nothing about the code needs to change.

---

## F2 — I attacked the wrapper six ways on Python 3.13.12 and could not break it

Probe run with `~/.local/share/uv/python/cpython-3.13.12-macos-aarch64-none/bin/python3.13`
on a scratch file (stdlib only). `FIXED` = `snapshot.copy().run`, `OLD` = the HEAD code
`ctx.run`, `MUT_B` = AC-1's second required mutation `contextvars.copy_context().run`
inside `_run`.

| Attack (state the pinned test never enters) | FIXED | OLD (pre-fix) |
|---|---|---|
| Production width: 6 workers, 12 units, all emitting the SAME kind (`glue_call_failed`, the one kind production actually emits), first wave forced simultaneous by a Barrier | 12 results, **12 degradations collected** | crashes (BrokenBarrier — the workers die before they can even meet) |
| NESTED fan-out: a wrapped worker that itself wraps a callable and fans out again | 12 records, no raise | `RuntimeError: cannot enter context` |
| RECURSION: the same wrapped closure invoked from inside itself, one thread | 4 records, no raise | `RuntimeError: cannot enter context` |
| SINGLE unit (AC-3's negative — the shape that worked throughout the outage) | succeeds, degradation list **empty** — it does not start crying wolf | succeeds, empty |
| TWO concurrent requests in one process, 3 workers each (a live server, two tourists) | `{A: [A0,A1,A2], B: [B0,B1,B2]}` — no cross-request leakage | n/a |
| AC-1's second mutation `MUT_B` | n/a | **12 results, 0 degradations** — it silently drops everything, exactly as the docstring predicts |

The last row is the important one: I independently re-derived that AC-1's *second* required
mutation genuinely goes RED on the propagation assertions, without needing to run the suite.
A worker thread starts with an empty context, so `copy_context()` inside `_run` finds no
active scope and `record` becomes a no-op. `worker_0 in kinds` cannot hold.

I also checked the shape the OLD code takes under the new test and the arithmetic
reconciles: worker 0 parks for the full 3.0s handshake timeout, so a RED run must take
just over three seconds. The evidence reports `1 failed in 3.10s`. It fits.

**I could not construct any input, width, nesting depth or concurrency pattern where the
shipped wrapper raises or loses a degradation.**

---

## F3 (medium) — AC-1 requires two mutations; the evidence contains one

AC-1, verbatim: *"REQUIRED MUTATION: restore the single wrap-time context ... and this goes
RED with 'cannot enter context'; **separately**, move the copy inside `_run` as
`contextvars.copy_context().run` and the propagation assertion goes RED."*

The QA verdict ran only the first (`git checkout -- src/tour/degradations.py`, which
restores HEAD's `ctx.run`). The test's own docstring asserts *"UNDO TESTS, all three
EXECUTED"*, but no transcript for the other two is attached, and this project's standing
rule is that a guard nobody has been shown turning red does not exist.

I have shown by independent execution (F2, `MUT_B` row) that it *would* go red. That is
reasoning about the mechanism on an isolated copy — it is not the pinned test going red.

**PROPOSED for the serial verifier** (I did not run these; each needs the shared containers):

```
# mutation (b) — must go RED on "the first worker's degradation was DROPPED"
#   edit src/tour/degradations.py:119 to:
#       return contextvars.copy_context().run(fn, *args, **kwargs)
make test-file FILE="tests/test_degradations.py::test_overlapping_workers_all_record_without_raising"

# mutation (c) — must go RED on the handshake assertion, after ~3s
#   edit tests/test_degradations.py:143 to ThreadPoolExecutor(max_workers=1)
make test-file FILE="tests/test_degradations.py::test_overlapping_workers_all_record_without_raising"

# and the whole file, to prove the deletion of the old test broke no sibling
make test-file FILE="tests/test_degradations.py"
```

I confirmed there are no stale references to the deleted test name anywhere in the tree
outside this spec folder (`grep -rn` across the repo: only `state.json`, `run-context.md`
and the test's own docstring). Deleting it breaks no manifest and no count guard.

---

## F4 (medium, and it lands on S3 not S1) — a failing unit CANCELS its siblings, so only the FIRST failure ever produces a degradation

MEASURED in the probe, on 3.13.12, identical under FIXED and OLD (so this is **not** an S1
regression — it is untested space S1's claim walks past):

Two units, unit 0 raises `RuntimeError("MARKER-9f3c")` after recording, unit 1 waits for it
then records. Collected: `['boom_recorded']`. The sibling's `'sibling'` row **is missing**.

Cause: `Executor.map` returns a generator whose `finally` clause cancels every still-pending
future when the generator is torn down by the exception. Unit 1 was cancelled before it ran.

Why it matters here: AC-1 as written is *"BOTH workers' degradations reach the caller's
collector"*, and the S1 test proves that only on the happy path. AC-4 (step S3) asserts
*"a degradation carrying the exception type, message and stop index reaches the caller's
scope"* — that will hold for the first failure and silently not hold for any concurrent
second failure. A tour where two stops fail will report one. If S3's test is written with
the failing unit at index 0 and a 2-unit plan, it will pass while proving nothing about the
multi-failure case.

**PROPOSED, for whoever writes S3:** assert that a fan-out where units 0 AND 1 both fail
produces two degradation rows, not one. I expect that to go RED today.

---

## F5 (low, advisory) — a third fan-out on the SHARED path is still unwrapped

`src/tour/verify.py:238` runs `pool.submit(checker.entails, ...)` across up to 8 workers
(`_FAITHFULNESS_MAX_WORKERS`) with **no** `in_current_context`. This sits inside
`finalize_certification_composition`, which per decision D0 is the finaliser BOTH surfaces
share, so it is the same code path reached by a different entry point.

Nothing on that path calls `record()` today, so nothing is being dropped right now. But the
sibling test `test_an_unwrapped_worker_still_loses_it_so_the_wrapper_is_load_bearing`
codifies the rule that unwrapped means lost, and this is the identical trap sitting armed on
the most-shared function in the system. The moment anyone adds a degradation to the
faithfulness path — which is precisely what a "never silent" ledger invites — it vanishes.

Two smaller things in the same pool, both pre-existing and out of this ledger's scope:
`HaikuFaithfulnessChecker.entails` does `self.calls += 1` (a non-atomic read-modify-write)
under 8 concurrent workers, so its call count undercounts; and `MockFaithfulnessChecker`
appends to `self.calls` from those workers, so any test asserting call ORDER there is
nondeterministic.

---

## F6 (low, latent) — a wrapped closure outlives the request it captured

MEASURED: a closure wrapped inside a `degradation_scope()` and invoked AFTER that scope
exits still appends into the finished request's list. The snapshot holds a hard reference to
the collector forever.

Not reachable today — both fan-out sites wrap inline and call within the same `with` block.
It becomes a live cross-request bug the day anyone caches or memoises a wrapped callable on
a long-lived object. Worth one line in the docstring; not worth a code change now.

---

## F7 (low, evidence-chain) — the "$0" proof cannot be independently re-derived by a parallel reviewer

`Makefile:217-225`: `test-file` declares `$(PRE_PYTEST)` and runs under `$(TEST_EXEC)`. So
the pinned S1 command starts the test and dev Neo4j containers, provisions dev data, brings
up Valhalla and fetches the full Render service environment — to run a test whose only
import is `contextvars` and `threading`. This is documented project behaviour, not a new
defect, but it is why F3's mutations and the pinned test itself stay PROPOSED in this
review: a concurrent skeptic cannot re-run the single command the claim rests on without
corrupting a sibling's run. Treat every "verified" line in the handed evidence that came
from `make test-file` as single-sourced until the serial verifier repeats it.

---

## Attacks I ran that FAILED to break the claim

So the confirmation means something, here is everything I tried:

1. Six workers, twelve units, one shared closure, identical degradation kind, forced
   simultaneous — no raise, nothing lost.
2. Nested fan-out (a wrapped worker that wraps and fans out again) — no raise.
3. Recursion through the same wrapped closure on one thread — no raise.
4. Two concurrent request scopes in one process — no cross-talk, no leakage.
5. Single-unit plan (AC-3's negative) — still succeeds, degradation list still empty.
6. AC-1's second mutation, executed on an isolated copy — confirmed it drops everything,
   so the test's propagation assertions really are load-bearing.
7. Diff-stat, SHA and timing arithmetic in the handed evidence versus the live repo — all
   three reconcile exactly (105/24, `68c4f723`, 3.10s ≈ the 3.0s handshake timeout).
8. Searched the whole tree for stale references to the deleted test and for a suite-count
   or manifest guard that its removal would break — none exist.
9. `make lint`, re-run by me, unpiped — exit 0.
