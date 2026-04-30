# Tour A — "Survival on the Island"

> **DEPRECATED — 2026-04-22.** Parked along with the tour-builder design doc. Preserved for reference; restart is learn-by-example from real guidebooks.

**Status:** DEPRECATED. Original status was "Complete first draft. Full script with sentence-level source attribution."
**Last updated:** 2026-04-08 (content); deprecated 2026-04-22.

This is the first hand-built example tour. It exists to derive the rules for the eventual tour-builder skill, not to be a shippable tour. Treat it as a reference for what good output should look like.

---

## The brief

Generated from Scenario 1:

- **Starting point:** Place Saint-Michel area (5th arr.). Plausible Latin Quarter hotel near 48.851, 2.347.
- **Duration ask:** 2 hours
- **Interests:** History (multiple lenses), Architecture
- **Round trip:** Yes
- **City:** Paris

---

## How the theme was discovered (bottom-up)

1. Pulled all POIs within 1.2 km of starting point (the round-trip walking radius).
2. Ranked candidates by tier × beat richness.
3. Top tier-5 anchors in range: Notre-Dame Cathedral (12 beats), Conciergerie (5), Sorbonne (9), Île de la Cité (4), Pont Neuf (3), Cafe de Flore (4), Luxembourg Gardens (4). Plus tier-4: Sainte-Chapelle (3), Saint-Germain-des-Prés (8), Saint-Sulpice (8), Pantheon (5).
4. Read the actual beat texts from the strongest island candidates (Sainte-Chapelle, Conciergerie, Pont Neuf, Notre-Dame, Île de la Cité, Rue Chanoinesse).
5. **Spotted a recurring subject across multiple beats:** these buildings nearly didn't exist. Sainte-Chapelle was "put on the market for sale and demolition." Notre-Dame was "put up for sale as building material… a certain Citoyen Simon nearly purchased the cathedral." Both Sainte-Chapelle and Notre-Dame survived Communard arson attempts in May 1871. The Crown of Thorns "miraculously survived" the Mint. The Kings of Judah statues were torn down and rediscovered in 1977.
6. **Theme:** *Survival on the Island.* What almost wasn't here.

This theme was not chosen — it was found. Every supporting beat above is a direct quote from the database.

**Killer cold-open hook (also from data):** Buried in a Sainte-Chapelle beat is the fact that Place Saint-Michel — where the user is literally standing — is named after a 12th-century chapel that no longer exists, the Chapelle Saint-Michel built by Louis VII. Sainte-Chapelle is its successor across the river. The cold open writes itself from real beat content: the place you're standing in is named after a thing that's gone, and we're going to walk to its successor.

**Graph-adjacency moment:** the Île de la Cité POI has a beat about Étienne Marcel's 1358 uprising — the moment the kings of France permanently abandoned the palace on the island. The Conciergerie POI has a beat about that same palace becoming a prison in 1391. **Neither beat alone explains the full arc, but together they do.** The Marcel beat became the perfect walking transition from Sainte-Chapelle to the Conciergerie because it explains *why* the royal palace became a prison. This is exactly the cross-POI entity adjacency that richer beat metadata (`entities`, `time_period`) would surface automatically — discovered here by reading the texts manually.

---

## Stop list

| # | Stop | Tier | Type | Beats used | Function |
|---|---|---|---|---|---|
| 1 | Place Saint-Michel | — | Cold open | Sainte-Chapelle "Chapelle Saint-Michel" beat | Hook + scene set |
| 2 | Sainte-Chapelle façade | 4 | Anchor | "reliquary aspect" + "nearly did not survive" | Architecture + first survival story |
| — | (walking) | — | Walking transition | Île de la Cité "Marcel uprising" beat | Bridges S-C → Conciergerie via shared palace history |
| 3 | Conciergerie façade | 5 | Anchor | "originally seat of governor → 1391 prison" + "Revolution prisoners (Marie-Antoinette + 2780)" | The dark counterpoint |
| — | (walking) | — | Silent walk | — | Long pause for ambient |
| 4 | Pont Neuf / Square du Vert-Galant | 5 | Anchor (breath) | "bouquinistes are a remnant" | Quieter survival story; pace settles |
| — | (walking) | — | Walking transition | Île de la Cité "origins" beat | Roman → medieval setting for the climax |
| 5 | Notre-Dame parvis | 5 | Anchor (climax) | "construction 1163-1330" + "Revolution sale" + "Hugo's novel" + "Communards 1871" | Three near-deaths in one building |
| — | (walking) | — | Silent walk around cathedral | — | Quiet transition |
| 6 | Rue Chanoinesse | 3 | Walk-through | Abelard/Heloise affair + remains | Personal coda |
| — | (walking) | — | Silent walk | — | Returning to start |
| 7 | Pont Saint-Michel / Place Saint-Michel | — | Closing callback | Summary referencing all of the above | Theme named retroactively |

