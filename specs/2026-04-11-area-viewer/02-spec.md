# Spec: Area-Aware Content Viewer

**Date:** 2026-04-11
**Thinking mode:** Contract designer — "What does the system promise?"
**Flavor:** A — Behavior Spec (user-facing work)

---

## Slice goal

A **founder** can **view Area boundaries on the map, click into them to see contained POIs and beats, and distinguish Area-owned beats from POI-owned beats** so that **they can visually assess correctness and completeness of the spatial data**.

## Walkthrough

1. User selects "Paris" from the city dropdown. Map loads with POI markers (as before) AND semi-transparent colored polygons for all 18 Areas.
2. User sees polygons color-coded by type: districts are blue, neighborhoods green, islands orange, corridors purple. City polygon (Paris) is a faint outline only.
3. User clicks an arrondissement polygon (e.g., "4th Arrondissement"). Map zooms to fit that area's bounds. Side panel opens showing: area name, type badge, short description, beat count, and a list of contained sub-areas and POIs.
4. User sees "Île de la Cité" and "Le Marais" listed as sub-areas under the 4th. Clicks "Île de la Cité" in the list — map zooms to the island polygon, panel updates to show the island's own beats (4 beats) and its contained POIs (Conciergerie, Place Dauphine, etc.).
5. User clicks a beat card on the island — sees full beat detail: lens, script body, duration, word count. The beat card shows an "Area beat" indicator distinguishing it from POI beats.
6. User clicks a POI marker (Notre-Dame) from the map. Panel switches to the POI detail view (same as current): POI info + POI beats. Beat cards show "POI beat" indicator.
7. User clicks the parent area name at top of panel to navigate back up to the parent area view.

## Acceptance criteria

- **AC-1:** All 18 Paris Areas render as polygons on the map when the city loads, with distinct colors per area_type.
- **AC-2:** Clicking an Area polygon opens the side panel with area name, area_type badge, short_description, and beat count.
- **AC-3:** The Area panel lists all directly contained sub-areas and POIs (from WITHIN edges), with counts.
- **AC-4:** Clicking an Area polygon zooms the map to fit that area's boundary.
- **AC-5:** Area beats are displayed as beat cards (same format as POI beats: lens, script body, duration, word count).
- **AC-6:** Beat cards visually indicate whether the beat belongs to an Area or a POI (e.g., a small label/badge).
- **AC-7:** `GET /graph/area/{name}/beats` returns active beats with lens info for a given Area (same shape as POI beats endpoint).
- **AC-8:** `GET /graph/area/{name}/contents` returns contained POIs and sub-areas with their names, types, and beat counts.

## Edge cases

1. **Area with no beats** (most arrondissements) — panel shows "No beats" same as current POI behavior, but still shows contained POIs/sub-areas.
2. **POI in multiple Areas** (e.g., Notre-Dame in Île de la Cité + 4th Arr + Latin Quarter) — appears in all parent Area content lists. Not a conflict.
3. **City-level polygon (Paris)** — very large boundary. Renders as faint outline only, not filled, to avoid obscuring everything.
4. **Corridor polygons** — very small/narrow. May be hard to click. Tooltip on hover with area name helps discoverability.

## Open questions

None — simple panel replacement for navigation (click replaces panel, parent name clickable to go back).
