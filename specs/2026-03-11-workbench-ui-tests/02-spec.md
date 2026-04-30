# Contract Spec: Editorial Workbench UI Test Script

**Date:** 2026-03-11
**Scope ref:** `specs/2026-03-11-workbench-ui-tests/01-scope.md`
**North star ref:** Phase 1 — Content pipeline + Editorial Workbench

---

## Purpose

A Playwright (Python) test script + purpose-built JSON fixture that systematically exercises the Editorial Review Workbench (`review.html`) through its complete workflow, producing a markdown bug report documenting every UI issue found — with screenshots, reproduction steps, and severity.

---

## Inputs

| Input | Shape | Source |
|-------|-------|--------|
| **Test fixture** | JSON array of POI objects (V2 schema) | New file: `tests/fixtures/ui_test_fixture.json` |
| **Seed data** | 1 POI with 3 beats, seeded into Neo4j via API before test run | Test setup step (cleaned up in teardown) |
| **Running stack** | Docker + Neo4j + FastAPI on `localhost:8000` | Developer starts manually before running tests |
| **City name** | `"Paris"` hardcoded in test | Matches launch city in north star |

### Fixture design

The JSON must include entries that trigger these specific UI states:

| # | Entry | Purpose | Key properties |
|---|-------|---------|---------------|
| 1 | Valid standard POI | Happy path baseline | Valid Paris coords, 2 beats, gravity 3–4, known lenses |
| 2 | High-gravity anchor POI | Gravity boundary (5) | Gravity 5 on all beats, long `script_body` (>500 chars) |
| 3 | Low-gravity POI | Gravity boundary (1) | Gravity 1, minimal `script_body` |
| 4 | Outside-geofence POI | Geofence flag flow | Coords in New York (~340km from Paris) |
| 5 | Invalid-coords POI | Coord validation | Latitude 999, longitude -999 |
| 6 | Duplicate-name POI A | Duplicate resolver (pair 1/2) | Same `poi_name` as entry #7 |
| 7 | Duplicate-name POI B | Duplicate resolver (pair 2/2) | Same `poi_name` as entry #6 |
| 8 | Multi-lens POI | Multiple lenses + beat editing | 4+ beats across different lenses, distinct gravity values |
| 9 | Empty-beat-text POI | Empty script_body warning | One beat with `script_body: ""` |
| 10 | Long-text POI | Text overflow / truncation | `poi_name` 80+ chars, `short_description` 300+ chars, `orientation` 200+ chars |
| 11 | Conflict-target POI | All conflict bands in one POI | `poi_name` matches seeded POI, 5 beats: beat A same lens as seeded (hard match), beat B net-new lens (no conflict), beat C different lens with ≥70% post-stop-word Jaccard vs seeded beat (soft conflict), beat D different lens with 30–69% Jaccard (review band), beat E different lens with <30% Jaccard (pass-through) |
| 12 | Audit-notes POI | Audit notes rendering | Has `audit_notes` object on POI and beats, has `poi_audit_notes` array |

### Seed data design

Before the test suite runs, seed one POI into Neo4j via the API:

- **POI name:** `"UI Test Seed — Sacré-Cœur"` (unique prefix avoids collision with real data)
- **Beats (3):**
  - Beat 1: lens `hidden_history`, gravity 4, 100-word `script_body` about lantern signals
  - Beat 2: lens `revolutionary_moments`, gravity 3, 80-word `script_body` about Paul Revere
  - Beat 3: lens `dark_history`, gravity 2, 60-word `script_body` about British occupation

Fixture entry #11 uses `poi_name: "UI Test Seed — Sacré-Cœur"` and its 5 beats are crafted to hit specific Jaccard similarity bands against the seeded beats. **Critical:** Jaccard scores must be computed using the same stop-word–filtered algorithm as `review.html` (lines 1878–1888) to ensure beats land in the correct conflict bands. Include the expected post-filtering Jaccard score as a comment in the fixture (e.g., `"_expected_jaccard": 0.74`).

---

## Outputs

| Output | Format | Destination |
|--------|--------|-------------|
| **Bug report** | Markdown file | `tests/reports/workbench-ui-bugs-YYYY-MM-DD.md` |
| **Screenshots** | PNG files | `tests/reports/screenshots/` |
| **Test log** | Console output (stdout) | Terminal (visible browser) |

### Bug report structure

```markdown
# Editorial Workbench UI Bug Report — {date}

## Summary
- Tests run: N
- Issues found: N (X critical, Y major, Z minor)
- Screenshots captured: N

## Issues

### [SEVERITY] Short title
- **Flow:** Which workflow stage this occurs in
- **Steps:** Numbered reproduction steps
- **Expected:** What should happen
- **Actual:** What actually happens
- **Screenshot:** Link to screenshot file
```

