# Scope — Persistent Map & Manual POI Merge

**Date:** 2026-03-19
**Status:** Approved

---

## What we're building

- **Persistent map panel:** Restructure the workbench layout to top (map, always visible) + bottom (list + detail). The map shows all POIs within the existing 50km geofence from the database, plus incoming JSON POIs in a distinct color — so the editor can see what already exists before and during upload.
- **Two-way map ↔ list selection:** Clicking a marker on the map selects that POI in the list and loads its detail. Clicking a POI in the list pans/zooms the map to it. Incoming (upload) POIs are visually distinct from database POIs at all times.
- **Manual POI merge (both directions):** During upload, the editor can manually search for and pick an existing database POI to match with (beyond the automatic 50m proximity match). Post-upload, the editor can select two database POIs and merge them — combining beats onto the surviving POI using the existing conflict resolution UI (replace/skip/merge/change-lens).

## Why

Phase 1 gate requires 100+ Boston POIs live with reliable deduplication. The editor currently has no way to visually confirm what's in the database, verify matching is working, or fix duplicates after the fact — making it impractical to populate the system with confidence.

## What we're NOT building

- Map marker clustering (deferred — will revisit if performance degrades at scale)
- Filtering/search on the map (e.g., by lens, gravity, status)
- Bulk merge operations (merge is one pair at a time)
- New API endpoints for spatial queries (use existing `GET /nodes/POI` with client-side filtering)
- Any changes to the matching algorithm itself (50m proximity + name similarity stays as-is)

## What already exists

- **Leaflet map** in `frontend/review.html` — per-POI only, initialized by `initMap()` (~line 2008). Uses OpenStreetMap tiles, draggable blue marker, address geocoding marker.
- **`cachedPoiList[]`** — already fetches all database POIs via paginated API calls in `fetchLensesAndPoiList()` (~line 2188). Currently used only for proximity matching.
- **Proximity matching** — `findProximityMatches()` (~line 902) with 50m Haversine + `nameSimilarity()` Jaccard (~line 920).
- **Beat conflict resolution UI** — `showConflictOverlay()` (~line 2458) with replace/skip/merge/change-lens. This will be reused for merge conflicts.
- **Geofence** — `cityCentre` + `GEOFENCE_KM = 50` already defined (~line 850).

## Dependencies or risks

- **Performance:** Hundreds of Leaflet markers without clustering could cause sluggish rendering on lower-end machines. Mitigation: simple circle markers (not icon markers) are much lighter; defer clustering.
- **Layout complexity:** Moving from a two-panel to a map-on-top layout is a significant CSS restructure of a 3200-line single-file app. Risk of breaking existing functionality.
- **Merge edge cases:** Merging two POIs that both have beats on the same lens requires the full conflict resolution flow. The existing UI handles this for upload, but wiring it for arbitrary database POI pairs is new work.

## Best practices flag

This scope touches **UX** (layout restructure, two-way interaction) and **data integrity** (merge operations that modify graph relationships). Stage 3 should audit merge operations against the Neo4j schema to ensure relationship integrity (HAS_BEAT, TAGGED_WITH, LOCATED_IN edges all transfer correctly).
