# Tour engine convergence — run context

**Tier 2**, set mechanically from the path-glob table. Paths actually touched:
`src/tour/`, `src/api/routes/`, `frontend/` (Tier 2 row); `scripts/`, `tests/` (Tier 1 row);
`Docs/`, `specs/` (Tier 0 row). **No step touches `Makefile`, `.claude/`, deploy/infra,
DB/data or `.github/`**, so the Tier 3 row does not match. Skeptic panel P=2, acceptance runs.

An earlier draft of this ledger said Tier 3, reasoning by feel that "deleting code and
changing what `make test` enforces" felt like infra. That is exactly the judgement the
protocol forbids — the table is about paths touched, and it roughly doubled the price.
Corrected before pricing.

**approved_by_human:** false (read verbatim from state.json — NOT inferred, NOT set here)

**Baseline:** `make lint` → *All checks passed!* (2026-07-26). HEAD `930b1e2`, dirty tree
(31 modified files + 4 untracked specs dirs). RE-CONFIRMED clean during this preflight
(2026-07-26). `make _test-golden` is RED at clean HEAD for an unrelated fixture-provenance
defect — see `decisions.D2`. Every phase gate cites `_test-python`, never `_test-golden`.

---

## The problem, stated once

`src/tour` has 45 modules / 26,053 lines and **44 of them are imported from outside the
package**. There is no API surface, so adding a new path has always been cheaper than
changing an existing one. That is why there are two authoring implementations today:

- `compose.compose_script` — whole-tour, verify+repair loop. Reached by the phone via
  `POST /trips/{id}/compose`.
- `premium_tour` — per-stop units, zero retry, receipts preserved. Reached by the
  workbench via `POST /trips/preview`.

Route *planning* is already shared (`selection.select_k_routes` serves both). Only
authoring is forked.

**This is the second convergence attempt.** Commit `8d8fa9f` (2026-07-19) —
*"ONE algorithm in the workbench"* — removed every narration toggle from `/trips/preview`.
It did not hold, because nothing mechanical held it. That same commit shipped
`test_trips_route_holds_no_unpatchable_corrector_binding`, an accepted **structural guard
test** against a bad import pattern returning. The firewall here generalises that proven,
in-repo pattern from one class name to the whole package boundary.

---

## Corrections to the original brief — all verified 2026-07-26

The brief this ledger was written from contained five errors. Each was checked against the
code before the ledger was written; a builder acting on the unamended brief would have
broken the tree.

| # | Claim in brief | Reality |
|---|---|---|
| 1 | `scripts/tour_text_candidate.py` is dead, delete it | **FALSE.** `scripts/tour_batch_candidate.py:18` and `scripts/tour_batch_review.py:17` import from it; those back four *paid* Make targets. Only `tour_text_candidate_review.py` is dead. Guarded by a permanent must-exist assertion in step 5. |
| 2 | Deleting `author.py` / `tour_consistency.py` affects only their own tests | **FALSE.** `tests/conftest.py:181` and `:235` import both at module level inside the money guard. Deleting either alone turns the **entire suite** RED at collection. Steps 2 and 3 are therefore irreducibly multi-file, `maxAttempts: 3`. |
| 3 | "Delete the old whole-tour composer path" can mean deleting `compose.py` | **FALSE.** `premium_tour.py:48-61` imports twelve names from it, including privates. Only `compose_script` is separable — and see `decisions.D4`. |
| 4 | Register the geometry gate in `quality_rubric` | **Would break an accepted ruling.** `tests/test_spatial_check.py:651 test_deliberately_not_wired_into_quality_rubric` asserts `check_script_spatial_claims(` does not appear in `quality_rubric`'s source. Registering in the **engine** honours it; see `decisions.D3`. |
| 5 | Feed the checker from the corpus snapshot via the existing seam | **Shape-incompatible.** `spatial_check` expects poi-raw dicts (`name_variations`, `latitude`, `longitude`, `_pipeline.geocode_confidence`); `contract.POI` is a frozen model with `aliases`, `lat`, `lng` and **no confidence field**. An adapter is required and it silently drops the LOW-confidence filter — step 21 must make that loss explicit and tested, not accidental. |

Two more constraints found and encoded:

- `Severity` has only `BLOCKER` and `WARN` (`quality_rubric.py:179-183`). `SHADOW` must be
  added **before** the geometry wiring or the finding lands in `warnings` and becomes
  editor-visible noise. That is step 6.
- `tests/test_tour_compose_live.py` is in `LIVE_TEST_FILES` (`Makefile:12-16`) and consumes
  `compose_script` twice. Under `decisions.D4` it survives unchanged.

---

## Scope

**IN** — the structural convergence and the two things that make it safe:
one engine facade; the firewall ratchet; the dead-code deletion; `Severity.SHADOW` plus the
geometry gate registered at shadow; typed fallback reasons, the fallback counter, and the
editor/tourist surfaces; the test inventory; the regenerated architecture diagram.

