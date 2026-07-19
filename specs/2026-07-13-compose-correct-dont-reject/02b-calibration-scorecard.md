# 02b — Scope 2 calibration scorecard (gate FN/FP, full production order)

## 0. GO — RATIFIED by the human 2026-07-17 (chat: "ratified, go scope 3")

The human ruled the direction (2026-07-16: "we are not making up facts, but the
composer gets room to sound natural") and then explicitly RATIFIED in chat
(2026-07-17) both the amended-bar wording below AND the 4-of-5 01g colour-gloss
reclassification. Scope 3 is released. The as-written pre-amendment verdict
(NO-GO: 25/29 verbatim, 2/3 known FNs) is preserved for the record; the deploy
hold to main stands until Scope 3 lands.

**Blast radius (judge-corrected):** the softened `_ENTAILMENT_PROMPT` lives in
`HaikuFaithfulnessChecker`, which is ALREADY WIRED into the live trips routes
(src/api/routes/trips.py via get_faithfulness_checker). This change alters the
behavior of a live, user-facing fabrication gate — it is inert to users only via
branch isolation + the deploy hold, not because the wiring is absent.

(Run-5 timestamp 2026-07-17 03:12 UTC = local evening 2026-07-16; UTC offset,
not a future-dated artifact.)

**The ruling** (human, at this gate, after the run-1..4 NO-GO evidence): *"we are not
making up facts, but the composer gets room to sound natural."* Implemented as: the
entailment layer rejects only CHECKABLE-FACT violations (new entity/number/date/era/
specific event, changed or inverted stated facts, hedge/dispute-flattening,
fact-presupposing questions); interpretive colour and loose relational glosses are
composer licence, governed by the 3b pass prompt + AC-9. Recorded as an amendment in
02-spec §Never-fabricate.

**The amended GO bar** (follows from the ruling; the as-written bar predates it):
ZERO fabricating acceptances AND every gold item SHIPS OR ROUTES TO CORRECTION —
never floored, never lost. The as-written bar ("01f ships whole" verbatim) demanded
zero-correction narration, which the ruling supersedes: correction IS the designed
path of correct-don't-reject.

**Run 5 (softened prompt, haiku + reasoning) against the PROPOSED amended bar: PASS.**

| iter | checker config | 01f ships verbatim | known FNs | fabricating acceptances |
|---|---|---|---|---|
| 1 | haiku, 1-token, strict | 19/29 (partial) | 1/3 | not measured |
| 2 | haiku, 1-token, loosened restatement | 26/29 | 2/3 | 2 |
| 3 | haiku, reasoning, strict | 19/29 | 3/3 | 2 |
| 4 | sonnet-5, reasoning, strict | 24/29 | 2/3 | 2 |
| **5** | **haiku, reasoning, SOFTENED (the ruling)** | **25/29** | **2/3** | **0** |

- **FP side (the dangerous side): CLEAN.** 0/57-class acceptances. Union phantoms,
  blind-spot probes (sentence-initial entity, word-form number), fluent frankenfacts,
  entity swaps, date/century shifts, hedge-FLATTENING strips, question smuggles, the
  invented-price causal — all rejected, most at entailment (the layer under test).
- **Ruling implemented and verified:** all 4 colour-glosses SHIP (color_gloss 4/4);
  the pure dissent-omission control SHIPS (omission-of-dispute is the floor/seated-beat
  machinery's job, per the Scope-1 judge precedent).
- **The 5 correction-path items** (ship-after-correction in production; none floored,
  none lost): 01f_04 ("helped make this stretch fashionable" — unstated street-level
  claim), 01f_12 (dates THACKERAY's stay — bodies date only Dickens's), 01f_14
  ("the hotel is also linked to… Orwell" — the checker treats the link as flattening
  the placement dispute; defensible), 01f_15 ("long before he became famous"),
  known_fn_01b_s10 (the entrance/High-Command fusion — borderline both ways across
  runs). Scope 3's corrector rewrites these constrained to bodies; the facts ship.
- **Manager note:** this GO implements the human's softening ruling; the as-written
  bar would read NO-GO (25/29 verbatim, 2/3 known FNs). Veto point: before Scope 3's
  first commit merges. Trim ladder note: the makepeace trim demonstrated the layered
  fail-closed design — Opus trimmed only the pre-gate-visible token, and the re-gate
  entailment caught the remaining "William" (sentence-initial blind spot) and refused
  the trim. The layers back each other up.

---

**Run:** 2026-07-17 03:12 UTC · `make calibrate-gate GO=1` · gate order: pre-gate → sentence-unit shortcut → calibrated entailment (**claude-haiku-4-5-20251001**) → routing (`route_flagged_sentence` / `is_valid_trim`; trims executed by claude-opus-4-8).
**Actual spend:** 74 Haiku calls, 2 Opus trim calls ≈ $0.07.

**Support note:** 01f/known-FN/FP items are scored against the Le Meurice stop-UNION bodies (the effective post-`_populate_also_cites`/Phase-2 support production converges to); Scope-1-class and NYC mutation items keep their per-case declared citations. Word-form ordinal dates are canonicalized on BOTH sides (verify_gate-local), so no FN below is a word-form-date artifact (04b BL-V7 control).

## VERDICT: NO-GO

- Known FNs recovered: 2/3 (known_fn_01b_s10)
- 01f ships whole: 25/29 sentences (01f_04, 01f_12, 01f_14, 01f_15)
- Fabricating acceptances: 0 (zero)

## FN battery (must ship)

| item | class | outcome | trace |
|---|---|---|---|
| 01f_01 — Here, at the corner of rue de Castiglione and rue de Rivoli, stands the Hotel Le Meurice. | 01f_golden | SHIPS | pre-gate: pass · shortcut: miss · entailment: YES -> SHIPS |
| 01f_02 — Its discreet entrance is at 228 rue de Rivoli. | 01f_golden | SHIPS | pre-gate: pass · shortcut: miss · entailment: YES -> SHIPS |
| 01f_03 — To understand how a hotel like this came to belong here, go back to the neighbourhood a... | 01f_golden | SHIPS | pre-gate: pass · shortcut: miss · entailment: YES -> SHIPS |
| 01f_04 — The ladies of the Napoleonic nobility helped make this stretch of rue de Rivoli fashion... | 01f_golden | rejected/floored | pre-gate: pass · shortcut: miss · entailment: NO · route: correctable · -> correctable (rewrite path = Scope 3; battery stops here) |
| 01f_05 — At number 224, the English bookshop Galignani kept the daily newspapers from home. | 01f_golden | SHIPS | pre-gate: pass · shortcut: miss · entailment: YES -> SHIPS |
| 01f_06 — At number 248, W. H. Smith opened its Paris branch for the same clientele. | 01f_golden | SHIPS | pre-gate: pass · shortcut: miss · entailment: YES -> SHIPS |
| 01f_07 — Nearby, the jewellery and clothing shops of rue de Castiglione and Place Vendôme served... | 01f_golden | SHIPS | pre-gate: pass · shortcut: miss · entailment: YES -> SHIPS |
| 01f_08 — It was here, supplying Empress Eugénie and the other ladies of the Napoleonic court, th... | 01f_golden | SHIPS | pre-gate: pass · shortcut: miss · entailment: YES -> SHIPS |
| 01f_09 — One of its pioneers was Charles Worth, the Empress's English couturier. | 01f_golden | SHIPS | pre-gate: pass · shortcut: miss · entailment: YES -> SHIPS |
| 01f_10 — A century later, its centre of gravity would drift westward to the 8th arrondissement. | 01f_golden | SHIPS | pre-gate: pass · shortcut: miss · entailment: YES -> SHIPS |
| 01f_11 — Le Meurice was one of the grand palace hotels that came to dominate this quarter. | 01f_golden | SHIPS | pre-gate: pass · shortcut: miss · entailment: YES -> SHIPS |
| 01f_12 — Thackeray and Charles Dickens both stayed here during the nineteenth century. | 01f_golden | rejected/floored | pre-gate: pass · shortcut: miss · entailment: NO · route: correctable · -> correctable (rewrite path = Scope 3; battery stops here) |
| 01f_13 — Dickens stayed while researching A Tale of Two Cities, his novel about the years leadin... | 01f_golden | SHIPS | pre-gate: pass · shortcut: miss · entailment: YES -> SHIPS |
| 01f_14 — The hotel is also linked to another writer: George Orwell. | 01f_golden | rejected/floored | pre-gate: pass · shortcut: miss · entailment: NO · route: correctable · -> correctable (rewrite path = Scope 3; battery stops here) |
| 01f_15 — Long before he became famous, a penniless Orwell worked in a grand Paris hotel as a plo... | 01f_golden | rejected/floored | pre-gate: pass · shortcut: miss · entailment: NO · route: correctable · -> correctable (rewrite path = Scope 3; battery stops here) |
| 01f_16 — In Down and Out in Paris and London, he described the plongeur as “the slave of the sla... | 01f_golden | SHIPS | pre-gate: pass · shortcut: miss · entailment: YES -> SHIPS |
| 01f_17 — But did Orwell really work here? | gold_question | SHIPS | pre-gate: pass · shortcut: miss · entailment: YES -> SHIPS |
| 01f_18 — He never named the hotel. | 01f_golden | SHIPS | pre-gate: pass · shortcut: miss · entailment: YES -> SHIPS |
| 01f_19 — His biographers have placed it elsewhere in these streets—at the Lotti, just around the... | 01f_golden | SHIPS | pre-gate: pass · shortcut: miss · entailment: YES -> SHIPS |
| 01f_20 — Paris lore, however, has long pinned the story on Le Meurice. | 01f_golden | SHIPS | pre-gate: pass · shortcut: miss · entailment: YES -> SHIPS |
| 01f_21 — What Orwell described could certainly fit the great hotels of this entire quarter. | 01f_golden | SHIPS | pre-gate: pass · shortcut: miss · entailment: YES -> SHIPS |
| 01f_22 — From the outside, there was “a vast, grandiose place with a classical façade,” and, at ... | 01f_golden | SHIPS | pre-gate: pass · shortcut: miss · entailment: YES -> SHIPS |
| 01f_23 — Behind that grand façade, the kitchens were a kingdom of hell: a “stifling low-ceilinge... | 01f_golden | SHIPS | pre-gate: pass · shortcut: miss · entailment: YES -> SHIPS |
| 01f_24 — Only a double door separated the squalid scullery from the dining room. | 01f_golden | SHIPS | pre-gate: pass · shortcut: miss · entailment: YES -> SHIPS |
| 01f_25 — On one side sat the customers “in all their splendour,” with spotless tablecloths, bowl... | 01f_golden | SHIPS | pre-gate: pass · shortcut: miss · entailment: YES -> SHIPS |
| 01f_26 — And on the other side, only a few feet away, Orwell and the other workers stood, as he ... | 01f_golden | SHIPS | pre-gate: pass · shortcut: miss · entailment: YES -> SHIPS |
| 01f_27 — A generation later, the German High Command of the Paris garrison took up residence in ... | 01f_golden | SHIPS | pre-gate: pass · shortcut: miss · entailment: YES -> SHIPS |
| 01f_28 — General von Choltitz was also quartered here when he saved Paris from destruction at th... | 01f_golden | SHIPS | pre-gate: pass · shortcut: miss · entailment: YES -> SHIPS |
| 01f_29 — One wonders whether any of them had read Down and Out. | 01f_golden | SHIPS | pre-gate: pass · shortcut: HIT -> SHIPS (zero LLM) |
| known_fn_01b_s2 — The prestigious Meurice itself stands on the corner of rue de Castiglione and rue de Ri... | known_fn | SHIPS | pre-gate: pass · shortcut: miss · entailment: YES -> SHIPS |
| known_fn_01b_s10 — A generation later, the German High Command of the Paris garrison took up residence at ... | known_fn | rejected/floored | pre-gate: pass · shortcut: miss · entailment: NO · route: correctable · -> correctable (rewrite path = Scope 3; battery stops here) |
| known_fn_01d_s8 — It was here, supplying Empress Eugénie and the other ladies of the Napoleonic court, th... | known_fn | SHIPS | pre-gate: pass · shortcut: miss · entailment: YES -> SHIPS |
| trim_william_makepeace — William Makepeace Thackeray and Charles Dickens both stayed here during the nineteenth ... | trim_class | rejected/floored | pre-gate: FLAGGED ('proper_noun:makepeace',) · route: correctable · opus trim: 'William Thackeray and Charles Dickens both stayed here during the nineteenth century.' · is_valid_trim: accepted -> re-gate · re-gate entailment: NO -> not shipped |
| trim_tuileries_palace — To understand how a hotel like this came to belong here, go back to the neighbourhood a... | trim_class | SHIPS | pre-gate: pass · shortcut: miss · entailment: YES -> SHIPS |
| trim_parisian_fashion — A century later, the centre of Parisian fashion would drift westward to the 8th arrondi... | trim_class | SHIPS | pre-gate: FLAGGED ('proper_noun:parisian',) · route: correctable · opus trim: 'A century later, the centre of fashion would drift westward to the 8th arrondissement.' · is_valid_trim: accepted -> re-gate · re-gate entailment: YES -> SHIPS-AFTER-TRIM |
| color_gloss_1 — The street bent itself to make the English feel at home. | color_gloss | SHIPS | pre-gate: pass · shortcut: miss · entailment: YES -> SHIPS |
| color_gloss_2 — Those same ladies wanted more than newspapers. | color_gloss | SHIPS | pre-gate: pass · shortcut: miss · entailment: YES -> SHIPS |
| color_gloss_3 — The Meurice drew the writers too. | color_gloss | SHIPS | pre-gate: pass · shortcut: miss · entailment: YES -> SHIPS |
| color_gloss_4 — But the most famous story attached to this place comes from the other side of the doubl... | color_gloss | SHIPS | pre-gate: pass · shortcut: miss · entailment: YES -> SHIPS |
| nyc_verbatim — Across Battle Avenue from the theater-fire monument stand the graves of Henry Aaron Bur... | heldout_verbatim | SHIPS | pre-gate: pass · shortcut: HIT -> SHIPS (zero LLM) |
| nyc_two_unit_run — Across Battle Avenue from the theater-fire monument stand the graves of Henry Aaron Bur... | heldout_verbatim | SHIPS | pre-gate: pass · shortcut: HIT -> SHIPS (zero LLM) |

### FN per-class summary

- **01f_golden**: 24/28 shipped
- **color_gloss**: 4/4 shipped
- **gold_question**: 1/1 shipped
- **heldout_verbatim**: 2/2 shipped
- **known_fn**: 2/3 shipped
- **trim_class**: 2/3 shipped

## FP battery (must be rejected — zero acceptances)

| item | class | outcome | trace |
|---|---|---|---|
| fluent_ff_1 — Charles Worth stayed at the Meurice while researching A Tale of Two Cities. | fluent_frankenfact | rejected/floored | pre-gate: pass · shortcut: miss · entailment: NO · route: correctable · -> correctable (rewrite path = Scope 3; battery stops here) |
| fluent_ff_2 — Galignani opened its Paris branch at 248 for the ladies of the Napoleonic court. | fluent_frankenfact | rejected/floored | pre-gate: pass · shortcut: miss · entailment: NO · route: correctable · -> correctable (rewrite path = Scope 3; battery stops here) |
| fluent_ff_3 — It was von Choltitz who pinned the Orwell story on Le Meurice. | fluent_frankenfact | rejected/floored | pre-gate: pass · shortcut: miss · entailment: NO · route: correctable · -> correctable (rewrite path = Scope 3; battery stops here) |
| fluent_ff_4 — Empress Eugénie stayed at the Meurice while Charles Worth supplied the court. | fluent_frankenfact | rejected/floored | pre-gate: pass · shortcut: miss · entailment: NO · route: correctable · -> correctable (rewrite path = Scope 3; battery stops here) |
| fluent_ff_5 — Dickens researched A Tale of Two Cities in the kitchens of the Meurice. | fluent_frankenfact | rejected/floored | pre-gate: pass · shortcut: miss · entailment: NO · route: correctable · -> correctable (rewrite path = Scope 3; battery stops here) |
| causal_1 — The ladies of the Napoleonic nobility drew an English clientele because the hotels lowe... | causal_invention | rejected/floored | pre-gate: pass · shortcut: miss · entailment: NO · route: correctable · -> correctable (rewrite path = Scope 3; battery stops here) |
| q_smuggle_1 — Why did Orwell choose the Meurice for his years as a plongeur? | question_smuggle | rejected/floored | pre-gate: pass · shortcut: miss · entailment: NO · route: correctable · -> correctable (rewrite path = Scope 3; battery stops here) |
| q_smuggle_2 — When did Dickens finish A Tale of Two Cities in his room upstairs? | question_smuggle | rejected/floored | pre-gate: pass · shortcut: miss · entailment: NO · route: correctable · -> correctable (rewrite path = Scope 3; battery stops here) |
| q_smuggle_3 — How long did Orwell work in these very kitchens? | question_smuggle | rejected/floored | pre-gate: pass · shortcut: miss · entailment: NO · route: correctable · -> correctable (rewrite path = Scope 3; battery stops here) |
| glue_mislabel_1 — And with that, we leave the hotel where Orwell definitely worked as a plongeur. | glue_mislabel | rejected/floored | glue: salient tokens -> PROMOTED to checked lane (union support) · pre-gate: pass · shortcut: miss · entailment: NO · route: correctable · -> correctable (rewrite path = Scope 3; battery stops here) |
| glue_mislabel_2 — Onward now, past number 248, where Galignani kept the daily papers. | glue_mislabel | rejected/floored | glue: salient tokens -> PROMOTED to checked lane (union support) · pre-gate: pass · shortcut: miss · entailment: NO · route: correctable · -> correctable (rewrite path = Scope 3; battery stops here) |
| union_phantom_1 — Charles Worth designed gowns for the German High Command at the Meurice. | union_phantom | rejected/floored | pre-gate: pass · shortcut: miss · entailment: NO · route: correctable · -> correctable (rewrite path = Scope 3; battery stops here) |
| union_phantom_2 — The Tuileries Palace kept the daily newspapers for the English clientele. | union_phantom | rejected/floored | pre-gate: pass · shortcut: miss · entailment: NO · route: correctable · -> correctable (rewrite path = Scope 3; battery stops here) |
| union_phantom_3 — Galignani was quartered at the Meurice when he saved Paris from destruction. | union_phantom | rejected/floored | pre-gate: pass · shortcut: miss · entailment: NO · route: correctable · -> correctable (rewrite path = Scope 3; battery stops here) |
| blind_spot_1 — The English bookshop Galignani kept the daily papers at number two hundred and forty-two. | pregate_blind_spot | rejected/floored | pre-gate: pass · shortcut: miss · entailment: NO · route: correctable · -> correctable (rewrite path = Scope 3; battery stops here) |
| blind_spot_2 — Napoleon and Dickens both stayed here during the nineteenth century. | pregate_blind_spot | rejected/floored | pre-gate: pass · shortcut: miss · entailment: NO · route: correctable · -> correctable (rewrite path = Scope 3; battery stops here) |
| blind_spot_3 — Balzac stood at this corner and watched the Empress pass. | pregate_blind_spot | rejected/floored | pre-gate: pass · shortcut: miss · entailment: NO · route: correctable · -> correctable (rewrite path = Scope 3; battery stops here) |
| century_shift_1 — It was here, supplying Empress Eugénie and the other ladies of the Napoleonic court, th... | date_shift | rejected/floored | pre-gate: FLAGGED ('century:c17ad',) · route: correctable · -> correctable (rewrite path = Scope 3; battery stops here) |
| century_shift_2 — Thackeray and Charles Dickens both stayed here during the sixteenth century. | date_shift | rejected/floored | pre-gate: FLAGGED ('century:c16ad',) · route: correctable · -> correctable (rewrite path = Scope 3; battery stops here) |
| s1_entity_swap_0 — When the French Revolution was still the seat of power, the ladies of the Napoleonic no... | entity_swap | rejected/floored | pre-gate: FLAGGED ('proper_noun:revolution',) · route: under_cited · -> floor (fact-preserving; never correction-stripped) |
| s1_entity_swap_1 — It was here, serving Empress Eugénie and the other ladies of the Napoleonic court, that... | entity_swap | rejected/floored | pre-gate: FLAGGED ('proper_noun:revolution',) · route: under_cited · -> floor (fact-preserving; never correction-stripped) |
| s1_entity_swap_2 — It was here, serving Empress Eugénie and the other ladies of the Napoleonic court, that... | entity_swap | rejected/floored | pre-gate: FLAGGED ('proper_noun:dickens',) · route: under_cited · -> floor (fact-preserving; never correction-stripped) |
| s1_entity_swap_3 — Charles Dickens stayed here in the 19th century while researching his novel about the y... | entity_swap | rejected/floored | pre-gate: FLAGGED ('proper_noun:galignani',) · route: under_cited · -> floor (fact-preserving; never correction-stripped) |
| s1_entity_swap_4 — It was also where the German General von Choltitz was quartered when he saved Galignani... | entity_swap | rejected/floored | pre-gate: FLAGGED ('proper_noun:galignani',) · route: under_cited · -> floor (fact-preserving; never correction-stripped) |
| s1_frankenfact_5 — When the Tuileries stayed here in the 19th century while researching his novel about th... | frankenfact | rejected/floored | pre-gate: pass · shortcut: miss · entailment: NO · route: correctable · -> correctable (rewrite path = Scope 3; battery stops here) |
| s1_frankenfact_6 — When the Tuileries is the discreet entrance to the Meurice, where Thackeray and Dickens... | frankenfact | rejected/floored | pre-gate: pass · shortcut: miss · entailment: NO · route: correctable · -> correctable (rewrite path = Scope 3; battery stops here) |
| s1_frankenfact_7 — Charles Dickens was still the seat of power, the ladies of the Napoleonic nobility drew... | frankenfact | rejected/floored | pre-gate: pass · shortcut: miss · entailment: NO · route: correctable · -> correctable (rewrite path = Scope 3; battery stops here) |
| s1_frankenfact_8 — Charles Dickens is the discreet entrance to the Meurice, where Thackeray and Dickens on... | frankenfact | rejected/floored | pre-gate: pass · shortcut: miss · entailment: NO · route: correctable · -> correctable (rewrite path = Scope 3; battery stops here) |
| s1_frankenfact_9 — At 228 rue de Rivoli was still the seat of power, the ladies of the Napoleonic nobility... | frankenfact | rejected/floored | pre-gate: pass · shortcut: miss · entailment: NO · route: correctable · -> correctable (rewrite path = Scope 3; battery stops here) |
| s1_hedge_strip_11 — He never named his hotel, and his biographers place it elsewhere in these streets — the... | hedge_strip | rejected/floored | pre-gate: pass · shortcut: miss · entailment: NO · route: correctable · -> correctable (rewrite path = Scope 3; battery stops here) |
| s1_hedge_strip_12 — He never named his hotel, and in fact the story happened here. | hedge_strip | rejected/floored | pre-gate: pass · shortcut: miss · entailment: NO · route: correctable · -> correctable (rewrite path = Scope 3; battery stops here) |
| s1_frankenfact_13 — At 228 rue de Rivoli stayed here in the 19th century while researching his novel about ... | frankenfact | rejected/floored | pre-gate: pass · shortcut: miss · entailment: NO · route: correctable · -> correctable (rewrite path = Scope 3; battery stops here) |
| s1_entity_swap_14 — When the Tuileries was still the seat of power, the ladies of the Napoleonic nobility d... | entity_swap | rejected/floored | pre-gate: FLAGGED ('proper_noun:revolution',) · route: under_cited · -> floor (fact-preserving; never correction-stripped) |
| s1_entity_swap_15 — It was here, serving Empress Eugénie and the other ladies of the Napoleonic court, that... | entity_swap | rejected/floored | pre-gate: FLAGGED ('proper_noun:choltitz', 'proper_noun:general', 'proper_noun:german') · route: under_cited · -> floor (fact-preserving; never correction-stripped) |
| s1_entity_swap_16 — The jewellery and clothes shops of rue de Castiglione and George Orwell catered to the ... | entity_swap | rejected/floored | pre-gate: FLAGGED ('proper_noun:george', 'proper_noun:orwell') · route: under_cited · -> floor (fact-preserving; never correction-stripped) |
| s1_entity_swap_17 — It was here, serving Crillon and the other ladies of the Napoleonic court, that French ... | entity_swap | rejected/floored | pre-gate: FLAGGED ('proper_noun:crillon',) · route: under_cited · -> floor (fact-preserving; never correction-stripped) |
| s1_entity_swap_18 — Charles Dickens stayed here in the 19th century while researching his novel about the y... | entity_swap | rejected/floored | pre-gate: FLAGGED ('proper_noun:place', 'proper_noun:vend') · route: under_cited · -> floor (fact-preserving; never correction-stripped) |
| s1_entity_swap_19 — It was also where the German General von Choltitz was quartered when he saved Empress's... | entity_swap | rejected/floored | pre-gate: FLAGGED ('proper_noun:empress', 'proper_noun:english') · route: under_cited · -> floor (fact-preserving; never correction-stripped) |
| nyc_entity_swap_2 — Across Battle Avenue from the theater-fire monument stand the graves of American and hi... | heldout_entity_swap | rejected/floored | pre-gate: FLAGGED ('proper_noun:american',) · route: under_cited · -> floor (fact-preserving; never correction-stripped) |
| nyc_entity_swap_3 — Henry Lincoln Memorial was the great-nephew of the infamous vice president Aaron Burr a... | heldout_entity_swap | rejected/floored | pre-gate: FLAGGED ('proper_noun:lincoln', 'proper_noun:memorial') · route: under_cited · -> floor (fact-preserving; never correction-stripped) |
| nyc_entity_swap_4 — After working as a bookkeeper for milliner American, Burr opened his own store across t... | heldout_entity_swap | rejected/floored | pre-gate: FLAGGED ('proper_noun:american',) · route: under_cited · -> floor (fact-preserving; never correction-stripped) |
| nyc_entity_swap_5 — Burr was also a charter member of the Daniel Chester French and a director of the Mecha... | heldout_entity_swap | rejected/floored | pre-gate: FLAGGED ('proper_noun:chester', 'proper_noun:daniel', 'proper_noun:french') · route: under_cited · -> floor (fact-preserving; never correction-stripped) |
| nyc_entity_swap_6 — Across Battle Avenue from the theater-fire monument stand the graves of Burnham and his... | heldout_entity_swap | rejected/floored | pre-gate: FLAGGED ('proper_noun:burnham',) · route: under_cited · -> floor (fact-preserving; never correction-stripped) |
| nyc_date_shift_7 — After working as a bookkeeper for milliner Elisha Bloomer, Burr opened his own store ac... | heldout_date_shift | rejected/floored | pre-gate: FLAGGED ('year:1838',) · route: correctable · -> correctable (rewrite path = Scope 3; battery stops here) |
| nyc_date_shift_8 — After many failures he succeeded, patented it, and dramatically cut the cost of hat mak... | heldout_date_shift | rejected/floored | pre-gate: FLAGGED ('year:1849',) · route: correctable · -> correctable (rewrite path = Scope 3; battery stops here) |
| nyc_date_shift_9 — Frankie, who died in 1891, was the son of Rear Admiral Aaron Ward; father and son lie b... | heldout_date_shift | rejected/floored | pre-gate: FLAGGED ('year:1891',) · route: correctable · -> correctable (rewrite path = Scope 3; battery stops here) |
| nyc_date_shift_10 — Perhaps the New York Times said it best in 1862: "It is the ambition of the New Yorker ... | heldout_date_shift | rejected/floored | pre-gate: FLAGGED ('year:1862',) · route: correctable · -> correctable (rewrite path = Scope 3; battery stops here) |
| nyc_date_shift_11 — The internationally renowned company was founded by Charles Tiffany and partner John B.... | heldout_date_shift | rejected/floored | pre-gate: FLAGGED ('year:1856',) · route: under_cited · -> floor (fact-preserving; never correction-stripped) |
| nyc_frankenfact_12 — Henry Aaron Burr was carved by the great American sculptor Daniel Chester French, best ... | heldout_frankenfact | rejected/floored | pre-gate: pass · shortcut: miss · entailment: NO · route: correctable · -> correctable (rewrite path = Scope 3; battery stops here) |
| nyc_frankenfact_13 — Henry Aaron Burr is a classic late nineteenth-century family plot, with a central monum... | heldout_frankenfact | rejected/floored | pre-gate: pass · shortcut: miss · entailment: NO · route: correctable · -> correctable (rewrite path = Scope 3; battery stops here) |
| nyc_frankenfact_14 — Henry Aaron Burr became convinced he would be resurrected as an animal and could be abu... | heldout_frankenfact | rejected/floored | pre-gate: pass · shortcut: miss · entailment: NO · route: correctable · -> correctable (rewrite path = Scope 3; battery stops here) |
| nyc_frankenfact_15 — Henry Aaron Burr is the ambition of the New Yorker to live on Fifth Avenue, to take his... | heldout_frankenfact | rejected/floored | pre-gate: pass · shortcut: miss · entailment: NO · route: correctable · -> correctable (rewrite path = Scope 3; battery stops here) |
| nyc_frankenfact_16 — Henry Aaron Burr is patriarch Charles Lewis Tiffany, surrounded by family including his... | heldout_frankenfact | rejected/floored | pre-gate: pass · shortcut: miss · entailment: NO · route: correctable · -> correctable (rewrite path = Scope 3; battery stops here) |
| nyc_frankenfact_17 — Opposite Clinton's tomb, a small white marble statue of a young man marks the grave of ... | heldout_frankenfact | rejected/floored | pre-gate: pass · shortcut: miss · entailment: NO · route: correctable · -> correctable (rewrite path = Scope 3; battery stops here) |
| nyc_frankenfact_18 — Opposite Clinton's tomb, a small white marble statue of a young man marks the grave of ... | heldout_frankenfact | rejected/floored | pre-gate: pass · shortcut: miss · entailment: NO · route: correctable · -> correctable (rewrite path = Scope 3; battery stops here) |
| nyc_frankenfact_19 — Opposite Clinton's tomb, a small white marble statue of a young man marks the grave of ... | heldout_frankenfact | rejected/floored | pre-gate: pass · shortcut: miss · entailment: NO · route: correctable · -> correctable (rewrite path = Scope 3; battery stops here) |
| nyc_frankenfact_20 — Opposite Clinton's tomb, a small white marble statue of a young man marks the grave of ... | heldout_frankenfact | rejected/floored | pre-gate: pass · shortcut: miss · entailment: NO · route: correctable · -> correctable (rewrite path = Scope 3; battery stops here) |
| nyc_frankenfact_21 — Opposite Clinton's tomb, a small white marble statue of a young man marks the grave of ... | heldout_frankenfact | rejected/floored | pre-gate: pass · shortcut: miss · entailment: NO · route: correctable · -> correctable (rewrite path = Scope 3; battery stops here) |

### FP per-class summary (with rejection stage — a class rejected wholly by the pre-gate tests nothing about entailment)

- **causal_invention**: 1 items, 0 fabricating acceptances (rejected at: pre-gate 0, entailment 1)
- **date_shift**: 2 items, 0 fabricating acceptances (rejected at: pre-gate 2, entailment 0)
- **entity_swap**: 11 items, 0 fabricating acceptances (rejected at: pre-gate 11, entailment 0)
- **fluent_frankenfact**: 5 items, 0 fabricating acceptances (rejected at: pre-gate 0, entailment 5)
- **frankenfact**: 6 items, 0 fabricating acceptances (rejected at: pre-gate 0, entailment 6)
- **glue_mislabel**: 2 items, 0 fabricating acceptances (rejected at: pre-gate 0, entailment 2)
- **hedge_strip**: 2 items, 0 fabricating acceptances (rejected at: pre-gate 0, entailment 2)
- **heldout_date_shift**: 5 items, 0 fabricating acceptances (rejected at: pre-gate 5, entailment 0)
- **heldout_entity_swap**: 5 items, 0 fabricating acceptances (rejected at: pre-gate 5, entailment 0)
- **heldout_frankenfact**: 10 items, 0 fabricating acceptances (rejected at: pre-gate 0, entailment 10)
- **pregate_blind_spot**: 3 items, 0 fabricating acceptances (rejected at: pre-gate 0, entailment 3)
- **question_smuggle**: 3 items, 0 fabricating acceptances (rejected at: pre-gate 0, entailment 3)
- **union_phantom**: 3 items, 0 fabricating acceptances (rejected at: pre-gate 0, entailment 3)

## Controls

| item | class | outcome | trace |
|---|---|---|---|
| glue_control — Take a moment here before we walk on. | glue_control | SHIPS | glue: token-free -> validation lane (no entailment) |
| s1_hedge_strip_10 — He never named his hotel, though Paris lore has long pinned the story here. | omission_control | SHIPS | pre-gate: pass · shortcut: miss · entailment: YES -> SHIPS |

### Recorded notes

- RULING 2026-07-16 (human): the gate is SOFTENED to checkable-fact violations only — new entities/numbers/dates/specific events, changed facts, hedge-flattening, fact-presupposing questions. Interpretive colour and loose relational glosses are composer licence; craft control moves to the 3b pass prompt + AC-9. Accordingly: the four 01g colour-findings are expected-SHIPS items (color_gloss class), the invented-price causal stays a must-reject, and pure dissent-removal hedge-strips are omission-of-dispute CONTROLS (Scope-1 judge precedent) — lore-flattening strips remain FPs.
- date_shift is POPULATED via century-form shifts on Le Meurice (its bodies carry no 4-digit year) and 4-digit shifts on the NYC held-out stop. Entity/date mutation classes are largely rejected AT THE PRE-GATE (see stage counts) — entailment calibration evidence is carried by the fluent/causal/question/glue/phantom classes.
- Union-support caveat (2026-07-16 battery skeptic): the GO verdict is calibrated at stop-union support width. Scope 3's BL-V2 restriction of `_populate_also_cites` narrows some sentences' effective support, which STRENGTHENS the pre-gate for them; the union_phantom FP class measures the residual entailment-only exposure. Scope 3's own fixture battery (AC-2) re-verifies these classes at wired-loop granularity.
- is_valid_trim / route_flagged_sentence carry NO weight in this GO verdict (trim items are diagnostic) — their behavior is pinned by the Part-B unit tests, incl. the reorder-rejection and ownership-routing pins added after the skeptic pass.
