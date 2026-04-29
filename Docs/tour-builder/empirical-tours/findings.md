# Empirical Tour Findings — distilled design implications

**Source:** Two hand-write tours composed from the Paris v2 corpus on 2026-04-26.
**Inputs to read alongside:** `01-place-des-vosges.md`, `02-ile-de-la-cite-notre-dame.md`, `Docs/tour-builder/source-study.md` (the original guidebook study), `Docs/tour-builder/extraction-requirements.md` (the v2 schema spec).

This doc distills what the two empirical walks teach the tour-builder design. **It is descriptive, not prescriptive.** Rules are validated only after they survive contact with these walks.

---

## Validated patterns (rules that held up)

These rules from the parked `design.md` and the source-study survived empirical contact:

1. **Source-traceable output.** Every script sentence in both walks traced to a beat or to a structural connector. No invention. The ~6–8 glue sentences across each walk are pure structural transitions (no factual claims).
2. **Inline foreign-word + gloss preserved.** 22+ glossed phrases per walk. The "you are abroad" register depends on it, and the v2 extractor preserves it consistently.
3. **Sub_location sequencing inside a building.** Notre-Dame's 16 sub_locations produced a coherent walk through the cathedral (parvis → kilometre-zero → façade → gallery-of-kings → central-portal → side-portals → bell-tower-vestibule → nave → choir → treasury → towers → exterior-east-end). This is the spatial primitive for tier-5 anchor stops.
4. **Trigger_address sequencing around a square.** Place des Vosges's 18 distinct addresses produced a circumnavigation. This is the spatial primitive for square/street walks.
5. **Cross-book triangulation produces complementary detail without redundancy.** When source corpus has multiple books on the same POI, beats triangulate well — Conciergerie has Vallois etymology + RG sensory detail + Frommer's name origin, no two books say the same thing twice. (Notre-Dame is the exception — see "Gaps".)
6. **Specific numbers, never round.** Both walks preserve "1301–15", "2,780 victims", "April 5, 6, 7 of 1612", "13-ton Emmanuel Bell", "9,000 congregation", "7,500 pipes". The v2 corpus carries this consistently.
7. **A named human in every entry.** Even tiny address vignettes anchor to a person — Théophile Gautier at no. 8, the duchess and her gypsy at no. 18, etc.
8. **Voice survives extraction.** "Nice fellow." preserved verbatim. The bronze-gypsy-in-pickup-truck story carried in full. Maupassant's *eau-de-vie* line. Mme de Motteville's "give you heartburn" zinger. Viollet-le-Duc's heavenward statue.

## Revised patterns (rules that need adjustment)

1. **Closings are simpler than the parked design.md said.** The parked rule was "closing callback honors every flagged hook." Reality: real walks just stop. Pariswalks Walk 4 closes with "you have now completely circled the place des Vosges... but if you still have the strength, the walk continues in Walk 5." Frommer's W1 closes with "End the walk here or carry on with Walk 9." No thematic summary, no callback. Only one editorial flourish allowed at most.
2. **Seasoning rule is more specific than "shares entity/time/theme with adjacent anchor."** The actual rule: **the anchor teaches the vocabulary; the seasoning uses it.** A précieuse vignette at Place des Vosges no. 6 only lands because the anchor essay introduced what a *précieuse* is. The "shared entity" framing is too loose — it's vocabulary inheritance.
3. **Themes are NOT named at openings.** The parked rule was "themes as callbacks, never as forecasts." This held — but reality goes further: themes are barely named at all, even in closings. Only the title of the walk does the thematic work ("The Birthplace of the City", "Place des Vosges"). The body of the walk demonstrates the theme without naming it.
4. **Audio silence budget rule needs revisiting.** The parked rule was "audio ≤ 60% of tour time." Both empirical walks would land closer to 70–80% audio if you read them at 150 wpm — not because they violate the rule but because the walks are dense. The 60% budget might be aspirational; tour-builder should generate within an explicit time budget, not derive silence as a hard cap.

## New patterns (not in design.md, surfaced by empirical evidence)

