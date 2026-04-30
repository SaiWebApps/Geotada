# Red Team Review: Workbench Map & Coordinate UX

**Spec:** [02-spec.md](02-spec.md)
**Date:** 2026-03-15
**Reviewer:** Adversarial engineering review (Stage 3)

---

## 1. Blockers

**B1 — Nominatim Usage Policy requires meaningful `User-Agent`, not just `Referer`**
Nominatim's usage policy requires a custom `User-Agent` header identifying the application. The existing city geocoding code (review.html:960) sets `Referer` but no `User-Agent`. Increased request volume from address geocoding risks being blocked without proper identification.
**Resolution:** Add `User-Agent: Geotada-Workbench/1.0` header to all Nominatim fetch calls (including the existing city geocode).

**B2 — Spec says "address geocoded via Nominatim" but doesn't specify the endpoint**
The existing code uses `/search` (forward geocoding by city name). The spec needs forward geocoding of a street address — same endpoint, but the spec should be explicit.
**Resolution:** Clarify: "Forward geocode the `address` field value using Nominatim `/search` endpoint with `format=json&limit=1`."

---

## 2. Risks

**R1 — Nominatim accuracy for historical Paris addresses (Likelihood: High)**
Many POIs will have historical or informal addresses. Nominatim may return wrong locations or no results. The no-result case is handled (AC3), but editors may misinterpret a confidently wrong geocode.
**Mitigation:** Add a subtle "approximate" label or tooltip on the orange marker to reinforce that this is an approximation, not ground truth.

**R2 — `initMap()` destroys and recreates the map on every POI selection (Likelihood: Medium)**
Current code calls `map.remove()` on every `renderDetail()`. Adding a second marker plus `fitBounds()` means full reconstruction on every navigation. May cause flicker.
**Mitigation:** Accept existing pattern. Optimize only if flicker becomes noticeable during testing.

**R3 — Rapid POI navigation floods Nominatim despite debounce (Likelihood: Low)**
Clicking through POIs quickly queues requests even with debounce.
**Mitigation:** Use `AbortController` to cancel in-flight Nominatim requests when a new POI is selected. Simpler and more correct than debounce alone.

---

## 3. Open Questions — Resolved

**Q1 — Should the orange marker have a popup/tooltip?**
**Decision: Yes.** Clicking the orange marker shows the geocoded address text in a Leaflet popup.

**Q2 — Where does the "Verify on Google Maps" button go?**
**Decision: Next to the address field.** When no address is present, place it after the orientation field in the same relative position.

**Q3 — Cache strategy for geocode results?**
**Decision: Option B — store on the POI object itself** (e.g., `poi._geocodedLatLng`). Follows existing pattern (`poi._conflicts`), simpler, no new global. Cache is lost on data reload, which is acceptable.

---

## 4. Codebase Conflicts

**C1 — `initMap()` only manages one marker (`marker` global)**
Current code has a single global `marker` variable (review.html:833). Adding a second marker requires a second global (`addressMarker`) or a marker group. `updateMapPin()` (review.html:1931) also only handles the single marker — must handle or ignore the address marker.

**C2 — No existing session-level cache pattern for API results**
Resolved by Q3 decision: store on POI object (`poi._geocodedLatLng`), consistent with `poi._conflicts` pattern.

**C3 — Address field is conditionally rendered**
The address `<div>` only exists in the DOM when `poi.address` is truthy (review.html:1565). Per AC7, the "Verify on Google Maps" button is always visible — so it cannot be nested inside the conditional address block. Must be a separate element positioned adjacently.

**C4 — `escHtml()` exists but URL encoding needs `encodeURIComponent()`**
Google Maps URL construction needs `encodeURIComponent()` for POI name and address. `escHtml()` (review.html:870) is for HTML entity escaping, not URL encoding. Must not be confused.

---

## 5. North Star Check

**Aligned:**
- Uses Nominatim (OSM) per commitment: "OpenStreetMap (free) for MVP"
- Editorial Workbench is browser-based HTML/JS per commitment
- No API keys or paid services introduced
- Supports Phase 1 gate (100+ Paris POIs) by speeding editorial review

**No conflicts found.** The spec stays within "Build the Machine" phase scope.

**Clarification:** The Google Maps integration here is a URL open (search link), NOT the launch-phase Google Geocoding API integration referenced in the north star. No conflict.

---

## 6. Best Practices Audit

### A) Security & Privacy Practices (SECURITY_PRIVACY_PRACTICES.md — 16 sections)

