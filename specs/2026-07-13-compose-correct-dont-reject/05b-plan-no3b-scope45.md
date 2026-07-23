# 05b — Adapted plan: 3b DROPPED, Scopes 4+5 MERGED (no narrative pass)

**Date:** 2026-07-18 · **Human ruling (chat):** after reading the live Scope-3 output
(Tuileries, four Île de la Cité stops, three Place des Vosges lens variants — all
fact-safe, all reading as one narrator), the human judged the composer + softened gate
already deliver most of what Scope 3b (the verified narrative pass) was designed to add.
3b was calibrated against the OLD disjointed "Version B"; that gap has largely closed via
(a) using the Opus composer properly and (b) the 2026-07-16 softening ruling. **Decision:
DROP Scope 3b.** The one residual 3b benefit (audio pacing — unpacking dense compound
sentences for the ear) is deferred; if ever needed it folds into `_COMPOSE_SYSTEM` as a
prompt rule, not a second LLM pass. The human declined the audio tiebreaker and is
satisfied with quality.

**Consequence:** Scopes 4 (telemetry) and 5 (convergence + availability) were written
assuming 3b's pass/fallback layer. With 3b gone they SIMPLIFY and merge into one build
("Scope 45"). The correct-loop output (Scope 3) IS the final composed Script — there is
no pass above it.

## What DROPS from the approved 4/5 plan (no pass layer exists)

- Status enum loses `narrative_fallback`. Final enum:
  `composed | composed_corrected | composed_floored | stitched_fallback | stitched`.
- Counters `pass_facts_restored` / `pass_fallback_reason` are NOT persisted (no pass).
  KEEP `glue_dropped` / `affirm_reject` (the correct-loop emits these).
- The "narrative_fallback FORCES flagged unconditionally" rule → re-anchored: a
  **`stitched_fallback` stop (compose-call outage) FORCES the tour `flagged`
  unconditionally** and is EXCLUDED from threshold math (it is honest degradation, must
  be surfaced). Floored-heavy stops flag via the threshold.
- Scope-5 task 1 "converge onto per-chapter corrector gate **+ pass**" → just the
  corrector gate. No pass call site, so no pass-failure ladder rung.

## JUDGE PROVE-FIRST (2026-07-18) — two deterministic safety guards 3b would have carried

The judge caught that dropping 3b silently drops TWO deterministic anti-fabrication guards
04b §4 assigned to the VERIFY layer (not the LLM pass): **glue-promotion (BL-V3)** and
**quote-fidelity (BL-V4)**. Both are absent in production today (`verify.py:333` skips all
glue; no quote check anywhere) and one is exploitable in the SHIPPED correct-loop path
independent of any pass. The human ruled on FLOW (three live reads = "one narrator"), NOT
on dropping these SAFETY checks — and dispute-flattening remains a violation even under the
2026-07-16 softened bar (`02-spec.md`). These are cheap, deterministic, LLM-pass-independent,
so carrying them forward does NOT resurrect 3b. They are **Step A0, done FIRST in verify**:

- **A0a Quote-fidelity (deterministic):** for every beat-cited sentence, any text inside
  quotation marks (handle “ ” and ASCII " ") must appear verbatim (whitespace-normalized)
  in a cited beat's body; else it is a faithfulness failure. Pure string check, zero LLM —
  new `verify_gate` primitive, called in `verify_faithfulness`. Catches a corrector (or
  composer) subtly altering a quoted passage that paraphrase-tolerant entailment misses.
- **A0b Glue-promotion (the checked lane, BL-V3):** a glue-labeled sentence containing ANY
  pre-gate salient token (`verify_gate.salient_tokens` — year/number/proper-noun) is
  PROMOTED to the checked lane: entailment-checked against the stop union (dispute/question
  rules apply), then routed through the existing Scope-3 glue ladder (correct → floor to
  stitched glue → drop). Token-free glue keeps validation's existing scan — no
  entailment-free lane. Update `test_glue_and_unknown_cited_sentences_skip_entailment`
  (`test_tour_verify.py:146`): token-free glue still skips; token-BEARING glue is checked.
