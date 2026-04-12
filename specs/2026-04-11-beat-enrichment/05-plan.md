# Implementation Plan: Beat & POI Metadata Enrichment

**Date:** 2026-04-11
**Spec:** `02-spec.md` | **Scopes:** `03-scopes.md` | **Red Team:** `04-red-team.md`

---

## Scope 1: Schema & Model Updates

### Part A — Task Breakdown

#### Task 1.1: Add enrichment fields to NarrativeBeatCreate model

**Files to touch:** `src/api/models/nodes.py`
**What to do:** Add 6 optional fields to `NarrativeBeatCreate`:
```python
entities: list[str] = []
sensory_anchor: bool | None = None
est_spoken_seconds: int | None = None
narrative_function: str = ""
beat_type: str = ""
emotional_register: str = ""
```
All optional with defaults so existing code that creates beats without enrichment still works.

**What NOT to touch:** CRUD layer (`crud/nodes.py`) — the SET loop already handles arbitrary properties. No changes needed there.
**Success check:** `NarrativeBeatCreate(script_body='test', entities=['x'], sensory_anchor=True, est_spoken_seconds=10, narrative_function='hook', beat_type='anecdote', emotional_register='dramatic')` instantiates without error.

#### Task 1.2: Add `poi_role` to POICreate model

**Files to touch:** `src/api/models/nodes.py`
**What to do:** Add `poi_role: str = "stop"` to `POICreate`. Default `"stop"` because most POIs are stops.
**What NOT to touch:** POI validators, CRUD layer.
**Success check:** `POICreate(name='test', latitude=0.0, longitude=0.0, importance_tier=3, poi_role='setting')` instantiates without error.

#### Task 1.3: Fix pre-existing broken test

**Files to touch:** `tests/test_api_models.py`
**What to do:** The test `test_poi_create_requires_lat_lng` (line 86) is currently failing because it doesn't pass the required `importance_tier`. Fix by adding `importance_tier=3` to the test.
**What NOT to touch:** Other tests.
**Success check:** `pytest tests/test_api_models.py -v` passes.

#### Task 1.4: Add model tests for new fields

**Files to touch:** `tests/test_api_models.py`
**What to do:** Add tests:
- `test_beat_create_with_enrichment_fields` — instantiate with all 6 new fields, verify they round-trip via `model_dump()`
- `test_beat_create_without_enrichment_fields` — instantiate with only `script_body`, verify defaults
- `test_poi_create_with_poi_role` — instantiate with `poi_role='setting'`, verify
- `test_poi_create_default_poi_role` — instantiate without `poi_role`, verify default is `"stop"`
**What NOT to touch:** Existing tests (except the fix in 1.3).
**Success check:** `pytest tests/test_api_models.py -v` — all pass.

### Part B — Test Definitions

| AC | Test | Type | Expected |
|---|---|---|---|
| AC-8 | Beat model accepts all 6 enrichment fields | Unit | `model_dump()` includes all fields with correct types |
| AC-8 | Beat model works without enrichment fields | Unit | Defaults applied, no validation error |
| AC-8 | POI model accepts `poi_role` | Unit | `model_dump()` includes `poi_role` |
| AC-8 | POI model defaults `poi_role` to `"stop"` | Unit | Default value correct |

### Part C — Claude Code Prompt

```
## Scope 1: Schema & Model Updates for Beat Enrichment

**Goal:** Add 6 optional enrichment fields to NarrativeBeatCreate and 1 field to POICreate so the API accepts enriched data on create/update.

**Context:** We're adding metadata to NarrativeBeat nodes (entities, sensory_anchor, est_spoken_seconds, narrative_function, beat_type, emotional_register) and POI nodes (poi_role) to support the tour builder. The CRUD layer at `src/api/crud/nodes.py` already handles arbitrary properties via a SET loop — no CRUD changes needed. We only need to update the Pydantic models and tests.

**What to build:**

1. In `src/api/models/nodes.py`, add to `NarrativeBeatCreate` (after line 114):
   - `entities: list[str] = []`
   - `sensory_anchor: bool | None = None`
   - `est_spoken_seconds: int | None = None`
   - `narrative_function: str = ""`
   - `beat_type: str = ""`
   - `emotional_register: str = ""`

2. In `src/api/models/nodes.py`, add to `POICreate` (after `name_variations`):
   - `poi_role: str = "stop"`

3. Fix `tests/test_api_models.py` line 86: add `importance_tier=3` to the POI test that's currently broken.

4. Add 4 new tests to `tests/test_api_models.py`:
   - `test_beat_create_with_enrichment_fields` — all 6 fields provided
   - `test_beat_create_without_enrichment_fields` — only script_body, verify defaults
   - `test_poi_create_with_poi_role` — poi_role='setting'
   - `test_poi_create_default_poi_role` — verify default is "stop"

**What NOT to touch:** `src/api/crud/nodes.py`, `src/api/routes/`, `src/schema/definitions.py`, any other model classes.

**Verification:**
```bash
.venv/bin/python -m pytest tests/test_api_models.py -v
.venv/bin/python -m pytest tests/ -v --tb=short
```

Before starting, confirm you understand the full scope and flag any conflicts with the existing codebase or assumptions you are making.
```

