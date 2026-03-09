# Scope: Workbench Upload & Beat Conflict Resolution

**Date:** 2026-03-07
**Status:** Approved

---

## What we're building

- **Upload button** on the Editorial Review Workbench that batch-uploads all reviewed POIs and beats to Neo4j via the existing REST API
- **Upload progress feedback** showing real-time status as each POI/beat/relationship is created
- **Success confirmation** screen summarizing what was uploaded (counts of POIs created, POIs matched, beats created, relationships linked)
- **Beat conflict resolution overlay** that detects when a beat collides with an existing beat on the same POI (same lens or matching script content) and lets the editor overwrite, skip, or merge field-by-field
- **Idempotent POI handling** — create net-new POIs, match existing ones by name, and attach new beats under them either way

## Why

This completes step 4 ("Commit to Live") of the Book-to-Street pipeline — the critical gap between editorial review and live content in the graph database. Without it, reviewed content sits in the workbench with nowhere to go.

## What we're NOT building

- No bulk delete or rollback of uploads
- No version history or undo for conflict resolutions
- No selective per-item upload (batch only for v1)
- No changes to the review/validation flow itself — only adding upload after review is complete
- No new API endpoints unless the existing CRUD can't support the conflict detection queries

## What already exists

- `frontend/review.html` — Editorial Review Workbench with "Ready for upload" banner (no upload logic)
- `src/api/routes/nodes.py` — POST/PUT/DELETE for POI and NarrativeBeat (409 on constraint violations)
- `src/api/routes/edges.py` — POST for HAS_BEAT, TAGGED_WITH relationships
- `src/api/crud/nodes.py` — create/read/update/delete with Neo4j driver
- Unique constraints on POI.name and NarrativeBeat.id; MERGE-based seeding pattern in `src/seed/locations.py`

## Dependencies or risks

- **Beat conflict detection needs a new query** — the current API doesn't support "find beats on this POI with this lens." We'll likely need a lookup endpoint or a compound query to detect collisions before upload.
- **No transaction batching** — the current API is one-node-per-request. A large upload (100 POIs × multiple beats) could be slow and leave partial state if it fails mid-batch. For v1 this is acceptable but worth noting.
- **Review workbench data is client-side** — the reviewed POI/beat data lives in the browser. If the user closes the tab before uploading, it's lost. This is an existing limitation, not something we're fixing here.
