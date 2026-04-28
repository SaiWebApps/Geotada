# Tour-Builder — Phase 1 Design

**Status:** DESIGN. No code, no implementation. STOP for user signoff before Phase 2.
**Created:** 2026-04-27.
**Inputs:** `source-study.md`, `empirical-tours/01-place-des-vosges.md`, `empirical-tours/02-ile-de-la-cite-notre-dame.md`, `empirical-tours/findings.md`, `extraction-requirements.md`, parked `design.md`, the 8 `feedback_tour_*` memories, live Paris Neo4j graph (queried 2026-04-27).
**Authoritative source-of-truth:** the two empirical walks. Any rule contradicted by them is suspect.

---

## 1. Live-graph reconnaissance

Sampled the Paris corpus directly (`/tmp/sample_neo4j*.py`, 2026-04-27). Results below frame what tour-builder can rely on vs. what is thin.

### 1.1 Corpus shape

| Metric | Value |
|---|---|
| Total POIs in Paris | **303** (linked via `WITHIN→Area{name:'Paris'}`) |
| POIs by tier | t5=36, t4=52, t3=85, t2=67, t1=63 |
| `poi_role` distribution | stop=177, walk_by_only=102, setting=23, null=1 |
| Total NarrativeBeats | **1164** |
| Average beats per POI by tier | t5 avg 9.75 (median 7, max 59), t4 avg 4.5 (med 3, max 24), t3 avg 3.0 (med 1, max 39), t2 avg 3.1 (med 2, max 19), t1 avg 1.8 (med 1) |
| POIs within 1.5 km of Île de la Cité (`point.distance` works on `POI.location`) | 172 |
| Areas roster | 1 city + 20 arrondissements + 2 islands + 11 neighborhoods + 3 corridors (orphans) + 1 unowned neighborhood (Grands Boulevards) = **38 declared**, plus 1 unowned shell (Tuileries) likely missing |

POI.location is `Point(lng, lat)`; geo math (Cypher `point.distance`) is available natively. No external geocoder required at runtime.

### 1.2 Tier-5 anchors — sub_location coverage

Sub_location is the spatial primitive for buildings. Empirical Tour 2 confirmed it carries an interior walk on Notre-Dame.

| POI | Total beats | With sub_location | Distinct sub_locations |
|---|---|---|---|
| Notre-Dame Cathedral | 48 | 20 | 15 |
| Conciergerie | 16 | 8 | 6 |
| Sainte-Chapelle | 9 | 2 | 1 |
| Eiffel Tower | 12 | 2 | 1 |
| Pantheon | 12 | 1 | 1 |

Notre-Dame and Conciergerie are walk-ready. Sainte-Chapelle, Eiffel, Pantheon are thin — runtime should degrade gracefully (sequence by `narrative_function` instead).

### 1.3 Squares — trigger_address coverage

Trigger_address is the spatial primitive for circumnavigation. Empirical Tour 1 stress-tested it on Place des Vosges.

| Square | Tier | Total beats | With trigger_address |
|---|---|---|---|
| Place des Vosges | 5 | 59 | **26** |
| Place de la Bastille | 3 | 15 | 2 |
| Place du Châtelet | 3 | 10 | 1 |
| Place Vendôme | 5 | 7 | 1 |
| Place Dauphine | 2 | 6 | 1 |
| Place de la Concorde | 4 | 4 | 0 |
| Place du Tertre | 4 | 4 | 1 |

**Place des Vosges is the only square ready for full circumnavigation.** Other squares can do "stop and look around" but not Pariswalks-style address-by-address. This is fine for MVP; extraction can fill out the others later.

### 1.4 Stop-orientation beats — known thin

Per findings.md, this is the cold-open primitive. Live counts:

- **13 total** `stop_orientation` beats across 12 POIs
- Covered: Sacré-Cœur, Place des Vosges (3), Notre-Dame (1), Eiffel Tower, Palais Garnier, Catacombs, Rue Cler, Trocadéro, Saint-Germain-l'Auxerrois, Père Lachaise, Parc Monceau
- **Conspicuously missing:** Conciergerie, Sainte-Chapelle, Louvre, Pantheon, Pont Neuf, Place Vendôme, Tuileries, Île de la Cité, Sorbonne, Luxembourg, Champs-Élysées, Arc de Triomphe, Musée d'Orsay

This matches the findings.md gap. Runtime must degrade by composing a stop_orientation from `physical_cues` + `pronunciation` if available.

### 1.5 Transit beats — better than expected

- **87 total** transit beats; **78 carry trigger_address** (the rest carry only navigation prose).
- Île de la Cité chain (Pont Neuf → Place Dauphine → Conciergerie → Sainte-Chapelle → Notre-Dame): all 4 bridge-stops have at least 1 transit beat. The Frommer's Walk-1 chain is reproducible from the corpus.
- Top transit-providers: Père Lachaise (7), Rue Cler (6), Place des Vosges (3), Centre Pompidou (2), Place de la Bastille (2).

Transit material is unevenly distributed. For routes outside the established Frommer's/Pariswalks corridors, runtime will need to generate structural glue. Acceptable per findings.md (glue is structural, not creative).

### 1.6 Field-population health

