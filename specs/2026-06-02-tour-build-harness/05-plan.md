# 05 — Implementation Plan: Tour-Build Harness

> **Date:** 2026-06-02 · **Stage:** 5 (Plan) · **Thinking mode:** Implementation engineer
>
> Per-scope task breakdown, test definitions, and self-contained Claude Code prompts. Each scope = one commit. Each Part C prompt is paste-ready into a fresh `/clear` session.

---

## Code-reality notes (read before any scope)

Items the spec describes that already exist in `src/tour/` — do not invent parallel concepts:

- **`Sentence`** (`src/tour/contract.py:201`) already has `source_id: str` and `source_type: Literal["beat", "glue", "arith"]`. No new `glue_id` field — the spec's `{source_type, source_id}` lands on the existing model. Glue category whitelist: `GLUE_NAV`, `GLUE_STAGING`, `GLUE_PACING`, `GLUE_CALLBACK`, `ARITH`, `GLUE_CLOSING`, `SYNTHESIZED_OPENER` (`glue_client.py:52`).
- **`MockGlueClient`** (`glue_client.py:62`) is already a deterministic test double. `glue_mode: "mock"` query param in Scope 3 just selects it.
- **`POI.tier`** (`contract.py:54`) — spec calls it `tier`, not `importance_tier`. Naming aligned in the contract.
- **`Route.pois`/`Route.transits`** (`contract.py:159–160`) — spec calls these `stops`/`segments`. Renamed at the API serializer boundary, not in `src/tour/`.
- **`TourInput`** is frozen (`extra="forbid"`); new fields must extend the class, with defaults that preserve current behavior for existing callers.
- **`routing.py`** constants `PACE_KMH=3.0`, `HAVERSINE_CORRECTION=1.35` (`routing.py:29–30`). `pace_corrected_walk_seconds()` is the single swap point — keep haversine as fallback.
- **`compute_dwell_seconds(tier)`** (`routing.py:95`) is per-tier; `visit_mode` adds a multiplier layer on top, doesn't replace it.
- **`src/api/app.py:78–84`** mounts routers under `/api/v1/`. Our endpoints land at `/api/v1/tours/plan-route`, `/api/v1/tours/build-script`, `/api/v1/pois`.
- **`make api`** exists at port 8000. No new make target needed for API; harness verification uses it.

---

# SCOPE 1 — Production Routing Infrastructure

**Goal:** Replace haversine × 1.35 walking-time math with a production three-tier chain (matrix → live OSRM → haversine fallback), backed by self-hosted OSRM and a precomputed Paris POI-to-POI distance matrix.

**Branch suggestion:** `scope-1-routing-infra`

## Part A — Task Breakdown

### Task 1.1 — OSRM Docker container + make targets

- **Files:** `docker-compose.osrm.yml` (new), `Makefile`, `Docs/Markdown Docs/TROUBLESHOOTING.md`
- **What to do:**
  - Add an `osrm` service to a new `docker-compose.osrm.yml` (keep separate from the Neo4j compose so OSRM can be started independently). Image `osrm/osrm-backend:latest`. Bind to `127.0.0.1:5000:5000` (NOT `0.0.0.0`).
  - Add make targets: `osrm-up` (compose up + healthcheck loop until `curl -fsS http://localhost:5000/route/v1/foot/2.34,48.85;2.35,48.86` returns 200, with 60s timeout), `osrm-down` (compose down), `osrm-status` (healthcheck only).
  - First-run instructions in TROUBLESHOOTING.md: download Île-de-France OSM extract, run `osrm-extract -p foot.lua` + `osrm-partition` + `osrm-customize` once. Pin the OSM extract version (date) so reruns are reproducible.
  - Use the `foot` profile.
- **What NOT to touch:** any existing Neo4j make target or compose file.
- **Success check:** `make osrm-up && curl -fsS 'http://localhost:5000/route/v1/foot/2.3214,48.8676;2.3499,48.8530' | jq -e '.code == "Ok"'` exits 0.

### Task 1.2 — `src/tour/distance.py` three-tier abstraction

- **Files:** `src/tour/distance.py` (new), `src/tour/distance_matrix.py` (new, may consolidate)
- **What to do:**
  - Module exposes `walking_time(a: Point, b: Point) → int` (seconds) and `walking_polyline(a: Point, b: Point) → list[tuple[float, float]]` plus `walking_distance_m(a, b) → float`.
  - `Point = tuple[float, float]` or `tuple[float, float, str | None]` where the optional third element is a POI ID (enables matrix lookup).
  - Three-tier resolution per call: (1) if both points carry POI IDs and both are in the loaded matrix → matrix lookup; (2) else → live OSRM call with retry-once; (3) else (OSRM unreachable) → haversine + `pace_corrected_walk_seconds` fallback. Each tier increments a counter exposed via `get_counters() → dict`.
  - LRU cache on live-OSRM calls keyed by `(round(lat1, 5), round(lng1, 5), round(lat2, 5), round(lng2, 5))`, max 1024 entries, TTL 1h. Use `cachetools.TTLCache`.
  - Log fallback events at WARNING level. **PII-safe:** when a point has no POI ID, log only the `nearest_poi_id` (computed via a quick matrix scan) plus a 100m-bucketed coord hash. Never log raw lat/lng.
- **What NOT to touch:** `routing.py` (handled in Task 1.4); `selection.py`.
- **Success check:** unit tests in 1.7 pass for each tier path.

### Task 1.3 — Matrix builder

- **Files:** `scripts/build_distance_matrix.py` (new), `Makefile`
- **What to do:**
  - Reads all POIs for a city from Neo4j (`MATCH (p:POI) WHERE p.city_slug = $city RETURN p.id, p.lat, p.lng`).
  - For each ordered pair `(i, j)` with `i < j`, calls live OSRM `/route/v1/foot/...` to get `distance_m` and `duration_sec`. Symmetric storage: write both `(i, j)` and `(j, i)` rows.
  - Output format: SQLite file at `data/paris/distance_matrix.sqlite` with table `pairs(from_poi_id TEXT, to_poi_id TEXT, distance_m REAL, duration_sec INTEGER, PRIMARY KEY (from_poi_id, to_poi_id))`. Also writes a small `meta(corpus_version_hash, built_at_iso, osm_extract_date, pair_count)` table.
  - Retry policy: 3 attempts per pair with exponential backoff. Pairs that fail all retries are logged and inserted with `distance_m = -1, duration_sec = -1` (sentinel); `distance.py` treats sentinel as "miss" and falls through to live OSRM.
  - Add `matrix-build` make target: `python scripts/build_distance_matrix.py paris`.
  - Add `matrix-rebuild` target: same as `matrix-build` but with a confirmation prompt and an `OSRM healthcheck → fail fast if down` pre-check.
- **What NOT to touch:** corpus upload pipeline, Neo4j schema.
- **Success check:** `make matrix-build paris` completes; SQLite file exists; `select count(*) from pairs` ≥ 50000 for Paris.

### Task 1.4 — Swap `routing.py` walking-time math

- **Files:** `src/tour/routing.py`
- **What to do:**
  - Inside `pace_corrected_walk_seconds()`, retain the haversine math as the explicit fallback path. Add an optional `from_poi_id`/`to_poi_id` parameter pair; when provided, delegate to `distance.walking_time(...)`. When not provided (arbitrary points, no POI IDs), keep haversine direct — distance.py also falls through to this for unknown points.
  - `summarise_route()` should pass POI IDs (`prev_id`, `poi.id`) when calling `pace_corrected_walk_seconds()` so segments between known POIs hit the matrix.
  - Add `os.environ.get("TOUR_DISTANCE_MODE", "auto")` toggle: `"auto"` (default, three-tier), `"haversine"` (force fallback, for fast tests), `"live"` (skip matrix). Document in module docstring.
