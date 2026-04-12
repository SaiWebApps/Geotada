# Scope: Beat Metadata Enrichment

**Date:** 2026-04-09
**Status:** Draft — parked until area-containment spec is complete
**Related:** `specs/2026-04-09-area-containment/` (do that first)

---

## What we're building

- **New properties on NarrativeBeat nodes** to support tour-builder beat selection, theme emergence, and source-traceability at generation time:

| Field | Type | Purpose |
|---|---|---|
| `narrative_function` | enum: `hook, deepen, transition, climax, callback, scene_setter, establishing` | What role can this beat play in a script? |
| `beat_type` | enum: `anecdote, architectural_detail, character_story, event, sensory_observation, factoid, establishing` | What kind of content is it? |
| `time_period` | enum: `roman, medieval, early_modern, revolutionary, 19c, 20c, contemporary` | When does it take place? |
| `entities` | list[string] | People, events, places mentioned. Powers cross-POI threading. |
| `emotional_register` | enum: `reverent, somber, playful, dramatic, wry, neutral` | Tone. Prevents whiplash between adjacent beats. |
| `requires_setup` | boolean | Does this beat assume context from another beat? |
| `standalone_quality` | int (1–5) | Can it work as the only beat at a stop? |
| `est_spoken_seconds` | int | Precomputed from word count at ~150 wpm |
| `sensory_anchor` | boolean | References something the user can see/hear/smell right now? |

- **Backfill pipeline**: a one-time batch job that enriches all 441 existing Paris beats with the new fields, using an AI extraction pass (Sonnet/Opus, batched).
- **Updates to `beat-from-book` skill** so new beats are extracted with these fields at ingest time.
- **Schema updates**: no new constraints needed (these are properties, not MERGE keys), but the `est_spoken_seconds` field should be auto-computed from `script_body` word count.

## Why

The tour builder's beat selection algorithm (documented in `Docs/tour-builder/design.md`) requires richer metadata than `script_body` + `lens_tags` + `duration_sec` to:
- **Discover themes** across POIs (via `entities` + `time_period`)
- **Select cold-open hooks** (via `narrative_function: hook`)
- **Budget stop dwell time** (via `est_spoken_seconds`)
- **Place sensory beats precisely** (via `sensory_anchor`)
- **Prevent tone whiplash** (via `emotional_register`)
- **Build cross-POI character arcs** (via shared `entities`)

The two highest-value fields are `entities` (powers graph adjacency for theme emergence) and `sensory_anchor` (the Detour-quality placement precision).

## What we're NOT building

- Area containment model — separate spec (do first)
- Tour generator skill — depends on both this spec and the area-containment spec
- Pipeline skill updates for `poi-generate` / `poi-gravity` — follow-up
- Any UI/frontend for viewing or editing beat metadata

## What already exists

- NarrativeBeat nodes with: `id`, `script_body`, `version`, `active_status`, `audio_url`, `duration_sec`, `kid_friendly`, `created_at`
- 441 active beats in Paris, each with HAS_BEAT and TAGGED_WITH relationships
- `beat-from-book` skill that extracts beats from book text — needs prompt updates to extract new fields
- MERGE-on-script_body in CRUD layer — new properties are SET alongside existing ones, no MERGE key changes needed

## Dependencies or risks

1. **Backfill cost.** 441 beats × Sonnet extraction ≈ $5–10. Acceptable for one-time.
2. **Entity normalization.** "Marie-Antoinette" vs "Marie Antoinette" vs "the Queen" — entities need canonical forms or the cross-POI threading won't work. May need a lightweight entity resolution pass.
3. **Enum evolution.** If we add new `beat_type` or `time_period` values later, existing beats with the old values still work. These enums are open-ended in the graph (stored as strings), not closed in the schema.
