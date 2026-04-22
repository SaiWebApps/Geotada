> **DEPRECATED (2026-04-21):** Merged into `/unified-beat-extract` which extracts AND classifies in one pass. This skill is kept only for backward-compat with existing beats that were extracted by `beat-from-book` and need post-hoc enrichment until Scope 6 re-extraction wipes them. Do not use for new work.

You are a tourism data analyst specializing in content classification for GPS-triggered audio tours. You classify narrative beats and POIs with structured metadata to support automated tour generation.

Your task: enrich beats and POIs for the city of **$ARGUMENTS** (default: "paris").

---

## INPUT

1. Beat data: `data/{city}/beats.json`
2. POI data: `data/{city}/poi-raw.json`
3. Field definitions and enum values: defined in this skill below

---

## PHASE 1 — BEAT ENRICHMENT

Read `data/{city}/beats.json`. Group beats by `poi_name`.

For each POI batch (all beats sharing the same `poi_name`), classify every beat with 5 AI fields. Process all beats for one POI together so context-dependent fields (`narrative_function`) benefit from seeing siblings.

### Fields to classify

**entities** (list[str]):
Named people, historical events, specific buildings/monuments, and named groups mentioned in the beat.
- Use full proper names ("Philippe-Auguste", not "the king")
- INCLUDE: people, specific historical events, specific buildings/monuments, named groups
- EXCLUDE: the city name itself (e.g. "Paris"), common geographic features (Seine, Left Bank, Right Bank), and the POI's own name UNLESS the beat discusses it as a subject rather than just a location
- Min 0 entities, no max

**sensory_anchor** (bool):
`true` ONLY if the beat references something the user can currently see, hear, smell, or touch at the POI location.
- References to demolished/destroyed/moved things = `false`
- References to visible architectural features, plaques, views, textures = `true`
- Notre-Dame post-2019 fire: spire references = `false` (under reconstruction). West facade = `true`. Interior features = `false` unless exterior-visible.
- When uncertain, default to `false`

**narrative_function** (enum — pick ONE, the strongest):
- `hook` — strong opening candidate: surprising, provocative, or place-name origin
- `establishing` — explains what this POI IS: age, builder, basic identity
- `deepen` — adds depth to an already-introduced subject
- `climax` — high-drama payoff moment
- `scene_setter` — atmospheric, mood-setting
- `transition` — bridges between subjects
- `callback` — references or echoes another beat's content

**beat_type** (enum — pick ONE):
- `anecdote` — a specific story with characters and action
- `character_story` — biographical focus on a person
- `event` — something that happened at a specific time
- `architectural_detail` — describes physical structure
- `sensory_observation` — describes atmosphere/sound/light
- `factoid` — a discrete surprising fact
- `establishing` — basic identity of the POI

**emotional_register** (enum — pick ONE):
- `reverent` — respect, awe
- `somber` — death, loss, gravity
- `playful` — light, witty
- `dramatic` — high stakes, tension
- `wry` — ironic, understated
- `neutral` — informational, no strong tone

### Computed field (no AI)

**duration_sec** (int):
`round(word_count(script_body) / 2.5)` — 2.5 words/sec = 150 wpm spoken pace. Compute this from the text, do not use AI.

### Output per beat

Add all 6 fields directly to each beat object in the array. Also add an `_enrichment` metadata block:

```json
{
  "_enrichment": {
    "model": "claude-sonnet-4-6",
    "enriched_at": "2026-04-11T...",
    "version": "v1"
  }
}
```

### Processing rules

- Process POI batches sequentially. For each batch, read all beats' `script_body` texts, classify them together, then write results.
- Use temperature 0 equivalent: be deterministic and consistent.
- After classifying each batch, write the updated beats back to `beats.json` immediately (incremental saves prevent data loss).
- Preserve ALL existing fields on each beat. Only ADD the 6 new fields and `_enrichment`. Never remove or rename existing fields.

---

## PHASE 2 — POI ROLE CLASSIFICATION

After all beats are enriched, read `data/{city}/poi-raw.json`.

For each POI, classify with one field:

**poi_role** (enum):
- `stop` — a destination where users stop and listen. Default for tier 3-5 discrete buildings/monuments.
- `setting` — a geographic area providing contextual walking narration, not a destination itself. Large islands, boulevards, gardens used as through-routes.
- `walk_by_only` — never a stop; beats play while walking past. Tier 1-2 minor landmarks, plaques.

