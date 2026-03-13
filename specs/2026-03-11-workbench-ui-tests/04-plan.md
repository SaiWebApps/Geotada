# Implementation Plan: Editorial Workbench UI Test Script

**Date:** 2026-03-11
**Spec ref:** `specs/2026-03-11-workbench-ui-tests/02-spec.md`
**Red team ref:** `specs/2026-03-11-workbench-ui-tests/03-red-team.md`
**North star ref:** Phase 1 — Content pipeline + Editorial Workbench

---

## Part A — Task Breakdown

### Task 1: Create the JSON test fixture

**Files to touch:**
- `tests/fixtures/ui_test_fixture.json` (new)

**What to do:**
Create a JSON array with 12 POI entries matching the fixture design table in the spec (`02-spec.md`, "Fixture design" section). Each entry must use the established schema format (see `tests/fixtures/stress_test_valid.json` for reference).

Key requirements per entry:
1. **Valid standard POI** — Boston coords (42.36xx, -71.05xx), 2 beats, gravity 3–4, lenses `Hidden History` and `Local Legends & Folklore`
2. **High-gravity anchor POI** — gravity 5 on all beats, `script_body` > 500 chars each
3. **Low-gravity POI** — gravity 1, minimal `script_body` (~20 words)
4. **Outside-geofence POI** — New York coords (40.7128, -74.0060)
5. **Invalid-coords POI** — latitude 999, longitude -999
6. **Duplicate-name POI A** — `poi_name: "UI Test — Duplicate Harbor Walk"`, Boston coords
7. **Duplicate-name POI B** — `poi_name: "UI Test — Duplicate Harbor Walk"`, different coords/beats
8. **Multi-lens POI** — 4+ beats across different lenses, distinct gravity values (1, 2, 4, 5)
9. **Empty-beat-text POI** — one beat with `script_body: ""`
10. **Long-text POI** — `poi_name` 80+ chars, `short_description` 300+ chars, `orientation` 200+ chars
11. **Conflict-target POI** — `poi_name: "UI Test Seed — Old North Church"` (matches seed data). 5 beats crafted for specific Jaccard bands:
    - Beat A: lens `hidden_history` (hard match with seeded beat 1)
    - Beat B: lens `music_nightlife` (net-new, no conflict)
    - Beat C: lens `food_culinary`, `script_body` crafted for ≥70% post-stop-word Jaccard vs seeded beat 2 (soft conflict)
    - Beat D: lens `art_street`, `script_body` crafted for 30–69% Jaccard vs seeded beat 3 (review band)
    - Beat E: lens `nature_green`, `script_body` with <30% Jaccard vs any seeded beat (pass-through)
12. **Audit-notes POI** — has `audit_notes` object on beats and `poi_audit_notes` array on POI

**Critical for entry #11:** Compute Jaccard scores using the exact stop-word–filtered algorithm from `frontend/review.html:1871–1888`. Include `_expected_jaccard` comments in the fixture. The stop words list is:

```
a, an, the, is, was, in, on, at, to, of, and, or, for, with, that, this, it, as, by, from, be, are, were, been, has, had, have, do, does, did, but, not, so, if, no, he, she, they, we, you, i, my, your, his, her, its, our, their
```

Algorithm: lowercase → split on whitespace → filter stop words → Jaccard = |intersection| / |union|.

**What NOT to touch:** No existing fixtures. No backend code. No `review.html`.

**Success check:** JSON is valid, parseable, has exactly 12 entries, and entry #11's Jaccard scores land in the correct conflict bands when computed with the algorithm above.

---

### Task 2: Create the Playwright test script scaffold

**Files to touch:**
- `tests/test_workbench_ui.py` (new)

**What to do:**
Create the Playwright test file with:

1. **Imports:** `playwright.sync_api`, `pytest`, `requests`, `json`, `pathlib`, `datetime`
2. **Constants block** (top of file) — all DOM selectors centralized:
   ```python
   # IDs
   CITY_OVERLAY = "#cityOverlay"
   CITY_INPUT = "#cityInput"
   CITY_SUBMIT = "#citySubmitBtn"
   CITY_LABEL = "#cityLabel"
   LOAD_JSON_BTN = "#loadJsonBtn"
   FILE_INPUT = "#fileInput"
   WORKLIST = "#worklist"
   DUP_OVERLAY = "#dupOverlay"
   DUP_RESOLVE_BTN = "#dupResolveBtn"
   DETAIL_VIEW = "#detailView"
   DETAIL_TITLE = "#detailTitle"
   DEFER_BTN = "#deferBtn"
   MARK_COMPLETE_BTN = "#markCompleteBtn"
   ERROR_TOAST = "#errorToast"
   SUCCESS_TOAST = "#successToast"

   # CSS classes
   WORKLIST_ROW = ".worklist-row"
   BADGE_PENDING = ".badge-pending"
   BADGE_COMPLETE = ".badge-complete"
   BADGE_DEFERRED = ".badge-deferred"
   BADGE_FLAGGED = ".badge-flagged"
   BADGE_UPLOADED = ".badge-uploaded"
   BEAT_CARD = ".beat-card"
   BEAT_CONFLICT_BADGE_HARD = ".beat-conflict-badge-hard"
   BEAT_CONFLICT_BADGE_REVIEW = ".beat-conflict-badge-review"
   CONFLICT_SIDE = ".conflict-side"
   MERGE_OVERLAY = ".merge-overlay"
   FIELD_WARNING = ".field-warning"
   AUDIT_NOTES_BOX = ".audit-notes-box"
   POI_AUDIT_NOTES_BOX = ".poi-audit-notes-box"

   # Data attributes
   DATA_FIELD = "[data-field=\"{}\"]"
   DATA_BEAT_FIELD = "[data-beat-field=\"{}\"]"
   DATA_BEAT_INDEX = ".beat-card[data-beat-index=\"{}\"]"
   ```
3. **Configuration:**
   - `API_BASE = "http://localhost:8000/api/v1"`
   - `WORKBENCH_URL = "http://localhost:8000/review.html"` (or wherever FastAPI serves the frontend)
   - `FIXTURE_PATH = Path(__file__).parent / "fixtures" / "ui_test_fixture.json"`
   - `REPORT_DIR = Path(__file__).parent / "reports"`
   - `SCREENSHOT_DIR = REPORT_DIR / "screenshots"`
4. **BugReporter class** — accumulates issues with severity, flow, steps, expected/actual, and screenshot path. Has `save_report()` that writes the markdown bug report to `tests/reports/workbench-ui-bugs-YYYY-MM-DD.md`.
5. **Fixture and seed data setup/teardown** (see Task 3)
6. **Empty test methods** as stubs for each AC group (filled in Tasks 4–7)

**What NOT to touch:** No existing test files. No conftest.py modifications. No backend code.

**Success check:** File imports cleanly, constants are comprehensive, BugReporter writes valid markdown.

---

### Task 3: Implement seed data setup and teardown

**Files to touch:**
- `tests/test_workbench_ui.py` (add to scaffold from Task 2)

**What to do:**
Add a pytest fixture (module-scoped) that:

**Setup:**
1. Verify API is reachable (`GET /api/v1/nodes/Lens?limit=1` — if fails, skip with clear message)
2. Check that 12 lenses exist (`GET /api/v1/nodes/Lens?limit=50`). If missing, seed them via `POST /api/v1/nodes/Lens` with the 12 lens slugs and display labels
3. Create seed POI via API:
   ```
   POST /api/v1/nodes/POI
   {
     "name": "UI Test Seed — Old North Church",
     "latitude": 42.3663,
     "longitude": -71.0544,
     "short_description": "Seed POI for UI conflict detection tests",
     "importance_tier": 1,
     "trigger_radius": 10,
     "typical_duration_min": 30,
     "kid_friendly": "yes"
   }
   ```
4. Create 3 seed beats via `POST /api/v1/nodes/NarrativeBeat`:
   - Beat 1: lens `hidden_history`, gravity 4, ~100-word `script_body` about lantern signals
   - Beat 2: lens `revolutionary`, gravity 3, ~80-word `script_body` about Paul Revere
   - Beat 3: lens `dark_history`, gravity 2, ~60-word `script_body` about British occupation
5. Link beats to POI via `POST /api/v1/edges/HAS_BEAT`
6. Tag beats with lenses via `POST /api/v1/edges/TAGGED_WITH` (look up lens IDs from step 2)
7. Store created node/edge IDs for teardown

