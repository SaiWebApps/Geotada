# Red Team Review: POI Matching — Location-First Deduplication

**Date:** 2026-03-17
**Stage:** 3 — Red Team
**Spec:** `specs/2026-03-15-poi-matching-fix/02-spec.md`
**North Star Ref:** `specs/NORTHSTAR.md`

---

## 1. Blockers

### B1 — `cachedPoiList` is capped at 200 POIs

**Problem:** `frontend/review.html:2105` fetches `cachedPoiList` with `?limit=200`. The Phase 1 gate is 100+ Paris POIs, and this will grow. Once the cache exceeds 200, proximity matches against uncached POIs will be missed silently — the most dangerous failure mode the spec is designed to prevent.

**Resolution:** Paginate the fetch to load all POIs, or increase the limit to a safe ceiling (e.g., 2000). Since this is an internal editorial tool with a small dataset, loading all POIs is acceptable.

### B2 — Backend MERGE key (`name`) conflicts with "different place, same name" flow

**Problem:** The spec says (AC 5, AC 8) that the editor can choose "different place" and a new POI node is created even if the name matches. But `src/api/crud/nodes.py:77` uses `MERGE (n:POI {name: $name})` — if the frontend sends a POI with the same name as an existing one, MERGE will silently update the existing node instead of creating a new one.

The spec's Section 3 says "the frontend pre-resolves POI identity and passes an explicit instruction." But the current API has no mechanism to distinguish "create new" vs "attach to existing." Both paths hit the same `POST /nodes/POI` endpoint with the same MERGE behavior.

**Resolution:** Two options:
1. **Frontend renames:** When the editor chooses "different place" for a name collision, the frontend appends a disambiguator (e.g., `"Old City Hall (Beacon Hill)"`) before sending to the API. This keeps MERGE intact but requires the editor to provide a distinct name.
2. **Backend `force_create` flag:** Add an optional parameter that switches from MERGE to CREATE when the frontend explicitly requests a new node. This is cleaner but changes the API contract.

**Recommendation:** Option 1 is simpler and aligns with the spec's "frontend controls which path is taken" design. The editor already has context to provide a disambiguated name. Option 2 is more robust but deferred scope.

### B3 — No coordinate validation on the backend

**Problem:** `src/api/models/nodes.py:71-80` accepts `latitude: float` and `longitude: float` with no bounds validation. AC 7 says POIs without coordinates should be flagged as errors. The spec puts this validation in the frontend, but the backend has no defense — a malformed request (e.g., lat=999) would create a corrupt spatial point in Neo4j.

**Resolution:** Add server-side validation: `-90 ≤ latitude ≤ 90`, `-180 ≤ longitude ≤ 180`. This is a boundary validation (external input from JSON upload) and should exist regardless of frontend checks. Align with Section 11 of SECURITY_PRIVACY_PRACTICES.md.

---

## 2. Risks

### R1 — 50m threshold in dense urban areas (Medium likelihood)

**Risk:** The scope acknowledges this: in dense European old towns, distinct buildings can be <20m apart. Paris is less dense but has clusters (e.g., multiple buildings on Jardin du Luxembourg, adjacent buildings on Champs-Élysées). False proximity matches will create editor friction.

**Mitigation:** The editor-in-the-loop design handles this. Make the 50m threshold a named constant as the spec requires, so it can be tuned per-city later. Consider logging proximity match decisions to calibrate the threshold over time.

### R2 — Haversine precision at short distances (Low likelihood)

**Risk:** Haversine assumes a spherical Earth. At 50m distances the error is negligible (<0.1m), but worth noting. No action needed — just documenting.

### R3 — Race condition: concurrent editors uploading overlapping POIs (Low likelihood)

**Risk:** Two editors uploading the same area simultaneously could both get "auto-new" for the same physical location because `cachedPoiList` is loaded at session start, not refreshed per-POI.

**Mitigation:** Low risk for Phase 1 (single editor). For Phase 2+, add a cache refresh before upload execution, or add a uniqueness check on coordinates in the backend.

---

## 3. Open Questions

### Q1 — What happens when the editor picks "same place" but the names differ?

The spec says beats attach to the existing POI node. But which name wins? If the incoming POI is "The Old State House" and the existing is "Old State House," should the existing name be preserved, the incoming name be used, or should the incoming name be added to `name_variations`?

**Recommendation:** Preserve the existing name and auto-add the incoming name to `name_variations` if not already present. This builds the alt-name list organically.

### Q2 — Should the 50m threshold apply to coordinate-less existing POIs?

