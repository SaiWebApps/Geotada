# Red Team Review: Editorial Workbench Bug Fixes

**Date:** 2026-03-12
**Spec ref:** `specs/2026-03-12-workbench-bug-fixes/02-spec.md`
**North star ref:** Phase 1 — Content pipeline + Editorial Workbench

---

## 1. Blockers

### B1 — Root cause of conflict detection failure is unknown

The spec identifies 7 conflict-related bugs but the root cause cannot be determined from code reading alone. `detectConflictsForPoi()` (review.html:2068–2143) calls `GET /graph/poi/{name}/beats` — if this returns empty or errors, all downstream conflict UI silently fails. The function swallows errors into `result.errors[]` but these errors aren't prominently surfaced to the developer.

**Resolution required:** Must reproduce locally with the running stack to identify whether:
- (a) The API endpoint returns an unexpected response shape (`data.beats` vs something else)
- (b) The seeded POI name doesn't match (encoding, prefix mismatch)
- (c) The endpoint itself errors/404s
- (d) `resolveLensSlug()` can't map the incoming lens string, causing hard-match detection to silently skip

**Suggested approach:** Add temporary `console.log` statements in `detectConflictsForPoi()` to trace the API response and conflict detection flow, then remove before final commit.

### B2 — Test triggers conflict check via "Mark as Complete", not POI selection

The test (test_workbench_ui.py:1578) clicks "Mark as Complete" to trigger conflict detection, then checks for badges. But in the code, conflict detection runs during `selectPoi()` (review.html:1312), not during "Mark as Complete". The "Mark as Complete" handler only checks whether conflicts are *already resolved* (review.html:1385–1393).

This means:
- If conflicts ARE found during selection → badges render immediately → clicking Mark as Complete shows "Resolve all beat conflicts first" error → test should still see badges
- If conflicts are NOT found during selection → Mark as Complete proceeds with upload → no badges to find

The test's 500ms wait after POI selection (test_workbench_ui.py:1564) may be too short for the async `detectConflictsForPoi()` API call. But this is a test timing issue, not a workbench bug — and we said no test changes.

**Resolution required:** Confirm whether the 500ms wait is sufficient. If not, this is a test issue that must be addressed separately. The workbench code itself may be correct — `selectPoi()` awaits the conflict detection before calling `renderDetail()`.

---

## 2. Risks

### R1 — Lens dropdown fix may be data-dependent, not code-dependent
**Risk:** The lens dropdown shows 1 option. The code at review.html:1901 fetches `/nodes/Lens?limit=50` and parses `lensData.items`. If the dev database genuinely has only 1 Lens node, the fix isn't in the code — it's in the database seeding.
**Likelihood:** Medium
**Mitigation:** Check lens count in Neo4j before debugging the code. The test setup should seed 12 lenses if missing (test spec says so at line 161).

### R2 — Adding `.beat-conflict-badge-soft` may create a visual regression
**Risk:** Currently, soft conflicts use `.beat-conflict-badge-hard` (red). Changing to amber could confuse editors who've already seen the red styling, and we need to pick a CSS variable that exists (`--orange` is defined and used for conflict panels already).
**Likelihood:** Low (no editors are using the workbench in production yet)
**Mitigation:** Use `--orange` for the amber color to match the existing `.beat-conflict-panel` border color.

### R3 — Auto-advance after upload may clear toast prematurely
**Risk:** After successful upload (review.html:1401–1414), the code auto-advances to the next POI via `selectPoi(nextIdx)`, which triggers `renderDetail()`. If `renderDetail()` manipulates the DOM in a way that removes or repositions the toast, it could disappear before the 4-second timeout.
**Likelihood:** Low — the toast is a fixed-position element outside the detail panel DOM
**Mitigation:** Verify the toast is a sibling of the detail panel, not a child. Confirm it survives re-renders.

---

## 3. Open Questions

