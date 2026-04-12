# Scope — Content Browser Workbench

**Date:** 2026-03-24
**Status:** Approved
**Supersedes:** `specs/2026-03-19-persistent-map-merge/` (persistent map deferred; this spec replaces the worklist/detail changes)

---

## What we're building

- **DB POIs populate the worklist on city select.** After choosing a city, all database POIs within the geofence load into the left-hand worklist (with a "DB" badge). Beats lazy-load when the editor clicks a POI.
- **JSON load merges incoming beats into existing POIs.** When a JSON file is loaded, incoming beats are matched to existing DB POIs and shown inline below existing beats with an "Incoming" badge. Unmatched incoming POIs appear as new entries with a "New POI" badge.
- **Unified detail panel shows full content context.** Clicking any POI in the worklist shows all its beats — existing (read-only) and incoming (editable) — so the editor reviews new content with full context of what's already there.
- **Sortable worklist.** The worklist is sortable so POIs with incoming beats bubble to the top. DB-only POIs remain visible and browsable.
- **"Update POI" action replaces "Mark Complete."** The existing mark-complete button becomes an upload trigger — clicking it uploads all pending incoming beats for that POI (running through existing conflict resolution), then marks the POI as updated.

## Why

Phase 1 gate requires 100+ Boston POIs live. As content grows, editors need to see what's already in the system to avoid duplicates and make better editorial decisions — the current blind-upload flow doesn't scale.

## What we're NOT building

- Editing existing beats (read-only for this pass — editing is a future spec)
- Batch upload across all POIs (per-POI upload only)
- The persistent map (deferring Tasks 1-12 from the persistent-map-merge spec — this spec supersedes it)
- Changes to the backend API or Neo4j schema
- Content search or filtering within beats

## What already exists

- `cachedPoiList` — already fetches all POIs on city select, now geofence-filtered (`review.html:2366-2379`)
- `GET /graph/poi/{name}/beats` — endpoint for fetching beats per POI, used in conflict detection (`review.html:2578`)
- `renderWorklist()` — sorts by priority, separates active/uploaded (`review.html:1442-1523`)
- `renderDetail()` — renders POI fields + beat cards with conflict badges (`review.html:1712-1810`)
- `detectConflictsForPoi()` / `runBeatConflictDetection()` — proximity matching + same-lens/similarity detection (`review.html:2536-2624`)
- `uploadSinglePoi()` — per-POI upload with conflict resolution handling (`review.html:2832-2911`)
- JSON load handler with dedup, proximity matching, and `poiData[]` population (`review.html:1230-1308`)

## Dependencies or risks

- **N+1 API calls on worklist click:** Each POI click triggers a beats fetch. Acceptable for text content, but if latency is noticeable we may need a loading skeleton.
- **JSON matching logic changes:** Currently JSON replaces the worklist. Now it must merge into an existing worklist — the matching logic (proximity + name similarity) needs to work against already-loaded worklist entries, not just `cachedPoiList`.
- **`poiData[]` structure changes:** Currently holds only incoming JSON POIs. Now it holds DB POIs too, with a different shape (DB POIs have `id`, beats come from API, not inline). Need a clear `_source: 'db' | 'incoming' | 'matched'` discriminator.

## Best practices (light)

- **Performance:** Lazy beat loading keeps initial load fast. Worklist rendering with 200+ items should remain smooth.
- **UX:** Sorting and visual badges are critical for usability — editors need to immediately see which POIs have new content.
- **Data integrity:** Read-only existing beats prevents accidental edits. Upload action must go through existing conflict resolution flow.
