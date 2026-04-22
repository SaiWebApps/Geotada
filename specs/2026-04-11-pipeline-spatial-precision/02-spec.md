# 02-spec: Unified Extraction Pipeline

**Stage:** 2 — Contract Spec (Flavor B, infrastructure work)
**Date:** 2026-04-13
**Scope:** `01-scope.md` in this folder

---

## Purpose

Produce tour-builder-ready content by running a single unified extraction skill that emits fully-enriched beats and classified POIs in one pass, for any city, with explicit preservation of manually curated data.

## Inputs

- `city_slug` parameter (e.g., `paris`, `london`)
- Chunked source books in `Books/{city}/` (from `book-prep`)
- Existing POI master list in `data/{city}/poi-raw.json` — **preserved**
- Existing Neo4j: `Area` nodes, `WITHIN` edges, POI nodes with `importance_tier`, `lat`/`lon`, `name_variations`, `verified`, `trigger_radius`, `parent_poi` — **preserved**
- Lens definitions from `src/schema/definitions.py`

**Precondition:** POI nodes and `poi-raw.json` entries must carry a `city_name` property (matching the `Area.city_name` convention already in `src/api/models/nodes.py:127`), the POI MERGE key must be `(name, city_name)` in both the seed path (`src/seed/locations.py`) and the production write path (`src/api/crud/nodes.py`), existing POI nodes must be backfilled with `city_name`, and all read-side `MATCH (p:POI {name: ...})` queries must include a `city_name` filter. None of this holds today (239 Paris POIs have no city field; MERGE is `{name: $name}` globally; four production read-paths match POIs by name alone). Scope 2 (POI city-tagging) lands this precondition before any AC in this spec can be evaluated against multi-city Cypher.

## Outputs

- `data/{city}/beats.json` — regenerated; every beat carries: `script_body`, `entities`, `sensory_anchor`, resolved duration field, `narrative_function`, `beat_type`, `emotional_register`, `subject_tag`, structured `physical_cues`, new-format `beat_id`, `parent_poi` where applicable, standard source attribution
- `data/{city}/poi-raw.json` — updated in place; every POI has `poi_role` and `city_name`
- New sub-POI entries with `parent_poi` set, `poi_role` classified from source with a `source_passage` excerpt, and coordinates from `poi-geocode` (not LLM). Sub-POIs pass through `poi-dedup` before upload.
- Pipeline reports: long-beat flags, establishing-beat coverage, collision-check results, dedup-merge log for sub-POIs
- `data/{city}/_restore/pre-re-extract-{timestamp}/` — snapshot archive of pre-wipe state

## Constraints

- Duration field name is singular across all layers (skill output, Pydantic, Neo4j, CRUD, frontend)
- `beat_id` format: `{city}_{poi_slug}_{lens_slug}_{book_slug}_{topic_slug}`; within-run uniqueness enforced in skill self-verification
- City is a parameter — no city name hardcoded in skill logic
- Preservation boundaries: `Area` nodes, `WITHIN` edges, POI master data untouched
- Sub-POI coordinates resolved via `poi-geocode` skill, never extraction LLM
- Every `poi_role: stop` POI has `narrative_function: establishing` beat OR `establishing_not_applicable: true`
- Every beat with `sensory_anchor: true` has non-empty structured `physical_cues`
- Beats with duration > 60s flagged in pipeline report (kept whole)

## Acceptance Criteria

