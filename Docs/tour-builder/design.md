# Tour Builder — Active Design Doc

**Status:** In active design. Building example tours by hand to derive the rules before writing the skill.
**Last updated:** 2026-04-11
**Companion artifacts:** see `examples/` for worked example tours.

---

## What we're building

A skill that generates a personalized walking tour on demand, given:
- A starting point (lat/lon)
- An available duration (e.g. "2 hours")
- A set of user interests (lenses)
- A round-trip vs. one-way preference

The skill pulls POIs and beats from the Neo4j graph, selects a coherent set, derives a narrative theme, and produces a fully-scripted audio walking tour with sentence-level source attribution.

The quality bar is **Detour app**: a tour that feels like a story, not a list of facts.

---

## The two test scenarios

These drive the design. We're working through them by hand before generalizing.

**Scenario 1:** User at a Latin Quarter hotel. 2 hr tour, history + architecture interests, round trip. *(In progress — see `examples/tour-a-survival-on-the-island.md`.)*

**Scenario 2:** Pre-trip planning. 4 hr tour from Eiffel Tower, art + faith interests, one-way. *(Not yet started.)*

---

## Core principles (the non-negotiables)

These are the rules everything else hangs off. Each maps to a feedback memory.

1. **No editorializing.** Every script sentence traces to a beat or a verifiable structural fact. No invented prose. (`feedback_tour_no_editorializing`)
2. **Themes emerge from beats.** Bottom-up only. Lenses filter the pool; shared entities/subjects determine the theme. (`feedback_tour_themes_emerge`)
3. **Themes as callbacks, never forecasts.** Interpretive theme statements only at the end, summarizing what the user has heard. (`feedback_tour_themes_as_callbacks`)
4. **Silence is design.** Audio ≤ 60% of tour time. (`feedback_tour_silence_budget`)
5. **Seasoning serves the spine.** Walk-by beats only if they share entity/time/theme with adjacent anchor. (`feedback_tour_seasoning_rule`)
6. **House voice + lens modulations.** Single narrator, modulated word choice and pacing per lens. (`feedback_tour_tone_default`)
7. **Runtime gets no world knowledge.** Generator prompted with only beats + glue whitelist. (`feedback_tour_runtime_no_world_knowledge`)
8. **Source-traceable output.** Every sentence carries a source ID; untraceable sentences fail validation. (`feedback_tour_source_traceability`)

---

## POI selection model

### Tier as gravity

`importance_tier` (1–5) IS gravity per North Star. Mapping:

| Tier | Role | Dwell |
|---|---|---|
| 5 | **Anchor** — unmissable headline POI | 4–6 min stationary |
| 4 | **Anchor or strong pause** — major destination | 3–5 min stationary |
| 3 | **Pause stop** — texture, named places | 2–3 min stationary |
| 2 | **Walk-by** — atmospheric mention while walking past | 0 min (audio plays during walking) |
| 1 | **Walk-by** — micro-mention if relevant | 0 min |

### Selection scoring

Interests are a **bias**, not a filter. Every POI in walking range is a candidate; interests tilt the scoring.

```
score = importance_tier
      × beat_richness          # log(active_beat_count + 1) so a 10-beat POI doesn't 10x a 1-beat one
      × interest_alignment     # 1.0 + (matching_lens_beat_count / total_beat_count) — multiplier, not gate
      × narrative_fit          # graph adjacency: how many entities/themes does this POI's beats share with already-selected POIs
      × distance_decay         # gentle penalty for distance from start, sharp penalty past max walk radius
```

`narrative_fit` is computed iteratively as the tour gets built — early stops have neutral fit, later stops are scored against what's already in.

### Beat selection within a POI

A POI with 12 beats does not get all 12 in the tour. Once a POI is selected, pick beats by:

1. Filter to active beats only
2. Strongly prefer beats whose lens or entities match the emerging tour theme
3. Prefer beats matching the user's interest lenses
4. Cap by total dwell time at the stop (≈ 2–4 beats per anchor, 1 per pause)
5. Ensure tone variety — don't pick three somber dark_history beats in a row at one stop