**OUT — explicitly:**

1. **Any change to route planning.** `select_k_routes` is already shared. Behaviour must be
   provably identical (AC-6, AC-7).
2. **The golden fixture repair** — separate ledger (`decisions.D2`).
3. **Promoting the geometry gate above SHADOW.** No WARN, no BLOCKER, no editor surface.
4. **Improving the geometry extractor's precision.** Shadow exists to *measure* it first.
5. **The phone's cutover to per-stop Premium authoring** (`decisions.D4`) — it needs async
   job delivery and is the next slice. This ledger makes that cutover a one-argument change
   instead of a second fork.
6. **Deleting `grade.py`, `audit.py`, `compose_metrics.py`, `quality_certification.py`,
   `quality_requests.py`** — they back `make _test-grade` and `make tour-batch-review-live`.
7. **Re-enabling the dark G4 redundancy judge.**
8. **Any `git push`.** Commit on main after a judge ruling; never auto-push.
9. **Moving the workbench off real Opus.** Non-negotiable.

---

## Slice boundary and the recommended cut

The ledger is one dependency chain but has a natural cut after **step 20**:

- **Steps 1–20 — "one engine, mechanically held."** Purely structural, `$0`, reversible,
  and **zero user-visible change** by design: `/trips/preview` and `/trips/{id}/compose`
  must return byte-identical payloads for identical inputs. Its value is that the phone
  cutover later becomes a one-argument change rather than a second fork.
- **Steps 21–29 — the visible half.** Geometry shadow slot, fallback ladder, warning light,
  inventory, diagram.

If cost or wall-clock forces a cut, stop after 20 and run 21–29 as a second ledger. Do not
stop *inside* 11–15: those all edit `src/api/routes/trips.py` and a partial migration leaves
the route importing both the engine and its internals.

## Parallelisation

- **Strictly serial:** steps 2→3 (both edit `tests/conftest.py`) and 11→15 (all edit
  `src/api/routes/trips.py` — one builder per file, never two).
- **Safe to fan out:** 4 ∥ 5; 16–20 after 14; **21–23 ∥ 24–27** — but 22 and 24 both edit
  `src/tour/engine.py`, so give them a worktree each or land 24–25 first.
- **Never concurrent:** any two `make test-file` runs. `Makefile:144-146` pulls
  `_ensure-test-db`, `_ensure-dev-data` and `valhalla-up`, so every "cheap" step starts the
  shared containers and **writes the shared 7687 dev graph**. Parallel authoring is safe;
  parallel verification is not. The engine serialises the gate.

## Top risks

1. **`tour_text_candidate.py` gets deleted anyway** — it sits on the original list and looks
   exactly like its dead siblings. Breaks four paid targets, and nothing in `_test-python`
   covers them, so it surfaces on the next paid run. → step 5 carries a permanent
   must-exist assertion.
2. **The facade quietly becomes a fork.** `plan_premium_tour` is 117 lines of hash-bearing
   identity construction; "tidying while moving" changes `route_sha256` /
   `authoring_policy_sha256` and silently invalidates every frozen batch receipt. → step 8
   is a **byte-identity** test, not a behaviour test.
3. **The firewall is written absolutist and never lands.** Even after a perfect `trips.py`
   migration, five unrelated modules still violate. → shrink-only ratchet (`decisions.D6`).
4. **A lone module deletion reddens the whole suite** at `conftest.py:181`/`:235`, an agent
   misreads it as unrelated and weakens the money guard to "fix" it. → steps 2 and 3 are
   explicitly multi-file with `maxAttempts: 3`.
5. **The geometry gate gets promoted.** SHADOW→WARN is a one-token edit and the comment at
   `quality_rubric.py:743` currently *invites* it ("re-wire as WARN"). → step 23 rewrites
   that comment in the same phase; step 22 asserts `passed` and `warnings` are untouched.

Runner-up: `_test-golden` is RED at HEAD, so any agent seeing a red gate is tempted to
re-baseline the fixtures. No step cites it.

## Money

Every step is `$0`. The single paid command is the engine's close gate, `make audit`, run
**exactly once**. `make workbench` (~$1, up to 8 Opus calls per preview) is **not** in this
ledger — the editor-surface steps use the established stub-the-fetch Playwright pattern.
A real-money acceptance preview is a separate, explicitly-approved run.

---

## Decisions (verbatim from state.json — locked, do not relitigate)

- **D1-anthropic-client:** `src/tour/anthropic_client.py` is a shared SDK helper, not tour
  logic (imported by `src/api/routes/feedback.py` and `src/onboard/beat_draft.py`). It stays
  inside the firewall's FROZEN_EXCEPTIONS ratchet for now rather than being moved to
  `src/llm/` — moving it is a rename touching 11 importers and would inflate this change.
  Revisit when the exception set is drained.
