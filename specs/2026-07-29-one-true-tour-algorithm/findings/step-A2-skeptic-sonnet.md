# Step A2 skeptic review — FIX CORRECTNESS angle (sonnet)

Stamped against: HEAD `c8ec39690030901660c843d46910bedb40e84c13`, working tree
dirty with the A2 change-set (`src/tour/authoring.py`, `src/tour/candidate_authoring.py`
new/modified untracked+modified; `tests/test_tour_authoring_from_route.py` new/untracked).
This is uncommitted in-progress work, not a merged commit — noted for the record, not
treated as a defect by itself.

## What I checked

Read (not re-derived by execution, except `make lint`):
- `src/tour/authoring.py` lines 1-130, 484-660 (`_certification_compose_requests`),
  660-898 (the seam: `plan_prebuilt_route_authoring`, `author_prebuilt_route`).
- `tests/test_tour_authoring_from_route.py` in full (418 lines) — the pinned gate test
  and its four siblings.
- `src/tour/candidate_authoring.py` (`AuthoringCandidatePlan`/`AuthoringCandidateResponseSet`
  validators) and its diff.
- `src/tour/contract.py` (`Sentence.stop_idx` constraint, `TransitSegment` fields).
- `src/tour/reflection.py` (`reflection_slots`'s `leg_seconds` fallback) and
  `src/tour/compose_gate.py` (`build_full_verifier`) to check for hidden transit/receipt
  dependencies.
- `src/tour/selection.py` for `HARD_ANCHOR_CAP`.
- `specs/2026-07-29-one-true-tour-algorithm/state.json`'s A2 entry (`criterion_ids: [AC-4]`
  only — confirms D3 gate-parity / real-checker wiring is correctly OUT of this step's scope).

Ran myself (safe, no shared state): `make lint` — exit 0, "All checks passed!".

## Correctness analysis of the reverted guard

The mutation cited in the evidence (`src/tour/authoring.py:757-758`,
`if len(stops) != len(route.pois): raise ValueError("the prebuilt route needs one
authoring unit per dwell stop")`) is real and I traced it by hand against the test:

- `stops` is `sorted(by_stop)`, a set of unique `Sentence.stop_idx` values
  (`stop_idx: int = Field(..., ge=0)` in `contract.py`, so always non-negative).
- Combined with the preceding check `stops[-1] >= len(route.pois)` (raises a
  *different* message, "the stitched script names a stop the prebuilt route lacks"),
  the two guards together force `stops == list(range(len(route.pois)))` — there is no
  gap, overrun, or duplicate that can slip through both.
- Dropping the trailing stop of a 4-stop route (`_drop_stop(stitched, 3)`) yields
  `stops = [0, 1, 2]`: `stops[-1]=2 < len(pois)=4` so the first guard doesn't fire, then
  `len(stops)=3 != len(pois)=4` fires the reverted guard exactly as claimed — matches the
  QA-supplied "DID NOT RAISE" output when reverted.
- I additionally traced why this guard is specifically load-bearing only for a *trailing*
  gap: `AuthoringCandidatePlan._plan_is_complete_and_single_candidate` (candidate_authoring.py:157-167)
  independently rejects any *interior* gap (`indexes != tuple(range(len(stop_requests)))`),
  but a trailing gap of length N-k still equals `range(k)`, so it passes that downstream
  validator trivially. This matches the test's own comment (lines 328-333) and is the
  correct, non-strawman failure mode: a real caller reserving `len(units)` provider calls
  from a stitched script that silently dropped its last stop would pay for and persist a
  tour whose final stop was never authored. That is not a strawman.

## The five-clause docstring claim vs. the single-mutation evidence

The test's docstring (`tests/test_tour_authoring_from_route.py:19-21`) asserts reverting
ANY of five things turns this one node id red: no-replanning, one-unit-per-dwell-stop,
round-trip tolerance, the 15-stop cap, receiptless tolerance. The QA mutation evidence
pasted to me tested only ONE of those five (the count guard). That is a real gap in the
mutation-testing *process* as presented — a single green/red pair does not prove a
five-clause claim.

I closed that gap by static trace rather than by running four more live mutations myself
(restricted to `make lint` only under the concurrency rules):
- **No-replanning**: `_assert_the_seam_cannot_reach_the_planner()` (AST-based, scans
  `authoring.py`'s own import/call graph for `_PLANNING_MODULES`/`_PLANNING_CALLS`) is
  called at the top of the pinned test body (line 303), and `_forbid_planning` monkeypatches
  `selection.select_k_routes`/`choose_discrete_route` to explode for the whole test. I
  independently grepped `authoring.py` and confirmed zero imports of any planning module
  and zero calls to any planning entry point (only a docstring *mention* of
  `plan_premium_tour`, which the AST walker correctly ignores since it parses code not
  comments). Any future addition of such an import/call is caught directly by this test —
  covered, not a strawman.
- **15-stop cap**: `assert AUTHORING_MAX_STOPS == selection.HARD_ANCHOR_CAP == 15` is a
  literal line (338) inside the pinned test body, plus the test builds and successfully
  authors a real 15-stop plan. `AUTHORING_MAX_STOPS` (authoring.py:128) and
  `HARD_ANCHOR_CAP` (selection.py:273) both independently verified equal to 15 by direct
  grep. Reverting the cap to the old value (8/9) would fail this assertion directly —
  covered.
- **Round-trip and receiptless tolerance**: these are proven by *omission*, not by an
  active guard — I grepped `authoring.py` for any reference to `transits`, `leg_seconds`,
  `valhalla_receipt` and found none outside a docstring comment. The seam never reads
  route-transit shape or receipt fields at all, so it structurally cannot reject either
  case; `reflection.py`'s `reflection_slots` (the one place `leg_seconds` is consumed
  downstream) already falls back to `walk_seconds` when `leg_seconds is None`
  (reflection.py:37). The pinned test exercises both scenarios end-to-end
  (`round_trip=True` and `routed=False`) and asserts successful authoring, so a future
  regression that adds back a transit/receipt precondition (as `plan_premium_tour` has)
  would break this test on the success assertions — covered, though there is nothing to
  literally "revert" for these two clauses since no gate exists to remove.

Net: I did not find a case where the five-clause claim is false. The one-mutation
evidence supplied was incomplete on its own terms, but my independent static trace
closes that gap without needing to spend a live pytest run.

## Minor issue found, not blocking

`_prebuilt()`'s test fixture (`tests/test_tour_authoring_from_route.py:174-197`) sets
`source="haversine"` unconditionally, even when `routed=True` (where a real receipted leg
would carry `source="valhalla"`), and never sets `valhalla_receipt` in either branch — so
the "routed" scenario in the fixture doesn't actually represent a receipted leg, only a
leg with non-null `leg_seconds`/`leg_distance_m`. This is harmless for what AC-4 actually
requires (authoring must tolerate a *receiptless* route, which the `routed=False` branch
correctly represents, and authoring.py never reads `source`/`valhalla_receipt` at all), so
it does not undermine the claim. Flagged as a fixture-naming nit only.

## Scope check

`state.json`'s A2 entry has `criterion_ids: ["AC-4"]` only. `author_prebuilt_route` calls
`finalize_certification_composition` without passing `faithfulness_checker` or
`chunk_text_by_slug`, so it runs against the offline `MockFaithfulnessChecker` and does no
provenance/coverage checking — this is NOT a defect of A2: D3 (real-gate-parity, AC-5) is
explicitly a later wiring concern once the endpoint injects the real checker, and A2's own
criterion list correctly excludes AC-5. Confirmed via `state.json`, not assumed.

## Verdict

CONFIRMED, with one process caveat: the QA mutation evidence pasted to me tested 1 of the
5 clauses the test docstring claims to guard; I closed the remaining 4 by independent
static trace (import/call graph grep, field-usage grep, direct assertion reading) rather
than by running pytest myself (restricted under the concurrency rules to `make lint`).
I found no incorrect guard, no off-by-one in the stop-count math, no strawman in the
red-first failure mode, and no plausible neighbouring input (leading-stop drop, middle-stop
drop, zero-POI route, empty stitch, over-cap route) that evades the count guard or the
downstream `AuthoringCandidatePlan` validator.

## Attacks tried (all failed to break the claim)

1. Hand-traced the exact reverted line against the test's failure path (leading/trailing/
   middle stop drops) — guard is correct and matches the QA-supplied mutation output.
