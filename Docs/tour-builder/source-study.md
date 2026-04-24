# Guidebook Source Study — Observations (not rules)

**Status:** Observations from reading real Paris guidebooks. Pending validation against our own writing.
**Purpose:** Replace the parked rule-forward `design.md` approach. Learn by example before codifying anything.
**Created:** 2026-04-22.
**Scope:** Rough Guide to Paris (14th ed), Frommer's 24 Great Walks in Paris, Pariswalks (Landes).
**Not yet studied:** Rick Steves Paris, Around and About Paris (Vallois), A Walk Through Paris (Hazan).

> ⚠️ **This is NOT a design doc.** Do not treat entries here as rules. They are observations from three source books. A rule only earns its place in the project after it survives contact with our own written output on real Paris beats. The predecessor `design.md` became a rulebook before any example existed — this doc exists to *not repeat that*.

---

## What was read

| Book | Passages studied | Lines in pdftotext extract |
|---|---|---|
| Rough Guide | Conciergerie entry; Place des Vosges entry + surrounding Marais intro; Notre-Dame entry (Cathédrale, Façade, Towers, Interior, Kilomètre zéro, Crypte archéologique, Mémorial, "School for Scandal" sidebar) | `/tmp/rg.txt` 2248–2515 (Islands ch.); 5948–6100 (Marais) |
| Frommer's 24 Walks | Walk 1 "Birthplace of the City" end-to-end | `/tmp/frommers.txt` 265–553 |
| Pariswalks | Walk 4 "Place des Vosges" end-to-end (start → close); sample of Walk 3 (rue Bonaparte address-by-address) | `/tmp/pariswalks.txt` 4539–5911 (Walk 4); 4100–4300 (Walk 3 sample) |

All content cited below comes directly from the extracted PDF text. Line refs are to the `/tmp/*.txt` extracts (reproducible with `pdftotext -layout` on the originals in `Books/Paris/`).

---

## The three books are three genres

The most important observation: Rough Guide, Frommer's, and Pariswalks are not three voices writing the same thing. They're three different structural genres. Our audio tours do not need to pick one — on-demand generation lets us mix, which none of these books can.

| | Rough Guide | Frommer's 24 Walks | Pariswalks |
|---|---|---|---|
| Role | Reference book | Scripted walking route | Literary walking essay |
| Reader's choice of path | Yes | No | No |
| Turn-by-turn directions | None | Every stop | Every stop, leisurely |
| Words per minor POI | ~150–250 | ~150–200 | 20–200 (address-level vignettes) |
| Words per major POI | ~500–700 (in sub-entries) | ~200–400 (split over 2 stops) | 1000–2000+ (as anchor for whole walk) |
| Major-to-minor scaling ratio | 4–5x | ~3x | 20x+ (one anchor carries the walk) |
| Voice person | 3rd (never "you") | 2nd person imperatives for directions; 3rd for story | "We" and "you" freely |
| Authorial editorializing | Parenthetical, dry wit only | Rare | Occasional one-word asides ("Nice fellow.") |
| Foreign-word glossing | Sparing, inline | Sparing | Constant, with pronunciation |
| Pre-story sensory framing | No | No | **Yes** — sits reader down before content |
| Opens with | POI name + practical info | Multi-paragraph grounding essay, then directions | Epigraph → practical → direction → sensory setup → *then* content |
| Closes with | N/A (reference) | Practical navigation to end or continuation | Physical closure ("you have now circled") + optional continuation, no thematic summary |
| Throughline mechanism | None (reader's choice) | Implicit temporal (Celtic → Roman → medieval → modern) | Spatial (one place, all its stories) |

---

## Question 1: How length scales with POI importance

### Rough Guide — clean 4–5x scaling via sub-entries

Conciergerie = 1 entry, 2 paragraphs, ~180 words (lines 2251–2277).

Notre-Dame = 4 sub-heads — **Cathédrale** (intro, ~280 words) → **The façade** (~220 words) → **The towers** (~160 words) → **The interior** (~180 words) — plus satellite entries **Kilomètre zéro**, **Crypte archéologique**, **Mémorial de la Déportation**, plus a sidebar **School for Scandal** on Abélard & Héloïse (~120 words). Total ~1300 words on the Notre-Dame complex.

**Mechanism:** a major site earns sub-heads. Each sub-head is a self-contained unit. Reader can skim sub-heads.

### Frommer's — compressed ~3x scaling, stops held near-equal

Conciergerie narrative = ~10 lines, embedded in walking directions (lines 320–343).

Notre-Dame narrative = ~45 lines across two stops — façade (stop 4) + interior and buttress-garden (stop 5) (lines 485–548).

**Mechanism:** the walk has to keep moving. Frommer's deliberately levels stops so no single site overwhelms the journey.

### Pariswalks — extreme scaling via anchor-spine

Walk 4 is ~1400 lines focused on **one square**, Place des Vosges. The square is the entire walk's spine. "Minor stops" are individual addresses around the square — no. 2, no. 6 (Hugo's house), no. 8 (Gautier), no. 14 (Abbé de la Riviére / synagogue), no. 16 (François le Roux). Each address is a 50–200-word vignette. The anchor essay (before circumnavigation) is ~1000 words.