- **D2-goldens:** The RED golden fixtures are a separate ledger. They are the only artifact
  that could prove selection behaviour did not change, so repairing them inside this change
  would launder the signal. Slice A instead proves no-behaviour-change via byte-identity
  (AC-6) and an unchanged-response test (AC-7).
- **D3-shadow-location:** `spatial_check` registers as a SHADOW gate in the ENGINE facade,
  NOT inside `quality_rubric.score_tour`. This keeps
  `tests/test_spatial_check.py::test_deliberately_not_wired_into_quality_rubric` GREEN and
  unmodified, honouring the 2026-07-19 measured ruling instead of overruling it.
- **D4-compose-script:** `compose_script` is NOT deleted in this ledger. Deleting it forces
  the phone onto per-stop Premium authoring, which multiplies phone cost ~8x and turns a
  single call into minutes — that cutover needs async job delivery and is its own slice.
  Here it is demoted to a named authoring mode reachable ONLY through the engine facade,
  pinned by test to exactly one call site. The firewall makes a second door impossible; the
  knob is removed when the phone cuts over.
- **D5-tour-text-candidate:** `scripts/tour_text_candidate.py` is NOT dead and is NOT
  deleted. Verified 2026-07-26: `scripts/tour_batch_candidate.py:18` and
  `scripts/tour_batch_review.py:17` both import from it, and those back four paid Make
  targets. Only `scripts/tour_text_candidate_review.py` is dead. A permanent must-exist
  assertion guards this.
- **D6-firewall-ratchet:** The firewall ships as a RATCHET, not an absolutist rule: a
  FROZEN_EXCEPTIONS literal naming today's remaining violators plus an assertion that the
  set never grows. An absolutist firewall cannot land without dragging in five unrelated
  modules; a ratchet lands immediately and makes regression impossible, which is the actual
  goal.

## Acceptance criteria (verbatim from state.json — all 27)

- **AC-1:** Given an AST walk of src/ outside src/tour, when the firewall runs, then the only permitted src.tour.* imports are engine and contract plus a pinned FROZEN_EXCEPTIONS literal; the failure message names file, line and module.
- **AC-2** (negative): Given a new deep tour import added to any src/ or scripts/ file, when the firewall runs, then it goes RED naming that exact file and line.
- **AC-3** (negative): Given the FROZEN_EXCEPTIONS set, when a file is added to it, then a companion assertion fails because the set may only shrink.
- **AC-4:** Given tests/, when the firewall runs, then it is exempt by construction: the walker's root set is asserted to be exactly {src, scripts}.
- **AC-5:** Given an AST scan of src/ for narration-producing provider constructions, when the firewall runs, then exactly one module qualifies and equals a pinned literal; judge/verifier clients are excluded by an explicit pinned list, never by accident.
- **AC-6:** Given the facade and the raw premium chain driven with OfflinePremiumExecutor on identical input, when both run, then the resulting blueprint hashes are byte-identical — proving the facade is a facade and not a re-implementation.
- **AC-7:** Given a fixed preview request and the offline executor, when /trips/preview is called before and after the migration, then responses are byte-identical after removing only a pinned list of non-deterministic fields.
- **AC-8** (negative): Given build_tour(phase=PLAN) with an executor whose execute() raises, then it returns route options and the executor is never invoked (zero calls on a counting stub).
- **AC-9** (negative): Given build_tour(n_options=k) for k in {1,3}, then exactly k deterministically-ordered options are returned; k=0 raises ValueError; k above the feasible count returns all feasible without raising.
- **AC-10:** Given engine.ENGINE_GATES, then it equals a pinned literal in order AND the gates actually execute from it: reordering two entries changes the observed order of emitted findings.
- **AC-11** (negative): Given engine.__all__, then it equals a pinned approved list; appending a name turns the firewall RED.
- **AC-12** (negative): Given src/tour/engine.py and its exclusive call tree, then it contains no Neo4j write verb and no call into src/api/crud/ — persistence stays the caller's job.
- **AC-13:** Given /trips/{id}/compose, then it still returns TripComposeResponse with fresh stop ids, still 409s on already_composed, and still 422s with reason == compose_verification_failed — the exact shape mobile/lib/services/trip_service.dart:225 branches on.
- **AC-14** (negative): Given the tree after deletion, then src/tour/author.py, tour_consistency.py, content_budget.py and the eight dead scripts are absent and unimportable, while scripts/tour_text_candidate.py, grade.py, audit.py, compose_metrics.py, quality_certification.py and quality_requests.py all still exist and import cleanly.
- **AC-15:** Given the deletions, when make _test-python is collected, then there are zero collection errors — the tests/conftest.py money-guard arms at :181 and :235 were removed in the same step as their modules.
- **AC-16** (negative): Given compose_script after the migration, then exactly one call site reaches it and that call site is inside src/tour/engine.py; a second caller anywhere turns the firewall RED.
- **AC-17:** Given Severity, then a SHADOW member exists and a SHADOW finding lands in neither RubricReport.passed nor .warnings — the partition is unchanged for BLOCKER and WARN.
- **AC-18** (negative): Given a tour containing a guaranteed-IMPLAUSIBLE look-cue, when the engine runs, then rubric.passed is True and rubric.warnings is empty while the shadow channel is non-empty, and the response JSON contains zero keys or values matching S1- or spatial.
- **AC-19** (negative): Given the engine's spatial path with spatial_check._load_city_pois_cached monkeypatched to raise, then coordinates still resolve from the CorpusSnapshot — proving the .dockerignore'd data file is never consulted in production.
- **AC-20:** Given tests/test_spatial_check.py::test_deliberately_not_wired_into_quality_rubric, then it is still GREEN and its source is unmodified — the 2026-07-19 ruling was honoured, not overruled.
- **AC-21:** Given three structurally different induced authoring failures, then each yields a distinct typed CandidateRejection code — today two of them collapse into GENERATION_FAILED.
- **AC-22** (negative): Given N previews of which F fell back, then a fallback counter and rate are observable; zero previews reports samples:0 rather than a divide-by-zero or a fabricated rate, and crossing the threshold emits exactly one ERROR per crossing, not per request.
- **AC-23:** Given a preview response with candidate_eligible:false and a populated candidate_rejection, when review.html renders, then the human-readable reason is visible and Basic stops are NOT rendered until an explicit control is clicked.
- **AC-24** (negative): Given the Basic lane rendered anywhere, then the strings Basic, not Premium and not graded are present and Claude / full AI voice / Quality rubric are absent — the existing honesty assertions stay green and unmodified.
- **AC-25:** Given the tourist lane, when the chosen route's authoring fails, then another route option is attempted before Basic is offered, and the ladder never retries the same route twice.
- **AC-26:** Given the test inventory document, then every path in its DELETE column is absent from git ls-files and every path in KEEP/ENHANCE is present, and every ADD entry names a node id that exists and passes.
- **AC-27:** Given the architecture diagram, then every name in the live engine.ENGINE_GATES appears in the diagram text — a diagram that disagrees with the code fails.

