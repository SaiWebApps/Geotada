# Scopes: Area Nodes with Spatial Containment

**Date:** 2026-04-09
**Spec:** [02-spec.md](02-spec.md)
**Thinking mode:** Delivery planner — "What's the smallest thing we can ship and verify?"

---

## AC Mapping

| AC | Description | Scope |
|----|-------------|-------|
| AC-1 | Area node creation via API | Scope 1 |
| AC-2 | MERGE idempotency on compound key | Scope 1 |
| AC-3 | WITHIN edge creation + MERGE | Scope 1 |
| AC-4 | Hierarchical containment query | Scope 4 |
| AC-5 | Area has beats (migrated from POI) | Scope 3 |
| AC-6 | 7 migrated POIs no longer exist as POI | Scope 3 |
| AC-7 | Point-in-polygon utility | Scope 4 |
| AC-8 | Area.centroid spatial proximity query | Scope 1 |

---

### Scope 1: Area CRUD Foundation

**What:** Add Area node type and WITHIN relationship to Neo4j schema, Pydantic models, CRUD layer, and REST API — the full vertical slice needed to create, read, update, and delete Areas and WITHIN edges.

**Acceptance criteria:** AC-1, AC-2, AC-3, AC-8

**Depends on:** None.

**Verification commands:**

```bash
# 1. Create an Area node via API
curl -s -X POST http://localhost:8000/api/v1/nodes/Area \
  -H "Content-Type: application/json" \
  -d '{"name":"Test Arrondissement","area_type":"district","city_name":"Paris","boundary":[[48.85,2.34],[48.86,2.34],[48.86,2.35],[48.85,2.35],[48.85,2.34]],"centroid_lat":48.855,"centroid_lng":2.345,"short_description":"Test"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['id'], 'missing id'; assert d['properties']['city_name']=='Paris', 'missing city_name'; print('AC-1 PASS')"

# 2. Create same Area again — should return same node (MERGE idempotency)
curl -s -X POST http://localhost:8000/api/v1/nodes/Area \
  -H "Content-Type: application/json" \
  -d '{"name":"Test Arrondissement","area_type":"district","city_name":"Paris","boundary":[[48.85,2.34],[48.86,2.34],[48.86,2.35],[48.85,2.35],[48.85,2.34]],"centroid_lat":48.855,"centroid_lng":2.345}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('AC-2 PASS — returned existing node:', d['id'])"

# 3. Verify MERGE didn't duplicate (count should be 1)
curl -s http://localhost:8000/api/v1/nodes/Area | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['total']==1, f'expected 1 Area, got {d[\"total\"]}'; print('AC-2 PASS — no duplication')"

# 4. Run tests
pytest tests/ -k "area or within" -v
```

**Estimated sessions:** 1

---

### Scope 2: Paris Area Hierarchy

**What:** Fetch simplified boundary polygons from OSM Overpass API for Paris's 7 arrondissements (1st–7th) plus named sub-areas (Île de la Cité, Île Saint-Louis, Les Halles neighborhood, Latin Quarter, etc.), create Area nodes, and wire the `(:Area)-[:WITHIN]->(:Area)` hierarchy: sub-areas → arrondissements → Paris city.

**Acceptance criteria:** None directly (enables AC-4, which is verified in Scope 4). This scope creates the container structure that Scopes 3 and 4 populate.

**Depends on:** Scope 1.

**Verification commands:**