| Field | Populated / 1164 | Notes |
|---|---|---|
| `entities` | 1159 (99.6%) | strong |
| `subject_tag` | 1095 (94%) | strong (489 of which are empty string — likely Vallois legacy) |
| `physical_cues` | 1095 (94%) | strong (better than the 61% in source-study; v2 fix landed) |
| `inline_foreign_phrases` | 1095 (94%) | strong |
| `narrative_function` | 1159 (99.6%) | strong (establishing 380, deepen 340, climax 151, hook 135) |
| `emotional_register` | 1159 (99.6%) | strong (neutral 424, reverent 218, somber 167, dramatic 137, wry 117, playful 96) |
| `beat_length_class` | 599 of 1164 (51%) | **THIN** — 496 empty string + 69 null; only 296 seasoning + 255 mid + 32 micro + 16 anchor are usable |
| `pronunciation` | 12 (1%) | **VERY THIN** — only Place des Vosges + a handful of others |
| `book_slug` | 0 (all empty/null) | **MISSING** — no per-book filtering possible without re-attribution |

`beat_length_class` and `pronunciation` are the largest data quirks tour-builder must handle. Both have backlog tickets implicit in the post-launch list.

### 1.7 Lens system (live)

Live count is **21 child lenses + 8 parent lenses = 29 total**. NORTHSTAR says "16 taggable lenses." This is a discrepancy worth flagging to the user — see Open Question 6 below.

Lens relationship is `TAGGED_WITH` (parked design.md called it `TAGGED_LENS`).

Top child-lens usage: hidden_history 269, historic_arch 170, dark_history 136, famous_residents 100, literary_heritage 90.

### 1.8 Known data quirks (confirmed)

- **Notre-Dame is in `Latin Quarter` Area** (polygon overshoot bug, post-launch backlog item 9). Confirmed live.
- **Unowned shell Areas (post-launch item 10):** Rue Mouffetard, Rue Visconti, Rue Chanoinesse (corridors), Grands Boulevards (neighborhood). Tuileries shell from the docs is not visible in live data; either renamed or already cleaned.
- **Vallois lossy `physical_cues`** (post-launch item 7): the migration default is `{cue, direction:"here", feature_type:"view"}`. Tour-builder selection should not over-weight `physical_cues` content for these.
- **Notre-Dame does have 1 stop_orientation beat** — better than findings.md reported. Conciergerie, Sainte-Chapelle, and most other tier-5s do not.

### 1.9 Le Marais and Île de la Cité as test cases

Le Marais (47 POIs) and Île de la Cité (14 POIs) are dense enough to support full Phase-1-spec walks.

| Area | t5 | t4 | t3 | t2 | t1 |
|---|---|---|---|---|---|
| Le Marais | 4 | 9 | 7 | 16 | 11 |
| Île de la Cité | 5 | 2 | 2 | 1 | 2 |
| Latin Quarter | 3 | 2 | 3 | 5 | 7 |
| Saint-Germain-des-Prés | (data row dropped — query truncated) | | | | |

Le Marais is the best target for the first generated tour: 4 tier-5 anchors (PdV is the killer one), enough mid-tier seasoning for between-anchor walking, and a coherent Area boundary.

### 1.10 What tour-builder can rely on

- **POI selection**: full coverage. Tier, location, poi_role, Area membership all populated.
- **Beat metadata for selection**: entities, subject_tag, narrative_function, emotional_register, lens — all >94%.
- **Spatial sequencing within a POI**: working for Notre-Dame, Conciergerie, Place des Vosges. Thin elsewhere.
- **Cold-open assembly**: only 13 anchors have stop_orientation. Runtime must compose from physical_cues + pronunciation when missing.
- **Transit weaving**: 87 beats, decent for established corridors, sparse off-corridor.
- **Cross-book triangulation**: empirical walks proved this works at hand-write quality. Claim-level dedup (B8) deferred.

### 1.11 What tour-builder cannot do well yet

- **Pronunciation**: only 12 beats carry it. Cold-open pronunciation moments only land at PdV.
- **Length-class budgeting**: half the corpus has no length_class. Runtime must fall back to word count from `script_body`.
- **Per-book attribution at runtime**: `book_slug` not populated. If we want "this fact came from Pariswalks" UX, schema needs a backfill.
- **Thin tier-5 sub_location** at Sainte-Chapelle, Eiffel, Pantheon — building-walk degrades to flat sequencing at these anchors.

---

## 2. Rule ledger

Walked through every rule in the parked `design.md` and the 8 `feedback_tour_*` memories. Status against the two empirical walks.

