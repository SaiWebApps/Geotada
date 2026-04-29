# Red Team: Workbench Triage & Progressive Upload

**Date:** 2026-03-09
**Status:** Approved
**Reviewed against:** `02-spec.md`, `specs/NORTHSTAR.md`, `Docs/Markdown Docs/SECURITY_PRIVACY_PRACTICES.md`

---

## 1. Blockers

**B1 — `localStorage` persistence deferred.** ~~Large JSON files (~100 POIs × 12 beats) could approach localStorage's 5MB limit with no degradation strategy.~~
**Resolution:** Drop localStorage session persistence from this slice. Still in active development — will add proper persistence later. Workbench operates in-memory only for now. *Remove AC8 (session resume) and Edge Case 1 (quota exceeded) from the spec for this slice.*

**B2 — `executeUpload()` is a batch function, not per-POI.**
The existing upload flow (`review.html:1876–2184`) processes all work items in a single pass. AC4 requires per-POI upload on "Mark Complete."
**Resolution:** Add a new `uploadSinglePoi()` function alongside the existing batch upload. Keep `executeUpload()` intact — bulk upload may be useful in the future. Plan must account for both paths coexisting.

**B3 — Open Question 1 (poi_audit_notes structure) unresolved — blocks Prompt V2.**
The workbench can't render POI-level audit notes (AC9) without knowing the data shape.
**Resolution:** Separate top-level `poi_audit_notes` key per POI — keeps it parallel to beat-level `audit_notes` and avoids polluting the existing POI object. This will be defined in Prompt V2. **Important:** Create Prompt V2 as a new file alongside V1 (do not overwrite V1 — keep it for rollback).

---

## 2. Risks

**R1 — Per-POI conflict detection makes redundant API calls (Medium likelihood).**
Each POI selection triggers `GET /graph/poi/{name}/beats` + `GET /nodes/POI?limit=200` (`review.html:1536, 1542`). For 100 POIs reviewed sequentially, the full POI list fetch is repeated every time.
**Mitigation:** Cache the full POI list on first fetch at workbench load. Only re-fetch per-POI beats (necessary for freshness).

**R2 — No upload atomicity (Medium likelihood).**
Uploading a POI with beats requires: POST POI → POST NarrativeBeat (×N) → POST edges (×2N). Connection drop mid-sequence leaves orphaned nodes in Neo4j.
**Mitigation:** Conflict detection on retry will catch partial uploads (existing beats show as conflicts). Acceptable for Phase 1 editorial volumes. Document as known limitation.

**R3 — Concurrent editor overlap (Low likelihood).**
If two editors open the same POI simultaneously, both see no conflicts, and the second upload creates duplicate beats. Detection runs at review-time, not upload-time.
**Mitigation:** Acceptable for Phase 1 (small editorial team). Document as known limitation. Consider optimistic locking for Phase 2.

---

## 3. Open Questions

**OQ1 — V1 JSON tag handling.**
**Resolution:** No V1 JSON files will be uploaded going forward. Kill tag support entirely — no backward compatibility needed. Strip all tag-related code (parsing at line 902, UI input at line 1263, save at line 1107).

**OQ2 — Should unresolved audit flags block "Mark Complete"?**
**Resolution:** No blockers. The editor is responsible for reviewing and deciding what is true. They can upload with unresolved flags. May add enforcement in a future slice.

**OQ3 — Lens dropdown fallback: cached vs. hardcoded?**
**Resolution:** Cache only. If we can't connect to the database, the workbench can't function anyway (uploads require DB). Fetch lenses at load time, cache in memory for the session. If the fetch fails, show an error state — don't fall back to a stale hardcoded list. *Update AC7 accordingly: remove "hardcoded fallback" language, replace with connection-required error state.*

---

## 4. Codebase Conflicts

**C1 — `resolveLensSlug()` uses hardcoded `MVP_LENSES` throughout.**
`review.html:1468–1481` defines the map. AC6 replaces it with a live-fetched list, but `resolveLensSlug()` is called during JSON parsing, conflict detection, and upload. The lens list must be available before any of these run.
**Impact:** Gate JSON loading on lens fetch completion. Fetch lenses → then allow "Load JSON."

**C2 — `renderWorklist()` has no status-based sorting.**
`review.html:1037–1070` iterates POIs in load order. Only `complete` and `pending` statuses exist — need to add `deferred`, `uploaded`, `flagged`.
**Impact:** Moderate refactor of worklist data model and sort function.

**C3 — `detectConflicts()` returns a batch result object.**
`review.html:1524–1625` returns `{ newPois, matchedPois, conflicts, reviewItems, errors }` for the entire JSON. Spec wants per-POI conflict detection at review time.
**Impact:** Wrap or decompose into a single-POI conflict check.