### Classification heuristics (use as starting defaults, override with judgment)

- Tier 1-2 → default `walk_by_only`
- Tier 3-5 discrete buildings/monuments → default `stop`
- Tier 3-5 with large footprint (trigger_radius >= 50m, or description mentions island/boulevard/garden/quarter) → candidate for `setting`
- Override heuristic with judgment based on the POI's `short_description` and its beat content from the enriched `beats.json`

### Output per POI

Add `poi_role` and `_poi_role_reasoning` (one sentence explaining the classification) to each POI object. Preserve all existing fields.

---

## PHASE 3 — VALIDATION

After both phases, run these validation checks:

```bash
# Validate all beats have valid enrichment fields
.venv/bin/python -c "
import json
VALID_NF = {'hook','deepen','transition','climax','callback','scene_setter','establishing'}
VALID_BT = {'anecdote','architectural_detail','character_story','event','sensory_observation','factoid','establishing'}
VALID_ER = {'reverent','somber','playful','dramatic','wry','neutral'}
beats = json.load(open('data/{city}/beats.json'))
for b in beats:
    assert 'entities' in b and isinstance(b['entities'], list), f'{b[\"beat_id\"]}: missing entities'
    assert 'sensory_anchor' in b and isinstance(b['sensory_anchor'], bool), f'{b[\"beat_id\"]}: missing sensory_anchor'
    assert 'duration_sec' in b and isinstance(b['duration_sec'], int), f'{b[\"beat_id\"]}: missing duration_sec'
    assert b.get('narrative_function') in VALID_NF, f'{b[\"beat_id\"]}: bad narrative_function'
    assert b.get('beat_type') in VALID_BT, f'{b[\"beat_id\"]}: bad beat_type'
    assert b.get('emotional_register') in VALID_ER, f'{b[\"beat_id\"]}: bad emotional_register'
    expected = round(len(b['script_body'].split()) / 2.5)
    assert b['duration_sec'] == expected, f'{b[\"beat_id\"]}: duration mismatch'
print(f'All {len(beats)} beats validated.')
"

# Distribution check
.venv/bin/python -c "
import json
from collections import Counter
beats = json.load(open('data/{city}/beats.json'))
for f in ['narrative_function', 'beat_type', 'emotional_register']:
    dist = Counter(b[f] for b in beats)
    total = len(beats)
    for val, count in dist.most_common():
        pct = count/total*100
        flag = ' WARNING' if pct > 70 else ''
        print(f'  {f}: {val} = {count} ({pct:.0f}%){flag}')
    print()
"

# Validate all POIs
.venv/bin/python -c "
import json
VALID_ROLES = {'stop','setting','walk_by_only'}
pois = json.load(open('data/{city}/poi-raw.json'))
for p in pois:
    assert p.get('poi_role') in VALID_ROLES, f'{p[\"name\"]}: bad poi_role'
print(f'All {len(pois)} POIs validated.')
"
```

Report the distribution of each enum field. Flag if any single value exceeds 70% of beats.

---

## RULES

- Never modify `script_body`, `beat_id`, `poi_name`, `key_claims`, or any other existing field
- Never remove beats or POIs from the arrays
- Never reorder the arrays
- Every beat must get all 6 fields — no partial enrichment
- Every POI must get `poi_role` — no exceptions
- Save incrementally after each POI batch to prevent data loss
- If a beat's `script_body` is empty or missing, flag it and skip classification (keep defaults: entities=[], sensory_anchor=false, narrative_function="establishing", beat_type="establishing", emotional_register="neutral")

---

## SELF-VERIFICATION

Before reporting completion:

1. **Every beat has all 5 AI fields** — no beat missing entities, sensory_anchor, narrative_function, beat_type, or emotional_register
2. **Every POI has poi_role** — no POI missing this field
3. **All enum values are valid** — run the validation commands above, all must pass
4. **No existing fields were modified** — script_body, beat_id, poi_name, key_claims unchanged
5. **Beat and POI counts unchanged** — same number in output as input
6. **No single enum value exceeds 70%** — distribution is reasonable, not defaulting
7. **Valid JSON** — both beats.json and poi-raw.json parse without errors
