# Implementation Plan — Persistent Map & Manual POI Merge

**Spec:** `specs/2026-03-19-persistent-map-merge/02-spec.md`
**Red Team:** `specs/2026-03-19-persistent-map-merge/03-red-team.md`
**Date:** 2026-03-19
**Status:** Approved

---

## Part A — Task Breakdown

### Task 1: Restructure Layout — Top Map + Bottom Worklist/Detail

**Files to touch:** `frontend/review.html` (CSS + DOM structure)

**What to do:**
1. Add a new `<div id="persistent-map-container">` above the existing worklist/detail area. Give it ~40% viewport height, full width, with a resize handle or fixed split.
2. Create a `<div id="persistent-map">` inside the container for the Leaflet instance.
3. Move the existing worklist (`#worklist`) and right panel (`#rightPanel`) into a `<div id="bottom-panel">` below the map, keeping their existing left-right flex layout.
4. Update CSS: the overall layout becomes `flex-direction: column`. The top is the persistent map, the bottom is the existing two-panel layout.
5. Ensure `map.invalidateSize()` fires on window resize so the Leaflet map redraws correctly.

**What NOT to touch:** The existing per-POI detail map (`initMap()` with `id="map"`) stays untouched — it continues to work inside the detail panel for coordinate editing.

**Success check:** Page loads with map on top, worklist + detail on bottom. Existing worklist navigation and detail panel still work. No visual regressions in the bottom panel.

---

### Task 2: Initialize Persistent Map with Database POI Markers

**Files to touch:** `frontend/review.html` (new function + call in `fetchLensesAndPoiList`)

**What to do:**
1. After `fetchLensesAndPoiList()` completes, call a new function `initPersistentMap()`.
2. `initPersistentMap()` creates a Leaflet map in `#persistent-map` with the same OpenStreetMap tile layer and geofence circle as `initMap()`.
3. Create a `L.layerGroup()` named `dbMarkerLayer` for database POI markers.
4. Iterate `cachedPoiList` and add an `L.circleMarker` (grey, radius 6, fillOpacity 0.6) for each POI with valid coordinates. Bind a popup showing: POI name, lat/lng (4 decimal places), beat count (store as marker property — fetch later or use "N/A" initially).
5. Store a `Map<poiId, marker>` lookup (`persistentMarkers`) for later reference.
6. Fit the map bounds to show all markers, or default to `cityCentre` if no POIs exist.

**What NOT to touch:** `initMap()` — leave it as-is for the detail panel.

**Success check:** On page load (after city selection), the persistent map shows all database POIs as grey circles. Clicking a grey marker shows a popup with name and coordinates.

---

### Task 3: Add Incoming POI Markers on JSON Load

**Files to touch:** `frontend/review.html` (modify JSON load handler + `initPersistentMap`)

**What to do:**
1. Create a second `L.layerGroup()` named `incomingMarkerLayer` in the persistent map.
2. After the JSON file is parsed and `poiData[]` is populated, iterate all incoming POIs and add `L.circleMarker` (amber/orange, `#e67e22`, radius 7, fillOpacity 0.7) to `incomingMarkerLayer`.
3. Store an `incomingMarkers` Map keyed by `activeIdx` for cross-reference.
4. Both layers are added to the map simultaneously so grey (database) and amber (incoming) markers are visible together.

**What NOT to touch:** The existing JSON parsing logic, `poiData` structure, or validation.

**Success check:** After loading a JSON file, amber markers appear on the persistent map alongside grey database markers. Both are visually distinct at all zoom levels.

---

### Task 4: Map → Worklist Selection (Incoming POIs)

**Files to touch:** `frontend/review.html` (marker click handlers)

**What to do:**
1. On each incoming POI marker, add a click handler that calls `selectPoi(idx)` — the existing function that selects a POI in the worklist and loads its detail.
2. Visually highlight the selected marker (increase radius or add a colored ring) and reset the previous selection.

**What NOT to touch:** `selectPoi()` internals — just call it.

**Success check:** Clicking an amber marker on the map selects the corresponding POI in the worklist and loads its detail panel.

---

### Task 5: Worklist → Map Pan/Zoom

**Files to touch:** `frontend/review.html` (modify `selectPoi()`)