- **What NOT to touch:** `selection.py`, `beat_select.py`.
- **Success check:** `TOUR_DISTANCE_MODE=haversine pytest -k routing` matches pre-change numbers exactly (proves haversine path unchanged).

### Task 1.5 — Re-baseline 88 existing tour tests

- **Files:** `tests/test_tour_routing.py`, `tests/test_tour_selection.py`, `tests/test_tour_beat_select.py`, `tests/test_tour_density.py`, `tests/test_tour_golden_ile.py`, `tests/test_tour_golden_pdv.py`, plus any other `test_tour_*.py` that pins numeric values.
- **What to do:**
  - **First**, before touching expected values: grep every numeric assertion in those files and produce a list (`grep -nE '(assert.*[<>=][0-9]+|approx\([0-9])' tests/test_tour_*.py`). Save to `specs/2026-06-02-tour-build-harness/SCOPE1-baseline-grep.txt`.
  - For each assertion, classify: (a) **structural** (e.g., `len(pois) >= 3` — keep); (b) **range bound** (e.g., `200 < walk_sec < 400` — must justify in PR or tighten); (c) **exact value** (e.g., `walk_sec == 287` — rebase against real OSRM numbers).
  - Re-run `make matrix-build paris` first (Task 1.3 must be done).
  - Run `pytest tests/test_tour_*.py -v` with `TOUR_DISTANCE_MODE=auto`. For every failing exact-value assertion, replace with the new value, append `# rebased 2026-06-02: OSRM real-walk` comment.
  - PR description must list every range-bound retained with one-line justification.
- **What NOT to touch:** test logic (only expected values).
- **Success check:** `make test-unit` passes; ZERO skipped tests; range bounds documented.

### Task 1.6 — Distance counters + Paris smoke routes

- **Files:** `tests/test_tour_distance.py` (new), `scripts/distance_smoke.py` (new)
- **What to do:**
  - Add `get_counters()` to `distance.py` exposing `{matrix_hit, live_osrm, fallback}` counts.
  - Add `tests/test_tour_distance.py` covering AC-3 (a/b/c) + AC-6 (matrix lookup p99 < 1ms): 5 unit tests minimum.
  - Add `scripts/distance_smoke.py` that runs five canonical Paris routes (Concorde→Notre-Dame; Sacré-Cœur→Pigalle; Marais center→Panthéon; Louvre courtyard internal; Pont Neuf crossing) through `walking_time()` and prints expected-vs-actual bands. Routes with >25% deviation from a hardcoded ground-truth Google-Maps-walking number print a YELLOW warning.
- **What NOT to touch:** algorithm code.
- **Success check:** `pytest tests/test_tour_distance.py -v` passes; `python scripts/distance_smoke.py` exits 0.

### Task 1.7 — Matrix loader + degraded-mode startup

- **Files:** `src/tour/distance.py` (extend), `src/api/app.py`
- **What to do:**
  - `distance.load_matrix(city: str) → MatrixHandle | None`. On file-missing, return None + WARNING log; do not raise.
  - In `src/api/app.py` lifespan, call `load_matrix("paris")` at startup. Store handle on `app.state.distance_matrix`. If None, log "API starting in degraded routing mode."
  - Startup time check: matrix-load + 1000 random lookups complete in < 5s total (logged at startup).
- **What NOT to touch:** route handlers (Scope 3 territory).
- **Success check:** API starts cleanly whether matrix exists or not. Startup log shows `matrix_pairs_loaded` count or "degraded".

### Task 1.8 — Lint, full test, PR

- Run `make format && make lint` — zero errors.
- Run `make test` — full suite green including re-baselined tests.

## Part B — Test Definitions (Scope 1)

| Test | Type | AC | Expected |
|------|------|-----|----------|
| `test_walking_time_three_tier_resolution` | unit | AC-3 | Mocked matrix-hit, live-OSRM-hit, haversine-fallback paths each route correctly; counter incremented. |
| `test_osrm_down_falls_back_to_haversine` | unit | AC-3a | With `requests.post` patched to raise ConnectionError, `walking_time(arbitrary_a, arbitrary_b)` returns a haversine value; WARNING logged. |
| `test_matrix_missing_falls_back_to_osrm` | unit | AC-3b | `load_matrix()` returns None; `walking_time(poi_a, poi_b)` falls to live OSRM. |
| `test_all_down_haversine` | unit | AC-3c | Matrix None + OSRM unreachable → haversine value returned + log emitted; route still constructs. |
| `test_matrix_lookup_p99_under_1ms` | perf-unit | AC-6 | timeit 10k lookups; assert p99 < 1ms wallclock. |
| `test_pii_safe_logging` | unit | SECURITY §7 | Patch logger; call `walking_time((48.87, 2.32), (48.85, 2.34))` with no POI IDs; assert no log message contains the raw float values. |
| `test_lru_cache_polyline` | unit | perf-best-practice | Second identical `walking_polyline()` call doesn't hit OSRM (mock `requests` count). |
| `test_route_summary_with_real_osrm` | integration | AC-8 | With OSRM up + matrix loaded, `summarise_route()` returns walk_seconds within 10% of a known Google-Maps ground truth for Concorde→Notre-Dame. |

## Part C — Claude Code Prompt (Scope 1)

```
You are implementing Scope 1 of `specs/2026-06-02-tour-build-harness/`: production routing infrastructure for the Ondoway tour-builder.

## Goal
Replace the haversine × 1.35 walking-time fudge with a three-tier resolution chain (precomputed matrix → live OSRM → haversine fallback), backed by a self-hosted OSRM container and a SQLite distance matrix for the Paris POI corpus. Re-baseline the 88 existing tour tests against the new (more accurate) numbers.

## Stack context
- Python 3.11+ via uv (NEVER pip install). Existing deps in pyproject.toml.
- FastAPI app at `src/api/app.py:27`; lifespan startup at line 20.
- Tour algorithm in `src/tour/`: `routing.py` constants `PACE_KMH=3.0`, `HAVERSINE_CORRECTION=1.35`; `pace_corrected_walk_seconds()` at line 57 is the single swap point — keep haversine as the documented fallback.
- 88 tour tests in `tests/test_tour_*.py`. `tests/test_tour_routing.py`, `tests/test_tour_selection.py`, the two golden tests (`tests/test_tour_golden_ile.py`, `tests/test_tour_golden_pdv.py`) pin numeric walk seconds and will need re-baselining.
- Makefile has `make api` (port 8000), `make test`, `make lint`, `make format`. NO existing `osrm-*` or `matrix-*` targets — you add them.
- Existing Neo4j compose lives separately; add OSRM as a new `docker-compose.osrm.yml`. Bind OSRM to `127.0.0.1:5000:5000` (security: do not expose to 0.0.0.0).

## Tasks (do in order)
1. **Add OSRM Docker + make targets** (`docker-compose.osrm.yml`, `Makefile`). Image `osrm/osrm-backend:latest`. Foot profile. Make targets: `osrm-up` (with healthcheck loop), `osrm-down`, `osrm-status`. First-run setup (osrm-extract/-partition/-customize) documented in `Docs/Markdown Docs/TROUBLESHOOTING.md`.
2. **Create `src/tour/distance.py`** with `walking_time(a, b) → int`, `walking_polyline(a, b) → list[tuple[float, float]]`, `walking_distance_m(a, b) → float`, `get_counters() → dict`. Point type accepts an optional POI ID for matrix lookup. Three-tier resolution: matrix → live OSRM (retry once) → haversine. LRU TTLCache (1024 entries, 1h) on live calls. WARNING logs on fallback are **PII-safe** — never log raw lat/lng for arbitrary points; log `nearest_poi_id` + bucketed-coord-hash instead.
3. **Add `scripts/build_distance_matrix.py`** that queries all `paris` POIs from Neo4j, calls live OSRM for every ordered pair, writes SQLite to `data/paris/distance_matrix.sqlite` with tables `pairs(from_poi_id, to_poi_id, distance_m, duration_sec)` and `meta(corpus_version_hash, built_at_iso, osm_extract_date, pair_count)`. Retry 3× per pair; failed pairs get sentinel `-1` values. Add `make matrix-build` and `make matrix-rebuild` targets.
4. **Swap `routing.py:pace_corrected_walk_seconds()`** to optionally delegate to `distance.walking_time()` when called with POI IDs. `summarise_route()` passes POI IDs. Add `TOUR_DISTANCE_MODE` env var (`auto` | `haversine` | `live`). The haversine path stays identical when `TOUR_DISTANCE_MODE=haversine`.
5. **Re-baseline 88 tests.** Grep numeric assertions first; save list to `specs/2026-06-02-tour-build-harness/SCOPE1-baseline-grep.txt`. Classify each: structural (keep), range bound (justify in PR), exact value (rebase). Run `make matrix-build paris`, then `make test-unit` with `TOUR_DISTANCE_MODE=auto`. Fix failing exact-value assertions, comment `# rebased 2026-06-02: OSRM real-walk`. PR description lists every range bound retained with justification.
6. **Add `tests/test_tour_distance.py`** with 5 unit tests covering three-tier paths, OSRM-down/matrix-missing/both-down, PII-safe logging, LRU caching. Plus `test_matrix_lookup_p99_under_1ms` measuring with `timeit` over 10k iterations.
7. **Matrix loader + degraded startup** in `src/api/app.py` lifespan: `distance.load_matrix("paris")` → `app.state.distance_matrix`. On file-missing, log "degraded routing mode" and proceed (API still starts). Startup logs `matrix_pairs_loaded` count or "degraded" status.
8. **Add `scripts/distance_smoke.py`** that runs 5 canonical Paris routes through `walking_time()` and prints expected-vs-actual against hardcoded Google-Maps ground truth; flag >25% deviation.

