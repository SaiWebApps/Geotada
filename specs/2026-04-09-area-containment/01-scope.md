# Scope: Area Nodes with Spatial Containment

**Date:** 2026-04-09
**Status:** Awaiting approval
**Depends on:** North Star update (move "POI hierarchy" from deferred to active)

---

## What we're building

- **New `Area` node type** in Neo4j with properties: `id`, `name`, `area_type` (enum: `city | district | neighborhood | island | corridor`), `boundary` (simplified polygon stored as list of coordinate pairs, 5–15 vertices), `centroid` (GeoPoint for proximity queries), `short_description`, `created_at`.
- **New `WITHIN` relationship type**: `(:POI)-[:WITHIN]->(:Area)` and `(:Area)-[:WITHIN]->(:Area)` for hierarchical containment. Precomputed at ingest, not computed at query time. Follows the Neo4j best practice of storing spatial containment as relationships.
- **`(:Area)-[:HAS_BEAT]->(:NarrativeBeat)` support**: Areas can have beats (the Île de la Cité has 4 beats about the island itself). Reuses the existing `HAS_BEAT` relationship type.
- **Migration of ~10 misclassified Paris POIs to Area nodes**: Île de la Cité, Île Saint-Louis → `island`. Rue Mouffetard, Rue Visconti, Rue Chanoinesse, Grands Boulevards → `corridor`. Les Halles → `neighborhood` (pending curator confirmation). Their existing beats and relationships are moved, not duplicated.
- **POINT index on Area.centroid** for spatial proximity queries. No native polygon index in Neo4j — containment uses the precomputed WITHIN relationships.
- **REST API endpoints**: CRUD for Area nodes and WITHIN edges, following existing patterns in `src/api/routes/nodes.py` and `src/api/routes/edges.py`.
- **A Python utility for point-in-polygon checks** to support the ingest pipeline (given a lat/lon, determine which Areas contain it and create WITHIN relationships).

## Why

The tour builder (Phase 2) needs to know whether a POI is a stoppable destination or a geographic setting/corridor. It also needs to gather beats from the *area* the user is walking through, not just from individual POIs. Without Area nodes, the Île de la Cité's 4 beats about the island itself have nowhere correct to live — they're currently on a fake POI with a single lat/lon for a 600m island. The containment hierarchy also unblocks "give me a tour of the 5th arrondissement" and "all POIs in the Latin Quarter" queries, which are core to the on-demand tour product.

The `area_type` enum is modeled after Google Maps' typed place hierarchy and OpenStreetMap's `admin_level` system for France, adapted to Neo4j's precomputed-relationship pattern.

## What we're NOT building

- **Beat metadata enrichment** (entities, time_period, narrative_function, sensory_anchor) — separate spec, written alongside this one.
- **Pipeline skill updates** (`poi-generate`, `poi-gravity`, `poi-geocode`) to classify new POIs as Area vs POI at extraction time — follow-up scope after the data model is proven.
- **Full GeoJSON polygon support** — we use simplified polygons (5–15 vertex coordinate pairs), not precise GeoJSON. Sufficient for "is this POI roughly in this area" checks; not for cartographic rendering.
- **Polygon rendering in the frontend** — the frontend/workbench doesn't need to draw area boundaries yet.
- **City-level Area creation for cities beyond Paris** — we create the Paris city Area and its arrondissements/neighborhoods. Other cities come with their content pipelines.
- **Native Neo4j spatial polygon indexing** — Neo4j doesn't support polygon indexes natively. Containment is precomputed into WITHIN relationships. Point-in-polygon checks happen in Python at ingest time, not in Cypher at query time.

## What already exists

- **Neo4j schema** (`src/schema/definitions.py`): 7 node types, 11 relationship types, POINT index on POI.location. No Area or WITHIN concept yet.
- **CRUD layer** (`src/api/crud/nodes.py`): Generic node CRUD with MERGE-on-name for POI, MERGE-on-script_body for NarrativeBeat. Supports `force_create`. All other labels use CREATE.
- **Edge CRUD** (`src/api/crud/edges.py`): MERGE for HAS_BEAT and TAGGED_WITH, CREATE for everything else.
- **REST API** (`src/api/routes/`): Full CRUD for nodes and edges, schema introspection, graph visualization, POI-beats convenience endpoint.
- **Graph route** (`src/api/routes/graph.py`): Returns all nodes/edges for vis.js. Will need to include Area nodes.
- **The ~10 misclassified POIs** with their beats and TAGGED_WITH relationships — must be migrated, not lost.
- **Tour-builder design doc** (`Docs/tour-builder/design.md`): Documents POI roles, beat selection, and open question #8 about `stop` vs `setting` vs `walk_by_only`.
- **`make setup`** pipeline: applies schema constraints/indexes and seeds initial data. Must include Area constraints/indexes.

## Dependencies or risks

1. **North Star conflict.** The North Star explicitly defers "POI hierarchy (IS_INSIDE relationship)." Must update the North Star to move this to active before proceeding. The tour-builder design work surfaced this as a real blocker, not premature.
2. **Migration data integrity.** When converting a POI to an Area, we must preserve all beat relationships (HAS_BEAT + TAGGED_WITH chains) and not break any existing ItineraryItem → POI references if they exist. The migration script needs verification steps.
3. **Edge case: Les Halles.** The historical "Belly of Paris" is a neighborhood/setting, but the Forum des Halles is a stoppable destination today. The migration may need to split this into an Area (the neighborhood) + a POI (the Forum). Requires curator call.
4. **Polygon data sourcing.** ✅ **Resolved:** Use OpenStreetMap via the Overpass API as the universal source for administrative boundary polygons in any city. Simplify with Shapely (Douglas-Peucker algorithm) to 5–15 vertices. Add `shapely` to Python dependencies. All boundaries must be sourced from verified OSM data — never assumed or invented. The approach is city-agnostic: Overpass queries work for any city worldwide.
5. **MERGE behavior for Area nodes.** ✅ **Resolved:** Area nodes MERGE on compound key `(name, area_type, city_name)` to be multi-city safe from day one. The business model depends on rapid scaling to new cities via content consumption — a single-city MERGE key would create silent data corruption when a second city is added. This is a core data model decision, not deferrable.

## Best practices domains touched

- **Data integrity** — migration of existing nodes/relationships
- **Performance** — spatial index on centroids, precomputed containment relationships
- **Security** — new API endpoints need the same access patterns as existing ones (no auth for MVP per North Star)
