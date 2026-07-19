# 05 — Implementation Plan: correct-don't-reject compose + verified narrative pass

**Date:** 2026-07-14 · **REGENERATED 2026-07-15** against `02-spec.md` + `03-scopes.md`
as amended per `04b-red-team-reopen.md` (v2.1, approved). · **Stage:** 5 (Plan) ·
**Thinking mode:** Implementation engineer
Scope 0 and Scope 1 sections are the historical record of completed work (condensed);
Scopes 2 / 3 / 3b / 4 / 5 / 6 are the live plan. The oracle for Scopes 2/3b/6 is
`01f-goldenized-acceptance-text.md`.

## How to run this plan (the `/team` handoff)

- **One scope = one `/team` run = one FRESH conversation.** Start each with:
  `/team Implement Scope N of specs/2026-07-13-compose-correct-dont-reject/05-plan.md — that
  file's Scope-N section (Parts A+B+C) is the full request; check state.json for progress.`
- The PO/Planner front half of `/team` is PRE-DONE by this spec (Stages 1–4 + the 04b
  re-open, human-approved). Each Part C states the rigor tier; `/team` starts at Developer
  and runs its full back half (QA undo-test → skeptics where stated → judge → acceptance
  where stated).
- Update `state.json` as each scope lands: `pending → in_progress → committed`.
- Order: `0 ∥ 1 (done) → 2 → 3 → 3b → 4 → 5 → 6`. NEVER start a scope whose deps aren't
  committed. **Deploy hold:** no Render deploy between Scope 2 and Scope 3 landing
  (Scope 2 alone makes live compose WORSE — more sentences under the checker while the
  OLD drop/revert ladder still runs; 2+3 are one release unit). 3b/4/5 each ship
  deployable improvements.
- **TWO measured GO gates guard the line** — Scope 2 (full-gate FN/FP calibration) and
  Scope 3b (stop-level fallback rate). A NO-GO on either STOPS the line at Stage 4;
  say so loudly and do not proceed to the next scope.
- Every scope: `make lint` zero errors; `make test` green (the bar) before commit; scope
  name in the commit message; read the staged diff.

**Stage-5 structural decision (dependency fix, flagged for the record):** the amended
Scope 2 GO battery must run the **FULL production gate** (pre-gate + shortcut +
entailment + correction routing — 04b BL-V1), but the pre-gate and the trim-acceptance
check were Scope-3 deliverables in the old plan. Resolution: Scope 2 builds them as
**pure, unit-tested verify-layer primitives** (no compose-loop wiring, no behavior
change to any compose path); Scope 3 wires them into the loop. The battery therefore
exercises the exact functions production will run, and Scope 2 stays a verify-layer
scope. The alternative (a harness-local reimplementation) risks a battery that measures
a gate production doesn't run — rejected.

**CRUD reality the implementer must know (read before coding, per Stage-5 rule):**
`src/api/crud/trips.py` — stops flow `route_script_to_stops` (:18) → `create_trip_with_stops`
(:77, `CREATE` Trip) → `_create_itinerary_items` (:141, `CREATE` items with UUIDs — no MERGE,
so no multi-city MERGE-key concern) → `mark_trip_composed` (:233) → `list_trips_for_profile`
(:265). ItineraryItems are DETACH-DELETEd on re-compose (`replace_trip_stops` :209) — new
properties ride the item lifecycle, no migration, legacy items read null via `coalesce`.
`compose_script_per_chapter` deliberately propagates client errors (compose.py:677-682
comment) — Scope 5 reverses this BY DESIGN; update the comment. `MockComposeClient` returns
stitched sentences + inserts reflections (compose.py:219-257) — Scope 3 commit 2 removes the
insertion. `MockNarrativePass` (Scope 3b) is the IDENTITY, so the committed Scope-0 goldens
stay binding through every scope with zero re-pinning (04b BL-R9: verified —
`_populate_also_cites` is idempotent; the mock path renders no prompts).

---

## Scope 0 — Golden Pin — **COMMITTED (23f52e0), historical record**

As executed: deterministic fixture tour; both entry points pinned byte-equal under
deterministic mocks in `tests/test_compose_golden.py`; goldens
(`tests/goldens/compose_per_chapter.json`, `compose_whole_tour.json`) committed first as
the frozen oracle, split (i) non-reflection / (ii) `GLUE_REFLECTION`. AC-7. Golden (ii)
retires with a note in Scope 3 commit 2; golden (i) must stay byte-green through every
scope (the identity `MockNarrativePass` preserves this — no re-pin, ever).

## Scope 1 — Le Meurice Live Probe — **COMPLETE (9fb2308), historical record**

As executed: `tools/diagnose_compose_correct_loop.py` + `make diag-compose-correct`;
verdict **NO-GO by the human on FN usability** (`01b-probe-transcript.md`) — corrections
faithful, floors safe, but the assembled text (Version B, `01c`) is a disjointed
narrative. FP ceiling 19/20 with the single acceptance judge-cleared. The evidence drove
the 04b re-open; the human's rewrite (`01e`) was goldenized as `01f` — the machine oracle
for everything below.

---

## Scope 2 — Gate Calibration + script_body-Only Faithfulness (the first GO gate)

Surface: `src/tour/verify.py` (+ a new sibling module for the deterministic primitives),
`src/tour/compose.py` (`_beat_support_signature` only), `src/tour/compose_metrics.py`,
`tools/`, `Makefile`, `tests/`. Binding contract: `02-spec.md` Inputs/Outputs item 1 +
Never-fabricate; `03-scopes.md` Scope 2; 04b D2a/D2b.

### Part A — Tasks

1. **Support re-base (body-only)** — `verify.py`: `_entailment_support` (:173-180)
   returns `script_body` texts only (key_claims dropped); DELETE the
   `if not any(b.key_claims ...)` skip (:279-280) — a `key_claims=()` beat is now fully
   checked; vignette beats ENTER the verify support map (today `beats_by_id` at the
   compose call sites excludes them from support — accept a `beats_by_id` that includes
   them or a parallel vignette map; smallest diff wins; the vignette EXCLUSION from the
   Phase-2 stop union at :302-303 is behavior to KEEP). The reflection path
   (`_visited_claims`, the fail-closed reflection branch :265-271) is UNTOUCHED — Scope 3
   commit 2 deletes it. Success: Part B tests 1/5 flip red→green.