| # | Rule | Status | Source-of-truth |
|---|---|---|---|
| **Core principles (parked design.md §"Core principles")** | | | |
| 1 | No editorializing — every sentence traces to a beat or structural fact | **VALIDATED** | Both walks; ~6–8 glue sentences each, all structural |
| 2 | Themes emerge from beats (entity overlap) | **REVISED** | findings.md: vocabulary inheritance is the actual mechanism, not entity overlap. Anchor essay teaches the vocabulary; seasoning uses it |
| 3 | Themes as callbacks, never forecasts | **REVISED → DROPPED** | findings.md §"Revised patterns": real walks don't theme-callback either. Title carries the thematic work; body demonstrates without naming |
| 4 | Audio ≤ 60% of tour time | **REVISED** | Empirical walks land 70–80% audio at 150 wpm. Aspirational target, not hard cap. Generate within an explicit time budget instead |
| 5 | Seasoning shares entity/time/theme with adjacent anchor | **REVISED** | The actual rule: anchor teaches vocabulary; seasoning uses it. "Shared entity" framing is too loose |
| 6 | House voice + per-lens modulations | **DEFERRED** | Empirical walks show no clear lens modulation — house voice throughout. Park; revisit if Phase 4 testers flag flatness |
| 7 | Runtime gets only beats, no world knowledge | **VALIDATED** | Both walks; structural connectors are pure navigation, never factual claims |
| 8 | Source-traceable output | **VALIDATED** | Both walks ship sentence-level beat IDs; validation diff is feasible |
| **POI selection (parked design.md §"POI selection")** | | | |
| 9 | Tier as gravity (5=anchor, 3=pause, 1–2=walk-by) | **VALIDATED** | Both walks treat anchors and seasoning per this mapping |
| 10 | Selection scoring: `tier × beat_richness × interest × narrative_fit × distance_decay` | **REVISED** | `narrative_fit` at city scale is near-zero (parked doc admits this); replace with Area+route geometry. Routing-aware required |
| 11 | Pre-selection theme clustering via entity co-occurrence | **DEFERRED** | Empirical walks didn't surface a "theme" via entity overlap — the Area or square IS the theme. MVP can use Area boundary as the cluster signal; revisit when corpus is multi-city |
| 12 | Stop budget: `(planned_time − base_walk_time) / cost_per_stop` | **VALIDATED** | Walks fit ~22 stops in PdV (90 min, anchor + 18 vignettes) and ~12 in Île (90 min) under similar arithmetic |
| 13 | Routing-aware selection (`score / marginal_route_cost`) | **VALIDATED** | The Île chain is on-corridor and that's what made it composable |
| 14 | Stop quality floor (min beats per stop, max ~8 stops, diminishing returns) | **VALIDATED** | Walks have 4–6 beats per anchor and 1–2 per seasoning stop |
| 15 | Geographic barriers (Seine, arterials) penalize crossings | **VALIDATED** | Île walk crosses Pont Neuf once, on purpose; doesn't bounce banks |
| **Beat-within-POI selection (parked §"Beat selection within a POI")** | | | |
| 16 | Cap 2–4 beats per anchor, 1 per pause | **REVISED** | Empirical anchor stops have 4–6 beats (Notre-Dame had ~12 over 6 sub_locations). Drop the cap; sequence by sub_location or trigger_address instead |
| 17 | Filter to active beats only | **VALIDATED** | Standard hygiene |
| 18 | Prefer beats matching emerging theme/lens/entities | **REVISED** | Drop "emerging theme" as a filter; use sub_location/trigger_address ordering as the primary signal, lens as bias |
| 19 | Tone variety within a stop (no three-somber-in-a-row) | **VALIDATED** | `emotional_register` is populated; runtime can enforce |
| **Time math (parked §"Time and dwell math")** | | | |
| 20 | Walking pace ~3 km/h | **VALIDATED** | Provisional Paris value, validate per neighborhood |
| 21 | Haversine ×1.35 correction | **VALIDATED** | Paris-wide; per-neighborhood variance documented |
| 22 | Dwell: 4–6 min anchor, 2–3 min pause, 0 min walk-by | **VALIDATED** | Walks fit this |
| 23 | Audio rate ~150 wpm | **VALIDATED** | Both walks audited at this rate |
| 24 | Buffer 15% on top | **VALIDATED** | Carry forward |
| 25 | "Err short": plan 83% of stated duration | **VALIDATED** | Carry forward |
| 26 | "Honest length": deliver shorter when corpus thin | **VALIDATED** | findings.md ack: PdV walks ~60 min, Île ~90 min; don't pad |
| **Narrative structure (parked §"Narrative structure")** | | | |
| 27 | Cold open: concrete hook, no abstract theme | **REVISED** | Pariswalks sit-down staging is the gold standard, not just "concrete hook." See findings.md §"New patterns" item 1 |
| 28 | Connective navigation between stops | **VALIDATED** | Both walks use minimal navigational glue |
| 29 | Stop blocks 1–3 beats ordered architecture→story→consequence | **REVISED** | At tier-5 anchors, 4–6 beats; ordering is sub_location or trigger_address driven, not architecture→story |
| 30 | Walk-bys must share entity/time/theme | **REVISED** | Same as rule 5: vocabulary inheritance is the actual rule |
| 31 | Closing callback honors flagged hooks | **DROPPED** | Real walks just stop. Pariswalks: "you have now circled" + optional continuation. Frommer's: "End the walk here or carry on with Walk 9." No thematic summary |
| 32 | "Imagine" / "picture this" forbidden | **VALIDATED** | feedback_tour_tone_default; both walks observe this |
| 33 | Walk-bys must connect to spine | **VALIDATED with §5 revision** | |
| **House voice details (parked §"House voice")** | | | |
| 34 | 2nd person, present-then-past, conversational | **VALIDATED** | Both walks |
| 35 | Read-aloud test (must sound spoken) | **VALIDATED** | Both walks |
| 36 | Active verbs, fragments, varied length, no parallel lists, no abstract measurements | **VALIDATED** | Both walks |
| 37 | One sensory prompt per stop minimum | **VALIDATED** | Empirical walks all carry at least one physical cue per stop |
| 38 | Action-Reflection-Stakes (TAL framework) | **DEFERRED** | Philosophical scaffolding, not algorithmic. Revisit when prompting the runtime LLM |
| 39 | Forward hook + return signal contract | **DROPPED** | Both walks don't use forward hooks. The mechanism the parked doc described isn't observed in real guidebook output |
| 40 | Beat-to-beat glue: causal/temporal/structural linkage from beat content | **VALIDATED** | Both walks; glue cites beat-internal arithmetic only |
| 41 | Interest is bias, not filter (esp. tier-4/5) | **VALIDATED** | Both walks include non-interest beats at anchors |
| 42 | Assumed-knowledge test (smart traveler, no specialist background) | **VALIDATED** | Both walks observe this |
| **Allowed structural operations (parked §"Allowed")** | | | |
| 43 | Date arithmetic from cited beats | **VALIDATED** | Mark `[ARITH]` |
| 44 | Sensory callouts for visible features | **VALIDATED** | |
| 45 | Cross-POI structural callbacks ("the building you stood in front of") | **VALIDATED** | Worth keeping for multi-POI walks |
| 46 | Place-name etymology when in cited beat | **VALIDATED** | Useful cold-open hook |
| 47 | Light paraphrase preserving meaning | **VALIDATED** | |
| 48 | Closing callback gets 3–5% of total tour time | **DROPPED** | Walks close with 1–2 sentences. The 3–5% allocation is a fiction |
| **NEW patterns surfaced by empirical walks (findings.md §"New patterns")** | | | |
| 49 | Pariswalks sit-down opener structure: heading → epigraph → métro → walking direction → pronunciation → inline definition → physical orientation → sit-down with sensory invitation → cold-weather alternative → content signal | **NEW VALIDATED** | Empirical Tour 1; the gold standard |
| 50 | Address-level seasoning via `trigger_address` is the killer feature | **NEW VALIDATED** | Empirical Tour 1 |
| 51 | Sub_location sequencing inside a building | **NEW VALIDATED** | Empirical Tour 2 (Notre-Dame) |
| 52 | Cross-source claim-level dedup (B8) | **NEW REQUIREMENT, DEFERRED** | Empirical Tour 2 (Vallois/LEG overlap on Notre-Dame) |
| 53 | Glue is structural, never invents claims | **NEW VALIDATED** | Both walks; ~6–8 glue sentences each |

