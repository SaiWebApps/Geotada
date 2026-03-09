# Spec: Workbench Upload & Beat Conflict Resolution

**Date:** 2026-03-07
**Status:** Approved
**Flavor:** Behavior Spec (user-facing)

---

## Slice Goal

An **editor** can **upload all reviewed POIs and beats from the workbench to Neo4j** so that **reviewed content goes live in the graph database with conflicts detected and resolved inline**.

---

## Walkthrough

1. Editor finishes reviewing all POIs in the workbench. The "Ready for upload" banner appears with a new **"Upload to Database"** button.
2. Editor clicks "Upload to Database." A progress overlay appears showing: "Checking for conflicts… (0/N POIs scanned)."
3. For each POI, the system queries Neo4j by name. **New POIs** are queued for creation. **Matched POIs** are flagged and their existing beats are fetched.
4. For matched POIs, each incoming beat is compared against existing beats on that POI:
   - **Hard match** (same lens) → auto-conflict.
   - **Soft match** (different lens but Jaccard word-overlap similarity on `script_body` ≥ 70%) → auto-conflict.
   - **Review band** (similarity 30–69%) → flagged for editor review.
   - **Pass-through** (< 30%) → queued for creation, no conflict.
5. If conflicts exist, a **conflict resolution overlay** appears showing a side-by-side diff (existing beat left, incoming beat right). For each conflict, the editor picks one of: **Replace** (deprecate existing, create incoming), **Skip** (keep existing, discard incoming), **Merge** (field-by-field picker), or **Change Lens** (reassign incoming beat to a different lens).
6. Editor resolves all conflicts and clicks **"Confirm & Upload."** The progress overlay returns showing real-time status: "Creating POI 3/12… Creating beat 7/24… Linking relationships…"
7. Upload completes. A **summary screen** appears showing: POIs created (count), POIs matched (count), beats created (count), beats replaced (count), beats skipped (count), relationships linked (count).
8. Editor dismisses the summary. The workbench returns to its default state.

---

## Acceptance Criteria

1. **Works when** all POIs are net-new: every POI, beat, HAS_BEAT, and TAGGED_WITH relationship is created in Neo4j, and the summary shows correct creation counts with zero conflicts.
2. **Works when** a POI name matches an existing POI: the system attaches new beats under the existing POI (no duplicate POI created) and the summary distinguishes "created" vs. "matched."
3. **Works when** a hard conflict exists (same POI + same lens): the conflict overlay shows the existing and incoming beats side-by-side, and the editor can replace, skip, merge, or change lens.
4. **Works when** the editor chooses "Replace": the existing beat's `active_status` is set to `"deprecated"` and the incoming beat is created with `version` incremented by 1.
5. **Works when** the editor chooses "Merge": a field-by-field picker lets the editor choose values from either beat, and the resulting beat is saved as a new version.
6. **Works when** a soft conflict is detected (Jaccard word-overlap similarity ≥ 70% on `script_body`, different lens): it is surfaced in the conflict overlay the same way as a hard match.
7. **Works when** similarity is in the review band (30–69%): the beat is flagged for editor review with a similarity score shown, and the editor can approve (pass-through) or treat as conflict.
8. **Works when** the upload is interrupted (network error mid-batch): the progress overlay shows which items succeeded and which failed, and the editor can retry failed items without duplicating successes.

---

## Edge Cases

1. **POI name matches but coordinates differ significantly (>500m):** Show a warning asking the editor to confirm it's the same POI before attaching beats.
2. **Max beats per POI exceeded:** If a POI already has 12 beats and the upload would add more, block with a message referencing the 1-beat-per-lens cap.
3. **Lens not found in database:** If a beat's lens slug doesn't match any existing Lens node, show an error for that beat and let the editor fix it before retrying.
4. **Empty upload (0 POIs marked complete):** The upload button is disabled with a tooltip explaining why.
5. **All conflicts skipped:** Upload proceeds with only net-new content; summary reflects zero beats created from conflicted items.

---

## Open Questions

1. ~~**Cosine similarity implementation:**~~ **Resolved:** Using Jaccard word-overlap similarity, computed client-side in ~15 lines of JS. No library needed. Upgrade to cosine/embeddings tracked as a deferred improvement.
2. ~~**Retry granularity:**~~ **Resolved:** MERGE-based creation makes retry idempotent at any granularity — retrying already-created items is a no-op.
