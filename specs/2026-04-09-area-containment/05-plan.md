# Implementation Plan: Area Nodes with Spatial Containment

**Date:** 2026-04-10
**Thinking mode:** Implementation engineer — "How do I build this given the actual code?"
**Spec:** [02-spec.md](02-spec.md)
**Scopes:** [03-scopes.md](03-scopes.md)
**Red Team:** [04-red-team.md](04-red-team.md)

---

## Existing Codebase Behaviors (Read Before Implementing)

These behaviors in the current code fundamentally shape what each scope needs to do:

1. **POI MERGE is on `name` only** (`src/api/crud/nodes.py:102`). Area MERGE must use compound key `(name, area_type, city_name)` — a different pattern requiring a new MERGE clause.
2. **`centroid_lat`/`centroid_lng` → GeoPoint** conversion must follow the exact POI pattern (`src/api/crud/nodes.py:77-107`): pop the lat/lng params, add them back as `$lat`/`$lng`, and use `point({latitude: $lat, longitude: $lng, srid: 4326})` in the SET clause.
3. **Edge MERGE list** is at `src/api/crud/edges.py:93`: `rel_type in ("HAS_BEAT", "TAGGED_WITH")`. WITHIN must be added here.
4. **Edge label validation** uses `NodeLabel` enum (`src/api/routes/edges.py:55-61`). Area must be added to `NodeLabel` first, or WITHIN edge creation will 422.
5. **`_serialize_props`** already handles GeoPoints (`hasattr(val, "latitude")`) and lists — WKT boundary strings need no special handling.
6. **`test_definitions.py`** asserts exact counts (9 constraints, 11 relationships, etc.). These tests MUST be updated or they'll fail.
7. **No `src/utils/` directory exists.** Must be created for the spatial utility.

---

## Scope 1: Area CRUD Foundation

### Part A — Task Breakdown

**Task 1: Schema definitions**
- **Files:** `src/schema/definitions.py`
- **Do:** Add `UniqueConstraint("Area", "id")` to `UNIQUE_CONSTRAINTS`. Add `Index("Area", ("centroid",), index_type="POINT")` to `INDEXES`. Add `"WITHIN"` to `RELATIONSHIP_TYPES`. Add `"WITHIN": []` to `RELATIONSHIP_SCHEMAS`.
- **Don't touch:** Lens definitions, existing constraints, existing relationship schemas.
- **Success check:** `python -c "from src.schema.definitions import UNIQUE_CONSTRAINTS, INDEXES, RELATIONSHIP_TYPES; assert len(UNIQUE_CONSTRAINTS) == 10; assert len(RELATIONSHIP_TYPES) == 12; assert any(i.label == 'Area' for i in INDEXES)"`

**Task 2: Update definition tests**
- **Files:** `tests/test_definitions.py`
- **Do:** Update `test_count_matches_schema_v3` to assert 10 constraints. Update `test_eleven_relationship_types` to assert 12 and rename to `test_twelve_relationship_types`. Add `"WITHIN"` to the `expected` set. Add test for Area POINT index on centroid.
- **Don't touch:** Lens tests.
- **Success check:** `pytest tests/test_definitions.py -v` passes.

**Task 3: Pydantic model for Area**
- **Files:** `src/api/models/nodes.py`
- **Do:** Add `Area = "Area"` to `NodeLabel` enum. Create `AreaCreate` model with fields: `name` (str, required), `area_type` (Literal["city", "district", "neighborhood", "island", "corridor"], required), `city_name` (str, required), `boundary` (str, required — WKT POLYGON), `centroid_lat` (float, required, -90..90), `centroid_lng` (float, required, -180..180), `short_description` (str, default ""). Add validators: `centroid_lat` in range, `centroid_lng` in range, `boundary` starts with "POLYGON((" and ends with "))". Add `AreaCreate` to `CREATE_MODELS` dict.
- **Don't touch:** Existing models.
- **Success check:** `python -c "from src.api.models.nodes import AreaCreate, NodeLabel; NodeLabel('Area'); AreaCreate(name='Test', area_type='district', city_name='Paris', boundary='POLYGON((2.34 48.85, 2.35 48.86, 2.36 48.85, 2.34 48.85))', centroid_lat=48.85, centroid_lng=2.35); print('OK')"`

**Task 4: Area CRUD — create_node branch**
- **Files:** `src/api/crud/nodes.py`
- **Do:** Add `elif label == "Area"` branch after the NarrativeBeat branch (before the generic `else`). MERGE on `{name: $name, area_type: $area_type, city_name: $city_name}`. Pop `centroid_lat` and `centroid_lng` from params, store as `centroid = point({latitude: $lat, longitude: $lng, srid: 4326})`. Store `boundary` as-is (WKT string). Use coalesce for `id` and `created_at` (MERGE pattern). SET remaining properties.
- **Don't touch:** POI or NarrativeBeat branches. Don't touch `update_node` yet (centroid update handling is a nice-to-have).
- **Success check:** Unit-testable — covered by Task 6.

**Task 5: Area CRUD — update_node centroid handling**
- **Files:** `src/api/crud/nodes.py`
- **Do:** Add `elif label == "Area"` block in `update_node` (after the POI block at line 152) to convert `centroid_lat`/`centroid_lng` to GeoPoint, same as POI's lat/lng pattern.
- **Don't touch:** POI update logic.
- **Success check:** Covered by Task 6 tests.

**Task 6: WITHIN edge support**
- **Files:** `src/api/crud/edges.py`, `src/api/models/edges.py`, `src/api/routes/edges.py`
- **Do:**
  - `edges.py` model: Add `WITHIN = "WITHIN"` to `RelType` enum.
  - `edges.py` CRUD: Add `"WITHIN"` to the `use_merge` tuple at line 93: `rel_type in ("HAS_BEAT", "TAGGED_WITH", "WITHIN")`.
  - `edges.py` route: Add WITHIN label validation after the TAGGED_WITH block (after line 74): if `rel_type.value == "WITHIN"`, validate source label is `"POI"` or `"Area"` and target label is `"Area"`. Reject with 422 otherwise.
- **Don't touch:** Existing validation logic.
- **Success check:** Covered by Task 7 tests.

