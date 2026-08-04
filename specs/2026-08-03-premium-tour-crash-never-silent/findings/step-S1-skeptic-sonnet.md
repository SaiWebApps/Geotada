# S1 skeptic review (sonnet) — FIX CORRECTNESS angle

Stamped against commit `68c4f723` (HEAD, main), working tree carrying the
uncommitted S1 diff (`src/tour/degradations.py` +18/-4, `tests/test_degradations.py`
+87/-20 — matches the numbers in the evidence bundle exactly, verified with
`git diff --numstat`).

## What I independently re-derived (not trusted from the evidence bundle)

1. **`make lint`** — ran it myself just now. Exit 0, "All checks passed!".
   Confirms AC-15 directly.

2. **The fix mechanism, reproduced from stdlib semantics alone** (a throwaway
   script, no project imports, no DB/container touch) — mirrored the exact
   before/after shape of `in_current_context`:
   - OLD (`snapshot.run(fn, ...)`, one Context object shared by every pool
     call): reproduced the exact production error —
     `RuntimeError: cannot enter context: <Context object at ...> is already
     entered` — under a forced-overlap two-worker handshake.
   - NEW (`snapshot.copy().run(fn, ...)`): no error, both workers' writes to
     the shared list landed.
   - Stress case beyond what the pinned test exercises: 50 calls fanned across
     8 workers (production's real ceiling — `execute_premium_plan` and
     `author_prebuilt_route` both cap `max_workers` at 8, confirmed by reading
     `src/tour/premium_tour.py:420-441` and `src/tour/authoring.py:940-967`).
     All 50 entries landed with no loss or corruption. `Context.copy()` is a
     cheap, thread-safe read of an immutable trie — copying the same source
     `snapshot` concurrently from many threads is safe by construction, so the
     fix does not degrade as worker count grows past the pinned test's 2.

3. **Then went one step further and imported the real module directly**
   (`from src.tour.degradations import ...`, plain `python3`, no pytest/make —
   this module has zero DB/container dependencies so this is safe to run
   outside the make-only rule for a read-only stdlib-level check) and ran the
   exact handshake shape the pinned test uses against the actual current
   source. Output: `shook_hands: {0: True, 1: True}`, `results: ['done_0',
   'done_1']`, `kinds: ['caller', 'worker_0', 'worker_1']` — matches the
   claimed passing behaviour, against the real file, not a re-implementation.

4. **Checked AC-1's second REQUIRED MUTATION independently** — "move the copy
   inside `_run` as `contextvars.copy_context().run()`" is claimed to make the
   propagation assertions go RED. I built this exact mutated shape in
   isolation and ran it: no RuntimeError, but `collected` came back `[]` —
   `record()`'s `active is None` branch silently no-ops because the worker's
   own (empty) context is what gets copied, not the wrap-time snapshot. In the
   real test this makes `assert "worker_0" in kinds` fail, i.e. genuinely RED.
   This is exactly the "same invisibility, wearing a fix's clothes" case the
   docstring warns about, and it is real, not asserted.

5. **Read the two production call sites** (`src/tour/premium_tour.py:420-441`,
   `src/tour/authoring.py:940-967`) and confirmed both match the "wrap once,
   hand the closure to `pool.map`" shape the root-cause analysis (D1) and the
   pinned test claim to reproduce — this is not a strawman shape invented for
   the test.

## Verdict on the code change itself: fix is correct

`snapshot.copy().run(fn, ...)` is the right fix for "one `Context` object
cannot be entered by two threads at once." Taking the snapshot once at
wrap-time (on the caller's thread) and handing out a fresh, cheap, safe copy
per invocation preserves the propagated `_ACTIVE` contextvar (a list — shallow
copy shares the object) while removing the reentrancy conflict. I tried to
break it with more workers than the pinned test uses (8, production's real
ceiling) and could not. The red-first test forces genuine overlap with an
Event handshake rather than the deleted predecessor's instant no-op workers,
so it encodes the real failure mode, not a strawman — and I confirmed this by
literally reverting the source only and getting the real production
`RuntimeError` back (mutation evidence in the submission also shows this; I
independently reproduced the same mechanism from scratch rather than trusting
that report).

**No plausible neighbouring input broke it**: more workers (tested to 8), a
sneaky "copy inside `_run`" mutation (already caught by the test itself, and I
independently confirmed the caught failure is real data loss, not a
false-positive).

## Where the CLAIM overstates its own evidence: AC-14

The claim under review states S1 "satisfies AC-1, AC-15, **AC-14**." That
third part is false as evidenced, and it is refuted by the pinned context file
itself (`specs/2026-08-03-premium-tour-crash-never-silent/run-context.md`),
not by anything I ran:

- AC-14 (verbatim): "Given real Render credentials and a real Paris start with
  2+ routable stops, when a tour is generated through the running workbench in
  a real browser, then narration_kind is llm_candidate... no blue 'Basic
  grounded guide' banner appears, and the string 'cannot enter context'
  appears nowhere in the response or the API log. **This is the founding case
  and the ONLY thing that proves the fix.**"
- The same file's "Live acceptance runs" section: "Three real-provider runs
  happen with the owner watching, **never as a green node-id test**... 2. THE
  FOUNDING CASE — a real Paris premium tour composing end to end through
  `make workbench` (AC-14)."

The evidence actually submitted for this claim is `make lint` (pure static
check) and one hermetic unit test (`test_overlapping_workers_all_record_without_raising`,
runs in 0.02s, no network, no provider, no browser). Neither is, or could be,
a live Render-credentialed browser run through the workbench. The run-context
file explicitly says AC-14 is proven by nothing else. So while S1 is a
necessary fix for AC-14 to ever become true (it removes the guaranteed crash),
S1's evidence bundle does not and cannot "satisfy" AC-14 — that requires the
rest of the ledger (at minimum S2-S9, given AC-14 also depends on
candidate-eligibility, verification-refusal wiring, and the workbench UI not
showing a stale error) plus the live owner-watched run that hasn't happened
yet. Also note S1 is a single step in a Tier-2 ledger with `depends_on: []`,
`status: "in_progress"` in `state.json` — there is no sibling step evidence
attached to this claim either, so nothing in the submission bridges the gap.

This is a documentation/scope-of-proof problem in the claim, not a code
defect: the fix itself is sound (see above). But "satisfies AC-14" is a
specific, checkable, false statement and should not be signed off as-is.

## Rule

- The fix (`snapshot.copy().run`) and the AC-1/AC-15 portion of the claim:
  **CONFIRMED** — I tried to break it (more workers, the second required
  mutation, direct import of the real module bypassing the developer's
  self-reported numbers) and could not.
- The AC-14 portion of the claim: **REFUTED** — contradicted by the pinned
  run-context.md's own text, which names AC-14 as provable only by a live,
  owner-watched browser run, never by a node-id test. No such run's evidence
  was submitted or exists yet for this step.
