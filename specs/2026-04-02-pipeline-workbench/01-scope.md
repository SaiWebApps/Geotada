# Scope — Content Pipeline Workbench

**Date:** 2026-04-02
**Status:** Awaiting approval

---

## What we're building

- A new single-page HTML workbench (`frontend/pipeline.html`) that visualizes city content from Neo4j and manages upload of pipeline-produced JSON export files
- **City selector/creator:** On load, user selects an existing city or creates a new one by uploading an initial export JSON (produced by `export-validate` skill)
- **Map view:** Leaflet map showing all POIs in the selected city. Marker size scales by `importance_tier` (gravity). Marker labels show beat count. Clicking a marker selects the POI.
- **POI/beat viewer panel:** When a POI is selected, shows POI metadata (name, description, gravity, coordinates, trigger radius, duration) and a list of its beats (script_body, lens label, duration_sec, fact_check_status)
- **Chunk upload:** User uploads a new export JSON chunk. The workbench matches POIs by name against Neo4j, creates new POIs, adds new beats, and highlights affected POIs on the map for the current session. Conflict handling reuses the proven proximity-match + name-similarity approach from the existing `review.html` workbench.

## Why

Phase 1 milestone requires 100+ POIs with beats uploaded to Neo4j. The Claude Code skills pipeline produces export-ready JSON files. This workbench bridges the gap — letting the user see what's in the database, upload new content, and verify it landed correctly. Without it, the user has no visibility into the growing content library.

## What we're NOT building

- No editing of POI fields or beat content in the browser (that's done in Claude Code via skills)
- No book upload or pipeline execution from the page (user runs skills in Claude Code, uploads the export JSON here)
- No multi-user auth or cloud deployment (local only, single user)
- No audio generation or playback
- No tour routing or preview
- No connection to Neo4j Cloud (local Neo4j only for now)

## What already exists

- **`frontend/review.html`** (4,567 lines) — The existing editorial workbench with Leaflet map, POI worklist, conflict resolution (proximity matching + name similarity), beat-by-beat upload to Neo4j via FastAPI. Dark theme, DM Sans/JetBrains Mono fonts, polished UI. **Reuse:** design system (CSS variables, card layouts), conflict detection logic (`findProximityMatches`, `nameSimilarity`, `mergeIncomingIntoDbPois`), Neo4j upload flow.
- **`frontend/editor/index.html`** (1,574 lines) — Graph editor with direct Neo4j visualization. **Reuse:** nothing directly, but confirms the FastAPI → Neo4j connection works.
- **FastAPI backend** (`src/api/`) — Full CRUD for POI, NarrativeBeat, Lens nodes and all 11 relationship types. Handles coordinate conversion to Neo4j POINT type. **Reuse:** all node creation and relationship endpoints.
- **Export JSON format** — `data/{city}/export/{chunk}.json` — POIs with nested beats, clean schema fields, `parent_poi` for CONTAINS_POI relationships.

## Dependencies or risks

- **FastAPI backend must be running** — the page talks to `localhost:8000`. If the backend isn't up, nothing works. The existing `make all` bootstrap handles this.
- **Neo4j must be seeded with Lens nodes** — beats create TAGGED_WITH relationships to Lens nodes. If lenses aren't seeded, upload fails. The existing `seed_lenses()` in `src/seed/lenses.py` handles this but needs updating for the new 8-parent/21-child hierarchy.
- **Export JSON format is the contract** — if `export-validate` changes its output format, the upload logic breaks. This is a tight coupling by design.
- **Beat dedup on upload** — the skills handle dedup during extraction, but if the user accidentally uploads the same chunk twice, beats would be duplicated in Neo4j. The workbench should detect and prevent this (check if a beat with identical `script_body` already exists at a POI).

## Best practices touched

- **Security:** File upload validation (JSON only, size limit), no auth needed (local only)
- **Performance:** Large city data (500+ POIs) needs efficient map rendering (marker clustering)
- **UX:** Clear upload feedback, visual diff of what changed, no destructive actions without confirmation
