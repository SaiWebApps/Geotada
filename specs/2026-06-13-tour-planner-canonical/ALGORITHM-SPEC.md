# Ondoway Tour-Generation Algorithm — Canonical Spec

> **Status: CANONICAL (2026-06-13).** The single source of truth for how Ondoway turns a request
> into a narrated walking tour. Implementation steps + per-step tests live in
> `IMPLEMENTATION-PLAN.md` (same folder). This doc is the stable *what/why*; the plan is the living
> *how/when*.
>
> **Supersedes** (see §11): `ondoway-tour-algorithm.html` (the "v2/netlify" doc),
> `specs/2026-05-23-tour-planning-algorithm/*` (the rule-forward engineer spec),
> `specs/2026-06-10-tour-5phase-engine/05-plan.md` (the solver-ban 5-phase plan), and
> `specs/2026-06-12-tour-algorithm-decision/*` (the prior canonical, now folded in here).
>
> **How to read this:** this doc describes the **target** design; `IMPLEMENTATION-PLAN.md` is a
> **forward plan of unbuilt work**. The code does **not** yet implement most of this — building it *is*
> the plan. "Field/endpoint/function X is not in the code yet" is therefore the *work*, not a defect.
> §8 records the verified *current* state so target and present aren't confused. The four canonical UX
> examples (Eiffel→Arc with a reflection, open-ended, loop, refusal) describe the **complete
> post-Phase-4 product**; earlier phases deliver subsets.

---

## 0. The goal — one paragraph

A user asks for a walk **from A to an optional B**, for a **time budget**, optionally through a chosen
**lens**. Ondoway returns a small set of **route options**; the user picks one; we then compose a
single **continuous, grounded, narrated story** for that route — taking them past interesting places
along the way, **stitching the corpus beats together**, and filling dead air with **reflections** that
synthesize what's been seen so far. **The route serves the story. The lens sets the genre.**

Three product commitments fall out of that sentence, and they are the things the prior specs lost:

1. **A→B directionality** (B optional) — the planner is directional, not "wander out from A."
2. **The story actually reaches the user's ears** — narration is composed *and voiced*, not computed
   and discarded.
3. **Lens is genre/tone, not a filter** — nothing is excluded on lens alone; lens allocates spotlight.

---

## 1. Inputs — `TourInput`

| Field | Status | Meaning |
|---|---|---|
| `start: (lat, lng)` | exists | origin A (live GPS for "tour now") |
| `end: (lat, lng) \| None` | **NEW** | destination B; `None` = no fixed destination |
| `duration_min: int` | exists | time budget (the hard constraint) |
| `city_slug: str` | exists | corpus scope |
| `lenses: list[str] \| None` | exists | the **genre/tone**; `None`/empty = unbiased |
| `round_trip: bool` | exists | return to A; mutually exclusive with a user `end` |

`lenses` values are the canonical taxonomy (21 lenses, verified `src/schema/definitions.py`):
`dark_history, famous_residents, film_tv, hidden_history, historic_arch, historic_cuisine,
historic_markets, historic_worship, literary_heritage, local_legends, markets_street_food,
modern_design, music_heritage, parks_gardens, sacred_traditions, science_tech, social_change,
street_art, visual_art, war_conflict, waterways_views`.

---

## 2. The planning model — the time-ellipse corridor

The route is the classic **Orienteering Problem with fixed start and end**: choose a budget-bounded
*subset* of places that maximizes value, walking A → … → B. The reachable region is the **time-ellipse
with foci A and B**:

```
reach(A→B) = { poi : t(A, poi) + t(poi, B) ≤ T_walk_budget }
```

where `t(·,·)` is the routed pedestrian time (Valhalla; pace-corrected haversine fallback). A POI's
**cost to include** is its *marginal detour*: `t(A,poi) + t(poi,B) − t(A,B)`. Places on the A–B line
have tiny detour cost, so directional weighting is *intrinsic* — no separate "cone" or "directional
weight" hack.

**One algorithm, three cases:**

| Case | B | Region | Ordering end |
|---|---|---|---|
| Directional | user-given | ellipse(A, B) | `fixed_end = B` |
| Open walk | none, `round_trip=false` | ellipse(A, B*) where **B\*** = best far anchor (endpoint-pull) | `fixed_end = B*` |
| Loop | none, `round_trip=true` | ellipse degenerates to circle(A) | closed tour, ends at A |

