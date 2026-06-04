# 04 — Red Team: Tour-Build Harness Spec

> **Date:** 2026-06-02 · **Stage:** 4 (Red Team) · **Thinking mode:** Adversarial reviewer
>
> Independent adversarial pass by the challenger agent. Resolutions proposed inline; user-call items surfaced in §3.

---

## 1. Blockers

All blockers below have proposed resolutions. Resolutions land in Stage 5 (implementation plan) — they don't require 02-spec.md churn.

### B1. `Route.stops[].role` enum is fictional

Spec declares `role: "anchor" | "content" | "mood_pacing" | "segment"`. Reality (`src/tour/contract.py:55`, `selection.py:334`): POI carries `poi_role` defaulting to `"stop"`, with `"walk_by_only"` as the only special value. The `mood_pacing` / `segment` / `content` taxonomy doesn't exist anywhere.

**Resolution:** Derive `role` at the API serializer boundary from `(is_user_anchor, poi_role, tier)`:
- `is_user_anchor=True` → `"anchor"`
- `poi_role="walk_by_only"` → `"walk_by_only"` (rename `segment` to this in spec)
- `tier ≥ 4` → `"anchor"` (per rule B2 — T5 POIs on path)
- `tier ≤ 2` AND not user anchor → `"mood_pacing"`
- else → `"content"`

Document the derivation in Scope 3. The enum stays in the API contract; the *source* is computed, not stored.

### B2. `importance_tier` is `tier` in code

Spec uses `importance_tier`; codebase uses `tier` (`contract.py:54`). Cypher returns `p.importance_tier AS tier`.

**Resolution:** Rename to `tier` in the API response and update the example.json. Match the model.

### B3. `glue_id` namespace is fiction

Spec invents `glue_id` values like `"transit_short"`, `"scene_setter_short"`. Codebase: `Sentence.source_id` already carries either a beat UUID or one of `{GLUE_NAV, GLUE_STAGING, GLUE_PACING, GLUE_CALLBACK, GLUE_CLOSING, ARITH, SYNTHESIZED_OPENER}` (`generation.py:67`). The spec's parallel namespace breaks source-traceability ([[feedback_tour_source_traceability]]).

**Resolution:** Replace `{source, beat_id, glue_id}` with `{source_id, source_type}` matching `Sentence`. `source_type ∈ {"beat", "glue", "synth"}`; `source_id` is either a beat UUID or a whitelisted glue category. Regenerate example.json to match.

### B4. Example.json is internally inconsistent with its own contract

The `per_segment` beat (line 280) omits `narrative_function`; the Notre-Dame per-stop beats omit `source`. Mixed schemas in the same file.

**Resolution:** After B1–B3 land, regenerate example.json end-to-end. One pass, one shape.

### B5. `tour_name` doesn't exist in current `generate()`

`Script` (`contract.py:244-259`) has no `tour_name` field. Spec invents it.

**Resolution:** Add to Scope 3 task list: compute `tour_name = f"{dominant_lens_label}: {anchor_name}"` post-hoc at the API boundary, where `dominant_lens` is the lens with the highest summed `lens_density` across the chosen stops, **excluding** `hidden_history`. **Fallback rule:** if all selected lenses are `hidden_history` (or all-excluded), `tour_name = anchor_name` alone.

### B6. `silence_pct ≥ 0.6` references undefined `total_tour_sec`

Formula uses `total_tour_sec` which isn't on the response shape. Walking time alone undercounts; dwell time matters.

**Resolution:** Define `total_tour_sec = total_walking_time_sec + sum(stop.dwell_sec)` and expose it on the ScriptPlan. `dwell_sec` per stop is derived in Scope 2 from `visit_mode` (see B11). The 0.6 floor becomes an advisory `warnings[]` entry, not a hard 422 — see §3 Q3.

### B7. AC-3 OSRM-down test understates the triple-fallback chain

The matrix → live OSRM → haversine chain has three failure surfaces. AC-3 as written can pass while the matrix path is silently broken.

**Resolution:** Split into:
- **AC-3a:** OSRM container stopped, matrix loaded → `routing_mode_summary` shows mixed `{matrix: N, fallback: M}` where N counts POI-POI segments and M counts arbitrary-start segments
- **AC-3b:** Matrix file absent at startup → `live_osrm: all` with a startup-warning log
- **AC-3c:** Both down → `fallback: all`, route still returns 200, warning logged

### B8. `route_id` determinism vs. Haiku non-determinism

Spec claims `route_id` is deterministic. `/build-script` calls `HaikuGlueClient.stitch()` (`glue_client.py:104`) which hits the Anthropic API — non-deterministic.

