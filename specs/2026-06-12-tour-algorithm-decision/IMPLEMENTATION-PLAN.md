# Ondoway Tour Algorithm — Implementation Plan (per-step verified)

> Companion to `ALGORITHM-SPEC.md`. Every milestone is atomic, names real locations, and ends with a
> **runnable proof**. The bar each step keeps green is `make test-local` (full Python suite on Neo4j
> 7688; clears `__pycache__`); `make test` (adds Flutter) is the commit bar.
>
> Existing files cited were read this session; items written as a bare module path (e.g.
> `src/tour/ordering`, `scripts/backfill_poi_role`) are **NEW files to create**.

## Verified landmines (read this session — do not trip these)
- `scripts/poi_gravity_rescore.py:22` is hardcoded `ROOT = Path("/Users/adamserblowski/Geotada")` and
  rescores `importance_tier`, NOT `poi_role`. **Do NOT extend it for M0a** — write a fresh script.
- `tests/test_trip_api.py:131` (`test_generate_trip_golden_ratio_applied`) and the
  `anchor_count`/`flavour_count` response fields **break when `apply_golden_ratio` is deleted** (M0b).
- `tests/conftest.py` flips every SKIP→FAIL, so engine tests depending on Valhalla must **MOCK** it.
- `tests/fixtures/tour_golden/` is referenced (`test_tour_golden_ile.py`) but **absent** → golden tests
  FAIL under `make test`; M0c markers + fixtures fix this.
- `make test-cloud` does `DETACH DELETE` on Aura — **never** in a loop ([[feedback_never_destructive_api]]).
- After any `make sync`, `git checkout -- uv.lock` (keep the lock public-PyPI only).
- Density gate is `assess(input, pois, beats)` (`src/tour/density.py`); `walk_by_only` excluded,
  `setting` counts (`tests/test_tour_density.py:257,266`).

## Dependency ledger
- **Add (pip via `make sync`, then `git checkout -- uv.lock`):** `rapidfuzz` (M7).
- **Add (Docker only, never pip):** Valhalla + IDF pedestrian tiles (M1).
- **Stay absent (design forbids):** `ortools`, `networkx`, `routingpy`, `openrouteservice`, `h3`.
- **Reuse (installed):** `httpx` (Valhalla HTTP), `shapely` (isochrone + Seine test), `anthropic` (COMPOSE).

## New Makefile targets
`backfill-poi-role` (M0a); `valhalla-up`/`valhalla-down`/`valhalla-status`/`valhalla-build-tiles` (M1);
`test-golden` + `tour-grade` (M0c/M8). Edit `pyproject.toml` addopts `-m 'not live'` →
`-m 'not live and not golden and not grade'`; register `golden` + `grade` markers.

---

## M0 — Close the two-pipeline divergence (CRITICAL PATH)

