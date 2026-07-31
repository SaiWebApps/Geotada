# Skeptic panel — step A3 ("Cut POST /trips/{id}/compose over to the seam")

**Verified against commit:** `c8ec39690030901660c843d46910bedb40e84c13` (working tree, tree is
dirty with A1/A2/A3-in-progress uncommitted changes — matches state.json: A1/A2
`status: completed, commit: pending`, A3 `status: in_progress`).

**Angle assigned:** FIX CORRECTNESS — is the change itself right, and does the red-first test
encode the ORIGINAL failure mode or a strawman? Would a plausible neighbouring input still
break it?

## What I re-derived myself

- `git diff src/api/routes/trips.py` (full diff read, not trusted from the evidence bundle).
- `git diff --stat` / `git status --short` at repo root: matches the claimed 17 modified +
  4 new/untracked files.
- Read `tests/test_trip_api.py::test_compose_authors_per_stop_and_keeps_the_wire_contract`
  in full (lines 651-777), plus its three provider test doubles
  (`_HallucinatingExecutor`, `_PerStopCountingExecutor`, `_MarkerAuthoringExecutor`).
- Read `src/tour/authoring.py::plan_prebuilt_route_authoring`, `::author_prebuilt_route`,
  `::finalize_certification_composition` in full.
- Read `src/tour/compose_gate.py::build_full_verifier`.
- Read `src/tour/verify.py::MockFaithfulnessChecker`.
- Read `src/tour/validation.py::validate_script` / `::validate_source_traceability`.
- Read `src/api/dependencies.py::get_faithfulness_checker` / `::get_compose_client`.
- Diffed the OLD `compose_script` (`git show HEAD:src/tour/compose.py`, lines 1341-1374)
  against the new `finalize_certification_composition` call chain.
- Ran `make lint` myself (pure ruff, no shared state): **exit 0, "All checks passed!"** —
  matches the claimed evidence.

I did NOT run `make test-file` myself (shared 7688 DB / Valhalla — reserved for the serial
verifier per the concurrency rule). The AC-3/AC-7 mutation evidence pasted in the claim was
cross-checked by static reading only, not re-executed.

## AC-3 / AC-7 as narrowly scoped: evidence holds up under static review

- The 409 `already_composed` check (`src/api/routes/trips.py:673-677`) unconditionally
  precedes `plan_prebuilt_route_authoring` / `_spend_precheck` (first reachable at line
  763-773), so AC-7's "runs AFTER the 409 already_composed check" clause is structurally
  true in the code as written.
- `plan_prebuilt_route_authoring` is genuinely provider-free (no executor/client call inside
  it — confirmed by reading its full body, `src/tour/authoring.py:729-805`), so computing
  `planned_calls=len(plan.units)` before `_spend_precheck` cannot leak an unreserved call.
- `COMPOSE_ATTEMPTS = 1` is consistent everywhere it is used (`ComposeVerificationError`'s own
  `attempts` field is also hardcoded to `1` at `finalize_certification_composition`'s raise
  site, `authoring.py:654`), so there is no attempts-source inconsistency.
- Minor, non-blocking test-hygiene defect: the assertion message at
  `tests/test_trip_api.py:770-773` — `"the 409 reserved spend — the precheck still runs
  before the already_composed check"` — is **backwards**. The assertion itself
  (`len(_global_hits) == n_stops`, i.e. unchanged after the duplicate call) correctly proves
  the precheck did **NOT** run again on the 409 path, i.e. the precheck runs AFTER (not
  "still runs before") the already-composed check, matching AC-7. The code and the
  assertion are both right; only the English comment contradicts them. Not blocking, but a
  future reader following that comment would draw the wrong conclusion.
