# 02 — Spec (Contract): Beat-level "correct-don't-reject" compose + verified narrative pass

**Date:** 2026-07-13 · **Stage:** 2 (Spec, Flavor B) · **Thinking mode:** Contract designer
**Builds on:** `01-scope.md` (approved)
**Amended:** 2026-07-14 per `04-red-team.md` · **2026-07-15 per `04b-red-team-reopen.md`
(v2.1, approved): verified narrative pass added as the layer above the correct-loop;
entailment calibrated; no entailment-free lanes; goldenized acceptance oracle = `01f`.

---

## Purpose

The compose pipeline corrects or grounds unverifiable sentences instead of discarding
them, and a **verified narrative pass** then rewrites each stop's verified text into one
flowing narration — so a dense stop always ships faithful, coherent, ENGAGING prose,
closing the whole-stop-revert bug, the 51% `key_claims` blind spot, and the Scope-1
NO-GO's disjointed-narrative failure.

## Inputs

- A stitched `Script` + `BeatSequence` + `Route` (unchanged upstream contract).
- Each `BeatRef.script_body` (non-empty for every seated beat) — the **only** grounding
  source. `key_claims` is never read on this path.
- A `ComposeClient` (Opus/mock), a `FaithfulnessChecker` (Haiku/mock), and a
  `NarrativePassClient` (Opus/identity-mock), injected as today.

## Outputs

