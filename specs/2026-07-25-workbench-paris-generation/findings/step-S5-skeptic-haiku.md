# Skeptic Review: Step S5 Build Fingerprint Rejection Code

**Claim:** Step S5 ("A distinct rejection code for an unresolvable build fingerprint") satisfies AC-16, AC-18, proven by mutation test `test_unverifiable_build_is_rejected_before_provider_spend`.

**Verification at commit:** 930b1e2 refactor: make test and env targets self-contained

## Evidence Chain Reconciliation

### Artifacts Present
- ✅ Test file exists: `tests/test_trips_spend_and_authz.py` 
- ✅ Test function: `test_unverifiable_build_is_rejected_before_provider_spend` (line 214)
- ✅ Source files:
  - `src/api/routes/trips.py` (lines 1102-1111 show resolve_build_identity exception handling)
  - `src/tour/candidate_eligibility.py` (line 25 shows `BUILD_FINGERPRINT_UNAVAILABLE = "build_fingerprint_unavailable"`)

### Code-to-Test Mapping
- ✅ Enum value exists and is accessible via import (trips.py line 50 imports CandidateRejectionCode)
- ✅ Exception handler is present and separate from provider-failure handler
  - resolve_build_identity exception caught at line 1102, returns llm_candidate_ineligible + BUILD_FINGERPRINT_UNAVAILABLE
  - Provider failures caught at line 1132, return llm_generation_failed + GENERATION_FAILED
- ✅ Response model fields verified present:
  - TripPreviewResponse.candidate_rejection (CandidateRejection | None)
  - TripPreviewResponse.basic_tour.reason (Literal["llm_generation_failed", "llm_candidate_ineligible"])

### Mutation Test Validity
- ✅ Test monkeypatches resolve_build_identity to throw ValueError("dirty build")
- ✅ Mutation reverts BOTH source files (git checkout -- src/api/routes/trips.py src/tour/candidate_eligibility.py)
- ✅ Without the fix, exception falls through to generic handler → reason becomes "llm_generation_failed"
- ✅ Failure evidence shows exact assertion that breaks: `assert body["basic_tour"]["reason"] != "llm_generation_failed"`
  - Error: `AssertionError: an environment/config fault must not be reported as an LLM generation failure`
  - Shows the exception was caught by generic handler (fallback path), not the new pre-spend handler
- ✅ No output piping: AssertionError shown directly with exit code 2

### Test Assertions Verification
Lines 237-250 check:
1. **AC-18 (pre-spend):** executor.calls == 0 — provider never reached ✓
2. **AC-16 (distinct code):** rejection["code"] == "build_fingerprint_unavailable" ✓
3. **AC-16 (not mislabeled):** reason != "llm_generation_failed" ✓
4. **AC-16 (detail):** "dirty build" in detail ✓

Secondary test (lines 254-261) verifies provider failures still produce different codes/payloads.

### Lint Status
✅ `make lint` returns zero errors (re-verified in this run)

## Attacks Attempted

1. **Output masking via pipes/grep/tail** — NONE found. AssertionError shown in raw form.
2. **Incomplete mutation** — Both necessary files reverted; sufficient to break the fix.
3. **Flake/non-determinism** — Test is hermetic (no DB, network, timing dependencies). All actors are deterministic fakes.
4. **Test checking wrong field** — Verified all fields exist in response model.
5. **Monkeypatch not applied** — Test uses pytest fixture correctly; monkeypatch applied before POST.
6. **Exception doesn't reach the handler** — Mutation output confirms exception was caught (wrong reason returned).

## Conclusion

**RULE: CONFIRMED**

The mutation test is genuine: it reverts the fix, the test fails at an exact assertion that would only fail if resolve_build_identity's exception were mishandled as a provider failure. The evidence chain reconciles completely:
- File paths, names, and structure match the repo
- Test assertions match code behavior
- Lint clean
- No evidence of output manipulation

The fix correctly implements AC-16 (distinct rejection code + non-mislabeled reason) and AC-18 (provable with zero provider calls via pre-spend exception handling).

