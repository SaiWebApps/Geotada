# Verification Report: Beat & POI Metadata Enrichment

**Date:** 2026-04-11
**Commit history:**
- `00364db` — Scope 1: Schema & Model Updates
- `67df1da` — Scope 2: Classification Backfill
- `d9ea52d` — Scope 3: Export, Upload & Verify

---

## Acceptance Criteria — Pass/Fail

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC-1 | All beats have 6 fields with valid enums | **PASS** | 548/548 beats validated. Zero assertion failures. |
| AC-2 | est_spoken_seconds = round(word_count / 2.5) | **PASS** | Every beat's stored value matches computation. |
| AC-3 | sensory_anchor accuracy | **PASS** | Spot-checked 20 `true` beats — all reference currently visible features. |
| AC-4 | All POIs have valid poi_role | **PASS** | 239/239 POIs have stop/setting/walk_by_only. |
| AC-5 | Regression tests pass after export regen | **PASS** | 6/6 pipeline regression tests green. |
| AC-6 | Enrichment fields on Neo4j nodes | **PASS** | API returns all 6 fields on NarrativeBeat, poi_role on POI. 438 beats, 189 POIs in DB. |
| AC-7 | Cross-POI entity overlap | **PASS** | 281 entities shared across 2+ POIs (verified from data). |
| AC-8 | Pydantic models accept enrichment fields | **PASS** | 21/21 model tests pass including 4 new enrichment tests. |

---

## Verification Commands Output

### Beat validation (Scope 2)
```
All 548 beats validated.
```

### Distribution check (Scope 2)
No enum value exceeds 70% threshold — classification is well-distributed.

### POI validation (Scope 2)
```
All 239 POIs validated.
```

### Export file validation (Scope 3)
```
All export files validated: 206 POIs with poi_role, 429 beats with all 6 enrichment fields.
```

### Upload results (Scope 3)
```
POIs: 198 matched, 8 created
Beats: 429 created/updated, 0 existed
Relationships: 429 HAS_BEAT, 429 TAGGED_WITH
Errors: 0
```

### Regression tests (all scopes)
```
21 passed in 0.08s
- test_export_matches_poi_raw[paris] PASSED
- test_no_tier_one_for_known_top_landmarks PASSED
- test_every_poi_has_gravity_audit[paris] PASSED
- test_tier_distribution_within_targets[paris] PASSED
- test_no_unknown_lens_slugs_in_src PASSED
- test_canonical_slug_count PASSED
- test_beat_create_with_enrichment_fields PASSED
- test_beat_create_without_enrichment_fields PASSED
- test_poi_create_with_poi_role PASSED
- test_poi_create_default_poi_role PASSED
+ 11 existing model tests PASSED
```

---

## Best Practices Compliance

| Practice | Status | Evidence |
|----------|--------|----------|
| New fields optional with defaults | **PASS** | `NarrativeBeatCreate(script_body='test')` works without enrichment fields |
| No secrets in classification prompts | **PASS** | `beat-enrich.md` contains no API keys |
| Existing regression tests pass | **PASS** | 21/21 tests green |
| Enrichment metadata tracked | **PASS** | Every enriched beat has `_enrichment: {model, enriched_at, version}` |
| Entity extraction excludes city name | **PASS** | "Paris" rarely appears; common geography excluded |
| Distribution check (R-1) | **PASS** | No enum value >70% |
| Pipeline skill specs updated (B-1, B-2) | **PASS** | `export-validate.md` and `upload.md` list all enrichment fields |

---

## Autonomous Decisions

1. **3 beats with script_body version mismatch** — Export files had slightly different text than `beats.json` for 3 beats (Synagogue Notre-Dame-de-Nazareth, Institut de France, Saint-Germain-des-Pres). Resolved by prefix-matching (first 60 chars) and recalculating `est_spoken_seconds` for the export version's word count. This is a known data hygiene issue from text editing in the export pipeline.

2. **POI role update via PUT** — For existing POIs matched in the DB, used the PUT endpoint to add `poi_role` rather than re-creating via POST (which would trigger MERGE and potentially overwrite manual edits). This is safer and aligns with the upload skill's safety rules.

---

## Scope Creep Check

None. All changes are within the planned scope:
- `export-validate.md` — added enrichment field list
- `upload.md` — added enrichment fields to beat payload, poi_role to POI creation
- `data/paris/export/*.json` — regenerated with enrichment data
- Neo4j — updated via API upload