**What to do:**
1. At the end of `selectPoi()`, after the existing logic, pan the persistent map to center on the selected POI's coordinates using `persistentMap.setView([lat, lng], 16)` (zoom 16 for street-level).
2. Briefly highlight the target marker — pulse effect using a temporary larger circle that fades, or a simple size bump (radius 6→10) that resets after 1 second via `setTimeout`.
3. Handle the case where the POI has no valid coordinates (skip the pan).

**What NOT to touch:** The rest of `selectPoi()` — append to it, don't restructure it.

**Success check:** Clicking a worklist entry pans the persistent map to that POI and briefly highlights its marker.

---

### Task 6: Database POI Popup with Beat Count

**Files to touch:** `frontend/review.html` (marker popup content)

**What to do:**
1. When creating database POI markers (Task 2), set popup content to show name + coordinates initially.
2. Add a lazy-load for beat count: on popup open, fetch `GET /graph/poi/{name}/beats` and update the popup content with the beat count. Cache the result on the marker so subsequent opens don't re-fetch.
3. Add a "Merge into this POI..." button in the popup (rendered but wired in Task 9).

**What NOT to touch:** The `/graph/poi/{name}/beats` endpoint — use it as-is.

**Success check:** Clicking a grey database marker shows a popup with name, coordinates, and beat count (fetched on first open).

---

### Task 7: Manual Match During Upload — Searchable Dropdown

**Files to touch:** `frontend/review.html` (detail panel, new UI element)

**What to do:**
1. In the detail panel (rendered by `renderDetail()`), add a "Match to existing POI..." button below the proximity match panel.
2. Clicking it opens a searchable dropdown populated from `cachedPoiList`, sorted by distance from the incoming POI's coordinates (nearest first). Each entry shows: POI name + distance in meters.
3. Typing in the search input filters the list by name (case-insensitive substring match).
4. Selecting a database POI from the dropdown sets `poi._conflicts.proximityResolution = 'same'` and `poi._conflicts.matchedExistingPoi = selectedDbPoi`, then triggers `runBeatConflictDetection(poi, selectedDbPoi.properties.name)` to detect beat-level conflicts.
5. If the POI already had an automatic proximity match, the manual selection overrides it (EC2).
6. Show the matched POI name + distance as a confirmation badge. Allow clearing the manual match to revert to automatic.

**What NOT to touch:** The automatic proximity matching logic — manual match supplements it, doesn't replace the algorithm.

**Success check:** Editor can search for and select any database POI to match an incoming POI to. The upload flow then creates beats on the matched POI instead of a new one.

---

### Task 8: Database POI Merge — Target Selection

**Files to touch:** `frontend/review.html` (persistent map interaction)

**What to do:**
1. In the database POI popup (from Task 6), wire the "Merge into this POI..." button.
2. Clicking it enters "merge mode":
   - Store the target POI reference.
   - Change the cursor to crosshair.
   - Show a banner/toast: "Click the source POI to merge into [target name]".
   - Disable incoming marker clicks temporarily.
3. Clicking a second database POI marker sets it as the source.
4. If the editor clicks the same POI (EC1), show a toast "Cannot merge a POI into itself" and ignore.
5. Clicking anywhere else (not a DB marker) or pressing Escape cancels merge mode.
6. Console-log: `"Merge mode: target=[targetName], source=[sourceName]"`.

**What NOT to touch:** Incoming POI markers — merge mode only works between database POIs.

**Success check:** Editor can click "Merge into this POI..." on a database marker, then click a second database marker to select source and target. Self-merge is prevented.

---

### Task 9: Merge Preview & Beat Transfer

**Files to touch:** `frontend/review.html` (new merge execution logic)

**What to do:**
1. After source + target are selected (Task 8), fetch beats for both POIs via `GET /graph/poi/{name}/beats`.
2. Show a merge preview panel (modal or inline) listing:
   - Target POI: name, beat count, list of lens slugs
   - Source POI: name, beat count, list of lens slugs
   - Collisions: source beats whose lens matches a target beat (same-lens = conflict)
3. If source has zero beats (EC4), show confirmation: "Source POI has no beats. Merge will delete [source name]. Continue?"
4. For beats with no collision: show as "Will transfer" with a checkmark.
5. For same-lens collisions: reuse the existing conflict resolution UI (`showConflictOverlay` pattern — replace/skip/merge/change-lens). Present as a list of conflict items with the same action buttons.
6. "Confirm Merge" button is disabled until all collisions are resolved.