**Teardown:**
1. Delete the seed POI by ID via `DELETE /api/v1/nodes/POI/{id}` (cascades per API behavior)
2. Delete the uploaded POI from AC #8 (search by name prefix `"UI Test"` via `GET /api/v1/nodes/POI?limit=100`, filter, delete matches)
3. If lenses were seeded by the test, delete them too (track this)

**Also add:** A Playwright browser fixture (module-scoped) launching Chromium with `headless=False`, `slow_mo=300`.

**What NOT to touch:** No modifications to existing conftest.py. No backend changes.

**Success check:** Setup creates 1 POI + 3 beats + 3 HAS_BEAT edges + 3 TAGGED_WITH edges, all verifiable via GET. Teardown leaves no test data behind.

---

### Task 4: Implement tests for city prompt, JSON load, and duplicate resolver (ACs #1–2)

**Files to touch:**
- `tests/test_workbench_ui.py`

**What to do:**

1. **City prompt flow:**
   - Navigate to workbench URL
   - Assert `#cityOverlay` is visible
   - Type "Boston" into `#cityInput`
   - Click `#citySubmitBtn`
   - Wait for overlay to be hidden (timeout 10s for Nominatim)
   - Assert `#cityLabel` contains "Boston"
   - If overlay doesn't close, log as bug and attempt to proceed

2. **JSON load flow:**
   - Click `#loadJsonBtn`
   - Use Playwright's `set_input_files()` on the hidden `#fileInput` to load `ui_test_fixture.json`
   - Wait for worklist to populate

