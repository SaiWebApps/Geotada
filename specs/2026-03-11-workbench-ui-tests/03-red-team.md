# Red Team Review: Editorial Workbench UI Test Script

**Date:** 2026-03-11
**Spec ref:** `specs/2026-03-11-workbench-ui-tests/02-spec.md`
**North star ref:** Phase 1 — Content pipeline + Editorial Workbench

---

## 1. Blockers

### B1 — Conflict badges only appear after "Mark as Complete", not during browsing (RESOLVED)

Conflict detection in `review.html` fires when the user triggers "Mark as Complete" or batch upload — not when browsing POIs in the worklist. ACs #13–17 originally implied badges would be visible during detail browsing.

**Resolution applied:** ACs #13–17 rewritten to specify that "Mark as Complete" must be triggered on the conflict-target POI before asserting on conflict badges.

### B2 — Jaccard similarity uses stop-word filtering — raw word overlap percentages won't land in expected bands (RESOLVED)

The Jaccard implementation (`review.html:1878–1888`) filters common stop words before calculating similarity. Fixture entries crafted for "~75% word overlap" could land in wrong conflict bands after filtering.

**Resolution applied:** Spec now requires fixture beat text to be crafted using the same stop-word–filtered Jaccard algorithm, with expected post-filtering scores included as comments in the fixture.

### B3 — "Mark as Complete" triggers immediate upload — not a two-step flow (RESOLVED)

The workbench uses progressive single-POI upload (lines 2350–2431). "Mark as Complete" immediately uploads via API — there is no separate "upload" button for individual POIs.

**Resolution applied:** AC #8 rewritten to reflect the progressive single-POI upload behavior (POST /api/v1/nodes/POI + beat/edge creation fires on "Mark as Complete").

### B4 — Fixture entries #11–14 shared `poi_name`, triggering the batch duplicate resolver (RESOLVED)

Original entries #11–14 all used `poi_name: "UI Test Seed — Old North Church"`. Having 4 entries with the same name in the fixture would trigger the duplicate name resolver at load time — before conflict detection could even run.

**Resolution applied:** Consolidated entries #11–14 into a single POI (entry #11) with 5 beats, each targeting a different conflict band. Fixture reduced from 15 to 12 entries. AC #1 updated to reflect correct POI count (12).

---

## 2. Risks

### R1 — Fragile DOM selectors (Medium likelihood, High impact)

The workbench uses `data-field`, `data-beat-field`, and `data-beat-index` attributes — but **not `data-testid`**. These are functional attributes that could change if the workbench is refactored.

**Mitigation:** Document all selectors the test depends on in a single constants block at the top of the test file. If selectors break, only one place to update.

### R2 — Nominatim external API dependency for city geofence (Medium likelihood, Medium impact)

The city prompt triggers a Nominatim geocoding call. If Nominatim is slow or down, the test stalls at step 1.

**Mitigation:** The test should type "Boston" and verify the overlay closes. If flaky, consider whether the workbench can accept a pre-set city via URL param or localStorage.

### R3 — Upload teardown must cascade-delete (Low likelihood, Medium impact)

AC #8 uploads a POI to Neo4j. Teardown must delete the POI node **and** its `HAS_BEAT` edges, `NarrativeBeat` nodes, and `TAGGED_WITH` edges.

**Mitigation:** Teardown should use `DETACH DELETE` via Cypher (or the API) to cascade-delete all nodes/relationships matching the test prefix.

### R4 — Lens data must exist in Neo4j (Low likelihood, High impact)

The workbench populates lens dropdowns from database lens nodes. If the 12 lenses aren't seeded in the dev instance, beat editing ACs (#9, #11) and conflict detection will fail.

**Mitigation:** Test setup verifies lenses exist and seeds them if missing.

---

## 3. Open Questions (all resolved)

1. **Upload teardown** — **Resolved:** Teardown deletes all test data including uploaded POI. DETACH DELETE cascades removal. Idempotency requires full cleanup.
2. **Batch upload testing** — **Resolved:** Not in scope. Batch upload is not part of the current workflow. Only progressive single-POI upload is tested.
3. **Lens seeding** — **Resolved:** Lenses should already exist. Test setup seeds them if missing.

---

## 4. Codebase Conflicts

### C1 — POI count in AC #1 was incorrect (FIXED)

Original spec said "13 unique after duplicate resolution" with 15 entries. After consolidating entries #11–14 into one POI: 12 entries, one duplicate pair (#6/#7 both remain after rename), worklist shows 12 POIs.

**Fix applied:** AC #1 updated to "12 POIs."

### C2 — Merge overlay only offers 3 fields for selection

`review.html:2267` — Merge resolution only allows merging `script_body`, `gravity`, and `lens`. Does NOT offer `physical_cue` or `source_passage`.

