# Scope: Workbench Triage & Progressive Upload

**Date:** 2026-03-09
**Status:** Approved

---

## What we're building

- **Prompt V2:** Restructure the Fact Check & Gravity Score prompt to produce clearly separated POI-level audits (coordinates, status, description) and beat-level audits (gravity, facts, script accuracy). Remove tags from prompt output.
- **Triage queue:** Replace the current sequential worklist with a prioritized queue — items with audit flags/issues surface first, clean items sink to the bottom.
- **Progressive upload:** Each POI uploads to the database when the user marks it complete, instead of batching all uploads at the end. Conflict detection runs per-POI at review time.
- **Local persistence:** Save the loaded JSON and review state to `localStorage` so the user can close the browser and resume where they left off.
- **Defer mechanism:** User can mark a POI as "come back later" — it stays in the queue but drops below unreviewed items.
- **Dynamic lens dropdown:** Replace the hardcoded `MVP_LENSES` map with a dropdown populated from the database (`Lens` nodes) at workbench load. Lens validation uses this live list instead of a static lookup.
- **Remove tags:** Strip tags from the prompt output, JSON structure, and workbench UI. Lenses are the only classification system.

## Why

Phase 1 gate requires 100+ Boston POIs live. The current batch-review-then-upload flow forces the editor to review everything before discovering conflicts or uploading anything. Progressive triage lets the team consume fact-checked data rapidly and get content into the database continuously.

## What we're NOT building

- Automated pipeline integration (prompt still runs manually in Gemini)
- Changes to the upload API or Neo4j schema
- Lens expansion (keeping current lenses; just removing hardcoded frontend list)
- Changes to the Data Miner prompt
- Batch operations (select-all, bulk approve)
- Admin UI for managing lenses (add/remove lenses directly in Neo4j)

## What already exists

- **Fact Check & Gravity Score Prompt V1** (`Docs/Prompts/Fact Check & Gravity Score Prompt V1`) — single-pass audit prompt, no POI/beat separation, includes tags
- **review.html** (`frontend/review.html`) — ~2000 lines: worklist, detail panel, audit notes renderer, conflict detection, upload flow, hardcoded `MVP_LENSES` map
- **Upload API:** `POST /nodes`, `POST /edges`, `GET /graph/poi/{name}/beats` — all functional
- **Lens nodes** already seeded in Neo4j with `name`, `slug`, `description` properties
- **Conflict detection:** `detectConflicts()`, `jaccardSimilarity()`, conflict overlay, merge overlay — all built in the previous slice

## Dependencies or risks

- **localStorage size:** Large JSON files (~100 POIs x 12 beats) could approach localStorage limits (~5MB). May need to chunk or compress.
- **Per-item conflict detection:** Each "mark complete" now makes API calls to check for existing beats. Need to handle offline/error gracefully.
- **Prompt V2 migration:** Existing fact-checked JSONs use the V1 structure (includes tags). The workbench should handle both V1 and V2 formats during the transition.
- **Lens endpoint dependency:** Workbench requires the API to be reachable at load time to populate the lens dropdown. Need a fallback if the API is down.

## Best practices flagged

- **Security:** localStorage stores content data (not credentials) — acceptable for editorial tool
- **UX:** Progressive upload changes the mental model significantly — needs clear visual feedback on what's uploaded vs pending vs deferred
- **Performance:** Per-POI DB lookups on mark-complete — should be fast for editorial volumes but needs error handling
