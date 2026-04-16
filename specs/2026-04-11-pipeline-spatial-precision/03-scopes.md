# 03-scopes: Unified Extraction Pipeline

**Stage:** 3 — Scopes (Delivery plan)
**Date:** 2026-04-13 (rev. post-red-team)
**Scope:** `01-scope.md` + `02-spec.md` in this folder

---

## Split rationale

The 6-way split was committed in `01-scope.md` after Stage 4 red-team surfaced two prerequisites: POI city-tagging (no POI currently carries a `city` property; MERGE is globally keyed on `name` alone — incompatible with multi-city Cypher in AC-3/AC-6) and tour-builder Scenario 2 completion (required-field set isn't locked until both design scenarios are hand-drafted; running a full re-extraction before that risks a second wipe).

Code investigation resolved `Open Question 1` from the spec — `duration_sec` is canonical (50 code hits vs 18 for `est_spoken_seconds`), so Scope 1 migrates the lesser-used name away.

Paris has one book currently (`Around and About Paris`, chunked 22 ways), so "smallest book" = smallest chunk for validation throughout.

---

### Scope 1: Duration Field Unification

**What:** Adopt `duration_sec` as the canonical beat duration field across code, schemas, tests, and skill prompts; remove `est_spoken_seconds`. **Does not migrate `data/paris/beats.json`** — that file is wiped and regenerated in Scope 6, so migrating it here would be wasted work.

**Acceptance criteria:** AC-1

**Depends on:** None

**Verification commands:**

```bash
# AC-1a — deprecated name removed from code and frontend (word-boundaries to avoid false positives)
grep -rE "\best_spoken_seconds\b" src/ frontend/ scripts/ tests/ .claude/commands/ | wc -l
# Expected: 0

# AC-1b — Pydantic model validates against a fresh fixture emitting the new field name
.venv/bin/python -c "
import json
from src.api.models.nodes import NarrativeBeatCreate
fixture = json.load(open('tests/fixtures/beats_duration_sec.json'))
for b in fixture:
    NarrativeBeatCreate(**b)
print(f'validated {len(fixture)} fixture beats')
"
# Live data/paris/beats.json intentionally NOT validated — it still carries the old name
# and will be wiped in Scope 6. Validating it here would require a migration we don't need.

# AC-1c — full test suite passes
.venv/bin/pytest tests/ -q
```

**Estimated sessions:** 1

---

### Scope 2: POI City-Tagging + MERGE Key + Read-Path Multi-City Safety

**What:** Add `city_name` property (matching the `Area.city_name` precedent in `src/api/models/nodes.py:127` — no new convention) to every POI in `data/{city}/poi-raw.json` and to every POI node in Neo4j, then change the MERGE key from `{name: $name}` to `{name: $name, city_name: $city_name}` in *both* write paths, and update read paths to filter by `city_name`.

**Concrete task list (ordered, non-negotiable):**

1. **Backfill existing POI nodes first.** Run `MATCH (p:POI) WHERE p.city_name IS NULL SET p.city_name = 'paris'` *before* any MERGE-key change. This prevents the MERGE switch from treating the 239 existing Paris POIs as non-matches and creating duplicates that orphan the 548 `HAS_BEAT` edges.
2. **Backfill the data file.** Add `city_name: "paris"` to every entry in `data/paris/poi-raw.json`.
3. **Update both write paths:**
   - `src/seed/locations.py` — `MERGE (p:POI {name: $name})` → `MERGE (p:POI {name: $name, city_name: $city_name})`
   - `src/api/crud/nodes.py` — the POI MERGE (and the `force_create` CREATE branch if it exists) — same change. This is the real production write path the upload skill uses via `POST /api/nodes/POI`.
4. **Update Pydantic models.** `POICreate` in `src/api/models/nodes.py` adds required `city_name: str`.
5. **Update all read-side POI-by-name queries to add a `city_name` filter:**
   - `src/api/routes/graph.py:74`
   - `src/seed/narratives.py:17`
   - `src/audio/pipeline.py:208` (implicit POI lookup — confirm and patch)
   - `.claude/commands/upload.md:59` (upload skill's beat-lookup Cypher)
6. **Update the upload skill prompt** (`.claude/commands/upload.md`) to pass `city_name` on every POI/beat operation.

**Why it's here:** AC-3c and AC-6 rely on `MATCH (p:POI {city_name: 'paris'})` Cypher; today that filter matches zero nodes because POIs have no city property. Read-path queries today match globally by name — under multi-city (Notre-Dame Paris vs Notre-Dame Reims) they silently return the wrong POI. Honors `feedback_merge_key_multicity` — multi-city safety belongs in the data model from day one.

**Acceptance criteria:** AC-3/AC-6 precondition (enables those ACs to run); no AC is owned here beyond the schema prep (see mapping table).

**Depends on:** Scope 1 (optional ordering; no hard dependency, but Scope 1 is fast and independent)

**Verification commands:**

```bash
# Every POI entry in data file has city_name
.venv/bin/python -c "
import json
pois = json.load(open('data/paris/poi-raw.json'))
missing = [p['name'] for p in pois if not p.get('city_name')]
assert not missing, f'POIs missing city_name: {missing[:5]}'
print(f'{len(pois)} POIs all have city_name')
"

# Neo4j: every POI node has city_name, and the Paris backfill covered all 239
cypher-shell -u neo4j -p "$NEO4J_PASSWORD" -a "$NEO4J_URI" "
MATCH (p:POI) WHERE p.city_name IS NULL RETURN count(p) AS missing_city;
MATCH (p:POI {city_name: 'paris'}) RETURN count(p) AS paris_count;
"
# Expected: missing_city = 0, paris_count = 239 (or current known count)

# MERGE keys in BOTH write paths use (name, city_name)
grep -E "MERGE \(p:POI \{" src/seed/locations.py src/api/crud/nodes.py
# Expected: both lines show MERGE (p:POI {name: $name, city_name: $city_name})

# No stray read-path POI lookups without a city filter
grep -rE "MATCH \([a-z]+:POI \{name: \\\$?[a-zA-Z_]+\}\)" src/ .claude/commands/ | grep -v city_name | wc -l
# Expected: 0 (any remaining POI-by-name match without city_name is a failure)

# Re-upload-of-existing-POI regression: uploading Paris POIs after the change produces zero new nodes
# (Run the upload skill in dry-run or test namespace with the existing poi-raw.json; count before/after)
# Expected: before_count == after_count == 239
```

**Estimated sessions:** 1-2 (widened from 1 due to read-path sweep)

---

### Scope 3: Tour-Builder Scenario 2 Hand-Drafting Completion

**What:** Finish `Docs/tour-builder/examples/` Scenario 2 (pre-trip planning, 4 hr tour from Eiffel Tower, art + faith interests, one-way) by hand with the founder. Harvest any additional required beat or POI fields the scenario surfaces (design.md lists 10 open questions, several of which may force schema additions — e.g. Q4 thin-lens handling, Q8 `poi_role` states, Q9 `establishing` semantics). Lock the unified skill's field set based on the union of Scenario 1 + Scenario 2 requirements.

**Why it's here:** Running a full re-extraction in Scope 6 before Scenario 2 surfaces its requirements risks a second full wipe and re-extraction. The design is being built collaboratively through hand-drafting; making it a scope step ties the work to this project's plan rather than floating as parallel-but-related effort.

**Acceptance criteria (all three artifacts must exist as commits; no vibes-check exits):**
1. **Scenario 2 tour committed** to `Docs/tour-builder/examples/tour-b-*.md`, matching the Scenario 1 quality bar (every sentence source-backed with beat IDs, theme emerges bottom-up, closing-callback structure present, 60% silence budget respected).
2. **Design.md Open Questions 4, 8, and 9 have written resolutions committed** — not parked, not "revisit later." Specifically: Q4 (thin-lens interest coverage), Q8 (`poi_role` state semantics for `stop`/`setting`/`walk_by_only`), Q9 (`establishing` beat type definition). Each gets a concrete decision in `Docs/tour-builder/design.md` with the reasoning captured.
3. **02-spec.md amended** — any new required beat or POI field that Scenarios 1+2 surfaced is added to §Outputs and to AC-4's required-field list, with the amendment committed before Scope 4 starts. If no new fields emerged, the commit explicitly records "Scenarios 1+2 complete; no new required fields needed" in the 02-spec.md commit message.

**Depends on:** None for drafting; must complete before Scope 4 starts

**Verification:**
- `ls Docs/tour-builder/examples/tour-b-*.md` returns at least one file
- `grep -A 3 "^### Q4\|^### Q8\|^### Q9" Docs/tour-builder/design.md` shows explicit resolution text for each (not "open" / "TBD")
- `git log --oneline 02-spec.md` shows a post-Scope-3 commit touching the §Outputs or AC-4 region (or a commit message explicitly noting no changes needed)

**Estimated sessions:** 2-3 (collaborative drafting, not code)

---

### Scope 4: Unified Extraction Skill (base) with Multi-City beat_id

**What:** Create the unified extraction skill (merging `beat-from-book` + `beat-enrich`) that emits one-pass beats with all required fields (including any added in Scope 3) and the new multi-city-safe `beat_id` format `{city}_{poi_slug}_{lens_slug}_{book_slug}_{topic_slug}`. Sub-POI emergence and establishing-beat coverage are NOT in this scope — deferred to Scope 5.

**Acceptance criteria:** AC-4 (all required beat fields populated), AC-5 (sensory_anchor → structured physical_cues), AC-8 (no city hardcoded in skill source, fixture-city run passes)

**Depends on:** Scope 1, Scope 3 (Scope 2 not a hard dep for this scope's ACs, but sequencing in practice places it after Scope 2)

**Verification commands:**

```bash
# Test run: execute the unified skill on a single small chunk to a test output location
# (e.g., data/paris/_scope4_test/beats.json). Then:

# AC-4 — every emitted beat has required fields, passes NarrativeBeatCreate model
.venv/bin/python -c "
import json
from src.api.models.nodes import NarrativeBeatCreate
beats = json.load(open('data/paris/_scope4_test/beats.json'))
for b in beats:
    NarrativeBeatCreate(**b)
    assert b['beat_id'].split('_')[0] == 'paris', f\"bad city prefix: {b['beat_id']}\"
    assert all(k in b for k in ('entities','sensory_anchor','narrative_function','beat_type','emotional_register','physical_cues','duration_sec','beat_id'))
print(f'AC-4 pass: {len(beats)} beats')
"

# AC-5 — every sensory_anchor beat has structured physical_cues
.venv/bin/python -c "
import json
beats = json.load(open('data/paris/_scope4_test/beats.json'))
for b in beats:
    if b['sensory_anchor']:
        assert len(b['physical_cues']) >= 1, f\"{b['beat_id']}: sensory_anchor true but no cues\"
        for c in b['physical_cues']:
            assert 'cue' in c and 'direction' in c and 'feature_type' in c, f\"{b['beat_id']}: unstructured cue\"
print('AC-5 pass')
"

# AC-8 part 1 — fixture-city run completes and emits correct prefix
.venv/bin/python scripts/run_unified_skill.py --city test_city_xx --input tests/fixtures/mini_chunk.txt --output /tmp/_ac8_test/
.venv/bin/python -c "
import json
beats = json.load(open('/tmp/_ac8_test/beats.json'))
for b in beats:
    assert b['beat_id'].startswith('test_city_xx_'), f'AC-8 fixture city failure: {b[\"beat_id\"]}'
print(f'AC-8 fixture pass: {len(beats)} beats')
"

# AC-8 part 2 — grep sweep (broader city list, word boundaries)
grep -iE "\b(paris|london|boston|rome|tokyo|reims|lyon|marseille|new_york)\b" .claude/commands/unified-beat-extract.md \
  | grep -viE "(example|ARGUMENTS|\$\{|<!--|^\s*#)" \
  | wc -l
# Expected: 0

# Within-run beat_id uniqueness
.venv/bin/python -c "
import json
beats = json.load(open('data/paris/_scope4_test/beats.json'))
ids = [b['beat_id'] for b in beats]
assert len(ids) == len(set(ids)), 'collision detected'
print('uniqueness ok')
"
```

**Note on AC-4/AC-5 scope:** These ACs hold on Scope 4's test output (partial — one chunk). Scope 6 re-runs the same assertions on the full post-re-extraction `data/paris/beats.json` as a regression check.

**Estimated sessions:** 2-3

---

### Scope 5: Sub-POI Emergence + Establishing-Beat Coverage + Single-Chunk Validation Gate

**What:** Extend the unified skill to emit sub-POIs (semantic detection, source-backed `poi_role` with `source_passage`, `poi-geocode` invocation for coordinates, then `poi-dedup` handoff). Enforce establishing-beat coverage with the tier-≤2 auto-flag rule. Run the single-chunk validation gate on the smallest Paris chunk, end-to-end, including upload to a test Neo4j namespace.

**Acceptance criteria:** AC-2 (single-chunk validation), AC-6 (establishing-beat coverage), AC-9 (sub-POI source-backed poi_role)

**Depends on:** Scope 2 (POI `city_name` property + MERGE key must exist for AC-6 Cypher to run), Scope 4

**Verification commands:**

```bash
# Run unified skill on smallest chunk; output to data/paris/_scope5_test/
# Upload to a test Neo4j database or scoped namespace before running Cypher checks.

# AC-2a — zero within-run beat_id collisions
.venv/bin/python -c "
import json
beats = json.load(open('data/paris/_scope5_test/beats.json'))
ids = [b['beat_id'] for b in beats]
assert len(ids) == len(set(ids)); print('no collisions')
"

# AC-2b — 100% of beats either match existing POI or emit new_poi: true
.venv/bin/python -c "
import json
beats = json.load(open('data/paris/_scope5_test/beats.json'))
pois = {p['name'] for p in json.load(open('data/paris/poi-raw.json'))}
orphans = [b for b in beats if b['poi_name'] not in pois and not b.get('new_poi')]
assert not orphans, f'orphans: {[b[\"beat_id\"] for b in orphans]}'
print(f'AC-2b pass: {len(beats)} beats accounted for')
"

# AC-2c — sub-POI coords: round-trip within 10m, distinct from parent by ≥15m, confidence ≥70%
.venv/bin/python scripts/verify_sub_poi_coords.py --pois data/paris/poi-raw.json
# Script asserts for each sub-POI (parent_poi is not null):
#   (1) re-invoke poi-geocode on sub-POI name → haversine(new, stored) ≤ 10m
#   (2) haversine(sub-POI, parent POI) ≥ 15m (else OSM returned parent centroid — flag)
#   (3) poi-geocode confidence ≥ 0.70 (NORTHSTAR threshold)

# AC-2d — zero preservation-boundary fields touched (pre-snapshot created as Scope 5 task 1)
.venv/bin/python -c "
import json
pre = {p['name']: p for p in json.load(open('data/paris/_scope5_test/poi-raw.pre.json'))}
post = {p['name']: p for p in json.load(open('data/paris/poi-raw.json'))}
PRESERVED = ['importance_tier','lat','lon','name_variations','verified']
for name, p_pre in pre.items():
    p_post = post.get(name)
    assert p_post, f'POI dropped: {name}'
    for f in PRESERVED:
        assert p_pre.get(f) == p_post.get(f), f'{name}: {f} changed'
print('preservation ok')
"

# AC-2e + AC-9 — every new sub-POI has source_passage grounding poi_role
.venv/bin/python -c "
import json
pois = json.load(open('data/paris/poi-raw.json'))
sub_pois = [p for p in pois if p.get('parent_poi') and p.get('_new_in_scope5')]
for p in sub_pois:
    assert p.get('poi_role') in ('stop','setting','walk_by_only'), f\"{p['name']}: bad poi_role\"
    assert p.get('source_passage','').strip(), f\"{p['name']}: missing source_passage\"
print(f'AC-9 pass: {len(sub_pois)} sub-POIs, all source-grounded')
"
# Plus: ≥10% random-sample human spot-check confirming source_passage is faithful to source text

# AC-6 — every poi_role:stop POI has establishing beat OR valid not-applicable flag
cypher-shell -u neo4j -p "$NEO4J_PASSWORD" -a "$NEO4J_URI" "
MATCH (p:POI {city_name: 'paris', poi_role: 'stop'})
WHERE NOT EXISTS { MATCH (p)-[:HAS_BEAT]->(b:NarrativeBeat) WHERE b.narrative_function = 'establishing' }
  AND NOT (coalesce(p.establishing_not_applicable, false) = true AND p.importance_tier <= 2)
RETURN count(p) AS offenders;
"
# Expected: offenders = 0
# (This Cypher is only runnable after Scope 2 lands the city property on POIs.)
```

**Estimated sessions:** 3

---

### Scope 6: Full Paris Re-Extraction with Restore Archive + AC-4/AC-5 Regression

**What:** Implement restore-archive creation (with import round-trip validation), execute wipe-and-re-extract for all remaining Paris chunks, and verify preservation boundaries. Re-run AC-4 and AC-5 assertions as a regression on the full re-extracted output.

**Acceptance criteria:** AC-3 (preservation Cypher diff), AC-7 (restore archive), plus regression on AC-4 and AC-5

**Depends on:** Scope 5 (single-chunk validation gate must have passed)

**Verification commands:**

```bash
# AC-7a — archive files exist and are populated
ARCHIVE=$(ls -td data/paris/_restore/pre-re-extract-*/ | head -1)
test -s "${ARCHIVE}beats.json" && test -s "${ARCHIVE}neo4j-export.cypher" || echo "FAIL archive missing"

# AC-7b — SEMANTIC round-trip: import archive into scratch Neo4j, count beats, compare to pre-wipe production count
# (Regex counting CREATE statements is fragile across APOC / neo4j-admin export shapes — avoid.)
.venv/bin/python scripts/verify_archive_roundtrip.py \
    --archive "${ARCHIVE}" \
    --scratch-uri "${NEO4J_SCRATCH_URI}" \
    --city paris \
    --expected-pre-wipe-count "${PRE_WIPE_BEAT_COUNT}"
# Script:
#   1. Spins up or connects to scratch Neo4j, clears it
#   2. Runs archive cypher-shell import
#   3. MATCH (b:NarrativeBeat {city_name:'paris'}) RETURN count(b)
#   4. Asserts equal to $PRE_WIPE_BEAT_COUNT (captured pre-wipe in Scope 6 task 1)

# AC-3a — Area/WITHIN counts unchanged (compare against pre-wipe snapshot captured in Scope 6 task 1)
cypher-shell -u neo4j -p "$NEO4J_PASSWORD" -a "$NEO4J_URI" "
MATCH (a:Area {city_name: 'paris'}) WITH count(a) AS area_count
MATCH ()-[w:WITHIN]->(aa:Area {city_name: 'paris'}) RETURN area_count, count(w) AS within_count;
"
# Expected: area_count AND within_count equal values captured before Scope 6 wipe

# AC-3b — zero POIs lost preserved fields
cypher-shell -u neo4j -p "$NEO4J_PASSWORD" -a "$NEO4J_URI" "
MATCH (p:POI {city_name: 'paris'})
WHERE p.importance_tier IS NULL OR p.lat IS NULL OR p.lon IS NULL
RETURN count(p) AS missing_fields;
"
# Expected: missing_fields = 0

# AC-3c — pre-existing POI MERGE keys are a subset of post-extraction keys (now (name, city_name))
.venv/bin/python scripts/verify_poi_merge_subset.py \
    --pre data/paris/_restore/pre-re-extract-LATEST/poi-raw.json \
    --post data/paris/poi-raw.json \
    --city paris
# Script: assert {(p['name'], p['city_name']) for p in pre} ⊆ {(p['name'], p['city_name']) for p in post}

# AC-4 regression — full final beats.json passes Pydantic validation
.venv/bin/python -c "
import json
from src.api.models.nodes import NarrativeBeatCreate
beats = json.load(open('data/paris/beats.json'))
for b in beats: NarrativeBeatCreate(**b)
print(f'AC-4 regression pass: {len(beats)} beats')
"

# AC-5 regression — every sensory_anchor beat has structured physical_cues
.venv/bin/python -c "
import json
beats = json.load(open('data/paris/beats.json'))
for b in beats:
    if b['sensory_anchor']:
        assert len(b['physical_cues']) >= 1 and all('direction' in c and 'feature_type' in c for c in b['physical_cues'])
print('AC-5 regression pass')
"
```

**Estimated sessions:** 2

---

## AC-to-Scope Mapping

| AC | Scope | Verified at | Regression |
|---|---|---|---|
| AC-1 duration field | Scope 1 | Scope 1 | — |
| AC-2 single-chunk validation | Scope 5 | Scope 5 | — |
| AC-3 preservation Cypher diff | Scope 6 | Scope 6 | (enabled by Scope 2 POI city-tagging) |
| AC-4 all required fields | Scope 4 | Scope 4 (partial) | Scope 6 (full) |
| AC-5 sensory_anchor → cues | Scope 4 | Scope 4 (partial) | Scope 6 (full) |
| AC-6 establishing coverage | Scope 5 | Scope 5 | (enabled by Scope 2 POI city-tagging) |
| AC-7 restore archive | Scope 6 | Scope 6 | — |
| AC-8 no city hardcoding | Scope 4 | Scope 4 | — |
| AC-9 sub-POI source-backed poi_role | Scope 5 | Scope 5 | — |

All 9 ACs owned exactly once. AC-4/AC-5 owned by Scope 4 (where the feature lives); regression run at Scope 6 where the full output exists. Scope 2 (POI city-tagging) is a structural prerequisite — it doesn't own an AC but is required for AC-3/AC-6 Cypher to execute. Scope 3 (Scenario 2 completion) is a requirements-lock checkpoint — it doesn't own an AC but may amend 02-spec.md's field list before Scope 4 locks implementation.

## Scope hammering

- No scope is nice-to-have — each is load-bearing for the next.
- Sequential ordering enforced by dependencies; limited parallelization (Scopes 1, 2, 3 could run concurrently if staffed separately, but Scope 4 requires all three).
- Open Question 2 from `02-spec.md` (physical_cues enum values) resolves in Scope 4's implementation.
- Open Question 3 already resolved (promoted into AC-6 language in `02-spec.md`).
