# Scope: Duplicate Beat Prevention

**Date:** 2026-04-22
**Status:** Approved for Stage 2
**Related:** `specs/2026-04-11-pipeline-spatial-precision/` (Scope 5 validation gate surfaced the duplication problem); `specs/NORTHSTAR.md` (pipeline architecture, "no embedding similarity for MVP" boundary)

---

## Problem context

Running the unified-beat-extract skill on `chunk-15-5th-arr-val-de-grace.txt` (Scope 5 gate) produced 7 new beats for Val-de-Grace alongside 5 pre-existing legacy beats from the deprecated `pipeline_batch_v1` skill. The POI now has 12 beats with substantial semantic overlap but zero byte-identical `script_body` duplicates. Neo4j's existing MERGE on `script_body` only catches byte-identical beats — it will happily create all 12 as distinct nodes.

This will multiply across Scope 6 (21 more Paris chunks) and compound further when a second book is ingested. Duplicate prevention must ship before Scope 6.

## What we're building

1. **Refuse-on-reprocess policy.** The unified-beat-extract skill checks `book-log.json` at invocation time and refuses to run if the target book+chunk was already processed by any skill version. User must run an explicit wipe command (new: `/beat-wipe {book_slug} [--chunk {chunk_slug}]`) before re-extracting. Default is safe; the wipe is opt-in.

2. **Identity-tuple uniqueness.** `(city_name, poi_name, lens, book_slug, topic_slug)` enforced unique across `beats.json`. Validation happens at save time and as a standalone check (`scripts/validate_beats.py`) that's also called pre-upload.

3. **Script-body hash dedup.** Every beat carries a `script_body_hash` field (SHA-256 of normalized prose — lowercased, whitespace-collapsed). Duplicates within the file are rejected. Catches byte-identical re-runs even when IDs differ.

4. **Semantic dedup pass (`/beat-dedup` skill).** Post-extraction batch review:
   - **Stage A — MinHash/shingling** on `script_body` finds candidate pairs with Jaccard ≥ 0.5 (tunable).
   - **Stage B — Haiku-as-judge** classifies each candidate into: `same_story_same_wording` / `same_story_added_detail` / `same_story_enhanced_content` / `different_story`.
   - Writes a review report (`data/{city}/_dedup_review/{timestamp}.md`) with per-pair recommendations:
     - `same_story_same_wording` → recommend SKIP the new beat (keep existing)
     - `same_story_added_detail` → recommend INSERT the new beat (more specifics)
     - `same_story_enhanced_content` → recommend COMBINE (manual merge, user composes)
     - `different_story` → KEEP BOTH (no action)
   - Human approves each recommendation; skill applies.

5. **Val-de-Grace cleanup.** Run the new dedup pass on Val-de-Grace's 12 beats as the first real workload. Resolve the mixed legacy+new state. Validates the tooling.

## Why

Content-pipeline hygiene is load-bearing for (a) Scope 6 full Paris re-extraction (21 chunks × current leakage rate = meaningful pollution) and (b) multi-book ingestion where the same POI can be covered by multiple sources. Addresses a concrete gap the Scope 5 gate surfaced.

## What we're NOT building

- **Embedding-based similarity** — NORTHSTAR rule for MVP. MinHash covers the need without violating the commitment.
- **Real-time dedup during extraction** — runs post-extraction as a separate pass. Keeps extraction throughput high and keeps the unified skill focused.
- **Auto-merge without review** — every semantic match surfaces for human decision. Combinations are explicitly human-composed.
- **Changes to Neo4j MERGE or upload path** — current `script_body` MERGE stays as the final idempotency net.
- **Cross-city dedup** — scoped per city.
- **Book #2 ingestion** — this spec makes book #2 safer but doesn't add it.
- **Corpus-wide dedup sweep** — `/beat-dedup paris --all` across the 548 legacy beats is deferred to post-Scope-6 cleanup. ~17 POIs with multi-chunk overlap remain semi-validated (identity-tuple wildcards + hash-only) until that follow-up runs. Accepted risk per 04-red-team Q-1.

## What already exists

- **Neo4j MERGE on `script_body`** (final DB-level idempotency; stays)
- **`book-log.json` tracking** of processed chunks (needs the unified skill to consult it refusing-style)
- **Unified-beat-extract within-run `beat_id` uniqueness** (stays; complements identity tuple)
- **Pydantic `NarrativeBeatCreate`** in `src/api/models/nodes.py` (needs `script_body_hash` field; collection-level identity check lives outside Pydantic)
- **555 Paris beats** currently in `data/paris/beats.json` — 548 legacy + 7 new unified_v1. Val-de-Grace is the one POI with mixed versions.

## Dependencies / risks

- **New Python dep:** `datasketch` (MinHash/LSH). Lightweight, widely used, pure-Python fallback available.
- **Haiku API cost:** scales with candidate-pair count. MinHash pre-filter keeps candidate set small; negligible per-dedup-run cost in practice.
- **MinHash false negatives at conservative thresholds** — tune ≥0.5 Jaccard; accept that edge cases may slip through and rely on periodic human review.
- **Backward compat:** 548 legacy beats lack `script_body_hash`. One-time migration populates it deterministically; part of Val-de-Grace cleanup.
- **Scope 6 sequencing:** this spec must ship before Scope 6 of the pipeline-spatial-precision project. Confirmed with user.

## Complexity sizing

**Medium-to-large.** Touches Pydantic models, unified skill prompt, a new dedup skill, a validation script, a migration, and a cleanup workload. Full spec-pm workflow (Stages 2 → 3 → 4 → 5 → 6). Expect 3-5 focused scopes.

## Best-practices domains touched

- **Data integrity** (primary — this is the whole point)
- **Performance** (MinHash must handle tens of thousands of beats without blowing up)
- **UX** (the dedup review interface — human-in-the-loop clarity matters)
- **Cost** (LLM-as-judge API spend bounded by pre-filter)
- Security, privacy, auth — N/A (offline data pipeline, no user-facing surfaces)
