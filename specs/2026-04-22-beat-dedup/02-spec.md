# Spec: Duplicate Beat Prevention

**Date:** 2026-04-22
**Status:** Approved — sliced into 3 scopes ([03-scopes.md](03-scopes.md))
**Flavor:** B — Contract Spec (infrastructure work, no user-facing surface)

---

## Purpose

Prevent duplicate and near-duplicate `NarrativeBeat` records from accumulating in `data/{city}/beats.json` across re-extraction, skill-version changes, and multi-book ingestion. The cascade runs at three checkpoints: (A) *pre-extraction* refuse-on-reprocess, (B) *end-of-extraction* atomic validation (identity-tuple + normalized script-body hash) with staging-file rollback on fail, plus a human-reviewed MinHash semantic pass as a separate post-extraction skill, and (C) *pre-upload* hard-block validator. The existing Neo4j `MERGE` on `script_body` stays as the final idempotency net after upload.

**NORTHSTAR alignment.** The extraction prompt remains permissive per the "keep the miner permissive" rule — the LLM still extracts every candidate story. Validation runs at the commit-to-disk step (end of extraction), not inside the miner.

## Inputs

- `data/{city}/beats.json` — 555 Paris beats today (548 legacy + 7 unified_v1).
- `data/{city}/book-log.json` — per-chunk processing history.
- Source book chunks (`Books/{city}/{book_slug}/chunk-*.txt`).
- Claude Haiku API for semantic-pair judgments.

## Outputs

- **Schema change:** every beat in `beats.json` carries a `script_body_hash` (SHA-256 of `lower().strip()` with whitespace collapsed to single spaces).
- **Schema change:** every beat carries `source_chunk_slug: str` at top level — the chunk filename stem (e.g., `chunk-15-5th-arr-val-de-grace`) the beat was extracted from. New extractions populate it from the invocation arg. Legacy migration backfills via `book-log.json` POI→chunk lookup; beats whose POI appears in ≥2 chunks get the sentinel `legacy_ambiguous` (never auto-wiped; user deletes manually if needed). This is the authoritative chunk→beat mapping — without it, `/beat-wipe` cannot operate safely (see 04-red-team B-1).
- **Pydantic:** `NarrativeBeatCreate.script_body_hash` field with computed-from-body validator.
- **`scripts/validate_beats.py`** — CLI that exits 1 when identity-tuple or hash duplicates exist; invoked by `/unified-beat-extract` (end-of-run) and by `/upload` (pre-upload).
- **Updated `/unified-beat-extract`** — refuses (exit, do not process) when book+chunk already in `book-log.json`; message names prior run date. Writes new beats to a staging file, runs `validate_beats.py` on the merged result, and atomically commits (rename → `beats.json`, update `book-log.json`) only on pass. On fail: staging discarded, both files unchanged, skill exits non-zero.
- **`/beat-wipe {book_slug} --chunk {chunk_slug}`** — removes the named beats and their book-log entry; idempotent. Chunk-level only; no book-wide flag (footgun).
- **`/beat-dedup {city}`** — MinHash pre-filter → Haiku 4-way classifier → markdown review report at `data/{city}/_dedup_review/{timestamp}.md` → user-approved actions applied to `beats.json`.
- **Dedup-run audit log** appended to `data/{city}/_dedup_review/_log.jsonl` — one line per applied decision (pair IDs, classification, action, approver timestamp).
- **One-time migration** populates `script_body_hash`, `book_slug`, `topic_slug`, `city_name`, and `source_chunk_slug` on the 548 legacy beats plus the 7 unified_v1 beats. Migration branches on `_meta.prompt_version`:
  - `unified_v1` path preserves existing top-level `topic_slug`; parses `book_slug` from the `{city}_{poi_slug}_{lens}_{book_slug}_{topic_slug}` envelope.
  - Legacy path parses both `book_slug` (suffix) and `topic_slug` (middle) from `{poi_slug}_{lens}_{topic_slug}_{book_slug}`; sentinel `legacy_unknown` when unparseable.
  - `source_chunk_slug` resolved via `book-log.json` POI→chunk lookup; sentinel `legacy_ambiguous` when POI appears in ≥2 chunks.
  - Idempotent: never overwrites a non-empty non-sentinel value.

## Constraints

