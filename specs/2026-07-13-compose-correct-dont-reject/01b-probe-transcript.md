# Scope 1 — Le Meurice live probe transcript
_2026-07-15T19:05:28+00:00 · LIVE RUN_

### Config (static repro config from the ticket)
- center (48.8635, 2.328), duration 240 min, city paris
- lenses ['famous_residents', 'literary_heritage', 'historic_arch']
- Neo4j: NEO4J_URI from env/default — matches dev default bolt://localhost:7687: True (value never echoed); COMPOSE_PROVIDER=anthropic
- models: compose/correct=claude-opus-4-8, entailment=claude-haiku-4-5-20251001

### Building the tour (Neo4j reads — free)
Le Meurice stop located: stop_idx=1, 12 stitched sentences, 3 anchor beats (reflection slot at this stop in the live config: False)

### Probe-beat presence check
- key_claims=() beat: seated as c9c90a74… (key_claims=0, body=744 chars)
- compound beat: seated as 85ebe707… (key_claims=0, body=1312 chars)
- third anchor (c3d4a78a…): seated as c3d4a78a… (key_claims=2, body=362 chars)

### Cost estimate (live run)
- 1 stop compose      — claude-opus-4-8 ($5.00/MTok in, $25.00/MTok out): ~6K in / ~3K out  = ~$0.10
- 31-46 entailment calls — claude-haiku-4-5-20251001 ($1.00/$5.00 per MTok): ~700 in / 5 out each = ~$0.03
- <=10 correction calls — claude-opus-4-8: ~2.5K in / ~700 out each = ~$0.30 worst case
- ESTIMATED TOTAL: ~$0.44 (worst case; actual spend printed at the end of a live run)

## Live compose (1 call)
composed 12 sentences (11 beat-cited)

## Per-sentence correct-loop transcript

--- Sentence 1/11 [cites: c9c90a74] [PROBE: key_claims=() beat c9c90a74]
  original : When the Tuileries was still the seat of power, the ladies of the Napoleonic nobility drew an English clientele to this stretch of rue de Rivoli: the English bookshop Galignani at 224 kept the daily papers of home, and WH Smith opened its Paris branch at 248 for their convenience.
  shortcut : miss
  entailment (script_body-only support): YES
  verdict  : PASS-ENTAILED

--- Sentence 2/11 [cites: 85ebe707, c9c90a74, c3d4a78a] [PROBE: key_claims=() beat c9c90a74] [PROBE: compound beat 85ebe707] [PROBE: fused citation (cites >=2 beats)]
  original : The prestigious Meurice itself stands on the corner of rue de Castiglione and rue de Rivoli, its discreet entrance at no. 228 facing the Tuileries Gardens — the grandest of the palace hotels that colonised this quarter.
  shortcut : miss
  entailment (script_body-only support): NO
  corrected : The prestigious Meurice itself stands on the corner of rue de Castiglione and rue de Rivoli, its discreet entrance at no. 228 facing the Tuileries Gardens — the grandest of the palace hotels that colonised this quarter.
  re-check  : shortcut=miss entailment=NO
  verdict  : FLOOR — beat's stitch sentences ship instead:
    | When the Tuileries was still the seat of power, the ladies of the Napoleonic nobility drew an English clientele to this stretch of rue de Rivoli: the prestigious Meurice at no. 228 faced the Tuileries Gardens, the English bookshop Galignani at 224 kept the daily papers of home, and WH Smith opened its Paris branch at 248 for their convenience.
    | The jewellery and clothes shops of rue de Castiglione and Place Vendôme catered to the same set.
    | It was here, serving Empress Eugénie and the other ladies of the Napoleonic court, that French haute couture was born in the second half of the 19th century — pioneered by Charles Worth, the Empress's English couturier.
    | A century later its centre of gravity drifted westward to the 8th arrondissement.
    | On the corner of rue de Castiglione and rue de Rivoli stands the hotel le Meurice.
    | Charles Dickens stayed here in the 19th century while researching his novel about the years leading up to the French Revolution, A Tale of Two Cities.
    | It was also where the German General von Choltitz was quartered when he saved Paris from destruction at the end of World War II.
    | At 228 rue de Rivoli is the discreet entrance to the Meurice, where Thackeray and Dickens once stayed — the grandest of the palace hotels that colonised this quarter, and the world a penniless George Orwell served when he was worked to the bone as a plongeur, “the slave of the slave,” in Down and Out in Paris and London.
    | He never named his hotel, and his biographers place it elsewhere in these streets — the Lotti, just around the corner on rue de Castiglione, or the Crillon — though Paris lore has long pinned the story here.
    | What he described fits the whole quarter: “a vast, grandiose place with a classical façade, and at one side a little, dark doorway like a rat hole, which was the service entrance.” The kitchens were the kingdom of hell: “stifling low-ceilinged inferno of a cellar, red-lit from the fires, and deafening with oaths and clanging of pots and pans.” Only a double door separated the squalid scullery from the dining room. “There sat the customers in all their splendour and spotless table-cloths, bowls of flowers, mirrors and gilt cornices and painted cherubims; and here, just a few feet away we in our disgusting filth.” A generation later, the German High Command of the Paris garrison took up residence at the lavish Meurice.
    | One wonders whether any of them had read Down and Out.

