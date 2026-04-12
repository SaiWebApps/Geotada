# Scope: Area-Aware Content Viewer

**Date:** 2026-04-11
**Thinking mode:** Product thinker — "What problem are we solving?"
**Right-sizing:** Medium (3-6 files, 1-2 sessions) → Stages 1 → 2 → 5 → 6

---

## What we're building

- **Two API endpoints** for Area data: beats-for-area and contents-of-area (mirrors existing POI beats pattern)
- **Area boundary polygons** drawn on the Leaflet map as clickable overlays, color-coded by area_type
- **Area detail panel** showing area info, its beats (if any), and list of contained POIs/sub-areas
- **Click-to-zoom** on area polygons to zoom in and reveal contents
- **Existing POI functionality preserved** — markers, beat cards, edit mode all unchanged

## Why

Visual assessment tool for verifying correctness and completeness of the Area containment work (Scopes 1-4). Also unblocks tour builder by exposing Area beats through the API. Supports Phase 1 milestone: content pipeline verification.

## What we're NOT building

- Area editing (boundaries, properties) in the viewer
- Tour builder integration
- Lens filtering or layer toggles
- New pages — evolving existing `frontend/viewer.html` only
- Area CRUD through the frontend

## What already exists

- `frontend/viewer.html` — Leaflet map with POI markers, beat panel, edit mode (~440 lines vanilla JS)
- `src/api/routes/graph.py` — `GET /graph/poi/{name}/beats` endpoint (pattern to copy)
- `GET /nodes/Area` — returns all Areas including WKT boundary strings
- 18 Areas with boundaries in Neo4j, 486 WITHIN edges, 31 beats on 7 Areas
- Leaflet already supports `L.polygon()` for drawing boundaries

## Dependencies or risks

- **API must be running** for the viewer (already the case)
- WKT parsing in the browser — need a small parser (WKT → Leaflet LatLng array). Leaflet doesn't parse WKT natively, but the format is simple enough for a 10-line regex parser. No library needed.
- Performance: 18 area polygons is trivial for Leaflet. If we scale to hundreds of areas in future cities, we'd need to lazy-load by viewport — but not now.

## Best practices touched

- **Performance** (light) — polygon rendering, but trivial at 18 areas
- **UX** — map interaction design, panel navigation
