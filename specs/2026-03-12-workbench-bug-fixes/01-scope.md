# Scope: Editorial Workbench Bug Fixes

**Date:** 2026-03-12
**North star ref:** Phase 1 — Content pipeline + Editorial Workbench
**Bug report ref:** `tests/reports/workbench-ui-bugs-2026-03-11.md`

---

## What We're Building

- **Fix lens dropdown population:** Dropdown shows 1 option instead of 12+. Likely an API response parsing issue in `fetchLensesAndPoiList()` (review.html:1899–1913).
- **Fix conflict detection cascade:** `detectConflictsForPoi()` (review.html:2068–2143) either isn't triggering or returns empty results, causing 7 downstream bugs: missing hard/soft/review conflict badges, missing side-by-side comparison panels, and missing resolution action buttons (replace, skip, merge).
- **Add missing `.beat-conflict-badge-soft` CSS class:** Amber badge for soft conflicts (≥70% Jaccard) has no dedicated CSS class — hard badges and soft badges both render as `.beat-conflict-badge-hard`.
- **Fix upload toast reliability:** Ensure `showSuccess()` toast fires and remains visible after successful upload. The uploaded badge is in a collapsed worklist section — the test will adapt to check the toast rather than the badge.

## Why

Conflict detection and resolution is the active build target (north star: "Database Upload & Conflict Resolution slice"). These bugs block the editorial workflow from being usable for real content triage — a Phase 1 gate requirement.

## What We're NOT Building

- No changes to the upload API endpoints or backend logic
- No changes to the Playwright test script or test fixture (separate concern — test re-run after fixes)
- No new features or UI enhancements beyond fixing the 10 reported bugs
- No batch upload changes (out of scope per north star boundaries)

## What Already Exists

- `frontend/review.html` — the monolithic workbench file containing HTML, CSS, and JS (~2200+ lines)
- Conflict detection logic exists at review.html:2068–2143 (hard/soft/review band detection)
- Badge rendering exists at review.html:1530–1535 (hard and review, but soft uses hard's class)
- Side-by-side panels exist at review.html:1538–1584 (conditional on conflict data)
- Resolution buttons exist at review.html:1554–1560 (conditional on conflict data)
- Upload flow exists at review.html:1375–1425 with toast at review.html:833–867
- Lens fetch exists at review.html:1899–1913
- Playwright test: `tests/test_workbench_ui.py` with fixture `tests/fixtures/ui_test_fixture.json`

## Dependencies or Risks

- **Root cause uncertainty:** The 7 conflict bugs likely share a root cause (conflict detection returning empty), but we won't know until we debug with the running stack. Fix may be in the API response shape, the fetch call, or the detection algorithm.
- **Stack dependency:** Reproducing and verifying requires Docker + Neo4j + FastAPI running locally with seeded test data.
- **Lens data dependency:** The lens dropdown fix depends on whether 12 Lens nodes actually exist in the dev Neo4j instance.