**Summary:** 30 validated, 11 revised, 5 dropped, 4 deferred, 4 new. The parked design's overall shape holds; the closing-callback / theme-forecast machinery doesn't.

---

## 3. Algorithm sketch

Designed for Haiku-scale runtime cost. No Opus-level reasoning per tour. Selection and routing are graph queries; generation is short-prompt Haiku stitching beat texts with whitelisted glue.

### 3.1 INPUT contract

```
{
  start: { lat: float, lng: float },
  duration_min: int,             # user-stated; algorithm targets 0.83 × this
  lenses: [string] | null,       # 0–N child-lens slugs; empty = no interest bias
  round_trip: bool,              # see Open Question 1
  theme_hint: string | null,     # optional; surfaces in cold-open ("a walk about kings")
  city_slug: string,             # mandatory per CLAUDE.md (multi-city safe)
  start_label: string | null     # optional human-readable origin ("from your hotel near the Sorbonne")
}
```

### 3.2 POI selection — routing-aware scoring

**Pre-pass: route envelope.**

1. Compute `target_audio_min = duration_min × 0.83 × 0.6` (the "err short" planned audio budget; 60% silence target).
2. Walk-time budget: `walk_min = duration_min × 0.83 × 0.4`.
3. Reachable envelope: `max_radius = (walk_min × 3.0 / 1.35) / 60 × 1000` meters from start. (3 km/h actual progress, ÷1.35 haversine correction.) For round-trip, halve the radius.
4. Cypher query:
   ```
   MATCH (p:POI {city_name:'paris'})-[:WITHIN]->(:Area {name:'Paris'})
   WHERE p.poi_role IN ['stop','setting'] AND p.location IS NOT NULL
     AND point.distance(p.location, $start_point) <= $max_radius
   RETURN p
   ```

**Spine selection: Area-first.**

The parked doc's "pre-selection theme clustering via entity co-occurrence" doesn't pay off at city scale (its own §80 admits this). Replace with: **the Area IS the spine.** When the start point falls in or near a single neighborhood Area, that Area is the spine. When it sits between two, score both and pick the one with more tier-5/4 beats inside the walk envelope.

Alternative: if user provides a `theme_hint`, score POIs by lens/subject_tag overlap and prefer Areas with higher concentration.

**Tie-break (Updated 2026-04-27 (Phase 2 calibration)):** when multiple Areas score within 5% of the leader, prefer in this order: `neighborhood > island > corridor > district > city`. All else equal, prefer the more specific (lower vote-count) Area, then break alphabetically. This makes "Île de la Cité" the spine for a Pont Neuf start instead of "1st Arrondissement".

**Per-POI score:**

```
score(p) = importance_tier(p)
         × beat_richness(p)              # log(1 + beat_count(p))
         × interest_bias(p, lenses)      # 1.0 + 0.5 × (matching_lens_beats / total_beats); cap 2.0
         × area_alignment(p, spine)      # 1.0 if p in spine Area, 0.5 if adjacent Area, 0.2 otherwise
         × poi_role_multiplier(p)        # 1.0 stop, 0.7 setting, 0.0 walk_by_only (handled separately)
```

Routing-aware selection picks `argmax(score / marginal_route_cost)` greedily until either:
- `walk_min` budget exhausted, OR
- `target_audio_min` budget reached (estimated as `Σ dwell_min(p) × audio_density(p)`), OR
- `max_anchors = max(1, duration_min // 10)` outer anchors selected, capped at 12 (§5 Q5; **Updated 2026-04-27 (Phase 2 calibration)** — divisor was 12, calibration against the empirical Île walk drove it to 10).

`marginal_route_cost` is the additional walking minutes a candidate adds to the optimal route through already-selected stops. Computed by inserting candidate at best position in current route (TSP-light; fine for ≤12 stops).

