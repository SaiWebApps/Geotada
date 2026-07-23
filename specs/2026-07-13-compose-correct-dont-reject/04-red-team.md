# 04 — Red Team: Beat-level "correct-don't-reject" compose

**Date:** 2026-07-14 · **Stage:** 4 (Red Team) · **Thinking mode:** Adversarial reviewer
**Panel:** 3 independent reviewers — design/correctness (general-purpose), anti-hallucination
skeptic (ran 4 executable probes against HEAD via `make test-file`, all passed), API/tests/
best-practices (general-purpose). Main agent verified the Makefile and test-existence claims
directly before accepting them. Resolutions below follow the propose-don't-punt rule; each
blocker was code-verified, not auto-promoted.

**Panel verdict in one line:** the contract's core (correct-don't-reject, floor, never-fail)
is sound and worth building, but as WRITTEN the never-lose-a-fact and never-fabricate claims
were refuted/unproven — every hole has a deterministic, cheap fix, adopted below. No Stage-2
re-open; the spec + scopes get amendments.

---

## 1. BLOCKERS (all resolved — amendments to 02/03 listed at the end)

**BL-1. Flagged GLUE sentences have no fate once `drop_failing_sentences` dies.**
The composer rewrites glue too; `validate_script` flags glue for forbidden phrases / new proper
nouns / new years (validation.py:145-163) and bad labels (→ untraceable, validation.py:124-126).
The spec's ladder covers only beat-cited sentences (02-spec Outputs). HIGH × HIGH.
**Resolution:** glue floor = the stitched glue sentence(s) of the same `(stop_idx, source_id)`
(deterministic template text, whitelist-clean by construction). Composer-ADDED glue with no
stitched counterpart is dropped — glue is fact-free by rule, so never-lose-a-fact holds. Spec's
"sentence-drop are removed" wording amended to "beat-content drop is removed".

**BL-2. Vignette sentences are invisible to the ladder and their floor is undefined.**
Per-chapter `beats_by_id` excludes vignette beats (compose.py:646, :663-667); today a rewritten
vignette sentence is silently UNCHECKED (verify.py:278-280). Full-body floor would voice a whole
beat where the design mandates a one-liner (generation.py:736-761). HIGH × HIGH.
**Resolution:** add vignette beats to the verify-side support map (support = their
`script_body`; union/rescue exclusions unchanged); vignette floor = the beat's verbatim FIRST
stitch sentence (`split_sentences(script_body)[0]` — exactly the stitch one-liner); corrector
never changes a vignette sentence's `source_id` (trips.py:614-625 strips by source_id). Fixture:
vignette one-liner with an invented fact → corrected or floored to the one-liner.

**BL-3. Floor source contradiction (01 vs 02) — raw `script_body` floors re-introduce
repetition the stitch already deduped; the all-floor worst case beats today's revert on the
repetition axis.** `suppress_repeated_claims`/`suppress_exact_repeats` run only inside
`generate` (generation.py:227-230) — never on composed output. A 3-beat overlapping stop
flooring all 3 raw bodies voices the shared fact 3×. MEDIUM-HIGH × HIGH.
**Resolution:** floor = the beat's **surviving post-dedup stitch sentences** (composer-chosen
position). Content-safe by dedup's own construction (only already-voiced restatements were
dropped); AC-3's compound ships whole (it IS one stitch sentence); strictly less double-voicing
than raw bodies. 02-spec's "verbatim `script_body`" wording amended to "its verbatim stitch
sentences (the post-dedup `script_body` sentences the stitch voiced)".

**BL-4. (Skeptic F1 — EXECUTED refutation) Fact loss via under-cited paraphrased fusion →
correction-strip.** Probe B proved `_populate_also_cites` cannot find the true owner of a
PARAPHRASED fused fact (zero salient-token overlap) — so "cited beats always names its true
owners" (02-spec) is false; correction "constrained to its cited beats" then legitimately
STRIPS the un-cited beat's fact, re-verify passes, coverage is retired → nothing notices.
Attempt-1's loss in a new coat. HIGH × HIGH.
**Resolution — fact-preserving correction contract (deterministic):** before correcting, diff
the flagged sentence's salient tokens (years, numbers, proper-noun tokens — `_signature`
exists) against its declared citations' bodies. Tokens NOT covered by declared citations mark
the sentence UNDER-CITED: route it to the floor of the stop-union beats owning those tokens
(never to correction, which would strip them). Correction is only allowed when the declared
citations cover the sentence's salient tokens. Fixture: paraphrased under-cited fusion → floor
fires, fact ships.

