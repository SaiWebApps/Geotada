# Implementation Plan: POI Matching — Location-First Deduplication

**Date:** 2026-03-17
**Stage:** 4 — Implementation Plan
**Spec:** `specs/2026-03-15-poi-matching-fix/02-spec.md`
**Red Team:** `specs/2026-03-15-poi-matching-fix/03-red-team.md`
**North Star Ref:** `specs/NORTHSTAR.md`

---

## Part A — Task Breakdown

### Task 1: Add `PROXIMITY_THRESHOLD_M` constant and `findProximityMatches()` function

**Files to touch:** `frontend/review.html`

**What to do:**
- Add a named constant `PROXIMITY_THRESHOLD_M = 50` near the other constants (around line 898, near `haversineKm`).
- Write a new function `findProximityMatches(poi, cachedPoiList)` that:
  1. Takes an incoming POI (with `latitude`, `longitude`) and the cached POI list.
  2. Iterates `cachedPoiList`, computes Haversine distance to each POI that has `properties.location`.
  3. Returns an array of `{ existingPoi, distanceM }` for all POIs within `PROXIMITY_THRESHOLD_M`, sorted ascending by distance.
  4. Returns empty array if no matches (= auto-new).

**What NOT to touch:** Beat-level conflict detection, upload logic, renderDetail.

**Success check:** Function exists and returns correct results when called manually from browser console with test data.

---

### Task 2: Replace `detectConflictsForPoi()` with location-first logic

**Files to touch:** `frontend/review.html` (lines ~2275-2367)

**What to do:**
- Rewrite `detectConflictsForPoi(poi)` to use location-first matching:
  1. **Missing coordinates check (AC 7):** If `poi.latitude` or `poi.longitude` is missing/invalid, return immediately with `errors: ["POI has no valid coordinates"]` and a new flag `missingCoords: true`.
  2. **Proximity check:** Call `findProximityMatches(poi, cachedPoiList)`.
  3. **No matches → auto-new (AC 1, AC 8):** Set `isNew: true`. Do NOT check names, alt-names, or existing beats. Return immediately.
  4. **One match (AC 2):** Set `isNew: false`, `proximityMatches: [match]`. Add `nameInfo` with both POI names and distance for display. Do NOT auto-resolve — the editor must decide.
  5. **Multiple matches (AC 3):** Set `isNew: false`, `proximityMatches: [matches]` ranked by distance.
- Remove the alt-name matching logic (lines 2278-2294) entirely.
- Remove the 500m coordinate warning (lines 2318-2325) — superseded by the 50m proximity check.
- Change `isNew` determination (line 2314) from beat/coordinate check to "no proximity matches."
- Keep beat-level conflict detection (lines 2328-2363) unchanged — it runs only after the editor resolves the POI match.
- Add `proximityResolution` field to the result: `null` initially, set to `'same'` or `'different'` by the editor.
- Compute name similarity as a display-only signal: show `nameSimilarity` percentage in the result for editor reference.

**What NOT to touch:** `detectConflicts()` (the batch version at line 2170) — it will be addressed by Task 6.

**Success check:** `detectConflictsForPoi()` returns `isNew: true` for a POI with no nearby existing POIs (regardless of name). Returns `proximityMatches` array for a POI within 50m of an existing one.

---

### Task 3: Build proximity match resolution UI

**Files to touch:** `frontend/review.html` (within `renderDetail()`, lines ~1551-1670)

**What to do:**
- After the coordinate fields and map, when `poi._conflicts.proximityMatches` is non-empty, render a **proximity match panel** showing:
  - For each candidate: existing POI name, incoming POI name, distance in meters, and map pins for both.
  - Two buttons per candidate: **"Same Place"** and **"Different Place"**.
  - Name similarity score as a helper label (e.g., "Names: 92% similar" or "Names: different").
