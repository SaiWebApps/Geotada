# 01 — Scope: Beat-level "correct-don't-reject" compose

**Date:** 2026-07-13 · **Stage:** 1 (Scope) · **Thinking mode:** Product thinker
**Sources:** `Docs/bug-reports/2026-07-13-compose-next-steps-handoff.md`,
`Docs/bug-reports/2026-07-13-compose-stop-revert-haiku-ceiling.md` (OPEN ticket)

---

## The problem (why this exists)

The AI-voice composer rewrites a stop's stitched beats into one flowing story, then a
faithfulness gate checks each sentence. Today the gate is a **discarder**: a sentence it
rejects is dropped, and if that leaves a fact uncovered the WHOLE stop reverts to the
scattered "shotgun" stitch. Two proven defects make this fire constantly:

1. **The gate is blind on half the corpus.** Its "did we keep every fact?" check keys off
   `key_claims`, but **51% of Paris beats (2396/4644) and 15% of NYC beats have none** — so
   coverage and the faithfulness skip (`verify.py:279`, `:282`) are no-ops on those beats.
2. **Haiku returns NO on faithful sentences.** Dense multi-clause fusions and faithful
   rephrasings get false-negatives; one rejected sentence reverts the whole mostly-good stop
   (live proof: the Le Meurice Orwell sentence, `2026-07-13-compose-stop-revert-haiku-ceiling.md`).

The shelved per-sentence-restore fix (`wip/compose-per-sentence-restore`) was STOPPED by the
skeptic panel: it silently lost the "High Command took up residence" fact trapped in a
compound stitch sentence. Root cause is the whole `key_claims` + drop-then-revert design.

## What we're building

- **Make `script_body` the single source of truth.** The composer, the faithfulness check,
  and the fallback all read a beat's full `script_body` prose — never `key_claims`.
- **Turn VERIFY from a gate into a CORRECTOR.** A flagged sentence is NOT dropped: it is
  **regenerated constrained to its source beat(s)' `script_body`** (re-ground the
  faithful-but-rejected sentence / strip the hallucination), then re-checked — a bounded
  retry (1–2).
- **Beat-level verbatim FLOOR.** If a sentence still can't verify after the bounded retry,
  replace **all of that one beat's composed sentences with its verbatim `script_body`**.
  Verbatim corpus text cannot be hallucinated or lost, and the beat stays a coherent chunk.
  Other beats at the stop keep their good composed prose. **No whole-stop revert ever.**
- **Retire the coverage machinery from the compose path.** `claims_realized_by` /
  `verify_claim_coverage` / the `coverage_failures` gate / `drop_failing_sentences` /
  `repair_composed`'s whole-stop revert become vestigial — the verbatim floor is the new
  never-lose-a-fact guarantee.
- **Drop reflections for now** (the one real `key_claims` consumer). Remove them from the
  compose output; the long-leg audio-deficit filler can be re-added later re-sourced from
  `script_body`. (Logged as a future scope, not built here.)

## Why

Closes the OPEN high-severity Le Meurice bug that blocks the AI-voice differentiator, and
unblocks Phase 1's MVP thesis — *"can we generate compelling narrative tours"* — by making
dense stops ship good fused prose instead of reverting to the shotgun stitch.

## What we're NOT building

- **No `key_claims` teardown in the schema or extraction pipeline.** `key_claims` stays a
  (now-unused-by-compose) beat property; `unified-beat-extract`, the Neo4j schema, and
  `claim_dedup`'s route-level dedup are a **separate follow-up spec**. Compose-only blast radius.
- **No reflection rebuild.** Reflections are removed from compose, not re-sourced. Future work.
- **No change to the deterministic stitcher** (`generation.generate`) — it stays the
  offline/`make test` baseline and the source of the verbatim floor text.
- **No loosening of the anti-hallucination bar.** Correcting toward a beat's own prose must
  never let a fabricated fact through — this is the danger half (full skeptic panel + fabrication
  negative-fixtures required at red-team/QA).
- **No new TTS/audio work.** Audio is TTS of the FINAL accepted text, baked once
  post-acceptance (already resolved in the handoff) — out of scope.

## What already exists (this work touches)

- `src/tour/compose.py` — `compose_script_per_chapter` (~619-781): per-stop compose,
  best-of-N, and the drop→whole-stop-revert repair ladder (~769-781) being replaced. ALSO
  `compose_script` (~539-592, whole-tour, the persisted `/compose` path) — its separate
  drop/revert ladder retires under the same corrector contract. (Amended post-challenger.)
- `src/tour/verify.py` — `verify_faithfulness` (~200-316): the `key_claims` skip (`:279`),
  verbatim shortcut (`:282`), strict→stop-union entailment, and `HaikuFaithfulnessChecker`.
- `src/tour/compose_gate.py` — `drop_failing_sentences`, `repair_composed`,
  `build_full_verifier`, `compose_and_verify` (the coverage wiring at `:194`).
- `src/tour/claim_dedup.py` — `claims_realized_by` / `verify_claim_coverage` (compose-side
  usage goes away; the route-level `suppress_repeated_claims` dedup is untouched here).
- `src/tour/reflection.py` + `verify._visited_claims` — the reflection path being dropped.
- `src/tour/contract.py` — `ValidationReport.coverage_failures`, `BeatRef.key_claims`
  (fields stay; compose stops populating/reading the compose-only ones).
- `src/api/routes/trips.py` — the two call sites: `/compose` persisted path (`:518`) and the
  preview per-chapter path (`:769`, `candidates=2`).
- `tools/diagnose_compose_stop_revert*.py` — live single-stop harnesses (dev Neo4j :7687 +
  `COMPOSE_PROVIDER=anthropic`) for the cheap Le Meurice first-proof.

## Dependencies & risks

- **Danger half (highest risk):** the corrector regenerates a sentence *against a ~450-char
  paragraph* instead of terse bullets. Unproven whether Haiku entailment behaves on paragraph
  support — **cheap first step:** one live Le Meurice stop through the correct-against-beat loop
  before any corpus-wide work (handoff open-Q 3). Requires the full adversarial panel + fabrication
  negative-fixtures — do NOT close on offline fixtures alone (the lesson of the shelved attempt).
- **Cross-beat fusion:** a fused sentence cites beats A+B; a fusion is "owned" by all cited
  beats — correct/floor must resolve toward BOTH (handoff open-Q 2). A spec decision.
- **Regression seam:** removing the whole-stop-revert path changes behavior on EVERY composed
  tour, not just Le Meurice — realignment work, needs a characterization/golden pin before the
  behavior change (Stage 3 characterization gate).
- **Live-cost:** every real proof spends Opus (compose) + Haiku (verify); the mock path keeps
  `make test` offline. Budget the live proofs.

---

**Right-sizing:** Large + realignment (changes existing behavior across compose.py / verify.py /
compose_gate.py, danger-half anti-hallucination). → **Full workflow 1→2→3→4→5→6**, Tier 3 rigor.