- A composed `Script` whose every beat-cited sentence is one of, per stop (the
  CORRECT-LOOP, pre-pass):
  1. **verified** — passes the deterministic pre-gate (no year/number/entity token absent
     from its cited beats' `script_body` union) AND is entailed by that union. Citations
     are first repaired deterministically (`_populate_also_cites`, its token
     justification RESTRICTED to the pre-gate salient class — years/numbers/proper-noun
     tokens — per 04b BL-V2); a sentence rescued only by the per-stop anchor union gains
     ONLY the minimal token-justified subset of it; vignette beats are never in the union.
  2. **corrected** — regenerated constrained to its cited beats' `script_body`,
     re-entering pre-gate + entailment + forbidden/traceability. Correction is PERMITTED
     only when the flagged sentence's salient tokens are covered by its declared
     citations' bodies — an UNDER-CITED sentence routes straight to the floor of the
     stop-union beats owning its uncovered tokens. **Attempt 1 is a TRIM** when the
     failure is separable unsourced garnish: LLM-executed, mechanically accepted only if
     no tokens were added AND every removed content token is in the flagged unsupported
     set — anything else counts as the attempt-2 full rewrite (04b D2c). A correction
     returning ~identical text (affirm) routes to floor and increments `affirm_reject`
     telemetry — there is NO escalation ship-path (04b D2d).
  3. **floored** — each owning (cited) beat's sentences replaced by its verbatim
     **post-dedup stitch sentences**, in composer-chosen position; collateral subset
     rule: a floor replaces only sentences whose FULL citation set ⊆ the floored-beat
     set.
- **Seated-beat invariant (pre-pass):** every beat in the stop's compose request owns
  ≥1 shipped sentence (as `source_id` or in `also_cites`); a beat owning none is floored
  in adjacent to its POI's block. Deterministic; works on `key_claims=()` beats.
- **Glue:** a flagged glue sentence gets ONE correction attempt (same trim-then-rewrite
  ladder, constrained to the glue whitelist rules) BEFORE any drop; a still-failing
  composed glue sentence floors to the stitched glue of the same `(stop_idx, source_id)`;
  composer-ADDED glue with no stitched counterpart is dropped only after its correction
  attempt fails, and every drop increments `glue_dropped` (04b BL-R7).
- **Vignettes:** unchanged from the 04 amendments (verify support = `script_body`;
  vignette floor = the verbatim FIRST stitch sentence; corrector never changes a vignette
  sentence's `source_id`; bodyless citations stripped pre-verify).
- **THE NARRATIVE PASS (P1, 04b — the layer above the correct-loop):** after the
  correct-loop finalizes a stop, ≤2 pass calls (initial + one restore retry) rewrite the
  stop's verified sentence stream to the `01f` golden bar — orient the walker first;
  motivate every transition; unpack compound blocks (including floored raw-stitch
  splices) into single-idea sentences placed where the story needs them; voice each fact
  exactly once; surface the theme through transitions, never as a stated moral; stage
  quotes as a scene; keep disputes intact as pivots; locked voice. Pass input carries
  the verified sentences WITH citations plus the seated beats' bodies (**phrasing source
  only** — the prompt forbids adding any fact absent from the input sentences). Pass
  output is the same source-attributed sentence schema and re-enters the FULL gate, plus
  three pass-specific deterministic rules:
  - **Quote fidelity (fail-closed):** text inside quotation marks must appear verbatim
    (whitespace-normalized) in a cited beat's body.
  - **Glue promotion:** a glue-labeled sentence containing ANY pre-gate-class salient
    token is entailment-checked against the stop union (dispute/question instructions
    apply); token-free glue takes validation's existing scan. No entailment-free lane
    exists anywhere.
  - **Two-sided fact diff:** every pre-gate-class salient token in the pass INPUT's
    beat-cited sentences must appear in the pass OUTPUT; missing ⇒ ONE restore retry
    (which also lists any seated beat left owning no sentence); still missing ⇒ fallback.
    Calibrated by committed fixtures BOTH ways (`01f`: the Version-B→gold must-PASS pair
    AND the must-CATCH mutations).
  Any unsalvageable pass failure — correction exhausted, affirm, seated-beat violation,
  diff failure, budget exhausted, pass-call error — ships the stop's **pre-pass verified
  text** as `narrative_fallback`: whole-stop, deterministic, LLM-free; mixing pass prose
  with pre-pass prose is forbidden; there is NO floor inside pass output.
- **Both compose entry points** converge on this contract INCLUDING the pass: per-chapter
  preview (`compose_script_per_chapter`, `trips.py:769`) and the persisted whole-tour
  `/compose` (`compose_script`, `trips.py:518`) — the old drop/whole-revert ladders are
  retired in both.
- `ValidationReport` on the returned script passes; `coverage_failures` is always empty
  (machinery retired from this path). No `GLUE_REFLECTION` sentences are emitted.
- Per-stop compose status distinguishes fully-composed / corrected / floored (pre-pass
  counts) AND the pass outcome `narrative | narrative_fallback`; `narrative_fallback`
  unconditionally forces the tour's `flagged` editorial-review status.

## Constraints

- **Never-lose-a-fact:** enforced by FOUR deterministic mechanisms — the floor, the
  seated-beat invariant, the fact-preserving correction rule (under-cited → floor, never
  correction-strip), and the pass's two-sided fact diff + whole-stop fallback. Whole-stop
  revert and beat-content drop are removed. Recorded limit (04b R-V2): a dropped RELATION
  between still-present entities is not mechanically detectable — covered by the pass
  prompt, the FN battery, and AC-9.
- **Never-fabricate (AMENDED 2026-07-16, human ruling at the Scope-2 GO gate):** the
  entailment layer is calibrated to CHECKABLE-FACT violations only — a new entity /
  number / date / era / specific event or act, a changed or inverted stated fact,
  hedge- or dispute-flattening, or a question presupposing an unsupported fact as
  settled. Interpretive colour, motives, atmosphere, and loose relational glosses
  ("the Meurice DREW the writers" over "they stayed") are the composer's licence —
  "we are not making up facts, but the composer gets room to sound natural." Craft
  control of colour lives in the 3b pass prompt + AC-9, never in the gate. The
  deterministic layers below are unchanged; original text follows.
- **Never-fabricate:** the layer stack survives — (1) deterministic pre-gate fails closed
  on any year/number/entity token absent from cited bodies BEFORE any LLM verdict;
  (2) the verbatim shortcut passes ONLY a complete sentence-unit run of
  `split_sentences(script_body)`; (3) correction/trim re-enters the full per-sentence
  verify; (4) the floor and the pass fallback are already-verified text. The entailment
  prompt is CALIBRATED fusion-aware (04b D2a): support presented as one continuous
  source text; restating/reordering/splitting/combining stated facts = YES, **but a new
  relation between source facts is ADDED content = NO**; a sentence asserting flatly
  what the source hedges or disputes = NO; a question is YES only if the source supports
  what it presupposes. Calibration is MEASURED through the FULL production gate before
  the line restarts (Scope 2 GO gate): FN battery (the `01f` goldenized sentences, the
  01b s2/s10 fusions, 01d s8, the gold question — per-class pass definitions) and FP
  battery (entity_swap, POPULATED date_shift, FLUENT frankenfacts, hedge-strip/
  dispute-flatten, question-presupposition smuggles, glue-mislabel) with held-out
  non-Le-Meurice material; ZERO fabricating acceptances; the per-tour fabrication bound
  is measured on real pass output (shortcut hit rate collapses on novel prose).
- **Fusion ownership:** unchanged (a fused sentence failing bounded correction floors
  ALL cited beats; bounded double-voicing accepted).
- **Narrative flow (the value prop) — now a mechanism, not a hope:** the PASS is the
  flow layer; corrections remain rewrites in the locked narrator voice with surrounding
  context. Flow degradation is observable, never silent: pre-pass
  verified/corrected/floored counts + pass status + `glue_dropped` / `affirm_reject` /
  `pass_facts_restored` / `pass_fallback_reason` telemetry persist with every composed
  trip.
- **Fallback-rate is a measured GO criterion (04b BL-V6):** whole-stop sinking means
  stop survival ≈ (1−q)^n for n≈28 checked sentences; the Scope-3b live probe measures
  STOP-LEVEL pass rate on a multi-stop tour and its GO bar includes a fallback-rate
  ceiling (~≥90% survival target, set on reading). The redesign is a no-op if
  calibration does not clear it — the line stops again there.
- **Prod flow-quality guard:** as before (prevention / selection / detection); best-of-N
  ranks on pre-gate violations first, predicted correction need second, never the LLM
  verdict alone. An LLM flow-judge remains a telemetry-triggered follow-up.
- **Bounded cost:** ≤2 correction attempts per flagged sentence; per-tour pre-pass
  correction budget `2 × stop_count`; the PASS has its OWN lines — ≤2 pass calls per
  stop AND a separate `2 × stop_count` pass-correction budget (04b BL-R8/V6). Any
  exhaustion ⇒ floor (pre-pass) / `narrative_fallback` (in-pass). Deterministic
  termination everywhere (floor and fallback are LLM-free and always reachable).
- **Availability — a tour is NEVER refused when content exists:** ladder = verified →
  corrected → floored (per beat) → narrative pass → `narrative_fallback` (per stop) →
  grounded stitch (`stitched_fallback`, ONLY on a stop's compose-call failure; excluded
  from threshold math). A pass-call failure degrades to `narrative_fallback`, a
  correction-call failure to the FLOOR. The tourist always gets a tour; every fallback
  ships with an honest status + telemetry flag.
- **Worst case (recorded deviation, accepted 2026-07-15):** `narrative_fallback` ships
  Version-B-class verified prose (raw-stitch floors included) — below the `01f` bar but
  factual, never silent (forced `flagged`), and rate-gated by BL-V6's GO bar.
- **Offline bar:** `make test` runs green with mock clients (`MockNarrativePass` =
  identity — the Scope-0 goldens hold byte-identical), no network, no key_claims
  fixtures.
- **Compose-only blast radius:** stitcher, extraction pipeline, schema, and route-level
  dedup untouched. The composer prompt (`_COMPOSE_SYSTEM`) is also untouched — the pass
  is a new stage, not a composer rebuild (04b v2 revision note).

## Acceptance criteria

- **AC-1** Works when a live Le Meurice compose (repro config in the ticket) ships stop
  2 as PASS output (`narrative` status, not fallback), NOT byte-identical to the stitch,
  with the von Choltitz fusion surviving as a fusion (verified|corrected, never floored).
- **AC-2** Works when every fabrication negative-fixture ends corrected or floored —
  zero fabricated or inverted claims in shipped text. Fixture classes: invented
  name/date/fact; cross-POI vignette bleed; meaning-inverting truncation;
  attribution-strip; FRANKENFACT — including FLUENT frankenfacts (grammatical
  false-relation recombinations); POPULATED date_shift; hedge-strip/dispute-flatten;
  question-presupposition smuggle; glue-mislabel (factual assertion labeled glue →
  promoted and checked); flagged-glue with an invented proper noun.
- **AC-3** Works when no fact can be lost, proven by the four correct-loop fixtures
  (compound-packed fact; under-cited paraphrased fusion → floor; omitted beat → seated-
  beat invariant; floor-collateral fusion survives) — pass-side fact preservation is
  AC-12's diff fixtures.
- **AC-4** Works when a beat with `key_claims=()` gets full faithfulness checking (the
  `verify.py:279` skip is gone) — support is `script_body` alone.
- **AC-5** Works when a fused sentence citing beats A+B fails correction and BOTH beats
  floor to their verbatim post-dedup stitch sentences.
- **AC-6** Works when composed output contains no `GLUE_REFLECTION` sentences and no
  coverage machinery fires (empty `coverage_failures` on all paths).
- **AC-7** Works when, under the deterministic mock clients (including the identity
  `MockNarrativePass`), a stop whose every sentence verifies first-pass ships its
  beat-cited sentences byte-identical to today's passing output (pinned by the committed
  Scope-0 goldens; no re-pin needed).
