# Tour B — "Builders of Paris"

> **DEPRECATED — 2026-04-22.** Parked along with the tour-builder design doc. Preserved for reference; restart is learn-by-example from real guidebooks.

**Status:** DEPRECATED. Original status was "First draft. Full script with sentence-level source attribution."
**Last updated:** 2026-04-15 (content); deprecated 2026-04-22.

Hand-built example tour for Scenario 2. Derives and tests rules for the tour-builder skill, focusing on: one-way routing, free endpoint selection, thin-lens interest handling (faith), haversine correction, and routing-aware stop selection.

---

## The brief

Generated from Scenario 2:

- **Starting point:** Eiffel Tower (48.858, 2.295)
- **Duration ask:** 4 hours
- **Interests:** Art, Faith
- **One-way:** Yes (endpoint is an algorithm output, not an input)
- **City:** Paris

---

## How the route was selected (algorithm walkthrough)

1. **Time-budget geometry first.** 4 hr → plan 200 min (err-short rule: ~83% of stated). At 3 km/h tourist pace with ×1.35 haversine correction, the walking budget constrains which POIs are reachable.

2. **Scored all tier 3+ POIs** using `score = importance_tier × beat_richness × interest_alignment × distance_decay`. Top 9 natural anchors (score > 10): Notre-Dame, Hôtel de Ville, Place des Vosges, Eiffel Tower, Louvre, Musée d'Orsay, Sorbonne, Saint-Germain-des-Prés, Saint-Sulpice.

3. **Routing-aware selection.** The 9 anchors don't fit in 4 hours (5+ hours at corrected distances). Selection must account for routing cost, not just score. The natural corridor follows the Left Bank east → crosses to Île de la Cité → ends on the Right Bank. Stops that require detours off-corridor (Sorbonne: southward swing, Place des Vosges: 2+ km further east) were cut despite high scores. The Louvre, as the endpoint, incurs zero onward walking cost — making it efficient despite being a detour from the Left Bank.

4. **Final route (8 stops, 204 min planned → 235 min actual ≈ 3.9 hr):**
   Eiffel Tower → Les Invalides → Musée d'Orsay → Saint-Germain-des-Prés → Saint-Sulpice → Notre-Dame → Sainte-Chapelle → Louvre Museum

5. **`narrative_fit` was computed but had near-zero effect.** Entity overlap between stops spanning different neighborhoods is effectively zero. This term matters within geographic clusters, not across a 4-hour city tour.

---

## How the theme was discovered (bottom-up)

1. Selected 19 beats across 8 stops (establishing openers, interest-matching art/faith beats, sensory-anchored hooks).
2. Read the selected beat texts and spotted a recurring subject: **who built each place and why.**
   - Eiffel Tower: engineers Koechlin & Nouguier, for the Republic's 1889 Exhibition
   - Les Invalides: Louis XIV, for his wounded veterans
   - Musée d'Orsay: the Republic, converting a railway station into a museum
   - Saint-Germain-des-Prés: anonymous builders, 990 AD — before the kings
   - Saint-Sulpice: 17th-century Catholic expansion, parish swollen with population
   - Notre-Dame: anonymous artisans, 1163–1330
   - Sainte-Chapelle: Saint Louis IX, to house relics
   - Louvre: Philippe-Auguste → François I → Henri IV → Louis XIV (four rulers, one building)
3. **Theme: "Builders of Paris."** Every stop on this walk was shaped by someone who thought they were building forever — anonymous artisans, kings, emperors, republics. The Louvre is the payoff: four rulers in one building, each overwriting the last, until Louis XIV abandoned it entirely.

This theme was found, not chosen. The algorithm currently can't surface it automatically because entity extraction produces unnormalized strings ("When Louis XIV" vs "Louis XIV") — the same person at two stops doesn't string-match. This is the strongest argument for future entity resolution (deferred in NORTHSTAR; proven necessary here).

---

## Clarification: what "runtime" means in design.md

Throughout this design doc, "runtime" means **the moment the tour-builder skill executes to generate a specific tour for a specific user request.** It does NOT mean a running server or production deployment. It means:

- **Ingest time** = when the pipeline extracts beats from books. One-time per beat. Opus/Sonnet. ~$0.01/beat.
- **Runtime** = when a user says "give me a 4-hour tour from the Eiffel Tower." The skill queries the graph, selects POIs and beats, stitches the script. Per-tour. Haiku. ~$0.01–0.05/tour.

