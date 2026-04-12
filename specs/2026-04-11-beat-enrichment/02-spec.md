# Spec: Beat & POI Metadata Enrichment

**Date:** 2026-04-11
**Type:** Contract Spec (Flavor B — infrastructure work)
**Scope:** `01-scope.md` in this folder

---

## Purpose

Classify ~548 existing Paris beats and ~119 POIs with structured metadata so the tour builder can select and sequence content through graph queries instead of re-reading raw text at runtime. This is the "expensive at ingest, cheap at runtime" architecture: a one-time classification pass that makes every future tour cheap to generate.

---

## Inputs

**Beat classification input:**
- `data/paris/beats.json` — array of beat objects, each with `script_body` (the full narrative text), `poi_name`, `lens`, `physical_cues`, `key_claims`
- Batched by POI — all beats for a single POI are sent to the classifier together so context-dependent fields (`narrative_function`) can be judged relative to siblings

**POI classification input:**
- `data/paris/poi-raw.json` — array of POI objects with `name`, `short_description`, `importance_tier`, `latitude`, `longitude`, `trigger_radius`
- Beat count and lens distribution per POI (derived from beats.json)

**Computation input:**
- `script_body` word count for `est_spoken_seconds` — no AI, pure math

---

## Outputs

### Beat enrichment output

Each beat in `beats.json` gains 6 new fields. Example for the Louvre fortress beat:

```json
{
  "beat_id": "louvre_museum_war_conflict_fortress_around_and_about_paris",
  "poi_name": "Louvre Museum",
  "lens": "war_conflict",
  "script_body": "The Louvre began not as a museum but as a military fortress...",
  "entities": ["Philippe-Auguste", "Third Crusade", "Plantagenets", "Gisors", "Tour de Nesle"],
  "sensory_anchor": false,
  "est_spoken_seconds": 52,
  "narrative_function": "establishing",
  "beat_type": "event",
  "emotional_register": "dramatic",
  "_enrichment": {
    "model": "claude-sonnet-4-6",
    "enriched_at": "2026-04-11T14:00:00Z",
    "version": "v1"
  }
}
```

**Field definitions:**

| Field | Type | Values | Rules |
|---|---|---|---|
| `entities` | list[string] | Named people, events, buildings, groups | Extract proper nouns and specific historical events. Use full proper names ("Philippe-Auguste", not "the king"). Include place names only when the beat discusses them as subjects, not when they're just the location. Min 0, no max. |
| `sensory_anchor` | boolean | true/false | `true` if the beat references something the user can currently see, hear, smell, or touch at the POI location. References to demolished/destroyed things = `false`. References to visible architectural features, plaques, views = `true`. |
| `est_spoken_seconds` | int | 1+ | `word_count(script_body) / 2.5`, rounded to nearest integer. 2.5 words/sec = 150 wpm spoken pace. |
| `narrative_function` | enum | `hook`, `deepen`, `transition`, `climax`, `callback`, `scene_setter`, `establishing` | A beat's potential role in a tour script. `hook` = strong opening candidate (surprising, provocative, or place-name origin). `establishing` = explains what this POI IS (age, builder, basic identity). `deepen` = adds depth to an already-introduced subject. `climax` = high-drama payoff. `scene_setter` = atmospheric/mood. `transition` = bridges between subjects. `callback` = references or echoes another beat's content. A beat may only have ONE function — pick the strongest. |
| `beat_type` | enum | `anecdote`, `architectural_detail`, `character_story`, `event`, `sensory_observation`, `factoid`, `establishing` | What kind of content the beat IS. `anecdote` = a specific story with characters and action. `character_story` = biographical focus on a person. `event` = something that happened at a specific time. `architectural_detail` = describes physical structure. `sensory_observation` = describes atmosphere/sound/light. `factoid` = a discrete surprising fact. `establishing` = basic identity of the POI. |
| `emotional_register` | enum | `reverent`, `somber`, `playful`, `dramatic`, `wry`, `neutral` | The dominant tone. `dramatic` = high stakes, tension. `somber` = death, loss, gravity. `reverent` = respect, awe. `playful` = light, witty. `wry` = ironic, understated. `neutral` = informational, no strong tone. |