- **AC-8** Works when `make test` passes offline, correction-call count per flagged
  sentence is asserted ≤ 2, AND the per-tour pre-pass budget is asserted: a fixture
  where every sentence is flagged floors the remainder once `2 × stop_count` corrections
  are spent.
- **AC-9** Works when the live Le Meurice output (AC-1's run) passes an acceptance
  review — the acceptance agent + a human judge it ONE coherent narration OF THE `01f`
  GOLDEN'S CHARACTER (orientation, motivated transitions, facts once, staged quotes,
  dispute pivot; no register break at correction seams). Tier-3 human sign-off — a
  ONE-TIME calibration gate: the run's counts become AC-10's thresholds.
- **AC-10** Works when the persisted `/compose` path stores per-stop
  verified/corrected/floored counts + pass status + tour-level status on
  Trip/ItineraryItem (additive), BOTH response models carry per-stop statuses + the tour
  rollup, statuses derive from gate counts
  (`composed | composed_corrected | composed_floored | narrative_fallback |
  stitched_fallback | stitched`), a `narrative_fallback` stop FORCES the tour's
  `flagged` status unconditionally, threshold-breaching tours are machine-flagged (the
  `flagged` filter + text badge), and the `glue_dropped` / `affirm_reject` /
  `pass_facts_restored` / `pass_fallback_reason` counters persist. `_compose_status`'s
  byte-equality heuristic is deleted.
