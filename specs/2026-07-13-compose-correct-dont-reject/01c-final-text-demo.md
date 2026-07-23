# Scope 1 — the Le Meurice stop as a tourist would hear it (assembled for human judgment)

**How this was assembled (read first):** the live probe (01b-probe-transcript.md) verdicts each
sentence but does not assemble a final script. Version B below is assembled mechanically from
those verdicts: PASS sentences ship as composed, CORRECTED sentences ship their corrected text,
FLOORED sentences ship their corpus fallback sentences **once** (deduped) — i.e. Scope 3's
collateral-subset + dedup floor rule applied by hand. The probe's *naive* floor (whole cited-beat
sets) would collapse Version B back into roughly Version A — which is exactly the pathology
Scope 3's rule exists to kill. Provenance tags: [composed] survived checking as written,
[corrected] one Opus correction call, [corpus] verbatim stitch fallback (floor).

---

## Version A — TODAY (stitched revert; the ticket's complaint)

When the Tuileries was still the seat of power, the ladies of the Napoleonic nobility drew an
English clientele to this stretch of rue de Rivoli: the prestigious Meurice at no. 228 faced the
Tuileries Gardens, the English bookshop Galignani at 224 kept the daily papers of home, and WH
Smith opened its Paris branch at 248 for their convenience. The jewellery and clothes shops of
rue de Castiglione and Place Vendôme catered to the same set. It was here, serving Empress
Eugénie and the other ladies of the Napoleonic court, that French haute couture was born in the
second half of the 19th century — pioneered by Charles Worth, the Empress's English couturier.
A century later its centre of gravity drifted westward to the 8th arrondissement. On the corner
of rue de Castiglione and rue de Rivoli stands the hotel le Meurice. Charles Dickens stayed here
in the 19th century while researching his novel about the years leading up to the French
Revolution, A Tale of Two Cities. It was also where the German General von Choltitz was
quartered when he saved Paris from destruction at the end of World War II. At 228 rue de Rivoli
is the discreet entrance to the Meurice, where Thackeray and Dickens once stayed — the grandest
of the palace hotels that colonised this quarter, and the world a penniless George Orwell served
when he was worked to the bone as a plongeur, "the slave of the slave," in Down and Out in Paris
and London. He never named his hotel, and his biographers place it elsewhere in these streets —
the Lotti, just around the corner on rue de Castiglione, or the Crillon — though Paris lore has
long pinned the story here. What he described fits the whole quarter: "a vast, grandiose place
with a classical façade, and at one side a little, dark doorway like a rat hole, which was the
service entrance." The kitchens were the kingdom of hell: "stifling low-ceilinged inferno of a
cellar, red-lit from the fires, and deafening with oaths and clanging of pots and pans." Only a
double door separated the squalid scullery from the dining room. "There sat the customers in all
their splendour and spotless table-cloths, bowls of flowers, mirrors and gilt cornices and
painted cherubims; and here, just a few feet away we in our disgusting filth." A generation
later, the German High Command of the Paris garrison took up residence at the lavish Meurice.
One wonders whether any of them had read Down and Out.

---

## Version B — AFTER the correct-loop (composed, corrected where needed, floored where needed)

[composed] When the Tuileries was still the seat of power, the ladies of the Napoleonic nobility
drew an English clientele to this stretch of rue de Rivoli: the English bookshop Galignani at 224
kept the daily papers of home, and WH Smith opened its Paris branch at 248 for their convenience.

[corpus — floor of a rejected fusion] On the corner of rue de Castiglione and rue de Rivoli
stands the hotel le Meurice. At 228 rue de Rivoli is the discreet entrance to the Meurice, where
Thackeray and Dickens once stayed — the grandest of the palace hotels that colonised this
quarter, and the world a penniless George Orwell served when he was worked to the bone as a
plongeur, "the slave of the slave," in Down and Out in Paris and London.

[composed] The jewellery and clothes shops of rue de Castiglione and Place Vendôme catered to
the same set. It was here, serving Empress Eugénie and the other ladies of the Napoleonic court,
that French haute couture was born in the second half of the 19th century — pioneered by Charles
Worth, the Empress's English couturier. A century later its centre of gravity drifted westward
to the 8th arrondissement.

[corrected] Charles Dickens stayed here in the 19th century, as did Thackeray — Dickens while
researching A Tale of Two Cities, his novel about the years leading up to the French Revolution.

[corrected] Did he really work here? He never named his hotel, and his biographers place it
elsewhere in these streets — the Lotti, just around the corner on rue de Castiglione, or the
Crillon — though Paris lore has long pinned the story here.

[composed] What he described fits the whole quarter: "a vast, grandiose place with a classical
façade, and at one side a little, dark doorway like a rat hole, which was the service entrance."
The kitchens were the kingdom of hell: "stifling low-ceilinged inferno of a cellar, red-lit from
the fires, and deafening with oaths and clanging of pots and pans." Only a double door separated
the squalid scullery from the dining room. "There sat the customers in all their splendour and
spotless table-cloths, bowls of flowers, mirrors and gilt cornices and painted cherubims; and
here, just a few feet away we in our disgusting filth."

[corpus — floor of a rejected fusion] A generation later, the German High Command of the Paris
garrison took up residence at the lavish Meurice. It was also where the German General von
Choltitz was quartered when he saved Paris from destruction at the end of World War II.

[composed] One wonders whether any of them had read Down and Out.

---

**Notes for the reader:**
- One rejected fusion ("The prestigious Meurice itself stands on the corner… the grandest of the
  palace hotels…") and one rejected Orwell sentence floored to the same two corpus sentences —
  they ship once (the dedup above).
- The judge confirmed the two fusion floors were Haiku FALSE rejections (every atom is in the
  cited bodies) — with Scope 2's fusion-support tuning they would ship as composed, moving
  Version B further from Version A.
- The compose call also emits glue/transition sentences between stops; they are outside this
  stop's beat-cited set and not shown.