This is why the same POI yields very different scripts in different tours. **Same Notre-Dame, three different stories.**

---

## Time and dwell math

Real numbers from research and testing in Paris.

**Walking pace:** Tourist progress through central Paris with crowds, traffic lights, and looking-around: **~3 km/h actual progress** (not the 4–5 km/h Parisians commute at).

**Dwell per stop:**
- Anchor (tier 5): 4–6 min (looking + listening)
- Anchor (tier 4): 3–5 min
- Pause (tier 3): 2–3 min
- Walk-by (tier 1–2): 0 min (audio during walking)

**Audio rate:** ~150 words/min spoken. A 3-min beat ≈ 450 words.

**The "free" insight:** Audio that plays during walking time costs nothing on the clock. Audio at stops is added time. So the script can be much longer than the stop time would suggest, as long as most of it plays while moving.

**Buffer:** 15% on top of computed total. Accounts for traffic lights, photos, bathroom, getting briefly turned around.

**The "err short" rule:** When user says "2 hours," target a planned budget of 95–105 min. Reality plus the 15% buffer lands them at 110–125 min. If they finish early they're delighted; if they finish late they're annoyed. Always err short.

**The "honest length" rule:** If the strongest tour from a starting point fits in 60 min, deliver a 60-min tour and tell the user upfront. Don't pad. The app should offer an "extend the tour" option if they want more, not silently dilute the spine. *(With richer beat data this becomes less of an issue — see seasoning rule.)*

---

## Narrative structure

Every tour is a single script with natural breakpoints, not a collection of independent stop monologues.

**Required elements:**

1. **Cold open** — at the starting point, before any walking. Anchored in something the user can see right now. Sets up a *concrete hook* (a fact, a question, a sensory observation), NOT an abstract theme. Sourced from a real beat.
2. **Connective navigation** — between stops, navigation glue + walk-by seasoning. Pure structural language for navigation, sourced beats for seasoning.
3. **Stop blocks** — 1–3 beats per stop, ordered by function (architecture/setup → story/character → consequence/twist). Built-in "look at the thing" silence after the audio.
4. **Walk-bys** — short audio mentions that play *while the user is walking past* a tier-1/2 POI. Must share entity/time/theme with a nearby anchor.
5. **Closing callback** — at the end, summarizes the theme by referencing beats the user already heard. Where any interpretive claim about the tour's meaning belongs.

**Forbidden:**
- Cold opens that name an abstract theme upfront ("This tour is about X")
- "Imagine" / "picture this" framing
- Wall-to-wall narration with no breathing room
- Walk-bys that don't connect to the spine
- Any factual claim not traceable to a beat

---

## Competitive research & quality signals (April 2026)

What separates great audio tours from mediocre ones? Research across Detour, Viator, Fat Tire, Rick Steves, VoiceMap, Questo, izi.TRAVEL, GetYourGuide, and academic heritage interpretation literature converges on three capabilities:

### 1. Sensory anchoring — the #1 quality signal

Every source points to "what you can see right now" as the single strongest differentiator.

- **Detour** (the gold standard, acquired by Bose 2018): GPS-synced narration meant the narrator described what you were looking at at the exact moment. Production borrowed from public radio — hired Radiolab and Ken Burns collaborators. Each tour took 3 months, cost tens of thousands, 8,000-12,000 word scripts.
- **method-writing.com** (professional audio guide scriptwriting): "An actual object that can be seen is often a stronger choice than a story about something that can't be seen."
- **VoiceMap** (600+ destinations, GPS-triggered): Their system checks that "talk times match travel times from one location to the next." Their own docs warn that creators "sometimes get bogged down... resulting in a list of facts instead of stories, with physically obvious landmarks presented at the forefront instead of the compelling stories that make the walk engaging."
- **Viator 5-star Paris reviews** consistently praise guides who point at things and share "lively stories to add further colour to each site."
- **Viator 3-star reviews** consistently criticize "no real direction on how to walk" — the navigation/sensory void.