- **AC-11** Works when systemic failures degrade per the ladder: (a) a compose client
  raising a MIX of errors on every call still yields a complete, servable tour (grounded
  stitch) with an honest fallback status, both paths, no user-facing error; (b) PARTIAL
  outage yields composed + `stitched_fallback` stops, fallback stops excluded from
  threshold math; (c) a correction-call failure degrades to the floor; (d) a PASS-call
  failure degrades to `narrative_fallback`, never an error; (e) the stitch is proven
  LLM-free.
- **AC-12 (the pass contract)** Works when: (a) under the identity mock, pipeline output
  is byte-identical to today (goldens green); (b) the two-sided diff fixtures hold —
  the (Version B → `01f`) pair PASSES and every `01f` must-catch mutation FAILS;
  (c) a quote mutated inside its quotation marks fails the quote-fidelity rule;
  (d) a factual assertion labeled glue is promoted and checked (rejected when
  unsupported); (e) every fallback reason (correction-exhausted | affirm | seated-beat |
  fact-diff | budget | pass-call-error) is reachable by fixture, each ships the intact
  pre-pass text, and no fixture hangs (≤2 pass calls + own correction line asserted);
  (f) the live multi-stop probe's stop-level fallback rate meets the GO ceiling set on
  reading (~≥90% survival) with ZERO fabricating acceptances.

## Concrete output example

Le Meurice stop (3 beats), after correct-loop + narrative pass:

```json
{
  "stop_idx": 2,
  "pre_pass_counts": {"verified": 6, "corrected": 2, "floored": 1},
  "pass_status": "narrative",
  "sentences": [
    {"text": "Here, at the corner of rue de Castiglione and rue de Rivoli, stands the Hotel Le Meurice.", "source_id": "85ebe707", "source_type": "beat"},
    {"text": "To understand how a hotel like this came to belong here, go back to the neighbourhood as it was when the nearby Tuileries was still the seat of power.", "source_id": "c9c90a74", "source_type": "beat"},
    {"text": "…", "source_id": "…", "source_type": "beat"}
  ],
  "stop_compose_status": "composed_corrected"
}
```

(Field placement illustrative — Stage 5 decides; the sentence TEXTS above are the `01f`
golden's opening, i.e. the pass's target character.)

## Downstream dependencies

- **Preview + persisted `/compose`:** both consume the gate + pass; the 422 refusal path
  disappears entirely. Mobile refusal handling becomes dead code (follow-up cleanup).
- **TTS/audio:** consumes the final accepted text unchanged (bake-once, post-acceptance).
  Note R-V9 (04b): per-sentence citations are support attribution, not provenance
  guarantees — TTS traceability reads accordingly.
- **Workbench:** consumes the persisted counts + pass statuses + threshold flag as the
  standing editorial review queue; `narrative_fallback` items always appear there.
- **Unblocks:** the `key_claims` teardown follow-up spec; the premium tour-tester loop.

## Open questions

None. (The Stage-3 probe question was answered by 01b/01d; the 04b re-open's three
approval questions — worst-case residual, mandate refinements, expanded goldenization —
were ACCEPTED by the human 2026-07-15.)
