# Implementation Plan: V3 Pipeline Support in Workbench

**Date:** 2026-03-15
**Spec:** `02-spec.md` | **Red Team:** `03-red-team.md`
**North Star Phase:** Phase 1 — Build the Machine

---

## Part A — Task Breakdown

### Task 1: Normalize `alternative_names` in `processJson()`

**Files to touch:** `frontend/review.html` — `processJson()` (~line 1023)

**What to do:**
- After the required-field validation loop (line 1040) and before the `data = raw.map(...)` spread (line 1042), add normalization:
  - If `entry.alternative_names` exists and `entry.name_variations` does not, copy `entry.alternative_names` to `entry.name_variations` and delete `entry.alternative_names`
  - Validate that `name_variations` (if present) is an array of strings. Filter out any non-string or empty-string entries. If the result is empty, delete the key.
- This must happen **before** the duplicate check at line 1050.

**What NOT to touch:** Don't change the duplicate-checking logic itself (that's Task 5). Don't change the `_status` attachment or beat filtering.

**Success check:** Paste V3 JSON with `alternative_names: ["Old Name", "Former Name"]`. After `processJson()`, the POI object in `poiData` has `name_variations: ["Old Name", "Former Name"]` and no `alternative_names` key.

---

### Task 2: Update `validateV2Schema()` to accept V3 keys

**Files to touch:** `frontend/review.html` — `validateV2Schema()` (~line 988)

**What to do:**
- Add V3 keys to the `allowedPoiKeys` Set at line 991: `'address'`, `'alternative_names'`, `'name_variations'`, `'_meta'`, `'gravity_audit'`, `'gravity'`
- `gravity` at POI level is output by V3 prompts — add to allowlist without additional validation (fact-checker handles upstream)

**What NOT to touch:** Beat-level validation. Required field checks. The `tags` rejection logic.

**Success check:** V3 JSON with `address`, `alternative_names`, `gravity_audit`, `_meta`, and POI-level `gravity` passes validation. JSON with truly unknown keys (e.g., `"foo"`) still fails.

---

### Task 3: Update `renderAuditNotes()` for array format

**Files to touch:** `frontend/review.html` — `renderAuditNotes()` (~line 1108)

**What to do:**
- Add an `Array.isArray(notes)` check **before** the `typeof notes === 'object'` check (R3 from red team — JS gotcha where `typeof []` is `'object'`)
- When notes is an array, iterate and render each element as its own audit card using the existing object-rendering logic
- Wrap array output in a container: `<div class="audit-notes-box"><span class="audit-heading">Audit Notes</span>{cards}</div>`
- Each card must use `escHtml()` on all rendered fields

**What NOT to touch:** The string branch. The single-object branch (it still works for V2).

**Success check:**
- Array of 3 audit issue objects → renders 3 separate cards with issue, current_text, suggested_fix, source, confidence
- Single object (V2) → still renders as before
- String → still renders as before
- Empty array → returns empty string

---

### Task 4: Add V3 fields to detail panel (`renderDetail()`)

**Files to touch:** `frontend/review.html` — `renderDetail()` (~line 1460)

**What to do:**
- After the Orientation field (line 1471) and before `renderAuditNotes(poi.audit_notes)` (line 1473), add four read-only sections:
  1. **Address** — read-only text field. Only render if `poi.address` exists. Use `escHtml()`.
  2. **Name Variations** — comma-separated read-only display. Only render if `poi.name_variations` exists and has length > 0. Use `escHtml()` on each entry.
  3. **Gravity Audit** — read-only text showing the two-signal reasoning. Only render if `poi.gravity_audit` exists. Use `escHtml()`. If it's an object, render `poi.gravity_audit.reasoning` or JSON.stringify as fallback.
  4. **`_meta`** — collapsible `<details><summary>Pipeline Metadata</summary><pre>{formatted JSON}</pre></details>`. Only render if `poi._meta` exists. Use `escHtml()` on the JSON string.
- All fields read-only (no `data-field` attribute, use `<div>` not `<input>`).
- `_meta` `<details>` element is natively accessible — no extra aria attributes needed.

**What NOT to touch:** The editable fields (poi_name, short_description, orientation, lat/lng). The beat rendering section. The map initialization.

**Success check:** V3 POI with all four fields shows Address, Name Variations, Gravity Audit, and collapsible _meta. V2 POI without these fields shows no empty sections.

---

### Task 5: Within-file alt-name duplicate detection in `processJson()`