**Implication for Travlr:** The `sensory_anchor` beat field is architecturally essential. Without it, the tour builder can't distinguish beats that require the user to be looking at the thing from beats that work anywhere. Misplaced sensory beats are jarring; correctly placed ones are the Detour secret sauce.

### 2. Narrative threading — stories, not facts

- **Freeman Tilden's Principle #2** (the foundational text of heritage interpretation, 1957): "Information, as such, is not interpretation. Interpretation is revelation based upon information." A date is information. Why that date changed everything is revelation.
- **Sam Ham's TORE framework** (University of Idaho): Effective interpretation must be Thematic, Organized, Relevant, and Enjoyable. "Presenting a strongly relevant theme greatly increases the likelihood an interpreter will succeed in provoking an audience to think."
- **Springer 2022 study** on audio in heritage storytelling: four concepts drive audience engagement — perceived realism, narrative transportation, emotional engagement, and character identification.
- **Detour's approach:** tours were "serialized urban documentaries" with character-driven narratives. Narrators had genuine personal connections (the Castro tour by activist Cleve Jones, the Suffragettes tour by Dr. Helen Pankhurst).
- **Tour A validation:** the "Survival on the Island" theme was discovered by spotting shared entities across beats (Marcel uprising → Conciergerie origin → Revolution prisoners → Communard arson). Neither beat alone tells the story. The cross-POI graph adjacency is what creates arc from facts.

**Implication for Travlr:** The `entities` field powers this. Without entity extraction, theme discovery requires reading every beat's raw text — either by a human or by a frontier model at runtime ($0.50-2.00/tour, the anti-pattern).

### 3. Structural variety — pacing, silence, and beat function

- **Cognitive science** (Henna Wang): "Working memory thrives when input is voluntary, contextual, and spatially anchored — not delivered as a relentless feed." Recommend 8-12 seconds of ambient audio between clips.
- **Driftscape guide:** "When a tour feels like a history lecture on foot, people treat it like optional homework. But when you treat it like a mission or a story, you turn a passive stroll into an immersive travel experience." Recommends the "breadcrumb method" — end every stop with a teaser for the next one.
- **Rick Steves:** Proves brisk pacing and genuine enthusiasm carry weight even without production polish. But also proves audio-only navigation without GPS breaks down on busy city streets — "it was hard to listen to him when navigating through busy streets."
- **Fat Tire Tours:** Guided tours' strength is the human guide who adapts in real time — reads the moment, connects story to what's visible, adjusts pacing. Self-guided audio must replicate this structurally.
- **Heritage walking tour design literature:** "The order of stops matters and should aim for a narrative arc — start with a provocative hook, then develop context, introduce key figures, raise tensions, and resolve with a reflective final stop."

**Implication for Travlr:** The `narrative_function` and `beat_type` fields enable this. Without them, the tour builder can't distinguish a cold-open hook from a deep dive from a walk-by factoid. The 60% silence budget is validated by the research, but enforcing it requires `est_spoken_seconds`.

### What bad tours get wrong (failure modes to prevent)

Every source identifies the same failures:

1. **Facts without stories.** Tilden, VoiceMap, and Viator reviews all converge: reciting dates and names without narrative wrapping kills engagement.
2. **Navigation failures.** Getting lost destroys trust immediately. GPS-triggered audio is not a luxury — it's necessary.
3. **Pacing mismatch.** Audio that keeps playing when the listener has stopped. Silent gaps that don't match walk times.
4. **Wall-to-wall narration.** No breathing room. The listener can't process or look around.
5. **No sensory anchoring.** Talking about things the listener cannot see.
6. **Marketplace quality inconsistency.** GetYourGuide axed self-guided tours entirely because quality was uncontrollable across creators. Questo quality varies wildly by city. The in-house production model (Detour) produced the best results but didn't scale economically. Travlr's "expensive at ingest, cheap at runtime" approach threads this needle.

### Detour insight worth noting

Detour's use of first-person narrators with genuine personal connections created emotional engagement that third-person narration cannot match. Travlr's beat data is book-sourced and third-person. Future data ingestion could capture first-person primary-source quotes (letters, diaries, trial transcripts) as a distinct beat type that the runtime weaves in as character voices — even within TTS, a shift to direct quotation ("As Marie Antoinette wrote to her mother...") creates a different register than pure narration.