**BL-5. (Skeptic F2) No seated-beat invariant — a beat the composer omits entirely owns
nothing and is silently lost; coverage (the only net) is retired.** HIGH × HIGH.
**Resolution — the seated-beat invariant replaces coverage as the deletion net:** every beat in
the stop's compose request must own ≥1 shipped sentence (as `source_id` or `also_cites`); a
beat owning none is floored (its stitch sentences, placed adjacent to its POI's block).
Deterministic, works on the 51% `key_claims=()` corpus where even HEAD is blind — strictly
stronger than the machinery it replaces. New AC (folded into AC-3's scope): omitted-beat
fixture → beat floors in.

**BL-6. (Skeptic F3 — EXECUTED at HEAD) The verbatim shortcut ships meaning-inverted
fragments with ZERO entailment calls** ("the Gestapo ever used the cellars…" from a body that
says "He DENIED that…"). A negation-lexicon rule is defeated by attribution-stripping ("the
brochure claims Dalí paid in drawings" → "Dalí paid in drawings"). Full-body-only (the other
Stage-5 option) breaks pass-through economics: every genuine corpus sentence would hit Haiku —
the ticket's false-NO mode on the corpus's own text (verify.py:215-217). HIGH × HIGH.
**Resolution — sentence-unit alignment:** the shortcut passes iff the normalized sentence
equals one or a CONTIGUOUS RUN of complete `split_sentences(script_body)` units of a cited
beat. Kills sub-sentence fragments (both attacks are partial units) while keeping genuine
corpus sentences free. Fixtures: negation-truncation AND attribution-strip (added to AC-2).

**BL-7. (Skeptic F4) Never-fabricate is UNPROVEN — every guarantee terminates in Haiku's
unmeasured false-POSITIVE rate, and the design multiplies draws against it** (2 correction
retries; union support ≈3× text; best-of-N ranking by "fewest corrections" argmaxes checker
leniency). HIGH × MEDIUM.
**Resolution (three parts):**
(a) **Deterministic pre-gate for beat sentences** (the prompt already promises it; VERIFY never
enforced it): any 4-digit year / number / capitalized entity token in a composed-or-corrected
beat sentence absent from its cited beats' `script_body` union FAILS CLOSED before Haiku is
consulted. Mirrors validate_script's existing glue rule (validation.py:167-204).
(b) **FP battery in Scope 1's GO gate:** ~20 corrupted sentences (entity swap, date shift,
relation splice across the stop's real beats = frankenfacts, hedge-strip) that Haiku MUST
reject; the measured FP ceiling joins the FN question as GO/NO-GO criteria.
(c) **Best-of-N ranking:** deterministic pre-gate violations rank FIRST (fabrication-safe),
flagged-sentence count second (flow proxy) — never the LLM verdict alone. Frankenfact +
attribution-strip fixture classes added to AC-2.

**BL-8. (Skeptic F5) Floor collateral unspecified — one reading loses a fact.** S2 cites A+B,
verified, sole voicing of B's fact; A floors. If S2 counts as "A's sentences" it dies and B's
fact vanishes. MEDIUM × HIGH.
**Resolution:** a floor replaces only sentences whose FULL citation set ⊆ the floored-beat set;
a verified fusion co-citing a non-floored beat SURVIVES (bounded double-voicing accepted).
Fixture added.

**BL-9. Verification commands don't exist as written.** `make test-unit PYTEST_ARGS=...` — no
such variable (Makefile:190-191, hard-coded list); `make api-test` starts a SERVER
(Makefile:369-370), it never returns. Verified directly. HIGH(process) × CONFIRMED.
**Resolution:** Scopes 0/2/3 use `make test-file FILE=...` (pure) or `make test-file-local
FILE=...` (Neo4j-backed, 7688); Scope 4's endpoint tests run under `make test-local`. 03-scopes
text corrected.

**BL-10. Deleting the 422 breaks `test_refused_flavour_is_422_and_leaves_trip_untouched`
(tests/test_trip_api.py:701) and no scope owns it.** Verified present. MEDIUM-HIGH × CONFIRMED.
**Resolution:** Scope 4 explicitly rewrites it: rejecting checker → 200, corrected/floored
status, stops re-persisted, `composed_route_id` set (assertions invert — the trip IS now
modified). Also: `test_tour_compose.py:290` (whole-tour `ComposeVerificationError`) dies in
Scope 4 — owned there too.

**BL-11. AC-10's "workbench review queue" doesn't exist, and counts persist only on the
`/compose` path while the workbench only exercises PREVIEW (persists nothing).** review.html is
the pipeline-editorial tool; tour-preview.html renders one status string. HIGH × CONFIRMED.
**Resolution — scope AC-10 to what's real:** (1) persist per-stop counts + tour status on
Trip/ItineraryItem at `/compose` (4 layers named: gate → route_script_to_stops →
_create_itinerary_items Cypher → response models — all additive, no migration, no MERGE-key
implications); (2) per-stop statuses + tour rollup on BOTH response models; preview counts are
response-only + one structured log line (drift observable while compose is preview-only);
(3) minimum queue = a `flagged` filter on the existing trips list endpoint + a status badge on
tour-preview.html (text, not color-only); richer UI stays in the follow-up spec. Data-inventory
note (SECURITY_PRIVACY_PRACTICES §16) added to Scope 5.

**BL-12. No per-TOUR cost/latency ceiling — the worst case (Haiku broadly refusing) is exactly
the live failure mode being fixed**: ~150 flagged sentences × 2 attempts ≈ +300 Opus calls; a
fully-flagged 15-sentence stop corrected serially ≈ 3-8 min; every concurrent tour degrades the
same way. HIGH × HIGH.
**Resolution:** per-tour correction budget = `2 × stop_count` (constant, tunable); on
exhaustion remaining flagged beats floor immediately (floor is LLM-free and safe). Corrections
for different sentences run CONCURRENTLY (same ThreadPoolExecutor pattern); the per-sentence
attempt→re-verify chain is the only serial unit. Added to spec Constraints + AC-8's assertion.

**BL-13. (Skeptic F6 + design) Partial systemic failure is undefined — mixed scripts, stale
counts.** LOW-MEDIUM × MEDIUM, promoted to blocker because the resolution changes the ladder.
**Resolution:** correction-call failure ⇒ FLOOR (deterministic, always available) — stitch
fallback fires ONLY when a stop's COMPOSE call itself fails, per-stop; a `stitched_fallback`
stop is excluded from (never averaged into) threshold math. Partial-outage fixture (raise on a
subset of stops) added to Scope 4. AC-11's stub raises a MIX (anthropic APIError + ValueError +
JSONDecodeError — truncation surfaces as ValueError, compose.py:502-506).

## 2. RISKS (accepted with mitigations; owners assigned)

- **R-1 Audio totals go stale after correction/floor** (pre-existing for the old rungs too:
  compose_gate.py:72-73,:111 never recompute). → Scope 3: recompute `_sum_audio` as the gate's
  LAST step; floored-fixture asserts it. Scope 5 telemetry carries floored-audio seconds
  (silence-budget visibility, ≤60% rule).
- **R-2 Correction-loop shape:** assemble → verify WHOLE tour → correct per flagged sentence →
  re-verify affected checks. Per-stop verification would falsely flag legit glue callbacks
  (validate_script's canonical context is whole-script: validation.py:141-143). → Stage 5 fixes
  the shape; stated here so it's a decision, not an accident.
- **R-3 `_beat_support_signature` still unions key_claims tokens** (compose.py:106-112) —
  breaks the declared parity invariant (verify.py:246) once support is body-only. → Scope 2
  re-bases it (and compose_metrics) body-only in the same commit.
- **R-4 Union-rescue citation gain widens floor blast radius** (rescue→correct→fail chain could
  floor a whole stop). → Gain only the MINIMAL token-justified subset (reuse
  `_populate_also_cites` logic); rescue→fail fixture.
- **R-5 Scope 4∥5 collides with one-developer-per-file** (both edit trips.py + compose.py) AND
  C1: landing 4 before 5 ships silent-degradable persisted trips with no telemetry. → Order
  becomes `0 ∥ 1 → 2 → 3 → 5 → 4 → 6`. Dissolves both.
- **R-6 `_compose_status` heuristic inverts** (byte-equality reads floored as composed;
  trips.py:693-705). → Scope 5 DELETES it; statuses derive from gate counts
  (`composed | composed_corrected | composed_floored | stitched_fallback | stitched`;
  `refused` retires). Mobile never reads compose_status (grep-verified); additive-safe.
- **R-7 Whole-tour path has no golden.** → Scope 0 pins BOTH entry points (one extra golden,
  same fixture).
- **R-8 Threshold calibration from n=1** (one dense Paris stop is the tail, not the
  distribution). → Calibrate from Scope 6's run PLUS the mock/replay scoreboard across existing
  fixture tours; constants marked provisional with a telemetry-review trigger.
- **R-9 Reflections-removal leftovers** (ComposeRequest.slots, `_is_transit_sentence`,
  `_reflection_text`, reflection.py module, `_visited_claims`; KEEP the `GLUE_REFLECTION` label
  for legacy traceability). → Scope 3 removal checklist; its own commit inside the scope
  (halves the skeptic-panel diff).
- **R-10 `FaithfulnessChecker.entails(key_claims=...)` param name becomes a lie.** → Scope 2
  renames to `support` (Protocol is structural; stubs unaffected).
- **R-11 Scope 6's "stop-2 ≠ stitch" passes even if the fusion FLOORED.** → Add machine
  assertion: a sentence citing `85ebe707` (±`c3d4a78a`) ships with status verified|corrected —
  the fusion survives AS a fusion; then the human judges quality (AC-9).
- **R-12 Scope-1 probe under-sampled.** → Probe adds: an unchanged-corpus-sentence case, a
  `key_claims=()` beat, and BL-7's FP battery. Transcript must not echo env/keys.

## 3. OPEN QUESTIONS (user's call — none block Stage 5 prep)

None remaining — the panel's questions all had clear technical resolutions (adopted above).
Product-flavored calls made by recommendation, veto anytime: (a) AC-10 queue = minimal
filter+badge now, richer UI parked; (b) best-of-N keeps a flow term but ranked AFTER the
deterministic fabrication gate; (c) scope order 5-then-4.

## 4. CODEBASE CONFLICTS (verified)

- compose.py:677-682 comment ("systemic failure must SURFACE") is the design being reversed —
  Scope 4 updates the comment (the honest `stitched_fallback` status answers its rationale).
- `ComposeVerificationError` remains raised by compose_gate.py:147 until Scope 4; its coverage
  line (compose_gate.py:53) dies with Scope 3. Import in trips.py:44 orphans at Scope 4.
- `serve_or_block` / `compose_and_verify(repair=)` become dead post-Scope-4 — swept there or
  explicitly logged to the follow-up cleanup spec (one owner, stated in 05-plan).
- Q2 (whole-tour path): `build_compose_request` puts ALL plan beats in `beats_by_id`
  (compose.py:88) — a composer-invented citation of a bodyless beat (`script_body=None`,
  contract.py:138) must be STRIPPED deterministically pre-verify; a bodyless beat's floor is a
  no-op (it voiced nothing in the stitch — nothing to lose).
- Q3 (golden config): pin `candidates=2` (the production preview config); assert the sentence
  stream only; fixture MUST include key_claims + a ≥90s-deficit leg so a reflection actually
  appears (else the reflections seam is unguarded). Mock determinism verified sound
  (pool.map order-preserving; min() first-wins; `_local_penalty`=0 under mock).
- Q4: in the 3→5 window best-of-N ranks on `len(verify_faithfulness failures)` alone — stated
  in Scope 3 notes. "Correction/floor need" ranking = PREDICTED need (flagged count), never
  actually running the corrector per candidate.
- Q1 (corrected-sentence re-entry): a correction re-enters entailment + forbidden/traceability
  for that sentence; failing ANY counts toward the ≤2 ceiling.

## 5. NORTH-STAR CHECK

Sound. Bake-once audio consistent; Gravity×60s formula divergence is pre-existing and not
widened; empty-placeholder/city-scoping/MERGE rules untouched (Scope 5 persistence is CREATE'd
UUID ItineraryItems under a Trip — id-scoped, not geospatial); availability ladder aligns with
the variable-length differentiator. The ≤60% silence budget gets BETTER visibility via R-1's
floored-audio telemetry.

## 6. SCOPE REVIEW

Ordering re-cut: **`0 ∥ 1 → 2 → 3 → 5 → 4 → 6`** (R-5/C1). The 2→3 deploy hold stands (verified:
Scope 2 alone provably worsens live behavior). Scope 3 keeps AC-6 but the reflections removal
is its own commit inside the scope. Scope 0 pins both entry points with the Q3 fixture
constraints in its acceptance line. Scope 1 gains the FP battery + two probe cases and its
GO/NO-GO now has TWO criteria (FN usability AND FP ceiling). All scopes' verification commands
corrected to real Makefile targets. AC map unchanged (11/11 once) with AC-2 gaining frankenfact
+ attribution-strip fixture classes and AC-3 gaining the seated-beat + under-cited-fusion
fixtures.

## 7. BEST-PRACTICES AUDIT

`SECURITY_PRIVACY_PRACTICES.md` (16 sections): 8 Pass / 8 N/A — full table in the panel report;
substantive items: §5 Secrets — Scope 1 transcript must not echo env/keys (adopted, R-12);
§7 Logging — statuses/counts logged, not payloads (adopted, BL-11); §16 Compliance — new
persisted fields require the data-inventory note (adopted into Scope 5). Noted OUT of scope:
the trips router carries no server-side auth dependency (pre-existing) — logged as its own
follow-up ticket, not this spec's.
Library domains: Security = the danger-half treatment (fixtures + panel + Tier-3 gate) is the
threat model — sound. Privacy = no PII anywhere — clean. Performance = BL-12 adopted.
Accessibility = badge is text, not color-only (adopted).

## Attacks that FAILED (recorded so the refutations mean something)

Declared A+B fusion → floor-all survives; cross-POI vignette bleed blocked consistently in
union/repair/spec; stitch-fallback introduces no new cross-stop repetition; termination is
genuinely deterministic (≤2 attempts + LLM-free floor). The floor concept itself was never
broken — every successful attack went through DISHONEST CITATIONS or the VERBATIM SHORTCUT,
which is exactly where the amendments land.

---

## AMENDMENTS APPLIED ON APPROVAL

**02-spec.md:** floor = post-dedup stitch sentences (BL-3); glue + vignette floors (BL-1/2);
fact-preserving correction contract + seated-beat invariant (BL-4/5); sentence-unit-run
verbatim shortcut (BL-6); deterministic pre-gate + FP battery + safe best-of-N ranking (BL-7);
floor-collateral subset rule (BL-8); per-tour correction budget + concurrency (BL-12);
partial-failure ⇒ floor, stitch only on compose-call failure, fallback stops out of threshold
math (BL-13); AC-2 gains frankenfact/attribution-strip; AC-10 rescoped to persistence + API
flag + minimal filter/badge; AC-11 stub mix.
**03-scopes.md:** order `0∥1 → 2 → 3 → 5 → 4 → 6`; real Makefile targets (BL-9); Scope 0 pins
both paths + fixture constraints; Scope 1 gains FP battery/GO criteria; Scope 2 gains
`_beat_support_signature`+metrics re-base + `entails(support=…)` rename; Scope 3 gains the new
fixtures, audio recompute, reflections-removal checklist/commit; Scope 4 owns the two dying
tests + partial-outage fixture + comment update; Scope 5 gains the 4-layer persistence list,
`_compose_status` deletion, data-inventory note; Scope 6 gains the fusion-survives machine
assertion + scoreboard-calibration.
