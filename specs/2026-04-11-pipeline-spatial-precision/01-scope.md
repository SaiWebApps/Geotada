# Scope: Pipeline Extraction & Spatial Precision

**Date:** 2026-04-11
**Status:** Draft
**Related:** `specs/2026-04-11-beat-enrichment/` (companion scope — backfill & schema for metadata fields)

---

## The problem

The content pipeline has two gaps that prevent GPS-triggered tours from working well:

### Gap 1: Forward extraction doesn't produce enrichment metadata

The `beat-from-book` skill extracts `script_body`, `lens`, `physical_cues`, `key_claims`, and `source_attribution`. It does NOT extract the 6 metadata fields the tour builder needs (`entities`, `sensory_anchor`, `est_spoken_seconds`, `narrative_function`, `beat_type`, `emotional_register`). The companion scope backfills existing beats, but every future beat extracted by the pipeline will arrive without these fields unless the extraction skills are updated.

### Gap 2: Large POIs have no spatial granularity

The Louvre has 10 beats, all pinned to a single coordinate (48.8609, 2.3358) with a 10m trigger radius. The actual building spans ~700m east-to-west. A user standing at the Pyramid entrance is 400m from the Denon Wing. With the current model:

- Beats about the Louvre's medieval fortress foundations (east end) trigger at the same point as beats about the Grande Galerie (center) and the Tuileries connection (west end).
- The 10m trigger radius means a user must be within 10m of the single POI pin to trigger ANY Louvre beat — standing 50m away triggers nothing.
- Physical cues that say "look at the gargoyles" or "the tower is ahead of you" have no spatial data to tell the app WHICH direction the user should be facing or WHERE they need to be standing.

This isn't just a Louvre problem. It affects: Notre-Dame (26 beats, 10m radius), Palais Royal (12 beats, 10m radius), Luxembourg Gardens (4 beats, 100m radius), Champs-Elysees (4 beats, 30m radius), Tuileries (3 beats, 30m radius), and any future complex/campus/garden POI.

**Current physical cues state:** 61% of beats have text-based physical cues, but they're unstructured strings like "Look at the gargoyles" with no coordinates, no directional data, and no zone identifiers. The Louvre's 10 beats have ALL EMPTY physical_cues arrays — zero spatial anchoring for the largest museum in the world.

## What we're building

### Part A: Pipeline skill updates for enrichment metadata

Update `beat-from-book` (and any other extraction skills) to extract the 6 new beat metadata fields at initial extraction time, so new beats arrive enriched. This means:

- Adding extraction instructions for `entities`, `sensory_anchor`, `narrative_function`, `beat_type`, `emotional_register` to the beat extraction prompt
- Adding `est_spoken_seconds` computation (word count ÷ 2.5) as a post-extraction step
- Adding `poi_role` classification to the POI generation/matching step
- Updating export-validate to include the new fields in validation checks
- Updating the upload skill's field mapping to handle the new properties

### Part B: Spatial precision for large POIs

The simplest path to solve the large-POI problem without changing the data model:

**Approach: Sub-POIs for large sites.**

Create child POIs for distinct zones of large sites. Example for the Louvre:

| Sub-POI | Coordinates | Trigger radius | Beats assigned |
|---|---|---|---|
| Louvre - Cour Napoleon (Pyramid) | 48.8611, 2.3358 | 30m | Pyramid construction, I.M. Pei |
| Louvre - Medieval Foundations | 48.8606, 2.3381 | 20m | Philippe-Auguste fortress, moat |
| Louvre - Grande Galerie | 48.8609, 2.3365 | 20m | Gallery construction, artisan quarters |
| Louvre - Denon Wing | 48.8607, 2.3345 | 20m | Napoleon III apartments |

This uses the existing POI model — no schema changes needed. Each sub-POI is a regular POI node with its own coordinates and trigger radius. The parent Louvre POI becomes `poi_role: setting` (the umbrella), and sub-POIs are `poi_role: stop`.

**What this requires:**
- Identifying which existing POIs need sub-POI decomposition (likely 10-15 for Paris)
- Creating sub-POIs with precise coordinates for each zone
- Reassigning existing beats to the correct sub-POI based on their content
- Extracting richer physical cues from source text during re-read (the source books often describe specific locations within buildings — "in the northeast corner," "the tower facing the river" — that aren't currently captured because the extraction prompt doesn't look for sub-location precision)