### Sources

- [TapSmart Detour Review](https://www.tapsmart.com/apps/review-detour-immersive-audio-tours/)
- [KQED Andrew Mason Interview](https://www.kqed.org/about/5790/interview-detour-andrew-mason)
- [VoiceMap Publisher Docs](https://docs.voicemap.me/tour-publishers/read-this-before-creating-your-self-guided-audio-tour/)
- [method-writing.com Audio Guide Script](https://method-writing.com/how-to-write-an-audio-guide-tour-script/)
- [Driftscape Tour Design Guide](https://www.driftscape.com/post/self-guided-walking-tour-how-to-design-a-route-people-actually-finish)
- [Freeman Tilden via SavedByNature](https://www.savedbynature.org/post/freeman-tilden-the-father-of-heritage-interpretation-people-of-the-parks-past-series-8)
- [Sam Ham's TORE / Wikipedia](https://en.wikipedia.org/wiki/Thematic_interpretation)
- [Springer 2022 — Audio in Heritage Storytelling](https://link.springer.com/article/10.1007/s11042-024-19288-4)
- [Arival — GetYourGuide Axes Self-Guided](https://arival.travel/article/getyourguide-axes-self-guided-tours/)
- [Oral History Walking Tour Design](https://oralhistory.ws/resources/designing-historical-walking-tours/)

---

## Beat metadata wishlist

The current beat schema (just `script_body`, `lens_tags`, `duration_sec`) is too thin for the selection algorithm to work well. The pipeline needs to extract richer metadata at ingest time so runtime selection is fast and cheap.

**Proposed additions** (to be added to `beat-from-book` and related skills), prioritized by competitive research (see above) and Tour A construction experience:

### Tier 1 — The tour doesn't work without these

| Field | Type | Purpose | Research backing |
|---|---|---|---|
| `entities` | list[string] | People, events, places mentioned. Powers cross-POI threading, theme discovery, and `narrative_fit` scoring. Tour A's entire "Survival" theme was found via shared entities across 4 POIs. | Tilden #5 (present the whole). Detour's serialized documentary approach. |
| `sensory_anchor` | boolean | References something the user can see/hear/smell right now? Without it, the builder can't distinguish beats that require physical presence from beats that work anywhere. | #1 quality signal across all sources. method-writing.com: "visible object > invisible story." |
| `est_spoken_seconds` | int | Precomputed from word count at ~150 wpm. Without it, the 60% silence budget is unenforceable and dwell-time budgeting is guesswork. | VoiceMap checks talk-time vs walk-time. Cognitive science: working memory needs pauses. |

### Tier 2 — The tour works but is mediocre without these

| Field | Type | Purpose | Research backing |
|---|---|---|---|
| `narrative_function` | enum | What role can this beat play? `hook`, `deepen`, `transition`, `climax`, `callback`, `scene_setter`, `establishing`. Without it, cold opens are random and stop sequencing is flat. | Driftscape breadcrumb method. Heritage interpretation: provocative hook first. |
| `beat_type` | enum | What kind of content? `anecdote`, `architectural_detail`, `character_story`, `event`, `sensory_observation`, `factoid`, `establishing`. Enables within-stop sequencing (architecture → story → consequence). | Sam Ham's TORE: "Organized" = easy to follow. |
| `emotional_register` | enum | Tone: `reverent`, `somber`, `playful`, `dramatic`, `wry`, `neutral`. Prevents whiplash — three somber beats in a row at one stop. | Springer 2022: "emotional engagement" as key driver. |

### Tier 3 — Defer (derivable or low-signal)

| Field | Type | Why defer |
|---|---|---|
| `time_period` | enum | Useful for temporal arcs, but `entities` captures most of this implicitly (Marie-Antoinette → Revolutionary era). Could be derived at runtime or added in a follow-up pass. |
| `requires_setup` | boolean | Useful safety check, but `standalone_quality` captures the same signal from the other direction. |
| `standalone_quality` | int 1–5 | Useful for thin stops (tier 3 POIs with 1 beat), but the selector can approximate from beat count + narrative_function. |

**Recommended scope: enrich Tier 1 + Tier 2 (6 fields). Defer Tier 3.**

`est_spoken_seconds` is pure computation (word count ÷ 2.5) — no AI needed. The other 5 require an AI extraction pass over each beat's `script_body`.

### POI-level addition

Tour A also surfaced the need for a `poi_role` field on POI nodes:

| Value | Meaning | Example |
|---|---|---|
| `stop` | Destination where the user stops and listens | Notre-Dame, Sainte-Chapelle |
| `setting` | Geographic container whose beats serve as walking-transition narration | Île de la Cité |
| `walk_by_only` | Never a stop; beats play while walking past | Small plaques, minor landmarks |

The Île de la Cité is tier 5 but functioned as walking-narration spine in Tour A, not as a destination. Without `poi_role`, the builder would try to route users to "stop at" a 22-hectare island.

### Cost model

Extracting these at ingest is one-time per beat, batched, expensive model OK (Sonnet/Opus). Runtime selection then becomes fast graph queries + light stitching by a cheap model (Haiku). This is what keeps per-tour cost low at scale.

---

## Generation cost architecture

The whole system is designed around: **expensive at ingest, cheap at runtime.**

- **Ingest (per beat, one time):** Opus/Sonnet extracts entities, themes, narrative function, sensory anchor. ~$0.01 per beat. 1M beats = $10K one-time.
- **Runtime selection (per tour):** pure graph queries. Effectively free.
- **Runtime stitching (per tour):** Haiku, tightly prompted, no factual freedom. Generates ~10–20 short connective sentences and applies tone modulations to selected beat texts. ~$0.01–0.05 per tour.
- **TTS:** the dominant runtime cost. Minimized by the silence budget (less audio = less TTS).

**Anti-pattern:** asking a frontier model to "write me a Paris tour" at runtime. That's $0.50–2.00 per tour and the model invents constantly. We never do this.

---

## House voice & lens modulations

See `feedback_tour_tone_default.md` for the full table.

**Default voice:** 2nd person, present-then-past, conversational but literate, names its uncertainty, never says "imagine."

**Per-lens modulations:** word choice and pacing changes only — TTS voice is constant within a tour.

---

## Allowed structural operations (refinements to the no-editorializing rule)

These are operations the script generator may perform that don't constitute invention. All discovered during Tour A drafting.

1. **Arithmetic on numeric facts in cited beats.** "Four hundred years later" / "forty years later" — computing differences between dates that appear in the cited beats is allowed as a structural connector, provided the arithmetic is correct and the inputs come from beats. Mark with `[ARITH]` in source attribution.

2. **Structural sensory callouts.** Pointing at a currently-visible feature adjacent to a beat's subject ("the hospital just to the north of the parvis, on your left") is allowed if and only if the feature is verifiable in the database or on a map. These add real-world pointers to beat-sourced facts; they don't introduce new claims.

3. **Cross-POI structural callbacks.** Referencing earlier moments in the same tour ("the building you stood in front of half an hour ago") is always allowed and is the preferred way to build narrative continuity without introducing new facts. Tour-internal pointers create memory and connection without risk.

4. **Place-name etymology when in a cited beat.** If a beat explains why a place is called what it's called, the script can cite that — and these are killer cold-open hooks because they're sensory-anchored (the user is standing in the named place). Heuristic: when scoring beats for cold-open candidates, prefer beats that explain the user's current location's name.

5. **Light paraphrase of beat content.** The script may rewrite a beat sentence in different words for tone/flow as long as no new factual claims are introduced and no claims are removed that change meaning. Mark with paraphrase indicator. Tested in Tour A: works as long as the source ID still points back to the beat text and the diff is verifiable.

## Closing callback time budget

The closing callback gets **3–5% of total tour time minimum**. The closing is where the theme is named and earned; rushing it wastes the rest of the tour. Tour A's closing was ~3 min of a ~70 min tour (~4%) and felt right.

## Open questions

These are the unresolved decisions to discuss next sessions:

1. **Interest bias formula.** What multiplier strength on `interest_alignment` is right? Too weak → tour ignores user's interests. Too strong → tour skips obvious anchors that don't match interests. Need to test against scenarios 1 and 2.
2. **Theme-naming threshold.** How many supporting beats does a theme need before the closing callback can name it? Tour A had 6 strong supporting beats for "survival" — that felt comfortable. Probably ≥4 is the floor.
3. **Round-trip vs one-way routing.** For round trip, prefer geographic loops; for one-way, prefer "spine" routes that end at notable locations. How do we score routes? Open.
4. **What happens when interests don't have enough beat coverage?** Scenario 2 has only 9 `historic_worship` beats globally. The user picked faith as one of two interest categories. How does the algorithm handle this? Probably: degrade interest weight when the matching pool is thin, surface stronger nearby content from related lenses. To work out in Scenario 2.
5. **Multi-city scaling.** All current rules are derived from Paris data. Need to confirm they generalize.
6. **The "extend my tour" UX.** If we honestly deliver a 70-min tour for a 2-hr ask, how does the user extend it? Do we pre-compute a longer alternative, or do we do it on demand?
7. **Sensory-anchor placement precision.** Walk-by beats with sensory anchors need to play at the right physical moment. GPS trigger? Time-based estimate from walking pace? Requires runtime work.
8. **POI roles: `stop` vs `setting` vs `walk_by_only`.** The Île de la Cité is a tier-5 POI but has no fixed stop point — it IS the island. Its beats functioned as walking-transition narration bridging other anchors. Tour A used it that way naturally. Suggests a `poi_role` field on POIs so the algorithm knows which POIs are destinations and which are setting/spine.
9. **`establishing` beat type.** The Pont Neuf had zero beats that simply explain what the bridge IS (its age, builder, when). Every Pont Neuf beat assumes the user knows. Without an `establishing` beat type, the script has to either improvise structural sentences (invention risk) or jump straight into a story without setup (jarring). Add to beat metadata wishlist and to the `beat-from-book` extraction prompts.
10. **Beat length distribution at extraction time.** The Conciergerie Sanson-family beat is 96 seconds — substantially longer than most others. Long beats are harder to fit into stops. Should the extraction pipeline prefer to break long beats into multiple shorter ones, or keep them whole? Probably whole, with `est_spoken_seconds` metadata so the selector can budget.

---

## Lessons captured so far (from Tour A drafting)

These all became feedback memories or live in this design doc. Listed here for visibility:

**Core rules (memories):**
- Don't editorialize — every sentence sourced
- Themes emerge from beats, not labels
- Themes only as closing callbacks
- Silence is design (60% audio cap)
- Seasoning serves the spine
- Default voice + per-lens modulations
- Runtime gets no world knowledge
- Source-traceability is mandatory

**Design observations (this doc):**
- Honest length over padded length (today; richer data changes this)
- The same POI yields different scripts under different themes (beat selection is the lever)
- Place-name origins are killer cold-open hooks (Sainte-Chapelle → Place Saint-Michel)
- Cross-POI graph adjacency is the killer feature (Île de la Cité Marcel beat + Conciergerie origin beat together explain why the palace became a prison; neither alone does)
- Some POIs are settings, not stops (Île de la Cité functioned as walking-narration spine, not as a destination)
- Some POIs lack establishing beats (Pont Neuf has no beat that explains what the bridge IS — every beat assumes you know)
- Per-lens tone modulations are embedded in how beats are paraphrased, not bolted on afterwards
- Arithmetic on beat dates and structural sensory pointers are useful operations that need explicit allowance (see "Allowed structural operations" above)
- Source-traceability caught seven hallucination attempts in one careful hand-drafted pass — at scale this discipline is non-optional
- Closing callbacks need real time budget (3–5% of tour minimum)

**Data-side findings:**
- The user found a major gravity-tier bug during this session — tier values now match the model
- Paris dataset has known hygiene issues (see `feedback_tour_data_hygiene_paris` memory)
- Beat length varies wildly (24s to 96s); selector needs `est_spoken_seconds` metadata to budget
