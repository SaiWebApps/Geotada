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
A RUNTIME fact-loss guard in the compose gate: for each stop, the composed text
must retain the distinctive grounded entities (proper nouns + years) of the
stop's SOURCE beats; a stop that drops one REVERTS to its stitch (which has the
fact). Narrow (proper-noun/year tokens), not the full semantic-granularity
rewrite the judge flagged as over-gating-risky. Prototype confirmed it flags
Charing/Cross/1200s on the current output. Wiring it into the gate + one
re-validation is the path to ship the (real, proven) opener improvement safely.

## The improved prompt block (ready to re-apply once the runtime guard exists)
Inserted after VOICE, before the negative CRAFT block in _COMPOSE_SYSTEM:
- OPEN ON A HOOK, NOT A LABEL
- ANSWER YOUR OWN HOOK (a question opener must be answered from a beat fact)
- REWORK THE SHAPE, KEEP EVERY FACT (carry BOTH facts of a two-fact sentence)
- LEAD WITH THE STAKES THE BEATS STATE (invent nothing)
- WRITE FOR THE EAR
Full text preserved in git history of this session's uncommitted compose.py, and
in PROPOSED-prompt-changes.md (base version).