**What NOT to touch:** Don't modify `showConflictOverlay()` itself — create a parallel function `showMergeConflictOverlay()` that reuses the same UI patterns.

**Success check:** After selecting source and target, a preview shows all beats and highlights collisions. Each collision has resolution options.

---

### Task 10: Execute Merge — Beat Transfer + Source Deletion

**Files to touch:** `frontend/review.html` (new merge execution function)

**What to do:**
Implement `executeMerge(targetPoi, sourcePoi, resolutions)`:

1. Console-log: `"Merge start: [sourceName] → [targetName]"`
2. Get max `sort_order` from target POI's beats (R4 mitigation). Default to 0 if none.
3. For each source beat (in order):
   a. If resolution is `skip` → console-log skip, continue.
   b. If resolution is `replace` → deprecate target's conflicting beat via `PUT /nodes/NarrativeBeat/{id}` (set `active_status: 'deprecated'`). Console-log: `"Deprecated beat [id] on target"`.
   c. If resolution is `merge` → use merged beat content (from conflict UI selections).
   d. If resolution is `change-lens` → update the beat's `TAGGED_WITH` edge to the new lens.
   e. Create `HAS_BEAT` edge: `POST /edges/HAS_BEAT` from target POI → beat node. Set `sort_order` to max + 1 (incrementing). Console-log: `"Transferred beat [id] to target"`.
   f. Delete old `HAS_BEAT` edge from source POI → beat node: `DELETE /edges/HAS_BEAT/{edge_id}`. (Need to fetch edge ID first via a query, or use the delete-by-endpoints pattern if the API supports it.)
4. After all beats processed: `DELETE /nodes/POI/{source_id}`. Console-log: `"Deleted source POI [sourceName]"`.
5. If any step fails: stop, show error toast with the step that failed. Console-log full error. Both POIs still exist so the editor can retry.

**What NOT to touch:** The backend CRUD endpoints — use them as-is.

**Success check:** After confirming merge, beats transfer from source to target. Source POI is deleted. Console shows step-by-step log. Errors stop execution and show which step failed.

---

### Task 11: Post-Merge Map + Cache Update

**Files to touch:** `frontend/review.html` (persistent map + cachedPoiList)

**What to do:**
1. After successful merge:
   - Remove the source POI's marker from `dbMarkerLayer` and `persistentMarkers`.
   - Update the target POI's popup to reflect new beat count.
   - Remove the source POI from `cachedPoiList`.
   - Show a success toast: "Merged [sourceName] into [targetName]".
2. No full page reload needed (AC7).

**What NOT to touch:** `incomingMarkerLayer` — merge only affects database markers.

**Success check:** After merge, the source marker disappears from the map. The target marker's popup shows updated beat count. `cachedPoiList` is updated. Success toast appears.

---

### Task 12: Edge Case Handling & Performance Verification

**Files to touch:** `frontend/review.html` (guards and edge cases)

**What to do:**
1. **EC1 — Self-merge:** Already handled in Task 8 (same-POI click ignored + toast).
2. **EC2 — Manual match overrides automatic:** Already handled in Task 7 (manual sets `matchedExistingPoi` directly).
3. **EC3 — All target lenses occupied:** The conflict resolution UI in Task 9 handles this — every collision triggers resolution, no silent drops.
4. **EC4 — Source has zero beats:** Already handled in Task 9 (confirmation prompt).
5. **EC5 — Browser resize:** Add `window.addEventListener('resize', () => persistentMap.invalidateSize())` and also fire on any layout changes.
6. **AC8 — Performance test:** Manually verify with 200+ markers. `L.circleMarker` (SVG) should handle this without clustering. If jank occurs, add `preferCanvas: true` to the Leaflet map options (canvas renderer is faster than SVG for many markers).

**What NOT to touch:** The existing edge case handling for the upload flow.

**Success check:** All 5 edge cases handled. 200+ markers render smoothly.

---

## Part B — Test Definitions

### T1: Persistent Map Visibility (AC1)
- **Type:** Manual verification
- **Steps:** Open workbench → select city → verify map is visible in upper panel. Load JSON → verify map remains visible. Navigate POIs → verify map remains visible.
- **Expected:** Map is always visible, never hidden or replaced.

