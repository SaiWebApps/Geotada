# Contract Spec: Editorial Workbench Bug Fixes

**Date:** 2026-03-12
**Scope ref:** `specs/2026-03-12-workbench-bug-fixes/01-scope.md`
**North star ref:** Phase 1 — Content pipeline + Editorial Workbench
**Bug report ref:** `tests/reports/workbench-ui-bugs-2026-03-11.md`

---

## Purpose

Fix 10 bugs in `frontend/review.html` that block the editorial conflict detection and resolution workflow — the active Phase 1 build target. Fixes unblock the editorial team from using the workbench to triage content against the live Neo4j database.

---

## Inputs

| Input | Shape | Source |
|-------|-------|--------|
| Bug report | 10 issues (2 critical, 8 major) | `tests/reports/workbench-ui-bugs-2026-03-11.md` |
| Test spec | AC definitions + fixture design | `specs/2026-03-11-workbench-ui-tests/02-spec.md` |
| Workbench source | Single HTML/CSS/JS file | `frontend/review.html` |
| Playwright tests | Python test suite + fixture | `tests/test_workbench_ui.py` + `tests/fixtures/ui_test_fixture.json` |

---

## Outputs

| Output | Format | Destination |
|--------|--------|-------------|
| Fixed workbench | Modified HTML/CSS/JS | `frontend/review.html` |
| Passing test run | Updated bug report with 0 critical/major issues | `tests/reports/workbench-ui-bugs-YYYY-MM-DD.md` |

---

## Constraints

- All fixes are client-side only — no backend/API changes
- No changes to the Playwright test script or test fixture
- No new features, UI enhancements, or refactoring beyond what's needed to fix each bug
- Must not regress any of the 46 tests that passed in the original run (56 total − 10 failures)
- The file remains a single monolithic HTML file (per architectural commitment)

---

## Acceptance Criteria

1. **Works when** the lens dropdown on every beat card contains 12+ options (one per lens in the database), not 1, after loading a JSON fixture — verified by `select.lens-select` having ≥12 `<option>` elements

2. **Works when** clicking "Mark as Complete" on a valid, non-conflicting POI triggers `showSuccess()` and the `#successToast` element has the `.visible` class for at least 3 seconds — verified by Playwright checking `#successToast.visible` after upload

3. **Works when** the conflict-target POI (fixture entry #11) is selected and `detectConflictsForPoi()` returns a non-empty `beatConflicts` array containing the hard-match beat (same lens as seeded data) — verified by `.beat-conflict-badge-hard` appearing on the correct beat card

4. **Works when** a hard-conflict beat displays a red badge with text "Conflict (same lens)" and renders a `.conflict-sides` panel with two `.conflict-side` divs showing existing vs incoming script previews

5. **Works when** the soft-conflict beat (≥70% Jaccard) displays an amber badge using a new `.beat-conflict-badge-soft` CSS class (distinct from hard's red) with text "Conflict (XX% similar)" — verified by `.beat-conflict-badge-soft` presence and amber background color

6. **Works when** the review-band beat (30–69% Jaccard) displays a yellow `.beat-conflict-badge-review` badge with text "Review (XX% similar)" and offers "Approve" and "Treat as conflict" action buttons

7. **Works when** hard and soft conflict beats each render a `.conflict-actions` div containing Replace, Skip, Merge, and Change Lens buttons — verified by `[data-beat-action="replace"]`, `[data-beat-action="skip"]`, `[data-beat-action="merge"]` selectors being present

8. **Works when** the Playwright test suite (`tests/test_workbench_ui.py`) re-runs against the fixed workbench and produces 0 critical and 0 major issues in the bug report

---

## Edge Cases

1. If the API returns 0 Lens nodes (database not seeded), the dropdown should show the "Select lens..." placeholder only — not crash or show stale data
2. If `detectConflictsForPoi()` fails (API error), the error is captured in `poi._conflicts.errors` and displayed to the user — conflict UI degrades gracefully to show no badges rather than crashing
3. If a beat's lens string is a display label (e.g., "Hidden History") rather than a slug ("hidden_history"), `resolveLensSlug()` must resolve it correctly for hard-match detection
4. If upload succeeds but then auto-advance to the next POI triggers a re-render before the toast timeout, the success toast must remain visible (not get cleared by the re-render)

---

## Downstream Dependencies

- Passing test suite validates that the Editorial Workbench is ready for real content triage against the Boston POI dataset
- Conflict resolution workflow is a prerequisite for the "Database Upload & Conflict Resolution slice" noted in the north star's Active Build Target
- Fixed workbench becomes the baseline for future regression tests

---

## Open Questions

None — all questions resolved during scope.
