# Spec: V3 Pipeline Support in Workbench

**Date:** 2026-03-13
**Flavor:** A — Behavior Spec
**North Star Phase:** Phase 1 — Build the Machine

---

## Slice Goal

An **editor** can upload V3 pipeline JSON (with `address`, `alternative_names`, `gravity_audit`, `_meta`) and have the workbench **match incoming POIs against existing POIs by alt names**, surface the richer V3 metadata for review, and store `name_variations` on POI nodes — so that duplicate POIs from different source texts are caught before they reach the database.

---

## Walkthrough

1. Editor pastes V3 JSON containing POIs with `alternative_names`, `address`, `gravity_audit`, and `_meta` fields. The workbench accepts it without validation errors.
2. In the detail panel, the editor sees read-only sections for **Address**, **Name Variations** (from `alternative_names`), **Gravity Audit** (showing two-signal reasoning), and a collapsible **_meta** block.
3. `audit_notes` on beats renders correctly whether it's a string, single object, or an **array of audit issue objects** (V3 format) — each issue rendered as its own card.
4. Editor clicks "Upload All" (or per-POI upload). The conflict detector checks each incoming `poi_name` against cached POIs' `name` **and** `name_variations` lists. A match via alt name triggers conflict detection using the existing POI's canonical name.
5. When a match is found via alt name, the editor sees a UI indicator (e.g., badge or note) explaining: *"Matched via alt name 'X' → existing POI 'Y'"*.
6. POIs uploaded to Neo4j include `name_variations` as a string list property. The `POICreate` model accepts the field and the Cypher MERGE/SET writes it.
7. If a POI in the JSON uses `alternative_names` (V3 prompt key), the workbench normalizes it to `name_variations` transparently.

---

## Acceptance Criteria

1. **Works when** V3 JSON with `address`, `alternative_names`, `gravity_audit`, and `_meta` fields passes `validateV2Schema()` without "unknown property" errors, while still rejecting truly unknown keys.
2. **Works when** `renderAuditNotes()` receives an array of audit issue objects and renders each as a separate audit card with issue, current_text, suggested_fix, source, and confidence fields.
3. **Works when** the detail panel displays `address` as a read-only text field, `name_variations` as a comma-separated read-only list, `gravity_audit` showing the two-signal reasoning text, and `_meta` in a collapsible section — all HTML-escaped via `escHtml()`.
4. **Works when** `detectConflictsForPoi()` finds an existing POI whose `name_variations` array contains the incoming `poi_name`, and returns it as a match (not "new") with conflict/review results using the existing POI's canonical name.
5. **Works when** `detectConflicts()` (bulk) also matches incoming POIs against cached POIs' `name_variations`, following the same logic as per-POI detection.
6. **Works when** the conflict detection UI shows a visible indicator explaining that the match was found via an alternative name (e.g., *"Matched via alt name 'Eiffel Tower' → 'Tour Eiffel'"*).
7. **Works when** V3 JSON using the key `alternative_names` is normalized to `name_variations` during `processJson()`, so downstream code only deals with one key name.
8. **Works when** the `POICreate` Pydantic model accepts an optional `name_variations: list[str]` field, and the `create_node()` Cypher writes it as a Neo4j list property on the POI node.

---

## Edge Cases

1. **Mixed V2/V3 batch** — JSON array contains some POIs with V3 fields and some without. Validation passes for both; V3 fields display only when present.
2. **Empty `alternative_names`** — POI has `"alternative_names": []`. No alt-name matching occurs; `name_variations` stored as empty list or omitted.
3. **Alt-name matches multiple existing POIs** — Incoming `poi_name` matches `name_variations` on more than one existing POI. Flag as an error to the editor rather than silently picking one.
4. **Incoming `poi_name` matches its own `alternative_names`** — The canonical name is in the alt names list. Deduplicate silently; don't self-conflict.
5. **`audit_notes` is a single object (V2) in a mixed batch** — Continues rendering as before; array handling doesn't break the existing single-object path.

---

## Open Questions (resolved)

1. **`name_variations` editability** — Read-only for this slice. Editing deferred to a follow-up.
2. **`_meta` display format** — Render as formatted JSON in a `<pre>` block inside a collapsible `<details>`/`<summary>`, with `escHtml()`.

---

## Best Practices Check

| Domain | Coverage |
|--------|----------|
| **Security / XSS** | AC3 explicitly requires `escHtml()` on all new rendered fields. Covered. |
| **Input Validation** | AC1 covers validation schema update. AC8 covers Pydantic model validation for `name_variations` type. Entries validated as non-empty strings. |
| **Privacy** | No new PII fields. `address` and `name_variations` are POI metadata, not user data. N/A. |
| **Performance** | Alt-name matching is O(POIs × alt names) on cached list. At 100-200 POIs this is negligible. Flagged in scope as Phase 2 concern. |
| **Accessibility** | Collapsible `_meta` uses semantic `<details>`/`<summary>`. Audit notes array cards individually navigable by screen reader. |