- When editor clicks **"Same Place" (AC 4):**
  - Set `poi._conflicts.proximityResolution = 'same'` and `poi._conflicts.matchedExistingPoi = existingPoi`.
  - Auto-add incoming name to `name_variations` if different from existing name (per Q1 resolution).
  - Run beat-level conflict detection against the matched existing POI's beats (the existing logic from lines 2328-2363).
  - Re-render to show beat conflicts.
- When editor clicks **"Different Place" (AC 5):**
  - Set `poi._conflicts.proximityResolution = 'different'`.
  - Mark POI as new (no beat conflict check needed).
  - Re-render.
- For multi-match (AC 3): editor must resolve all candidates before "Mark as Complete" is enabled.
- Remove the `altNameMatch` display (line 1587) — replaced by proximity match panel.

**What NOT to touch:** Beat card rendering, beat conflict resolution UI, map initialization.

**Success check:** Proximity match panel renders when a POI has proximity matches. Clicking "Same Place" triggers beat-level conflict detection. Clicking "Different Place" marks POI as new.

---

### Task 4: Update `mapPoiForApi()` and `uploadSinglePoi()` for location-first decisions

**Files to touch:** `frontend/review.html` (lines ~2134-2148, ~2575-2656)

**What to do:**
- **`mapPoiForApi(poi)` update:** Accept an optional second parameter `options = {}`:
  - `options.useExistingName` — when editor chose "same place," the payload must use the existing POI's name (not the incoming name) so MERGE hits the correct node.
  - `options.forceCreate` — when editor chose "different place" and names collide, set `force_create: true` in the payload so the backend uses CREATE instead of MERGE.
- **`uploadSinglePoi(poiIdx)` update:**
  - Read `poi._conflicts.proximityResolution`:
    - `'same'`: Call `mapPoiForApi(poi, { useExistingName: poi._conflicts.matchedExistingPoi.properties.name })`. Also send `name_variations` including the incoming name if different.
    - `'different'`: Call `mapPoiForApi(poi, { forceCreate: true })`.
    - `null` / `isNew: true`: Call `mapPoiForApi(poi)` as today (default MERGE path — fine for genuinely new POIs).
- **Cache refresh:** After a POI is created (new or force-created), append the new POI node to `cachedPoiList` so subsequent proximity checks within the same session see it (resolves Performance audit fail).

**What NOT to touch:** Beat upload logic, conflict resolution upload logic, `executeUpload()`.

**Success check:** "Same place" uploads use the existing POI name. "Different place" with same name sends `force_create: true`. New POIs appear in `cachedPoiList` immediately after creation.

---

### Task 5: Update `markCompleteBtn` gating for proximity resolution

**Files to touch:** `frontend/review.html` (lines ~1497-1516)

**What to do:**
- Before allowing "Mark as Complete," check:
  1. If `poi._conflicts.proximityMatches` is non-empty, `proximityResolution` must be set (`'same'` or `'different'`).
  2. If `proximityResolution === 'same'`, all beat conflicts must also be resolved (existing check).
  3. If `poi._conflicts.missingCoords === true`, block with error "POI has no valid coordinates — cannot upload."
- Update the gating logic in the `markCompleteBtn` click handler (line 1507).

**What NOT to touch:** Defer logic, worklist rendering.

**Success check:** "Mark as Complete" is disabled when proximity matches are unresolved. Enabled after editor makes a decision.

---

### Task 6: Update batch `detectConflicts()` to use location-first logic

**Files to touch:** `frontend/review.html` (lines ~2170-2271)

**What to do:**
- The batch `detectConflicts()` function is used by the bulk upload flow. Update it to mirror the per-POI changes from Task 2:
  - Replace alt-name matching with proximity matching.
  - Auto-new when no proximity match.
  - Add proximity matches to the result for editor review.
- Since the batch flow collects all results upfront, proximity matches go into `result.matchedPois` with a `proximityMatch: true` flag, and the editor resolves them in the triage overlay.

**What NOT to touch:** Beat-level Jaccard similarity logic, conflict resolution overlay rendering.

**Success check:** Batch upload correctly identifies proximity matches using the same logic as per-POI detection.