### T2: Dual Marker Rendering (AC2)
- **Type:** Manual verification
- **Steps:** Open workbench with database POIs loaded → verify grey circle markers. Load JSON → verify amber markers appear alongside grey ones.
- **Expected:** Grey = database, amber = incoming. Both visible simultaneously. Distinguishable at zoom levels 10–18.

### T3: Database Marker Popup (AC3a)
- **Type:** Manual verification
- **Steps:** Click a grey marker → verify popup shows POI name, coordinates, beat count.
- **Expected:** Popup displays correct data. Beat count loads on first open.

### T4: Incoming Marker → Worklist Selection (AC3b)
- **Type:** Manual verification
- **Steps:** Load JSON → click an amber marker on the map.
- **Expected:** Corresponding POI is selected in worklist, detail panel loads.

### T5: Worklist → Map Pan (AC4)
- **Type:** Manual verification
- **Steps:** Load JSON → click a worklist entry.
- **Expected:** Map pans to center on that POI's marker. Marker briefly highlights.

### T6: Manual Match Override (AC5)
- **Type:** Manual verification
- **Steps:** Load JSON → select an incoming POI → click "Match to existing POI..." → search for a database POI → select it → verify the match is set → proceed to upload → verify beats are created on the matched database POI (not a new POI).
- **Expected:** Upload creates beats on the manually selected database POI. No new POI is created.

### T7: Database POI Merge — Full Flow (AC6)
- **Type:** Manual verification (integration)
- **Steps:**
  1. Ensure two database POIs exist (one with beats, one with beats including at least one same-lens collision).
  2. Click target POI marker → "Merge into this POI..." → click source POI marker.
  3. Merge preview shows beats from both sides, highlights collisions.
  4. Resolve collisions (test each action: replace, skip, merge, change-lens).
  5. Confirm merge.
  6. Verify: source POI's beats appear on target, source POI is deleted, conflict resolutions applied correctly.
- **Expected:** All beats transfer (or resolve). Source POI deleted. Target POI has all non-skipped beats.

### T8: Immediate Map Update (AC7)
- **Type:** Manual verification
- **Steps:** Complete a merge → check the map without reloading the page.
- **Expected:** Source marker gone, target marker updated.

### T9: Performance — 200+ Markers (AC8)
- **Type:** Manual verification
- **Steps:** Load a database with 200+ POIs → open workbench → interact with map (pan, zoom, click markers).
- **Expected:** No visible jank. Markers render within 1 second. Pan/zoom is smooth.

### T10: Self-Merge Prevention (EC1)
- **Type:** Manual verification
- **Steps:** Click "Merge into this POI..." → click the same POI.
- **Expected:** Toast message, merge does not proceed.

### T11: Zero-Beat Source Merge (EC4)
- **Type:** Manual verification
- **Steps:** Create a database POI with no beats → merge it into another POI.
- **Expected:** Confirmation prompt noting no beats to transfer. Source deleted after confirmation.

### T12: Browser Resize (EC5)
- **Type:** Manual verification
- **Steps:** Resize the browser window during map interaction.
- **Expected:** Map and lower panel resize. No rendering artifacts.

---

## Part C — Claude Code Prompt

```
## Slice Goal

Add a persistent map to the Editorial Workbench that shows all database and incoming
POIs, supports interactive selection between map and worklist, and enables manual
POI matching and database POI merging.

## Context

Read these files before starting:
- `specs/NORTHSTAR.md` — project north star
- `specs/2026-03-19-persistent-map-merge/02-spec.md` — approved behavior spec
- `specs/2026-03-19-persistent-map-merge/03-red-team.md` — red team review with resolutions
- `specs/2026-03-19-persistent-map-merge/04-plan.md` — this implementation plan
- `frontend/review.html` — the workbench (single-file app, ~3228 lines)

## What to Build

All work is in `frontend/review.html`. No backend changes needed.

### Task 1: Restructure Layout
- Add `<div id="persistent-map-container">` (40vh) above the existing worklist/detail.
- Inside it, `<div id="persistent-map">` for a new Leaflet instance.
- Wrap existing worklist + detail in `<div id="bottom-panel">` below the map.
- Overall layout: flex column. Top = map, bottom = existing two-panel layout.
- Add `window.addEventListener('resize', () => persistentMap.invalidateSize())`.
- The existing per-POI detail map (`initMap()` with `id="map"`) stays untouched.

### Task 2: Initialize Persistent Map with Database Markers
- After `fetchLensesAndPoiList()` completes, call `initPersistentMap()`.
- Create Leaflet map in `#persistent-map` with OpenStreetMap tiles and geofence circle.
- Add `L.layerGroup` named `dbMarkerLayer`.
- For each POI in `cachedPoiList` with valid coords: add `L.circleMarker` (grey `#888`,
  radius 6, fillOpacity 0.6).
