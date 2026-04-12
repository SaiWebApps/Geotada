# Contract Spec — Content Pipeline Workbench

**Date:** 2026-04-02
**Status:** Awaiting approval
**Scope:** [01-scope.md](01-scope.md)

---

## 1. Purpose

A browser-based dashboard (`frontend/pipeline.html`) that reads city content from Neo4j, displays it on a map with beat density and gravity indicators, and ingests export JSON chunks produced by the Claude Code pipeline skills. Unblocks the Phase 1 milestone by giving the user visibility into the growing content library and a reliable upload path from pipeline to database.

## 2. Inputs

- **Export JSON chunks** — Files from `data/{city}/export/`, produced by `export-validate` skill. Each file is a JSON array of POIs with nested beats. Format:
  ```
  [{name, short_description, latitude, longitude, importance_tier, trigger_radius,
    typical_duration_min, kid_friendly, name_variations, parent_poi, beats: [{
      script_body, lens, duration_sec, kid_friendly, physical_cues,
      source_passage, source_attribution, fact_check_status
    }], _meta}]
  ```
- **Neo4j database** — via FastAPI at `localhost:8000`. Existing POI, NarrativeBeat, Lens nodes and relationships.

## 3. Outputs

- **POI nodes** created/matched in Neo4j via `POST /api/nodes/POI`
- **NarrativeBeat nodes** created in Neo4j via `POST /api/nodes/NarrativeBeat`
- **PLAYS_BEAT relationships** (POI → Beat) via `POST /api/edges/PLAYS_BEAT`
- **TAGGED_WITH relationships** (Beat → Lens) via `POST /api/edges/TAGGED_WITH`
- **CONTAINS_POI relationships** (POI → POI) via `POST /api/edges/CONTAINS_POI` where `parent_poi` is set — deferred if parent not yet in DB

## 4. Constraints

- Single static HTML file — no build step, no bundler, no framework
- Connects to FastAPI backend at `localhost:8000` — backend must be running
- Lens nodes must already be seeded in Neo4j (8 parents + 21 children)
- File upload capped at 5MB per chunk (prevents accidental full-dump upload)
- No destructive operations — cannot delete POIs or beats from the workbench

## 5. Acceptance Criteria

1. **Works when** the user opens `pipeline.html` and sees a city selector listing all cities that have POIs in Neo4j, plus a "New City" option with file upload.
2. **Works when** the user uploads an initial export JSON for a new city and all POIs + beats + relationships are created in Neo4j, with a progress indicator and success/error count.
3. **Works when** the map displays all POIs for the selected city with marker size proportional to `importance_tier` and a label showing beat count per POI.
4. **Works when** clicking a map marker opens the POI detail panel showing: name, short_description, importance_tier, trigger_radius, typical_duration_min, lat/lng, and a scrollable list of beats with script_body, lens label, and duration_sec.
5. **Works when** the user uploads a subsequent export JSON chunk and: new POIs are created, existing POIs are matched by name (exact match first, then name_variations), new beats are added to matched POIs, and duplicate beats (identical script_body at same POI) are skipped with a count shown to the user.
6. **Works when** POIs affected by the latest upload are visually highlighted on the map (distinct marker color/ring) for the duration of the current session.
7. **Works when** the upload summary shows: POIs created, POIs matched, beats added, beats skipped (duplicates), relationships created, and any errors.
8. **Works when** a POI with `parent_poi` set creates a CONTAINS_POI relationship if the parent exists in Neo4j, or logs a warning if the parent is not found (non-blocking).

## 6. Downstream Dependencies

- **Tour builder (future)** — reads POI → Beat → Lens graph from Neo4j to assemble tours at runtime. This workbench populates that graph.
- **Audio generation (future)** — reads `script_body` from NarrativeBeat nodes. Beats must be correctly created with complete text.
- **Mobile app (future)** — triggers beats based on `location` POINT and `trigger_radius`. POIs must have valid coordinates.

## 7. Open Questions

1. **City identification in Neo4j:** POI nodes don't have a `city` field in the current schema. How do we filter POIs by city? Options: (a) add a `city` property to POI nodes, (b) use a bounding box query based on known city coordinates, (c) create a City node with HAS_POI relationships. Which approach?
2. **Lens seeding:** The `seed_lenses()` function still references the old 11-parent/8-child hierarchy. Should updating it be part of this scope or a separate task?