**Feasibility gate (one comparison, before any selection/LLM/TTS):** if `t(A,B) > T_walk_budget`, the
A→B walk cannot be done in the time given — **refuse** with **computed** alternatives, not canned text:
(a) *extend to* `TourabilityAssessment.max_supportable_duration_min` (the density module already
computes this field); (b) *drop B and loop* from A within budget; (c) *closer B* = the highest-spotlight
anchor B′ within a **±45° wedge** of the A→B bearing (Euclidean) with `t(A,B′) ≤ T_walk_budget` (if the
wedge is empty, the highest-spotlight anchor within budget regardless of bearing). This is the original spec's Rule F1 as
a single cheap check. It surfaces as **HTTP 422** with a structured body
`{reason, gap_minutes, alternatives: [{kind: "extend"|"loop"|"closer_b", ...}]}` — never a bare error.

**B\* (the open-walk endpoint) is the EXISTING endpoint-pull, not new code:**
`_apply_endpoint_pull` (`src/tour/selection.py`) already selects the far high-value anchor and pins it
as `fixed_end`. The open-walk case reuses it verbatim; the corridor (ellipse) filter activates **only
when a destination exists**, so the `end=None` path stays byte-for-byte today's behavior. (An open walk
**ends at B\*** — it does **not** loop back to A; returning to A is the separate round-trip case.)

---

## 3. The spotlight model — lens sets the spotlight, never the gate

> Decided 2026-06-13 (user): **lens is genre/tone, not a filter.** Replaces both the hard tier gate
> and the hard lens-miss exclusion in the current `SELECT` (`ANCHOR_TIERS={3,4,5}` filter
> `selection.py:553`; lens-miss exclusion `selection.py:559`).

Every POI in the corridor is **eligible**. A single continuous **spotlight score** decides how much of
the user's time and audio each one gets:

```
spotlight(poi) = gravity(poi.tier) × lens_relevance(poi, lenses) × proximity(poi, route)
  gravity        ∝ importance_tier (1..5)
  lens_relevance = 1.0 direct lens hit | 0.6 parent/child 1-hop | LENS_FLOOR (= 0.25) miss
                   (no lenses → uniform 1.0)
  proximity      = on-path bonus; falls with marginal detour off the A–B line
```

`lens_relevance` has a **positive floor** — a lens miss *dims*, it never *zeroes*. Spotlight maps to an
output band:

| spotlight band | output |
|---|---|
| highest | **headline dwell** — full composed narration + a reflection |
| high | **full stop** — expanded narration |
| mid | **short stop** — a beat or two |
| low (above floor) | **walk-past vignette** — one line as you pass (the "Phase 3 enrichment" never built) |
| below floor | **silent** — skipped *for this user* |

**The only silence is low-gravity AND off-genre.** Lens alone never silences a landmark on the user's
path (a tier-5 off-genre POI still clears the floor on gravity → at least a brief mention). Lens
*promotes* too: a tier-2 oddity that nails the genre earns a real stop.

**"Never exclude" means never exclude from *eligibility/mention* — not "stop everywhere."** Time is
finite, so spotlight *allocates* scarce dwell-minutes; it does not abolish selection. Band boundaries
(silent / vignette / short / full / headline) are set during the **Phase-3 golden re-baseline**, not
guessed here. The one fixed invariant: a POI is silent only when it is **both** below `LENS_FLOOR` on
lens **and** low on gravity — lens by itself can dim a POI to a one-line vignette but never to silence.

This unifies the two prior gates into one knob and produces the **two-track** output (dwell stops +
walk-past vignettes) as bands of the same score — no separate machinery.

### 3.1 Honest constraint — tone is bounded by corpus coverage

Beats are **pre-written and grounded**; `VERIFY` blocks invented facts. So lens can re-frame a POI only
where the corpus *has a beat in that lens*. Verified corpus reality (Paris, 1,562 beats): `war_conflict`
= 75 beats city-wide; tails are tiny (`film_tv` = 4, `street_art` = 2). Therefore:

- **Spotlight (how much time) by lens — fully deliverable now.**
- **Tone (how we narrate) by lens — only where a beat in that lens exists.** Elsewhere we narrate the
  POI through its *available* beat and let the lens shape only the LLM-written framing/transitions —
  never invent a fact.
- **REACH measures per-corridor lens coverage and surfaces it** ("only 2 places on this route speak to
  film & TV — broaden?") instead of silently shipping an off-tone tour. *(Delivered in Phase 3 with the
  spotlight model — see §5; preview before then omits the coverage note.)*

Forward path (corpus investment, upstream in the workbench): multi-lens beats per anchor make full
genre re-framing real. **The algorithm here is forward-compatible** — build "never exclude, lens =
spotlight" now; quality deepens as coverage grows.

---

## 4. The seven layers (deterministic spine; LLM/TTS in COMPOSE only)