- **AC-1** Duration field name is singular across `src/schema/`, `src/api/crud/`, `frontend/`, and skill output. The field name is chosen at Stage 3 (see Open Question 1); verification is `grep -r "{deprecated_name}" src/ frontend/` returning zero hits, where `{deprecated_name}` is the name not chosen.
- **AC-2** Single-chunk validation run satisfies all of: (a) zero within-run `beat_id` collisions, (b) 100% of extracted beats either match an existing POI *or* emit `new_poi: true` with a pending-review entry in the pipeline report — no silent orphans, (c) for every sub-POI created, re-invoking `poi-geocode` on the sub-POI name returns coordinates within 10m of the stored `lat`/`lon` **AND** the sub-POI's coordinates differ from its parent POI's coordinates by ≥15m (if they're identical, OSM returned the parent centroid and the sub-POI is flagged, not accepted) **AND** `poi-geocode` confidence ≥70% (per NORTHSTAR), (d) zero preservation-boundary fields modified, (e) every new sub-POI has a non-empty `source_passage` quoted from the source text grounding its `poi_role` classification.
- **AC-3** Post-full-re-extraction Cypher diff: `Area` count unchanged, `WITHIN` count unchanged, and the set of pre-existing POI MERGE keys is a subset of the post-extraction POI MERGE keys (no silent delete-and-recreate). Additionally, zero POIs lost `importance_tier`, `lat`, `lon`, `name_variations`, or `verified` value.
- **AC-4** Every beat in output has all required fields populated (`entities`, `sensory_anchor`, `narrative_function`, `beat_type`, `emotional_register`, `subject_tag`, `physical_cues`, duration, new-format `beat_id`). Verified by `NarrativeBeatCreate` Pydantic model validation passing on every beat in `data/{city}/beats.json`. `subject_tag` must be a non-empty string between 1 and 32 characters (enforced 1–3 words via post-extraction regex or Pydantic validator — Stage 3 decides).
- **AC-5** Every beat where `sensory_anchor == true` has `len(physical_cues) >= 1`, each cue an object with cue text + `direction` + `feature_type`. Verified by `NarrativeBeatCreate` Pydantic model validation (structured `physical_cues` schema).
- **AC-6** Every `poi_role: stop` POI satisfies: `(has ≥1 beat with narrative_function == "establishing") OR (establishing_not_applicable == true AND importance_tier <= 2)`. The auto-flag is restricted to tier ≤ 2; higher-tier stops must have a real establishing beat. Cypher join query returns zero offenders.
- **AC-7** Restore archive exists and contains valid pre-wipe `beats.json` + Neo4j Cypher export scoped to the affected city, created before any destructive operation. Verified by **semantic round-trip**: importing the archive into a scratch Neo4j database yields a `NarrativeBeat` node count equal to the pre-wipe production beat count for that city. (Regex-counting `CREATE` statements is insufficient — APOC and `neo4j-admin` exports use varying batch shapes like `UNWIND […] CREATE`.)
- **AC-8** No city name is hardcoded in the unified skill's logic, demonstrated by running the skill against a fixture city `test_city_xx` on a 3-beat synthetic chunk; the skill must complete without error and every emitted `beat_id` must start with `test_city_xx_`. Complements (not replaces) the grep sweep `grep -iE "\b(paris|london|boston|rome|tokyo|reims|lyon|marseille|new_york)\b"` against the skill source files; any hit outside parameter defaults, ARGUMENTS placeholders, fixture paths, or comments is a failure.

- **AC-9** Every new sub-POI emitted during extraction carries (a) `parent_poi` set to an existing POI name, (b) `poi_role` ∈ {`stop`, `setting`, `walk_by_only`}, and (c) a non-empty `source_passage` field containing a verbatim or near-verbatim quotation from the source text that justifies the `poi_role`. Verified by Pydantic model validation on sub-POI entries in `poi-raw.json` plus a random-sample human spot-check (≥10% or n≥5, whichever larger) confirming the quotation is faithful to the source.

## Concrete Output Example

```json
{
  "beat_id": "paris_louvre_museum_hidden_history_around_and_about_paris_charles_v_royal_library",
  "city_name": "paris",
  "poi_name": "Louvre Museum",
  "parent_poi": null,
  "lens": "hidden_history",
  "topic_slug": "charles_v_royal_library",
  "script_body": "Charles V founded the royal library here in 1368...",
  "duration_sec": 52,
  "entities": ["Charles V", "Royal Library", "Louvre fortress"],
  "sensory_anchor": false,
  "narrative_function": "deepen",
  "beat_type": "character_story",
  "emotional_register": "neutral",
  "subject_tag": "royal library origin",
  "physical_cues": [
    {
      "cue": "The medieval foundations are exposed on the east side of the Cour Carrée",
      "direction": "east",
      "feature_type": "architectural_foundation"
    }
  ],
  "key_claims": ["Charles V founded the royal library", "Library held 917 manuscripts", "..."],
  "source_passage": "...",
  "source_attribution": {"book_title": "Around and About Paris", "author": "T. Okey", "chapter": "1st arrondissement"},
  "_meta": {"prompt_version": "unified_v1", "generated_at": "2026-04-13T...", "city_name": "paris"}
}
```

## Downstream Dependencies

- **Tour-builder skill** (future): consumes all 6 enrichment fields + `poi_role` + structured `physical_cues` to enforce design.md rules (sensory anchoring, theme discovery, silence budgeting, seasoning)
- **TTS pipeline** (future): consumes resolved duration field + `script_body`
- **Neo4j upload skill** (existing): consumes new `beats.json` via MERGE on `beat_id`

## Open Questions

1. **Duration field name.** `duration_sec` (current extraction/schema) or `est_spoken_seconds` (enrichment)? Stage 3 should pick whichever requires fewer downstream edits — grep both terms across `src/` and `frontend/` to decide.
2. **Structured `physical_cues` enum values.** `direction` (e.g., `up`, `down`, `north`, `south`, ...) and `feature_type` (e.g., `architectural_detail`, `plaque`, `view`, ...) values need enumeration. Stage 3 defines.
3. *(Resolved — promoted into AC-6.)* `establishing_not_applicable` auto-flag is restricted to `importance_tier <= 2`. Higher-tier stops must carry a real establishing beat; no escape hatch.

---

## Best Practices Check

- **Data integrity:** preservation boundaries explicit (ACs 3, 7); restore archive mandatory before destructive ops; archive validated by import round-trip, not regex count
- **Multi-city safety:** city is a parameter, AC-8 tests it with a fixture city `test_city_xx`; POI `city` property + `(name, city)` MERGE key land in Scope 2 before any multi-city Cypher is exercised
- **Schema consistency:** AC-1 enforces singular duration field name across layers
- **Source-traceability:** AC-9 extends NORTHSTAR/tour-builder source-backing rule to sub-POI `poi_role` classifications

No auth, PII, or accessibility concerns in this data-pipeline layer.

## North Star Alignment

- Sub-POI geocoding via `poi-geocode` preserves NORTHSTAR OSM commitment (6 decimals, `<70%` confidence flag)
- `beat_id` format matches NORTHSTAR Area MERGE-key precedent `(name, area_type, city_name)`
- `Area` preservation boundary is explicit; no drift