Some existing POIs in the database may lack coordinates (seeded manually or from earlier imports). If an existing POI has no location, it can never appear as a proximity match. Is that acceptable, or should it fall back to name matching for those POIs?

**Recommendation:** Accept it. The spec explicitly says "coordinate data must be present on incoming POIs." Existing POIs without coordinates are a data quality issue to clean up separately, not a matching logic concern.

---

## 4. Codebase Conflicts

### C1 — Alt-name matching logic will be replaced, not extended

`frontend/review.html:2271-2287` — The current `detectConflictsForPoi()` starts with alt-name matching against `cachedPoiList`. The new location-first logic replaces this entry point entirely. The alt-name matching code should be removed (not left as dead code) to avoid confusion about what drives POI identity.

**Risk:** If alt-name matching is removed but `name_variations` is still populated on POI nodes, the data sits unused until a future feature needs it. That's fine — the data layer should be permissive (per north star: "constraints at database layer, not extraction layer").

### C2 — `isNew` determination changes meaning

`frontend/review.html:2307` — Currently `isNew = existingBeats.length === 0 && !existingPoiCoords`. With location-first logic, `isNew` should mean "no existing POI within 50m" — a fundamentally different check. The variable name can stay, but the semantics change and all downstream consumers (triage display, upload plan building) must be updated.

### C3 — 500m coordinate warning becomes redundant

`frontend/review.html:2312-2318` — The current 500m coordinate mismatch warning checks distance *after* name matching. With location-first logic, distance is the primary signal. The 500m warning as currently implemented is superseded by the 50m proximity check. It should be removed to avoid confusing the editor with two different distance-based signals.

### C4 — `executeUpload` assumes name-based POI identity

`frontend/review.html:2723-2816` — The upload function calls `mapPoiForApi(poi)` which sends `name: poi.poi_name` to `POST /nodes/POI`. The backend MERGEs on name. For "same place" decisions, the frontend needs to send the *existing* POI's name (not the incoming name) to hit the right MERGE target. This is a subtle but critical mapping change.

---

## 5. North Star Check

**Alignment: Strong.** This spec directly protects the graph spine (`POI → NarrativeBeat → Lens`) which is the core architectural commitment. Specific checks:

- **Graph spine integrity:** The spec's primary purpose. POI is the anchor node — false merges/splits corrupt everything downstream. This is prerequisite work for the Phase 1 gate (100+ Paris POIs live).
- **Extraction philosophy:** "Constraints belong at the database layer, not the extraction layer." The spec respects this — the miner can still extract whatever it finds; deduplication happens at the editorial/database layer.
- **Editorial Workbench commitment:** "Browser-based HTML/JS, Leaflet maps, manual JSON upload." The spec stays within this boundary.
- **No scope creep toward boundaries:** No automated merging, no fuzzy geocoding, no batch operations — all explicitly excluded.
- **50m threshold vs 10m trigger radius:** The north star specifies a 10m geofence trigger radius for the mobile app. The 50m matching threshold is for editorial deduplication, not runtime triggering — these are independent. No conflict.

**One concern:** The spec doesn't create a new MERGE key or uniqueness constraint. Long-term, as the system scales, `name` as a MERGE key will increasingly cause problems (Blocker B2). This is acceptable for Phase 1 with the frontend-controls-identity design, but should be logged as technical debt for Phase 2.

---

## 6. Best Practices Audit

### A) Security & Privacy Practices (all 16 sections)

| # | Section | Status | Notes |
|---|---------|--------|-------|
| 1 | Data Classification & Minimization | **N/A** | No new data types collected. POI coordinates already exist in schema. |
| 2 | Consent & Transparency | **N/A** | Internal editorial tool, no end-user data collection changes. |
| 3 | Authentication & Authorization | **N/A** | No auth changes. Workbench is internal-only. |
| 4 | Secure Session Management | **N/A** | No session changes. |
| 5 | Secrets & Credentials | **N/A** | No new secrets or credentials. |
| 6 | Encryption | **N/A** | No new data channels. Existing TLS and Neo4j encryption unchanged. |
| 7 | Logging & Monitoring | **Pass** | No PII in logs. POI names and coordinates are not user PII — they're editorial content about public places. |
| 8 | Data Retention & Deletion | **N/A** | No new data retention requirements. |
| 9 | Third-Party Risk | **N/A** | No new third-party services. |
| 10 | Secure Development Lifecycle | **Pass** | Spec-driven with red team review. Code review required. |
| 11 | Input Validation & Output Encoding | **Fail** | Backend lacks coordinate bounds validation (see Blocker B3). Frontend validates but backend does not. Server-side validation required per this section. |
| 12 | Infrastructure & Network Security | **N/A** | No infra changes. |
| 13 | Privacy by Design | **N/A** | No user-facing privacy changes. |
| 14 | Incident Response | **N/A** | No incident response changes needed. |
| 15 | Testing & Verification | **Fail** | No existing tests for POI merge/dedup logic (see test gaps below). Stage 4 must define comprehensive test cases. |
| 16 | Compliance & Documentation | **N/A** | No new compliance requirements. |

