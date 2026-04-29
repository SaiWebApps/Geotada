# Workbench Changes Required for V3 Prompt Pipeline

## Summary of V3 Prompt Changes That Affect the Workbench

| Change | Miner V3 | Fact-Checker V3 | Workbench Impact |
|--------|----------|-----------------|------------------|
| Coordinates removed from miner, added by fact-checker | `address` field instead of lat/lng | Adds `latitude`/`longitude` in Step 2 | No change — workbench already expects lat/lng |
| `alternative_names` array on each POI | New field | Enriched in Step 1 | **New**: display + use in conflict detection |
| `gravity` removed from miner | No gravity field on beats | Assigned in Step 3 | No change — workbench already expects gravity |
| `gravity_audit` on each beat | N/A | New field with signal_a, signal_b, score, reasoning | **New**: display in beat cards |
| `audit_notes` is now an ARRAY (not object) | N/A | Array of issues per beat | **Change**: renderer must handle arrays |
| `_meta` block on each POI | prompt_version, generated_at, source_id | Adds audited_at | **New**: display metadata |
| `address` field on each POI | New field | Preserved | **New**: display in detail panel |
| POI existence unverified flag | N/A | poi_audit_notes entry | Already handled by poi_audit_notes renderer |
| No `tags` field | Removed in V2 | Confirmed excluded | No change |

---

## Change 1: Alternative Name Conflict Detection (HIGH PRIORITY)

### Problem
Current conflict detection (`detectConflictsForPoi` at line 2071 and `detectConflicts` at line 1968) matches POIs by exact `poi_name` string only. "Sacré-Cœur" and "Basilique du Sacré-Cœur de Montmartre" are treated as completely separate POIs.

### Solution
When checking for conflicts, also search the database for any POI whose name matches any entry in the incoming POI's `alternative_names` array, and vice versa.

**In `detectConflictsForPoi()`:**
1. After the primary fetch by `poi.poi_name`, also check `cachedPoiList` for any POI whose `name` appears in `poi.alternative_names`.
2. If a match is found, treat it as a matched POI (not new) and run beat-level conflict detection against those existing beats.
3. Show a UI indicator: "Matched via alternative name: Basilique du Sacré-Cœur de Montmartre → Sacré-Cœur"

**In the duplicate resolver overlay:**
1. After checking for duplicate `poi_name` values within the uploaded file, also check whether any POI's `alternative_names` array contains another POI's `poi_name` (cross-reference within the batch).

**In `cachedPoiList`:**
The API would need to return `alternative_names` as a property on POI nodes, or the workbench needs a separate lookup. For now, the simplest approach is to store `alternative_names` as a JSON string property on the POI node and parse it client-side.

---

## Change 2: Display `gravity_audit` on Beat Cards (MEDIUM PRIORITY)

### Problem
The fact-checker now provides structured reasoning for every gravity score (signal_a, signal_b, score, reasoning). The workbench currently shows gravity as an editable number field but doesn't show why it was assigned.

### Solution
Add a read-only gravity audit block below the gravity input on each beat card.

```
┌─────────────────────────────────────────────┐
│ Gravity: [4]                                │
│ ┌─ Gravity Audit ─────────────────────────┐ │
│ │ POI Reach: 3  ·  Distinctiveness: 2     │ │
│ │ "Faneuil Hall is a global landmark;     │ │
│ │  grasshopper story is known but not     │ │
│ │  the headline."                         │ │
│ └─────────────────────────────────────────┘ │
└─────────────────────────────────────────────┘
```

Style: muted info box (blue-dim), not editable. If the human editor changes gravity, the audit block stays visible as a reference.

---

## Change 3: Handle `audit_notes` as an Array (HIGH PRIORITY)

### Problem
The current `renderAuditNotes()` function (around line 1113) handles two formats: string (legacy) and single object. V3 outputs an array of objects — one per issue.

### Solution
Update `renderAuditNotes()` to handle three formats:
1. **String** — existing behavior (legacy)
2. **Single object** — existing behavior (V2 compat)
3. **Array of objects** — iterate and render each as a separate audit note block

Each array entry gets its own bordered section within the audit-notes-box, with a separator between entries. Number them: "Issue 1 of 3", "Issue 2 of 3", etc.

---

## Change 4: Display `_meta` Block (LOW PRIORITY)

### Problem
The V3 pipeline adds traceability metadata (`prompt_version`, `generated_at`, `source_id`, `audited_at`) but the workbench ignores it.

### Solution
Add a small collapsible metadata footer at the bottom of each POI's detail panel:

