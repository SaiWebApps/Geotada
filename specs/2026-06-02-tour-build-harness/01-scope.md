# 01 — Scope: Production Tour-Build Pipeline + Test Harness

> **Date:** 2026-06-02 · **Stage:** 1 (Scope) · **Thinking mode:** Product thinker
>
> **Framing:** This scope moves the tour-builder from CLI prototype toward production. The HTML harness is the validation surface, not the goal.

---

## What we're building

1. **Production routing infrastructure.**
   - Self-hosted OSRM (Docker, Île-de-France OSM extract, "foot" profile). `make osrm-up` alongside Neo4j.
   - Precomputed Paris **POI-to-POI distance matrix** built offline via OSRM. Per-city file (sqlite/Parquet), loaded into memory at API startup. Rebuild becomes a step in the corpus upload pipeline; corpus_version hash tracks staleness.
   - New `src/tour/distance.py` abstraction: `walking_time(a, b) → seconds` and `walking_polyline(a, b) → [(lat,lng)]`. Three call patterns internally:
     - POI ↔ POI → matrix lookup (microseconds)
     - Arbitrary start pin → POI → live OSRM call
     - Final chosen route segments → live OSRM polylines (visualization)
   - `src/tour/routing.py` haversine math becomes the fallback (POIs not yet in matrix, tests, dev).

2. **Algorithm extension (`src/tour/contract.TourInput`).**
   Add `anchor_poi_id` (required), `optional_pois` (≤2), `visit_modes` (`walk_past` | `stop_visit` per anchor). Thread through `select_route()`: anchor is forced inclusion, optional sites scored as preferred candidates within detour budget. Selection budget math now uses `distance.walking_time()` (matrix-backed), not haversine × 1.35.

3. **Two-phase API + endpoints with explicit lens responsibilities.**
   - `POST /tours/plan-route` (Layer A) — runs `select_route()` only. **Uses lenses for POI-level scoring**: aggregates lens-matching beat density per candidate POI (via `(POI)-[:HAS_BEAT]->(:NarrativeBeat)-[:TAGGED_WITH]->(:Lens)`) and weights that signal alongside importance tier and walk cost when deciding inclusion. Does NOT select individual beats. Returns Route: ordered stops, walking segments (with real OSRM polylines + times), total walking time.
   - `POST /tours/build-script` (Layer B) — takes the approved Route, runs `select_poi_beats → generate`. **Uses lenses for beat-level selection**: picks which of each stop's matching beats fire, in what order, scaled to per-stop duration cap, closed with physical-action cue. Returns per-stop beat plan + **script text only** (no rendered audio, no ElevenLabs, no MP3, no S3 upload — those are downstream). Route is locked at this point — Layer B does not reorder stops.
   - Both bypass the older `src/api/crud/trips.py` flow (`/trips/generate` stays untouched).

   **Why two phases, not one:** Route selection and beat selection use lenses at different granularities. Confusing them (one mega-endpoint that returns route + audio together) makes failures harder to diagnose: was the route bad, or was the audio bad on a fine route? The split also lets the user validate the spatial plan before committing to a full audio render — short-circuits expensive corrections.

4. **HTML test harness (`frontend/tour-tester.html`).**
   Paris Leaflet map, draggable start pin, lens multi-select, time-budget input, anchor-POI picker (search-by-name), optional-site picker, visit-mode toggles. Two-phase UX: **"Plan route"** CTA → map renders route + OSRM polylines + per-stop POI cards + total time → user clicks **"Build audio"** OR **"Rebuild with different inputs"** → audio plan reveals per stop. Second read-only draggable "simulated user" pin shows nearest stop + distance only — no execution logic.

## Why

Phase 1 milestone gate requires the Boredom Test passing internally. The existing `src/tour/` pipeline implements ~75% of Layer A and ~40% of Layer B with no user-testable surface beyond a CLI, and its routing math (haversine × 1.35) is documented as a temporary fudge ("upgrade to OSRM later if precision matters" — engineer-spec.md). This scope replaces the fudge with production routing, adds the missing destination semantics, exposes the pipeline over HTTP in a route-validate-then-audio flow, and gives us a harness to evaluate output quality against real Paris corpus inputs.

## What we're NOT building

- **Tour execution simulator** — no proximity-triggered audio firing, dwell tracking, end-time warnings. The "simulated user" pin is read-only positional inspection. (Separate scope.)
- **Audio rendering** — no ElevenLabs TTS call, no MP3 generation, no S3 upload. The pipeline produces the **script text** that an audio engine will later render. Audio rendering is a deterministic transform of a good script; gating on it now would block validation of script quality, which is the actual unknown.
- **Old `/trips/generate` deprecation** — stays as-is. New endpoints sit alongside.
- **Layer B rule completeness** — subject_tag grouping (H1/H2/H4), interior-option flagging (D2), Area entry/exit tagging (G1-G3), tour-naming (N1), optional-detour surfacing (B6/E3 mid band). Use what `src/tour/` currently produces.
- **Multimodal routing** (metro/bus) — north star locks walking-only.
- **Live traffic, time-of-day variance, closures** — open questions in engineer-spec; post-MVP.
- **Elevation / accessibility / mobility profiles** — engineer-spec deferral.
- **Custom OSRM routing profile** — "foot" profile is correct out of the box.
- **Production-scale polyline caching (Redis/CDN)** — flag for later, not in this scope.
- **Multi-city matrices** — Paris only. Architecture is per-city so additive later.
- **Mobile app integration** — endpoints exist for the harness; mobile wiring is downstream.
- **Persisting tours to Neo4j** — harness output is ephemeral JSON.
- **Auth on the new endpoints** — same access pattern as the rest of the API in dev.