**Resolution:** Two-layer claim:
- `route_id` is deterministic (planner output is pure)
- ScriptPlan is **not** claimed deterministic; AC-2 asserts structural properties only (per_stop length, anchor stop has ≥1 beat, total_audio_sec within tier floor band)
- API supports a `glue_mode: "haiku" | "template" | "mock"` query param; tests default to `"mock"` (uses MockGlueClient already in code); harness defaults to `"haiku"`

### B9. Five make targets don't exist

`make matrix-build paris`, `make osrm-up`, `make osrm-down`, `make api-up`, `make frontend-up` are all cited in verification commands but absent from the Makefile.

**Resolution:** Each scope's "What" section adds the targets it introduces:
- Scope 1: `osrm-up`, `osrm-down`, `matrix-build`
- Scope 3: no new target (reuses existing `make api`); fix verification command to `make api`
- Scope 4: adds `frontend-up` (`python -m http.server 8001 --directory frontend`)

### B10. Scope 2 CLI verification uses flags the script doesn't accept

`scripts/tour_build.py` argparse currently parses `--start, --duration, --lenses, --round-trip, --theme, --city-slug` (`tour_build.py:215-232`). Verification command invokes `--anchor`, `--optional`, `--visit-mode`.

**Resolution:** Add to Scope 2's "What": update `scripts/tour_build.py` argparse to accept `--anchor` (required), `--optional` (repeatable, ≤2), `--visit-mode KEY=VALUE` (repeatable). Document in the script's `--help`.

### B11. `walk_past` vs `stop_visit` has no algorithm behavior defined

The field is in the contract; the dwell math doesn't change for it.

