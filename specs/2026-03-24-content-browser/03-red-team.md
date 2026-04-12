# Red Team — Content Browser Workbench

**Date:** 2026-03-24
**Spec:** [02-spec.md](02-spec.md)
**Status:** Approved

---

## 1. Blockers

### B1 — `poiData[]` dual-shape creates fragile index coupling — RESOLVED

**Problem:** DB POIs from `cachedPoiList` have a different shape (`properties.name`, `properties.location.lat/lng`) than JSON entries (`poi_name`, `latitude`, `beats[]`, `_status`). Mixing them in `poiData[]` would break ~40 call sites.

**Resolution:** Don't put DB POIs in `poiData[]` at all. Keep two separate data sources:
- **`cachedPoiList`** (already exists, populated on city select) — DB POIs, rendered read-only with their native API shape. Render code handles field differences (`properties.name` vs `poi_name`). Lens slugs translated to display labels for DB beat cards.
- **`poiData[]`** — incoming JSON entries only. No shape changes, no new status values. All existing functions (`updateProgress`, `checkAllComplete`, `canMarkComplete`, next/prev) work untouched.
- **Selection** changes from bare `activeIdx` integer to a compound selector like `{ source: 'db' | 'incoming', idx: number }` so click handlers know which array to read from.
- **On JSON merge:** matched DB POIs get incoming beats attached (e.g., `_incomingBeats` array on the `cachedPoiList` entry). Detail panel shows both.

### B2 — `_status` enum needs a new value for DB POIs — RESOLVED

**Resolution:** Eliminated by B1 resolution. DB POIs stay in `cachedPoiList` and never enter `poiData[]`, so the `_status` enum doesn't need changes. Progress, completion, and skip logic remain untouched.

---

## 2. Risks

### R1 — N+1 beats fetches could feel sluggish on slow connections (Likelihood: Medium)

Each POI click fires `GET /graph/poi/{name}/beats`. With 200+ DB POIs in the worklist, an editor rapidly clicking through POIs creates a burst of sequential API calls. The current `selectPoi` is `async` and doesn't cancel prior in-flight requests.

**Mitigation:** (a) Cache fetched beats on the `cachedPoiList` entry (e.g., `_dbBeats`) so repeat clicks don't re-fetch. (b) Add an AbortController pattern so clicking a new POI cancels the prior fetch. (c) The spec already calls for a loading skeleton — ensure it's visible quickly.

### R2 — JSON load matching logic must work against `cachedPoiList` (Likelihood: High)

Currently the JSON load handler (line 1258–1308) ends with `poiData = data` — a full replacement. The spec says JSON should "merge into" existing DB POIs. The merge logic needs to:
1. Match incoming JSON POIs against `cachedPoiList` entries using existing proximity + name-similarity logic
2. On match: attach incoming beats as `_incomingBeats` on the matched `cachedPoiList` entry
3. On no match: append to `poiData[]` as a new incoming entry with "New POI" badge

If matching isn't precise, the same POI could appear twice in the worklist (once as DB, once as incoming).

**Mitigation:** The implementation plan must specify the exact merge algorithm. `cachedPoiList` is the authoritative source for matching since it already has the DB POI data.

### R3 — Read-only enforcement is CSS-only, not data-protected (Likelihood: Low)

DB beats are marked "read-only" in the spec, but the current `renderDetail` renders all fields as `<input>` elements.

**Mitigation:** DB POI detail views should render fields as static `<div>` elements (not `<input>`). Since DB POIs live in `cachedPoiList` (not `poiData`), `autoSaveCurrent()` won't touch them — but the render path should still use non-editable elements for clarity.

---

## 3. Open Questions — RESOLVED

### Q1 — Auto-refresh detail panel when JSON loads beats for currently-selected DB POI?

**Answer: Yes.** If the currently-viewed DB POI gets matched with incoming beats on JSON load, the detail panel auto-refreshes to show them.

### Q2 — What action buttons show for DB-only POIs with no incoming beats?

**Answer: Upload button is blanked out (disabled).** No action available for DB-only POIs since everything is read-only.

### Q3 — Re-loading JSON: revert matched POIs to DB-only?

**Answer: Not applicable.** We assume one JSON load per session. Edge Case 5 (re-loading a second JSON file) is deferred — not a scenario we need to handle now.

---

## 4. Codebase Conflicts

### C1 — `poiData = data` replacement pattern (line 1305)

The JSON load handler hard-assigns `poiData = data`. This still works for incoming-only entries in `poiData[]`, but the handler must also run the merge step: match incoming POIs against `cachedPoiList` and attach `_incomingBeats` to matched DB entries. The duplicate-resolver flow (`showDuplicateResolver` at line 1303) also ends with a `poiData =` assignment — both paths need the merge step added after.

### C2 — `renderWorklist()` badge logic assumes only JSON-origin statuses

The badge rendering (lines 1464–1473) only handles: flagged+pending, deferred, complete, or pending. The function needs to also render `cachedPoiList` entries with "DB" badges, and distinguish "New POI" (unmatched incoming) from "Matched" (DB POI with incoming beats). Since DB POIs come from a different array, this is new render logic rather than modifying existing badge branches.

### C3 — `renderDetail()` renders all fields as editable inputs (lines 1742–1778)

POI-level fields (`poi_name`, `short_description`, `latitude`, `longitude`) are all `<input>` elements. For DB POIs (selected from `cachedPoiList`), the detail renderer needs a separate read-only path using static `<div>` elements. `autoSaveCurrent()` is not a concern since it only operates on `poiData[activeIdx]`.

### C4 — `uploadSinglePoi()` for matched DB POIs must upload only incoming beats

