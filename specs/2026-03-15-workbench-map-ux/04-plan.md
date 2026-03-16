# Implementation Plan: Workbench Map & Coordinate UX

**Spec:** [02-spec.md](02-spec.md)
**Red Team:** [03-red-team.md](03-red-team.md)
**Date:** 2026-03-15
**File:** `frontend/review.html`

---

## Part A — Task Breakdown

### Task 1: Add `addressMarker` global and cleanup infrastructure

**Files to touch:** `frontend/review.html` (~line 836)
**What to do:**
- Add `let addressMarker = null;` next to the existing `let marker = null;` (line 836)
- Add `let geocodeAbortController = null;` for in-flight request cancellation
- In `initMap()` (line 1876), add `addressMarker = null;` alongside the existing `marker = null;` reset

**What NOT to touch:** `updateMapPin()` logic for the blue draggable marker, geofence circle code
**Success check:** No runtime errors. Existing map behavior unchanged.

---

### Task 2: Create `geocodeAddress()` helper function

**Files to touch:** `frontend/review.html` (add after `updateMapPin()`, ~line 1966)
**What to do:**
Write an async function `geocodeAddress(poi)` that:
1. Returns early if `!poi.address` (no address to geocode)
2. Returns cached result if `poi._geocodedLatLng` already exists
3. Cancels any in-flight geocode request via `geocodeAbortController.abort()`
4. Creates a new `AbortController` and stores it in `geocodeAbortController`
5. Calls Nominatim `/search` endpoint:
   - URL: `https://nominatim.openstreetmap.org/search?format=json&limit=1&q=${encodeURIComponent(poi.address)}`
   - Headers: `{ 'User-Agent': 'Geotada-Workbench/1.0', 'Referer': 'https://geotada.app' }`
   - Pass `{ signal: geocodeAbortController.signal }` to fetch
6. Validates response: `data[0].lat` and `data[0].lon` must be finite numbers (use `isFinite(parseFloat(...))`)
7. Caches result on `poi._geocodedLatLng = { lat: parseFloat(data[0].lat), lng: parseFloat(data[0].lon) }`
8. Returns the cached object
9. On any error (including `AbortError`), returns `null` silently — no console errors for abort, log others

**What NOT to touch:** Existing city geocoding code (lines 949-993)
**Success check:** Calling `geocodeAddress(poi)` with a valid address returns `{ lat, lng }`. Calling with no address or bad address returns `null`. Calling twice returns cached result without a second fetch.

---

### Task 3: Create `addAddressMarker()` function to place/remove the orange marker

**Files to touch:** `frontend/review.html` (add after `geocodeAddress()`)
**What to do:**
Write a function `addAddressMarker(geocodedLatLng, addressText)` that:
1. Removes existing `addressMarker` if present: `if (addressMarker) { map.removeLayer(addressMarker); addressMarker = null; }`
2. If `geocodedLatLng` is null, return (no marker to show)
3. Creates an orange circle marker (not a pin — visually distinct from blue):
   ```javascript
   addressMarker = L.circleMarker([geocodedLatLng.lat, geocodedLatLng.lng], {
     radius: 10, color: '#f97316', fillColor: '#f97316', fillOpacity: 0.7,
     weight: 2, title: 'Geocoded address location'
   }).addTo(map);
   ```
4. Binds a popup to the orange marker: `addressMarker.bindPopup(escHtml(addressText))`
5. If the blue `marker` also exists, fits bounds to show both:
   ```javascript
   if (marker) {
     const group = L.featureGroup([marker, addressMarker]);
     map.fitBounds(group.getBounds().pad(0.3));
   }
   ```

**What NOT to touch:** Blue marker creation/dragging logic, geofence circle
**Success check:** Orange circle marker appears at geocoded location. Popup shows address text on click. Map fits to show both markers. Removing the marker (calling with null) cleans up.

---

### Task 4: Add map legend

**Files to touch:** `frontend/review.html` (inside `addAddressMarker()`, or as a separate helper called from it)
**What to do:**
When `addressMarker` is added (and blue marker exists), add a Leaflet control for the legend:
```javascript
if (!map._legend) {
  const legend = L.control({ position: 'bottomright' });
  legend.onAdd = function() {
    const div = L.DomUtil.create('div', 'map-legend');
    div.innerHTML = '<span style="color:#3b82f6;">&#9679;</span> Coordinates &nbsp; <span style="color:#f97316;">&#9679;</span> Address';
    return div;
  };
  legend.addTo(map);
  map._legend = legend;
}
```

Add CSS for `.map-legend`:
```css
.map-legend {
  background: rgba(20, 24, 32, 0.9);
  color: var(--text);
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 0.75rem;
  font-family: 'DM Sans', sans-serif;
  border: 1px solid var(--border);
}
```