**C4 — Tag fields still parsed and rendered in UI.**
`review.html:902` (parse), `review.html:1107` (save), `review.html:1263` (render input). Tags aren't sent to the API, but UI still shows tag inputs.
**Impact:** Per OQ1 resolution — strip all tag code entirely.

---

## 5. North Star Check

**Aligned:**
- Progressive upload directly supports Phase 1 gate (100+ Paris POIs live) — right work, right time.
- Dynamic lens dropdown moves source of truth from frontend JS to database Lens nodes — better architecture.
- Removing tags aligns with "Lenses are the only classification system."

**Note for plan:**
- The north star's Active Build Target mentions "cosine similarity on script_body" for conflict detection. The current codebase uses Jaccard similarity (`review.html:1454–1464`). This is fine for this slice — Jaccard is already built. The plan should note that cosine similarity is the north star target and Jaccard is interim.

---

## 6. Best Practices Audit

### A) Security & Privacy Practices (16 sections)

| # | Section | Verdict | Notes |
|---|---------|---------|-------|
| 1 | Data Classification & Minimization | **Pass** | Editorial content data only. No PII. |
| 2 | Consent & Transparency | **N/A** | Internal editorial tool. |
| 3 | Authentication & Authorization | **Pass*** | No auth — acceptable for local-only dev tool. Flag auth for Phase 2 deployment. |
| 4 | Secure Session Management | **N/A** | No user sessions. |
| 5 | Secrets & Credentials | **Pass** | No secrets in frontend. API is localhost. |
| 6 | Encryption | **N/A** | Local-only traffic. |
| 7 | Logging & Monitoring | **N/A** | Internal tool. |
| 8 | Data Retention & Deletion | **Pass** | No persistent local storage (deferred). DB retention handled by Neo4j. |
| 9 | Third-Party Risk | **Pass** | No new dependencies. |
| 10 | Secure Development Lifecycle | **Pass** | Spec-driven with red team review. |
| 11 | Input Validation & Output Encoding | **Fail** | See below. |
| 12 | Infrastructure & Network Security | **N/A** | Local dev only. |
| 13 | Privacy by Design | **N/A** | No end-user data. |
| 14 | Incident Response | **N/A** | Internal tool. |
| 15 | Testing & Verification | **Pass** | Acceptance criteria defined; plan will define tests. |
| 16 | Compliance & Documentation | **N/A** | Internal tool. |

**Section 11 failures (must fix in plan):**
- **JSON schema validation:** Validate JSON structure against expected V2 schema on load. Reject files with unexpected properties or malformed structure.
- **XSS prevention:** `script_body`, `audit_notes`, and `suggested_fix` are AI-generated text rendered in the DOM. All content fields must be HTML-escaped before insertion. Verify existing rendering uses `textContent` or equivalent, not `innerHTML` with raw strings.

### B) Best Practices Library

**Security**

| Item | Verdict | Notes |
|------|---------|-------|
| JSON input validation | **Fail** | Add V2 schema validation on load. |
| XSS in DOM rendering | **Fail** | Verify/enforce HTML escaping for all rendered content fields. |
| API error handling | **Pass** | Upload failure covered (Edge Case 2). Lens fetch failure → error state. |

**Performance**

| Item | Verdict | Notes |
|------|---------|-------|
| Redundant API calls | **Fail** | Cache POI list on first fetch (per R1 mitigation). |
| Worklist re-sort | **Pass** | 100 items trivial to sort client-side. |

**UX**

| Item | Verdict | Notes |
|------|---------|-------|
| Loading states | **Pass** | Conflict detection on POI select implies loading indicator. |
| Error recovery | **Pass** | Upload retry covered. |
| Progressive disclosure | **Pass** | Uploaded POIs collapse to summary count. |
| Visual state distinction | **Pass** | Priority sorting + badges for flagged/deferred/uploaded. |

**Privacy & Accessibility:** N/A — internal editorial tool.

---

## Spec Amendments Required

Based on resolutions above, the following spec changes are needed before Stage 4:

1. **Remove AC8** (session resume from localStorage) — deferred.
2. **Remove Edge Case 1** (localStorage quota) — deferred.
3. **Update AC7** — remove "hardcoded fallback" language. If DB unreachable, show error state (workbench requires DB connection).
4. **Remove AC10 tag reference to "uploaded payloads"** — tags are being fully stripped from codebase, not just payloads.
5. **Add AC** — JSON input validated against V2 schema on load; malformed files rejected with error message.
6. **Add AC** — All content fields (script_body, audit_notes, suggested_fix) HTML-escaped before DOM rendering.
7. **Prompt V2** created as new file alongside V1 (V1 preserved for rollback). V2 adds `poi_audit_notes` as separate top-level key per POI and removes tags from output.