**Files to touch:** `frontend/review.html` — `processJson()` (~line 1050)

**What to do:**
- After the existing `nameCount` duplicate check (line 1050-1063), add a second check:
  - For each pair of POIs in the file: if POI A's `poi_name` (case-insensitive) appears in POI B's `name_variations`, or POI B's `poi_name` appears in POI A's `name_variations`, flag as a likely duplicate
  - Add flagged pairs to the existing `dupes` array format or show a warning via `showError()` listing the pairs
- Also deduplicate self-references: if a POI's `poi_name` appears in its own `name_variations`, silently remove it (Edge Case 4)

**What NOT to touch:** The existing exact-name duplicate logic. The `showDuplicateResolver()` UI.

**Success check:**
- File with POI "Christ Church" having `name_variations: ["Old North Church"]` and POI "Old North Church" → flagged as duplicate
- POI with its own name in `name_variations` → silently removed, no self-conflict

---

### Task 6: Alt-name matching in `detectConflictsForPoi()` (per-POI)

**Files to touch:** `frontend/review.html` — `detectConflictsForPoi()` (~line 2071)

**What to do:**
- Before the API call at line 2077, check `cachedPoiList` for an alt-name match:
  - Search `cachedPoiList` for any POI where `(p.properties.name_variations || [])` contains the incoming `poi.poi_name` (case-insensitive via `.toLowerCase()`)
  - Also check existing `p.properties.name` against incoming `poi.name_variations` (if present), case-insensitive
  - If a match is found, use the matched POI's **canonical name** (`p.properties.name`) for the API call instead of `poi.poi_name`
  - Store the match info (matched alt name, canonical name) on the result for UI display
- If multiple cached POIs match, add a descriptive error to `result.errors` and return early (Edge Case 3, R2)
- The existing exact-name match via `cachedPoiList.find(p => p.properties.name === poi.poi_name)` at line 2083 should remain as a fallback

**What NOT to touch:** The beat-level conflict detection logic (lines 2108-2143). The coordinate mismatch check.

**Success check:** Upload a POI named "Old North Church" when the DB has a POI "Christ Church in the City of Boston" with `name_variations: ["Old North Church"]`. The per-POI detector finds the match, calls the API with "Christ Church in the City of Boston", and returns conflict/review results.

---

### Task 7: Alt-name matching in `detectConflicts()` (bulk)

**Files to touch:** `frontend/review.html` — `detectConflicts()` (~line 1968)

**What to do:**
- **Architecture change (B1 from red team):** Before the API call at line 1978, check `cachedPoiList` for an alt-name match (same logic as Task 6):
  - Search for `poi.poi_name` in cached POIs' `name` and `name_variations` (case-insensitive)
  - Search for cached POIs' `name` in incoming `poi.name_variations` (case-insensitive)
  - If match found, use canonical name for the API call
  - If multiple matches, add error and `continue`
- Replace the re-fetch of POI list at line 1984 (`fetch(${API_BASE}/nodes/POI?limit=200)`) with a lookup against `cachedPoiList` (already fetched at startup). This eliminates redundant API calls per-POI.
- Store alt-name match info on the POI entry for UI display

**What NOT to touch:** The beat-level conflict logic (hard match, soft match, review). The 12-beat cap check.

**Success check:** Bulk upload of 3 POIs where one matches via alt name. That POI is classified as "matched" (not "new") and its beats go through conflict detection against the correct existing POI.

---

### Task 8: Alt-name match UI indicator

**Files to touch:** `frontend/review.html` — `renderDetail()` and/or worklist rendering

**What to do:**
- When a POI was matched via alt name (data stored in Tasks 6/7), display a visible indicator in the detail panel, e.g.:
  ```html
  <div class="alt-name-match-note" aria-label="This POI was matched to an existing POI via an alternative name">
    Matched via alt name "Old North Church" → existing POI "Christ Church in the City of Boston"
  </div>
  ```
