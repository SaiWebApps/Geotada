# Implementation Plan: Area-Aware Content Viewer

**Date:** 2026-04-11
**Thinking mode:** Implementation engineer — "How do I build this given the actual code?"
**Spec:** [02-spec.md](02-spec.md)
**Red Team:** [04-red-team.md](04-red-team.md)

---

## Existing Codebase Behaviors (Read Before Implementing)

1. **`graph.py` has its own `_serialize_props`** (line 13) — different from `crud/nodes.py`. New endpoints go in `graph.py` and use its serializer.
2. **POI beats endpoint pattern** (`graph.py:70-93`): parameterized Cypher, filters `active_status = "active"`, returns `{poi_name, beats: [...]}`. Area beats endpoint should mirror this exactly.
3. **Frontend `esc()` function** (viewer.html line 126) — all dynamic strings must pass through it. Uses `textContent` (safe).
4. **Frontend `encodeURIComponent()`** used at line 322 for POI names — same pattern for Area names.
5. **Leaflet map** initialized once in `loadCity()` with CARTO dark tiles. POI markers added to `map` directly. Area polygons should be added to a separate `L.layerGroup` for easy clearing.
6. **Panel open/close** via `openPanel()`/`closePanel()` — toggle `.open` class on `#panel`. `map.invalidateSize()` called after transition.
7. **City filtering** uses rough bounding box (±0.15 degrees). Areas should be filtered by `city_name` property instead (more precise).

---

## Scope 1: API Endpoints

### Part A — Task Breakdown

**Task 1: Area beats endpoint**
- **Files:** `src/api/routes/graph.py`
- **Do:** Add `GET /graph/area/{area_name}/beats` endpoint. Copy the POI beats pattern (lines 70-93) but match `(a:Area {name: $name})` instead of `(p:POI {name: $name})`. Same return shape: `{area_name, beats: [{id, script_body, version, active_status, duration_sec, lens_slug}]}`. Filter `active_status = "active"`.
- **Don't touch:** Existing POI beats endpoint. CRUD code. Edge routes.
- **Success check:** `curl -s 'http://localhost:8000/api/v1/graph/area/%C3%8Ele%20de%20la%20Cit%C3%A9/beats' | python3 -m json.tool` returns 4 beats.

**Task 2: Area contents endpoint**
- **Files:** `src/api/routes/graph.py`
- **Do:** Add `GET /graph/area/{area_name}/contents` endpoint. Cypher:
  ```
  MATCH (child)-[:WITHIN]->(a:Area {name: $name})
  OPTIONAL MATCH (child)-[:HAS_BEAT]->(b:NarrativeBeat)
  WITH child, labels(child) AS lbls, count(b) AS beat_count
  RETURN lbls, child.name AS name, child.id AS id,
         child.area_type AS area_type, child.short_description AS short_description,
         beat_count
  ORDER BY lbls[0], name
  ```
  Return shape: `{area_name, sub_areas: [...], pois: [...]}` — split by label in Python.
- **Don't touch:** Existing endpoints.
- **Success check:** `curl -s 'http://localhost:8000/api/v1/graph/area/4th%20Arrondissement/contents' | python3 -m json.tool` returns 3 sub_areas and 50 pois.

**Task 3: Verify both endpoints**
- **Files:** None (verification step)
- **Do:** Test accented names, empty results, city-level area.
- **Success check:**
  - `curl -s 'http://localhost:8000/api/v1/graph/area/Saint-Germain-des-Pr%C3%A9s/beats'` — returns beats
  - `curl -s 'http://localhost:8000/api/v1/graph/area/Paris/contents'` — returns 7 arrondissements as sub_areas
  - `curl -s 'http://localhost:8000/api/v1/graph/area/1st%20Arrondissement/beats'` — returns `{area_name, beats: []}` (empty, not 404)

### Part B — Test Definitions

| AC | Test | Type | Expected |
|----|------|------|----------|
| AC-7 | `curl /graph/area/Île de la Cité/beats` | Integration (curl) | 4 beats with lens_slug fields |
| AC-7 | `curl /graph/area/1st Arrondissement/beats` | Integration (curl) | Empty beats array (not 404) |
| AC-8 | `curl /graph/area/4th Arrondissement/contents` | Integration (curl) | 3 sub_areas + ~50 pois with beat_counts |
| AC-8 | `curl /graph/area/Paris/contents` | Integration (curl) | 7 sub_areas (arrondissements), 0 pois |

