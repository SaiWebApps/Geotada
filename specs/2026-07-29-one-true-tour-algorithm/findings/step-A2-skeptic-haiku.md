# Step A2 Skeptic Review — Haiku Model

**Commit verified:** c8ec3969 (HEAD, 32 commits ahead of origin/main)

**Verified at:** 2026-07-30 per skeptic run

---

## Claim

> Step A2 "Author-a-prebuilt-route seam: no re-planning, 1..15 stops, round-trip and receiptless tolerated" satisfies AC-4, proven by `make test-file FILE="tests/test_tour_authoring_from_route.py::test_prebuilt_route_authors_without_replanning"` plus a QA mutation verdict of REAL.

---

## Evidence Chain Audit

### Discrepancy 1: Pinned Gate vs. Claimed Proof

**run-context.md line 230:**
```
- A2: `make lint`
```

**Claim says proof is:**
```
make test-file FILE="tests/test_tour_authoring_from_route.py::test_prebuilt_route_authors_without_replanning"
```

The run-context specifies the A2 gate as `make lint` alone, not the cited test-file command. The claimed test-file command is positioned as _evidence_, not the _gate_. This is consistent — extra evidence beyond the gate is permitted. However, the mutation evidence itself undermines the claimed proof.

---

### Discrepancy 2: Mutation Verdict Contradicts Claim

**Claim:** The proof is the test plus "a QA mutation verdict of REAL"

**Mutation evidence (from provided evidence package):**
```
"exit_code":0,"summary":"MUTATION on the pinned node id: source fix reverted (max_length back to 8, no MAX_CANDIDATE_STOPS), but the pinned test STAYED GREEN (did not go RED). This node id only exercises a 4-stop round-trip route, well under both the old 8-cap and the new 15-cap, so it never touches the changed constraint."
```

**Explicit admission from evidence package:**
> "By the letter of the instructed rule ('a test that still passes with the fix reverted is FAKE'), that specific pairing is FAKE: this node id proves nothing about the A2 diff."

The QA mutation verdict is NOT "REAL" — it is explicitly labeled **FAKE**. The test stayed GREEN when the fix was reverted, proving the test does NOT catch the mutation.

---

### Root Cause: Test Selection Mismatch

**Test being claimed:** `test_prebuilt_route_authors_without_replanning` (line 191 of test_tour_authoring_from_route.py)

```python
def test_prebuilt_route_authors_without_replanning(monkeypatch: pytest.MonkeyPatch) -> None:
    """The seam authors a persisted ROUND-TRIP route, one unit per dwell stop."""
    _forbid_planning(monkeypatch)
    stitched, sequence, route = _prebuilt(4, round_trip=True)  # ← 4 stops only
```

**The fix:** Relaxed `max_length` from 8 to 15 (candidate_authoring.py lines 154 and 177)

**Why the test doesn't catch it:** The test uses `_prebuilt(4, round_trip=True)` — a 4-stop route. Both the old constraint (max 8) and new constraint (max 15) allow 4 stops. The test never exercises the boundary that changed (9-15 stops).

---

### Tests That DO Catch the Mutation

The evidence package provides these:

1. **`test_prebuilt_route_authors_fifteen_stops`** (line 216, same file)
   - Explicitly tests 15 stops: `stitched, sequence, route = _prebuilt(15)`
   - Mutation evidence: "went RED with a pydantic 'at most 8 items... not 15' ValidationError and GREEN on restore"
   - This test **IS a real mutation catcher** for the A2 fix

2. **`test_candidate_plan_covers_every_stop_selection_can_seat`** (in test_tour_candidate_authoring.py)
   - Developer's own new unit test in the diff
   - Mutation evidence: "went RED (ImportError for MAX_CANDIDATE_STOPS) and GREEN on restore"
   - This test **IS a real mutation catcher** for the A2 fix

**Arithmetic check:** The provided evidence confirms both these tests went RED when the fix was reverted. This proves the fix is REAL, just not via the claimed pinned test.

---

## AC-4 Coverage Check

AC-4 requires (verbatim from run-context.md):
> Given the author-a-prebuilt-route seam driven by a counting offline executor, then select_k_routes is never called, exactly one authoring unit is built per dwell stop, and **a round-trip-shaped route, a 15-stop route, and a receiptless (haversine-degraded) route each author successfully.**

The test file provides:
- Line 191: `test_prebuilt_route_authors_without_replanning` — 4-stop round-trip ✓ (part of requirement)
- Line 216: `test_prebuilt_route_authors_fifteen_stops` — **15-stop test** ✓ (required for AC-4)
- Line 241: `test_prebuilt_route_authors_receiptless_haversine_legs` — receiptless test ✓ (required for AC-4)

AC-4 is adequately covered by the test file as a whole. But the **specific test cited as proof** (`test_prebuilt_route_authors_without_replanning`) is blind to the 15-stop clause.

---

## Finding

**Rule:** REFUTED

**Title:** Pinned test does not prove the mutation was fixed; test stayed GREEN when fix was reverted.

**Severity:** High

**Why:** The claim states the test `test_prebuilt_route_authors_without_replanning` **proves** AC-4 satisfaction via a mutation verdict of REAL. The provided mutation evidence explicitly shows:
1. The test stayed GREEN when the fix was reverted (did not go RED)
2. The evidence package itself labels this pairing as "FAKE: this node id proves nothing about the A2 diff"

The fix itself is REAL (caught by `test_prebuilt_route_authors_fifteen_stops` and developer tests), but the claimed proof test does not catch it. The claim conflates "the fix exists" with "the pinned test proves the fix" — they are not the same thing.

**Evidence:** Provided mutation evidence exhibits:
- Expected: test RED when fix reverted → GREEN when restored
- Observed: test GREEN both when fix reverted and when restored
- Conclusion: test is blind to the mutation

---

## Reproduction (Proposed)

Cannot run directly (shared DB); recommend serial verifier run:

```bash
# Verify pinned test passes with fix in place:
make test-file FILE="tests/test_tour_authoring_from_route.py::test_prebuilt_route_authors_without_replanning"

# Revert the fix (max_length back to 8, remove MAX_CANDIDATE_STOPS):
git stash push -- src/tour/candidate_authoring.py

# Re-run the pinned test — it should FAIL if it truly catches the mutation:
make test-file FILE="tests/test_tour_authoring_from_route.py::test_prebuilt_route_authors_without_replanning"

# Restore and verify the 15-stop test IS caught by mutation:
git stash pop
make test-file FILE="tests/test_tour_authoring_from_route.py::test_prebuilt_route_authors_fifteen_stops"
git stash push -- src/tour/candidate_authoring.py
make test-file FILE="tests/test_tour_authoring_from_route.py::test_prebuilt_route_authors_fifteen_stops"
git stash pop
```

Expected outcome: pinned test green both times; fifteen-stops test green/red/green.

---

## Recommendation

**Do not merge** step A2 with this specific proof claim. Options:

1. **Update the proof:** Replace the claimed pinned test with `test_prebuilt_route_authors_fifteen_stops`, which actually catches the mutation.
2. **Broaden the claim:** State that AC-4 is proven by the full test file (`test_tour_authoring_from_route.py`), not one specific node id.
3. **Re-architect:** If the pinned test was intentionally chosen for a reason (e.g., CI perf, isolation), document why one test is selected over the mutation-catching one.

The fix itself is sound (evidenced by the tests that DO catch it). This finding is about the evidence chain, not the code quality.

