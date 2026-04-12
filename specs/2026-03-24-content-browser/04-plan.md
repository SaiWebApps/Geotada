# Implementation Plan — Content Browser Workbench

**Date:** 2026-03-24
**Spec:** [02-spec.md](02-spec.md)
**Red Team:** [03-red-team.md](03-red-team.md)
**Status:** Approved

---

## Part A — Task Breakdown

### Task 1: Introduce compound selection model

**Files to touch:** `frontend/review.html` (~lines 958, 1525–1568, 1590–1596)

**What to do:**
- Replace `let activeIdx = -1` with a compound selector: `let activeSelection = { source: null, idx: -1 }` where `source` is `'incoming'` or `'db'`.
- Create a helper `getSelectedPoi()` that returns the correct object from either `poiData[idx]` (when source is `'incoming'`) or `cachedPoiList[idx]` (when source is `'db'`).
- Update `autoSaveCurrent()` to only run when `activeSelection.source === 'incoming'` (DB POIs are read-only).
- Update `panPersistentMapTo()` to read coordinates from the correct source object (DB POIs use `properties.location.lat/lng`, incoming use `latitude/longitude`).

**What NOT to touch:** `poiData[]` array shape, `_status` enum values, `updateProgress()`, `checkAllComplete()`, `canMarkComplete()`. These continue to operate only on `poiData[]`.

**Success check:** The app loads and selects incoming JSON POIs the same as before. No regressions in existing worklist click → detail flow.

---

### Task 2: Render DB POIs in the worklist

**Files to touch:** `frontend/review.html` — `renderWorklist()` (~lines 1442–1523)

**What to do:**
- After rendering the existing `poiData` active/uploaded sections, render a new "Database POIs" section below.
- Iterate `cachedPoiList` and render each as a worklist row with:
  - POI name from `poi.properties.name`
  - A `<span class="badge badge-db">DB</span>` badge (styled with `--blue` color vars)
  - Beat count showing `"--"` (lazy load — no fetch on render)
  - If the DB POI has `_incomingBeats` (set later by Task 5), show an additional badge: `<span class="badge badge-incoming">+ Incoming</span>`
- Click handler calls `selectPoi()` with `{ source: 'db', idx: i }` (index into `cachedPoiList`).
- Add CSS for `.badge-db` (blue background) and `.badge-incoming` (orange background).

**What NOT to touch:** The existing `poiData` rendering logic. DB POIs are a separate section, not mixed into `poiData` iteration.

**Success check:** After selecting a city, the worklist shows DB POIs with "DB" badges below the "No entries loaded" message (or below incoming POIs if JSON is loaded). Clicking a DB POI updates `activeSelection`.

---

### Task 3: Render read-only detail panel for DB POIs

**Files to touch:** `frontend/review.html` — `renderDetail()` (~lines 1712–1960), `selectPoi()` (~line 1566)

**What to do:**
- Modify `selectPoi()` to accept either a number (legacy, source='incoming') or a `{ source, idx }` object. Normalize internally.
- When `activeSelection.source === 'db'`:
  - Fetch beats via `GET /graph/poi/{name}/beats` (with loading skeleton). Cache result on the `cachedPoiList` entry as `_dbBeats` so repeat clicks don't re-fetch.
  - Add AbortController: store a module-level `let beatFetchController = null`. Before each fetch, abort the previous one.
  - Render POI fields as static `<div class="readonly-field">` elements (not `<input>`): name, short_description, coordinates. Use `poi.properties.name`, `poi.properties.short_description`, `poi.properties.location.lat/lng`.
  - Render beat cards as read-only: each shows lens (translate slug to display label via `lensDisplayToSlug` reverse lookup), gravity (derived from `duration_sec / 60`), and `script_body`. All fields are `<div>` not `<input>`/`<textarea>`. All content passed through `escHtml()`.
  - Show "DB" badge on each beat card header.
  - If `_incomingBeats` exist (set by Task 5), render them below the DB beats with "Incoming" badge, as editable cards (same as current beat card rendering).
  - Hide "Mark as Complete" button for DB-only POIs (no incoming beats). Show "Update POI" button if `_incomingBeats` exist (Task 6).
  - Hide "Defer" button for DB POIs.
