# Red Team Review — Persistent Map & Manual POI Merge

**Spec:** `specs/2026-03-19-persistent-map-merge/02-spec.md`
**Date:** 2026-03-19
**Status:** Approved

---

## 1. Blockers

**B1 — No authentication on any endpoint.** ✅ RESOLVED
The spec notes (line 77): "Merge/delete use existing authenticated endpoints." This is incorrect — the codebase has zero auth. CORS is `allow_origins=["*"]`. The `DELETE /nodes/POI/{id}` endpoint is completely open.

**Resolution:** Accepted risk for MVP/Phase 1. This is an internal editorial tool used only by founders. Auth will be added before Phase 2. The spec's claim of "authenticated endpoints" is noted as inaccurate — no auth exists yet.

**B2 — No beat-transfer mechanism exists.** ✅ RESOLVED
AC6 requires transferring all `HAS_BEAT` edges from source POI to target POI. The backend uses `DETACH DELETE` for node deletion (`src/api/crud/nodes.py:177`), which destroys all connected edges including `HAS_BEAT`. If the source POI is deleted before beats are transferred, beats are destroyed.

**Resolution:** The merge is always **source (new/duplicate) → target (original/established)**. The original POI with existing relationships (`AT_POI`, etc.) is always the target and is never deleted. The implementation plan must define this sequence:

1. Fetch source POI's beats via `GET /graph/poi/{source_name}/beats`
2. For each beat, run conflict detection against target POI's beats (same-lens check)
3. Present conflict resolution UI for any collisions
4. For beats that pass (or after resolution): create new `HAS_BEAT` edge from target POI → beat node, delete old `HAS_BEAT` edge from source POI → beat node
5. After all beats transferred (or skipped), `DELETE /nodes/POI/{source_id}` — `DETACH DELETE` is now safe because no `HAS_BEAT` edges remain, and the source (duplicate) POI should have no `AT_POI` or other important relationships
6. If any step fails mid-sequence, stop and show error with current state — partial transfer is recoverable because both POIs still exist

---

## 2. Risks

**R1 — Layout restructure breaks existing functionality (Likelihood: HIGH)**
The workbench is a 3229-line single-file app. Moving from left-right flex layout to top-bottom with a persistent map is a significant CSS/DOM restructure. The per-POI map (`initMap()` at line 2008) destroys and recreates the Leaflet instance on every POI selection.

**Mitigation:** Keep the existing `initMap()` for the detail panel's coordinate editing (draggable pin). The persistent map is a separate Leaflet instance in a new DOM container (`id="persistent-map"`).

**R2 — `cachedPoiList` is currently empty (Likelihood: HIGH)**
The scope states `cachedPoiList` "already fetches all database POIs" but the code shows it is declared but never populated. `fetchLensesAndPoiList()` (line 2188) only fetches lenses.

**Mitigation:** Implementation must add paginated POI fetching to `fetchLensesAndPoiList()`. The API supports `GET /nodes/POI?limit=200&skip=0`.

**R3 — Merge operation is not atomic (Likelihood: MEDIUM)**
Client-side orchestration of beat transfer + source deletion uses multiple sequential API calls. Network interruption mid-merge could leave the system in an inconsistent state.

**Mitigation:** The sequence defined in B2 is designed so partial failure is recoverable — both POIs still exist until the final delete step. Add a confirmation dialog before starting. Log each step to console. If failure occurs mid-merge, show an error with instructions to manually verify state.

**R4 — `sort_order` property on HAS_BEAT edges (Likelihood: LOW)**
When beats transfer from source to target POI, the `sort_order` on `HAS_BEAT` edges may collide with existing beats on the target.

**Mitigation:** Append transferred beats after the target's highest `sort_order`.

---

## 3. Open Questions — RESOLVED

**Q1 — What happens to the source POI's non-beat relationships?**
**Answer:** The merge direction is always new/duplicate (source) → original/established (target). The original POI with `AT_POI` relationships from trips is always preserved as the target. The source is the duplicate that came in from a JSON upload where the automatic match didn't work. The source should have no trip relationships — it's a newly created duplicate.

**Q2 — Should the merge preview show POI-level properties or only beats?**
**Answer:** Only beats. The POIs themselves should already be the same location — the merge is about consolidating beats from a duplicate onto the original. Target POI properties remain unchanged.

**Q3 — Cancel/undo merge?**
**Answer:** Confirmation dialog before merge is sufficient for Phase 1. No undo mechanism needed.

---

## 4. Codebase Conflicts

**C1 — Map ID collision.**
Current map uses `id="map"` in the detail panel DOM. The persistent map needs its own container. Implementation must use a different ID (e.g., `id="persistent-map"`) and manage two Leaflet instances simultaneously — one persistent, one per-POI for coordinate editing.

**C2 — `addressMarker` uses `L.circleMarker` (orange).**
The spec uses amber for incoming POIs. The existing address geocoding marker is also orange/amber. The persistent map should use its own marker layer separate from the detail-panel map — no conflict since they're different Leaflet instances.

