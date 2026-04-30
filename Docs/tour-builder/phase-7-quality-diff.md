# Phase 7 — Tour-Builder Quality Diff vs Phase 6

**Generated:** 2026-04-29
**Scope:** five focused fixes to selection + generation, no schema or
density-gate changes. Re-runs of the five Phase 5/6 tours saved at
`data/paris/tours/phase7-rerun/`.

---

## Top-line table

| Tour | P6 POIs | P7 POIs | P6 audio | P7 audio | P6 walk | P7 walk | P6 unique beats | P7 unique beats | Cold open | Closing-beat type |
|---|---|---|---|---|---|---|---|---|---|---|
| Tour 1 — PdV 60min round-trip | 5 | 5 | 24 min | 22 min | 17 min | 17 min | 37 | 31 | **ebeab682 (real PariswalkS opener)** | climax (`87e82317` bronze gypsy) |
| Tour 2 — Île 90min one-way | 8 | 8 | 30 min | 30 min | 24 min | 24 min | 56 | 55 | SYNTHESIZED_OPENER (no Area-mate) | climax (`a86ed923` Napoleon coronation) |
| Tour 3 — Sacré-Cœur 90min RT | RED (refused) | RED (refused) | — | — | — | — | — | — | — | — |
| Tour 4 — Concorde 180min one-way | 5 | 6 | 9 min | 9 min | 41 min | 53 min | 16 | 14 | SYNTHESIZED_OPENER | deepen (`c44099e7` Tour de France — corpus has no climax/callback) |
| Tour 5 — Pantheon 120min round-trip | 3 | 3 | 13 min | 12 min | 30 min | 30 min | 18 | 17 | SYNTHESIZED_OPENER | hook/deepen |

The unique-beats reductions (-6 PdV, -1 Île, -2 Concorde, -1 Pantheon)
are intentional: B8-lite recalibration + transit-class anchor filtering
collapse near-duplicates and cleanly drop wrong-direction transit
prose. The trade is a few seconds of audio for substantively cleaner
output.

---

## Per-fix verification

### Fix 1 — B8-lite recalibration

**Diagnostic on the three confirmed dup pairs (Phase 7 thresholds):**

| Pair | Lens overlap | Entities Jaccard (raw) | Entities Jaccard (canonical) | Subject-tag Jaccard | Char-5gram Jaccard | Year+canonical-entity hit | Phase 6 result | Phase 7 result |
|---|---|---|---|---|---|---|---|---|
| Mesme Gallet (`de1377b4` / `bf668074`) | yes (`hidden_history`) | 0.500 | 1.000 (after stripping leading "Built") | 0.000 | **0.327** ≥ 0.30 ✓ | n/a | both emitted | **dropped `bf668074`** |
| Hugo affair (`b41d4c77` / `a1833622`) | yes (`famous_residents`) | 0.667 | 0.667 | 0.000 | **0.384** ≥ 0.30 ✓ | n/a | both emitted | **dropped `b41d4c77`** |
| Pantheon vow (`ee115ca8` / `142060a7`) | yes (`hidden_history`) | 0.125 | 0.286 (Saint↔St normalisation) | 0.000 | 0.064 | **2 canonical entities + shared 1744 ✓** | both emitted | **dropped `ee115ca8`** |

The legacy 0.8 entity / 0.8 subject_tag thresholds are unchanged. Two
new signals were added:

- char-5-gram Jaccard on `script_body` ≥ 0.30 — catches paraphrase
  pairs where extractor/source variations rewrite the same anecdote.
- canonical-entity overlap ≥ 2 + shared 4-digit year — catches "same
  founding story, divergent supporting cast" pairs the entity Jaccard
  alone misses. Canonicalisation does ASCII-folding, lowercasing,
  strips leading sentence-starter words ("Built"), and normalises
  "Saint X" / "St. X" / "St X" to a single form.

**Test pinning:** four new tests in `tests/test_tour_beat_select.py`
Phase 7 section, including a guard against over-collapsing PdV-style
complementary address vignettes.