2. Checked whether `AuthoringCandidatePlan`'s own "cover every stop in order" validator
   already covered the guard's job (would make the added guard redundant/dead) — it does
   NOT cover the trailing-drop case, confirming the guard is load-bearing exactly where
   claimed.
3. Grepped `authoring.py`'s full import list and every call site for the five planning
   modules/entry points named in the test's `_PLANNING_MODULES`/`_PLANNING_CALLS` — zero
   hits outside a docstring comment.
4. Grepped `authoring.py` for any transit/receipt field reads to check whether "receiptless
   tolerance" is a real guarantee or an untested no-op — confirmed genuine (no code path
   reads those fields at all), and traced the one downstream consumer
   (`reflection.py:reflection_slots`) to confirm it degrades gracefully.
5. Verified `AUTHORING_MAX_STOPS == selection.HARD_ANCHOR_CAP == 15` by direct source read
   of both constants (not just trusting the assertion in the test).
6. Checked A2's scope in `state.json` to rule out a false claim of gate-parity (AC-5)
   coverage that isn't actually A2's job.
7. Ran `make lint` myself — exit 0, clean.

I did not execute `make test-file` myself (restricted to avoid corrupting a sibling
skeptic's shared-DB run); the exact pinned command is proposed below for the serial
verifier.