```
▸ Pipeline Metadata
  Prompt: data_miner_v3  |  Mined: 2026-03-12T14:30:00Z
  Source: "Walking Paris — Ch.5 Montmartre"
  Audited: 2026-03-12T15:45:00Z
```

Collapsed by default. Styled in `--text-muted` color. Not editable.

---

## Change 5: Display `address` Field (MEDIUM PRIORITY)

### Problem
V3 miner outputs an `address` field that the fact-checker uses for geocoding. The workbench doesn't display it.

### Solution
Add a read-only `address` field above the lat/lng inputs in the POI detail panel. This gives the human reviewer context for whether the map pin is correct — they can see "35 Rue du Chevalier de la Barre, Paris" and visually confirm against the Leaflet map.

```
┌─ Location ──────────────────────────┐
│ Address: 35 Rue du Chevalier de la Barre, Paris   │  (read-only)
│ Lat: [42.366389]  Lng: [-71.05444] │  (editable + draggable pin)
└─────────────────────────────────────┘
```

---

## Change 6: Display `alternative_names` (MEDIUM PRIORITY)

### Problem
The workbench doesn't show or store alternative names.

### Solution
Add a read-only tag list below the POI name field:

```
POI Name: [Sacré-Cœur                    ]
Also known as: Basilique du Sacré-Cœur de Montmartre · Basilique du Sacré-Cœur
```

Styled as small pill badges in `--text-muted`. Not directly editable in the workbench — these come from the pipeline and are used for conflict detection.

When uploading to Neo4j, store `alternative_names` as a property on the POI node (JSON-encoded string array or native list property) so that future conflict detection can query against them.

---

## Change 7: Schema — Store `alternative_names` on POI Node (HIGH PRIORITY)

### Problem
The Neo4j POI node schema doesn't include `alternative_names`. Without this, the conflict detection improvement (Change 1) has nothing to match against on the database side.

### Solution
In `src/schema/definitions.py`, add `alternative_names` to the POI node properties. In `src/api/models/nodes.py`, add it to `POICreate`:

```python
alternative_names: Optional[List[str]] = None
```

In the Cypher MERGE query for POI creation, include:
```cypher
SET n.alternative_names = $alternative_names
```

Store as a Neo4j native string list property. This enables future Cypher queries like:
```cypher
MATCH (p:POI) WHERE $name IN p.alternative_names RETURN p
```

---

## Change 8: API — Query POIs by Alternative Name (MEDIUM PRIORITY)

### Problem
`GET /graph/poi/{name}/beats` only matches on exact `name`. The workbench needs to also check alternative names for conflict detection.

### Solution
Add a query parameter or new endpoint:

Option A: Expand existing endpoint
```
GET /graph/poi/{name}/beats?include_alt_names=true
```
This runs:
```cypher
MATCH (p:POI)
WHERE p.name = $name OR $name IN p.alternative_names
OPTIONAL MATCH (p)-[:HAS_BEAT]->(b:NarrativeBeat)-[:TAGGED_WITH]->(l:Lens)
RETURN p, b, l
```

Option B: New search endpoint
```
GET /api/v1/graph/poi/search?name=Christ+Church
```
Returns any POI where `name` or any `alternative_names` entry matches.

---

## Change 9: Validate JSON with `_meta` and New Fields (LOW PRIORITY)

### Problem
The JSON validation on upload (around line 987) has an allowlist of known keys. New fields like `_meta`, `alternative_names`, `address` will trigger "unexpected key" warnings.

### Solution
Add the new fields to the allowed keys list:

```javascript
const KNOWN_POI_KEYS = [
  'poi_name', 'latitude', 'longitude', 'beats', 'short_description',
  'orientation', 'poi_audit_notes', 'audit_notes',
  // V3 additions
  'address', 'alternative_names', '_meta'
];

const KNOWN_BEAT_KEYS = [
  'script_body', 'lens', 'gravity', 'physical_cue', 'source_passage',
  'audit_notes',
  // V3 additions
  'gravity_audit'
];
```

---

## Implementation Priority

| Priority | Change | Effort |
|----------|--------|--------|
| **P0** | Change 3: audit_notes as array | Small — update one render function |
| **P0** | Change 7: Schema for alternative_names | Small — add one property |
| **P1** | Change 1: Alternative name conflict detection | Medium — JS logic + API query |
| **P1** | Change 8: API query by alt name | Small — one Cypher query |
| **P1** | Change 5: Display address field | Small — one HTML block |
| **P1** | Change 6: Display alternative_names | Small — tag pills |
| **P2** | Change 2: Display gravity_audit | Small — info box |
| **P2** | Change 9: JSON validation update | Trivial — add strings to array |
| **P3** | Change 4: Display _meta block | Small — collapsible footer |