## Do NOT
- Touch `src/tour/selection.py` or `src/tour/beat_select.py` (Scope 2/3 territory).
- Modify any test logic — only expected values, only where needed.
- Expose OSRM on `0.0.0.0` — must be `127.0.0.1:5000:5000`.
- Use the public OSRM demo server (`router.project-osrm.org`) anywhere in production code. Tests may mock with that URL pattern.
- Skip the PR-description range-bound justification step — that's how we catch silent test shifts.
- Use `import requests` for OSRM calls if `httpx` is already a dep — check pyproject.toml first.

## Verification commands (from `03-scopes.md`, with red-team fixes)
```bash
make osrm-up && curl -fsS 'http://localhost:5000/route/v1/foot/2.3214,48.8676;2.3499,48.8530' | jq -e '.code == "Ok"'
make matrix-build paris && python -c "from src.tour.distance import load_matrix; m = load_matrix('paris'); print(f'pairs={len(m)} mem_mb={m.memory_mb()}')"
make test && echo OK   # full bar — 88 re-baselined + new distance-layer tests; 0 failed, 0 skipped
TOUR_DISTANCE_MODE=haversine pytest -k routing --co -q | wc -l   # confirm collection > 0 (false-green guard)
make osrm-down && python -c "from src.tour.distance import walking_time; print(walking_time((48.8676,2.3214,'a'),(48.8530,2.3499,'b')))" 2>&1 | grep -i 'WARNING.*fallback'
python scripts/distance_smoke.py   # 5 routes, exit 0
```

## Best practices to enforce
- SECURITY §7 (logging): PII-safe coord handling — see Task 1.2 logging spec.
- SECURITY §12 (network): OSRM bound to `127.0.0.1` only.
- Performance: LRU TTL cache on live OSRM polyline fetches; matrix lookup must measure p99 < 1ms.
- Ruff rules: line ≤100, modern Python (`str | None`, `list[str]`), no mutable defaults, no bare except.
- Run `make format && make lint` after every task; ZERO lint errors before commit.

Before starting, confirm you understand the full scope and flag any conflicts with the existing codebase or assumptions you are making. If `pyproject.toml` doesn't already include `cachetools` and `httpx`, propose adding them via `uv add` before Task 1.2.
```

---

# SCOPE 2 — TourInput Anchor + Visit Modes

**Goal:** Extend the algorithm contract to accept a required anchor POI, ≤2 optional sites, and per-POI visit modes. Make `walk_past` vs `stop_visit` functionally meaningful in selection/beat math. Surface infeasibility with a clear diagnostic.

**Branch suggestion:** `scope-2-tourinput-extension`

## Part A — Task Breakdown

### Task 2.1 — Extend `TourInput` contract

- **Files:** `src/tour/contract.py`
- **What:** Add three fields with defaults that preserve existing behavior:
  - `anchor_poi_id: str | None = None` (required at API boundary, optional at contract level so existing tests keep working)
  - `optional_pois: tuple[str, ...] = ()` (≤2 enforced by validator)
  - `visit_modes: dict[str, Literal["walk_past", "stop_visit"]] = Field(default_factory=dict)` (frozen via `Mapping` semantics — write a `@field_validator` that converts dict → frozendict-equivalent tuple-of-tuples for hashability since the model is frozen)
- Add `@field_validator` for `optional_pois` (≤2, dedup, no overlap with `anchor_poi_id`) and for `visit_modes` (keys must be subset of `{anchor_poi_id} ∪ optional_pois`).
- **NOT:** API model — that's Scope 3.
- **Success:** existing 88 tests pass with no changes (defaults preserve behavior).

### Task 2.2 — `AnchorInfeasibleError` + feasibility check

- **Files:** `src/tour/selection.py`, `src/tour/contract.py` (or new `src/tour/exceptions.py`)
- **What:** Define `AnchorInfeasibleError(min_required_min: int, budget_min: int)` as a dataclass-style exception. At the top of `select_route()`, when `anchor_poi_id` is set, compute minimum round-trip walking time from `start → anchor → start` using `distance.walking_time()`. If this exceeds `time_budget_min * 0.83` (err-short), raise.
- **NOT:** HTTP-level mapping (Scope 3).
- **Success:** `test_anchor_infeasible_raises_with_diagnostic` passes.

### Task 2.3 — Anchor forced-inclusion in `select_route()`

- **Files:** `src/tour/selection.py`
- **What:** When `anchor_poi_id` is set, the anchor is pinned into the route before greedy fill. Treat it as the route's geographic centroid: greedy spine_area selection re-roots around it; budget math subtracts the start→anchor→nearest-return cost before opening greedy fills. Mark the anchor's POI record with a derived flag `is_user_anchor=True` for serializer use in Scope 3.
- **NOT:** changes to the scoring formula for non-anchor POIs.
- **Success:** `test_anchor_always_in_route` + `test_anchor_uses_distance_matrix_when_loaded` pass.

### Task 2.4 — Optional sites scoring boost

- **Files:** `src/tour/selection.py`
- **What:** During greedy candidate scoring, add a positive bias for POIs in `optional_pois` proportional to `INTEREST_BIAS`. If an optional site can't fit within its detour budget (3-10 min added walking per rule E3), surface it via a new `Route.optional_unreached: tuple[str, ...]` field rather than silently dropping. (Adds a contract field to `Route` — minor.)
- **NOT:** UI for the user to accept/reject — that's harness territory.
- **Success:** `test_optional_sites_score_boost` + `test_optional_unreached_surfaced` pass.

### Task 2.5 — Visit mode dwell + beat filter behavior

- **Files:** `src/tour/routing.py`, `src/tour/beat_select.py`
- **What:** Define dwell semantics:
  - `stop_visit`: dwell = `compute_dwell_seconds(tier)` (unchanged tier-default).
  - `walk_past`: dwell = `min(60, compute_dwell_seconds(tier))`; **plus** `beat_select` filters this POI's beat candidates to those with `narrative_function ∈ {"establishing", "transition"}` (no deepen/climax — walker doesn't stop long enough).
- Add `compute_dwell_seconds_for_visit_mode(tier: int, visit_mode: str | None) → int` helper.
- **NOT:** propagating visit_mode into the audio script wording.
- **Success:** `test_walk_past_clamps_dwell` + `test_walk_past_filters_long_form_beats` pass.

### Task 2.6 — Update `scripts/tour_build.py` CLI

- **Files:** `scripts/tour_build.py`
- **What:** Extend argparse with `--anchor POI_ID` (required when running anchor mode), `--optional POI_ID` (action=append, max 2), `--visit-mode KEY=VALUE` (action=append, parses `key=value` pairs into a dict). Keep all existing flags working unchanged — additive only.
- **NOT:** changing the script's output shape; that's still `Script` JSON.
- **Success:** `python scripts/tour_build.py --start 48.8676,2.3214 --duration 180 --lenses dark_history --anchor notre-dame-cathedral --optional sainte-chapelle --visit-mode notre-dame-cathedral=stop_visit | jq '.selected_pois | length' > 0` runs end-to-end.

### Task 2.7 — New tests for Scope 2 behaviors

- **Files:** `tests/test_tour_selection.py` (extend), `tests/test_tour_anchor.py` (new), `tests/test_tour_visit_mode.py` (new)
- **What:** Add 6 tests covering anchor inclusion, optional scoring, walk-past clamping, beat filtering, infeasibility raise, and CLI smoke. See Part B for full list.
- **Success:** `pytest tests/test_tour_anchor.py tests/test_tour_visit_mode.py -v` passes; full `make test` still green.

## Part B — Test Definitions (Scope 2)

| Test | Type | Expected |
|------|------|----------|
| `test_tour_input_anchor_default_none_preserves_behavior` | unit | Existing TourInput-construction tests pass without changes. |
| `test_tour_input_optional_pois_max_2_enforced` | unit | Pydantic raises on 3 optional sites. |
| `test_tour_input_visit_modes_key_subset_validator` | unit | Pydantic raises when `visit_modes` key not in `{anchor} ∪ optional`. |
| `test_anchor_always_in_route` | unit | `select_route()` with `anchor_poi_id` set returns Route whose `pois[].id` includes anchor. |
| `test_anchor_infeasible_raises_with_diagnostic` | unit | Anchor too far + 30-min budget → `AnchorInfeasibleError(min_required_min, budget_min)` raised. |
| `test_optional_sites_score_boost` | unit | A T3 POI in `optional_pois` is selected when a higher-score T3 POI without optional flag would have been picked. |
| `test_optional_unreached_surfaced` | unit | An optional site requiring 12-min detour is in `Route.optional_unreached`. |
| `test_walk_past_clamps_dwell` | unit | `compute_dwell_seconds_for_visit_mode(5, "walk_past") == 60`. |
| `test_walk_past_filters_long_form_beats` | unit | At a walk_past anchor, only `establishing`/`transition` beats are selected (no `deepen`/`climax`). |
| `test_cli_anchor_flag_end_to_end` | integration | CLI smoke from Part A Task 2.6 success check. |

## Part C — Claude Code Prompt (Scope 2)

```
You are implementing Scope 2 of `specs/2026-06-02-tour-build-harness/`: extending the tour-builder's TourInput contract and selection algorithm to accept a required anchor POI, optional sites, and per-POI visit modes — making walk_past vs stop_visit functionally meaningful.

