# Stage-4 micro-probe — the human's gold rewrite vs the CURRENT checker

Question: does per-sentence Haiku entailment (support = union of the three Le
Meurice beats' script_body, identical to the Scope-1 probe conditions) accept a
human-quality global rewrite? If yes → redesign = free the composer, keep the
gate. If it rejects good sentences → the gate must change too.

Sentences: 29 · shortcut 1 · entailed 24 · REJECTED 4

- [PASS-ENTAILED] Here, at the corner of rue de Castiglione and rue de Rivoli, stands the Hotel Le Meurice.
- [PASS-ENTAILED] Its discreet entrance is at 228 rue de Rivoli.
- [PASS-ENTAILED] To understand how a hotel like this came to belong here, we have to imagine the neighbourhood when the nearby Tuileries Palace was still the seat of power.
- [PASS-ENTAILED] The ladies of the Napoleonic nobility helped make this stretch of rue de Rivoli fashionable, drawing an English clientele to the area.
- [PASS-ENTAILED] At number 224, the English bookshop Galignani kept the daily newspapers from home.
- [PASS-ENTAILED] At number 248, W. H. Smith opened its Paris branch for the same clientele.
- [PASS-ENTAILED] Nearby, the jewellery and clothing shops of rue de Castiglione and Place Vendôme served this fashionable society.
- [REJECTED] It was here, supplying Empress Eugénie and the other ladies of the Napoleonic court, that French haute couture was born in the second half of the nineteenth century.
- [PASS-ENTAILED] One of its pioneers was Charles Worth, the Empress's English couturier.
- [PASS-ENTAILED] A century later, the centre of Parisian fashion would drift westward to the 8th arrondissement.
- [PASS-ENTAILED] Le Meurice was one of the grand palace hotels that came to dominate this quarter.
- [REJECTED] The English writers William Makepeace Thackeray and Charles Dickens both stayed here during the nineteenth century.
- [PASS-ENTAILED] Dickens stayed while researching A Tale of Two Cities, his novel about the years leading up to the French Revolution.
- [REJECTED] The hotel is also linked to another English writer: George Orwell.
- [PASS-ENTAILED] Long before he became famous, a penniless Orwell worked in a grand Paris hotel as a plongeur.
- [PASS-ENTAILED] In Down and Out in Paris and London, he described the plongeur as “the slave of the slave,” worked to the bone behind the splendour of the hotel.
- [REJECTED] But did Orwell really work here?
- [PASS-ENTAILED] He never named the hotel.
- [PASS-ENTAILED] His biographers have placed it elsewhere in these streets—at the Lotti, just around the corner on rue de Castiglione, or at the Crillon.
- [PASS-ENTAILED] Paris lore, however, has long pinned the story on Le Meurice.
- [PASS-ENTAILED] What Orwell described could certainly fit the great hotels of this entire quarter.
- [PASS-ENTAILED] From the outside, there was “a vast, grandiose place with a classical façade,” and, at one side, “a little, dark doorway like a rat hole, which was the service entrance.”
- [PASS-ENTAILED] Behind that grand façade, the kitchens were a kingdom of hell: a “stifling low-ceilinged inferno of a cellar,” red-lit by the fires and deafening with oaths and the clanging of pots and pans.
- [PASS-ENTAILED] Only a double door separated the squalid scullery from the dining room.
- [PASS-ENTAILED] On one side sat the customers “in all their splendour,” with spotless tablecloths, bowls of flowers, mirrors, gilt cornices and painted cherubs.
- [PASS-ENTAILED] And on the other side, only a few feet away, Orwell and the other workers stood, as he put it, “in our disgusting filth.”
- [PASS-ENTAILED] A generation later, the German High Command of the Paris garrison took up residence in the lavish Le Meurice.
- [PASS-ENTAILED] General von Choltitz was also quartered here when he saved Paris from destruction at the end of the Second World War.
- [PASS-SHORTCUT] One wonders whether any of them had read Down and Out.

## Interpretation (manager review, 2026-07-15)

25/29 accepted — the human's global restructuring (reordering, motivation bridges, compound
unpacking, staged quotes, dispute pivot) passes the CURRENT gate. "Free the composer, keep the
gate" is validated. The 4 rejections decompose into three distinct classes:

1. **Genuine checker FN (1):** s8 "It was here, supplying Empress Eugénie… haute couture was
   born…" — near-verbatim corpus fact ("serving"→"supplying", Worth clause split off). Same
   fusion/paraphrase FN class as live-probe s2/s10. → the calibration work item.
2. **Correct catches of world-knowledge injection (2):** "William Makepeace" and the
   "English writer(s)" attributions are true in the world but absent from beat bodies — the
   never-fabricate/no-world-knowledge rule working as designed. In a correct-loop these get
   TRIMMED ("Thackeray and Charles Dickens"), not floored.
3. **Mechanical gap (1):** "But did Orwell really work here?" — a rhetorical question asserts
   nothing; entailment has nothing to affirm. Questions + pure bridging glue need a
   non-assertive lane: salient-token safety check only, no entailment.

Stage-4 redesign shape: composer rebuilt to write to the 01e bar (plan the stop globally,
constrained to bodies); gate kept with three amendments (fusion-FN calibration, non-assertive
lane, trim-don't-floor for unsourced garnish); floor stays as rare worst case, upgraded to
verified re-compose of the floored span (raw stitch seams remain below the human bar per the
Scope-1 NO-GO).