- **No embedding similarity** (NORTHSTAR boundary). MinHash + shingling only.
- **No auto-merge.** Every semantic match surfaces for human decision; COMBINE actions are user-composed text, not LLM-generated.
- **Identity tuple:** `(city_name, poi_name, lens, book_slug, topic_slug)` must be unique across `beats.json`.
- **Haiku judgment taxonomy** is fixed: `same_story_same_wording` / `same_story_added_detail` / `same_story_enhanced_content` / `different_story`. Call uses Messages API structured output enforcing the enum server-side. On parse fail: one retry with stricter prompt; final fallback sets `classification: different_story` + `_parse_failed: true` and surfaces the pair at the top of the report for human spot-check.
- **MinHash default:** Jaccard ≥ 0.5, 128 permutations, 5-gram shingles — all configurable via skill args. Threshold tuned empirically on the Val-de-Grace run; no upfront labeled test set.
- **Scope:** per-city. Cross-city dedup is out.
- **`NarrativeBeatCreate`** enforces hash-matches-body at validation time; collection-level identity-tuple uniqueness lives in `validate_beats.py`, not Pydantic.

## Acceptance criteria

1. **AC-1 — Refuse-on-reprocess.** Invoking `/unified-beat-extract` with a `{book, chunk}` pair already in `book-log.json` halts before any extraction work, prints the prior run date and beats-extracted count, and exits non-zero. Running on an unseen chunk proceeds normally.
2. **AC-2 — Wipe skill.** `/beat-wipe paris/around-and-about-paris --chunk chunk-15-5th-arr-val-de-grace` removes exactly the beats whose `book_slug` + `source_chunk_slug` match the target (NOT `topic_slug` — see 04-red-team B-1; `topic_slug` is per-beat, not per-chunk). Beats with `source_chunk_slug == legacy_ambiguous` are never touched by wipe. Removes the corresponding `chunks_processed` entry from `book-log.json`. Re-running on an already-wiped chunk is a no-op with a clear message and leaves both files byte-identical.
3. **AC-3 — Identity-tuple uniqueness.** `scripts/validate_beats.py data/paris/beats.json` exits 0 when all `(city_name, poi_name, lens, book_slug, topic_slug)` tuples are unique, exits 1 and prints each collision (with beat IDs) when any duplicate exists.
4. **AC-4 — Hash present and correct.** All 555 existing Paris beats carry `script_body_hash` post-migration; each hash equals SHA-256 of the normalized `script_body`; two beats with identical normalized prose share a hash.
5. **AC-5 — Hash uniqueness validation.** `validate_beats.py` exits 1 when any `script_body_hash` appears ≥ 2 times in `beats.json`.
6. **AC-6 — Dedup report structure.** `/beat-dedup paris` on Val-de-Grace's 12 beats produces a markdown report where every candidate pair (Jaccard ≥ 0.5) is assigned one of the four taxonomy labels (Haiku output — label text matches the enum but the specific label per pair is not required to be reproducible across runs), has a recommended action (`SKIP` / `INSERT` / `COMBINE` / `KEEP BOTH`), and cites both beats' IDs and lenses.
7. **AC-7 — Applied decisions logged.** Approval happens via interactive CLI only — the skill prompts per pair (`[a]ccept / [s]kip / [c]ombine / [k]eep-both / [q]uit`); markdown report is the read-only record, not an input channel. Approving a dedup recommendation mutates `beats.json` deterministically (SKIP removes the new beat; INSERT leaves both; COMBINE replaces both with user-composed merged text; KEEP BOTH flags both with `dedup_reviewed: true`) and appends a line to `_dedup_review/_log.jsonl` with pair IDs, classification, action, and timestamp. `[q]uit` writes partial progress + a resumable state file so the next invocation picks up mid-list.
8. **AC-8 — Val-de-Grace post-cleanup.** After the dedup pass, Val-de-Grace has no two beats with Jaccard ≥ 0.8 unless both carry `dedup_reviewed: true` with action `KEEP BOTH`.
9. **AC-9 — Pre-upload gate (hard-block).** `/upload` invokes `validate_beats.py` as its first step and refuses to run when it exits 1. No warn-and-continue mode; the validator is the gate, not a warning.
10. **AC-10 — Full suite green.** `pytest tests/` passes after every scope commit.
11. **AC-11 — Atomic end-of-extraction validation.** `/unified-beat-extract` writes new beats to a staging file (e.g., `data/{city}/beats.staging.json`), runs `validate_beats.py` against the staged merged result, and only on pass atomically renames staging → `beats.json` and appends the chunk entry to `book-log.json`. On fail: staging file deleted, `beats.json` and `book-log.json` unchanged, skill exits non-zero and prints the conflicting beat IDs plus conflict type (identity-tuple vs hash). A deliberate repro — planting a colliding beat mid-run — must demonstrate rollback leaves both files byte-identical to their pre-run state.
12. **AC-12 — Legacy field derivation.** The one-time migration populates `book_slug`, `topic_slug`, `city_name`, `source_chunk_slug`, and `script_body_hash` for every pre-existing beat, branching on `_meta.prompt_version`:
    - `unified_v1` (7 beats): preserve existing top-level `topic_slug`; parse `book_slug` from the `{city}_{poi_slug}_{lens}_{book_slug}_{topic_slug}` envelope. After migration all 7 carry `book_slug == "around_and_about_paris"`.
    - Legacy (548 beats): parse `book_slug` (suffix) and `topic_slug` (middle) from `{poi_slug}_{lens}_{topic_slug}_{book_slug}`; unparseable → `legacy_unknown`.
    - `source_chunk_slug`: derived from `book-log.json` POI→chunk lookup; POIs in ≥2 chunks → sentinel `legacy_ambiguous`.
    - `validate_beats.py` treats `legacy_unknown` in `book_slug` or `topic_slug` as a wildcard that does not collide with other wildcards in the same position; `script_body_hash` uniqueness still strict.
    - Migration is idempotent: never overwrites non-empty non-sentinel values; second run changes nothing. Pre-flight requires `git status` clean and writes a `beats.json.pre-migration` snapshot before mutation.