The 19 beats selected below were identified at *runtime* (selection from pre-extracted data). The beat texts themselves were extracted at *ingest time*. The connective narration (`[GLUE_NAV]`, `[STRUCTURAL]`) would be generated at *runtime* by a tightly-prompted cheap model with zero factual freedom.

---

## Stop list

| # | Stop | Tier | Type | Beats used | Function |
|---|------|------|------|------------|----------|
| 1 | Eiffel Tower | 5 | Anchor (cold open) | establishing (Koechlin) + SA hook ("Look up") + deepen (petition) | Who built it + sensory hook + why people hated it |
| — | (walking) | — | Walk-by | Pavillon de Flore "Henri IV's Grande Galerie" | Foreshadows Louvre ending |
| 2 | Les Invalides | 4 | Anchor | establishing (Dome) + deepen (Napoleon burial) | A king's building for his soldiers |
| — | (walking) | — | Walk-by | Musée de la Légion d'Honneur "Hôtel de Salm" | Aristocratic corridor texture |
| 3 | Musée d'Orsay | 5 | Anchor | establishing (station → museum) + callback (Impressionist collection) | The Republic repurposes stone |
| — | (walking) | — | Walk-by | Ecole des Beaux-Arts + Les Deux Magots | Art school + literary café |
| 4 | Saint-Germain-des-Prés | 4 | Anchor | SA establishing (oldest church) + SA faith (enamelled portico) | Before the kings |
| 5 | Saint-Sulpice | 4 | Anchor | art climax (Delacroix murals) + faith establishing (Catholic stronghold) | Faith as urban expansion |
| — | (walking) | — | Silent + navigation | — | Cross to Île de la Cité |
| 6 | Notre-Dame Cathedral | 5 | Anchor (climax) | establishing (1163–1330) + hook (Jupiter pillar) + climax (centuries of vandalism) | What anonymous artisans built, what power tried to destroy |
| 7 | Sainte-Chapelle | 4 | Anchor | establishing (reliquary) + SA callback (overshadowed earlier chapel) | A king's reliquary |
| — | (walking) | — | Walk-by | Pont Neuf or Pavillon de Flore view | Cross to Right Bank |
| 8 | Louvre Museum | 5 | Anchor (closing) | art climax (François I, Mona Lisa) + deepen (Henri IV, Grande Galerie) + hook (Louis XIV abandons for Versailles) | Four rulers, one building — the theme named |

**Time math:** ~7.5 km corrected walking / 150 min + 50 min dwell + connective audio during walking = ~204 min planned. With 15% buffer = ~235 min actual ≈ 3.9 hr. Under the 4-hour ask.

**Audio fraction:** 19 selected beats = 10.9 min. Plus connective narration and walk-by beats ≈ 6–8 min. Total ≈ 17–19 min audio in ~204 min planned = **~9%**. Massively under the 60% cap. The tour breathes — long walking segments between stops are silent by design, with occasional walk-by mentions.

---

## Format note for the script

Same as Tour A. `[B:short_id]` = beat-sourced. `[STRUCTURAL]` = verifiable structural fact. `[GLUE_NAV]` = navigation from whitelist. `[GLUE_PAUSE]` = silence cue. `[ARITH]` = arithmetic on beat dates.

Beat IDs reference the `beat_id` field in `data/paris/beats.json`. Where a beat doesn't have a clean beat_id, a descriptive slug is used with the POI name prefix.

---

## Full script

### Stop 1 — Cold open at the Eiffel Tower

**[NARRATOR — user is at the Eiffel Tower base, stationary]**

> Look up. Every rivet you see was placed by hand — 2.5 million of them. `[B:eiffel_tower_hidden_history_rivet_around_and_about_paris]`
>
> Gustave Eiffel didn't design this. Two engineers in his company did — Maurice Koechlin and Émile Nouguier — for the 1889 Universal Exhibition, the centenary of the French Revolution. `[B:eiffel_tower_historic_arch_koechlin_around_and_about_paris]`
>
> *[2-second pause]* `[GLUE_PAUSE]`
>
> Not everyone was grateful. Fifty leading figures from arts and letters — Alexandre Dumas, Charles Garnier, Guy de Maupassant — signed a petition calling it a disgrace to the city. `[B:eiffel_tower_social_change_petition_around_and_about_paris]`
>
> The engineers built it anyway. And here it is. `[STRUCTURAL]`
>
> *[3-second pause]* `[GLUE_PAUSE]`
>
> We're going to walk east from here. Every stop between here and where this tour ends was built by someone who thought they were building forever. Kings, emperors, republics — each one carved their mark into stone. You'll see whose stone is still standing. `[STRUCTURAL — no factual claims, pure structural framing]`
>
> Head east along the Champ de Mars, toward the river. We're making for the golden dome you can see in the distance — that's Les Invalides. It's about a twenty-minute walk. `[GLUE_NAV]`