### POI enrichment output

Each POI in `poi-raw.json` gains 1 new field:

```json
{
  "name": "Ile de la Cite",
  "poi_role": "setting",
  "_poi_role_reasoning": "Tier-5 POI but represents a 22-hectare island with no single stop point. Beats function as walking-transition narration bridging anchors on the island."
}
```

| Field | Type | Values | Rules |
|---|---|---|---|
| `poi_role` | enum | `stop`, `setting`, `walk_by_only` | `stop` = a destination where users stop and listen (default for tier 3-5 discrete buildings/monuments). `setting` = a geographic area whose beats provide contextual narration during walking, not a destination itself (large islands, boulevards, gardens used as through-routes). `walk_by_only` = never a stop; beats play while walking past (tier 1-2 minor landmarks, plaques). |

### Where outputs are stored

1. **`data/paris/beats.json`** — enrichment fields added in-place alongside existing fields. The `_enrichment` metadata block tracks model version and timestamp.
2. **`data/paris/poi-raw.json`** — `poi_role` added in-place alongside existing fields.
3. **`data/paris/export/*.json`** — regenerated by `export-validate` to include new fields in the export format.
4. **Neo4j** — new properties flow through existing upload pipeline. NarrativeBeat MERGE on `script_body` SETs the new fields. POI MERGE on `name` SETs `poi_role`.

---

## Constraints

- **No MERGE key changes.** New fields are properties, not part of any MERGE key or unique constraint. The CRUD layer's existing SET-on-MERGE pattern handles them without code changes.
- **No schema enforcement of enums.** Enum values are validated in the classification prompt, not in the database. Neo4j stores them as strings. This allows enum evolution without migration.
- **Backfill is idempotent.** Running the classification pass twice on the same beats produces the same output (deterministic prompt with temperature 0). Re-uploading enriched beats to Neo4j overwrites with identical values.
- **Batch by POI.** The classifier sees all beats for a single POI together. This produces better `narrative_function` classifications (deciding which beat is the `hook` requires seeing all candidates) and more consistent `emotional_register` (relative judgments are more accurate than absolute ones).
- **Entity format.** Entities are stored as plain strings, not normalized. "Marie-Antoinette" stays "Marie-Antoinette" even if another beat says "Marie Antoinette". Entity resolution is a follow-up scope, not this one.
- **Model cost.** ~548 beats across ~119 POIs, batched per POI. Estimated 100-120 API calls at Sonnet tier. Budget: $5-15 one-time.

---

## Acceptance criteria

- **AC-1:** Every beat in `beats.json` has all 6 enrichment fields populated with valid enum values (no nulls, no empty strings, no values outside the defined enums).
- **AC-2:** `est_spoken_seconds` for every beat equals `round(word_count(script_body) / 2.5)` — verifiable by recomputing from the text.
- **AC-3:** Every beat with `sensory_anchor: true` references something physically present at the POI location (not demolished, not moved, not hypothetical). Spot-check: sample 20 beats flagged `true` and verify each references a currently visible feature.
- **AC-4:** Every POI in `poi-raw.json` has a `poi_role` field with a valid enum value.
- **AC-5:** Enriched `beats.json` and `poi-raw.json` pass all existing pipeline regression tests (`test_export_consistency.py`, `test_gravity_distribution.py`, `test_lens_drift.py`).
- **AC-6:** Enriched data uploads to Neo4j successfully via the existing upload skill — new properties appear on NarrativeBeat and POI nodes queryable via the API.
- **AC-7:** Cross-POI entity overlap is verifiable: a Cypher query can find POIs that share entities (e.g., `MATCH (b1:NarrativeBeat), (b2:NarrativeBeat) WHERE any(e IN b1.entities WHERE e IN b2.entities) AND b1 <> b2` returns results).
- **AC-8:** `NarrativeBeatCreate` model in `src/api/models/nodes.py` accepts the 6 new fields as optional properties so future uploads include them at create time (not just via update).