--- Sentence 3/11 [cites: c9c90a74] [PROBE: key_claims=() beat c9c90a74]
  original : The jewellery and clothes shops of rue de Castiglione and Place Vendôme catered to the same set.
  shortcut : HIT (complete sentence-unit run of a cited body)
  verdict  : PASS-SHORTCUT (zero LLM checks)

--- Sentence 4/11 [cites: c9c90a74] [PROBE: key_claims=() beat c9c90a74]
  original : It was here, serving Empress Eugénie and the other ladies of the Napoleonic court, that French haute couture was born in the second half of the 19th century — pioneered by Charles Worth, the Empress's English couturier.
  shortcut : HIT (complete sentence-unit run of a cited body)
  verdict  : PASS-SHORTCUT (zero LLM checks)

--- Sentence 5/11 [cites: c9c90a74] [PROBE: key_claims=() beat c9c90a74]
  original : A century later its centre of gravity drifted westward to the 8th arrondissement.
  shortcut : HIT (complete sentence-unit run of a cited body)
  verdict  : PASS-SHORTCUT (zero LLM checks)

--- Sentence 6/11 [cites: c3d4a78a, 85ebe707] [PROBE: compound beat 85ebe707] [PROBE: fused citation (cites >=2 beats)]
  original : Charles Dickens stayed here in the 19th century, as did Thackeray, Dickens while researching his novel about the years leading up to the French Revolution, A Tale of Two Cities.
  shortcut : miss
  entailment (script_body-only support): NO
  corrected : Charles Dickens stayed here in the 19th century, as did Thackeray — Dickens while researching A Tale of Two Cities, his novel about the years leading up to the French Revolution.
  re-check  : shortcut=miss entailment=YES
  verdict  : CORRECTED (one correction call)

--- Sentence 7/11 [cites: 85ebe707] [PROBE: compound beat 85ebe707]
  original : But the Meurice was also the world a penniless George Orwell served when he was worked to the bone as a plongeur, “the slave of the slave,” in Down and Out in Paris and London.
  shortcut : miss
  entailment (script_body-only support): NO
  corrected : But the Meurice was also the world a penniless George Orwell served when he was worked to the bone as a plongeur, "the slave of the slave," in Down and Out in Paris and London.
  re-check  : shortcut=miss entailment=NO
  verdict  : FLOOR — beat's stitch sentences ship instead:
    | At 228 rue de Rivoli is the discreet entrance to the Meurice, where Thackeray and Dickens once stayed — the grandest of the palace hotels that colonised this quarter, and the world a penniless George Orwell served when he was worked to the bone as a plongeur, “the slave of the slave,” in Down and Out in Paris and London.
    | He never named his hotel, and his biographers place it elsewhere in these streets — the Lotti, just around the corner on rue de Castiglione, or the Crillon — though Paris lore has long pinned the story here.
    | What he described fits the whole quarter: “a vast, grandiose place with a classical façade, and at one side a little, dark doorway like a rat hole, which was the service entrance.” The kitchens were the kingdom of hell: “stifling low-ceilinged inferno of a cellar, red-lit from the fires, and deafening with oaths and clanging of pots and pans.” Only a double door separated the squalid scullery from the dining room. “There sat the customers in all their splendour and spotless table-cloths, bowls of flowers, mirrors and gilt cornices and painted cherubims; and here, just a few feet away we in our disgusting filth.” A generation later, the German High Command of the Paris garrison took up residence at the lavish Meurice.
    | One wonders whether any of them had read Down and Out.

