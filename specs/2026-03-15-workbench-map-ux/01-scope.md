# Scope: Workbench Map & Coordinate UX

**Date:** 2026-03-15
**North Star Phase:** Phase 1 — Build the Machine
**Slice:** A of 3 (B = Database Browser, C = Inactive POI Status)

---

## What we're building

- **Address geocode marker on map:** When a POI has an `address` field (from V3 pipeline JSON), geocode it via Nominatim (OSM) and show a second marker on the Leaflet map in a distinct color. Editor can eyeball whether the lat/lng pin and the address pin are close together — a quick visual sanity check.
- **Google Search verification button:** A "Verify on Google" button in the detail panel that opens `google.com/maps/search/{poi_name} {address}` in a new tab. Zero API cost, editor does the verification manually.

## Why

Supports Phase 1 gate (100+ Boston POIs live) by reducing time spent manually cross-referencing coordinates against addresses during editorial review.

## What we're NOT building

- Click-to-move pin (draggable pin already works)
- Editable address field (address not persisted to Neo4j; pipeline metadata only)
- Google Maps Geocoding API integration (north star says that's launch, not MVP)
- Address storage on POI node (deferred)
- Database browser mode (Slice B, separate scope)
- Inactive POI status (Slice C, separate scope)

## What already exists

- **Leaflet map** in `review.html` — `initMap()` (~line 1875) with draggable marker, geofence circle, tile layer
- **Address displayed** as read-only `<div class="readonly-field">` in detail panel (V3 work just shipped)
- **`cachedPoiList`** with POI data including `address` field when present
- **Nominatim** is the committed geocoding provider for MVP (north star: "OpenStreetMap (free) for MVP")

## Dependencies or risks

- **Nominatim rate limit:** 1 request/second, no API key needed. Fine for single-POI editorial review. Must not fire on every keystroke or panel render — only on explicit action or initial detail load.
- **Geocode accuracy:** Nominatim may return imprecise results for historical Boston addresses. The second marker is an approximation — the editor decides, not the tool.

## Best practices flagged for Stage 3

- **Performance:** Nominatim call must be debounced/cached per POI to avoid hammering the API
- **Security:** No API keys involved (Nominatim is keyless, Google link is a URL open). Low risk.
- **UX:** Two markers on a small map need clear visual distinction (color, label, legend)
