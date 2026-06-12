# Ondoway Tour-Generation Algorithm — Canonical Spec

> **Status: CANONICAL (decided 2026-06-11).** Single source of truth for how Ondoway turns a
> request into a narrated walking tour. **Supersedes** (see §8): the v1 design (Neo4j GDS / Yen's),
> the solver-ban framing in `specs/2026-06-10-tour-5phase-engine/05-plan.md`, and the shallow
> `src/api/crud/trips.py` generator. Build sequence + per-step verification live in
> `IMPLEMENTATION-PLAN.md` in this folder.

## 0. Verified facts this spec is built on (file:line, checked 2026-06-11)

- Greedy orienteering selector is real: `select_route` `selection.py:424`; greedy value/cost ratio
  `value = base / max(1.0, extra + 1.0)` `selection.py:515`; objective is a non-negative product
  `importance * richness * bias * alignment * role_mult` `selection.py:1082`.
- `POI_ROLE_MULTIPLIER = {stop:1.0, setting:0.7, walk_by_only:0.0}` `selection.py:53`;
  `HARD_ANCHOR_CAP = 12` `selection.py:66`.
- **poi_role coercion (corrects the brief):** `_snapshot_from_records` does
  `poi_role = r.get("poi_role") or "stop"` `selection.py:334`. So the 128 Paris POIs with a null
  `poi_role` are loaded as **"stop" (role_mult 1.0)** — they do **NOT** score 0. Only the 102
  `walk_by_only` POIs get role_mult 0.0, and they are pre-excluded from the candidate pool
  (`selection.py:451`). The "62% score 0" figure is a raw-`poi-raw.json` artifact, **false at
  runtime**. The data fix is role *correctness* (see PLAN M0a), not a zero-score rescue.
- Walk cost today = straight-line `haversine × 1.35 ÷ 3 km/h` `routing.py:30,29,57`. **No route
  polyline exists anywhere in `src/`** (grep: polyline/geometry/valhalla absent).
- Live API path `src/api/crud/trips.py` does **not** import `src/tour`; it orders by Neo4j crow-fly
  distance and `apply_golden_ratio` (`crud/trips.py:83`) / `compute_schedule` (`:143`) compute **no**
  walk geometry. This is the two-pipeline divergence the spec closes.
- `data/paris/beats.json` carries `source_passage`, `source_chunk_slug`, `key_claims` per beat — but
  `BeatRef` (`contract.py:75`) does **not** surface them at runtime (the load Cypher omits them).
- Existing audio/TTS infra to **reuse, not rebuild**: `src/audio/provider.py` (Mock/OpenAI/ElevenLabs
  TTS), `src/audio/storage.py` (Local/S3/R2), `src/audio/pipeline.py:168` `generate_beat_audio`,
  `src/audio/eval.py:111` (Whisper WER — TTS fidelity, NOT semantic faithfulness), 8 endpoints in
  `src/api/routes/audio.py`.
- Installed: `neo4j`, `shapely`, `httpx`, `requests`, `anthropic`. Absent: `ortools`, `rapidfuzz`,
  `networkx`, `routingpy`, `openrouteservice`, `h3`.
- **No broken solver build ever existed** (verified across `git log --all -S`): `networkx`,
  `edge_cost`, `Yen`, `k_shortest`, `GDS` appear only in the two v2 design docs, never in `src/`. The
  framing is therefore **evolve the working engine**, not "fix a broken one."

External evidence (researcher, this session): Held–Karp is exact TSP at Θ(2ⁿ·n²) — for n=12,
589,824 ops, sub-ms (en.wikipedia.org/wiki/Held–Karp_algorithm, fetched). Valhalla is the only engine
of {Valhalla, ORS, OSRM} that natively provides pedestrian costing **+** encoded polyline **+**
isochrone (valhalla.github.io, fetched; OSRM has no isochrone). Pedestrian detour factor in dense
European cores ≈ 1.3–1.5 average with a tail to ~2.0+ across rivers *(from training, not a fetched
study)* — so a flat 1.35×haversine under-estimates short hops and Seine crossings and is unfit as a
user-facing ETA.

## 1. Overview — narrative-first, seven layers

Ondoway is **narrative-first**: the route serves a story, never the reverse. The engine is a linear
pipeline. LLM/TTS calls happen in exactly one layer (COMPOSE); every other layer is deterministic and
free.

```
TourInput (start, duration_min, city_slug, lenses | profiles, round_trip)
  │
  ▼ REACH    Valhalla isochrone → reachable POI set → density.assess gate
  │          (GREEN=standard / sparse→ambient / redirect{area} / RED→refuse)   [shapely-buffer fallback]
  ▼ SELECT   greedy orienteering (evolve select_route): pick a budget-bounded STOP SET maximizing
  │          Σ non-negative value, greedily by value / routed_leg_seconds. k flavours = diversity-
  │          penalty re-runs (reject >60% Jaccard overlap → genuinely different stop sets).
  ▼ ORDER    exact open-TSP via Held-Karp DP (n ≤ 12), start fixed, optional end. No OR-Tools.
  ▼ ROUTE    one RoutingClient (Valhalla pedestrian, haversine fallback) → routed leg_seconds + encoded
  │          polyline. SAME measurement feeds SELECT's divisor, ORDER's matrix, and the drawn path.
  ▼ COMPOSE  fire-once Anthropic tool-use on the picked+ordered route; per-sentence source_beat_id
  │          whitelist → Script → existing TTS pipeline (one MP3/stop). NOT a new TTS system.
  ▼ VERIFY   rapidfuzz provenance + cheap entailment faithfulness. GATES SERVING: fail → 1 bounded
  │          recompose → else refuse the flavour. arc reranker orders the k flavours here.
  ▼ GRADE    exemplar-calibrated rubric: CI regression gate (excluded from `make test`) + live-sample
  │          audit. Never a per-request loop; never self-tunes the objective weights.
  → RouteOption × 2–3 flavours: ordered stops (name, lat/lng, lens, visit|walk_past, minutes), per-stop
    audio, route polyline, honest routed ETA, "why this works", offline package. Multi-profile + default-lens.
```

## 2. Layers (inputs → algorithm → outputs → contract)

### 2.1 REACH
- **In:** `TourInput`, full `CorpusSnapshot`.
- **Algo:** `RoutingClient.isochrone(start, walk_minutes)` → reachable polygon; point-in-polygon
  filter of `snapshot.pois`; gate via existing `density.assess(...)` → GREEN/YELLOW/RED →
  `ReachVerdict.mode` ∈ {standard, ambient, redirect, refuse}. RED raises `TourabilityRefusedError`
  (no SELECT/LLM/TTS). **Fallback:** if isochrone fails, use shapely buffer of
  `routing.envelope_radius_m(...)`, set `ReachVerdict.degraded=True`.
- **Out:** reachable `CorpusSnapshot` + `ReachVerdict` `[NEW type]`.
- **On-demand "Take a Tour Now":** start = live GPS, no anchor, only required input is `duration_min`.

### 2.2 SELECT (evolve `select_route`)
- **In:** reachable `CorpusSnapshot`, `TourInput`, `RoutingClient`, `ReachVerdict.mode`.
- **Algo:** keep greedy orienteering (candidate pool, spine, `HARD_ANCHOR_CAP=12`, endpoint-pull,
  fill-pass). Two changes: (1) objective per §3; (2) `lens_adjacency` **replaces** `_interest_bias`
  (`selection.py:1085`) — requires golden re-baseline. Greedy picks max `value / routed_leg_seconds`.
- **k flavours:** `select_k_routes(..., k=3)`: re-run greedy with a multiplicative penalty on
  already-used POIs; reject any flavour sharing >60% stops (Jaccard) with a kept one; ≤k **distinct
  stop sets**, each independently ordered + routed. `select_route` = the k=1 delegate.
- **Out:** ≤k stop sets (not yet ordered).

### 2.3 ORDER
- **In:** one stop set (≤12), fixed start, optional fixed end, routed cost matrix.
- **Algo:** exact open-path TSP via **Held–Karp DP**, `O(n²·2ⁿ)`, bounded by `n≤12` (ms-scale).
  Replaces the greedy best-insertion order (`_reorder_with_endpoint`) with the optimal one. No
  OR-Tools / networkx / Yen's — a self-contained DP in `src/tour`.
- **Out:** one optimal ordered POI sequence per flavour.

### 2.4 ROUTE (the one measurement)
- **In:** ordered POIs (or a single (a,b) pair during SELECT/ORDER).
- **Algo:** one `RoutingClient`: `leg_seconds(a,b)`, `route(points)→(seconds, distance, polyline)`,
  `isochrone(start, minutes)`. Primary = Valhalla pedestrian (Docker); fallback =
  `HaversineRoutingClient` (today's `pace_corrected_walk_seconds`). The **routed** `leg_seconds` is the
  same number SELECT divides by, ORDER's matrix uses, and the UI draws — the ETA the user sees is the
  number the engine optimized. `summarise_route` (`routing.py:143`) populates the new polyline/flow
  fields; if any leg falls back, `Route.routed=False` and `route_polyline=None`.
- **Out:** fully-routed `Route` per flavour.

### 2.5 COMPOSE (fire-once)
- **In:** the picked+ordered `Route`; its `BeatRef`s (with `script_body`, `source_passage`,
  `key_claims`); the per-stop `source_beat_id` whitelist.
- **Algo:** constrained Anthropic **tool-use** (reuse `glue_client.py`), fired **once** per picked
  route. Tool schema forces every `Sentence.source_id` ∈ {a whitelisted beat id} ∪ {whitelisted
  glue/arith labels}. Out-of-whitelist ids rejected inside the single call.
- **Out:** `Script` (existing contract) → existing TTS pipeline → one MP3 per stop. **No new TTS.**

### 2.6 VERIFY (teeth)
- **In:** the `Script`; contributing `BeatRef`s (+ `source_passage`/`source_chunk_slug`/`key_claims`);
  source chunk text.
- **Algo:** (1) **provenance** — `rapidfuzz` match of each beat's `source_passage` against its source
  chunk; (2) **faithfulness** — a cheap entailment pass (one Haiku call/stop, dev/CI) checking each
  beat-cited sentence follows from that beat's `key_claims`. Results written to `ValidationReport`
  (Script unmutated).
- **Gate:** a failing report **blocks audio**; the engine does **one bounded recompose** (re-run
  COMPOSE with failing sentences flagged); still failing → **refuse** the flavour. (`rapidfuzz` alone
  ≠ faithfulness; the two checks are independent.)
- **Out:** `ValidationReport`; `validation.passed` gates serving.

### 2.7 GRADE (CI gate + live audit, never a request loop)
- **CI gate** (`make tour-grade`, `@pytest.mark.grade`, excluded from `make test`): grade golden
  routes vs a git-tracked baseline; fail on regression. Calibrated only on `Books/` exemplars.
- **Live audit:** periodically grade a sample of served tours for drift.
- **Never** self-tunes objective weights. Changing any weight requires goldens ≥90% overlap **and** a
  non-regressing `tour-grade` **and** a human spot-check.

### 2.8 Output contract — `RouteOption` `[NEW type]`
One per flavour; 2–3 per request. Fields: `route_id`; `stops` (ordered:
`poi_id, name, lat, lng, lens, visit_or_walk_past, minutes`); `stop_audio` (stop_idx→url);
`route_polyline`; `eta_seconds` (honest routed + dwell); `why_this_works` (grounded in computed
`eta_seconds`/`flow_score`/`backtrack_ratio` — never invented); `lens_summary`; `flow_score`,
`backtrack_ratio`; `degraded`; `profiles` (whose lenses); `offline_package` (coords, geofences,
polyline, audio refs for offline replay).

## 3. Objective function

```
value(POI) = importance_tier × richness × lens_adjacency × role_mult          (all factors ≥ 0)
  importance_tier = POI.tier                          ∈ {1..5}
  richness        = log1p(POI.beat_count)             ≥ 0
  lens_adjacency  = 1.0 direct lens hit | 0.6 parent/child 1-hop via IS_PARENT_OF | 0.0 miss
  role_mult       = POI_ROLE_MULTIPLIER[poi_role]     {stop:1.0, setting:0.7, walk_by_only:0.0}

greedy picks argmax  value(POI) / routed_leg_seconds(insertion)   under the time budget, cap 12
```

- **Multiplicative, not additive.** This matches the working engine (`selection.py:1082`) and
  supersedes the additive `λ·lens_adjacency + μ·importance_tier + richness` sketch in `05-plan.md`.
- **Why non-negative / no subtractive edge cost.** Every factor ≥ 0 ⇒ value ≥ 0; cost enters only as
  the positive divisor `routed_leg_seconds`, never subtracted. This is the one correction vs v1 (a
  subtractive `edge_cost` that could go negative). `lens_adjacency` replaces `_interest_bias`
  (`selection.py:1085`) and requires golden re-baselining.
- **arc** = a post-selection reranker over the k finished flavours (uses `flow_score` + beat narrative
  tags to order which flavour leads). Never an edge weight, never in selection/ordering cost.

## 4. Multi-profile + default-lens
- `TourInput.profiles: tuple[ProfileLenses,...] | None` `[NEW]` (`ProfileLenses = {profile_id, lenses}`).
  Existing `lenses` stays the single-profile/default path.
- REACH + SELECT use the **union** of all profiles' lenses (no person geographically excluded);
  `lens_adjacency` scores a POI a direct hit if it matches *any* profile's lens.
- Each of the k flavours is tagged (`RouteOption.profiles`) with which profiles it best serves — the
  party walks together, picks the option that fits.
- **Default-lens fallback:** `profiles` None **and** `lenses` empty → city default lens set; with no
  lenses at all, `lens_adjacency` is uniform 1.0 and selection degrades gracefully to
  importance × richness × role (mirrors today's neutral `_interest_bias` branch, `selection.py:1086`).
  See [[project_multi_person_trips]].

## 5. New contract fields (only additions; every existing field preserved)
| Type | `[NEW]` field | Meaning |
|---|---|---|
| `TransitSegment` | `polyline: str \| None` | encoded leg geometry; `None` on haversine fallback |
| `TransitSegment` | `source: "valhalla"\|"haversine"` | which engine produced walk_seconds/polyline |
| `TransitSegment` | `leg_seconds: int` | routed seconds (vs the existing haversine `walk_seconds`) |
| `Route` | `route_polyline: str \| None` | full-route encoded polyline |
| `Route` | `routed: bool` | True iff every leg came from Valhalla |
| `Route` | `backtrack_ratio: float` | routed length ÷ straight-line span (flow metric) |
| `Route` | `flow_score: float` | monotonic-progress measure for arc reranker + "why this works" |
| `BeatRef` | `source_passage, source_chunk_slug, key_claims` | surfaced for VERIFY (load Cypher must fetch) |
| `GeneratedStop`/`ItineraryStop` | `transit_polyline` (+ provenance) | thread polyline to API + mobile map |
| new types | `RouteOption`, `ReachVerdict`, `ProfileLenses` | §2.8, §2.1, §4 |

## 6. Spy-counter (cost) contract
REACH + SELECT + ORDER + ROUTE = **0** LLM/TTS calls. COMPOSE = **exactly 1** per picked route.
GRADE = **0** calls inside the default `make test`.

## 7. Decided open items (decide-not-defer; flag to change)
1. **Objective = multiplicative** (matches code; supersedes the additive 05-plan sketch).
2. **Golden/audit tests** get a `golden`/`grade` marker, **excluded from the `make test` bar**, run via
   `make tour-grade`/`make test-golden`; the currently-missing `tests/fixtures/tour_golden/` fixtures
   are **created** in M0 (not deferred). Rationale: `make test` only guarantees Neo4j on 7688, and
   conftest turns SKIP→FAIL, so live-DB golden tests must be a separate gate.
3. **poi_role backfill (M0a)** = role *correctness* for the 128 nulls (currently coerced to full-weight
   "stop"): tier ≥ 4 or has an active stop-class beat → `stop`; else `setting`. Never flip the 102
   `walk_by_only`. (Not a zero-score rescue — see §0.)
4. **`TripGenerateRequest`** gains `lenses` + `round_trip`; lens precedence = request → profile
   `PREFERS_LENS` edges → city default-lens set.

## 8. Supersedes
1. **v1 (GDS/Yen's/networkx, subtractive edge_cost).** Retired. Selection is the Orienteering Problem
   (greedy in `select_route`); ordering is exact Held–Karp. No GDS/Yen's/networkx.
2. **The blanket solver-ban in `05-plan.md`.** Refined: OR-Tools/networkx/Yen's stay out, but a bounded
   exact DP (Held–Karp, n≤12) is adopted for ORDER — not a solver dependency, a self-contained DP. The
   additive objective sketch is superseded by §3's multiplicative form. `arc` is adopted as a
   post-selection reranker (not deferred).
3. **The shallow `src/api/crud/trips.py` generator.** Replaced by wiring `src/tour` into the API;
   `apply_golden_ratio` + `compute_schedule` deleted.

**Framing — evolve, not fix (verified):** no broken solver build ever existed; the mature `src/tour`
engine already solves orienteering correctly and is golden-tested. Work = evolve it (lens_adjacency,
RoutingClient, Held–Karp ORDER, COMPOSE/VERIFY/GRADE) + wire it into the API.
