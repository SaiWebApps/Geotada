# 04b — Red Team RE-OPEN: verified narrative pass, calibrated gate

**Date:** 2026-07-15 (v2.1 — same day) · **Stage:** 4 (re-opened per
`state.json.stage4_reopen`) · **Thinking mode:** Adversarial reviewer

**Trigger:** Scope-1 live probe ruled **NO-GO by the human on FN usability**
(`01b-probe-transcript.md`): the correct-loop WORKED (corrections faithful, floors safe),
but the assembled final text (`01c` Version B) is a disjointed narrative — verified
fragments spliced together, no global flow. The human's hand rewrite
(`01e-human-gold-rewrite.md`) is the acceptance golden, and its provenance is the design's
key evidence: **01e was produced FROM Version B** — the corrected output — not from the
beats. The proven transform is `corrected text → engaging narrative`.

**v2 REVISION NOTE (mandate correction by the product owner, 2026-07-15):** v1 of this
document designed a composer REBUILD (write globally from beat bodies), following the
literal wording of `state.json.stage4_reopen`. The product owner corrected the intent:
the error correction is not the problem — the missing piece is a step that TRANSLATES the
corrected text into a complete narrative. v2 designs that step: a **post-correction
verified narrative pass**. v2.1 folds in the delta review's refutations of the v2 draft.

**Panel:** 3 independent adversarial reviewers on the v1 design — fabrication skeptic
(opus), fact-loss/machinery skeptic (sonnet), challenger — plus a **delta skeptic on the
v2 architecture** (worked the Version B → 01e fixture token-by-token against the repo's
actual regexes; re-ran the Scope-0 golden 4/4 at HEAD). Main agent code-verified every
load-bearing panel claim before accepting it (`_signature` at claim_dedup.py:105-109;
glue-only forbidden-phrase scan at validation.py:144-146 + generation.py:86; `_sum_audio`
1.0 cap at generation.py:998-1046; mock/golden independence at compose.py:227-257;
Phase-2 rescue never repairs citations, verify.py:297-316).

---

## 0. THE REDESIGN (v2.1 — what the human approves)

Everything not restated here carries over unchanged from the amended `02-spec.md`: the
composer (`_COMPOSE_SYSTEM`, untouched), the deterministic pre-gate, the sentence-unit
verbatim shortcut, the fact-preserving correction routing, the floor (raw post-dedup
stitch sentences, PRE-pass only), seated-beat invariant (pre-pass; see P1 for its pass
semantics), glue/vignette rules (as amended), collateral-subset rule, availability
ladder, telemetry shape, offline bar, blast radius.

### P1 — The verified narrative pass (the new core)

A per-stop stage that runs AFTER the correct-loop completes a stop (its sentences final:
composed / corrected / floored under the existing rules).

- **Input:** the stop's verified sentence stream WITH citations (source_id + also_cites
  per sentence), the seated beats' `script_body` (the gate's support; **phrasing source
  only — the prompt forbids adding any fact absent from the input sentences**, since
  bodies still contain repeats the route-level dedup removed from the stream), POI name,
  `tour_context`, lenses.
- **The transform (the 01e bar — each item observable in that text, produced from this
  exact input class):** orient the walker first; motivate every transition; unpack
  compound blocks (including floored raw-stitch splices) into single-idea sentences
  placed where the story needs them; voice each fact exactly once; surface the connecting
  theme through transitions, never as a stated moral; stage quotes as a scene; keep
  disputes intact and use them as pivots. Locked voice rules unchanged (one warm
  second-person narrator; never "imagine"; no meaning-stating).
- **Output:** the same source-attributed sentence schema — every fact-carrying sentence
  cites the beat(s) whose facts it carries; `_populate_also_cites` runs on pass output,
  with its token justification RESTRICTED to the pre-gate salient class (years/numbers/
  proper-noun tokens), not the full `_signature` bag — the delta review showed the
  unrestricted repair manufactures false citations from common tokens ("second") on the
  gold fixture itself.