When `addAddressMarker()` is called with `null` (no orange marker), remove the legend:
```javascript
if (map._legend) { map.removeControl(map._legend); map._legend = null; }
```

**What NOT to touch:** Existing map styles, tile layer attribution
**Success check:** Legend appears in bottom-right when both markers are shown. Legend removed when orange marker is removed. Legend has semi-opaque background for WCAG AA contrast against map tiles.

---

### Task 5: Wire geocoding into `selectPoi()`

**Files to touch:** `frontend/review.html` (~line 1395, `selectPoi()` function)
**What to do:**
After `renderDetail()` is called (end of `selectPoi()`), add the geocode call:
```javascript
// Address geocode marker (fire-and-forget after render)
const poi = poiData[activeIdx];
const geocoded = await geocodeAddress(poi);
addAddressMarker(geocoded, poi.address || '');
```

This ensures:
- Geocode fires only on POI selection, not on every `renderDetail()` re-render
- The `AbortController` in `geocodeAddress` cancels stale requests if the user navigates quickly
- Result is cached on `poi._geocodedLatLng` so repeat visits skip the API call

**What NOT to touch:** Conflict detection logic in `selectPoi()`, `renderDetail()` itself
**Success check:** Selecting a POI with an address shows the orange marker after a brief delay. Selecting a POI without an address shows no orange marker. Rapidly clicking through POIs doesn't cause errors.

---

### Task 6: Add "Verify on Google Maps" button

**Files to touch:** `frontend/review.html` (~line 1565, inside `renderDetail()`)
**What to do:**
Add the button in the detail panel HTML template. Place it as a separate element after the address field (or after orientation if no address):

After the address conditional block and before `name_variations`, insert:
```javascript
<div class="field-group">
  <button class="verify-google-btn" onclick="window.open('https://www.google.com/maps/search/' + encodeURIComponent('${escHtml(poi.poi_name)}' + (poi.address ? ' ' + '${escHtml(poi.address)}' : '')), '_blank')" title="Open Google Maps to verify this POI's location">
    Verify on Google Maps &#8599;
  </button>
</div>
```

Note: The `onclick` handler must properly construct the URL using the actual POI data. Since this is inside a template literal, use a safer approach — define a helper:

Add a function `openGoogleMaps(idx)`:
```javascript
function openGoogleMaps(idx) {
  const poi = poiData[idx];
  const query = poi.address ? `${poi.poi_name} ${poi.address}` : poi.poi_name;
  window.open(`https://www.google.com/maps/search/${encodeURIComponent(query)}`, '_blank');
}
```

Then in the template:
```javascript
<div class="field-group">
  <button class="verify-google-btn" onclick="openGoogleMaps(${activeIdx})" title="Open Google Maps to verify this POI's location">
    Verify on Google Maps &#8599;
  </button>
</div>
```

Add CSS for `.verify-google-btn`:
```css
.verify-google-btn {
  background: var(--surface-2);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 0.4rem 0.8rem;
  font-size: 0.85rem;
  font-family: inherit;
  cursor: pointer;
  transition: border-color 0.15s;
}
.verify-google-btn:hover { border-color: var(--accent); }
.verify-google-btn:focus { outline: 2px solid var(--accent); outline-offset: 2px; }
```

**What NOT to touch:** Address field rendering, readonly-field styling
**Success check:** Button visible for all POIs. Click opens Google Maps in new tab with correct URL-encoded query. Button is keyboard-accessible (Tab + Enter works).

---

### Task 7: Update existing Nominatim call with User-Agent header

**Files to touch:** `frontend/review.html` (~line 960, city geocoding)
**What to do:**
Change the existing fetch headers from:
```javascript
{ headers: { 'Referer': 'https://geotada.app' } }
```
to:
```javascript
{ headers: { 'User-Agent': 'Geotada-Workbench/1.0', 'Referer': 'https://geotada.app' } }
```

**What NOT to touch:** City geocoding logic, error handling
**Success check:** City geocoding still works. Network inspector shows `User-Agent` header on Nominatim requests.

---

## Part B — Test Definitions

All tests are **manual verification** (browser-based HTML tool, no test framework).

| # | Acceptance Criterion | Test Type | Steps | Expected Result |
|---|---------------------|-----------|-------|-----------------|
| 1 | Orange marker for POI with address | Manual | Upload JSON with a POI that has `address`. Select it. | Orange circle marker appears on map at a plausible location for the address. Blue pin also visible. |
| 2 | No orange marker without address | Manual | Select a POI that has no `address` field. | Map shows only blue pin. No orange marker. No console errors. |
| 3 | Nominatim failure graceful | Manual | Disconnect network or use a POI with gibberish address (e.g., "zzzznotanaddress123"). | No orange marker. No error toast. Blue pin unaffected. Console may log error (not user-facing). |
| 4 | Navigation clears old marker | Manual | Select POI A (has address, orange marker appears). Select POI B (no address). | Orange marker from POI A is removed. Only blue pin for POI B. |
| 5 | fitBounds when markers apart | Manual | Use a POI where address geocodes far from coordinates (e.g., wrong address). | Map zooms out to show both markers with padding. Both visible. |
| 6 | Google Maps button with address | Manual | Select POI with address. Click "Verify on Google Maps". | New tab opens at `google.com/maps/search/POI+Name+Address`. URL-encoded correctly. |
| 7 | Google Maps button without address | Manual | Select POI without address. Click button. | New tab opens at `google.com/maps/search/POI+Name`. |
| 8 | Cache prevents duplicate calls | Manual | Select POI A (has address). Note network request. Select POI B. Select POI A again. | Second visit to POI A: no new Nominatim network request (check DevTools Network tab). |
| 9 | Legend appears/disappears | Manual | Select POI with address (both markers). Then select POI without address. | Legend appears with both markers. Legend disappears when only blue pin is shown. |
| 10 | Rapid navigation no errors | Manual | Click through 5+ POIs quickly in succession. | No console errors. No duplicate markers. Last selected POI shows correct state. |
| 11 | Orange marker popup | Manual | Click the orange circle marker. | Popup shows the address text. |
| 12 | Button keyboard accessible | Manual | Tab to the "Verify on Google Maps" button. Press Enter. | Button receives focus ring. New tab opens on Enter. |

---

## Part C — Claude Code Prompt

```
## Task: Add Address Geocode Marker and Google Maps Verification to Editorial Workbench

