# 03 — Scopes: Beat-level "correct-don't-reject" compose + verified narrative pass

**Date:** 2026-07-14 (amended post-red-team same day; **re-cut 2026-07-15 per
`04b-red-team-reopen.md` v2.1, approved**) · **Stage:** 3 (Scopes)
**Builds on:** `01-scope.md`, `02-spec.md` (as amended per 04 + 04b). 12 ACs, each mapped
to exactly one scope. Implementation is handed to **`/team`** per scope (see `05-plan.md`
— Scopes 2/3 prompts need Stage-5 amendment; Scope 3b is new); one fresh conversation per
scope.

Risk-weighted verification — where the heavy artillery goes:
(a) **fabrication laundering through the loosened gate / the pass** → Scope 2's FULL-GATE
FN/FP calibration GO gate (fluent frankenfacts, glue-mislabel, question smuggles,
held-out stop) + Scope 3's fixture battery + skeptic panel,
(b) **fact loss** → Scope 3's under-cited/seated-beat fixtures + Scope 3b's two-sided
diff fixtures (`01f`),
(c) **the pass silently becoming a no-op** (fallback the norm) → Scope 3b's live
fallback-rate GO bar,
(d) **removing whole-stop revert changes every composed tour** → Scope 0's goldens (the
identity `MockNarrativePass` keeps them binding).

---

### Scope 0: Golden Pin (characterization gate) — **COMMITTED (23f52e0)**

As executed: both entry points pinned byte-equal under deterministic mocks
(`tests/test_compose_golden.py`, goldens committed first, frozen oracle). AC-7. The
identity `MockNarrativePass` keeps these goldens binding through every later scope with
zero re-pinning.

---

### Scope 1: Le Meurice Live Probe — **COMPLETE; human NO-GO recorded (9fb2308)**

As executed: verdict NO-GO on FN usability (`01b`), FP ceiling 19/20 with the single
acceptance judge-cleared. Output evidence (`01b`–`01e`) drove the Stage-4 re-open; the
human's rewrite became the acceptance golden (goldenized as `01f`).

---

### Scope 2: Gate Calibration + script_body-Only Faithfulness (verify layer) — the GO gate

**What:** `verify_faithfulness` support becomes `script_body` alone: delete the
key_claims skip (`verify.py:279`) and key_claims from `_entailment_support`; rename
`entails(key_claims=…)` → `entails(support=…)`; re-base `_beat_support_signature` AND
`compose_metrics` body-only in the SAME commit; verbatim shortcut hardened to
sentence-unit alignment; vignette beats enter the verify support map. PLUS the 04b gate
calibration: `_ENTAILMENT_PROMPT` rewritten fusion-aware (one continuous SOURCE TEXT;
combining stated facts = YES **only when the joining relation is itself stated**; flat
assertion of a hedged/disputed claim = NO; a question = YES only if the source supports
its presupposition), and the **measured calibration GO gate run through the FULL
production gate** (pre-gate + shortcut + entailment + correction routing — 01d ran
entailment only, a weaker gate):
- FN battery: the `01f` goldenized sentences + 01b s2/s10 fusions + 01d s8 + the gold
  question, per-class pass definitions (entailment-YES vs ships-after-trim vs
  promoted-glue). Control for word-form dates in the analysis (04b BL-V7).
- FP battery: entity_swap, POPULATED date_shift, FLUENT frankenfacts, hedge-strip/
  dispute-flatten, question-presupposition smuggles, glue-mislabel.
- Held-out material from ≥1 non-Le-Meurice stop (NYC corpus, local Neo4j).

**GO/NO-GO (recorded in the spec folder):** all three known FNs recovered; the `01f`
text ships whole; ZERO fabricating acceptances. A NO-GO stops the line again at Stage 4.

**Acceptance criteria:** AC-4.

**Depends on:** Scopes 0+1 (done). Live spend: bounded battery runs (Haiku + a few Opus
corrections; cents).

**Verification — test:** `make test-file FILE=tests/test_tour_verify.py` — key_claims=()
beat checked (red under HEAD); negation-truncation AND attribution-strip fail the
shortcut; unchanged corpus sentence passes LLM-free; vignette sentence checked. Battery
scorecards printed by a Makefile harness target; goldens green.

**Verification — demo (human):** you READ the calibration scorecards — the FN battery
per-class table and the FP battery's zero-acceptance table.