- **Re-gate (full production gate, all layers):** pass output enters pre-gate → verbatim
  shortcut → calibrated entailment (D2) → bounded correction incl. trim. Plus two
  deterministic rules specific to novel-structure output:
  - **Quote fidelity (fail-closed):** any text inside quotation marks must appear
    verbatim (whitespace-normalized) in a cited beat's body — pass output is exactly the
    stage that rewrites quotes, the salient-token classes are blind to lowercase quote
    interiors, and entailment tolerates paraphrase; quotes are corpus material and ship
    verbatim or not as quotes. (The gold complies: where the human reworded, she moved
    the changed words OUTSIDE the quotation marks — 01e:52.)
  - **Glue lane assignment is deterministic, not label-trust:** a pass sentence labeled
    glue that contains ANY pre-gate-class salient token is PROMOTED to the checked lane
    (entailed against the stop union; dispute/question instructions apply; correctable/
    trimmable like a beat sentence). Token-free glue takes validation's existing scan.
    This kills the smuggle the delta review constructed ("It was in this hotel's cellars
    that Orwell slaved…" labeled glue → contains "Orwell" → promoted → dispute
    instruction fires). A glue-mislabel class joins the FP battery.
- **NO floor inside pass output — and the ladder is now fully defined:** a pass sentence
  that exhausts correction, an affirm-class rejection (corrector returns ~identical), a
  seated-beat-invariant violation (a beat owning no pass sentence), or a fact-diff
  failure after the restore retry each SINK THE PASS for that stop — the stop ships its
  **pre-pass verified text** (`narrative_fallback`). The restore retry's prompt lists
  BOTH missing facts AND unowned beats, so one retry addresses both violation classes.
  Mixing pass prose with pre-pass prose is forbidden (it would recreate the seam problem
  the pass exists to kill). The fallback is whole-stop, deterministic, LLM-free —
  termination is unconditional. (The v2 draft left seated-beat-on-pass-output undefined —
  its only remedy was a floor insertion, which the pass forbids; delta finding F3.)
- **Fact preservation — deterministic diff, TWO-SIDED:** every pre-gate-class salient
  token (years, numbers, proper-noun tokens — NOT the full `_signature` bag, which would
  false-fail legitimate rephrasing) present in the pass INPUT's beat-cited sentences must
  appear in the pass OUTPUT. Missing ⇒ ONE restore retry (the
  `dropped_facts_you_must_restore` pattern, compose.py:452-456); still missing ⇒
  `narrative_fallback`. Calibration is anchored on BOTH sides by committed fixtures:
  - *Must-pass:* the (Version B → goldenized 01e) pair — if the gold fails the diff, the
    diff is miscalibrated (`_canonicalize_dates` is extended for word-form ordinals like
    "19th"→"nineteenth"; it is digit-only today, claim_dedup.py:79-103).
  - *Must-catch (the anti-ratchet):* committed mutations of the gold that the diff MUST
    fail — a deleted year, a deleted entity ("Galignani"), a changed street number
    (224→242). Without these, every calibration step could only loosen (delta F6).
  - *Recorded blind spots:* tokens <3 chars ("WH", "II") are invisible to the class
    (validation.py:36-38) — short-entity loss is covered by the quote rule, entailment,
    and AC-9, not the diff; a dropped RELATION between still-present entities is not
    mechanically detectable (R-V2).
- **Budgets & termination:** ≤2 pass calls per stop (initial + the restore retry);
  pass-stage corrections draw from their **own `2 × stop_count` line** — NOT the
  pre-pass correction budget (the v2 draft shared one budget across ~2.4× checked-
  sentence volume, systematically starving late stops into fallback; delta F4). Any
  exhaustion ⇒ `narrative_fallback`. Pass calls parallelize per stop.