**Mechanism:** pick one anchor, make it the spine, season with address-level vignettes. There is no "medium-sized" stop in Pariswalks — it's binary.

### What we can do that the books can't

Because we're on-demand per tour, **a single tour can contain Rough-Guide-scale tier-3 stops *and* Pariswalks-scale tier-5 anchors.** A published book has to pick one scale. We don't. This is the strongest single argument for our architecture.

---

## Question 2: Voice, narrative flow, construction

### Rough Guide voice — dry wit inside reportorial prose

Never uses "you." Observes. Slips judgment inside parentheticals. Compresses big history into one sentence with a sly ending.

> "Napoleon restored some of the cathedral's prestige, crowning himself emperor here in 1804, though the walls were so dilapidated they had to be covered with drapes to provide a sufficiently grand backdrop." *(Rough Guide, line 2418–2421)*

> "Viollet-le-Duc's parting contribution was a statue of himself among the angels lining the roof: it's the only one looking heavenwards." *(Rough Guide, line 2430–2431)*

> "(Gothic architecture was particularly favoured by Romantic novelists, who deemed the soaring naves of the great cathedrals singularly suited to sheltering 'tormented souls')." *(Rough Guide, line 2425–2426)*

### Frommer's voice — bold imperative for nav + compressed 3rd-person story

Visual and tonal separation: bold direction line, then narrative.

> "**From the statue, cross the road into place Dauphine and turn left into rue de Harlay, walking around the Conciergerie. Turn right into boulevard du Palais, cross over to place Louis Lepine, stopping to admire the Conciergerie and the Sainte-Chapelle.**
>
> The Conciergerie was the royal palace before the Louvre was built. During the Revolution it became a prison where some 2,600 prisoners were kept before being guillotined." *(Frommer's, lines 332–343)*

Note the mode switch: "you do X" → "here's what to know."

### Pariswalks voice — scholar-friend with one-word editorial asides

Freely uses "we" and "you." Drops authorial asides that are short, aimed at dead people, and never at the city itself.

> "Not all the action in the place was outdoors. The place Royale was the center of Parisian social life, and such fashionable ladies of the neighborhood as Ninon de Lenclos and Marion Delorme invented a new and durable institution. They met at intimate gatherings called *rvelles* [sic, = ruelles], at which the elegant guests rivaled one another in wit, fine speech, and social finesse. Molière parodied their excesses in his play *Les Précieuses Ridicules*." *(Pariswalks, lines 4758–4765)*

> Regarding the Prince de Condé, who imprisoned his own wife on faked charges: "**Nice fellow.**" *(Pariswalks, line 5852)*

> Author anecdote: "Once, when we were sitting on a stone ledge in the big courtyard on the quai Malaquais, wondering where the spirit of art students had gone, we were suddenly doused with cold water from a balcony above. Amid gales of laughter, we were told how lucky we were it hadn't been ink or paint." *(Pariswalks, lines 4295–4299)*

**Observation about editorial register:** Pariswalks *does* editorialize, but narrowly. The targets are historical people (dead, distant, safe to judge). The city itself never gets a value judgment. The one exception in Walk 4's closing allows one sentence: "The area is so rich, now the richest in history and monuments in all Paris, that we have ended this walk here" — and that's *it* for city-level editorializing across ~1400 lines.

### Construction patterns shared by all three

These are consistent across all three books, which makes them safer than single-book patterns:

1. **Specific numbers, never round.** "1301–15" not "early 1300s." "2,600 prisoners" not "thousands." "April 5, 6, 7, 1612" not "in 1612." "13-ton Emmanuel Bell" not "a huge bell." Specificity signals authority and sticks.