```bash
# 1. Verify Paris city Area exists
python3 -c "
from neo4j import GraphDatabase
d = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j','password'))
with d.session() as s:
    r = s.run(\"MATCH (a:Area {name:'Paris', area_type:'city'}) RETURN a.name, a.city_name\").single()
    assert r, 'Paris city Area not found'
    print('PASS — Paris city Area exists')
d.close()
"

# 2. Verify 7 arrondissements exist and are WITHIN Paris
python3 -c "
from neo4j import GraphDatabase
d = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j','password'))
with d.session() as s:
    r = s.run(\"MATCH (a:Area {area_type:'district'})-[:WITHIN]->(c:Area {name:'Paris'}) RETURN count(a) AS cnt\").single()
    assert r['cnt'] == 7, f'Expected 7 arrondissements, got {r[\"cnt\"]}'
    print(f'PASS — {r[\"cnt\"]} arrondissements WITHIN Paris')
d.close()
"

# 3. Verify sub-areas (islands, neighborhoods) are WITHIN their arrondissements
python3 -c "
from neo4j import GraphDatabase
d = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j','password'))
with d.session() as s:
    r = s.run(\"MATCH (sub:Area)-[:WITHIN]->(arr:Area {area_type:'district'}) WHERE sub.area_type IN ['island','neighborhood','corridor'] RETURN sub.name, arr.name ORDER BY arr.name\").data()
    for row in r:
        print(f'  {row[\"sub.name\"]} WITHIN {row[\"arr.name\"]}')
    assert len(r) >= 2, f'Expected at least 2 sub-areas, got {len(r)}'
    print(f'PASS — {len(r)} sub-areas nested in arrondissements')
d.close()
"

# 4. Verify all Areas have boundary data (5-15 vertices)
python3 -c "
from neo4j import GraphDatabase
d = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j','password'))
with d.session() as s:
    r = s.run(\"MATCH (a:Area) WHERE a.boundary IS NULL OR size(a.boundary) < 10 RETURN a.name, a.area_type\").data()
    assert len(r) == 0, f'Areas missing boundary: {r}'
    print('PASS — all Areas have boundary data')
d.close()
"
```

**Estimated sessions:** 1–2 (depends on Overpass API response and polygon simplification work)

---

### Scope 3: POI-to-Area Migration

**What:** Convert 7 misclassified POIs (Île de la Cité, Île Saint-Louis, Les Halles, Rue Mouffetard, Rue Visconti, Rue Chanoinesse, Grands Boulevards) to Area nodes. Transfer all HAS_BEAT and TAGGED_WITH edges. Split Les Halles into Area (neighborhood) + POI (Forum des Halles). Delete the old POI nodes. Verify zero beat loss.

**Acceptance criteria:** AC-5, AC-6

**Depends on:** Scope 1, Scope 2 (migrated Areas need WITHIN edges to their arrondissements, which must exist first).

**Verification commands:**

```bash
# 1. Verify migrated POIs no longer exist (AC-6)
python3 -c "
from neo4j import GraphDatabase
d = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j','password'))
migrated = ['Île de la Cité','Île Saint-Louis','Les Halles','Rue Mouffetard','Rue Visconti','Rue Chanoinesse','Grands Boulevards']
with d.session() as s:
    r = s.run('MATCH (n:POI) WHERE n.name IN \$names RETURN n.name', names=migrated).data()
    assert len(r) == 0, f'Still POI nodes: {[x[\"n.name\"] for x in r]}'
    print('AC-6 PASS — no migrated POIs remain')
d.close()
"

# 2. Verify Île de la Cité Area has its beats (AC-5)
python3 -c "
from neo4j import GraphDatabase
d = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j','password'))
with d.session() as s:
    r = s.run(\"MATCH (a:Area {name:'Île de la Cité'})-[:HAS_BEAT]->(b:NarrativeBeat) RETURN count(b) AS cnt\").single()
    assert r['cnt'] >= 5, f'Expected >=5 beats, got {r[\"cnt\"]}'
    print(f'AC-5 PASS — Île de la Cité has {r[\"cnt\"]} beats')
d.close()
"

# 3. Verify beats retained their TAGGED_WITH lens edges
python3 -c "
from neo4j import GraphDatabase
d = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j','password'))
with d.session() as s:
    r = s.run(\"MATCH (a:Area)-[:HAS_BEAT]->(b:NarrativeBeat)-[:TAGGED_WITH]->(l:Lens) WHERE a.name IN ['Île de la Cité','Île Saint-Louis','Rue Visconti','Rue Chanoinesse'] RETURN a.name, count(DISTINCT l) AS lens_count\").data()
    for row in r:
        assert row['lens_count'] > 0, f'{row[\"a.name\"]} has no lens tags'
        print(f'  {row[\"a.name\"]}: {row[\"lens_count\"]} distinct lenses')
    print('PASS — all migrated Area beats retain lens tags')
d.close()
"

# 4. Verify Les Halles split: Area exists AND Forum des Halles POI exists
python3 -c "
from neo4j import GraphDatabase
d = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j','password'))
with d.session() as s:
    area = s.run(\"MATCH (a:Area {name:'Les Halles'}) RETURN a.area_type\").single()
    poi = s.run(\"MATCH (p:POI {name:'Forum des Halles'}) RETURN p.name\").single()
    assert area, 'Les Halles Area not found'
    assert area['a.area_type'] == 'neighborhood', f'Wrong type: {area[\"a.area_type\"]}'
    assert poi, 'Forum des Halles POI not found'
    print('PASS — Les Halles split: Area (neighborhood) + POI (Forum des Halles)')
d.close()
"

# 5. Verify total beat count unchanged (no beats lost or duplicated)
# Run this BEFORE migration to capture baseline, then AFTER to compare
python3 -c "
from neo4j import GraphDatabase
d = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j','password'))
with d.session() as s:
    r = s.run('MATCH (b:NarrativeBeat) RETURN count(b) AS cnt').single()
    print(f'Total beats: {r[\"cnt\"]} (compare against pre-migration count)')
d.close()
"
```

