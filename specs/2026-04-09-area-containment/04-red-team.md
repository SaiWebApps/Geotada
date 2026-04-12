# Red Team: Area Nodes with Spatial Containment

**Date:** 2026-04-10
**Thinking mode:** Adversarial reviewer — "What breaks?"
**Spec:** [02-spec.md](02-spec.md)
**Scopes:** [03-scopes.md](03-scopes.md)

---

## 1. Blockers

### B1 — Neo4j cannot store nested lists as node properties — RESOLVED

The spec defines `boundary` as a "list of `[lat, lng]` pairs" (e.g., `[[48.85, 2.34], [48.86, 2.34], ...]`). **Neo4j properties must be homogeneous arrays of primitive types.** Nested lists like `[[Float, Float], ...]` are rejected at write time.

**Where:** Spec `02-spec.md` Inputs §1, Constraints §4, all Scope 2 verification commands.

**Resolution: Store boundary as a WKT string.**

Research confirms WKT (Well-Known Text) is the standard approach for polygon storage in Neo4j (see Neo4j Spatial plugin, community best practices, and William Lyon's congressional boundaries example). The boundary property becomes a single string like `"POLYGON((2.34 48.85, 2.35 48.86, ...))"`.

Why WKT over alternatives:
- **Standard format** — understood by Shapely (`shapely.wkt.loads()`), Turf.js, and every GIS tool. Zero custom parsing code.
- **Human-readable** — inspectable in Neo4j Browser, unlike flattened float lists or binary.
- **No plugin required** — stored as a plain string property. Containment checks happen in Python with Shapely at ingest time, not in Cypher.
- **Tiny footprint** — a 15-vertex polygon is ~200 characters.
- **Alternatives considered and rejected:**
  - Flattened float list: valid in Neo4j, but loses semantic clarity and requires stride convention.
  - JSON string: works but adds a parsing layer with no advantage over the geospatial standard.
  - `Point[]` (list of Point values): Neo4j supports this type, but Cypher has no polygon operations on it.
  - neo4j-spatial plugin: supports RTree polygon indexing, but adds operational complexity and plugin dependency for a feature we don't need (containment is precomputed).

**Impact on spec:** Update `boundary` type from "list of coordinate pairs" to "WKT POLYGON string." Pydantic model accepts coordinate pairs as input and converts to WKT on write. Serializer returns WKT string as-is (callers parse with their GIS library of choice).

## 2. Implementation Notes (formerly Blockers B2, B3)

These are known implementation tasks with clear solutions — not blockers requiring decisions.

### I1 — Compound MERGE key for Area nodes

The CRUD layer (`src/api/crud/nodes.py:68-138`) needs an `elif label == "Area"` branch with `MERGE (n:Area {name: $name, area_type: $area_type, city_name: $city_name})`. Follows the existing POI/NarrativeBeat pattern. Must also convert `centroid_lat`/`centroid_lng` to a GeoPoint, same as POI's `latitude`/`longitude` handling.

### I2 — WITHIN in edge MERGE list

`src/api/crud/edges.py:93` — add `"WITHIN"` to the `use_merge` tuple. One-line change.

---

## 3. Risks

### R1 — Migration data loss (medium likelihood, high impact)

Scope 3 deletes POI nodes after transferring beats. If the migration script fails partway through (e.g., after deleting a POI but before creating the Area's HAS_BEAT edge), beats are orphaned or lost. There is no backup step in the scope.

**Mitigation:** Add a pre-migration step: `CALL apoc.export.cypher.all("backup.cypher", {})` or a Neo4j dump. Alternatively, verify beat counts before AND after within a single transaction. The scope's verification command #5 acknowledges this ("compare against pre-migration count") but doesn't automate the before/after comparison.

### R2 — Les Halles beat assignment ambiguity (medium likelihood, medium impact)

The spec says "existing beats about the historical neighborhood move to the Area" and a new Forum des Halles POI is created. But the existing Les Halles POI may have beats that reference both the neighborhood *and* the modern Forum. Who decides which beats go where?

**Mitigation:** Read the actual Les Halles beats before writing the migration script. If any beats are ambiguous, flag them for manual assignment rather than auto-assigning.

### R3 — Overpass API rate limiting / data availability (low likelihood, medium impact)

Scope 2 depends on OSM Overpass API for boundary polygons. Overpass has no formal SLA, can rate-limit, and some sub-area boundaries (e.g., informal neighborhoods like "Latin Quarter") may not have clean `admin_boundary` relations in OSM.

**Mitigation:** Cache Overpass responses to local JSON files so the scope can be re-run without re-fetching. For neighborhoods without OSM boundaries, fall back to manually defined polygons with a source annotation (and document the deviation from the "never hand-drawn" constraint).

### R4 — No database-level compound uniqueness constraint (low likelihood, medium impact)

MERGE on `(name, area_type, city_name)` prevents duplicates through the CRUD layer, but there is no Neo4j constraint enforcing this. If any code path bypasses the CRUD (e.g., a Cypher script, a seed file, or a future migration), duplicates can be silently created.

**Mitigation:** Neo4j Community Edition supports single-property uniqueness constraints only. Neo4j Enterprise supports composite constraints. Document this gap. If on Enterprise, add the composite constraint. If on Community, accept the risk and add a periodic audit query.

---

## 4. Open Questions — All Resolved

### Q1 — Which Neo4j edition is running? ✅ RESOLVED

Community Edition (`image: neo4j:5` in `docker-compose.yml`). Composite uniqueness constraints are Enterprise-only. Accept MERGE-only protection — the compound MERGE key `(name, area_type, city_name)` is sufficient since all writes go through the CRUD layer.

### Q2 — WITHIN label validation ✅ RESOLVED

Add source/target label validation for WITHIN edges: source must be `POI` or `Area`, target must be `Area`. Follows the existing TAGGED_WITH validation pattern in `src/api/routes/edges.py:64-74`. This is standard input validation at the boundary — the pipeline will bulk-create WITHIN edges, and a bug without validation would silently pollute the graph.

### Q3 — WITHIN cycle detection ✅ RESOLVED — DEFERRED

Deferred for MVP. Cycles can't happen organically — only the pipeline and manual curation create WITHIN edges (no end-user input). The hierarchy is shallow (max 3 levels) and manually curated. If needed later, a periodic audit query (`MATCH path=(a:Area)-[:WITHIN*]->(a) RETURN path`) catches any cycles.

---

## 5. Codebase Conflicts

### C1 — Boundary serialization (resolved by WKT decision)

With the WKT string approach (see B1 resolution), `_serialize_props` handles boundary correctly as-is — it's a plain string, no special handling needed. The API returns the WKT string directly.

### C2 — centroid requires the same spatial handling as POI.location

`src/api/crud/nodes.py:77-107` has POI-specific code to convert `latitude`/`longitude` into a `point()` call. Area's `centroid_lat`/`centroid_lng` needs identical treatment in the new `elif label == "Area"` CRUD branch. If this is missed, centroid will be stored as two floats instead of a GeoPoint, and AC-8 (spatial proximity query) will fail silently.

### C3 — `src/schema/definitions.py` and `src/schema/constraints.py` need updates

New entries needed:
- `LABELS` list: add `"Area"`
- `RELATIONSHIP_TYPES` list: add `"WITHIN"`
- `CONSTRAINTS`: add `uniq_area_id` on `Area.id`
- `INDEXES`: add POINT index on `Area.centroid`

These are all additive and follow existing patterns, but if any are missed, the schema will be inconsistent.

### C4 — Pydantic CREATE_MODELS dict needs Area entry

`src/api/models/nodes.py` has a `CREATE_MODELS` dict that maps labels to Pydantic models. Without an `"Area": AreaCreate` entry, `POST /api/v1/nodes/Area` will bypass validation entirely (the route falls through to accepting raw JSON).

---

## 6. North Star Check

### N1 — Explicit boundary conflict: "POI hierarchy (IS_INSIDE relationship deferred)"

`specs/NORTHSTAR.md:65` explicitly lists "POI hierarchy (IS_INSIDE relationship)" under "Will NOT build for MVP." The scope doc (`01-scope.md`) correctly identifies this and says the North Star must be updated before proceeding. The relationship is named `WITHIN` not `IS_INSIDE`, but it's the same concept.

**Action required:** Update `specs/NORTHSTAR.md` to:
1. Remove "POI hierarchy (IS_INSIDE relationship deferred)" from Explicit Boundaries
2. Add "Area nodes with WITHIN containment" to Architectural Commitments
3. Add a pointer to `specs/2026-04-09-area-containment/` in the Pointers table

This must happen before implementation begins — building against a North Star that explicitly forbids this feature is a process violation.

### N2 — Launch city discrepancy

`specs/NORTHSTAR.md:49` says "Launch city: Boston." But this spec is entirely Paris-focused (7 Paris arrondissements, Paris POIs). The memory index records a shift to Paris (2026-04-09). The North Star should be updated to reflect this.

### N3 — Alignment: compound MERGE key supports multi-city scaling

The spec's MERGE key design (`name, area_type, city_name`) directly supports the North Star's Phase 4 goal: "City two live in <6 weeks pipeline work." Good alignment — no conflict here.

---

## 7. Scope Review

### Scope 1: Area CRUD Foundation

- **Boundaries:** Clean. All CRUD infrastructure in one scope.
- **Verification gaps:**
  - Verification command #2 is weak: it re-POSTs the same Area and checks the response, but doesn't actually verify the *count* stays at 1. Command #3 does check the count, but it queries ALL Areas — in a seeded database with other Areas, the assertion `total==1` would fail. **Fix:** Filter the count query by name.
  - No verification of centroid as GeoPoint specifically (AC-8 is listed but not tested in the commands). Add a spatial distance query as a verification command.
  - No verification of WITHIN edge creation (AC-3). The scope lists AC-3 but has no curl command testing WITHIN edge creation. **Must add.**
- **Ordering:** Correct — this must be first.

### Scope 2: Paris Area Hierarchy

- **Boundaries:** Clean scope, but "no AC directly" is a yellow flag. This scope is purely data population with no spec-level acceptance criteria it satisfies independently.
- **Verification gaps:**
  - Command #4 checks `size(a.boundary) < 10` — this will fail depending on boundary storage format (see Blocker B1). If boundary is a flattened list, a 5-vertex polygon has `size = 10` (5 lat + 5 lng), which is NOT < 10, so it passes. If stored as 5 pairs... can't store nested lists. This command needs to be rewritten once B1 is resolved.
  - No verification that boundary polygons are actually valid (e.g., first vertex = last vertex for a closed polygon). A malformed polygon will silently break point-in-polygon in Scope 4.
- **Ordering:** Correct.

### Scope 3: POI-to-Area Migration

- **Boundaries:** Clean, but tightly coupled to Scope 2 (needs arrondissement Areas to exist for WITHIN edges).
- **Verification gaps:**
  - Command #5 ("compare against pre-migration count") is manual — it prints a count but doesn't assert against a known baseline. Should capture the count before migration and assert equality after.
  - No verification that ItineraryItem → POI references (if any exist) are handled. The scope doc (`01-scope.md`) mentions this risk but Scope 3 doesn't address it.
  - No verification of Grands Boulevards migration specifically — it's in the migration list but not in the TAGGED_WITH verification query (command #3 only checks 4 of the 7 migrated entities).
- **Ordering:** Correct.

### Scope 4: POI Containment Assignment

- **Boundaries:** Clean.
- **Verification gaps:**
  - Command #3 checks for orphan POIs (no WITHIN edge). This is a useful check but could produce false positives if any Paris POIs fall outside all arrondissement polygons due to inaccurate boundaries or POIs at the edge of coverage.
  - No verification of the utility function's edge cases: POI exactly on a polygon boundary, POI in overlapping areas (e.g., island + arrondissement), POI with no containing area.
- **Ordering:** Correct. Must be last since it depends on all Areas and migrated POIs existing.
- **Parallelization:** None possible — confirmed, the linear chain is correct.

---

## 8. Best Practices Audit

### A) SECURITY_PRIVACY_PRACTICES.md — All 16 Sections

| # | Section | Verdict | Notes |
|---|---------|---------|-------|
| 1 | Data Classification & Minimization | **Pass** | Area boundaries are geographic metadata, not PII. No new sensitive data types introduced. |
| 2 | Consent & Transparency | **N/A** | No user-facing data collection changes. |
| 3 | Authentication & Authorization | **Pass** | New endpoints follow existing patterns. No auth for MVP per North Star. |
| 4 | Secure Session Management | **N/A** | No session changes. |
| 5 | Secrets & Credentials | **Pass** | No new secrets. Overpass API is unauthenticated. |
| 6 | Encryption | **Pass** | Inherits existing TLS and Neo4j encryption settings. |
| 7 | Logging & Monitoring | **Pass** | No PII in Area node properties. |
| 8 | Data Retention & Deletion | **Pass** | `DELETE /api/v1/nodes/Area` uses DETACH DELETE (removes edges too). Consistent with existing pattern. |
| 9 | Third-Party Risk | **Pass** | OSM Overpass is public, no data sharing. Shapely is a well-maintained open-source library. |
| 10 | Secure Development Lifecycle | **Pass** | This red-team review satisfies threat modeling for this scope. |
| 11 | Input Validation & Output Encoding | **Fail** | See B-Input below. `area_type` enum validation, `boundary` vertex count validation (5-15), and coordinate range validation must be enforced in the Pydantic model. The spec mentions API-layer validation for vertex count but no Pydantic model is defined yet. |
| 12 | Infrastructure & Network Security | **N/A** | No infra changes. |
| 13 | Privacy by Design | **Pass** | No user data involved in Area nodes. |
| 14 | Incident Response | **N/A** | No changes to incident handling. |
| 15 | Testing & Verification | **Fail** | See B-Testing below. Migration scope lacks automated before/after beat count assertion. |
| 16 | Compliance & Documentation | **Fail** | New `Area` data type needs an entry in the data inventory per §16 ("New data fields require an update to the data inventory and retention policy"). |

### B) Best Practices Library — Domain-Specific

#### Security

| Item | Verdict | Notes |
|------|---------|-------|
| Input validation at boundary | **Fail** | `area_type` must be validated as enum (not arbitrary string). `boundary` must validate: (a) vertex count 5-15, (b) lat range -90/+90, (c) lng range -180/+180, (d) polygon is closed (first = last vertex). None of these are in the spec's acceptance criteria. Must add to Pydantic model. |
| Parameterized queries | **Pass** | Neo4j driver parameterization used throughout. No f-string interpolation of user input (labels are validated against known list in schema). |
| API rate limiting | **N/A** | No rate limiting exists for any endpoint. Not a regression. |

#### Performance

| Item | Verdict | Notes |
|------|---------|-------|
| POINT index on centroid | **Pass** | Spec explicitly includes this. |
| Precomputed containment | **Pass** | WITHIN edges avoid runtime polygon queries. Good design. |
| Unbounded traversals | **Pass** | Containment hierarchy is shallow (max 3 levels: sub-area → district → city). No risk of unbounded traversal. |

#### Data Integrity

| Item | Verdict | Notes |
|------|---------|-------|
| Migration atomicity | **Fail** | No transaction wrapping specified. Each POI migration (delete old + create Area + transfer beats) should be a single Neo4j transaction. If any step fails, the entire migration for that entity should roll back. |
| Beat count verification | **Fail** | Automated before/after comparison needed, not manual print-and-compare. |
| WITHIN edge semantic validation | **Fail** | No validation that WITHIN edges connect only (POI|Area) → Area. Generic edge route allows any label combination. Should add validation similar to TAGGED_WITH's parent-lens check. |

#### Accessibility

**N/A** — Infrastructure work with no user-facing UI.

#### UX

**N/A** — Infrastructure work.

---

## Summary of Required Actions Before Implementation

| # | Type | Action | Status |
|---|------|--------|--------|
| B1 | Resolved | Boundary stored as WKT string (standard geo format, parsed by Shapely) | Done |
| I1 | Impl task | Add `elif label == "Area"` CRUD branch with compound MERGE + centroid GeoPoint | Plan stage |
| I2 | Impl task | Add `"WITHIN"` to edge MERGE tuple | Plan stage |
| N1 | North Star | Update NORTHSTAR.md — move Area/WITHIN from deferred to active | Done |
| N2 | North Star | Update launch city from Boston to Paris | Done |
| Q1 | Resolved | Community Edition — MERGE-only protection, no composite constraint | Done |
| Q2 | Resolved | Add WITHIN label validation (source=POI|Area, target=Area) | Plan stage |
| Q3 | Resolved | Cycle detection deferred for MVP | Done |
| S1 | Scope fix | Scope 1: add WITHIN edge creation verification command | Before plan |
| S2 | Scope fix | Scope 1: add spatial proximity verification for AC-8 | Before plan |
| S3 | Scope fix | Scope 2: rewrite boundary validation for WKT format | Before plan |
| S4 | Scope fix | Scope 3: add automated beat count before/after assertion | Before plan |
| S5 | Scope fix | Scope 3: wrap each entity migration in a transaction | Before plan |
| V1 | Impl task | Pydantic model with area_type enum, WKT boundary validation, coordinate range | Plan stage |
| V2 | Impl task | WITHIN semantic validation (source=POI|Area, target=Area) | Plan stage |
| D1 | Doc | Update data inventory with Area node type | During impl |