### OQ1 — Should soft conflict badges use a different class from hard?
The current code (review.html:1532) renders ALL `beatConflicts` (both hard and soft) with `.beat-conflict-badge-hard`. The spec says to add `.beat-conflict-badge-soft`. But the rendering logic at line 1531 checks `if (conflict)` — which includes both hard AND soft matches (both are in `beatConflicts`).

**Need user's call:** The fix requires splitting the `if (conflict)` branch to check `conflict.matchType === 'hard'` vs `conflict.matchType === 'soft'` and apply different badge classes. This is a small logic change. Proceed?

---

## 4. Codebase Conflicts

### CC1 — `beatConflicts` contains both hard AND soft matches
The `detectConflictsForPoi()` function pushes both hard matches (line 2116) and soft matches (≥70% Jaccard, line 2132) into the same `beatConflicts` array, distinguished only by `matchType: 'hard'` vs `matchType: 'soft'`. The rendering code at line 1531 treats all `beatConflicts` entries identically (red hard badge). To implement AC5 (amber soft badge), the rendering branch must check `matchType`.

### CC2 — Resolution buttons render for hard conflicts only
The "Replace / Skip / Merge / Change Lens" buttons (review.html:1554–1560) only render inside the `if (conflict)` branch. The `else if (review)` branch (line 1562–1583) renders different buttons: "Approve" and "Treat as conflict". This is correct per the spec — but the test (test_workbench_ui.py) looks for `replace`/`skip`/`merge` on unspecified beat cards. If the test is checking review-band beats for those buttons, they won't exist by design.

---

## 5. North Star Check

**Alignment: Good.** This work directly supports the Active Build Target ("Database Upload & Conflict Resolution slice"). The conflict detection and resolution workflow is the core of the editorial process.

**No short-sighted decisions detected.** The fixes are scoped to the existing architecture — no new patterns, no structural changes. The monolithic HTML file approach is maintained per architectural commitment.

One note: the north star says "Spec and Claude Code prompt for this slice have not yet been written" — this spec-pm workflow is filling that gap.

---

## 6. Best Practices Audit

### A) Security & Privacy Constraints (`SECURITY_PRIVACY_PRACTICES.md`)

| # | Section | Verdict | Notes |
|---|---------|---------|-------|
| 1 | Data Classification & Minimization | N/A | No new data collection |
| 2 | Consent & Transparency | N/A | No user-facing consent changes |
| 3 | Authentication & Authorization | N/A | Workbench is a local dev tool, no auth layer |
| 4 | Secure Session Management | N/A | No session changes |
| 5 | Secrets & Credentials | Pass | No secrets in client code; API_BASE is a localhost URL |
| 6 | Encryption | N/A | No transport changes |
| 7 | Logging & Monitoring | N/A | No logging changes |
| 8 | Data Retention & Deletion | N/A | No retention changes |
| 9 | Third-Party Risk | N/A | No new dependencies |
| 10 | Secure Development Lifecycle | Pass | Bug fixes reviewed via spec-pm workflow |
| 11 | Input Validation & Output Encoding | Pass | Existing `escHtml()` usage preserved; no new user inputs |
| 12 | Infrastructure & Network Security | N/A | No infra changes |
| 13 | Privacy by Design | N/A | No new data flows |
| 14 | Incident Response | N/A | No IR changes |
| 15 | Testing & Verification | Pass | Playwright test suite re-run validates fixes |
| 16 | Compliance & Documentation | N/A | No compliance-relevant changes |

### B) Best Practices Library

**Security** — Pass. No new endpoints, no auth changes, no user input handling changes. Existing `escHtml()` output encoding is preserved in all badge/panel rendering.

**Performance** — Pass. No new API calls added. Conflict detection already caches results in `poi._conflicts`. Lens data already cached in `lensDisplayToSlug`.

**Privacy** — N/A. No user data involved; this is editorial tooling for internal content triage.

**Accessibility** — N/A. Scope excludes UI enhancements. Existing badge rendering patterns preserved.

**UX** — Pass. Fixes restore intended behavior; no new UX patterns introduced.