3. **Duplicate resolver (AC #2):**
   - Assert `#dupOverlay` becomes visible (entries #6 and #7 share a name)
   - Find the rename input for one duplicate entry
   - Clear and type a new name (e.g., append " (2)")
   - Click `#dupResolveBtn`
   - Assert overlay closes

4. **Worklist rendering (AC #1):**
   - Wait up to 5 seconds for `.worklist-row` count to equal 12
   - If count ≠ 12, log bug with actual count
   - Screenshot the worklist

**What NOT to touch:** No POI detail tests yet. No edit tests.

**Success check:** Test navigates from city prompt through JSON load to populated worklist. Duplicate resolver fires and resolves. 12 POIs visible.

---

### Task 5: Implement tests for POI detail, editing, badges, and beat rendering (ACs #3–7, #9–12)

**Files to touch:**
- `tests/test_workbench_ui.py`

**What to do:**

1. **Detail view rendering (AC #3):**
   - Click each `.worklist-row` in sequence
   - For each POI, assert `[data-field="poi_name"]` value matches fixture
   - Assert `[data-field="latitude"]` and `[data-field="longitude"]` match
   - Assert `[data-field="short_description"]` matches
   - Screenshot on any mismatch

2. **Geofence flag (AC #4):**
   - Navigate to outside-geofence POI (entry #4)
   - Assert `.badge-flagged` is visible on its worklist row
   - Assert a yellow geofence warning is visible in the detail view
   - Screenshot

3. **Invalid coords (AC #5):**
   - Navigate to invalid-coords POI (entry #5)
   - Assert `.field-warning` elements appear near latitude/longitude fields
   - Assert map shows "Invalid coordinates" message
   - Attempt to click `#markCompleteBtn` — assert it's blocked or shows error
   - Screenshot

4. **Edit persistence (AC #6):**
   - Navigate to a valid POI (entry #1)
   - Change `[data-field="poi_name"]` value
   - Change a beat's `[data-beat-field="script_body"]` value
   - Navigate to a different POI (click another worklist row)
   - Navigate back to the edited POI
   - Assert edited values persisted
   - Screenshot on mismatch

5. **Defer/re-select flow (AC #7):**
   - Navigate to a valid POI (entry #3)
   - Click `#deferBtn`
   - Assert the POI's worklist badge changes to `.badge-deferred`
   - Click the deferred POI's worklist row again
   - Click `#markCompleteBtn` (or equivalent to un-defer)
   - Assert badge changes appropriately
   - Screenshot

6. **Beat rendering (ACs #9, #10, #12):**
   - For multi-lens POI (entry #8), assert `.beat-card` count matches fixture beat count
   - For each beat card, assert all 5 fields are present: `script_body`, `physical_cue`, `lens`, `gravity`, `source_passage`
   - Assert lens dropdown contains 12 options
   - Assert beat count header text "Narrative Beats (N)" matches actual N
   - Screenshot

7. **Beat editing (AC #11):**
   - Change a beat's lens via the `[data-beat-field="lens"]` dropdown
   - Change gravity from 3 to 4 via `[data-beat-field="gravity"]` input
   - Navigate away, navigate back
   - Assert changed values persist
   - Screenshot on mismatch

8. **Edge cases:**
   - Empty beat text (entry #9): assert warning visible, "Mark as Complete" blocked
   - Gravity boundaries (entries #2 and #3): assert gravity 1 and 5 render without warnings
   - Long text (entry #10): assert no overflow / truncation in worklist row
   - Audit notes (entry #12): assert `.audit-notes-box` and `.poi-audit-notes-box` are rendered

**What NOT to touch:** No upload tests. No conflict tests.

**Success check:** All detail view assertions log results (pass or bug). Edit persistence verified. Beat rendering matches fixture data.

---

### Task 6: Implement tests for upload flow and error handling (ACs #8, #12a)

**Files to touch:**
- `tests/test_workbench_ui.py`

**What to do:**

1. **Single-POI upload (AC #8):**
   - Navigate to valid standard POI (entry #1)
   - Ensure it's in a "completable" state (no empty beats, valid coords)
   - Click `#markCompleteBtn`
   - Wait for upload to complete (watch for badge change or success toast)
   - Assert POI status changes to "uploaded" (`.badge-uploaded` visible)
   - Assert POI moves to the uploaded section in the worklist
   - Verify via API: `GET /api/v1/graph/poi/{poi_name}/beats` returns the uploaded beats
   - Screenshot the uploaded state

2. **Error handling (AC #12a):**
   - This is harder to trigger with a real stack. Strategy: attempt to upload the invalid-coords POI (entry #5) after manually fixing coords to trigger a different error, OR verify the error toast mechanism exists by checking the DOM.
   - Alternative: temporarily make the API unreachable (not recommended). Instead, assert that `#errorToast` element exists in the DOM and has the correct structure (visible on error, dismissable).
   - Document the error handling test approach in the bug report as a manual verification item if it can't be automated cleanly.

**What NOT to touch:** No conflict detection tests. No backend modifications.

**Success check:** One POI successfully uploads via the progressive flow. Upload verified via API GET. Error toast structure confirmed.

---

### Task 7: Implement tests for conflict detection and resolution (ACs #13–18)

**Files to touch:**
- `tests/test_workbench_ui.py`

**What to do:**

1. **Trigger conflict detection (AC #13):**
   - Navigate to conflict-target POI (entry #11, name `"UI Test Seed — Old North Church"`)
   - Click `#markCompleteBtn` to trigger conflict detection
   - Wait for conflict overlay/panel to appear

2. **Hard conflict — beat A (AC #13):**
   - Find beat A's card (same lens `hidden_history` as seeded beat)
   - Assert red conflict badge (`.beat-conflict-badge-hard`) is visible
   - Assert badge text contains "Conflict (same lens)" or similar
   - Assert side-by-side comparison panel (`.conflict-side`) is visible
   - Assert both existing and incoming script previews are rendered
   - Screenshot

3. **Net-new beat — beat B (AC #14):**
   - Find beat B's card (lens `music_nightlife`)
   - Assert NO conflict badge present
   - Screenshot

4. **Soft conflict ≥70% — beat C (AC #15):**
   - Find beat C's card
   - Assert amber conflict badge with "Conflict (XX% similar)"
   - Assert side-by-side panel visible
   - Screenshot

5. **Review band 30–69% — beat D (AC #16):**
   - Find beat D's card
   - Assert yellow review badge (`.beat-conflict-badge-review`) with "Review (XX% similar)"
   - Assert "approve" and "treat as conflict" actions are available
   - Screenshot

6. **Pass-through <30% — beat E (AC #17):**
   - Find beat E's card
   - Assert NO conflict badge present
   - Screenshot

7. **Conflict resolution actions (AC #18):**
   - On the hard-conflict beat (A): select "Replace" → assert "Will replace existing" label
   - On the soft-conflict beat (C): select "Skip" → assert "Will skip incoming" label
   - On the review-band beat (D): select "Merge" → assert merge overlay opens → select field values for `script_body`, `gravity`, `lens` → confirm
   - Create a scenario for "Change lens" — select it on one of the conflict beats → assert lens dropdown appears → select a new lens
   - Screenshot each resolution state

**What NOT to touch:** No modifications to conflict detection logic. No backend changes.

**Success check:** All 5 conflict bands render correct badges. All 4 resolution actions produce correct labels. Screenshots captured for each state.

---

### Task 8: Implement bug report generation and final cleanup

**Files to touch:**
- `tests/test_workbench_ui.py`

**What to do:**

1. **Bug report finalization:**
   - After all tests run, the BugReporter's `save_report()` generates the markdown file at `tests/reports/workbench-ui-bugs-YYYY-MM-DD.md`
   - Report includes the summary (tests run, issues found by severity, screenshots captured)
   - Each issue follows the template: severity, flow, steps, expected, actual, screenshot link
   - Ensure screenshot paths in the report are relative (e.g., `screenshots/ac1-worklist-count.png`)

2. **Ensure reports directory exists:**
   - Create `tests/reports/` and `tests/reports/screenshots/` in test setup if they don't exist

3. **Final test verification:**
   - Run the full script end-to-end with the stack running
   - Verify all 18 ACs are exercised
   - Verify the bug report is generated with correct structure
   - Verify all screenshots are saved

**What NOT to touch:** No review.html. No backend. No existing tests.

**Success check:** Bug report generated at expected path. Screenshots directory populated. Report markdown is valid and follows the spec template.

---

## Part B — Test Definitions

Each test maps to one or more acceptance criteria from the spec.

### T1 — Worklist renders all POIs after JSON load (AC #1)

- **Type:** Integration (Playwright)
- **Expected:** After city prompt + JSON load + duplicate resolution, `.worklist-row` count equals 12 within 5 seconds
- **Edge cases:** Duplicate resolver fires for entries #6/#7; both remain after rename

### T2 — Duplicate resolver overlay appears and resolves (AC #2)

- **Type:** Integration (Playwright)
- **Expected:** `#dupOverlay` becomes visible after JSON load. After renaming one entry and clicking `#dupResolveBtn`, overlay closes. Worklist shows 12 distinct entries.
- **Edge cases:** Only one duplicate pair (entries #6/#7)

### T3 — Detail view renders correct field values (AC #3)

- **Type:** Integration (Playwright)
- **Expected:** For each POI clicked, `[data-field="poi_name"]`, `[data-field="latitude"]`, `[data-field="longitude"]`, `[data-field="short_description"]` values match fixture data
- **Edge cases:** Long text (entry #10), empty beat (entry #9)

### T4 — Geofence flag renders for outside-geofence POI (AC #4)

- **Type:** Integration (Playwright)
- **Expected:** Entry #4 (New York coords) shows `.badge-flagged` in worklist and yellow geofence warning in detail
- **Edge cases:** None

### T5 — Invalid coords show warnings and block upload (AC #5)

- **Type:** Integration (Playwright)
- **Expected:** Entry #5 (lat 999, lng -999) shows `.field-warning` near coordinate fields. Map shows "Invalid coordinates — pin removed." `#markCompleteBtn` click is blocked or shows error.
- **Edge cases:** None

### T6 — Edit persistence across navigation (AC #6)

- **Type:** Integration (Playwright)
- **Expected:** Edit POI name and beat script_body on entry #1. Navigate to entry #2. Navigate back to entry #1. Edited values are preserved.
- **Edge cases:** Tests both POI-level and beat-level field persistence

### T7 — Defer and re-select flow (AC #7)

- **Type:** Integration (Playwright)
- **Expected:** Defer entry #3 → `.badge-deferred` visible. Re-click entry #3 → mark complete → badge changes.
- **Edge cases:** None

### T8 — Single-POI upload via Mark as Complete (AC #8)

- **Type:** Integration (Playwright + API verification)
- **Expected:** Mark entry #1 complete → upload fires → `.badge-uploaded` appears → POI moves to uploaded worklist section → `GET /api/v1/graph/poi/{name}/beats` returns beats
- **Edge cases:** Upload is progressive (immediate, not batched)

### T9 — Beat card renders all five fields (AC #9)

- **Type:** Integration (Playwright)
- **Expected:** Each `.beat-card` contains visible elements for `script_body`, `physical_cue`, `lens`, `gravity`, `source_passage`. Lens dropdown has 12 options.
- **Edge cases:** Empty script_body (entry #9) shows warning

### T10 — Multi-lens POI renders all beats (AC #10)

- **Type:** Integration (Playwright)
- **Expected:** Entry #8 (4+ beats) renders all beat cards. Each has correct lens selected and distinct gravity value.
- **Edge cases:** None

### T11 — Beat editing persists (AC #11)

- **Type:** Integration (Playwright)
- **Expected:** Change lens dropdown value and gravity input on a beat. Navigate away and back. Values persist.
- **Edge cases:** Lens change via dropdown, gravity boundary values

### T12 — Beat count header matches (AC #12)

- **Type:** Integration (Playwright)
- **Expected:** Section header text "Narrative Beats (N)" where N matches fixture beat count for each POI
- **Edge cases:** POI with 1 beat vs 4+ beats

### T12a — Error handling on upload failure (AC #12a)

- **Type:** Integration (Playwright) / Manual verification
- **Expected:** `#errorToast` exists in DOM, displays human-readable error with error code on API failure, remains visible until dismissed
- **Edge cases:** May require manual verification if API errors can't be triggered cleanly

### T13 — Hard conflict badge and side-by-side panel (AC #13)

- **Type:** Integration (Playwright)
- **Expected:** After triggering "Mark as Complete" on entry #11, beat A (lens `hidden_history`) shows `.beat-conflict-badge-hard` with "Conflict (same lens)" text and `.conflict-side` panel with both script previews
- **Edge cases:** None

### T14 — Net-new beat shows no conflict (AC #14)

- **Type:** Integration (Playwright)
- **Expected:** Beat B (lens `music_nightlife`) on entry #11 has no conflict badge
- **Edge cases:** None

### T15 — Soft conflict ≥70% Jaccard (AC #15)

- **Type:** Integration (Playwright)
- **Expected:** Beat C shows amber badge with "Conflict (XX% similar)" and `.conflict-side` panel
- **Edge cases:** Jaccard score must land ≥70% after stop-word filtering

### T16 — Review band 30–69% Jaccard (AC #16)

- **Type:** Integration (Playwright)
- **Expected:** Beat D shows `.beat-conflict-badge-review` with "Review (XX% similar)". "Approve" and "treat as conflict" actions visible.
- **Edge cases:** Jaccard score must land 30–69% after stop-word filtering

### T17 — Pass-through <30% Jaccard (AC #17)

- **Type:** Integration (Playwright)
- **Expected:** Beat E has no conflict badge
- **Edge cases:** Jaccard score must be <30% after stop-word filtering

### T18 — All four conflict resolution actions (AC #18)

- **Type:** Integration (Playwright)
- **Expected:** Replace → "Will replace existing" label. Skip → "Will skip incoming" label. Merge → overlay opens with `script_body`, `gravity`, `lens` fields only. Change-lens → lens dropdown appears.
- **Edge cases:** Merge overlay limited to 3 fields (not `physical_cue` or `source_passage`)

### T-EC1 — Empty script_body blocks Mark as Complete

- **Type:** Integration (Playwright)
- **Expected:** Entry #9 with empty beat text shows warning. "Mark as Complete" is blocked.
- **Edge cases:** None

### T-EC2 — Gravity boundaries render without warnings

- **Type:** Integration (Playwright)
- **Expected:** Entry #2 (gravity 5) and entry #3 (gravity 1) show no `.field-warning` on gravity fields
- **Edge cases:** None

### T-EC3 — Long text doesn't overflow containers

- **Type:** Integration (Playwright)
- **Expected:** Entry #10 (80+ char name, 300+ char description) renders without visible overflow or truncation in the worklist row
- **Edge cases:** Visual assertion — check bounding box doesn't exceed parent

### T-EC4 — Audit notes render in correct containers

- **Type:** Integration (Playwright)
- **Expected:** Entry #12 shows beat-level audit notes in `.audit-notes-box` and POI-level notes in `.poi-audit-notes-box`
- **Edge cases:** Two different data shapes (object vs array)

### T-EC5 — Map marker syncs on coordinate edit

- **Type:** Integration (Playwright)
- **Expected:** Edit latitude/longitude inputs to valid values → map marker position updates
- **Edge cases:** May need to trigger `input` event on the fields

---

## Part C — Claude Code Prompt

```
## Task

Build a Playwright (Python) UI test script and JSON fixture that systematically exercises
the Editorial Review Workbench (review.html) through its complete workflow, producing a
markdown bug report with screenshots.

## What to build

Read these files before starting:
- specs/2026-03-11-workbench-ui-tests/02-spec.md (the full spec with all acceptance criteria)
- specs/2026-03-11-workbench-ui-tests/03-red-team.md (resolved blockers and risks)
- specs/2026-03-11-workbench-ui-tests/04-plan.md (this plan — task breakdown and test defs)
- frontend/review.html (the workbench under test — read fully to understand DOM selectors)
- tests/fixtures/stress_test_valid.json (reference for JSON fixture format)

Follow the 8 tasks in Part A of 04-plan.md in order:

1. Create `tests/fixtures/ui_test_fixture.json` — 12 POI entries per the fixture design
   table. CRITICAL: Entry #11's beat text must produce specific Jaccard similarity scores
   using the stop-word-filtered algorithm from review.html:1871–1888. Compute scores
   explicitly and include `_expected_jaccard` fields.

2. Create `tests/test_workbench_ui.py` — Playwright test with:
   - All DOM selectors centralized in a constants block at the top
   - BugReporter class that accumulates issues and generates markdown report
   - Configuration: API_BASE, WORKBENCH_URL, FIXTURE_PATH, REPORT_DIR, SCREENSHOT_DIR
   - Browser launched with headless=False, slow_mo=300

3. Seed data setup/teardown as a module-scoped pytest fixture:
   - Setup: verify API, check/seed lenses, create seed POI + 3 beats + edges
   - Teardown: delete ALL test data (prefix "UI Test") via DETACH DELETE or API cascade

4. Tests for city prompt → JSON load → duplicate resolver → worklist (ACs #1–2)

5. Tests for detail view, editing, badges, beats (ACs #3–7, #9–12, edge cases)

6. Tests for upload flow (AC #8) and error handling (AC #12a)

7. Tests for conflict detection and all resolution actions (ACs #13–18)

8. Bug report generation at tests/reports/workbench-ui-bugs-YYYY-MM-DD.md

## Key DOM selectors (from review.html)

IDs: #cityOverlay, #cityInput, #citySubmitBtn, #cityLabel, #loadJsonBtn, #fileInput,
#worklist, #dupOverlay, #dupResolveBtn, #detailView, #detailTitle, #deferBtn,
#markCompleteBtn, #errorToast, #successToast

Classes: .worklist-row, .badge-pending, .badge-complete, .badge-deferred, .badge-flagged,
.badge-uploaded, .beat-card, .beat-conflict-badge-hard, .beat-conflict-badge-review,
.conflict-side, .merge-overlay, .field-warning, .audit-notes-box, .poi-audit-notes-box

Data attrs: [data-field="poi_name"], [data-field="latitude"], [data-field="longitude"],
[data-field="short_description"], [data-field="orientation"],
[data-beat-field="script_body"], [data-beat-field="physical_cue"],
[data-beat-field="lens"], [data-beat-field="gravity"], [data-beat-field="source_passage"],
.beat-card[data-beat-index="N"]

Duplicate resolver: #dupOverlay, input[data-dup-idx="N"], #dupResolveBtn

## API endpoints used

- GET  /api/v1/nodes/Lens?limit=50 — fetch lenses
- POST /api/v1/nodes/Lens — seed lens
- POST /api/v1/nodes/POI — create POI
- POST /api/v1/nodes/NarrativeBeat — create beat
- POST /api/v1/edges/HAS_BEAT — link beat to POI
- POST /api/v1/edges/TAGGED_WITH — tag beat with lens
- GET  /api/v1/graph/poi/{poi_name}/beats — verify upload
- GET  /api/v1/nodes/POI?limit=100 — find test POIs for cleanup
- DELETE /api/v1/nodes/POI/{id} — delete POI (cascades)

## Conflict detection algorithm (review.html:1871–1888)

Stop words: a, an, the, is, was, in, on, at, to, of, and, or, for, with, that, this,
it, as, by, from, be, are, were, been, has, had, have, do, does, did, but, not, so, if,
no, he, she, they, we, you, i, my, your, his, her, its, our, their

Algorithm: lowercase → split whitespace → filter stop words → Jaccard = |A∩B| / |A∪B|

Bands: ≥0.70 = soft conflict (amber), 0.30–0.69 = review (yellow), <0.30 = pass-through
Hard conflict = same lens as existing beat (separate from Jaccard)

## Constraints

- headless=False, slow_mo=300 (visible browser)
- Never modify review.html
- No mocks — hit real stack (FastAPI + Neo4j on localhost:8000)
- Failed assertions log bugs, don't stop the suite
- Screenshot on every issue
- Idempotent: seed in setup, clean in teardown
- All test POI names prefixed with "UI Test" for safe cleanup

## Best practices checklist (must implement)

- [ ] All DOM selectors in one constants block (Risk R1 mitigation)
- [ ] Nominatim timeout handling — 10s wait for city prompt (Risk R2)
- [ ] DETACH DELETE cascade in teardown (Risk R3)
- [ ] Lens existence check + seed-if-missing in setup (Risk R4)
- [ ] No secrets or credentials in test code
- [ ] Test data isolated with "UI Test" prefix
- [ ] Jaccard scores computed with exact stop-word algorithm, verified in fixture comments
- [ ] Bug report follows spec template (severity, flow, steps, expected, actual, screenshot)

## What NOT to touch

- frontend/review.html — read only
- Existing test files (test_api_*.py, conftest.py)
- Backend source code (src/)
- Existing fixtures (stress_test_*.json)

Before starting, confirm you understand the full scope and flag any conflicts with the
existing codebase or assumptions you are making.
```

---

## Part D — Best Practices Implementation Checklist

### From Red Team Risk Mitigations

| # | Practice | Task(s) | How to verify |
|---|----------|---------|---------------|
| D1 | All DOM selectors centralized in constants block | Task 2 | Single `# Selectors` section at top of test file; no hardcoded selectors elsewhere |
| D2 | Nominatim timeout handling (10s wait) | Task 4 | City prompt test uses `timeout=10000` on overlay hide assertion |
| D3 | DETACH DELETE cascade in teardown | Task 3 | Teardown deletes seed POI + uploaded POI + any "UI Test" prefixed nodes; verify via GET after teardown |
| D4 | Lens existence check + seed-if-missing | Task 3 | Setup checks lens count, seeds 12 if missing; test still works on fresh DB |

### From Security & Privacy Practices

| # | Practice | Task(s) | How to verify |
|---|----------|---------|---------------|
| D5 | No secrets in test code | Task 2 | No API keys, passwords, or credentials anywhere in test file; all endpoints are localhost |
| D6 | Test data isolation | Tasks 1, 3 | All POI names prefixed with "UI Test"; teardown cleans all test data |
| D7 | Data retention — test cleanup | Task 3 | Teardown deletes ALL test-created nodes (seed + uploaded); verify nothing remains via API |
| D8 | Input validation testing | Tasks 5, 6 | AC #5 verifies invalid coords blocked from upload; AC #12a verifies error messages |

### From UX Best Practices

| # | Practice | Task(s) | How to verify |
|---|----------|---------|---------------|
| D9 | Complete workflow coverage | Tasks 4–7 | Test exercises: city prompt → load → resolve → browse → edit → defer → complete → upload → conflict |
| D10 | Edge case coverage | Task 5 | Invalid coords, empty beats, long text, duplicate names, gravity boundaries, audit notes all tested |
| D11 | Error state coverage | Task 6 | AC #12a tested — error toast with human-readable message and error code |
| D12 | Conflict resolution completeness | Task 7 | All 4 actions tested (replace, skip, merge, change-lens); merge scoped to 3 fields only |

### From Performance

| # | Practice | Task(s) | How to verify |
|---|----------|---------|---------------|
| D13 | Rendering performance baseline | Task 4 | AC #1 asserts worklist renders 12 POIs within 5 seconds |

---

## North Star Final Check

- **Phase alignment:** This work directly supports Phase 1 ("Content pipeline + Editorial Workbench"). The workbench must be verified before editorial workflows begin.
- **Architectural commitments:** No new dependencies or architectural changes. Playwright is already in `.venv`. Tests use the existing API and frontend as-is.
- **Explicit boundaries respected:** No fixes to `review.html` (those come after the bug report). No CI automation (visible browser only). No backend modifications.
- **No short-sighted decisions detected.** The test fixture and seed data patterns establish conventions for future test suites without over-engineering.
