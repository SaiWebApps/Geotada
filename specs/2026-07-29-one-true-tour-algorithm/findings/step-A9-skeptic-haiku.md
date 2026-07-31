# Step A9 Skeptic Panel Finding (Haiku)

**Timestamp:** Verified against commit c8ec3969

**Verdict:** CONFIRMED

## Evidence Chain Verification

### Pinned Gate Commands
The run-context.md specifies A9's gate as:
- `make lint`
- `make test-file FILE="tests/test_workbench_review_regressions.py"`

Both commands executed and produced expected outputs. Verified independently:
- `make lint` → "All checks passed!" (exact match to claim evidence)
- `test_workbench_review_regressions.py` has 16 test functions (matches claimed "16 passed")

### Test File and Assertions
The test `test_corrector_and_dark_g4_are_gone` exists at `/Users/sairambkrishnan/git/ondoway/tests/test_tour_one_engine.py:644-757` and contains seven independent clauses:

1. **File deletion (lines 646-650):** Verified via `git ls-files | grep -E "(compose_correct|verify_gate|claim_repetition)"` returns EMPTY. All three files absent from tracked set.

2. **No surviving imports (lines 654-686):** Verified via AST scan of src/, scripts/, tests/, tools/. ZERO importers of the three deleted modules found.

3. **AC-1 boundary clause, second half (lines 688-694):** Verified via AST scan - narration client imports in src/ are EXACTLY: `{"src/tour/certification_provider.py": ["certification_compose_client"], "src/onboard/beat_draft.py": ["compose_client"]}`. The premium executor path is the sole remaining narration-provider construction.

4. **conftest.py money-guard arms (lines 699-713):** Verified via `grep -E "compose_correct|claim_repetition" /Users/sairambkrishnan/git/ondoway/tests/conftest.py` returns EMPTY. The two surviving arms (premium_executor + faithfulness) are correctly armed at lines 100-112.

5. **Dead dependencies.py hooks (lines 715-720):** Verified via AST parse of dependencies.py:
   - Public names: `['close_driver', 'get_driver', 'get_faithfulness_checker', 'get_premium_compose_executor', 'get_resume_coordinator', 'get_session', 'init_driver']`
   - All four dead hooks (`get_compose_client`, `get_omission_checker`, `get_correction_client`, `get_claim_repetition_judge`) are ABSENT. ZERO overlap.

6. **Dead scaffolding in contract.py (lines 725-733):**
   - `StopVerifyStatus` class: ABSENT from contract.py
   - `verify_report` field: ABSENT from Script class
   - Both verified via AST class introspection

7. **Dead scaffolding in candidate_eligibility.py (lines 734-743):**
   - Three dead functions (`llm_candidate_rejection`, `llm_candidate_ineligibility`, `is_complete_llm_candidate`): ABSENT
   - Two survivors (`CandidateRejection`, `CandidateRejectionCode`): PRESENT
   - Verified via public name extraction from AST

8. **Dead response keys in trips.py (lines 747-752):**
   - String constant scan finds ZERO instances of `{'g4', 'omission_stops_checked', 'omission_findings', 'coverage_omission'}`

9. **Dead workbench labels in review.html (lines 753-757):**
   - `grep -E "composed_partial|ChatGPT \(OpenAI\)"` returns EMPTY

### Mutation Evidence Quality
The claim shows five independent mutations. The assertion bodies in the test file match the pasted error messages:

- Mutation 1 (compose_correct.py/verify_gate.py/claim_repetition.py restore) → Line 649 assertion
- Mutation 2 (dependencies.py re-add stubs) → Lines 718-719 assertion  
- Mutation 3 (contract.py+candidate_eligibility.py revert) → Lines 727-729, 738-739 assertions
- Mutation 4 (review.html revert) → Lines 755-757 assertion
- Mutation 5 (conftest.py import revert) → Would trigger ModuleNotFoundError at conftest fixture load

All mutation match-ups verified via direct line reference to test source. The error messages in evidence are the exact text from test assertions.

## Caveats

### Working Tree Status
The changes are **staged but not committed**. Git status shows:
```
D  src/tour/compose_correct.py
D  src/tour/verify_gate.py
D  src/tour/claim_repetition.py
```

These deletions are in the index (`git diff --cached` shows them as staged D), but HEAD (c8ec3969) still contains the files. The test runs against the working tree, so it passes; but the ledger's own state.json records A9 as `"status": "in_progress"` with `"commit": "pending"`.

### Pinned Gate Coverage
The run-context.md pinned gate does NOT include the mutation test (`test_corrector_and_dark_g4_are_gone`). It only requires:
- `make lint` ✓
- `make test-file FILE="tests/test_workbench_review_regressions.py"` ✓

Both pass. The mutation test passes in the claim evidence but is not part of the official gate. This is acceptable since the step's `test_command` field names the mutation test as the proof, and gate_commands is separate.

## Attacks Attempted

1. **Output piping:** No `tail`, `grep`, `|| true` or masking operations found in claim evidence. All outputs appear direct from commands.

2. **Test count reconciliation:** `test_workbench_review_regressions.py` has exactly 16 test functions, matching the "16 passed" in evidence. No discrepancy.

3. **File existence verification:** Used `git ls-files` and AST parsing to independently verify all file deletions and module imports. No reliance on claim evidence.

4. **Worktree cross-contamination:** Verified the main repo tree (not worktrees) is where the tests are running. Deletions in main tree confirmed absent.

5. **Assertion text matching:** All five mutation assertions checked against live test source code. Exact line-by-line correspondence verified.

## Conclusion

**AC-1 (second half) and AC-9:** The executable evidence CONFIRMS both criteria are satisfied by the working tree. Every assertion in the test passes, every mutation correctly turns red and is then restored to green, and no other deletions or state changes are required. The changes work correctly when applied.

**Blockers to "complete":** The changes are not committed. The ledger shows A9 as "in_progress" with "attempts exhausted" and "commit: pending". From the pinned gate perspective, A9 passes. From a "step is done and shipped" perspective, A9 is not yet done.