---

## Scope 2: Classification Backfill

### Part A — Task Breakdown

#### Task 2.1: Build the beat enrichment skill

**Files to touch:** `.claude/commands/beat-enrich.md`
**What to do:** Create a new Claude Code skill that:
- Reads `data/{city}/beats.json`
- Groups beats by `poi_name`
- For each POI batch, sends all beats' `script_body` texts to the classifier with a structured prompt
- The prompt requests JSON output with the 5 AI-classified fields per beat
- Computes `est_spoken_seconds` from word count (no AI)
- Writes enriched fields back into each beat object in `beats.json`
- Adds `_enrichment` metadata block with model name, timestamp, version

**Prompt design requirements (from red team):**
- Entity extraction guidance: "Include people, specific historical events, specific buildings/monuments, and named groups. Exclude the city name itself, common geographic features (Seine, Left Bank), and the POI's own name unless the beat discusses it as a subject rather than a location."
- Batch by POI so context-dependent fields (narrative_function) benefit from seeing siblings
- Temperature 0 for consistency

**What NOT to touch:** `beats.json` structure — only add fields, never remove or rename existing ones. Don't touch `poi-raw.json` (that's Task 2.2). Don't touch export files (that's Scope 3).
**Success check:** Every beat in `beats.json` has all 6 fields with valid enum values.

#### Task 2.2: Build the POI role classification

**Files to touch:** `.claude/commands/beat-enrich.md` (same skill, second phase)
**What to do:** Add a POI classification phase to the skill that:
- Reads `data/{city}/poi-raw.json`
- For each POI, considers: `importance_tier`, `trigger_radius`, `short_description`, and beat count/lens distribution from `beats.json`
- Classifies as `stop`, `setting`, or `walk_by_only`
- Writes `poi_role` and `_poi_role_reasoning` back into each POI object in `poi-raw.json`

**Classification heuristics (to include in prompt):**
- Tier 1-2 → default `walk_by_only`
- Tier 3-5 discrete buildings/monuments → default `stop`
- Tier 3-5 with large footprint (trigger_radius ≥ 50m, or description mentions island/boulevard/garden/quarter) → candidate for `setting`
- Override heuristic with judgment based on the POI's description and beat content

**What NOT to touch:** Other fields in `poi-raw.json`.
**Success check:** Every POI has `poi_role` with a valid value.

#### Task 2.3: Run the classification and spot-check

**Files to touch:** `data/paris/beats.json`, `data/paris/poi-raw.json` (outputs)
**What to do:**
- Run the skill on Paris data
- After completion, run the validation scripts from Scope 2 verification commands
- Run the distribution check (from red team R-1): verify no enum value has >70% of beats
- Manually spot-check 20 beats with `sensory_anchor: true` — verify each references something currently visible (AC-3)
- Manually review the ~5-10 POIs classified as `setting` or `walk_by_only` — verify they make sense

**What NOT to touch:** Export files, Neo4j, pipeline skills.
**Success check:** All verification commands pass. Distribution is reasonable. Spot-checks confirm accuracy.

### Part B — Test Definitions

| AC | Test | Type | Expected |
|---|---|---|---|
| AC-1 | All beats have 6 fields with valid enums | Script | Zero assertion failures across 548 beats |
| AC-2 | est_spoken_seconds matches word count | Script | `round(word_count / 2.5)` matches stored value for every beat |
| AC-3 | sensory_anchor accuracy | Manual spot-check | 20 sampled `true` beats reference visible features |
| AC-4 | All POIs have valid poi_role | Script | Zero assertion failures across 119 POIs |
| — | Distribution check (R-1) | Script | No enum value >70% of beats |

### Part C — Claude Code Prompt