- Second-order QA-methodology gap (not blocking on its own): the evidence's one "surgical
  mutation" bundled two independent changes at once — moving `_spend_precheck` above the 409
  check AND reverting `planned_calls` to a flat `1`. The pasted RED transcript
  (`assert 1 == 7` at line 735) is fully explained by the flat-count regression alone; the
  test never actually reached the order-sensitive assertion at line 770 during that run, so
  the "runs after 409" half of AC-7 was not independently exercised by the mutation as
  executed, only proven by static reading. The test DOES contain a structurally correct,
  order-sensitive assertion (line 770) that would fail if only the ordering (not the count)
  regressed — I just could not confirm this without running it myself, so it stays UNPROVEN
  by execution, CONFIRMED by static reading.

None of the above refutes AC-3/AC-7 as tested. **The real problem is one level up: what the
change (correctly satisfying AC-3/AC-7) silently does to the persisted write path's safety
properties that AC-3/AC-7 never touch.**

## CRITICAL finding: the cutover strips ALL THREE of D3's named anti-hallucination gates from the persisted (Neo4j-writing, real-spend) compose path — not deferred to A4, dropped now

D3-gate-parity's decision text says the persisted path "keeps the anti-hallucination gates it
has today: real HaikuFaithfulnessChecker entailment + claims_realized_by coverage baseline +
full validate_script (forbidden-phrase/proper-noun/year scan)". A2's own proof text flagged a
version of this risk ("weaker anti-hallucination... briefly"). Reading the actual code shows
it is not a partial weakening — it is the **complete absence of all three gates**, replaced by
bare source-ID traceability only:

1. **Real faithfulness entailment → gone.** The old `compose_trip` route had
   `faithfulness_checker: FaithfulnessChecker | None = Depends(get_faithfulness_checker)` in
   its signature (removed by this diff) and passed it into `compose_script(...,
   faithfulness_checker=faithfulness_checker)`. `get_faithfulness_checker()`
   (`src/api/dependencies.py:143-151`) is documented "ALWAYS the real Haiku checker...
   M-7: the real compose is never gated by the trusting Mock." The new `compose_trip` no
   longer has this dependency at all (deleted from the `Depends()` list and from the
   import block). `author_prebuilt_route` → `finalize_certification_composition` →
   `build_full_verifier` is called with **no `faithfulness_checker` argument**
   (`src/tour/authoring.py:608-613`), so `build_full_verifier` falls back to
   `checker = faithfulness_checker or MockFaithfulnessChecker()`
   (`src/tour/compose_gate.py:331`). `MockFaithfulnessChecker.entails()`
   (`src/tour/verify.py:83-85`) unconditionally `return True` — its own docstring says
   "Tests inject a stub to exercise failures; **production wires the Haiku checker**."
   Production, post-A3, no longer does.
2. **Coverage baseline → gone.** The old `compose_script` computed
   `expected_claim_ids = claims_realized_by(stitched, request.beats_by_id)`
   **unconditionally, internally** (`git show HEAD:src/tour/compose.py:1364-1367`) — every
   persisted compose got this check whether the caller asked for it or not. The new
   `finalize_certification_composition` calls `build_full_verifier(...)` with no
   `expected_claim_ids` argument, so `coverage = ()` — a permanent no-op
   (`src/tour/compose_gate.py:341-345`).
3. **Full `validate_script` (forbidden-phrase/proper-noun/year scan) → gone.** The old
   `compose_script` relied on `build_full_verifier`'s DEFAULT `base_validator=validate_script`
   (never overridden it). `validate_script` = `validate_source_traceability` +
   `_forbidden_phrase_hits` (`src/tour/validation.py:96-102`). The new
   `finalize_certification_composition` explicitly overrides
   `base_validator=validate_authorized_sources` (`src/tour/authoring.py:599-613`), a local
   wrapper that calls `validate_source_traceability` ONLY — the forbidden-phrase/proper-noun/
   year scan half of `validate_script` is never invoked on this path.