**Coverage:** all 27 acceptance criteria are cited by at least one step's `criterion_ids`.
`criteria_uncovered: []`.

## Infra preflight (read-only, cheap probes — this run, 2026-07-26)

- `docker ps`: `ondoway-valhalla` (8002), `ondoway-neo4j-workbench` (7689),
  `ondoway-neo4j-test` (7688), `ondoway-neo4j` (7687 dev) — all up.
- HTTP probes (routes, not just container-up): valhalla `/status` → 200, neo4j-test :7475 →
  200, neo4j-dev :7474 → 200.
- `make lint` → All checks passed!, clean.
- `node .claude/team-engine.test.js` → exit 0, "all 91 checks passed across 17 pathological
  shapes." Guard green — the termination caps, paid-bar one-shot and pre-fan-out gate order
  are verified for this run.

## Pinned gate commands (derived from files[], per step)

Every step's `files[]` is confined to `src/`, `scripts/`, `tests/`, or (steps 26-27 only)
`frontend/`. No step touches `mobile/`, so `make flutter-analyze` is never required in this
ledger.

- **Steps 1-25, 28-29** (files entirely in src/ | scripts/ | tests/):
  `gate_commands: ["make lint"]`.
- **Step 26** (files: `frontend/review.html`, `tests/test_workbench_review_regressions.py`):
  `gate_commands: ["make lint", "make test-file FILE=\"tests/test_workbench_review_regressions.py::test_basic_lane_names_the_rejection_and_requires_opt_in\""]`
  — `make lint` covers the touched tests/ file; the frontend/ file is probed by the step's
  own targeted node id (a workbench-review test), satisfying the frontend/ gate rule without
  inventing a second, unrelated workbench test.
- **Step 27** (files: `frontend/tour-preview.html`, `tests/test_preview_page.py`):
  `gate_commands: ["make lint", "make test-file FILE=\"tests/test_preview_page.py::test_tourist_lane_offers_another_route_before_basic\""]`
  — same reasoning as step 26.

Never put `make test`, `make audit`, `make test-live`, or `make test-workbench`
(minutes-long, shared containers) in any per-step gate.

## Command validity

All 29 steps' `test_command` values match the required pattern
`make test-file FILE="<path>::<node id>"` exactly — no bare `-k`, no `LIVE=1`, and
`test-file` is a live target in the Makefile (`Makefile:139-149`). All `command_valid: true`,
no `command_problem` on any step.
