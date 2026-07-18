# Semantic Fact-Checker — DESIGN (faithfulness + coverage repair signal)

> STATUS: DESIGN ONLY. Nothing built. This designs the robust, **fully
> semantic** (no lexical/regex — user-banned) fact-checker for one tour stop:
> given a ~150-word composed narration and that stop's KNOWN source facts
> (the cited beats' `key_claims` + verbatim `script_body` sentences —
> CLOSED-BOOK, no retrieval), emit a repair signal
> `{unsupported_claims: [...], missing_facts: [...]}` the author engine
> rewrites against until both are empty (bounded), then serves.
>
> Read alongside `DECOMP-PLAN.md` (the SOURCE-side atomic decomposition —
> complementary), `FIX-B-VALIDATION.md` (why the LEXICAL coverage gate is a
> refuted dead end), and memories `tour-quality-root-cause.md`,
> `compose-regression-system.md`, `feedback-never-waste-anthropic-credits.md`.

Every factual claim below is cited to either a RESEARCH finding (family/method +
arXiv URL) or CODE (`path:line`). The citation map is the appendix.

---

## 0. Decision in one line

**Adopt claim-decomposition + bidirectional entailment, executed on the
entailment primitive we already own.** Decompose the narration into atomic,
*checkworthy* claims and entail each against the stop's source facts
(FAITHFULNESS → `unsupported_claims`); take each source fact and entail it
against the whole narration (COVERAGE → `missing_facts`). Both directions are
the SAME call to `HaikuFaithfulnessChecker.entails` with the premise/hypothesis
roles swapped (`src/tour/verify.py:119`) — the primitive is already a
direction-agnostic "does this premise list support this hypothesis?" engine, so
the only genuinely new model call is the narration decomposition. This
**retires** the lexical `verify_claim_coverage` gate (`src/tour/claim_dedup.py`)
from the decision path, which is exactly the banned lexical approach and a proven
blind spot (`FIX-B-VALIDATION.md` REJECTED #1/#2/#3).

---

## 1. RECOMMENDED METHOD — and why this one, decisively

### 1.1 The setting picks the method

Our task is the *easy corner* of the faithfulness literature: closed-book, the
evidence is a small KNOWN set of atomic facts (the beats), no discovery/retrieval
needed. That single fact eliminates most of the machinery the papers spend their
whole engineering budget on:

- **Full QAG (question-generation + QA + answer-matching) is overkill.** QAG
  exists to *discover* what to check when aligning a short summary against a LONG
  unstructured source; our source is already a discrete fact list, so there is
  nothing to discover and no QG to run [qag recommendation; QAGS runs ~20 QA
  round-trips + 3 learned models, https://arxiv.org/abs/2004.04228]. The clincher
  is TRUE (NAACL 2022): a single strong NLI/entailment model **ties** the full
  QAG pipeline (T5-11B/ANLI 81.5 vs Q² 80.7 avg AUC) while being one model instead
  of three; QAG only pulls ahead when *ensembled* with NLI — a luxury unjustified
  for 150 words vs a handful of facts [qag/TRUE, https://arxiv.org/abs/2204.04991].

- **A trained specialized checker (MiniCheck / AlignScore / SummaC) is the $0
  endgame, but not the first ship.** These are the research's top pick for cost:
  small LOCAL models at ~$0/check and GPT-4-level accuracy — MiniCheck-FT5 74.7 vs
  GPT-4 75.3 balanced-accuracy on LLM-AggreFact at ~400× lower cost, and its
  training explicitly forces "check each fact AND recognize synthesis across
  sentences" [nli-faithfulness/MiniCheck, https://arxiv.org/abs/2404.10774];
  AlignScore is one 355M forward pass, threshold ~0.5 [nli-faithfulness/AlignScore,
  https://arxiv.org/abs/2305.16739]. We adopt them — but as a **drop-in behind the
  existing `FaithfulnessChecker` Protocol** (`src/tour/verify.py:67`), for the
  $0-in-the-bar CI gate and an eventual serving cost-down, NOT as the day-one
  serving path. Reason: they are NEW infra (a model download + a serving process)
  and their threshold must be **calibrated against a hand-labeled set** before we
  trust the number — RoSE showed binary "is this fact present?" judgments only hit
  Krippendorff α≈0.75 [coverage-omission/ACU, https://aclanthology.org/2023.acl-long.228/].
  The Haiku primitive, by contrast, is already trusted in this repo at temp=0 with
  a hard convergence invariant (`src/tour/verify.py:127`).

### 1.2 The four ideas we DO import (each earns its place)

1. **Decompose the OUTPUT into atomic facts, then verify each — not one holistic
   verdict.** The FActScore recipe: split into atomic facts (one checkable
   proposition each) and score the fraction supported; fine-grained decomposition
   beats a whole-text verdict because long text mixes supported and unsupported
   pieces, and the automated estimator tracked humans within <2% error
   [claim-decomposition/FActScore, https://arxiv.org/abs/2305.14251]. This is
   precisely why the current sentence-level gate has a blind spot: a single
   composed SENTENCE packs several facts, so entailing the whole sentence lets a
   *within-sentence* fact-drop pass (the documented Charing-Cross hole,
   `DECOMP-PLAN.md` §0; `claim_dedup.py` multi-fact-sentence blind spot).

2. **Extract only CHECKWORTHY/verifiable claims — the single most important
   import.** Tour narration is deliberately evocative ("imagine standing here,"
   second-person address, sensory framing) — the *creative-writing* end of the
   verifiable-claim-density spectrum (WritingPrompts 0.03 claims/sentence vs
   non-fiction 2.31). A decompose-EVERYTHING method would score metaphor and
   framing as hallucinations. VeriScore's "extract only a single verifiable
   event/state" step is the fix; human annotators preferred it over SAFE's
   extraction 93% of the time, citing SAFE's three failures: extracting subjective
   content, over-decomposing into overlapping fragments, and extracting trivia
   [claim-decomposition/VeriScore, https://arxiv.org/abs/2406.19276]. Bonus: this
   also enforces Pipeline Guardrail #4 — an unsourced superlative that slips
   through decomposition entails to NO and is correctly flagged.

3. **Run BOTH directions (QuestEval framing), the comparison SEMANTIC (Q²).**
   output→facts catches invention (precision/faithfulness); facts→output catches
   omission (recall/coverage) [qag/QuestEval, https://arxiv.org/abs/2103.12693;
   coverage-omission/ACU recall]. The answer-comparison MUST be semantic (NLI/LLM),
   never token-overlap, because our narration paraphrases the beats heavily — Q²
   fixed exactly the "paraphrased-but-correct scored inconsistent" failure by
   replacing token-F1 with NLI [qag/Q², https://arxiv.org/abs/2104.08202]. Our beats
   ARE the ACUs (already atomic), so coverage = (#facts conveyed)/N with the
   unmatched set as the omission report — no decomposition needed on the source side
   [coverage-omission/ACU + Lite2Pyramid, https://arxiv.org/abs/2109.11503].

4. **Reference-guided, closed-world, CoT-then-JSON, DIFFERENT judge than
   composer.** Handing the source facts as the ground-truth reference is the single
   biggest reliability lever (reference-guided grading cut a hard-task failure rate
   70%→15%) [llm-judge/MT-Bench, https://arxiv.org/abs/2306.05685] — the existing
   `_ENTAILMENT_PROMPT` already does this ("Given a list of KEY CLAIMS…",
   `verify.py:91`). The decomposition call must reason in free text FIRST then emit
   JSON: forcing JSON-first crushed reasoning (GSM8K 76→49; Haiku 23→87 loose-vs-rigid
   schema) [llm-judge/"Let Me Speak Freely", https://arxiv.org/abs/2408.02442]. And
   the checker is Haiku while the composer is Opus/ChatGPT — a different model dodges
   self-enhancement bias for free [llm-judge/MT-Bench, self-enhancement].

**Net:** claim-decomposition + bidirectional entailment, on the Haiku primitive,
with a local-NLI drop-in reserved for the $0 CI bar and later cost-down. This is
the convergent recommendation of three of the four research families
[claim-decomposition rec; qag rec; coverage-omission rec].

---

## 2. THE ALGORITHM

### 2.1 Data model (all reused)

For a stop, `source_facts(stop)` = the union over the stop's CITED beats of
`key_claims + split_sentences(script_body)` — identical to the support set the
current faithfulness gate already builds (`verify.py:220-224`), and the same
body-sentence fallback the coverage baseline already uses (`_claims_for_coverage`,
`claim_dedup.py`, via `generation.split_sentences`). `narration_sentences` = the
composed stop's beat-sourced sentences (`Script.script` filtered to `stop_idx`).

```
FactCheckResult = {
    unsupported_claims: list[str],   # atomic narration claims NOT entailed by source_facts
    missing_facts:      list[str],   # source_facts NOT entailed by the narration
}
```

### 2.2 FAITHFULNESS pass (output → source) → `unsupported_claims`

1. `atomic_claims = decompose_narration(narration_text)` — ONE Haiku call
   (§2.4), returns only checkworthy, self-contained atomic claims (evocative
   framing / second-person / pure opinion dropped; pronouns resolved).
2. For each `c in atomic_claims`, run the EXISTING primitive UNCHANGED:
   `entails(key_claims=source_facts, sentence_text=c)` (`verify.py:119`). This
   asks "is claim `c` fully supported by the source facts?" — the primitive's
   exact semantics. `NO` (fail-closed) → append `c` to `unsupported_claims`.
   Calls are independent → run through the existing `ThreadPoolExecutor`
   concurrency pattern (`_FAITHFULNESS_MAX_WORKERS = 8`, `verify.py:90`).

Direction check: premise = source_facts, hypothesis = one narration claim. Same
argument order as the primitive — **zero change to `entails` or `_ENTAILMENT_PROMPT`.**

### 2.3 COVERAGE pass (source → output) → `missing_facts`

For each `f in source_facts`, run the SAME primitive with roles SWAPPED:
`entails(key_claims=narration_sentences, sentence_text=f)`. This asks "is source
fact `f` recoverable from the narration?" The premise is the **whole** narration
(all sentences), because a beat fact may be conveyed by two narration sentences
*jointly* — MiniCheck's cross-sentence-synthesis property, which the primitive's
list-premise supports for free [nli-faithfulness/MiniCheck; coverage-omission/MiniCheck,
https://arxiv.org/abs/2404.10774]. `NO` → append `f` to `missing_facts`.

Why one-way (narration ⊨ fact), not bidirectional, for coverage: the specific
fact must be *recoverable* from what the tourist heard. If narration says "in
ancient times" and the fact is "250 BC," narration ⊭ fact → correctly flagged a
dropped-precision miss; the `_ENTAILMENT_PROMPT`'s existing "adds/overstates"
clause does not misfire because the hypothesis is the specific fact
(`verify.py:91`). Bidirectional mutual-entailment is the presence rule the
literature recommends against FALSE misses from heavy paraphrase
[llm-judge/Semantic-Uncertainty, https://arxiv.org/abs/2302.09664]; here the
one-way semantic entailment already absorbs pure rewording, so we keep it one-way
and reserve mutual-entailment as a borderline-only re-check (§2.5).

### 2.4 Prompts

**Entailment (REUSED VERBATIM, both directions)** — `_ENTAILMENT_PROMPT`,
`verify.py:91`: strict fact-checker, `YES` iff "fully supported," `NO` if it
"adds, contradicts, or overstates," max 5 output tokens, only an explicit `YES`
passes (fail-closed, `verify.py:135`). No new entailment prompt is needed for
either direction — this is the core reuse.

**Decomposition (NEW)** — `_DECOMPOSE_PROMPT`, CoT-then-JSON, loose schema
[llm-judge/"Let Me Speak Freely"]:

```
System (cacheable): "You split a walking-tour narration into its ATOMIC,
CHECKWORTHY factual claims. A claim states EXACTLY ONE verifiable fact (one
date, person, place, measure, or relationship) and stands alone (resolve
'it/there/this' to the named subject). EXCLUDE: second-person address, sensory
or imaginative framing ('imagine standing here'), opinions, and rhetorical
questions — these are narration craft, not facts to check. Do NOT split a
compound fact that loses meaning when split. First, in a `reasoning` field,
walk the narration and mark each span factual-vs-framing; THEN return the
claims."
Few-shot: 2-3 grounded tour examples pinning (a) an evocative sentence that
yields ZERO claims, (b) a compound-but-atomic fact kept whole, (c) pronoun
resolution.
Output (loose json_schema): {"reasoning": str, "claims": [str, ...]}
```

The `reasoning`-before-`claims` order is load-bearing: JSON-first tanks
extraction quality [llm-judge/"Let Me Speak Freely",
https://arxiv.org/abs/2408.02442].

### 2.5 Model tier, determinism, self-consistency

- **Tier:** Haiku (`FAITHFULNESS_MODEL = "claude-haiku-4-5-20251001"`,
  `verify.py:88`) for BOTH the decomposition and the entailment — the tier this
  repo already trusts for a $0-in-the-bar entailment gate, and MiniCheck's result
  says GPT-4-level grounded checking does not require a frontier model
  [nli-faithfulness/MiniCheck].
- **Determinism (mandatory):** `temperature=0, top_p=1`, fixed model version,
  fingerprinted prompts (the compose suite already pins `PINNED_PROMPT_FINGERPRINT`;
  editing either prompt must turn that test RED on purpose — memory
  `compose-regression-system`). This is NOT optional polish: the repair loop
  re-verifies after rewrite, and `verify.py:127` documents that a borderline verdict
  MUST be identical every run or "the gate flakes and a compose that just passed
  fails on the post-repair re-verify (never converges)" [and llm-judge determinism].
- **Self-consistency: NOT in the serving/repair path.** K-sample majority vote
  needs temp>0, which breaks the convergence invariant above. The research agrees
  it should be used "sparingly," only on low-confidence items [llm-judge/self-consistency,
  https://arxiv.org/abs/2203.11171]. We keep serving deterministic single-shot; a
  K=3 mutual-entailment re-check (both directions must agree) is available ONLY in
  the offline calibration harness for borderline items, never in serving.

### 2.6 Cost per stop

Assumptions (stated, conservative): 4 chars/token; Haiku 4.5 $1.00/1M input,
$5.00/1M output (memory `compose-regression-system` / claude-api ref); a stop
seats ~4 cited beats → ~12 source facts (claims + body sentences); a 150-word
narration → ~8 checkworthy atomic claims after the checkworthiness filter drops
~30% evocative material.

| Component | Calls | Input tok | Output tok | Cost |
|---|---:|---:|---:|---:|
| Decompose narration | 1 | ~1,000 | ~184 | $0.0019 |
| Faithfulness entailment | ~8 | ~2,384 | ~40 | $0.0026 |
| Coverage entailment | ~12 | ~3,360 | ~60 | $0.0037 |
| **Per stop (uncached)** | ~21 | | | **≈ $0.008** |

Reductions on the SAME work: prompt-cache the constant entailment scaffold + the
shared source-facts (across the 8 faithfulness calls) + the shared narration
premise (across the 12 coverage calls) → **≈ $0.004/stop**. A ~15-stop tour ≈
$0.12 uncached / $0.06 cached; the offline eval batch is another −50% via the
Batches API. **Swap the entailment head to a local MiniCheck/AlignScore
`FaithfulnessChecker`** and the ~20 entailment calls go to **$0**, leaving only
the ~$0.002/stop decompose call (or $0 if decomposition also runs local). All
live spend stays behind the money-guard (printed estimate + explicit yes, cheapest
rung, memory `feedback-never-waste-anthropic-credits`).

---

## 3. REUSE vs NEW

| Piece | REUSED (unchanged) | NEW |
|---|---|---|
| Entailment head | `HaikuFaithfulnessChecker.entails` + `_ENTAILMENT_PROMPT` (`verify.py:91,119`), BOTH directions via role-swap | — |
| Model / determinism / concurrency | `FAITHFULNESS_MODEL`, temp=0 fail-closed, `ThreadPoolExecutor`/`_FAITHFULNESS_MAX_WORKERS` (`verify.py:88,90,127,135`) | — |
| Source facts | `source_facts = key_claims ∪ split_sentences(script_body)` (`verify.py:220-224`; `generation.split_sentences`) | — |
| Narration decomposition | — | `decompose_narration()` + `_DECOMPOSE_PROMPT` (Haiku, CoT-then-JSON, checkworthy-only) |
| Orchestrator | `FaithfulnessChecker` Protocol as the swap seam (`verify.py:67`) | `SemanticFactChecker.check(narration_sentences, source_facts) -> FactCheckResult` — runs §2.2/§2.3 concurrently |
| Coverage gate | — | **RETIRE** lexical `verify_claim_coverage`/`_signature`/`COVERAGE_MATCH_MIN` from the decision path (banned lexical; refuted, `FIX-B-VALIDATION.md`). Optional: keep as a non-authoritative $0 *prefilter* that may only SKIP a redundant confirming call, never PASS a fact — or drop entirely. |
| Report plumbing | `ValidationReport.faithfulness_failures` / `coverage_failures` (`contract.py:447-448`) | Populate from `FactCheckResult` instead of the sentence-gate + lexical gate |
| Local-NLI option | `FaithfulnessChecker` Protocol (`verify.py:67`) | `MiniCheckFactChecker` / `AlignScoreFactChecker` (same Protocol) for $0 CI + cost-down |

**One line:** the entailment engine, model, determinism, concurrency, source-fact
set, and report fields all already exist; the genuinely new code is (a) one
decomposition call, (b) a thin orchestrator that calls the primitive twice per
item with swapped roles, and (c) retiring the banned lexical coverage gate.

---

## 4. REPAIR LOOP

The plumbing already exists — the fact-checker only supplies BETTER signals.

1. **Compose → check → serve-or-repair**, bounded at `MAX_COMPOSE_ATTEMPTS = 2`
   (initial + one recompose, `compose_gate.py:36`). Per stop, run
   `SemanticFactChecker.check` → `{unsupported_claims, missing_facts}`; map onto
   `faithfulness_failures` (unsupported) and `coverage_failures` (missing) in the
   `ValidationReport` (`contract.py:447-448`). Empty+empty → the stop passes.
2. **Bounded recompose (one attempt).** The existing recompose prompt ALREADY
   feeds these two lists back verbatim: `unfaithful` and
   `dropped_facts_you_must_restore` (from `coverage_failures`), with the
   instruction to weave each dropped fact back "into the sentence that now covers
   that topic; do not re-introduce the repetition" (`compose.py:462-481`). The only
   change is provenance: those lists now come from the semantic checker, not the
   sentence-entailment + lexical-coverage gates.
3. **Deterministic surgical fallback (guarantees termination).** If the single
   recompose still fails, `repair_composed_surgical` drops the flagged sentences
   and splices the offending beats' grounded stitch back — a minimal, grounded edit
   (the RARR minimal-edit-preserving-the-rest principle
   [claim-decomposition/RARR, https://arxiv.org/abs/2210.08726], here deterministic,
   not an LLM edit). This is the fine-grained repair the FActScore per-fact error
   list enables [claim-decomposition/FActScore].
4. **Whole-stop revert (last resort, provably safe).** If the surgical result
   itself fails, revert the stop to its grounded stitch (`repair_composed`). The
   stitch is fact-complete and corpus-verbatim, so it trivially passes BOTH
   directions (a verbatim-corpus narration has empty unsupported + empty missing —
   the existing "corpus is canonical" skip, `verify.py:218`). **Termination is
   therefore guaranteed:** the ladder ends at a state that always passes.

Honesty guardrail: even GPT-4-class checkers top out ~0.63 F1 on false-claim
detection [claim-decomposition/Factcheck-GPT, https://arxiv.org/abs/2311.09000],
so treat the checker as an advisory gate with a safe deterministic floor (steps
3-4), NOT an oracle. A closed-book checker with guaranteed-complete evidence
should beat those web-retrieval numbers (no retrieval miss) but the floor still
protects us.

---

## 5. TEST PLAN

### 5.1 Offline ($0, in `make test` / `make tour-invariants`)

- **Mock checker (default, offline).** A `MockFactChecker` mirroring
  `MockFaithfulnessChecker` (`verify.py:73`): returns configurable
  `{unsupported, missing}` and records calls, so the repair loop's control flow
  and call-counts are asserted at $0 (the gate is already tested this way with
  deterministic stubs, `compose_gate.py:9`).
- **Substring-entailment fake (deterministic full-path).** Reuse the
  `_StrictHaikuLikeChecker` substring-entailment pattern
  (`tests/test_compose_repair_dedup.py:103`, per `DECOMP-PLAN.md` §4b) as the
  entailment head AND a trivial rule-based decomposer, so the WHOLE
  `SemanticFactChecker` runs end-to-end offline and deterministically — no LLM, no
  spend — exercising the real orchestration (not a vacuous golden,
  `DECOMP-PLAN.md` §3.4).
- **Undo-tests (mutation, the bar).** Fixture: a narration that DROPS a known fact
  (the Charing-Cross case, `DECOMP-PLAN.md` §0). Assert the checker lists it in
  `missing_facts`. Revert the coverage direction (or the checkworthiness filter) →
  the drop is no longer caught → the test goes RED. Mirror for faithfulness: a
  fixture narration that INVENTS a fact must land in `unsupported_claims`; revert →
  RED. (QA undo-test discipline, `CLAUDE.md`; `DECOMP-PLAN.md` §3.4.)
- **Invariants.** Every source fact lands in exactly one of {covered, missing};
  every atomic narration claim in {supported, unsupported}; a verbatim-stitch
  narration yields empty+empty; an evocative-only sentence yields ZERO atomic
  claims (checkworthiness holds — no false `unsupported`). Wire into
  `make tour-invariants` / `make test-unit`, $0.
- **Prompt fingerprint.** A `test_fixtures_pinned_to_prompt` analog: editing
  `_DECOMPOSE_PROMPT` (or the reused `_ENTAILMENT_PROMPT`) turns a pinned-fingerprint
  test RED on purpose, forcing a re-pin (memory `compose-regression-system` GOTCHA).

### 5.2 Cheap live validation — the two known fact-droppers (money-gated)

The prior live compose validation left two stops as the headline coverage
failures — **Palais 44%** and **Notre-Dame 50%** of source facts conveyed (i.e.
half-plus dropped). These are the acceptance targets: the semantic checker must
CATCH what the lexical gate MISSED.

- **Step A — replay, don't recompose ($0 compose, ~$0.02 checker).** Run
  `SemanticFactChecker.check` on the ALREADY-COMPOSED, saved narration for those
  two stops (no new compose spend — only the checker's ~$0.008/stop entailment
  calls). EXPECTED: `missing_facts` surfaces the specific dropped facts (the
  ~56% / ~50% that went missing). This is the acceptance proof the semantic gate
  sees the drop the 0.34-overlap lexical gate passed (`claim_dedup.py`
  `COVERAGE_MATCH_MIN`; `FIX-B-VALIDATION.md`).
- **Step B — no-false-positive control.** Run it on the GROUNDED STITCH for the
  same two stops → `missing_facts` empty, `unsupported_claims` empty (stitch is
  fact-complete + corpus-verbatim). Confirms the checker isn't just trigger-happy.
- **Step C — repair proof (only if A/B pass, separately money-gated A/B).** Feed
  the signal through the one bounded recompose and re-check → both lists shrink to
  empty (or the deterministic floor catches the residue). Undo: revert one restored
  fact → coverage goes RED (matches `DECOMP-PLAN.md` §3.4 live-undo discipline).

All live runs: printed cost estimate + explicit user yes, cheapest rung (1
candidate, not best-of-N), never re-run to re-confirm a finding (memory
`feedback-never-waste-anthropic-credits`). Estimate for A+B ≈ 4 stop-checks ≈
$0.03. This is Tier-2/3 user-facing, so it also needs a skeptic panel + acceptance
read before any milestone claim (`CLAUDE.md` Judge Protocol).

---

## 6. Risks / honest caveats

1. **Decomposer under-extraction** (misses a fact in the narration) → a genuine
   invention slips. Mitigation: an independent researcher agent re-derives claims
   and diffs, per the automated-review-before-human rule (`DECOMP-PLAN.md` §3.3;
   `CLAUDE.md`); the undo-test on the Charing-Cross case must go RED on revert.
2. **Decomposer over-extraction / mis-flagging evocative craft** → false
   `unsupported_claims` that would strip legitimate narration voice (the RUBRIC's
   whole point). Mitigation: VeriScore checkworthiness few-shot + the
   evocative-yields-zero-claims invariant [claim-decomposition/VeriScore].
3. **Checker is not an oracle** (~0.63 F1 ceiling on hostile false-claim detection
   [claim-decomposition/Factcheck-GPT]). Mitigation: the deterministic surgical +
   stitch-revert floor (§4) means a checker miss degrades to a grounded telling,
   never a shipped hallucination.
4. **Local-NLI threshold drift.** Before MiniCheck/AlignScore is authoritative,
   calibrate its threshold against a hand-labeled "which facts were dropped" set
   (α≈0.75 target) [coverage-omission/ACU]; until then it is CI-only, Haiku serves.
5. **Complementary to `DECOMP-PLAN.md`, not a substitute.** That plan atomizes the
   SOURCE (offline, corpus); this design atomizes the NARRATION (serve-time). If it
   lands, coverage source facts are already atomic (cleaner); if not, this design
   still decomposes the narration for faithfulness. They compose.

---

## Appendix — citation map

RESEARCH (family/method → arXiv): FActScore https://arxiv.org/abs/2305.14251 ·
VeriScore https://arxiv.org/abs/2406.19276 · Factcheck-GPT
https://arxiv.org/abs/2311.09000 · SAFE https://arxiv.org/abs/2403.18802 · FacTool
https://arxiv.org/abs/2307.13528 · RARR https://arxiv.org/abs/2210.08726 · MiniCheck
https://arxiv.org/abs/2404.10774 · AlignScore https://arxiv.org/abs/2305.16739 ·
SummaC https://arxiv.org/abs/2111.09525 · QAGS https://arxiv.org/abs/2004.04228 ·
QuestEval https://arxiv.org/abs/2103.12693 · Q² https://arxiv.org/abs/2104.08202 ·
QAFactEval https://arxiv.org/abs/2112.08542 · TRUE https://arxiv.org/abs/2204.04991 ·
ACU/RoSE https://aclanthology.org/2023.acl-long.228/ · Lite2Pyramid
https://arxiv.org/abs/2109.11503 · G-Eval https://arxiv.org/abs/2303.16634 ·
"Let Me Speak Freely" https://arxiv.org/abs/2408.02442 · MT-Bench
https://arxiv.org/abs/2306.05685 · Semantic Uncertainty
https://arxiv.org/abs/2302.09664 · Self-consistency https://arxiv.org/abs/2203.11171.
(Research access caveat, carried from source: figures were WebFetch-summariser-
extracted from arXiv/ar5iv/GitHub, cross-consistent with the papers; verify exact
decimals against the PDFs before hard-coding any threshold.)

CODE: `src/tour/verify.py` (`_ENTAILMENT_PROMPT`:91, `entails`:119,
`FaithfulnessChecker`:67, `MockFaithfulnessChecker`:73, `FAITHFULNESS_MODEL`:88,
`_FAITHFULNESS_MAX_WORKERS`:90, determinism:127, fail-closed:135, support set:220-224,
canonical skip:218) · `src/tour/claim_dedup.py` (`verify_claim_coverage`,
`_claims_for_coverage`, `_signature`, `COVERAGE_MATCH_MIN=0.34`) ·
`src/tour/compose_gate.py` (`MAX_COMPOSE_ATTEMPTS`:36, stub-tested control flow:9,
`repair_composed_surgical`) · `src/tour/compose.py` (recompose feedback:462-481) ·
`src/tour/contract.py` (`ValidationReport`:423, faithfulness/coverage failures:447-448)
· `tests/test_compose_repair_dedup.py` (`_StrictHaikuLikeChecker`:103).