- **Tests (RED-first):** the BL-V3 smuggle (a dispute-flattening assertion labeled glue,
  built from corpus proper nouns so validation's token scan passes it → must be caught by
  promotion) and the BL-V4 quote alteration (one word changed inside a quoted span → must
  fail quote-fidelity). Both RED under HEAD, green after.

This is the ONLY verify-layer change in Scope 45 (the corrector/entailment internals stay).
It runs BEFORE the endpoint wiring so the safety layer is intact when production starts
correcting live.

## Scope 45 — the merged build (Tier 3: live API + Neo4j persistence + ends deploy hold)

Surface: `src/tour/compose.py`, `src/tour/compose_gate.py`, `src/api/dependencies.py`,
`src/api/routes/trips.py`, `src/api/crud/trips.py`, `src/api/models/trips.py`,
`frontend/tour-preview.html`, `tests/`, docs §16.

### Step 0 — unblock the bar (pre-existing crash in this scope's own test file)
`tests/test_trip_api.py` currently fails (3F + ~14E) with `GeneratedStop.beat_id=None`
at `trips.py:346` — a beat-LESS POI reaches stop assembly on the live dev corpus. This
pre-exists on clean HEAD (verified at 8a4a346 and 62d2544) and blocks honest
verification of the very endpoints this scope rewrites. Diagnose the real layer (should
the engine ever seat a beat-less POI? — likely selection should exclude it, OR
`GeneratedStop.beat_id` legitimately becomes `str | None` for anchor-bearing endpoint
POIs) and fix with a regression test. This is task 0 so the scope's `make test-local`
bar is real.

### A. The corrector wiring (the core — makes production CORRECT, not floor)
1. **New DI** `get_correction_client()` in `dependencies.py` — `COMPOSE_PROVIDER`
   selects `AnthropicCorrectionClient` ('anthropic') vs `None`→floor-only path (mock;
   `make test` stays offline). Mirror `get_compose_client`.
2. Inject `correction_client=Depends(get_correction_client)` into `compose_trip`
   (`/compose`) and `preview_trip` and pass it into the compose calls. This is the line
   that flips live tours from flooring to correcting.

### B. Converge the whole-tour path
3. `compose_script` (whole-tour) becomes a thin wrapper over the per-chapter correct-loop
   engine (`compose_script_per_chapter`), preserving its signature; delete the old
   drop/revert + `repair=` path. Both entry points now run ONE engine (judge reviews the
   seam). `compose_script_per_chapter` gains `correction_client` passthrough (already
   accepts it).

### C. Never-fail availability (delete the 422)
4. Delete the `422 / ComposeVerificationError` path in both endpoints (`trips.py:521-532`
   + the import). Sweep dead machinery to zero-lint: `serve_or_block`,
   `compose_and_verify(repair=)`, `ComposeVerificationError`, `drop_failing_sentences`,
   `repair_composed`. Failure routing: a stop's **compose-call** failure (anthropic
   APIError / ValueError-truncation / JSONDecodeError) → that stop ships **stitched** as
   `stitched_fallback`, excluded from threshold, forces tour `flagged`; a **correction-call**
   failure already degrades to the floor inside the correct-loop (Scope 3). Loud
   structured log per fallback (status + reason, no payloads). Update the
   `compose.py:677-682` propagate-by-design comment — reversed BY DESIGN here.

### D. Telemetry (persist + surface)
5. **Status derivation** from the correct-loop counts (no pass): per-stop
   `composed | composed_corrected | composed_floored | stitched_fallback | stitched`;
   tour rollup = worst stop; a `stitched_fallback` stop forces `flagged`.
6. **Delete `_compose_status`** (`trips.py:693-705`) — statuses come from the gate counts,
   not byte-equality.
7. **Persist (additive, coalesce for legacy)** — per stop: verified/corrected/floored +
   status + floored-audio seconds; per tour: rollup status, `flagged`, `glue_dropped`,
   `affirm_reject`. Threads through `route_script_to_stops` → `_create_itinerary_items` →
   `mark_trip_composed`/`create_trip_with_stops` → `list_trips_for_profile` (coalesce) →
   pydantic (`GeneratedStop`, `TripComposeResponse`, `TripPreviewStop/Response`;
   `attempts` repurposed as corrections-spent, update Field description). ItineraryItems
   are CREATE'd with UUIDs (no MERGE), DETACH-DELETE'd on re-compose — legacy reads null.
