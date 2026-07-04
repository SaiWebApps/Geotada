# C9f — per-stop audio emission cap: design v2 (post adversarial panel)

Status: DESIGN (not yet implemented). Supersedes the v1 wrapper design after a
3-model hostile panel (opus/sonnet/fable) **unanimously refuted v1**. This note
records the refutations, what survived, and the revised, decomposed plan.

## The panel verdicts (workflow wzi1e973d, 2026-07-03)

### F1 — Compose seam (opus: BLOCKING; fable: MAJOR, same defect)
`Route.start_anchor_poi_id` / `Route.fixed_end_poi_id` are populated ONLY inside
`select_route`. `/trips/{id}/compose` rebuilds the Route via
`summarise_route(picked)` (trips.py:403), which sets NEITHER. So at compose the
wrapper's `exempt = {start_anchor_poi_id, fixed_end_poi_id} - {None} = ∅`, and a
round-trip is `end=None` → cap ACTIVE → **the start-anchor is capped**. Measured:
PdV generates 26 beats / 1248s (exempt), but composes truncated to
`governor_allowance_seconds(60)=597s` (~12 beats) — a generate-vs-compose
divergence on the tour centerpiece, on the PRIMARY flow. v1 predicted "PdV SAFE,
delta 0"; that is FALSE at compose.

fable's decisive additions:
- Anchors are **per-FLAVOUR** (`select_k_routes` re-runs greedy per flavour, each
  with its own first-seat + pulled endpoint). Per-TRIP persistence caps the wrong
  stop on route_2/route_3. Must persist **per-flavour**.
- Re-deriving the anchor at compose is IMPOSSIBLE: Held-Karp reorders `route.pois`
  (so `pois[0]` ≠ start-anchor), and the Step-4.6 pick-stability contract
  (trips.py:248-251) forbids re-running selection.
- Legacy trips (generated pre-C9f) have NO stored ids → must **fail-OPEN**
  (uncapped), never cap-the-anchor.

### F2 — Demotion-host currency gap (sonnet: MAJOR)
Greedy costs the UNMERGED pool (`planned_capped_audio_seconds` →
`snapshot.beats_for`, selection.py:824). `apply_co_located_demotion` runs AFTER
greedy and `_pick_demotion_host` has ZERO exemption/allowance awareness. Emission
caps the MERGED pool (`build_poi_beat_plans` extends with `route.demoted_beats`).
So for a NON-exempt demotion host, the allowance was sized against the smaller
unmerged pool but caps the larger merged pool → truncates merged content; the
route-level `delivered_thin` sum can mask one clipped stop. Goldens survive only
because PdV/Île demotion hosts happen to be the exempt start-anchor (coincidence).

### What SURVIVED the panel (measured on the live 7687 graph)
- Golden overlap byte-identical under the wrapper: every Île stop far under the
  896s (90-min) allowance (Conciergerie 401s, Notre-Dame 396s, Sainte-Chapelle
  **193s** [v1 said 374 — wrong], Vert-Galant 196s, Palais de Justice 125s, Crypte
  56s, Pont Neuf 162s); PdV's only incidental (Hotel de Sully) 157s vs 597s.
- No A→B leak — production passes `end_is_none=False`; the harness fallback
  (`start_anchor_poi_id is None` on A→B, guarded selection.py:1138) → allowance
  None for all stops.
- Duration back-out `round(err_short_total_seconds(d)/(ERR_SHORT*60))==d` exact
  for d in 30..120.
- No multi-stop collapse — `govern_poi_beats` always keeps `beats[0]`
  (beat_select.py:191).
- CORRECTION: golden delta can only be **0 or negative** (capping is subtractive),
  never "+1" as v1 claimed.

## Revised design (v2)

### Exempt-identity, now compose-safe (fixes F1)
- Populate `Route.fixed_end_poi_id` (exists, contract.py:256) and NEW
  `Route.start_anchor_poi_id` in `select_route`.
- At generate, persist **per-flavour** `{poi_ids, start_anchor_poi_id,
  fixed_end_poi_id}` into `options_json` (trips.py:262) — richer than today's bare
  id list.
- At compose, `model_copy` the picked option's two ids onto the
  `summarise_route`-rebuilt Route BEFORE the wrapper runs.
- **Legacy fail-open**: an options entry lacking anchor ids (any pre-C9f trip)
  composes UNCAPPED (allowance None for all stops). Never cap-the-anchor.

### Demotion host (mitigates F2)
- Cap the MERGED pool to the per-stop allowance — product-correct: one incidental
  STOP gets one allowance; a demoted sibling shares the host's stop budget, it does
  not earn its own.
- The dropped overflow is NOT lost: it flows to `ScriptPOI.overflow_beat_ids`
  (keep-exploring extras). Therefore **C9f and C9g SHIP IN ONE RELEASE** (ratified,
  DESIGN-AND-CRITIQUE.md:90) so demoted overflow is surfaced, never silently
  dropped. Re-baseline goldens once, at that release.
- Residual (documented, deferred): greedy costs the host on its unmerged pool, so
  it may under-cost a demotion host and seat one extra stop — a selection-QUALITY
  wrinkle, not a reporting-HONESTY bug once `delivered_thin` measures capped
  emission. The chicken-and-egg "demote-before-cost" restructure stays deferred.

### Honest reporting (judge hard-gate)
- Move `delivered_thin` (selection.py:1268-1277) to measure the CAPPED emitted
  audio, closing the two-currency conflation (v1 audit measured allowance=None).
- `govern_poi_beats` keeps `beats[0]`, so capping can never drop a stop → the
  `len(pois) >= 2 OR tourability set` invariant is structurally preserved.

## Atomic decomposition (each step: own tests + judge + goldens)

- **C9f-i (plumbing, emission byte-identical):** add + populate
  `start_anchor_poi_id`/`fixed_end_poi_id` on Route; per-flavour options_json;
  restore at compose; route ALL six build sites through a new
  `build_poi_beat_plans_capped` wrapper that currently returns the FULL plan +
  empty overflow (NO cap yet). This also fixes the compose non-merge latent bug
  (compose now merges demoted beats via the shared helper). Prove: goldens
  byte-identical; a compose-path test that PdV retains all beats and the restored
  route carries the right anchor ids; full bar.
- **C9f-ii (the cap):** enable the allowance cap for non-exempt end=None stops in
  the wrapper; `delivered_thin` on capped emission. Prove: goldens still
  16/47 · 10/18 (measured safe); compose PdV retains all 26 beats (exempt);
  demotion-host truncation battery; A→B byte-identical; full bar.
- **C9g (overflow surfaced):** thread the wrapper's overflow tuple →
  `ScriptPOI.overflow_beat_ids`. Ships with C9f-ii (same release) so demoted
  overflow becomes keep-exploring extras. Re-baseline goldens ONCE here if needed.

## Test seams the panel demands (do not skip)
- compose-path: composed PdV beat count == generated PdV beat count (end=None).
- legacy-options compose: an options entry without anchor ids composes uncapped.
- demotion battery: no NON-exempt demotion host has its merged pool truncated
  without its overflow being surfaced (once C9g lands).
- duration back-out unit: `round(err_short_total_seconds(d)/(ERR_SHORT*60))==d`
  for golden durations.
- start-anchor invariant: `route.start_anchor_poi_id in {p.id for p in route.pois}`
  for every end=None route.