**Time math:** ~1.8 km walking, ~30 min walking + ~22 min stops + ~3 min closing + 15% buffer = **~70 min total**. Substantially under the 2-hour ask. Per the "honest length" rule, this is the right answer for today's data — we deliver a 70-min tour and tell the user upfront. With richer beat data, the same skeleton fills more time via seasoning walk-bys.

**Audio fraction:** ~18 min audio in ~70 min total ≈ **26%** — well under the 60% cap. The script breathes a lot. Some long walking segments are entirely silent, which is intentional.

---

## Format note for the script

Every sentence is annotated with its source. `[B:<short_id>]` = beat-sourced. `[STRUCTURAL]` = verifiable structural fact (POI name, what is currently visible, name etymology that can be confirmed). `[GLUE_NAV]` = pure navigation phrase from a whitelist. `[GLUE_PAUSE]` = silence cue. `[ARITH]` = arithmetic on dates that appear in cited beats (e.g., "forty years later").

---

## Full script

### Stop 1 — Cold open at Place Saint-Michel

**[NARRATOR — at Place Saint-Michel, user is stationary]**

> You're standing in Place Saint-Michel. `[STRUCTURAL]`
>
> The name of this place is much older than anything you can see here, and it doesn't come from anything you can see here. `[B:sainte-chapelle-chapelle-saint-michel]`
>
> In the 12th century, King Louis VII built a small chapel here called the Chapelle Saint-Michel. It was where Philippe-Auguste was baptised. A simple rectangular building with a flat roof — and it was still standing in 1781. `[B:sainte-chapelle-chapelle-saint-michel]`
>
> The boulevard, the bridge, the quai, the fountain, this whole square — they're all named after that chapel. Millions of people pass through here every year and don't know it. `[B:sainte-chapelle-chapelle-saint-michel]`
>
> *[3-second pause] [GLUE_PAUSE]*
>
> The chapel is gone. But it had a successor. In the 13th century, on the small island just across the river in front of you, King Louis the Ninth — Saint Louis — built a much grander chapel to take its place. `[B:sainte-chapelle-reliquary]`
>
> We're going to walk to it now. It's about five minutes from here. Cross the bridge in front of you and turn right when you reach the island. `[GLUE_NAV]`

**[SILENCE — user begins walking. ~3 minutes of ambient. [GLUE_PAUSE]]**

---

### Stop 2 — Sainte-Chapelle

**[NARRATOR — user is approaching Sainte-Chapelle, audio resumes]**

> The spire you can see ahead of you, rising above the surrounding rooftops — that's the Sainte-Chapelle. `[STRUCTURAL]`
>
> It was built in barely five years, by an architect we believe was Pierre de Montreuil — possibly Jean de Chelles. We're not sure which. `[B:sainte-chapelle-reliquary]`
>
> What we do know is that Saint Louis didn't build it as an ordinary church. He built it as a reliquary — a container for two objects. He had bought a piece of the True Cross and the Crown of Thorns from Baudouin the Second, the last Emperor of Constantinople, who was desperate for money to defend his city. The chapel that would house them was designed to have the light, lacy aspect of a reliquary — because that is precisely what it was. `[B:sainte-chapelle-reliquary]`

**[NARRATOR — user has arrived at the façade, stops walking]**

> Stop here for a moment and look up. `[GLUE_NAV]`
>
> *[10-second pause] [GLUE_PAUSE]*
>
> During the Revolution, the silver and gold reliquary that held the Crown of Thorns was sent to the Mint to be melted down. The Crown itself somehow survived — perhaps because even the standard-bearers of the Revolutionary ideal did not dare to tamper with the most holy of Christian symbols. It's now kept at Notre-Dame, where we'll go later. `[B:sainte-chapelle-nearly-not-survive]`
>
> The chapel itself was less lucky. After the Revolution, it was used first to store flour, then as a depot for court archives. By the 1840s it was so dilapidated that it was put on the market for sale and demolition. In 1847 it still bore an inscription reading "National property, for sale." `[B:sainte-chapelle-nearly-not-survive]`
>
> Then on 24 May 1871, during the Paris Commune, revolutionaries poured petrol over the Sainte-Chapelle and only failed to set it on fire for lack of time. `[B:sainte-chapelle-nearly-not-survive]`
>
> *[5-second pause] [GLUE_PAUSE]*

