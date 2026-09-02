# 01g — Narrative-pass live demo + human editorial review (pass-prompt calibration evidence)

**Date:** 2026-07-15 · **What:** one UNCHECKED Opus call ran the Scope-3b transform on
Version B (`01c`) with the three Le Meurice beat bodies as phrasing-only reference —
the human asked to SEE a good narrative before approving the Stage-5 plan. Cost: 1 call,
2,408 in / 927 out tokens. Script: session scratchpad `demo_narrative_pass.py` (throwaway;
the real prompt lands in Scope 3b).

**Human verdict:** "much stronger than the earlier version… sounds like a tour guide
speaking at a physical location… main weakness is that some of the improved prose becomes
more confident than the underlying facts support; a few transitions create causal
relationships that were not established in the source."

This file preserves (A) the demo output, (B) the human's findings mapped to the mechanism
that owns each, (C) the pass-prompt rules the review adds. It is calibration input for the
Scope-3b prompt and the AC-9 acceptance checklist.

---

## A. The demo output (unchecked — never ship this text)

You're standing on the corner of rue de Castiglione and rue de Rivoli, and in front of you is the Hotel Le Meurice. Its discreet entrance sits at 228 rue de Rivoli — the grandest of the palace hotels that colonised this quarter.

To understand why it landed here, you have to go back to when the Tuileries was still the seat of power. The ladies of the Napoleonic nobility drew an English clientele to this very stretch of rue de Rivoli, and the street bent itself to make them feel at home. The English bookshop Galignani, at 224, kept the daily papers of home, and WH Smith opened its Paris branch at 248 for their convenience.

Those same ladies wanted more than newspapers. The jewellery and clothes shops of rue de Castiglione and Place Vendôme catered to the same set, and it was here — serving Empress Eugénie and the other ladies of the Napoleonic court — that French haute couture was born in the second half of the 19th century. Its pioneer was Charles Worth, the Empress's English couturier. A century later its centre of gravity drifted westward to the 8th arrondissement.

The Meurice drew the writers too. Both Thackeray and Dickens stayed here in the 19th century — Dickens while researching *A Tale of Two Cities*, his novel about the years leading up to the French Revolution.

But the most famous story attached to this place comes from the other side of the double doors. In *Down and Out in Paris and London*, a penniless George Orwell served this world, worked to the bone as a plongeur — "the slave of the slave." Whether he really worked here is another matter. He never named his hotel, and his biographers place it elsewhere in these streets — the Lotti, just around the corner on rue de Castiglione, or the Crillon — though Paris lore has long pinned the story right here.

What he described fits the whole quarter. He called it "a vast, grandiose place with a classical façade, and at one side a little, dark doorway like a rat hole, which was the service entrance." Through that door were the kitchens, the kingdom of hell — a "stifling low-ceilinged inferno of a cellar, red-lit from the fires, and deafening with oaths and clanging of pots and pans." Only a double door separated the squalid scullery from the dining room. "There sat the customers in all their splendour and spotless table-cloths, bowls of flowers, mirrors and gilt cornices and painted cherubims; and here, just a few feet away we in our disgusting filth."

A generation later, the splendour on the customers' side had new occupants. The German High Command of the Paris garrison took up residence at the lavish Meurice, and it was here that General von Choltitz was quartered when he saved Paris from destruction at the end of World War II. One wonders whether any of them had ever read *Down and Out*.

---

## B. The human's findings → the mechanism that owns each

The demo deliberately SKIPPED the re-gate — so the review is a live test of what the
machinery must catch. Three buckets:

### Bucket 1 — invented/strengthened causal relations → the CALIBRATED GATE (Scopes 2 + 3b)
The exact class the relation line targets ("combining is YES only when the joining
relation is itself stated; a new relation between source facts is ADDED content ⇒ NO"):

| Finding | Line | Gate behavior |
|---|---|---|
| #2 | "the ladies … DREW an English clientele" (causal claim; source only co-locates them) | beat-cited → entailment NO → correction/trim |
| #2 | "the street bent itself to make them feel at home" | beat-cited → entailment NO (added relation + personification) |
| #3 | "Those same ladies wanted more than newspapers" | beat-cited → entailment NO (invented motive) |
| #4 | "The Meurice DREW the writers too" | beat-cited → entailment NO (magnetism ≠ "they stayed") |
| #4 | "the MOST FAMOUS story attached to this place" | entailment NO (unsourced superlative ranking) |

**These findings are FP-battery material:** add a `causal-relation-invention` mutation
class (co-location → causation) to the Scope-2 FP battery, seeded from these five real
examples. The human independently generating the gate's target class is the strongest
calibration evidence yet.

### Bucket 2 — craft/pacing/attribution → the PASS PROMPT (Scope 3b) + AC-9 checklist
Not fact errors; the gate rightly ignores them. They become prompt rules (§C below) and
AC-9 review items: #1 dangling modifier ("entrance … the grandest of the palace hotels");
#3/#2 pronoun ambiguity ("them", "the same set"); #5 dense sentence overloaded for
audio; #7 repeated "Dickens"; #8 long uninterrupted quote block; #9 unattributed
corpus judgment ("kingdom of hell" IS verbatim in `85ebe707`'s body — grounded, so the
gate passes it; the rule is to attribute it to Orwell in the narration); #10 compressed
von Choltitz claim (grounded — body says "saved Paris from destruction" — but phrase for
restraint).

### Bucket 3 — missing background context → CORPUS, not the pass (recorded follow-up)
#6: "Tuileries Palace", plongeur = dishwasher, what an arrondissement is. The grounding
gate FORBIDS the pass from adding these (world knowledge; "Tuileries Palace" is
literally goldenization deviation #4 — the bodies don't carry "Palace"). The fix is
corpus enrichment (bodies/beats that carry the context), never gate loosening. Logged in
`state.json` follow_ups.

### Honest residual (matches 04b R-V2/R-V3)
"To understand why it landed here…" — a causally overpromising transition with no
salient tokens takes the token-free glue lane (scan only, no entailment). The
deterministic machinery cannot catch salient-token-free causal framing; coverage =
the pass-prompt rules (§C) + the AC-9 human gate. This review demonstrates the human
gate doing exactly that job. Recorded, not hidden.

## C. Pass-prompt rules added by this review (Scope 3b task 2 requirements)

1. **Facts beside each other, not welded:** when the source does not state WHY/BECAUSE,
   place facts in sequence without asserting causation, attraction, motive, or intent
   ("It also drew a substantial English clientele" — never "the ladies drew…").
2. **No unsourced rankings/superlatives** ("most famous", "grandest" only where the
   source says it).
3. **Pronoun discipline:** every "them / those same / the same set" must have an
   unambiguous referent in the previous sentence; else repeat the noun.
4. **Audio pacing:** one idea per spoken sentence; split any sentence carrying more
   than ~two facts; repeated proper nouns get a natural pause (new sentence), not a
   dash splice.
5. **Quote staging:** break quote runs longer than ~2 sentences with one sentence of
   narration; introduce the climax quote explicitly.
6. **Attribute judgments:** a vivid corpus characterization ("kingdom of hell") is
   voiced AS the source's ("Orwell described…"), not the narrator's.
7. **Restraint on large claims:** compress dramatic historical claims toward the
   source's own framing ("was spared destruction" phrasing pattern).

These are prompt + AC-9 review items — the deterministic rules of `02-spec.md` P1 are
unchanged.