**[SILENCE — user walks east across Champ de Mars. ~15 min of ambient.]** `[GLUE_PAUSE]`

---

#### Walk-by — Pavillon de Flore (tier 1, on route)

**[NARRATOR — as user passes near the Pavillon de Flore, approaching the river]**

> The building on your right with the heavy sculpted facade is the Pavillon de Flore — the southern anchor of Henri IV's Grande Galerie, the corridor he built to connect the Louvre to the Tuileries palace. `[B:pavillon_de_flore_historic_arch_grande_galerie_around_and_about_paris]`
>
> You'll see the other end of that corridor at the last stop today. `[STRUCTURAL — forward reference, no new claims]`

**[SILENCE — continues walking]** `[GLUE_PAUSE]`

---

### Stop 2 — Les Invalides

**[NARRATOR — user is approaching the Dôme des Invalides, audio resumes]**

> The gold dome ahead of you is the church of the Dôme — also known as the Royal Chapel. Jules-Hardouin Mansart designed it, and it is one of the most outstanding monuments in the history of French architecture. `[B:les_invalides_historic_arch_dome_around_and_about_paris]`
>
> Louis XIV built this entire complex — the hospital, the church, the courtyards — for his wounded soldiers. A king building a home for the men his wars had broken. `[B:les_invalides_historic_arch_dome_around_and_about_paris]`
>
> *[2-second pause]* `[GLUE_PAUSE]`
>
> Napoleon wished to be buried "on the banks of the Seine, by the French people whom I have loved so much." He died on Saint Helena. Nineteen years later, they brought him home. His coffin was carried up the Seine on a barge, landed at the Pont de Neuilly, and now rests beneath this dome. `[B:les_invalides_famous_residents_napoleon_around_and_about_paris]`
>
> *[4-second pause — let the user look up at the dome]* `[GLUE_PAUSE]`
>
> Continue east. The river is on your right. In about twelve minutes you'll reach the Musée d'Orsay — you'll see it across the Esplanade. `[GLUE_NAV]`

**[SILENCE — walking along the quai toward Orsay. ~12 min.]** `[GLUE_PAUSE]`

---

#### Walk-by — Musée de la Légion d'Honneur (tier 2, on route)

**[NARRATOR — as user passes the Hôtel de Salm, across from Orsay]**

> Across the street, the elegant Hôtel de Salm has a tragic founding story — its builder, a German prince, was executed in the Revolution before he could enjoy it. `[B:musee_legion_honneur_hidden_history_salm_around_and_about_paris]`

**[SILENCE]** `[GLUE_PAUSE]`

---

### Stop 3 — Musée d'Orsay