```
TourInput (start, end?, duration_min, lenses?, round_trip)
  ▼ REACH    time-ellipse corridor (Valhalla isochrones from A and to B; analytic ellipse fallback).
  │          density gate → standard/ambient/redirect/refuse. Measure per-corridor lens coverage.
  ▼ SELECT   spotlight orienteering: every corridor POI eligible; pick the dwell-set by spotlight /
  │          marginal-detour-seconds; tag the low-band on-path POIs as vignettes. k flavours via
  │          diversity penalty. (NO tier gate, NO lens gate.)
  ▼ ORDER    exact open-path Held–Karp, fixed_start=A, fixed_end=B (or B*); round_trip closes the loop.
  ▼ ROUTE    one RoutingClient (Valhalla pedestrian, haversine fallback) → routed leg_seconds + polyline.
  │          SAME measurement feeds the corridor, the detour cost, the order, and the drawn path.
  ── preview ── returns k RouteOptions (cheap: stops, vignettes, polyline, honest ETA, why). NO LLM/TTS.
  ▼ COMPOSE  (fire-once, on the PICKED route only) constrained Anthropic tool-use → one continuous
  │          narration, every sentence source-attributed; reflections injected on long legs. → TTS per stop.
  ▼ VERIFY   provenance (rapidfuzz) + faithfulness (entailment). GATES audio: fail → one bounded
  │          recompose → else refuse the flavour.
  ▼ GRADE    CI regression gate (excluded from `make test`) + live audit. Never a per-request loop.
```

LLM/TTS calls: REACH+SELECT+ORDER+ROUTE+preview = **0**. COMPOSE = **exactly 1** per picked route.
GRADE = **0** inside `make test`.

---

## 5. Two-step request flow — preview → compose

Because narration is LLM-composed and we spend **only on the picked route** (decided 2026-06-13), the
all-in-one endpoint splits. This **maps onto UI that already exists** (today's "Confirm & Prepare"
deferred-audio step):

1. **`POST /trips/preview`** — REACH→SELECT→ORDER→ROUTE for k flavours. Returns 2–3 `RouteOption`s:
   ordered stops + vignettes, polyline, honest routed ETA, lens summary + **per-corridor lens coverage
   note** *(coverage note ships with the spotlight model in Phase 3; preview before then omits it)*, and
   a *deterministic* "why this works" (a templated line from the computed `eta_seconds` / `flow_score` /
   `backtrack_ratio` — never LLM-written). **Zero LLM, zero TTS.**
2. **`POST /trips/{id}/compose`** (chosen `route_id`) — fire-once COMPOSE → VERIFY (gate) →
   recompose-once-or-block → TTS the composed per-stop narration → persist + serve.

The mobile flow gains a **flavour picker** between the two; everything downstream of "pick" is the
upgraded "Prepare" step.

**Phasing (resolves a spec/plan timing trap):** this two-step split **and** the `lens_coverage_note`
are delivered in **Phases 3–4** (see the plan), not Phase 2. Until then the existing single
`POST /trips/generate` stands. The preview contract above is the *target* state — Phase 2 adds
directionality to the existing endpoint; the preview/compose split and the coverage note come later.

---

## 6. Reflections — filling time, grounded

A reflection is a short synthesis of **what has already been visited**, authored at COMPOSE time from
the **union of the visited beats' `key_claims`** (so it recombines verified facts — `VERIFY` still
bites). It is a new whitelisted glue token `GLUE_REFLECTION` (alongside the existing
`GLUE_NAV/STAGING/PACING/CALLBACK/CLOSING`).

When it fires: compute the **audio deficit** ≈ `walking_seconds − sum(beat_audio_seconds)`. Distribute
reflections across the **longest legs** and at natural genre beats. Reflections honor the lens (a
`war_conflict` walk gets a war-themed synthesis). They are the clearest payoff of the LLM-composed
narration choice — a template cannot write them.

**Placement defaults (finalized when Phase 4 is atomized):** a leg is reflection-eligible when its
walking time exceeds its beat-audio by ≥ ~90s; cap ≈ 1 reflection per ~2 stops to avoid over-narration;
every reflection sentence must entail from the union of visited `key_claims` or VERIFY drops it.

---

## 7. Contract deltas (additive; every existing field preserved)

| Type | `[NEW]` field | Meaning |
|---|---|---|
| `TourInput` | `end: tuple[float,float] \| None` | optional destination B |
| `RouteOptionStop` | `band: "dwell" \| "vignette"` | spotlight output band |
| `RouteOptionStop` | `spotlight: float` | the computed score (for "why" + audit) |
| `RouteOption` | `lens_coverage_note` (or struct) | per-corridor lens density surfaced to the user |
| glue tokens | `GLUE_REFLECTION` | reflection sentences (whitelisted, source = visited beat ids) |
| `ItineraryItem` | `narration: str` (per stop) | the composed/stitched text that becomes audio |
| (existing M2/M6) | `route_polyline`, `leg_seconds`, `eta_seconds`, `RouteOption` | already on the contract |

