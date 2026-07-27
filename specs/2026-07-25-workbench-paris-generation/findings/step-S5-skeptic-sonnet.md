# S5 skeptic review — FIX CORRECTNESS angle

**Verified against:** HEAD 930b1e201d8528cd9ae493df5111127715d12d6b, working tree DIRTY
(as expected per run-context baseline), specifically the uncommitted diffs to
`src/tour/candidate_eligibility.py`, `src/api/routes/trips.py`, and
`tests/test_trips_spend_and_authz.py`.

## Verdict: CONFIRMED (no break found)

## What I checked

1. **Re-read the full diff myself** (`git diff -- src/tour/candidate_eligibility.py
   src/api/routes/trips.py`) rather than trusting the pasted excerpts. Confirmed:
   - `CandidateRejectionCode.BUILD_FINGERPRINT_UNAVAILABLE = "build_fingerprint_unavailable"`
     added as an 8th member to a StrEnum that previously had exactly 7 (matches the
     decision log's "provably lack a build-fingerprint case" claim).
   - `resolve_build_identity()` is now wrapped in its **own** `try/except Exception`
     block, physically preceding — not sharing a block with — the
     `_spend_precheck` / physical-authoring `try/except`. This is the actual fix:
     before, both calls lived in one try with one `except Exception` that always
     produced `reason="llm_generation_failed"` / `code="generation_failed"`.
   - The mutation evidence's captured failure (`assert 'llm_generation_failed' !=
     'llm_generation_failed'`) is consistent with reverting exactly this
     structural split — it is not a strawman produced by deleting an unrelated
     line.

2. **Traced AC-18's "before `_spend_precheck`" claim in the actual source**
   (`src/api/routes/trips.py:1097-1139`): `resolve_build_identity()` fires in a
   try block that returns immediately on failure, and `_spend_precheck` is the
   first statement of the *next* try block — genuinely unreachable until
   `build_identity` resolved. Also confirmed `plan_premium_tour` (which runs even
   earlier, at line ~1043) is docstring-marked "Pure/provider-free" and only
   touches `RoutingClient`/Valhalla, not an LLM — so no paid call happens before
   the new guard either. AC-18 ("zero paid calls") holds structurally, not just
   by the one test's assertion on `executor.calls == 0`.

3. **Checked `reason="llm_candidate_ineligible"` was not a fabricated/ad-hoc
   string.** `TripPreviewBasicTour.reason` (`src/api/models/trips.py:315`) is a
   `Literal["llm_generation_failed", "llm_candidate_ineligible"]` — the second
   value already existed in the model and is already exercised by two pre-existing
   workbench UI fixtures (`tests/test_workbench_ui.py:2007`, `:2063`) as the
   generic "Premium ineligible, not a generation failure" reason. Repurposing it
   for the build-fingerprint case is consistent with its pre-existing contract,
   not a new invented value that could silently break a frontend `Literal` union.

4. **Attacked the "neighbouring input" angle**: read the `preview_client` test
   fixture (`tests/test_trips_spend_and_authz.py:134-152`) carefully because the
   run-context's own `flake_trap` decision warns that any test touching
   `resolve_build_identity` against the *live* `REPO_ROOT` inverts once this repo
   goes clean (it is currently dirty, which is why the pinned test can pass at
   all if it weren't hermetic). Traced the call order for the second sub-assertion
   in the pinned test (the "other" provider-failure case at line 254): each call
   to `preview_client(...)` re-invokes `_make`, which re-applies
   `monkeypatch.setattr(trips_route, "resolve_build_identity", lambda: ...)` to
   the always-succeeding default — so the second client's call correctly
   overwrites the test's own throwing override from the first sub-case. Neither
   sub-case ever touches the real ambient git tree; the test is fully hermetic and
   does not risk the flake pattern the run-context explicitly warned about. This
   is a real, non-strawman regression guard.

5. **Checked for collateral/orphaned usages** of the new enum member or the old
   pre-fix branch shape: `grep -rn "CandidateRejectionCode"` outside
   `candidate_eligibility.py`/`trips.py` returns nothing else that hardcodes a
   7-member assumption (e.g., no OpenAPI-schema-pinning test enumerates the
   codes). No collateral breakage surface found.

6. **Ran `make lint` myself** (the only command safe to self-run under the
   concurrency constraint): `All checks passed!`, exit 0 — reconfirms the pasted
   evidence rather than trusting it blindly.

## Non-blocking observation (out of S5's claimed scope, noted for the run record)

`src/api/routes/trips.py` currently has **zero logger calls** anywhere
(`grep -n "logger\.\|logging.getLogger" src/api/routes/trips.py` → no matches).
AC-15 ("a WARNING-or-higher record on the 'ondoway' namespace names the
exception type and message... exactly one record per request") is **not yet
implemented** in the working tree. The S5 claim under review only asserts AC-16
and AC-18, and the run-context's pinned-gate table assigns
`src/api/routes/trips.py` + `tests/test_trips_spend_and_authz.py` to S7 as well
— so this is very likely S7's job, not a gap in S5. Flagging it so the run
doesn't accidentally treat S5 as having silently covered AC-15 too; it has not.

## Attacks tried that did NOT break the claim

- Attempted to find an ambient-repo flake in the pinned test (the `flake_trap`
  decision's named failure mode) — refuted by tracing the fixture's re-patch
  order.
- Attempted to find a case where an unrelated/earlier paid call happens before
  `resolve_build_identity()` — refuted by `plan_premium_tour`'s
  provider-free docstring and structural trace.
- Attempted to find a fabricated/non-existent enum or Literal value used by the
  fix — refuted; both `build_fingerprint_unavailable` (new, additive) and
  `llm_candidate_ineligible` (pre-existing, already covered by other tests) are
  legitimate.
- Attempted to find collateral damage from adding an 8th `CandidateRejectionCode`
  member (schema-pinning tests, hardcoded counts elsewhere) — none found.
- Did not independently re-execute the pinned pytest node id myself (blocked by
  the concurrency rule — shared 7688 DB / dev graph). Recommend the serial
  verifier run:
  `make test-file FILE="tests/test_trips_spend_and_authz.py::test_unverifiable_build_is_rejected_before_provider_spend"`
  to close that last gap; my source-level trace strongly predicts PASSED given
  the diff read above matches the developer's own reported output line-for-line.

## Findings

None that block. One advisory/non-blocking scope note recorded above.