--- Sentence 8/11 [cites: 85ebe707] [PROBE: compound beat 85ebe707]
  original : Did he really scrub these very kitchens? He never named his hotel, and his biographers place it elsewhere in these streets — the Lotti, just around the corner on rue de Castiglione, or the Crillon — though Paris lore has long pinned the story here.
  shortcut : miss
  entailment (script_body-only support): NO
  corrected : Did he really work here? He never named his hotel, and his biographers place it elsewhere in these streets — the Lotti, just around the corner on rue de Castiglione, or the Crillon — though Paris lore has long pinned the story here.
  re-check  : shortcut=miss entailment=YES
  verdict  : CORRECTED (one correction call)

--- Sentence 9/11 [cites: 85ebe707] [PROBE: compound beat 85ebe707]
  original : What he described fits the whole quarter: “a vast, grandiose place with a classical façade, and at one side a little, dark doorway like a rat hole, which was the service entrance.” The kitchens were the kingdom of hell: “stifling low-ceilinged inferno of a cellar, red-lit from the fires, and deafening with oaths and clanging of pots and pans.” Only a double door separated the squalid scullery from the dining room. “There sat the customers in all their splendour and spotless table-cloths, bowls of flowers, mirrors and gilt cornices and painted cherubims; and here, just a few feet away we in our disgusting filth.”
  shortcut : miss
  entailment (script_body-only support): YES
  verdict  : PASS-ENTAILED

--- Sentence 10/11 [cites: 85ebe707, c3d4a78a] [PROBE: compound beat 85ebe707] [PROBE: fused citation (cites >=2 beats)]
  original : A generation later, the German High Command of the Paris garrison took up residence at the lavish Meurice — this was where General von Choltitz was quartered when he saved Paris from destruction at the end of World War II.
  shortcut : miss
  entailment (script_body-only support): NO
  corrected : A generation later, the German High Command of the Paris garrison took up residence at the lavish Meurice, and it was here that German General von Choltitz was quartered when he saved Paris from destruction at the end of World War II.
  re-check  : shortcut=miss entailment=NO
  verdict  : FLOOR — beat's stitch sentences ship instead:
    | On the corner of rue de Castiglione and rue de Rivoli stands the hotel le Meurice.
    | Charles Dickens stayed here in the 19th century while researching his novel about the years leading up to the French Revolution, A Tale of Two Cities.
    | It was also where the German General von Choltitz was quartered when he saved Paris from destruction at the end of World War II.
    | At 228 rue de Rivoli is the discreet entrance to the Meurice, where Thackeray and Dickens once stayed — the grandest of the palace hotels that colonised this quarter, and the world a penniless George Orwell served when he was worked to the bone as a plongeur, “the slave of the slave,” in Down and Out in Paris and London.
    | He never named his hotel, and his biographers place it elsewhere in these streets — the Lotti, just around the corner on rue de Castiglione, or the Crillon — though Paris lore has long pinned the story here.
    | What he described fits the whole quarter: “a vast, grandiose place with a classical façade, and at one side a little, dark doorway like a rat hole, which was the service entrance.” The kitchens were the kingdom of hell: “stifling low-ceilinged inferno of a cellar, red-lit from the fires, and deafening with oaths and clanging of pots and pans.” Only a double door separated the squalid scullery from the dining room. “There sat the customers in all their splendour and spotless table-cloths, bowls of flowers, mirrors and gilt cornices and painted cherubims; and here, just a few feet away we in our disgusting filth.” A generation later, the German High Command of the Paris garrison took up residence at the lavish Meurice.
    | One wonders whether any of them had read Down and Out.

--- Sentence 11/11 [cites: 85ebe707] [PROBE: compound beat 85ebe707]
  original : One wonders whether any of them had read Down and Out.
  shortcut : HIT (complete sentence-unit run of a cited body)
  verdict  : PASS-SHORTCUT (zero LLM checks)

## Probe extras
- unchanged corpus sentence (from the stitch, beat c9c90a74): shortcut HIT as required — 'When the Tuileries was still the seat of power, the ladies of the Napoleonic nobility drew an English clientele to this stretch of rue de Rivoli: the prestigious Meurice at no. 228 faced the Tuileries Gardens, the English bookshop Galignani at 224 kept the daily papers of home, and WH Smith opened its Paris branch at 248 for their convenience.'
- key_claims=() beat c9c90a74: covered by the composed sentences above (see labels)
- compound beat 85ebe707: covered by the composed sentences above (see labels)
- fused-citation sentence: produced naturally by the live compose (see labels)

## FP battery run (entailment only, no correction)

