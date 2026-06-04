# 02 — Spec: Production Tour-Build Pipeline + Test Harness

> **Date:** 2026-06-02 · **Stage:** 2 (Spec) · **Flavor:** B (contract) · **Thinking mode:** Contract designer

---

## Purpose

Expose the existing `src/tour/` pipeline as a two-phase HTTP API (route → audio) backed by production walking-time routing (self-hosted OSRM + precomputed distance matrix), with an HTML harness for evaluating output quality against Paris corpus inputs. Unblocks the Boredom Test internal pass (Phase 1 gate) and downstream mobile-app consumption.

## Inputs

**`POST /tours/plan-route` request body:**
```
{
  city_slug: "paris",                           // string, whitelist
  start: { lat: float, lng: float },            // lat ∈ [-90, 90], lng ∈ [-180, 180]
  time_budget_min: int,                         // [30, 600]
  lenses: [string],                             // ≥1, all in 16-canonical-lens whitelist
  anchor_poi_id: string,                        // required, must exist in city's POI corpus
  optional_pois: [string],                      // ≤2, each must exist in corpus
  visit_modes: { [poi_id]: "walk_past" | "stop_visit" }   // anchor + each optional
}
```

**`POST /tours/build-script` request body:** the Route object returned by `/plan-route` (round-tripped unchanged so the script phase can be re-run without re-planning).

**Note on naming:** "build-script" emphasizes that this scope produces the **text** the audio guide will eventually speak — no MP3 rendering, no ElevenLabs call, no S3 upload. Audio rendering is a downstream concern handled in a later scope; it's a deterministic transform of a good script.

**Side inputs (read-only):** Paris corpus in Neo4j (POIs, NarrativeBeats, Lenses, Areas), precomputed distance matrix file loaded at API startup, OSRM container reachable.

## Outputs

**`POST /tours/plan-route` 200 response (Route):**
```
{
  route_id: string,                             // deterministic hash of inputs
  city_slug: "paris",
  inputs: { ...original request body },
  stops: [
    {
      poi_id, name, lat, lng,
      role: "anchor" | "content" | "mood_pacing" | "segment",
      importance_tier: int,
      visit_mode: "walk_past" | "stop_visit" | null,
      lens_density: { [lens_name]: int }        // matching beats per lens for this POI
    }
  ],
  segments: [
    {
      from_stop_index, to_stop_index,
      walking_distance_m, walking_time_sec,
      polyline: [[lat, lng], ...],              // OSRM-fetched, real street geometry
      routing_mode: "live_osrm" | "fallback"
    }
  ],
  total_walking_time_sec: int,
  total_walking_distance_m: int,
  routing_mode_summary: { live_osrm: int, fallback: int },
  warnings: [string]                            // e.g. "matrix-miss for POI X", "OSRM degraded"
}
```

**`POST /tours/build-script` 200 response (ScriptPlan):**
```
{
  route_id: string,
  per_stop: [
    {
      stop_index: int,
      poi_id: string,
      beats: [
        {
          source: "beat" | "glue",              // corpus beat vs. LLM/template glue
          beat_id: string | null,               // populated when source = "beat"
          glue_id: string | null,               // populated when source = "glue" (e.g. "transit_short")
          play_order: int,
          duration_sec: int,
          narrative_function: string | null,    // populated when source = "beat"
          lens: string | null,                  // populated when source = "beat"
          sentence_text: string                 // REQUIRED on every entry — server materializes inline
        }
      ],
      total_audio_sec: int
    }
  ],
  per_segment: [                                // walking-segment flavor (rule J1)
    {
      segment_index: int,
      from_stop_index: int,
      to_stop_index: int,
      beats: [
        { source, beat_id, glue_id, play_order, duration_sec, lens, sentence_text }
      ],
      total_audio_sec: int                      // may be 0 — silence between stops is acceptable
    }
  ],
  total_audio_sec: int,
  silence_pct: float,                           // (1 - total_audio_sec / total_tour_sec); must be ≥ 0.6
  tour_name: string,                            // whatever current generate() produces
  thinness_signal: bool                         // true if any stop's total_audio_sec < tier floor
}
```

