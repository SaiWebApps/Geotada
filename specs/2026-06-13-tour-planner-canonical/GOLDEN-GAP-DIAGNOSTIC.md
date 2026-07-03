# Golden-gap diagnostic (Track B Step B.8)

Date: 2026-07-02. Analysis only — no engine change was made. Environment: live dev graph
(port 7687), Valhalla routing UP (product parity; the haversine fallback reshapes the PdV
route — see §6). Diff tooling: `make golden-diff FIXTURE=<name>` (new target wrapping
`scripts/tour_golden_diff.py`). Per-miss categorization was produced by read-only one-off
scripts replaying `select_route` → `select_poi_beats` → `generate` against the same snapshot
and tracing the greedy, fill-pass, demotion, bucket, cap, dedup and transit-direction decisions.

## 1. Headline numbers (canonical: Valhalla up)

| Golden | Overlap (script-level, the gate) | Diff-CLI (plan-level) | Aspiration |
|---|---|---|---|
| `ile_oneway_90min` | **25/47 = 53.2%** | 25/47 = 53.2% | 0.90 |
| `pdv_round_trip_60min` | **12/18 = 66.7%** | 13/18 = 72.2% | 0.90 |

`make test-golden` (Valhalla up): `2 failed, 7 passed, 1089 deselected in 251.53s` —
"Île golden overlap 53.2% … Hit 25/47", "PdV golden overlap 66.7% … Hit 12/18".
Sensitivity: with Valhalla DOWN (haversine fallback) Île stays 53.2% but PdV falls to
55.6% because the route itself changes (§6.3).

Overlap denominator is the UNIQUE expected-beat set (Île 47, PdV 18): 1 Île beat = 2.13
points, 1 PdV beat = 5.56 points. Extras are not penalized.

Both fixtures already exclude their documented `structurally_unreachable` beats from
`expected_beat_ids` (verified: none of the PdV `structurally_unreachable` ids are in the
expected set) — the 0.90 aspiration is against reachable-in-principle content.

## 2. Category summary

Categories per the B.8 brief: (a) POI absent from corpus, (b) outside the reach corridor,
(c) walk_by_only role exclusion, (d) below the dwell band (future VIGNETTE), (e) beat exists
but beat_select caps/ordering drop it, (f) other.

| Category | Île misses | Île points | PdV misses | PdV points |
|---|---|---|---|---|
| (a) POI/beat absent from corpus | 0 | 0.0 | 0 | 0.0 |
| (b) outside the reach corridor | 0 | 0.0 | 0 | 0.0 |
| (c) walk_by_only role | 0 | 0.0 | 1 | 5.6 |
| (d) below dwell band (vignette-band POI) | 0 | 0.0 | 0 | 0.0 |
| (e) beat_select drop at a visited stop | **22** | **46.8** | 4 | 22.2 |
| (f) generation-stage transit-direction gate | 0 | 0.0 | 1 | 5.6 |
| **Total gap** | 22 | 46.8 | 6 | 33.3 |

The headline finding: **the gap is not corpus coverage and not reach.** Every one of the 28
missed beats exists, is active, and (27 of 28) sits at a POI the engine already visits or
demotes into a visited stop. The gap is per-POI *emission* policy: the single-winner rules
inside `beat_select.py`.

Category (e) decomposes mechanically:

| (e) sub-mechanism (`src/tour/beat_select.py`) | Île | PdV |
|---|---|---|
| SINGLE "no-spatial-key closer" slot (`_order_by_sub_location` / `_order_by_trigger_address` emit exactly ONE beat from the entire no-sub_location / no-trigger_address pool) | 16 | 1 (+2 via demotion, below) |
| One-beat-per-bucket single winner (sub_location / trigger_address bucket) | 2 | 1 |
| `DEFAULT_FLAT_MAX = 8` flat cap (Île de la Cité emits 8 of a 16-beat pool) | 3 | 0 |
| `PAUSE_BEATS_MAX = 3` tier-3 cap (Vert-Galant emits 3 of 5; the missed beat ranks 4th) | 1 | 0 |
| Demoted-POI beats (Musée Victor Hugo → PdV via `apply_co_located_demotion`) losing the same single no-key closer in the merged pool | 0 | 2 |

## 3. Île de la Cité — per-miss list (22, all category e)