**Endpoint-pull (one-way only).** **Added 2026-04-27 (Phase 2 calibration)** to keep traverses from truncating near the start. The greedy reserves ~25% of the walk-time budget for this step; otherwise it tends to consume 95–98% of the budget on tight neighborhood clusters and leaves no headroom for a far-envelope closing stop. After the (reduced-budget) greedy completes for a `round_trip=False` route:

1. Identify the top-K (=5) un-selected candidate POIs in the *far half* of the reachable envelope (haversine distance from start ≥ 0.5 × `max_radius`), ranked by score.
2. For each candidate in score order, attempt to insert it as the closing stop. Use best-insertion to reorder the interior anchors through the route up to (but never after) the endpoint.
3. Drop the lowest-scoring incumbent and retry, up to a bounded `max_drops` (=2) per candidate, if the new total would exceed the full walk budget or the hard anchor cap of 12.
4. Accept the first candidate that fits. If none of the top-K fit, abandon the pull and keep the greedy result.

The empirical Île walk approximates under this rule: with the reservation, the Pont Neuf 90-min one-way route picks up Hôtel de Ville (tier-5, ~820m east of start) as the closing anchor, instead of truncating at Place du Châtelet (~470m). Notre-Dame Cathedral does not currently surface as the endpoint because its `Latin Quarter` Area assignment (the §1.8 polygon overshoot) penalises its `area_alignment` score — the polygon fix in the post-launch backlog will correct this.

**Walk-by enrichment (separate pass, after spine fixed):**

For each walking segment between selected stops longer than ~2 min, find tier-1/2 POIs along the path within ~50 m of the route, with `poi_role IN ['walk_by_only','stop']`. Include if at least one beat at that POI shares an entity, subject_tag, or lens with the spine's vocabulary (per the revised seasoning rule). Cap walk-bys to ~1 per minute of walk-time.

### 3.3 Beat selection within a POI

**For tier-5/4 anchor stops:**

1. Filter to active beats at the POI.
2. Branch on spatial primitive:
   - **Building (sub_location populated for ≥3 distinct values):** order beats by sub_location sequence. Sequence is a hand-curated ordering per POI (Notre-Dame: parvis → kilometre-zero → façade → gallery-of-kings → central-portal → side-portals → bell-tower-vestibule → nave → choir → treasury → towers → exterior-east-end). Stored as POI metadata or derived deterministically. **Pick at most 1 beat per sub_location** (the highest-scoring), then 1 fallback "no sub_location" beat at the end as a closing thought.
   - **Square (trigger_address populated for ≥5 distinct values):** order by trigger_address. Use a stable ordering (e.g., starting at the closest address to walking-entry, then clockwise). One beat per address; sidebar beats can attach to the same address.
   - **Flat (neither populated densely):** order by `narrative_function`: hook → establishing → deepen → climax. Pick 4–6 beats (anchor 200–400w + 2–3 mid + 1 closing).
3. Within sub_location/trigger_address, prefer beats with higher `(lens_match × emotional_register diversity × subject_tag novelty)`.
4. Prepend cold-open if first stop (see §3.5).
5. Enforce tone variety: no 3 somber/reverent in a row.

**For tier-3 pause stops:** 1–2 beats. Highest-scoring + lens-matching.

**For tier-1/2 walk-bys:** exactly 1 beat each. Beat must share at least one entity, subject_tag, or lens with the adjacent anchor.

**Length-class budgeting:** when `beat_length_class` populated, prefer 1 anchor-class + several mid + seasoning interleaved per stop. When missing, fall back to word count from `script_body` (assume ~150 wpm).

**Source dedup:** Phase 1 plan does NOT do claim-level dedup at runtime — that's the deferred B8 work. For now, when two beats share ≥80% subject_tag overlap or the same `entities` list, runtime drops the lower-`narrative_function`-ranked one. Document the limitation; revisit when B8 ships.

### 3.4 Generation pipeline

Five stages. Each maps to a fixed beat-pool retrieval and a deterministic assembly with minimal LLM-glue.

| Stage | Beats pulled | Glue allowed |
|---|---|---|
| 1. Cold open | First stop's `stop_orientation` beat (if exists) + first 1–2 establishing/hook beats | "Settle in." / "Find a bench." Opening physical staging if no stop_orientation beat exists |
| 2. Anchor essay (per tier-5 stop) | 1 anchor-class + 2–3 mid beats by sub_location or trigger_address | Sub_location-to-sub_location or address-to-address transitions ("Now turn the corner east." / "Step inside.") |
| 3. Circumnavigation / interior walk | All remaining beats at the anchor, ordered spatially | Per-stop transitions ("Look up." / "Press the button at no. 3.") |
| 4. Transit | Transit beats from the corpus when present; structural glue when absent | Direction-only ("Walk for about three minutes." / "Cross the bridge ahead.") |
| 5. Close | Last stop's closing beats + any sidebar | Physical-closure phrase ("You have now circled..." / "End here, or continue west via rue X.") |

**Cold-open assembly (when `stop_orientation` missing):**

Compose from the first anchor's `physical_cues` + beat with `narrative_function='establishing'` + any beat carrying `pronunciation`. Pattern: physical cue → pronunciation → 1-line origin from establishing beat → "Find a bench" or "Stand here" glue. Acknowledge in `phase-1-design` that this falls short of the Pariswalks gold standard until the stop_orientation gap-fill ships.

**Closing assembly:** physical-closure glue + one sentence from a `narrative_function='callback'` beat if available + optional continuation pointer ("End here, or continue with Tour B"). No thematic summary.

### 3.5 Glue rules — whitelist

Runtime LLM may write only structural connectors. No factual claims. Whitelisted phrase categories:

