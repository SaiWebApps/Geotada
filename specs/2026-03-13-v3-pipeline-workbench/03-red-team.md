# Red Team Review: V3 Pipeline Support in Workbench

**Date:** 2026-03-15
**Spec reviewed:** `02-spec.md`
**North Star:** `specs/NORTHSTAR.md`
**Security ref:** `Docs/Markdown Docs/SECURITY_PRIVACY_PRACTICES.md`

---

## 1. Blockers

### B1 — `detectConflicts()` (bulk) makes per-POI API calls, not cache-based — RESOLVED

The bulk `detectConflicts()` at `review.html:1978` fetches beats per-POI via API (`/graph/poi/{name}/beats`) and then re-fetches the full POI list from the API on every match (`review.html:1984`). It does **not** use `cachedPoiList` for name matching. AC4 and AC5 assume alt-name matching works the same way in both bulk and per-POI flows, but the bulk flow's architecture is fundamentally different — it calls the API by exact canonical name only.

**Impact:** If an incoming POI has a name that matches an alt name of an existing POI, the bulk flow will call `/graph/poi/{incoming_name}/beats`, get zero results (because the API doesn't know about alt names), and classify it as "new" — silently creating a duplicate.

**Resolution (approved):** The bulk flow must check `cachedPoiList` name + `name_variations` **before** making the API call. If an alt-name match is found, use the matched POI's canonical name for the API call. This is an architecture change to the bulk flow, not just adding a filter.

### B2 — `processJson()` doesn't normalize `alternative_names` to `name_variations` — RESOLVED

AC7 says normalization happens in `processJson()`, but the current function (`review.html:1023-1064`) just spreads properties, strips empty beats, and checks for duplicates. There's no field renaming logic.

**Resolution (approved):** Add normalization early in `processJson()`: if `entry.alternative_names` exists and `entry.name_variations` does not, copy and delete. Validate it's an array of strings. This must happen before the duplicate check.

---

## 2. Risks

### R1 — Cached POI list limit of 200 (Medium likelihood)

`cachedPoiList` is fetched with `?limit=200` (`review.html:1920`). Alt-name matching only works against cached POIs. If the database has >200 POIs, newer ones won't be in the cache, and alt-name matching will miss them. Phase 1 target is 100+ POIs — safe now, but degrades silently at scale.

**Mitigation:** Document as known limitation. Raise limit to 500 or add pagination before Phase 2.

### R2 — Multi-match alt-name scenario (Low likelihood)

Edge case 3 says "flag as error" when an incoming name matches `name_variations` on multiple existing POIs. The spec doesn't define the UX for this.

**Mitigation:** Add entry to `result.errors` with a descriptive message and `continue` (skip that POI). Consistent with existing error handling pattern in `detectConflicts()`.

### R3 — `renderAuditNotes()` array detection gotcha (Medium likelihood)

The current function (`review.html:1108-1145`) checks `typeof notes === 'object'` which is true for both objects AND arrays in JavaScript. An array would enter the object branch, and `fields.some(f => notes[f.key])` would fail — silently swallowing V3 audit notes.

**Mitigation:** Implementation must add `Array.isArray(notes)` check **before** the `typeof === 'object'` check. Flag in implementation plan as a known JS gotcha.

---

## 3. Open Questions — RESOLVED

### Q1 — Case sensitivity for alt-name matching

**Decision:** Case-insensitive matching. Comparison should normalize both sides (e.g., `.toLowerCase()`) before comparing.

### Q2 — Missing `name_variations` property on existing POIs

**Decision:** Default to `[]` when the property is absent from cached POIs. No migration needed. As POIs are re-processed through V3 prompts, they'll naturally pick up `name_variations`. Code should use `(p.properties.name_variations || [])`.

### Q3 — Within-file alt-name duplicate checking

**Decision:** Yes, but scoped to the actual concern: catch entries in the uploaded file that refer to the **same physical location under different names**. Specifically: if POI A's `poi_name` appears in POI B's `name_variations` (or vice versa), flag it as a likely duplicate. Two POIs with the same name at different coordinates are fine (different locations). The concern is preventing two entries for the same place with different names from both being uploaded.

---

## 4. Codebase Conflicts

### C1 — `create_node()` SET loop handles list types correctly

The Cypher SET loop at `crud/nodes.py:89-91` does `f"n.{key} = ${key}"` for all non-excluded keys. The f-string interpolates the **key name** (from Pydantic model field names — hardcoded, not user input), while `$` parameterization handles the **value**. Neo4j driver correctly maps Python lists to Neo4j list properties via parameterization. **No conflict.**

### C2 — `POICreate` Pydantic model strict typing

Adding `name_variations: list[str] = []` is straightforward. Pydantic will reject non-string items (e.g., `[123, "name"]` or `[null, "name"]`) with a 422 error. This is correct — fail loud. The workbench should catch and surface this gracefully rather than showing a raw API error.

### C3 — `validateV2Schema()` allowlist needs V3 keys

The validation function (`review.html:991-994`) uses an explicit `allowedPoiKeys` Set. V3 keys (`address`, `alternative_names`, `name_variations`, `_meta`, `gravity_audit`, `gravity`) must be added. Note: `gravity` at the POI level is output by V3 prompts but currently only validated at the beat level. Add to allowlist without additional POI-level validation (the fact-checker handles this upstream).

---

## 5. North Star Check

**Alignment is strong.** This work directly supports the Phase 1 gate (100+ Paris POIs) and addresses a real problem (duplicate POIs from multiple source texts).

- **Editorial Workbench commitment** (browser-based HTML/JS, manual JSON upload) — stays within boundary. No new endpoints, no pipeline automation.
- **Extraction philosophy** ("constraints at the database layer, not extraction") — `name_variations` matching at the workbench layer is consistent; it's a UI/matching concern, not an extraction constraint.
- **Content pipeline prompts** — North star lists "Data Miner V1" and "Fact Check V1" as finalized. Scope correctly defers prompt updates (V3 naming alignment) as a separate task. No conflict.
- **Active Build Target** — North star says "Spec and Claude Code prompt for this slice have not yet been written." Should be updated after Stage 4 approval.

**Note:** `name_variations` adds a new property to the graph schema. Consider adding a pointer to the Schema v3 doc noting this addition after implementation.

---

## 6. Best Practices Audit

### A) Security & Privacy Practices — All 16 Sections

| # | Section | Verdict | Notes |
|---|---------|---------|-------|
| 1 | Data Classification & Minimization | **Pass** | `name_variations`, `address`, `gravity_audit`, `_meta` are POI metadata, not user PII. |
| 2 | Consent & Transparency | **N/A** | No new user data collection. |
| 3 | Authentication & Authorization | **N/A** | No new endpoints. Workbench is internal tool. |
| 4 | Secure Session Management | **N/A** | No session changes. |
| 5 | Secrets & Credentials | **Pass** | No new secrets. API_BASE already configured. |
| 6 | Encryption | **N/A** | No new data channels. Existing HTTPS assumed. |
| 7 | Logging & Monitoring | **N/A** | No new logging. |
| 8 | Data Retention & Deletion | **Pass** | `name_variations` follows POI node lifecycle. |
| 9 | Third-Party Risk | **N/A** | No new third-party services. |
| 10 | Secure Development Lifecycle | **Pass** | Spec-driven workflow with red team review. |
| 11 | Input Validation & Output Encoding | **Pass** | AC3 requires `escHtml()` on all rendered fields. AC1/AC8 cover validation. Cypher uses parameterized queries — key names from Pydantic model (hardcoded), values parameterized. Safe. |
| 12 | Infrastructure & Network Security | **N/A** | No infra changes. |
| 13 | Privacy by Design | **Pass** | No new PII. |
| 14 | Incident Response | **N/A** | No changes. |
| 15 | Testing & Verification | **Pass** | Spec includes testable ACs and edge cases. |
| 16 | Compliance & Documentation | **Pass** | `name_variations` added to Pydantic model. Schema v3 doc should be updated (pointer). |

### B) Best Practices Library — Domain Audit

#### Security

| Item | Verdict | Notes |
|------|---------|-------|
| XSS prevention | **Pass** | AC3 requires `escHtml()` on all new fields. `escHtml()` covers `&`, `"`, `<`, `>`. |
| Input validation (client) | **Pass** | AC1 updates validation schema. AC7 normalizes field names. |
| Input validation (server) | **Pass** | AC8 adds Pydantic `list[str]` validation. Rejects malformed data with 422. |
| Injection prevention | **Pass** | Cypher uses parameterized queries throughout. |
| API key exposure | **N/A** | No new keys. |

#### Performance

| Item | Verdict | Notes |
|------|---------|-------|
| Alt-name matching complexity | **Pass** | O(POIs x avg alt names) on cached list. At 200 POIs with ~3-5 alt names, <1000 comparisons — negligible. |
| Cached list size | **Pass (for now)** | 200 limit sufficient for Phase 1. Flagged as R1. |
| No new API calls | **Pass** | Alt-name matching uses cached data. No additional round-trips. |

#### Accessibility

| Item | Verdict | Notes |
|------|---------|-------|
| Collapsible `_meta` | **Pass** | `<details>`/`<summary>` is natively accessible. |
| Audit note cards (array) | **Pass** | Individual cards navigable. |
| Alt-name match indicator | **Needs implementation detail** | Badge/note for alt-name matches should include `aria-label` for screen reader context. Add to implementation plan. |

#### UX

| Item | Verdict | Notes |
|------|---------|-------|
| Mixed V2/V3 batch handling | **Pass** | Edge case 1 — V3 fields display only when present. |
| Error clarity for multi-match | **Pass** | Resolved — add to `result.errors` with descriptive message, skip POI. |
| Within-file alt-name duplicates | **Pass** | Resolved — flag when POI A's name appears in POI B's `name_variations` (same-location different-name scenario). |

---

## Implementation Checklist (carry forward to Stage 4)

1. Bulk `detectConflicts()` must check `cachedPoiList` name + `name_variations` (case-insensitive) before API call — use canonical name if alt-name match found
2. `processJson()` must normalize `alternative_names` → `name_variations` before duplicate check
3. Within-file duplicate check must flag cross-referencing alt names (POI A name in POI B's `name_variations`)
4. `renderAuditNotes()` must check `Array.isArray()` before `typeof === 'object'`
5. All new rendered fields must use `escHtml()`
6. All string comparisons for name matching must be case-insensitive (`.toLowerCase()`)
7. Default missing `name_variations` to `[]` on cached POIs
8. Alt-name match UI indicator must include `aria-label` for accessibility
9. Multi-match scenario: add descriptive error, skip POI
10. Add `name_variations` to `POICreate` Pydantic model as `list[str] = []`