```
## Scope 2: Classification Backfill for Beat & POI Enrichment

**Goal:** Classify all ~548 Paris beats with 6 metadata fields and all ~119 POIs with `poi_role`, writing results back to the JSON data files.

**Context:** We're enriching existing beat data so the tour builder can select and sequence beats without re-reading raw text. This is a classification pass over existing `script_body` text — NOT re-extraction from source books. Read `specs/2026-04-11-beat-enrichment/02-spec.md` for full field definitions and enum values.

**What to build:**

### Phase 1: Create the beat-enrich skill

Create `.claude/commands/beat-enrich.md` — a reusable skill that:

1. Reads `data/{city}/beats.json` (city from $ARGUMENTS, default "paris")
2. Groups beats by `poi_name`
3. For each POI batch, classifies all beats with 5 AI fields:
   - `entities`: list[str] — named people, historical events, buildings, groups. Use full proper names. EXCLUDE the city name, common geography (Seine, Left Bank), and the POI's own name unless discussed as a subject.
   - `sensory_anchor`: bool — true only if the beat references something currently visible/audible/touchable at the POI. Demolished/destroyed = false.
   - `narrative_function`: one of hook|deepen|transition|climax|callback|scene_setter|establishing
   - `beat_type`: one of anecdote|architectural_detail|character_story|event|sensory_observation|factoid|establishing
   - `emotional_register`: one of reverent|somber|playful|dramatic|wry|neutral
4. Computes `est_spoken_seconds = round(word_count(script_body) / 2.5)` — pure math, no AI
5. Writes all 6 fields back into each beat in `beats.json`
6. Adds `_enrichment: {model, enriched_at, version}` metadata

**Batching:** Send all beats for one POI together so narrative_function can be judged relative to siblings (which is the hook vs the deep dive?). Use temperature 0.

**Output format from classifier:** JSON array matching the input beat order, each element with the 5 classified fields.

### Phase 2: POI role classification

Same skill, second phase:

1. Reads `data/{city}/poi-raw.json`
2. For each POI, classifies as `stop`, `setting`, or `walk_by_only`
3. Heuristics to include in prompt:
   - Tier 1-2 → default walk_by_only
   - Tier 3-5 discrete buildings → default stop
   - Tier 3-5 with large footprint (trigger_radius ≥ 50m, or island/boulevard/garden) → candidate for setting
   - Override with judgment from description and beat content
4. Writes `poi_role` and `_poi_role_reasoning` to each POI in `poi-raw.json`

### Phase 3: Run on Paris and validate

Run the skill on Paris data, then verify:

```bash
# Validate all beats
.venv/bin/python -c "
import json
VALID_NF = {'hook','deepen','transition','climax','callback','scene_setter','establishing'}
VALID_BT = {'anecdote','architectural_detail','character_story','event','sensory_observation','factoid','establishing'}
VALID_ER = {'reverent','somber','playful','dramatic','wry','neutral'}
beats = json.load(open('data/paris/beats.json'))
for b in beats:
    assert 'entities' in b and isinstance(b['entities'], list), f'{b[\"beat_id\"]}: missing entities'
    assert 'sensory_anchor' in b and isinstance(b['sensory_anchor'], bool), f'{b[\"beat_id\"]}: missing sensory_anchor'
    assert 'est_spoken_seconds' in b and isinstance(b['est_spoken_seconds'], int), f'{b[\"beat_id\"]}: missing est_spoken_seconds'
    assert b.get('narrative_function') in VALID_NF, f'{b[\"beat_id\"]}: bad narrative_function'
    assert b.get('beat_type') in VALID_BT, f'{b[\"beat_id\"]}: bad beat_type'
    assert b.get('emotional_register') in VALID_ER, f'{b[\"beat_id\"]}: bad emotional_register'
    expected = round(len(b['script_body'].split()) / 2.5)
    assert b['est_spoken_seconds'] == expected, f'{b[\"beat_id\"]}: est mismatch'
print(f'All {len(beats)} beats validated.')
"

# Distribution check — flag if any value >70%
.venv/bin/python -c "
import json
from collections import Counter
beats = json.load(open('data/paris/beats.json'))
for f in ['narrative_function', 'beat_type', 'emotional_register']:
    dist = Counter(b[f] for b in beats)
    total = len(beats)
    for val, count in dist.most_common():
        pct = count/total*100
        flag = ' ⚠️' if pct > 70 else ''
        print(f'  {f}: {val} = {count} ({pct:.0f}%){flag}')
    print()
"

# Validate all POIs
.venv/bin/python -c "
import json
VALID_ROLES = {'stop','setting','walk_by_only'}
pois = json.load(open('data/paris/poi-raw.json'))
for p in pois:
    assert p.get('poi_role') in VALID_ROLES, f'{p[\"name\"]}: bad poi_role'
print(f'All {len(pois)} POIs validated.')
"