1. **Navigation**: "walk east for about three minutes", "cross the bridge ahead", "turn left at the corner", "stop halfway", "exit by the northwest corner".
2. **Physical staging**: "find a bench", "stand here", "look up at...", "press the button at no. X", "step into the courtyard".
3. **Transition/pacing**: "settle in", "now stand up", "turn the corner east", "we're going to circle the square", "take a moment".
4. **Cross-POI structural callbacks** (rule 45): "the building you stood in front of half an hour ago", "the same king who built the bridge you crossed earlier".
5. **Date arithmetic** (rule 43, marked `[ARITH]` in source attribution): "four hundred years later".
6. **Closing**: "you have now circled X", "end here, or continue with Y".

**Forbidden in glue:** any new factual claim, any thematic interpretation, "imagine" / "picture this", proper names not already in cited beats, dates not derivable from cited beats.

### 3.6 OUTPUT format

```
{
  city_slug: "paris",
  generated_at: "2026-04-27T...",
  inputs: { ... echoed ... },
  total_audio_seconds: int,
  total_walking_seconds: int,
  total_walk_distance_m: int,
  total_planned_seconds: int,
  selected_pois: [
    { id, name, tier, lat, lng, area, dwell_seconds, beat_ids: [...] },
    ...
  ],
  lens_coverage: { lens_slug: count_in_tour, ... },
  script: [
    { sentence: "...", source_id: "<beat_uuid> | GLUE_NAV | GLUE_PAUSE | ARITH | STRUCTURAL", source_type: "beat|glue|arith", stop_idx: int },
    ...
  ],
  validation: {
    untraceable_sentences: [...],   # must be empty before TTS
    forbidden_phrase_hits: [...],   # "imagine", "picture this"
  }
}
```

`validation.untraceable_sentences` must be empty before TTS — that's the source-traceability gate (rule 8).

### 3.7 Runtime cost estimate

- Selection (Cypher + Python): ~50–200 ms, no LLM.
- Beat dedup pass (claim-level overlap): ~50 ms, no LLM.
- Cold-open + transit glue (Haiku, ~1k input + 200 output tokens): ~$0.001–0.005.
- Validation diff: no LLM.
- TTS: dominant cost; out of scope for tour-builder.

Total tour-builder runtime: **<$0.01 per tour**, well under the parked design's $0.01–0.05 budget.

---

## 4. Skill structure proposal

### 4.1 File layout

```
.claude/commands/tour-build.md          # the skill (orchestrator; thin)
src/tour/
  __init__.py
  contract.py                            # input/output dataclasses + Pydantic validators
  selection.py                           # POI selection (Cypher queries, scoring)
  routing.py                             # route geometry, distance, dwell math
  beat_select.py                         # within-POI beat selection (sub_location/trigger_address ordering)
  generation.py                          # cold-open / transit / closing assembly + glue whitelist
  validation.py                          # source-traceability diff; forbidden-phrase scan
  fixtures.py                            # named ordering tables (Notre-Dame sub_location order, etc.)
tests/
  test_tour_selection.py                 # POI selection determinism + interest-bias unit tests
  test_tour_beat_select.py               # ordering + length-class budgeting
  test_tour_generation.py                # glue whitelist enforcement + traceability
  test_tour_golden_pdv.py                # golden output for Place des Vosges round-trip
  test_tour_golden_ile.py                # golden output for Île de la Cité one-way
fixtures/tour_golden/
  pdv_round_trip_60min.json              # canonical empirical Tour 1 normalized to output format
  ile_oneway_90min.json                  # canonical empirical Tour 2
```

The skill orchestrates; Python does the work. Per CLAUDE.md style: keep the skill prompt under 200 lines and let Python handle anything testable.

### 4.2 Skill contract (`.claude/commands/tour-build.md`)

**Invocation:**
```
/tour-build --start "48.8553,2.3653" --duration 60 --lenses historic_arch,famous_residents --round-trip
```
or with named anchor:
```
/tour-build --start "Place des Vosges" --duration 60 --round-trip
```

**The skill:**
1. Validates input against `contract.py` schema.
2. Calls `src/tour/selection.py:select_route(input)` → returns `Route` (POIs, transitions, time budget).
3. Calls `src/tour/beat_select.py:select_beats(route)` → returns `BeatSequence`.
4. Calls `src/tour/generation.py:generate(beat_sequence, route)` → returns `Script` (sentence-level traceable records). Uses Haiku.
5. Calls `src/tour/validation.py:validate(script)` → blocks on traceability or forbidden-phrase failures.
6. Writes output to `data/{city_slug}/tours/{generated_id}.json` and prints summary.

**The skill prompt body** is mostly the input schema + invocation rules + a paragraph each on the principles (no editorializing, source traceability, glue whitelist, "err short"). Python carries the algorithm.

### 4.3 Test plan

**Unit tests** (Phase 2–3):
- POI selection: deterministic given seed, respects max_radius, prefers spine Area
- Beat selection: sub_location ordering matches fixture, trigger_address ordering deterministic
- Glue whitelist: rejects "imagine", rejects new proper nouns
- Source traceability: untraceable sentence flagged

**Golden-output tests** (Phase 4):
- `test_tour_golden_pdv`: input `(start=PdV centroid, duration=60, round_trip=True)` → output is structurally equivalent to empirical Tour 1 (same POI list, same beat IDs in same order, glue sentences fall in whitelist categories). 90% beat-overlap threshold (allows runtime to make different choices that survive validation).
- `test_tour_golden_ile`: input `(start=Pont Neuf metro, duration=90, round_trip=False)` → empirical Tour 2 reproduction.