---

## Concrete output example

**Before enrichment** (current state of a beat in beats.json):
```json
{
  "beat_id": "sainte_chapelle_hidden_history_survival_around_and_about_paris",
  "poi_name": "Sainte-Chapelle",
  "lens": "hidden_history",
  "script_body": "During the Revolution, the silver and gold reliquary that held the Crown of Thorns was sent to the Mint to be melted down. The Crown itself somehow survived. After the Revolution, the chapel was used first to store flour, then as a depot for court archives. By the 1840s it was so dilapidated that it was put on the market for sale and demolition. In 1847 it still bore an inscription reading 'National property, for sale.' Then on 24 May 1871, during the Paris Commune, revolutionaries poured petrol over the Sainte-Chapelle and only failed to set it on fire for lack of time.",
  "physical_cues": [],
  "key_claims": ["Crown of Thorns sent to Mint", "Chapel used to store flour", "Put on market for demolition 1840s", "Communards poured petrol 24 May 1871"]
}
```

**After enrichment:**
```json
{
  "beat_id": "sainte_chapelle_hidden_history_survival_around_and_about_paris",
  "poi_name": "Sainte-Chapelle",
  "lens": "hidden_history",
  "script_body": "During the Revolution, the silver and gold reliquary that held the Crown of Thorns was sent to the Mint to be melted down...",
  "physical_cues": [],
  "key_claims": ["Crown of Thorns sent to Mint", "Chapel used to store flour", "Put on market for demolition 1840s", "Communards poured petrol 24 May 1871"],
  "entities": ["Crown of Thorns", "Paris Commune"],
  "sensory_anchor": false,
  "est_spoken_seconds": 46,
  "narrative_function": "climax",
  "beat_type": "event",
  "emotional_register": "dramatic",
  "_enrichment": {
    "model": "claude-sonnet-4-6",
    "enriched_at": "2026-04-11T14:00:00Z",
    "version": "v1"
  }
}
```

**POI example:**
```json
{
  "name": "Ile de la Cite",
  "importance_tier": 5,
  "poi_role": "setting",
  "_poi_role_reasoning": "22-hectare island with no single stop point. Contains sub-POIs (Notre-Dame, Conciergerie, Sainte-Chapelle) that are the actual stops. Beats provide walking-transition narration."
}
```

---

## Downstream dependencies

- **Tour builder skill** — consumes enrichment fields for POI selection (`entities` → `narrative_fit` scoring), beat selection (`narrative_function`, `sensory_anchor`, `emotional_register`), and time budgeting (`est_spoken_seconds`).
- **Pipeline extraction updates** (companion scope) — uses the same field definitions and enum values established here when updating `beat-from-book` to extract enrichment at ingest time.
- **Entity resolution** (future scope) — normalizes the raw `entities` lists produced here into canonical forms for reliable cross-POI matching.

---

## Open questions

1. **Should `narrative_function` allow multi-value?** A beat could arguably be both a `hook` and an `establishing` beat. Current spec says pick one (the strongest). If Tour Builder testing reveals this is too lossy, we could switch to a ranked list. Start with single-value and see.
2. **`sensory_anchor` for partially destroyed sites.** Notre-Dame post-2019 fire: beats referencing the spire are `sensory_anchor: false` (spire was destroyed, now under reconstruction). Beats referencing the west facade are `true`. Beats referencing interior features are ambiguous (cathedral reopened Dec 2024 but interior access may be limited). Rule for now: mark based on exterior visibility. Interior beats = `false` unless the physical cue specifies an exterior-visible feature.