**Notes.** Walk-past **vignettes are voiced** — one-line segments inside the *leg* narration (same TTS
path), not a separate audio track. The `band` / `spotlight` fields on `RouteOptionStop` land with the
spotlight model (Phase 3), as does `lens_coverage_note`. The **recompose-once-then-block** control flow
already exists (`src/tour/compose_gate.py`: `compose_and_verify`, `MAX_COMPOSE_ATTEMPTS = 2`, raises
`ComposeVerificationError`) — Phase 4 only *wires* it into the live compose. On a refused flavour the
user is offered another flavour; if all flavours are refused, a graceful error — never silent
degradation. `ItineraryItem.narration` (per stop) is a Neo4j node property; Neo4j is schemaless for
properties, so no schema migration is needed to add it.

---

## 8. Verified facts this spec is built on (checked 2026-06-13)

- `held_karp_open(points, *, fixed_start, fixed_end=None, round_trip=False, ...)` already accepts a
  destination (`src/tour/ordering.py:19`). The A→B *socket* exists; only the input + corridor feed it.
- Today `TourInput` has no `end` (`src/tour/contract.py:15`); REACH is a circle/isochrone around A; the
  selector hard-excludes tier-1/2 (`selection.py:553`, `ANCHOR_TIERS={3,4,5}`), `walk_by_only`
  (`selection.py:551`), and lens-miss POIs (`selection.py:559`).
- At a chosen stop, beats are **not** lens-filtered — lens is a within-bucket preference, capped 8
  (tier 4/5) / 3 (tier 3) (`src/tour/beat_select.py`).
- `generate()` produces a stitched `Script.script` (cold-open → transit glue → beats → closing) but the
  live path discards it: `route_script_to_stops` keeps only `beat_ids`; audio is TTS of one primary
  beat per stop; `compose_gate.py` is unwired (`src/api/routes/trips.py:107` comment confirms).
- Corpus (Paris): 370 POIs (tier 1–2 = 160 = 43%), 1,562 beats (tier 1–2 = 329 = 21%); roles stop 155
  / walk_by_only 146 / setting 69 / null 0; top lenses `hidden_history` 334, `historic_arch` 195,
  `dark_history` 168; tails `film_tv` 4, `street_art` 2.

---

## 9. Decided items (decide-not-defer; flag to change)

1. **B optional → open-ended default** (synthesize far anchor; loop only on explicit `round_trip`).
2. **Narration = LLM-composed, grounded** (fire-once Anthropic tool-use); deterministic stitcher is the
   offline/test default and the Phase-1 stepping stone (same audio plumbing).
3. **Spend only on the picked route** (k flavours cheap; compose + TTS once, on the pick). `k = 3` by
   default; 2–3 are surfaced after the diversity filter drops any flavour sharing > 60% of stops
   (Jaccard) with a kept one.
4. **Lens = spotlight, never a gate**; only silence is low-gravity AND off-genre; tone bounded by corpus
   coverage, which REACH measures and surfaces.
5. **Objective stays multiplicative** (`gravity × lens × proximity × role`, all ≥ 0; cost is the
   positive divisor — never a signed edge cost).

---

## 10. Honest caveats / known limits

- **GRADE is thin:** it scores POI-recall + beat-overlap + spine + validation vs a fixture, **not**
  satisfaction. Adequate as a regression gate; not a moat. Upgrading to an LLM-judge rubric is later
  work, off the MVP critical path.
- **Tone quality scales with corpus coverage** (§3.1) — a real dependency on the content pipeline, not
  something the algorithm can fix.
- **Valhalla** is the routed-time engine; with it down, everything falls back to pace-corrected
  haversine and `degraded=true` is surfaced.

---

## 11. Supersedes

| Doc | Status |
|---|---|
| `ondoway-tour-algorithm.html` (netlify/v2) | superseded — dropped the anchor; reversed story philosophy |
| `specs/2026-05-23-tour-planning-algorithm/*` | superseded — A→B "rules" frame folded into §2 corridor |
| `specs/2026-06-10-tour-5phase-engine/05-plan.md` | superseded — solver-ban + additive objective replaced |
| `specs/2026-06-12-tour-algorithm-decision/*` | superseded — prior canonical; as-built engine (M0–M8) folded in |

Disposition of the superseded files (delete vs supersede-header vs keep) is recorded in the plan once
confirmed with the user.
