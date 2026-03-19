# Scope: POI Matching — Location-First Deduplication

**Date:** 2026-03-15
**North Star Ref:** specs/NORTHSTAR.md

---

## What we're building

- **Location-first matching logic:** POI deduplication checks lat/long proximity first (50m threshold). Only POIs within this radius are flagged as potential matches. Name similarity is a secondary signal displayed to help the editor decide — it never triggers a match on its own.
- **Auto-create when no proximity match:** If no existing POI is within 50m of an incoming POI, it is automatically treated as new. No manual step, no flag, regardless of name similarity. Two POIs with the same name but far apart are always distinct.
- **Editor review for proximity matches only:** When an incoming POI lands within 50m of an existing POI, the workbench shows both side-by-side (names, coordinates, map pins) and the editor decides: "same place" (combine beats under existing POI) or "different place" (create as new).
- **Combine or split:** When the editor confirms a match, incoming beats attach to the existing POI node. When the editor rejects, a new distinct POI node is created even if names are similar.

## Why

The POI node is the anchor point for the entire product — every beat, lens, and tour traversal hangs off it. A false merge silently corrupts downstream content. A false split fragments beats across duplicate nodes. Both break the graph spine invisibly. The current name-first matching creates false merges for distinct POIs with similar names (e.g., multiple "Old City Hall" buildings in an old city). This must be correct before scaling content, as errors compound silently.

## What we're NOT building

- Automatic coordinate-based merging (proximity matches always require editor approval)
- Fuzzy geocoding or address normalization
- Batch match resolution (matches are resolved per-POI during the existing triage flow)
- Changes to beat-level conflict detection (Jaccard similarity, hard/soft thresholds stay as-is)
- Name-only matching or flagging (distance > 50m = always distinct)

## What already exists

- **`frontend/review.html`** — `detectConflictsForPoi()` (line ~2273) does alt-name matching against `cachedPoiList`. This is the primary code that needs to change to location-first logic.
- **`src/api/crud/nodes.py`** — POI MERGE uses `name` as the merge key. Needs to account for coordinates so that two nearby POIs with different names don't create duplicates, and two far-apart POIs with the same name stay distinct.
- **`src/api/routes/graph.py`** — `/graph/poi/{poi_name}/beats` endpoint used for conflict detection. May need a coordinate-based query alternative.
- **500m coordinate warning** already exists in the frontend but is informational only, not used in match logic.
- **`cachedPoiList`** — existing POIs are already fetched with coordinates. The data is available; the logic just doesn't use it as the primary key.

## Dependencies or risks

- **Proximity threshold tuning:** 50m starting point. In very dense areas (European old towns), distinct buildings can be <20m apart. May need to be adjustable per-city in the future, but 50m is the starting default.
- **DB MERGE key change:** If we change the POI MERGE key from `name` to coordinates, existing data could be affected. Since we're pre-launch with minimal data, risk is low.
- **Geocoding accuracy:** North star specifies "auto-flag <70% confidence" for geocoding. Low-confidence coordinates could cause false negatives (miss a real proximity match) or false positives (flag unrelated POIs). The editor-in-the-loop design mitigates this.
- **Invisible failure mode:** If this logic is wrong, the damage is silent — bad POI graph structure only surfaces when someone reviews a map or runs a tour. Must have high test coverage.

## Best practices domains touched

- **UX** — new confirmation/rejection UI for proximity matches
- **Data integrity** — this is the foundation of the Global Atlas graph structure; incorrect matching corrupts everything downstream
