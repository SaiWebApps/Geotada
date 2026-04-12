# Spec — Content Browser Workbench

**Date:** 2026-03-24
**Flavor:** Behavior Spec
**Scope:** [01-scope.md](01-scope.md)
**Status:** Approved

---

## Slice Goal

An **editor** can **browse all existing POIs and their beats from the database alongside incoming JSON content** so that **editorial decisions are made with full context of what's already in the system**.

## Walkthrough

1. Editor opens the workbench and selects "Boston" from the city dropdown.
2. The worklist populates with all DB POIs within the Boston geofence. Each row shows the POI name, a "DB" badge, and a beat count of "--" (beats not yet loaded).
3. Editor clicks a DB POI. The detail panel loads its beats from the API (with a loading skeleton) and displays them as read-only cards -- each showing lens, gravity, and script body. POI fields (name, coordinates, description) are also read-only.
4. Editor clicks "Load JSON" and selects a file. Incoming beats are matched against DB POIs using the existing proximity + name-similarity logic. Matched POIs show their incoming beats below existing beats with an "Incoming" badge. Unmatched incoming POIs appear in the worklist with a "New POI" badge.
5. Editor uses the sort control to push POIs with incoming beats to the top. DB-only POIs remain visible below.
6. Editor clicks a matched POI. The detail panel shows existing beats (read-only, "DB" badge) above incoming beats (editable, "Incoming" badge) -- giving full context for editorial review.
7. Editor clicks "Update POI" on the matched POI. The existing conflict resolution flow runs for incoming beats, then all pending incoming beats upload. The POI is marked as updated in the worklist.

## Acceptance Criteria

1. **Works when** selecting a city loads all geofence-filtered DB POIs into the worklist, each with a "DB" badge and beat count showing "--" until clicked.
2. **Works when** clicking a DB POI fetches its beats via `GET /graph/poi/{name}/beats` and displays them as read-only cards (all fields non-editable, no conflict actions).
3. **Works when** a loading indicator appears while beats are being fetched and disappears once they render.
4. **Works when** loading a JSON file merges incoming beats into existing DB POIs (matched by proximity + name similarity) rather than replacing the worklist.
5. **Works when** unmatched incoming POIs appear in the worklist with a "New POI" badge and remain fully editable (current behavior preserved).
6. **Works when** a matched POI's detail panel shows existing beats (read-only, labeled "DB") visually separated above incoming beats (editable, labeled "Incoming").
7. **Works when** the worklist auto-sorts on JSON load so POIs with incoming beats appear before DB-only POIs, with a toggle to revert to alphabetical order.
8. **Works when** clicking "Update POI" on a POI with incoming beats triggers the existing `uploadSinglePoi` conflict resolution flow, then marks the POI as updated in the worklist.

## Edge Cases

1. **DB POI with zero beats:** Detail panel shows POI fields (read-only) and an empty beats section with "No beats yet" message.
2. **JSON load with no matches:** All incoming POIs appear as "New POI" entries; DB POIs remain in the worklist unchanged.
3. **Beats fetch fails (network error):** Detail panel shows an inline error message ("Failed to load beats -- click to retry") instead of beats, without losing the worklist state.
4. **Large worklist (200+ POIs):** Worklist renders without visible jank or blocking the main thread.
5. **Re-loading a second JSON file:** Previous incoming beats are cleared and replaced by the new file's content; DB POIs remain.

## Open Questions

*Resolved during approval:*

1. **Beat count on DB POI rows:** Show "--" until clicked (lazy load). Avoids N+1 on initial load.
2. **Sort control UX:** Auto-sort on JSON load with a toggle to revert to alphabetical.
