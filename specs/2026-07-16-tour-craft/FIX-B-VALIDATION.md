# Fix B (hook-opener prompt) — live validation result (2026-07-16)

STATUS: HELD, not shipped. Judge STOP + a live re-validation both confirm the
prompt change dramatically improves openers but drops a grounded fact during
restructuring, with no runtime guard to catch it.

## What was validated (Opus, London West End tour, ~$0.40 total over 2 live runs)
- Dwell-stop label-openers: 2 -> 0 (National Gallery + Trafalgar de-labelled).
- Lint: stilted 0.233 -> 0.098, engagement 0.381 -> 0.569, second-person 0.32 -> 2.27/100w.
- Recovered a fact the OLD prompt dropped: Nelson's Column "169 feet / Vice-Admiral" (corpus-verbatim, no invention).
- Acceptance (rubric): 6.3 -> 7.7 avg; National Gallery 7->8, Trafalgar 7->9.

## Why it is HELD (the blocker)
On BOTH the first and the improved prompt, the Trafalgar stop DROPPED
"Charing Cross / distances measured from here" AND "since the 1200s" — two
grounded facts (data/london/wikipedia/trafalgar_square-rev-1364154913.txt,
beat london_trafalgar_square_wikipedia_3). The composed hook even ASKS the
question those facts answer ("where does London begin?" / "how far to London?")
then omits the answer. The improved prompt added ANSWER-YOUR-OWN-HOOK +
REWORK-THE-SHAPE-KEEP-EVERY-FACT bullets; the model still dropped it. Prompt
nudges are not a reliable fact-retention mechanism.

Root cause: the coverage gate's multi-fact-sentence blind spot — a source
sentence carrying two facts passes verify_claim_coverage when the composed text
retains EITHER, so the other is silently dropped. Restructuring for a hook makes
this fire.

## The real fix (next step, Tier-3, NOT prompt-only)
A RUNTIME fact-loss guard in the compose gate: if a stop's composed text drops a
distinctive grounded fact of its SOURCE beats, that stop REVERTS to its
fact-complete stitch. This makes Fix B safe: de-label where the compose keeps
every fact, revert where it doesn't.

### REJECTED implementation (2026-07-16): token / proper-noun matching. DO NOT REBUILD THIS WAY.
A first cut (`verify_hard_fact_retention`, token retention of distinctive
multi-word proper nouns) was built, unit-tested on synthetic ASCII names, and
then REFUTED by a hostile skeptic panel + 4 real full-bar failures. It was
reverted un-committed. Failure modes:
- **Over-gates the launch city.** The regex excludes accented letters, so ~494
  Paris beats ("Théâtre des Variétés" → garbage "Th"/"Vari" tokens) falsely flag
  on any faithful reword. Same for nicknames ("V&A" ← Victoria and Albert),
  possessives ("Nelson's" ≠ "Nelson" — its OWN docstring example), and
  sentence-initial capitals ("The King").
- **Manufactures duplicates.** Its coverage_failure escalates through
  `repair_composed_surgical`, which appends the stitch ALONGSIDE the good
  sentence → the stop ships both → the exact repetition compose exists to remove.
- **Under-gates.** "Tower Bridge" (both words generic), single proper nouns, and
  dates are invisible.
LESSON: fact retention is a SEMANTIC problem; token/entity matching cannot handle
synonyms/nicknames/accents without over- OR under-gating. Synthetic-ASCII unit
tests gave FALSE confidence — validate any such guard against real
`data/paris/beats.json` (and forecast it) BEFORE writing code.

### REJECTED implementation #2 (2026-07-16): per-STOP LLM omission check. DO NOT REBUILD AS-IS.
A per-stop Haiku omission gate (`verify_omissions`, mirror of HaikuFaithfulnessChecker
— "does the composed STOP still convey this claim?") was forecast (GO-WITH-CONDITIONS),
BUILT ($0 machinery, offline-inert, 1913-pass bar), then a hostile Fable-5 monitor
REFUTED the SERVING design PRE-commit (reverted un-committed). What was SOUND: the
anti-duplicate firewall (omission failures never reach the surgical splice), gate
off-by-default, $0 offline bar. What KILLED it — two structural flaws proven on REAL
`data/paris/beats.json`:
1. **Global baseline vs per-stop judging.** `claims_realized_by(stitched)` is
   tour-GLOBAL, but the check judged each claim against its beat's stop ONLY. Cross-stop
   dedup (`suppress_repeated_claims`, 82 real Paris twin-claim pairs) voices a fact at
   stop A and drops its retelling at stop B — the check then FALSELY refuses stop B on
   an IDENTITY compose (nothing changed). Only 7% of Paris key_claims are verbatim in
   their body, so the "verbatim shortcut guarantees convergence" claim is false on the
   launch city.
2. **Atomic multi-fact claim = no granularity.** For KEYLESS London the pseudo-claim is
   a whole body sentence ("landmark since the 1200s, distances measured from Charing
   Cross"). An atomic "did it drop ANY piece?" cannot PASS a hook that correctly drops
   nested geography while KEEPING Charing Cross — it over-gates the exact case it was
   built for.
Plus routing gaps (omission_failures silently dropped by `_report_for_stop`,
`ComposeVerificationError`, `_per_stop_verify_report`) and a sequential (un-parallelized)
call burst.

### The ACTUAL viable paths (pick one; both avoid the guard entirely)
- **A — SURGICAL-OPENER prompt (cheapest, prompt-only, testable):** constrain Fix B so
  the model rewrites ONLY the stop's FIRST sentence into a hook and leaves every other
  sentence's facts intact and in order. The Charing Cross drop came from restructuring
  the WHOLE stop; a surgical opener change de-labels (the main win) with minimal
  fact-drop risk, and the existing coverage gate catches gross drops. Re-validate live.
- **B — SINGLE-FACT beat decomposition (corpus fix, robust):** the ROOT cause is
  multi-fact body-sentence beats in the keyless London corpus. Split them into
  single-fact beats at extraction/dedup so the EXISTING per-claim coverage gate (no
  new machinery) catches any dropped fact and the compose model gets atomic units. This
  also independently improves compose quality. Bigger, but removes the blind spot at the
  source instead of guarding it downstream.
A per-fact (not per-stop, not per-claim) omission check would also work but needs an
extra LLM decomposition layer + global judging + calibration — a full Tier-3 project the
two rejected guards show is not a tail-of-session patch.

## The improved prompt block (ready to re-apply once the runtime guard exists)
Inserted after VOICE, before the negative CRAFT block in _COMPOSE_SYSTEM:
- OPEN ON A HOOK, NOT A LABEL
- ANSWER YOUR OWN HOOK (a question opener must be answered from a beat fact)
- REWORK THE SHAPE, KEEP EVERY FACT (carry BOTH facts of a two-fact sentence)
- LEAD WITH THE STAKES THE BEATS STATE (invent nothing)
- WRITE FOR THE EAR
Full text preserved in git history of this session's uncommitted compose.py, and
in PROPOSED-prompt-changes.md (base version).
