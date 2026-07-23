# Implementation plan (LOCKED) — rescue under-cited within-stop fusions

Companion to `2026-07-13-compose-fusion-fallback.md` (the diagnosis). This is the
manager-reconciled plan the Developer implements and QA/Skeptics/Judge hold it to.
**Tier 2.** RED-first. Do NOT commit — the manager gates + commits the proven subset.

## Locked decisions
- **Fix locus = `verify_faithfulness` (src/tour/verify.py): strict-first, per-stop-union fallback.**
  A beat sentence is entailed FIRST against its declared `cited_beat_ids` (unchanged
  primary path). ONLY on failure, retry against the UNION of `key_claims`+`script_body`
  of all beats seated at that sentence's `stop_idx`. Final failure iff BOTH fail.
  This also corrects best-of-N ranking (`compose.py` `_local_penalty` calls it).
- **`also_cites` population = minimal honest subset (PO option B).** Compose-side
  deterministic pass `_populate_also_cites` (src/tour/compose.py), applied to the
  assembled candidate BEFORE each `verify` (attempt 1 and attempt 2), and in the
  `compose_script` whole-tour closure for parity. `verify.py` stays non-mutating.
- **Regression metric** `undercited_fusions` in src/tour/compose_metrics.py (deterministic
  lexical signature-containment proxy; NO LLM). Field on `ComposeMetrics`, computed in
  `compute_compose_metrics`, surfaced via `quality_violations`.

## Invariant (load-bearing — skeptics WILL attack this)
The stop-union is built from `sentence.stop_idx` and includes a beat ONLY if some
sentence AT THAT STOP cites it. Never global, never cross-stop. A fact present in
neither the sentence's cited beats nor any co-stop beat is NOT entailed → still fails.
The metric likewise flags only "weakly covered by declared beats BUT strongly covered
by the stop union" — a fabricated token (in neither) has low union containment → never
flagged.

## Manager risk flags (QA/Skeptics must check)
1. **Absolute-violation coupling.** The Planner wires `undercited_fusions` as an ABSOLUTE
   `quality_violations` entry. The metric is a LEXICAL proxy; the gate is ENTAILMENT. If
   they disagree on a real corpus tour, the bar goes red. QA MUST run `make golden-probe`
   and `make tour-grade`. If the metric false-fires on any existing golden, DOWNGRADE it
   from an absolute `quality_violations` entry to a reported-only metric (still tested via
   fixtures) and note it. Do not ship a bar that a legitimate golden fails.
2. **Concurrency/order.** The two-phase (strict wave → union-fallback wave) rewrite of
   `verify_faithfulness` must keep the failure list in script order and keep
   `test_faithfulness_entailment_runs_concurrently` (test_tour_verify.py) green.
3. **Derivation parity.** §fix and §also_cites and §metric must derive "the stop's beats"
   IDENTICALLY, or the union that rescues won't equal the union that gets cited/measured.

## Implementation (per the Planner; concrete)
### verify.py — `verify_faithfulness` (signature unchanged)
- Build `stop_beats: dict[int, list[BeatRef]]` from the script's beat sentences
  (`for bid in s.cited_beat_ids`, dedup per stop). `from collections import defaultdict`.
- Phase 1: existing strict entailment against declared `support`, unchanged. Reflections
  and the verbatim shortcut stay exactly as-is; reflections NEVER enter phase 2.
- Phase 2: for beat sentences that FAILED phase 1 and whose stop union adds beats beyond
  the declared set, run one concurrent entailment per still-failing sentence against
  `union_support[stop] = concat(key_claims + script_body of stop_beats[stop])`. Keep as a
  failure only if declared AND union both say NO.

### compose.py — `_populate_also_cites(composed, beats_by_id) -> Script`
- Pure helper. Group beat sentences by `stop_idx`; stop pool = beats cited by any beat
  sentence at that stop. For each sentence, for each OTHER stop beat B not already cited:
  add B iff it contributes ≥1 salient token the declared citations lack (reuse
  `claim_dedup._signature`/`_overlap`; the "adds something" guard prevents over-citing).
  Rebuild via `model_copy(update={"also_cites": ...})`.
- Apply before EACH `verify` in `compose_script_per_chapter` (after `_assemble()` at
  attempt 1 and attempt 2) and in `compose_script`'s `compose()` closure.

### compose_metrics.py — `undercited_fusions(composed, beats_by_id)`
- `containment(sent, support) = |sent_sig ∩ support_sig| / |sent_sig|`.
- Flag a beat sentence iff `containment(sent, declared) < UNDERCITED_DECLARED_MAX (0.75)`
  AND `containment(sent, stop_union) >= UNDERCITED_UNION_MIN (0.85)`.
- Add `undercited_fusions` field to `ComposeMetrics`; set it in `compute_compose_metrics`;
  add to `quality_violations` (subject to risk-flag #1); add to `__all__`.

## Tests (RED-first, no live LLM)
Use a deterministic `_Containment` entailment stand-in (≥4-letter words must appear in the
support) — mirror the existing one in tests/test_tour_verify.py. Do NOT use
`MockFaithfulnessChecker` (always-passes → vacuous).

1. **tests/test_tour_verify.py** — `test_undercited_fusion_rescued_by_stop_union` (fused
   sentence cites A only, B also at stop 0 → rescued → []). AND the skeptic guard
   `test_union_fallback_is_per_stop_not_global` (B at stop 1 → NOT rescued → non-empty).
   Existing `test_invented_fact_still_fails` must stay green.
2. **tests/test_compose_metrics.py** — fires on bad pair; clean on well-cited; NOT flagged
   on a fabricated fact (metric-layer invariant).
3. **tests/test_compose_quality_eval.py** — `test_undercited_fusion_survives_composition`:
   2-beat single stop (BX "German High Command took up residence"; BY "von Choltitz
   commanded the garrison") + a trivial 2nd stop; replay a FUSED sentence citing BX only.
   Assert (a) the fused sentence SURVIVES with both facts in one sentence (RED today —
   reverts), (b) `served.validation.passed`, (c) `fused.cited_beat_ids == {BX, BY}`,
   (d) `undercited_fusions == ()` and `quality_violations == []`.

## Undo-test (QA)
Back out ONLY the verify.py phase-2 fallback (+ the `_populate_also_cites` call) while
keeping the tests → the eval test (3) must go RED (stop reverts) → restore → GREEN.

## Sequencing
5c(RED)→verify.py→green; metrics test(RED)→compose_metrics→green; eval test(RED)→compose.py
wiring→green; then full `make test` + `make lint` + `make golden-probe`/`make tour-grade`.

## Out of scope (do NOT touch)
Cross-POI entity-thread gathering; compose prompt text (keeps `PINNED_PROMPT_FINGERPRINT`
stable); the frontend AI-voice toggle; coverage/forbidden/reflection checks; best-of-N count.