**Task 7: Integration tests for Area CRUD + WITHIN edges**
- **Files:** `tests/test_area_crud.py` (new file)
- **Do:** Create integration tests following `test_api_create.py` and `test_api_edges.py` patterns:
  - `TestCreateArea`: 201 on valid payload, UUID generated, centroid stored as GeoPoint (verify via serialized `{lat, lng}`), boundary stored as WKT string, city_name present, area_type present.
  - `TestAreaMerge`: POST same (name, area_type, city_name) twice → count stays at 1, properties updated on second call.
  - `TestAreaValidation`: invalid area_type → 422, missing city_name → 422, centroid out of range → 422.
  - `TestWithinEdge`: Create Area + POI, create WITHIN edge → 201. Create same WITHIN again → no duplicate (MERGE). Invalid source label (e.g., User→Area) → 422.
  - `TestAreaSpatialQuery`: Create Area with centroid, query via `point.distance` in raw Cypher → verify centroid is a real GeoPoint.
- **Don't touch:** Existing test files.
- **Success check:** `pytest tests/test_area_crud.py -v` passes, `pytest tests/test_definitions.py -v` passes.

### Part B — Test Definitions

| AC | Test | Type | Expected |
|----|------|------|----------|
| AC-1 | POST /api/v1/nodes/Area with valid payload → 201, UUID id, centroid as GeoPoint, city_name present | Integration | Status 201, `id` is UUID, `properties.centroid` has `{lat, lng}`, `properties.city_name == "Paris"` |
| AC-2 | POST same Area twice (name+area_type+city_name match) → count stays 1 | Integration | GET /api/v1/nodes/Area returns `total == 1` after filtering by name |
| AC-3 | POST /api/v1/edges/WITHIN between POI→Area → 201, MERGE doesn't duplicate | Integration | First POST → 201. Second POST with same source/target → 201, edge count stays 1 |
| AC-8 | Area centroid supports spatial proximity query | Integration | Raw Cypher `point.distance(a.centroid, point(...))` returns the test Area |

### Part C — Claude Code Prompt

---

**SCOPE 1: Area CRUD Foundation**

You are implementing the Area node type and WITHIN relationship for a Neo4j-backed FastAPI application. This is a vertical slice: schema → Pydantic models → CRUD → routes → tests.

**Context:** The app manages a travel content graph. Current node types: User, Profile, Trip, ItineraryItem, POI, NarrativeBeat, Lens. POI uses MERGE on `name`. NarrativeBeat uses MERGE on `script_body`. Area nodes need MERGE on compound key `(name, area_type, city_name)`.

**What to build (in order):**

1. **Schema definitions** (`src/schema/definitions.py`):
   - Add `UniqueConstraint("Area", "id")` to `UNIQUE_CONSTRAINTS` (will become 10 total).
   - Add `Index("Area", ("centroid",), index_type="POINT")` to `INDEXES`.
   - Add `"WITHIN"` to `RELATIONSHIP_TYPES` (will become 12 total).
   - Add `"WITHIN": []` to `RELATIONSHIP_SCHEMAS` (no properties).

2. **Update tests** (`tests/test_definitions.py`):
   - Change constraint count assertion from 9 to 10.
   - Change relationship count assertion from 11 to 12, rename test method.
   - Add `"WITHIN"` to the expected relationship set.
   - Add a test for the Area POINT index on centroid.

3. **Pydantic model** (`src/api/models/nodes.py`):
   - Add `Area = "Area"` to `NodeLabel` enum.
   - Create `AreaCreate(BaseModel)`:
     - `name: str` (required)
     - `area_type: Literal["city", "district", "neighborhood", "island", "corridor"]` (required)
     - `city_name: str` (required)
     - `boundary: str` (required) — WKT POLYGON string
     - `centroid_lat: float` (required) — validate -90 to 90
     - `centroid_lng: float` (required) — validate -180 to 180
     - `short_description: str = ""`
   - Add validators: `centroid_lat` range, `centroid_lng` range, `boundary` must start with `"POLYGON(("` and end with `"))"`.
   - Add `NodeLabel.Area: AreaCreate` to `CREATE_MODELS`.

4. **Node CRUD** (`src/api/crud/nodes.py`):
   - Add `elif label == "Area"` branch after the NarrativeBeat branch (before the generic `else` at line 123).
   - Pop `centroid_lat` and `centroid_lng` from params into `lat` and `lng` variables.
   - MERGE clause: `MERGE (n:Area {name: $name, area_type: $area_type, city_name: $city_name})`
   - SET: `n.id = coalesce(n.id, randomUUID())`, `n.created_at = coalesce(n.created_at, datetime())`, `n.centroid = point({latitude: $lat, longitude: $lng, srid: 4326})`, plus all remaining params (boundary, short_description).
   - In `update_node`, add `elif label == "Area"` after the POI block to handle centroid_lat/centroid_lng → GeoPoint conversion (same pattern as POI).

5. **Edge CRUD** (`src/api/crud/edges.py`):
   - Change line 93 to: `use_merge = rel_type in ("HAS_BEAT", "TAGGED_WITH", "WITHIN")`

6. **Edge model** (`src/api/models/edges.py`):
   - Add `WITHIN = "WITHIN"` to `RelType` enum.

7. **Edge route validation** (`src/api/routes/edges.py`):
   - After the TAGGED_WITH validation block (after line 74), add:
   ```python
   if rel_type.value == "WITHIN":
       if body.source.label not in ("POI", "Area"):
           raise HTTPException(422, "WITHIN source must be POI or Area")
       if body.target.label != "Area":
           raise HTTPException(422, "WITHIN target must be Area")
   ```