**Integration test** (Phase 5):
- End-to-end CLI invocation against live Neo4j, output passes validation, total time within ±10% of stated.

### 4.4 What NOT to build in tour-builder

- Multi-language support — NORTHSTAR boundary
- Full audio generation (TTS) — out of scope
- Tour storage / serving — out of scope (tour-builder writes JSON; downstream consumes)
- Real-time GPS triggering — out of scope (tour-builder is offline composition)
- Beat re-extraction or POI cleanup — separate post-launch backlog
- Claim-level dedup (B8) — deferred; document in output

---

## 5. Open design questions (need user signoff)

Each has a recommended default; flagging for explicit signoff before Phase 2.

### Q1. Round-trip semantics

**Question:** What does `round_trip=true` mean? "Loop returns to origin" (Pariswalks PdV is a circle ending at start) or "linear path with origin = endpoint"?

**Recommendation:** **Round-trip = walk returns to origin point.** For square circumnavigation, the entire walk happens around one POI and ends at the start. For multi-POI round-trips, the algorithm picks an out-and-back loop. For one-way, the endpoint is an output of the algorithm (last selected stop).

**Why:** PdV empirical walk is a circle. Île walk is a one-way bank-to-bank. These are the two genuine modes. A "linear with origin=endpoint" would be a forced loop that empirical evidence doesn't support.

### Q2. Tour-internal callbacks ("the bridge you crossed earlier")

**Question:** Parked design.md proposed cross-POI structural callbacks. Empirical walks don't use them — was that because the walks are short, or because the rule is wrong?

**Recommendation:** **Allow but don't require.** Carry rule 45 as a generation option for tours with ≥4 anchor stops, where there's a meaningful "earlier" to point back to. Both empirical walks were on the short side (≤90 min, ≤9 anchors); a 3-hour walk through multiple neighborhoods plausibly wants this affordance. Mark uses with `[CALLBACK]` source attribution.

**Why:** The mechanism is sound (no new claims, just structural pointer) but unnecessary at empirical-walk scale. Defer aggressive use until Phase 4 testers report on longer walks.

### Q3. Voice modulation per lens

**Question:** Parked feedback_tour_tone_default proposed lens-specific word choices. Empirical walks show only house voice — no clear modulation.

**Recommendation:** **DEFER to post-MVP.** Implement house voice only in Phase 1–4. Revisit if Phase 4 testers report tonal flatness across mixed-lens walks.

**Why:** Empirical walks are Pariswalks-quality without modulation. YAGNI risk if we build it now and the testers don't notice. Cheap to add later — it's a prompt-engineering tweak in `generation.py`, not an architectural change.

### Q4. Theme discovery

**Question:** Parked design.md proposed bottom-up theme derivation from entity overlap. Empirical walks didn't surface a clear theme — title/Area carried the work.

**Recommendation:** **DROP algorithmic theme discovery. Use `theme_hint` as optional user-supplied + Area name as default.** The walk's "theme" is "Place des Vosges" or "the birthplace of Paris," not a computed cross-entity arc. Surface the Area name as the implicit theme; user can override with `theme_hint`.

**Why:** Both empirical walks confirm. Algorithmic theme discovery is the most expensive part of the parked algorithm and demonstrably unnecessary. Save for post-MVP if multi-Area routes need it.

### Q5. Stop budget tuning

**Question:** What's the right stop count for a given duration?

**Recommendation:** **1 outer anchor per 10 minutes of total tour duration, +0.5 walk-by stops per anchor.** A 60-min PdV walk has 1 anchor + 18 trigger_address vignettes (treated as one cumulative stop with internal sequencing). A 90-min Île walk has 9 anchors. Use:
```
max_anchors = max(1, duration_min // 10)
max_walkbys = anchors × 2
```
Cap total at 12 outer anchors. Internal sub_location/trigger_address vignettes inside a single anchor do **not** count toward this cap.

**Why:** Empirical anchor counts (1 PdV, 9 Île) calibrate this. The parked doc's "max ~8 stops" is too restrictive at the multi-Area scale; the 12 cap accommodates Île-style traverses.