## What already exists

- **Algorithm:** `src/tour/contract.py:15`, `src/tour/selection.py:424` (`select_route`), `src/tour/beat_select.py` (`select_poi_beats`), `src/tour/generation.py:121` (`generate`). **88 tests** in `tests/test_tour_*.py`.
- **CLI orchestrator:** `scripts/tour_build.py` exercises the full pipeline end-to-end.
- **Engineer spec:** `specs/2026-05-23-tour-planning-algorithm/engineer-spec.md` — destination + visit-mode semantics drafted; OSRM upgrade flagged.
- **API plumbing:** `src/api/app.py`, `src/api/routes/`, `src/api/dependencies.get_session()` — FastAPI + Neo4j session pattern to mirror.
- **Frontend Leaflet setup:** `frontend/viewer.html` — styling, POI rendering, marker drag patterns to reuse.
- **Paris corpus on Neo4j v2 schema (2026-04-27).**
- **Docker compose / make targets** for Neo4j — pattern for adding OSRM.

## Dependencies & risks

- **88 existing tour tests will re-baseline.** Real OSRM times ≠ haversine × 1.35 times. Tests pinning specific durations need new expected values. The *behaviors* verified (relative ordering, budget math, no padding) stay; absolute numbers shift. This is desired — the tests get more trustworthy — but it's a deliberate batch.
- **TourInput contract change ripples to all callers** (CLI, tests, future API). Add fields as optional with defaults so existing call sites keep working unchanged.
- **Anchor-as-forced-inclusion surfaces infeasibility cases** the current algorithm hides (anchor too far from start in time budget). Desired behavior, but harness needs a clear error path.
- **Lens-thin corridor degradation.** If user selects a lens with sparse corpus coverage near the anchor (e.g., `film_tv` has 3 beats globally), Layer A still picks a sensible spatial route (it has importance-tier and pacing signals to fall back on) but Layer B will produce thin audio per stop. Harness should surface this as visible thinness in the audio reveal, not as a route failure. Engineer-spec flags this as an open question for graceful-degradation surfacing — we'll observe behavior, not solve it in this scope.
- **Matrix-versioning tied to corpus.** A POI's coordinates change → matrix is stale. Needs a `corpus_version` hash on the matrix file, checked at load. Full rebuild for now; incremental later.
- **OSRM container lifecycle.** `make osrm-up`, healthcheck before API starts, `make osrm-down` for teardown. OSM extract download is ~150MB — one-time, cache in repo-ignored dir. Document in README.
- **OSRM-down fallback behavior.** If OSRM container is dead, distance.py should fall back to haversine math with a logged warning, not crash. Same for matrix-load failure.
- **POI search UX.** Harness needs to look up POIs by name to set the anchor. Simplest: client-side filter over a cached `GET /pois?city=paris` dump.
- **Partner coordination** — user confirmed partner is not active on `src/tour/`. Proceeding solo.

## Best practices touched (light awareness for Stage 4)

- **Security** — input validation on lat/lng bounds, anchor_poi_id existence check, lens-name whitelist, time-budget bounds. CORS for harness origin.
- **Privacy** — start-pin coordinates are test data. Note in harness UI that it's a dev tool. No PII flows through.
- **Performance** — matrix lookup is the unblock; OSRM polyline fetch on visualization side is the residual latency (5-12 calls per build, acceptable for self-hosted).
- **UX** — clear error states when (anchor + time budget) infeasible, OSRM down, corpus empty for inputs. No silent failures.
- **Observability** — distance.py should emit basic metrics (matrix-hit vs live-call vs fallback counts) so we can see whether the matrix is doing its job.

## Simplest-path check

The user's framing was a test page for a tour algorithm. Investigation showed a substantial algorithm already exists but with a documented routing shortcut. Two paths were considered: (a) ship the harness against the haversine fudge, validate quality with a known accuracy gap, invest in proper routing later; (b) do production routing now so harness output is trustworthy from day one. Path (a) is faster to a harness but risks invalidating its conclusions ("the algorithm picked a bad order because of distance math" vs. "the algorithm logic is wrong"). Path (b) is more work upfront but produces a harness whose outputs you can trust as production-grade. User chose (b) explicitly: *"the entire point of this is to move us towards production."*

We are NOT rebuilding the algorithm. We are NOT building execution simulation. We are NOT closing the remaining 40% of Layer B coverage. Those are different scopes whose value should be measured against real harness output — which this scope produces.

## Right-sizing

**Large.** Touches ~10-12 files across four layers (Docker/make infra, contract, algorithm, API, frontend), 88 tests re-baseline, schema-safe (no DB migration). **Full 6-stage workflow recommended** (1 → 2 → 3 → 4 → 5 → 6).

Anticipated Stage 3 slice shape (~4 scopes, 1-2 sessions each):
1. **Distance Infrastructure** — OSRM Docker, matrix builder, `distance.py`, routing.py fallback, test re-baseline
2. **TourInput Extension** — anchor + optional sites + visit modes, selection budget math swap
3. **Tour-Build API** — `POST /tours/plan-route` + `POST /tours/build-script` + POI search endpoint
4. **HTML Test Harness** — Leaflet + draggable pins + two-phase UX + OSRM polyline rendering

---

**Approval gate:** Confirm this scope before `/spec` (Stage 2).