**C3 — Edge creation uses `MERGE` semantics.**
`create_edge` uses Cypher `MERGE`, which is idempotent. If a `HAS_BEAT` edge already exists between target POI and a beat (shouldn't happen, but could in error recovery), the MERGE will silently succeed rather than creating a duplicate. This is a safety benefit for the merge flow.

**C4 — `TAGGED_WITH` parent lens validation.**
The edge route validates that `TAGGED_WITH` edges only connect to non-parent lenses. During merge, existing `TAGGED_WITH` edges stay on their beat nodes — we're only moving `HAS_BEAT` edges. If conflict resolution triggers re-tagging (change-lens action), the validation will correctly enforce the constraint.

---

## 5. North Star Check

**Aligned:**
- Phase 1 gate requires "100+ Boston POIs live" — this feature directly supports confident deduplication.
- Uses existing Leaflet commitment ("Editorial Workbench: Browser-based HTML/JS. Leaflet maps").
- No new endpoints required for the base flow (uses existing CRUD).
- Merge is manual, one-pair-at-a-time — consistent with "no pipeline automation" boundary.
- Merge direction (new→original) preserves graph integrity for downstream traversals (User → Trip → ItineraryItem → POI).

**No conflicts detected.**

---

## 6. Best Practices Audit

### A) Security & Privacy Practices (`SECURITY_PRIVACY_PRACTICES.md`) — All 16 Sections

| # | Section | Verdict | Notes |
|---|---------|---------|-------|
| 1 | Data Classification & Minimization | **Pass** | No new data collected. POI metadata is not PII. |
| 2 | Consent & Transparency | **N/A** | No user-facing data collection. |
| 3 | Authentication & Authorization | **Accepted deviation** | No auth on any endpoint. Accepted for Phase 1 internal tool. Must address before Phase 2. |
| 4 | Secure Session Management | **N/A** | No sessions implemented yet. |
| 5 | Secrets & Credentials | **Pass** | No secrets introduced. |
| 6 | Encryption | **Pass** | Inherits from existing stack. |
| 7 | Logging & Monitoring | **Accepted deviation** | No logging of destructive operations. Acceptable for Phase 1 internal tool. Console logging of merge steps added as mitigation. |
| 8 | Data Retention & Deletion | **Pass** | Source POI deletion is intentional and editor-initiated. |
| 9 | Third-Party Risk | **N/A** | No new third-party dependencies. |
| 10 | Secure Development Lifecycle | **Pass** | Spec-driven workflow with red team review. |
| 11 | Input Validation & Output Encoding | **Pass** | Existing API uses Pydantic models. Searchable dropdown filters cached data client-side, no injection vector. |
| 12 | Infrastructure & Network Security | **Accepted deviation** | CORS is `allow_origins=["*"]`. Acceptable for Phase 1 internal tool. Must tighten before external exposure. |
| 13 | Privacy by Design | **N/A** | No user data involved. |
| 14 | Incident Response | **N/A** | Internal tool, no user impact. |
| 15 | Testing & Verification | **Pass** | Spec defines testable acceptance criteria (AC1–AC8). |
| 16 | Compliance & Documentation | **N/A** | No regulatory data involved. |

**Summary: 3 Accepted Deviations** — Auth (#3), Logging (#7), CORS (#12). All pre-existing, documented here with commitment to address before Phase 2.

### B) Best Practices Library — Domain-Specific

#### Data Integrity (primary concern)

| Item | Verdict | Notes |
|------|---------|-------|
| Merge direction preserves established POI | **Pass** | Source is always the duplicate; target is the original with trip relationships. |
| Beat transfer before source deletion | **Pass** | Sequence defined in B2 resolution — delete is final step only after all beats transferred. |
| `sort_order` handled on transferred beats | **Pass** | Append after target's max `sort_order`. |
| No orphaned NarrativeBeat nodes | **Pass** | Beats keep their `TAGGED_WITH` edges. Only `HAS_BEAT` is re-pointed. If source delete happens after transfer, no orphans. |
| Conflict resolution for same-lens collisions | **Pass** | EC3 explicitly covers this. Reuses existing conflict UI. |
| Partial failure is recoverable | **Pass** | Both POIs exist until final delete step. Editor can manually verify and retry. |

#### Performance

| Item | Verdict | Notes |
|------|---------|-------|
| 200+ circle markers without jank | **Pass (expected)** | `L.circleMarker` is lightweight (SVG, no icon images). 200–500 is well within Leaflet's capability. AC8 sets a testable bar. |
| Paginated POI fetch at page load | **Needs implementation** | API defaults to `limit=50`. Must paginate or set higher limit. |

#### UX

| Item | Verdict | Notes |
|------|---------|-------|
| Merge has confirmation dialog | **Pass** | Confirmed as sufficient for Phase 1. |
| Merge-with-self prevented | **Pass** | EC1 covers this. |
| Clear feedback on merge completion | **Pass** | AC7 — map updates immediately, success toast. |
| Keyboard navigation for merge flow | **Nice-to-have** | Internal tool; not a blocker for Phase 1. |

#### Accessibility

| Item | Verdict | Notes |
|------|---------|-------|
| Searchable dropdown keyboard-navigable | **Nice-to-have** | Not in AC. Acceptable for internal tool. |
| Map merge has non-visual alternative | **N/A** | Internal editorial tool, visual workflow is appropriate. |

---

## Key Implementation Constraints (for Stage 4)

1. **Merge direction is fixed:** Source (new/duplicate) → Target (original/established). Never delete the original.
2. **Beat transfer sequence:** Fetch beats → conflict detect → resolve → re-point `HAS_BEAT` edges → delete source POI. Sequential, not parallel.
3. **Two Leaflet instances:** Persistent map (`#persistent-map`) and detail-panel map (`#map`) are independent.
4. **`cachedPoiList` must be populated** at page load via paginated API calls before map markers can render.
5. **`TAGGED_WITH` edges stay on beat nodes** — only `HAS_BEAT` edges are moved during merge.
6. **Console-log each merge step** for debugging partial failures.