Route (Valhalla): Pont Neuf → Vert-Galant → Palais de Justice → Conciergerie →
Sainte-Chapelle → Île de la Cité → Hôtel-Dieu → Crypte Archéologique → Notre-Dame.
Spine `Île de la Cité` (expected). All 8 expected POIs are visited (Palais de Justice is an
extra that carries 3 fixture beats, all hit). The 22 misses are identical under haversine —
they are routing-independent.

| Beat | POI | Mechanism |
|---|---|---|
| 1fbeb1b3, 4cb9c5a0, 519c3460, 5986370c, ad042301, d197b040, ef2eb2f7 | Pont Neuf | lost the SINGLE no-sub_location closer slot (7 fixture beats compete for 1 slot; winner 87c8ae7c) |
| 5fba0650, bc66c5fa, fdfd42f7, fe5b2662 | Conciergerie | lost the SINGLE no-sub_location closer slot (winner b2d711b7) |
| 6c03a747, d0b773ab, d50fb641 | Sainte-Chapelle | lost the SINGLE no-sub_location closer slot (winner 9bf472f0) |
| 182981a8, f95b4b9a | Notre-Dame | lost the SINGLE no-sub_location closer slot (winner 6fd66eb3) |
| 0c35674e | Sainte-Chapelle | lost sub_location bucket `upper-chapel` to 6ae3bf26 (one beat per bucket) |
| 87368cec | Conciergerie | lost sub_location bucket `rue-de-paris-cells` to 63007efd |
| 74f74693, a5bfa6e5, ea2fbd4a | Île de la Cité | `narrative_function` flat cap: plan emits 8 of 16 (DEFAULT_FLAT_MAX=8); these rank 9+ |
| af6c2d1f | Vert-Galant | tier-3 `PAUSE_BEATS_MAX=3`: emits 3 of 5; this deepen ranks 4th |

Dedup caveat inside the 16 no-sub misses: the two bouquinistes beats (ad042301 /
5986370c) are near-duplicates of each other — char-5-gram Jaccard 0.636 vs the 0.30
B8-lite threshold — so even with the closer slot relaxed, B8-lite dedup will (correctly)
collapse one of them. The human-ideal roster contains a near-duplicate pair; that is a
fixture-hygiene observation for the user, NOT something the engine should be re-baselined
around.

## 4. Place des Vosges — per-miss list (6)

Route (Valhalla): Rue Saint-Antoine → Hôtel de Sully → Village Saint-Paul → Place des
Vosges (round trip from the PdV centroid). Spine `Le Marais` (expected). Greedy also
selects Musée Victor Hugo, which `apply_co_located_demotion` then merges into PdV
(96 m apart, name-token overlap) — verified live: `route.demoted_beats["Place des
Vosges"]` contains b76bb264, 0573c615 (both fixture beats) plus 2 non-fixture beats.

| Beat | POI | Category | Mechanism |
|---|---|---|---|
| e73cae91 | Place des Vosges | (e) | no-trigger_address pool (strategy `trigger_address`) emits ONE closer; slot won by f4bc655f (itself a fixture beat — the human ideal wants BOTH climax essays) |
| 838902a8 | Place des Vosges | (e) | trigger bucket `no. 6 place des Vosges` single winner: lost to 8395d3a3 (also a fixture beat — the ideal wants Marion Delorme AND the Hugo anchor at no. 6) |
| b76bb264, 0573c615 | Musée Victor Hugo | (e) | demoted into PdV; both carry no trigger_address, so in the merged production pool they fight for the same single no-key closer slot and lose. Additionally invisible to the golden gate: the golden tests and the diff CLI never merge `route.demoted_beats` (§6.1) |
| b8f7e023 | Rue Saint-Antoine | (f) | IN the plan (Rue St-A plan hits 3/3) but dropped at generation: `nf=transition` beats are filtered from anchor blocks and only emitted by `_build_transit` when the beat text names the adjacent stop (`_find_directional_transit_beat` name-substring check). The beat says "Turn your back on Place de la Bastille…"; neither adjacent stop name appears → suppressed by the geographic-honesty gate. This is also why the diff CLI (plan-level, 13/18) over-reports the gate (script-level, 12/18) |
| 315b87a8 | Restaurant Bofinger | (c) | `poi_role='walk_by_only'` → excluded from the dwell pool by design. Also OFF the engine's legs: the route runs west/north of the start; Bofinger sits ~250 m east by Bastille, so no leg passes near it |