For matched DB POIs, the upload flow must only process `_incomingBeats` (not the existing DB beats). The existing `uploadSinglePoi` iterates `poi.beats` (line 2872) — the implementation needs to either call a variant that reads from `_incomingBeats`, or adapt the function to accept a beat source parameter.

### C5 — `addIncomingMarkers()` (line 1307) and map marker duplication

After JSON load, `addIncomingMarkers()` adds Leaflet markers for all `poiData` entries. Since DB POIs stay in `cachedPoiList` (not `poiData`), this function won't create duplicates for DB POIs. However, the persistent map already renders `cachedPoiList` markers — matched DB POIs may need a visual indicator (e.g., different color) to show they have incoming beats.

---

## 5. North Star Check

**Alignment: Good.** This spec directly serves Phase 1's gate ("100+ Boston POIs live") by giving editors visibility into what's already in the system. The "read-only existing beats" boundary correctly defers editing to a future spec, keeping scope tight.

**One concern:** The north star says "Editorial Workbench: Browser-based HTML/JS" — this is a single monolithic HTML file (~3900 lines). This spec adds significant complexity (dual data sources, merge logic, new badge types, lazy loading). The file is approaching the point where a single-file architecture creates maintenance risk. This isn't a blocker for this spec, but should be flagged for the next debrief — the north star may need an architectural commitment about when to modularize.

---

## 6. Best Practices Audit

### A) Security & Privacy Constraints (`SECURITY_PRIVACY_PRACTICES.md`)

| # | Section | Verdict | Notes |
|---|---------|---------|-------|
| 1 | Data Classification & Minimization | **Pass** | No new data collection. DB POIs are read from existing API. |
| 2 | Consent & Transparency | **N/A** | Internal editorial tool, no end-user data collection. |
| 3 | Authentication & Authorization | **Fail** | API calls to `localhost:8000` have no auth headers. The workbench is an internal tool, but `GET /nodes/POI` and `GET /graph/poi/{name}/beats` return all data without auth. Acceptable for Phase 1 local-only use, but must be documented as a known gap. |
| 4 | Secure Session Management | **N/A** | No sessions — stateless browser tool. |
| 5 | Secrets & Credentials | **Pass** | No secrets in client code. API_BASE is localhost. |
| 6 | Encryption | **N/A** | Localhost only. No TLS needed for local dev. |
| 7 | Logging & Monitoring | **N/A** | Client-side tool, no logging infrastructure. |
| 8 | Data Retention & Deletion | **N/A** | No new data stored by this spec. |
| 9 | Third-Party Risk | **Pass** | No new third-party dependencies. Leaflet already in use. |
| 10 | Secure Development Lifecycle | **Pass** | Spec-to-prompt workflow followed. |
| 11 | Input Validation & Output Encoding | **Fail** | `escHtml()` is used for POI names, but DB beat `script_body` content will be rendered in the detail panel. Must confirm that DB-sourced beat content also passes through `escHtml()` or equivalent to prevent stored XSS if the database ever contains malicious content. |
| 12 | Infrastructure & Network Security | **N/A** | Localhost development. |
| 13 | Privacy by Design | **N/A** | Internal tool, no end-user PII exposed. |
| 14 | Incident Response | **N/A** | No production deployment. |
| 15 | Testing & Verification | **Pass** | Spec defines testable acceptance criteria. Manual verification appropriate for a workbench tool. |
| 16 | Compliance & Documentation | **N/A** | Internal tool. |

### B) Best Practices Library — Domain-Specific

**Performance**

| Item | Verdict | Notes |
|------|---------|-------|
| Lazy beat loading | **Pass** | Spec explicitly calls for lazy load on click (AC2). |
| 200+ POI worklist rendering | **Pass** | Edge Case 4 addresses this. Implementation should use DOM fragment batching, not individual `appendChild` in a loop. |
| Cache fetched beats | **Fail** | Spec doesn't mention caching fetched beats. If an editor clicks POI A, then POI B, then POI A again, beats will re-fetch. Add a `_dbBeats` cache on the `cachedPoiList` entry. |
| Cancel in-flight requests | **Fail** | No mention of aborting prior beat fetches when clicking a new POI. Risk of stale data rendering if a slow response arrives after the editor has moved on. |

**UX (Editorial Workbench)**

| Item | Verdict | Notes |
|------|---------|-------|
| Visual distinction between DB/Incoming/New | **Pass** | Badges specified (AC1, AC5, AC6). |
| Sort control | **Pass** | AC7 specifies auto-sort + toggle. |
| Loading skeleton for beats | **Pass** | AC3 specifies loading indicator. |
| Error recovery for failed beat fetch | **Pass** | Edge Case 3 specifies retry. |

**Data Integrity**

| Item | Verdict | Notes |
|------|---------|-------|
| Read-only DB beats | **Pass** | Spec states read-only (AC2, AC6). |
| Upload only incoming beats | **Fail** | Not explicitly stated in spec. AC8 says "uploads all pending incoming beats" but the `uploadSinglePoi` function iterates all beats. Must explicitly filter to `_incomingBeats` only. |
| Conflict resolution preserved | **Pass** | AC8 says existing conflict resolution flow runs. |

### Summary of Fails Requiring Resolution

1. **Auth on API endpoints** (Section 3) — Document as known gap for Phase 1; no action needed now, but add to north star boundaries.
2. **XSS on DB-sourced content** (Section 11) — Ensure all DB beat fields pass through `escHtml()` when rendered.
3. **Beat fetch caching** (Performance) — Cache fetched DB beats on `cachedPoiList` entry to avoid redundant API calls.
4. **AbortController for beat fetches** (Performance) — Cancel in-flight requests when selecting a new POI.
5. **Upload filtering** (Data Integrity) — Upload flow for matched DB POIs must only process `_incomingBeats`, not existing DB beats.