2. **A named human in every entry.** Even tiny ones. Buildings without people don't get written about. Marie-Antoinette, Henri IV, Jacques de Molay, Viollet-le-Duc, Mme de Motteville, Théophile Gautier.

3. **Foreign words embedded then glossed, in the same sentence.**
   - Rough Guide: "pailleux, prisoners who couldn't afford to bribe a guard for their own cell and had to sleep on straw (paille)." *(line 2255–2257)*
   - Pariswalks: "Marais (marsh)", "hôtel (grand private residence)", "ravalement (cleaning of the facades)", "poule-au-pot... Henri IV's promise of a 'chicken in every pot.'"
   - Rule observed: never assume the reader knows the French word.

4. **Sensory detail anchored to something still visible.** Weirder = stickier.
   - Rough Guide: "a mock-up of Marie-Antoinette's cell in which the condemned queen's crucifix hangs forlornly against peeling fleur-de-lys wallpaper."
   - Frommer's: "The westernmost tower facing the Seine is where prisoners were tortured. Since their screams could be heard across the river, it is called the Tour Bon Bec, meaning 'Big Mouth Tower'."
   - Pariswalks: the bronze gypsy statue on the stairwell with one lost earring and missing lantern.

5. **Compression of long history into a single sentence with a wry ending.** See the Napoleon/drapes line above. Shared across all three.

---

## Question 3: Tour construction — openings, closings, grounding, throughline

### Opening patterns

**Frommer's Walk 1 — front-loaded grounding essay before the first step.**

Six paragraphs (lines 269–295) before any walking instruction. Content sequence: Celtic Parisii 3rd century BC → Roman invasion 52 BC → Lutetia → Parisii as boat-builders → the ship symbol adopted by Romans → *Fluctuat Nec Mergitur* motto (still used today) → east/west divide on the island preserved to today → medieval Notre-Dame replaced Roman temple to Jupiter → 19th-c. Haussmann demolition → modern Mémorial de la Déportation. "2,000 years of history can be traced here" closes the grounding. *Only then* the walk starts: "Leave Pont Neuf Metro station and cross the bridge, admiring the magnificent views. Stop halfway, at the statue."

**Pariswalks Walk 4 — compact frame but strong sensory staging.**

Exact sequence (lines 4539–4566):

1. Section heading: **Place des Vosges**
2. Epigraph — Victor Hugo quote in French
3. Epigraph translated to English
4. Practical info: Starting Point / Métro / Buses
5. Walking direction + sensory aside: *"Walk up the rue de Birague (stop and look at interesting shops) and continue into the place des Vosges..."*
6. Pronunciation of destination on first mention: *"(pronounced plass-day-voge)"*
7. Inline definition of the class word: *"A place is a square"*
8. Physical orientation: *"this one has a large park in the middle and symmetrical townhouses all around"*
9. Sit-down instruction with sensory invitation: *"Sit in the garden near the children's area so that you can watch the children play à la française (despite the mix of Hebrew, Yiddish, and Arabic you'll hear)."*
10. Weather alternative: *"If it is cold, try the café Ma Bourgogne, on the northwest corner of the place."*
11. Content signal: *"Read the history of this place and some of its surroundings."*

**Then ~1400 lines of content.** This structure is arguably the single most valuable pattern in the three books for audio-tour design: it **physically stages the listener** (where to sit, what direction to face, what to look at, cold-weather fallback) before any story plays.

**Rough Guide chapter openings** — brief scene-setter paragraph per neighborhood, then straight into POI entries. Not walk-shaped.

### Closing patterns

**Frommer's Walk 1 close (lines 549–553):**

> "End the walk here or carry on with Walk 9 by crossing the Pont St-Louis to the Île St-Louis. The nearest Metro station, Hôtel de Ville, is at the far end of Pont d'Arcole."

**Pariswalks Walk 4 close (lines 5906–5911):**

> "You have now completely circled the place des Vosges. The area is so rich, now the richest in history and monuments in all Paris, that we have ended this walk here. But if you still have the strength, the walk continues in Walk 5, right outside the place. Exit the place from the northwest corner, by Ma Bourgogne, and turn left onto the rue des Francs-Bourgeois."

**Observation (this was a big revision):** Neither book thematically summarizes. No "we saw three ways the Revolution shaped this island." No "the tension between royalty and revolt threads through every stop." The closes do exactly two things:

- **Physical closure signal** — "you have now circled" / "the memorial ends this walk"
- **Optional continuation** — "end here or carry on with Walk 9"

Pariswalks allows itself exactly one editorial clause ("the richest in history and monuments in all Paris"). That's the *entirety* of city-level editorializing across the walk's ~1400 lines.

This directly contradicts the parked design doc's "closing callback honors every hook" rule.

### Grounding patterns

- **Frommer's:** Front-loaded per walk. A compact history essay establishes the frame, then each stop delivers minimal new context.
- **Pariswalks:** Distributed. The main anchor gets a heavy history lesson; individual stops add context just-in-time as the walker arrives at each.
- **Rough Guide:** Per entry. Each POI is self-contained.

For on-demand audio tours, the interesting observation is that **grounding style may be a user-selectable dimension**: a first-time visitor wants Frommer's front-loaded frame; a returning visitor wants Pariswalks' distributed-as-you-go grounding. The same beats could serve either order.

### Throughline patterns

- **Frommer's Walk 1 = implicit temporal throughline.** Stops follow Paris's chronology: Celtic/Roman (Pont Neuf, place Dauphine area) → medieval (Conciergerie) → Gothic religion (Sainte-Chapelle, Notre-Dame) → 19th-c. (flower market, Hôtel-Dieu) → modern (Mémorial de la Déportation). *Nothing in the text names the chronological structure.* The reader feels it. The title "Birthplace of the City" plus the route ordering does the work.

- **Pariswalks Walk 4 = spatial throughline.** One square, circumnavigated. The through-question is "who lived in each of these houses?" — answered address by address.

- **Rough Guide = no throughline.** Reference format. Reader supplies the throughline.

**Key observation:** in both Frommer's and Pariswalks, the throughline is **implicit, never declared.** The title does the heavy lifting. "Trace the origins of Paris" appears once (Frommer's intro). Nothing similar in the body of either walk.

---

## Question 4: Seasoning — the Pariswalks specialty

Seasoning = the small facts threaded along the walking path *between and around* anchor stops. Pariswalks is a master class.

### Structure of a Pariswalks seasoning item

Each seasoning vignette contains:

1. **Spatial anchor** — a specific address, wall plaque, gate, window, or statue
2. **Named person + specific date**
3. **One-to-three-sentence micro-narrative**
4. **Tone signature** — dry, bawdy, wistful, sarcastic
5. **Implicit link back to the anchor story** — the anchor already introduced the vocabulary; the seasoning uses it

### Four examples of Pariswalks seasoning, by register

**Quotidian** (line 5802–5804):
> "No. 8, as the plaque tells us, was the home of the poet Théophile Gautier, who lent his name to the technical high school next door."

**Bawdy, with inline French translation** (line 5714–5720):
> "No. 16 was owned in the seventeenth century by a royal counselor named François le Roux, who had the dubious distinction of marrying 'une petit garce qui se donnait pour un quart d'écu' (a little bitch who gave herself for a quarter of an écu). That was slightly less than a livre, but in those days a livre was a day's wages for a manual worker, so Mme le Roux was not so cheap after all."

**Charming and contemporary** (line 5703–5713, the bronze gypsy):
> "Take a look at the bronze statue of the gypsy, in the stairwell on the left. She has lost the lantern from her left hand and one earring. The concierge proudly told us that Victor Hugo put the statue there, but we have not found mention of that anywhere else. We do know for a fact, though, that the gypsy was stolen some years ago. A woman resident called the police and got immediate results. The statue was found minutes later at the traffic light on a nearby corner. Her head was sticking out of the back of a pickup truck."

