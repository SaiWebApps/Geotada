# Scope: V3 Pipeline Support in Workbench

**Date:** 2026-03-13
**North Star Phase:** Phase 1 — Build the Machine

---

## What we're building

1. **`name_variations` on POI nodes** — Store as a native Neo4j string list property on each POI. `poi_name` remains the canonical name (MERGE key). The list holds alternative/former/colloquial names used purely for matching incoming POIs to existing ones during conflict detection.

2. **Client-side alt-name conflict detection** — When the workbench checks for conflicts, match the incoming `poi_name` against both the `name` AND `name_variations` of every cached POI. If a match is found via alt name, use the existing POI's canonical name to call the existing `/graph/poi/{name}/beats` endpoint. Show a UI indicator explaining the match.

3. **`audit_notes` as array** — Update the `renderAuditNotes()` function to handle arrays of audit issue objects (V3 format) in addition to the existing string and single-object formats.

4. **New V3 field display** — Show `address`, `name_variations`, `gravity_audit`, and `_meta` in the workbench detail panel. All read-only. `gravity_audit` shows the two-signal reasoning. `_meta` is collapsible.

5. **JSON validation update** — Accept V3 keys (`address`, `alternative_names`/`name_variations`, `_meta`, `gravity_audit`) without "unknown property" errors. Continue requiring `latitude`, `longitude`, and `gravity` (user must run fact-checker before uploading).

---

## Why

Phase 1 gate requires 100+ Paris POIs live. Content is being ingested from multiple source texts (books, articles). Different sources use different names for the same POI. Without alt-name matching, the workbench will create duplicate POIs or fail silently on conflict detection. The V3 prompts also produce richer audit metadata that the workbench needs to surface for editorial review.

---

## What we're NOT building

- **API changes** — No new endpoints. The cached POI list already returns all properties; alt-name matching is client-side. The `POICreate` model and `create_node` Cypher both need minor updates to accept `name_variations`, but no new routes.
- **Prompt updates** — V3 prompts currently output `alternative_names` as flat string arrays. Updating them to match the `name_variations` naming or Sairam's `{name, is_primary}` object format is deferred as a separate quick fix.
- **POI merge/consolidation** — If two POIs already exist in the database with different names for the same place, this scope won't merge them. It only prevents future duplicates during upload.
- **Fuzzy name matching** — Matching is exact string comparison against `name` and `name_variations` entries. No Levenshtein or embedding similarity.
- **`address` geocoding in the workbench** — The workbench displays the address for human reference but does not call a geocoding API. Coordinates come from the fact-checker.

---

## What already exists

| Component | File | Relevant behavior |
|-----------|------|-------------------|
| JSON validation | [review.html:988-1021](frontend/review.html#L988-L1021) | `validateV2Schema()` — allowlisted POI keys, rejects `tags`, requires lat/lng/gravity |
| Audit notes renderer | [review.html:1108-1145](frontend/review.html#L1108-L1145) | `renderAuditNotes()` — handles string and single object formats |
| Conflict detection (bulk) | [review.html:1968-2067](frontend/review.html#L1968-L2067) | `detectConflicts()` — exact `poi_name` match against API |
| Conflict detection (per-POI) | [review.html:2071-2087](frontend/review.html#L2071-L2087) | `detectConflictsForPoi()` — exact `poi_name` match against cached list |
| POI detail panel | [review.html:1440-1660](frontend/review.html#L1440-L1660) | `renderDetail()` — editable fields for name, coords, orientation, beats |
| POI create model | [nodes.py:71-79](src/api/models/nodes.py#L71-L79) | `POICreate` — no `name_variations` field |
| POI Cypher MERGE | [crud/nodes.py:77-97](src/api/crud/nodes.py#L77-L97) | `create_node()` for POI — MERGE on name, SET loop auto-includes new props |
| Duplicate resolver | [review.html:1050-1070](frontend/review.html#L1050-L1070) | Checks for duplicate `poi_name` within uploaded file only |

---

## Dependencies or risks

- **Cached POI list size** — Currently fetched with `?limit=200`. As Paris grows past 200 POIs, name_variations matching will miss POIs beyond the limit. Not a blocker now (Phase 1 target is 100+ POIs), but needs pagination or increased limit before Phase 2 city expansion.
- **Neo4j list property indexing** — `WHERE $name IN p.name_variations` works but isn't indexed. At 100-200 POIs this is negligible. At scale, we'd need a full-text index or the separate-node approach. Acceptable for MVP.
- **Field naming mismatch** — V3 prompts output `alternative_names`, workbench/DB will use `name_variations`. The JSON upload should accept either key (normalize on ingest). The prompt quick-fix to align naming is deferred.

---

## Best practices flagged

- **Input validation** — New `name_variations` property is a list of strings from LLM output. Validate type and sanitize before storing in Neo4j.
- **XSS** — All new displayed fields (address, name_variations, gravity_audit reasoning) must go through `escHtml()` before rendering.