Route-level evidence (why the human ideal's Bastille direction is fragile): under haversine
fallback the greedy spends 626 s of the 1,195 s walk budget detouring to Musée Carnavalet,
saturating the budget (1,187/1,195 s with audio only 1,200/1,793 s), and the fill pass then
skips Rue Saint-Antoine ("extra=314s would exceed walk_cap 1135"). Valhalla's real leg
costs flip that choice and Rue Saint-Antoine gets selected. The PdV overlap is therefore
partly a function of routing state — the golden gate should always run with Valhalla up.

## 5. What single change buys the most?

**Relax the single no-spatial-key closer slot** in `_order_by_sub_location` /
`_order_by_trigger_address` — emit the no-key pool through the same narrative-function
arc used by the flat strategy, bounded by the existing per-POI caps — instead of exactly
one beat. It is worth up to **+31.9 points on Île (53.2% → ~85.1%)** and **+5.6 on PdV
(66.7% → 72.2%)** on its own, with no re-baseline and no gate loosened. (Île arithmetic:
16 closer-slot misses − 1 bouquinistes dedup casualty = +15 beats.) No other single change
is worth more than ~6 points.

Feasibility caveat (must hold before landing): the 22 Île misses total 2,286 words ≈ 15 min
of extra narration. The audio/density feasibility gates must stay green; if they refuse, the
relaxation needs an audio-aware bound (e.g. emit extra closers only while the POI's dwell
allowance has headroom) rather than a blanket cap raise.

## 6. Measurement-fidelity findings (gate under-measures the shipped product)

1. **Demoted-beats blind spot.** The production paths merge demoted beats into the host
   stop's pool before `select_poi_beats` (`src/api/routes/trips.py:201,308`,
   `scripts/tour_build.py:124`); the golden tests (`tests/test_tour_golden_*.py::_generated_beat_ids`)
   and `scripts/tour_golden_diff.py` do not. The golden gate measures a pipeline nobody
   ships. Today this costs 0 points (the merged beats still lose the closer slot), but with
   the §5 change it hides +11.1 PdV points, and any future demotion will silently misreport.
2. **Plan-level vs script-level counting.** The diff CLI counts `plan.beats`; the gate counts
   Script sentences. They differ by generation-stage drops (today: 1 beat, the PdV transit
   direction gate) — the CLI shows 72.2% where the gate shows 66.7%. The CLI should run
   `generate()` and count sentences, matching the gate.
3. **Routing-state dependence.** `test-golden`/`golden-diff` depend only on `db-up`;
   with Valhalla down the PdV route reshapes (55.6% vs 66.7%) while `tour-grade` already
   requires `valhalla-up`. Golden numbers should be quoted (and gated) Valhalla-up only.

## 7. Ranked recommendations

### 7a. Mechanically safe selection changes (no re-baseline, no gate loosened)

| # | Change | Île | PdV |
|---|---|---|---|
| R1 | Multi-beat no-spatial-key emission (§5), within existing caps + audio headroom | 53.2 → ~85.1% | 66.7 → 72.2% |
| R2 | Golden-gate production parity: golden tests + diff CLI merge `route.demoted_beats` like trips.py, CLI counts script-level (§6.1/6.2). Measurement fix, not a re-baseline | — | with R1: → ~83.3% (recovers b76bb264/0573c615; one may still fall to B8 dedup vs the 8395d3a3 Hugo anchor — conservative 77.8%) |
| R3 | Allow a second beat per sub_location/trigger_address bucket when the runner-up is anchor/mid class | → ~89.4% | → ~88.9% |
| R4 | Raise `DEFAULT_FLAT_MAX` 8 → 12 (precedent: 6 → 8 on 2026-04-29), audio-checked | → ~95.7% | — |
| R5 | Raise `PAUSE_BEATS_MAX` 3 → 4 (the Vert-Galant miss ranks exactly 4th) | → ~97.9% | — |

Each step must land atomically with `make test` + `make test-golden` + `make tour-grade`
green (Valhalla up). The ladders are upper bounds; B8-lite dedup and the audio gates may
trim 1–2 beats.

### 7b. NOT mechanically safe (listed so they are not smuggled in)

- Greedy objective / walk-budget re-tuning (would reshape every route in the city; PdV's
  haversine-vs-Valhalla flip shows how sensitive stop choice is).
- Geometry-aware transit-direction check (bearing match instead of name-substring in
  `_find_directional_transit_beat`) — the only way to recover b8f7e023 (+5.6 PdV). Arguably
  a *better* honesty check, but it touches the geographic-honesty gate and needs its own
  adversarial review, not a ride-along.
- Re-baselining fixtures or loosening validation gates: forbidden by the plan.

### 7c. Corpus investment (content pipeline)