### M0a — poi_role correctness backfill (the 128 nulls)
- **Build:** NEW `scripts/backfill_poi_role` (own `ROOT` from the repo, NOT Adam's path). Update
  `data/paris/poi-raw.json` (canonical) + Neo4j. Rule: null → `stop` if tier ≥ 4 or has an active
  stop-class beat; else `setting`. Never touch the 102 `walk_by_only`. Add `make backfill-poi-role`.
- **Why (corrected vs the brief):** the 128 nulls are coerced to full-weight "stop"
  (`src/tour/selection.py:334`, `poi_role = r.get("poi_role") or "stop"`), so settings/walk-past POIs
  are **over-weighted**, not zeroed. This corrects weighting; it is not a zero-score rescue.
- **PROVE:** `MATCH (n:POI) WHERE n.poi_role IS NULL RETURN count(n)` → **0**; poi-raw.json 0 nulls. New
  pure test `tests/test_poi_role_backfill` (no DB): assert 0 nulls and that the count of POIs whose
  role_mult moves 1.0→0.7 (stop→setting) is **> 0**. Command: `make test-local`.

### M0b — wire `src/tour` into `POST /trips/generate`; delete `apply_golden_ratio`
- **Build:** rewrite `generate_trip` (`src/api/routes/trips.py:26`): `load_paris_corpus(driver)` → build
  `TourInput` from the request → `select_route` → `generate` → `validate_script` → persist via
  `create_trip_with_stops`. **Delete** `apply_golden_ratio` (`src/api/crud/trips.py:83`) +
  `compute_schedule` (`:143`) + imports. Add `lenses` + `round_trip` to `TripGenerateRequest`
  (`src/api/models/trips.py`); lens precedence request → profile `PREFERS_LENS` → default-lens.
- **Downstream (verified):** `tests/test_trip_api.py` `test_generate_trip_golden_ratio_applied:131` +
  the `anchor_count`/`flavour_count` response fields must be **replaced** with ordering/lens/
  traceability assertions; the Sydney `no_pois_in_radius` 422 maps to the REACH RED refuse path.
- **PROVE:** updated `tests/test_trip_api.py`: returned stop order **==** `select_route` ordered POI ids;
  every `beat_id` traceable to a route POI; `lens_coverage` present. `grep -rn apply_golden_ratio src/`
  → **0**. Command: `make test-local`.

### M0c — test-infra: markers + missing golden fixtures
- **Build:** register `golden`+`grade` markers (`pyproject.toml`); deselect them from `make test`;
  create the absent `tests/fixtures/tour_golden/` fixtures (`ile_oneway_90min`, `flagship_reference`);
  add `make test-golden` (`uv run pytest -m golden`, needs `make db-up`).
- **PROVE:** `make test` collects green with golden/grade **deselected** (0 fail from a missing fixture);
  `make test-golden` runs **> 0** golden tests, **0 fail**.

---

## M1 — Valhalla RoutingClient + haversine fallback
- **Build:** add a `valhalla` service to `docker-compose.yml` (IDF `.osm.pbf`, healthcheck); NEW module
  `src/tour/routing_client` exposing `RoutingClient` (`leg_seconds`, `route→(s,m,polyline)`,
  `isochrone`) over Valhalla HTTP (`httpx`), falling back to `pace_corrected_walk_seconds`
  (`src/tour/routing.py:57`) when unreachable. Add `make valhalla-up/down/status/build-tiles`.
- **PROVE:** new `tests/test_tour_routing_engine` — (a) **mock** the HTTP client → 5-Paris-point matrix
  has routed s/m ≠ haversine for ≥1 pair, diagonal == 0; (b) **mock** `ConnectionError` → returns
  exactly `pace_corrected_walk_seconds(haversine_m(...))`. **0 skips.** Command: `make test-local`.

## M2 — routed leg_seconds + polyline on the contract
- **Build:** add `leg_seconds`/`polyline`/`source` to `TransitSegment` and `route_polyline`/`routed`/
  `backtrack_ratio`/`flow_score` to `Route` (`src/tour/contract.py`); extend `summarise_route`
  (`src/tour/routing.py:143`) to take an optional `RoutingClient`. Surface `transit_polyline` on
  `GeneratedStop` (`src/api/models/trips.py`) + mobile `ItineraryStop`.
- **PROVE:** GREEN fixture + **mocked** routing client selects the **same** POI id set (Jaccard == 1.0)
  but `route.transits[i].leg_seconds` is populated and differs from `walk_seconds` for ≥1 leg;
  `Route`/`TransitSegment` round-trip `model_dump()/model_validate()`. Command: `make test-local`.

## M3 — SELECT: lens_adjacency hop model + routed divisor + golden re-baseline
- **Build:** in `src/tour/selection.py` switch the greedy insertion cost (`:493`+, `insertion_cost_seconds`
  in `src/tour/routing.py:99`) to `RoutingClient.leg_seconds`; replace `_interest_bias` (`:1085`) with a
  `lens_adjacency` term (1.0 direct / 0.6 parent-or-child 1-hop via `IS_PARENT_OF` / 0.0 miss) inside
  `poi_score` (`:1070`); keep the §3 multiplicative form. Re-baseline goldens with a reviewed diff.
- **PROVE:** unit test asserts the three hop values (direct/parent/miss); golden diff shows **only**
  intended deltas, each explained; one golden stays anchored to the empirical roster.
  Command: `make test-local`.

## M4 — ORDER: exact Held–Karp open-TSP
- **Build:** NEW module `src/tour/ordering` with `held_karp_open(points, *, fixed_start, fixed_end,
  routed_cost_fn)` (bitmask DP, open path; closes the loop only if `round_trip`). Call it from
  `select_route` after the set is chosen, replacing `_reorder_with_endpoint`
  (`src/tour/selection.py:913`). Bound by `HARD_ANCHOR_CAP=12`. No OR-Tools.
- **PROVE:** new `tests/test_tour_ordering_heldkarp` — "seesaw" fixture: HK total walk **<** greedy-NN
  total, backtrack (direction reversals) **== 0**, `order[-1] == end_poi.id`; **exactness**: for every
  n in 4..8, HK cost **==** `itertools.permutations` brute-force optimum (`abs(diff) < 1e-6`); per-case
  runtime < 1s. Command: `make test-local`.

## M5 — REACH: Valhalla isochrone + density/sparse
- **Build:** add `isochrone(origin, minutes)` to `src/tour/routing_client`; replace the analytic
  envelope filter (`src/tour/selection.py:445`) with point-in-isochrone (`shapely`), haversine-radius
  fallback; map `assess(...)` (`src/tour/density.py`) status → `ReachVerdict.mode`
  (standard/ambient/redirect/refuse).
- **PROVE:** new `tests/test_tour_reach` (extends `tests/test_tour_density.py`) with mocked isochrone:
  thin → `ambient`; denser-adjacent → `redirect` with `one_way_alternative_destination` set; RED →
  `select_route` raises `TourabilityRefusedError`; an out-of-isochrone POI the old radius admitted is
  now rejected. **0 skips.** Command: `make test-local`.

## M6 — k flavours
- **Build:** add `select_k_routes(input, snapshot, k, *, routing_client)` to `src/tour/selection.py` —
  re-run greedy with a diversity penalty on used POIs; reject >60% Jaccard overlap; each flavour
  independently ORDERed + ROUTEd. Surface `k` through the API as a list of `RouteOption`.
- **PROVE:** new `tests/test_tour_flavours`, dense GREEN fixture (mocked routing), k=3: every pair
  `jaccard < 0.60`; ordered paths pairwise differ; count ∈ {2,3}; each passes `validate_script`.
  Command: `make test-local`.

## M7 — COMPOSE fire-once → VERIFY with teeth
- **Build:** COMPOSE today is **per-stitch** Haiku calls (`src/tour/glue_client.py` `stitch(category,
  context, request)`); the new design is **one fire-once** Anthropic tool-use call per picked route —
  add it alongside `HaikuGlueClient`, keep `MockGlueClient` the default so `make test` stays offline.
  Surface `source_passage`/`key_claims` into `BeatRef` (load Cypher + `src/tour/contract.py:75`). Harden
  `validate_script` (`src/tour/validation.py:96`) with **`rapidfuzz`** provenance + an entailment
  faithfulness check; wire the gate so a failing report triggers **exactly one** recompose then **blocks
  serving**. Audio uses the existing pipeline (`src/audio/pipeline.py`, `src/audio/provider.py`).
- **PROVE:** extend `tests/test_tour_validation.py` — every beat-typed sentence's `source_id` ∈ route
  beats (0 orphans, mirrors `test_unknown_beat_id_is_untraceable`); a fabricated proper-noun sentence is
  caught (mirrors `test_glue_introducing_proper_noun_not_in_beats_is_flagged`). New
  `tests/test_tour_recompose` — stub emits one untraceable sentence on attempt 1, clean on attempt 2:
  compose called **exactly 2** times; audio invoked **0** while failing, **1** after pass; still-failing
  → trip **blocked** (pytest.raises). Command: `make test-local`.

## M8 — GRADE: CI gate + live audit
- **Build:** NEW `scripts/grade_tours` (exemplar-calibrated rubric over `tests/fixtures/tour_golden/*`),
  reuse the M7 validator for the live-sample audit. Add `make tour-grade` (`@pytest.mark.grade`,
  excluded from `make test`) + `make grade-live`.
- **PROVE:** `make tour-grade` exits non-zero when a deliberately-broken golden drops below threshold,
  passes on the current corpus; `make test` still excludes grade/golden.

---

## Audit gate (rides on M2+M4, signed off in M8)
Flagship Paris route must clear: **polyline ∩ Seine polygon = ∅** (decode each leg polyline to a
`shapely.LineString`, intersect `tests/fixtures/geo/seine_paris.geojson` with bridge corridors excluded
→ 0 m inside) **and** routed-vs-reference time error **< 20%** — the wireframe tracker's own gate.

## Sequencing
- **M0a → M0b → M0c critical path.** **M1 precedes M2–M6** (all consume `leg_seconds`/`isochrone`;
  haversine fallback keeps them green without `valhalla-up`). **M3 re-baselines goldens** before M4/M6.
  **M7 adds the only new pip dep**; keep `MockGlueClient` default through M7/M8.

## Definition of done (MVP — nothing deferred)
M0–M8 green under `make test` (golden/grade as their own gates), the flagship Paris route clears the
audit gate, and `POST /trips/generate` returns 2–3 `RouteOption` flavours with ordered stops, per-stop
audio, a real polyline, an honest routed ETA, and a grounded "why this works".