### Part C — Claude Code Prompt

---

**SCOPE 1: API Endpoints for Area Beats and Contents**

You are adding two read-only API endpoints to expose Area data for the content viewer frontend.

**Context:** This is a GPS-triggered walking tour app. The Neo4j database has Area nodes (city, district, neighborhood, island, corridor) connected via WITHIN edges to POIs and other Areas. Some Areas have HAS_BEAT edges to NarrativeBeat nodes. The viewer frontend needs these endpoints to display Area data.

**What to build:**

1. **`GET /graph/area/{area_name}/beats`** in `src/api/routes/graph.py`
   - Mirror the existing `get_poi_beats` endpoint (lines 70-93) exactly, but for Areas
   - Cypher: `MATCH (a:Area {name: $name})-[:HAS_BEAT]->(b:NarrativeBeat)-[:TAGGED_WITH]->(l:Lens) WHERE b.active_status = "active" RETURN ...`
   - Return: `{"area_name": str, "beats": [{id, script_body, version, active_status, duration_sec, lens_slug}]}`
   - Area with no beats returns `{"area_name": "...", "beats": []}` — NOT a 404
   - Use `$name` parameter (parameterized query, no string interpolation)

2. **`GET /graph/area/{area_name}/contents`** in `src/api/routes/graph.py`
   - Cypher: `MATCH (child)-[:WITHIN]->(a:Area {name: $name}) OPTIONAL MATCH (child)-[:HAS_BEAT]->(b:NarrativeBeat) WITH child, labels(child) AS lbls, count(b) AS beat_count RETURN lbls, child.name AS name, child.id AS id, child.area_type AS area_type, child.short_description AS short_description, beat_count ORDER BY lbls[0], name`
   - Split results by label in Python: items with `"Area"` in labels go to `sub_areas`, items with `"POI"` go to `pois`
   - Return: `{"area_name": str, "sub_areas": [{name, id, area_type, short_description, beat_count}], "pois": [{name, id, short_description, beat_count}]}`
   - Use `$name` parameter

**What NOT to touch:**
- Existing `get_poi_beats` endpoint
- CRUD code (`src/api/crud/`)
- Edge routes (`src/api/routes/edges.py`)
- Node models or schema definitions
- Frontend files

**Verification:**

```bash
# AC-7: Area beats
curl -s 'http://localhost:8000/api/v1/graph/area/%C3%8Ele%20de%20la%20Cit%C3%A9/beats' | python3 -c "
import sys, json; d = json.load(sys.stdin)
assert len(d['beats']) == 4, f'Expected 4 beats, got {len(d[\"beats\"])}'
assert all('lens_slug' in b for b in d['beats'])
print('AC-7 PASS')
"

# AC-7: Empty area returns empty list, not 404
curl -s 'http://localhost:8000/api/v1/graph/area/1st%20Arrondissement/beats' | python3 -c "
import sys, json; d = json.load(sys.stdin)
assert d['beats'] == [], f'Expected empty beats, got {d[\"beats\"]}'
print('AC-7 empty PASS')
"

# AC-8: Area contents
curl -s 'http://localhost:8000/api/v1/graph/area/4th%20Arrondissement/contents' | python3 -c "
import sys, json; d = json.load(sys.stdin)
assert len(d['sub_areas']) == 3, f'Expected 3 sub_areas, got {len(d[\"sub_areas\"])}'
assert len(d['pois']) >= 40, f'Expected 40+ pois, got {len(d[\"pois\"])}'
print('AC-8 PASS')
"

# AC-8: City level
curl -s 'http://localhost:8000/api/v1/graph/area/Paris/contents' | python3 -c "
import sys, json; d = json.load(sys.stdin)
assert len(d['sub_areas']) == 7, f'Expected 7 arrondissements, got {len(d[\"sub_areas\"])}'
print('AC-8 city PASS')
"

# Accented name
curl -s 'http://localhost:8000/api/v1/graph/area/Saint-Germain-des-Pr%C3%A9s/beats' | python3 -c "
import sys, json; d = json.load(sys.stdin)
assert 'beats' in d
print('Accented name PASS')
"
```

Before starting, confirm you understand the full scope and flag any conflicts with the existing codebase or assumptions you are making.

---

## Scope 2: Frontend — Area Polygons and Panel

### Part A — Task Breakdown

