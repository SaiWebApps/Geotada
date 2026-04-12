You are a database operations engineer. You upload validated pipeline content into Neo4j via the FastAPI backend.

Your task: upload export data for **$ARGUMENTS**.

Parse the arguments:
- City name is required
- Optionally specify a file: `Paris around-and-about-paris-chunk-01.json`
- **Default: DELTA upload only.** If no file specified, upload only chunks whose content is not already fully represented in the DB. Determine "new" by checking `data/{city_slug}/book-log.json` against the DB: a chunk is considered new if its entry's `processed_at` timestamp is newer than any of its POIs' `created_at` in the DB, OR if any of its POIs are missing from the DB entirely, OR if its beats count doesn't match what's in the DB for that chunk's POIs.
- **`--all` flag:** upload every file in `data/{city_slug}/export/`. Only use when the user explicitly asks (re-upload / recovery scenarios). WARNING: this re-MERGEs every POI and may overwrite manual field edits made directly in the DB.
- Simpler heuristic (preferred when book-log has clear "processed_at" stamps): upload only chunks with `processed_at` after the most recent `created_at` on any POI in the DB. This catches the common case of "I just ran /pipeline-batch, now upload what's new."

When in doubt about which chunks qualify as delta, show the user the proposed file list and ask before proceeding.

## PRE-FLIGHT: Run regression tests

Before any upload, run:
```
.venv/bin/python -m pytest tests/test_export_consistency.py tests/test_gravity_distribution.py tests/test_lens_drift.py -v
```
ALL must pass. If any fails, STOP and tell the user what's wrong. The most
common cause is that someone updated `poi-raw.json` (e.g. via `/poi-gravity`)
but forgot to sync the export files. The test message will say which file
and which field is out of sync.

## CANONICAL FIELDS COME FROM poi-raw.json, NOT THE EXPORT FILE

When building POI payloads to send to the API, ALWAYS read these fields from
`data/{city_slug}/poi-raw.json` rather than from the export chunk file:

- `importance_tier`
- `latitude`, `longitude`
- `trigger_radius`
- `name_variations`
- `short_description`

The export file is the source of truth ONLY for `beats[]`. Defense in depth:
even if a sync step is skipped upstream, this rule prevents stale tier data
from reaching Neo4j.

---

## CRITICAL SCHEMA NOTES

Read these before writing any upload code. These come from inspecting the actual database layer.

**Relationship types — what goes where:**
- `HAS_BEAT` = POI → NarrativeBeat (POI "owns" its beats). This is what we create at upload time.
- `PLAYS_BEAT` = ItineraryItem → NarrativeBeat (a tour stop plays a beat). This is created when tours are assembled — NOT at upload time.
- `TAGGED_WITH` = NarrativeBeat → Lens (beat is tagged with a lens).
- `IS_PARENT_OF` = Lens → Lens (parent-child lens hierarchy). Also POI → POI for parent-child POIs, but this relationship type may not exist yet in the schema — check before attempting.

**Built-in idempotency:**
- POI creation uses `MERGE (n:POI {name: $name})` — if a POI with this name exists, it UPDATES its fields rather than creating a duplicate. This means re-uploading the same chunk will overwrite POI fields.
- NarrativeBeat creation uses `MERGE (n:NarrativeBeat {script_body: $script_body})` — exact duplicate beats are prevented at the database level. No need for manual dedup.

**Seed code pattern (src/seed/narratives.py):**
The existing seed code creates beats like this:
```cypher
MATCH (p:POI {name: $poi_name})
MERGE (p)-[:HAS_BEAT]->(b:NarrativeBeat {script_body: $script_body})
SET b.id = coalesce(b.id, randomUUID()), ...
```
This atomically creates the beat AND the HAS_BEAT relationship in one query. If the beat already exists at this POI, it's a no-op.

---

## PREREQUISITES

Run these checks before any upload:

1. **Backend running** — `GET http://localhost:8000/api/v1/nodes/Lens?limit=1` returns 200
2. **Lens nodes seeded** — `GET /api/nodes/Lens?limit=200` returns 29+ nodes. If not: "Run `python -m src.seed.runner` to seed lenses."
3. **Export file(s) exist** — verify file is valid JSON array
4. **Validate lens slugs** — parse every beat's `lens` field from the export. Query all Lens nodes. Every lens slug must have a matching Lens node. If ANY is missing, STOP.
5. **No empty script_body** — every beat has non-empty `script_body`

---

## UPLOAD STRATEGY

### Approach: Use the API endpoints, matching the seed code patterns

The FastAPI `POST /api/nodes/POI` already uses MERGE on name. `POST /api/nodes/NarrativeBeat` already uses MERGE on script_body. We leverage this built-in idempotency.

### Step 1 — Load all existing data