**Slice goal:** An editor can visually compare a POI's coordinate pin against its geocoded address on the map, and quickly verify via Google Maps, so that coordinate accuracy is validated faster during editorial review.

**File:** `frontend/review.html` (single file, all changes here)

### What to build (in order):

**1. Globals (~line 836)**
Add alongside existing `let marker = null;`:
- `let addressMarker = null;`
- `let geocodeAbortController = null;`
In `initMap()` (line 1876), add `addressMarker = null;` in the cleanup block.

**2. `geocodeAddress(poi)` async function (add after `updateMapPin()`, ~line 1966)**
- Return null if `!poi.address`
- Return `poi._geocodedLatLng` if already cached
- Cancel in-flight request: `if (geocodeAbortController) geocodeAbortController.abort(); geocodeAbortController = new AbortController();`
- Fetch `https://nominatim.openstreetmap.org/search?format=json&limit=1&q=${encodeURIComponent(poi.address)}`
  - Headers: `{ 'User-Agent': 'Geotada-Workbench/1.0', 'Referer': 'https://geotada.app' }`
  - Options: `{ signal: geocodeAbortController.signal }`
- Validate: `isFinite(parseFloat(data[0].lat)) && isFinite(parseFloat(data[0].lon))`
- Cache: `poi._geocodedLatLng = { lat: parseFloat(data[0].lat), lng: parseFloat(data[0].lon) }`
- Return cached object, or null on any error (swallow AbortError silently, console.warn others)

**3. `addAddressMarker(geocodedLatLng, addressText)` function**
- Remove existing addressMarker if present
- Remove legend if present: `if (map._legend) { map.removeControl(map._legend); map._legend = null; }`
- If geocodedLatLng is null, return
- Create orange circle marker: `L.circleMarker([lat, lng], { radius: 10, color: '#f97316', fillColor: '#f97316', fillOpacity: 0.7, weight: 2 }).addTo(map)`
- Set title attribute for accessibility: use Leaflet's `title` option or set on the element
- Bind popup: `addressMarker.bindPopup(escHtml(addressText))`
- If blue `marker` exists, fitBounds with padding: `map.fitBounds(L.featureGroup([marker, addressMarker]).getBounds().pad(0.3))`
- Add legend control (position: bottomright) with semi-opaque background:
  - "● Coordinates  ● Address" (blue and orange dots)
  - Store as `map._legend` for cleanup

**4. CSS additions (in the `<style>` block)**
```css
.map-legend {
  background: rgba(20, 24, 32, 0.9);
  color: #e4e8f0;
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 0.75rem;
  font-family: 'DM Sans', sans-serif;
  border: 1px solid #252b38;
}
.verify-google-btn {
  background: #1a1f2b;
  color: #e4e8f0;
  border: 1px solid #252b38;
  border-radius: 6px;
  padding: 0.4rem 0.8rem;
  font-size: 0.85rem;
  font-family: inherit;
  cursor: pointer;
  transition: border-color 0.15s;
}
.verify-google-btn:hover { border-color: #f59e0b; }
.verify-google-btn:focus { outline: 2px solid #f59e0b; outline-offset: 2px; }
```