**Dark and cinematic** (line 4584–4589, from the anchor's Henri II joust):
> "For ten days Henri suffered. The greatest doctors were called; Ambroise Paré and Andreas Vesalius came all the way from Brussels. Four criminals under sentence of death were decapitated so that the doctors could study their cranial anatomy, but to no avail."

### The key observation about seasoning

**Seasoning only works because the anchor came first.** You cannot drop a précieuse vignette at no. 6 place des Vosges until the reader knows what a précieuse is.

The Pariswalks ordering:
1. Long anchor essay at the square introduces the vocabulary: the square's history, Henri IV's vision, duels as a social institution, précieuses as a social institution, Ninon de Lenclos and Marion Delorme as exemplars.
2. *Then* circumnavigate, dropping seasoning at each house. The house-level vignettes assume the reader knows what a précieuse is, what a ruelle is, what trompe-l'oeil is, what ravalement means.

This is more specific than the parked design doc's "seasoning must share entity/time/theme with the adjacent anchor." The actual pattern is: **the anchor teaches the vocabulary; the seasoning uses it.** A seasoning vignette does not need to reference the anchor's characters — it just needs to use a concept the anchor already grounded.

### Seasoning in the other two books

**Frommer's seasoning is structural.** Two mechanisms:

- Sidebar callouts ("Where to Eat" with three brasseries, addresses, phone numbers) — zero narrative integration.
- One-sentence cinematic facts embedded mid-paragraph. Example from the Pont Neuf stop (lines 312–315): *"The original statue of Henry IV was melted down during the Revolution. The anti-Royalist who replaced it secretly hid a statuette of Napoleon in the horse's belly; this was recently discovered during restoration work."* This is a perfect seasoning item — 2 sentences, specific, cinematic, tied to the object the reader is looking at.

**Rough Guide seasoning is the sidebar format.** "School for Scandal" on Abélard & Héloïse is a 120-word self-contained box dropped next to Notre-Dame (lines 2496–2506). Works on the page because the reader chooses whether to read it. **Would not work in audio** — it's disjoint from the main flow.

---

## Question 5: How much world grounding

**Pariswalks teaches Paris.** By the end of Walk 4 the reader has absorbed:

- **French language** — pronunciations, translations (*marais*, *hôtel*, *pavillon*, *oeil-de-boeuf*, *mansard*, *pailleux*, *trompe-l'oeil*, *ravalement*, *bleu-blanc-rouge*)
- **French social history** — précieuses, salons, duels, ruelles, marriage-at-12
- **French architectural vocabulary** — the trompe-l'oeil brick, the arcade structure, the four-arcades-per-lot plan
- **French political history** — Revolution renaming of place Royale → place de l'Indivisibilité → place des Vosges (1800); Louis Philippe's gate removal; Richelieu's dueling ban and subsequent six-man duel in front of the Pavillon du Roi
- **French literary references** — Hugo, Molière's *Précieuses Ridicules*, *Three Musketeers*, Alfred de Vigny's *Cinq-Mars*
- **Parisian urban sociology** — the Marais's post-aristocratic industrial decline, the 1962 *ravalement* law, tenants vs. developers in the 1970s

The reader finishes the walk **knowing more Paris than when they started**, not just more facts. This is a different kind of value than guided-tour information delivery. It treats the walk as an education.

**Frommer's** grounds each walk in its opening essay, then delivers efficient context at each stop. Less pedagogy, more pointing.

**Rough Guide** per-entry grounding only. Assumes the reader supplies their own larger context or consults an index.

---

## Voice observations that'll matter when we write

These are observations about *prose craft*. They'll need to hold up in our own written drafts before they become rules.

- **Inline foreign-word + definition** — consistent across all three. Never assume the reader knows the French word. Repeat the native word (for flavor) then gloss it.
- **Specific numbers always.** Never "several," "a few," "many," "hundreds of." Pick a number.
- **A named person in every entry.** If a fact is about a building with no people attached, find the architect, builder, resident, or visitor.
- **Sensory anchor per stop, minimum.** The weirdest verifiable visual detail works best.
- **Compress long history into one sentence with a sly ending.** The Napoleon/drapes and Viollet-le-Duc/heavenward-statue lines are the template.
- **Fragment sentences are normal.** "Nice fellow." "Comes back later." (latter is mine, from failed design doc, included here because it matches the observed pattern.)
- **Use "we" and "you" with purpose.** Pariswalks uses both. Frommer's reserves "you" for directions. Rough Guide uses neither. Our audio register probably resembles Pariswalks.
- **One-word editorial asides aimed at dead people are allowed.** "Nice fellow." They are *never* aimed at the city itself.
- **Bawdy is allowed if it's specific and historical.** The quarter-écu line lands because it has money math attached.
- **Author anecdotes (rare) are allowed in Pariswalks register.** The cold-water-on-the-ledge story wouldn't work in Rough Guide but fits Pariswalks. Whether it fits us is an open question — we don't have authors.

---

## Data diagnostic (as of 2026-04-22)

### What we have

- **555 beats across 188 POIs**, one book ingested (*Around and About Paris*, Thirza Vallois)
- Field population: entities 95%, sensory_anchor 100%, narrative_function 100%, beat_type 100%, emotional_register 100%, physical_cues 61%, key_claims 67%
- Median beat = 75 words (~30 seconds of audio). Range 17–256 words.
- Top-beaten POIs: Notre-Dame Cathedral (24), Place des Vosges (17), Hôtel de Ville (16), Île Saint-Louis (12), Val-de-Grâce (12), Arsenal Library (11), Louvre (10), Les Halles (10), Sorbonne (9), Eiffel Tower (9).
- 5 Conciergerie beats totaling 673 words. Quality is good (the Sanson executioner-dynasty beat is superior to Rough Guide's equivalent coverage).

### What's missing

Seven structural gaps. Numbered because they'll be referenced when extraction changes are proposed.

1. **Architectural/sensory interior detail thin.** Rough Guide Conciergerie covers what we don't: Salle des Gens d'Armes (1301–15), the iron grille separating the pailleux section, "salle de toilette" hair-cropping prep, fleur-de-lys wallpaper in Marie-Antoinette's cell mock-up, Tour de l'Horloge (~1350) with Paris's first public clock, its bell melted during the Commune. Our 5 beats cover *what happened here*, not *what you're looking at*. 4 of 5 Conciergerie beats have zero physical cues.

2. **Breadth shallow outside top 20 POIs.** 123 of 188 POIs (65%) have ≤2 beats. Only 19 POIs have ≥8 beats. A tour routing through a tier-3 corridor mostly encounters thin-beat POIs.

3. **Zero seasoning material at address granularity.** Our 17 Place des Vosges beats attach to the square as a whole. No per-address (no. 6, no. 8, no. 14) beats exist. Pariswalks-style circumnavigation is structurally unavailable.

4. **Wrong beat granularity.** Median 75 words is wrong for both roles: anchor stops need 200–400 words (90–180s audio); seasoning needs 20–40-word one-liners. We have only ~30 beats over 150 words across the whole corpus.

5. **Inconsistent linguistic texture.** Our Conciergerie Beat 2 does preserve "concierge" etymology and "bon-bec" translation inline. But "tricoteuses" appears elsewhere without definition. Inline French-word-with-gloss is hit-or-miss because the extractor paraphrases rather than preserves.

6. **No sub-location structure within a POI.** Notre-Dame has 24 beats but they're a flat list indexed by lens. The Rough Guide's Façade → Towers → Interior sequencing is unavailable to us — we have no field saying "this beat is about the façade."

7. **Lens ceiling at 16 beats per POI.** The North Star "1 beat per taggable lens per POI" rule caps even the richest tier-5 POI at 16 beats. Pariswalks Walk 4 uses ~25–30 vignettes for Place des Vosges. Our ceiling would clip this.

### Implication for the planned batch ingest

Running all 6 remaining books through the current `/unified-beat-extract` will fix **gap #2 (breadth)** but will **not** fix gaps #1, #3, #4, #5, #6, or #7 — those are structural. A second re-extraction would be required.

**Before committing to the full 6-book batch, consider:** tuning the extraction prompt to produce mixed-length beats (anchor + seasoning), sub-location tags, and preserved inline French texture. A few hours spent here saves a re-extraction later.

---

## What to do next

Not a plan. A priority list to discuss.

1. **Ingest the remaining 6 books** — necessary baseline for any tour-building attempt.
2. **Before running the full batch**, decide whether to tune `/unified-beat-extract` for gaps #3–#7. Otherwise we re-extract later.
3. **After ingest**, hand-build one Pariswalks-quality tour stop at Place des Vosges using the enriched beat corpus + any targeted fills. That's the empirical test of whether the content primitive works.
4. **Read Rick Steves next**, separately — he's explicitly an audio-tour author, so his patterns might differ from these three print-genre books.
5. **Read Around and About Paris (Vallois)** — this is our one ingested book's source. Reading the original helps us see what was preserved and what got lost in extraction.

---

## What is *not* in this doc (deliberately)

- **Rules.** The predecessor `design.md` became a rulebook before any example existed. This doc stays descriptive.
- **A scoring formula.** No POI selection algorithm. No narrative-fit multiplier. None of it has been tested against a written tour.
- **A generator architecture.** No "expensive at ingest, cheap at runtime" plumbing. That survives in the parked design doc if we need it later.
- **Feedback memories.** No new `feedback_tour_*` memories have been created from this session's observations. Observations become feedback only after they survive contact with our own writing.

When observations here have been validated against one real hand-built tour stop, they can graduate — into a proper design doc, into feedback memories, into extraction-prompt changes. Not before.