Net effect: after A3's cutover, `/trips/{id}/compose` — the endpoint that writes narration
into Neo4j and that D2 explicitly protects with "the 422 is the only thing keeping a failed
tour out of Neo4j" — spends real Anthropic money (`AnthropicPremiumExecutor`,
`cost_bearing = True`) per stop and verifies the result with **structural citation-ID
traceability only**. A sentence that cites a real, valid beat but states a fabricated
specific fact, a forbidden phrase, an invented superlative, or a wrong year will sail through
as 200 and be persisted — exactly the class of defect the pipeline guardrails
(`CLAUDE.md`: "Never auto-resolve: living people, superlatives, story deletions") and the
2026-07-19 same-day revert (cited by D2 itself) exist to prevent.

This is NOT something AC-3 or AC-7 tests for (neither one mentions faithfulness/coverage/
forbidden-phrase), so **it does not refute the specific claim under review**. It is squarely
a "is the change itself right" finding: the step's own name says "wire contract preserved,"
which is true of the *shape*, but silently discards the *safety property* the shape exists to
protect, with no test in the pinned node id (or anywhere in AC-3/AC-7) that would catch it.
A4 (`AC-5`, not yet built, `depends_on: ["A3"]`) is where the ledger plans to re-add these
gates via "injectable params into the per-stop finalize" (D3 text) — so this is a real,
already-partially-disclosed gap (A2's proof text flagged a milder version of it), but the A3
claim under review does not mention it at all, and if A3's commit ever lands on `main` and is
pushed/deployed before A4 also lands, the live persisted-compose endpoint runs with real spend
and zero content-faithfulness protection.

**Recommendation:** do not commit A3 in isolation, or if the ledger's mechanics require a
commit per step, do not push/deploy `main` between A3's commit and A4's commit. State this
explicitly in A3's judge ruling and commit message, not just in a carried-forward proof note.

## Repro (static, safe — no shared state touched)

```
grep -n "def finalize_certification_composition\|def build_full_verifier" -A 15 \
  src/tour/authoring.py src/tour/compose_gate.py | grep -E "def |faithfulness_checker|expected_claim_ids"
```
Output confirms `finalize_certification_composition` never passes `faithfulness_checker=` or
`expected_claim_ids=` into `build_full_verifier`, and `build_full_verifier`'s defaults for both
are `None`.

```
git show HEAD:src/tour/compose.py | sed -n '1341,1375p'
```
Output confirms the OLD `compose_script` computed `expected_claim_ids` unconditionally and
forwarded the caller's `faithfulness_checker` — both now dropped for the persisted path.

```
make lint
```
Exit 0, "All checks passed!" — re-confirms the claimed lint evidence myself.

## Attacks tried that did NOT break the claim

- Re-read the 409-before-precheck ordering in the actual route code (not the test) —
  structurally correct, matches AC-7.
- Checked whether `plan_prebuilt_route_authoring` could make a provider call before the
  spend reservation (it cannot — provably provider-free by reading its body).
- Checked `COMPOSE_ATTEMPTS` / `ComposeVerificationError.attempts` for a hardcoded-constant
  mismatch across the two 422 branches — both are `1`, consistent.
- Checked whether the new broad `except ValueError` could swallow the `_spend_precheck`'s own
  429 (`_too_many`) — it cannot; `_too_many` raises `HTTPException`, not `ValueError`.
- Ran `make lint` myself — clean, matches the pasted evidence.

## Verdict

- **AC-3 / AC-7 as literally tested: CONFIRMED** by static re-derivation (did not re-execute
  the pytest node id myself; that part is UNPROVEN by me specifically, though the pasted
  transcript is internally consistent and plausible).
- **The step's implicit "the persisted compose path is otherwise unchanged/safe" framing:
  REFUTED by direct code reading.** All three of D3's named anti-hallucination gates
  (faithfulness entailment, coverage baseline, forbidden-phrase/proper-noun/year scan) are
  absent from the code path A3 wires in, not merely "weaker" — and neither AC-3 nor AC-7
  would ever catch this, since neither criterion mentions content safety.
