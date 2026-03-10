# Spec: Workbench Triage & Progressive Upload

**Date:** 2026-03-09
**Status:** Approved
**Flavor:** Behavior Spec (user-facing editorial tooling)

---

## Slice Goal

An editor can load fact-checked JSON, triage POIs by audit priority, review each POI and its beats with live conflict detection, and upload individually on completion — so that 100+ Boston POIs reach the database continuously instead of in a single batch.

---

## Walkthrough

1. Editor opens the workbench. The lens dropdown loads from the database (`GET /nodes/Lens`). If the API is unreachable, the workbench shows an error state ("Cannot connect to database — workbench requires a live connection") and blocks further actions.

2. Editor clicks "Load JSON" and selects a V2 fact-checked JSON file. The workbench validates it against the expected V2 schema and rejects malformed files with an error message. The worklist renders sorted by priority: flagged (audit issues, coordinate warnings) first, then unreviewed, then deferred. Uploaded POIs collapse into a summary count at the bottom ("8 of 24 uploaded") with an expandable section.

3. Editor selects a POI. The workbench runs conflict detection **for that POI and its beats** against the database. The detail panel loads with: POI-level audit notes (coordinates, status, description) in a distinct section, each beat card with its beat-level audit notes (gravity, facts, script accuracy), and any beat-level conflicts shown inline within the beat card (existing vs. incoming side-by-side, with replace/skip/merge/change-lens options). The editor reviews everything — audit flags, edits, and conflict resolutions — in a single pass. No tags appear anywhere.

4. Editor reviews the POI, resolves any audit flags and beat conflicts, then clicks "Mark Complete." The workbench uploads the POI and its beats immediately (with conflict resolutions applied). The POI moves to the uploaded group at the bottom.

5. Editor encounters a POI they can't resolve now. They click "Defer" — the POI drops below unreviewed items in the worklist. Its row shows a "deferred" badge.

6. Editor continues until all POIs are either uploaded or deferred.

---

## Acceptance Criteria

1. **Works when** selecting a POI triggers conflict detection for that POI and its beats — conflict/review status appears in the detail panel before the editor begins reviewing.
2. **Works when** the worklist sorts by priority: flagged/audit-issues > unreviewed > deferred > uploaded — and re-sorts dynamically as statuses change.
3. **Works when** uploaded POIs collapse into a count summary at the bottom of the worklist, expandable to see individual items, keeping the active worklist focused on pending work.
4. **Works when** "Mark Complete" uploads only that single POI and its beats (with conflict resolutions already applied), and the POI moves to the uploaded group.
5. **Works when** an uploaded POI is locked — detail panel is read-only, no re-upload button.
6. **Works when** the lens dropdown is populated from `GET /nodes/Lens` at load time, and `resolveLensSlug()` validates against this live list instead of the hardcoded `MVP_LENSES` map.
7. **Works when** the API is unreachable at load time — workbench shows an error state and blocks further actions (DB connection required).
8. **Works when** POI-level audit notes and beat-level audit notes render in visually distinct sections in the detail panel.
9. **Works when** tags are fully absent — no tag fields in the UI, no tag parsing in JSON load, no tag code in the codebase.
10. **Works when** beat-level conflicts display inline within each beat card during review — showing existing vs. incoming beat side-by-side with resolution options (replace, skip, merge, change lens) — and resolved conflicts are applied at upload time.
11. **Works when** loading a JSON file that doesn't match the expected V2 schema shows a validation error and rejects the file.
12. **Works when** all content fields (`script_body`, `audit_notes`, `suggested_fix`) are HTML-escaped before DOM rendering — no raw HTML injection possible.

---

## Edge Cases

1. **Upload fails mid-POI** — POI reverts to reviewable state with an error message. Editor can retry.
2. **Concurrent editors** — two editors load the same JSON. Conflict detection at POI-open time catches overlaps per the existing resolution flow. If editor B opens a POI after editor A has uploaded, editor B sees those as existing beats. (Known limitation for Phase 1 — no optimistic locking.)
3. **All POIs clean** — no audit flags, no conflicts. Worklist renders in load order with all items as "unreviewed." Editor reviews and uploads sequentially.
4. **Mixed audit_notes formats** — some beats have string-format notes (legacy), others have structured object notes. Both render correctly.

---

## Open Questions

*All resolved during red team (see `03-red-team.md`).*

- ~~**Prompt V2 output structure**~~ → Resolved: `poi_audit_notes` as separate top-level key per POI. Prompt V2 created as new file (V1 preserved for rollback).
