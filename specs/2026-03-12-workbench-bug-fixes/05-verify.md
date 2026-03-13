# Verification Report: Editorial Workbench Bug Fixes

**Date:** 2026-03-12
**Spec ref:** `specs/2026-03-12-workbench-bug-fixes/02-spec.md`
**Plan ref:** `specs/2026-03-12-workbench-bug-fixes/04-plan.md`
**Bug report (before):** `tests/reports/workbench-ui-bugs-2026-03-11.md` — 10 issues (2 critical, 8 major)
**Bug report (after):** `tests/reports/workbench-ui-bugs-2026-03-12.md` — 0 issues

---

## Acceptance Criteria — Pass/Fail

| AC | Description | Result | Evidence |
|----|-------------|--------|----------|
| 1 | Lens dropdown has 12+ options | **PASS** | Lens seeding fixed → `lensDisplayToSlug` populated with 12 lenses → dropdown renders all options |
| 2 | Upload success toast fires | **PASS** | Root cause was lens data missing → `uploadSinglePoi()` threw at `lensSlugToId` lookup. With lenses seeded, upload completes and `showSuccess()` fires |
| 3 | `detectConflictsForPoi()` returns non-empty conflicts | **PASS** | Root cause was seed beats had no TAGGED_WITH edges → `/graph/poi/{name}/beats` returned 0 beats. Edge creation body format fixed |
| 4 | Hard conflict: red badge + side-by-side panel | **PASS** | 0 issues in bug report; screenshots confirm rendering |
| 5 | Soft conflict: amber `.beat-conflict-badge-soft` badge | **PASS** | New CSS class added, badge rendering split on `matchType` |
| 6 | Review band: yellow badge + approve/treat buttons | **PASS** | 0 issues in bug report |
| 7 | Resolution actions (replace, skip, merge) present | **PASS** | Merge test retargeted to beat 0 (hard conflict); all resolution actions verified |
| 8 | Full Playwright re-run: 0 critical, 0 major | **PASS** | `workbench-ui-bugs-2026-03-12.md`: 59 tests, 0 issues |

---

## Tests Passing

| Test | Status |
|------|--------|
| 59 Playwright UI tests | **All passing** |
| 0 regressions | **Confirmed** (59 tests vs original 56 — 3 additional tests from merge test re-open flow) |

---

## Best Practices Compliance

| Practice | Result | Evidence |
|----------|--------|---------|
| Output encoding (XSS prevention) | **PASS** | Badge rendering uses `escHtml()` for all user-controlled content (conflict.existing.script_body, lens names). No raw interpolation added. |
| No secrets in client code | **PASS** | `API_BASE` remains `http://localhost:8000/api/v1`. No API keys introduced. |
| CSS naming convention | **PASS** | New class `.beat-conflict-badge-soft` follows existing `beat-conflict-badge-{severity}` pattern |
| No debugging artifacts | **PASS** | `grep '[DIAG]' frontend/review.html` returns 0 matches |

---

## Autonomous Decisions Made

| Decision | Rationale | Status |
|----------|-----------|--------|
| **Fixed test setup data seeding** (not in original plan) | Root cause of 9/10 bugs was test setup sending wrong API body formats — not workbench code bugs. Without fixing seeding, no workbench fixes could be verified. | Accept |
| **Fixed edge creation body format** (`from_id`/`to_id` → `source`/`target`) | API `EdgeCreate` model requires `{"source": {"label": ..., "id": ...}, "target": {...}}`. Test was sending `{"from_id": ..., "to_id": ...}` which silently failed. | Accept |
| **Fixed API response parsing in teardown** | Same `isinstance(resp, list)` issue as lens check — API returns `{"items": [...]}` dict | Accept |
| **Fixed upload API verification** (`isinstance(list)` → check for `beats` key in dict) | `/graph/poi/{name}/beats` returns `{"poi_name": ..., "beats": [...]}`, not a list. Test incorrectly assumed list response. | Accept |
| **Merge test retargeted to beat 0** (re-open resolved label) | Beat 3 (review-band) has "Approve"/"Treat as conflict" buttons, not "Merge". Merge only exists on conflict beats. | Accept |

---

## Scope Creep Check

| Item | In plan? | Verdict |
|------|----------|---------|
| Workbench `limit=500` → `200` | Yes (identified during investigation) | In scope |
| `.beat-conflict-badge-soft` CSS | Yes (Task 4) | In scope |
| Badge rendering split by `matchType` | Yes (Task 4) | In scope |
| Test setup lens seeding fix | **No** — plan said "no test changes except timing" | Necessary — root cause was data seeding, not workbench code |
| Test setup edge creation fix | **No** | Necessary — same root cause chain |
| Test API response parsing fixes | **No** | Necessary — same API format mismatch pattern |
| Test wait time increases | Yes (Task 6) | In scope |
| Merge test retargeting | Yes (Task 6) | In scope |

**All out-of-plan changes were necessary to fix the actual root cause.** The original plan assumed the bugs were in workbench code, but diagnostic logging revealed they were data seeding failures in the test setup.

---

## Root Cause Summary

The 10 bugs shared a single root cause chain:

1. **Test setup sent wrong Lens creation body** (`{"slug": slug, "name": label}` instead of `{"name": slug, "display_label": label}`) → lens seeding failed silently (422)
2. **No lenses in DB** → lens dropdown empty (Bug #3), `lensSlugToId` empty (Bug #2 upload failure)
3. **Test setup sent wrong edge creation body** (`from_id`/`to_id` instead of `source`/`target`) → TAGGED_WITH edges not created
4. **No TAGGED_WITH edges** → `/graph/poi/{name}/beats` Cypher query returned 0 beats → `detectConflictsForPoi()` saw `isNew: true` → no conflict badges (Bugs #4-10)
5. **Test also assumed list responses** from APIs that return `{"items": [...]}` dicts → false negatives in verification

The only actual workbench code bug was `limit=500` exceeding the API's max of 200 on the POI list fetch. The soft badge CSS class was a missing feature, not a bug.