**Resolution:** Add to Scope 2:
- `stop_visit`: tier-default dwell from `selection.py` constants (unchanged from today's per-tier behavior)
- `walk_past`: dwell clamped to ≤60s; `beat_select` filters to beats with `narrative_function ∈ {establishing, transition}` only (no deepen, no climax) — the walker doesn't stop long enough for the long-form content

This makes the field functionally meaningful, not decorative.

### B12. `lens_density` per-POI requires data not currently aggregated

`select_route()` returns a single `matching_lens_beat_count` per POI, not a per-lens breakdown.

**Resolution:** Compute `lens_density: {lens_name: int}` at the API serializer boundary as a post-pass over `BeatRef.lenses` (already loaded into the corpus snapshot). No Cypher change. Cheaper than the alternative.

---

## 2. Risks

**R1. Matrix size at corpus growth.** Likelihood: high in 12 months. 500 POIs = 250k pairs (~MB); 5,000 = 25M pairs (~GB). **Mitigation:** Scope 1 designs the file format with a "warm core / cold tail" split — dense for tier 1–3 candidate-anchors; compute tier 4–5 on demand. Document the 100MB ceiling check.

**R2. OSRM "foot" profile accuracy across Île de la Cité bridges, Tuileries interior, Louvre courtyards.** Likelihood: medium. Default profile sometimes routes pedestrians via highway shoulders; pedestrian-only paths can be mapped inconsistently in OSM. **Mitigation:** Scope 1 adds a smoke check on five canonical Paris routes (Concorde→Notre-Dame, Sacré-Cœur→Pigalle, Marais→Pantheon, Louvre interior, Pont Neuf crossing); flag any >25% deviation from Google Maps walking ground-truth.

**R3. `algorithm_estimate_min` vs. `real_walking_min` delta has no defined threshold for "too far off."** **Mitigation:** Scope 4 defines banner colors: green <10%, yellow 10–25%, red >25%. Otherwise the field is decorative.

**R4. 88-test silent shift after re-baseline.** Likelihood: medium. Exact-integer assertions break loudly; range assertions (`200 < walk_sec < 400`) may pass with a wrong-but-overlapping answer. **Mitigation:** Scope 1 task: grep numeric assertions in `tests/test_tour_*.py`; list every range bound in the PR description with justification for keeping it.

**R5. `dominant_lens` fallback for all-`hidden_history` selection.** Resolved by B5 fallback rule (use anchor name alone).

---

## 3. Open Questions

These three are genuinely user-call. Everything else from §1 has a proposed resolution.

**Q1. Matrix rebuild trigger.** Recommend on-demand `make matrix-rebuild` only — auto-rebuild on every corpus upload stretches the NORTHSTAR "Pipeline automation deferred" boundary (line 64). Confirm.

**Q2. Auth on new endpoints in dev.** Spec said "dev-permissive, production-gated later." Challenger flagged this against SECURITY §3. Two paths:
- (a) Keep dev-permissive; add a `# DEV ONLY — DO NOT DEPLOY WITHOUT AUTH` banner in the response headers + a Stage-6 launch-gate item
- (b) Add a simple `X-Dev-Token` header check now (token from env var; harness reads same env var). 30 min of work; closes SECURITY §3.

Recommend (b). Cheap and closes the audit gap.

**Q3. `silence_pct < 0.6` enforcement.** Hard 422 or advisory warning?

Recommend advisory `warnings[]` entry. Aligns with the OSRM-fallback pattern; the harness chooses how to surface. Hard 422 would block legitimate thin-corpus tests.

---

## 4. Codebase Conflicts

| Spec calls it | Code calls it | Resolution |
|---|---|---|
| `time_budget_min` | `duration_min` (contract.py:22) | Use `time_budget_min` at API boundary; map to `duration_min` internally. Document in Scope 3. |
| `start: {lat, lng}` | `start: tuple[float, float]` (contract.py:20) | API serializer translates dict ↔ tuple. Scope 3. |
| `stops` | `Route.pois` | Translate in API serializer. Scope 3. |
| `segments` | `Route.transits` | Translate in API serializer. Scope 3. |
| `per_stop[].beats` (grouped) | `Script.script: tuple[Sentence,...]` (flat) | Group by `Sentence.stop_idx` in API serializer. Scope 3. |
| `per_segment` flavor | `_TRANSIT_NARRATIVE_FUNCTIONS` exists (generation.py:498) but emission path unclear | Scope 3 verifies generation.py actually emits transit sentences for walking segments; if missing, this becomes a deferred Scope 5+ enhancement, not a blocker. |
| `scripts/tour_build.py` changes | Existing flags will keep working — add new ones additively | Documented in B10. |

---

## 5. North Star Check

- **Beat-level vs POI-level gravity** (NORTHSTAR line 36): `lens_density` is a *derived* diagnostic, not a ranking change. Beat-level ranking inside `select_route()` is unchanged. **Clean.**
- **Manual JSON upload / pipeline automation deferred** (NORTHSTAR line 64): Spec language "rebuild becomes a step in the corpus upload pipeline" (01-scope.md:13) stretches this. **Resolution (per Q1):** matrix rebuild is a separate `make matrix-rebuild` step run by the operator after upload, not bundled into upload. Update 01-scope.md after red-team approval.
- **Schema v3** (line 34): no new node types. **Clean.**
- **Hidden_history corpus share** (22%): tour-naming exclusion handled by B5 fallback rule.
- **Beat budget per (lens, sub_location)** (line 35): unaffected. **Clean.**

---

## 6. Scope Review

### Scope 1 (Production Routing Infrastructure)
- `make matrix-build paris` and `make osrm-up`/`down` don't exist → resolved by B9.
- `make test 2>&1 | tail -3` violates CLAUDE.md spirit on piping make output. **Fix verification:** `make test && echo OK`.
- AC-6 says p99 <1ms but verification doesn't measure it. **Add:** `python -c "import timeit; ts = timeit.repeat(lambda: m.lookup(...), number=10000, repeat=10); print(f'p99_us={max(ts)*100:.2f}')"`.

### Scope 2 (TourInput Extension)
- CLI flags don't exist → resolved by B10.
- `pytest -k 'pattern'` returns exit 0 with `collected 0` — false-green risk. **Fix verification:** `pytest -k '...' --maxfail=1 -v && pytest -k '...' --co -q | grep -c 'test_' | xargs -I{} test {} -gt 0`.

### Scope 3 (Tour-Build HTTP API)
- `make api-up &` doesn't exist; use `make api` (existing).
- `-d @file:plan_route_request` curl syntax is invalid. **Fix:** `jq '.plan_route_request' specs/.../02-spec-example.json > /tmp/req.json && curl -d @/tmp/req.json ...`.

### Scope 4 (HTML Test Harness)
- "Open URL and look" not auditable. **Resolution (deferred to user choice):** add a Playwright smoke test in `tests/test_harness_smoke.py` that loads the page, asserts 16 lens options, draggable start pin, mock-API call resolves. If user prefers pure-manual, document explicitly.

### Parallelization
Scope 4 could run against a mocked API in parallel with Scope 3 *if* Scope 3's day-1 task is locking Pydantic models. Worth ordering for time savings; not required.

---

## 7. Best Practices Audit

### A) SECURITY_PRIVACY_PRACTICES.md

| Section | Status | Note / Resolution |
|---|---|---|
| §3 AuthN/Z | **Open (Q2)** | Recommend `X-Dev-Token` (cheap close) — user call. |
| §7 Logging PII | **Fix in Scope 1** | distance.py fallback warning will log start-pin coords. Coords are GDPR PII. **Resolution:** log `(nearest_poi_id, fallback_reason)` instead of raw lat/lng for arbitrary-start fallbacks. |
| §11 Input validation | **Fix in Scope 3** | Pydantic at boundary: `time_budget_min: ge=30, le=600`; `optional_pois` dedup (anchor in optional → 400); `visit_modes` keys must be subset of `{anchor} ∪ optional_pois` (else 400). |
| §12 Network | **Fix in Scope 1** | OSRM container bound to `127.0.0.1:5000:5000` in compose, not `0.0.0.0`. |
| §7 Rate limiting | **Fix in Scope 3** | `/build-script` calls Anthropic per request → cost risk. Add per-IP limit (10/min) via FastAPI-limiter, even in dev. |
| §11 Error leakage | **Acceptable in dev** | 404 "POI not in corpus" enumerates corpus. Flag for production-gate scope, not this one. |
| §13 CORS | **Fix in Scope 3** | Restrict to `http://localhost:8001` (harness origin); no wildcard. |

### B) Performance / UX

- **Matrix-load failure** → API should still start in degraded mode (`load_matrix()` returns None, logs WARNING; routes check and fall back). Add to Scope 1.
- **OSRM polyline LRU cache** keyed by `(from_poi_id, to_poi_id)`, TTL 1h — saves repeated calls during harness iteration. Add to Scope 1.
- **Harness error recovery for 422** — banner with min_required vs budget + "increase budget" CTA. Add to Scope 4.

---

## User Resolutions (2026-06-02)

All four open items resolved per challenger's recommendations:

| Q | Decision | Lands in |
|---|----------|----------|
| **Q1 (matrix rebuild trigger)** | On-demand `make matrix-rebuild` only. Operator runs after corpus changes. Aligns with NORTHSTAR's "Pipeline automation deferred" boundary. | Scope 1 task list |
| **Q2 (dev auth)** | Add `X-Dev-Token` header check on `/tours/plan-route` + `/tours/build-script`. Token from env var; harness reads same env var. Closes SECURITY §3. | Scope 3 task list |
| **Q3 (silence_pct < 0.6)** | Advisory `warnings[]` entry only — 200 still returned. Matches OSRM-fallback pattern. Does not block thin-corpus exploration. | Scope 3 task list |
| **Scope 4 verification** | Add Playwright smoke test in `tests/test_harness_smoke.py`: page loads, 16 lens options, draggable start pin, mock-API call resolves. Auditable. | Scope 4 task list |

## What lands in Stage 5

Stage 5's implementation plan will reflect:

**Contract corrections (B1–B6, B12, codebase conflicts §4):**
- API serializer translates code names (`tier`, `pois`, `transits`, `duration_min`, `tuple start`, `Sentence.source_id`, `Script.script` flat list) to spec names (`tier` — match code, `stops`, `segments`, `time_budget_min`, `{lat,lng}` dict, `source_id`+`source_type`, grouped `per_stop[].beats[]`). Field renames documented in code comments at the serializer boundary.
- `role` derivation rule (B1): `(is_user_anchor, poi_role, tier) → role` mapping.
- `tour_name` post-hoc compute (B5): dominant lens excluding `hidden_history`, fallback to anchor name alone.
- `lens_density` post-pass (B12) from `BeatRef.lenses` — no Cypher change.

**Algorithm behavior (B11, R5):**
- `walk_past` clamps dwell to ≤60s, filters beats to `establishing/transition` narrative functions only.
- `stop_visit` uses tier-default dwell (unchanged).

**Infrastructure (B7, B8, B9):**
- AC-3 split into AC-3a/b/c (three failure surfaces of the matrix → OSRM → haversine chain).
- AC-2 asserts structural properties only; `glue_mode` query param defaults to `"mock"` in tests, `"haiku"` for harness.
- Five make targets added per scope (B9).

**Security (§7 audit):**
- PII-safe fallback logging (nearest_poi_id, not raw coords) — Scope 1.
- Pydantic input validation completeness — Scope 3.
- OSRM bound to `127.0.0.1:5000` — Scope 1.
- Per-IP rate limit (10/min) on `/build-script` to cap Anthropic spend — Scope 3.
- CORS allowlist for `http://localhost:8001` only — Scope 3.

**Verification command fixes:**
- Replace `make test 2>&1 | tail -3` with `make test && echo OK` — Scope 1.
- Replace `make api-up &` with `make api` — Scope 3.
- Fix curl `-d @file:path` syntax via jq intermediate file — Scope 3.
- Add p99 timing measurement — Scope 1.
- Pytest false-green guard via `--co` count check — Scope 2.

**Risks tracked, not solved in this scope:**
- R1 corpus-growth matrix split → deferred until corpus exceeds 1,000 POIs
- R2 OSRM Paris-foot accuracy → smoke check added to Scope 1
- R4 silent test-range shifts → Scope 1 PR description lists every range bound

Red-team artifact locked. Advancing to Stage 5.
