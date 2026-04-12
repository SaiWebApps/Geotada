# Spec: Area Nodes with Spatial Containment

**Date:** 2026-04-09
**Scope:** [01-scope.md](01-scope.md)
**Flavor:** Contract Spec (infrastructure)

---

## Purpose

Introduce an `Area` node type and `WITHIN` relationship to Neo4j so the graph can distinguish stoppable destinations (POI) from geographic settings (Area), store hierarchical containment (city → district → neighborhood), and attach beats to areas — not just points. Unblocks tour-builder queries like "all POIs in the 5th arrondissement" and "beats about Île de la Cité the island."

---

## Inputs

1. **Area creation payload:**
   - `name` (string, required) — e.g., "5th Arrondissement"
   - `area_type` (enum: `city | district | neighborhood | island | corridor`, required)
   - `city_name` (string, required) — the parent city for multi-city MERGE safety, e.g., "Paris"
   - `boundary` (list of `[lat, lng]` pairs, 5–15 vertices, required) — simplified polygon from OSM/Overpass
   - `centroid_lat`, `centroid_lng` (floats, required) — converted to Neo4j GeoPoint
   - `short_description` (string, optional)

2. **WITHIN edge payload:**
   - `source` — `{label: "POI"|"Area", id: "<uuid>"}` (the contained entity)
   - `target` — `{label: "Area", id: "<uuid>"}` (the container)

3. **Migration input:** The 7 misclassified POIs identified in the Paris dataset (Île de la Cité, Île Saint-Louis, Les Halles, Rue Mouffetard, Rue Visconti, Rue Chanoinesse, Grands Boulevards) with their existing beats and TAGGED_WITH edges.

4. **Polygon data:** Fetched from OpenStreetMap Overpass API, simplified to 5–15 vertices via Shapely.

---

## Outputs

1. **Area nodes** in Neo4j with properties: `id` (UUID), `name`, `area_type`, `city_name`, `boundary` (list of coordinate pairs), `centroid` (GeoPoint), `short_description`, `created_at`.

2. **WITHIN edges** connecting: `(:POI)-[:WITHIN]->(:Area)` and `(:Area)-[:WITHIN]->(:Area)`.

3. **HAS_BEAT edges** from Area nodes to their NarrativeBeats (reuses existing relationship type).

4. **REST API** — full CRUD for Area nodes and WITHIN edges via existing generic endpoints (no new route files).

5. **Point-in-polygon utility** — Python function that, given a lat/lon and a list of Area boundaries, returns which Areas contain that point. Used at ingest time to create WITHIN edges.

---

## Constraints

- **MERGE key:** Area nodes MERGE on `(name, area_type, city_name)` — compound key for multi-city safety. This is non-negotiable; the business model depends on city-by-city scaling.
- **WITHIN is MERGE:** WITHIN edges use MERGE (idempotent), matching the HAS_BEAT/TAGGED_WITH pattern.
- **No runtime polygon queries:** All containment is precomputed into WITHIN relationships at ingest. Point-in-polygon checks happen in Python, not Cypher.
- **Boundary vertex count:** 5–15 vertices per polygon. Reject boundaries outside this range at the API validation layer.
- **Polygon sourcing:** All boundaries sourced from OSM Overpass API. Never assumed, invented, or hand-drawn.
- **Migration is destructive:** Old POI nodes are deleted after their beats and relationships are verified on the new Area node. No duplicate nodes.
- **Graph visualization:** Area nodes must appear in the existing `GET /graph` endpoint with no additional code (the generic `MATCH (n)` query handles it).

---

## Acceptance Criteria

1. **Works when** creating an Area node via `POST /api/v1/nodes/Area` with valid payload: returns 201, node has UUID `id`, `centroid` stored as GeoPoint, `boundary` stored as coordinate list, `city_name` present.

2. **Works when** creating the same Area twice (same name + area_type + city_name): MERGE returns the existing node without duplication. Properties are updated.

3. **Works when** creating a WITHIN edge via `POST /api/v1/edges/WITHIN` between a POI and an Area: returns 201, edge has UUID `id`. Creating the same WITHIN edge again does not duplicate it (MERGE behavior).

4. **Works when** querying hierarchical containment: `MATCH (p:POI)-[:WITHIN]->(n:Area)-[:WITHIN]->(a:Area) WHERE a.name = "4th Arrondissement"` returns POIs nested inside neighborhoods/islands inside the 4th.

5. **Works when** an Area has beats: `MATCH (a:Area {name: "Île de la Cité"})-[:HAS_BEAT]->(b:NarrativeBeat)` returns the island's own 5 beats with their TAGGED_WITH lens edges intact.

6. **Works when** the 7 migrated POIs no longer exist as POI nodes: `MATCH (n:POI) WHERE n.name IN ["Île de la Cité", "Île Saint-Louis", ...]` returns zero results. Their beats now hang off corresponding Area nodes.

7. **Works when** the point-in-polygon utility correctly classifies: given Notre-Dame's coordinates (48.8530, 2.3499), it returns both "Île de la Cité" (island) and "4th Arrondissement" (district).

8. **Works when** Area.centroid supports spatial proximity queries: `MATCH (a:Area) WHERE point.distance(a.centroid, point({latitude: 48.8566, longitude: 2.3522, srid: 4326})) < 2000 RETURN a.name` returns nearby areas.

---

## Concrete Output Example

After full implementation, this Cypher query:

```cypher
MATCH (p:POI {name: "Notre-Dame Cathedral"})-[:WITHIN]->(island:Area)-[:WITHIN]->(arr:Area)-[:WITHIN]->(city:Area)
RETURN p.name, island.name, island.area_type, arr.name, arr.area_type, city.name, city.area_type
```

Returns:

| p.name | island.name | island.area_type | arr.name | arr.area_type | city.name | city.area_type |
|--------|-------------|------------------|----------|---------------|-----------|----------------|
| Notre-Dame Cathedral | Île de la Cité | island | 4th Arrondissement | district | Paris | city |

And this query for area-level beats:

```cypher
MATCH (a:Area {name: "Île de la Cité"})-[:HAS_BEAT]->(b:NarrativeBeat)-[:TAGGED_WITH]->(l:Lens)
RETURN b.script_body, l.display_label
```

Returns the island's 5 beats with their lens tags — content that was previously on a misclassified POI node.

---

## Downstream Dependencies

1. **Tour builder (Phase 2):** Uses WITHIN traversals to gather beats from the area the user is walking through, not just individual POIs. Uses `area_type` to distinguish stoppable destinations from settings.
2. **Content pipeline skills:** Follow-up scope to classify POI vs Area at extraction time and auto-assign WITHIN edges using postal codes and chunk metadata.
3. **On-demand tour queries:** "Give me a tour of the 5th arrondissement" becomes a single graph traversal starting from an Area node.

---

## Open Questions — Resolved

1. **Les Halles split:** ✅ Split now. Create Area node (the neighborhood "Les Halles") + POI node (Forum des Halles, the stoppable destination). Existing beats about the historical neighborhood move to the Area; a new POI for the modern Forum is created.
2. **Arrondissement coverage:** ✅ Only the 7 covered by the consumed book (1st–7th). Do not create empty Area nodes — empty data has caused problems before. Arrondissements are created as their content is ingested.
