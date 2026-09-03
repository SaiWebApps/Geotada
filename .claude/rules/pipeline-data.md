---
paths:
  - "data/**"
  - "Books/**"
  - "**/pipeline/**"
  - "**/*.cypher"
---

# Pipeline and data conventions

## Guardrails

1. Two sources minimum for an auto-correction.
2. The source passage must exist in the chunk text.
3. A new POI within 100m of an existing one gets flagged for user review.
4. Never auto-resolve: living people, superlatives, story deletions.
5. Log every auto-correction with its source URLs.

Anything queued for human sign-off (data corrections, tier changes, spec decisions) first
passes the automated review suite, an independent researcher plus a hostile judge per item, so
the human reviews verdicts with evidence rather than raw candidates.

## Data

- Scope every query to the city geofence, never globally.
- MERGE keys must be multi-city safe, which means including `city_slug`.
- Create a node only when content exists. No empty placeholders.
- `data/{city_slug}/` holds pipeline data (`poi-raw.json`, `beats.json`, `export/`), and
  `poi-raw.json` is the canonical POI source of truth per city.
- `Books/{city_slug}/{book_slug}/` holds chunked source texts plus `manifest.json`.
- No fabricated values. Every field name, ID, and property traces to a verified source.
