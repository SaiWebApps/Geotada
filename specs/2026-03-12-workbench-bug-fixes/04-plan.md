# Implementation Plan: Editorial Workbench Bug Fixes

**Date:** 2026-03-12
**Spec ref:** `specs/2026-03-12-workbench-bug-fixes/02-spec.md`
**Red team ref:** `specs/2026-03-12-workbench-bug-fixes/03-red-team.md`
**North star ref:** Phase 1 — Content pipeline + Editorial Workbench

---

## Part A — Task Breakdown

### Task 1: Add diagnostic logging to `detectConflictsForPoi()`

**Files to touch:** `frontend/review.html`
**What to do:** Add `console.log` statements at key points in `detectConflictsForPoi()` (lines 2068–2143) to trace:
- The API URL being called (line 2074)
- The raw API response (after line 2075)
- The parsed `existingBeats` array (after line 2076)
- The `resolveLensSlug()` result for each incoming beat (after line 2107)
- Each conflict match found (inside the push calls at lines 2116 and 2132)

Also log in `fetchLensesAndPoiList()` (lines 1899–1913):
- The raw lens API response
- The populated `lensDisplayToSlug` object after the loop

**What NOT to touch:** No logic changes in this task — logging only.
**Success check:** Developer opens browser console, loads fixture, selects conflict-target POI, and sees detailed trace output identifying the failure point.

---

### Task 2: Fix lens dropdown population

**Files to touch:** `frontend/review.html`
**What to do:** Based on the diagnostic output from Task 1, fix the lens dropdown population. The likely issues are:
- (a) `lensData.items` is empty or undefined — check if the API returns `items` or a different key (e.g., `data`, `results`, or the array directly)
- (b) The `limit=50` param isn't being respected or is wrong
- Fix `fetchLensesAndPoiList()` (line 1901–1913) to correctly parse the API response

Verify: After fix, `Object.keys(lensDisplayToSlug).length` should be ≥12 in the console.

**What NOT to touch:** Don't change the API endpoint or backend.
**Success check:** Lens dropdown on any beat card shows 12+ options (one per lens in the database).

---

### Task 3: Fix conflict detection root cause

**Files to touch:** `frontend/review.html`
**What to do:** Based on the diagnostic output from Task 1, fix the conflict detection flow. Potential fixes by failure point:
- (a) API response shape: If `/graph/poi/{name}/beats` returns beats in a different key (not `data.beats`), fix the parsing at line 2076
- (b) POI name encoding: If the encoded name doesn't match seeded data, fix the encoding at line 2074
- (c) `resolveLensSlug()` mapping failure: If the incoming beat lens (display label) can't be resolved to a slug, fix the lens resolution logic
- (d) Empty `existingBeats` despite POI existing: Check if the API returns beats nested differently

**What NOT to touch:** Don't change the conflict detection algorithm (Jaccard thresholds, matchType logic). Don't change the API.
**Success check:** Console log shows non-empty `beatConflicts` and/or `beatReviewItems` when selecting the conflict-target POI.

---

### Task 4: Add `.beat-conflict-badge-soft` CSS class and split badge rendering

**Files to touch:** `frontend/review.html`
**What to do:**
1. Add CSS class after line 438:
   ```css
   .beat-conflict-badge-soft { background: var(--orange); color: #fff; }
   ```
2. Split the badge rendering at lines 1530–1535. Currently:
   ```javascript
   if (conflict) {
     conflictBadge = `<span class="beat-conflict-badge beat-conflict-badge-hard">...`;
   }
   ```
   Change to:
   ```javascript
   if (conflict && conflict.matchType === 'hard') {
     conflictBadge = `<span class="beat-conflict-badge beat-conflict-badge-hard">Conflict (same lens)</span>`;
   } else if (conflict && conflict.matchType === 'soft') {
     conflictBadge = `<span class="beat-conflict-badge beat-conflict-badge-soft">Conflict (${(conflict.similarity * 100).toFixed(0)}% similar)</span>`;
   } else if (review) {
     conflictBadge = `<span class="beat-conflict-badge beat-conflict-badge-review">Review (${(review.similarity * 100).toFixed(0)}% similar)</span>`;
   }
   ```

**What NOT to touch:** Don't change the conflict panel rendering (side-by-side panels) — those are controlled separately at lines 1538–1584 and remain conditional on `conflict` or `review` being truthy.
**Success check:** Hard conflict beat shows red badge, soft conflict beat shows amber badge, review beat shows yellow badge.

---

### Task 5: Verify upload toast fires correctly

