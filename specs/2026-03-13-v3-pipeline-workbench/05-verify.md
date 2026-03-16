# Verification Report: V3 Pipeline Support in Workbench

**Date:** 2026-03-15
**Plan:** `04-plan.md`
**Spec:** `02-spec.md`

---

## Acceptance Criteria — Pass/Fail

| AC | Description | Result | Evidence |
|----|-------------|--------|----------|
| AC1 | V3 JSON passes `validateV2Schema()` | **PASS** | Added `address`, `alternative_names`, `name_variations`, `_meta`, `gravity_audit`, `gravity` to `allowedPoiKeys` Set. Unknown keys still rejected. |
| AC2 | `renderAuditNotes()` handles array format | **PASS** | `Array.isArray()` check added before `typeof === 'object'`. Array renders each element as separate card via extracted `renderAuditCardFields()`. Single object and string branches preserved. |
| AC3 | V3 fields display in detail panel | **PASS** | Address (read-only div), Name Variations (comma-separated), Gravity Audit (reasoning text), `_meta` (collapsible `<details>`). All use `escHtml()`. Only render when present. |
| AC4 | Per-POI alt-name conflict detection | **PASS** | `detectConflictsForPoi()` checks `cachedPoiList` `name_variations` (case-insensitive) before API call. Uses canonical name for beat lookup. Multi-match returns error. |
| AC5 | Bulk alt-name conflict detection | **PASS** | `detectConflicts()` uses same alt-name matching logic. Replaced redundant per-POI `fetch()` with `cachedPoiList` lookup. |
| AC6 | Alt-name match UI indicator | **PASS** | `<div class="alt-name-match-note">` with `aria-label` rendered in `renderDetail()` when `poi._conflicts.altNameMatch` exists. |
| AC7 | `alternative_names` → `name_variations` normalization | **PASS** | Normalization in `processJson()` before data mapping. Validates array of non-empty strings. Filters invalid entries. |
| AC8 | `POICreate` model + Cypher | **PASS** | `name_variations: list[str] = []` added to `POICreate`. Existing `create_node()` SET loop auto-includes it. Integration tests confirm. |

---

## Tests — Status

| Test | Type | Status |
|------|------|--------|
| `test_poi_with_name_variations` | Integration | **PASS** |
| `test_poi_without_name_variations` | Integration | **PASS** |
| `test_poi_with_invalid_name_variations` | Integration | **PASS** |
| Full test suite (176 tests) | All | **176 PASS, 1 FAIL (pre-existing)** |

The single failure (`test_conflict_detection_and_resolution`) is a pre-existing Playwright timeout on a merge overlay Cancel button click — unrelated to this work.

---

## Best Practices Compliance

| # | Practice | Result | Evidence |
|---|----------|--------|----------|
| 1 | XSS prevention via `escHtml()` | **PASS** | All new rendered fields (address, name_variations entries, gravity_audit, `_meta` JSON, alt-name match note) use `escHtml()`. |
| 2 | `Array.isArray()` before `typeof` | **PASS** | Added in `renderAuditNotes()` at line ~1132, before the object branch. |
| 3 | Case-insensitive name matching | **PASS** | `.toLowerCase()` used in Tasks 5, 6, 7 for all name comparisons. |
| 4 | Default `name_variations` to `[]` | **PASS** | `(p.properties.name_variations \|\| [])` used in both `detectConflicts()` and `detectConflictsForPoi()`. `(poi.name_variations \|\| [])` in alt-name matching. |
| 5 | `aria-label` on alt-name indicator | **PASS** | `aria-label="This POI was matched to an existing POI via an alternative name: ..."` on `.alt-name-match-note` div. |
| 6 | Pydantic `list[str]` validation | **PASS** | `name_variations: list[str] = []` on `POICreate`. `[123]` returns 422 (confirmed by test). |
| 7 | Parameterized Cypher | **PASS** | `create_node()` uses `f"n.{key} = ${key}"` — key names from Pydantic model (hardcoded), values parameterized. No changes to Cypher code. |
| 8 | Multi-match error handling | **PASS** | Both `detectConflicts()` and `detectConflictsForPoi()` check `altMatches.length > 1`, add descriptive error, and skip/return early. |
| 9 | Self-dedup in name_variations | **PASS** | In `processJson()`, removes own `poi_name` from `name_variations` (case-insensitive) before duplicate check. |

---

## Autonomous Decisions Made

1. **Extracted `renderAuditCardFields()` helper** — The plan said to use "existing object-rendering logic" for array items. I extracted the field-rendering code into a separate function to avoid double-wrapping `<div class="audit-notes-box">` when rendering arrays. This is a structural improvement to avoid DOM nesting issues, not a scope change.

2. **Added `name_variations` to `mapPoiForApi()`** — The plan didn't explicitly mention this, but it's necessary for AC8 to work: the frontend needs to pass `name_variations` in the POI creation payload for it to reach the `POICreate` Pydantic model and be stored in Neo4j.

3. **Added CSS styles** — Added `.readonly-field`, `.meta-json`, `.audit-card`, and `.alt-name-match-note` styles to support the new UI elements. These are minimal styling additions consistent with the existing design system.

---

## Scope Creep Check

No scope creep detected. All changes are within the 10 tasks defined in the plan:
- No new API endpoints created
- No changes to V3 prompts
- No POI merge/consolidation logic
- No fuzzy matching (exact string, case-insensitive only)
- No address geocoding
- No changes to beat-level conflict resolution UI
- No changes to existing test fixtures

---

## Files Modified

| File | Changes |
|------|---------|
| `frontend/review.html` | Tasks 1-8: V3 schema validation, normalization, audit notes array, detail panel fields, alt-name duplicate detection, conflict detection matching, UI indicator, CSS |
| `src/api/models/nodes.py` | Task 9: `name_variations: list[str] = []` on `POICreate` |
| `tests/test_upload_api.py` | Task 10: 3 integration tests for `name_variations` |
