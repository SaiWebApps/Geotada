# Keyless-corpus fact-loss fix — DESIGN + COST + FORECAST (Path B decomposition)

STATUS: DESIGN ONLY. Nothing built. This documents the real fix for the
keyless-beat fact-loss blind spot, forecasts it against the REAL corpus, gives an
exact cost, and compares it honestly to the cheaper additive-only opener.

Read first: `FIX-B-VALIDATION.md` (REJECTED #1/#2/#3 + "the ACTUAL viable paths"),
memory `tour-quality-root-cause.md`. The convergent, un-relitigated conclusion:
the LEXICAL coverage gate CANNOT be Fix B's safety net; four lexical guards were
refuted. The fix must make each fact ATOMIC (so the EXISTING per-claim coverage
gate catches a drop) and be SEMANTIC (an LLM does the decomposition).

---

## 0. The established problem (one paragraph, not re-litigated)

Keyless beats — London 561 (100% keyless), Paris 417, New York 318, **1,296
total** — carry `key_claims=()`. `_claims_for_coverage` (`src/tour/claim_dedup.py:333`)
therefore falls back to using each whole `script_body` SENTENCE as one pseudo-claim.
A London body sentence packs multiple facts ("a significant landmark since the
1200s, with distances to London measured from Charing Cross"). The coverage gate
scores realization with the overlap-coefficient `|a∩b|/min` at threshold 0.34, which
is BLIND to a subset deletion: drop one fact inside that sentence and the composed
text still overlaps the pseudo-claim ≥0.34, so the gate passes. That is why proven
Fix B (hook opener, labels 2→0, engagement +49%) silently drops "Charing Cross /
distances measured from here." Simultaneously, keyless dedup (`suppress_repeated_claims`)
is a NO-OP on these beats (no `key_claims` → no signatures → nothing to dedup).
**Populate each keyless beat's `key_claims` with atomic, grounded single facts and
BOTH problems dissolve with zero new gate machinery.**

---

## 1. EXTRACTION APPROACH

### 1.1 Model — Haiku 4.5

`claude-haiku-4-5` ($1.00/1M input, $5.00/1M output). Rationale:
- Atomic-fact decomposition of a 20–80-word grounded body is a bounded extraction
  task, not open reasoning — Haiku is calibrated for exactly this (it already runs
  the project's live faithfulness entailment, `verify.FAITHFULNESS_MODEL =
  claude-haiku-4-5`).
- It is the same tier the project already trusts for a $0-in-the-bar gate, so no
  new capability assumption.
- Haiku 4.5 supports structured outputs (`output_config.format`, json_schema) —
  required so every beat returns a schema-valid claim list. It does NOT support
  `effort`/adaptive thinking (those 400 on Haiku 4.5); use plain
  `client.messages.create` with `output_config.format`, temperature omitted.

This is an OFFLINE ONE-TIME pass over `data/{city}/beats.json`, not a serving path.
It runs where public PyPI + `ANTHROPIC_API_KEY` are reachable (the money-guard rung
per memory `feedback-never-waste-anthropic-credits`: printed estimate + explicit yes
before any spend).

### 1.2 Prompt shape (decompose a body into atomic, grounded claims)

System prompt (cacheable, ~850 tok): "You split a walking-tour beat's body into
its ATOMIC factual claims. Each claim states EXACTLY ONE fact (one date, one
person, one measure, one relationship). Invent nothing; add no fact absent from the
body. For each claim also return `quote`: the verbatim span of the body that
supports it. Prefer 1 claim per independent fact; a sentence with two facts becomes
two claims. Keep a compound fact that cannot be split without loss as one claim."
Plus 2–3 grounded few-shot examples (one London-short, one Paris-long, one
accented/possessive) to pin the granularity.

User content per beat: `poi_name` + `script_body` (the grounding target). The
`source_passage` / chunk is NOT sent as input — the body is already the corpus-
verbatim grounding surface (it is what `verify_faithfulness` entails against today),
and keeping input small is the cost lever.

Output schema (json_schema, strict): `{ "claims": [ { "claim": str, "quote": str } ] }`.

Target granularity: mirror the keyed corpora, which average **3.12 claims/beat
(Paris)** and **2.89 (New York)**. London bodies are short (avg 23 words) → ~2
claims; Paris/NY keyless bodies are long (avg ~80 words) → ~3–4 claims.

### 1.3 GROUNDING GUARANTEE (reuse existing faithfulness machinery — no invention)

Two deterministic-then-semantic gates, both reusing machinery already in the repo:

1. **Quote-in-body (deterministic, $0)** — reuse the `verify_provenance` pattern
   (`src/tour/verify.py:61`, `rapidfuzz.fuzz.partial_ratio ≥ 88`). Each claim's
   `quote` must fuzzy-match the beat's `script_body` ≥ 88. A claim whose quote is not
   in the body is DROPPED (the model hallucinated a span). This is the same
   substring-tolerant check that already guards `source_passage` against its chunk.
2. **Claim-entails-quote (semantic, Haiku)** — reuse `HaikuFaithfulnessChecker.entails`
   (`src/tour/verify.py:119`) UNCHANGED: `entails(key_claims=(quote,), sentence_text=claim)`
   must return YES. This is the exact entailment the compose gate already runs; it
   rejects a "claim" that overstates or adds to its own quote. A NO drops the claim.

Only claims passing BOTH gates are written. A beat that ends with < 1 surviving
claim is left keyless (fail-open: it keeps today's whole-sentence pseudo-claim
baseline — no regression) and flagged for human review.

### 1.4 Idempotence / review

- **Idempotent by content hash.** Beats carry `script_body_hash`. The pass writes
  `key_claims` only for beats whose body hash is unchanged since extraction; a
  re-run over an unchanged corpus is a no-op (skip any beat already keyed unless
  `--force`). Never overwrites an already-keyed beat (Paris/NY keyed beats are
  untouched — the pass targets `key_claims == ()` only).
- **Grounded-by-construction, then human-gated.** Per CLAUDE.md "automated review
  before human review": each candidate beat's claim set passes the automated review
  suite (§3.4) BEFORE the human sees it — the human reviews verdicts+evidence, never
  raw candidates.
- **Atomic write + Neo4j push already exists.** Write claims into `beats.json`, then
  push to the live graph via the EXISTING non-destructive backfill
  `scripts/upload_paris.py::_backfill_provenance` (MATCH by `beat_id`, `SET
  beat.key_claims = b.key_claims`) — it already writes `key_claims` and is safe to
  re-run against a live graph (it does NOT plain-SET destructive fields). This is the
  push path; the engine reads `key_claims` from Neo4j via `selection.py:488`, NOT from
  `beats.json`, so the backfill is mandatory, not optional.

---

## 2. EXACT COST

Real census (parsed from `data/{london,paris,new_york}/beats.json`):

| City      | keyless beats | avg body chars | avg body words | target claims/beat |
|-----------|--------------:|---------------:|---------------:|-------------------:|
| London    |           561 |            141 |             23 |                  2 |
| Paris     |           417 |            491 |             83 |                4 |
| New York  |           318 |            481 |             80 |                4 |
| **TOTAL** |     **1,296** |                |                |                    |

### Token model (assumptions stated; no live tokenizer call — offline design)
- **4 chars/token** for English prose (Anthropic tokenizer; conservative — real is
  often 3.5–4, so this slightly OVER-estimates input).
- System prompt + few-shot: **850 input tok**, counted IN FULL per beat (conservative
  — it is prompt-cacheable, so the real figure is lower; see caching line below).
- Per-beat wrapper (json scaffold + poi_name + instruction): **60 input tok**.
- Body input tok = avg_body_chars / 4.
- Output = claims × 52 tok (claim ~18 + verbatim quote ~28 + json ~6) + 20 tok array
  wrapper. London (2 claims) = 124 out tok; Paris/NY (4 claims) = 228 out tok.

### Arithmetic (Haiku 4.5: input $1.00/1M = $1e-6/tok, output $5.00/1M = $5e-6/tok)

| City     | beats | in/beat | out/beat | in cost                | out cost               | **std cost** |
|----------|------:|--------:|---------:|------------------------|------------------------|-------------:|
| London   |   561 |     945 |      124 | 561·945·$1e-6=$0.530   | 561·124·$5e-6=$0.348   |   **$0.878** |
| Paris    |   417 |   1,033 |      228 | 417·1033·$1e-6=$0.431  | 417·228·$5e-6=$0.475   |   **$0.906** |
| New York |   318 |   1,030 |      228 | 318·1030·$1e-6=$0.328  | 318·228·$5e-6=$0.363   |   **$0.690** |
| **TOTAL**| 1,296 |         |          |                        |                        |   **$2.474** |

### ► SINGLE TOTAL-DOLLAR FIGURE: **≈ $2.50** (Haiku 4.5, standard sync, uncached — conservative upper bound)

Two legitimate reductions on the SAME work (state, don't hide):
- **Batches API −50%** (`messages.batches`; a one-time offline job of 1,296 requests
  is the textbook batch case, ≤24 h turnaround): **≈ $1.24**.
- **Prompt-cache the 850-tok system prompt** (read at ~0.1× after the first): saves
  ~$0.99 on the sync path → **≈ $1.48 sync**, or stacked with batching **< $1.00**.

**All-in with the automated grounding/review pass (§3.4):** the per-claim entailment
verification over the ~4,000 produced claims is another Haiku pass with tiny (YES/NO)
output ≈ **$0.70**. Grand total, worst case (sync, uncached, incl. verification):
**≈ $3.2**. Recommended path (batched + cached, incl. verification): **≈ $1.5**.
Either way the spend is trivial and one-time; the risk is quality, not dollars.

---

## 3. BLAST RADIUS

Populating `key_claims` changes behavior in every consumer that keys on it. Grep
(`grep -rn key_claims src/`) enumerates them:

### 3.1 What consumes `key_claims` (and how each changes)

| Consumer | File:line | Today on keyless | After population | Risk |
|---|---|---|---|---|
| **Coverage baseline** | `claim_dedup.py:343` `_claims_for_coverage` | whole body SENTENCE | atomic claims | **INTENDED FIX** — per-fact deletion now caught |
| **Cross-beat dedup** | `claim_dedup.py:166` `suppress_repeated_claims` | NO-OP (no sigs) | now dedups keyless twins | keyless London/NY dup facts start collapsing |
| **Compose input** | `compose.py:360,382` `_compose_user_prompt` | `key_claims: []` | atomic claims shown | model gets units to fuse (quality ↑) |
| **Semantic-dedup prompt** | `compose.py:278` | nothing to group | can group by claim | quality ↑ |
| **Reflections** | `verify.py:159` `_visited_claims` | keyless beats contribute **nothing** → London gets **NO reflections** (empty union → slots dropped in `build_compose_request`) | keyless beats now feed reflection synthesis | **NEW CONTENT** — London gains reflections; fail-closed by the entailment gate |
| **Faithfulness support** | `verify.py:213-223` `verify_faithfulness` | entails vs `script_body` only | support = `key_claims ∪ script_body` | strictly MORE lenient (union); claims are body-derived → no new admits |
| **Canonical context** | `validation.py:179,198` | body already included | + claims | NO regression — claims ⊂ body already in context |
| **Neo4j read** | `selection.py:488,574` | reads `()` | reads populated | requires the backfill push (§1.4) |

### 3.2 What could REGRESS

1. **Served duplication via the latent cascade bug** — the prerequisite, per
   FIX-B-VALIDATION REJECTED #3 and CONFIRMED on current committed code (offline, $0).
   `compose_gate.py:205-213` splices a grounded stitch for an uncovered beat WITHOUT
   checking `surviving_composed_beat[k]`; if a coverage failure fires on a beat whose
   composed sentence SURVIVED, the stitch is appended BESIDE the surviving twin →
   duplication. **Decomposition makes this fire AT SCALE** — atomic `key_claims` make
   per-fact coverage failures common (a survivor realizes claim-1, compose drops
   claim-2 → the beat is uncovered → full stitch spliced beside the survivor → claim-1
   voiced twice). `_prefer_deduped` does NOT rescue it (measured: the real Trafalgar
   pair scores rapidfuzz `token_set_ratio` 81.2, a "Remarkably, {claim}, …still
   celebrated today" survivor 77.0 — both < the 90 threshold of
   `suppress_same_beat_near_duplicates`; and `suppress_repeated_claims` keeps both,
   forward-only, or no-ops entirely on keyless beats). **Full specification, options,
   and the undo-tested proof are in §4b — this fix LANDS WITH the decomposition, not
   separately.**
2. **Over-gate from over-extraction** — splitting one fact into two claims makes the
   gate demand both survive a legit fusion (§4).
3. **0.34 threshold cliff on SHORT claims** — a 2–3-token atomic claim can fail a
   faithful paraphrase at overlap 0.333 (§4).
4. **New reflections on London** are user-visible content that never existed; must be
   acceptance-checked, not just gate-checked.

### 3.3 Gate (per CLAUDE.md automated-review-before-human)

Per-item (per beat), BEFORE human sign-off, the automated review suite runs:
- **Independent researcher agent** (Haiku/Sonnet): re-derives the atomic facts from
  the body independently and diffs against the extracted claims — flags MISSED facts
  (under-extraction) and INVENTED claims.
- **Hostile judge** (Opus, per Judge Protocol): tries to break each claim — is it
  atomic? grounded in its quote? does the set drop a fact the body states? Rules
  PROCEED / PROVE-FIRST / STOP per beat.
- Deterministic checks (§1.3): quote-in-body rapidfuzz ≥ 88; claim-entails-quote
  Haiku YES; no dead/empty claims; ≥ 1 surviving claim.
The human reviews the verdicts+evidence per beat, never raw candidates. Run on a
STRATIFIED sample first (short London, long Paris, accented, possessive, multi-year)
to calibrate the prompt before spending on all 1,296.

### 3.4 Proof gates before shipping (Tier-3, per CLAUDE.md)
- `make tour-invariants` + goldens must import and EXECUTE the changed path (the
  vacuous-proof trap from REJECTED #3: goldens generate stitch-only tours and don't
  exercise `claim_dedup`/`compose`). Add a real-corpus test that runs coverage over
  keyed keyless beats.
- Live re-validation of Fix B on the London West End tour (money-gated) to prove the
  Charing Cross drop is now CAUGHT (undo-test: revert one claim → coverage goes RED).
- Skeptic panel (2–4, different models) + acceptance read of a real London tour
  (new reflections included) before the milestone claim.

---

## 4. FORECAST — failure modes vs REAL data

| # | Failure mode | Likelihood | Evidence / where it bites | Mitigation |
|---|---|---|---|---|
| F1 | **Over-extraction** (one fact → two claims) → over-gate a legit fusion | **Med** | Compound facts ("renamed to honour the first département to pay taxes") wrongly split → gate demands both fragments survive | Few-shot pins "one independent fact = one claim; don't split a compound that loses meaning"; hostile judge flags non-atomic/over-split; `_prefer_deduped` fail-opens to the complete stitch (no fact lost, just a less-fused telling) |
| F2 | **Under-extraction** (misses a fact) → still blind | **Med** | The exact failure being fixed; a missed "Charing Cross" leaves that fact ungated | Independent RESEARCHER agent re-derives facts and diffs (catches misses the extractor made); undo-test on the headline Trafalgar case must go RED on revert; stratified calibration sample |
| F3 | **0.34 cliff on SHORT claims** — a 2–3-token atomic claim fails a faithful paraphrase at overlap 0.333 | **Med-High** | REJECTED #3 repro: Leicester Square fusion scored 0.333; census one-reword-from-flagged = 136 London / 281 Paris / 327 NY | **Do NOT split below ~4 salient tokens.** Keep claims ≥ `MIN_SHARED_TOKENS`+headroom; a "fact" needs its subject + predicate + a discriminator (name/date/measure), naturally ≥ 4 tokens. Where a fact is irreducibly tiny, keep it fused into a larger claim. This is a prompt/granularity constraint, NOT a threshold change (thresholds are calibrated; don't touch) |
| F4 | **Accented / possessive text** breaks a lexical step | **Low** (semantic path) | REJECTED #1 died on accents/possessives — but that was TOKEN matching. Here extraction is SEMANTIC (Haiku handles "Théâtre des Variétés", "Nelson's"); only the quote-in-body check is lexical, and rapidfuzz `partial_ratio` is diacritic-robust on a verbatim span | Few-shot includes an accented + a possessive example; quote is a verbatim body span so rapidfuzz matches; entailment is the model's job |
| F5 | **Served duplication via cascade** (§3.2.1, §4b) | **High — CONFIRMED on current code; scales WITH decomposition** | Trafalgar pair 81.2 / reframed survivor 77.0 (both < the 90 dedup threshold); `_prefer_deduped` cannot rescue | Land the §4b fix (option **a REPLACE** + option **b** fallback) WITH the decomposition — atomic claims make this fire at scale |
| F6 | **Does decomposition need 2-source** per Pipeline Guardrail #1? | **N/A → No** | Guardrail #1 ("two-source minimum") governs auto-CORRECTIONS that change facts. Decomposition INVENTS NOTHING — it re-expresses the beat's OWN body verbatim-grounded; the source IS the body (already two-source-vetted at extraction). It is a within-source restructuring, not a correction | Grounding gates (§1.3) enforce "no fact not in the body"; hostile judge confirms zero invention. No second source required — but the human sign-off gate stands |
| F7 | **New London reflections** read badly / over-synthesize | **Low-Med** | London currently ships zero reflections; turning them on is new user-facing content | Acceptance-agent read of a real London tour; reflections stay fail-closed (entailment vs visited claims); can gate reflections off for London separately if bad |

---

## 4b. CASCADE PREREQUISITE FIX (lands WITH decomposition — not separately)

CONFIRMED on current committed code (offline, $0), and COUPLED to decomposition:
populating `key_claims` makes keyless per-fact coverage failures common, which is
exactly when this duplication fires at scale. Ship the fix in the same change as the
decomposition.

### The bug (precise)

In `repair_composed_surgical` (`src/tour/compose_gate.py:205-213`), the "Uncovered
beats not tied to a dropped sentence (compose omitted them outright)" branch:

```python
for bid in sorted(uncovered):
    if any(bid in v for v in restored_by_stop.values()):
        continue
    k = beat_stop.get(bid)
    if k is not None:
        _restore(k, bid)          # <-- appends bid's FULL grounded stitch at stop k
```

`uncovered = {bid for bid, _claim in uncovered_report.coverage_failures}` is a set of
BEAT ids. A beat lands in it when ANY of its claims is unrealized — including the case
where a SURVIVING composed sentence at stop `k` still realizes claim-1 while claim-2
was dropped. The branch never consults `surviving_composed_beat[k]`, so it splices the
beat's fact-complete stitch BESIDE the survivor → the shared claim-1 fact is voiced
twice. `_prefer_deduped` cannot undo it: `suppress_same_beat_near_duplicates` needs
rapidfuzz `token_set_ratio ≥ 90` but the reframed survivor scores < 90 (Trafalgar 81.2;
"Remarkably, {claim-1}, a detail still celebrated today" survivor 77.0);
`suppress_repeated_claims` keeps both (the stitch carries a novel claim-2; the earlier
survivor is never dropped, forward-only) and no-ops entirely on keyless beats.
**Atomic decomposition manufactures this scenario routinely** (a keyless beat now has
several claims; keeping one survivor and dropping another is the common fusion outcome).

### Options evaluated

**(a) REPLACE — DROP the single-source survivor, use the stitch.** When restoring an
uncovered beat `bid` that has a surviving composed sentence citing ONLY `bid`
(`cited_beat_ids == (bid,)`, no `also_cites`), remove that survivor from `out_by_stop[k]`
and splice `bid`'s grounded stitch in its place.
- **Correctness:** the stitch is fact-complete for `bid` (carries claim-1 AND claim-2),
  so replacing the partial survivor loses nothing and removes the dup. Preserves the
  REST of the stop's composed sentences (unlike whole-stop revert).
- **Fact-loss risk:** near-zero WITH the guard the coordinator names — a survivor that
  is a FUSED multi-beat sentence (`also_cites` non-empty, or `cited_beat_ids` includes a
  COVERED beat) must NOT be dropped, or that other beat's fact is lost. So the replace
  fires ONLY when the survivor's `cited_beat_ids ⊆ {the uncovered beats being restored}`.
  When the survivor is fused and carries a covered beat's fact, fall through to (b).
- **Proof (undo-tested, offline, real path):** in `tests/test_compose_repair_dedup.py`
  style, use `_StrictHaikuLikeChecker` (substring entailment, `test_compose_repair_dedup.py:103`)
  + a KEYED beat whose ONE stitched sentence carries TWO key_claims, and a
  `_DupBeatClient`-style compose that keeps a < 90-similar single-source survivor
  ("Remarkably, {claim-1}, a detail still celebrated today" → 77.0) realizing claim-1 and
  drops claim-2. ASSERT: composed output voices claim-1 EXACTLY ONCE and claim-2 present
  (fact-complete, dup-free). UNDO: revert the guard → claim-1 voiced TWICE → test RED.
  This executes the real `repair_composed_surgical` path (not a vacuous golden).

**(b) WHOLE-STOP REVERT — route the stop to `repair_composed` when a surgical splice
would duplicate.** If restoring `bid` would append a stitch beside a surviving composed
sentence, revert that whole stop to its grounded stitch.
- **Correctness:** safe, fact-complete. The coordinator's nuance holds: this fires only
  on a stop where compose ALREADY dropped a fact, so that stop's compose is faulty and
  reverting it is the right call.
- **Fact-loss risk:** zero (stitch is fact-complete).
- **Cost:** coarse — a dense stop with several good composed sentences loses ALL of them
  for one dup-causing beat. Correct but quality-lossy.
- **Proof:** same recipe; assert the stop's `verify_report` status is
  `reverted_to_stitched`, no dup, all facts present; undo → dup returns.

**(c) SIGNATURE-SUBSET SUPERSEDE dedup in `_prefer_deduped`.** Generalize
`suppress_same_beat_near_duplicates` from rapidfuzz-90 to a claim-signature SUBSET rule:
if the spliced stitch's signature ⊇ a survivor's signature, drop the survivor.
- **Correctness:** would catch the < 90 lexical cases (81.2 / 77.0) that rapidfuzz misses.
- **Fact-loss risk: MEDIUM, and it re-opens the trap this whole spec exists to avoid.**
  It puts ANOTHER lexical/signature threshold into the very layer the four rejected
  guards proved cannot be a safety net (a false subset — a survivor whose salient tokens
  happen to be a subset but which carries a distinct particular the signature tokenizer
  drops — is wrongly dropped → fact loss). Worse, `_prefer_deduped` FAIL-OPENS: if the
  deduped candidate fails verify it returns the un-deduped (dup-carrying) candidate, so
  (c) does NOT guarantee removal — the dup can still ship. **Reject** — it is exactly the
  "do NOT build a 4th lexical downstream guard" the convergent lesson forbids.

### RECOMMENDATION — (a) primary, (b) bounded fallback, (c) rejected

Ship **(a) REPLACE** as the primary fix (minimal, targets the splice site, fact-complete,
dup-free, preserves the rest of the stop's compose quality), guarded to fire only when
the survivor cites ONLY the uncovered beat(s). For the one case (a) must not touch — a
FUSED survivor also carrying a COVERED beat's fact — fall back to **(b) whole-stop
revert** (correct because that stop's compose already dropped a fact). Reject **(c)**: it
re-introduces a lexical safety net the convergent lesson forbids and its fail-open path
can still ship the dup.

### Blast radius of the fix

Confined to `repair_composed_surgical` (and the `_recompute_fully` /
`_per_stop_verify_report` diagnostic labels, which already recompute reverted-vs-partial
after de-dup — the (a) drop must feed the same recompute so the `verify_report` status
stays accurate). No change to coverage thresholds, to `suppress_*`, or to the serving
control flow. Must ship WITH decomposition: without it, atomic claims turn a latent
occasional dup into a frequent served regression (the Trafalgar "landmark since the
1200s" twice-voiced case); without atomic claims, the fix is correct but rarely exercised.

---

## 5. CHEAPER ALTERNATIVE — additive-only opener (honest assessment)

**Design.** Constrain Fix B so compose does NOT restructure the stop. Instead it
PREPENDS exactly ONE grounded hook sentence and keeps every original stitch sentence
**verbatim**, in order. Enforced at **$0** by a deterministic check: after compose,
every original stitch sentence of the stop must still be present as a
normalized-substring of the composed stop; if any is missing, REVERT that stop to its
stitch. No paid decomposition, no LLM gate, no new coverage machinery — the
substring check is pure string work (like `suppress_exact_repeats`'s `_repeat_key`
normalization already in `claim_dedup.py:231`).

**Does it ship the opener win with ZERO fact-loss risk?**
- **Fact-loss: yes, provably zero.** If every original sentence survives verbatim,
  no fact inside them can be dropped — the Charing Cross drop is structurally
  impossible because that sentence is still there untouched. The deterministic
  substring check is a true guarantee, not a threshold.
- **Opener win: PARTIAL.** It removes the "label as the FIRST thing you hear" (the
  measured driver of stiltedness) by prepending a hook ahead of the label sentence.
  The proven engagement lift came substantially from the hook opener, so a large
  fraction of the +49% is preserved.

**Downsides (state them plainly):**
1. **The label is still recited, just later.** The dwell-stop label sentence ("X is a
   monument in <nested geography>") is kept verbatim per the guarantee — so the
   tourist still hears it, now as sentence 2. Fix B's acceptance win came partly from
   REMOVING the label, not just demoting it; additive-only keeps it.
2. **It fights the existing fusion mandate.** The compose system prompt's core
   directive is "FUSE REPEATS BOLDLY / voice each fact ONCE" (`compose.py:254-283`).
   Forbidding restructuring and mandating verbatim retention DISABLES fusion for these
   stops — so the cross-beat/semantic repetition that is the OTHER half of the
   "stilted/horrible" complaint (memory: Sainte-Chapelle "built to house the relics"
   told 4×) is NOT addressed on keyless stops; it may even be locked in, because a
   verbatim-retention rule prevents the model from collapsing duplicate stitch
   sentences. The additive opener and the fusion mandate are in direct tension.
3. **Prepended hook must itself be grounded** — it can introduce a fact; it needs the
   same glue-grounding the existing forbidden-phrase/invented-noun scan
   (`validation.py`) already applies, so this is covered, but it is one more thing to
   verify.
4. **Doesn't fix the corpus** — the keyless blind spot and the dead keyless dedup
   remain; any FUTURE op that rewrites a keyless stop reopens the hole. Decomposition
   removes the blind spot at the source; additive-only routes around it for this one
   feature.

### Comparison

| Axis | Decomposition (Path B) | Additive-only opener |
|---|---|---|
| Cost | ~$2.5 one-time (≤$1.5 batched+cached) | **$0** |
| Fact-loss risk | Near-zero via atomic gate; needs cascade fix (F5) + calibration (F3) | **Provably zero** (verbatim substring guarantee) |
| Opener win | **Full** (label removed) | Partial (label demoted, still recited) |
| Fixes cross-beat/semantic repetition on keyless stops | **Yes** (dedup turns on) | **No** (fights fusion; may lock repeats in) |
| Reflections on London | Enables them | No change |
| Blast radius | Wide (8 consumers) — needs Tier-3 gating | Narrow (one compose constraint + $0 check) |
| Removes the root blind spot | **Yes, at source** | No (routes around it) |
| Ship speed | Slower (offline pass + backfill + Tier-3 proof) | Fast (prompt constraint + deterministic check) |
| Reversibility | key_claims is additive; backfill re-runnable | Trivially revertible |

---

## 6. RECOMMENDATION — BOTH, sequenced

Do **additive-only opener FIRST**, then **decomposition** — they are complementary,
not either/or, and the cheap one de-risks the expensive one.

1. **Now (this week, ~$0): additive-only opener.** It ships the largest, safest slice
   of the proven opener win with a provable zero-fact-loss guarantee and no paid
   decomposition — the exact "de-label where compose keeps every fact, revert where it
   doesn't" outcome FIX-B-VALIDATION's viable-path A describes, achieved
   deterministically. Re-validate live on the London West End tour. This unblocks the
   HELD Fix B engagement win immediately.
2. **Ship the §4b cascade fix WITH the decomposition** (option **a REPLACE** +
   option **b** fallback; **c** rejected). It is a served-duplication bug on current
   code today and scales with atomic `key_claims`, so it must land in the SAME change,
   proven by the undo-tested `_StrictHaikuLikeChecker` regression test in §4b.
3. **Then (Tier-3, ~$1.5 batched): decomposition.** It is the only option that (a)
   removes the label entirely for the full acceptance win, (b) turns ON keyless
   cross-beat/semantic dedup — the OTHER half of the "stilted/horrible" complaint that
   additive-only cannot touch — and (c) removes the blind spot at the source so future
   keyless-stop rewrites are safe. Gate it with the automated review suite + skeptic
   panel + live undo-test proving the Charing Cross drop is now CAUGHT.

Rationale: the additive opener's fatal limitation (keeps reciting the label, fights
fusion, leaves keyless repetition unfixed) is precisely what decomposition fixes; and
decomposition's risk (F3/F5) is real enough that shipping the $0 win first — while the
corpus fix goes through Tier-3 proof — is the honest sequencing. Neither alone is the
whole answer; the cheap one is not a substitute for the corpus fix, only a fast
down-payment on the opener win.

---

## Appendix — census reproduction

`data/london/beats.json` 561 beats, ALL keyless. `data/paris/beats.json` 1,562 beats,
417 keyless (1,145 keyed, avg 3.12 claims). `data/new_york/beats.json` 2,005 beats,
318 keyless (1,687 keyed, avg 2.89 claims). Keyless total = **1,296**. Body-length and
token arithmetic in §2. Haiku 4.5 pricing $1.00/$5.00 per 1M in/out (authoritative,
via the claude-api reference, 2026-07).