1. **The Pariswalks sit-down opener is the gold-standard cold-open structure.** No `design.md` rule captured this. It goes: section heading → epigraph (optional) → practical info (starting point/métro) → walking direction + sensory aside → pronunciation of destination → inline definition of class word ("a place is a square") → physical orientation ("park in the middle, townhouses around") → sit-down with sensory invitation → cold-weather alternative → content signal ("Read the history of this place"). **This is the single most valuable pattern for audio-tour design.** When a tier-5 anchor lacks a `stop_orientation` beat with this structure, the cold open feels flat (per Île de la Cité walk experience).
2. **Address-level seasoning is the Pariswalks killer feature.** Eighteen mini-vignettes at Place des Vosges, each ~50–250 words, tied to a specific door/façade/window the user walks past. Prior corpus could not do this; v2 with `trigger_address` + the new beat-length-class system enables it. **This is the structural innovation that distinguishes Travlr-quality from Rough-Guide-quality.**
3. **Cross-source triangulation requires claim-level dedup, not raw-text dedup.** Vallois and LEG (legacy_unknown) on Notre-Dame had heavy overlap on canonical facts (Pilier des Nautes, Hugo's novel, Gargantua, Kings of Judah). They're not duplicates by raw text but by canonical claim. **Tour-builder must dedup at claim level, preserving complementary detail across sources.** This is the deferred B8 work.
4. **Glue is structural, not creative.** ~6–8 short navigational sentences across an entire walk. None make factual claims. Examples: "Now stand up. We're going to circle the square." / "Turn the corner east. The east side starts at no. 6." / "Settle in. Here's how this place came to be." Acceptable as runtime-generated structural connectors; NOT acceptable as runtime invention with claims.

## Concrete tour-builder requirements surfaced

These follow directly from the walks:

### Selection algorithm requirements

1. Given start point + duration + lenses, must select POIs by routing-aware score, with tier-5 POIs as anchor candidates and tier-3-and-below as seasoning.
2. Within each tier-5 anchor, must select beats by sub_location sequence (architectural walk-around) where sub_location populated, OR by trigger_address sequence (circumnavigation) for square/street POIs.
3. Beat selection must enforce length-class diversity — at least one anchor-class (200–400w) and several mid-class beats per tier-5 stop, with seasoning-class beats interleaved.
4. Cross-source triangulation must collapse redundant claims to one beat per claim while preserving complementary detail (the deferred B8 dedup).

### Generation pipeline requirements

5. **Cold-open structure** — for each walk, identify the "first stop" anchor and assemble the Pariswalks-format opener: orientation → pronunciation → inline definition → physical staging → sensory invitation → content signal. If a `stop_orientation` beat exists, use it. If not, generate one from the corpus's `physical_cues` + `pronunciation` fields.
6. **Anchor essay sequence** — at each tier-5 stop, sequence beats anchor (200-400w) → mid → seasoning, with sub_location ordering for buildings or trigger_address ordering for squares.
7. **Transit weaving** — connect stops with transit beats from the corpus when present; generate structural-connector glue when absent.
8. **Closing** — append physical closure ("you have now circled..." / "this is the end of the walk") + optional continuation pointer. No thematic summary.
9. **Voice consistency** — preserve inline foreign words, named persons, specific numbers, sensory anchors verbatim from beats. Glue is the only place runtime can write new prose, and glue must not make factual claims.

### Schema/data requirements (carry-forward from the campaign)

10. The `stop_orientation` gap: tier-5 anchors that lack a stop_orientation beat (e.g., Notre-Dame, Eiffel Tower, Sacré-Cœur) need one for proper cold-open. This is in the post-launch backlog; tour-builder must degrade gracefully when missing.
11. Vallois beats currently have lossy `physical_cues` (`{cue: <legacy string>, direction: "here", feature_type: "view"}`) from the migration. Tour-builder selection should not over-weight `physical_cues` for these beats; flag for re-extraction post-launch.
12. The 5 unowned migration-shell Areas (Tuileries, Visconti, Mouffetard, Grands Boulevards, Chanoinesse) plus the Latin-Quarter-overshoot-into-Notre-Dame issue — tour-builder must handle these gracefully or surface them as known data quirks.

## What tour-builder is NOT

- Not a frontier-model "write me a Paris tour" runtime. That costs $0.50–2/tour and invents constantly. Anti-pattern.
- Not a templated tour generator with hard-coded itineraries. Defeats the on-demand/personalization point.
- Not a beat-randomizer. Selection must be principled.
- Not editorializing. The 8 `feedback_tour_*` memories captured this. Reaffirmed by both walks.

## Open questions for tour-builder Phase 1 design

1. **Beat selection scoring formula.** The parked design.md proposed `score = importance_tier × beat_richness × interest_alignment × narrative_fit × distance_decay`. Does this hold up against the empirical walks? Specifically — what's the right `narrative_fit` formula given that cross-source claim-overlap is the actual signal?
2. **Stop budget.** Per `design.md`: "(planned_time - base_walk_time) / cost_per_stop". The empirical walks are 22 stops (PdV) and 12+ stops (Île). Anchor stops have 4–6 beats; seasoning stops have 1–2. Verify the budget math against the empirical walks.
3. **Theme discovery.** The parked design said themes emerge from entity overlap across selected POIs. The empirical walks didn't surface a clear theme (PdV is "the square's history"; Île is "the birthplace of Paris"). Was theme discovery actually used, or did the title carry the thematic work?
4. **Voice modulation per lens.** The parked `feedback_tour_tone_default.md` proposed lens-modulated word choice. Does this hold up empirically? The walks don't show clear lens modulations — it's house voice throughout.
5. **Round-trip vs one-way.** Both walks were one-way (PdV is a circular walk inside one square; Île de la Cité walks across the island). What does round-trip routing add? Specifically for Place des Vosges: do you START and END at Café Ma Bourgogne, or do you traverse the square in one direction? The empirical walk circled it.

These are the questions tour-builder Phase 1 design should answer.