- **Fallback-rate is a measured GO criterion, not a hope:** whole-stop sinking means
  stop survival ≈ (1−q)^n for n≈28 checked sentences — q=1% residual FN already means
  ~25% of stops fall back, and the unconditional flag would saturate the editorial queue
  (~94% of 10-stop tours flagged). Therefore the calibration probe (D2a) measures
  STOP-LEVEL pass rate on a real multi-stop tour, and the Scope-3b GO bar includes a
  fallback-rate ceiling set on reading it (the residual per-sentence FN rate must
  support ≥~90% stop survival). Pre-calibration, the gold stop itself would have fallen
  back (01d s8 is an affirm-class FN) — the fallback bar is honest about this: the
  redesign is a no-op if calibration does not clear it, and the line stops again there.
- **Statuses (additive to AC-10):** stop-level `narrative` | `narrative_fallback`,
  layered over the existing verified/corrected/floored counts (pre-pass telemetry).
  `narrative_fallback` **unconditionally forces the tour's `flagged` editorial-review
  status**. New counters: `glue_dropped`, `affirm_reject` (both stages),
  `pass_facts_restored`, `pass_fallback_reason` (correction-exhausted | affirm |
  seated-beat | fact-diff | budget).
- **Both entry points** converge on the pass (preview + persisted `/compose`).
- **Mock/golden:** `MockNarrativePass` is the IDENTITY — under mocks the pipeline output
  is byte-identical to today; the committed Scope-0 goldens hold with zero re-pinning
  (verified: the mock path never renders prompts; `_populate_also_cites` is idempotent,
  so its second call site cannot perturb the goldens; 4/4 at HEAD re-run twice).
- **Why the floor can stay raw stitch:** the pass rewrites floored blocks into flow —
  their content is corpus text, fully supported by the cited body. The v1 floor-span
  re-compose (D3) is ABSORBED by the pass and dropped as separate machinery.
- **Citation-attribution honesty (recorded limit):** Phase-2 union rescue ships a
  sentence with its DECLARED citations unchanged (verify.py:297-316) — a fact can ship
  attributed to a co-stop beat that didn't source it. This limit is PRE-EXISTING in the
  approved spec (the union-rescue design); the pass widens exposure (more novel
  sentences). Mitigated by the salient-class restriction on `_populate_also_cites`
  (above) and recorded as R-V9: per-sentence citations are support attribution, not
  provenance guarantees. Blast-radius note: false citations widening fusion-ownership
  floors applies pre-pass only (no floors inside pass output).

### D2 — Gate amendments (from the v1 panel, carried VERBATIM — pass output faces this gate)

`01d` proves the current entailment rejects 4/29 of exactly the text class the pass
produces, and the v1 panel proved how a carelessly loosened gate gets fooled. All v1
gate resolutions stand:

