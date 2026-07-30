# Tour engine convergence — run context

**Tier 2**, set mechanically from the path-glob table. Paths actually touched:
`src/tour/`, `src/api/routes/`, `src/api/models/`, `src/api/dependencies.py`, `frontend/`
(Tier 2 row); `scripts/`, `tests/` (Tier 1 row); `Docs/`, `specs/` (Tier 0 row). **No step
touches `Makefile`, `.claude/`, deploy/infra, DB/data or `.github/`, and no step touches
`mobile/`**, so the Tier 3 row does not match and `make flutter-analyze` is never required
in this ledger. Skeptic panel P=2, acceptance runs.

**approved_by_human:** `true` (read verbatim from state.json — NOT inferred, NOT set here).
`approved_at`: `2026-07-29T18:37:17Z`. `approval_note` (verbatim): "Re-approved by the owner
in chat after the ledger was reshaped: steps 30/31/32 replaced by N1-N4, N5 added
(screen-vocabulary sweep, gated after 26/27), N3 narrowed to source identifiers, step 6
re-pinned to 3+4. The prior 2026-07-27T04:34:26Z stamp covered the 35-step shape and was NOT
carried forward."

**Baseline:** `make lint` → *All checks passed!* (2026-07-26). HEAD `930b1e2`, dirty tree
(31 modified files + 4 untracked specs dirs). RE-CONFIRMED clean during this preflight
(2026-07-29). `make _test-golden` is RED at clean HEAD for an unrelated fixture-provenance
defect — see `decisions.D2`. Every phase gate cites `_test-python`, never `_test-golden`.

---

## The problem, stated once

`src/tour` has 45 modules / 26,053 lines and 44 of them are imported from outside the
package. There is no API surface, so adding a new path has always been cheaper than
changing an existing one. That is why there are two authoring implementations today:

- `compose.compose_script` — whole-tour, verify+repair loop. Reached by the phone via
  `POST /trips/{id}/compose`.
- `premium_tour` — per-stop units, zero retry, receipts preserved. Reached by the
  workbench via `POST /trips/preview`.

Route *planning* is already shared (`selection.select_k_routes` serves both). Only
authoring is forked.

**This is the second convergence attempt.** Commit `8d8fa9f` (2026-07-19) — *"ONE algorithm
in the workbench"* — removed every narration toggle from `/trips/preview`. It did not hold,
because nothing mechanical held it. The firewall here generalises that proven, in-repo
guard-test pattern from one class name to the whole package boundary.

---

## Scope

**IN** — the structural convergence and the things that make it safe: one engine facade;
the firewall ratchet; the dead-code deletion; `Severity.SHADOW` plus the geometry gate
registered at shadow; typed fallback reasons, the fallback counter, the editor/tourist
surfaces; retry/partial-retention/cost-recording on the premium chain; the vocabulary
rename (fallback reasons, the two misleading names, `premium`, wire fields) *and* the
screen-vocabulary sweep (N5); the test inventory; the regenerated architecture diagram.

**OUT — explicitly:**

1. **Any change to route planning.** `select_k_routes` is already shared. Behaviour must
   be provably identical (AC-6, AC-7).
2. **The golden fixture repair** — separate ledger (`decisions.D2`).
3. **Promoting the geometry gate above SHADOW.** No WARN, no BLOCKER, no editor surface.
4. **Improving the geometry extractor's precision.** Shadow exists to *measure* it first.
5. **The phone's cutover to per-stop Premium authoring** (`decisions.D4`) — needs async job
   delivery and is the next slice.
6. **Deleting `grade.py`, `audit.py`, `compose_metrics.py`, `quality_certification.py`,
   `quality_requests.py`** — they back `make _test-grade` and `make tour-batch-review-live`.
7. **Re-enabling the dark G4 redundancy judge.**
8. **Any `git push`.** Commit on main after a judge ruling; never auto-push.
9. **Moving the workbench off real Opus.** Non-negotiable.

---

## Money

Every step is `$0`. The single paid command is the engine's close gate, `make audit`, run
**exactly once**. `make workbench` (~$1, up to 8 Opus calls per preview) is not in this
ledger — the editor-surface steps use the established stub-the-fetch Playwright pattern.
A real-money acceptance preview is a separate, explicitly-approved run.

---

## Decisions (verbatim from state.json — locked, do not relitigate)