2. **Protocol rename** — `FaithfulnessChecker.entails(key_claims=…)` →
   `entails(support=…)` (:71), Mock/Haiku implementations and every caller; the Protocol
   is structural, so grep for keyword AND positional callers (`tests/`, `tools/`).
3. **Sentence-unit verbatim shortcut** — replace the substring check (:281-283): a
   sentence shortcuts iff its normalized text equals ONE complete unit or a CONTIGUOUS
   run of complete units of `split_sentences(b.script_body)` (generation.py:113) for a
   cited beat. Kills the negation-truncation / attribution-strip acceptances (a fragment
   of a corpus sentence no longer passes verbatim).
4. **Calibrated entailment prompt** — rewrite `_ENTAILMENT_PROMPT` (:92-97) per 04b D2a:
   support presented as one continuous **SOURCE TEXT** (bodies joined), not a claims
   list; restating / reordering / splitting / combining facts stated in the source =
   YES, **but combining is YES only when the joining relation is itself stated — a new
   relation between source facts is ADDED content ⇒ NO**; a sentence asserting flatly
   what the source hedges or disputes ⇒ NO; a QUESTION is YES only if the source
   supports what it presupposes. Keep temperature=0 and the fail-closed YES-prefix
   parse (:128-137).
5. **Parity re-base (same commit)** — `_beat_support_signature` (compose.py:106-112)
   and `compose_metrics` go body-only in the SAME commit (the support-derivation parity
   invariant, verify.py:246-247) — the union that rescues must equal the union that gets
   cited and measured.