- Store `persistentMarkers = new Map()` keyed by POI id.
- Bind popup on each marker: POI name, lat/lng. Beat count lazy-loaded on popup open
  via `GET /graph/poi/{name}/beats`.
- Add "Merge into this POI..." button in popup (wired in Task 8).
- Fit bounds to show all markers, or default to `cityCentre`.

### Task 3: Add Incoming POI Markers on JSON Load
- Create `L.layerGroup` named `incomingMarkerLayer`.
- After JSON parse + `poiData[]` populated: add `L.circleMarker` for each incoming POI
  (amber `#e67e22`, radius 7, fillOpacity 0.7) to `incomingMarkerLayer`.
- Store `incomingMarkers = new Map()` keyed by `activeIdx`.

### Task 4: Map → Worklist Selection
- Click handler on each incoming marker: call `selectPoi(idx)`.
- Highlight selected marker (radius bump to 10), reset previous.

### Task 5: Worklist → Map Pan/Zoom
- At end of `selectPoi()`: `persistentMap.setView([lat, lng], 16)`.
- Briefly highlight the marker (radius 6→10 for 1s via setTimeout).
- Skip if POI has no valid coordinates.

### Task 6: Database POI Popup Beat Count
- On popup open event, fetch `/graph/poi/{name}/beats`, update popup with beat count.
- Cache result on the marker object to avoid re-fetching.

### Task 7: Manual Match — Searchable Dropdown
- Add "Match to existing POI..." button in the detail panel below the proximity match area.
- Opens a searchable dropdown populated from `cachedPoiList`, sorted by distance from
  incoming POI (nearest first). Shows name + distance in meters.
- Text input filters by name (case-insensitive substring).
- Selecting sets `poi._conflicts.proximityResolution = 'same'` and
  `poi._conflicts.matchedExistingPoi = selectedPoi`.
- Triggers `runBeatConflictDetection(poi, selectedPoi.properties.name)`.
- Manual match overrides automatic proximity match.
- Show confirmation badge with matched name + distance. Allow clearing.

### Task 8: Merge Mode — Target + Source Selection
- "Merge into this POI..." button in popup enters merge mode.
- Store target POI. Cursor → crosshair. Banner: "Click source POI to merge into [target]".
- Clicking second DB marker → set as source.
- Self-merge prevented (toast + ignore). Escape or non-marker click → cancel merge mode.
- Console-log: `"Merge mode: target=[name], source=[name]"`.

### Task 9: Merge Preview & Conflict Resolution
- Fetch beats for both POIs via `/graph/poi/{name}/beats`.
- Show merge preview modal:
  - Target: name, beat count, lens list.
  - Source: name, beat count, lens list.
  - Non-colliding beats: "Will transfer" checkmark.
  - Same-lens collisions: conflict resolution buttons (replace/skip/merge/change-lens)
    using the same UI pattern as `showConflictOverlay()`.
- Zero beats on source (EC4): confirmation prompt.
- "Confirm Merge" disabled until all collisions resolved.

### Task 10: Execute Merge
Implement `executeMerge(targetPoi, sourcePoi, resolutions)`:
1. Console-log: `"Merge start: [source] → [target]"`
2. Get max `sort_order` from target's beats. Default 0.
3. For each source beat:
   - `skip`: log and continue.
   - `replace`: deprecate target's beat (`PUT /nodes/NarrativeBeat/{id}` → `active_status: 'deprecated'`).
   - `merge`: use merged content.
   - `change-lens`: update `TAGGED_WITH` edge.
   - Create `HAS_BEAT` edge: `POST /edges/HAS_BEAT` from target POI → beat. `sort_order` = max+1.
   - Delete old `HAS_BEAT` edge from source.
   - Console-log each step.
4. Delete source POI: `DELETE /nodes/POI/{source_id}`.
5. On any failure: stop, show error toast, log error. Both POIs still exist.