**Estimated sessions:** 1–2

---

### Scope 3: The Corrector + Floor (the correct-loop core)

**What:** Replace the repair ladders in `compose_script_per_chapter` per `02-spec.md`
(loop shape: assemble → verify WHOLE tour → correct per flagged sentence concurrently →
re-verify): deterministic pre-gate; fact-preserving correction (under-cited → floor;
≤2 attempts; per-tour budget `2 × stop_count`); floor = post-dedup stitch sentences,
composer position, collateral subset rule; seated-beat invariant; union-rescue minimal
subset; retire coverage machinery; recompute `_sum_audio` last; best-of-N ranking
(pre-gate violations first). PLUS the 04b correct-loop amendments: **trim as attempt 1**
with the mechanical acceptance check (no added tokens; removed content tokens ⊆ flagged
set); **affirm telemetry** (`affirm_reject`; no escalation ship-path); **glue
correction-before-drop** + `glue_dropped` counter; **`_populate_also_cites` token
justification restricted to the pre-gate salient class** (fixture: the "second"
false-citation case from 04b BL-V2 must NOT gain a citation). Reflections removal as its
own commit inside the scope (unchanged checklist).
**Skeptic panel (2–4, mixed models) before this scope's commit — the danger half.**

**Acceptance criteria:** AC-2, AC-3, AC-5, AC-6, AC-8.

**Depends on:** Scope 2 (GO).

**Verification — test:** `make test-file FILE=tests/test_tour_recompose.py` + goldens —
AC-3's four fixtures; AC-2's full battery (incl. fluent-frankenfact, populated
date_shift, question-smuggle, glue-mislabel, dispute-flatten classes); AC-5
fusion-floors-both; AC-6 no reflections/coverage; AC-8 ceilings; trim-acceptance
fixtures (a hedge-dropping "trim" must be rejected as a trim); audio recompute.
`make test` full offline bar.

**Verification — demo (human):** workbench preview on a mock-composed fixture: the stop
shows corrected/floored prose in place — no shotgun revert.

**Estimated sessions:** 2–3

---

### Scope 3b: The Verified Narrative Pass (NEW — the 04b core)

**What:** The per-stop pass per `02-spec.md` P1: `NarrativePassClient`
(Opus/identity-mock); prompt to the `01f` bar (input = verified sentences WITH citations
+ bodies as phrasing-only); output re-enters the FULL gate + quote-fidelity rule + glue
promotion + two-sided fact diff with restore retry; fully-defined sink ladder
(correction-exhausted | affirm | seated-beat | fact-diff | budget | pass-call-error ⇒
whole-stop `narrative_fallback`, no mixing, no floor inside pass output); own budget
lines (≤2 pass calls + `2 × stop_count` pass corrections); both entry points; the `01f`
diff fixtures (must-pass pair + must-catch mutations) and quote fixture committed as
tests; cross-stop overlap telemetry.

**Live GO gate (bounded spend, recorded in the spec folder):** the multi-stop probe
measures the stop-level fallback rate (ceiling ~≥90% survival, set on reading) and the
per-tour fabrication bound (zero fabricating acceptances) on real pass output. A NO-GO
stops the line at Stage 4 — the pass must not ship as a de-facto no-op.

**Acceptance criteria:** AC-12.

**Depends on:** Scopes 2 + 3.

**Verification — test:** `make test-file FILE=tests/test_narrative_pass.py` — AC-12
(a)–(e): identity-mock golden equality; diff fixtures both ways; quote mutation fails;
glue promotion fixture; every fallback reason reachable + ships intact pre-pass text +
no hang. `make test` full offline bar.

**Verification — demo (human):** you READ the probe transcript's before/after for one
stop (pre-pass verified text vs pass output) + the fallback-rate scorecard.

**Estimated sessions:** 2

---

### Scope 4: Quality Telemetry + Threshold Flag

**What:** As previously amended (4-layer persistence: gate → `route_script_to_stops` →
`_create_itinerary_items` Cypher + Trip status → response models; additive, no
migration; preview = response-only + one structured log line; `_compose_status` heuristic
DELETED; `flagged` filter + text badge; floored-audio seconds). PLUS 04b: statuses
derive from gate counts AND pass outcome
(`composed | composed_corrected | composed_floored | narrative_fallback |
stitched_fallback | stitched`); **`narrative_fallback` forces the tour's `flagged`
status unconditionally** (bypasses threshold math); persist the `glue_dropped` /
`affirm_reject` / `pass_facts_restored` / `pass_fallback_reason` counters.
Data-inventory note per SECURITY_PRIVACY_PRACTICES §16.