**[NARRATOR — user is at the Musée d'Orsay entrance, stationary]**

> Paris loves novelty — and converting a railway station into a museum was bound to create a sensation. `[B:musee_dorsay_historic_arch_station_around_and_about_paris]`
>
> This was the Gare d'Orsay, opened in 1900 for the Universal Exhibition. By 1939 the platforms were too short for modern trains. The station died. The Republic gave it a second life. `[B:musee_dorsay_historic_arch_station_around_and_about_paris]`
>
> *[2-second pause]* `[GLUE_PAUSE]`
>
> The collection here — Impressionist, Post-Impressionist, everything between 1848 and 1914 — arrived from the Louvre, which had outgrown its walls. Zola called that kind of painting "la Bête humaine." The Orsay made it respectable. `[B:musee_dorsay_visual_art_impressionist_around_and_about_paris]`
>
> Head south from the museum. Cross the boulevard and walk into the narrow streets of the 6th arrondissement. You're making for a church — the oldest in Paris. About ten minutes. `[GLUE_NAV]`

**[SILENCE — walking through Left Bank streets. ~10 min.]** `[GLUE_PAUSE]`

---

#### Walk-by — Ecole des Beaux-Arts (tier 2, near route)

**[NARRATOR — as user passes rue Bonaparte]**

> On your left, the Beaux-Arts school occupies part of a convent built by Marguerite de Valois. The architects who shaped half of Paris studied behind that gate. `[B:ecole_beaux_arts_historic_arch_convent_around_and_about_paris]`

**[SILENCE]** `[GLUE_PAUSE]`

---

### Stop 4 — Saint-Germain-des-Prés

**[NARRATOR — user is at the church entrance, stationary]**

> You are standing before the oldest church in Paris, built between 990 and 1014 AD in the Romanesque tradition. `[B:saint_germain_des_pres_historic_arch_oldest_around_and_about_paris]`
>
> Look at the bell tower above you — it predates the kings who built everything else on this tour. No royal patron. No architect we can name. Just stone and faith. `[B:saint_germain_des_pres_historic_arch_oldest_around_and_about_paris]` `[STRUCTURAL — visible feature]`
>
> *[3-second pause]* `[GLUE_PAUSE]`
>
> On the eastern wall of the church, look for the spectacular enamelled sandstone portico — it was affixed for the 1900 Universal Exposition by Victor Baltard, the architect who built the old Les Halles markets. `[B:saint_germain_des_pres_historic_worship_portico_around_and_about_paris]`
>
> Walk south from here. Saint-Sulpice is five minutes away — a very different kind of church. `[GLUE_NAV]`

**[SILENCE — short walk to Saint-Sulpice. ~5 min.]** `[GLUE_PAUSE]`

---

### Stop 5 — Saint-Sulpice

**[NARRATOR — user is at Saint-Sulpice, stationary]**

> The neighbourhood around Saint-Sulpice remains the stronghold of Catholicism in Paris. Walk down the Allée du Séminaire and you'll pass the seminary, the religious bookshops, the vestment makers — a parallel economy that has operated here for centuries. `[B:saint_sulpice_historic_worship_catholicism_around_and_about_paris]`
>
> But the church itself was built for a more practical reason. In the 17th century, the parish was swollen with population, and the old church was too small. So they built big. `[B:saint_sulpice_historic_arch_parish_around_and_about_paris]`
>
> *[2-second pause]* `[GLUE_PAUSE]`
>
> Inside, in the Chapelle des Saints-Anges — the first chapel on the right — are Eugène Delacroix's mural paintings. Jacob Wrestling with the Angel on one wall, Heliodorus Driven from the Temple on the other, and Saint Michael Slaying the Dragon on the ceiling. Delacroix worked on them for years, sometimes in despair. They are among the greatest works of art in any Paris church. `[B:saint_sulpice_visual_art_delacroix_around_and_about_paris]`
>
> *[4-second pause]* `[GLUE_PAUSE]`
>
> From here, we cross the river. Head north to the Seine, then cross to the Île de la Cité. It's about fifteen minutes. The walk is mostly quiet — enjoy the streets. `[GLUE_NAV]`

**[SILENCE — walking north to river crossing, then across to Île de la Cité. ~15 min. This is the longest silent stretch.]** `[GLUE_PAUSE]`

---

### Stop 6 — Notre-Dame Cathedral

**[NARRATOR — user is at the Notre-Dame parvis, stationary]**

> Between 1163 and 1330, anonymous artisans carved Notre-Dame from stone. `[B:notre_dame_cathedral_historic_arch_artisans_around_and_about_paris]`
>
> Not a king. Not a named architect. Bishop Maurice de Sully launched the project, but the hands that cut every block, that slipped the building imperceptibly from Romanesque into Gothic over a hundred and sixty-seven years — we don't know their names. `[B:notre_dame_cathedral_historic_arch_artisans_around_and_about_paris]` `[ARITH: 1330 - 1163 = 167 years]`
>
> *[3-second pause]* `[GLUE_PAUSE]`
>
> Beneath the chancel, vestiges of something much older were found in 1711 — a monument to Jupiter from the reign of Emperor Tiberius, the Pilier des Nautes. People were building on this spot two thousand years ago. `[B:notre_dame_cathedral_hidden_history_jupiter_around_and_about_paris]`
>
> *[2-second pause]* `[GLUE_PAUSE]`
>
> Notre-Dame endured centuries of vandalism. The chancel screen was destroyed in 1699. The original stained glass was removed. The Kings of Judah statues were torn down by Revolutionaries who mistook them for Kings of France. `[B:notre_dame_cathedral_dark_history_vandalism_around_and_about_paris]`
>
> What the named builders put up, others tore down. What the anonymous artisans built lasted. `[STRUCTURAL — interpretive, no new claims]`
>
> Sainte-Chapelle is a short walk from here — through the construction barriers, past the Palais de Justice. Five minutes. `[GLUE_NAV]`

**[SILENCE — short walk. ~5 min.]** `[GLUE_PAUSE]`

---

### Stop 7 — Sainte-Chapelle

**[NARRATOR — user is at Sainte-Chapelle, stationary]**

> The Sainte-Chapelle was designed to have the light, lacy aspect of a reliquary — for that is precisely what it was. Saint Louis built it to house a piece of the True Cross and the Crown of Thorns, which he had bought from Baudouin the Second, the last Emperor of Constantinople. `[B:sainte_chapelle_historic_arch_reliquary_around_and_about_paris]`
>
> A king who thought he could build a container for God. `[STRUCTURAL — interpretive framing, no new claim]`
>
> *[3-second pause]* `[GLUE_PAUSE]`
>
> So great is this chapel's aura that it has completely overshadowed an earlier royal chapel on the Left Bank — the one Louis VII built, dedicated to Saint Michel. That's the chapel that gave its name to the place, the boulevard, the bridge, and the fountain across the river. `[B:sainte_chapelle_hidden_history_earlier_chapel_around_and_about_paris]`
>
> *[2-second pause]* `[GLUE_PAUSE]`
>
> Cross the river now. Head north over the Pont au Change to the Right Bank. You're making for the Louvre — the last stop. It's about fifteen minutes. `[GLUE_NAV]`

**[SILENCE — cross to Right Bank, walk along quai toward Louvre. ~15 min.]** `[GLUE_PAUSE]`

---

### Stop 8 — Louvre Museum (closing)

**[NARRATOR — user is at the Louvre courtyard, stationary]**

> François the First didn't just rebuild the Louvre — he gave it its artistic soul. He brought Leonardo da Vinci to France, along with the Mona Lisa, which Leonardo carried with him. After Leonardo's death at Amboise, François acquired the painting. It has never left France. `[B:louvre_museum_visual_art_francois_around_and_about_paris]`
>
> *[2-second pause]* `[GLUE_PAUSE]`
>
> Henri IV entered Paris on the 22nd of March, 1594, four years after his accession, having converted to Catholicism to claim his capital. He immediately began building the Grande Galerie — the immense corridor connecting the Louvre to the Tuileries palace, the one whose southern end you passed near the Eiffel Tower this morning. `[B:louvre_museum_historic_arch_henri_iv_around_and_about_paris]` `[STRUCTURAL — back-reference to Pavillon de Flore walk-by]`
>
> *[2-second pause]* `[GLUE_PAUSE]`
>
> When Louis XIV moved his court to Versailles in 1682, the Louvre descended into a bizarre state of decay. The Académie des Sciences, the Académie de Peinture, and dozens of squatters and artisans moved in. Booths and shacks filled the Grande Galerie. The greatest palace in Paris became a bazaar. `[B:louvre_museum_hidden_history_versailles_around_and_about_paris]`

**[4-second pause — the closing callback begins]** `[GLUE_PAUSE]`

> You've walked past two thousand years of building today. `[ARITH — Tiberius-era Pilier des Nautes (~1st century) to present]`
>
> The anonymous artisans at Saint-Germain, nine hundred years ago. The anonymous artisans at Notre-Dame, eight hundred years ago. `[STRUCTURAL — back-references to stops 4 and 6]`
>
> A king who built a golden chapel to house God. A king who built a corridor to connect his palaces. A king who abandoned all of it for Versailles. `[STRUCTURAL — back-references to stops 7 and 8, no new claims]`
>
> Engineers who built a tower the whole country hated, for a Republic that was barely a century old. `[STRUCTURAL — back-reference to stop 1]`
>
> Every one of them thought they were building forever. None of them were right. But the stone they cut is still here. `[STRUCTURAL — interpretive, no new claims]`

---

## Post-script analysis

### Silence budget
- Total selected beat audio: ~10.9 min (19 beats)
- Connective narration + walk-by beats: ~6 min estimated
- Total audio: ~17 min in a ~204 min planned tour = **8% audio / 92% silence**
- Well under the 60% cap. The long walking segments (15 min Eiffel→Invalides, 12 min Invalides→Orsay, 15 min Saint-Sulpice→Notre-Dame, 15 min Sainte-Chapelle→Louvre) are almost entirely silent.

### Source traceability
- Every script sentence carries a `[B:...]`, `[STRUCTURAL]`, `[GLUE_NAV]`, `[GLUE_PAUSE]`, or `[ARITH]` tag
- Zero sentences without attribution
- Interpretive framing sentences (e.g., "A king who thought he could build a container for God") are marked `[STRUCTURAL]` and make no factual claims beyond what the cited beats contain

### Theme validation
- Theme ("Builders of Paris") emerges from the beats, not imposed
- Every stop contributes: who built it, when, why
- Closing callback references specific stops by content, not by abstract label
- Theme is named only at the close — never forecast at the open (per design rule)

### Walk-by seasoning
- 3 walk-by beats used (Pavillon de Flore, Légion d'Honneur, Ecole des Beaux-Arts)
- All share entity/theme with adjacent anchors:
  - Pavillon de Flore → shares Henri IV's Grande Galerie with Louvre closing
  - Légion d'Honneur → aristocratic building adjacent to Invalides (royal building theme)
  - Beaux-Arts → architects trained here shaped the buildings on this tour
- Per design rule: seasoning serves the spine

### Interest coverage (Q4 partial answer)
- Art interest: well-served. 15 of 19 selected beats are `historic_arch` or `visual_art`.
- Faith interest: 2 of 19 selected beats are `historic_worship` (Saint-Germain portico, Saint-Sulpice Catholic stronghold). But the tour visits 4 churches (Saint-Germain, Saint-Sulpice, Notre-Dame, Sainte-Chapelle) — the faith experience is delivered through architecture at religious sites, not through dedicated worship beats.
- **Q4 finding:** The algorithm handles thin lens coverage through architectural adjacency — churches score high on architecture, which is what faith-interested users want to visit. This works for faith + architecture overlap. Untested: an interest lens with no proxy (e.g., `music_heritage` at non-architectural venues). That remains open.

---

## Lessons captured (new from Tour B)

### Algorithm design
1. **Time-budget geometry must precede selection.** Compute stop budget before scoring.
2. **Endpoint is an output for one-way tours.** The Louvre emerged as the endpoint because it's a high-scoring stop at the corridor's natural end — not because anyone specified it.
3. **Selection and routing are inseparable.** Greedy score-then-route produces infeasible tours or wrong tours. The algorithm must score candidates including their marginal routing cost.
4. **`narrative_fit` has near-zero effect at city scale.** Entity overlap between stops in different neighborhoods is negligible. Keep the term for within-cluster differentiation; don't rely on it for the tour spine.
5. **Stop quality floor needed.** Pure value-per-minute greedy overstuffs with cheap tier-3 stops. Need minimum beat count per stop, max stop count, or diminishing-returns penalty.

### Data and measurement
6. **Haversine correction factor: ×1.35 for Paris.** Real walking distance >> straight-line. Varies by neighborhood (boulevards ×1.2, medieval streets ×1.4, construction zones ×1.5). Must be validated per city.
7. **Entity extraction needs normalization for theme discovery.** "When Louis XIV" and "Louis XIV" at different stops are the same person but don't string-match. Runtime theme discovery needs normalized entity IDs — the entity resolution improvement noted in NORTHSTAR.
8. **Geographic barriers (rivers, major roads) create routing corridors.** The Seine forces the tour into Left Bank → Island → Right Bank. A city-agnostic algorithm needs barrier awareness. Likely generalizes to other European cities with rivers or medieval centers.

### Tour quality
9. **Thin-lens interests are served through architectural adjacency.** Faith interest → churches → architecture beats at churches. This is smart, not a bug. But needs validation with a lens that has no proxy.
10. **The cold open must be sensory, not thematic.** "Look up" works. "This tour is about builders of Paris" would not. Theme at the close only.
11. **Walk-by foreshadowing works.** The Pavillon de Flore walk-by near the start connects to the Louvre closing via Henri IV's Grande Galerie. Cross-stop callbacks create narrative continuity without new facts.