**Task 1: Add CSS for area polygons and area panel**
- **Files:** `frontend/viewer.html` (style section)
- **Do:** Add styles for: `.badge-area-type` (color per area_type), `.area-contents` list, `.content-item` (clickable list items for sub-areas and POIs), `.beat-source` badge ("Area" or "POI" indicator on beat cards). Use existing color palette — blue for district, green for neighborhood, orange for island, purple for corridor.
- **Don't touch:** Existing styles (POI markers, beat cards, panel layout).
- **Success check:** Page loads without CSS errors.

**Task 2: WKT parser and Area polygon rendering**
- **Files:** `frontend/viewer.html` (script section)
- **Do:**
  - Add `parseWkt(wktStr)` function: regex to extract coordinate pairs from `POLYGON((lng lat, lng lat, ...))`, return as `[[lat, lng], ...]` for Leaflet. Defensive: return `null` on parse failure, log warning.
  - Add state: `let areaPolygons = L.layerGroup();` and `let allAreas = [];`
  - In `loadCity()`, after POI loading: fetch `GET /nodes/Area?limit=200`, filter by `city_name === city.name`, parse boundaries, create `L.polygon()` for each.
  - Color map: `{city: 'rgba(255,255,255,0.1)', district: 'rgba(70,130,180,0.2)', neighborhood: 'rgba(100,200,100,0.2)', island: 'rgba(230,126,34,0.25)', corridor: 'rgba(180,100,220,0.25)'}`. City polygon: no fill, faint white dashed outline.
  - Bind tooltip with area name on each polygon.
  - Bind click handler: `selectArea(area)`.
  - Add `areaPolygons` layer group to map.
  - Update stats line: `${allPois.length} POIs · ${allAreas.length} Areas · ${totalBeats} beats`
- **Don't touch:** POI marker logic. Edit mode. Panel HTML structure.
- **Success check:** Reload page, select Paris — 18 colored polygons visible on map with tooltips.

**Task 3: Area selection — panel with beats and contents**
- **Files:** `frontend/viewer.html` (script section)
- **Do:**
  - Add `async function selectArea(area)`:
    1. Zoom map to polygon bounds: `map.fitBounds(polygon.getBounds().pad(0.05))`
    2. Open panel with loading state
    3. Fetch `GET /graph/area/{name}/beats` and `GET /graph/area/{name}/contents` in parallel
    4. Render area detail panel
  - Add `function renderAreaDetail(area, beats, contents)`:
    - Header: area name + close button
    - Badges: area_type badge, beat count, POI count
    - Short description (if any)
    - Beats section (same beat card format as POI, but with `<span class="beat-source">Area</span>` badge)
    - Contents section: sub-areas list (clickable → `selectArea()`), POIs list (clickable → `selectPoi()`)
    - Each list item shows name + beat count
  - Add parent navigation: if area has a parent, show clickable parent name at top of panel
  - To get parent: the contents endpoint for the parent area will include this area. Store `parentArea` when navigating from a contents list click.
- **Don't touch:** `selectPoi()`, `renderPoiDetail()`, `closePanel()`.
- **Success check:** Click 4th Arrondissement polygon → panel shows 3 sub-areas, ~50 POIs. Click Île de la Cité → panel shows 4 beats + contained POIs.

**Task 4: Update POI beat cards with source badge**
- **Files:** `frontend/viewer.html` (script section)
- **Do:** In `renderPoiDetail()`, add `<span class="beat-source">POI</span>` to each beat card's meta section. This distinguishes POI beats from Area beats visually.
- **Don't touch:** Beat card structure or data fetching.
- **Success check:** Click any POI → beat cards show "POI" badge.

**Task 5: Full visual verification**
- **Files:** None (verification step)
- **Do:** Open viewer, select Paris. Verify:
  1. 18 polygons visible, color-coded by type
  2. Click 4th Arrondissement → zooms, panel shows sub-areas + POIs
  3. Click Île de la Cité in list → zooms to island, shows 4 beats with "Area" badge
  4. Click Notre-Dame POI marker → shows POI beats with "POI" badge
  5. Paris polygon is faint outline only
  6. Corridor tooltips visible on hover
- **Success check:** All 6 checks pass visually.

### Part B — Test Definitions