- When `activeSelection.source === 'incoming'`: existing behavior unchanged.

**What NOT to touch:** Existing beat card rendering for incoming POIs. Conflict resolution panels. `autoSaveCurrent()` logic (it already guards on `activeIdx` into `poiData`, which won't match DB POIs).

**Success check:** Clicking a DB POI shows a loading skeleton, then read-only POI fields and beat cards. Clicking the same POI again uses the cache (no network request). Clicking a different POI cancels the in-flight request.

---

### Task 4: Handle loading skeleton and beat fetch errors

**Files to touch:** `frontend/review.html` — within `selectPoi()` and `renderDetail()`

**What to do:**
- When a DB POI is selected and `_dbBeats` is not cached, show a skeleton in `detailBody`: a pulsing placeholder div (CSS animation, 3 grey rectangles simulating beat cards).
- Add CSS class `.beat-skeleton` with a pulse animation.
- On fetch error: show inline error in `detailBody`: "Failed to load beats — click to retry" with a retry button that re-triggers the fetch.
- On success: cache beats as `cachedPoiList[idx]._dbBeats = data.beats || []`, then call `renderDetail()`.

**What NOT to touch:** Error handling for incoming POI conflict detection (existing flow).

**Success check:** Slow network (throttle in DevTools) shows skeleton. Network error shows retry button. Retry works.

---

### Task 5: JSON load merges incoming beats into DB POIs

**Files to touch:** `frontend/review.html` — JSON load handler (~lines 1258–1308)

**What to do:**
- After `poiData = data` (or after duplicate resolution), add a merge step:
  1. For each entry in `poiData`, run `findProximityMatches(entry, cachedPoiList)` using existing proximity logic.
  2. If a match is found (distance ≤ threshold AND name similarity ≥ 50%):
     - Attach the incoming POI's beats to the matched `cachedPoiList` entry: `matchedDbPoi._incomingBeats = entry.beats`.
     - Store a back-reference: `matchedDbPoi._incomingPoiData = entry` (for coordinate/metadata access during upload).
     - Remove the entry from `poiData` (it's now represented by the DB POI with incoming beats).
  3. If no match: leave in `poiData` as-is (becomes "New POI" with existing badge logic).
- After merge, re-render worklist (DB POIs with `_incomingBeats` will show the "+Incoming" badge from Task 2).
- If the currently selected DB POI gains incoming beats, auto-refresh the detail panel (Q1 resolution).

**What NOT to touch:** The duplicate resolution flow (`showDuplicateResolver`). The `poiData = data` assignment for unmatched entries. `addIncomingMarkers()` — it operates on `poiData` which now only contains unmatched (new) POIs.

**Success check:** Loading a JSON file with POIs that match DB entries: matched POIs disappear from `poiData` and their beats appear on the matched DB POI entries. Unmatched POIs remain as "New POI" in the worklist. DB POIs with incoming beats show the "+Incoming" badge.

---

### Task 6: Sort control — auto-sort on JSON load

**Files to touch:** `frontend/review.html` — `renderWorklist()`, add sort toggle UI

**What to do:**
- Add a module-level `let dbSortMode = 'default'` (`'default'` = incoming-first, `'alpha'` = alphabetical).
- On JSON load, set `dbSortMode = 'default'` and re-render.
- In `renderWorklist()`, when rendering the DB POI section:
  - If `dbSortMode === 'default'`: sort DB POIs so those with `_incomingBeats` appear first, then alphabetical.
  - If `dbSortMode === 'alpha'`: sort all DB POIs alphabetically by `properties.name`.
- Add a small toggle button at the top of the DB POI section: "Sort: Incoming first | A-Z". Clicking toggles `dbSortMode` and re-renders.

**What NOT to touch:** The sort logic for `poiData` (existing `getDisplayPriority` function). The incoming POI section sort order.

**Success check:** After JSON load, DB POIs with incoming beats appear at the top of the DB section. Toggle switches to alphabetical and back.

---

### Task 7: "Update POI" action for matched DB POIs

**Files to touch:** `frontend/review.html` — `renderDetail()`, `markCompleteBtn` click handler (~line 1645), `uploadSinglePoi()` (~line 2832)

**What to do:**
- When rendering a DB POI with `_incomingBeats`:
  - Show "Update POI" button (reuse `markCompleteBtn` element, change text to "Update POI").
  - Enable the button only when incoming beats pass validation (`canMarkComplete`-equivalent check on `_incomingBeats`).
- On "Update POI" click for a DB POI:
  1. Build a synthetic POI object for upload: use the DB POI's name (`properties.name`) and coordinates (`properties.location`), but with `beats` set to `_incomingBeats` only.
  2. Run `detectConflictsForPoi()` if not already cached on the DB POI (proximity resolution will auto-resolve as "same place" since it matches itself).
  3. Run `runBeatConflictDetection()` for incoming beats against the existing DB POI name to get beat-level conflicts.
  4. If conflicts exist, show the existing conflict resolution overlay for the incoming beats.
  5. After resolution, call a modified upload path that:
     - Does NOT create/merge a new POI node (the POI already exists in DB).
     - Only uploads the incoming beats, linking them to the existing POI node via `HAS_BEAT` edges.
  6. On success: clear `_incomingBeats` from the `cachedPoiList` entry, mark the DB POI row as "Updated" (temporary visual badge), refresh the detail panel.

**What NOT to touch:** The existing `uploadSinglePoi()` for incoming/new POIs in `poiData`. Create a new function `uploadIncomingBeatsForDbPoi(dbPoiIdx)` instead of modifying the existing one.

**Success check:** Clicking "Update POI" on a matched DB POI triggers conflict detection for incoming beats, shows resolution UI if needed, uploads only the incoming beats, and marks the POI as updated.

---

### Task 8: Map marker visual indicator for matched DB POIs

**Files to touch:** `frontend/review.html` — `addIncomingMarkers()` (~line 3484), persistent map marker rendering (~line 3420)

**What to do:**
- After the JSON merge step (Task 5), update the persistent map: for each DB POI that gained `_incomingBeats`, change its marker style from grey (`#888`) to orange-outlined (`fillColor: '#888', color: '#e67e22', weight: 2`).
- Create a helper `updateDbMarkerStyles()` that iterates `cachedPoiList`, finds markers in `persistentMarkers`, and updates style based on whether `_incomingBeats` exists.
- Call `updateDbMarkerStyles()` after the merge step and after a successful "Update POI" action (revert to grey).

**What NOT to touch:** `addIncomingMarkers()` logic for `poiData` entries. DB marker popup content.

**Success check:** After JSON load, DB POIs with incoming beats have an orange outline on the map. After uploading, they revert to grey.

---

### Task 9: XSS protection for DB-sourced content

**Files to touch:** `frontend/review.html` — within the DB beat card rendering (Task 3)

**What to do:**
- Ensure every DB beat field rendered in the detail panel passes through `escHtml()`: `script_body`, `lens_slug`, `physical_cue`, and any other text fields.
- This is built into Task 3's implementation but listed separately as a best-practices verification task.
- Audit: search all `innerHTML` assignments in the new DB rendering code and confirm no raw DB values are interpolated without `escHtml()`.

**What NOT to touch:** Existing `escHtml()` usage for incoming POI rendering.

**Success check:** Manually test with a DB beat containing `<script>alert(1)</script>` in `script_body` — it renders as escaped text, not executed.

---

## Part B — Test Definitions

### T1: DB POIs load into worklist on city select (AC1)

**Test type:** Manual verification
**Steps:** Select "Boston" from city dropdown. Observe worklist.
**Expected:** All geofence-filtered DB POIs appear with "DB" badge. Beat count shows "--". No API calls to `/graph/poi/{name}/beats` until a POI is clicked.

### T2: Clicking DB POI fetches and displays beats (AC2, AC3)

**Test type:** Manual verification
**Steps:** Click a DB POI in the worklist. Observe detail panel.
**Expected:** Loading skeleton appears immediately. After fetch completes, POI fields render as static text (not editable inputs). Beat cards show lens, gravity, script body — all read-only. "DB" badge on each beat card.

### T3: Beat fetch caching (Performance — from red team)

**Test type:** Manual verification (DevTools Network tab)
**Steps:** Click DB POI A. Wait for beats to load. Click DB POI B. Click DB POI A again.
**Expected:** Second click on POI A shows beats instantly — no network request in DevTools.

### T4: AbortController cancels stale requests (Performance — from red team)

**Test type:** Manual verification (DevTools Network tab, throttle to Slow 3G)
**Steps:** Click DB POI A. Before beats load, click DB POI B.
**Expected:** POI A's request shows as "cancelled" in DevTools. POI B's beats render correctly. No stale data from POI A appears.

### T5: JSON load merges into DB POIs (AC4)

**Test type:** Manual verification
**Steps:** Select Boston. Load a JSON file containing a POI that matches an existing DB POI (same name or within proximity threshold).
**Expected:** The matched POI does NOT appear as a separate entry in the worklist. The matched DB POI shows a "+Incoming" badge. Clicking it shows DB beats (read-only) above incoming beats (editable).

### T6: Unmatched incoming POIs appear as "New POI" (AC5)

**Test type:** Manual verification
**Steps:** Load a JSON file containing a POI that doesn't match any DB POI.
**Expected:** The unmatched POI appears in the incoming section with existing badge logic (Pending/Flagged). All fields editable. Existing behavior preserved.

### T7: Detail panel shows both DB and incoming beats (AC6)

**Test type:** Manual verification
**Steps:** Click a matched DB POI (one with "+Incoming" badge).
**Expected:** Detail panel shows read-only DB beats (labeled "DB") visually separated above editable incoming beats (labeled "Incoming").

### T8: Auto-sort on JSON load (AC7)

**Test type:** Manual verification
**Steps:** Load a JSON file. Observe DB POI section order.
**Expected:** DB POIs with incoming beats appear before DB-only POIs. Toggle button switches to A-Z sort. Toggle again reverts.

### T9: "Update POI" uploads only incoming beats (AC8, Data Integrity — from red team)

**Test type:** Manual verification (DevTools Network tab)
**Steps:** Click a matched DB POI. Click "Update POI".
**Expected:** Conflict detection runs for incoming beats only. After resolution, only incoming beats are uploaded as new `NarrativeBeat` nodes. No duplicate POI node created. Network tab shows beat creation requests but NOT a new `POST /nodes/POI`.

### T10: DB POI with zero beats (EC1)

**Test type:** Manual verification
**Steps:** Click a DB POI that has no beats in the database.
**Expected:** Detail panel shows POI fields (read-only) and an empty beats section with "No beats yet" message.

### T11: Beat fetch failure with retry (EC3)

**Test type:** Manual verification (block the endpoint in DevTools)
**Steps:** Block `GET /graph/poi/*/beats` in DevTools. Click a DB POI.
**Expected:** Detail panel shows "Failed to load beats — click to retry". Unblock endpoint. Click retry. Beats load.

### T12: Large worklist rendering (EC4)

**Test type:** Manual verification
**Steps:** Ensure 200+ DB POIs are in the database. Select the city.
**Expected:** Worklist renders without visible jank. Scrolling is smooth.

### T13: XSS protection on DB content (Security — from red team)

**Test type:** Manual verification
**Steps:** Insert a beat with `<img src=x onerror=alert(1)>` in `script_body` via direct DB insertion. Click the POI.
**Expected:** The tag renders as escaped text. No alert fires.

---

## Part C — Claude Code Prompt

```
## Content Browser Workbench — Implementation Prompt

### Slice Goal
An editor can browse all existing DB POIs and their beats alongside incoming JSON content, so editorial decisions are made with full context of what's already in the system.

### Context
- Read `specs/NORTHSTAR.md` for architectural commitments
- Read `specs/2026-03-24-content-browser/02-spec.md` for the full behavior spec
- Read `specs/2026-03-24-content-browser/03-red-team.md` for resolved blockers and risks
- Primary file: `frontend/review.html` (monolithic HTML/JS workbench)

### Key Architectural Decisions (from red team)
1. **Two separate data sources:** `cachedPoiList` (DB POIs, read-only) and `poiData[]` (incoming JSON only). Do NOT mix them.
2. **Compound selection:** Replace `activeIdx` integer with `activeSelection = { source: 'db'|'incoming', idx: number }`.
3. **Lazy beat loading:** Fetch beats on click, cache as `_dbBeats` on `cachedPoiList` entry.
4. **JSON merge:** On JSON load, match incoming POIs against `cachedPoiList`. Matched → attach `_incomingBeats` to DB entry, remove from `poiData[]`. Unmatched → stays in `poiData[]`.
5. **Upload filtering:** "Update POI" for matched DB POIs uploads ONLY `_incomingBeats`, does NOT create a new POI node.

### Task Breakdown (execute in order)

**Task 1 — Compound selection model**
- Replace `let activeIdx = -1` (line 958) with `let activeSelection = { source: null, idx: -1 }`.
- Add `let activeIdx = -1` as a computed alias that `autoSaveCurrent()` and other `poiData`-specific code can continue using. When `activeSelection.source === 'incoming'`, set `activeIdx = activeSelection.idx`. When `source === 'db'`, set `activeIdx = -1` so `autoSaveCurrent()` is a no-op.
- Update `selectPoi()` to accept either a number (legacy) or `{ source, idx }`. Normalize at the top.
- Update `panPersistentMapTo()` to handle both data shapes.

**Task 2 — Render DB POIs in worklist**
- In `renderWorklist()`, after the existing uploaded section, add a "Database POIs" section.
- Iterate `cachedPoiList`. Each row: POI name (`properties.name`), "DB" badge (blue), beat count "--".
- If entry has `_incomingBeats`, add "+Incoming" badge (orange).
- Click handler: `selectPoi({ source: 'db', idx: i })`.
- CSS: `.badge-db { background: var(--blue-dim); color: var(--blue); }` `.badge-incoming { background: var(--orange-dim); color: var(--orange); }`

**Task 3 — Read-only detail panel for DB POIs**
- In `renderDetail()`, branch on `activeSelection.source`.
- When `'db'`: render POI fields as `<div class="readonly-field">` (not `<input>`). Render cached `_dbBeats` as read-only beat cards (lens display label, gravity from `duration_sec/60`, `script_body` — all via `escHtml()`). Show "DB" badge per beat. If `_incomingBeats` exist, render below as editable cards (reuse existing beat card HTML).
- Hide Mark Complete / Defer buttons for DB-only POIs. Show "Update POI" button if `_incomingBeats` exist.

**Task 4 — Loading skeleton and beat fetch errors**
- In `selectPoi()` when `source === 'db'`: if `_dbBeats` not cached, show skeleton, fetch `GET /graph/poi/{name}/beats`, cache result. Use AbortController (`let beatFetchController = null` at module level) to cancel prior in-flight requests.
- On error: show "Failed to load beats — click to retry" with retry handler.
- CSS: `.beat-skeleton` with pulse animation.

**Task 5 — JSON merge into DB POIs**
- After `poiData = data` (line 1305) and after duplicate resolution resolves to `poiData = ...`, add merge step:
  - For each `poiData` entry, run `findProximityMatches(entry, cachedPoiList)`.
  - Filter matches to those with name similarity ≥ 50%: `nameSimilarity(entry.poi_name, match.existingPoi.properties.name) >= 0.5`.
  - If match found: attach `entry.beats` as `matchedPoi._incomingBeats`, store `matchedPoi._incomingPoiData = entry`, splice entry out of `poiData`.
  - Iterate in reverse to safely splice.
- After merge: call `renderWorklist()` and `addIncomingMarkers()` (only unmatched remain in `poiData`).
- If currently viewing a DB POI that gained incoming beats, re-render detail.

**Task 6 — Sort control**
- Add `let dbSortMode = 'default'`.
- In the DB POI section of `renderWorklist()`: sort by `_incomingBeats` presence first (default) or alphabetical (alpha).
- Add toggle button: "Incoming first | A-Z".
- On JSON load: set `dbSortMode = 'default'`.

**Task 7 — "Update POI" action**
- Create `async function uploadIncomingBeatsForDbPoi(dbIdx)`:
  - Get DB POI from `cachedPoiList[dbIdx]`. Get its `_incomingBeats`.
  - The POI already exists — find its node ID from the `cachedPoiList` entry (`.id`).
  - Run `runBeatConflictDetection()` with a synthetic POI object (`{ beats: _incomingBeats, poi_name: properties.name, latitude: properties.location.lat, longitude: properties.location.lng }`).
  - If conflicts exist, render conflict panels in the detail view and wait for resolution.
  - For each incoming beat (skipping those with `_conflictResolution.action === 'skip'`): call `mapBeatForApi()`, create via `POST /nodes/NarrativeBeat`, link via `POST /edges/HAS_BEAT`.
  - Handle replace/merge/change-lens resolutions same as `uploadSinglePoi`.
  - On success: clear `_incomingBeats` and `_incomingPoiData`, clear `_dbBeats` cache (force re-fetch to show new beats), show success toast, re-render.
- Wire "Update POI" button click to this function.

**Task 8 — Map marker indicator**
- Create `function updateDbMarkerStyles()`: iterate `cachedPoiList`, for each with `_incomingBeats`, update its marker style to orange-outlined. Without: grey.
- Call after JSON merge (Task 5) and after successful "Update POI" (Task 7).

**Task 9 — XSS audit**
- Search all `innerHTML` assignments in new code. Confirm every DB-sourced string passes through `escHtml()`.
- Specifically: `script_body`, `properties.name`, `properties.short_description`, `lens_slug`, `physical_cue`.

### What NOT to touch
- `poiData[]` array shape or `_status` enum values
- `updateProgress()`, `checkAllComplete()`, `canMarkComplete()` — these operate on `poiData` only
- Existing conflict resolution UI/logic for incoming POIs
- Backend API or Neo4j schema
- The persistent map initialization or geofence logic
- Batch upload flow

### Best Practices Checklist (mandatory)
1. [ ] All DB beat fields pass through `escHtml()` before innerHTML insertion
2. [ ] AbortController cancels prior beat fetch on new POI selection
3. [ ] Fetched DB beats are cached on `cachedPoiList` entry (`_dbBeats`)
4. [ ] "Update POI" uploads only `_incomingBeats`, never existing DB beats
5. [ ] DB POI fields render as `<div>` not `<input>` — no accidental edits
6. [ ] No new secrets, API keys, or auth tokens in client code
7. [ ] Large worklist (200+ items) renders without blocking main thread (use DocumentFragment for batch DOM insertion)

### Verification
After all tasks, verify each acceptance criterion from the spec:
- AC1: City select → DB POIs in worklist with "DB" badge, beat count "--"
- AC2: Click DB POI → fetches beats, displays read-only cards
- AC3: Loading indicator while fetching, disappears on render
- AC4: JSON load merges into DB POIs (not replace)
- AC5: Unmatched POIs appear as "New POI" (current behavior)
- AC6: Matched POI detail shows DB beats above incoming beats
- AC7: Auto-sort on JSON load, toggle to A-Z
- AC8: "Update POI" triggers upload of incoming beats only

Before starting, confirm you understand the full scope and flag any conflicts with the existing codebase or assumptions you are making.
```

---

## Part D — Best Practices Implementation Checklist

| # | Practice | Task(s) | How to Verify |
|---|----------|---------|---------------|
| 1 | XSS: All DB-sourced content escaped via `escHtml()` | 3, 9 | Grep all `innerHTML` in new code; confirm no raw DB values. Manual test with `<script>` in `script_body`. |
| 2 | Performance: AbortController for beat fetches | 4 | Throttle network in DevTools, click two POIs rapidly — first request shows "cancelled". |
| 3 | Performance: Cache fetched DB beats (`_dbBeats`) | 3, 4 | Click POI A → B → A. Network tab shows only one request for A. |
| 4 | Performance: DocumentFragment for large worklist | 2 | 200+ POIs render without jank (Chrome Performance profiler shows no long tasks >50ms). |
| 5 | Data integrity: Upload only `_incomingBeats` | 7 | Network tab during "Update POI" shows NarrativeBeat creates but no `POST /nodes/POI`. |
| 6 | Data integrity: Read-only DB POI fields | 3 | DB POI detail has no `<input>` or `<textarea>` for POI fields or DB beat fields. |
| 7 | Auth gap documented | — | No action needed now. Already documented in red team as known Phase 1 gap. |