**Inline-materialization contract:** `sentence_text` is required on every entry, including glue. The server is the single source of truth for the rendered script — callers (harness, future mobile) never re-render. This avoids forcing every caller to carry an LLM client + corpus access just to display the script. Mobile bandwidth concerns are handled with response gzip, not by splitting the contract.

**Error responses:** `400` (input validation), `404` (anchor or optional POI not in corpus), `422` (infeasibility: anchor unreachable within time budget; lens whitelist miss).

## Constraints

- **Distance call ordering:** matrix lookup → live OSRM → haversine fallback. Each path increments a counter visible in `warnings` / logs.
- **OSRM-down behavior:** request returns 200 with `routing_mode: "fallback"` populated per segment and a warning logged. Never crashes.
- **Performance:** `/plan-route` p95 < 2s; `/build-script` p95 < 5s. Matrix lookup p99 < 1ms.
- **Test re-baseline:** all 88 existing `tests/test_tour_*.py` cases run with real OSRM math and pass.
- **No mutation of Neo4j** in either endpoint. Tour state is ephemeral.
- **Determinism:** identical inputs produce identical `route_id` and identical Route output (no embedded timestamps in the hash).
- **Auth:** same access controls as existing API endpoints (dev-permissive, production-gated later).
- **Input validation:** at FastAPI Pydantic boundary; no raw user input reaches `select_route()`.

## Acceptance Criteria

1. **Works when** a valid request to `POST /tours/plan-route` returns 200 with `anchor_poi_id` present in `stops[].poi_id` and at least one segment with `polyline.length ≥ 2`.
2. **Works when** a returned Route is POSTed verbatim to `POST /tours/build-script` and the response 200 contains `per_stop` with one entry per Route stop and at least one beat at the anchor stop.
3. **Works when** the OSRM container is stopped: `POST /tours/plan-route` still returns 200, every segment's `routing_mode` is `"fallback"`, and a `WARNING`-level log message references OSRM unavailability.
4. **Works when** an anchor POI is selected whose nearest reachable round-trip from start exceeds `time_budget_min`: response is 422 with body `{ error: "anchor_infeasible", min_required_min: int, budget_min: int }`.
5. **Works when** `lenses: ["film_tv"]` is submitted (3 corpus beats globally): `/plan-route` still returns a valid Route, `/build-script` returns 200 with `thinness_signal: true` and at least one stop's `total_audio_sec` below the tier floor.
6. **Works when** the API process starts: the Paris distance matrix loads into memory in <5s, memory delta <100MB, and a startup log confirms `matrix_pairs_loaded: int`.
7. **Works when** the HTML harness at `frontend/tour-tester.html` is loaded with a start pin in Paris, valid inputs, and "Plan route" clicked: the map renders stops as numbered markers, OSRM polylines between them, and a header line showing `algorithm_estimate_min` vs. `real_walking_min` with a percent delta.
8. **Works when** `make test` is run: the 88 re-baselined tour tests plus all new acceptance-criteria tests pass with 0 failures, 0 skipped.

## Concrete Output Example

See [02-spec-example.json](02-spec-example.json) for a full round-trip example: anchor = `notre-dame-cathedral`, start = Place de la Concorde, lenses = `[dark_history, historic_arch]`, time_budget = 180 min. Both endpoint responses included verbatim.

## Downstream Dependencies

- **Boredom Test evaluation loop** consumes harness outputs to assess tour quality across input combinations — direct prerequisite for Phase 1 milestone gate.
- **Mobile app** is the eventual consumer of `/plan-route` + `/build-script`. Schema must stay forward-compatible.
- **CLI `scripts/tour_build.py`** can be refactored to call the endpoints once they exist — replaces in-process pipeline with HTTP. Backwards-compat optional.
- **Future tour-execution scope** consumes the Route + BeatPlan format as its input — schema decisions here lock execution-side assumptions.

## Open Questions

1. **Matrix rebuild trigger.** Corpus upload hook (auto, possibly slow), `make matrix-rebuild` (manual, explicit), or daily cron (background)? Probably belongs in Stage 5 (implementation plan), not Stage 2. Flagging.
2. **Harness replanning UX.** When user changes lenses on a planned route, do we replan from scratch (simple) or diff-and-update (clever)? Recommend simple. Confirm in Stage 3.