## Concrete output example

**`data/paris/_dedup_review/2026-04-22T14-30-00Z.md`:**

```markdown
# Beat Dedup Review — Paris — 2026-04-22

**Candidate pairs:** 3 (Jaccard ≥ 0.5)
**Threshold:** 0.5 | **Shingles:** 5-gram | **Permutations:** 128

---

## Pair 1 — Jaccard 0.74

- **A:** `val_de_grace_faith_spirituality_around_and_about_paris`
  (lens: `faith_spirituality`, 387 chars, `unified_v1`)
- **B:** `val_de_grace_faith_ritual_pipeline_batch_v1`
  (lens: `faith_spirituality`, 412 chars, `pipeline_batch_v1`)

**Haiku classification:** `same_story_added_detail`
**Reasoning:** Both describe the 1645 Anne of Austria vow and founding. B
adds the cornerstone-laying date (1 April 1645) and Louis XIV's age (7).

**Recommendation:** `INSERT` — B adds verifiable detail; keep both.

[ ] Approve   [ ] Change to SKIP   [ ] Change to COMBINE   [ ] Change to KEEP BOTH
```

**`_dedup_review/_log.jsonl` entry (one approval):**
```json
{"ts":"2026-04-22T14:35:11Z","pair":["val_de_grace_faith_spirituality_...","val_de_grace_faith_ritual_..."],"jaccard":0.74,"classification":"same_story_added_detail","action":"INSERT","approver":"serblowa"}
```

## Downstream dependencies

- **Scope 6 of `specs/2026-04-11-pipeline-spatial-precision/`** — full-Paris re-extraction blocks on this spec landing first.
- **`/upload`** — gains the pre-upload validator gate (AC-9).
- **Future book-#2 ingestion** — same POIs across sources rely on the `book_slug` component of the identity tuple and the semantic pass.

## Resolved decisions

1. **`/beat-wipe` granularity — chunk-level only.** No book-wide flag. Full-book wipes are doable via shell loop; the loop is visible and a typo hits one chunk, not 22.
2. **Pre-upload validator — hard-block.** Neo4j `MERGE` won't catch identity-tuple or near-duplicate cases; warn-only defeats the spec's whole purpose. Override by fixing `beats.json` and re-running, not by flag.
3. **MinHash threshold — 0.5, tune on Val-de-Grace.** 66 pairs in that POI is eyeball-reviewable in one sitting. Defer a labeled test set until beat counts make manual review stop scaling (~10K+).
