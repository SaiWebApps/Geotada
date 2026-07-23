# Scope 1 — Le Meurice live probe transcript
_2026-07-15T18:31:29+00:00 · DRY RUN (no LLM spend)_

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

### FP battery (20 corrupted sentences, seed=20260715)
per class: entity_swap=11, date_shift=0, frankenfact=6, hedge_strip=3 — an under-filled class means this stop's corpus carries no such material (e.g. no 4-digit year / no hedge to strip)
- [entity_swap] 'Tuileries' (beat c9c90a74) -> 'French Revolution' (beat c3d4a78a)
  corrupted: When the French Revolution was still the seat of power, the ladies of the Napoleonic nobility drew an English clientele to this stretch of rue de Rivoli: the prestigious Meurice at no. 228 faced the Tuileries Gardens, the English bookshop Galignani at 224 kept the daily papers of home, and WH Smith opened its Paris branch at 248 for their convenience.
- [entity_swap] 'Empress's English' (beat c9c90a74) -> 'French Revolution' (beat c3d4a78a)
  corrupted: It was here, serving Empress Eugénie and the other ladies of the Napoleonic court, that French haute couture was born in the second half of the 19th century — pioneered by Charles Worth, the French Revolution couturier.
- [entity_swap] 'Charles Worth' (beat c9c90a74) -> 'Dickens' (beat 85ebe707)
  corrupted: It was here, serving Empress Eugénie and the other ladies of the Napoleonic court, that French haute couture was born in the second half of the 19th century — pioneered by Dickens, the Empress's English couturier.
- [entity_swap] 'French Revolution' (beat c3d4a78a) -> 'Galignani' (beat c9c90a74)
  corrupted: Charles Dickens stayed here in the 19th century while researching his novel about the years leading up to the Galignani, A Tale of Two Cities.
- [entity_swap] 'Paris' (beat c3d4a78a) -> 'Galignani' (beat c9c90a74)
  corrupted: It was also where the German General von Choltitz was quartered when he saved Galignani from destruction at the end of World War II.
- [frankenfact] subject of c9c90a74 x predicate of c3d4a78a
  corrupted: When the Tuileries stayed here in the 19th century while researching his novel about the years leading up to the French Revolution, A Tale of Two Cities.
- [frankenfact] subject of c9c90a74 x predicate of 85ebe707
  corrupted: When the Tuileries is the discreet entrance to the Meurice, where Thackeray and Dickens once stayed — the grandest of the palace hotels that colonised this quarter, and the world a penniless George Orwell served when he was worked to the bone as a plongeur, “the slave of the slave,” in Down and Out in Paris and London.
- [frankenfact] subject of c3d4a78a x predicate of c9c90a74
  corrupted: Charles Dickens was still the seat of power, the ladies of the Napoleonic nobility drew an English clientele to this stretch of rue de Rivoli: the prestigious Meurice at no. 228 faced the Tuileries Gardens, the English bookshop Galignani at 224 kept the daily papers of home, and WH Smith opened its Paris branch at 248 for their convenience.
- [frankenfact] subject of c3d4a78a x predicate of 85ebe707
  corrupted: Charles Dickens is the discreet entrance to the Meurice, where Thackeray and Dickens once stayed — the grandest of the palace hotels that colonised this quarter, and the world a penniless George Orwell served when he was worked to the bone as a plongeur, “the slave of the slave,” in Down and Out in Paris and London.
- [frankenfact] subject of 85ebe707 x predicate of c9c90a74
  corrupted: At 228 rue de Rivoli was still the seat of power, the ladies of the Napoleonic nobility drew an English clientele to this stretch of rue de Rivoli: the prestigious Meurice at no. 228 faced the Tuileries Gardens, the English bookshop Galignani at 224 kept the daily papers of home, and WH Smith opened its Paris branch at 248 for their convenience.
- [hedge_strip] removed dissenting clause ', and his biographers place it elsewhere in these streets — …' — only the local placement survives (beat 85ebe707)
  corrupted: He never named his hotel, though Paris lore has long pinned the story here.
- [hedge_strip] flattened lore hedge '— though Paris lore has long pinned the story here…' to a flat assertion (beat 85ebe707)
  corrupted: He never named his hotel, and his biographers place it elsewhere in these streets — the Lotti, just around the corner on rue de Castiglione, or the Crillon, and in fact the story happened here.
- [hedge_strip] removed the dissent AND flattened the lore hedge — the disputed story becomes flat local fact (beat 85ebe707)
  corrupted: He never named his hotel, and in fact the story happened here.
- [frankenfact] subject of 85ebe707 x predicate of c3d4a78a
  corrupted: At 228 rue de Rivoli stayed here in the 19th century while researching his novel about the years leading up to the French Revolution, A Tale of Two Cities.
- [entity_swap] 'Meurice' (beat c9c90a74) -> 'French Revolution' (beat c3d4a78a)
  corrupted: When the Tuileries was still the seat of power, the ladies of the Napoleonic nobility drew an English clientele to this stretch of rue de Rivoli: the prestigious French Revolution at no. 228 faced the Tuileries Gardens, the English bookshop Galignani at 224 kept the daily papers of home, and WH Smith opened its Paris branch at 248 for their convenience.
- [entity_swap] 'Charles Worth' (beat c9c90a74) -> 'German General von Choltitz' (beat c3d4a78a)
  corrupted: It was here, serving Empress Eugénie and the other ladies of the Napoleonic court, that French haute couture was born in the second half of the 19th century — pioneered by German General von Choltitz, the Empress's English couturier.
- [entity_swap] 'Place Vendôme' (beat c9c90a74) -> 'George Orwell' (beat 85ebe707)
  corrupted: The jewellery and clothes shops of rue de Castiglione and George Orwell catered to the same set.
- [entity_swap] 'Empress Eugénie' (beat c9c90a74) -> 'Crillon' (beat 85ebe707)
  corrupted: It was here, serving Crillon and the other ladies of the Napoleonic court, that French haute couture was born in the second half of the 19th century — pioneered by Charles Worth, the Empress's English couturier.
- [entity_swap] 'French Revolution' (beat c3d4a78a) -> 'Place Vendôme' (beat c9c90a74)
  corrupted: Charles Dickens stayed here in the 19th century while researching his novel about the years leading up to the Place Vendôme, A Tale of Two Cities.
- [entity_swap] 'Paris' (beat c3d4a78a) -> 'Empress's English' (beat c9c90a74)
  corrupted: It was also where the German General von Choltitz was quartered when he saved Empress's English from destruction at the end of World War II.

### DRY RUN — what the live run WOULD do
1. Compose the Le Meurice stop (stop_idx=1) once with claude-opus-4-8 (3 beats, ~11 beat sentences).
2. Per composed beat sentence: sentence-unit shortcut -> body-only Haiku entailment -> one correction call on NO -> re-check -> floor on second NO.
3. Probe extras: unchanged corpus sentence, c9c90a74 (key_claims=()), 85ebe707 (compound), a fused-citation sentence (synthesized if needed).
4. Run the 20-case FP battery above through entailment only; print the per-class scorecard.
5. Write this transcript to specs/2026-07-13-compose-correct-dont-reject/01b-probe-transcript.md and end with the two-criteria scorecard + verdict 'PENDING HUMAN REVIEW'.

No Anthropic client was constructed; nothing was spent. Re-run with --go (or make diag-compose-correct GO=1) to run live.