| # | Section | Verdict | Notes |
|---|---------|---------|-------|
| 1 | Data Classification & Minimization | **Pass** | No new data collected. Address from existing pipeline JSON. Nominatim receives only POI address strings. |
| 2 | Consent & Transparency | **N/A** | No user data — editor tool only. |
| 3 | Authentication & Authorization | **N/A** | No new endpoints. |
| 4 | Secure Session Management | **N/A** | No sessions involved. |
| 5 | Secrets & Credentials | **Pass** | No API keys needed. |
| 6 | Encryption | **N/A** | Nominatim uses HTTPS. No new data storage. |
| 7 | Logging & Monitoring | **N/A** | No server-side changes. |
| 8 | Data Retention & Deletion | **N/A** | In-memory cache, lost on page reload. |
| 9 | Third-Party Risk | **Fail → Fixed** | Nominatim usage increase requires User-Agent compliance. See Blocker B1. |
| 10 | Secure Development Lifecycle | **Pass** | Spec-driven with red team review. |
| 11 | Input Validation & Output Encoding | **Fail → Requires implementation note** | Nominatim response lat/lng must be validated as numbers before creating marker. Google Maps URL must use `encodeURIComponent()`. |
| 12 | Infrastructure & Network Security | **N/A** | Client-side only. |
| 13 | Privacy by Design | **Pass** | No user data exposed. POI metadata only. |
| 14 | Incident Response | **N/A** | No new failure modes. |
| 15 | Testing & Verification | **Pass** | Testable acceptance criteria defined. |
| 16 | Compliance & Documentation | **N/A** | No new data flows. |

### B) Best Practices Library Audit

**Security**

| Item | Verdict | Notes |
|------|---------|-------|
| API keys not in client code | **Pass** | No keys needed. |
| Input validation at boundary | **Fail → Requires implementation note** | Validate Nominatim response (lat/lng are numbers, within plausible range) before creating Leaflet marker. |
| XSS prevention | **Pass** | `escHtml()` for display, `encodeURIComponent()` for URLs. |
| CORS | **N/A** | Nominatim allows cross-origin. |

**Performance**

| Item | Verdict | Notes |
|------|---------|-------|
| Network resilience | **Pass** | AC3 handles failure gracefully. |
| Caching | **Pass** | Session-level cache on POI object (AC8, Q3). |
| Rate limiting respect | **Pass** | AbortController + cache (R3 mitigation). |
| No unnecessary requests | **Fail → Requires implementation note** | Geocode call must fire only on `selectPoi()`, not on every `renderDetail()`. Gate the call appropriately. |

**Privacy**

| Item | Verdict | Notes |
|------|---------|-------|
| No user data to external service | **Pass** | Only POI addresses sent. |
| Data minimization | **Pass** | Only address string sent. |

**Accessibility**

| Item | Verdict | Notes |
|------|---------|-------|
| Map legend readable | **Fail → Requires AC update** | Legend must meet WCAG 2.1 AA contrast against map tile background. Specify semi-opaque background on legend element. |
| Button keyboard accessible | **Pass** | Standard `<button>` is keyboard-accessible by default. |
| Screen reader for markers | **Fail → Requires implementation note** | Orange marker needs `title` or `alt` attribute (e.g., "Geocoded address location") for assistive technology. |

**UX**

| Item | Verdict | Notes |
|------|---------|-------|
| Clear visual distinction | **Pass** | Blue vs. orange markers with legend. |
| Graceful degradation | **Pass** | All failure modes result in "behaves as today." |
| Cognitive load | **Pass** | Adds only two UI elements (marker + button). |

---

## Implementation Notes for Stage 4

These items must be addressed in the implementation plan:

1. **Add `User-Agent: Geotada-Workbench/1.0`** to all Nominatim fetch calls (B1)
2. **Use Nominatim `/search` endpoint** with `format=json&limit=1` for forward geocoding (B2)
3. **Validate Nominatim response** — confirm lat/lng are valid numbers before creating marker (Section 11)
4. **Gate geocode call to `selectPoi()` only** — never on `renderDetail()` re-renders or coordinate drags (Performance)
5. **Use `AbortController`** to cancel in-flight Nominatim requests on POI navigation (R3)
6. **Cache geocode result on `poi._geocodedLatLng`** — skip API call if already populated (Q3)
7. **Orange marker popup** shows geocoded address text on click (Q1)
8. **"Verify on Google Maps" button placed next to address field** — separate element, always visible (Q2, C3)
9. **Map legend** needs semi-opaque background for WCAG 2.1 AA contrast (Accessibility)
10. **Orange marker `title` attribute** for screen reader accessibility (Accessibility)
11. **Use `encodeURIComponent()`** for Google Maps URL, not `escHtml()` (C4)
12. **New global `addressMarker`** variable alongside existing `marker` (C1)
