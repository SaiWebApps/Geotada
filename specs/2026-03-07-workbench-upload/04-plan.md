# Implementation Plan: Workbench Upload & Beat Conflict Resolution

**Date:** 2026-03-08
**Status:** Approved
**Inputs:** `02-spec.md`, `03-red-team.md`, `release-notes.md`, codebase inspection

---

## Part A — Task Breakdown

### Task 1: Add `GET /graph/poi/{poi_name}/beats` endpoint

**Files to touch:**
- `src/api/routes/graph.py` — add new route
- `src/api/app.py` — already includes `graph.router`, no change needed

**What to do:**
- Add a new endpoint `GET /api/v1/graph/poi/{poi_name}/beats` to `graph.py`
- Run a single Cypher query: `MATCH (p:POI {name: $name})-[:HAS_BEAT]->(b:NarrativeBeat)-[:TAGGED_WITH]->(l:Lens) WHERE b.active_status = "active" RETURN b, l.name AS lens_slug`
- Return JSON: `{ "poi_name": "...", "beats": [{ "id", "script_body", "version", "active_status", "duration_sec", "lens_slug" }] }`
- If no POI found, return `{ "poi_name": "...", "beats": [] }`

**What NOT to touch:**
- Existing CRUD endpoints or graph endpoint
- No new Pydantic models needed — return raw dict

**Success check:** `curl GET /api/v1/graph/poi/TestPOI/beats` returns the correct beat+lens data for a seeded POI.

---

### Task 2: Switch `create_node()` to MERGE for POI and NarrativeBeat

**Files to touch:**
- `src/api/crud/nodes.py` — modify `create_node()` function

**What to do:**
- For `label == "POI"`: change `CREATE` to `MERGE (n:POI {name: $name})` with `coalesce(n.id, randomUUID())` and `coalesce(n.created_at, datetime())` to preserve existing IDs. Follow the exact pattern in `src/seed/locations.py:10-19`.
- For `label == "NarrativeBeat"`: change `CREATE` to `MERGE (n:NarrativeBeat {script_body: $script_body})` with same coalesce pattern. Follow `src/seed/narratives.py:14-26`.
- For all other labels: keep `CREATE` behavior unchanged.
- Ensure spatial `point()` conversion still works for POI.

**What NOT to touch:**
- `get_node()`, `update_node()`, `delete_node()`, `list_nodes()`
- Other node labels (User, Profile, Trip, etc.)

**Success check:** POST the same POI twice → second call returns the existing node (same ID), not a duplicate. Existing `test_api_create.py` tests still pass.

---

### Task 3: Switch `create_edge()` to MERGE for HAS_BEAT and TAGGED_WITH

**Files to touch:**
- `src/api/crud/edges.py` — modify `create_edge()` function

**What to do:**
- For `rel_type` in `["HAS_BEAT", "TAGGED_WITH"]`: change `CREATE` to `MERGE` on the relationship. Use `coalesce(r.id, randomUUID())` to preserve existing edge IDs.
- For all other relationship types: keep `CREATE` behavior unchanged.

**What NOT to touch:**
- `get_edge()`, `update_edge()`, `delete_edge()`, `list_edges()`
- Other relationship types

**Success check:** POST the same HAS_BEAT edge twice → second call returns the existing edge (same ID), not a duplicate.

---

### Task 4: Add Jaccard similarity utility function (frontend)

**Files to touch:**
- `frontend/review.html` — add JS function in `<script>` block

**What to do:**
- Add a `jaccardSimilarity(textA, textB)` function that:
  1. Lowercases both texts
  2. Splits on whitespace into word sets
  3. Removes English stop words (a, an, the, is, was, in, on, at, to, of, and, or, for, with, that, this, it, as, by, from, be, are, were, been, has, had, have, do, does, did, but, not, so, if, no, he, she, they, we, you, I, my, your, his, her, its, our, their)
  4. Computes `|intersection| / |union|`
  5. Returns a float 0–1
- ~15 lines of JS, no libraries

**What NOT to touch:**
- Existing review UI logic
- No external dependencies

**Success check:** `jaccardSimilarity("the old north church history", "old north church hidden history")` returns a reasonable similarity score (>0.5).

---

### Task 5: Add field mapping and lens lookup utilities (frontend)

**Files to touch:**
- `frontend/review.html` — add JS constants and helper functions

**What to do:**
- Add `MVP_LENSES` lookup object mapping display labels to slugs (mirror `src/schema/definitions.py:117-139`):
  - `"Hidden History"` → `"hidden_history"`, `"Architecture & Design"` → `"arch_design"`, etc.
