# Release Notes: Workbench Upload & Beat Conflict Resolution

Technical details for backend and frontend changes introduced in this slice. Intended for team members who own the affected code.

---

## Backend Change: New Graph Traversal Endpoint

### What
A new read-only endpoint: `GET /graph/poi/{poi_name}/beats`

### Why
The upload feature needs to detect beat conflicts before writing to Neo4j. It must know which beats (and their lens tags) already exist on a given POI. No existing endpoint supports this — the current CRUD endpoints would require 3+ full-table scans per POI, joined client-side.

### How it works
Runs a single Cypher query that traverses `POI → HAS_BEAT → NarrativeBeat → TAGGED_WITH → Lens`:

```cypher
MATCH (p:POI {name: $name})-[:HAS_BEAT]->(b:NarrativeBeat)-[:TAGGED_WITH]->(l:Lens)
WHERE b.active_status = "active"
RETURN b, l.name AS lens_slug
```

### Response shape
```json
{
  "poi_name": "Old North Church",
  "beats": [
    {
      "id": "uuid",
      "script_body": "...",
      "version": 1,
      "active_status": "active",
      "duration_sec": 60,
      "lens_slug": "hidden_history"
    }
  ]
}
```

### Where to add it
- Route: `src/api/routes/graph.py` (new file, or add to existing routes)
- No CRUD changes needed — this is a read-only traversal

---

## Backend Change: MERGE-Based Node and Edge Creation

### What
Switch `create_node()` and `create_edge()` from `CREATE` to `MERGE` for POI and NarrativeBeat operations.

### Why
The upload feature needs **retry safety**. If an upload fails halfway through (e.g., network error after creating 30 of 50 POIs), the editor needs to retry without creating duplicates. Currently, `CREATE` always makes a new node — retrying would produce duplicate POIs and beats. `MERGE` checks if a matching node already exists first: if it does, it updates the properties; if not, it creates it.

### What changes

**`src/api/crud/nodes.py` — `create_node()` function (lines 68-101):**

Current behavior:
```python
query = f"CREATE (n:{label}) SET n.id = randomUUID(), ..."
```

New behavior for POI:
```python
query = """
MERGE (n:POI {name: $name})
SET n.id = coalesce(n.id, randomUUID()),
    n.created_at = coalesce(n.created_at, datetime()),
    n.location = point({latitude: $lat, longitude: $lng, srid: 4326}),
    ...other properties...
RETURN ...
"""
```

New behavior for NarrativeBeat:
```python
query = """
MATCH (p:POI {name: $poi_name})
MERGE (p)-[:HAS_BEAT]->(b:NarrativeBeat {script_body: $script_body})
SET b.id = coalesce(b.id, randomUUID()),
    b.created_at = coalesce(b.created_at, datetime()),
    b.version = $version,
    b.active_status = $active_status,
    ...other properties...
RETURN ...
"""
```

Key detail: `coalesce(n.id, randomUUID())` ensures existing nodes keep their original ID and timestamp. Only truly new nodes get a fresh UUID.

**`src/api/crud/edges.py` — `create_edge()` function (lines 72-109):**

Same pattern — switch `CREATE` to `MERGE` for `HAS_BEAT` and `TAGGED_WITH` relationships.

### What doesn't change
- All other CRUD behavior (read, update, delete) stays the same
- Constraint handling and HTTP response formats stay the same
- The seeding code (`src/seed/locations.py`, `src/seed/narratives.py`) already uses this exact MERGE pattern — this change brings the API in line with seeding

### Reference
The seeding code is the proven pattern to follow:
- `src/seed/locations.py:10-19` — POI MERGE by name
- `src/seed/narratives.py:14-26` — Beat MERGE by script_body, with lens linking

---

## Frontend Change: beforeunload Warning

### What
A `beforeunload` event listener on `frontend/review.html` that warns the editor before closing the tab if there are reviewed but not-yet-uploaded POIs.

### Why
Reviewed POI/beat data lives entirely in the browser (client-side). If the editor closes the tab after reviewing 50 POIs but before uploading, all work is lost. This is a one-line safety net.

### Implementation
```javascript
window.addEventListener('beforeunload', (e) => {
  const hasUnuploaded = poiData.some(p => p._status === 'complete');
  if (hasUnuploaded) {
    e.preventDefault();
  }
});
```

---

## GitHub Summary

> Copy-paste this into your commit or PR description.

### Workbench Upload & Beat Conflict Resolution

Adds the ability for editors to upload reviewed POIs and narrative beats from the Editorial Workbench directly to Neo4j, with inline conflict detection and resolution.

**Backend**
- New `GET /api/v1/graph/poi/{poi_name}/beats` endpoint — single Cypher traversal returning active beats and their lens tags for a POI
- `create_node()` now uses `MERGE` (instead of `CREATE`) for POI and NarrativeBeat, keyed on `name` and `script_body` respectively — makes uploads idempotent and retry-safe
- `create_edge()` now uses `MERGE` for `HAS_BEAT` and `TAGGED_WITH` relationships

**Frontend (review.html)**
- "Upload to Database" button in the completion banner (disabled until POIs are marked complete)
- Conflict detection: queries existing beats per POI, flags hard matches (same lens), soft matches (Jaccard word-overlap >= 70%), and review-band items (30-69%)
- Conflict resolution overlay: side-by-side diff with Replace, Skip, Merge (field-by-field picker), and Change Lens actions
- Upload execution with real-time progress overlay and per-item error tracking
- Summary screen with counts (POIs created/matched, beats created/replaced/skipped/merged, relationships linked)
- Retry support for failed items (MERGE makes retry idempotent)
- `beforeunload` warning to prevent data loss from accidental tab close
- Field mapping layer: workbench format → API format (lens display labels → slugs, `poi_name` → `name`, defaults for `version`, `active_status`, `duration_sec`)

**Tests**
- 6 new integration tests in `tests/test_upload_api.py` covering MERGE idempotency (POI + edge) and beat traversal endpoint (active beats, empty POI, deprecated beat exclusion)
- All 158 tests passing, 0 regressions

---

## Future Work

Items identified during spec and red team review, explicitly deferred from this slice.

| Item | Priority | Why deferred | Trigger to revisit |
|------|----------|-------------|-------------------|
| **POI deconfliction at ingest** | High | Next slice — fuzzy name matching (case, spacing, spelling), coordinate proximity check, editor disambiguation UI | Immediately after this slice ships |
| **Batch upload endpoint** | Medium | One-request-per-node is slow (~50s for 100 POIs) but acceptable for internal editorial tool | Upload times exceed 2 minutes or editor complaints |
| **Upgrade Jaccard → cosine similarity** | Low | Jaccard word-overlap is sufficient for near-duplicate detection on 50-200 word script bodies | False negatives reported (semantically similar beats not caught) or script bodies grow significantly longer |
| **Selective per-item upload** | Low | Batch-only upload is simpler for v1 | Editor requests ability to upload individual POIs |
| **Upload rollback / undo** | Low | Adds significant complexity (version tracking, cascading deletes) | Data quality issues from bad uploads |
| **POI.name unique constraint** | Low | Exact name match is sufficient for v1; fuzzy matching belongs in the deconfliction slice | After POI deconfliction slice ships |