**Estimated sessions:** 1–2

---

### Scope 4: POI Containment Assignment

**What:** Build a point-in-polygon Python utility using Shapely, then assign every remaining Paris POI to its containing Area(s) via WITHIN edges. Uses postal codes from export data and point-in-polygon as verification. After this scope, the full hierarchical query `POI → sub-area → arrondissement → city` works.

**Acceptance criteria:** AC-4, AC-7

**Depends on:** Scope 1, Scope 2, Scope 3 (migration must complete first so we don't assign WITHIN edges to POIs that are about to become Areas).

**Verification commands:**

```bash
# 1. Point-in-polygon utility test (AC-7)
python3 -c "
from src.utils.spatial import point_in_areas
# Notre-Dame: should be in Île de la Cité AND 4th Arrondissement
results = point_in_areas(48.8530, 2.3499)
names = [r['name'] for r in results]
assert 'Île de la Cité' in names, f'Missing Île de la Cité in {names}'
assert '4th Arrondissement' in names, f'Missing 4th Arr in {names}'
print(f'AC-7 PASS — Notre-Dame contained in: {names}')
"

# 2. Full hierarchical containment query (AC-4)
python3 -c "
from neo4j import GraphDatabase
d = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j','password'))
with d.session() as s:
    r = s.run(\"\"\"
        MATCH (p:POI {name:'Notre-Dame Cathedral'})-[:WITHIN]->(island:Area)-[:WITHIN]->(arr:Area)-[:WITHIN]->(city:Area)
        RETURN p.name, island.name, island.area_type, arr.name, arr.area_type, city.name, city.area_type
    \"\"\").single()
    assert r, 'Hierarchical path not found'
    assert r['island.name'] == 'Île de la Cité'
    assert r['arr.name'] == '4th Arrondissement'
    assert r['city.name'] == 'Paris'
    print('AC-4 PASS — Notre-Dame → Île de la Cité → 4th Arr → Paris')
d.close()
"

# 3. Verify all POIs have at least one WITHIN edge
python3 -c "
from neo4j import GraphDatabase
d = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j','password'))
with d.session() as s:
    orphans = s.run(\"\"\"
        MATCH (p:POI) WHERE NOT (p)-[:WITHIN]->(:Area) RETURN p.name
    \"\"\").data()
    if orphans:
        print(f'WARNING — {len(orphans)} POIs without WITHIN: {[x[\"p.name\"] for x in orphans]}')
    else:
        print('PASS — all POIs have WITHIN edges')
d.close()
"

# 4. Run full test suite (regression check across all scopes)
pytest tests/ -v
```

**Estimated sessions:** 1

---

## Scope Hammering

| Scope | Could we ship without it? | Verdict |
|-------|--------------------------|---------|
| 1: Area CRUD Foundation | No — everything depends on this | **Must-have** |
| 2: Paris Area Hierarchy | No — migration and containment need containers to exist | **Must-have** |
| 3: POI-to-Area Migration | No — 7 POIs are wrong today, beats are on fake nodes | **Must-have** |
| 4: POI Containment Assignment | Technically yes (hierarchy and migration work without it), but AC-4 and AC-7 require it, and "all POIs in the 5th" is a core tour-builder query | **Must-have** |

No nice-to-haves. All 4 scopes are required by acceptance criteria. The spec is already tightly scoped.

---

## Dependency Graph

```
Scope 1 (Foundation)
  ↓
Scope 2 (Paris Hierarchy)
  ↓
Scope 3 (Migration)
  ↓
Scope 4 (POI Containment)
```

Linear chain — each scope depends on the previous. No parallelization possible because each scope's data is consumed by the next.