---

### Task 7: Clean up dead code

**Files to touch:** `frontend/review.html`

**What to do:**
- Remove the old alt-name matching logic from both `detectConflicts()` and `detectConflictsForPoi()` (confirmed dead after Tasks 2 and 6).
- Remove the 500m coordinate warning code (lines 2318-2325 area, or wherever it exists after prior edits).
- Remove the `altNameMatch` display in `renderDetail()`.
- Verify no remaining references to the old matching approach.

**What NOT to touch:** `name_variations` data on POI nodes — the field stays; only the matching logic changes.

**Success check:** No dead alt-name matching code remains. `name_variations` is still populated on POIs (used in "same place" flow to accumulate names).

---

### Task 8: Write backend and frontend tests

**Files to touch:** `tests/test_api_endpoints.py`, `tests/test_workbench_ui.py`

**What to do:**

**Backend tests** (in `test_api_endpoints.py`):
- Test `force_create=true` creates a new POI even when name matches an existing one.
- Test `force_create=false` (default) still MERGEs on name.
- Test coordinate validation rejects `latitude=999`.
- Test coordinate validation accepts valid coordinates.
- Test that two POIs with the same name but `force_create=true` result in two distinct nodes.

**Frontend tests** (in `test_workbench_ui.py` or a new JS test if the project has a JS test runner):
- Test `findProximityMatches()` returns empty array for POI >50m from all existing.
- Test `findProximityMatches()` returns single match for POI <50m from one existing.
- Test `findProximityMatches()` returns multiple matches sorted by distance.
- Test `detectConflictsForPoi()` returns `isNew: true` for POI with same name but >50m away.
- Test `detectConflictsForPoi()` returns `missingCoords: true` for POI without coordinates.
- Test `mapPoiForApi()` with `useExistingName` sends the existing name.
- Test `mapPoiForApi()` with `forceCreate` includes `force_create: true`.
- Test cache refresh: after POI creation, new POI appears in `cachedPoiList`.

**What NOT to touch:** Existing passing tests.

**Success check:** All new tests pass. All existing tests still pass.

---

## Part B — Test Definitions

### AC 1: Auto-new when no proximity match

| | |
|---|---|
| **Test description** | Incoming POI with no existing POI within 50m is auto-classified as new |
| **Test type** | Frontend unit (JS) + integration |
| **Expected behavior** | `findProximityMatches({lat: 42.36, lng: -71.06}, cachedPoiList)` returns `[]` when nearest existing POI is 200m away → `detectConflictsForPoi()` returns `isNew: true` |
| **Edge case** | POI with identical name to existing POI but 200m away still returns `isNew: true` (AC 8) |

### AC 2: Single proximity match → editor review

| | |
|---|---|
| **Test description** | Incoming POI within 50m of exactly one existing POI shows side-by-side |
| **Test type** | Frontend integration |
| **Expected behavior** | `detectConflictsForPoi()` returns `proximityMatches` with 1 entry containing `existingPoi`, `distanceM`, both names |
| **Edge case** | Existing POI at exactly 50m boundary (edge: include at ≤50m, exclude at >50m) |

### AC 3: Multiple proximity matches → ranked display

| | |
|---|---|
| **Test description** | Incoming POI within 50m of two+ existing POIs shows all ranked by distance |
| **Test type** | Frontend integration |
| **Expected behavior** | `findProximityMatches()` returns 2+ entries sorted ascending by `distanceM` |
| **Edge case** | Three existing POIs at 10m, 30m, 51m — only two should appear |

### AC 4: "Same place" → beats flow to existing POI

| | |
|---|---|
| **Test description** | Editor confirms "same place" and beats enter existing conflict detection |
| **Test type** | Frontend integration |
| **Expected behavior** | After "Same Place" click, `poi._conflicts.proximityResolution === 'same'`, beat-level detection runs against existing POI's beats |
| **Edge case** | Existing POI has no beats — still valid "same place," beats create as new |

### AC 5: "Different place" → new POI node created

