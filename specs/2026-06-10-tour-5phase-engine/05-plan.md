# Tour Algorithm — Build Plan (v2, corrected · executable)

> For Claude Code. Build the tour engine by **evolving what's already in the repo**. Every decision here is made — do not stop to ask the user. Source design: `ondoway-tour-algorithm.html` (v2). **This supersedes the v1 plan**, which used the wrong THREAD mechanism (networkx Yen's). Reconciled + adopted 2026-06-10.

## The one corrected idea

Tour selection is the **Orienteering Problem** — pick a budget-bounded *subset* of POIs that maximizes value, in walking order. `src/tour/selection.py::select_route` already solves it (greedy best-insertion under a budget, density gate, endpoint-pull, fill-pass). **Evolve it.** Never replace it with a graph shortest-path (no networkx / Neo4j GDS / OR-Tools / Yen's). The objective is a **non-negative value divided by walk cost** — never a subtractive `edge_cost` (that goes negative and breaks pathfinding):

```
value(POI) = λ·lens_adjacency + μ·importance_tier + richness      # every term ≥ 0
select greedily by  (marginal value / marginal walk_seconds),  under the time budget
k "flavours"      =  re-run the same greedy, penalizing POIs already used
```

## Decisions — baked, do not re-open

| Topic | Decision |
|---|---|
| **THREAD engine** | Evolve `select_route`. No new graph/solver dependency. |
| **Objective** | Non-negative `value / walk_seconds`. λ, μ are documented hand-set constants ("set 2026-06-10"). |
| **gravity** | := `POI.importance_tier` (1–5). There is no `gravity` field — do not invent one. |
| **Anchors** | Use `select_route`'s existing anchor handling. **Delete** the old API-path `apply_golden_ratio` 20/80 — do not port it. Assert anchors appear, in a golden. |
| **arc_fit** | ν = 0 for v1. The corpus beat tags don't support a real 5-stage arc. Later: a post-hoc reranker over the k routes — never an edge weight. |
| **REACH** | Default = shapely buffer ($0, sub-second). ORS isochrone is an opt-in upgrade behind an interface — not called on every request. |
| **COMPOSE** | Raw Anthropic SDK tool-use + Pydantic (reuse `glue_client.py`). Not instructor. Fire once, on the picked route. |
| **VERIFY** | Honest split: rapidfuzz = **provenance** (passage↔chunk); a cheap entailment pass = **claim faithfulness** (sentence↔cited beat's `key_claims`). Never report "0 unfaithful" from rapidfuzz alone. |
| **GRADE** | Exemplar-calibrated regression gate (no completion-rating store exists yet — label it honestly). Hand-set λ/μ; the gate catches regressions. No closed-loop auto-tuning against our own judge. |

## Facts to build against (verified this session)

- `POST /api/v1/trips/generate` → `src/api/crud/trips.py` (`find_candidate_pois` radius + `apply_golden_ratio` + `compute_schedule`). The good engine `src/tour/` is **not imported by `src/api/`**. M1 wires it in.
- **62% of POIs score 0 today**: 128 null `poi_role` + 102 `walk_by_only`, both map to `POI_ROLE_MULTIPLIER` 0.0 in `selection.py`. Backfill is a real content pass (M0), not a one-liner.
- Live request = `center_lat, center_lng, radius_m, max_stops, start_time, kid_friendly_only` (`duration_min` optional/None, no `round_trip`, no `lenses` — lenses come from `profile_id`→`PREFERS_LENS`). Engine `TourInput` = `start, duration_min, city_slug, lenses, round_trip`. M1 needs the explicit adapter below.
- Mobile stop = `ItineraryStop` (Dart) / `GeneratedStop` (backend Pydantic): single required `beat_id` + optional `audio_url`, 10 m geofence. Preserve this shape (one MP3 per stop).
- `source_passage`, `source_chunk_slug`, `script_body_hash`, `key_claims` already exist on every beat in `data/paris/beats.json` — not yet carried through `BeatRef`. M5 carries them.
- `make test-cloud` is **not read-only**: it `--ignore`s 3 files and its `seeded_driver` runs `MATCH (n) DETACH DELETE n` + reseed against Aura, **bypassing `conftest._assert_test_port()`**. Bring every new write fixture under that guard.

## Testing contract (keep — verified real)

- Bar = `make test` = `test-local` (Docker Neo4j 7688) + `test-cloud` (Aura) + `flutter-test`, **0 fail / 0 skip**. `conftest.py` flips skip→fail.
- Network/LLM tests live **outside** the default suite (own marker + `-m "not <marker>"`). Never skip, never `--ignore` a would-pass test.
- The first tour functional test edits the hardcoded `make test-functional` recipe in the same change.
- New dep + its first test + a public-PyPI `uv lock` land in one change.
- Goldens re-baseline atomically with a reviewed diff. Keep one golden anchored to the empirical roster — don't let the engine grade its own homework.
- Spy-counters: REACH+THREAD = 0 LLM/TTS calls; COMPOSE = exactly 1 per picked route; GRADE = 0 in the default suite.

---

## M0 — Foundations

- **M0.1** Green baseline: `make test` = 0/0. Archive the two golden tours' markdown as the "before."
- **M0.2** Backfill `poi_role` for the 128 null POIs in `data/paris/poi-raw.json` (stop/setting/walk_by_only) and re-upload. Content pass — a non-zero default is only a stopgap; real roles are the fix.
- **M0.3** Record in `specs/NORTHSTAR.md`: `gravity := importance_tier`; anchors via `select_route` (the API-path 20/80 is retired).
- **M0.4** Add `rapidfuzz` (shapely already present); `uv lock` on public PyPI.
- **Verify** [I] `load_paris_corpus` returns 0 null-role POIs; [F] `uv.lock` is all `files.pythonhosted.org`; `make test` green.
- **Gate:** green `make test`; no accidental null-role zeros.

## M1 — Make `src/tour` the production engine + adapter + Tour Workbench

- **M1.1** Extract `scripts/tour_build.py` orchestration (`select_route → select_poi_beats → generate → validate_script`) into `src/tour/pipeline.py`. No behavior change. **Verify** [U] identical `Script` for a fixed `TourInput` + `MockGlueClient`; [F] existing goldens pass unchanged; [M] CLI still writes the same markdown.
- **M1.2** Adapter `TripGenerateRequest → TourInput` (write this table in code + docstring): `start = (center_lat, center_lng)`; `duration_min = request.duration_min or invert envelope_radius_m(radius_m)`; `round_trip = True` for "Tour Now"; `lenses = profile PREFERS_LENS`; `city_slug` from request. **Verify** [U] each field incl. far-center → 422.
- **M1.3** Rewrite `crud/trips.py` to call `src/tour/pipeline` and map `Script → GeneratedTrip/GeneratedStop` (one ordered stop per `ScriptPOI`, single `beat_id` + `audio_url`). Preserve `201 + trip_id`, `404` unknown profile, `422` no-pois, `respects_max_stops`, `anchor_count+flavour_count==total_stops`, `creates_graph_nodes` (Trip + ItineraryItem via HAS_STOP). **Delete** `apply_golden_ratio` + `compute_schedule`; rewrite their unit tests to cover the new mapping. New write fixtures use `_assert_test_port()`.
- **M1.4** Tour Workbench page (dashboard `:8080`): Leaflet ordered numbered markers + polyline + stop list (reuse `frontend/review.html` `#map`). This is the manual surface for all later milestones. **Verify** [M] enter start+duration → ordered polyline + stop list matching the CLI markdown; [F] a Playwright test (pattern of `test_workbench_ui.py`, already `--ignore`d from default) asserts polyline + N markers.
- **Gate:** `/trips/generate` serves a walk-ordered `src/tour` route; workbench draws it; goldens green (or atomically re-baselined); `make test` green.

## M2 — REACH (provider interface, shapely default)

- **M2.1** `src/tour/reach`: `ReachProvider.isochrone(start, walk_minutes) -> shapely.Polygon`. Impls: `ShapelyBufferProvider` (wraps `routing.envelope_radius_m`, the default), `ORSIsochroneProvider` (opt-in, live HTTP), `StubReachProvider` (fixture polygon, tests). DI into pipeline; ORS failure → shapely + `degraded=True`.
- **M2.2** Feed the reachable set into existing `density.assess()` (GREEN/YELLOW/RED). Defer H3.
- **Verify** [U] inside→reachable, just-outside→not; ORS raise → shapely fallback + degraded; [I] `StubReachProvider` in integration (no live network).
- **Gate:** REACH behind the interface, shapely default; `make test` hermetic + green.

## M3 — Objective + greedy + flavours (the core)

- **M3.1** Formalize `value()` in `selection.py`: non-negative `value = λ·lens_adjacency + μ·importance_tier + richness`, λ/μ documented constants. `lens_adjacency` = direct 1.0 / `IS_PARENT_OF` hop 0.6 / miss 0.0. Keep walk as the existing `insertion_cost_seconds` (the divisor). **Verify** [U] value ≥ 0 always; raising `lens_adjacency` or `importance_tier` raises value; λ=μ=0 → value = richness.
- **M3.2** `select_k_routes(input, snapshot, k=3)`: run `select_route`, then re-run with a multiplicative penalty on already-used POIs, k times; reject a route sharing > 60% POIs (Jaccard) with a kept one; return ≤k distinct routes. `select_route` stays the k=1 delegate. **Verify** [U] ≤k distinct; deterministic (fixed tie-break); degrades to fewer on a small pool (no crash).
- **M3.3** `RouteOption{route_id, ordered_poi_ids, ordered_beat_ids, lens_summary, budgets}`; `route_id` = content-hash incl. `city_slug`. COMPOSE later takes the full option, not a re-derivation. **Verify** [U] stable hash; reorder → new id.
- **M3.4** Re-baseline PdV/Île goldens (reviewed diff) + add one k-route one-way golden (real 11-key schema). Keep one golden's `expected_beat_ids` anchored to the empirical roster (rule #5).
- **M3.5** Workbench: flavour picker (distinct coloured polylines + each route's lens summary). **Verify** [M] Concorde, 180 min, lenses `hidden_history` then `historic_arch` → 2–3 flavours; lens change re-threads, sub-second.
- **Gate:** value objective + k flavours live; goldens green; `make test` green on both legs.

## M4 — COMPOSE (constrained, fire-once, per-stop audio)

- **M4.1** Extend `generation.py`: tool-use + Pydantic schema forcing `source_beat_id ∈ supplied whitelist` on every sentence (reuse `glue_client.py`, `templates/glue_prompt.txt`). Glue/openers keep `GLUE_*` labels. **Verify** [U] out-of-whitelist id → retry then valid; spy counter = exactly 1 compose per picked route; REACH+THREAD = 0 LLM.
- **M4.2** Compose runs once when the user picks a `RouteOption` (`POST /tour/compose` or a compose step in `/trips/generate`). **Verify** [I] seed 2–3 POIs with real beat bodies → every `Sentence.source_id` traces to a seeded beat.
- **M4.3** Per-stop audio: concatenate each stop's composed sentences → one MP3/stop via the existing ElevenLabs path, keyed `route_id + stop_idx` (handles glue/opener sentences with no `beat_id`; preserves the single-`audio_url` mobile contract). **Verify** [U] a stop containing a synthesized opener still yields a playable segment.
- **M4.4** Real-LLM functional test (`skipif not reachable`), wired into the `test-functional` recipe; asserts `validation.passed`, 0 forbidden, cost under ceiling.
- **Gate:** compose fires once → traceable narrative + per-stop audio; `make test` green; functional test only under `make test-functional`.

## M5 — VERIFY (provenance + claim faithfulness — editor, not writer)

- **M5.1** Carry `source_passage`, `source_chunk_slug`, `key_claims` through `LOAD_PARIS_BEATS_CYPHER` + `BeatRef` (they exist in `beats.json`). A `BeatRef` with these None still validates.
- **M5.2** Two checks added to `ValidationReport` (never mutate `Script`), reported separately: provenance = `rapidfuzz(beat.source_passage, chunk)`; faithfulness = cheap entailment (one Haiku call/stop, dev/CI) of each beat-cited sentence against its beat's `key_claims`. **Verify** [U] verbatim→provenance-ok; a sentence unsupported by its cited beat's `key_claims` → `faithful=False` with the beat id; failing check writes a report entry, leaves `Script` unchanged.
- **M5.3** Goldens assert 0 provenance-absent + 0 unsupported on the live corpus.
- **Gate:** both checks in goldens + workbench panel; `make test` green.

## M6 — GRADE (exemplar-calibrated regression gate)

- **M6.1** DIY Opus rubric (coherence, factual_density, pacing, would_recommend), median of N, responses cached. Calibrate on `Books/` exemplars only — label every score "exemplar-calibrated." **Verify** [U] gate logic with a mocked judge (PASS/FAIL, tolerance, median-of-N) — no live LLM.
- **M6.2** `make tour-grade` (new target) runs the judge over golden routes vs a git-tracked baseline; FAIL if any dimension drops > tolerance. Add `@pytest.mark.grade` + `addopts = -m "not grade"` in the same step (deselection ≠ skip). **Verify** [F] prints a per-route table + exits non-zero on a regression; not part of `make test`.
- **M6.3** λ/μ stay hand-set. The gate catches regressions; it does not auto-tune. If weights are ever changed, require **both** goldens ≥90% overlap **and** `tour-grade` non-regressing **and** a human spot-check on a held-out exemplar set.
- **Gate:** `make tour-grade` works, excluded from the default bar; `make test` green.

## M7 — Cache popular starts

- **M7.1** Cache composed `Script`s keyed on `route_id` + a corpus-version hash (contributing beats' `script_body_hash` set) + the objective-weight version + beat `active_status`. **Verify** [U] key includes `city_slug` + corpus version; reorder → new key.
- **M7.2** Dependency invalidation: each entry records its beat ids; editing a beat invalidates exactly the dependent entries. **Verify** [I] mutate one beat → miss for dependents only.
- **M7.3** Pre-generate popular starts offline. **Verify** [F] cache hit = 0 LLM/TTS (spy).
- **Gate:** cached compose instant + $0; edits invalidate precisely; `make test` green.

---

## Definition of done (every milestone)

[U] unit + [I] integration (Neo4j 7688) + [F] functional (golden + skip-gated real-service, outside the default suite) + [M] manual workbench (exact `make` + ports + "You should see / If it fails") — and the milestone ends with `make test` green (0 fail / 0 skip) on both legs. From M6, `make tour-grade` must be non-regressing.