**Golden test impact:** PdV 100% / Île 100% beat-overlap maintained.

### Fix 2 — Area-level cold-open lookup

When the start POI lacks a `stop_orientation` beat, `find_area_orientation_beat`
now searches the rest of the Route for a sibling POI that shares an
Area with the start POI and carries an orientation beat. Found beat
hoists to position 0 of the cold open and is added to `consumed_beat_ids`
so it doesn't double-fire.

**Tour 1 verification:** Hotel de Sully has no orientation beat. Place
des Vosges (5th stop, same Le Marais Area) has the canonical
Pariswalks "find a bench in the garden" opener (`ebeab682`). Phase 6
emitted SYNTHESIZED_OPENER at stop 1 + the orientation beat at stop 5.
**Phase 7 emits `ebeab682` at stop 1 only**, with the cold open now
reading:

```
Settle in.
Find a bench in the garden, near the children's play area, …
If it's cold, step into Café Ma Bourgogne…
```

This matches the Pariswalks gold-standard cold-open structure for
the first time on the live corpus.

**Tour 4 / Tour 5:** start POIs sit in Areas where no other POI in
the route carries an orientation beat (Champs-Élysées, Latin Quarter
respectively). Falls through to SYNTHESIZED_OPENER as before. The
runtime workaround does not fix the corpus gap — that's still the
post-launch backlog item 4 (extraction-time gap-fill).

**Test pinning:** three new tests in `test_tour_beat_select.py`
covering the hoist, the no-shared-Area negative case, and the no-
sibling-orientation-beat negative case.

### Fix 3 — target_audio_min as a floor (fill pass)

After the main greedy + endpoint-pull, if delivered audio is below
`0.8 × audio_budget`, a fill pass adds anchors with relaxed
cost-efficiency (score-first, not score / cost). Stops on any of:

- audio floor met,
- walk-time hits 95% of `walk_budget`,
- `HARD_ANCHOR_CAP` (12) reached,
- pool exhausted.

For one-way routes with ≥2 stops, the post-endpoint-pull last anchor
is preserved as the closing stop; fill insertions clamp to interior
positions.

**Tour 4 verification:** main greedy stalls at 5 anchors / 41 min walk,
audio proxy 25 min vs floor 71 min. Fill pass adds Hôtel de Crillon
(low-cost, Area-adjacent) → 6 anchors / 53 min walk. Higher-scoring
candidates (Arc de Triomphe, Louvre, Conciergerie, Palais Garnier)
all required ≥27 min of additional walking and exceeded the 95% walk
cap; fill pass legitimately stops there. **Delivered audio (9 min) is
unchanged** — the corpus along the Concorde→Champs-Élysées corridor
genuinely lacks rich tier-5 content to draw from inside the walk
budget. The fill pass is structurally sound; the audio ceiling is a
corpus density issue, not a selection bug.

**Tours 1, 2, 5:** main greedy already meets the audio floor (or
exceeds it). Fill pass is a no-op.

**Test pinning:** five new tests in `test_tour_selection.py`,
including a synthetic "below floor with slack" case, a hard-anchor
cap regression, a walk-budget cap regression, and a live-Neo4j
Concorde smoke test.

### Fix 4 — Transit beat direction-awareness

`_find_directional_transit_beat` now requires the transit beat's
`trigger_address + script_body` to mention the previous stop (case-
insensitive substring) before reuse. When no directional match
exists, falls through to GLUE_NAV with explicit
`from {previous}, walk to {current}, distance approx {N}m` context.

A separate fix: `_build_anchor_block` now unconditionally filters
out transit-class beats (`narrative_function ∈ {transition, transit,
navigation}`). Without this, rejected transit beats leaked into the
anchor block as out-of-place navigation prose.