**Failures to resolve before implementation:**
- **Section 11:** Add server-side coordinate validation (`-90 ≤ lat ≤ 90`, `-180 ≤ lng ≤ 180`) to `POICreate` model.
- **Section 15:** Stage 4 must include test definitions for all 8 acceptance criteria.

### B) Best Practices Library — Domain-Specific Audit

#### Data Integrity (Primary domain)

| Item | Status | Notes |
|------|--------|-------|
| MERGE key prevents false merges | **Fail** | Blocker B2 — `name` MERGE key allows silent updates when "different place" has same name. Frontend must control the path. |
| MERGE key prevents false splits | **Pass** | "Same place" decision sends existing POI name, hitting correct MERGE target. |
| Coordinate data required on incoming POIs | **Pass** | AC 7 explicitly handles missing coordinates. |
| No silent data corruption | **Fail** | Blocker B1 — `cachedPoiList` cap of 200 means proximity checks are incomplete at scale. |
| Spatial index exists for proximity queries | **Pass** | `src/schema/definitions.py:55` has POINT index on POI.location. |
| Named constant for threshold | **Pass** | Spec explicitly requires 50m as a named constant. |

#### UX (Secondary domain)

| Item | Status | Notes |
|------|--------|-------|
| One primary action per screen | **Pass** | Editor resolves one POI match at a time. |
| Sufficient context for decision | **Pass** | AC 2 requires names, coordinates, distance, map pins. |
| Clear error states | **Pass** | AC 7 handles missing coordinates as error. |
| No cognitive overload | **Pass** | Multi-match (AC 3) ranks by distance, editor resolves sequentially. |
| Loading/progress states | **N/A** | Existing upload UX handles this. |

#### Input Validation

| Item | Status | Notes |
|------|--------|-------|
| Server-side coordinate validation | **Fail** | See B3. No bounds checking on lat/lng in backend. |
| Frontend validates before send | **Pass** | `isValidLat`/`isValidLng` functions exist in `review.html`. |
| Parameterized queries | **Pass** | Neo4j queries use `$name`, `$lat`, `$lng` parameters. No injection risk. |

#### Performance

| Item | Status | Notes |
|------|--------|-------|
| Proximity check is O(n) against cached list | **Pass** | Acceptable for Phase 1 dataset size (<500 POIs). At Phase 4 scale, consider spatial index query on backend. |
| No unbounded graph traversals | **Pass** | Spec doesn't change graph query patterns. |
| Cache refresh strategy | **Fail** | `cachedPoiList` loaded once at session start. If editor uploads 50 POIs, newly created POIs aren't in the cache for subsequent proximity checks within the same session. Must refresh cache after each POI creation, or maintain a local append list. |

---

## Summary of Items Requiring Resolution

| ID | Type | Description | Status |
|----|------|-------------|--------|
| B1 | Blocker | `cachedPoiList` capped at 200 — incomplete proximity checks | **RESOLVED** — Paginated fetch in `review.html` now loads all POIs |
| B2 | Blocker | MERGE on `name` prevents creating "different place, same name" POIs | **RESOLVED** — Added `force_create` flag to `POICreate` model and `create_node()`. When true, uses CREATE instead of MERGE. Frontend sends `force_create: true` for "different place" decisions. |
| B3 | Blocker | No server-side coordinate validation | **RESOLVED** — Added `field_validator` on `POICreate` for lat (-90 to 90) and lng (-180 to 180) |
| R1 | Risk | 50m threshold may cause friction in dense areas | Accept (mitigated by editor-in-the-loop) |
| R3 | Risk | Concurrent editors can bypass proximity check | Accept for Phase 1 |
| Q1 | Question | Name handling on "same place" match with name mismatch | **RESOLVED** — Preserve existing name, auto-add incoming name to `name_variations` |
| Q2 | Question | Coordinate-less existing POIs excluded from proximity matching | **RESOLVED** — Accepted. Clean up data quality separately. |
| C4 | Conflict | `executeUpload` must send existing POI name for "same place" | Must address in plan |
| Perf | Fail | Cache not refreshed during multi-POI upload session | Must address in plan |
