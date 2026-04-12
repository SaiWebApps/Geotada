# Scope: Beat & POI Metadata Enrichment

**Date:** 2026-04-11
**Status:** Draft
**Supersedes:** `specs/2026-04-09-beat-metadata-enrichment/01-scope.md` (parked draft)
**Related:** `specs/2026-04-11-pipeline-spatial-precision/` (companion scope — extraction & physical cue upgrades)

---

## What we're building

Add 6 metadata fields to NarrativeBeat nodes and 1 field to POI nodes so the tour builder can replicate programmatically what was done by hand in Tour A ("Survival on the Island"). Without these fields, every selection and sequencing decision requires re-reading raw `script_body` text — either by a human or a frontier model at runtime.

**Beat fields (Tier 1 — tour doesn't work without):**

| Field | Type | What it unlocks |
|---|---|---|
| `entities` | list[string] | Cross-POI theme discovery. Tour A's entire theme was found by spotting shared entities (Marcel, Marie-Antoinette, Communards) across 4 POIs. Powers the `narrative_fit` term in POI selection scoring. |
| `sensory_anchor` | boolean | Distinguishes beats that require the user to be *looking at the thing* from beats that work anywhere. Misplaced sensory beats are jarring; correctly placed ones are what Detour did. |
| `est_spoken_seconds` | int | Word count ÷ 2.5, no AI needed. Without it, the 60% silence budget and dwell-time budgeting are guesswork. |

**Beat fields (Tier 2 — tour is mediocre without):**

| Field | Type | What it unlocks |
|---|---|---|
| `narrative_function` | enum: `hook, deepen, transition, climax, callback, scene_setter, establishing` | Beat's role in a script. Without it, cold opens are random, stop sequencing is flat, and POIs like Pont Neuf that lack `establishing` beats can't be detected. |
| `beat_type` | enum: `anecdote, architectural_detail, character_story, event, sensory_observation, factoid, establishing` | What kind of content. Enables within-stop sequencing (architecture → story → consequence). |
| `emotional_register` | enum: `reverent, somber, playful, dramatic, wry, neutral` | Prevents tone whiplash — three somber dark_history beats in a row at one stop. |

**POI field:**

| Field | Type | What it unlocks |
|---|---|---|
| `poi_role` | enum: `stop, setting, walk_by_only` | Tells the tour builder whether a POI is a destination, a geographic context provider, or a walking mention. Ile de la Cite is tier 5 but functioned as walking-narration spine in Tour A, not a stop. Without this, the builder tries to route users to "stop at" a 22-hectare island. |

**How it works — classification, not re-extraction:**

This is NOT a re-extraction from source books. Each beat already has the full narrative text stored in `script_body`. The backfill reads that existing text and adds structured labels. For example, the Louvre fortress beat's `script_body` ("The Louvre began not as a museum but as a military fortress. In 1190, Philippe-Auguste built it...") gets classified as:

```json
{
  "entities": ["Philippe-Auguste", "Third Crusade", "Plantagenets", "Gisors"],
  "sensory_anchor": false,
  "narrative_function": "establishing",
  "beat_type": "event",
  "emotional_register": "dramatic",
  "est_spoken_seconds": 52
}
```

5 fields are AI classification of existing text. 1 field (`est_spoken_seconds`) is pure word-count math. No source books needed.

Batching by POI (sending all of a POI's beats together) produces better results for context-dependent judgments — e.g., deciding which beat is the `hook` vs. the `deepen` is easier when the model sees all siblings.

**Three deliverables:**

1. **Backfill existing beats** — classify all ~548 Paris beats with the 6 new fields via batched AI classification pass (5 fields) + computation (est_spoken_seconds).
2. **Classify existing POIs** — assign `poi_role` to all ~119 Paris POIs.
3. **Schema property registration** — update schema definitions so the API exposes these fields via schema introspection.

## Why

The tour builder's selection algorithm (documented in `Docs/tour-builder/design.md`) needs these signals to:
- **Discover themes** across POIs (via `entities`) — validated by competitive research: Tilden principle #5, Detour's documentary approach
- **Place sensory beats precisely** (via `sensory_anchor`) — the #1 quality signal across Detour, VoiceMap, Viator reviews, and academic literature
- **Budget stop dwell time** (via `est_spoken_seconds`) — VoiceMap checks talk-time vs walk-time; the 60% silence rule needs real numbers
- **Select cold-open hooks** and sequence stops (via `narrative_function`) — heritage interpretation literature: "provocative hook first"
- **Prevent tone whiplash** (via `emotional_register`) — Springer 2022: emotional engagement as key audience driver
- **Route correctly around large/abstract POIs** (via `poi_role`) — without it, the builder can't distinguish a destination from a setting

This is the "expensive at ingest, cheap at runtime" architecture: ~$5-15 one-time extraction cost so that every future tour is built with fast graph queries, not frontier model reasoning.

## What we're NOT building

- **Pipeline extraction updates** — updating `beat-from-book` and other skills to extract these fields on new beats is a separate companion scope (`pipeline-spatial-precision`). This scope handles the backfill and schema; that scope handles forward-looking extraction.
- **Entity resolution / normalization** — "Marie-Antoinette" vs "Marie Antoinette" vs "the Queen" can be normalized in a follow-up pass after extraction. Extract first, deduplicate later.
- **Tier 3 fields** — `time_period`, `requires_setup`, `standalone_quality` are deferred. `entities` captures most of what `time_period` provides. The other two are derivable from Tier 1+2 fields.
- **Tour builder skill** — depends on this enrichment but is a separate scope.
- **Beat-level coordinates / sub-locations** — the spatial precision problem for large POIs (Louvre, Notre-Dame) is handled in the companion scope.
- **Any UI for viewing or editing beat metadata.**

## What already exists

- **548 beats** in Paris with `script_body`, `lens`, `physical_cues` (61% non-empty), `key_claims`, `source_attribution`, `fact_check` — but none of the 6 new fields.
- **~119 POIs** with `importance_tier`, coordinates, `trigger_radius`, `name_variations` — but no `poi_role`.
- **NarrativeBeat CRUD** uses MERGE on `script_body` — new properties are SET alongside existing ones. No MERGE key changes needed.
- **POI CRUD** uses MERGE on `name` — same, new properties are additive.
- **Schema definitions** at `src/schema/definitions.py` — currently declares constraints and indexes only, not property schemas. Property schemas are implicit in the CRUD models at `src/api/models/nodes.py`.

## Dependencies or risks

1. **Backfill cost.** ~548 beats × Sonnet extraction ≈ $5-15. Acceptable for one-time. Should batch by POI so the model sees all of a POI's beats together — makes `standalone_quality`-adjacent judgments (like `narrative_function`) more accurate when you see siblings.
2. **Entity normalization.** Extracting entities is straightforward; getting canonical forms is harder. Recommend: extract as-is, then run a lightweight dedup pass matching on fuzzy string similarity + co-occurrence. Defer to follow-up if the first pass is good enough.
3. **Enum evolution.** New enum values can be added later without breaking existing data — these are stored as strings in Neo4j, not enforced as closed enums in the schema. The validation happens in the extraction prompt, not the database.
4. **poi_role assignment.** Most POIs are obviously `stop`. The judgment calls are tier-5 POIs that are geographic areas (Ile de la Cite, Champs-Elysees) and tier-1/2 POIs that are walk-by-only. A human pass of ~119 POIs is fast — or an AI pass with human review of the ambiguous ones.

---

*Competitive research backing these decisions is documented in `Docs/tour-builder/design.md` § "Competitive research & quality signals (April 2026)".*