- **D1-anthropic-client:** `src/tour/anthropic_client.py` is a shared SDK helper, not tour
  logic (imported by `src/api/routes/feedback.py` and `src/onboard/beat_draft.py`). It
  stays inside the firewall's FROZEN_EXCEPTIONS ratchet for now rather than being moved to
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
- **D7-vocabulary:** The code says what the traveller is told: a walk is `full` or `basic`,
  the same two words in the app, the API and the source. 'Premium' is retired outright (it
  implies a paid tier that does not exist); 'candidate' is retired ONLY in the authoring
  sense — it stays where it genuinely means one of several routes under consideration
  (PoiCandidate, best_candidate, anchor_candidates). The naming sweep runs BEFORE the
  engine is built (steps N1-N4) so the engine is authored in the new vocabulary and no name
  is introduced twice.

---

## Acceptance criteria (verbatim from state.json — all 33)

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
- **AC-24** (negative): Given the source-text walk rendered on either surface, then the reader is told plainly that the AI wrote none of it and that the facts came from the source authors; and no surface implies it was AI-written. The honesty assertion is retargeted from the old literal strings to the new ones — the PROPERTY it protects is unchanged, only the wording it pins moves.
- **AC-25** (negative): Given the tourist lane, when the chosen route's authoring fails, then another route option is attempted before Basic is offered, and the ladder never retries the same route twice.
- **AC-26:** Given the test inventory document, then every path in its DELETE column is absent from git ls-files and every path in KEEP/ENHANCE is present, and every ADD entry names a node id that exists and passes.
- **AC-27:** Given the architecture diagram, then every name in the live engine.ENGINE_GATES appears in the diagram text — a diagram that disagrees with the code fails.
- **AC-28** (negative): Given any message a human reads, in the workbench or the app, then it contains none of the banned internal vocabulary (build fingerprint, blueprint, traceability, candidate, certification, eligible, compose, provider, LLM, grounded, floored, degraded) — enforced by a test scanning the shipped frontend strings and the API's human-readable fields.
- **AC-29** (negative): Given the renamed reason codes and wire fields, then every old name is absent from src/ and frontend/, and the response still deserialises for the existing Flutter client — the rename ships with whatever compatibility shim the client needs, not a silent break.
- **AC-30** (negative): Given a walk that fails the quality standard, then no field or label anywhere states or implies that it passed; specifically the flag currently named candidate_eligible is renamed to say only what it means (every stop was fully written) and is never read as a quality verdict.
- **AC-31** (negative): Given an 8-stop build where one stop's call raises and the rest succeed, then the successful stops are RETAINED and returned rather than discarded — today tuple(pool.map(...)) re-raises the first exception and throws away siblings that were already executed and already billed.
- **AC-32** (negative): Given repeated transient failures, then the whole build makes at most 2 extra calls beyond one per stop (worst case 10 for an 8-stop walk); a deterministic content failure is never retried; and every attempt passes through the existing spend guard so the per-IP, hourly and daily ceilings still bind.
- **AC-33:** Given any completed build, then its real token usage and cost are persisted rather than discarded — the receipt hook already receives this data and currently drops it — and a failed build records what was spent before it failed.

**Coverage:** all 33 acceptance criteria are cited by at least one step's `criterion_ids`.
`criteria_uncovered: []`. (Verified by union over every step: 1-33 all present. AC-33 ←
step 35; AC-31 ← step 33; AC-32 ← step 34; AC-27 ← step 29; AC-28/29 ← N1/N2/N3/N4/N5;
AC-30 ← N4.)

---

## Infra preflight (read-only, cheap probes — this run, 2026-07-29)

- `docker ps`: `ondoway-valhalla` (8002), `ondoway-neo4j-workbench` (7689),
  `ondoway-neo4j-test` (7688), `ondoway-neo4j` (7687 dev) — all up and port-mapped as
  expected.
- `make lint` → *All checks passed!*, clean.
- `node .claude/team-engine.test.js` → exit 0, "all 91 checks passed across 17 pathological
  shapes." Guard green — the termination caps, paid-bar one-shot and pre-fan-out gate order
  are verified for this run. `infra.engine_guard: true`.

---

## Pinned gate commands (derived from files[], per step)

Rule: `make lint` covers only `src/`, `tests/`, `scripts/` (Makefile:103-106). A `mobile/`
step needs `make flutter-analyze` (none exist in this ledger — no step touches `mobile/`).
A `frontend/` step needs a targeted `make test-file` node id in addition to `make lint`.

