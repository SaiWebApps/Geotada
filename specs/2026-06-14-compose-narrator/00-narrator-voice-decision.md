# COMPOSE Narrator Voice — Decision: SINGLE NARRATOR (LOCKED 2026-06-14)

> **Status: LOCKED** (user decision, 2026-06-14). Scope: the narrator *format* for the
> Phase-4 COMPOSE step of the Ondoway tour engine. Companion to
> `specs/2026-06-13-tour-planner-canonical/ALGORITHM-SPEC.md` (COMPOSE = §4–5).

## Decision

Ondoway tours are narrated by **ONE warm, second-person narrator** — "a knowing friend walking
with you." **Not** a guide+novice pair, **not** two co-experts in conversation. A single voice with
**range** (register / diction / pacing shift by lens), not a static reader.

A **second voice** is permitted only as a **deferred (Phase 4+) option**, in exactly **one** narrow,
**mechanically-gated** case: a **verbatim historical quotation read as itself** on a long stop,
*introduced by* the primary narrator. It is never a novice asking questions, never a co-host, never a
lens device, and never speaks a new or paraphrased fact.

### Options considered
- **A — Single narrator** (chosen, as the factual spine).
- **B — Guide + novice** (rejected as default).
- **C — Two co-experts conversing** (rejected outright — worst grounding fit).
- **D — Single + a surgical second voice** (the verbatim-quote exception is banked for Phase 4+).

## Why (evidence — from the 2026-06-14 narrator-format research: 5 angles + adversarial skeptic + synthesis)

1. **The pedagogy for a second voice doesn't transfer.** The "learning by overhearing" case requires
   *active co-construction* (Chi, Roy & Hausmann 2008) or *genuinely deep questions* (Craig 2003) and
   does not reliably replicate (Lee & Muldner 2019, n=77). Ondoway's listener is solo, passive,
   attention-divided — the ICAP "Passive" tier, where format adds no lift.
2. **Walking penalizes *conversation* specifically.** Hyman 2010 ("unicycling clown"): phone
   *conversation* caused inattentional blindness; passive listening did not. Guide+novice couples the
   most fragile benefit to the one proven safety hazard.
3. **Grounding fails hardest with two voices — verified in our own code.** `verify_faithfulness`
   entails only `source_type=="beat"` sentences (`src/tour/verify.py`). A second voice's
   questions/reactions either escape the fact-gate (NotebookLM's documented "hosts sometimes introduce
   inaccuracies") or need a new, unsolved entailment shape (a question asserts a presupposition; a
   reaction asserts agreement). `Sentence` is `frozen, extra="forbid"` with no speaker field
   (`src/tour/contract.py:251`).
4. **The market leader is retreating from the format.** Google added NotebookLM "Brief" / length
   controls / Debate / Critique because the two-host Deep Dive was padded, long, and loose.
5. **The engagement is reproducible with one voice.** Momentum and "what happens next" come from the
   *structure of the telling* — anecdote → raised question → reflection (Ira Glass), not a second mouth.
6. **Intimacy = single voice.** Single second-person direct address builds the strongest parasocial
   bond; two voices conversing demote the listener to eavesdropper.

## Mechanical gate for the future (Phase 4+) second voice

When/if the verbatim-quote second voice ships, `validate_script` MUST enforce that any `Sentence`
spoken by the second voice is a **verbatim quote or glue** — never a free-form `"beat"` paraphrase —
so the **verifier, not the prompt**, guarantees the second voice can never speak an un-entailed fact.
The trigger is a **data condition** (the beat carries a first-person quotation), not the model
deciding a moment is "earned." Long stops only; never short ones.

## Implications for the COMPOSE design (near term)

- **No `speaker` field now** — keep the single-speaker `Sentence` model. The real near-term contract
  work is **multi-beat citation** + a **no-fact connective/voice category**, NOT a speaker migration.
- **Capture the newcomer's curiosity as STRUCTURE** — COMPOSE raises the question a first-timer would
  ask, then answers it from the beats (per Glass). We do not lose the novice's value; we internalize it.
- **Lens = a register/diction dial on the one narrator** — which keeps a multi-lens tour one *whole*
  story instead of partitioning a place between two experts.

## Open / NEEDS VERIFICATION (decide against the real provider, later — none asserted as fact)

- Whether **one TTS voice can carry lens-appropriate register shifts** — validate by ear against the
  real provider before relying on it. (This is the single biggest risk to the single-voice bet:
  TTS prosody is narrower than a human's, so a single voice could read *monotonous* even with great
  writing.)
- The deferred D-phase TTS path: ElevenLabs multi-speaker "Text to Dialogue" was found to default to
  the **alpha** `eleven_v3` (~2,000-char cap, no SLA), which collides with our 4,000-char
  `_split_for_tts` chunker (`src/audio/provider.py`). Re-verify before any D work.

## Validation tie-in

The cheap experiment to confirm single-voice suffices: generate the **same** real Paris tour two ways
— today's stitched-verbatim output vs. a COMPOSE-rewritten single-narrator version — and **listen while
walking**. This rides the Phase-1.5c audio harness (live TTS + Whisper eval), so the two workstreams
converge here.

## Source
Narrator-format research workflow, 2026-06-14 (audio-tour industry · two-host/NotebookLM · cognitive
science/pedagogy · narrative craft · Ondoway engineering+grounding fit; adversarial skeptic; scored
synthesis). Key citations: VoiceMap publisher docs; Detour (Wired 2015, Mason eng. 2014/16); Rick
Steves; Elliston & FitzGerald 2012; Chi & Wylie 2014 (ICAP); Chi/Roy/Hausmann 2008; Craig 2000/2003;
Lee & Muldner 2019; Hyman 2010; Mayer voice/personalization principles; Rettberg 2026 (NotebookLM
"synthetic intimacy"); 9to5Google 2025 (NotebookLM formats).