8. **Integration tests** (`tests/test_area_crud.py`, new file):
   - Follow the exact patterns in `tests/test_api_create.py` and `tests/test_api_edges.py`.
   - Test classes: `TestCreateArea`, `TestAreaMerge`, `TestAreaValidation`, `TestWithinEdge`, `TestAreaSpatialQuery`.
   - Use `@needs_neo4j` decorator, `clean_driver` fixture, `TestClient`.
   - Tests must cover: AC-1 (create returns 201 with all expected fields), AC-2 (MERGE idempotency — same compound key doesn't duplicate), AC-3 (WITHIN edge creation + MERGE), AC-8 (centroid spatial query).

**What NOT to touch:**
- POI or NarrativeBeat CRUD logic
- Lens definitions or seeding
- Frontend code
- Any migration or data population (that's Scope 2+)

**Verification commands** (run after implementation):

```bash
# Start services
make db-up && make api &

# AC-1: Create Area
curl -s -X POST http://localhost:8000/api/v1/nodes/Area \
  -H "Content-Type: application/json" \
  -d '{"name":"Test Arrondissement","area_type":"district","city_name":"Paris","boundary":"POLYGON((2.34 48.85, 2.35 48.86, 2.36 48.85, 2.34 48.85))","centroid_lat":48.855,"centroid_lng":2.345,"short_description":"Test"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['id'], 'missing id'; assert d['properties']['city_name']=='Paris'; assert 'lat' in str(d['properties'].get('centroid',{})), 'centroid not GeoPoint'; print('AC-1 PASS')"

# AC-2: MERGE idempotency
curl -s -X POST http://localhost:8000/api/v1/nodes/Area \
  -H "Content-Type: application/json" \
  -d '{"name":"Test Arrondissement","area_type":"district","city_name":"Paris","boundary":"POLYGON((2.34 48.85, 2.35 48.86, 2.36 48.85, 2.34 48.85))","centroid_lat":48.855,"centroid_lng":2.345}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('AC-2 PASS — returned existing node:', d['id'])"

# AC-3: WITHIN edge
# (Create a POI first, then WITHIN edge to the Area created above)

# AC-8: Spatial proximity
# (Run raw Cypher via neo4j driver to verify point.distance works on centroid)

# Full test suite
pytest tests/test_definitions.py tests/test_area_crud.py -v
```

Before starting, confirm you understand the full scope and flag any conflicts with the existing codebase or assumptions you are making.

---

## Scope 2: Paris Area Hierarchy

### Part A — Task Breakdown

**Task 1: Add Shapely dependency**
- **Files:** `requirements.txt`
- **Do:** Add `shapely>=2.0` to requirements. Run `pip install shapely>=2.0`.
- **Don't touch:** Other dependencies.
- **Success check:** `python -c "from shapely.geometry import Polygon; print('OK')"`

**Task 2: Create spatial utility module**
- **Files:** `src/utils/__init__.py` (new), `src/utils/spatial.py` (new)
- **Do:** Create `src/utils/` directory with `__init__.py`. Create `spatial.py` with:
  - `fetch_osm_boundary(osm_relation_id: int) -> list[tuple[float, float]]`: Fetch polygon from Overpass API, return raw coordinate list. Cache response to `data/paris/boundaries/{relation_id}.json`.
  - `simplify_polygon(coords: list[tuple[float, float]], max_vertices: int = 15) -> list[tuple[float, float]]`: Use Shapely's `simplify()` (Douglas-Peucker) to reduce to target vertex count. Validate result has 5–15 vertices.
  - `coords_to_wkt(coords: list[tuple[float, float]]) -> str`: Convert coordinate pairs to WKT POLYGON string. Ensure polygon is closed (first = last vertex).
  - `point_in_polygon(lat: float, lng: float, wkt: str) -> bool`: Parse WKT polygon, test if point is inside. Used by Scope 4.
  - `point_in_areas(lat: float, lng: float) -> list[dict]`: Given coordinates, query all Areas from Neo4j and return those containing the point. Used by Scope 4.
- **Don't touch:** Any existing source files.
- **Success check:** `python -c "from src.utils.spatial import coords_to_wkt, simplify_polygon; print('OK')"`

**Task 3: Create Paris area data file**
- **Files:** `data/paris/areas.json` (new)
- **Do:** Create a JSON file containing the Paris area hierarchy. For each area: `name`, `area_type`, `city_name` ("Paris"), `osm_relation_id` (for boundary fetching), `parent_area` (name of containing area or null for Paris city). Include:
  - Paris (city, OSM relation 7444)
  - 1st–7th Arrondissements (district, each with its OSM relation ID)
  - Sub-areas with content: Île de la Cité (island), Île Saint-Louis (island), Les Halles (neighborhood), Latin Quarter (neighborhood), Saint-Germain-des-Prés (neighborhood), Le Marais (neighborhood)
  - Only include areas where we have content or need them for containment. Do NOT create empty placeholder areas.
- **Don't touch:** Existing data files.
- **Success check:** `python -c "import json; d=json.load(open('data/paris/areas.json')); assert any(a['name']=='Paris' for a in d); print(f'{len(d)} areas defined')"`

**Task 4: Build and run the area creation script**
- **Files:** `scripts/create_paris_areas.py` (new)
- **Do:** Script that:
  1. Reads `data/paris/areas.json`
  2. For each area, fetches boundary from OSM Overpass (using `fetch_osm_boundary`), simplifies it, converts to WKT
  3. Computes centroid using Shapely
  4. Creates the Area node via `POST /api/v1/nodes/Area`
  5. Creates WITHIN edges for hierarchy (sub-areas → arrondissements → Paris city) via `POST /api/v1/edges/WITHIN`
  6. Caches all boundary data to `data/paris/boundaries/` for re-runs without API calls
  7. Prints a summary table of created areas and WITHIN edges
- **Don't touch:** Existing scripts.
- **Success check:** Run the script, then verify with the Scope 2 verification commands from `03-scopes.md`.

**Task 5: Validate polygon quality**
- **Files:** No new files — verification step.
- **Do:** After creating areas, run a validation check: every Area has boundary data, every polygon is valid (closed, 5–15 vertices), every WITHIN edge connects to the correct parent.
- **Don't touch:** Nothing.
- **Success check:** Scope 2 verification commands all pass.

### Part B — Test Definitions

| Test | Type | Expected |
|------|------|----------|
| `simplify_polygon` reduces vertices to target range | Unit | Input 100-vertex polygon → output 5-15 vertices |
| `coords_to_wkt` produces valid closed WKT | Unit | Output matches `POLYGON((lng lat, ...))` format, first=last vertex |
| `point_in_polygon` returns True for interior point | Unit | Known-inside point → True |
| `point_in_polygon` returns False for exterior point | Unit | Known-outside point → False |
| Paris city Area exists with boundary | Integration (manual) | Cypher query returns Paris with non-null boundary |
| 7 arrondissements WITHIN Paris | Integration (manual) | Count query returns 7 |
| Sub-areas WITHIN arrondissements | Integration (manual) | At least 2 sub-areas have WITHIN edges to districts |

### Part C — Claude Code Prompt

---

**SCOPE 2: Paris Area Hierarchy**

You are creating the Area hierarchy for Paris — the city node, 7 arrondissements (1st–7th), and named sub-areas — using boundary polygons from OpenStreetMap.

**Prerequisites:** Scope 1 is complete. Area CRUD and WITHIN edges work via the API.

**Context:** This is a GPS-triggered audio tour app. Area nodes represent geographic containers (city, district, neighborhood, island, corridor). Boundary polygons are stored as WKT strings on the `boundary` property. Containment is precomputed into WITHIN relationships, not computed at query time.

**What to build (in order):**

1. **Add Shapely dependency** (`requirements.txt`):
   - Add `shapely>=2.0`. Run `pip install shapely>=2.0`.

2. **Create spatial utility** (`src/utils/__init__.py` + `src/utils/spatial.py`):
   - `fetch_osm_boundary(osm_relation_id: int) -> list[tuple[float, float]]`: Fetches polygon coordinates from Overpass API (`https://overpass-api.de/api/interpreter`). Query: `[out:json]; relation(ID); out geom;`. Extracts outer way coordinates. Caches response JSON to `data/paris/boundaries/{relation_id}.json` to avoid repeated API calls.
   - `simplify_polygon(coords, max_vertices=15) -> list[tuple[float, float]]`: Shapely `simplify()` with increasing tolerance until vertex count is in 5–15 range. Ensure polygon remains valid.
   - `coords_to_wkt(coords) -> str`: Convert `[(lat, lng), ...]` to `"POLYGON((lng lat, lng lat, ...))"`. Note WKT uses `(longitude latitude)` order. Ensure closed (first=last).
   - `point_in_polygon(lat, lng, wkt) -> bool`: `shapely.wkt.loads(wkt).contains(Point(lng, lat))`. Note: Shapely uses (x=lng, y=lat).
   - `point_in_areas(lat, lng) -> list[dict]`: Connect to Neo4j, fetch all Areas with their boundaries, test each with `point_in_polygon`. Return list of matching area dicts `{name, area_type, city_name}`.

3. **Create Paris area data** (`data/paris/areas.json`):
   - JSON array. Each entry: `{"name": "...", "area_type": "...", "city_name": "Paris", "osm_relation_id": N, "parent_area": "..." or null}`.
   - Paris (city, relation 7444, parent: null)
   - 1st Arrondissement (district, relation 105506, parent: "Paris")
   - 2nd Arrondissement (district, relation 105507, parent: "Paris")
   - 3rd Arrondissement (district, relation 105508, parent: "Paris")
   - 4th Arrondissement (district, relation 105509, parent: "Paris")
   - 5th Arrondissement (district, relation 105510, parent: "Paris")
   - 6th Arrondissement (district, relation 105511, parent: "Paris")
   - 7th Arrondissement (district, relation 105512, parent: "Paris")
   - Île de la Cité (island, relation 3245243, parent: "4th Arrondissement") — verify OSM relation ID
   - Île Saint-Louis (island, relation 3245241, parent: "4th Arrondissement") — verify OSM relation ID
   - Les Halles (neighborhood, relation TBD or manual polygon, parent: "1st Arrondissement")
   - **IMPORTANT:** Verify all OSM relation IDs before using them. Use Overpass Turbo to confirm. If a relation doesn't exist or doesn't have a clean polygon (especially informal neighborhoods), define the boundary manually with 5-8 vertices and annotate `"source": "manual"` in the data file.

4. **Build area creation script** (`scripts/create_paris_areas.py`):
   - Read `data/paris/areas.json`.
   - For each area (process parents before children — sort by: city first, then districts, then sub-areas):
     a. Fetch/load boundary (from cache or Overpass API)
     b. Simplify polygon to 5–15 vertices
     c. Compute centroid via Shapely
     d. POST to `/api/v1/nodes/Area` with name, area_type, city_name, boundary (WKT), centroid_lat, centroid_lng
     e. Record the returned `id` for WITHIN edge creation
   - After all areas created, create WITHIN edges:
     a. For each area with a `parent_area`, POST `/api/v1/edges/WITHIN` with source=child Area, target=parent Area
   - Print summary table: area name, type, vertex count, parent, status.

5. **Validate polygons:**
   - After running the script, verify:
     a. All Areas have non-null boundary
     b. All polygons are valid (parseable by Shapely)
     c. WITHIN hierarchy is correct (7 districts → Paris, sub-areas → their districts)

**What NOT to touch:**
- Node or edge CRUD code (Scope 1 handles that)
- Existing POI data
- Migration of misclassified POIs (that's Scope 3)
- Frontend/workbench

**About OSM Overpass:**
- Rate limit: max 2 requests/second, 10K elements per query. Our queries are small (single relations).
- Cache responses to `data/paris/boundaries/` for idempotent re-runs.
- If Overpass is down, the script should work from cached files.

**Verification commands** (from `03-scopes.md`, updated for WKT):

```bash
# 1. Paris city Area exists
python3 -c "
from neo4j import GraphDatabase
d = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j','travlr_dev_2026'))
with d.session() as s:
    r = s.run(\"MATCH (a:Area {name:'Paris', area_type:'city'}) RETURN a.name, a.city_name\").single()
    assert r, 'Paris city Area not found'
    print('PASS — Paris city Area exists')
d.close()
"

# 2. 7 arrondissements WITHIN Paris
python3 -c "
from neo4j import GraphDatabase
d = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j','travlr_dev_2026'))
with d.session() as s:
    r = s.run(\"MATCH (a:Area {area_type:'district'})-[:WITHIN]->(c:Area {name:'Paris'}) RETURN count(a) AS cnt\").single()
    assert r['cnt'] == 7, f'Expected 7 arrondissements, got {r[\"cnt\"]}'
    print(f'PASS — {r[\"cnt\"]} arrondissements WITHIN Paris')
d.close()
"

# 3. Sub-areas WITHIN arrondissements
python3 -c "
from neo4j import GraphDatabase
d = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j','travlr_dev_2026'))
with d.session() as s:
    r = s.run(\"MATCH (sub:Area)-[:WITHIN]->(arr:Area {area_type:'district'}) WHERE sub.area_type IN ['island','neighborhood','corridor'] RETURN sub.name, arr.name ORDER BY arr.name\").data()
    for row in r:
        print(f'  {row[\"sub.name\"]} WITHIN {row[\"arr.name\"]}')
    assert len(r) >= 2, f'Expected at least 2 sub-areas, got {len(r)}'
    print(f'PASS — {len(r)} sub-areas nested in arrondissements')
d.close()
"

# 4. All Areas have valid WKT boundary
python3 -c "
from neo4j import GraphDatabase
from shapely import wkt
d = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j','travlr_dev_2026'))
with d.session() as s:
    areas = s.run('MATCH (a:Area) RETURN a.name, a.boundary').data()
    for a in areas:
        assert a['a.boundary'], f'{a[\"a.name\"]} has no boundary'
        poly = wkt.loads(a['a.boundary'])
        assert poly.is_valid, f'{a[\"a.name\"]} has invalid polygon'
        verts = len(poly.exterior.coords)
        assert 5 <= verts <= 16, f'{a[\"a.name\"]} has {verts} vertices (want 5-15 + closing)'
        print(f'  {a[\"a.name\"]}: {verts-1} vertices, valid')
    print(f'PASS — all {len(areas)} Areas have valid boundaries')
d.close()
"
```

Before starting, confirm you understand the full scope and flag any conflicts with the existing codebase or assumptions you are making.

---

## Scope 3: POI-to-Area Migration

### Part A — Task Breakdown

**Task 1: Audit existing data**
- **Files:** None (read-only investigation)
- **Do:** Run Cypher queries to document the current state of each of the 7 misclassified POIs:
  - For each: list all HAS_BEAT edges, all NarrativeBeats, all TAGGED_WITH edges from those beats. Count beats per POI.
  - Check for any ItineraryItem → AT_POI edges pointing to these POIs.
  - Record the total beat count across the entire database (baseline for post-migration comparison).
  - Read the actual Les Halles beats to determine which are about the historical neighborhood vs the modern Forum.
- **Don't touch:** Nothing — read-only.
- **Success check:** Documented beat counts per POI, total beat baseline captured, Les Halles beats categorized.

**Task 2: Write migration script**
- **Files:** `scripts/migrate_pois_to_areas.py` (new)
- **Do:** Create a migration script that processes each POI→Area conversion **within a single Neo4j transaction per entity** (red team R1 mitigation). For each misclassified POI:
  1. Record all HAS_BEAT edges (beat IDs + sort_order)
  2. Record all TAGGED_WITH edges from those beats (beat ID + lens ID + confidence)
  3. Look up the corresponding Area node by name (must already exist from Scope 2)
  4. Create HAS_BEAT edges from the Area to each beat (preserving sort_order)
  5. Verify beat count on Area matches expected count
  6. Delete the old POI node (DETACH DELETE removes old HAS_BEAT edges)
  7. Verify beats still have their TAGGED_WITH edges (these are beat→lens, not POI→lens, so they survive POI deletion)
  - **Special handling for Les Halles:**
    - Beats about the historical neighborhood → move to "Les Halles" Area node
    - Create "Forum des Halles" POI node with coordinates (48.8620, 2.3469), importance_tier=3
    - If any beats are about the modern Forum, assign them to the new POI
  - **Transaction safety:** If any step in the entity's migration fails, roll back the entire transaction for that entity. Log the failure and continue with the next entity.
  - Print before/after beat counts to verify zero loss.
- **Don't touch:** Area nodes (created by Scope 2). Existing non-migrated POIs. Schema code.
- **Success check:** Scope 3 verification commands from `03-scopes.md` all pass.

**Task 3: Handle ItineraryItem references (if any)**
- **Files:** `scripts/migrate_pois_to_areas.py` (extend)
- **Do:** Before deleting each POI, check for `(:ItineraryItem)-[:AT_POI]->(:POI)` edges. If found, log a warning — ItineraryItems reference stoppable destinations, which Areas are not. These need manual resolution (likely re-point to a nearby POI or the Forum des Halles POI for Les Halles).
- **Don't touch:** ItineraryItem nodes themselves (just log, don't auto-fix).
- **Success check:** No warnings logged (likely no ItineraryItem references exist yet for these POIs).

**Task 4: WITHIN edges for migrated Areas**
- **Files:** `scripts/migrate_pois_to_areas.py` (extend)
- **Do:** After each POI→Area conversion, if the resulting Area doesn't already have a WITHIN edge to its parent arrondissement, create one. Mapping:
  - Île de la Cité → 4th Arrondissement
  - Île Saint-Louis → 4th Arrondissement
  - Les Halles (neighborhood) → 1st Arrondissement
  - Rue Mouffetard → 5th Arrondissement (corridor)
  - Rue Visconti → 6th Arrondissement (corridor)
  - Rue Chanoinesse → 4th Arrondissement (corridor)
  - Grands Boulevards → 2nd Arrondissement (corridor)
  - Note: Some of these Areas may already have WITHIN edges if they were created in Scope 2. The MERGE behavior on WITHIN edges handles idempotency.
- **Don't touch:** Existing WITHIN hierarchy from Scope 2.
- **Success check:** All 7 migrated Areas have WITHIN edges to their parent arrondissements.

**Task 5: Post-migration verification**
- **Files:** None (verification step)
- **Do:** Run all Scope 3 verification commands. Verify total beat count matches pre-migration baseline. Verify no orphaned beats (beats with no HAS_BEAT edge from any node).
- **Don't touch:** Nothing.
- **Success check:** All commands pass, beat counts match, no orphans.

### Part B — Test Definitions

| AC | Test | Type | Expected |
|----|------|------|----------|
| AC-5 | Île de la Cité Area has ≥5 beats with TAGGED_WITH lens edges | Manual verification | Cypher returns ≥5 beats, each with at least 1 lens tag |
| AC-6 | 7 migrated names no longer exist as POI nodes | Manual verification | `MATCH (n:POI) WHERE n.name IN [...]` returns 0 rows |
| — | Total beat count unchanged after migration | Manual verification | Pre count == post count |
| — | No orphaned beats (beats with 0 incoming HAS_BEAT edges) | Manual verification | `MATCH (b:NarrativeBeat) WHERE NOT ()-[:HAS_BEAT]->(b) RETURN count(b)` returns 0 |
| — | Les Halles split: Area exists + Forum des Halles POI exists | Manual verification | Both nodes found with correct labels and types |

### Part C — Claude Code Prompt

---

**SCOPE 3: POI-to-Area Migration**

You are migrating 7 misclassified POI nodes to Area nodes in Neo4j, preserving all beat relationships. This is a data migration with strict integrity requirements.

**Prerequisites:** Scope 1 (Area CRUD) and Scope 2 (Paris Area hierarchy) are complete. The 7 target Area nodes should already exist from Scope 2 for Île de la Cité and Île Saint-Louis. For corridors (Rue Mouffetard, Rue Visconti, Rue Chanoinesse, Grands Boulevards) and Les Halles, the Areas may need to be created during this scope if they weren't part of Scope 2.

**Context:** 7 POI nodes in the Paris dataset are actually geographic settings (islands, corridors, neighborhoods), not stoppable destinations. Their beats need to move to Area nodes. Beats have TAGGED_WITH→Lens edges that must survive the migration. The HAS_BEAT edges go POI→Beat (and will become Area→Beat), but TAGGED_WITH goes Beat→Lens — so deleting the POI doesn't affect lens tags.

**The 7 POIs to migrate:**
1. Île de la Cité → Area (island), 4th Arr
2. Île Saint-Louis → Area (island), 4th Arr
3. Les Halles → Area (neighborhood), 1st Arr — SPLIT: also create "Forum des Halles" POI
4. Rue Mouffetard → Area (corridor), 5th Arr
5. Rue Visconti → Area (corridor), 6th Arr
6. Rue Chanoinesse → Area (corridor), 4th Arr
7. Grands Boulevards → Area (corridor), 2nd Arr

**What to build:**

1. **Audit current state** (read-only first!):
   ```cypher
   // For each migrated POI: count beats and their lens tags
   MATCH (p:POI)-[:HAS_BEAT]->(b:NarrativeBeat)
   WHERE p.name IN ["Île de la Cité", "Île Saint-Louis", "Les Halles", "Rue Mouffetard", "Rue Visconti", "Rue Chanoinesse", "Grands Boulevards"]
   OPTIONAL MATCH (b)-[:TAGGED_WITH]->(l:Lens)
   RETURN p.name, count(DISTINCT b) AS beats, count(DISTINCT l) AS lenses

   // Total beat baseline
   MATCH (b:NarrativeBeat) RETURN count(b) AS total_beats

   // Check for ItineraryItem references
   MATCH (ii:ItineraryItem)-[:AT_POI]->(p:POI)
   WHERE p.name IN ["Île de la Cité", "Île Saint-Louis", "Les Halles", "Rue Mouffetard", "Rue Visconti", "Rue Chanoinesse", "Grands Boulevards"]
   RETURN ii, p.name
   ```

2. **Create migration script** (`scripts/migrate_pois_to_areas.py`):
   - Each POI migration runs in a **single Neo4j transaction** — if any step fails, the whole entity rolls back.
   - For each POI:
     a. MATCH the POI node by name, collect all HAS_BEAT edges with their beat IDs and sort_orders
     b. Find or create the Area node (MERGE on compound key via API or direct Cypher)
     c. For each beat: CREATE `(area)-[:HAS_BEAT {sort_order: $sort_order}]->(beat)` — use MERGE to be safe
     d. Verify the Area now has the expected number of HAS_BEAT edges
     e. DETACH DELETE the old POI node (this removes the old POI→Beat HAS_BEAT edges, but Beat→Lens TAGGED_WITH edges are unaffected)
     f. Verify the beats still have their TAGGED_WITH edges

   - **Les Halles special handling:**
     - Read all Les Halles beats first. Categorize: neighborhood-about-the-area beats vs modern-Forum beats (read `script_body` to determine).
     - Move neighborhood beats to "Les Halles" Area node.
     - Create "Forum des Halles" POI: `POST /api/v1/nodes/POI` with name="Forum des Halles", latitude=48.8620, longitude=2.3469, importance_tier=3, short_description="Modern shopping and transit complex on the site of the historic central market".
     - If any beats are about the modern Forum, attach them to the Forum des Halles POI.
     - If all beats are about the historical neighborhood (likely), all go to the Area and the Forum POI starts with 0 beats.

   - For corridor Areas (Rue Mouffetard, etc.): these POIs may not have corresponding Area nodes from Scope 2. Create them via the API with:
     - `area_type: "corridor"`
     - `city_name: "Paris"`
     - Boundary: a simplified buffer polygon around the street's path (can be manual 5-vertex polygon — these are informal areas). Annotate as `source: "manual"`.
     - The old POI's coordinates become the centroid.
     - Parent arrondissement from the mapping above.

3. **Post-migration verification:**
   ```cypher
   // AC-6: No migrated POIs remain
   MATCH (n:POI) WHERE n.name IN ["Île de la Cité", "Île Saint-Louis", "Les Halles", "Rue Mouffetard", "Rue Visconti", "Rue Chanoinesse", "Grands Boulevards"]
   RETURN count(n) AS remaining  // Must be 0

   // AC-5: Île de la Cité beats
   MATCH (a:Area {name: "Île de la Cité"})-[:HAS_BEAT]->(b:NarrativeBeat)-[:TAGGED_WITH]->(l:Lens)
   RETURN count(DISTINCT b) AS beats, count(DISTINCT l) AS lenses

   // Total beats unchanged
   MATCH (b:NarrativeBeat) RETURN count(b) AS total_beats  // Must match baseline

   // No orphaned beats
   MATCH (b:NarrativeBeat) WHERE NOT ()-[:HAS_BEAT]->(b) RETURN b.id, left(b.script_body, 50)

   // Les Halles split
   MATCH (a:Area {name: "Les Halles"}) RETURN a.area_type  // "neighborhood"
   MATCH (p:POI {name: "Forum des Halles"}) RETURN p.name  // exists
   ```

**What NOT to touch:**
- Non-migrated POI nodes
- Area hierarchy WITHIN edges created in Scope 2 (except adding new WITHIN for corridor Areas)
- Schema code, CRUD code, route code
- Frontend/workbench

**Critical safety rules:**
- Capture total beat count BEFORE starting any migration
- Each entity migration is a single transaction
- If a migration fails, log the error and continue with the next entity — do NOT stop the whole script
- After all migrations, assert total beat count is unchanged
- Check for orphaned beats (beats with no parent node pointing to them via HAS_BEAT)

Before starting, confirm you understand the full scope and flag any conflicts with the existing codebase or assumptions you are making.

---

## Scope 4: POI Containment Assignment

### Part A — Task Breakdown

**Task 1: Assign existing POIs to Areas via WITHIN**
- **Files:** `scripts/assign_poi_containment.py` (new)
- **Do:** Script that:
  1. Fetches all POI nodes from Neo4j (name, id, location coordinates)
  2. Fetches all Area nodes with their boundaries
  3. For each POI, runs `point_in_polygon` against each Area's boundary
  4. For each match, creates a WITHIN edge: `(POI)-[:WITHIN]->(Area)` via `POST /api/v1/edges/WITHIN`
  5. A POI can be WITHIN multiple Areas (e.g., Notre-Dame is in Île de la Cité AND 4th Arrondissement AND Paris) — create all matching edges
  6. Uses MERGE (already configured in Scope 1) so re-runs are idempotent
  7. Prints summary: POI name → list of containing Areas
  8. Flags any POIs with 0 matches (orphans)
- **Don't touch:** Existing nodes/edges. CRUD/schema code.
- **Success check:** All verification commands from Scope 4 in `03-scopes.md` pass.

**Task 2: Handle edge cases**
- **Files:** `scripts/assign_poi_containment.py` (extend)
- **Do:**
  - POIs exactly on polygon boundaries: Shapely's `contains()` may return False for boundary points. Use `covers()` instead, or add a small buffer (1m).
  - POIs outside all arrondissement polygons: log a warning. These might have inaccurate coordinates or be outside the 1st–7th arrondissement coverage area.
  - POIs in overlapping areas (island + arrondissement): create WITHIN edges to ALL containing areas — this is correct behavior, not a conflict.
- **Don't touch:** Polygon boundaries. CRUD code.
- **Success check:** No POI orphans within the 1st–7th arrondissement bounding box.

**Task 3: Unit tests for spatial utility**
- **Files:** `tests/test_spatial.py` (new)
- **Do:** Unit tests for `src/utils/spatial.py`:
  - `test_coords_to_wkt` — valid output format, closed polygon
  - `test_point_in_polygon_inside` — known interior point returns True
  - `test_point_in_polygon_outside` — known exterior point returns False
  - `test_point_in_polygon_boundary` — boundary point handling
  - `test_simplify_polygon` — output has 5–15 vertices
  - Use real Paris coordinates for all tests (e.g., Notre-Dame at 48.8530, 2.3499 inside a simplified Île de la Cité polygon).
- **Don't touch:** Existing tests.
- **Success check:** `pytest tests/test_spatial.py -v` passes.

**Task 4: Full regression check**
- **Files:** None (verification step)
- **Do:** Run the complete test suite: `pytest tests/ -v`. Run all verification commands from all 4 scopes to confirm no regressions.
- **Don't touch:** Nothing.
- **Success check:** All tests pass, all verification commands pass.

### Part B — Test Definitions

| AC | Test | Type | Expected |
|----|------|------|----------|
| AC-7 | `point_in_areas(48.8530, 2.3499)` returns Île de la Cité + 4th Arr | Integration | Both area names in result list |
| AC-4 | `MATCH (p:POI {name:"Notre-Dame Cathedral"})-[:WITHIN]->(island)-[:WITHIN]->(arr)-[:WITHIN]->(city)` | Integration | Returns Notre-Dame → Île de la Cité → 4th Arr → Paris |
| — | `coords_to_wkt` produces valid WKT | Unit | Starts with `POLYGON((`, ends with `))`, first=last vertex |
| — | `point_in_polygon` interior/exterior correctness | Unit | True for inside, False for outside |
| — | `simplify_polygon` vertex count in range | Unit | 5 ≤ vertices ≤ 15 |
| — | All POIs have ≥1 WITHIN edge (warning for outliers) | Integration | Orphan count is 0 or only non-Paris POIs |

### Part C — Claude Code Prompt

---

**SCOPE 4: POI Containment Assignment**

You are assigning every Paris POI to its containing Area(s) via WITHIN edges, and writing unit tests for the spatial utility module.

**Prerequisites:** Scopes 1-3 are complete. Area hierarchy exists (Paris → arrondissements → sub-areas), 7 misclassified POIs have been migrated to Area nodes, and all Area nodes have boundary polygons stored as WKT strings.

**Context:** The app uses precomputed WITHIN relationships instead of runtime spatial queries. Each POI needs WITHIN edges to all Areas that contain it. A POI can be in multiple Areas (e.g., Notre-Dame is in both Île de la Cité island and 4th Arrondissement district and Paris city). The `point_in_polygon` utility in `src/utils/spatial.py` already exists (created in Scope 2). WITHIN edges use MERGE (configured in Scope 1) so the assignment script is idempotent.

**What to build:**

1. **POI containment script** (`scripts/assign_poi_containment.py`):
   - Connect to Neo4j (use `src.connection.create_driver`).
   - Fetch all POIs: `MATCH (p:POI) RETURN p.id, p.name, p.location` — deserialize the GeoPoint to lat/lng.
   - Fetch all Areas: `MATCH (a:Area) RETURN a.id, a.name, a.area_type, a.boundary` — the boundary is a WKT string.
   - For each POI:
     a. Extract lat/lng from the POI's location GeoPoint
     b. For each Area, call `point_in_polygon(lat, lng, area_boundary_wkt)` from `src/utils/spatial`
     c. For each match, create WITHIN edge via the API: `POST /api/v1/edges/WITHIN` with source={label:"POI", id:poi_id}, target={label:"Area", id:area_id}
     d. Also check if the POI falls in a sub-area (island, neighborhood) AND its parent arrondissement — it should get WITHIN edges to both
   - Use Shapely's `Polygon.covers()` instead of `contains()` for boundary-inclusive checks.
   - Print summary table: POI name → [area names].
   - Flag orphans (POIs with 0 containing Areas).

2. **Unit tests** (`tests/test_spatial.py`, new file):
   - No Neo4j needed — pure unit tests on the spatial functions.
   - Test `coords_to_wkt`:
     ```python
     def test_coords_to_wkt_format():
         coords = [(48.85, 2.34), (48.86, 2.34), (48.86, 2.35), (48.85, 2.34)]
         wkt = coords_to_wkt(coords)
         assert wkt.startswith("POLYGON((")
         assert wkt.endswith("))")
     
     def test_coords_to_wkt_closes_polygon():
         coords = [(48.85, 2.34), (48.86, 2.34), (48.86, 2.35)]  # not closed
         wkt = coords_to_wkt(coords)
         # Should auto-close
         parts = wkt.replace("POLYGON((", "").replace("))", "").split(",")
         assert parts[0].strip() == parts[-1].strip()
     ```
   - Test `point_in_polygon`:
     ```python
     # Use a simple square polygon around central Paris
     SQUARE_WKT = "POLYGON((2.33 48.84, 2.36 48.84, 2.36 48.87, 2.33 48.87, 2.33 48.84))"
     
     def test_interior_point():
         assert point_in_polygon(48.855, 2.345, SQUARE_WKT) is True
     
     def test_exterior_point():
         assert point_in_polygon(48.90, 2.50, SQUARE_WKT) is False
     ```
   - Test `simplify_polygon`:
     ```python
     def test_simplify_within_range():
         # Generate a 50-vertex circle
         import math
         coords = [(math.cos(i*2*math.pi/50), math.sin(i*2*math.pi/50)) for i in range(50)]
         result = simplify_polygon(coords, max_vertices=15)
         assert 5 <= len(result) <= 15
     ```

3. **Full verification** — run after the assignment script:

```bash
# AC-7: point_in_areas utility
python3 -c "
from src.utils.spatial import point_in_areas
results = point_in_areas(48.8530, 2.3499)
names = [r['name'] for r in results]
assert 'Île de la Cité' in names, f'Missing Île de la Cité in {names}'
print(f'AC-7 PASS — Notre-Dame contained in: {names}')
"

# AC-4: Full hierarchical containment
python3 -c "
from neo4j import GraphDatabase
d = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j','travlr_dev_2026'))
with d.session() as s:
    r = s.run('''
        MATCH (p:POI {name:'Notre-Dame Cathedral'})-[:WITHIN]->(island:Area)-[:WITHIN]->(arr:Area)-[:WITHIN]->(city:Area)
        RETURN p.name, island.name, island.area_type, arr.name, arr.area_type, city.name, city.area_type
    ''').single()
    assert r, 'Hierarchical path not found'
    assert r['island.name'] == 'Île de la Cité'
    assert r['arr.name'] == '4th Arrondissement'
    assert r['city.name'] == 'Paris'
    print('AC-4 PASS — Notre-Dame → Île de la Cité → 4th Arr → Paris')
d.close()
"

# Orphan check
python3 -c "
from neo4j import GraphDatabase
d = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j','travlr_dev_2026'))
with d.session() as s:
    orphans = s.run('MATCH (p:POI) WHERE NOT (p)-[:WITHIN]->(:Area) RETURN p.name').data()
    if orphans:
        print(f'WARNING — {len(orphans)} POIs without WITHIN: {[x[\"p.name\"] for x in orphans]}')
    else:
        print('PASS — all POIs have WITHIN edges')
d.close()
"

# Full test suite
pytest tests/ -v
```

**What NOT to touch:**
- Area nodes or WITHIN hierarchy (created in Scopes 2-3)
- CRUD/schema/route code
- Beat data or TAGGED_WITH edges
- Frontend/workbench

Before starting, confirm you understand the full scope and flag any conflicts with the existing codebase or assumptions you are making.

---

## Part D — Best Practices Implementation Checklist

Based on the Stage 4 red team audit, these items must be implemented and verified:

| # | Practice | Scope(s) | How to Verify |
|---|----------|----------|---------------|
| D1 | `area_type` validated as enum via Pydantic `Literal` (not arbitrary string) | Scope 1, Task 3 | POST with `area_type: "bogus"` → 422 |
| D2 | `boundary` validated as WKT POLYGON format in Pydantic | Scope 1, Task 3 | POST with `boundary: "not wkt"` → 422 |
| D3 | `centroid_lat` range validated (-90..90) | Scope 1, Task 3 | POST with `centroid_lat: 999` → 422 |
| D4 | `centroid_lng` range validated (-180..180) | Scope 1, Task 3 | POST with `centroid_lng: 999` → 422 |
| D5 | WITHIN source validated as POI or Area only | Scope 1, Task 6 | POST WITHIN with source label "User" → 422 |
| D6 | WITHIN target validated as Area only | Scope 1, Task 6 | POST WITHIN with target label "POI" → 422 |
| D7 | Migration uses per-entity transactions | Scope 3, Task 2 | Script uses `with session.begin_transaction() as tx:` per entity |
| D8 | Migration asserts pre/post beat count equality | Scope 3, Task 2 | Script prints and compares total beat count before/after |
| D9 | Migration checks for orphaned beats | Scope 3, Task 5 | `MATCH (b:NarrativeBeat) WHERE NOT ()-[:HAS_BEAT]->(b)` returns 0 |
| D10 | All polygons are valid (Shapely `is_valid`) | Scope 2, Task 5 | Verification command 4 checks every Area's polygon |
| D11 | All polygons are closed (first vertex = last vertex) | Scope 2, Task 2 | `coords_to_wkt` auto-closes; unit test verifies |
| D12 | Spatial utility uses `covers()` not `contains()` for boundary inclusion | Scope 4, Task 1 | Unit test for boundary point |
| D13 | Overpass responses cached to `data/paris/boundaries/` | Scope 2, Task 2 | Cache files exist after first run; script works offline from cache |
| D14 | Data inventory updated with Area node type | Scope 1 | Document Area properties and retention in appropriate location |

---

## Summary

| Scope | Est. Sessions | Files Created | Files Modified |
|-------|---------------|---------------|----------------|
| 1: Area CRUD Foundation | 1 | `tests/test_area_crud.py` | `src/schema/definitions.py`, `src/api/models/nodes.py`, `src/api/models/edges.py`, `src/api/crud/nodes.py`, `src/api/crud/edges.py`, `src/api/routes/edges.py`, `tests/test_definitions.py` |
| 2: Paris Area Hierarchy | 1–2 | `src/utils/__init__.py`, `src/utils/spatial.py`, `data/paris/areas.json`, `scripts/create_paris_areas.py` | `requirements.txt` |
| 3: POI-to-Area Migration | 1–2 | `scripts/migrate_pois_to_areas.py` | — |
| 4: POI Containment Assignment | 1 | `scripts/assign_poi_containment.py`, `tests/test_spatial.py` | — |

Total: 4–6 sessions, 8 new files, 8 modified files.
