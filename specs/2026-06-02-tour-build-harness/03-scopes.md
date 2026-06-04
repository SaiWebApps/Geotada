# 03 — Scopes: Tour-Build Pipeline + Test Harness

> **Date:** 2026-06-02 · **Stage:** 3 (Scopes) · **Thinking mode:** Delivery planner

This document slices the spec into independently verifiable vertical scopes. Each scope = one commit; can be implemented, tested, and merged before the next begins. AC numbering matches [02-spec.md](02-spec.md).

---

## AC → Scope mapping

| AC | Scope | Notes |
|----|-------|-------|
| AC-1 (valid request → 200 with anchor in stops) | Scope 3 | End-to-end HTTP test |
| AC-2 (route round-tripped to `/build-script` → 200) | Scope 3 | End-to-end HTTP test |
| AC-3 (OSRM down → 200 with `routing_mode: "fallback"`) | Scope 1 | Distance layer test |
| AC-4 (anchor infeasible → 422 with diagnostic) | Scope 3 | HTTP shape; Scope 2 has its own algorithm-level raise test |
| AC-5 (sparse-lens corpus → `thinness_signal: true`) | Scope 3 | Computed from audio side, surfaced in HTTP response |
| AC-6 (matrix loaded at startup, p99 < 1ms lookup) | Scope 1 | Distance layer test |
| AC-7 (harness drops pin → renders stops + polylines + delta) | Scope 4 | Manual browser verification |
| AC-8 (`make test` green: 88 re-baselined + all new) | Scope 1 | Re-baseline lands at Scope 1; new tests added incrementally; full green at every commit |

Every AC maps to exactly one scope. No unmapped ACs.

---

## Scope 1: Production Routing Infrastructure

**What:** Stand up self-hosted OSRM in Docker with the Île-de-France OSM extract; build a `make matrix-build paris` target that produces a precomputed POI-to-POI walking-time + distance matrix file; introduce `src/tour/distance.py` as the three-tier abstraction (matrix → live OSRM → haversine fallback); swap `src/tour/routing.py`'s walking-time math to call through it; re-baseline all 88 existing `tests/test_tour_*.py` cases against the new (more accurate) numbers.

**Acceptance criteria:** AC-3, AC-6, AC-8.

**Depends on:** None. Foundation scope.

**Verification commands:**
```bash
# Infrastructure stands up cleanly
make osrm-up && curl -fsS http://localhost:5000/route/v1/foot/2.3214,48.8676;2.3499,48.8530 | jq '.code'   # "Ok"

# Matrix builds and loads quickly
make matrix-build paris && python -c "from src.tour.distance import load_matrix; m = load_matrix('paris'); print(f'pairs={len(m)} mem_mb={m.memory_mb()}')"   # pairs > 50000, mem_mb < 100

# Tests green after re-baseline (88 existing + new distance-layer tests)
make test 2>&1 | tail -3   # X passed, 0 skipped, 0 failed

# Fallback behavior with OSRM down
make osrm-down && python -c "from src.tour.distance import walking_time; print(walking_time((48.8676,2.3214),(48.8530,2.3499)))" 2>&1 | grep -i 'WARNING.*fallback'   # warning logged, value returned
```

**Estimated sessions:** 3.

---

## Scope 2: TourInput Anchor + Visit Modes

**What:** Extend `src/tour/contract.TourInput` with `anchor_poi_id: str` (required), `optional_pois: list[str]` (≤2), `visit_modes: dict[str, Literal["walk_past", "stop_visit"]]`. Thread through `src/tour/selection.select_route()`: the anchor is a forced inclusion using matrix-backed walking-time budget math (from Scope 1); optional sites are scored as preferred candidates within their detour budget; `visit_modes` modify per-stop dwell time. Raise `AnchorInfeasibleError(min_required_min, budget_min)` when the anchor cannot fit within `time_budget_min`. All 88 prior tests remain green (defaults preserve existing behavior); add new tests for the three field behaviors and the infeasibility raise.

**Acceptance criteria:** None directly (AC-4's HTTP test lives in Scope 3; AC-5's full surfacing lives in Scope 3). This scope satisfies the algorithm-level prerequisites for both.

**Depends on:** Scope 1 (uses `distance.walking_time()` for budget math).

**Verification commands:**
```bash
# New algorithm-level tests pass
make test-unit -k 'tour_selection and (anchor or optional or visit_mode or infeasible)' 2>&1 | tail -3   # 0 failed, 0 skipped

# CLI end-to-end with new fields
python scripts/tour_build.py --start 48.8676,2.3214 --duration 180 --lenses dark_history,historic_arch \
  --anchor notre-dame-cathedral --optional sainte-chapelle --visit-mode notre-dame-cathedral=stop_visit \
  | jq '.stops[] | select(.poi_id == "notre-dame-cathedral")'   # anchor present in stops

# Infeasibility raises with diagnostic
python scripts/tour_build.py --start 48.8676,2.3214 --duration 30 --anchor arc-de-triomphe 2>&1 \
  | grep 'anchor_infeasible.*min_required'   # diagnostic in output
```