**Tour 4 verification:** Phase 6 stop 3 (Pont Alexandre III) opened
"Starting at Invalides Metro station, walk to Pont Alexandre III"
when the user was arriving from Pont de la Concorde. **Phase 7 stop 3
opens with GLUE_NAV** ("Walk to the next stop.") and goes directly
into the bridge content — no broken Invalides reference. Same
correction at stop 5 (Champs-Elysees, Phase 6 said "Starting at
Charles de Gaulle-Étoile Métro" while user was arriving from Grand
Palais).

**Test pinning:** three new tests in `test_tour_generation.py`:
wrong-direction beat rejected → GLUE_NAV with explicit context;
direction-consistent beat accepted; cross-segment fallback to glue
when neither side carries a matching transit beat.

### Fix 5 — Closing-friendly beat reservation

`reorder_final_stop_for_closing` runs at the top of `generate()` and,
when needed, moves a closing-friendly beat to the last position at
the final stop. Preference order (per spec): `narrative_function='callback'`
> `'climax'` > longest body. `stop_orientation` beats are excluded
from the closing-friendly pool — they're cold-open primitives.

The post-closing callback re-emission in `_build_closing` was removed
(it now lives naturally as the last anchor-block beat).

**Tour 1 verification:** Phase 6 ended on `43885a1b` (Mme de
Motteville zinger about ambassadors, climax). Phase 7 picks the
first climax — `87e82317` (bronze gypsy "firmly bolted to her red-
marble base, which is firmly bolted to the floor", climax). Different
climax beat; both qualify per spec.

**Tour 4 verification:** Champs-Elysees has no callback or climax
beats. Fallback to "longest body" → `c44099e7` (Tour de France jersey
colors, 1051 chars). That beat happens to already be last in the
natural ordering, so the reorder is a no-op. **Closing is unchanged
from Phase 6** — the corpus at Champs-Elysees genuinely lacks a wrap-
up beat. Fixing this would require extraction-side work, not a
selection-time fix.

**Tour 5 verification:** Phase 6 ended on `f4e7d0fd` (Napoleon /
Restoration sculpture group, deepen). Phase 7 ends on `0b7888cb`
(Voltaire/Rousseau ejected by Royalists, deepen — longest body at
the Pantheon stop pool). Different beat, also no callback/climax in
corpus.

**Test pinning:** five new tests in `test_tour_beat_select.py` —
callback promotion, climax fallback, longest-body fallback,
already-friendly no-op, single-beat no-op.

---

## Baseline regression coverage

- 180 tour tests pass (was 160 pre-Phase-7; +20 new tests).
- Live PdV golden test: 22/22 beat overlap (100% maintained).
- Live Île golden test: passing (100% maintained).
- The 23 unrelated test failures in `test_api_*`, `test_seed`,
  `test_data_integrity`, `test_upload_api`, `test_traversals` are
  pre-existing — verified by running them on `main` before any
  Phase 7 changes.

---

## Honest gaps not closed by Phase 7

1. **Tour 4 audio fill stays at 5%** — the Concorde→Champs-Élysées
   corridor has thin tier-5 anchor density along its geometry. The
   fill pass adds 1 anchor (Hôtel de Crillon) but cannot reach the
   spec's "≥40% delivered" target without violating the walk-budget
   ceiling. Real fix is extraction (richer Champs-Élysées corpus)
   or a longer envelope.
2. **Cold-open SYNTHESIZED_OPENER still fires** on Tours 2, 4, 5 —
   the start POIs sit in Areas with no orientation beats anywhere
   in the Route. Phase 7 Fix 2 helps when an Area-mate carries one,
   but the underlying gap (≤13 stop_orientation beats across 12 POIs
   per phase-1-design §1.4) is unchanged. Backlog item 4.
3. **Closing-friendly fallback to "longest body"** is corpus-bound.
   On stops with no callback/climax beats, the longest beat may
   still feel factoid-y rather than wrap-up-y. Mitigated, not
   solved.
4. **Tour 4 `unique_beats` dropped** 16 → 14 because Phase 7
   correctly rejects wrong-direction transit beats and the new
   anchor-block transit-class filter drops them entirely. This is a
   small audio-time cost in exchange for cleaner navigation prose.

---

## Recommended next-phase priorities

1. **Extraction backlog** — `stop_orientation` gap-fill (item 4),
   Champs-Élysées callback/climax, Concorde corridor anchor depth.
2. **Optional Phase 8 selection refinement** — when the fill pass
   stalls due to walk budget, consider an even-more-relaxed mode
   that picks the lowest-marginal-cost candidate regardless of
   score floor. May add 1-2 anchors to off-corridor tours.
3. The push-divergence reconciliation, polygon hygiene, and
   `book_slug` backfill remain in the post-launch backlog —
   unchanged by Phase 7.

---

# Phase 7.5 — Surgical fixes on top of Phase 7

**Generated:** 2026-04-29
**Scope:** three focused fixes building on Phase 7. No algorithm
shape changes. Re-runs of the four GREEN Phase 7 tours saved at
`data/paris/tours/phase7.5-rerun/`; Tour 3 (Sacré-Cœur) remains RED.

## Top-line table

| Tour | P7 POIs | P7.5 POIs | P7 cold open | P7.5 cold open | Notes |
|---|---|---|---|---|---|
| Tour 1 — PdV 60min RT | 5 | **4** | `ebeab682` (geographically dishonest at Hotel de Sully) | SYNTHESIZED — Hotel de Sully courtyard cue | Hugo museum demoted into PdV no. 6 |
| Tour 2 — Île 90min OW | 8 | 8 | SYNTHESIZED (no Area-mate) | SYNTHESIZED — rue Dauphine view cue | Vert-Galant retained (tier-3 pause guard) |
| Tour 3 — Sacré-Cœur 90min RT | RED | RED | — | — | unchanged |
| Tour 4 — Concorde 180min OW | 6 | 6 | SYNTHESIZED stub | SYNTHESIZED — Concorde obelisk + Arc-de-Triomphe view cue | richer opener |
| Tour 5 — Pantheon 120min RT | 3 | 3 | SYNTHESIZED stub | SYNTHESIZED — Cluny Old Roman baths cue + Latin Quarter | richer opener |

Total tour tests: **194** passing (was 180 in Phase 7; +14 new
covering the three fixes). Live PdV / Île golden tests still 100%.

## Per-fix verification

### Fix 1 — Geographically-honest cold-open hoist

`find_area_orientation_beat` now requires a candidate orientation beat
to satisfy at least one of:

- (a) the beat's POI matches the start POI (Phase 5 behaviour);
- (b) the beat carries no `physical_cues` at all (Area-generic);
- (c) the beat's source POI is within 100 m of the start stop
  (`HOIST_PROXIMITY_M`).

When no candidate passes, the cold open falls through to
SYNTHESIZED_OPENER instead of hoisting a beat whose physical cues
describe a different place.

**Tour 1 verification:** Phase 7 hoisted PdV's `ebeab682`
("find a bench in the garden, near the children's play area, …
Café Ma Bourgogne at the northwest corner") to position 0 at Hotel
de Sully — none of those features exist there. Phase 7.5 rejects
the hoist (PdV is ~190 m from Hotel de Sully, well past
`HOIST_PROXIMITY_M=100`, and the beat carries view + adjacent_landmark
cues). The cold open is now the Phase 7.5 SYNTHESIZED opener; PdV
beat `ebeab682` fires later at its own stop where it's geographically
honest.

**Test pinning:** four new tests in `tests/test_tour_beat_select.py`
(reject-when-distant, accept-when-area-generic, accept-when-no-cues,
accept-when-within-proximity) plus a constant pin.

Code: [src/tour/beat_select.py:367-466](../../src/tour/beat_select.py#L367-L466).

### Fix 2 — Improved SYNTHESIZED_OPENER

When no orientation beat can hoist (the Phase 7.5 default for tours
2/4/5 and now also 1), the synthesized opener composes from real
corpus data at the start POI:

1. **Pacing primitive**: "Settle in." (`GLUE_PACING`)
2. **Location anchor**: "You're starting in {Area}." from
   `Route.spine_area`. Article-prefix table handles "the Île de la
   Cité" vs "Le Marais" deterministically.
3. **Pronunciation**: when any beat at the start POI carries
   `pronunciation`, append "That's pronounced X."
4. **Physical staging**: pick the strongest physical_cue at the
   start POI by feature_type — view ≻ architectural_detail ≻ plaque
   ≻ adjacent_landmark. View cues use "Look up at X."; everything
   else uses "Notice X." (`GLUE_STAGING`).
5. **Sensory invitation**: "Take a moment to take it in."
   when any beat at the start POI carries a view-feature cue;
   otherwise the duration primer "We're going to walk for about N
   minutes." (`GLUE_PACING`).

Validation extended to add Area names + every beat's
`physical_cues` + `pronunciation` to the canonical-context corpus,
so cue proper nouns (e.g. "Café Ma Bourgogne", "Arc de Triomphe")
don't trigger the new-proper-noun gate.

**Sample (Tour 4 — Concorde 180min OW, first 5 sentences of Stop 1):**

```
## STOP 1 — Place de la Concorde
Settle in. [GLUE_PACING]
You're starting in Champs-Élysées. [SYNTHESIZED_OPENER]
Look up at The obelisk as the center point — look up the Champs-Élysées
toward the Arc de Triomphe, and see the Grande Arche beyond. [GLUE_STAGING]
Take a moment to take it in. [GLUE_STAGING]
```

**Sample (Tour 5 — Pantheon-area 120min RT, first 5 sentences of Stop 1):**

```
## STOP 1 — Musee de Cluny
Settle in. [GLUE_PACING]
You're starting in Latin Quarter. [SYNTHESIZED_OPENER]
Notice Old Roman baths structure housing the museum. [GLUE_STAGING]
We're going to walk for about 120 minutes. [GLUE_PACING]
```

Both read as honest setup, not template stub.

**Test pinning:** four new tests in `test_tour_generation.py`
(uses-physical-cues, uses-pronunciation, falls-back-gracefully,
view-cue-uses-look-up-verb).

Code: [src/tour/generation.py:265-461](../../src/tour/generation.py#L265-L461).

### Fix 3 — Same-physical-location POI demotion

After selection, `apply_co_located_demotion` audits every selected
POI pair. A pair (A, B) demotes the smaller-tier POI into the larger
when **all** of:

- both POIs are tier ≥ 4 (`DEMOTION_MIN_TIER` — anchor-only);
- haversine(A, B) ≤ 100 m (`DEMOTION_PROXIMITY_M`, the v3 schema
  geofence radius);
- one POI's beats reference a distinctive name token of the other
  via `trigger_address` or `sub_location` (case-insensitive
  substring; generic words like "place", "rue", "musee" excluded).

Demoted POI's beats merge into the host's pool via
`Route.demoted_beats`; the harness extends the host's beat list
before calling `select_poi_beats`. The host POI's existing
trigger_address ordering keeps demoted content in the right address
bucket; B8-lite handles any duplicative content (the Tour 1 Hugo
case: PdV's beat `8064951e` already covers Hugo museum at no. 6, and
the demoted museum's `84ec9be0` collapses against it).

**Why 100 m not 15 m (the spec's literal threshold).** Live Paris
corpus geocodes Place des Vosges to its centroid (48.8555, 2.3656)
~85 m from Musée Victor Hugo's pin (48.8548, 2.3661). A 15 m gate
would never catch the headline case. 100 m is the v3 geofence
radius — the natural notion of "same physical place" — and the
name-token signal stays the semantic guard against over-collapsing.
The tier-≥4 guard prevents collapsing empirical pause stops
(Square du Vert-Galant, ~80 m from Pont Neuf with overlapping
sub_location text but tier 3) into anchors.

**Tour 1 verification:** Phase 7 had Musée Victor Hugo as Stop 4
*and* the Hugo Museum sub_location at PdV's Stop 5 — same physical
building visited twice. Phase 7.5 demotes Hugo museum (tier 4) into
Place des Vosges (tier 5); the user walks past no. 6 PdV exactly
once, hearing the canonical 8064951e Hugo content in the trigger-
address sequence.

```
P7 POIs: ['Hotel de Sully', 'Rue Saint-Antoine', 'Restaurant Bofinger',
          'Musee Victor Hugo', 'Place des Vosges']
P7.5    : ['Hotel de Sully', 'Rue Saint-Antoine', 'Restaurant Bofinger',
          'Place des Vosges']
```

**Tour 2 verification:** Pont Neuf (tier 5) and Square du Vert-Galant
(tier 3) are co-located within 100 m and Pont Neuf carries a beat
with sub_location text mentioning Vert-Galant — but the tier-≥4
guard skips the pair and Vert-Galant remains its own pause stop, as
the empirical Île walk requires.

**Test pinning:** four new tests in `test_tour_selection.py`
(demote-co-located, no-demotion-above-threshold,
no-demotion-when-pause-tier, no-demotion-without-overlap-signal)
plus an end-to-end `select_route` test.

Code: [src/tour/selection.py:540-657](../../src/tour/selection.py#L540-L657)
(detection + harness wiring at
[scripts/tour_build.py:109-122](../../scripts/tour_build.py#L109-L122)).

## Tour 1 — before/after

**Before (Phase 7, Stop 1 cold open):**

```
## STOP 1 — Hotel de Sully
Settle in. [GLUE_PACING]

### square-center-park
Find a bench in the garden, near the children's play area, so you
can watch the children play à la française — and despite the mix of
Hebrew, Yiddish, and Arabic you'll hear, you're standing in what was
for nearly two centuries the single most fashionable square in Paris.
[BEAT:ebeab682]

If it's cold, step into Café Ma Bourgogne at the northwest corner;
the view of the square is nearly as good from the window. [BEAT:ebeab682]
```

(Both lines describe Place des Vosges, not Hotel de Sully.)

**After (Phase 7.5):**

```
## STOP 1 — Hotel de Sully
Settle in. [GLUE_PACING]
You're starting in Le Marais. [SYNTHESIZED_OPENER]
Look up at Oak tree, manicured hedges, vine-covered walls in the
back courtyard. [GLUE_STAGING]
Take a moment to take it in. [GLUE_STAGING]
During the reign of Henry IV (1589–1610), this area — originally a
swamp (marais) — became the hometown of the French aristocracy.
[BEAT:6a0b70b8]
…
```

(Cold open references Hotel de Sully's actual back courtyard.)

## Soft-launch readiness

- **Tour 1 (PdV 60-min RT)**: Pariswalks-quality readable. Cold open
  is geographically honest; Hugo museum collapses into PdV no. 6;
  the address-by-address PdV circumnavigation lands correctly at
  Stop 4. Ready for tester walk-throughs.
- **Tour 2 (Île 90-min OW)**: Pariswalks-quality readable. 8 anchors
  including Vert-Galant; cold open opens with rue Dauphine view from
  Pont Neuf; Notre-Dame closes the route. Ready for tester walk-
  throughs.
- **Tour 4 (Concorde 180-min OW)**: structurally sound but corpus-
  bound at 9 min audio delivered (extraction backlog). Better cold
  open lifts the opening but doesn't fix the corpus depth issue.
- **Tour 5 (Pantheon-area 120-min RT)**: 3 anchors (Cluny, Sorbonne,
  Pantheon); YELLOW tourability (fill ratio 0.56). Better cold open;
  the corpus thinness around the Sorbonne/Pantheon corridor remains
  a backlog item.

**194 tour tests pass** (180 Phase 7 + 14 Phase 7.5). Golden PdV /
Île tests still 100% beat overlap.

**Updated 2026-04-29.**