**Acceptance criteria:** AC-10.

**Depends on:** Scope 3b.

**Verification — test:** `make test-local` — fixture tours either side of the threshold
→ flagged vs clean; a within-threshold tour containing ONE `narrative_fallback` stop is
still flagged; persistence round-trip incl. the new counters.

**Verification — demo (human):** curl the flagged-filter endpoint + see the badge on
tour-preview.html for a flagged vs clean preview.

**Estimated sessions:** 1

---

### Scope 5: Entry-Point Convergence + Never-Fail Availability

**What:** As previously amended: the persisted `/compose` path converges on the gate
(now gate + pass); the 422 refusal path is deleted; failure routing per spec
(correction-call failure ⇒ floor; **pass-call failure ⇒ `narrative_fallback`**; a stop's
compose-call failure ⇒ `stitched_fallback`, excluded from threshold math); owns
rewriting `test_refused_flavour_is_422_and_leaves_trip_untouched` (assertions invert)
and `test_tour_compose.py:290`; comment update compose.py:677-682; dead-machinery sweep
(`serve_or_block`, `compose_and_verify(repair=)`, `ComposeVerificationError`).

**Acceptance criteria:** AC-11.

**Depends on:** Scopes 3b + 4.

**Verification — test:** `make test-local` — (a) always-raising compose client ⇒
complete stitched tour, no 4xx/5xx, both endpoints; (b) partial outage ⇒ mixed script,
fallback stops excluded from thresholds; (c) correction-call failure ⇒ floor; (d)
pass-call failure ⇒ `narrative_fallback`, 200; (e) always-REJECTING checker ⇒ 200 with
corrected/floored/fallback statuses, never 422 (red under HEAD trips.py:521-523).

**Verification — demo (human):** workbench preview with `COMPOSE_PROVIDER` broken on
purpose → the tour still renders, honestly labeled.

**Estimated sessions:** 1

---

### Scope 6: Live Acceptance Run + Calibration (closes the ticket)

**What:** The full live Le Meurice run (ticket repro config) through the COMPLETE
pipeline (correct-loop + pass). Machine assertions FIRST: stop 2 ships `narrative` (not
fallback), NOT byte-identical to the stitch, AND a sentence citing `85ebe707`
(±`c3d4a78a`) ships verified|corrected — the fusion survives as a fusion. Then the human
gate (AC-9): acceptance agent + YOUR read judge one coherent narration of the `01f`
character. Thresholds calibrated from this run PLUS the mock/replay scoreboard;
constants provisional with a telemetry-review trigger. Ticket
`2026-07-13-compose-stop-revert-haiku-ceiling.md` closed with evidence.

**Acceptance criteria:** AC-1, AC-9.

**Depends on:** Scopes 3b, 4, 5.

**Verification — test:** harness/curl with the machine assertions; fabrication fixtures
still green.

**Verification — demo (human):** you read/listen to the actual Le Meurice stop and sign
off (Tier-3 gate). Per-stop counts recorded in `06-verify.md` as the quality baseline.

**Estimated sessions:** 1

---

## Ordering & notes

**`0 ∥ 1 (done) → 2 → 3 → 3b → 4 → 5 → 6`.** One commit per scope (Scope 3: two
commits — reflections removal separate). Live spend: Scope 2's battery runs, Scope 3b's
fallback-rate probe, Scope 6's closing run — all bounded and printed. TWO measured GO
gates now guard the line: Scope 2 (gate calibration) and Scope 3b (fallback rate); a
NO-GO on either stops the line at Stage 4. Active scopes = 6 (0 and 1 complete) — within
the 7-scope cap.

**Deploy hold (2→3 window):** unchanged — Scope 2 alone makes live compose WORSE (more
sentences under the checker while the OLD drop/revert ladder still runs). Do NOT deploy
to Render between Scope 2 and Scope 3 landing; treat 2+3 as one release unit. (3b/4/5
each ship deployable improvements.)

**AC map:** 0→AC-7 · 2→AC-4 · 3→AC-2,3,5,6,8 · 3b→AC-12 · 4→AC-10 · 5→AC-11 ·
6→AC-1,9 (all 12 mapped once).