## Goal
After this scope, `select_route()` accepts a forced-inclusion anchor, scoring boosts for optional sites, and dwell/beat-filter behavior keyed on visit mode. Infeasibility (anchor unreachable in time budget) raises a clear typed exception. CLI exposes the new fields.

## Prerequisite
Scope 1 must be merged (`distance.walking_time()` available). If `src/tour/distance.py` doesn't exist, STOP and flag — you cannot do this work without it.

## Stack context
- `TourInput` (`src/tour/contract.py:15`) is `frozen=True, extra="forbid"`. Add fields with defaults that preserve existing behavior — 88 tests must still pass unchanged.
- `Sentence.source_type` already exists with the right literal values — no related changes needed here.
- `select_route()` entry: `src/tour/selection.py:424`. The function loads a CorpusSnapshot and runs a greedy with insertion-cost scoring. `INTEREST_BIAS` constant exists; reuse for the optional-poi boost.
- `compute_dwell_seconds(tier)` at `routing.py:95` is per-tier default. Visit mode multiplies on top, doesn't replace.
- `narrative_function` is a field on `BeatRef` (`contract.py:93`); known values include `establishing`, `transition`, `deepen`, `climax`, `hook`.
- CLI `scripts/tour_build.py:215-232` parses `--start, --duration, --lenses, --round-trip, --theme, --city-slug`. Extend additively.
- Tests: existing `tests/test_tour_selection.py` patterns — `from src.tour.fixtures import build_test_snapshot` is the standard test setup.

## Tasks (in order)
1. **Extend `TourInput`**: add `anchor_poi_id: str | None = None`, `optional_pois: tuple[str, ...] = ()` (≤2, deduped, not overlapping anchor), `visit_modes: dict[str, Literal["walk_past", "stop_visit"]] = Field(default_factory=dict)` (keys must be ⊆ {anchor} ∪ optional). Add Pydantic validators for the constraints.
2. **Define `AnchorInfeasibleError`** in `src/tour/exceptions.py` (new module) as a dataclass-style exception carrying `min_required_min: int, budget_min: int`. At the top of `select_route()`, when `anchor_poi_id` is set, compute `start → anchor → start` round-trip time via `distance.walking_time()`. If > `time_budget_min × 0.83`, raise.
3. **Force-include anchor** in `select_route()`: pin the anchor into the route before greedy fill. Re-root spine_area selection around the anchor. Subtract start→anchor→nearest-return cost from greedy's walk budget. Mark anchor's POI record with a flag (`is_user_anchor=True`) that survives into the Route output — extend POI with this optional field if needed.
4. **Optional sites scoring**: during greedy candidate scoring, add `INTEREST_BIAS` boost for POIs in `optional_pois`. If an optional site can't fit (detour ≥ 10 min added per rule E3), append its ID to a new `Route.optional_unreached: tuple[str, ...] = ()` field rather than silently dropping.
5. **Visit-mode dwell + beat behavior**: in `routing.py`, add `compute_dwell_seconds_for_visit_mode(tier, visit_mode) → int` that returns `min(60, compute_dwell_seconds(tier))` for `walk_past`, else `compute_dwell_seconds(tier)`. In `beat_select.py`, when picking beats for a stop with `visit_mode="walk_past"`, filter candidates to `narrative_function ∈ {"establishing", "transition"}` only.
6. **CLI extension** (`scripts/tour_build.py`): add `--anchor`, `--optional` (append, max 2), `--visit-mode KEY=VALUE` (append, parses into dict). Existing flags work unchanged.
7. **Tests**: add 10 new tests per Part B above. Use `tests/test_tour_anchor.py` (new), `tests/test_tour_visit_mode.py` (new), extend `tests/test_tour_selection.py`. All tests must run in <2s each (use small fixtures).

## Do NOT
- Change scoring formula for non-anchor POIs.
- Add HTTP/API code — Scope 3 territory.
- Add new fields to `Sentence` or `Script` (audio side is locked here).
- Mutate `TourInput` callers other than CLI — defaults handle them.
- Skip the false-green guard: every test assertion must be meaningful (no `assert True`).

