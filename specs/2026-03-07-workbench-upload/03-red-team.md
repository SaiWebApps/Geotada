# Red Team Review: Workbench Upload & Beat Conflict Resolution

**Date:** 2026-03-08
**Status:** Approved (all blockers resolved)
**Reviewed against:** `02-spec.md`, `specs/NORTHSTAR.md`, codebase inspection

---

## 1. Blockers — Resolved

### B1: POI.name has no unique constraint — matching is ambiguous
**Problem:** `POI.id` is unique but `POI.name` is not (`src/schema/definitions.py:38-48`). The spec assumes a 1:1 name match, but multiple POIs can share the same name. Coordinates can also differ slightly for the same real-world location.

**Resolution:** Split into a separate slice. POI deconfliction/deduplication at workbench load time will be the next slice after this one. For this slice, we proceed with exact name matching at upload time. During testing, the database can be cleared manually.

**Follow-up slice:** POI deconfliction at workbench ingest — fuzzy name matching (case, spacing, spelling), coordinate proximity check, editor disambiguation UI.

### B2: No API endpoint exists for "find beats on a POI by lens"
**Problem:** Conflict detection requires traversing `POI → HAS_BEAT → NarrativeBeat → TAGGED_WITH → Lens`. No existing endpoint supports this. Using the existing CRUD endpoints would require 3+ full-table scans per POI, joined client-side.

**Resolution:** Add one new read-only graph traversal endpoint: `GET /graph/poi/{poi_name}/beats`. See `release-notes.md` in this folder for technical details.

### B3: API uses CREATE, not MERGE — no idempotency on retry
**Problem:** `create_node()` in `src/api/crud/nodes.py:68-101` uses `CREATE`, which produces duplicates on retry. The spec requires retry safety (AC #8).

**Resolution:** Switch `create_node()` and `create_edge()` to use `MERGE` instead of `CREATE`, matching the pattern already used in `src/seed/locations.py` and `src/seed/narratives.py`. See `release-notes.md` in this folder for a detailed explanation for the backend developer.

---

## 2. Risks — Accepted

### R1: Similarity metric clarified — Jaccard, not cosine
**Original risk:** "Cosine similarity" in the spec requires vectorization (TF-IDF or embeddings), which is heavyweight for client-side JS on short texts.

**Resolution:** Use **Jaccard word-overlap similarity** instead. Split both texts into lowercase words, remove stop words, compute `|intersection| / |union|`. Same thresholds apply (≥70% auto-conflict, 30-69% review band, <30% pass-through). Runs in ~15 lines of JS, no libraries needed.

**Spec update required:** Change "cosine similarity" to "word-overlap similarity (Jaccard)" in `02-spec.md`, walkthrough step 4 and AC #6-7.

**Deferred improvement:** Upgrade to cosine similarity with embeddings if Jaccard proves too coarse for longer or semantically similar beats. Tracked in Deferred Improvements below.

### R2: Large uploads will be slow (one-request-per-node)
**Likelihood:** Medium. 100 POIs × 3 beats = ~1,000 HTTP requests ≈ 50 seconds.

**Resolution:** Accept for v1 — this is an internal editorial tool, not customer-facing. Progress overlay provides feedback during the wait.

**Deferred improvement:** Add a batch upload endpoint to reduce round trips. Tracked below.

### R3: Client-side data loss on tab close
**Resolution:** Add a `beforeunload` warning if there are unuploaded reviewed POIs. Added to scope.

---

## 3. Open Questions — Resolved

### Q1: What similarity metric?
**Answer:** Jaccard word-overlap similarity. See R1 above.

### Q2: Should we add a POI.name unique constraint?
**Answer:** Not in this slice. Exact name match at upload time is sufficient. Fuzzy matching (case/spacing/spelling normalization) is deferred to the POI deconfliction slice. For now, the editor is responsible for consistent naming during review.

### Q3: Should the `beforeunload` warning be in scope?
**Answer:** Yes. Added to scope.

---

## 4. Codebase Conflicts — Addressed

### C1: Field name mismatch between workbench and API
**Workbench** (`frontend/review.html`): `poi_name`, `lens` (display label or slug), `tags` (comma-separated)
**API** (`src/api/models/nodes.py`): `name`, `script_body`, `version`, `active_status`

**Resolution:** The upload JS code handles all field mapping. No changes to the workbench JSON format. Mappings:
- `poi_name` → `name`
- `lens` display label → slug lookup against `MVP_LENSES` in `src/schema/definitions.py:117-139`
- Default `version: 1`, `active_status: "active"` for new beats
- On "Replace": query existing beat's version and increment

### C2: Beat lens field may be display label, not slug
**Resolution:** Upload code includes a label→slug lookup against the 12 MVP lenses. Validation error if no match found (edge case #3 in spec).

### C3: version and active_status not in workbench data
**Resolution:** Upload code defaults incoming beats to `version: 1, active_status: "active"`. On conflict resolution "Replace," existing beat is set to `active_status: "deprecated"` and incoming beat gets `version: existing.version + 1`.

---

## 5. North Star Check

**Aligned.** This slice directly addresses the Active Build Target (NORTHSTAR.md line 93-100).

- Manual JSON upload matches the "pipeline automation deferred" commitment (line 63)
- 1-beat-per-lens-per-POI cap enforced at upload/database time, not extraction — matches "constraints belong at the database layer" (line 44)
- Browser-based HTML/JS stays within the Editorial Workbench commitment (line 42)
- Jaccard similarity is content deduplication, NOT embedding-based lens similarity (which is explicitly out of scope, line 64)

---

## 6. Scope Adjustments from Red Team

Added to this slice:
- `beforeunload` warning for unuploaded reviewed POIs
- New `GET /graph/poi/{poi_name}/beats` endpoint for conflict detection
- MERGE-based creation in CRUD layer for retry safety
- Field mapping layer in upload JS

Explicitly deferred (separate slices):
- POI deconfliction/deduplication at workbench load time (fuzzy name matching, coordinate proximity, editor disambiguation)

---

## 7. Deferred Improvements

Items identified during red team that should be addressed in future slices. These carry forward to `/debrief` and north star updates.

| Item | Why deferred | Priority | Trigger to revisit |
|------|-------------|----------|-------------------|
| **Batch upload endpoint** | One-request-per-node is slow but acceptable for internal tool | Medium | Upload times exceed 2 minutes or editor complaints |
| **Upgrade Jaccard → cosine similarity** | Jaccard is sufficient for near-duplicate detection on 50-200 word texts | Low | False negatives reported (semantically similar beats not caught) or script bodies grow significantly longer |
| **POI deconfliction at ingest** | Splitting into next slice to keep this one focused | High | Immediately after this slice ships |
| **Selective per-item upload** | Batch-only is simpler for v1 | Low | Editor requests ability to upload individual POIs |
| **Upload rollback / undo** | Adds significant complexity | Low | Data quality issues from bad uploads |