**5. Wire into `selectPoi()` (~line 1395)**
After `renderDetail()` at the end of `selectPoi()`, add:
```javascript
const currentPoi = poiData[activeIdx];
const geocoded = await geocodeAddress(currentPoi);
addAddressMarker(geocoded, currentPoi.address || '');
```

**6. `openGoogleMaps(idx)` function**
```javascript
function openGoogleMaps(idx) {
  const poi = poiData[idx];
  const query = poi.address ? `${poi.poi_name} ${poi.address}` : poi.poi_name;
  window.open(`https://www.google.com/maps/search/${encodeURIComponent(query)}`, '_blank');
}
```

**7. "Verify on Google Maps" button in `renderDetail()` (~line 1565)**
After the address conditional block and before the `name_variations` conditional, add:
```javascript
`<div class="field-group"><button class="verify-google-btn" onclick="openGoogleMaps(${activeIdx})" title="Open Google Maps to verify this POI location">Verify on Google Maps &#8599;</button></div>`
```
This must be OUTSIDE the `poi.address` conditional — the button is always visible per AC7.

**8. Update existing Nominatim call (~line 960)**
Add `'User-Agent': 'Geotada-Workbench/1.0'` to the existing city geocoding fetch headers.

### What NOT to touch:
- Blue draggable marker logic (`marker` global, drag handlers)
- `updateMapPin()` behavior
- Geofence circle
- Conflict detection system
- Upload/commit flow
- Beat rendering
- Any backend files

### Verification checklist:
1. POI with address → orange circle marker at geocoded location, blue pin at coordinates, both visible
2. POI without address → no orange marker, no errors
3. Nominatim failure → no orange marker, no user-visible error
4. Navigate between POIs → old orange marker removed, new one placed (or not)
5. Markers far apart → map fitBounds shows both with padding
6. "Verify on Google Maps" click → new tab with correct URL (name + address, URL-encoded)
7. No address → button still visible, opens with just POI name
8. Select same POI twice → second visit uses cache, no Nominatim request
9. Legend appears when both markers shown, disappears when only blue pin
10. Rapid POI clicking → no errors, no stale markers, AbortController cancels old requests
11. Orange marker click → popup with address text
12. Button keyboard accessible (Tab + Enter)
13. User-Agent header present on all Nominatim requests

### Best practices implementation checklist:
- [ ] `User-Agent: Geotada-Workbench/1.0` on all Nominatim calls (B1)
- [ ] Nominatim response validated (lat/lng are finite numbers) before marker creation (Section 11)
- [ ] Geocode fires only in `selectPoi()`, never on `renderDetail()` re-renders (Performance)
- [ ] `AbortController` cancels in-flight requests on navigation (R3)
- [ ] `encodeURIComponent()` for Google Maps URL (C4)
- [ ] Map legend has semi-opaque background for WCAG AA contrast (Accessibility)
- [ ] Orange marker has title/alt for assistive technology (Accessibility)
- [ ] Button has focus styles and is keyboard-operable (Accessibility)

Before starting, confirm you understand the full scope and flag any conflicts with the existing codebase or assumptions you are making.
```

---

## Part D — Best Practices Implementation Checklist

| # | Practice | Task(s) | How to Verify |
|---|----------|---------|---------------|
| 1 | User-Agent header on Nominatim | Task 2, Task 7 | DevTools Network tab: check request headers on Nominatim calls |
| 2 | Input validation on Nominatim response | Task 2 | Test with gibberish address — no marker created, no crash. Check `isFinite()` call in code. |
| 3 | Geocode gated to `selectPoi()` only | Task 5 | Drag the blue pin (triggers `renderDetail()` via coord update) — verify no new Nominatim request in Network tab |
| 4 | AbortController for stale requests | Task 2 | Rapidly click through 5 POIs — Network tab shows cancelled requests, no duplicate markers |
| 5 | `encodeURIComponent()` for URLs | Task 6 | Select POI with special characters in name/address — verify Google Maps URL is properly encoded |
| 6 | Legend WCAG AA contrast | Task 4 | Visual check: legend text readable against map tiles with semi-opaque dark background |
| 7 | Orange marker accessibility title | Task 3 | Inspect element in DevTools — confirm `title` attribute present |
| 8 | Button keyboard accessibility | Task 6 | Tab to button, verify focus ring. Press Enter, verify Google Maps opens. |

---

## North Star Final Check

- Uses Nominatim (OSM) per commitment: "OpenStreetMap (free) for MVP"
- No paid APIs introduced (Google Maps link is a URL open, not an API call)
- Editorial Workbench remains browser-based HTML/JS
- Supports Phase 1 gate by speeding editorial coordinate review
- Google Maps link here is NOT the launch-phase Geocoding API integration — no conflict
- Under 12 tasks (7 tasks). Single file. Fits cleanly in one Claude Code session.