## Verification commands
```bash
# All algorithm-level tests pass; collection guard prevents false-green
pytest tests/test_tour_anchor.py tests/test_tour_visit_mode.py -v --maxfail=1 && \
  test "$(pytest tests/test_tour_anchor.py tests/test_tour_visit_mode.py --co -q | grep -c 'test_')" -ge 10

# CLI end-to-end smoke
python scripts/tour_build.py --start 48.8676,2.3214 --duration 180 --lenses dark_history,historic_arch \
  --anchor notre-dame-cathedral --optional sainte-chapelle --visit-mode notre-dame-cathedral=stop_visit \
  | jq -e '.selected_pois | map(.id) | index("notre-dame-cathedral") != null'

# Infeasibility raises with diagnostic
python scripts/tour_build.py --start 48.8676,2.3214 --duration 30 --anchor arc-de-triomphe 2>&1 \
  | grep -E 'anchor_infeasible.*min_required.*budget'

# Full suite still green
make test && echo OK
```

## Best practices to enforce
- SECURITY §11: Pydantic validates `optional_pois` ≤ 2, dedup, no anchor overlap, visit_modes key subset.
- Ruff rules: line ≤100, modern Python, no mutable defaults (use `Field(default_factory=...)`).
- `make format && make lint` after every task — ZERO errors before commit.