**Estimated sessions:** 2.

---

## Scope 3: Tour-Build HTTP API

**What:** Add `POST /tours/plan-route` and `POST /tours/build-script` to `src/api/routes/tours.py` (new file), mounted at the existing FastAPI router. Pydantic input validation (lat/lng bounds, anchor POI existence in corpus, lens whitelist, time-budget bounds) at the boundary. Routes call `select_route → select_poi_beats → generate` from `src/tour/`. Map `AnchorInfeasibleError` to a 422 response with the spec's diagnostic body. Compute `thinness_signal` from the audio plan (any stop's `total_audio_sec` below its importance-tier floor). Add lightweight `GET /pois?city=paris` returning `{id, name, lat, lng}` for the harness's anchor picker (Paris corpus is ~500 POIs — single un-paginated response is fine). CORS allows the harness origin.

**Acceptance criteria:** AC-1, AC-2, AC-4, AC-5.

**Depends on:** Scope 2 (consumes extended TourInput); Scope 1 transitively.

**Verification commands:**
```bash
# All four ACs verified by API tests
make test 2>&1 | grep -E '(test_tours_api|test_pois_api)' | tail -10

# Smoke against running API
make api-up & sleep 3
curl -fsS -X POST http://localhost:8000/tours/plan-route -H 'content-type: application/json' \
  -d @specs/2026-06-02-tour-build-harness/02-spec-example.json:plan_route_request \
  | jq '.stops[] | select(.poi_id == "notre-dame-cathedral") | .role'   # "anchor"

# Infeasibility returns 422 with body shape from spec
curl -sS -o /dev/null -w '%{http_code}' -X POST http://localhost:8000/tours/plan-route \
  -d '{"city_slug":"paris","start":{"lat":48.8676,"lng":2.3214},"time_budget_min":30,"lenses":["dark_history"],"anchor_poi_id":"arc-de-triomphe","optional_pois":[],"visit_modes":{}}'   # 422
```

**Estimated sessions:** 2.

---

## Scope 4: HTML Test Harness

**What:** New `frontend/tour-tester.html` (single-file, Leaflet + vanilla JS following the pattern in `frontend/viewer.html`). UI elements: Paris map centered on Île de la Cité; draggable green "start" pin; lens multi-select (16 canonical lenses); time-budget slider [30, 600]; anchor-POI search-and-pick (typeahead against `GET /pois?city=paris`); optional-POI picker (≤2); visit-mode toggle per chosen POI. Two CTAs: **"Plan route"** → calls `/tours/plan-route`, renders stops as numbered Leaflet markers, draws OSRM polylines from `segments[].polyline`, shows header with `algorithm_estimate_min` vs. `real_walking_min` + percent delta; **"Build script"** → calls `/tours/build-script` with the planned route, reveals per-stop script text in a side panel (collapsed by default, expand per stop). Second draggable red "simulated user" pin, read-only, displays nearest stop + distance-in-meters in real time (no audio firing).

**Acceptance criteria:** AC-7.

**Depends on:** Scope 3.

**Verification commands:**
```bash
# Manual browser verification — automation is overkill for a single-file dev tool
make api-up &
make frontend-up &
open http://localhost:8001/tour-tester.html
# Drop start pin in Paris; pick anchor "Notre-Dame Cathedral"; select dark_history; 180 min budget.
# Click "Plan route" → 8 stops appear, OSRM polylines visible, header shows delta.
# Click "Build script" → script reveals per stop, Conciergerie's text matches example.
# Drag red simulated-user pin → nearest stop + distance updates in header.

# Lint check on the new HTML/JS (avoid stray console.errors)
node -e "console.log('ok')"   # placeholder if no JS lint configured yet
```

**Estimated sessions:** 2.

---

## Implementation order and rationale

1. **Scope 1 first** — Distance infrastructure is the foundation. Doing TourInput anchor-forcing on top of haversine math means the anchor-test baselines get re-baselined twice (once for the algorithm change, once when real OSRM lands). One baseline pass is enough.
2. **Scope 2 second** — Algorithm changes consume Scope 1's distance layer. Confined to `src/tour/`; no HTTP surface yet.
3. **Scope 3 third** — Exposes the algorithm over HTTP with input validation, error mapping, and the audio-side `thinness_signal`. Closes the four behavioral ACs.
4. **Scope 4 last** — HTML harness consumes the endpoints. No algorithm risk; pure presentation.

Each commit is independently shippable: Scope 1 ships better walking-time accuracy to the CLI; Scope 2 adds anchor semantics to the CLI; Scope 3 makes both available over HTTP; Scope 4 makes them user-testable.

---

**Approval gate:** Confirm scope slicing before `/red-team` (Stage 4).