8. **Threshold flag** — provisional config constants (Scope 6 calibrates); `flagged`
   filter on the trips list endpoint; TEXT badge on `tour-preview.html` (a11y: text, not
   colour-only). One §16 data-inventory note (additive strings/counters, no new PII).

### NOT to touch
verify's ENTAILMENT/corrector internals (Scope 2/3) — EXCEPT the two Step-A0 deterministic
guards above (quote-fidelity + glue-promotion), which verify GAINS; the generation
stitcher; claim_dedup route-dedup; mobile (its 422/refusal handling becomes dead code — LOG
to follow-ups, do not delete); the goldens' fixtures.

### Line-ref hygiene (judge note)
Every `file:line` in this doc was inherited from 05-plan.md (written at 8a4a346, BEFORE
Scope 3 landed at 58deb53+aadcd05). The Developer MUST re-anchor each reference at the
real HEAD (df7051f) before editing — e.g. the "propagate-by-design" comment is no longer at
compose.py:677-682. Grep for the symbol, don't trust the number.

### Tests (RED-first where marked; `make test-local`, Neo4j 7688)
- Never-fail: TOTAL outage stub (mixed APIError/ValueError/JSONDecodeError) → BOTH
  endpoints 200 + complete stitched tour + honest fallback status, no 4xx/5xx (RED:
  `/compose` raises 422 today). PARTIAL outage → mixed script, `stitched_fallback`
  excluded from threshold. Always-REJECTING checker → `/compose` 200 (RED today).
- Corrector wiring: with a real-shaped correction stub injected via the endpoint, a
  flagged sentence CORRECTS (not floors) end-to-end through `/compose` + preview.
- Telemetry round-trip: mock-compose → counts+status on items, rollup+counters on trip →
  list endpoint returns them; legacy trip reads null-clean; re-compose round-trip stable;
  a within-threshold tour with ONE `stitched_fallback` stop is STILL flagged.
- `_compose_status` gone (grep/import assert). Status derivation table-tested.
- Stitch proven LLM-free (no client constructed).

### Deploy note (judge-corrected)
`render.yaml` has NO `autoDeploy: false`, so Render's default applies: **merging
`scope2-gate-calibration` → `main` IS a live prod deploy of ondoway-api.** There is no
separate deploy gate — the merge is the Tier-3 production deploy action. Treat it as such:
prod smoke first, human performs the merge deliberately. This scope makes the branch
deployable (correct-don't-reject engine live, never-fail); the Scope-2 deploy hold lifts
only when the human chooses to merge. Do NOT merge as part of this build — land Scope 45 on
the branch; the human merges/deploys separately.

**Rigor:** Tier 3 (live API + DB + availability). Developer (step 0 first) → QA undo-test
→ skeptic on the failure-routing matrix (every exception × call site → right ladder rung)
→ judge before commit → real functional demo the human can repeat (live tour showing
correction + telemetry + a forced-outage never-fail run).

## Panel + decisions (2026-07-18)
- **D1 RESOLVED (human, chat):** the persisted `/compose` path stays **candidates=1** (best-of-1).
  Rationale: best-of-N predates the correct-loop; the loop now deterministically corrects/floors
  any flagged sentence, so a 2nd sample adds Opus cost without meaningful fabrication benefit.
  Preview stays 2 (harmless extra on a throwaway). Not a safety difference.
- **B1 RESOLVED:** ported commit 9e9747a (sibling worktree canonical fix — same-id dedup collapse
  in select_poi_beats; Palais de Justice 0→3 beats) instead of a divergent floor; `beat_id`
  reverted to non-nullable. Judge STOP caught the reinvention + worktree collision.
- **R1 (two-write persistence non-transactional) / R2 (derive_tour_flagged dilutes with plain
  `stitched`):** recorded limits, follow-ups; R2 latent (unreachable via current endpoints).