---

### Walking transition — to the Conciergerie

**[NARRATOR — transitioning to next stop]**

> When you're ready, walk back out the way you came in. Turn right along Boulevard du Palais, then right again onto the quai that runs along the river. We're going to the next building over. About three minutes. `[GLUE_NAV]`

**[NARRATOR — audio continues during the walk]**

> The chapel you just stood in front of and the building you're walking to now were two halves of the same complex. They were both part of the medieval royal palace on this island. `[B:ile-de-la-cite-marcel-uprising — paraphrased setup, supported by Sainte-Chapelle "adjoining the palace" beat]`
>
> The kings of France lived there for centuries. Then, on 22 February 1358, with King Jean the Second held captive in England, the provost of merchants Étienne Marcel believed he could overthrow the monarchy. The Dauphin — the future Charles V — was sitting with two of his counsellors in the palace when Marcel's men erupted in and slew the counsellors before his very eyes. The gushing blood stained the Dauphin's clothes, an experience he was never going to forget. `[B:ile-de-la-cite-marcel-uprising]`
>
> He left the palace one night by way of the river. He moved first to the Hôtel de Saint-Pol in the Marais, then arranged a residence within the safer walls of the Louvre. The kings of France never returned to the island. The premises were taken over by the parliament — the kingdom's court of justice. `[B:ile-de-la-cite-marcel-uprising]`

**[SILENCE — last ~30 seconds of walking. [GLUE_PAUSE]]**

---

### Stop 3 — Conciergerie

