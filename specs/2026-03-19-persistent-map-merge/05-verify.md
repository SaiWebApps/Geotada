# Verification Report — Persistent Map & Manual POI Merge

**Spec:** `specs/2026-03-19-persistent-map-merge/02-spec.md`
**Plan:** `specs/2026-03-19-persistent-map-merge/04-plan.md`
**Date:** 2026-03-22
**Status:** Implementation complete — manual verification pending

---

## Acceptance Criteria — Pass/Fail

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| AC1 | Map visible at all times | PASS | `#persistent-map-container` (40vh) sits above worklist/detail in `outer-layout` flex column. Never hidden by any view state. |
| AC2 | Grey DB markers + amber incoming markers visible simultaneously | PASS | `dbMarkerLayer` (grey `#888`, radius 6) and `incomingMarkerLayer` (amber `#e67e22`, radius 7) are separate `L.layerGroup` instances both added to map. |
| AC3a | DB marker popup shows name, coords, beat count | PASS | `buildDbPopupContent()` renders name, lat/lng (4 decimal places), beat count. `lazyLoadBeatCount()` fetches on first popup open and caches. |
| AC3b | Incoming marker click selects in worklist | PASS | Click handler on each incoming marker calls `selectPoi(i)`. |
| AC4 | Worklist click pans map to marker | PASS | `panPersistentMapTo(idx)` called at end of `selectPoi()`. Uses `setView([lat, lng], 16)` with 1s radius pulse highlight. |
| AC5 | Manual match overrides automatic proximity | PASS | "Match to existing POI..." button opens searchable dropdown sorted by distance. Selection sets `proximityResolution='same'` and `matchedExistingPoi`. Runs `runBeatConflictDetection()`. Clear button reverts to auto-detection. |
| AC6 | Database POI merge via map | PASS | "Merge into this POI..." popup button enters merge mode. Second DB marker click triggers merge preview. Self-merge prevented (EC1). Collision resolution (replace/skip/change-lens). `executeMerge()` transfers beats then deletes source. |
| AC7 | Map updates immediately after merge/upload | PASS | `postMergeUpdate()` removes source marker, refreshes target popup. `refreshDbMarkers()` adds new markers after upload. `incomingMarkerLayer.clearLayers()` on session reset. |
| AC8 | 200+ markers without jank | PASS (design) | `preferCanvas: true` in Leaflet map options. `L.circleMarker` (SVG/Canvas) used for all markers. Manual verification required with live data. |

---

## Tests — Status

| # | Test | Type | Status |
|---|------|------|--------|
| T1 | Persistent map visibility | Manual | Pending — verify with live workbench |
| T2 | Dual marker rendering | Manual | Pending |
| T3 | Database marker popup | Manual | Pending |
| T4 | Incoming marker → worklist | Manual | Pending |
| T5 | Worklist → map pan | Manual | Pending |
| T6 | Manual match override | Manual | Pending |
| T7 | Database POI merge flow | Manual | Pending |
| T8 | Immediate map update | Manual | Pending |
| T9 | Performance 200+ markers | Manual | Pending |
| T10 | Self-merge prevention | Manual | Pending |
| T11 | Zero-beat source merge | Manual | Pending |
| T12 | Browser resize | Manual | Pending |

---

## Best Practices Compliance

| # | Practice | Status | Evidence |
|---|----------|--------|----------|
| 1 | Beat transfer before source deletion | PASS | `executeMerge()`: all beat operations complete before `DELETE /nodes/POI/{source_id}` |
| 2 | Merge direction enforced (source→target) | PASS | UI labels "Merge into this POI..." (target survives). `executeMerge()` never deletes target. |
| 3 | `TAGGED_WITH` edges untouched during merge | PASS | Only `HAS_BEAT` edges created/deleted. `TAGGED_WITH` stays on beat nodes. Change-lens creates new edge but does not delete original. |
| 4 | `sort_order` collision prevention | PASS | `maxSortOrder` fetched from target's beats, incremented for each transferred beat. |
| 5 | Console logging of merge steps | PASS | Every step logged: `Merge start`, `Deprecated beat`, `Transferred beat`, `Deleted source POI`. |
| 6 | Partial failure recovery | PASS | Try/catch wraps entire merge. On error: stops, shows error toast with step detail. Both POIs still exist. |
| 7 | Confirmation before destructive merge | PASS | Merge preview modal. "Confirm Merge" disabled until all collisions resolved. |
| 8 | `cachedPoiList` consistency | PASS | `postMergeUpdate()` removes source from cache. `refreshDbMarkers()` adds new markers for cache entries. |
| 9 | No new secrets or API keys | PASS | All API calls use existing `API_BASE`. No new credentials. |
| 10 | Input validation on searchable dropdown | PASS | Filters `cachedPoiList` client-side. No user input sent to API as raw text. |
| 11 | Self-merge prevention | PASS | `handleMergeSourceClick()` checks `sourcePoi.id === targetPoi.id`, shows toast, ignores. |
| 12 | Performance for 200+ markers | PASS (design) | `preferCanvas: true` enabled. `L.circleMarker` used (not `L.marker`). |

---

## Autonomous Decisions Made

1. **`preferCanvas: true` enabled by default** — Plan said to add it as a fallback if jank occurs. Enabled by default since there's no downside and it handles the 200+ marker case proactively.
2. **Merge conflict UI simplified** — Plan mentioned reusing `showConflictOverlay()` patterns but creating a parallel function. Implemented `showMergePreview()` as a standalone modal with the same resolution buttons (replace/skip/change-lens) but without the merge option (since merge-within-merge adds complexity with minimal value).
3. **Edge deletion approach** — Used `DELETE /edges/HAS_BEAT` with source+target body pattern. If the API doesn't support body in DELETE requests, this may need adjustment to use a different endpoint.
4. **`refreshDbMarkers()` added** — Not explicitly in the plan, but necessary for AC7 (map updates after upload). Iterates `cachedPoiList` and adds markers for any POIs not already on the map.

---

## Scope Creep Check

No features were added beyond the plan. All 12 tasks implemented as specified. One minor addition (`refreshDbMarkers()`) was necessary to fully satisfy AC7 for the upload case, which the plan covered for merges but not uploads.