- Add `mapPoiForApi(poi)` function that converts workbench POI to API format:
  - `poi_name` → `name`
  - Include `short_description`, `latitude`, `longitude`
  - Default `importance_tier: 1`, `trigger_radius: 10`, `typical_duration_min: 30`, `kid_friendly: "yes"`
- Add `mapBeatForApi(beat)` function:
  - Include `script_body`
  - Resolve `lens` display label → slug via lookup (error if not found)
  - Default `version: 1`, `active_status: "active"`, `duration_sec: gravity * 60`, `kid_friendly: "yes"`

**What NOT to touch:**
- Existing review flow or data structures

**Success check:** `mapPoiForApi({poi_name: "Test", ...})` returns `{name: "Test", ...}` with correct shape.

---

### Task 6: Build conflict detection logic (frontend)

**Files to touch:**
- `frontend/review.html` — add `detectConflicts(poiData)` async function

**What to do:**
- For each completed POI:
  1. Call `GET /api/v1/graph/poi/{poi_name}/beats` to fetch existing beats
  2. If no existing POI → mark all beats as "create" (no conflict)
  3. If existing POI found → for each incoming beat:
     - **Hard match:** existing beat has same `lens_slug` → auto-conflict
     - **Soft match:** different lens but `jaccardSimilarity(existing.script_body, incoming.script_body) >= 0.70` → auto-conflict
     - **Review band:** similarity 0.30–0.69 → flagged for review
     - **Pass-through:** similarity < 0.30 → queue for creation
  4. Also check: if POI name matches but coordinates differ >500m, flag a warning (edge case #1)
  5. Also check: if matched POI already has 12 beats and upload would exceed cap, block with error (edge case #2)
- Return a structured result: `{ newPois: [...], matchedPois: [...], conflicts: [...], reviewItems: [...], errors: [...] }`

**What NOT to touch:**
- Don't modify or create anything in Neo4j during detection — read-only

**Success check:** Given a POI with an existing beat on `hidden_history`, uploading a new beat on `hidden_history` produces a hard conflict entry.

---

### Task 7: Build conflict resolution overlay UI (frontend)

**Files to touch:**
- `frontend/review.html` — add HTML overlay + JS handler functions

**What to do:**
- Add a modal overlay (same dark theme as existing UI) with:
  - Side-by-side display: existing beat (left) vs. incoming beat (right)
  - Fields shown: `script_body`, `lens`, `gravity`, `tags`
  - Similarity score displayed for soft matches and review-band items
  - Four action buttons per conflict: **Replace**, **Skip**, **Merge**, **Change Lens**
- **Replace:** mark existing beat for deprecation (`active_status: "deprecated"`), incoming beat gets `version: existing.version + 1`
- **Skip:** discard incoming beat entirely
- **Merge:** show field-by-field picker — for each field, editor clicks left (existing) or right (incoming) to choose value. Result saved as new version.
- **Change Lens:** dropdown of 12 MVP lenses to reassign incoming beat. If new lens has no conflict, proceed; if new lens also conflicts, show that conflict.
- **Review-band items:** show similarity score and let editor choose "Approve (pass-through)" or "Treat as conflict"
- **Coordinate warning** (edge case #1): show a confirmation dialog before proceeding with mismatched POI
- "Confirm & Upload" button enabled only after all conflicts resolved

**What NOT to touch:**
- Existing review UI layout or functionality
- Don't change the `poiData` array structure — work with a separate upload state

**Success check:** Conflict overlay renders with correct side-by-side data. Each resolution action correctly updates the upload plan.

---

### Task 8: Build upload execution with progress overlay (frontend)

**Files to touch:**
- `frontend/review.html` — add upload execution function + progress overlay HTML/CSS

**What to do:**
- Add progress overlay (full-screen, semi-transparent background, centered card):
  - Phase 1: "Checking for conflicts… (X/N POIs scanned)" — during conflict detection
  - Phase 2: "Uploading… Creating POI 3/12… Creating beat 7/24… Linking relationships…" — during upload
- Upload execution (`executeUpload(uploadPlan)`) — processes the resolved upload plan:
  1. For each new POI: `POST /api/v1/nodes/POI` with mapped data
  2. For each matched POI: skip POI creation (already exists)
  3. For each beat to create: `POST /api/v1/nodes/NarrativeBeat` with mapped data
  4. For each beat to replace: `PUT /api/v1/nodes/NarrativeBeat/{id}` to set `active_status: "deprecated"` on existing, then `POST` the incoming beat with incremented version
  5. For each merged beat: `POST /api/v1/nodes/NarrativeBeat` with merged field values
  6. For each beat: `POST /api/v1/edges/HAS_BEAT` to link POI → Beat
  7. For each beat: `POST /api/v1/edges/TAGGED_WITH` to link Beat → Lens (look up Lens node by slug)
- Track success/failure per item. On network error: stop, show which items succeeded and which failed.
- Store succeeded item IDs so retry skips them (MERGE makes this safe, but avoids unnecessary requests).

**What NOT to touch:**
- Don't add batch endpoints — one request per node/edge for v1
- Don't modify API routes

**Success check:** Upload of 3 new POIs with 2 beats each creates all nodes and relationships in Neo4j. Progress overlay shows real-time counts.

---

### Task 9: Build summary screen and "Upload to Database" button (frontend)

**Files to touch:**
- `frontend/review.html` — add summary overlay HTML + upload button next to the "Ready for upload" banner

**What to do:**
- Add **"Upload to Database"** button in the existing "Ready for upload" banner area. Button is disabled if no POIs have `_status === 'complete'` (edge case #4). Show tooltip on disabled state.
- On click: trigger conflict detection (Task 6) → show conflicts if any (Task 7) → execute upload (Task 8) → show summary
- Summary screen shows:
  - POIs created: count
  - POIs matched (existing): count
  - Beats created: count
  - Beats replaced: count
  - Beats skipped: count
  - Beats merged: count
  - Relationships linked: count
  - Errors (if any): list with retry button
- "Retry Failed" button re-runs only failed items
- "Done" button dismisses summary and resets workbench to default state (clear `poiData`, reset UI)

**What NOT to touch:**
- Don't change the review flow or validation logic

**Success check:** Full end-to-end flow works: button → conflict detection → resolution → upload → summary with correct counts.

---

### Task 10: Add `beforeunload` warning (frontend)

**Files to touch:**
- `frontend/review.html` — add event listener

**What to do:**
- Add `window.addEventListener('beforeunload', ...)` that fires if `poiData.some(p => p._status === 'complete')` — i.e., there are reviewed but not-yet-uploaded POIs.
- After successful upload and workbench reset, the warning should no longer fire.

**What NOT to touch:**
- Nothing else

**Success check:** Closing the tab with reviewed POIs shows browser's native "Leave site?" confirmation. After upload completes and state resets, closing the tab does NOT show the warning.

---

### Task 11: Lens node lookup for TAGGED_WITH edge creation (frontend)

**Files to touch:**
- `frontend/review.html` — add lens ID lookup in upload execution

**What to do:**
- Before upload execution, fetch all Lens nodes: `GET /api/v1/nodes/Lens?limit=20`
- Build a slug→ID map from the response
- When creating `TAGGED_WITH` edges, use the Lens node ID as the target
- If a beat's lens slug has no matching Lens node, add to errors list (edge case #3) and skip that beat

**What NOT to touch:**
- Don't create Lens nodes — they should already exist from seeding

**Success check:** TAGGED_WITH edges are created with correct Lens node IDs. Missing lens slug produces a clear error message.

---

## Part B — Test Definitions

### Test 1: All-new POIs upload correctly (AC #1)

**Test type:** Integration (manual via workbench + Neo4j verification)
**Setup:** Empty database (only Lens nodes seeded). Load 3 POIs with 2 beats each into workbench, mark all complete.
**Steps:** Click "Upload to Database" → no conflicts expected → upload proceeds
**Expected:** Summary shows 3 POIs created, 6 beats created, 6 HAS_BEAT + 6 TAGGED_WITH relationships. Neo4j browser confirms all nodes and relationships exist.
**Edge case:** Edge case #4 — upload button disabled when 0 POIs complete.

### Test 2: Matched POI attaches beats without duplication (AC #2)

**Test type:** Integration
**Setup:** Seed one POI ("Sacré-Cœur") with 1 beat. Load workbench with "Sacré-Cœur" + 2 new beats (different lenses from existing).
**Steps:** Upload
**Expected:** Summary shows 0 POIs created, 1 POI matched, 2 beats created. No duplicate POI node in Neo4j.

### Test 3: Hard conflict detection and resolution (AC #3)

**Test type:** Integration
**Setup:** Seed POI with beat on `hidden_history` lens. Load workbench with same POI + new beat on `hidden_history`.
**Steps:** Upload → conflict overlay appears
**Expected:** Side-by-side shows existing vs. incoming beat. All four resolution options available.

### Test 4: Replace action (AC #4)

**Test type:** Integration
**Setup:** Same as Test 3.
**Steps:** Choose "Replace" in conflict overlay → confirm upload
**Expected:** Existing beat has `active_status: "deprecated"`. New beat has `version: 2`, `active_status: "active"`.

### Test 5: Merge action (AC #5)

**Test type:** Integration
**Setup:** Same as Test 3.
**Steps:** Choose "Merge" → pick `script_body` from incoming, `gravity` from existing → confirm
**Expected:** New beat with merged fields, `version: 2`. Existing beat deprecated.

### Test 6: Soft conflict detection (AC #6)

**Test type:** Integration
**Setup:** Seed POI with beat (lens: `hidden_history`, script_body: "The old church was built in 1723 by settlers"). Load workbench with same POI + beat (lens: `scandal_crime`, script_body: "The old church built in 1723 by the settlers witnessed many events").
**Steps:** Upload
**Expected:** Jaccard similarity ≥ 0.70 → conflict overlay appears despite different lenses.

### Test 7: Review band flagging (AC #7)

**Test type:** Integration
**Setup:** Seed POI with beat. Load workbench with same POI + beat with 30–69% word overlap.
**Steps:** Upload
**Expected:** Beat flagged for review with similarity score shown. Editor can approve (pass-through) or treat as conflict.

### Test 8: Retry after network failure (AC #8)

**Test type:** Manual
**Setup:** Load 5 POIs. Start upload. Simulate network failure (disable network after 2 POIs created).
**Steps:** Re-enable network → click "Retry Failed"
**Expected:** Progress overlay shows which items succeeded/failed. Retry creates only the remaining items (no duplicates due to MERGE).

### Test 9: Coordinate mismatch warning (Edge case #1)

**Test type:** Manual
**Setup:** Seed POI "Test Place" at (48.86, 2.35). Load workbench with "Test Place" at (48.87, 2.36) — >500m apart.
**Steps:** Upload
**Expected:** Warning dialog asks editor to confirm it's the same POI.

### Test 10: Max beats per POI cap (Edge case #2)

**Test type:** Manual
**Setup:** Seed POI with 12 beats (one per lens). Load workbench with same POI + 1 new beat.
**Steps:** Upload
**Expected:** Error message referencing the 1-beat-per-lens cap. Upload blocked for that POI.

### Test 11: Invalid lens slug (Edge case #3)

**Test type:** Manual
**Setup:** Load workbench with a beat whose `lens` field doesn't match any MVP lens.
**Steps:** Upload
**Expected:** Error for that beat. Editor can fix lens before retrying.

### Test 12: beforeunload warning

**Test type:** Manual
**Steps:** Review POIs → try closing tab → warning appears. Upload successfully → try closing tab → no warning.

### Test 13: MERGE idempotency (backend)

**Test type:** API test (can be automated in `tests/`)
**Steps:** POST same POI to `/api/v1/nodes/POI` twice with identical `name`.
**Expected:** Second call returns same `id` as first. Only one POI node exists in database.

### Test 14: Beat traversal endpoint

**Test type:** API test
**Steps:** Seed POI with 2 beats on different lenses. GET `/api/v1/graph/poi/{name}/beats`.
**Expected:** Response contains 2 beats with correct `lens_slug` values.

---

## Part C — Claude Code Prompt

```
## Slice Goal

An editor can upload all reviewed POIs and beats from the Editorial Workbench to Neo4j, with conflicts detected and resolved inline before writing.

## Context

Read these files before starting:
- `specs/NORTHSTAR.md` — project north star
- `specs/2026-03-07-workbench-upload/02-spec.md` — behavior spec with acceptance criteria
- `specs/2026-03-07-workbench-upload/03-red-team.md` — red team review with resolved blockers
- `specs/2026-03-07-workbench-upload/release-notes.md` — technical details for backend changes
- `specs/2026-03-07-workbench-upload/04-plan.md` — this implementation plan (full task breakdown and test definitions)

## Stack

- Backend: FastAPI + Neo4j (Python). API lives in `src/api/`.
- Frontend: Vanilla HTML/JS in `frontend/review.html`. No frameworks, no build step.
- Seeding pattern (MERGE-based): `src/seed/locations.py`, `src/seed/narratives.py` — follow this pattern.
- Lens config: `src/schema/definitions.py:117-139` (MVP_LENSES list).

## What to build (in order)

### Backend (Tasks 1–3)

1. **New endpoint:** `GET /api/v1/graph/poi/{poi_name}/beats` in `src/api/routes/graph.py`. Single Cypher traversal: `POI → HAS_BEAT → NarrativeBeat → TAGGED_WITH → Lens`. Returns `{ poi_name, beats: [{ id, script_body, version, active_status, duration_sec, lens_slug }] }`. Only return beats where `active_status = "active"`.

2. **MERGE for POI creation:** In `src/api/crud/nodes.py`, modify `create_node()` so that when `label == "POI"`, it uses `MERGE (n:POI {name: $name})` instead of `CREATE`. Use `coalesce(n.id, randomUUID())` and `coalesce(n.created_at, datetime())`. Follow the pattern in `src/seed/locations.py:10-19`. Keep `CREATE` for all other labels.

3. **MERGE for edges:** In `src/api/crud/edges.py`, modify `create_edge()` so that `HAS_BEAT` and `TAGGED_WITH` use `MERGE` instead of `CREATE`. Use `coalesce(r.id, randomUUID())`. Keep `CREATE` for all other relationship types.

### Frontend (Tasks 4–11, all in `frontend/review.html`)

4. **Jaccard similarity function:** `jaccardSimilarity(textA, textB)` — lowercase, split on whitespace, remove stop words, compute `|intersection| / |union|`. ~15 lines, no libraries.

5. **Field mapping utilities:**
   - `MVP_LENSES` object: display label → slug for all 12 lenses (mirror `src/schema/definitions.py:117-139`)
   - `mapPoiForApi(poi)`: `poi_name` → `name`, include coordinates, defaults for `importance_tier`, `trigger_radius`, etc.
   - `mapBeatForApi(beat)`: resolve lens label → slug, default `version: 1`, `active_status: "active"`, `duration_sec: gravity * 60`

6. **Conflict detection:** `detectConflicts(poiData)` async function:
   - For each complete POI, call `GET /graph/poi/{name}/beats`
   - Hard match: same lens → auto-conflict
   - Soft match: different lens, Jaccard ≥ 0.70 → auto-conflict
   - Review band: 0.30–0.69 → flag for review
   - Pass-through: < 0.30 → create
   - Check coordinate mismatch >500m → warning
   - Check 12-beat cap → error

7. **Conflict resolution overlay:** Modal with side-by-side diff. Four actions: Replace (deprecate existing, version+1), Skip (discard incoming), Merge (field-by-field picker), Change Lens (dropdown). Review-band items show similarity score with approve/conflict toggle. "Confirm & Upload" button.

8. **Upload execution + progress overlay:** `executeUpload(plan)` — POST nodes and edges one at a time with real-time progress counter. Track success/failure per item. On error: stop, show status, enable retry.

9. **Summary screen + upload button:** "Upload to Database" button in the "Ready for upload" banner. Disabled if 0 complete POIs (with tooltip). Summary shows counts for POIs created/matched, beats created/replaced/skipped/merged, relationships linked, errors. "Retry Failed" and "Done" buttons.

10. **beforeunload warning:** Fire if `poiData.some(p => p._status === 'complete')`. Don't fire after upload resets state.

11. **Lens node lookup:** Before upload, `GET /api/v1/nodes/Lens?limit=20` to build slug→ID map. Use Lens IDs for TAGGED_WITH targets. Error if lens slug not found.

## What NOT to touch

- Existing review/validation flow in `review.html`
- Existing CRUD behavior for node types other than POI and NarrativeBeat
- Existing edge behavior for relationship types other than HAS_BEAT and TAGGED_WITH
- No new Python packages or JS libraries
- No batch upload endpoint (one request per item for v1)
- No changes to the workbench JSON import format
- No changes to the seeding code

## Verification

After implementation, verify all 14 test definitions in Part B of `04-plan.md`. For automated API tests (Tests 13–14), add them to `tests/`. For integration tests (Tests 1–8), verify manually through the workbench. For edge case tests (Tests 9–12), verify manually.

Before starting, confirm you understand the full scope and flag any conflicts with the existing codebase or assumptions you are making.
```

---

## North Star Alignment Check

Final verification against `specs/NORTHSTAR.md`:

- **Manual JSON upload** — no pipeline automation added (line 63) ✓
- **Browser-based HTML/JS** — no frameworks introduced (line 42) ✓
- **Constraints at database layer** — 1-beat-per-lens enforced at upload time, not extraction (line 44) ✓
- **Jaccard similarity ≠ embedding similarity** — not violating the explicit boundary (line 64) ✓
- **MERGE pattern** — follows existing seeding code, not a new architectural choice ✓
- **Active Build Target** — directly addresses lines 93-100 ✓
- **Task count:** 11 tasks — under the 12-item cap ✓