# Regression tests
.venv/bin/python -m pytest tests/test_export_consistency.py tests/test_gravity_distribution.py tests/test_lens_drift.py -v
```

After running validation, manually spot-check:
- 20 beats with `sensory_anchor: true` — verify each references a currently visible feature
- All POIs classified as `setting` or `walk_by_only` — verify they make sense

**What NOT to touch:** Export files in `data/paris/export/` (Scope 3). Neo4j database. Pipeline skills (`beat-from-book`, `pipeline-chunk`). Backend code.

Before starting, confirm you understand the full scope and flag any conflicts with the existing codebase or assumptions you are making.
```

---

## Scope 3: Export, Upload & Verify

### Part A — Task Breakdown

#### Task 3.1: Update export-validate skill spec

**Files to touch:** `.claude/commands/export-validate.md`
**What to do:** Add the 6 enrichment fields to the "What to include on each beat" section (after line 123):
- `entities` (list[str])
- `sensory_anchor` (bool)
- `est_spoken_seconds` (int)
- `narrative_function` (str)
- `beat_type` (str)
- `emotional_register` (str)

Add `poi_role` to the "What to include on each POI" section (after line 126).

**What NOT to touch:** The strip list, the validation logic, the file naming.
**Success check:** The skill spec explicitly lists all enrichment fields.

#### Task 3.2: Update upload skill spec

**Files to touch:** `.claude/commands/upload.md`
**What to do:** Update Step 3 (line 117-120) to include all enrichment fields in the NarrativeBeat payload:
```
Call POST /api/nodes/NarrativeBeat with:
- script_body
- duration_sec
- kid_friendly
- entities
- sensory_anchor
- est_spoken_seconds
- narrative_function
- beat_type
- emotional_register
```

Update Step 2 to include `poi_role` when creating new POIs.

**What NOT to touch:** Upload strategy, matching logic, edge creation.
**Success check:** The skill spec explicitly maps all enrichment fields to API payloads.

#### Task 3.3: Regenerate export files

**Files to touch:** `data/paris/export/*.json`
**What to do:** Run the export-validate skill to regenerate all export files from `beats.json` + `poi-raw.json`, now including enrichment fields.
**What NOT to touch:** Source data files (`beats.json`, `poi-raw.json`).
**Success check:** Every beat in every export file has all 6 enrichment fields. Every POI has `poi_role`.

#### Task 3.4: Upload to Neo4j and verify

**Files to touch:** Neo4j database (via API)
**What to do:**
- Start the backend (`uvicorn src.api.app:app`)
- Run the upload skill for Paris (all chunks, since enrichment fields are new)
- Verify enrichment fields appear on NarrativeBeat nodes via API
- Verify `poi_role` appears on POI nodes via API
- Run the cross-POI entity overlap query via cypher-shell to verify AC-7

**What NOT to touch:** Backend code (already updated in Scope 1). Data files.
**Success check:** API returns enrichment fields on nodes. Entity overlap query returns results.

### Part B — Test Definitions

| AC | Test | Type | Expected |
|---|---|---|---|
| AC-5 | Regression tests pass after export regen | Automated | `pytest tests/test_export_consistency.py tests/test_gravity_distribution.py tests/test_lens_drift.py` all green |
| AC-6 | Enrichment fields on Neo4j nodes | Manual/curl | `GET /api/v1/nodes/NarrativeBeat?limit=5` returns nodes with `entities`, `sensory_anchor`, etc. |
| AC-7 | Cross-POI entity overlap | Manual/cypher-shell | Query returns POI pairs sharing entities |

### Part C — Claude Code Prompt