**[NARRATOR — user has arrived at the Conciergerie façade on quai de l'Horloge]**

> Stop here. The medieval towers in front of you are what's left of that royal palace. `[STRUCTURAL]`
>
> The building was originally the seat of the governor of the King's palace — that's where the name "Conciergerie" comes from. It became a prison in 1391, and remained one until 1914. `[B:conciergerie-origin]`
>
> In the 15th century, passers-by could still hear the screams of tortured prisoners in the Tour Bonbec — the most westerly tower, the one closest to the river. The name "bon-bec" meant "prate" in the Middle Ages, probably alluding to the interrogations on the ground floor. A varied spectrum of torture methods was devised to make victims confess and denounce their accomplices. During a restoration in 1828, two oubliettes were found in the basement of the tower, communicating with the river and spiked with iron points. `[B:conciergerie-origin]`
>
> *[5-second pause] [GLUE_PAUSE]*
>
> Four hundred years later, during the Revolution, the Conciergerie filled with a different kind of prisoner. `[ARITH — 1391 prison opening + Revolution = ~400 years]` `[B:conciergerie-revolution-prisoners]`
>
> Madame Roland, who had supported the Revolution but sided with the Girondins at the wrong time. Marie-Antoinette, who occupied a dreary cell from 2 August to 16 October 1793, when she was taken to the guillotine. Then Danton, Robespierre and Saint-Just were detained here in their turn — Danton and Robespierre in the cells adjacent to the Queen's. `[B:conciergerie-revolution-prisoners]`
>
> In all, some two thousand seven hundred and eighty victims of the Revolutionary Tribunal passed through that arcade entrance to the jeers of delighted tricoteuses huddled on the perron. `[B:conciergerie-revolution-prisoners]`
>
> *[8-second pause] [GLUE_PAUSE]*

---

### Walking transition — to Pont Neuf

**[NARRATOR]**

> The next stop is quieter. Walk west along the quai, past the front of the building you're standing in front of, and keep going toward the tip of the island. About eight minutes. The first bridge you'll cross is the Pont au Change; keep going past it. The bridge after that is the Pont Neuf. When you reach it, walk halfway across, then take the staircase down to the small park at the tip of the island just below the bridge. `[GLUE_NAV]`

**[SILENCE — ~8 minutes of ambient walking. [GLUE_PAUSE]]**

---

### Stop 4 — Pont Neuf / Square du Vert-Galant

**[NARRATOR — user is at Square du Vert-Galant, looking up at the Pont Neuf and the bouquinistes along the quais]**

> Stop here for a moment. `[GLUE_NAV]`
>
> Look at the green wooden boxes along the quais on either side of the river — those are the bouquinistes, the booksellers. `[STRUCTURAL]`
>
> They're a remnant. They come from a time when this bridge itself was a world of its own — crowded with strollers, pedlars, acrobats, prostitutes and riff-raff. When the bridge was cleaned up in the late 18th century, its hucksters spilled over to the quais on either side, and eventually settled into the book trade that survives today. `[B:pont-neuf-bouquinistes]`
>
> *[15-second pause — the longest deliberate pause in the tour, lets the user actually look at the river. [GLUE_PAUSE]]*

---

### Walking transition — to Notre-Dame

**[NARRATOR]**

> When you're ready, walk back up to the bridge and continue across to the Right Bank. Then turn right onto the quai and follow the river east, past the Conciergerie on your right. Cross back onto the island over the next bridge, the Pont au Change, and follow the signs toward Notre-Dame. About ten minutes. `[GLUE_NAV]`

**[SILENCE — ~3 minutes of walking. [GLUE_PAUSE]]**

**[NARRATOR — audio resumes mid-walk]**

> While we walk, here's what this island is. `[GLUE_NAV]`
>
> The Île de la Cité was the first part of Paris to be settled, occupied by the Celtic tribe of the Parisii in the 3rd century BC. `[B:ile-de-la-cite-origins]`
>
> In the 3rd century AD, the Roman Emperor Julian established his seat on the island, on the site of today's Palais de Justice — the building you stood in front of half an hour ago. It was here in 360 that he was proclaimed emperor by his own soldiers. `[B:ile-de-la-cite-origins, with structural callback]`
>
> In the 6th century, the Merovingian king Childebert made the island the permanent home of the kings of France. And in the 13th century, Louis the Ninth built that private chapel adjoining the palace — la Sainte-Chapelle — to house the piece of the Holy Cross and the Crown of Thorns he had bought from the last Emperor of Constantinople. `[B:ile-de-la-cite-origins]`

**[SILENCE — last few minutes of approach. [GLUE_PAUSE]]**

---

### Stop 5 — Notre-Dame parvis (climax)

**[NARRATOR — user has arrived at the parvis, the open plaza in front of the west façade]**

> The cathedral is in front of you. Find a spot in the open plaza where you can see both towers and the rose window above the central door. `[GLUE_NAV]`
>
> *[15-second pause — let the building land. [GLUE_PAUSE]]*
>
> Between 1163 and 1330, anonymous artisans carved Notre-Dame from stone, slipping imperceptibly from the Romanesque to the Gothic style yet sustaining architectural unity. Bishop Maurice de Sully initiated the project, commissioning a monument to transcend every other in the kingdom. `[B:notre-dame-construction]`
>
> *[5-second pause] [GLUE_PAUSE]*
>
> During the French Revolution, Notre-Dame was stripped of its treasures and rededicated to the Cult of Reason. Then it was put up for sale as building material. A certain Citoyen Simon nearly purchased the cathedral — one of the closest brushes with destruction in the building's history. `[B:notre-dame-revolution-sale]`
>
> *[5-second pause] [GLUE_PAUSE]*
>
> Forty years later, in 1831, Victor Hugo published a novel about the cathedral. `[ARITH]` The Hunchback of Notre-Dame was written partly as a plea to save the crumbling building. The book ignited a wave of public passion for the medieval monument and directly led to the campaign for its restoration — proof, as one writer put it, that a novel can save a building. `[B:notre-dame-hugo-saved]`
>
> *[5-second pause] [GLUE_PAUSE]*
>
> Forty years after that, in May 1871, during the Paris Commune, Communards piled chairs and furniture against the doors of the cathedral and set them alight. `[ARITH]` `[B:notre-dame-commune-fire]`
>
> Doctors and staff from the neighbouring Hôtel-Dieu — the hospital just to the north of the parvis, on your left — rushed across and extinguished the flames, saving the cathedral from destruction. `[B:notre-dame-commune-fire, with structural sensory callout]`
>
> *[15-second pause — the climax pause. [GLUE_PAUSE]]*

---

### Walking transition — to Rue Chanoinesse

**[NARRATOR]**

> The walk from here goes around the north side of the cathedral. Walk past the towers on your left, around the back, and follow the small street that runs behind the cathedral. The street is called Rue Chanoinesse. About four minutes. `[GLUE_NAV]`

**[SILENCE — ~3 minutes of walking around the cathedral. [GLUE_PAUSE]]**

---

### Stop 6 — Rue Chanoinesse (walk-through)

**[NARRATOR — user is walking along Rue Chanoinesse, audio plays during movement]**

> You're walking along Rue Chanoinesse now. `[STRUCTURAL]`
>
> In 1118, the brilliant philosopher Peter Abelard came to this street to tutor a young woman called Heloise, the niece of Canon Fulbert. Their passionate love affair — one of the most famous in history — ended in catastrophe when Fulbert, enraged by a secret marriage and pregnancy, hired thugs to castrate Abelard. Heloise became a nun. Abelard became a monk. Their anguished love letters became classics of medieval literature. `[B:rue-chanoinesse-abelard-heloise]`
>
> *[10-second pause] [GLUE_PAUSE]*
>
> Their remains had an extraordinary journey through the centuries. They were eventually reunited in death and now lie together at Père Lachaise cemetery — the most visited grave in that famous necropolis. Medallion portraits of the lovers can be seen at 9 quai aux Fleurs, near the site of their fateful encounter. `[B:rue-chanoinesse-remains]`

---

### Walking transition — back to Pont Saint-Michel

**[NARRATOR]**

> Keep walking. Follow the street back toward the river, then turn left along the quai. You'll see the Pont Saint-Michel ahead — the bridge that takes you back to where you started. About five minutes. `[GLUE_NAV]`

**[SILENCE — ~5 minutes of walking. [GLUE_PAUSE]]**

---

### Stop 7 — Closing callback at Place Saint-Michel

**[NARRATOR — user is back at the fountain in Place Saint-Michel]**

> You're back where you started. `[STRUCTURAL]`
>
> *[5-second pause] [GLUE_PAUSE]*
>
> When this walk began, we stood in a square named after a chapel that no longer exists. `[callback to opening — refs B:sainte-chapelle-chapelle-saint-michel]`
>
> *[3-second pause]*
>
> Then you walked across the river to its successor, the Sainte-Chapelle, which was put up for sale as national property in 1847 and very nearly went the way of the chapel it replaced. The Communards poured petrol on it in 1871 and only failed to burn it because they ran out of time. `[callback — refs B:sainte-chapelle-nearly-not-survive]`
>
> *[3-second pause]*
>
> You stood in front of the Conciergerie, the medieval royal palace that the kings of France abandoned after a riot in 1358 and that became, four centuries later, a Revolutionary prison. Marie-Antoinette was held there for ten weeks. Two thousand seven hundred and eighty victims of the Revolutionary Tribunal passed through that arcade entrance. `[callback — refs B:ile-de-la-cite-marcel-uprising + B:conciergerie-origin + B:conciergerie-revolution-prisoners]`
>
> *[3-second pause]*
>
> You stopped at the tip of the island, where the green bookstalls along the river are the last quiet remnant of a bridge that used to be a world of its own. `[callback — refs B:pont-neuf-bouquinistes]`
>
> *[3-second pause]*
>
> You walked into the parvis of Notre-Dame, which was nearly sold for stone after the Revolution, and which was nearly burned by the Communards. It is still standing because doctors from the Hôtel-Dieu rushed across the parvis and put the fire out — and because forty years earlier, Victor Hugo had written a novel that made the city care about the building enough to save it. `[callback — refs B:notre-dame-revolution-sale + B:notre-dame-commune-fire + B:notre-dame-hugo-saved]`
>
> *[3-second pause]*
>
> And you walked along Rue Chanoinesse, where in 1118 a philosopher and a young woman fell in love and were torn apart. He became a monk. She became a nun. They were buried in different places and reunited in death centuries later. Their letters survived. `[callback — refs B:rue-chanoinesse-abelard-heloise + B:rue-chanoinesse-remains]`
>
> *[10-second pause] [GLUE_PAUSE]*
>
> The Sainte-Chapelle. The bouquinistes. The cathedral. The letters of Heloise. Every one of them came close to being lost. They're here because of accidents — and because some people, in some moments, decided to save them. `[theme statement — summary callback to beats already played, allowed under "themes as callbacks" rule]`
>
> *[5-second pause] [GLUE_PAUSE]*
>
> Thank you for walking with us.

---

## Audit notes

### Time and audio budget

| Segment | Walking | Stop | Audio |
|---|---|---|---|
| Cold open | — | 2 min | ~2 min |
| Walk to Sainte-Chapelle | 3 min | — | ~1.5 min |
| Sainte-Chapelle stop | — | 5 min | ~4 min |
| Walk to Conciergerie | 3 min | — | ~1.5 min (Marcel beat) |
| Conciergerie stop | — | 4 min | ~3 min |
| Walk to Pont Neuf | 8 min | — | 0 (silent) |
| Pont Neuf stop | — | 2 min | ~1 min |
| Walk to Notre-Dame | 10 min | — | ~1 min (origins beat) |
| Notre-Dame stop | — | 6 min | ~3 min |
| Walk to Rue Chanoinesse | 4 min | — | 0 (silent) |
| Rue Chanoinesse walk-through | 5 min | — | ~1.5 min |
| Walk to Pont Saint-Michel | 5 min | — | 0 (silent) |
| Closing callback | — | 4 min | ~3 min |
| **Totals** | **38 min** | **23 min** | **~22 min audio** |

**Total tour time:** 61 min planned + 15% buffer = **~70 min total**.
**Audio fraction:** 22 / 70 = **~31%** ✅ well under the 60% cap.
**Distance:** ~1.8 km.
**Stops:** 5 anchors + 1 walk-through + cold open + closing.

### Sourcing audit

All factual content traces to a beat or a structural fact. Three categories of borderline cases that should become explicit rules in the design doc:

1. **Arithmetic on dates from beats** (`[ARITH]`): "four hundred years later," "forty years later," "forty years after that." These compute differences between dates that appear in cited beats. **Proposed rule: arithmetic on numeric facts in cited beats is allowed as a structural connector. The arithmetic itself must be correct and the inputs must come from beats.**

2. **Structural sensory callouts** ("the hospital just to the north of the parvis, on your left"): These add a real-world pointer to a beat-sourced fact. They're verifiable against any map. **Proposed rule: pointing to currently-visible features adjacent to a beat's subject is allowed if and only if the feature is verifiable in the database or on a map.**

3. **Cross-POI structural callbacks** ("the building you stood in front of half an hour ago"): These reference earlier moments in the same tour, not new claims. **Proposed rule: tour-internal callbacks are always allowed and are the preferred way to build narrative continuity without introducing new facts.**

### Violations caught and cut during drafting

These are the failure modes that would have shipped without the discipline:

1. **First-pass cold open:** "the fountain you see — that's only 19th century, Haussmann's work" — date and attribution with no beat backing. Cut. *This is the exact failure mode the runtime guard must structurally prevent.*
2. **First-pass Sainte-Chapelle ending:** "Everything you're looking at right now is here by accident. We'll see that pattern again on this walk." Theme forecast at the start. Cut per the "themes as callbacks" rule.
3. **First-pass Pont Neuf opening:** "The Pont Neuf is the oldest standing bridge in Paris. Henri IV inaugurated it in [year]." Both claims unsourced. Cut. The Pont Neuf beats reference the bridge but never establish its age or its inauguration date.
4. **First-pass Pont Neuf closing line:** "They survived. Most things on this island didn't." Editorial summary statement at a mid-tour stop, mini-forecast. Cut.
5. **First-pass closing callback:** "They were buried in different places and reunited in death seven hundred years later." The "seven hundred years" was invention — the beat says "centuries" without specifying. Cut to "centuries later."
6. **First-pass Conciergerie line:** "the antechamber to the guillotine" — poetic framing not in any beat. Cut. Replaced with the literal beat content.
7. **First-pass Notre-Dame framing:** Calling the Revolution and the Commune "first revolution / second revolution." The Commune is debated as a revolution. Cut the framing words; let the beats name themselves.

**Seven violations caught in one hand-drafted pass by a careful model.** At scale of 10,000 generated tours, this is a constant background pressure. Source-traceability at sentence level is not optional.

### Beat selection notes

**Notre-Dame had 12 beats; the tour used 4.** Picked: construction, Revolution sale, Hugo's novel, Communards. Rejected for THIS theme: polyphonic music origins, the Emmanuel bell story, Kings of Judah recovery (great survival beat — runner-up), Viollet-le-Duc, Rabelais's Gargantua, two coronations, Pilier des Nautes, baroque interior vandalism. **Same POI in a different theme would pick a different 4.** This confirms the beat-selection-by-theme intuition: POI selection and beat selection are different problems and the second one is where lens/entity/theme matching pays off.

**Conciergerie had 5 beats; the tour used 2.** Picked: origin (governor → 1391 prison) and Revolution prisoners (Marie-Antoinette + 2780). Rejected: the Sanson family executioners (96-second beat, fascinating but too long and tangential), Ravaillac/Brinvilliers/Cartouche list (atmospheric but doesn't move the spine), Marshal Fersen invisible ink (sensory anchor is at rue Saint-Honoré, wrong location).

**Île de la Cité had 4 beats; the tour used 2 — both as transition narration during walking, not as a stop.** This is interesting. The Île de la Cité is a tier-5 POI but it has no fixed point you'd "stop at" — it IS the island. So its beats functioned as walking-narration spine that bridged other anchors. **This suggests a new POI type: `setting` POIs whose beats provide transition/contextual narration rather than acting as stop destinations.** Worth capturing as an open question in the design doc.

---

## Lessons this example surfaced

(All also captured as feedback memories where applicable.)

1. **Themes can be discovered from beat content, not just lens tags.** "Survival" is not a lens — it's a subject pattern across beats. Suggests we need entity/theme extraction at ingest, not just lens tagging. *(Memory: feedback_tour_themes_emerge.)*

2. **Cross-POI graph adjacency is the killer feature.** The Marcel uprising beat (Île de la Cité) and the Conciergerie origin beat together explain why the royal palace became a prison — neither does it alone. With entity tagging, the runtime would surface this automatically. Today it required reading texts. **This is the strongest argument for adding `entities` and `time_period` to the beat schema.**

3. **The killer cold-open hook is often a place-name origin.** Several POI beats explain why nearby places are named what they are. Those make perfect cold opens because they're sensory-anchored — the user is standing in the named place. *Add to design doc as a heuristic: when scoring beats for cold-open candidates, prefer beats that explain the user's current location's name.*

4. **Source-traceability caught seven violations during a single careful pass.** Without it, all seven would have shipped. *(Memory: feedback_tour_source_traceability.)*

5. **Honest length: the right tour for this brief is ~70 min, not 120 min.** Padding it would dilute the spine. With richer beat data and good seasoning, the same skeleton would honestly fill more time.

6. **The "look at the thing" silence after each anchor scales with stop importance.** Notre-Dame got 15 + 15 second pauses; Pont Neuf got a single 15-second pause; Conciergerie got 5 + 8. *Not a uniform rule — it scales with how much there is to look at.*

7. **The 12-beat Notre-Dame problem is a beat-selection problem, not a POI-selection problem.** The same POI yields a completely different script under a different theme. The selection happens at two layers: which POIs make the cut, and then which beats per POI serve the theme. *(Already in design doc.)*

8. **Some POIs are settings, not stops.** The Île de la Cité has no fixed stop point — its beats served as walking-transition narration that bridged other anchors. Suggests a `poi_role` field: `stop` vs `setting` vs `walk_by_only`. *Open question for design doc.*

9. **Some POIs lack "establishing" beats.** The Pont Neuf has zero beats that simply explain what the bridge IS (its age, when it was built). Every beat assumes the user knows. **We need a beat type called something like `establishing` or `definition` that tersely describes what the POI is — short, factual, no story.** Without it, the script has to either improvise structural sentences (risky for invention) or jump straight into a story without setup (jarring). *Add to beat metadata wishlist.*

10. **Per-lens tone modulations are embedded in how a beat is paraphrased into the script, not applied as a separate layer.** The Conciergerie (dark history) wanted slower, less rhetorical sentences. Rue Chanoinesse (literary) wanted longer, story-shaped sentences. Notre-Dame (mixed) wanted variation across the four beats. The runtime stitcher's prompt should include the relevant lens-tone instructions for each segment, applied as the beats get paraphrased — not bolted on afterwards.

11. **Arithmetic on beat-dated facts is a useful structural connector** ("forty years later"). Should be an explicit allowed operation in the source-traceability rules. Same for cross-POI structural callbacks ("the building you stood in front of half an hour ago") — they create narrative continuity without introducing new claims.

12. **The closing callback ended up substantial — ~3 min of audio.** Worth budgeting for. The closing is where the theme is named and earned, and rushing it would waste the rest of the tour. **Proposed rule: closing callback gets 3–5% of total tour time minimum.**