**Severity definitions:**
- **Critical** — blocks the workflow (can't proceed past this point)
- **Major** — data loss, incorrect data sent to API, or misleading UI state
- **Minor** — cosmetic, layout, or UX issue that doesn't block functionality

---

## Constraints

- **Visible browser only** — `headless=False`, `slow_mo=300` so developer can watch
- **No fixes** — script observes and reports, never modifies `review.html`
- **No mocks** — tests hit the real running stack (FastAPI + Neo4j)
- **Assertion = observation** — failed assertions don't stop the suite; they get logged as issues in the bug report
- **Screenshot on every issue** — automatic capture when an assertion fails or unexpected state is detected
- **Idempotent** — test seeds its own data via API in setup, cleans up in teardown; running twice produces the same results

---

## Acceptance Criteria

### Workflow flow

1. **Works when** the test script loads the fixture via the file picker, and the worklist renders all 12 POIs (12 unique after duplicate resolution — entries #6/#7 both remain, one renamed) within 5 seconds
2. **Works when** the duplicate resolver overlay appears for the duplicate-name entries, and the test renames one entry to resolve the conflict
3. **Works when** the test clicks through every POI in the worklist and the detail view renders with correct field values matching the fixture data
4. **Works when** the outside-geofence POI shows a yellow geofence warning and a `flagged` badge in the worklist
5. **Works when** the invalid-coords POI shows red field warnings for latitude and longitude, the map shows "Invalid coordinates — pin removed", and the POI is blocked from "Mark as Complete" until coordinates are corrected (client-side validation gate)
6. **Works when** the test edits a POI name, beat script_body, lens selection, and gravity — and the changes persist when navigating away and back
7. **Works when** the test defers a POI and its badge changes to "deferred", then re-selects it and marks it complete
8. **Works when** the test marks a valid POI as complete, the POI is immediately uploaded to Neo4j via the progressive single-POI upload flow (POST /api/v1/nodes/POI + beat/edge creation), the status changes to "uploaded", and the POI moves to the uploaded section in the worklist

### Beat rendering and editing

9. **Works when** each beat card renders all five fields (script_body, physical_cue, lens, gravity, source_passage) with values matching the fixture data, and the lens dropdown is populated with all 12 lenses
10. **Works when** the multi-lens POI (4+ beats) renders all beat cards in order, each with the correct lens selected and distinct gravity values displayed
11. **Works when** editing a beat's lens via the dropdown changes the selection, and editing gravity to a valid value (e.g., 3→4) persists after navigating away and back
12. **Works when** the beat count in the section header ("Narrative Beats (N)") matches the actual number of beats in the fixture for each POI

### Error handling

12a. **Works when** the UI displays an explicit, human-readable error message with an error code when the API returns an error during upload (e.g., network failure, validation rejection), and the error toast remains visible until dismissed

### Conflict detection and resolution

13. **Works when** the test triggers "Mark as Complete" on the conflict-target POI (entry #11), and the hard-conflict beat (same lens as seeded data) shows a red conflict badge with "Conflict (same lens)" and renders a side-by-side comparison panel showing both the existing and incoming script previews
14. **Works when** the net-new beat (beat B) on the conflict-target POI shows no conflict badge and is ready for normal create
15. **Works when** the near-duplicate beat (beat C, ≥70% post-stop-word Jaccard similarity) shows an amber conflict badge with "Conflict (XX% similar)" and renders the side-by-side comparison panel
16. **Works when** the review-band beat (beat D, 30–69% similarity) shows a yellow review badge with "Review (XX% similar)" and offers both "approve" and "treat as conflict" actions
17. **Works when** the pass-through beat (beat E, <30% similarity) shows no conflict badge and proceeds as a normal create
18. **Works when** the test exercises all four conflict resolution actions — replace (shows "Will replace existing"), skip (shows "Will skip incoming"), merge (opens merge overlay for field-by-field selection of script_body, gravity, and lens only), and change-lens (shows lens dropdown) — and each displays the correct resolved label

---

## Edge Cases

1. Empty `script_body` beat shows warning text and blocks "Mark as Complete" until content is added
2. Gravity boundary values (1 and 5) render without validation warnings; values outside 1–5 show warnings
3. Long text fields (80+ char POI name, 300+ char description) don't overflow their containers or get truncated in the worklist
4. Audit notes (object format on beats, array format on POI) render in their respective `.audit-notes-box` / `.poi-audit-notes-box` sections
5. Map marker syncs when coordinate inputs are manually edited to valid values

---

## Downstream Dependencies

- Bug report feeds into a separate planned bug-fix effort (not in this scope)
- Test fixture becomes reusable reference for future regression testing
- Seed data pattern (API setup/teardown) establishes the convention for future UI test suites

---

## Open Questions

1. ~~Seed data dependency~~ **Resolved:** Test seeds its own POI + beats via API in setup, cleans up in teardown. Uses unique `"UI Test Seed —"` prefix to avoid collision.
2. ~~Upload cleanup~~ **Resolved:** Teardown deletes all test data including the uploaded POI from AC #8. Uses DETACH DELETE to cascade-remove related beats, edges, and relationships. Idempotency requires full cleanup.
3. ~~Batch upload testing~~ **Resolved:** Not in scope — batch upload is not part of the current workflow. Only progressive single-POI upload (Mark as Complete) is tested.
4. ~~Lens seeding~~ **Resolved:** The 12 lenses should already exist in the dev Neo4j instance. If missing, test setup seeds them before the test run.