### Part C: Physical cue enrichment

Upgrade physical cues from unstructured text to structured data that the GPS app can use:

**Current:** `"physical_cues": ["Look at the gargoyles"]`

**Proposed:**
```json
"physical_cues": [
  {
    "cue": "Look at the gargoyles — most are Viollet-le-Duc additions",
    "direction": "up",
    "feature_type": "architectural_detail",
    "visibility_conditions": "exterior_only"
  }
]
```

This is a stretch goal. The minimum viable version is: ensure every beat with `sensory_anchor: true` has at least one non-empty physical cue. Currently 39% of beats have empty physical_cues — some of those should have them and the extraction missed them.

## Why

Without Part A, every new beat extracted by the pipeline arrives without enrichment metadata, creating an ever-growing backfill debt.

Without Part B, the tour builder can't create tours that work at large sites. A user walking around the Louvre grounds for 30 minutes would hear nothing because they never get within 10m of the single POI pin — or they'd get all 10 beats dumped at once when they do, with no spatial sequencing.

Without Part C (minimum version), sensory-anchored beats have no physical cue to actually anchor to — the `sensory_anchor: true` flag says "this beat references something visible" but doesn't say what or where.

## What we're NOT building

- **Backfilling existing beats** with metadata — that's the companion scope (`beat-enrichment`). This scope updates the pipeline so future extraction produces enriched output.
- **Indoor positioning / floor-level mapping** — GPS doesn't work inside buildings. Indoor beats (museum galleries, church interiors) are not GPS-triggerable and need a different UX (manual playback). Don't solve this now.
- **Beat-level coordinates on every beat** — adding lat/lon to the NarrativeBeat schema is over-engineering. The sub-POI approach uses existing infrastructure. The beat's location is its parent POI's location.
- **Automated sub-POI decomposition** — the decision of how to split a large POI into zones requires judgment about where a walker would actually stand. This is a human-guided process for 10-15 POIs, not an automated pipeline step.
- **Tour builder skill** — depends on both this scope and the enrichment scope.

## What already exists

- **`beat-from-book.md`** extracts `physical_cues` as text strings — the prompt already looks for directional/spatial instructions, but misses many (Louvre: 0/10 beats have physical cues). The prompt can be tightened.
- **`pipeline-chunk.md`** orchestrates the full extraction chain — needs a new step for metadata enrichment after extraction.
- **`poi-geocode.md`** assigns POI coordinates — can be extended to handle sub-POI geocoding.
- **`export-validate.md`** validates export JSON — needs updated validation rules for new fields.
- **`upload.md`** uploads to Neo4j — the CRUD layer already handles new properties via SET, so new fields flow through without CRUD changes.
- **POI CRUD uses MERGE on name** — sub-POIs like "Louvre - Cour Napoleon" are distinct names, so they MERGE cleanly as separate nodes.

## Dependencies or risks

1. **Part A depends on the companion scope** finalizing the field definitions and enum values. The extraction prompts need to know exactly what to extract. Recommend: finalize the enrichment scope first, backfill a batch of beats, validate the field definitions work, THEN update the pipeline skills.

2. **Sub-POI identification is manual.** Someone needs to walk through the POI list and decide which ones need decomposition. The signal is: `trigger_radius` < building footprint, or beat count > 5 with content that references different physical locations within the POI.

3. **Beat reassignment.** Moving a beat from "Louvre Museum" to "Louvre - Medieval Foundations" means the `poi_name` changes, which changes the MERGE key for the HAS_BEAT relationship. Need to handle this as delete-old + create-new in the upload, not an in-place update.

4. **Source text re-reads.** Some physical cues that were missed during initial extraction exist in the source text but weren't captured. Enriching these means re-reading the relevant source passages — the `source_passage` field on each beat points back to the text. This can be done in the backfill pass (companion scope) if the prompts are extended to also extract/upgrade physical cues.

5. **Ordering.** Recommended sequence: enrichment backfill (companion scope) → pipeline skill updates (this scope Part A) → sub-POI decomposition (this scope Part B) → physical cue enrichment (this scope Part C). Each step validates the previous one.

---

*This scope is a companion to `specs/2026-04-11-beat-enrichment/`. Together they form the enrichment prerequisite for the tour builder skill.*
