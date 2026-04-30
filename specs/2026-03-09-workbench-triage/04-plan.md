# Implementation Plan: Workbench Triage & Progressive Upload

**Date:** 2026-03-09
**Status:** Draft
**Inputs:** `specs/NORTHSTAR.md`, `02-spec.md`, `03-red-team.md`, codebase inspection of `frontend/review.html`

---

## Part A — Task Breakdown

### Task 1: Create Fact Check & Gravity Score Prompt V2

- **Files to touch:** `Docs/Prompts/Fact Check & Gravity Score Prompt V2` (new file)
- **What to do:**
  - Copy V1 as starting point. Make two changes:
    1. Add a `poi_audit_notes` key as a separate top-level field per POI object (parallel to existing beat-level `audit_notes`). This holds POI-level audit results from Steps 3 (Coordinate QA) and 4 (Status Check). Structure: same `{ issue, current_text, suggested_fix, source, confidence }` format as beat-level notes, but as an array at the POI level.
    2. Remove all references to `tags` from the output format. Beats should no longer include a `tags` field.
  - Preserve V1 unchanged for rollback.
- **What NOT to touch:** V1 prompt file. Data Miner prompt.
- **Success check:** V2 file exists alongside V1. Diff shows only `poi_audit_notes` addition and `tags` removal. V1 is byte-identical to before.

---

### Task 2: Strip all tag code from the codebase

- **Files to touch:** `frontend/review.html`
- **What to do:**
  - Remove tag parsing in `processJson()` (~line 902 area — anywhere `tags` are read from JSON input)
  - Remove tag input field in `renderDetail()` (~line 1263 — the "Tags (comma-separated)" field group)
  - Remove tag saving in `autoSaveCurrent()` (~line 1107 — the split/trim/filter on tags)
  - Remove any tag references in `mapBeatForApi()` or conflict resolution
  - Search for any remaining references to `tags` or `tag` in the file and remove them