| | |
|---|---|
| **Test description** | Editor chooses "different place" and a new POI is created |
| **Test type** | Backend integration |
| **Expected behavior** | `POST /nodes/POI` with `force_create: true` and same name as existing POI → response has a different `id` than existing POI |
| **Edge case** | Same name, same coordinates, force_create=true → still creates new (explicit editor decision) |

### AC 6: "Attach to existing POI ID" → beats on correct node

| | |
|---|---|
| **Test description** | "Same place" upload uses existing POI name → MERGE hits correct node |
| **Test type** | Backend integration |
| **Expected behavior** | `POST /nodes/POI` with existing POI name → response `id` matches the existing POI's ID |
| **Edge case** | N/A |

### AC 7: Missing coordinates → error

| | |
|---|---|
| **Test description** | POI without lat/lng is flagged as error |
| **Test type** | Frontend unit + backend unit |
| **Expected behavior** | Frontend: `detectConflictsForPoi()` returns `missingCoords: true`, `errors: [...]`. Backend: `POST /nodes/POI` with `latitude=null` returns 422. |
| **Edge case** | POI with latitude but no longitude also triggers error |

### AC 8: Identical names 200m apart → two separate POIs

| | |
|---|---|
| **Test description** | Two POIs named "Old City Hall" 200m apart both auto-new |
| **Test type** | Frontend unit + backend integration |
| **Expected behavior** | `findProximityMatches()` returns `[]` for second POI → both created as separate nodes |
| **Edge case** | N/A — this is the core regression test for the name-first bug |

---

## Part C — Claude Code Prompt

```
## Slice Goal

Replace name-first POI deduplication with location-first matching (50m proximity) in the
Editorial Workbench so that POI identity is determined by physical location, not name.

## Context

Read these files before starting:
- `specs/NORTHSTAR.md` — project north star
- `specs/2026-03-15-poi-matching-fix/02-spec.md` — the approved spec (8 acceptance criteria)
- `specs/2026-03-15-poi-matching-fix/03-red-team.md` — red team review with resolved blockers
- `specs/2026-03-15-poi-matching-fix/04-plan.md` — this implementation plan (full task breakdown)

Key codebase files:
- `frontend/review.html` — the Editorial Workbench (all frontend logic in one file)
- `src/api/crud/nodes.py` — POI MERGE/CREATE logic (already has `force_create` support)
- `src/api/models/nodes.py` — POI model (already has coordinate validation and `force_create` field)
- `src/schema/definitions.py` — POINT index on POI.location confirmed
- `tests/test_api_endpoints.py` — existing backend tests

## What to Build

Execute the 8 tasks from Part A of the plan in order. Summary:

1. Add `PROXIMITY_THRESHOLD_M = 50` constant and `findProximityMatches(poi, cachedPoiList)` function.
2. Rewrite `detectConflictsForPoi()` to use location-first logic:
   - No coordinates → error (AC 7)
   - No match within 50m → auto-new, regardless of name (AC 1, AC 8)
   - Match within 50m → present for editor review with distance + name info (AC 2, AC 3)
3. Build proximity match resolution UI in `renderDetail()`:
   - Side-by-side display with names, distance, map pins
   - "Same Place" button → beats attach to existing POI (AC 4)
   - "Different Place" button → new POI created (AC 5)
   - Multi-match: resolve all before proceeding (AC 3)
   - On "Same Place": auto-add incoming name to `name_variations` if different
4. Update `mapPoiForApi()` and `uploadSinglePoi()`:
   - "Same place" → use existing POI name in payload (AC 6)
   - "Different place" → set `force_create: true` (AC 5)
   - After POI creation, append to `cachedPoiList` for session-level freshness
5. Gate "Mark as Complete" on proximity resolution being decided.
6. Update batch `detectConflicts()` with same location-first logic.
7. Remove dead alt-name matching code and 500m warning.
8. Write tests for all 8 acceptance criteria (backend + frontend).

## What NOT to Touch

- Beat-level conflict detection (Jaccard similarity, hard/soft thresholds) — unchanged
- Backend MERGE key (`name`) — unchanged (frontend controls which path is taken)
- `name_variations` field on POI nodes — keep populating it
- Existing passing tests
- Any files outside `frontend/review.html`, `tests/test_api_endpoints.py`, `tests/test_workbench_ui.py`
- `src/api/crud/nodes.py` and `src/api/models/nodes.py` already have the `force_create` and validation
  changes from the red team — do NOT modify them further

## Best Practices Checklist (must implement)

- [ ] `PROXIMITY_THRESHOLD_M` is a named constant, never a magic number
- [ ] Name similarity is display-only — it never triggers or blocks a match
- [ ] All POIs without valid coordinates are flagged as errors and excluded from upload
- [ ] "Same place" sends existing POI name → MERGE hits correct node (no silent false merge)
- [ ] "Different place" with same name sends `force_create: true` → CREATE, not MERGE
- [ ] `cachedPoiList` refreshed after each POI creation within a session
- [ ] No dead alt-name matching code remains
- [ ] 500m coordinate warning removed (superseded by 50m proximity check)

## Verification

After all tasks, run:
1. `pytest tests/ -v` — all existing and new tests pass
2. Manual verification: upload a JSON with two POIs named "Old City Hall" 200m apart → both auto-new
3. Manual verification: upload a POI within 30m of an existing one → proximity match panel appears
4. Manual verification: click "Different Place" on a same-name proximity match → new POI created

Before starting, confirm you understand the full scope and flag any conflicts with the existing
codebase or assumptions you are making.
```