| AC | Test | Type | Expected |
|----|------|------|----------|
| AC-1 | Load Paris → count polygons on map | Manual visual | 18 polygons visible, distinct colors per type |
| AC-2 | Click any polygon → panel opens | Manual visual | Panel shows name, type badge, description, beat count |
| AC-3 | Click 4th Arr → check contents list | Manual visual | 3 sub-areas (Rue Chanoinesse, Île Saint-Louis, Île de la Cité) + ~50 POIs with beat counts |
| AC-4 | Click polygon → map zooms | Manual visual | Map viewport fits the clicked area's bounds |
| AC-5 | Click Île de la Cité → check beats | Manual visual | 4 beat cards with lens, body, duration, words |
| AC-6 | Compare Area beat card vs POI beat card | Manual visual | Area cards show "Area" badge, POI cards show "POI" badge |

### Part C — Claude Code Prompt

---

**SCOPE 2: Frontend — Area Polygons and Detail Panel**

You are evolving `frontend/viewer.html` to display Area boundaries on the Leaflet map and show Area details (beats + contained POIs/sub-areas) in the side panel.

**Prerequisites:** Scope 1 is complete. Two new API endpoints exist:
- `GET /api/v1/graph/area/{name}/beats` — returns `{area_name, beats: [...]}`
- `GET /api/v1/graph/area/{name}/contents` — returns `{area_name, sub_areas: [...], pois: [...]}`

**Context:** The viewer is a single-file vanilla JS app (~440 lines) using Leaflet.js on a dark CARTO basemap. It shows POI markers, and clicking one opens a side panel with beat cards. You are adding Area polygon overlays and an Area detail panel alongside the existing POI functionality. The file uses an `esc()` function (line 126) for XSS prevention — ALL dynamic strings must pass through it.

**What to build:**

1. **CSS additions** (in the `<style>` block):
   - `.badge-district { background: #1e3a5f; color: #5b9bd5; }` (blue)
   - `.badge-neighborhood { background: #1f3d2d; color: #6dca8d; }` (green)
   - `.badge-island { background: #3d2d1f; color: #e6a85c; }` (orange)
   - `.badge-corridor { background: #2d1f3d; color: #b48eda; }` (purple)
   - `.badge-city { background: #2a2a2a; color: #888; }` (grey)
   - `.beat-source { font-size: 10px; padding: 2px 6px; border-radius: 3px; text-transform: uppercase; letter-spacing: 0.5px; }` 
   - `.beat-source-area { background: #3d2d1f; color: #e6a85c; }` (orange)
   - `.beat-source-poi { background: #1e3a5f; color: #5b9bd5; }` (blue)
   - `.content-item { display: flex; justify-content: space-between; align-items: center; padding: 8px 12px; border: 1px solid #333; border-radius: 6px; margin-bottom: 6px; cursor: pointer; font-size: 13px; }` 
   - `.content-item:hover { background: #2a2a2a; }`
   - `.content-item .item-name { color: #e0e0e0; }` 
   - `.content-item .item-meta { color: #666; font-size: 11px; }`
   - `.parent-link { font-size: 12px; color: #5b9bd5; cursor: pointer; margin-bottom: 12px; display: inline-block; }`
   - `.parent-link:hover { text-decoration: underline; }`
   - `.contents-section h3` — same style as `.beats-section h3`

2. **WKT parser** (add to Helpers section):
   ```javascript
   function parseWkt(wktStr) {
     try {
       const inner = wktStr.match(/POLYGON\(\((.+)\)\)/)?.[1];
       if (!inner) return null;
       return inner.split(',').map(pair => {
         const [lng, lat] = pair.trim().split(/\s+/).map(Number);
         return [lat, lng];  // Leaflet uses [lat, lng]
       });
     } catch (e) {
       console.warn('WKT parse failed:', e);
       return null;
     }
   }
   ```

3. **State additions** (add alongside existing state vars):
   ```javascript
   let allAreas = [];
   let areaPolygons = L.layerGroup();
   let selectedArea = null;
   let parentAreaStack = [];  // for back navigation
   ```

4. **Area polygon color map**:
   ```javascript
   const AREA_COLORS = {
     city:         { color: '#666', fillColor: 'transparent', weight: 1, dashArray: '8 4' },
     district:     { color: '#5b9bd5', fillColor: 'rgba(70,130,180,0.15)', weight: 2 },
     neighborhood: { color: '#6dca8d', fillColor: 'rgba(100,200,100,0.12)', weight: 2 },
     island:       { color: '#e6a85c', fillColor: 'rgba(230,168,92,0.18)', weight: 2 },
     corridor:     { color: '#b48eda', fillColor: 'rgba(180,100,220,0.18)', weight: 2 },
   };
   ```