- Include `aria-label` for screen reader accessibility (red team checklist item #8)
- Style with a distinctive background (info blue or similar) so it's clearly visible

**What NOT to touch:** The conflict resolution UI. The beat conflict badges.

**Success check:** After conflict detection via alt name, the detail panel shows the match indicator with both the alt name and canonical name. Screen reader announces the explanation.

---

### Task 9: Add `name_variations` to `POICreate` Pydantic model

**Files to touch:** `src/api/models/nodes.py` — `POICreate` class (~line 71)

**What to do:**
- Add field: `name_variations: list[str] = []`
- The existing `create_node()` Cypher at `src/api/crud/nodes.py:89-91` auto-includes new properties via the `for key in params` loop. `name_variations` is not in the excluded keys (`lat`, `lng`, `name`), so it will be SET automatically. Neo4j driver maps Python lists to Neo4j list properties via parameterization. **No Cypher changes needed.**

**What NOT to touch:** Other models. The `create_node()` function. The MERGE logic.

**Success check:**
- `POST /nodes/POI` with `name_variations: ["Alt 1", "Alt 2"]` → POI created with `name_variations` list property in Neo4j
- `POST /nodes/POI` without `name_variations` → defaults to empty list, no error
- `POST /nodes/POI` with `name_variations: [123]` → 422 validation error

---

### Task 10: Integration test for `name_variations` on POI creation

**Files to touch:** `tests/test_upload_api.py`

**What to do:**
- Add a test that creates a POI with `name_variations: ["Alt Name 1", "Alt Name 2"]` via the API and verifies:
  - 200/201 response
  - The returned node properties include `name_variations` as a list
  - A second GET confirms the property persisted
- Add a test that creates a POI without `name_variations` and confirms it defaults to `[]` or is absent (acceptable either way)

**What NOT to touch:** Existing tests. Don't change the test fixtures.

**Success check:** `pytest tests/test_upload_api.py` passes with the new tests.

---

## Part B — Test Definitions

### AC1 — V3 schema validation
| | |
|---|---|
| **Test type** | Manual verification (browser) |
| **Input** | JSON array with one POI containing `address`, `alternative_names`, `gravity_audit`, `_meta`, and POI-level `gravity` |
| **Expected** | `validateV2Schema()` returns empty errors array. Adding `"unknown_key": "value"` produces error. |
| **Edge cases** | Mixed V2/V3 batch (EC1) — V2 POI without V3 keys also passes |

### AC2 — `renderAuditNotes()` array handling
| | |
|---|---|
| **Test type** | Manual verification (browser) |
| **Input** | Beat with `audit_notes: [{issue: "X", current_text: "Y", suggested_fix: "Z", source: "W", confidence: "HIGH"}, {issue: "A", ...}]` |
| **Expected** | Two separate audit cards rendered, each with all 5 fields. Confidence badge colored correctly. |
| **Edge cases** | Single object (V2) still works (EC5). Empty array → no output. |

### AC3 — V3 field display in detail panel
| | |
|---|---|
| **Test type** | Manual verification (browser) |
| **Input** | POI with `address: "123 Main <script>alert('xss')</script>"`, `name_variations: ["Alt 1", "Alt 2"]`, `gravity_audit: {reasoning: "High reach..."}`, `_meta: {source: "book.pdf"}` |
| **Expected** | All four fields render. HTML in address is escaped (shows literal `<script>` text). `_meta` is collapsed by default. |
| **Edge cases** | POI without V3 fields → no empty sections shown |

### AC4 — Per-POI alt-name conflict detection
| | |
|---|---|
| **Test type** | Manual verification (browser with seeded DB) |
| **Input** | DB has POI "Christ Church" with `name_variations: ["Old North Church"]`. Upload POI named "Old North Church". |
| **Expected** | `detectConflictsForPoi()` returns `isNew: false`, uses "Christ Church" for beat comparison. |
| **Edge cases** | EC3: incoming name matches `name_variations` on 2 different existing POIs → error, POI skipped |

### AC5 — Bulk alt-name conflict detection
| | |
|---|---|
| **Test type** | Manual verification (browser with seeded DB) |
| **Input** | Same DB setup as AC4. Bulk upload 3 POIs: "Old North Church", "New POI", "Another New". |
| **Expected** | "Old North Church" classified as matched (not new). Other two classified as new. |
| **Edge cases** | Same as AC4 |

### AC6 — Alt-name match UI indicator
| | |
|---|---|
| **Test type** | Manual verification (browser) |
| **Input** | POI matched via alt name (from AC4/AC5) |
| **Expected** | Detail panel shows: `Matched via alt name "Old North Church" → existing POI "Christ Church"`. Element has `aria-label`. |

### AC7 — `alternative_names` → `name_variations` normalization
| | |
|---|---|
| **Test type** | Manual verification (browser console) |
| **Input** | JSON with `alternative_names: ["A", "B"]` and no `name_variations` |
| **Expected** | After `processJson()`, POI in `poiData` has `name_variations: ["A", "B"]`, no `alternative_names` key |

### AC8 — `POICreate` model + Cypher
| | |
|---|---|
| **Test type** | Integration test (pytest) |
| **Input** | `POST /nodes/POI` with `name_variations: ["Alt 1", "Alt 2"]` |
| **Expected** | 200 response. Node in Neo4j has `name_variations` list property. |
| **Edge cases** | Missing field → defaults to `[]`. Non-string items → 422. |

---

## Part C — Claude Code Prompt

```
## Slice Goal

Add V3 pipeline support to the Editorial Workbench: accept V3 JSON fields (address,
alternative_names, gravity_audit, _meta), match incoming POIs against existing POIs
by alternative names, surface V3 metadata for editorial review, and store
name_variations on POI nodes.

## Context

Read these files before starting:
- specs/NORTHSTAR.md (project north star)
- specs/2026-03-13-v3-pipeline-workbench/02-spec.md (behavior spec with 8 ACs)
- specs/2026-03-13-v3-pipeline-workbench/03-red-team.md (red team with resolutions)
- specs/2026-03-13-v3-pipeline-workbench/04-plan.md (this plan — task breakdown + tests)
- frontend/review.html (workbench — all JS changes go here)
- src/api/models/nodes.py (Pydantic models)
- src/api/crud/nodes.py (Cypher CRUD)

## Tasks (execute in order)

### Task 1: Normalize `alternative_names` in `processJson()`
In `processJson()` (~line 1023 of review.html), after the required-field validation
loop and before the `data = raw.map(...)` spread:
- If `entry.alternative_names` exists and `entry.name_variations` does not, copy
  to `entry.name_variations` and delete `entry.alternative_names`
- Validate `name_variations` is array of non-empty strings; filter invalid entries
- Also deduplicate: if poi_name appears in its own name_variations, remove it

### Task 2: Update `validateV2Schema()` to accept V3 keys
Add to `allowedPoiKeys` Set (~line 991): 'address', 'alternative_names',
'name_variations', '_meta', 'gravity_audit', 'gravity'

### Task 3: Update `renderAuditNotes()` for array format
At ~line 1108, add `Array.isArray(notes)` check BEFORE `typeof notes === 'object'`
(JS gotcha: typeof [] === 'object'). When array, iterate and render each element as
its own audit card using the existing object-rendering logic. All fields escHtml'd.

### Task 4: Add V3 fields to detail panel
In `renderDetail()` after the Orientation field (~line 1471), add read-only sections:
1. Address (text div, only if present)
2. Name Variations (comma-separated, only if array has items)
3. Gravity Audit (two-signal reasoning text, only if present)
4. _meta (collapsible <details><summary> with <pre> formatted JSON, only if present)
All values must use escHtml(). No data-field attributes (read-only).

### Task 5: Within-file alt-name duplicate detection
In `processJson()` after the nameCount duplicate check (~line 1050):
- Self-dedup: remove poi_name from own name_variations (case-insensitive)
- Cross-check: if POI A's poi_name (lowercased) is in POI B's name_variations
  (lowercased), or vice versa, flag as likely duplicate
- Use existing showDuplicateResolver or showError pattern for flagged pairs

### Task 6: Alt-name matching in `detectConflictsForPoi()` (per-POI)
Before the API call at ~line 2077:
- Search cachedPoiList: check if incoming poi.poi_name (lowercased) matches any
  cached POI's name_variations entries (lowercased), OR if incoming poi.name_variations
  entries match any cached POI's name (lowercased)
- Default missing name_variations to [] on cached POIs: (p.properties.name_variations || [])
- If ONE match: use canonical name for API call, store match info on result
- If MULTIPLE matches: add descriptive error, return early
- Keep existing exact-name match as fallback

### Task 7: Alt-name matching in `detectConflicts()` (bulk)
Same logic as Task 6 but in the bulk flow at ~line 1968:
- Check cachedPoiList BEFORE the API call at line 1978
- Replace the redundant per-POI re-fetch at line 1984 with cachedPoiList lookup
- If alt-name match found, use canonical name for API call
- Store match info for UI

### Task 8: Alt-name match UI indicator
In renderDetail(), when POI has alt-name match info (stored by Tasks 6/7), show:
<div class="alt-name-match-note" aria-label="Matched via alternative name: [alt] maps to existing POI [canonical]">
  Matched via alt name "[alt]" → existing POI "[canonical]"
</div>
Style distinctively (info blue background). Include aria-label for accessibility.

### Task 9: Add `name_variations` to POICreate Pydantic model
In src/api/models/nodes.py, add to POICreate class:
  name_variations: list[str] = []
No changes needed to create_node() — the Cypher SET loop auto-includes new fields.

### Task 10: Integration test
In tests/test_upload_api.py, add:
- Test: create POI with name_variations → verify property persists in response
- Test: create POI without name_variations → verify defaults without error
- Test: create POI with invalid name_variations (e.g., [123]) → verify 422

## What NOT to touch
- No new API endpoints
- No changes to the V3 prompts (naming alignment deferred)
- No POI merge/consolidation logic
- No fuzzy matching (exact string only, case-insensitive)
- No address geocoding
- No changes to beat-level conflict resolution UI
- No changes to existing test fixtures

## Best Practices Checklist (MUST implement)
1. escHtml() on ALL new rendered fields (address, name_variations entries,
   gravity_audit text, _meta JSON, alt-name match note text)
2. Array.isArray() before typeof === 'object' in renderAuditNotes
3. Case-insensitive comparison (.toLowerCase()) for all name matching
4. Default missing name_variations to [] — never assume the property exists
5. aria-label on alt-name match indicator for screen reader accessibility
6. Pydantic list[str] validation — rejects non-string items with 422
7. Parameterized Cypher queries — no string interpolation of user values
   (already handled by existing create_node pattern)

## Verification
After all tasks, verify:
- V3 JSON uploads without validation errors
- V3 fields visible in detail panel (address, name variations, gravity audit, _meta)
- audit_notes array renders as separate cards
- Alt-name matching works in both per-POI and bulk flows
- Alt-name match indicator visible with aria-label
- Within-file alt-name duplicates detected
- name_variations persists on POI nodes in Neo4j
- All existing tests still pass: pytest tests/
- No XSS: paste <script>alert(1)</script> in address field, verify it's escaped

Before starting, confirm you understand the full scope and flag any conflicts with
the existing codebase or assumptions you are making.
```

---

## Part D — Best Practices Implementation Checklist

| # | Practice | Task(s) | How to verify |
|---|----------|---------|---------------|
| 1 | XSS prevention via `escHtml()` on all new rendered fields | Tasks 3, 4, 8 | Paste `<script>alert(1)</script>` in address, name_variations, gravity_audit, _meta, and audit_notes array. Verify literal text rendered, no script execution. |
| 2 | `Array.isArray()` before `typeof` check | Task 3 | Pass `audit_notes: [{issue:"test"}]` — renders as card. Pass `audit_notes: {issue:"test"}` — still renders as card (object branch). |
| 3 | Case-insensitive name matching | Tasks 5, 6, 7 | Upload "old north church" when DB has "Old North Church" in name_variations. Verify match found. |
| 4 | Default `name_variations` to `[]` | Tasks 5, 6, 7 | Upload against DB with POIs that have no `name_variations` property. No errors thrown. |
| 5 | Accessibility: `aria-label` on alt-name indicator | Task 8 | Inspect DOM element — `aria-label` present with descriptive text. |
| 6 | Pydantic `list[str]` type validation | Task 9 | POST with `name_variations: [123]` → 422. POST with `name_variations: ["valid"]` → 200. |
| 7 | Parameterized Cypher (no user-value interpolation) | Task 9 | Code review: `create_node()` uses `${key}` parameterization for values. Key names from Pydantic model (hardcoded). |
| 8 | Multi-match error handling | Tasks 6, 7 | If incoming name matches name_variations on 2+ cached POIs → descriptive error, POI skipped. |
| 9 | Self-dedup in name_variations | Task 5 | POI with own name in name_variations → silently removed, no self-conflict. |

---

## North Star Final Check

- **Phase 1 alignment:** Directly supports 100+ Boston POIs gate by preventing duplicates from multi-source ingestion. ✓
- **Editorial Workbench commitment:** All changes are browser-side JS + one Pydantic field. No new endpoints, no pipeline automation. ✓
- **Extraction philosophy:** Matching at the workbench layer (UI/matching concern), not extraction constraint. ✓
- **Schema addition:** `name_variations` is a new graph property. After implementation, update the Schema v3 doc pointer and the Active Build Target section in NORTHSTAR.md.
- **Task count:** 10 tasks. Under the 12-task limit. ✓