```
## Scope 3: Export, Upload & Verify for Beat Enrichment

**Goal:** Update pipeline skill specs, regenerate export files with enrichment fields, upload to Neo4j, and verify end-to-end.

**Context:** Scopes 1 and 2 are complete. The Pydantic models now accept enrichment fields. `data/paris/beats.json` and `data/paris/poi-raw.json` contain enrichment data. Now we need to flow that data through exports and into Neo4j.

**Red team blockers to resolve (from `specs/2026-04-11-beat-enrichment/04-red-team.md`):**
- B-1: Upload skill drops enrichment fields — must update `.claude/commands/upload.md`
- B-2: Export-validate doesn't list enrichment fields — must update `.claude/commands/export-validate.md`
- B-3: Graph query endpoint doesn't exist — use `cypher-shell` for verification

**What to build:**

### Task 1: Update export-validate skill spec

In `.claude/commands/export-validate.md`, add to "What to include on each beat" section (after the `fact_check_status` line):
- `entities` (list[str] — from enrichment)
- `sensory_anchor` (bool — from enrichment)
- `est_spoken_seconds` (int — from enrichment)
- `narrative_function` (str — from enrichment)
- `beat_type` (str — from enrichment)
- `emotional_register` (str — from enrichment)

Add to "What to include on each POI" section:
- `poi_role` (str — stop/setting/walk_by_only)

### Task 2: Update upload skill spec

In `.claude/commands/upload.md`, update Step 3 to pass enrichment fields when creating NarrativeBeat nodes:
```
Call POST /api/nodes/NarrativeBeat with:
- script_body
- duration_sec
- kid_friendly
- entities (from export, list[str])
- sensory_anchor (from export, bool)
- est_spoken_seconds (from export, int)
- narrative_function (from export, str)
- beat_type (from export, str)
- emotional_register (from export, str)
```

Update Step 2 to include `poi_role` when creating new POIs.

### Task 3: Regenerate export files

Run `/export-validate Paris` to regenerate all export files from the enriched `beats.json` and `poi-raw.json`.

Verify:
```bash
.venv/bin/python -c "
import json, glob
for f in sorted(glob.glob('data/paris/export/*.json')):
    data = json.load(open(f))
    for poi in data:
        for beat in poi.get('beats', []):
            assert 'entities' in beat, f'{f}: beat missing entities'
            assert 'sensory_anchor' in beat, f'{f}: beat missing sensory_anchor'
            assert 'est_spoken_seconds' in beat, f'{f}: beat missing est_spoken_seconds'
            assert 'narrative_function' in beat, f'{f}: beat missing narrative_function'
            assert 'beat_type' in beat, f'{f}: beat missing beat_type'
            assert 'emotional_register' in beat, f'{f}: beat missing emotional_register'
        assert 'poi_role' in poi or 'poi_role' not in poi  # optional on export
    print(f'  OK: {f.split(\"/\")[-1]}')
print('All export files validated.')
"
```

### Task 4: Upload and verify

Ensure backend is running: `GET http://localhost:8000/api/v1/nodes/Lens?limit=1` returns 200.

Run `/upload Paris --all` to upload all enriched data.

Verify enrichment fields in Neo4j:
```bash
# Check a beat node has enrichment fields
curl -s http://localhost:8000/api/v1/nodes/NarrativeBeat?limit=3 | python3 -m json.tool | head -40

# Check a POI node has poi_role
curl -s "http://localhost:8000/api/v1/nodes/POI?limit=3" | python3 -m json.tool | head -30

# Cross-POI entity overlap (AC-7) — run via cypher-shell
echo "MATCH (p1:POI)-[:HAS_BEAT]->(b1:NarrativeBeat), (p2:POI)-[:HAS_BEAT]->(b2:NarrativeBeat)
WHERE p1 <> p2 AND any(e IN b1.entities WHERE e IN b2.entities)
RETURN p1.name AS poi1, p2.name AS poi2, [e IN b1.entities WHERE e IN b2.entities] AS shared
LIMIT 20" | cypher-shell -u neo4j -p password
```

Run regression:
```bash
.venv/bin/python -m pytest tests/test_export_consistency.py tests/test_gravity_distribution.py tests/test_lens_drift.py -v
```

**What NOT to touch:** Backend code (Scope 1 already updated models). Data source files (Scope 2 already enriched). Beat extraction pipeline skills (companion scope).

Before starting, confirm you understand the full scope and flag any conflicts with the existing codebase or assumptions you are making.
```

---

## Part D — Best Practices Implementation Checklist

| Practice | Scope(s) | How to verify |
|---|---|---|
| New fields are optional with defaults (backward compatible) | Scope 1 | `NarrativeBeatCreate(script_body='test')` works without enrichment fields |
| No secrets in classification prompts | Scope 2 | Review skill file — no API keys hardcoded |
| Existing regression tests pass after all changes | Scope 1, 3 | `pytest tests/ -v` green |
| Enrichment metadata tracked (`_enrichment` block) | Scope 2 | Every enriched beat has model/timestamp/version |
| Entity extraction excludes city name and common geography (R-2) | Scope 2 | Spot-check: "Paris" and "Seine" not in entity lists for most beats |
| Distribution check for classification consistency (R-1) | Scope 2 | No enum value >70% of beats |
| Sensory anchor spot-check for accuracy (R-3, AC-3) | Scope 2 | 20 sampled `true` beats verified by human |
| Pipeline skill specs updated for enrichment fields (B-1, B-2) | Scope 3 | `export-validate.md` and `upload.md` list all fields |
| Data inventory updated per SECURITY_PRIVACY_PRACTICES.md §16 | Scope 3 | New fields documented as "derived editorial metadata, no PII" |