- **(a) Fusion/paraphrase FN calibration — with the relation line.** The entailment
  prompt (`verify.py:92-97`) is rewritten fusion-aware: support presented as one
  continuous SOURCE TEXT (union of cited bodies); restating, reordering, splitting, or
  combining facts stated in the source is YES — **but combining is YES only when the
  relation joining the facts is itself stated in the source; a new relation between two
  source facts is ADDED content ⇒ NO** (the fluent-frankenfact line). Plus the dispute
  instruction: a sentence asserting flatly what the source hedges or disputes ⇒ NO.
  Plus the question instruction (b).
  **Calibration is MEASURED before the line restarts, on BOTH sides, through the FULL
  production gate (pre-gate + shortcut + entailment + correction routing) — NOT
  entailment alone: 01d ran entailment-only, a strictly weaker gate than production
  (delta F1), so 25/29 there does NOT prove the gold clears the pre-gate.**
  - *FN battery:* the goldenized-01e sentences, the two judge-verified live fusions
    (01b s2/s10), the near-verbatim paraphrase (01d s8), the gold question — per-class
    pass definitions (entailment-YES vs ships-after-trim vs promoted-glue). Bar: all
    three known FNs recovered; goldenized text ships whole THROUGH THE FULL GATE.
    (Calibration analysis note: 01d's two "nineteenth century" sentences are 2 of its 4
    rejections — control for word-form dates before attributing the FN class; delta F8.)
  - *FP battery, extended:* the original four classes with `date_shift` actually
    populated (0/20 in 01b:132 — never tested), PLUS fluent frankenfacts (grammatical
    false-relation recombinations — 01b's frankenfacts were broken-grammar strawmen),
    PLUS dispute-flatten/hedge-strip, PLUS question-presupposition smuggles, PLUS
    glue-mislabel (factual assertions labeled glue — must be caught by the promotion
    rule). Bar: ZERO fabricating acceptances.
  - *Held-out material* from ≥1 non-Le-Meurice stop (NYC corpus is live locally).
  - *Per-tour exposure:* the probe runs the NARRATIVE PASS on a multi-stop tour — pass
    output is novel prose, the verbatim-shortcut hit rate collapses (4/11 → ~1/29), so
    the fabrication bound AND the stop-level fallback rate are measured per-tour.
- **(b) Questions — checked, not exempted.** The v1 entailment-free question lane was
  REFUTED (its token gate rested on a false description of `_signature` — ALL
  non-stopword tokens ≥3 chars, claim_dedup.py:105-109 — and bag-of-words containment
  against a 1312-char compound body constrains ~nothing; a question can presuppose the
  DISPUTED Orwell location as settled and ship unchecked). **No entailment-free lane
  exists anywhere in the design** (questions, glue — see P1's promotion rule). A
  beat-cited QUESTION goes through calibrated entailment with a question-aware
  instruction: YES only if the source supports what the question presupposes. The gold's
  "But did Orwell really work here?" is the FN fixture; presupposition smuggles are FP
  fixtures. **Recorded deviation from `state.json:32`** ("salient-token check only") —
  the mandated lane was refuted with a concrete attack.
- **(c) Trim-don't-floor — deterministically accepted.** LLM-executed, mechanically
  accepted: no added tokens AND every removed content token is in the flagged
  unsupported set. Anything else — e.g. a tidied-away hedge clause flattening the
  dispute (recreating the hedge_strip class that leaked 1/20) — is NOT a trim: it counts
  as the attempt-2 full rewrite.
- **(d) Affirm-path — telemetry only.** A correction returning ~identical text routes to
  floor (pre-pass) or sinks the pass (in-pass) and increments `affirm_reject`. The v1
  escalation ship-path (Opus grading Opus on its own unchanged output, unmeasured FP
  rate, bypassing the gate that caught all six frankenfacts) is DEAD. D2a's calibration
  targets the same FN class (01b s2/s10 ARE the affirm cases); if telemetry still shows
  a persistent affirm class, an INDEPENDENT-family escalation with its own FP battery is
  the recorded follow-up.

### Glue under the pass (v1 finding + delta hardening)

BL-1's drop rule is actively harmful here: motivated transitions ARE the bar, they are
glue by construction, and the drop is silent — demonstrated on the golden itself (01e's
bridge contains "imagine": generation.py:86, scanned because glue, validation.py:144-146).
Amended rules: (1) flagged glue gets ONE correction attempt before any drop +
`glue_dropped` counter; (2) P1's promotion rule — factual glue is entailment-checked, so
the glue lane cannot smuggle assertions (delta F5); (3) promoted-glue support is the
STOP union, sidestepping validation's script-wide cited-text scope.

### The worst case (surfaced for the human, not buried)

`narrative_fallback` = the pre-pass verified text — Version-B-class prose: factual,
verified, but below the 01e bar (its floors are raw stitch splices). A MATERIAL
improvement over the v1 worst case (bare raw stitch), never silent (unconditional
`flagged`), but still short of the mandate's "worst case is acceptable prose"
(`state.json:30`) — full compliance is impossible under deterministic termination. AND:
how often the worst case occurs is now a measured GO criterion (P1 fallback-rate bar),
because at plausible FN rates it would otherwise be the norm, not the tail. Accepting
this residual is part of approving this document.

### Known evidence-anchored gaps the design carries (recorded, not hidden)

- **Dispute-marker rule** (from 01b's single FP acceptance) ships as: the D2a prompt
  instruction + the dispute-flatten FP class + trim's mechanical check — NOT a
  deterministic guarantee. Deviation from `state.json:29` is deliberate: subject-bound
  dissent is not deterministically detectable; live s7 (01b:78-87) shows the rejection
  already works at the entailment layer.
- **Goldenization deviations (EXPANDED by the delta review):** the goldenized acceptance
  text is 01e minus SIX deviations — the three recorded in 01e's header ("we have to
  imagine"; "William Makepeace"; "English writer(s)") plus three the delta review found
  by running the pre-gate the 01d probe never ran: "**Tuileries Palace**" (bodies say
  "the Tuileries"), "**Parisian** fashion" (no body carries "Parisian"), "the **Second**
  World War" (bodies say "World War II"). Grounded equivalents substitute. The FN
  battery and diff fixtures score against THIS text.

---

## 1. BLOCKERS — v1 panel (remapped to v2) and delta review (v2.1); all resolved into §0

### From the v1 panel

**BL-R1. Entailment-free question lane refuted** (fabrication skeptic, HIGH × HIGH) —
false `_signature` description + concrete presupposition-smuggle + internal
inconsistency. → Lane deleted; checked-questions (D2b). Carries to v2 unchanged.

**BL-R2. Loosened prompt invites fluent frankenfacts the battery couldn't detect**
(fabrication skeptic + fact-loss skeptic + challenger) — relation line; extended battery
(fluent frankenfacts, populated date_shift, dispute-flatten, question smuggles);
held-out stop; per-tour measurement (D2a). Carries to v2 unchanged.

**BL-R3. Affirm-escalation was self-grading** — ship-path deleted; telemetry +
independent-family follow-up (D2d). Carries to v2 unchanged.

**BL-R4. Trim was an unconstrained LLM deletion able to flatten disputes** — mechanical
trim-acceptance check (D2c). Carries to v2 unchanged.

**BL-R5. Per-claim fact loss** (fact-loss skeptic, HIGH × HIGH) — v2 TRANSFORMS the v1
token-coverage invariant into the pass's deterministic input/output diff + restore retry
+ whole-stop fallback, now two-sided per BL-V4.

**BL-R6. Dedup hints on the wrong artifact** — v2 narrows it (composer untouched, pass
input already deduped) but does NOT fully dissolve it: bodies handed to the pass still
contain stream-removed repeats (delta F7). → Bodies are phrasing-only by prompt rule;
cross-STOP overlap telemetry is the detection net; recorded as R-V10.

**BL-R7. Glue-drop silently deletes the transitions that ARE the bar** (demonstrated on
01e's own "imagine" bridge) — correction attempt before drop + counter. Carries to v2,
hardened by the promotion rule (BL-V3).

**BL-R8. Budget starvation + undefined status semantics** — v2.1 resolves properly: the
pass has its own call line AND its own correction line (the v2 draft shared one budget
across 2.4× volume — starvation reintroduced, delta F4); `narrative_fallback` forces
`flagged`; fallback reasons enumerated.

**BL-R9. Golden byte-equality retention condition** — DISSOLVED in v2: composer/request
untouched; identity mock; `_populate_also_cites` idempotence verified; 4/4 at HEAD.

### From the delta review (v2.1)

**BL-V1. The GO fixture contradicted the carried-over pre-gate** (delta F1, HIGH ×
HIGH) — 01d tested entailment-only; the goldenized text as then defined fails the
production pre-gate on three capitalized tokens absent from bodies.
→ Goldenization deviations expanded to six (§0); the FN battery runs the FULL gate.

**BL-V2. Citation bookkeeping had no honesty mechanism, and the repair manufactured a
false citation on the gold itself** (delta F2, HIGH × HIGH) — Phase-2 rescue never
repairs citations (verify.py:297-316); unrestricted `_populate_also_cites` attaches the
fashion beat to the von-Choltitz sentence via the common token "second".
→ Repair token-justification restricted to the pre-gate salient class; attribution limit
recorded as R-V9 (pre-existing in the approved union-rescue design, widened here).

**BL-V3. The glue lane was the refuted entailment-free lane, resurrected** (delta F5,
HIGH × HIGH) — label-trusted glue skips entailment (verify.py:272) and its scan is
script-wide and token-only; a dispute-flattening assertion labeled glue shipped
unchecked. → Deterministic promotion rule (factual glue is entailment-checked against
the stop union); glue-mislabel FP battery class.

**BL-V4. The fact diff was a one-way loosening ratchet with verified blind spots**
(delta F6, MED-HIGH × HIGH) — only a must-pass fixture existed; "WH"/"II" invisible;
quotes wholly unguarded exactly at the stage that rewrites them.
→ Must-catch counter-fixtures committed; quote-fidelity fail-closed rule; blind spots
recorded with their covering mechanisms.

**BL-V5. Seated-beat invariant vs no-floor-inside-pass was self-contradictory** (delta
F3, HIGH × HIGH) — the invariant's only remedy was floor insertion; undefined for pass
output; affirm-in-pass likewise undefined.
→ Fully defined ladder: invariant violation and affirm both sink to the restore retry /
`narrative_fallback`; the retry prompt lists unowned beats alongside missing facts.

**BL-V6. Fallback frequency made the redesign a plausible no-op and saturated the flag**
(delta F4, HIGH × MED-HIGH) — (1−q)^28 math; the gold stop itself would have fallen back
pre-calibration (01d s8); no fallback bar existed in any GO gate; shared budget starved
late stops. → Stop-level fallback-rate GO bar measured on the multi-stop probe (~≥90%
survival target, set on reading); separate pass budget lines; `pass_fallback_reason`
telemetry.

**BL-V7. (Delta F8, LOW-MED)** 01d's FN-class diagnosis never controlled for word-form
dates ("nineteenth century" appears in 2 of the 4 rejections). → Calibration analysis
note in D2a.

## 2. RISKS (accepted with mitigations)

- **R-V1 Per-tour FP exposure** (shortcut collapse ⇒ ~every pass sentence checked). →
  Measured per-tour in the calibration probe; prod telemetry. Residual until Scope 6.
- **R-V2 Relation loss invisible to the token diff** ("Dickens… researching A Tale of
  Two Cities" → facts voiced apart, purpose-link lost). Not mechanically detectable. →
  Pass prompt, FN battery, AC-9 human acceptance. The design's honest soft spot.
- **R-V3 Question/dispute instructions are prompt-level.** → FP classes must be 0-accept
  at calibration; any live acceptance is a judge-review item.
- **R-V4 Whole-stop sink sensitivity.** Now a measured GO bar (BL-V6), not an assumption.
  Fallback-rate telemetry in prod decides revisiting.
- **R-V5 Diff token-class calibration.** Two-sided fixtures (must-pass gold pair;
  must-catch mutations) prevent both false-fallback drift and the loosening ratchet.
- **R-V6 Uncapped glue audio** (+4s/glue sentence; the pass adds bridges; ~2/stop ≈ 80s
  on 240 min). LOW; telemetry only.
- **R-V7 n=1 quality bar** (one stop, one author). → Scope 6 acceptance stays the Tier-3
  human gate on a full tour; held-out-stop battery material reduces single-stop tuning.
- **R-V8 Cost/latency.** ≤2 pass calls + own correction line per stop + ~2.4× Haiku
  volume — roughly doubles per-stop compose spend (cents), parallelizes per stop.
- **R-V9 Citation attribution is support, not provenance** (BL-V2). Pre-existing limit,
  widened by novel prose; salient-class restriction narrows it; telemetry/TTS
  traceability reads accordingly.
- **R-V10 Cross-stop repeat restoration via bodies** (BL-R6 residual). → Phrasing-only
  prompt rule + cross-stop overlap telemetry.

## 3. OPEN QUESTIONS (the human's call at approval)

1. **Accept the worst-case residual?** `narrative_fallback` ships Version-B-class
   verified prose (raw-stitch floors included), always flagged — below the mandate's
   "acceptable prose" bar, strictly better than v1's raw-stitch worst case, and its
   FREQUENCY is now a measured GO criterion (BL-V6). Recommendation: ACCEPT — the
   alternative is unbounded retries, which breaks deterministic termination.
2. **Accept the two mandate refinements?** (a) `state.json:32`'s entailment-free lane
   replaced by checked-questions AND checked-factual-glue (BL-R1 + BL-V3 refutations);
   (b) `state.json:29`'s dispute rule delivered as prompt + battery + trim-check, not a
   deterministic guarantee. Recommendation: ACCEPT both — each is the strictly-safer
   reading, refuting evidence cited inline.
3. **Accept the expanded goldenization?** Six deviations from your 01e text (three you
   recorded + three the pre-gate check surfaced: "Tuileries Palace", "Parisian",
   "Second World War" → grounded equivalents). Recommendation: ACCEPT — keeps the
   pre-gate strict rather than loosening the fabrication direction; the alternative
   (case-fold/alias pre-gate) weakens the one deterministic never-fabricate layer.

## 4. CODEBASE CONFLICTS (verified)

- The composer (`_COMPOSE_SYSTEM`, `_compose_user_prompt`, dedup plumbing) is UNTOUCHED.
- The pass is a NEW stage after both entry points' existing gate; it slots after Scope
  3's corrector lands (the correct-loop is still unbuilt — Version B was assembled by
  hand from the probe harness; scopes 2-6 pending per state.json).
- `verify.py:92-97` (`_ENTAILMENT_PROMPT`) is Scope 2's surface, as planned. The
  quote-fidelity and glue-promotion rules are new deterministic checks in the verify
  layer (same module family as the pre-gate).
- `_populate_also_cites` gains a second call site with the salient-class restriction —
  the restriction ALSO applies at the existing call sites (same function, one behavior);
  its effect on the pre-pass path must be covered by the Scope-3 fixtures (it can only
  REMOVE spurious citation gains, but the collateral-floor fixture set exercises it).
- AC-8's budget fixture gains the pass lines (≤2 calls + own correction line; exhaustion
  ⇒ fallback, never a hang).
- Status enum (Scope 4) gains `narrative`/`narrative_fallback` + unconditional-flag +
  the counters — additive; the `_compose_status` deletion plan stands.

## 5. NORTH-STAR CHECK

Sound. The pass serves the MVP thesis directly ("compelling, personalized narrative
tours" — the NO-GO was a compellingness failure); the locked narrator voice survives
(the glue lane keeps scanning "imagine"; goldenization removes it from the acceptance
text). Bake-once audio unchanged; `_sum_audio` 1.0 cap holds; ≤60% silence budget
monitored via R-V6. No schema/MERGE implications beyond AC-10's additive properties.
No boundary violations.

## 6. SCOPE REVIEW (implications for 03-scopes — applied on approval)

- **Scope 2 = gate calibration + script_body-only faithfulness:** entailment prompt
  rework (relation + question + dispute instructions) + FN/FP batteries THROUGH THE FULL
  GATE + held-out stop. GO bar: all three known FNs recovered; goldenized text ships
  whole; ZERO fabricating acceptances including the new classes (fluent frankenfacts,
  glue-mislabel, question smuggles, populated date_shift).
- **Scope 3 = corrector + floor, as originally spec'd** + the correct-loop amendments:
  trim mechanics (D2c), affirm telemetry (D2d), glue correction-before-drop,
  salient-class `_populate_also_cites` restriction.
- **NEW Scope 3b = the narrative pass** (P1 complete: prompt, two-sided diff + fixtures,
  quote rule, glue promotion, defined sink ladder, budgets, statuses/counters, identity
  mock, both entry points). Its live GO gate: the multi-stop probe's stop-level
  fallback-rate ceiling + per-tour fabrication bound. Depends on Scopes 2+3. With
  Scopes 0/1 complete, active scopes stay ≤7; Stage 5 renumbers.
- **Scope 6 live acceptance** runs the FULL pipeline; AC-9's judgment target is the
  goldenized-01e character.
- **AC amendments (02-spec on approval):** AC-1/AC-9 → goldenized-01e character; AC-2
  gains fluent-frankenfact + question-presupposition + glue-mislabel + populated
  date_shift classes; NEW AC for the pass (two-sided diff + restore + sink ladder +
  quote rule + glue promotion + statuses, incl. both fixture directions); AC-8 gains the
  pass budget lines; AC-10 gains the statuses, unconditional-flag rule, and counters.
  AC-7 needs NO amendment (identity mock).
- Ordering, deploy hold (2→3), one-commit-per-scope stand.

## 7. BEST-PRACTICES AUDIT (delta over 04-red-team §7 — that audit stands)

- §5 Secrets: calibration transcripts must not echo env/keys. Pass.
- §7 Logging: counters/statuses are counts, never payloads. Pass.
- §16 Compliance: additive status strings/counters extend the existing data-inventory
  note; no new PII. Pass.
- Cost: bounded lines (2×stops pre-pass corrections + ≤2×stops pass calls + 2×stops
  pass corrections) + ~2.4× Haiku volume (cents). Pass.
- Accessibility: badge/sub-statuses remain text. Pass.
- Held-out NYC data stays local (7687/7688). Pass.

## Attacks that FAILED (recorded so the refutations mean something)

- **Deterministic invariants vs novel-structure output:** `_populate_also_cites` derives
  from citations, the seated-beat invariant from ownership — neither needs stitch-shaped
  text (v1 fabrication skeptic; the PASS-side semantics gap was BL-V5, now defined).
- **Golden/AC-7:** identity mock; no prompt rendering on the mock path;
  `_populate_also_cites` idempotence verified; 4/4 at HEAD re-run by two reviewers.
- **Audio inflation via sentence expansion:** `_sum_audio` word-coverage cap at 1.0
  (residual = R-V6 glue).
- **Fallback fabrication:** the fallback is the already-gated verified stream —
  structurally clean; its usability deviation is Open Question 1; its FREQUENCY is
  BL-V6's GO bar.
- **Termination:** ≤2 pass calls, bounded corrections, LLM-free whole-stop fallback
  always reachable — confirmed by the delta skeptic (their attack was frequency, not
  termination).
- **"Empty-signature question" attack** (v1): `_signature` includes common nouns/verbs,
  so out-of-body verbs already fail token coverage — the lane was insufficient, not
  vacuous (hence BL-R1).

---

## AMENDMENTS TO APPLY ON APPROVAL

**02-spec.md:** add the narrative-pass contract (P1 complete: input/transform/re-gate/
quote rule/glue promotion/two-sided diff/sink ladder/budgets/statuses/mock) as the layer
above the correct-loop; D2a calibrated entailment contract + full-gate battery ACs;
checked-questions; trim mechanics; affirm telemetry; glue correction-before-drop;
salient-class citation-repair restriction; worst-case residual + fallback-rate bar in
Constraints; AC amendments per §6. The correct-loop contract itself is otherwise
unchanged.
**03-scopes.md:** Scope 2 gains the full-gate calibration GO gate; Scope 3 gains the
correct-loop amendments; NEW Scope 3b (narrative pass) with its fallback-rate GO gate;
Scope 6 acceptance target updated; AC map updated per §6.
**05-plan.md:** re-planned at Stage 5 for Scopes 2/3/3b.
**Goldenization:** commit the goldenized 01e (six deviations, §0) + the diff
counter-fixtures as spec-folder artifacts (01f) — they are the acceptance/calibration
oracle for Scopes 2/3b/6.
**state.json:** stage4_reopen resolved with the v2 mandate correction recorded (composer
rebuild → verified narrative pass, by product-owner clarification 2026-07-15); scopes
updated; open questions 1-3 recorded with the approval decision.