- **Nothing is missing.** Categories (a) and (b) are zero in both fixtures; corpus ADDITIONS
  buy 0 points here.
- **Metadata enrichment is the content-side alternative to R1:** the 20 Île+PdV no-key
  misses all carry `sub_location=None` / `trigger_address=None`. Backfilling real
  sub_locations (e.g. Pont Neuf's bouquinistes-quai, Conciergerie's revolutionary-prison
  wing) gives them buckets and they emit under CURRENT rules. Same points as R1, bought
  with pipeline work instead of engine change.
- **Bofinger role decision:** 315b87a8 is unreachable while `poi_role='walk_by_only'` and the
  route never walks rue de la Bastille. Re-tagging is a content/UX decision (the fixture's own
  notes flag the same pattern for Place Dauphine/Mémorial on Île).
- **Fixture hygiene (user decision, not engine):** the Île roster contains a true near-duplicate
  pair (ad042301/5986370c, J=0.636); the engine's dedup is right to collapse it. Worth a
  human pass over the fixture — as a curation act, not a re-baseline to engine output.

### 7d. Expected lift from vignette surfacing already in flight (Track B B.1–B.4)

**≈ 0.0 points on these goldens.** No missed beat sits at a vignette-band POI: category (d)
is zero in both fixtures. The only walk-by candidate (Bofinger) computes band "short"
(t3 spotlight 3.0) because `band_for_spotlight` is role-blind — under B.1's locked
eligibility (`band_for_spotlight(...) == "vignette"`) it is not vignette-eligible either, and
no engine leg passes within 50 m of it anyway. Flag for the B.1 implementer: the
`selection.py` §3 comment ("any walk_by_only POI … band='vignette'") and the role-blind
band computation (`options.py:128`) disagree; B.1 should reconcile whether walk_by_only
POIs are vignette-eligible by role. Even then, PdV would gain at most 1 beat (5.6 pts) and
only if the route shape also changed.

## 8. Honest bottom line vs the 0.90 aspiration

- **Île CAN reach ≥0.90 with mechanically safe selection changes alone** (R1+R3 ≈ 89.4%,
  R1+R3+R4 ≈ 95.7%) — no corpus work required. The binding constraint is the audio
  feasibility budget, not content.
- **PdV cannot reach 0.90 with strictly-safe changes.** R1+R2+R3 tops out ≈ 88.9%
  (conservative 83.3% if dedup collapses one Hugo beat). The last points need either the
  medium-risk transit-direction geometry fix (→ 94.4%) or content decisions (Bofinger role
  → 100%). Neither is corpus ADDITION; both are judgment calls that should be their own
  reviewed steps.
- The 0.90 number itself is sound as an aspiration: nothing in these fixtures is
  structurally unreachable except what the fixtures already document and exclude.

---

## UPDATE 2026-07-02 — pace pin moved the headline numbers (attribution, not re-baselining)

The Valhalla pace pin (`costing_options.pedestrian.walking_speed = PACE_KMH = 3.0`,
this branch) removed a silent inconsistency: routed legs were previously timed at
Valhalla's ~5.1 km/h default while every budget/envelope in the engine assumes
3.0 km/h (§3.2 rule ledger 20-25; live-measured: the same 3.87 km leg times at
2.98 km/h pinned vs 5.04 km/h default). Honest leg costs fit fewer stops per
duration, so the CURRENT overlap numbers move — the fixtures themselves are
unchanged and remain the target:

| fixture | pre-pin (5.1 km/h legs) | post-pin (3.0 km/h legs) | target |
|---|---|---|---|
| `ile_oneway_90min` | 25/47 = 53.2% (9 POIs) | **16/47 = 34.0% (7 POIs)** | 0.90 |
| `pdv_round_trip_60min` | 12/18 = 66.7% (4 POIs) | **10/18 = 55.6% (2 POIs)** | 0.90 |

GRADE stays green (4/4 ≥ baseline). Interpretation: the pre-pin overlaps were
partly INFLATED by under-priced legs — the engine could afford stops a 3 km/h
walker cannot. Two coherent readings for a future calibration pass: (a) the
empirical golden walks imply the human moved faster than 3 km/h effective, so
PACE_KMH itself deserves an evidence-based revisit (the fixtures ARE pace
data); or (b) 3.0 km/h stands and the gap closes via R1 (beat emission),
which this doc already identifies as worth +31.9 points on Île independent of
stop count. Do NOT re-baseline the fixtures to post-pin output.