**Updated 2026-04-27 (Phase 2 calibration):** the original recommendation read `walk_min / 12`, where `walk_min` was ambiguous between *walking-minutes-of-budget* and *total tour minutes*. Calibrating against the empirical Île walk (90 min total → 9 anchors) the divisor is `duration_min // 10`. This matches both PdV (60 // 10 = 6 anchor budget; PdV consumes 1 outer slot) and Île (90 // 10 = 9). The hard cap of 12 is unchanged.

### Q6. Lens count mismatch (Northstar 16 vs live 21+8)

**Question:** NORTHSTAR locks "16 taggable lenses." Live graph has 21 child + 8 parent = 29 lens nodes, with 21 child lenses being taggable (TAGGED_WITH from beats).

**Recommendation:** **Flag for user — this is a NORTHSTAR drift, not a tour-builder concern.** Tour-builder takes the live lens roster as authoritative. User decides whether NORTHSTAR needs updating to "21 taggable lenses" or whether some live lenses should be deprecated.

**Why:** Doesn't block tour-builder design. But the phrase "16 taggable lenses" appears in the Phase 1 milestone gate — worth knowing whether the gate is met.

### Q7. Stop_orientation gap-fill at runtime

**Question:** Most tier-5 anchors lack a `stop_orientation` beat. Should tour-builder runtime synthesize one from `physical_cues` + `pronunciation`, or fail loud?

**Recommendation:** **Synthesize when missing; mark as `[SYNTHESIZED_OPENER]` in source attribution.** The synthesizer takes the first anchor's first 2 physical_cues + any pronunciation + a fixed glue template ("Stand here. The first thing you'll notice is..."). Quality will be visibly worse than a real stop_orientation beat, which is fine — it documents the gap and motivates back-fill extraction.

**Why:** Failing loud breaks any tour at Conciergerie/Sainte-Chapelle/most anchors. Synthesizing flags the gap honestly without blocking the user.

### Q8. Round-trip closing for a square (Pariswalks PdV "you have now circled")

**Question:** Pariswalks Walk 4 has no canonical "you have now circled" closing beat in our corpus (gap noted in Tour 1 §"Gaps surfaced"). Synthesize, or omit?

**Recommendation:** **Synthesize as `STRUCTURAL` glue.** Whitelisted closing phrase: "You've now circled {square_name}." or "We've now walked {area_name} end to end." The phrase is structural (no claims), so it falls inside the glue whitelist.

**Why:** Empirical walks confirm the closing pattern; the data just doesn't carry it as beats. Glue is the right home.

---

## 6. Phase 2-and-beyond outline

| Phase | Scope | Gate to advance |
|---|---|---|
| **Phase 1 (THIS doc)** | Diagnostic + design only. | User signoff on §5 open questions. |
| **Phase 2** | Implement `selection.py` + `routing.py` + `beat_select.py` against live Neo4j. Unit tests for selection determinism, interest bias, sub_location ordering. | All unit tests pass; selection runs <500 ms on Paris corpus. |
| **Phase 3** | Implement `generation.py` (cold-open, transit, closing assembly) + glue whitelist + Haiku prompt. `validation.py` enforces source traceability and forbidden-phrase scans. | A 60-min PdV tour generates without invocation errors and passes validation. |
| **Phase 4** | Golden-output tests against the two empirical walks. Calibrate scoring weights so generated PdV ≥90% overlaps empirical Tour 1 beat IDs. Same for Île. | Golden tests pass at ≥90% overlap. |
| **Phase 5** | End-to-end `/tour-build` CLI invocation. Multi-tour smoke test (Latin Quarter 2hr, Marais 3hr, Île 90min). Record audio_min / walk_min / total / cost telemetry. | 5 tours pass validation; cost < $0.01 each; user reads output and approves quality. |
| **Phase 6 (post-MVP)** | Lens-modulated voice. Tour-internal callbacks for ≥4-stop walks. Per-Area haversine corrections. Claim-level dedup (B8). Stop_orientation gap-fill via extraction. | Tied to Phase-1-milestone "Boredom Test passing internally." |

---

## 7. Surfaced assumptions and gaps (audit trail)

Every assumption in this doc that isn't anchored to evidence:

1. **Walking pace 3 km/h** — provisional Paris value (parked design.md). Assumed valid until per-neighborhood validation in Phase 5.
2. **Haversine ×1.35** — same. Per-neighborhood variance (Marais ×1.4, Haussmann ×1.2) acknowledged but not yet measured.
3. **Audio at 150 wpm** — TTS-engine-dependent; ElevenLabs Conversational AI may run faster/slower. Validate against actual MP3 output in Phase 5.
4. **8-stop hard cap from parked design** — relaxed to 12 for multi-Area walks. No empirical evidence above 9 (Île). Phase 4 calibration may revise.
5. **`area_alignment` weights (1.0/0.5/0.2)** — guessed. Phase 4 calibration tunes against empirical golden output.
6. **Interest-bias multiplier (1.0–2.0)** — guessed. Same calibration.
7. **80% claim-overlap dedup threshold** — guessed; placeholder until B8 ships.
8. **Lens count mismatch** — flagged in Q6; assumed orthogonal to tour-builder.
9. **`book_slug` empty in live data** — runtime cannot do per-book attribution. Acceptable for MVP; flag if user wants source attribution UX.
10. **`pronunciation` 1% coverage** — runtime can synthesize "that's pronounced X" only at PdV. Cold-open elsewhere falls short of Pariswalks gold standard.
11. **`beat_length_class` 51% missing** — runtime falls back to word count. Length budgeting becomes approximate.
12. **Notre-Dame in Latin Quarter** — known polygon overshoot; tour-builder uses Île de la Cité as the canonical Area for ND.
13. **`stop_orientation` synthesis quality** — unverified. Synthesized opener marked `[SYNTHESIZED_OPENER]`; user can audit and decide whether to defer launch until back-fill ships.

These are the points where Phase 1 design has knowingly substituted reasoned defaults for measured data. Phase 4–5 calibration is the right place to validate.

---

## 8. What this doc does NOT do

Per the prompt's constraints:

- **No code.** Selection scoring, dwell math, and pipeline pseudocode are illustrative; nothing in `src/` or `.claude/commands/` is touched.
- **No memory updates.** The 8 `feedback_tour_*` memories are inputs to the rule ledger; updating them is the user's call after signoff.
- **No empirical-walk edits.** They are authoritative reference.
- **No Phase 2+ specifics beyond the outline.** Each phase will get its own spec under `specs/{date}-tour-builder/`.
- **No B8 claim-dedup design.** Deferred per findings.md and post-launch backlog.
- **No stop_orientation back-fill plan.** Deferred per backlog item 4.
- **No solution to the Latin Quarter polygon overshoot** beyond "use Île de la Cité as canonical." Backlog item 9 owns the fix.

---

**End Phase 1 design. Awaiting user signoff on §5 open questions before Phase 2.**
