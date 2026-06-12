# M0b — Design decision + execution plan (wire src/tour into POST /trips/generate)

> Companion to IMPLEMENTATION-PLAN.md M0b. Written 2026-06-12 after reading the real code with the Read tool:
> src/api/routes/trips.py, src/api/crud/trips.py, src/api/models/trips.py, src/tour/contract.py,
> src/tour/selection.py, src/tour/density.py. M0b step 1 (request fields `lenses`+`round_trip`) landed: 5e6ac15.

## The core mismatch (verified)
The engine emits a **narrated multi-beat** tour; the API persists a **single-beat-per-stop** itinerary:

| Engine output (src/tour/contract.py) | API persistence today |
|---|---|
| `Route.pois: tuple[POI]` (ordered) + `Route.transits` (TransitSegment: from/to_poi_id, distance_m, walk_seconds) | `GeneratedStop.beat_id: str` — ONE beat (models/trips.py:65) |
| `Script.selected_pois: tuple[ScriptPOI]`; each ScriptPOI has `beat_ids: tuple[str,...]` (MANY), `dwell_seconds`, `area` (contract.py:216-228) | `ItineraryItem-[:PLAYS_BEAT]->` ONE beat (crud/trips.py:244) |
| `Script.script: tuple[Sentence]` (text, source_id, source_type, stop_idx) — the narration | not stored |
| `Script.lens_coverage: dict[str,int]` | `anchor_count`/`flavour_count` (golden-ratio era) |

No per-stop single lens exists in engine output (BeatRef carries `lenses: tuple`; coverage is tour-wide), so the
old `GeneratedStop.lens_name`/`lens_display` cannot be filled 1:1 without computing a dominant lens.

## DECISION (minimal-churn, non-lossy where it matters, M0b-scoped)
1. A **stop = a ScriptPOI** in route order; `sort_order` = index in `Script.selected_pois`.
2. **Persist all of a stop's beats**: add `beat_ids: list[str]` to `ItineraryItem` and create one `PLAYS_BEAT`
   edge per beat. Keep a `primary_beat_id` (= `beat_ids[0]`) for back-compat with existing read paths/mobile.
   Makes "every beat_id traceable to a route POI" (M0b PROVE) literally true.
3. **Per-stop lens** = dominant lens among that stop's beats (from `BeatRef.lenses`), NOT fabricated; `None` if
   the stop has no lensed beat.
4. **Response** (`TripGenerateResponse`): add `lens_coverage: dict[str,int]` (from `Script.lens_coverage`).
   Compute `anchor_count` (tier 5) / `flavour_count` from the stops for back-compat, or drop them (the plan
   flags they break) — computing is cheap and avoids a breaking response change.
5. **Narration is OUT of M0b scope.** `Script.script` (Sentence stream) is audio-script content → belongs with
   COMPOSE (M7) + the audio pipeline. M0b delivers SELECTION + ORDER + beat traceability + lens_coverage.

Rationale: keeps the Trip/ItineraryItem graph and GeneratedStop contract, adds only what the engine genuinely
produces, satisfies the M0b PROVE, defers the audio-narration schema to M7.

## Test-corpus landmine (verified, src/tour/density.py + selection.py:442-444)
`select_route` runs a density gate: `assess_tourability(...)`; `status == "RED"` → `raise TourabilityRefusedError`
(selection.py:443-444). RED unless ≥ `GREEN_ANCHOR_CANDIDATES_MIN=4` (or YELLOW `=3`) **anchor candidates** =
POIs with `tier ≥ ANCHOR_CANDIDATE_TIER_MIN(3)` AND `beat_count ≥ ANCHOR_CANDIDATE_BEAT_COUNT_MIN(3)`
(density.py:45,49,70-71). The trip-API test (tests/test_trip_api.py:22-29) wipes the graph and `seed_all`s TOY
data (3 POIs / 5 beats) → cannot clear the gate → the engine endpoint can't return a tour there.
**Resolution (recommended):** point the trip-API engine test at the **live Paris dev graph (port 7687)** the way
tests/test_tour_golden_*.py bypass conftest; mark it (e.g. @pytest.mark.golden-style) so it's excluded from the
hermetic default bar if it proves flaky. **Alternative:** build a denser hermetic seed (≥4 tier-3+ POIs each with
≥3 beats) — keeps the test self-contained; prefer if the live-graph dependency becomes fragile.

## Atomic sub-steps (each its own green commit)
- [x] **1.** `lenses` + `round_trip` on `TripGenerateRequest` — DONE 5e6ac15.
- [x] **2.** Pure `route_script_to_stops(route, script) -> list[dict]` in crud/trips.py (decided shape) +
      HERMETIC unit test from hand-built Route/Script contract objects (no DB, no engine run) — DONE 31336f3.
- [x] **3.** Output models: `GeneratedStop` gains `beat_ids: list[str]` (+ optional `dwell_seconds`);
      `TripGenerateResponse` gains `lens_coverage`. Additive; update test_trip_models.py — DONE bf7d506.
- [x] **4.** `create_trip_with_stops` writes `beat_ids` + one `PLAYS_BEAT` per beat (+ `primary_beat_id`).
- [x] **5.** Rewrite `generate_trip`: TourInput(start=(center_lat,center_lng), duration_min, city_slug="paris",
      lenses, round_trip) → `load_paris_corpus` → `select_route` → `generate` (runs validation internally) →
      `route_script_to_stops` → `create_trip_with_stops`. `TourabilityRefusedError` → 422. DELETE
      `apply_golden_ratio` (crud/trips.py:83) + `compute_schedule` (:143) + imports; grep -rn apply_golden_ratio src/ → 0.
- [x] **6.** Rework tests/test_trip_api.py per the corpus resolution (live 7687 graph, disposable test
      profiles, cleanup in teardown); assert stop order == select_route ordered POI ids, every beat_id
      traceable to a route POI, lens_coverage present; Sydney → 422.
- [x] **7.** Lens precedence: request → profile `PREFERS_LENS` (sorted) → None = engine unbiased. The "city
      default" starter set is a future computed feature (ondoway-lens-defaults-spec.md), not implemented —
      decided + user-approved 2026-06-12.

PROVE the milestone: `make test` green + `grep -rn apply_golden_ratio src/` → 0. `make test-golden` may shift
again (engine now drives the API too) — still do NOT re-baseline; fixtures stay the human-ideal target.