**Files to touch:** `frontend/review.html` (only if a fix is needed)
**What to do:** Using the diagnostic logging from Task 1, verify:
1. `showSuccess()` (line 863–868) is called after successful upload (line 1403)
2. The `#successToast` element receives the `.visible` class
3. The toast remains visible for 4 seconds despite the auto-advance to the next POI (line 1406–1414)

If the toast IS firing but the test misses it: the issue is test timing — the auto-advance triggers `selectPoi()` which is async and may complete before the test checks. The 4-second timeout (line 867) should be sufficient, but verify the toast DOM element is not inside a container that gets replaced during re-render.

If the toast is NOT firing: debug why `uploadSinglePoi()` is throwing before reaching line 1403. The catch block (line 1416–1418) would show an error toast instead.

**What NOT to touch:** Don't change the upload API call or the success/error logic structure.
**Success check:** After clicking Mark as Complete on a valid, non-conflicting POI, `#successToast.visible` is present for 4 seconds.

---

### Task 6: Update test wait times

**Files to touch:** `tests/test_workbench_ui.py`
**What to do:**
1. Increase the 500ms wait after POI selection to 2000ms at lines where conflict detection needs to complete before assertions. Key locations:
   - Line 1564: `page.wait_for_timeout(500)` → `page.wait_for_timeout(2000)` (conflict POI selection)
   - Line 1425: `page.wait_for_timeout(500)` → `page.wait_for_timeout(2000)` (upload POI selection)
2. Fix AC18 merge test target: The test calls `_test_merge_action()` on beat index 3 (review-band), but review-band beats have "Approve"/"Treat as conflict" buttons, not "Merge". Change the merge test to target beat index 0 or 2 (a conflict beat). Since beat 0 was already resolved with "replace" and beat 2 with "skip", the test should:
   - Click the resolved label on beat 0 (which has `data-change-resolution="true"`) to re-open resolution options
   - Then click "Merge" on beat 0
   - OR: reorder the tests so merge is tested before replace/skip

**What NOT to touch:** Don't change assertion logic, severity levels, or screenshot names.
**Success check:** Test timing allows async operations to complete before assertions fire.

---

### Task 7: Remove diagnostic logging

**Files to touch:** `frontend/review.html`
**What to do:** Remove all `console.log` statements added in Task 1. Leave no debugging artifacts.
**What NOT to touch:** Don't remove any pre-existing console.log/warn/error statements.
**Success check:** No Task 1 logging remains in the file.

---

### Task 8: Re-run Playwright test suite and verify

**Files to touch:** None (run only)
**What to do:**
1. Ensure Docker + Neo4j + FastAPI are running
2. Run: `python -m pytest tests/test_workbench_ui.py -v --headed`
3. Check the generated bug report at `tests/reports/workbench-ui-bugs-YYYY-MM-DD.md`
4. Verify: 0 critical issues, 0 major issues
5. Verify: previously passing tests still pass (no regressions)

**What NOT to touch:** Don't fix any new issues found — log them for a separate scope.
**Success check:** Bug report shows 0 critical, 0 major issues. All 56 tests produce expected results.

---

## Part B — Test Definitions

| AC | Test Description | Type | Expected Behavior | Edge Cases |
|----|-----------------|------|-------------------|------------|
| 1 | Lens dropdown option count | Playwright (AC9) | `select.lens-select` has ≥12 `<option>` elements | EC1: 0 lenses → only placeholder shown |
| 2 | Upload success toast | Playwright (AC8) | `#successToast.visible` present after upload | EC4: toast survives auto-advance re-render |
| 3 | Conflict detection returns data | Playwright (AC13) | `.beat-conflict-badge-hard` appears on beat A | EC3: lens string as display label vs slug |
| 4 | Hard conflict panel | Playwright (AC13) | `.conflict-sides` with 2 `.conflict-side` divs | — |
| 5 | Soft conflict amber badge | Playwright (AC15) | `.beat-conflict-badge` with "similar" text + amber color | — |
| 6 | Review band badge | Playwright (AC16) | `.beat-conflict-badge-review` present on beat D | — |
| 7 | Resolution actions present | Playwright (AC18) | `button:has-text('Replace')` etc. found on conflict beats | — |
| 8 | Full suite pass | Playwright (all) | 0 critical, 0 major in bug report | Regression on 46 passing tests |

---

## Part C — Claude Code Prompt