5. **Area loading** — add to `loadCity()` AFTER the POI loading block (after line 280):
   - Fetch all Areas: `GET /nodes/Area?limit=200`
   - Filter by `city_name === city.name`
   - For each area: parse WKT boundary, create `L.polygon()` with colors from map, bind tooltip with `esc(area.properties.name)`, bind click to `selectArea(area)`, add to `areaPolygons` layer group
   - Add `areaPolygons` to map
   - Update stats: `${allPois.length} POIs · ${allAreas.length} areas · ${totalBeats} beats`
   - Also clear areas on city switch: `areaPolygons.clearLayers(); allAreas = [];`

6. **`selectArea(area)` function**:
   - Set `selectedArea = area`
   - Find polygon for this area, fit map bounds to it with `pad(0.05)`
   - Open panel with loading state
   - Fetch beats and contents in parallel:
     ```javascript
     const [beatsResp, contentsResp] = await Promise.all([
       fetch(`${API}/graph/area/${encodeURIComponent(area.properties.name)}/beats`),
       fetch(`${API}/graph/area/${encodeURIComponent(area.properties.name)}/contents`)
     ]);
     ```
   - Call `renderAreaDetail(area, beats, contents)`

7. **`renderAreaDetail(area, beats, contents)` function**:
   - Header: area name + close button
   - Parent link: if `parentAreaStack.length > 0`, show "← {parent name}" link that calls `selectArea()` with the parent and pops the stack
   - Badges: area_type badge (use `.badge-{area_type}` class), beat count, POI count from contents
   - Short description
   - Beats section: use same beat card HTML as POI, add `<span class="beat-source beat-source-area">Area</span>` in `.beat-meta`
   - Contents section header: "Sub-areas" (if any), then "Points of Interest"
   - Sub-area items: clickable `.content-item`, on click → push current area to `parentAreaStack`, call `selectArea()` with the sub-area (fetch the sub-area from allAreas by name)
   - POI items: clickable `.content-item`, on click → find POI in `allPois` by name, call `selectPoi()` with its index

8. **Update `renderPoiDetail()` beat cards**: add `<span class="beat-source beat-source-poi">POI</span>` in the `.beat-meta` div.

9. **Update `closePanel()`**: also clear `selectedArea = null; parentAreaStack = [];`

**What NOT to touch:**
- Edit mode / drag functionality
- The existing `selectPoi()` function logic (only add badge to `renderPoiDetail`)
- API backend code (Scope 1 handles that)
- Map tile layer or base styles

**Verification (manual — open `frontend/viewer.html` in browser):**

1. Select Paris → 18 colored polygons visible on dark map
2. Hover corridor → tooltip shows area name
3. Click "4th Arrondissement" polygon → map zooms, panel shows: name, "district" badge, 3 sub-areas, ~50 POIs
4. Click "Île de la Cité" in sub-areas list → map zooms to island, panel shows 4 beats with "Area" badge, parent link "← 4th Arrondissement"
5. Click "← 4th Arrondissement" → returns to 4th Arr panel
6. Click "Notre-Dame Cathedral" in POI list → POI panel with beats showing "POI" badge
7. Paris polygon is dashed outline only, not filled
8. Stats line shows POI count + Area count + beat count

Before starting, confirm you understand the full scope and flag any conflicts with the existing codebase or assumptions you are making.

---

## Part D — Best Practices Implementation Checklist

| # | Practice | Scope(s) | How to Verify |
|---|----------|----------|---------------|
| D1 | Parameterized Cypher queries (no string interpolation) | Scope 1 | Grep `graph.py` for `$name` in both new endpoints — no f-string Cypher |
| D2 | XSS prevention via `esc()` | Scope 2 | Grep viewer.html — every `${...name}` or `${...description}` wrapped in `esc()` |
| D3 | `encodeURIComponent()` for area names in fetch URLs | Scope 2 | Grep viewer.html — all fetch URLs for area endpoints use `encodeURIComponent` |
| D4 | Defensive WKT parsing | Scope 2 | `parseWkt('garbage')` returns null, doesn't throw |
| D5 | City-level polygon: no fill, dashed outline | Scope 2 | Visual: Paris polygon is a faint dashed outline, not a solid fill |

---

## Summary

| Scope | Est. Sessions | Files Created | Files Modified |
|-------|---------------|---------------|----------------|
| 1: API Endpoints | 1 | — | `src/api/routes/graph.py` |
| 2: Frontend | 1 | — | `frontend/viewer.html` |

Total: 2 sessions, 0 new files, 2 modified files.