### FP battery (20 corrupted sentences, seed=20260715)
per class: entity_swap=11, date_shift=0, frankenfact=6, hedge_strip=3 — an under-filled class means this stop's corpus carries no such material (e.g. no 4-digit year / no hedge to strip)
- [entity_swap] 'Tuileries' (beat c9c90a74) -> 'French Revolution' (beat c3d4a78a)  => rejected (good)
  corrupted: When the French Revolution was still the seat of power, the ladies of the Napoleonic nobility drew an English clientele to this stretch of rue de Rivoli: the prestigious Meurice at no. 228 faced the Tuileries Gardens, the English bookshop Galignani at 224 kept the daily papers of home, and WH Smith opened its Paris branch at 248 for their convenience.
- [entity_swap] 'Empress's English' (beat c9c90a74) -> 'French Revolution' (beat c3d4a78a)  => rejected (good)
  corrupted: It was here, serving Empress Eugénie and the other ladies of the Napoleonic court, that French haute couture was born in the second half of the 19th century — pioneered by Charles Worth, the French Revolution couturier.
- [entity_swap] 'Charles Worth' (beat c9c90a74) -> 'Dickens' (beat 85ebe707)  => rejected (good)
  corrupted: It was here, serving Empress Eugénie and the other ladies of the Napoleonic court, that French haute couture was born in the second half of the 19th century — pioneered by Dickens, the Empress's English couturier.
- [entity_swap] 'French Revolution' (beat c3d4a78a) -> 'Galignani' (beat c9c90a74)  => rejected (good)
  corrupted: Charles Dickens stayed here in the 19th century while researching his novel about the years leading up to the Galignani, A Tale of Two Cities.
- [entity_swap] 'Paris' (beat c3d4a78a) -> 'Galignani' (beat c9c90a74)  => rejected (good)
  corrupted: It was also where the German General von Choltitz was quartered when he saved Galignani from destruction at the end of World War II.
- [frankenfact] subject of c9c90a74 x predicate of c3d4a78a  => rejected (good)
  corrupted: When the Tuileries stayed here in the 19th century while researching his novel about the years leading up to the French Revolution, A Tale of Two Cities.
- [frankenfact] subject of c9c90a74 x predicate of 85ebe707  => rejected (good)
  corrupted: When the Tuileries is the discreet entrance to the Meurice, where Thackeray and Dickens once stayed — the grandest of the palace hotels that colonised this quarter, and the world a penniless George Orwell served when he was worked to the bone as a plongeur, “the slave of the slave,” in Down and Out in Paris and London.
- [frankenfact] subject of c3d4a78a x predicate of c9c90a74  => rejected (good)
  corrupted: Charles Dickens was still the seat of power, the ladies of the Napoleonic nobility drew an English clientele to this stretch of rue de Rivoli: the prestigious Meurice at no. 228 faced the Tuileries Gardens, the English bookshop Galignani at 224 kept the daily papers of home, and WH Smith opened its Paris branch at 248 for their convenience.
- [frankenfact] subject of c3d4a78a x predicate of 85ebe707  => rejected (good)
  corrupted: Charles Dickens is the discreet entrance to the Meurice, where Thackeray and Dickens once stayed — the grandest of the palace hotels that colonised this quarter, and the world a penniless George Orwell served when he was worked to the bone as a plongeur, “the slave of the slave,” in Down and Out in Paris and London.
- [frankenfact] subject of 85ebe707 x predicate of c9c90a74  => rejected (good)
  corrupted: At 228 rue de Rivoli was still the seat of power, the ladies of the Napoleonic nobility drew an English clientele to this stretch of rue de Rivoli: the prestigious Meurice at no. 228 faced the Tuileries Gardens, the English bookshop Galignani at 224 kept the daily papers of home, and WH Smith opened its Paris branch at 248 for their convenience.
- [hedge_strip] removed dissenting clause ', and his biographers place it elsewhere in these streets — …' — only the local placement survives (beat 85ebe707)  => **ACCEPTED (BAD)**
  corrupted: He never named his hotel, though Paris lore has long pinned the story here.
- [hedge_strip] flattened lore hedge '— though Paris lore has long pinned the story here…' to a flat assertion (beat 85ebe707)  => rejected (good)
  corrupted: He never named his hotel, and his biographers place it elsewhere in these streets — the Lotti, just around the corner on rue de Castiglione, or the Crillon, and in fact the story happened here.
- [hedge_strip] removed the dissent AND flattened the lore hedge — the disputed story becomes flat local fact (beat 85ebe707)  => rejected (good)
  corrupted: He never named his hotel, and in fact the story happened here.