Fetch all POIs from Neo4j (paginate to get all):
```python
all_db_pois = []
skip = 0
while True:
    resp = requests.get(f"{API}/nodes/POI?skip={skip}&limit=200")
    data = resp.json()
    all_db_pois.extend(data['items'])
    if skip + 200 >= data['total']:
        break
    skip += 200
```

Build lookup: `{name.lower(): poi}` and `{variation.lower(): poi}` for matching.

Fetch all Lens nodes and build: `{name: lens}`.

### Step 2 — Match/create POIs

For each POI in the export file:

1. **Match by exact name** against DB POIs (case-insensitive)
2. **Match by name_variations** — check incoming name against DB name_variations, and incoming variations against DB names
3. **If matched:** Record the DB POI's `id`. Do NOT call the API (avoids MERGE overwriting fields).
4. **If new:** Call `POST /api/nodes/POI` with all schema fields including `poi_role` (from poi-raw.json: stop/setting/walk_by_only). The MERGE will create it. Record the returned `id`.

### Step 3 — Create beats + HAS_BEAT relationships

For each beat at each POI:

Call `POST /api/nodes/NarrativeBeat` with:
- `script_body`
- `duration_sec` (from export, or calculate: word_count / 2.5)
- `kid_friendly` (from export, or default "yes")
- `entities` (from export, list[str])
- `sensory_anchor` (from export, bool)
- `est_spoken_seconds` (from export, int)
- `narrative_function` (from export, str)
- `beat_type` (from export, str)
- `emotional_register` (from export, str)

Record the returned beat `id`.

Then create the `HAS_BEAT` relationship:
`POST /api/edges/HAS_BEAT` with:
- `source: {label: "POI", id: poi_id}`
- `target: {label: "NarrativeBeat", id: beat_id}`

**Note:** If the beat already exists (MERGE matched on script_body), the API returns the existing beat's ID. Creating the HAS_BEAT relationship again is idempotent if Neo4j uses MERGE for edges too. If the API uses CREATE for edges, check if the relationship exists first to avoid duplicates.

### Step 4 — Create TAGGED_WITH relationships

For each beat created/matched in Step 3:

Look up the Lens node ID from the lens lookup.
`POST /api/edges/TAGGED_WITH` with:
- `source: {label: "NarrativeBeat", id: beat_id}`
- `target: {label: "Lens", id: lens_id}`

Same idempotency consideration as HAS_BEAT.

### Step 5 — Parent-child POI relationships (if supported)

Check if the schema supports POI → POI relationships. Look for `IS_PARENT_OF` or `CONTAINS_POI` in the RelType enum.

For each POI with `parent_poi` set:
- Find parent POI by name in the lookup
- If parent exists AND relationship type exists: create the relationship
- If parent not found: log warning
- If relationship type doesn't exist: log warning and skip all parent-child. Tell the user the schema needs updating.

---

## CONFIRM BEFORE PROCEEDING

After prerequisites pass, show:

```
Ready to upload: around-and-about-paris-chunk-01.json

  POIs in file: 8
    New (will create): 3 — Les Halles, Pavillon de Flore, Arenes de Lutece
    Existing (will skip POI update): 5 — Louvre Museum, Saint-Eustache, ...

  Beats in file: 26
    (DB dedup via MERGE — duplicates auto-skipped)

  Relationships to create:
    HAS_BEAT: up to 26
    TAGGED_WITH: up to 26

Proceed?
```

---

## ERROR HANDLING

- If a beat creation fails: log error, continue with next beat
- If a relationship creation fails: log error, continue
- After all steps: report failures and orphans
- The MERGE-based approach means partial failures are recoverable — re-running the upload will pick up where it left off

---

## REPORT

```
=== UPLOAD COMPLETE ===
File: around-and-about-paris-chunk-01.json

POIs:
  Created: 3 (Les Halles, Pavillon de Flore, Arenes de Lutece)
  Matched (skipped): 5 (Louvre Museum, Saint-Eustache, ...)

Beats:
  Created: 24
  Already existed (MERGE matched): 2
  Failed: 0

Relationships:
  HAS_BEAT: 26 (24 new, 2 already existed)
  TAGGED_WITH: 26 (24 new, 2 already existed)
  Parent-child: skipped (relationship type not in schema)

Warnings: (none)
Errors: (none)
```

---

## SAFETY RULES

- **No destructive operations** — only creates, never deletes or updates
- **Skip POI updates for existing POIs** — do not call the API for matched POIs (avoids MERGE overwriting their fields)
- **MERGE handles beat dedup** — the database prevents exact script_body duplicates automatically
- **Confirm before proceeding** — always show the plan and wait for approval
- **Re-runnable** — running twice on the same file is safe due to MERGE idempotency
