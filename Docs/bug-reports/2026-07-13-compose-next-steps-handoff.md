# Compose stop-revert — next-steps handoff (2026-07-13)

Companion to `2026-07-13-compose-stop-revert-haiku-ceiling.md` (still OPEN). Written
to hand off to a fresh conversation. Decision made this session: **drop `key_claims`.**

## TL;DR
The "safe half" per-sentence restore fix is SHELVED — it can silently lose a fact.
Diagnosis found the real root cause: the compose gate's "did we keep every fact?"
check keys off `key_claims` (a per-beat bullet list of facts), but **51% of Paris
beats (2396/4644) and 15% of NYC beats have no `key_claims` at all** — so the check
is blind on half the corpus. User's call: `key_claims` are not useful for our
purpose; drop them and move to a **beat-level** model.

## State of the tree
- **main**: `ccd6a21` frontend AI-voice toggle (UI wiring only, browser-proven);
  `4abcfcc` ticket update with the attempt-1 finding. Ticket stays OPEN.
- **branch `wip/compose-per-sentence-restore`** (`79dd034`): the shelved
  `restore_grounded_for_uncovered` rung + tests + `tools/diagnose_compose_stop_revert_fix.py`.
  Correct for atomic facts but loses a fact trapped in a compound stitch sentence;
  carries a red-first `xfail` guard. **NOT for merge.**

## What a beat actually is (plain terms)
A row in Neo4j (`NarrativeBeat`) = a vetted paragraph of narration about a POI, tagged
with a lens. Key properties: `script_body` (the real text — the source of truth),
`entities`, `beat_type`, `narrative_function`, `emotional_register`, `physical_cues`,
`source_passage`, `trigger_address`, and `key_claims` (a bullet summary of the facts —
**often missing**). Today THREE representations of the same beat float around:
`script_body` (real), `key_claims` (bullet summary, 51% missing), and the sentence-
split "stitch" the composer starts from. The bug lives in the seams between them.

## Decision
DROP `key_claims`. The beat's `script_body` is the single source of truth for both
checking the AI's rewrite and falling back when it's rejected.

## Recommended path — CORRECT, don't reject (refined 2026-07-13 with user)
A **beat-level, generate-then-correct** compose model. `script_body` is the single source
of truth; verify becomes a CORRECTOR grounded in the beat, not a gate that discards.

Per stop, at BUILD time (audio is baked only once, AFTER the tour is built + accepted — so
extra LLM passes are a fine one-time cost, no real-time pressure):
1. Compose the stop (rewrite/fuse the beats).
2. Check each sentence against its source beat(s)' `script_body` (anti-hallucination). This
   IMPROVES on today — `verify_faithfulness` currently SKIPS the check when a cited beat has
   no `key_claims` (verify.py ~279), i.e. it is softest on the same 51%.
3. A flagged sentence is NOT dropped — **regenerate it constrained to that beat's text**
   (fix the hallucination / re-ground the faithful-but-rejected sentence), then re-check.
4. FLOOR: if it still can't verify after a bounded try or two, fall back to the beat's OWN
   words (verbatim `script_body` → cannot be hallucinated or lost).

This dissolves the whole ticket: a Haiku false-negative on a faithful sentence triggers a
re-ground (or the verbatim floor) instead of nuking the stop — no loss, no shotgun, good
prose most of the time, and the beat stays a coherent chunk (no fragmentation of the
composer's construction). `key_claims`, the claim-coverage machinery, and the shelved
per-sentence restore rung all become vestigial.

## Open questions to resolve in the spec
1. **Reflections** are the ONE real `key_claims` user (a recap of already-visited facts,
   spoken on a long leg to fill audio deficit — reflection.py + `verify._visited_claims`).
   Re-source the recap from prior beats' `script_body`, or simplify/drop it. Low-stakes but
   it is the seam to decide.
2. **Cross-beat fusion rule:** a fused sentence cites beats A+B; if it fails, correct/floor
   toward BOTH A and B. (Cleanest: a fusion is "owned" by all its cited beats.)
3. **TEST FIRST (cheap):** does checking/correcting against a ~450-char PARAGRAPH (vs terse
   bullets) behave with Haiku? One live Le Meurice stop through the correct-against-beat loop
   before any corpus-wide work. This is the danger half → full skeptic panel + fabrication
   negative-fixtures.
4. RESOLVED — no need to keep the sentence-"stitch" as an audio source: audio is TTS of the
   FINAL accepted text (built once, post-acceptance). May still want split_sentences for TTS
   units on the final text, and the mock/offline baseline for `make test`.
5. **`key_claims` removal cleanup** (follow-up, not blocking): extraction pipeline
   (`unified-beat-extract` etc.), schema, reflections.

## Key files
- `src/tour/compose.py` — `compose_script_per_chapter` (~620-805, the repair ladder ~784-805).
- `src/tour/compose_gate.py` — `drop_failing_sentences`, `repair_composed` (whole-stop revert).
- `src/tour/verify.py` — `verify_faithfulness` (~200-316; the key_claims skip at ~279).
- `src/tour/claim_dedup.py` — `claims_realized_by`, `verify_claim_coverage` (the coverage that goes away).
- `src/tour/reflection.py` + `verify._visited_claims` — the reflection dependency on key_claims.

## Key data facts
- Paris: 4644 active beats, 51% no `key_claims`. NYC: 4000, 15% no `key_claims`.
- Flagship: Le Meurice (Paris), 3 beats — `c9c90a74` (English corridor, no key_claims),
  `c3d4a78a` (Dickens + von Choltitz, HAS key_claims), `85ebe707` (Orwell/kitchens/High
  Command, key_claims=None — the beat whose "High Command took up residence" fact the
  shelved fix lost). Repro config: POST /trips/preview, center 48.8635,2.3280,
  duration_min 240, lenses [famous_residents, literary_heritage, historic_arch],
  compose:true, COMPOSE_PROVIDER=anthropic, dev Neo4j :7687.

## How to resume
Read this + the ticket. Run `/spec-pm` (or `/team`) to design the beat-level model —
treat it as the danger half (anti-hallucination path): full adversarial panel + fabrication
fixtures. Cheap first step: prototype "recover = splice the failing beat's `script_body`"
live on Le Meurice and confirm it reads well + loses nothing, before any corpus-wide work.