- **What NOT to touch:** Lens system. Beat fields other than tags. Prompt files.
- **Success check:** `grep -i "tag" frontend/review.html` returns zero relevant matches (CSS class names like `TAGGED_WITH` edge type are fine — that's the Lens relationship, not content tags).

---

### Task 3: Dynamic lens fetch at load time

- **Files to touch:** `frontend/review.html`
- **What to do:**
  - At workbench initialization (after city prompt), fetch `GET /api/v1/nodes/Lens?limit=50` to get all Lens nodes
  - Build the lens map dynamically from the response: `{ displayName: slug }` from each Lens node's `name` and `slug` properties
  - Replace the hardcoded `MVP_LENSES` constant and `SLUG_SET` (~lines 1468–1484) with the dynamically fetched map
  - Update `resolveLensSlug()` (~line 1486) to use the dynamic map
  - **Gate JSON loading on lens availability:** Disable the "Load JSON" file input until lenses are fetched. If the fetch fails, show an error state: "Cannot connect to database — workbench requires a live connection" and block further actions (per AC7)
  - Cache the lens list in memory for the session (no re-fetch needed)
- **What NOT to touch:** The lens dropdown in `showChangeLensDropdown()` should also use the dynamic list — update it to iterate the fetched map instead of `MVP_LENSES`. Don't change Lens nodes in the database.
- **Success check:** Workbench loads → lenses fetched from API → "Load JSON" enabled. Kill the API → reload → error state shown, "Load JSON" disabled. `MVP_LENSES` constant no longer exists in the file.

---

### Task 4: JSON V2 schema validation on load

- **Files to touch:** `frontend/review.html`
- **What to do:**
  - Add a `validateV2Schema(data)` function that checks the loaded JSON against expected V2 structure:
    - Must be an array
    - Each entry must have: `poi_name` (string), `latitude` (number), `longitude` (number), `beats` (array)
    - Each beat must have: `script_body` (string), `lens` (string), `gravity` (number, 1–5)
    - Optional fields: `short_description`, `orientation`, `poi_audit_notes` (array of audit note objects), beat-level `audit_notes` (string or object), `physical_cue`, `source_passage`
    - Reject if: `tags` field is present (V1 format — not supported), unknown top-level properties beyond the expected set, beats array is empty
  - Call this validation in the JSON load handler (before `processJson()`). On failure, show an error message listing what's wrong and reject the file
  - Support both string and structured-object formats for `audit_notes` (per Edge Case 4 in spec)
- **What NOT to touch:** The existing `processJson()` validation (required fields, coord validation). Layer the schema check before it.
- **Success check:** Load a V2 JSON → passes. Load a V1 JSON with tags → rejected with "V1 format not supported" message. Load a malformed JSON (missing beats array) → rejected with specific error.

---

### Task 5: Refactor status model and worklist priority sorting

- **Files to touch:** `frontend/review.html`
- **What to do:**
  - Expand the `_status` field from `{ 'pending', 'complete' }` to `{ 'pending', 'deferred', 'complete', 'uploaded' }`
  - Add a computed priority function: `getDisplayPriority(poi)` that returns a sort key:
    1. `flagged` (computed: `isFlagged(poi) === true` AND status is `pending`) — highest priority
    2. `pending` (unreviewed, not flagged)
    3. `deferred`
    4. `uploaded` — lowest (will be collapsed, but needed for sort)
  - Refactor `renderWorklist()` (~lines 1037–1070):
    - Sort `poiData` indices by priority before rendering
    - Show status badges: "Flagged" (orange), "Pending" (default), "Deferred" (yellow), "Uploaded" (green)
    - Re-sort dynamically when any status changes
  - Update `canMarkComplete()` to work with the new status model
  - Update `checkAllComplete()` to treat `uploaded` as done
- **What NOT to touch:** The `isFlagged()` logic itself. The detail panel rendering.
- **Success check:** Load JSON with mix of flagged/clean POIs → flagged items appear first. Worklist re-sorts when statuses change.

---

### Task 6: Uploaded POIs collapsed summary section

- **Files to touch:** `frontend/review.html`
- **What to do:**
  - In `renderWorklist()`, separate uploaded POIs from the active worklist
  - Render uploaded POIs as a collapsed summary at the bottom: "8 of 24 uploaded" with a toggle to expand/collapse individual items
  - Expanded view shows uploaded POI names (read-only, no click-to-select behavior — selecting an uploaded POI shows read-only detail per AC5)
  - Add CSS for the collapsed summary section (subtle styling, distinct from active worklist)
- **What NOT to touch:** Active worklist items (flagged/pending/deferred). Progress bar.
- **Success check:** Upload a POI → it moves from active worklist to collapsed summary. Count updates. Toggle expand/collapse works. Clicking an uploaded POI in expanded view shows read-only detail.

---

### Task 7: POI-level audit notes rendering in detail panel

- **Files to touch:** `frontend/review.html`
- **What to do:**
  - In `renderDetail()` (~line 1164), add a distinct "POI Audit Notes" section above the beats section. Render `poi.poi_audit_notes` (array) using the existing `renderAuditNotes()` function, wrapped in a visually distinct container (different background, clear "POI-Level Audit" header)
  - Handle both the V2 format (`poi_audit_notes` as top-level array) and the case where it's absent (no section shown)
  - Ensure POI-level audit notes are visually distinct from beat-level audit notes (AC8 in spec): use a section header like "POI Audit Notes" with a border/background that differs from beat-level notes
- **What NOT to touch:** Beat-level audit notes rendering. The `renderAuditNotes()` function itself (reuse it).
- **Success check:** Load JSON with `poi_audit_notes` → POI audit section renders with distinct styling. Load JSON without `poi_audit_notes` → no section shown. Beat-level notes still render within beat cards as before.

---

### Task 8: Add defer mechanism

- **Files to touch:** `frontend/review.html`
- **What to do:**
  - Add a "Defer" button next to the "Mark Complete" button in the detail panel action bar
  - On click: set `poi._status = 'deferred'`, re-render worklist (POI drops below unreviewed items per priority sort), show "deferred" badge on the worklist row
  - Deferred POIs remain selectable and editable — the editor can un-defer by clicking "Mark Complete" when ready
  - Disable "Defer" for uploaded POIs (read-only state)
- **What NOT to touch:** Mark Complete logic. Upload flow.
- **Success check:** Select POI → click Defer → POI moves below unreviewed in worklist, shows "Deferred" badge. Select deferred POI → edit → click Mark Complete → status changes, POI re-sorts.

---

### Task 9: Per-POI conflict detection on select

- **Files to touch:** `frontend/review.html`
- **What to do:**
  - Create a new function `detectConflictsForPoi(poi)` that extracts the single-POI logic from `detectConflicts()` (~lines 1526–1625). It should:
    1. Fetch existing beats: `GET /api/v1/graph/poi/{poi_name}/beats`
    2. Use the cached POI list (fetched once at load time per R1 mitigation — add a `cachedPoiList` variable populated alongside the lens fetch)
    3. Return `{ isNew, existingBeats, beatConflicts, beatReviewItems, coordWarning, errors }` for that single POI
  - Call `detectConflictsForPoi()` in `selectPoi()` when the POI is selected (not uploaded, not already checked)
  - Show a loading indicator in the detail panel while conflict detection runs
  - Cache per-POI conflict results in a `_conflicts` property on the POI object so re-selecting doesn't re-fetch (invalidate on edit)
  - Keep the existing batch `detectConflicts()` function intact for now — it may be useful later
- **What NOT to touch:** The similarity logic (`jaccardSimilarity()`). The conflict resolution actions (replace/skip/merge/change-lens) — those move to Task 10.
- **Success check:** Select a POI → loading indicator → conflict results appear in detail panel. Re-select same POI → no re-fetch (cached). Edit a beat → cache invalidated → next select re-fetches.

---

### Task 10: Inline beat-level conflicts in detail panel

- **Files to touch:** `frontend/review.html`
- **What to do:**
  - When `detectConflictsForPoi()` returns conflicts for a POI, render them **inline within each beat card** in the detail panel (not in a separate overlay):
    - Show a "Conflict" badge on the beat card header
    - Below the beat's fields, show a side-by-side comparison: existing beat (from DB) vs. incoming beat (from JSON)
    - Show resolution buttons: Replace, Skip, Merge, Change Lens (reuse logic from `showConflictOverlay` ~lines 1629–1741)
    - Once resolved, show the chosen resolution as a label (e.g., "Will replace existing") and allow changing the decision
  - Store conflict resolutions on the beat object (e.g., `beat._conflictResolution = { action, existingBeat, mergedBeat?, newLensSlug? }`)
  - For review items (Jaccard 0.30–0.70), show a softer "Review" badge with "Approve" / "Treat as conflict" options
  - The merge overlay and change-lens dropdown can remain as popups/modals — just triggered from within the beat card instead of the batch overlay
- **What NOT to touch:** The batch `showConflictOverlay()` — leave it in place but it won't be called in the new flow. Don't change similarity thresholds.
- **Success check:** Select a POI with conflicts → beat cards show inline conflict panels with side-by-side comparison. Resolve a conflict → resolution label shown. All conflicts resolved → "Mark Complete" enabled (if other validations pass).

---

### Task 11: Progressive upload — `uploadSinglePoi()` on Mark Complete

- **Files to touch:** `frontend/review.html`
- **What to do:**
  - Create `uploadSinglePoi(poiIdx)` that uploads a single POI and its beats with conflict resolutions applied:
    1. Build the upload payload for one POI (reuse `mapPoiForApi`, `mapBeatForApi`)
    2. Apply conflict resolutions from `beat._conflictResolution` (replace → deprecate existing + create new; skip → don't create; merge → deprecate + create merged; change-lens → create with new slug)
    3. POST POI → POST beats → POST edges (HAS_BEAT, TAGGED_WITH)
    4. On success: set `poi._status = 'uploaded'`, re-render worklist (POI moves to collapsed section)
    5. On failure: revert to `complete` status, show error, allow retry (Edge Case 1 in spec)
  - Change the "Mark Complete" button behavior:
    - Current: sets `_status = 'complete'` (review done, awaiting batch upload)
    - New: sets `_status = 'complete'` AND immediately calls `uploadSinglePoi()`. On success → `_status = 'uploaded'`
  - Show a brief loading state on the button during upload ("Uploading...")
  - Lock uploaded POIs: detail panel becomes read-only (disable all inputs, hide action buttons) per AC5
  - Fetch the lens node ID map once at load time (alongside lens names) so `uploadSinglePoi` doesn't need to re-fetch it
- **What NOT to touch:** The batch `executeUpload()` function — leave intact. The conflict overlay (batch). Summary overlay (batch).
- **Success check:** Mark Complete on a clean POI → uploads → moves to collapsed section → detail is read-only. Mark Complete on a POI with resolved conflicts → conflict resolutions applied during upload. Upload fails → POI reverts to reviewable state with error message.

---

### Task 12: XSS audit and HTML escaping enforcement

- **Files to touch:** `frontend/review.html`
- **What to do:**
  - Audit every `innerHTML` assignment in the file. For each one, verify that all dynamic content passes through `escHtml()` before insertion
  - Pay special attention to these high-risk fields (AI-generated content): `script_body`, `audit_notes` (both string and object formats), `suggested_fix`, `poi_audit_notes`
  - Check `renderAuditNotes()` (~lines 964–1001): verify that `issue`, `current_text`, `suggested_fix`, and `source` fields are escaped. The existing function uses innerHTML — confirm `escHtml()` is applied to all interpolated values
  - Check the new inline conflict panel (Task 10): existing beat `script_body` from the DB must also be escaped
  - Check the new POI audit notes section (Task 7): all fields escaped
  - Fix any instances where raw content is inserted via `innerHTML` without escaping
- **What NOT to touch:** `textContent` assignments (already safe). CSS class names in innerHTML templates.
- **Success check:** Insert a test POI with `script_body: "<script>alert('xss')</script>"` → renders as escaped text, no script execution. Same test for `audit_notes.suggested_fix`, `poi_audit_notes[0].issue`. No alerts fire.

---

## Part B — Test Definitions

### AC1: Per-POI conflict detection on select
- **Type:** Manual verification
- **Test:** Load JSON with POIs that have existing beats in DB. Select a POI → conflict status appears in detail panel before editor begins reviewing.
- **Expected:** Loading indicator shows, then conflict/review badges appear on beat cards with side-by-side comparisons.

### AC2: Worklist priority sorting
- **Type:** Manual verification
- **Test:** Load JSON containing: 2 POIs outside geofence (flagged), 3 clean POIs (unreviewed), 1 deferred POI (defer it manually). Verify sort order.
- **Expected:** Flagged POIs at top, then unreviewed, then deferred. Upload one → it moves to collapsed section at bottom. Re-sort happens dynamically.

### AC3: Uploaded POIs collapsed summary
- **Type:** Manual verification
- **Test:** Upload 3 of 10 POIs. Check worklist.
- **Expected:** Bottom of worklist shows "3 of 10 uploaded" with expandable section. Active worklist shows only 7 items.

### AC4: Mark Complete uploads single POI
- **Type:** Manual verification + network inspection
- **Test:** Mark a POI complete. Monitor network tab.
- **Expected:** POST requests for that POI only (not others). POI moves to uploaded group. Network shows: POST POI → POST beats → POST edges.

### AC5: Uploaded POI is locked/read-only
- **Type:** Manual verification
- **Test:** Click an uploaded POI in the expanded uploaded section.
- **Expected:** Detail panel renders with all fields disabled/read-only. No "Mark Complete" or "Defer" buttons.

### AC6: Dynamic lens dropdown from database
- **Type:** Manual verification
- **Test:** Add a new Lens node to Neo4j. Reload workbench. Check lens resolution.
- **Expected:** New lens appears in change-lens dropdown. `resolveLensSlug()` resolves it correctly. `MVP_LENSES` no longer exists in source.

### AC7: API unreachable error state
- **Type:** Manual verification
- **Test:** Stop the API server. Load the workbench.
- **Expected:** Error message: "Cannot connect to database — workbench requires a live connection." Load JSON button disabled. No other actions available.

### AC8: POI-level audit notes distinct rendering
- **Type:** Manual verification
- **Test:** Load JSON with `poi_audit_notes` on at least 2 POIs. Select one.
- **Expected:** "POI Audit Notes" section renders above beats with distinct styling. Beat-level audit notes render within beat cards. The two are visually distinguishable.

### AC9: Tags fully absent
- **Type:** Code search + manual verification
- **Test:** `grep -i "tag" frontend/review.html` — no tag-related code (excluding `TAGGED_WITH` edge type). Load JSON → no tag input fields visible.
- **Expected:** Zero tag references in UI code. No tag input in detail panel. No tag parsing in JSON load.

### AC10: Beat-level conflicts inline with resolution
- **Type:** Manual verification
- **Test:** Load JSON with a POI that has hard-match conflicts (same lens as existing beat in DB). Select that POI.
- **Expected:** Beat card shows "Conflict" badge, side-by-side comparison, and resolution buttons (replace/skip/merge/change-lens). Resolve → label shown. All resolved → Mark Complete enabled.

### AC11: JSON V2 schema validation
- **Type:** Manual verification
- **Test:** (a) Load valid V2 JSON → accepted. (b) Load V1 JSON with `tags` → rejected with error. (c) Load JSON missing `beats` array → rejected with specific error.
- **Expected:** Clear error messages for each rejection case. Valid V2 files load normally.

### AC12: XSS prevention on all content fields
- **Type:** Manual verification
- **Test:** Create a JSON with `script_body: "<img src=x onerror=alert(1)>"`, `audit_notes: { issue: "<script>alert(2)</script>" }`, `poi_audit_notes: [{ suggested_fix: "<b onmouseover=alert(3)>hover</b>" }]`. Load and select the POI.
- **Expected:** All content renders as escaped text. No script execution, no event handlers fire. Angle brackets visible as literal characters.

---

## Part C — Claude Code Prompt

```
## Slice Goal

An editor can load fact-checked JSON, triage POIs by audit priority, review each POI and its beats with live conflict detection, and upload individually on completion — so that 100+ Paris POIs reach the database continuously instead of in a single batch.

## Context

You are working on the Ondoway Editorial Workbench — a browser-based HTML/JS tool at `frontend/review.html` (~2,310 lines, single-file). The workbench lets editors review and upload fact-checked POI data to a Neo4j database via a REST API at localhost:8000.

Read these files before starting:
- `specs/NORTHSTAR.md` — project north star
- `specs/2026-03-09-workbench-triage/02-spec.md` — approved behavior spec
- `specs/2026-03-09-workbench-triage/03-red-team.md` — red team review with resolutions
- `specs/2026-03-09-workbench-triage/04-plan.md` — this implementation plan (you are here)
- `frontend/review.html` — the file you are modifying
- `Docs/Prompts/Fact Check & Gravity Score Prompt V1` — existing prompt to base V2 on

## Task Breakdown (execute in order)

### Task 1: Create Fact Check & Gravity Score Prompt V2
- Copy V1 to `Docs/Prompts/Fact Check & Gravity Score Prompt V2`
- Add `poi_audit_notes` as a separate top-level key per POI (array of `{ issue, current_text, suggested_fix, source, confidence }` objects). POI-level audit results from Steps 3 (Coordinate QA) and 4 (Status Check) go here instead of being inlined.
- Remove `tags` from the output format — beats should no longer include a `tags` field.
- Do NOT modify V1.

### Task 2: Strip all tag code
In `frontend/review.html`:
- Remove tag parsing (~line 902 area in processJson)
- Remove tag input field (~line 1263 in renderDetail — the "Tags (comma-separated)" field group)
- Remove tag saving (~line 1107 in autoSaveCurrent)
- Remove any tag references in mapBeatForApi, conflict resolution, merge overlay
- Search for all remaining `tag` references and remove (preserve `TAGGED_WITH` edge type — that's the Lens relationship)

### Task 3: Dynamic lens fetch at load time
- After city prompt resolves, fetch `GET /api/v1/nodes/Lens?limit=50`
- Build lens map dynamically from response (each Lens node has `name` and `slug` properties)
- Replace hardcoded `MVP_LENSES` (~line 1468) and `SLUG_SET` (~line 1484) with the fetched map
- Update `resolveLensSlug()` (~line 1486) to use dynamic map
- Gate JSON loading: disable "Load JSON" input until lenses are fetched. If fetch fails → show error: "Cannot connect to database — workbench requires a live connection" and block all actions
- Also fetch and cache the full POI list (`GET /api/v1/nodes/POI?limit=500`) at load time for use in conflict detection (avoids redundant calls per R1 mitigation)
- Fetch lens node IDs at the same time (needed for TAGGED_WITH edges during upload)

### Task 4: JSON V2 schema validation on load
- Add `validateV2Schema(data)` function before `processJson()`:
  - Must be array; each entry needs `poi_name` (string), `latitude` (number), `longitude` (number), `beats` (non-empty array)
  - Each beat needs `script_body` (string), `lens` (string), `gravity` (number 1–5)
  - Reject if `tags` field present (V1 format)
  - Allow optional: `short_description`, `orientation`, `poi_audit_notes`, beat `audit_notes` (string or object), `physical_cue`, `source_passage`
- On failure: show error listing issues, reject file

### Task 5: Refactor status model + worklist priority sorting
- Expand `_status` to: `pending`, `deferred`, `complete`, `uploaded`
- Add `getDisplayPriority(poi)` returning sort key: flagged-pending (1) > pending (2) > deferred (3) > uploaded (4)
  - "flagged" = `isFlagged(poi) && _status === 'pending'`
- Refactor `renderWorklist()` (~line 1037) to sort by priority
- Show status badges: Flagged (orange ⚠), Pending (default), Deferred (yellow), Uploaded (green ✓)
- Re-sort dynamically on status changes

### Task 6: Uploaded POIs collapsed summary section
- In `renderWorklist()`, separate uploaded POIs from active list
- Render at bottom: "N of M uploaded" with expand/collapse toggle
- Expanded view shows POI names, clickable to view read-only detail
- Update `updateProgress()` to reflect uploaded count

### Task 7: POI-level audit notes in detail panel
- In `renderDetail()` (~line 1164), add "POI Audit Notes" section above the beats section
- Render `poi.poi_audit_notes` (array) using `renderAuditNotes()` for each item
- Wrap in a visually distinct container (different background/border, clear "POI Audit Notes" header)
- If `poi_audit_notes` is absent or empty, don't render the section

### Task 8: Add defer mechanism
- Add "Defer" button in detail panel action bar, next to "Mark Complete"
- On click: set `_status = 'deferred'`, re-render worklist
- Deferred POIs remain editable. "Mark Complete" un-defers.
- Disable Defer for uploaded POIs

### Task 9: Per-POI conflict detection on select
- Create `detectConflictsForPoi(poi)` extracting single-POI logic from `detectConflicts()` (~line 1526):
  1. Fetch existing beats: `GET /api/v1/graph/poi/{name}/beats`
  2. Use cached POI list (from Task 3) for coordinate comparison
  3. Return: `{ isNew, existingBeats, beatConflicts, beatReviewItems, coordWarning, errors }`
- Call in `selectPoi()` for non-uploaded POIs
- Show loading indicator during detection
- Cache results in `poi._conflicts`; invalidate on edit
- Keep existing batch `detectConflicts()` intact

### Task 10: Inline beat-level conflicts in detail panel
- When `poi._conflicts` has beat conflicts, render inline within each beat card:
  - "Conflict" badge on beat header
  - Side-by-side: existing (DB) vs incoming (JSON) beat
  - Resolution buttons: Replace, Skip, Merge, Change Lens
  - Resolved → label shown (e.g., "Will replace existing"), changeable
- For review items (Jaccard 0.30–0.70): "Review" badge with Approve/Treat-as-conflict options
- Store resolutions on beat: `beat._conflictResolution = { action, existingBeat, mergedBeat?, newLensSlug? }`
- Reuse merge overlay and change-lens dropdown logic from existing code

### Task 11: Progressive upload — uploadSinglePoi() on Mark Complete
- Create `uploadSinglePoi(poiIdx)`:
  1. Build payload (reuse mapPoiForApi, mapBeatForApi)
  2. Apply conflict resolutions from `beat._conflictResolution`
  3. POST POI → POST beats → POST edges (HAS_BEAT, TAGGED_WITH) using cached lens ID map
  4. Success → `_status = 'uploaded'`, re-render worklist
  5. Failure → revert to reviewable state, show error, allow retry
- Wire into "Mark Complete": complete review → upload immediately → uploaded
- Show "Uploading..." state on button
- Lock uploaded POIs: read-only detail panel (disable inputs, hide action buttons)

### Task 12: XSS audit and HTML escaping enforcement
- Audit every `innerHTML` assignment in the file
- Verify `escHtml()` is applied to all dynamic content, especially:
  - `script_body`, `audit_notes` (string + object), `suggested_fix`, `poi_audit_notes`
  - Existing beat `script_body` from DB in conflict panels
  - Source URLs in audit notes
- Fix any unescaped insertions
- Test with XSS payloads in script_body, audit_notes, poi_audit_notes

## What NOT to Touch
- Neo4j schema or API endpoints
- Data Miner prompt
- `frontend/index.html` or `frontend/editor/index.html`
- Similarity thresholds (Jaccard stays as-is; cosine similarity is north star target, not this slice)
- Batch upload functions (`executeUpload`, `showConflictOverlay`, `showSummaryOverlay`) — leave intact, just don't call them in the new flow
- Lens nodes in the database

## Best Practices Implementation Checklist

1. **JSON schema validation on load** (Task 4) — reject malformed/V1 files before processing
   - Verify: `validateV2Schema()` called before `processJson()`, rejects invalid input with clear error
2. **XSS prevention via HTML escaping** (Task 12) — all AI-generated content escaped before DOM insertion
   - Verify: every `innerHTML` with dynamic content uses `escHtml()`. Test with `<script>alert(1)</script>` in script_body → renders as text
3. **API error handling** (Task 3) — lens fetch failure blocks workbench; upload failure reverts POI state
   - Verify: kill API → load workbench → error state shown, no actions available
4. **POI list caching** (Task 3, Task 9) — fetch once at load, reuse in conflict detection
   - Verify: network tab shows single POI list fetch, not per-select
5. **No secrets in client code** — API_BASE is localhost, no API keys
   - Verify: grep for API keys, tokens, secrets → none found

## North Star Final Check

- ✅ Progressive upload directly enables Phase 1 gate (100+ POIs live continuously)
- ✅ Dynamic lens dropdown moves source of truth to database Lens nodes
- ✅ Tags removed — lenses are the only classification system
- ✅ Jaccard similarity retained as interim; cosine similarity noted as north star target (not this slice)
- ✅ Prompt V2 created alongside V1 (V1 preserved for rollback)
- ✅ No changes to API, schema, or architectural commitments

Before starting, confirm you understand the full scope and flag any conflicts with the existing codebase or assumptions you are making.
```

---

## Part D — Best Practices Implementation Checklist

| # | Practice | Task(s) | How to Verify |
|---|----------|---------|---------------|
| 1 | JSON schema validation on load | Task 4 | Load V1 JSON → rejected. Load malformed JSON → rejected with specific errors. Load valid V2 → accepted. |
| 2 | XSS prevention via HTML escaping | Task 12 (audit), Tasks 7, 10 (new rendering) | Insert `<script>alert(1)</script>` in script_body, audit_notes.issue, poi_audit_notes[0].suggested_fix → all render as escaped text, no execution. |
| 3 | API connection gating | Task 3 | Kill API → reload workbench → "Cannot connect to database" error shown. Load JSON button disabled. |
| 4 | API error handling on upload failure | Task 11 | Simulate upload failure (kill API mid-upload) → POI reverts to reviewable state with error message. |
| 5 | POI list caching (performance) | Tasks 3, 9 | Network tab: single `GET /nodes/POI` at load. Select 5 POIs → no additional POI list fetches. |
| 6 | No secrets in client code | All | `grep -i "key\|token\|secret\|password" frontend/review.html` → no credentials found (only CSS/HTML keywords). |
| 7 | Input sanitization at boundary | Task 4 | JSON with unexpected properties → rejected. JSON with missing required fields → rejected. Clear error messages for each case. |
