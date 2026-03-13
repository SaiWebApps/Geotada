# Scope: Editorial Workbench UI Test Script

**Date:** 2026-03-11
**North star ref:** Phase 1 — Content pipeline + Editorial Workbench

---

## What we're building

- A Playwright (Python) test script that opens a **visible browser**, loads a purpose-built JSON fixture into the Editorial Review Workbench (`review.html`), and exercises the happy path plus key edge cases
- A **comprehensive JSON test fixture** designed to trigger specific UI states: valid POIs, invalid coordinates, outside-geofence POIs, duplicate POI names, empty beats, gravity boundary values (1 and 5), long text fields, and multiple lenses
- Tests cover: city prompt → JSON load → duplicate resolution → POI list rendering → POI detail editing → beat editing → defer/complete flow → conflict detection → upload to Neo4j — with assertions at each step
- Output is a **bug report** (not fixes) — a markdown file listing every UI issue found with reproduction steps, severity, and screenshots

## Why

Phase 1 gate requires the Editorial Workbench to reliably process content. The workbench is now feature-complete (upload + triage) but has never been systematically tested from a user's perspective. This closes that gap before real editorial workflows begin.

## What we're NOT building

- Tests for the Schema Dashboard (`index.html`) or Graph Editor (`editor/index.html`)
- Headless/CI automation — this runs visible so the developer can watch
- Bug fixes — those come after the report, as a separate planned effort
- API/backend tests — those already exist (152 pytest tests)
- Regression suite or ongoing test infrastructure

## What already exists

- `frontend/review.html` — 2,900-line single-file workbench (HTML/CSS/JS)
- `tests/fixtures/` — 3 JSON fixtures for backend stress testing (not designed for UI edge cases)
- Playwright package already in `.venv`
- FastAPI backend serves the frontend and proxies to Neo4j
- Previous Selenium suite (deleted) tested wrong UI — lesson: **test the actual workbench workflow, not generic form tests**

## Dependencies or risks

- **Full stack must be running** — Docker + Neo4j + FastAPI required for upload/conflict flows
- `review.html` is a single 2,900-line file with no framework — all DOM manipulation is vanilla JS, so selectors may be fragile (no `data-testid` attributes)
- The workbench loads external resources (Leaflet CDN, Google Fonts) — network required
- Conflict detection flow depends on existing data in Neo4j — test fixture design must account for this

## Best practices flagged for Stage 3

- **Security:** Tests will interact with the real API — ensure test data doesn't corrupt production-like data
- **Performance:** Large fixture could reveal rendering bottlenecks in the worklist
- **UX:** This is fundamentally a UX audit — the test script is the vehicle for finding UX problems
