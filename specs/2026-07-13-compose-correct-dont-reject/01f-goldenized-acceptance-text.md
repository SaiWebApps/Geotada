# 01f — Goldenized acceptance text + diff fixtures (the oracle for Scopes 2 / 3b / 6)

**Provenance:** `01e-human-gold-rewrite.md` (the product owner's hand rewrite of the
Scope-1 corrected output, Version B) with the SIX recorded deviations substituted for
grounded equivalents — approved by the human 2026-07-15 (04b Open Question 3). This text
is what the FN battery, the fact-diff must-pass fixture, and AC-9's acceptance review
score against. 01e remains the record of the human's raw rewrite; THIS file is the
machine oracle.

## The six deviations and their substitutions

| # | 01e text | Goldenized | Why |
|---|----------|------------|-----|
| 1 | "we have to imagine the neighbourhood" | "go back to the neighbourhood as it was" | locked voice: never "imagine" (generation.py:86) |
| 2 | "William Makepeace Thackeray" | "Thackeray" | world knowledge absent from beat bodies (01d) |
| 3 | "The English writers … both stayed" / "another English writer" | "Thackeray and Charles Dickens both stayed" / "another writer" | world knowledge absent from bodies (01d) |
| 4 | "the nearby Tuileries Palace" | "the nearby Tuileries" | "Palace" absent from bodies (04b BL-V1, pre-gate check) |
| 5 | "the centre of Parisian fashion" | "its centre of gravity" | "Parisian" absent from bodies (04b BL-V1); "its" = haute couture's, matching the body |
| 6 | "the end of the Second World War" | "the end of World War II" | bodies say "World War II" (04b BL-V1) |

---

## The goldenized text

Here, at the corner of rue de Castiglione and rue de Rivoli, stands the Hotel Le Meurice. Its discreet entrance is at 228 rue de Rivoli.

To understand how a hotel like this came to belong here, go back to the neighbourhood as it was when the nearby Tuileries was still the seat of power.

The ladies of the Napoleonic nobility helped make this stretch of rue de Rivoli fashionable, drawing an English clientele to the area. At number 224, the English bookshop Galignani kept the daily newspapers from home. At number 248, W. H. Smith opened its Paris branch for the same clientele.

Nearby, the jewellery and clothing shops of rue de Castiglione and Place Vendôme served this fashionable society. It was here, supplying Empress Eugénie and the other ladies of the Napoleonic court, that French haute couture was born in the second half of the nineteenth century.

One of its pioneers was Charles Worth, the Empress's English couturier. A century later, its centre of gravity would drift westward to the 8th arrondissement.

Le Meurice was one of the grand palace hotels that came to dominate this quarter. Thackeray and Charles Dickens both stayed here during the nineteenth century. Dickens stayed while researching A Tale of Two Cities, his novel about the years leading up to the French Revolution.

The hotel is also linked to another writer: George Orwell.

Long before he became famous, a penniless Orwell worked in a grand Paris hotel as a plongeur. In Down and Out in Paris and London, he described the plongeur as “the slave of the slave,” worked to the bone behind the splendour of the hotel.

But did Orwell really work here?

He never named the hotel. His biographers have placed it elsewhere in these streets—at the Lotti, just around the corner on rue de Castiglione, or at the Crillon. Paris lore, however, has long pinned the story on Le Meurice.

What Orwell described could certainly fit the great hotels of this entire quarter.

From the outside, there was “a vast, grandiose place with a classical façade,” and, at one side, “a little, dark doorway like a rat hole, which was the service entrance.”

Behind that grand façade, the kitchens were a kingdom of hell: a “stifling low-ceilinged inferno of a cellar,” red-lit by the fires and deafening with oaths and the clanging of pots and pans.

Only a double door separated the squalid scullery from the dining room.

On one side sat the customers “in all their splendour,” with spotless tablecloths, bowls of flowers, mirrors, gilt cornices and painted cherubs.

And on the other side, only a few feet away, Orwell and the other workers stood, as he put it, “in our disgusting filth.”

A generation later, the German High Command of the Paris garrison took up residence in the lavish Le Meurice. General von Choltitz was also quartered here when he saved Paris from destruction at the end of World War II.

One wonders whether any of them had read Down and Out.

---

## Fact-diff fixtures (two-sided; committed as tests in Scope 3b)

**Must-PASS (diff calibration):** the pair (`01c` Version B → this text) passes the
salient-token diff. Known calibration work this forces: `_canonicalize_dates` extended
to word-form ordinals ("19th" ↔ "nineteenth"); "WH"/"II"-class tokens (<3 chars) are
recorded blind spots covered by the quote rule + entailment, not the diff.

**Must-CATCH (the anti-ratchet — each mutation of this text MUST fail the diff):**
1. Delete "Galignani" (entity loss).
2. Delete "224" (street-number loss).
3. Change "224" → "242" (number corruption — caught by the diff's input-token
   requirement plus the pre-gate on the output side).

**Quote-fidelity fixture:** every quoted span above appears verbatim in beat
`85ebe707`'s body (where the human reworded, the changed words sit OUTSIDE the quotation
marks — e.g. "painted cherubs"). A mutated version with one word changed INSIDE a quoted
span must fail the quote rule.
