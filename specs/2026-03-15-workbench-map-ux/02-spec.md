# Spec: Workbench Map & Coordinate UX

**Date:** 2026-03-15
**Type:** Behavior Spec (Flavor A)
**Scope:** [01-scope.md](01-scope.md)
**North Star Phase:** Phase 1 — Build the Machine

---

## Slice Goal

An **editor** can **visually compare a POI's lat/lng pin against its geocoded address on the map, and quickly verify via Google Maps** so that **coordinate accuracy is validated faster during editorial review**.

## Walkthrough

1. Editor uploads a V3 pipeline JSON and opens a POI that has an `address` field.
2. The detail panel shows the address as a read-only field (already exists).
3. The Leaflet map loads with the existing blue draggable pin at the POI's lat/lng coordinates.
4. A second marker (orange, non-draggable) appears on the map at the location returned by geocoding the `address` via Nominatim.
5. If both markers are visible, the map auto-fits bounds so both pins and the area between them are in view. A small legend in the map corner labels "Blue = coordinates" and "Orange = address."
6. If the Nominatim geocode fails or the POI has no address, no orange marker appears and no error is shown — the map behaves exactly as it does today.
7. Below the address field in the detail panel (or below orientation if no address), a "Verify on Google Maps" button is visible.
8. Editor clicks the button; a new browser tab opens to `https://www.google.com/maps/search/{poi_name}+{address}` (or just `{poi_name}` if no address).

## Acceptance Criteria

1. **Works when** a POI with a valid `address` field is selected — an orange non-draggable marker appears at the Nominatim-geocoded location, distinct from the blue draggable coordinate pin.
2. **Works when** a POI without an `address` field is selected — no orange marker appears, no errors, map behaves as before.
3. **Works when** the Nominatim API returns no results or errors — no orange marker appears, no UI error shown, blue pin unaffected.
4. **Works when** the editor navigates between POIs — the previous orange marker is removed and a new one is placed (or not) based on the new POI's address.
5. **Works when** the two markers are far apart — the map auto-fits bounds to show both markers with padding.
6. **Works when** the editor clicks "Verify on Google Maps" — a new tab opens with the correct search URL containing the POI name and address (if present), URL-encoded.
7. **Works when** the POI has no address — the "Verify on Google Maps" button is still visible and opens a Google Maps search using only the POI name.
8. **Works when** multiple POIs are reviewed in sequence — Nominatim is called at most once per POI (result cached for the session).

## Edge Cases

1. **Address geocodes to a location far from the POI coordinates** (e.g., >1km) — map zooms out to fit both; the visual gap itself is the signal to the editor.
2. **Nominatim rate limit hit** (>1 req/sec during rapid POI navigation) — geocode requests are debounced; if skipped, no orange marker appears silently.
3. **Address contains special characters or non-ASCII** — URL-encoded properly for both Nominatim API call and Google Maps link.
4. **POI has coordinates but they're invalid** — blue pin is already absent per existing behavior; orange marker may still appear if address geocodes successfully.

## Best Practices Check

- **Security:** Low risk — no API keys, no user auth involved. Google Maps link is a URL open. Nominatim is keyless public API.
- **Privacy:** No user data involved — POI metadata only.
- **Performance:** Nominatim calls debounced and cached per session to respect rate limits.
- **Accessibility:** Map legend must be readable; button must be keyboard-accessible.
- **UX:** Two markers need clear color distinction and a legend. Button placement consistent with detail panel layout.
