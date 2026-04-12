# Spec — Persistent Map & Manual POI Merge

**Date:** 2026-03-19
**Status:** Pending approval
**Flavor:** A — Behavior Spec
**Scope:** `specs/2026-03-19-persistent-map-merge/01-scope.md`

---

## Slice Goal

An **editor** can **see all database and incoming POIs on a persistent map, select them interactively, and manually merge duplicate POIs** so that **Boston's 100+ POIs can be populated with confidence in deduplication**.

---

## Walkthrough

1. **Editor opens the workbench.** The page loads with a top-bottom layout: a persistent Leaflet map in the upper panel and the worklist + detail area in the lower panel. The map shows the geofence circle and all existing database POIs as **grey circle markers** (loaded from `cachedPoiList`).

2. **Editor loads a JSON file.** Incoming POIs appear on the map as **amber circle markers**, visually distinct from the grey database POIs. The worklist populates in the lower panel as before.

3. **Editor clicks a map marker.** If it's an incoming POI, the corresponding entry is selected in the worklist and its detail panel loads. If it's a database POI, a compact popup shows the POI name, coordinates, and beat count.

4. **Editor clicks a worklist entry.** The map pans and zooms to center on that POI's marker with a brief highlight (marker pulse or size bump). The detail panel loads as normal.

5. **Editor manually matches an incoming POI to a database POI during upload.** In the detail panel, the editor clicks "Match to existing POI..." A searchable dropdown lists database POIs sorted by proximity. The editor selects one. The incoming POI links to that database POI — beats upload to the matched POI instead of creating a new one, running through the existing conflict resolution flow.

6. **Editor merges two database POIs post-upload.** The editor clicks a database POI marker on the map. The popup includes a "Merge into this POI..." button. Clicking it highlights the target POI and prompts the editor to click a second (source) database POI on the map. A merge preview shows both POIs' beats side by side. The editor confirms, and beats from the source POI transfer to the target using the existing conflict resolution UI (replace/skip/merge/change-lens) for same-lens collisions. The source POI is deleted.

7. **Editor completes the merge.** The map updates immediately — the source marker disappears, the target marker reflects the merged state. A success toast confirms.

---

## Acceptance Criteria

1. **Works when** the map is visible at all times — before JSON load, during review, and during upload — without the editor needing to navigate to a specific POI first.

2. **Works when** all database POIs within the 50km geofence render as grey circle markers, and all incoming JSON POIs render as amber circle markers, with both visible simultaneously and visually distinguishable at all zoom levels.

3. **Works when** clicking a database POI marker on the map shows a popup with the POI's name, coordinates, and beat count; clicking an incoming POI marker selects it in the worklist and loads its detail.

4. **Works when** clicking a worklist entry pans and zooms the map to center on that POI's marker.

5. **Works when** the editor can manually search for and select a database POI to match an incoming POI to, overriding or supplementing the automatic 50m proximity match, and the resulting upload creates beats on the matched existing POI rather than a new one.

6. **Works when** two database POIs can be merged via the map: the editor clicks a target POI's "Merge into this POI..." popup button, then clicks a source POI. All beats from the source transfer to the target, same-lens collisions trigger the existing conflict resolution UI, and the empty source POI is deleted.

7. **Works when** the map reflects all changes immediately after upload or merge — new markers appear, merged markers disappear — without a full page reload.

8. **Works when** the persistent map renders 200+ circle markers without visible jank on a standard laptop (Chrome/Firefox).

---

## Edge Cases

1. **Merge with itself:** The UI prevents selecting the same POI as both source and target (ignores the click, shows a toast).

2. **Incoming POI manually matched to an automatic proximity match:** The manual match takes precedence; the automatic match suggestion is cleared.

3. **All target lenses occupied:** If the target POI already has a beat on every taggable lens, all incoming beats from the source trigger conflict resolution — no silent drops.

4. **Source POI has zero beats:** Merge completes (source deleted, target unchanged), with a confirmation prompt noting there are no beats to transfer.

5. **Browser resized:** The map and lower panel resize responsively; `map.invalidateSize()` fires on layout changes.

---

## Open Questions

None — all resolved during spec review.

---

## Best Practices Notes (for Stage 3)

- **Data integrity:** AC6 requires conflict resolution for same-lens collisions during merge. The delete-source step must cleanly remove all Neo4j relationships (HAS_BEAT, LOCATED_IN, etc.). Stage 3 must audit the exact Cypher operations.
- **Security:** No new endpoints introduced. Merge/delete use existing authenticated endpoints. Stage 3 should verify editor auth is checked on destructive operations.
- **Privacy:** N/A — no user data or location tracking changes.
- **Accessibility:** The searchable dropdown (AC5) and merge flow (AC6) should be keyboard-navigable. Stage 3 should verify.
- **Performance:** AC8 sets a concrete bar (200+ markers). Stage 3 should confirm Leaflet `L.circleMarker` handles this without clustering.