---

## Part D — Best Practices Implementation Checklist

| # | Practice | Task(s) | How to Verify |
|---|----------|---------|---------------|
| 1 | Named constant for 50m threshold | Task 1 | `PROXIMITY_THRESHOLD_M = 50` exists and is used in `findProximityMatches()` — no hardcoded `50` elsewhere |
| 2 | Name similarity is display-only | Tasks 2, 3 | Name similarity is shown as a label in the proximity panel but does not appear in any `if` condition that determines match/no-match |
| 3 | Coordinate validation on incoming POIs | Task 2 | `detectConflictsForPoi()` returns error for POIs without valid lat/lng. Backend rejects out-of-range coords (already implemented in `POICreate` model). |
| 4 | "Same place" uses existing POI name | Task 4 | `uploadSinglePoi()` calls `mapPoiForApi(poi, { useExistingName: existingName })` when `proximityResolution === 'same'` |
| 5 | "Different place" uses `force_create` | Task 4 | `uploadSinglePoi()` sends `force_create: true` when `proximityResolution === 'different'` and names collide |
| 6 | Cache refresh during session | Task 4 | After `POST /nodes/POI` succeeds, new node is appended to `cachedPoiList` |
| 7 | Dead code removal | Task 7 | No references to alt-name matching logic. No 500m warning code. Grep confirms. |
| 8 | Server-side coordinate validation | Pre-done | `POICreate` model has `field_validator` for lat (-90 to 90) and lng (-180 to 180) — already implemented per B3 resolution |
| 9 | Test coverage for all 8 ACs | Task 8 | Each AC has at least one dedicated test. `pytest` passes. |

---

## North Star Final Check

- **Graph spine integrity:** This plan's primary purpose. Location-first matching prevents false merges (same name, different place) and false splits (different name, same place). POI remains the reliable anchor node.
- **Extraction philosophy:** Untouched. The miner remains permissive. Deduplication is at the editorial/database layer.
- **Editorial Workbench boundary:** All changes are in `frontend/review.html` (browser-based HTML/JS) — stays within the committed architecture.
- **No scope creep:** No automated merging, no fuzzy geocoding, no batch resolution, no backend MERGE key changes.
- **Task count:** 8 tasks — within the 12-task limit.
- **Technical debt logged:** `name` as MERGE key will need rethinking for Phase 2+ (per red team §5). Accepted for Phase 1.