IMPORTANT — Merge direction: Source (new/duplicate) → Target (original/established).
The target is NEVER deleted. `TAGGED_WITH` edges stay on beat nodes — only
`HAS_BEAT` edges are re-pointed.

### Task 11: Post-Merge Map + Cache Update
- Remove source marker from `dbMarkerLayer` + `persistentMarkers`.
- Update target popup beat count.
- Remove source from `cachedPoiList`.
- Success toast: "Merged [source] into [target]".

### Task 12: Edge Cases & Performance
- EC1: Self-merge → toast, ignore (Task 8).
- EC2: Manual match overrides auto (Task 7).
- EC3: All lenses occupied → all trigger conflict resolution.
- EC4: Zero beats → confirmation prompt (Task 9).
- EC5: Resize → `map.invalidateSize()` on resize event.
- AC8: If 200+ markers are janky, add `preferCanvas: true` to Leaflet map options.

## What NOT to Touch
- `initMap()` — the per-POI detail map stays as-is.
- The automatic proximity matching algorithm (50m + name similarity).
- The JSON parsing and `poiData` structure.
- Backend API endpoints — no backend changes.
- `showConflictOverlay()` — create a parallel function for merge conflicts.

## Best Practices Checklist
- [ ] `HAS_BEAT` edge uses MERGE (idempotent) — verify POST calls go through existing endpoint.
- [ ] Beat transfer happens BEFORE source POI deletion — never reverse order.
- [ ] `TAGGED_WITH` edges are never deleted or moved during merge (they stay on beats).
- [ ] Console-log every merge step for debugging partial failures.
- [ ] `sort_order` on transferred beats appends after target's max (no collision).
- [ ] `cachedPoiList` updated after merge and after successful upload (existing pattern).
- [ ] No auth changes needed — accepted deviation for Phase 1 internal tool.
- [ ] No new secrets, API keys, or external dependencies introduced.
- [ ] Confirmation dialog shown before executing destructive merge.
- [ ] Error during merge stops execution and shows which step failed.

## Verification Steps
After implementation, verify:
1. Map visible at all times (before JSON, during review, during upload).
2. Grey markers = DB POIs, amber = incoming. Both visible simultaneously.
3. Click DB marker → popup with name, coords, beat count.
4. Click incoming marker → selects in worklist, loads detail.
5. Click worklist entry → map pans to marker with highlight.
6. Manual match overrides automatic, upload creates beats on matched POI.
7. Merge two DB POIs: beats transfer, source deleted, conflicts resolved.
8. Map updates immediately after merge (no reload).
9. 200+ markers render without jank.
10. Self-merge prevented. Zero-beat merge prompts. Resize works.

Before starting, confirm you understand the full scope and flag any conflicts
with the existing codebase or assumptions you are making.
```

---

## Part D — Best Practices Implementation Checklist

| # | Practice | Task(s) | How to Verify |
|---|----------|---------|---------------|
| 1 | Beat transfer before source deletion | T10 | Read `executeMerge()` — delete is final step. Console logs show sequence. |
| 2 | Merge direction enforced (source→target) | T8, T9, T10 | UI labels target as "Merge into this POI" (target survives). Code never deletes target. |
| 3 | `TAGGED_WITH` edges untouched during merge | T10 | Only `HAS_BEAT` edges are created/deleted. `TAGGED_WITH` stays on beat nodes. |
| 4 | `sort_order` collision prevention | T10 | Transferred beats get `max(target sort_order) + 1`. |
| 5 | Console logging of merge steps | T10 | Every step (deprecate, transfer, delete) logged with POI/beat identifiers. |
| 6 | Partial failure recovery | T10 | On error: stop execution, show error toast, both POIs still exist. |
| 7 | Confirmation before destructive merge | T9 | Confirm button in merge preview. Disabled until all conflicts resolved. |
| 8 | `cachedPoiList` consistency | T11 | Source removed from cache after merge. Target popup updated. |
| 9 | No new secrets or API keys | All | No new credentials introduced. Uses existing `API_BASE`. |
| 10 | Input validation on searchable dropdown | T7 | Filters cached data client-side. No user input sent to API as raw text. |
| 11 | Self-merge prevention | T8 | Same-POI click ignored with toast. |
| 12 | Performance for 200+ markers | T2, T12 | `L.circleMarker` (SVG). Fallback: `preferCanvas: true` if needed. |
