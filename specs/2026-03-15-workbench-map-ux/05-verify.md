# Verification Report: Workbench Map & Coordinate UX

**Date:** 2026-03-15
**Spec:** [02-spec.md](02-spec.md)
**Plan:** [04-plan.md](04-plan.md)
**File modified:** `frontend/review.html`

---

## Acceptance Criteria — Pass/Fail

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | POI with address → orange circle marker at geocoded location | **PASS** | `addAddressMarker()` creates `L.circleMarker` with orange color at Nominatim-returned coordinates (line 2028-2031) |
| 2 | POI without address → no orange marker, no errors | **PASS** | `geocodeAddress()` returns null if `!poi.address` (line 2002); `addAddressMarker(null, ...)` removes existing marker and returns early (line 2027) |
| 3 | Nominatim failure → no orange marker, no UI error | **PASS** | `geocodeAddress()` catch block returns null, swallows AbortError silently, console.warns others (lines 2018-2021) |
| 4 | Navigation clears old marker | **PASS** | `addAddressMarker()` always removes existing `addressMarker` and legend first (lines 2025-2026) before placing new one |
| 5 | Markers far apart → fitBounds | **PASS** | When both `marker` and `addressMarker` exist, `L.featureGroup` + `fitBounds` with 0.3 padding (lines 2033-2035) |
| 6 | Google Maps button with address → correct URL | **PASS** | `openGoogleMaps()` builds query as `poi_name + address`, URL-encoded via `encodeURIComponent()` (lines 2050-2054) |
| 7 | Google Maps button without address → visible, uses POI name only | **PASS** | Button is outside the `poi.address` conditional in the template (line 1597). `openGoogleMaps()` falls back to just `poi.poi_name` (line 2052) |
| 8 | Cache prevents duplicate Nominatim calls | **PASS** | `geocodeAddress()` checks `poi._geocodedLatLng` and returns cached result immediately (line 2003) |

---

## Tests — Manual Verification Steps

| # | Test | Type | Status |
|---|------|------|--------|
| 1 | Orange marker for POI with address | Manual | Ready to verify |
| 2 | No orange marker without address | Manual | Ready to verify |
| 3 | Nominatim failure graceful | Manual | Ready to verify |
| 4 | Navigation clears old marker | Manual | Ready to verify |
| 5 | fitBounds when markers apart | Manual | Ready to verify |
| 6 | Google Maps button with address | Manual | Ready to verify |
| 7 | Google Maps button without address | Manual | Ready to verify |
| 8 | Cache prevents duplicate calls | Manual | Ready to verify |
| 9 | Legend appears/disappears | Manual | Ready to verify |
| 10 | Rapid navigation no errors | Manual | Ready to verify |
| 11 | Orange marker popup | Manual | Ready to verify |
| 12 | Button keyboard accessible | Manual | Ready to verify |

---

## Best Practices Compliance

| # | Practice | Status | Evidence |
|---|----------|--------|----------|
| 1 | User-Agent on all Nominatim calls | **PASS** | `geocodeAddress()` line 2009 and city geocoding line 961 both include `'User-Agent': 'Ondoway-Workbench/1.0'` |
| 2 | Input validation on Nominatim response | **PASS** | `isFinite(parseFloat(...))` check on both lat and lon (line 2013) |
| 3 | Geocode gated to `selectPoi()` only | **PASS** | Geocode call is at end of `selectPoi()` (lines 1452-1454), not in `renderDetail()` |
| 4 | AbortController for stale requests | **PASS** | Previous controller aborted before new one created (lines 2004-2005); signal passed to fetch (line 2010) |
| 5 | `encodeURIComponent()` for URLs | **PASS** | Used in both Nominatim query (line 2007) and Google Maps URL (line 2053) |
| 6 | Legend WCAG AA contrast | **PASS** | `rgba(20, 24, 32, 0.9)` background with `#e4e8f0` text (CSS `.map-legend` class) |
| 7 | Orange marker accessibility title | **PASS** | `title: 'Geocoded address location'` option passed to circleMarker (line 2030) |
| 8 | Button keyboard accessibility | **PASS** | Native `<button>` element (inherently focusable/keyboard-operable) with explicit `:focus` outline style |

---

## Autonomous Decisions Made

1. **`window.openGoogleMaps` instead of IIFE-scoped function** — The entire workbench JS is wrapped in an IIFE. Since the "Verify on Google Maps" button uses an inline `onclick` attribute (rendered via template literal), the function must be accessible from the global scope. Exposed via `window.openGoogleMaps` to resolve this. Alternative was event delegation, but inline onclick is simpler for a single button.

2. **Legend cleanup on every `addAddressMarker` call** — The plan specified legend removal in `addAddressMarker(null)`, but we clean up legend at the top of every `addAddressMarker` call (before checking if `geocodedLatLng` is null) for robustness. This prevents stale legends when switching between POIs.

---

## Scope Creep Check

No items built outside the plan. All 7 tasks implemented exactly as specified:
- Task 1: Globals added (lines 837-838)
- Task 2: `geocodeAddress()` function (lines 2001-2022)
- Task 3: `addAddressMarker()` function (lines 2024-2048)
- Task 4: Map legend (integrated into `addAddressMarker()`, lines 2037-2047)
- Task 5: Wired into `selectPoi()` (lines 1452-1454)
- Task 6: `openGoogleMaps()` + button in template (lines 1597, 2050-2054)
- Task 7: User-Agent header on city geocoding (line 961)
- CSS: `.map-legend` and `.verify-google-btn` styles added (lines 746-766)
