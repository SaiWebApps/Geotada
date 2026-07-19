# The Tour Quality Standard

**Status:** LIVE. This document is the reference for what a good Ondoway tour is.
**Created:** 2026-07-19. **Owner:** the product owner (the gold text below is theirs).

## Why this exists

Five separate tour-quality root-cause memories were written in eight days
(`tour-gen-overhaul` Jul 12, `tour-quality-root-cause` Jul 17, `tour-qa-campaign`
Jul 18, `spatial-claims-unverified` Jul 18, `tour-repetition-root-causes` Jul 19).
Each session re-derived "what good looks like" from first principles, fixed a local
defect, and wrote a new memory. That is a loop, not progress.

The loop's cause: **the definition of good lived in a context window, never in the
repo.** This document ends that. It is the fixed reference. Every session reads it
before touching tour quality, and `src/tour/quality_rubric.py` enforces the
mechanically checkable parts on every generated tour.

Two layers, borrowed from a discipline that already works in this house
(the `writing-craft` skill's `validate.sh` + adversarial-read model):

- **The FLOOR** — mechanical, deterministic, $0. Counts, ratios, structural
  properties. Runs on every tour. A BLOCKER failure regenerates the script.
- **The GATE** — semantic, model-judged. Meaning-level properties a regex can
  never see. Per `feedback-no-lexical-shortcuts`, word-matching for MEANING is a
  banned shortcut here: narrative quality is judged semantically or not at all.

A tour that has passed only the floor is a first draft, not a deliverable.

---

## 1. The North Star — the human gold

Written by the product owner on 2026-07-15 by hand-rewriting the machine output
they had just ruled NO-GO. Source of record:
`origin/scope2-gate-calibration:specs/2026-07-13-compose-correct-dont-reject/01e-human-gold-rewrite.md`.

This is the quality bar made concrete. Reproduced in full because paraphrase is
exactly how it gets lost.

> Here, at the corner of rue de Castiglione and rue de Rivoli, stands the Hotel Le
> Meurice. Its discreet entrance is at 228 rue de Rivoli.
>
> To understand how a hotel like this came to belong here, we have to imagine the
> neighbourhood when the nearby Tuileries Palace was still the seat of power.
>
> The ladies of the Napoleonic nobility helped make this stretch of rue de Rivoli
> fashionable, drawing an English clientele to the area. At number 224, the English
> bookshop Galignani kept the daily newspapers from home. At number 248, W. H. Smith
> opened its Paris branch for the same clientele.
>
> Nearby, the jewellery and clothing shops of rue de Castiglione and Place Vendôme
> served this fashionable society. It was here, supplying Empress Eugénie and the
> other ladies of the Napoleonic court, that French haute couture was born in the
> second half of the nineteenth century.
>
> One of its pioneers was Charles Worth, the Empress's English couturier. A century
> later, the centre of Parisian fashion would drift westward to the 8th arrondissement.
>
> Le Meurice was one of the grand palace hotels that came to dominate this quarter.
> The English writers Thackeray and Charles Dickens both stayed here during the
> nineteenth century. Dickens stayed while researching A Tale of Two Cities, his
> novel about the years leading up to the French Revolution.
>
> The hotel is also linked to another English writer: George Orwell.
>
> Long before he became famous, a penniless Orwell worked in a grand Paris hotel as
> a plongeur. In Down and Out in Paris and London, he described the plongeur as "the
> slave of the slave," worked to the bone behind the splendour of the hotel.
>
> But did Orwell really work here?
>
> He never named the hotel. His biographers have placed it elsewhere in these
> streets—at the Lotti, just around the corner on rue de Castiglione, or at the
> Crillon. Paris lore, however, has long pinned the story on Le Meurice.
>
> What Orwell described could certainly fit the great hotels of this entire quarter.
>
> From the outside, there was "a vast, grandiose place with a classical façade," and,
> at one side, "a little, dark doorway like a rat hole, which was the service entrance."
>
> Behind that grand façade, the kitchens were a kingdom of hell: a "stifling
> low-ceilinged inferno of a cellar," red-lit by the fires and deafening with oaths
> and the clanging of pots and pans.
>
> Only a double door separated the squalid scullery from the dining room.
>
> On one side sat the customers "in all their splendour," with spotless tablecloths,
> bowls of flowers, mirrors, gilt cornices and painted cherubs.
>
> And on the other side, only a few feet away, Orwell and the other workers stood, as
> he put it, "in our disgusting filth."
>
> A generation later, the German High Command of the Paris garrison took up residence
> in the lavish Le Meurice. General von Choltitz was also quartered here when he saved
> Paris from destruction at the end of the Second World War.
>
> One wonders whether any of them had read Down and Out.

### Two corrections the owner already flagged on this text

Carried here so they are never reintroduced:

1. **"we have to imagine" violates the locked house voice** — the narrator never says
   "imagine". (See also `feedback-no-lexical-shortcuts`: the goal is anti-hallucination,
   and the word-ban itself was called out as the wrong instrument. The rule stands as a
   *voice* rule, enforced semantically, not as a regex on the word.)
2. **"William Makepeace" and "English writer(s)" are world knowledge** absent from the
   beat bodies. The faithfulness gate correctly rejects them. The grounded equivalents
   are "Thackeray and Charles Dickens" / "another writer". The gold text above is
   reproduced with that correction applied.

---

## 2. What makes the gold good

Derived from the text above and the owner's own analysis in `01e`. These are the
properties to reproduce — each one is a check in §4.

**S1. Orientation before history.** The stop opens by placing the listener in
physical space. *"Here, at the corner of rue de Castiglione and rue de Rivoli, stands
the Hotel Le Meurice. Its discreet entrance is at 228 rue de Rivoli."* The listener
knows where to stand and what to look at before a single date arrives.

**S2. Motivated transitions.** Movement between ideas is caused, not sequential.
*"To understand how a hotel like this came to belong here…"* — the transition states
why the next thing follows. Contrast with "Also," / "In addition," / bare adjacency.

**S3. A causal chain, not a list.** ladies → made the street fashionable → drew an
English clientele → Galignani and W. H. Smith served them. Each fact earns the next.
The machine version had the same facts with the causal middle missing.

**S4. Compound material unpacked and placed.** A single dense source beat is broken
into its component ideas and each is placed where the story needs it — not dumped
where it happened to sit in the corpus.

**S5. Every fact exactly once.** No restatement in new words. (Identical to the
`writing-craft` rule "Say it once": no mic-drop line that repackages the paragraph
above it.)

**S6. A theme, surfaced through transitions.** Englishness runs through the whole
Le Meurice stop and is carried by the connective tissue, never announced.

**S7. A dramatic pivot.** *"But did Orwell really work here?"* A single-line turn that
reframes everything after it. The stop has a shape: setup → deepening → turn → payoff.

**S8. Scene staging.** The Orwell quotes are staged spatially — outside → behind the
façade → one side of the door → the other side. The listener is walked through a
space, not read a passage.

**S9. Disputes kept whole and used.** The Orwell placement dispute is not flattened
into false certainty, nor dropped for being messy. It becomes the pivot. Hedges are
content, not noise.

**S10. A wry, non-moralising close.** *"One wonders whether any of them had read Down
and Out."* It lands the theme without stating a lesson. No "and so we see that…".

---

## 3. Prose discipline (from the house `writing-craft` skill)

These rules are already enforced elsewhere in this project for creative prose. They
transfer to tour narration unchanged.

**P1. Say it; don't circle it.** State the fact directly. Do not bury a point under
three sentences of atmosphere and simile before letting it land. Weight belongs in
the content, never in portentous staging.

**P2. Name what the listener would be told.** Atmospheric periphrasis used as a dodge
— "a famous queen", "a monster of a building" — is a flinch and a hard error. If the
source names Marie-Antoinette, the narration says Marie-Antoinette. Epithets are
legitimate only to *rotate* reference to something already named.

**P3. Say it once.** No restatement, no summary paragraph that repackages what was
just said, no examining the same idea from three angles that land in the same place.

**P4. No metadata laundering.** "Historians say", "records show", "it is said that"
used to make an unsourced claim feel earned is fabrication. Name the concrete source
or cut the claim. **This is the hallucination failure mode in its commonest costume.**

**P5. Not everything is symbolic.** A detail given as a detail stays a detail. Do not
upgrade it into theme or metaphor. This is the moralising-closer generator.

**P6. Register.** Concrete over summary. Short declaratives for impact. One metaphor,
landed, then moved on — never a chain. Avoid reverent description ("terrifyingly
precise"), moral hand-wringing, and "the kind of X that Y" (≤1 per stop).

**P7. The substance floor.** From `writing-craft`, and it is the rule this project
keeps breaking: *"short has always meant under-developed, never tight."* A stop that
"feels done" quickly has usually skipped the setup, the consequence, or the turn.
Judge depth by reading, never by hitting a number with water — but a stop rendered far
below the material available for it is under-developed by definition. See C1.

---

## 4. The checks

Severity: **BLOCKER** = the tour is not served; regenerate. **WARN** = surface to the
editor in the workbench.

### FLOOR — mechanical, deterministic, $0

| id | check | measurement | pass | severity |
|---|---|---|---|---|
| **C1** | **Starvation** — a POI with plenty of material is not reduced to a line | for each stop: `words_rendered` vs `beats_available` for that POI in the corpus. A stop whose POI has ≥`STARVE_MIN_BEATS` beats must render ≥`STARVE_MIN_WORDS_PER_BEAT × beats` words, unless deliberately a walk-past vignette AND the POI is below tier 4 | see §5 | **BLOCKER** |
| C2 | Tier inversion | no tier-5 POI is rendered as a vignette while a lower-tier POI is a full anchor | zero inversions | **BLOCKER** |
| C3 | Thin tour | delivered audio vs requested duration | ≥ the engine's own `FILL_PASS_AUDIO_FLOOR_FRAC × target` | WARN (already disclosed by banner) |
| C4 | Stop balance | no single stop holds a disproportionate share of total words | max stop share ≤ `BALANCE_MAX_SHARE` | WARN |
| C5 | Verbatim repetition | no sentence repeated within the tour | zero exact dupes | **BLOCKER** |
| C6 | Empty/glue-only stop | every stop has ≥1 substantive (non-glue) sentence | zero | **BLOCKER** |
| C7 | Time-budget overrun | walk + listening ≤ the err-short total | within budget | **BLOCKER** |
| **C8** | **Gorging** — the inverse of C1 | words per stop | ≤ `GORGE_MAX_WORDS_PER_STOP` (750) | **BLOCKER** |
| C9 | Sentence length for the ear | `mean_sentence_words` (reuse `narration_quality`) | ≤ 15 (sourced) | WARN |
| C10 | Opens with a look-cue, not a bare fact | first sentence of each stop prompts observation | every stop | WARN (G1 judges semantically) |
| C11 | Date density for the ear | `year_density` per 100w (reuse `narration_quality`) | report + WARN on outliers | WARN |

### GATE — semantic, model-judged

| id | check | judged on | severity |
|---|---|---|---|
| G1 | Orientation before history (S1) | does the stop open by placing the listener physically? | WARN |
| G2 | Motivated transitions (S2) | are transitions caused, or bare adjacency? | WARN |
| G3 | Causal chain not list (S3) | do facts earn each other? | WARN |
| G4 | Semantic repetition (S5/P3) | same fact restated in new words anywhere in the tour | **BLOCKER** |
| G5 | Metadata laundering (P4) | unsourced authority appeals | **BLOCKER** |
| G6 | Periphrasis dodge (P2) | a named entity referred to only obliquely | WARN |
| G7 | Moralising close (P5/S10) | does any stop end by stating a lesson? | WARN |
| G8 | Fabrication | every checkable fact traces to a beat body | **BLOCKER** — already enforced by the calibrated entailment gate; see §6 |

---

## 5. Thresholds, and their provenance

**Every number here is either measured, inherited, or explicitly a judgement call.
Nothing is invented and dressed as evidence.**

| constant | value | provenance |
|---|---|---|
| `STARVE_MIN_BEATS` | 5 | **judgement call.** Measured context: on the Île de la Cité 60-min tour, Sainte-Chapelle (tier 5, **12 beats**) rendered as 9 words while Palais de Justice (tier 4, **3 beats**) was a full anchor. 5 sits above the 3-beat thin POIs and below the 12-beat starved one. Revisit with more data. |
| `STARVE_MIN_WORDS_PER_BEAT` | 12 | **judgement call**, anchored on measurement: the gold Le Meurice stop runs ~560 words; healthy measured stops ran 1022 words / 59 beats ≈ 17 w/b and 915 / 23 ≈ 40 w/b. 12 is deliberately permissive — it catches 9-words-for-12-beats (0.75 w/b), not merely terse stops. |
| `BALANCE_MAX_SHARE` | 0.60 | **judgement call.** Measured: the 2-stop tour split 1022/915 words (53%/47%) — fine. The failure shape is one stop at 90%+. |
| audio floor | `FILL_PASS_AUDIO_FLOOR_FRAC = 0.8` | **inherited** from `src/tour/selection.py:343`. Not a new number. |
| time ceiling | `walk_budget / WALK_FRACTION` | **inherited** — the engine's own err-short total, `src/tour/routing.py:42-43`. |
| words/sec for audio | existing `_sum_audio` | **inherited** from `src/tour/generation.py`. |

### Externally sourced thresholds (professional audio-guide practice)

Researched 2026-07-19. These are **cited**, not invented.

| constant | value | source |
|---|---|---|
| `WORDS_PER_MINUTE` | 130–150 | [Musa Guide](https://www.musa.guide/en/resources/how-to-write-audio-guide-script), [Nubart](https://www.nubart.eu/audio-guides/content-production/writing-museum-guide-scripts.html) ("one minute of speaking time in English corresponds to about 130 words") |
| `MAX_SENTENCE_WORDS` | 15 | Nubart: keep sentences ≤10–15 words, one thought per sentence, active voice, no parenthetical clauses. "Sentences difficult to read aloud become three times more difficult for the visitor to hear." |
| `MAX_WORDS_PER_STATION` | 250 (museum station) | Nubart: "Maximum 250 words per station (approximately 2 minutes of audio)" |
| `GORGE_MAX_WORDS_PER_STOP` | 750 | **adapted, stated as such.** A walking-tour anchor with a 5-min dwell is not a museum station; 750 words ≈ 5 min at 150 wpm, which is the engine's own tier-5 `DWELL_SECONDS_BY_TIER` of 300 s plus listening slack. The museum 250 is the floor of the evidence, 750 the walking-tour adaptation. **Measured violation:** Notre-Dame rendered **1022 words** in one stop — over even the adapted cap. |
| audio ≈ half total visit | 0.5 | Nubart: "Total guide length should be roughly half the average visit time." **Corroborates the engine's own `AUDIO_FRACTION = 0.60`** — the existing target was never wrong. |
| attention ceiling | ~30 min | Nubart: concentration degrades after ~30 minutes. |

### Craft rules (same sources)

- **Never open a stop with bare object identification.** "The first sentence should prompt
  the visitor to observe, compare or reflect — not merely state a fact." Good: *"Look at the
  small figure on the right-hand edge…"* This is S1 (orientation before history),
  independently confirmed.
- **Second person.** "Did you notice…" beats a passive construction.
- **Reduce numeric data to essentials.** Dimensions and dense dates suit a wall label, not
  the ear. Speak dates ("born in Malaga in 1881"), don't list them ("1881–1973").
- **One anecdote or surprising fact per stop** aids concentration and retention.
- **No jargon**; define a term when it is unavoidable.
- **Story, not catalogue.** [Detour](https://techcrunch.com/2014/07/30/detour/) — the
  best-regarded product in this category — staffed **journalists and radio producers**,
  targeting "an episode of This American Life or Radiolab" rather than a guide reciting
  facts. This is the same instinct as the human gold's pivot-and-payoff structure.

`src/tour/narration_quality.py` already computes `mean_sentence_words`,
`long_sentence_rate`, `year_density`, `burstiness` and `second_person_rate` — the rubric
**reuses** those and now has sourced thresholds to judge them against.

---

## 6. What already exists — do not reimplement

- **`src/tour/narration_quality.py`** — `score_narration` / `craft_score`. Computes
  stilted/engagement composites, burstiness, mean sentence words, long-sentence rate,
  second-person rate, look-prompt rate, and per-100w "tells". The rubric **reuses**
  these; it does not recompute them.
- **The calibrated entailment gate** — `HaikuFaithfulnessChecker`, calibrated in
  `scope2-gate-calibration` over five runs to **zero fabricating acceptances**
  (`02b-calibration-scorecard.md`). G8 is that gate. Do not build a second one.
  Its governing ruling, from the owner: *"we are not making up facts, but the composer
  gets room to sound natural"* — the gate rejects checkable-fact violations; interpretive
  colour is composer licence.
- **The correct-don't-reject corrector** — `src/tour/compose_correct.py`, ported to
  main in `a1bb982`. A flagged sentence is repaired (trim, then rewrite) before it is
  allowed to degrade to raw stitch.

---

## 6b. Remaining divergence — the app compose path

**The workbench and the app do not yet narrate identically, and that is a known,
scoped gap rather than an oversight.**

| surface | endpoint | composer | best-of-2 | corrector | on gate failure |
|---|---|---|---|---|---|
| workbench | `POST /trips/preview` | `compose_script_per_chapter` | yes | yes | floors to stitch, returns 200 + `compose_status` |
| mobile app | `POST /trips/{id}/compose` | `compose_script` (whole-tour) | no | no | raises → **HTTP 422, trip left UNMUTATED** |

They were unified on 2026-07-19 and the unification was **deliberately reverted the
same day**. The reason is not prose, it is persistence:

- `/trips/{id}/compose` **writes to Neo4j** (`replace_trip_stops` + `mark_trip_composed`)
  and the audio flow then voices whatever is stored.
- Whole-tour compose refuses loudly on verification failure, so a bad tour is never
  persisted and another flavour can be tried. That is what
  `tests/test_trip_api.py::test_refused_flavour_is_422_and_leaves_trip_untouched`
  protects.
- Per-chapter never refuses — it floors to grounded stitch and returns 200. Swapping
  it in silently means degraded content gets persisted and marked "composed", and
  `TripComposeResponse` carries **no `compose_status`**, so the app cannot tell the
  difference.

**To close it properly** (a decided change, not a swap): add `compose_status` to
`TripComposeResponse` so the app knows what it received, and/or refuse when the compose
*wholly* degraded. Both need a product ruling on whether a partially-stitched tour
should be persisted at all.

---

## 7. How this runs

`src/tour/quality_rubric.py` exposes:

```python
def score_tour(script, route, snapshot, *, tour_input) -> RubricReport
```

`RubricReport` carries per-check results, the blocker list, and an overall verdict.
The compose path calls it after composition. **A BLOCKER verdict regenerates the
script** rather than serving it. WARN results surface in the workbench so an editor
sees them without being blocked.

The floor runs on every tour, always, at $0. The gate runs where a model call is
already being made, so it adds no new spend tier.

---

## 8. Provenance of this document

- §1 gold text — `origin/scope2-gate-calibration`, `01e-human-gold-rewrite.md`, written
  by the product owner 2026-07-15.
- §2 properties — the owner's own analysis in `01e`, restated as checks.
- §3 prose discipline — the house `writing-craft` skill, applied unchanged.
- §5 measured values — a $0 engine run on the live Paris graph (370 POIs / 1543 beats),
  Île de la Cité, 60 min, `dark_history`, 2026-07-19.
- §6 — `02b-calibration-scorecard.md` and the modules cited.

**External professional practice (Rick Steves, Detour, museum audio-guide style
guides, broadcast writing-for-the-ear) is NOT yet folded in.** Research is in flight;
§5 marks exactly which thresholds are waiting on it. This document is honest about
that gap rather than filling it with plausible-sounding numbers.