```
## Goal

Fix 10 bugs in `frontend/review.html` (Editorial Workbench) identified in the test report at `tests/reports/workbench-ui-bugs-2026-03-11.md`. After fixing, re-run the Playwright test suite to verify 0 critical/major issues remain.

## Context

- Read the north star: `specs/NORTHSTAR.md`
- Read the bug report: `tests/reports/workbench-ui-bugs-2026-03-11.md`
- Read the spec: `specs/2026-03-12-workbench-bug-fixes/02-spec.md`
- Read the red team: `specs/2026-03-12-workbench-bug-fixes/03-red-team.md`
- Primary file to fix: `frontend/review.html`
- Test file (may need timing adjustments): `tests/test_workbench_ui.py`

## Task Breakdown (do in order)

### 1. Add diagnostic logging
Add `console.log` at these locations in `frontend/review.html`:
- `detectConflictsForPoi()` (line ~2068): log API URL, raw response, parsed `existingBeats`, `resolveLensSlug()` results, and each conflict match
- `fetchLensesAndPoiList()` (line ~1899): log raw lens API response and populated `lensDisplayToSlug` object

### 2. Fix lens dropdown
The lens dropdown shows 1 option instead of 12+. The issue is in `fetchLensesAndPoiList()` (line ~1901). Check whether the API response uses `items`, `data`, `results`, or returns the array directly. Fix the parsing so `lensDisplayToSlug` is populated with all 12 lenses. Verify `Object.keys(lensDisplayToSlug).length >= 12` in the console after fix.

### 3. Fix conflict detection
`detectConflictsForPoi()` (line ~2068) returns empty conflicts. Based on the diagnostic logging, fix the root cause. Check:
- API response shape at line ~2076 (`data.beats` may need to be `data` or `data.items`)
- POI name encoding at line ~2074
- `resolveLensSlug()` mapping — does it handle both display labels AND slugs?

### 4. Add soft conflict badge CSS and split rendering
Add after line ~438:
```css
.beat-conflict-badge-soft { background: var(--orange); color: #fff; }
```

Split the badge rendering at lines ~1530-1535:
- `if (conflict && conflict.matchType === 'hard')` → red `.beat-conflict-badge-hard`
- `else if (conflict && conflict.matchType === 'soft')` → amber `.beat-conflict-badge-soft`
- `else if (review)` → yellow `.beat-conflict-badge-review` (unchanged)

### 5. Verify upload toast
Check that `showSuccess()` fires after upload. If it works but the test misses it, the fix is in test timing (Task 6). If it doesn't fire, debug why `uploadSinglePoi()` throws.

### 6. Update test timing and fix merge test target
In `tests/test_workbench_ui.py`:
- Increase wait from 500ms to 2000ms after POI selection at line ~1564 and line ~1425
- Fix the AC18 merge test: it targets beat index 3 (review-band, which has "Approve"/"Treat as conflict" buttons, not "Merge"). Change it to target a conflict beat that has the Merge button — either reorder the resolution tests or click the resolved label to re-open options before testing merge.

### 7. Remove diagnostic logging
Remove all `console.log` statements added in Task 1. Leave no debugging artifacts.

### 8. Re-run tests
Run: `python -m pytest tests/test_workbench_ui.py -v --headed`
Verify bug report shows 0 critical, 0 major issues. Verify no regressions on the 46 previously passing tests.

## What NOT to touch
- No backend/API changes
- No new features or UI enhancements
- No changes to conflict detection thresholds (Jaccard percentages)
- No changes to the monolithic HTML file structure
- Don't remove pre-existing console.log/warn/error statements

## Best Practices Checklist
- [ ] All badge/panel HTML uses `escHtml()` for user-controlled content (script_body, lens names, POI names)
- [ ] No new XSS vectors introduced in template literals
- [ ] Toast DOM element remains outside the detail panel container (survives re-renders)
- [ ] New CSS class follows existing naming convention (`.beat-conflict-badge-{severity}`)

Before starting, confirm you understand the full scope and flag any conflicts with the existing codebase or assumptions you are making.
```

---

## Part D — Best Practices Implementation Checklist

| Practice | Task(s) | How to verify |
|----------|---------|---------------|
| Output encoding (XSS prevention) | Task 4 | All new template literal content in badge rendering uses `escHtml()` — verify no raw `conflict.existing.*` values are interpolated without escaping |
| No secrets in client code | All | Verify `API_BASE` remains a relative or localhost URL, no API keys introduced |
| CSS naming convention | Task 4 | New class `.beat-conflict-badge-soft` follows `beat-conflict-badge-{severity}` pattern |
| Test coverage for security scenarios | Task 8 | Existing test assertions for input validation (invalid coords, empty script_body) still pass |
| No debugging artifacts in production | Task 7 | `grep -c "console.log" frontend/review.html` shows same count as before Task 1 |
