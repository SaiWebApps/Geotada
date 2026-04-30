# Spec: POI Matching — Location-First Deduplication

**Date:** 2026-03-17
**Stage:** 2 — Contract Spec (Flavor B)
**Scope:** `specs/2026-03-15-poi-matching-fix/01-scope.md`
**North Star Ref:** `specs/NORTHSTAR.md`

---

## 1. Purpose

Replace the name-first POI deduplication logic with location-first matching so that POI identity in the graph is determined by physical proximity (50m), preventing false merges of distinct places with similar names and false splits of the same place with different names.

## 2. Inputs

- **Incoming POI from JSON upload:** `poi_name` (string), `latitude` (float, 6 decimal places), `longitude` (float, 6 decimal places), `beats[]`, optional `name_variations[]`
- **Existing POI list from database:** `cachedPoiList` — array of POI nodes with `properties.name`, `properties.location.lat`, `properties.location.lng`, `properties.name_variations[]`

## 3. Outputs

For each incoming POI, one of three outcomes:

- **Auto-new:** No existing POI within 50m → create as new POI node. No editor action needed.
- **Proximity match (single):** Exactly one existing POI within 50m → present side-by-side to editor for "same place" / "different place" decision.
- **Proximity match (multiple):** Two or more existing POIs within 50m → present all candidates ranked by distance. Editor must resolve all candidates before proceeding.

Editor decision flows into:

- **"Same place"** → incoming beats attach to the existing POI node (existing beat-level conflict detection continues as-is)
- **"Different place"** → new POI node created regardless of name similarity

The frontend pre-resolves POI identity and passes an explicit instruction to the API: "create new POI" or "attach beats to existing POI ID." The backend MERGE key (`name`) is unchanged; the frontend controls which path is taken.

## 4. Constraints

- 50m proximity threshold is a named constant, not a magic number
- Name similarity is displayed as a secondary signal during editor review — it never triggers or blocks a match on its own
- Beat-level conflict detection (Jaccard similarity, hard/soft thresholds) is untouched — it runs after POI matching is resolved
- Coordinate data must be present on incoming POIs; POIs without coordinates are flagged as errors
- Editor must resolve all proximity match candidates for a POI before that POI can proceed to upload

## 5. Acceptance Criteria

1. **Works when** an incoming POI has no existing POI within 50m — it is auto-classified as new with zero editor interaction, regardless of name similarity to distant POIs.
2. **Works when** an incoming POI is within 50m of exactly one existing POI — the editor sees both POIs side-by-side with names, coordinates, distance in meters, and map pins, and can choose "same place" or "different place."
3. **Works when** an incoming POI is within 50m of multiple existing POIs — all candidates are shown ranked by distance, and the editor must match to one or reject all before proceeding.
4. **Works when** the editor confirms "same place" — incoming beats flow into the existing beat-level conflict detection against that POI's existing beats.
5. **Works when** the editor chooses "different place" — a new POI node is created in the database with its own coordinates, even if the name matches an existing POI.
6. **Works when** the frontend sends "attach to existing POI ID" — beats are written to that POI node without the backend MERGE silently creating or merging a different node.
7. **Works when** an incoming POI has no latitude/longitude — it is flagged as an error in the triage view and excluded from upload.
8. **Works when** two POIs named identically are 200m apart — they are auto-classified as new (no proximity match), resulting in two separate POI nodes.

## 6. Downstream Dependencies

- **Beat-level conflict detection** consumes the POI match decision. Once a POI is matched (or created as new), the existing `beatConflicts` / `beatReviewItems` logic runs unchanged.
- **Backend API** receives explicit instructions from the frontend — "create new" or "attach to existing ID" — rather than relying on MERGE key behavior to determine POI identity.
- **Map view** in the workbench already shows POI pins — proximity matches should be visually distinguishable from auto-new POIs during triage.

## 7. Resolved Questions

1. **Multi-match resolution:** Editor must resolve all proximity candidates before proceeding. No deferring.
2. **Backend MERGE key:** Unchanged. The frontend pre-resolves POI identity and passes explicit "create new" vs "attach to existing POI ID" to the API. This keeps MERGE idempotent and avoids touching existing data.

## Best Practices Notes

- **Data integrity:** AC 5, 6, and 8 directly test that the graph spine remains correct — no silent false merges.
- **UX:** AC 2 and 3 ensure the editor has enough information (distance, map pins, names) to make an informed decision. One primary action per POI.
- **Input validation:** AC 7 ensures POIs without coordinates can't corrupt the matching logic.
- **No security/privacy concerns** for this scope — internal editorial tool, no user-facing auth or PII changes.

## North Star Alignment

The graph spine is `User → Profile → Trip → ItineraryItem → POI → NarrativeBeat → Lens`. POI is the anchor. This spec directly protects graph integrity, prerequisite for the Phase 1 gate (100+ Paris POIs live). No conflicts with architectural commitments or explicit boundaries.