Before starting, confirm you understand the full scope. Flag if `src/tour/distance.py` (Scope 1 output) isn't present — you cannot do this work without it. Also flag if the existing `INTEREST_BIAS` constant isn't where I claim, or if `BeatRef.narrative_function` enum doesn't include the values I cited.
```

---

# SCOPE 3 — Tour-Build HTTP API

**Goal:** Expose the pipeline over HTTP with two endpoints (`/tours/plan-route`, `/tours/build-script`), plus `/pois` for the harness. Pydantic validation at the boundary, X-Dev-Token auth, rate limit, CORS, and a serializer that translates code names to spec names.

**Branch suggestion:** `scope-3-tour-build-api`

## Part A — Task Breakdown

### Task 3.1 — Pydantic request/response models in `src/api/models/tours.py`

- **Files:** `src/api/models/tours.py` (new)
- **What:** Define `PlanRouteRequest` (Pydantic): `city_slug: str`, `start: dict[str, float]` (with lat/lng), `time_budget_min: int = Field(ge=30, le=600)`, `lenses: list[str]`, `anchor_poi_id: str`, `optional_pois: list[str] = Field(default_factory=list, max_length=2)`, `visit_modes: dict[str, Literal["walk_past", "stop_visit"]]`. Cross-field validators: optional dedup + no-overlap-with-anchor; visit_modes keys ⊆ {anchor} ∪ optional. `BuildScriptRequest` accepts the Route response shape verbatim (use `Route` Pydantic mirror with `model_config = ConfigDict(extra="allow")` to round-trip cleanly). Response models `RouteResponse` and `ScriptPlanResponse` per `02-spec.md`.
- **NOT:** business logic.

### Task 3.2 — `src/api/routes/tours.py` endpoints

- **Files:** `src/api/routes/tours.py` (new)
- **What:** `POST /tours/plan-route` and `POST /tours/build-script`. Mounted at `/api/v1/` in `src/api/app.py`. Endpoints call `select_route → select_poi_beats → generate` from `src/tour/`. Map `AnchorInfeasibleError` → 422 with body `{error: "anchor_infeasible", min_required_min, budget_min}`. Use `Depends(verify_dev_token)` (Task 3.4) and `Depends(get_session)` (existing) and `Depends(get_distance_matrix)` (new, reads from `app.state`).
- **Success:** `pytest tests/test_tours_api.py` passes Part B tests.

### Task 3.3 — API serializer (code names → spec names)

- **Files:** `src/api/serializers/tours.py` (new)
- **What:** Pure functions that translate:
  - `Route(pois, transits, ...)` → `RouteResponse(stops, segments, ...)`
  - Derive `role` per stop from `(is_user_anchor, poi_role, tier)` per B1 rule (anchor / walk_by_only / content / mood_pacing).
  - Compute `lens_density: dict[lens, int]` per stop from `BeatRef.lenses` aggregated over the POI's beats (in-memory pass).
  - Compute `tour_name` post-hoc: dominant_lens = lens with max summed lens_density across chosen stops, excluding `hidden_history`. If all selected lenses are excluded, `tour_name = anchor_name`.
  - `Script.script: tuple[Sentence,...]` (flat) → `per_stop[].beats[]` (grouped by `Sentence.stop_idx`) + `per_segment[].beats[]` (grouped by segment index encoded in `stop_idx` namespace per generation.py convention — confirm during implementation).
  - Compute `total_tour_sec = total_walk_seconds + sum(stop dwell)`; `silence_pct = 1 - total_audio_sec / total_tour_sec`. If `silence_pct < 0.6`, append `"silence_pct_below_floor"` to `warnings[]`.
  - `thinness_signal`: True if any stop's `total_audio_sec` < tier-specific floor (define floors: T5=60s, T4=45s, T3=30s, T2=20s, T1=10s).
- **Success:** Direct unit tests on serializer functions.

### Task 3.4 — `X-Dev-Token` auth dependency

- **Files:** `src/api/auth/dev_token.py` (new), `src/api/routes/tours.py`
- **What:** `verify_dev_token(x_dev_token: str = Header(...)) → None` reads `os.environ["ONDOWAY_DEV_TOKEN"]` and compares constant-time. Missing env var or mismatch → `HTTPException(401, "invalid dev token")`. Used by Depends on `/tours/*`. Document env var in `.env.template`.
- **NOT:** Touch existing auth flow at `src/api/auth/routes.py`.

### Task 3.5 — Rate limit on `/build-script`

- **Files:** `pyproject.toml` (add `slowapi`), `src/api/app.py`, `src/api/routes/tours.py`
- **What:** Install `slowapi`. Add rate-limit middleware. Decorate `/tours/build-script` with `@limiter.limit("10/minute")` (per IP). Document the limit in route docstring + `Docs/Markdown Docs/API_REFERENCE.md`.
- **NOT:** Rate-limit `/plan-route` (no LLM cost there).

### Task 3.6 — `GET /pois` endpoint

- **Files:** `src/api/routes/tours.py`
- **What:** `GET /pois?city=paris` returns `[{id, name, lat, lng, tier}]` for the harness's anchor picker. Cypher: `MATCH (p:POI {city_slug: $city}) RETURN ...`. Cache in-process for 5 min (no LRU TTL needed; small dataset, simple `functools.lru_cache` on a city-keyed snapshot). No auth required on this endpoint (read-only, public corpus data already).
- **NOT:** Pagination, search params — Paris ~500 POIs, single response.

### Task 3.7 — CORS + app wiring

- **Files:** `src/api/app.py`
- **What:** Add `CORSMiddleware` allowing `http://localhost:8001` origin only (no wildcard). Mount `tours.router` with prefix `/api/v1`. Initialize `app.state.distance_matrix` via `distance.load_matrix("paris")` (already in Scope 1's Task 1.7).
- **NOT:** Modify other route mounts.

### Task 3.8 — Endpoint tests

- **Files:** `tests/test_tours_api.py` (new), `tests/test_pois_api.py` (new)
- **What:** Cover AC-1, AC-2, AC-4, AC-5 from Part B. Use FastAPI `TestClient` with `glue_mode=mock` to avoid Haiku calls. Set `ONDOWAY_DEV_TOKEN` in test fixture.

## Part B — Test Definitions (Scope 3)

| Test | Type | AC | Expected |
|------|------|-----|----------|
| `test_plan_route_200_with_anchor_in_stops` | integration | AC-1 | Valid request → 200, response.stops contains anchor_poi_id. |
| `test_build_script_200_round_trip_with_per_stop` | integration | AC-2 | Plan route response POSTed verbatim to /build-script → 200, per_stop length matches stops length, anchor stop has ≥1 beat. |
| `test_anchor_infeasible_422_with_diagnostic` | integration | AC-4 | Anchor unreachable in budget → 422, body `{error, min_required_min, budget_min}`. |
| `test_thin_lens_corpus_thinness_signal_true` | integration | AC-5 | `lenses: ["film_tv"]` → /build-script response has `thinness_signal: true` and at least one stop below tier floor. |
| `test_silence_pct_below_floor_warning` | integration | spec constraint | When script audio is >40% of total_tour_sec, response includes `"silence_pct_below_floor"` in warnings[]. |
| `test_missing_dev_token_401` | integration | SECURITY §3 | Request without X-Dev-Token → 401. |
| `test_rate_limit_build_script_11th_request_429` | integration | SECURITY §7 | 10 successful + 1 limited request inside 60s window. |
| `test_pois_endpoint_returns_paris_corpus` | integration | harness dep | `GET /pois?city=paris` → 200, ≥100 items, each has `{id, name, lat, lng, tier}`. |
| `test_optional_poi_overlap_with_anchor_400` | unit | SECURITY §11 | Anchor in optional_pois → Pydantic 400. |
| `test_visit_modes_key_not_in_anchor_or_optional_400` | unit | SECURITY §11 | visit_modes for non-included POI → 400. |
| `test_cors_localhost_8001_allowed` | integration | SECURITY §13 | Preflight from `http://localhost:8001` → allowed; from `http://evil.com` → blocked. |
| `test_role_derivation_anchor` | unit | B1 fix | User-anchor POI → role="anchor" regardless of tier. |
| `test_tour_name_excludes_hidden_history` | unit | B5 fix | When dominant lens by density is `hidden_history`, falls back to next-highest. |
| `test_tour_name_all_hidden_falls_back_to_anchor` | unit | B5 fix | When user selects only `hidden_history` lenses, tour_name = anchor name alone. |

## Part C — Claude Code Prompt (Scope 3)

```
You are implementing Scope 3 of `specs/2026-06-02-tour-build-harness/`: exposing the tour-builder pipeline over HTTP with two endpoints + a POI listing + X-Dev-Token auth + rate limit + a serializer that translates internal code names to the spec's API contract.

## Goal
After this scope, the harness (Scope 4) can drive the full pipeline via `POST /api/v1/tours/plan-route` → user validates → `POST /api/v1/tours/build-script`, with proper auth, rate-limited LLM calls, and clean error mapping. `GET /api/v1/pois` feeds the anchor picker.

## Prerequisites
- Scope 1 merged: `src/tour/distance.py` exists, matrix loads at startup.
- Scope 2 merged: `TourInput` has `anchor_poi_id`/`optional_pois`/`visit_modes`; `AnchorInfeasibleError` defined in `src/tour/exceptions.py`.
If either is missing, STOP and flag.

## Stack context
- FastAPI app factory: `src/api/app.py:27`. Routers mounted at `/api/v1/` (see `app.include_router` calls at lines 78-85).
- Existing Pydantic models pattern: `src/api/models/trips.py`. Mirror style.
- Existing serializer pattern: none yet — create `src/api/serializers/` as a new package.
- Existing routes pattern: `src/api/routes/trips.py` (Depends, error handling, response_model). Mirror style.
- Auth dependency pattern: existing routes use `Depends(get_session)`. New `Depends(verify_dev_token)` joins it.
- `Sentence.source_type` is `Literal["beat", "glue", "arith"]`. Don't invent new namespaces.
- `Script.script: tuple[Sentence,...]` is flat; group by `Sentence.stop_idx` for `per_stop[]`. For `per_segment[]`, generation.py uses... CONFIRM during implementation by reading `_build_transit` in `src/tour/generation.py:~498`. If the convention is unclear, ask before guessing.
- Existing rate-limit lib: none. Add `slowapi` via `uv add slowapi`.
- Existing CORS: NOT currently configured — add `CORSMiddleware` with allowlist `http://localhost:8001` only.

## Tasks (in order)
1. **Create `src/api/models/tours.py`** with `PlanRouteRequest`, `BuildScriptRequest`, `RouteResponse`, `ScriptPlanResponse` per `specs/2026-06-02-tour-build-harness/02-spec.md` shapes. Pydantic field validators: `time_budget_min: Field(ge=30, le=600)`; `optional_pois`: dedup + no-overlap-with-anchor + max_length=2; `visit_modes` keys ⊆ {anchor} ∪ optional. Lens whitelist enforcement: read canonical lenses from existing config (find via `grep -r 'lens' src/api/models/ | grep -i canonical` first).
2. **Create `src/api/routes/tours.py`** with `POST /tours/plan-route` and `POST /tours/build-script`. Use `Depends(verify_dev_token)` + `Depends(get_session)` + `app.state.distance_matrix`. Map `AnchorInfeasibleError` to 422 with body `{error, min_required_min, budget_min}`. Use `glue_mode` query param to choose `MockGlueClient` (default) or `HaikuGlueClient` for `/build-script`.
3. **Create `src/api/serializers/tours.py`** with pure functions: `to_route_response(route, snapshot)`, `to_script_plan_response(script, route, snapshot)`. Implement field translations per `specs/2026-06-02-tour-build-harness/04-red-team.md` §6 ("What lands in Stage 5"). Compute `role` (B1), `lens_density` (B12), `tour_name` (B5), `total_tour_sec` + `silence_pct` (B6), `thinness_signal` (with tier floors T5=60s, T4=45s, T3=30s, T2=20s, T1=10s). If `silence_pct < 0.6`, append `"silence_pct_below_floor"` to warnings.
4. **Create `src/api/auth/dev_token.py`** with `verify_dev_token(x_dev_token: str = Header(...))` reading `os.environ["ONDOWAY_DEV_TOKEN"]`. Constant-time compare via `secrets.compare_digest`. Missing or wrong → 401. Add var to `.env.template` with a TODO comment to rotate before any non-dev deployment.
5. **Install `slowapi`** (`uv add slowapi`). Initialize `Limiter(key_func=get_remote_address)` in `src/api/app.py`. Decorate `/tours/build-script` with `@limiter.limit("10/minute")`. Document in route docstring + `Docs/Markdown Docs/API_REFERENCE.md`.
6. **Add `GET /pois`** in `src/api/routes/tours.py` (or new `src/api/routes/pois.py` — both fine, keep small). Cypher pulls `id, name, lat, lng, tier` for `MATCH (p:POI {city_slug: $city})`. Cache in-process with `functools.lru_cache(maxsize=4)` (one per city). No auth.
7. **Wire CORS + mount routers** in `src/api/app.py`: add `CORSMiddleware` allowing exactly `["http://localhost:8001"]`. Mount `tours.router` with `prefix="/api/v1"`.
8. **Tests** in `tests/test_tours_api.py` + `tests/test_pois_api.py`. Use FastAPI `TestClient` with `glue_mode=mock` to avoid LLM. Set `ONDOWAY_DEV_TOKEN` via a session-scoped fixture. See Part B for the 14 required tests.

## Do NOT
- Touch `src/api/routes/trips.py` or `src/api/crud/trips.py` — older parallel implementation is out of scope.
- Persist tours to Neo4j — pipeline output is ephemeral JSON.
- Invent `glue_id` field — use `source_type` + `source_id` from existing `Sentence` model.
- Hardcode the dev token; always env-var.
- Loosen CORS to wildcard — strict origin list only.
- Bypass the rate limit in tests via env var; instead, test the limit explicitly with a tight loop.

## Verification commands
```bash
# All endpoint tests pass; collection guard
pytest tests/test_tours_api.py tests/test_pois_api.py -v --maxfail=1
test "$(pytest tests/test_tours_api.py --co -q | grep -c 'test_')" -ge 11

# Smoke against running API
ONDOWAY_DEV_TOKEN=devsecret make api &
sleep 3
jq '.plan_route_request' specs/2026-06-02-tour-build-harness/02-spec-example.json > /tmp/req.json
curl -fsS -X POST http://localhost:8000/api/v1/tours/plan-route \
  -H 'X-Dev-Token: devsecret' -H 'content-type: application/json' \
  -d @/tmp/req.json | jq -e '.stops | map(.poi_id) | index("notre-dame-cathedral") != null'

# Auth gate
curl -sS -o /dev/null -w '%{http_code}' -X POST http://localhost:8000/api/v1/tours/plan-route \
  -d @/tmp/req.json   # expect 401

# Infeasibility
curl -sS -w '\n%{http_code}\n' -X POST http://localhost:8000/api/v1/tours/plan-route \
  -H 'X-Dev-Token: devsecret' -H 'content-type: application/json' \
  -d '{"city_slug":"paris","start":{"lat":48.8676,"lng":2.3214},"time_budget_min":30,"lenses":["dark_history"],"anchor_poi_id":"arc-de-triomphe","optional_pois":[],"visit_modes":{}}' \
  | tail -1 | grep -q 422

# Full suite green
make test && echo OK
```

## Best practices to enforce
- SECURITY §3: every new route Depends on `verify_dev_token` (except `GET /pois` — read-only public data; document the exception in route docstring).
- SECURITY §7: rate limit on `/build-script`; document the per-minute budget.
- SECURITY §11: Pydantic boundary validators per Task 3.1.
- SECURITY §13: CORS allowlist exactly `http://localhost:8001`.
- Performance: `GET /pois` cached in-process; `/plan-route` uses matrix-backed distance.

Before starting, confirm you understand the scope. Flag if `src/tour/distance.py` or `src/tour/exceptions.AnchorInfeasibleError` aren't present (Scope 1/2 not yet merged). Also flag any conflict between the serializer field-translation rules and the actual shapes returned by `select_route()` and `generate()` — read those functions before writing the serializer.
```

---

# SCOPE 4 — HTML Test Harness

**Goal:** A single HTML file that drives the full pipeline, lets the user drop a start pin, validate the route, build the script, and drag a simulated user pin. Plus a Playwright smoke test.

**Branch suggestion:** `scope-4-html-harness`

## Part A — Task Breakdown

### Task 4.1 — Scaffold `frontend/tour-tester.html`

- **Files:** `frontend/tour-tester.html` (new)
- **What:** Single-file HTML. Leaflet via CDN (mirror `frontend/viewer.html` import pattern). Layout: top header (input form + CTAs), main map (full viewport), right side panel (collapsed by default; reveals per-stop script after Build). Vanilla JS, no build step. Dark theme matching viewer.html.
- **Inputs in the header:** lens multi-select (16 canonical lens checkboxes), time-budget slider [30, 600] with displayed value, anchor POI picker (typeahead), optional-POI picker (up to 2 chips), visit-mode toggle per chosen POI (default `stop_visit`), city dropdown (Paris hardcoded for MVP).
- **Map:** centered on Île de la Cité (`48.855, 2.345`), zoom 14. Draggable green "start" pin initialized at Place de la Concorde.

### Task 4.2 — Anchor + optional POI search picker

- **Files:** `frontend/tour-tester.html` (extend)
- **What:** On page load, fetch `GET /api/v1/pois?city=paris` once (no auth). Render as a typeahead component (vanilla JS, no library). User types → filter by name substring → show 5 options → click selects + adds chip. Optional picker capped at 2 chips.

### Task 4.3 — "Plan route" flow + map rendering

- **Files:** `frontend/tour-tester.html` (extend)
- **What:** On "Plan route" click → POST `/api/v1/tours/plan-route` with `X-Dev-Token` from a `window.ONDOWAY_DEV_TOKEN` global (set by the user manually or via URL hash). Render response: numbered stop markers (color by `role`), OSRM polylines from `segments[].polyline`. Header banner shows: `algorithm_estimate_min` vs `real_walking_min` with percent delta in colored badge (green <10%, yellow 10–25%, red >25%).
- **422 error path:** banner with `Required: {min_required_min} min · Budget: {budget_min} min`, plus an "Increase budget to X" button that bumps the slider.

### Task 4.4 — "Build script" flow + per-stop reveal

- **Files:** `frontend/tour-tester.html` (extend)
- **What:** "Build script" CTA enabled only after a successful Plan. POST `/api/v1/tours/build-script?glue_mode=haiku` with the Route response body. On 200: side panel reveals per-stop accordion; click a stop marker → expand its script in the panel. Show `total_audio_sec`, `silence_pct`, `tour_name`, `thinness_signal` (warning badge if true).

### Task 4.5 — Simulated user pin

- **Files:** `frontend/tour-tester.html` (extend)
- **What:** Second draggable red pin labeled "Simulated user." Initial position = first stop. On drag, compute nearest stop by haversine (client-side) over all stops; display "Nearest: {name} · Distance: {m}m" in a small footer overlay. Pure read-only — no audio firing, no state changes.

### Task 4.6 — `make frontend-up` target

- **Files:** `Makefile`
- **What:** Add `frontend-up: python -m http.server 8001 --directory frontend`. Document briefly in `Docs/Markdown Docs/TROUBLESHOOTING.md`.

### Task 4.7 — Playwright smoke test

- **Files:** `tests/test_harness_smoke.py` (new), `pyproject.toml` (add `pytest-playwright`)
- **What:** `uv add --dev pytest-playwright`. Test: launches `make api &` + `make frontend-up &` in a fixture, navigates to `http://localhost:8001/tour-tester.html`, asserts:
  - Lens picker has 16 options
  - Start pin is draggable (has `draggable=true` or Leaflet equivalent attr)
  - Mocked `/tours/plan-route` (use Playwright route interception) → map renders stop markers
  - Header shows the delta badge after a successful plan response
- Skip with `pytest.mark.skipif` when `PLAYWRIGHT_BROWSERS_PATH` env not set (CI gate; local dev opt-in).

### Task 4.8 — Manual verification + screenshots

- **What:** Run the full harness against real `make api` + Scope 1 OSRM + Paris matrix. Drop pin at Place de la Concorde; anchor = Notre-Dame; lenses = dark_history + historic_arch; budget = 180 min. Click Plan route → expect ≈8 stops via Tuileries / Louvre / Pont Neuf / Île de la Cité. Click Build script → per-stop script reveals. Save 3 screenshots to `specs/2026-06-02-tour-build-harness/manual-verify/`.

## Part B — Test Definitions (Scope 4)

| Test | Type | AC | Expected |
|------|------|-----|----------|
| `test_harness_loads_with_lens_options` | playwright | AC-7 | Page loads in <3s; 16 lens checkboxes present. |
| `test_start_pin_draggable` | playwright | AC-7 | Start pin DOM element has draggable affordance; drag-end fires an event handler. |
| `test_plan_route_mock_renders_stops` | playwright | AC-7 | Route-intercept `/tours/plan-route` returns example.json; map shows N stop markers; header shows delta badge. |
| `test_422_banner_shown_on_infeasible` | playwright | spec UX | Route-intercept returns 422; banner renders min_required + Increase-budget button. |
| `test_simulated_user_pin_distance_updates` | playwright | spec UX | Drag simulated pin; footer overlay shows updated nearest stop + meters. |
| `test_manual_paris_concorde_to_notre_dame` | manual | AC-7 | Real run; screenshot in `manual-verify/`. |

## Part C — Claude Code Prompt (Scope 4)

```
You are implementing Scope 4 of `specs/2026-06-02-tour-build-harness/`: a single-file HTML test harness that drives the tour-build pipeline through the API.

## Goal
After this scope, a user can open one HTML page in their browser, drop a start pin in Paris, pick an anchor POI + lenses + time budget, click "Plan route" to see the algorithm's spatial plan rendered on Leaflet with OSRM polylines, click "Build script" to reveal the per-stop script, and drag a "simulated user" pin around the map for read-only proximity inspection. A Playwright smoke test covers the page structure.

## Prerequisites
- Scope 3 merged: API endpoints `/api/v1/tours/plan-route`, `/api/v1/tours/build-script`, `/api/v1/pois` exist.
- A `ONDOWAY_DEV_TOKEN` env var set; harness reads it from `window.ONDOWAY_DEV_TOKEN` (user pastes it into a textbox in the header, or appends `#token=...` to the URL).
- Local Paris distance matrix built (Scope 1's `make matrix-build paris`).
If endpoints don't respond, STOP and flag.

## Stack context
- Existing frontend pattern: `frontend/viewer.html` — single-file Leaflet HTML, dark theme, vanilla JS. Mirror imports and styles for visual consistency.
- 16 canonical lenses: read from `data/paris/poi-raw.json` or via `GET /api/v1/lenses` — find the source via `grep -r '\"dark_history\"' data/ src/ | head -5` first.
- `make api` runs FastAPI on port 8000. No existing `make frontend-up` — you add it.
- Tests use pytest + (new) Playwright. `uv add --dev pytest-playwright` is the install.
- The 02-spec.md JSON example at `specs/2026-06-02-tour-build-harness/02-spec-example.json` is the contract reference for rendering. The harness must handle exactly this shape.

## Tasks (in order)
1. **Scaffold `frontend/tour-tester.html`** — single HTML file, vanilla JS, Leaflet CDN imports per viewer.html. Layout: header with input form + 2 CTAs, fullscreen map, collapsible right side panel. Dark theme. Map center at Île de la Cité, zoom 14. Green "start" pin at Place de la Concorde, draggable.
2. **Anchor + optional POI picker.** On page load, `fetch('/api/v1/pois?city=paris')` once. Typeahead: filter by substring as user types, show top 5, click adds chip. Optional picker capped at 2 chips. Each chip has a visit-mode toggle (`stop_visit` default).
3. **"Plan route" flow.** Build request body from form inputs; POST to `/api/v1/tours/plan-route` with `X-Dev-Token` header from `window.ONDOWAY_DEV_TOKEN` (or a token input in the header). On 200: clear existing markers, render numbered stop markers colored by `role`, draw `segments[].polyline` as L.polyline. Header banner: `Est: {algorithm_estimate_min}m | Real: {real_walking_min}m | Δ {pct}%` — color the delta badge green/yellow/red per threshold (≤10/10–25/>25%). On 422: banner with `Required: {min_required_min}m · Budget: {budget_min}m` + "Increase to {min_required + 10}" button that bumps the slider and re-submits.
4. **"Build script" flow.** Enabled only after successful Plan. POST `/api/v1/tours/build-script?glue_mode=haiku` with the Route response body. On 200: side panel becomes a per-stop accordion (collapsed by default). Show header summary: tour_name, total_audio_min, silence_pct (badge red if <60%), thinness_signal (warning badge if true). Click stop marker on map → opens its accordion item in the panel.
5. **Simulated user pin.** Second draggable red pin labeled "Simulated user," initial position = first stop. On `dragend`, compute haversine distance from pin to every stop in the route; show nearest in a small overlay at the map's bottom-left: `Nearest: {stop_name} · {distance_m}m`. Pure read-only.
6. **Add `make frontend-up`** target: `python -m http.server 8001 --directory frontend`. Document in TROUBLESHOOTING.md.
7. **Playwright smoke test** at `tests/test_harness_smoke.py`. `uv add --dev pytest-playwright`. Tests per Part B above. Use Playwright's `route.fulfill` to mock `/api/v1/tours/plan-route` with the spec example.json body — the test verifies harness behavior, not backend.
8. **Manual verification + screenshots.** Run the full stack (Scope 1 OSRM + Scope 3 API + your harness). Drop start at Place de la Concorde; anchor = Notre-Dame; lenses = dark_history + historic_arch; 180 min. Capture 3 screenshots to `specs/2026-06-02-tour-build-harness/manual-verify/`: (1) form filled before Plan, (2) Plan result with stops + polylines, (3) Build script with per-stop reveal.

## Do NOT
- Use a frontend build step or bundler. Vanilla JS only. Browser-native ES modules OK.
- Add audio playback or proximity-triggered audio (Scope 5+ territory — execution simulator).
- Persist anything to localStorage beyond the dev token (UX nicety; not state).
- Wildcard CORS — Scope 3 already locks origin to `http://localhost:8001`, so test on that exact origin.
- Skip the screenshots — they're the artifact that closes AC-7.

## Verification commands
```bash
# Playwright smoke test (skipped if Playwright browsers not installed)
pytest tests/test_harness_smoke.py -v

# Manual run-through (cannot be automated; produces screenshots)
ONDOWAY_DEV_TOKEN=devsecret make api &
make frontend-up &
sleep 2
open "http://localhost:8001/tour-tester.html#token=devsecret"
# Follow Task 8 verification; save 3 screenshots.

# Full suite green
make test && echo OK
```

## Best practices to enforce
- UX: clear loading states during API calls; error banner copy human-readable.
- Accessibility: all inputs have labels; keyboard navigation works for the typeahead.
- Performance: `GET /pois` fetched once at page load, cached.

Before starting, confirm Scope 3 endpoints are reachable. Flag if `02-spec-example.json` differs from current API response shape — generate a small test against `make api` first to compare.
```

---

# PART D — Best Practices Implementation Checklist (covers all scopes)

| Practice | Where (scope.task) | How to verify |
|----------|-------------------|---------------|
| OSRM bound to 127.0.0.1 only | 1.1 | `grep 127.0.0.1:5000 docker-compose.osrm.yml` |
| PII-safe fallback logging | 1.2 | `pytest tests/test_tour_distance.py::test_pii_safe_logging` |
| LRU TTL cache on live OSRM | 1.2 | `pytest tests/test_tour_distance.py::test_lru_cache_polyline` |
| Matrix loads to degraded mode if missing | 1.7 | API starts cleanly with no matrix file; startup log shows "degraded" |
| `make matrix-build` manual (not auto on upload) | 1.3 | No upload script invokes matrix builder; doc says operator runs |
| Pydantic input validation: time_budget, optional dedup, visit_modes subset | 3.1 | `pytest tests/test_tours_api.py -k "400 or invalid"` |
| Constant-time dev-token compare | 3.4 | `grep secrets.compare_digest src/api/auth/dev_token.py` |
| Rate limit 10/min on /build-script | 3.5 | `pytest tests/test_tours_api.py::test_rate_limit_build_script_11th_request_429` |
| CORS strict allowlist | 3.7 | `pytest tests/test_tours_api.py::test_cors_localhost_8001_allowed` |
| Glue mode mock default in tests | 3.2 | `grep glue_mode=mock tests/test_tours_api.py` |
| MockGlueClient (no Anthropic in CI) | 3.2 | Test fixture asserts `os.environ.get('ANTHROPIC_API_KEY') is None or glue_mode='mock'` |
| 88 tests re-baselined with documented range bounds | 1.5 | PR description lists each retained range bound + justification |
| AC-3 split a/b/c covered | 1.6 | Three named tests, all green |
| AC-7 manual screenshots | 4.8 | `ls specs/.../manual-verify/*.png \| wc -l` ≥ 3 |
| `make lint` zero errors | every scope | hook enforced |

---

## Implementation order

1. Scope 1 (Production Routing Infrastructure) — 3 sessions
2. Scope 2 (TourInput Anchor + Visit Modes) — 2 sessions
3. Scope 3 (Tour-Build HTTP API) — 2 sessions
4. Scope 4 (HTML Test Harness) — 2 sessions

Total: 9 sessions, one commit per scope. `/clear` between scopes.

## Approval gate

Confirm before `/implement` (Stage 6). After approval, Stage 6 starts with Scope 1's Part C prompt in a fresh `/clear` session.
