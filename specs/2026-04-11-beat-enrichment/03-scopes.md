# Scopes: Beat & POI Metadata Enrichment

**Date:** 2026-04-11
**Spec:** `02-spec.md` in this folder

---

## Overview

Three scopes. The first updates the API model so enriched data can be created via the API. The second does the actual classification and writes enriched data to the JSON files. The third uploads the enriched data to Neo4j and verifies end-to-end.

---

### Scope 1: Schema & Model Updates

**What:** Add the 6 beat enrichment fields and `poi_role` to the Pydantic models and verify the CRUD layer passes them through to Neo4j.

**Acceptance criteria:** AC-8

**Depends on:** None

**Verification commands:**
```bash
# Models accept new fields without error
.venv/bin/python -c "
from src.api.models.nodes import NarrativeBeatCreate, POICreate
b = NarrativeBeatCreate(script_body='test', entities=['x'], sensory_anchor=True, est_spoken_seconds=10, narrative_function='hook', beat_type='anecdote', emotional_register='dramatic')
p = POICreate(name='test', latitude=0.0, longitude=0.0, importance_tier=3, poi_role='stop')
print('Beat fields:', b.model_dump().keys())
print('POI fields:', p.model_dump().keys())
"

# Existing tests still pass
.venv/bin/python -m pytest tests/ -v --tb=short
```

**Estimated sessions:** 1

---

### Scope 2: Classification Backfill

**What:** Build and run the classification pass that reads existing `beats.json` and `poi-raw.json`, classifies every beat and POI, and writes enriched data back to those files.

**Acceptance criteria:** AC-1, AC-2, AC-3, AC-4

**Depends on:** None (writes to JSON files, not to Neo4j — model updates are independent)

**Verification commands:**
```bash
# All beats have all 6 fields with valid values
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
    assert b.get('narrative_function') in VALID_NF, f'{b[\"beat_id\"]}: bad narrative_function {b.get(\"narrative_function\")}'
    assert b.get('beat_type') in VALID_BT, f'{b[\"beat_id\"]}: bad beat_type {b.get(\"beat_type\")}'
    assert b.get('emotional_register') in VALID_ER, f'{b[\"beat_id\"]}: bad emotional_register {b.get(\"emotional_register\")}'
    # AC-2: verify est_spoken_seconds
    expected = round(len(b['script_body'].split()) / 2.5)
    assert b['est_spoken_seconds'] == expected, f'{b[\"beat_id\"]}: est_spoken_seconds {b[\"est_spoken_seconds\"]} != {expected}'
print(f'All {len(beats)} beats validated.')
"

# All POIs have poi_role
.venv/bin/python -c "
import json
VALID_ROLES = {'stop','setting','walk_by_only'}
pois = json.load(open('data/paris/poi-raw.json'))
for p in pois:
    assert p.get('poi_role') in VALID_ROLES, f'{p[\"name\"]}: bad poi_role {p.get(\"poi_role\")}'
print(f'All {len(pois)} POIs validated.')
"

# Regression tests still pass
.venv/bin/python -m pytest tests/test_export_consistency.py tests/test_gravity_distribution.py tests/test_lens_drift.py -v
```

**Estimated sessions:** 1-2 (classification prompt design + run + spot-check sensory anchors)

---

### Scope 3: Export, Upload & Verify

**What:** Regenerate export files to include enrichment fields, upload enriched data to Neo4j, and verify entity-based graph queries work end-to-end.

**Acceptance criteria:** AC-5, AC-6, AC-7

**Depends on:** Scope 1 (model accepts new fields), Scope 2 (JSON files are enriched)

**Verification commands:**
```bash
# Export files include enrichment fields
.venv/bin/python -c "
import json, glob
for f in sorted(glob.glob('data/paris/export/*.json')):
    data = json.load(open(f))
    for poi in data:
        for beat in poi.get('beats', []):
            assert 'entities' in beat, f'{f}: {poi[\"name\"]} beat missing entities'
            assert 'sensory_anchor' in beat, f'{f}: {poi[\"name\"]} beat missing sensory_anchor'
            assert 'est_spoken_seconds' in beat, f'{f}: {poi[\"name\"]} beat missing est_spoken_seconds'
    print(f'  OK: {f.split(\"/\")[-1]} ({len(data)} POIs)')
print('All export files validated.')
"

# After upload: query Neo4j for enrichment fields on a beat
curl -s http://localhost:8000/api/v1/nodes/NarrativeBeat?limit=5 | python3 -m json.tool | grep -E 'entities|sensory_anchor|narrative_function'

# AC-7: Cross-POI entity overlap query
curl -s -X POST http://localhost:8000/api/v1/graph/query -H 'Content-Type: application/json' -d '{
  "query": "MATCH (p1:POI)-[:HAS_BEAT]->(b1:NarrativeBeat), (p2:POI)-[:HAS_BEAT]->(b2:NarrativeBeat) WHERE p1 <> p2 AND any(e IN b1.entities WHERE e IN b2.entities) RETURN p1.name AS poi1, p2.name AS poi2, [e IN b1.entities WHERE e IN b2.entities] AS shared_entities LIMIT 20"
}'
# Expected: returns pairs like (Conciergerie, Place de la Concorde) sharing "Marie-Antoinette"
```

**Estimated sessions:** 1

---

## Scope summary

| # | Scope | ACs | Depends on | Sessions |
|---|---|---|---|---|
| 1 | Schema & Model Updates | AC-8 | None | 1 |
| 2 | Classification Backfill | AC-1, AC-2, AC-3, AC-4 | None | 1-2 |
| 3 | Export, Upload & Verify | AC-5, AC-6, AC-7 | 1, 2 | 1 |

Scopes 1 and 2 can run in parallel. Scope 3 depends on both.

**Nice-to-haves:** None. All three scopes are required to deliver usable enrichment data to the tour builder.