6. **Deterministic verify-layer primitives** (new module, e.g.
   `src/tour/verify_gate.py` — pure functions, unit-tested, NO compose-loop wiring; see
   the Stage-5 structural decision above):
   (a) **salient-class extractor** — pre-gate token class = 4-digit years / numbers /
   proper-noun tokens (reuse `_CAP_TOKEN_RE`/`_YEAR_RE` + sentence-head handling,
   validation.py:36-70, and `_canonicalize_dates`, claim_dedup.py:84-103); the <3-char
   blind spot ("WH", "II") is a RECORDED limit, not fixed here;
   (b) **pre-gate** — `pregate_violations(sentence_text, cited_bodies) -> violations`:
   any salient-class token absent from the cited bodies' union fails closed, zero LLM;
   (c) **trim-acceptance check** — `is_valid_trim(original, trimmed, flagged_tokens) ->
   bool`: no added tokens AND every removed content token ∈ the flagged unsupported set
   (04b D2c) — anything else is NOT a trim;
   (d) **correction router decision** — `route_flagged_sentence(sentence, declared_bodies)
   -> under_cited | correctable`: under-cited (declared citations' bodies do not cover
   the sentence's salient tokens) routes to the floor, never to correction. Scope 3
   WIRES this function — the battery and production run the same routing code.
7. **Calibration battery harness** — `tools/calibrate_gate.py` + Makefile target
   `calibrate-gate` (dry-run default printing the cost estimate; `GO=1` runs live —
   follow the `diag-compose-correct` pattern, Makefile:530). The harness runs each
   battery item through the FULL gate in production order: pre-gate → sentence-unit
   shortcut → calibrated entailment (live Haiku) → correction ROUTING decision via the
   SAME Scope-2 primitives production will wire (`route_flagged_sentence` +
   `is_valid_trim` — never a harness-local reimplementation; trim-class items execute a
   real Opus trim and the mechanical acceptance check).
   Fixture sources: `01f` sentences (goldenized — score against THIS text, not 01e),
   01b s2/s10, 01d s8, the gold question, + FP mutations generated from the same beats,
   + ≥1 held-out non-Le-Meurice stop (NYC corpus, local Neo4j :7687). Per-class PASS
   definitions printed per item: `entailment-YES` vs `ships-after-trim` vs
   `promoted-glue` (glue items assert the PROMOTION DECISION — salient-token glue routes
   to the checked lane; the full promotion machinery is 3b's). Analysis note: control
   for word-form dates before attributing FN classes (04b BL-V7).
8. **Run the battery + record the verdict** — scorecards written to
   `02b-calibration-scorecard.md` in the spec folder: FN per-class table; FP
   zero-acceptance table (classes: entity_swap, POPULATED date_shift, FLUENT
   frankenfacts, hedge-strip/dispute-flatten, question-presupposition smuggle,
   glue-mislabel). **GO bar: all three known FNs recovered (01b s2, 01b s10, 01d s8);
   the `01f` text ships whole through the full gate; ZERO fabricating acceptances.**
   Record GO/NO-GO; a NO-GO stops the line at Stage 4. The FP battery ALSO includes a
   `causal-relation-invention` class (co-location stated → causation asserted), seeded
   from the five real examples the human's editorial review caught on the live demo
   (`01g-narrative-pass-demo.md` §B bucket 1 — "drew an English clientele", "the street
   bent itself", "wanted more than newspapers", "drew the writers", "most famous story").

**NOT to touch:** the repair ladders (`drop_failing_sentences`/`repair_composed` and the
compose_gate rungs), reflections/`_visited_claims`, `_COMPOSE_SYSTEM`, claim_dedup's
route-level dedup, trips.py, mobile.

### Part B — Tests (AC-4; committed RED-first where marked, frozen before implementing)

- `key_claims=()` beat, rewritten sentence → CHECKED (RED under HEAD — the :279 skip
  passes it today) — the undo-test anchor.
- Negation-truncation fragment AND attribution-strip fragment of a corpus sentence →
  shortcut REFUSES, sentence goes to entailment (RED under HEAD).
- Unchanged full corpus sentence → shortcut passes, ZERO checker calls (assert via
  `MockFaithfulnessChecker.calls`).
- Contiguous two-sentence run of a body → passes; same words resegmented mid-sentence →
  refused.
- Rewritten vignette-cited sentence → CHECKED (RED under HEAD); vignette beats still
  EXCLUDED from the Phase-2 stop union (existing behavior pinned).
- Pre-gate unit tests: absent year / absent number / absent proper noun each fail
  closed; all-tokens-present passes; "WH"/"II" invisibility pinned as a recorded-limit
  test; word-form ordinal handled per `_canonicalize_dates` semantics.
- Trim-check unit tests: valid garnish-removal trim accepted; hedge-dropping "trim"
  REJECTED (dispute-flatten guard); token-adding "trim" rejected.
- Both goldens byte-green (`tests/test_compose_golden.py`).
- Battery: live evidence, not pytest — the scorecard artifact is the deliverable
  (Part A task 8).

### Part C — `/team` prompt (Tier 2, live-spend + GO gate)

> Implement Scope 2 (Gate Calibration + script_body-only faithfulness) of
> specs/2026-07-13-compose-correct-dont-reject/05-plan.md — that file's Scope-2 section
> (Parts A/B) is the full request; binding contract = 02-spec.md (Outputs item 1 +
> Never-fabricate) and 04b-red-team-reopen.md D2a/D2b — read all three first, plus
> 01f-goldenized-acceptance-text.md (the oracle the battery scores against). Stages 1–4
> are pre-approved; start at Developer. **Tier 2**: QA undo-test (restore the verify.py:279
> skip → the key_claims=() test must go RED), 1-2 skeptics on the two anti-fabrication
> surfaces (the sentence-unit shortcut rewrite and the calibrated entailment prompt +
> battery design — check the FP classes are real attacks, not strawmen; 04b BL-R2), judge
> BEFORE the live battery run (it spends Haiku + a few Opus calls — print the cost
> estimate) and before commit. Files: src/tour/verify.py, new src/tour/verify_gate.py,
> src/tour/compose.py (_beat_support_signature ONLY), src/tour/compose_metrics.py,
> tools/calibrate_gate.py, Makefile, tests/test_tour_verify.py. Do NOT touch: the repair
> ladders, reflections/_visited_claims, _COMPOSE_SYSTEM, claim_dedup route-dedup,
> trips.py, mobile. The new verify_gate primitives (pre-gate, salient-class extractor,
> trim-acceptance) are PURE functions with unit tests — no compose-loop wiring (Scope 3
> wires them). Tests committed RED-first where Part B marks them, then frozen. Battery
> runs through the FULL gate in production order and writes
> 02b-calibration-scorecard.md; GO bar = all three known FNs recovered + 01f ships whole
> + ZERO fabricating acceptances. Report the GO/NO-GO verdict loudly — a NO-GO stops the
> whole line at Stage 4; the human reads the scorecards and rules. Verification:
> `make test-file FILE=tests/test_tour_verify.py`, both goldens byte-green, full
> `make test` + `make lint` zero. WARNING for your final report: this scope alone makes
> live compose WORSE — deploy hold until Scope 3 lands (state it). Before starting,
> confirm you understand the full scope and flag any conflicts with the existing
> codebase or assumptions you are making.

**Estimated sessions:** 1–2

---

## Scope 3 — The Corrector + Floor (the correct-loop core; two commits)

Surface: `src/tour/compose.py`, `src/tour/compose_gate.py`, new
`src/tour/compose_correct.py`, `src/tour/verify.py` + `src/tour/reflection.py` (commit 2),
`tests/`. Binding contract: `02-spec.md` Outputs 1-3 + Glue/Vignettes + Constraints;
`03-scopes.md` Scope 3; 04b D2c/D2d, BL-R7, BL-V2.

### Part A — Tasks (commit 1: corrector+floor; commit 2: reflections removal)

1. **Correct-loop module** — new `src/tour/compose_correct.py`: the per-sentence ladder
   over a verified whole-tour report. Wire the Scope-2 primitives: pre-gate runs BEFORE
   any LLM verdict (a pre-gate violation is flagged without an entailment call);
   verbatim shortcut and calibrated entailment as landed in Scope 2.
2. **Correction router** — for each flagged sentence: route via Scope-2's
   `route_flagged_sentence` (do NOT reimplement): under-cited → straight to the FLOOR of
   the stop-union beats owning the uncovered tokens (fact-preserving rule — under-cited
   is NEVER correction-stripped); else ≤2 correction attempts, **attempt 1 = TRIM** (LLM-executed;
   mechanically accepted ONLY via Scope-2 `is_valid_trim`; a failed acceptance counts as
   the attempt-2 full rewrite — 04b D2c), attempt 2 = narrator-voice rewrite constrained
   to cited bodies with stop context in-prompt; every attempt re-enters pre-gate +
   entailment + forbidden/traceability. **Affirm detection:** a correction returning
   ~identical text (use `_normalize_for_verbatim` equality after trivial-space fold)
   routes to floor + increments `affirm_reject` — NO escalation ship-path (04b D2d).
   Per-tour budget `2 × stop_count` correction calls; concurrent across sentences
   (the `_run`/ThreadPoolExecutor pattern, compose.py:709-713).
3. **The floor** — replace a flagged/exhausted sentence's OWNING beats' sentences with
   each beat's verbatim post-dedup STITCH sentences (from `by_stop`, already in scope at
   the ladder site), composer-chosen position; **collateral subset rule** (a floor
   replaces only sentences whose FULL citation set ⊆ the floored-beat set); a fused
   sentence failing correction floors ALL cited beats (bounded double-voicing accepted).
   **Glue:** a flagged glue sentence gets ONE correction attempt (same trim-then-rewrite
   ladder, glue-whitelist constrained) BEFORE any drop; still-failing composed glue
   floors to the stitched glue of the same `(stop_idx, source_id)`; composer-ADDED glue
   with no stitched counterpart drops only after its failed attempt; every drop
   increments `glue_dropped` (04b BL-R7). **Vignettes:** floor = the verbatim FIRST
   stitch sentence; corrector never changes a vignette sentence's `source_id`; bodyless
   citations stripped pre-verify. **Seated-beat invariant sweep** last: every beat in the
   stop's compose request owns ≥1 shipped sentence (source_id or also_cites); an
   unowned beat's stitch block floors in adjacent to its POI's block.
4. **`_populate_also_cites` salient-class restriction** (compose.py:115-179) — token
   justification restricted to the PRE-GATE salient class (years/numbers/proper-noun
   tokens via the Scope-2 extractor), NOT the full `_signature` bag (04b BL-V2: the
   unrestricted repair manufactures false citations from common tokens — fixture: the
   "second" case must NOT gain a citation). Applies at ALL call sites (one function, one
   behavior); union-rescue citation gain = the minimal token-justified subset.
5. **Wire into `compose_script_per_chapter`** — loop shape: assemble → verify WHOLE tour
   → correct/floor per flagged sentence (concurrent) → re-verify affected checks →
   recompute `_sum_audio` LAST → emit per-stop `{verified, corrected, floored}` counts +
   `glue_dropped`/`affirm_reject` on the gate result (the raw data Scopes 3b/4 consume —
   emission is THIS scope's job). DELETE the `drop_failing_sentences` → `repair_composed`
   → `ComposeVerificationError` ladder from this path (compose.py:769-781) and coverage
   machinery from this path (`coverage_failures` always empty); best-of-N
   `_local_penalty` re-ranks on pre-gate violations FIRST, then faithfulness-failure
   count — never an LLM verdict alone, and it never runs the corrector.
   `compose_script` (whole-tour) is UNTOUCHED until Scope 5.
6. **(Commit 2) Reflections removal** — delete slot machinery from the compose path:
   `reflection_slots` wiring, `visited_claims_by_slot`, the prompt's REFLECTION section,
   `MockComposeClient`'s insertion (compose.py:249-256), `_is_transit_sentence`,
   `_reflection_text`, reflection.py, `_visited_claims` + the fail-closed reflection
   branch in verify.py (:140-164, :265-271). KEEP the `GLUE_REFLECTION` label
   (generation.py:68 — old persisted scripts may carry it). Golden (ii) test retired
   with a note; golden (i) untouched and byte-green. Zero dead code (lint bar).
7. **Fixture battery** — Part B, committed RED-first as its own checkpoint where
   assertable against HEAD, then frozen.

**Skeptic panel (2–4, mixed models) on the full diff BEFORE commits are pushed — this is
the danger half of the whole feature.**

**NOT to touch:** claim_dedup's route-level dedup (`suppress_repeated_claims`/
`suppress_exact_repeats`), the generation.py stitcher, trips.py endpoints (Scopes 4/5),
`_COMPOSE_SYSTEM` (the composer is NOT rebuilt — 04b v2 revision note), the goldens'
fixture. The 3→5 window: whole-tour `compose_script` still runs the OLD ladder after
this scope — intentional; Scope 5 converges it.

### Part B — Tests (AC-2, 3, 5, 6, 8 — `tests/test_tour_recompose.py`)

- **AC-3 quartet:** (a) compound-packed fact ships + sibling sentences keep composed
  prose (RED under main — today the whole stop reverts); (b) under-cited paraphrased
  fusion → floored, fact ships; (c) omitted beat → seated-beat invariant floors it in;
  (d) floor-collateral fusion (cites A+B, only A floors) SURVIVES.
- **AC-2 battery** (each: fabricated text NEVER ships — ends corrected or floored):
  invented name/date/fact; cross-POI vignette bleed; meaning-inverting truncation;
  attribution-strip; broken-grammar frankenfact AND **FLUENT frankenfact** (grammatical
  false-relation recombination); **POPULATED date_shift**; **hedge-strip /
  dispute-flatten**; **question-presupposition smuggle**; **glue-mislabel** (factual
  assertion labeled glue — the checked-lane routing decision); flagged glue with an
  invented proper noun → floors to stitched glue.
- **AC-5:** A+B fusion fails correction → BOTH beats floor to their verbatim post-dedup
  stitch sentences.
- **AC-6:** no `GLUE_REFLECTION` in composed output; `coverage_failures == ()` on every
  path.
- **AC-8 (pre-pass lines):** per-sentence ≤2 correction calls (counting stub client);
  all-flagged tour → floors the remainder once `2 × stop_count` is spent, call count ==
  budget, never hangs.
- **Trim mechanics:** separable-garnish trim accepted mechanically; hedge-dropping
  "trim" rejected AS A TRIM (counts as the full rewrite); token-adding trim rejected.
- **Affirm:** stub corrector returning identical text → sentence floors,
  `affirm_reject` increments, no third call.
- **Glue ladder:** flagged glue corrected on attempt 1 → ships; still-failing → floors
  to stitched counterpart; composer-added glue → dropped only after failed attempt,
  `glue_dropped` increments.
- **Citation repair:** the "second" false-citation fixture (04b BL-V2) — sentence must
  NOT gain the fashion beat; a genuine year-justified fusion still gains its beat.
- **Rescue chain (04-red-team R-4):** union-rescued sentence gains ONLY the minimal
  token-justified subset; when its correction then fails, the floor covers only those
  beats — never the whole stop.
- **Audio:** floored fixture → `total_audio_seconds` recomputed (≠ stale pre-floor).
- **Counts:** per-stop verified/corrected/floored emission matches the fixture's known
  outcome.
- Types: unit with stub checker/client (rejecting, accepting, flaky-sequence,
  affirming, error-raising stubs). Golden (i) byte-green both commits; golden (ii)
  retired in commit 2 with a note.

### Part C — `/team` prompt (Tier 3 — the danger half)

> Implement Scope 3 (Corrector + Floor) of
> specs/2026-07-13-compose-correct-dont-reject/05-plan.md — that file's Scope-3 section
> (Parts A/B) is the full request; binding contract = 02-spec.md Outputs/Constraints as
> amended per 04-red-team.md AND 04b-red-team-reopen.md (D2c trim, D2d affirm, BL-R7
> glue, BL-V2 citation restriction) — read all of them first. Stages 1–4 pre-approved;
> start at Developer. **Tier 3**: QA undo-test on the AC-3(a) fixture (revert the ladder
> → RED), FULL skeptic panel (2–4, different models) on the complete diff before push,
> judge before EACH of the two commits, acceptance agent on the workbench demo. TWO
> commits: (1) corrector+floor, (2) reflections removal — scope name in both messages.
> Files: src/tour/compose.py, src/tour/compose_gate.py, NEW src/tour/compose_correct.py,
> verify.py + reflection.py (commit 2 only), tests/. Scope 2 landed the verify-layer
> primitives (pre-gate, salient-class extractor, trim-acceptance in verify_gate) — WIRE
> them, do not reimplement. Do NOT touch: claim_dedup route-dedup, generation.py
> stitcher, trips.py endpoints, _COMPOSE_SYSTEM (the composer is NOT rebuilt), the
> goldens' fixture. Whole-tour compose_script keeps the OLD ladder — intentional (Scope
> 5 converges it). Tests committed RED-first where assertable against HEAD, then frozen.
> Verification: `make test-file FILE=tests/test_tour_recompose.py`, golden (i)
> byte-green, full `make test` + `make lint` zero. Demo: workbench preview on a
> mock-composed fixture — the stop shows corrected/floored prose IN PLACE, no shotgun
> revert (screenshot). Before starting, confirm Scope 2 is committed GO per state.json,
> and confirm you understand the fact-preserving correction rule (under-cited → floor,
> NEVER correction-strip) — it is the load-bearing fix for the red-team's executed
> refutation. Flag any conflicts or assumptions before coding.

**Estimated sessions:** 2–3

---

## Scope 3b — The Verified Narrative Pass (NEW — the 04b core; the second GO gate)

Surface: new `src/tour/narrative_pass.py`, `src/tour/verify_gate.py` (the three
pass-specific deterministic rules + the word-form-ordinal date canonicalizer, kept
LOCAL to the diff's token class), `src/tour/compose.py` (wiring), `tools/`, `Makefile`,
`tests/`.
Binding contract: `02-spec.md` P1 (THE NARRATIVE PASS) + Constraints; `03-scopes.md`
Scope 3b; 04b §0 P1 complete.

### Part A — Tasks

1. **Client + mock** — `NarrativePassClient` Protocol (one pass call: request →
   source-attributed sentence tuple, same schema as compose) + **`MockNarrativePass` =
   IDENTITY** (returns the input sentences unchanged; records calls) +
   `AnthropicNarrativePass` (Opus, deferred import, streamed, structured output —
   follow `AnthropicComposeClient`, compose.py:467-536, including the max_tokens
   truncation ValueError). Injected via the same DI seam as the compose client
   (`COMPOSE_PROVIDER` selects mock/anthropic for both).
2. **Pass request + prompt (the `01f` bar)** — input: the stop's verified sentence
   stream WITH citations (source_id + also_cites per sentence), the seated beats'
   `script_body` (**phrasing source ONLY — the prompt forbids adding any fact absent
   from the input sentences**; bodies still contain repeats the route-dedup removed —
   04b BL-R6/R-V10), POI name, `tour_context`, lenses. The transform, each item
   observable in `01f`: orient the walker first; motivate every transition; unpack
   compound blocks (including floored raw-stitch splices) into single-idea sentences
   placed where the story needs them; voice each fact exactly once; surface the theme
   through transitions, never a stated moral; stage quotes as a scene; keep disputes
   intact as pivots; locked voice rules verbatim from `_COMPOSE_SYSTEM`'s VOICE/CRAFT
   sections (never "imagine"; no meaning-stating). PLUS the seven editorial rules from
   the human's live-demo review (`01g-narrative-pass-demo.md` §C — facts beside each
   other never welded into unsourced causation; no unsourced superlatives; pronoun
   discipline; audio pacing / one idea per sentence; quote-run staging; attribute vivid
   corpus judgments to their source; restraint on large claims). Output schema = the
   compose sentence schema (text/source_id/source_type/stop_idx/also_cites).
3. **Re-gate + the three pass-specific rules** — pass output → `_populate_also_cites`
   (salient-restricted, landed in Scope 3) → FULL gate: pre-gate → sentence-unit
   shortcut → calibrated entailment → bounded correction incl. trim (drawing on the
   pass's OWN correction line). Plus, in `verify_gate.py`:
   (a) **Quote fidelity (fail-closed):** text inside quotation marks (handle “ ” and
   ASCII quotes) must appear verbatim (whitespace-normalized) in a cited beat's body;
   (b) **Glue promotion:** a glue-labeled pass sentence containing ANY pre-gate-class
   salient token is PROMOTED to the checked lane (entailed against the stop union;
   dispute/question instructions apply; correctable/trimmable like a beat sentence);
   token-free glue takes validation's existing scan — NO entailment-free lane;
   (c) **Two-sided fact diff:** every pre-gate-class salient token in the pass INPUT's
   beat-cited sentences must appear in the pass OUTPUT; missing ⇒ ONE restore retry
   whose prompt lists BOTH the missing facts AND any seated beat left owning no sentence
   (the `dropped_facts_you_must_restore` pattern, compose.py:452-456); still missing ⇒
   fallback. **Word-form ordinal canonicalization ("19th" ↔ "nineteenth") is a
   verify_gate-LOCAL function composed WITH `_canonicalize_dates`, used only by the
   diff's token class — do NOT modify claim_dedup.py: `_signature` (claim_dedup.py:106-110)
   feeds route-level dedup, which the spec locks untouched.** "WH"/"II" <3-char blind
   spot recorded, covered by quote rule + entailment, not the diff.
4. **Sink ladder + budgets** — any unsalvageable pass failure sinks the WHOLE stop to
   `narrative_fallback` = the intact pre-pass verified text: reasons enumerated
   `correction-exhausted | affirm | seated-beat | fact-diff | budget | pass-call-error`.
   An in-pass affirm ALSO increments `affirm_reject` (04b: both stages). This scope
   lands the pass-call-error catch on the per-chapter path; Scope 5 extends the routing
   to the converged whole-tour path + endpoint-level tests.
   Mixing pass prose with pre-pass prose is FORBIDDEN; there is NO floor inside pass
   output. Budgets: ≤2 pass calls per stop (initial + restore retry) AND a separate
   `2 × stop_count` pass-correction line (NOT shared with pre-pass — 04b BL-R8/F4).
   Fallback is whole-stop, deterministic, LLM-free — termination unconditional.
5. **Wiring + telemetry** — the pass runs per stop after the Scope-3 correct-loop
   finalizes it, parallelized per stop, in `compose_script_per_chapter` (Scope 5
   converges the whole-tour path); per-stop pass outcome `narrative |
   narrative_fallback` + `pass_facts_restored` + `pass_fallback_reason` + cross-stop
   overlap telemetry (detection net for body-sourced repeat restoration, R-V10) emitted
   alongside the Scope-3 counts.
6. **`01f` fixtures as tests** — from `01f-goldenized-acceptance-text.md`: must-PASS
   diff pair (`01c` Version B → `01f`); must-CATCH mutations (delete "Galignani",
   delete "224", change "224"→"242"); quote-fidelity fixture (one word mutated INSIDE a
   quoted span fails; the gold's outside-quote rewording passes); glue-promotion fixture
   (unsupported factual "glue" rejected; the gold's token-free bridge passes the scan).
7. **Live GO gate** — `tools/probe_narrative_pass.py` + Makefile target (dry-run
   default, `GO=1` live, cost printed): run the full pipeline on a real MULTI-STOP tour
   (dev :7687); measure the STOP-LEVEL fallback rate and audit every gate acceptance on
   pass output (novel prose — the shortcut hit rate collapses, so this measures the real
   per-tour fabrication exposure). Write `03b-pass-probe.md`: per-stop before/after
   text, fallback reasons, fabrication audit. **GO bar: stop survival ≥ the ceiling set
   on reading (~90%) AND zero fabricating acceptances.** NO-GO stops the line at
   Stage 4 — the pass must not ship as a de-facto no-op.

**NOT to touch:** `_COMPOSE_SYSTEM` / the composer, the stitcher, the pre-pass floor
rules (Scope 3's), trips.py endpoints (Scope 4/5), persistence.

### Part B — Tests (AC-12 — `tests/test_narrative_pass.py`)

- **(a) Identity-mock equality:** under `MockNarrativePass`, pipeline output
  byte-identical to the pre-pass stream; golden (i) stays byte-green untouched
  (golden (ii) was retired in Scope 3 commit 2).
- **(b) Two-sided diff:** the (Version B → `01f`) pair PASSES (forces the word-form
  ordinal extension — RED until `_canonicalize_dates` handles "19th"/"nineteenth");
  each `01f` must-catch mutation FAILS the diff.
- **(c) Quote fidelity:** a quote mutated inside its quotation marks fails; the gold
  text passes whole.
- **(d) Glue promotion:** a factual assertion labeled glue is promoted and rejected
  when unsupported; token-free glue takes the scan lane; NO path skips both.
- **(e) Sink ladder:** EVERY fallback reason reachable by fixture (stub pass clients:
  fact-dropping → restore retry → still-dropping; affirming corrector; output leaving a
  seated beat unowned; budget-exhausting; error-raising) — each ships the INTACT
  pre-pass text (byte-compare), sets the right `pass_fallback_reason`, never mixes, and
  never hangs (≤2 pass calls + own correction line asserted via counting stubs). The
  affirm fixture asserts the in-pass `affirm_reject` increment. The restore retry that
  SUCCEEDS increments `pass_facts_restored` and ships `narrative`.
- **(f)** is the live probe (Part A task 7) — evidence artifact, not pytest.
- `make test` full offline bar; `make lint` zero.

### Part C — `/team` prompt (Tier 3 — new LLM surface + GO gate)

> Implement Scope 3b (Verified Narrative Pass) of
> specs/2026-07-13-compose-correct-dont-reject/05-plan.md — that file's Scope-3b section
> (Parts A/B) is the full request; binding contract = 02-spec.md P1 + Constraints and
> 04b-red-team-reopen.md §0 (read both fully), oracle =
> 01f-goldenized-acceptance-text.md. Stages 1–4 pre-approved; start at Developer.
> **Tier 3**: QA undo-test (disable the two-sided diff → the must-catch mutation tests
> go RED), skeptic panel (2–4, mixed models) on the three deterministic rules (quote
> fidelity, glue promotion, two-sided diff — attack them: can a fabrication or a fact
> loss slip each?), judge before the live probe spend (print the cost estimate) AND
> before commit, acceptance agent reads one stop's before/after from the probe. Files:
> NEW src/tour/narrative_pass.py, src/tour/verify_gate.py (three pass rules + the
> LOCAL word-form-ordinal canonicalizer), src/tour/compose.py (per-chapter wiring),
> tools/probe_narrative_pass.py, Makefile, tests/test_narrative_pass.py. Do NOT touch: _COMPOSE_SYSTEM/the composer, the
> stitcher, Scope-3's floor rules, trips.py, persistence, mobile. HARD RULES you must
> not soften: MockNarrativePass is the IDENTITY (golden (i) must stay byte-green with
> ZERO re-pinning — golden (ii) was retired in Scope 3; if golden (i) changes, you broke
> the contract); no floor inside pass output; no mixing pass and pre-pass prose; the
> pass budget lines are SEPARATE from pre-pass; word-form ordinal handling is
> verify_gate-LOCAL — claim_dedup.py is OFF-LIMITS (route-dedup rides _signature).
> Verification: `make test-file FILE=tests/test_narrative_pass.py`, golden (i),
> full `make test` + `make lint` zero; then the live GO probe → write
> 03b-pass-probe.md and report the fallback-rate + fabrication scorecard loudly — the
> human reads it and rules GO/NO-GO; a NO-GO stops the line at Stage 4. Before starting,
> confirm Scopes 2 AND 3 are committed per state.json, and flag any conflicts or
> assumptions before coding.

**Estimated sessions:** 2

---

## Scope 4 — Quality Telemetry + Threshold Flag

Surface: `src/tour/compose.py` (gate outputs), `src/api/crud/trips.py`,
`src/api/models/trips.py`, `src/api/routes/trips.py`, `frontend/tour-preview.html`,
docs §16 note, `tests/`. Binding contract: AC-10 as amended; `03-scopes.md` Scope 4.

### Part A — Tasks

1. **Status derivation** — per-stop status derives from gate counts AND pass outcome:
   `composed | composed_corrected | composed_floored | narrative_fallback |
   stitched_fallback | stitched` (`refused` retires); tour rollup = worst stop class.
   **A `narrative_fallback` stop FORCES the tour's `flagged` status UNCONDITIONALLY**
   (bypasses threshold math).
2. **Persist (4 layers)** — `route_script_to_stops` stop dicts → `_create_itinerary_items`
   Cypher (item properties) + Trip-level status (`mark_trip_composed` /
   `create_trip_with_stops`) → `list_trips_for_profile` (`coalesce` for legacy) →
   pydantic models (`GeneratedStop`, `TripComposeResponse`; `attempts` REPURPOSED as
   corrections-spent — additive-safe, mobile only read it in the dead 422 path; update
   its Field description). Persisted per stop: verified/corrected/floored counts, pass
   status, floored-audio seconds; per tour: rollup status, `flagged`, and the counters
   `glue_dropped` / `affirm_reject` / `pass_facts_restored` / `pass_fallback_reason`.
3. **Preview response-only** — `TripPreviewStop`/`TripPreviewResponse` carry per-stop
   statuses + the tour rollup; one structured log line per preview compose (statuses +
   counts, never payloads).
4. **Delete `_compose_status`** (trips.py:693-705) — the byte-equality heuristic dies;
   statuses come from the gate.
5. **Threshold flag** — config constants (provisional; Scope 6 calibrates, with a
   telemetry-review trigger comment); `flagged` filter param on the trips list endpoint;
   TEXT badge on tour-preview.html (a11y: text, not color-only).
6. **Data-inventory note** — one line in SECURITY_PRIVACY_PRACTICES §16 (additive
   status strings + counters; no new PII).

**NOT to touch:** the 422 path (Scope 5 deletes it — it still exists here), verify /
corrector / pass internals, mobile.

### Part B — Tests (AC-10 — `make test-local`, Neo4j :7688)

- Persistence round-trip: mock-compose a trip → counts + pass status on items, rollup +
  counters on trip → list endpoint returns them; legacy trip (no properties) reads
  null-clean; re-compose (DETACH DELETE) round-trip keeps properties consistent.
- Threshold fixtures both sides → flagged vs clean; `flagged` filter returns only
  breachers; **a within-threshold tour containing ONE `narrative_fallback` stop is
  STILL flagged** (the unconditional rule — the key new fixture).
- Preview response carries statuses; `_compose_status` gone (import error / grep-level
  assert).
- Status derivation table-tested: each count/pass-outcome combination → expected enum
  value.

### Part C — `/team` prompt (Tier 2)

> Implement Scope 4 (Quality Telemetry + Threshold Flag) of
> specs/2026-07-13-compose-correct-dont-reject/05-plan.md — that file's Scope-4 section
> (Parts A/B) is the full request; AC-10 in 02-spec.md (as amended per 04b: pass
> statuses, unconditional narrative_fallback flag, four new counters) is the contract.
> Stages 1–4 pre-approved; start at Developer. Tier 2 (QA undo-test: remove the
> unconditional-flag rule → its fixture goes RED; judge before commit; acceptance agent
> on the badge demo). Files: src/tour/compose.py (gate/pass output threading ONLY),
> src/api/crud/trips.py, src/api/models/trips.py, src/api/routes/trips.py,
> frontend/tour-preview.html, the §16 doc note, tests. Do NOT touch: the 422 path (Scope
> 5 owns its deletion — it still exists here), verify/corrector/pass internals, mobile.
> All persisted properties are ADDITIVE; ItineraryItems are CREATE'd with UUIDs (no
> MERGE keys) and DETACH-DELETEd on re-compose — legacy items read null via coalesce.
> Scopes 3/3b already EMIT every count and status this scope persists — thread them
> outward, roll up, persist; do not recompute. Neo4j tests via `make test-local` (7688).
> Verification: `make test-local`, full `make test` + `make lint` zero. Demo: curl the
> flagged-filter endpoint + screenshot the text badge on tour-preview.html for a flagged
> vs clean preview (real browser, per the visibility contract). Before starting, confirm
> Scope 3b is committed per state.json, and flag any conflicts or assumptions.

**Estimated sessions:** 1

---

## Scope 5 — Entry-Point Convergence + Never-Fail Availability

Surface: `src/tour/compose.py`, `src/tour/compose_gate.py`, `src/api/routes/trips.py`,
`tests/test_trip_api.py`, `tests/test_tour_compose.py`. Binding contract: AC-11 + the
Availability ladder in `02-spec.md`; `03-scopes.md` Scope 5.

### Part A — Tasks

1. **Converge `compose_script`** — the whole-tour path becomes a thin wrapper over the
   per-chapter corrector gate + pass (recommended: single-chapter-set call preserving
   its signature; judge reviews the seam) — the old drop/revert + `repair=` path deleted.
2. **Failure routing (the ladder)** — correction-call failure → FLOOR (catch at the
   correction call site); **pass-call failure → `narrative_fallback`** (catch at the
   pass call site — never an error); a stop's compose-call failure → that stop ships
   stitched as `stitched_fallback`, EXCLUDED from threshold math. Catch anthropic
   APIError + ValueError (truncation, compose.py:502-506) + JSONDecodeError at each
   site. Loud structured log per fallback (status + reason, no payloads). Update the
   compose.py:677-682 propagate-by-design comment — Scope 5 reverses it BY DESIGN.
3. **Delete the 422** — trips.py:521-532 + the `ComposeVerificationError` import; sweep
   dead machinery (`serve_or_block`, `compose_and_verify(repair=)`,
   `ComposeVerificationError`, `drop_failing_sentences`, `repair_composed`) — delete, or
   log explicitly to the follow-up spec if anything must stay (lint bar: zero dead code).
4. **Rewrite the two dying tests** —
   `test_refused_flavour_is_422_and_leaves_trip_untouched` (test_trip_api.py:701 —
   assertions INVERT: 200, corrected/floored/fallback status, stops re-persisted,
   `composed_route_id` set) and test_tour_compose.py:290.
5. **New tests** per Part B.

**NOT to touch:** Scope 4's persistence internals (crud/models) — but the
threshold-math EXCLUSION of `stitched_fallback` stops lives in the gate/route rollup,
which IS this scope's; verify/pass internals; mobile (its 422/refusal handling becomes
dead code — LOGGED for follow-up, not deleted).

### Part B — Tests (AC-11 — `make test-local`)

- (a) Mixed-exception TOTAL outage stub (APIError/ValueError/JSONDecodeError across
  calls) → BOTH endpoints return a complete, servable stitched tour, honest fallback
  status, no 4xx/5xx (RED under HEAD — trips.py:521 raises 422 today).
- (b) PARTIAL outage (raise on a stop subset) → mixed script; `stitched_fallback` stops
  excluded from threshold math.
- (c) Correction-call failure stub → the sentence FLOORS (not stitch, not error).
- (d) **Pass-call failure stub → `narrative_fallback`, 200, tour flagged** (new per
  04b).
- (e) Always-REJECTING checker → `/compose` 200 with corrected/floored/fallback
  statuses, never 422 (RED under HEAD).
- Stitch proven LLM-free: fixture runs with no network/client constructed at all.

### Part C — `/team` prompt (Tier 2)

> Implement Scope 5 (Entry-point convergence + never-fail availability) of
> specs/2026-07-13-compose-correct-dont-reject/05-plan.md — that file's Scope-5 section
> (Parts A/B) is the full request; AC-11 + the Availability ladder in 02-spec.md (as
> amended: pass-call failure ⇒ narrative_fallback) is the contract. Stages 1–4
> pre-approved; start at Developer. Tier 2 (QA undo-test on the (a) fixture; 1-2
> skeptics on the failure-routing matrix — every exception type × every call site ends
> at the RIGHT ladder rung; judge before commit). Files: src/tour/compose.py,
> src/tour/compose_gate.py, src/api/routes/trips.py, tests/test_trip_api.py,
> tests/test_tour_compose.py. Do NOT touch: Scope 4's crud/models internals, verify/pass
> internals, mobile (its 422 handling is dead code — log to follow-ups, do not delete).
> Tests committed RED-first where marked. Verification: `make test-local`, full
> `make test` + `make lint` zero. Demo: workbench preview with COMPOSE_PROVIDER broken
> on purpose → the tour still renders, honestly labeled (screenshot). Before starting,
> confirm Scope 4's statuses exist per state.json, and flag any conflicts or
> assumptions.

**Estimated sessions:** 1

---

## Scope 6 — Live Acceptance Run + Calibration (closes the ticket)

Surface: `tools/` harness, threshold constants, `Docs/bug-reports` update,
`06-verify.md`. Binding contract: AC-1 + AC-9 (judged against the `01f` character);
`03-scopes.md` Scope 6.

### Part A — Tasks

1. **Machine-asserted live run** — harness (extend Scope 1's / Scope 3b's) runs the
   ticket repro config (center 48.8635,2.3280, duration 240, lenses [famous_residents,
   literary_heritage, historic_arch]) through the COMPLETE pipeline (correct-loop +
   pass). Asserts FIRST, before any human reads: stop 2 ships **`narrative` status (not
   fallback)**, NOT byte-identical to the stitch, AND a sentence citing `85ebe707`
   (± `c3d4a78a`) ships verified|corrected — the von Choltitz fusion survives AS a
   fusion. Dumps per-stop counts, pass statuses, fallback reasons, and full text to the
   spec folder.
2. **Acceptance review (AC-9)** — the acceptance agent judges the full tour text against
   the **`01f` character**: orientation first, motivated transitions, each fact once,
   staged quotes, the dispute as a pivot, no register break at correction seams — AND
   the `01g` §C editorial checklist (no welded causation, pronoun clarity, spoken
   pacing, quote staging, attributed judgments; the token-free-glue causal-framing
   residual is exactly what this human read covers). Then the HUMAN reads/listens and
   signs off — a ONE-TIME Tier-3 calibration gate.
3. **Calibrate thresholds** — from this run + the mock/replay scoreboard across existing
   fixture tours; commit constants as provisional with a telemetry-review trigger
   comment (LLM flow-judge remains a telemetry-triggered follow-up).
4. **Close out** — fabrication fixtures re-run green; ticket
   `2026-07-13-compose-stop-revert-haiku-ceiling.md` closed with evidence appended;
   `06-verify.md` written (all-AC closure per Stage 6); memory updated.

### Part B — Tests (AC-1, AC-9)

- The machine assertions on the live artifact (scripted; artifact saved to the spec
  folder). AC-1 fails if stop 2 ships `narrative_fallback` — that is a FINDING to
  report upstream, not to hotfix.
- AC-9: acceptance-agent report + human verdict recorded in `06-verify.md` with the
  run's counts as the quality baseline (they become AC-10's calibrated thresholds).
  Never close on fixtures alone; never on live alone.

### Part C — `/team` prompt (Tier 3 — closes the ticket)

> Implement Scope 6 (Live acceptance + calibration) of
> specs/2026-07-13-compose-correct-dont-reject/05-plan.md — that file's Scope-6 section
> (Parts A/B) is the full request; acceptance target = the 01f golden's CHARACTER
> (read 01f-goldenized-acceptance-text.md first). Stages 1–4 pre-approved; start at
> Developer. **Tier 3**: judge before the live spend (print the cost estimate),
> acceptance agent on the real tour text judged against the 01f character, HUMAN
> sign-off REQUIRED before closing the ticket — do NOT mark done without it (the
> visibility contract: the human must SEE the Le Meurice stop text). Machine assertions
> run FIRST and include: stop 2 ships `narrative` (not fallback) — if it falls back,
> that is an AC-1 FAILURE to report upstream loudly, not to hotfix silently. Files:
> tools harness, threshold constants, Docs/bug-reports update, specs 06-verify.md. Do
> NOT touch src logic beyond threshold constants. Repro config is in the ticket. Before
> starting, confirm Scopes 3b, 4, 5 are committed per state.json and `make test` is
> green at baseline.

**Estimated sessions:** 1

---

## Part D — Best-Practices Checklist (from the Stage-4 + 04b audits)

| Practice | Where | Verify |
|---|---|---|
| Fabrication threat model: full-gate FN/FP batteries + skeptic panels + two GO gates + Tier-3 human gate | Scopes 2, 3, 3b, 6 | Scorecards in 02b/03b artifacts; AC-2/AC-12 batteries green; panel verdicts pasted |
| No secrets in transcripts/logs (calibration + probe harnesses never echo env/keys) | Scopes 2, 3b, 6 (harnesses), 5 (fallback logs) | Transcript review; log lines carry statuses/counts, never payloads/keys |
| Logging: statuses + counts, loud fallbacks, no payload dumps | Scopes 4, 5 | Structured-log asserts in AC-11 tests |
| New persisted fields → data-inventory note (§16) | Scope 4 | Doc diff in the scope's commit |
| Retention: counts ride ItineraryItem lifecycle (DETACH DELETE) | Scope 4 | Re-compose round-trip test |
| Text-not-color-only badge (a11y) | Scope 4 | Badge is a text status string |
| Bounded LLM cost: ≤2 corrections/sentence, 2×stops pre-pass line, ≤2 pass calls/stop + own 2×stops pass line; ~2.4× Haiku volume accepted (cents) | Scopes 3, 3b | AC-8 + AC-12(e) budget fixtures; probe cost printouts |
| Held-out NYC battery data stays local (7687/7688), never in committed fixtures with PII | Scope 2 | Battery reads from local Neo4j; scorecard carries text only |
| Follow-up tickets logged, not built (trips-router auth gap; mobile dead-code; key_claims teardown; richer workbench UI; affirm escalation; cross-stop overlap watch) | `state.json` follow_ups | Present in state.json |

## North-star final check

Consistent: the pass serves the MVP thesis directly (compelling narrative was the NO-GO
failure); locked narrator voice survives (glue lane still scans "imagine"; 01f removed
it from the acceptance text); bake-once audio unchanged (`_sum_audio` cap holds; glue
audio watched via R-V6); corpus-canonical grounding strengthened (body-only support, no
entailment-free lanes); compose-only blast radius holds (no extraction/schema/stitcher
surface touched; `_COMPOSE_SYSTEM` untouched). No locked commitment re-opened.