- [frankenfact] subject of 85ebe707 x predicate of c3d4a78a  => rejected (good)
  corrupted: At 228 rue de Rivoli stayed here in the 19th century while researching his novel about the years leading up to the French Revolution, A Tale of Two Cities.
- [entity_swap] 'Meurice' (beat c9c90a74) -> 'French Revolution' (beat c3d4a78a)  => rejected (good)
  corrupted: When the Tuileries was still the seat of power, the ladies of the Napoleonic nobility drew an English clientele to this stretch of rue de Rivoli: the prestigious French Revolution at no. 228 faced the Tuileries Gardens, the English bookshop Galignani at 224 kept the daily papers of home, and WH Smith opened its Paris branch at 248 for their convenience.
- [entity_swap] 'Charles Worth' (beat c9c90a74) -> 'German General von Choltitz' (beat c3d4a78a)  => rejected (good)
  corrupted: It was here, serving Empress Eugénie and the other ladies of the Napoleonic court, that French haute couture was born in the second half of the 19th century — pioneered by German General von Choltitz, the Empress's English couturier.
- [entity_swap] 'Place Vendôme' (beat c9c90a74) -> 'George Orwell' (beat 85ebe707)  => rejected (good)
  corrupted: The jewellery and clothes shops of rue de Castiglione and George Orwell catered to the same set.
- [entity_swap] 'Empress Eugénie' (beat c9c90a74) -> 'Crillon' (beat 85ebe707)  => rejected (good)
  corrupted: It was here, serving Crillon and the other ladies of the Napoleonic court, that French haute couture was born in the second half of the 19th century — pioneered by Charles Worth, the Empress's English couturier.
- [entity_swap] 'French Revolution' (beat c3d4a78a) -> 'Place Vendôme' (beat c9c90a74)  => rejected (good)
  corrupted: Charles Dickens stayed here in the 19th century while researching his novel about the years leading up to the Place Vendôme, A Tale of Two Cities.
- [entity_swap] 'Paris' (beat c3d4a78a) -> 'Empress's English' (beat c9c90a74)  => rejected (good)
  corrupted: It was also where the German General von Choltitz was quartered when he saved Empress's English from destruction at the end of World War II.

### FP scorecard (target: zero corrupted accepted)
| class | accepted (BAD) | rejected |
|---|---|---|
| entity_swap | 0 | 11 |
| date_shift | 0 | 0 |
| frankenfact | 0 | 6 |
| hedge_strip | 1 | 2 |
| **total** | **1** | **19** |

## Two-criteria scorecard
1. **FN usability** — of 11 genuine composed sentences: 4 shortcut, 2 entailed, 2 corrected, 3 floored (5 correction calls spent). Do the corrected sentences read well? — human judgment on the texts above.
2. **FP ceiling** — corrupted accepted: 1/20 (per-class table above). Target is ZERO; any acceptance is a judge-review item.

Actual spend: opus 24114 in / 5175 out tokens ($0.25); haiku 32 calls (~$0.02 est). No env values echoed.

## GO/NO-GO verdict
**NO-GO — ruled by the human 2026-07-15, basis: FN usability (criterion 1).**

- **Criterion 1, FN usability: FAILED (human).** The human read the assembled final text
  (01c-final-text-demo.md, Version B) and the fact that it is the FINAL output (no later
  readability pass — post-verification rewriting is structurally forbidden). Verdict: the
  floored corpus blocks / degraded flow make the shipped text not good enough. Context the
  redesign must address: 2 of the 3 floors were Haiku FALSE rejections of true multi-beat
  fusions (judge-verified against the cited bodies), and 2 of 5 correction calls were wasted
  on already-faithful sentences before flooring them.
- **Criterion 2, FP ceiling: not the failing criterion.** 19/20 corruptions rejected — all
  fabricating corruptions caught. The single acceptance (omission-of-dispute) was judge-reviewed:
  strict propositional subset, attribution intact, asserts nothing false; recorded as a
  structural boundary of per-sentence entailment + a dispute-marker pre-gate rule for any
  future design.
- (The judge's recommendation was GO-with-recorded-items; the human's NO-GO on FN usability
  overrides per the scope gate.)

**Consequence (state.json scope_1_gate): the line is STOPPED. Scopes 2–6 do not start.
Checker design re-opens at Stage 4 (04-red-team.md), with this transcript + the judge's
carry-forward items (union-support fusion tuning, corrector affirm-path, collateral-subset
floor, dispute-marker rule) as the evidence base.**