**Fix applied:** AC #18 updated to specify "field-by-field selection of script_body, gravity, and lens only."

### C3 — Audit notes have two distinct rendering paths

POI-level audit notes use `.poi-audit-notes-box` and expect an **array** format (`poi_audit_notes`). Beat-level audit notes use `.audit-notes-box` and expect an **object** format. The fixture must match both shapes exactly.

**Status:** Already correctly specified in the fixture table (entry #12) and edge case #4.

### C4 — Conflict cache invalidation doesn't cover POI name changes

`invalidateConflictCache()` is called when beat content changes (line 1655) but NOT when POI name changes. If the test renames a POI to match the seeded POI name, conflict detection won't re-run until "Mark as Complete" is triggered.

**Status:** Not a spec issue — the test doesn't rename POIs to trigger conflicts. But worth noting as a potential workbench bug for the bug report.

---

## 5. North Star Check

**Alignment: Good.**

- This spec directly supports Phase 1 gate: the workbench must reliably process content before editorial workflows begin.
- The north star says "Editorial Workbench: Browser-based HTML/JS. Manual JSON upload (pipeline automation deferred)." This test exercises exactly the manual JSON upload workflow.
- No architectural changes or new dependencies introduced.
- No short-sighted decisions detected.

---

## 6. Best Practices Audit

### A) Security & Privacy Practices (`SECURITY_PRIVACY_PRACTICES.md`)

| # | Section | Verdict | Notes |
|---|---------|---------|-------|
| 1 | Data Classification & Minimization | **N/A** | Test script, not a feature collecting user data |
| 2 | Consent & Transparency | **N/A** | No user-facing data collection |
| 3 | Authentication & Authorization | **N/A** | Workbench is internal tool, no auth in current phase |
| 4 | Secure Session Management | **N/A** | No sessions in workbench |
| 5 | Secrets & Credentials | **Pass** | No secrets introduced; API runs on localhost |
| 6 | Encryption | **N/A** | Localhost testing only |
| 7 | Logging & Monitoring | **N/A** | Test outputs a markdown report, no production logging |
| 8 | Data Retention & Deletion | **Pass** | Teardown cleans up all test data (idempotent constraint) |
| 9 | Third-Party Risk | **Pass** | Playwright is well-vetted; no new third-party SDKs |
| 10 | Secure Development Lifecycle | **Pass** | This IS the testing/verification step the SDL requires |
| 11 | Input Validation & Output Encoding | **Pass** | AC #5 now verifies invalid coords are blocked from upload via client-side validation gate. AC #12a verifies explicit error codes on API errors. |
| 12 | Infrastructure & Network Security | **N/A** | Local dev stack |
| 13 | Privacy by Design | **N/A** | Test tooling only |
| 14 | Incident Response | **N/A** | Not applicable to test scripts |
| 15 | Testing & Verification | **Pass** | This spec IS the testing & verification effort |
| 16 | Compliance & Documentation | **N/A** | Internal tooling |

### B) Best Practices Library Audit

**Security:**

| Item | Verdict | Notes |
|------|---------|-------|
| Test data isolation | **Pass** | Unique `"UI Test Seed —"` prefix prevents collision with real data |
| No secrets in test code | **Pass** | No API keys or credentials needed (localhost) |
| Test doesn't modify workbench source | **Pass** | Explicitly stated in constraints |
| Invalid data blocked before upload | **Pass** | AC #5 updated — invalid coords blocked from "Mark as Complete" |

**Performance:**

| Item | Verdict | Notes |
|------|---------|-------|
| Fixture size reasonable | **Pass** | 12 entries is small; won't stress the UI |
| Test identifies rendering bottlenecks | **Pass** | AC #1 includes a 5-second timeout for worklist rendering |
| `slow_mo=300` appropriate | **Pass** | Balances visibility with runtime |

**UX (primary domain):**

| Item | Verdict | Notes |
|------|---------|-------|
| Tests cover complete user workflow | **Pass** | City → load → resolve → edit → complete → upload |
| Edge case coverage | **Pass** | Invalid coords, empty beats, long text, duplicates, boundary gravity |
| Error state coverage | **Pass** | AC #12a added — explicit error codes with human-readable messages on API errors |
| Conflict resolution completeness | **Pass** | All four resolution actions covered (AC #18), scoped to the 3 mergeable fields |
| Audit notes rendering | **Pass** | Both POI-level (array) and beat-level (object) formats covered |

**Accessibility:**

| Item | Verdict | Notes |
|------|---------|-------|
| Screen reader testing | **N/A** | Internal tool, accessibility deferred per scope |
| Keyboard navigation | **N/A** | Not in scope for this test pass |