- **Steps 1, 2, 3, 4, 5, N1, N2, N3, N4, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19,
  20, 21, 22, 23, 24, 25, 28, 33, 34, 35, 29** (files entirely in `src/` | `scripts/` |
  `tests/` | `Docs/` | `specs/`): `gate_commands: ["make lint"]`. (`Docs/` and `specs/` are
  not lint-scoped themselves, but every one of these steps also touches a `tests/` file,
  which is.)
- **Step 26** (files: `frontend/review.html`, `tests/test_workbench_review_regressions.py`):
  `gate_commands: ["make lint", "make test-file FILE=\"tests/test_workbench_review_regressions.py::test_basic_lane_names_the_rejection_and_requires_opt_in\""]`
  — `make lint` covers the touched `tests/` file; the frontend/ file is probed by the
  step's own targeted node id.
- **Step 27** (files: `frontend/tour-preview.html`, `tests/test_preview_page.py`):
  `gate_commands: ["make lint", "make test-file FILE=\"tests/test_preview_page.py::test_tourist_lane_offers_another_route_before_basic\""]`
  — same reasoning as step 26.
- **Step N5** (files: `frontend/review.html`, `frontend/tour-preview.html`,
  `src/api/models/trips.py`, `tests/test_tour_engine_boundary.py`):
  `gate_commands: ["make lint", "make test-file FILE=\"tests/test_tour_engine_boundary.py::test_no_banned_vocabulary_in_user_facing_strings\""]`
  — this step's own primary `test_command` IS the targeted node id that scans both touched
  frontend files' shipped strings, so it doubles as the frontend/ gate; no second, unrelated
  workbench test is invented.

Never put `make test`, `make audit`, `make test-live`, or `make test-workbench`
(minutes-long, shared containers) in any per-step gate.

## Command validity

All 35 steps' `test_command` values match the required pattern
`make test-file FILE="<path>::<node id>"` exactly — no bare `-k`, no `LIVE=1`, and
`test-file` is a live target in the Makefile (`Makefile:141`). All `command_valid: true`,
no `command_problem` on any step.

## Slice boundary and the recommended cut

The ledger is one dependency chain but has a natural cut after **step 20**:

- **Steps 1–20 (plus N1-N4, which now precede 6-10 in the dependency chain) — "one engine,
  mechanically held."** Purely structural, `$0`, reversible, and zero user-visible change
  by design: `/trips/preview` and `/trips/{id}/compose` must return byte-identical payloads
  for identical inputs.
- **Steps 21–29, 33-35, N5 — the visible half.** Geometry shadow slot, fallback ladder,
  retry/retention/cost-recording, warning light, inventory, diagram, screen-vocabulary
  sweep.

## Parallelisation

- **Strictly serial:** steps 2→3 (both edit `tests/conftest.py`); N1→N2→N3→N4 (rename
  chain, each depends on the last); 11→15 (all edit `src/api/routes/trips.py`).
- **Never concurrent:** any two `make test-file` runs. `Makefile:144-146` pulls
  `_ensure-test-db`, `_ensure-dev-data` and `valhalla-up`, so every "cheap" step starts the
  shared containers and writes the shared 7687 dev graph. The engine serialises the gate.

## Top risks (carried forward, still live)

1. `tour_text_candidate.py` gets deleted anyway — step 5 carries a permanent must-exist
   assertion (D5).
2. The facade quietly becomes a fork via "tidying while moving" — step 8 is a byte-identity
   test, not a behaviour test.
3. The firewall is written absolutist and never lands — shrink-only ratchet (D6).
4. A lone module deletion reddens the whole suite at `conftest.py:181`/`:235` — steps 2 and
   3 are explicitly multi-file with `maxAttempts: 3`.
5. The geometry gate gets promoted from SHADOW — step 23 rewrites the inviting comment;
   step 22 asserts `passed`/`warnings` are untouched.
6. **New in this reshape:** the vocabulary rename (N1-N4) runs before the engine is built
   (D7) specifically so the engine is authored once in final names — if the rename slips
   after step 7+, engine.py would need a second pass.

Runner-up: `_test-golden` is RED at HEAD, so any agent seeing a red gate is tempted to
re-baseline the fixtures. No step cites it.
