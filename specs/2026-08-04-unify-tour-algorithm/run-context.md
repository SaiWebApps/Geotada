# Run context — unify-tour-algorithm

Read this file by path. It is the shared brief for every step's builder,
skeptic and judge in this run so nothing has to be re-pasted into prompts.

## Tier

**Tier 2** (feature / user-facing / tour-engine): touches `src/tour/`,
`src/api/routes/`, `frontend/` and `mobile/`. No Makefile, `.claude/`, deploy,
DB/data or `.github` path touched, so it does not reach Tier 3. Skeptic panel
size P=2, acceptance runs.

## approved_by_human

`true` (stamped `approved_at: 2026-08-04T22:06:21Z` in `state.json`). This is
reported verbatim from the ledger, not inferred.

## Decisions locked (do not relitigate — see `state.json.decisions` for full text)

- **Target shape:** two shared blocks in `src/tour`. BLOCK 1 PLAN (start
  required, end optional, lenses, timing → K=3 route options, no LLM, no
  spend; its output IS the preview). BLOCK 2 AUTHOR (one chosen option → per-
  stop scripts + audio, paid, never re-plans) is `premium_tour.py`'s
  `execute_premium_plan` + `finalize_premium_tour`; `authoring.py:805-1038` is
  deleted.
- **Flavour** = a different route through different POIs for the same lens,
  duration, start and end (`selection.py:246-247`, `DIVERSITY_PENALTY 0.3`,
  `JACCARD_OVERLAP_MAX 0.60`). Three shown on both surfaces.
- **No stop-count cap, period** (OWNER RULING 5). All seven enforcement
  points removed, including `quality_rubric.MAX_COMPOSED_STOPS = 8`. Duration
  alone bounds tour length, including in the scorer. `ORDERING_EXACT_MAX = 16`
  inside `order_stops` in the existing `src/tour/ordering.py` is the
  tractability fallback (cheapest insertion above 16, no stop ever dropped).
- **Walk budget:** certification 0.90–1.10, nominal 1.00.
  `LEGACY_ROUTE_PLANNING_POLICY` (routing.py:124-128, 0.83 flat) is deleted,
  not made optional.
- **Audio char cap:** deleted from the preview path entirely (was an abuse
  bound on an anonymous endpoint, not a quality setting).
- **Valhalla receipt bar:** RESOLVED to labelled degradation, not hard
  refusal — `ondoway-valhalla` is a real network dependency
  (`render.yaml:98-124`) that can cold-start or rebuild tiles, so a hard
  refusal would take tour generation down app-wide during an outage. Uses the
  existing `src/tour/degradations.py` channel. Structural refusals (empty
  route, transit-count mismatch) stay hard refusals.
- **Audio staleness:** per-stop audio path gains a content hash so edited
  narration invalidates its audio (matches per-beat `audio_script_hash` and
  keep-exploring `keep_exploring_audio_hash`).
- **OWNER RULING 1 — planning shows places only:** on both surfaces, route
  options show POI names, order, walking times, ETA — no LLM glue, no
  vignette prose, no teaser text at plan time. All prose arrives only after a
  route is picked, in AUTHOR. Consequence: Block 1's glue client is OFF when
  planning options (this is what makes Block 1 genuinely free — see
  `q8_block_one_is_not_actually_free`, recommendation (a) adopted).
  `build_route_option` must not carry narration/vignette prose into the
  preview payload.
- **OWNER RULING 2 — workbench never asks a human to log in:** Phase 2
  initialises a background identity silently; step 11's anonymous route is a
  stopgap for that, not a permanent surface. Each of the three option cards
  gets a "Select / Build this tour" button (step 12).
- **OWNER RULING 3 — delete the POC page:** `frontend/tour-preview.html` is
  deleted outright (step 13), not re-pointed; its standalone-preview test in
  `tests/test_workbench_ui.py` is deleted with it.
- **OWNER RULING 4 — keep the build-identity stamp, fix the tests:** the
  dirty-tree refusal in `finalize_premium_tour` (premium_tour.py:545-615) is
  correct and stays. Step 3 makes the test suite declare itself a local build
  via the existing `ONDOWAY_ALLOW_DIRTY_LOCAL_BUILD=1` opt-in (a suite-wide
  `tests/conftest.py` setdefault), the same opt-in `scripts/workbench.sh`
  already sets. An unresolvable build fingerprint on the compose path should
  return 503 with a named reason, not a generic 500.
- **Endpoint name:** the new anonymous route is `POST /trips/preview/author`
  (not `/compose` — that name is taken by the authenticated
  `/trips/{trip_id}/compose`). Selector is `route_id`, a 12-hex plan
  fingerprint; a stale fingerprint is refused `409 plan_changed`.
- **q3 (fixed-destination over-ceiling):** the certification infeasibility
  error must not escape as an uncaught 500; give it the gap-minutes and
  alternatives payload via the existing refusal-detail helper, catch it on
  the generate route, and replace the internal identifier
  `premium_route_infeasible` with plain English on the workbench.
- **Step 5's `b1_repair_trial_bound` (OPEN, low severity):** `TIMEBOX_REPAIR_MAX_TRIALS
  = 4000` should not bind on anything reachable today, but the real eligible-
  pool size on the live dev graph was unmeasured at plan time — verify during
  step 5.
- **Unbound-change remedies are mandatory:** the caps contract
  (`findings/contracts-caps-and-policy.md`) named one-assertion remedies for
  changes in steps 5 and 6 that their own proving test could not bind. These
  remedies must ship with those steps — an unbound change is a change nobody
  proved.

## Full acceptance criteria (verbatim)

- **AC-1**: Given the repository at the end of this slice, when the module graph of src/tour is parsed, then exactly one callable produces the K=3 route options (the PLAN block) and exactly one seam authors a chosen option (execute_premium_plan + finalize_premium_tour in premium_tour.py), and no second implementation of either exists.
- **AC-2**: Given a corpus snapshot and a TourInput with a start, no end, one lens and a duration, when the PLAN block is called with a stub routing client and a provider that raises on any call, then it returns 3 RouteOptions and the provider is never invoked.
- **AC-3**: Given the same input, when PLAN returns its 3 options, then no two options have a Jaccard stop-set overlap above JACCARD_OVERLAP_MAX (0.60, selection.py:246-247) and all 3 share the same lens, duration, start and end.
- **AC-4**: Given a live FastAPI test client, when POST /trips/generate is called, then its options field contains 3 options produced by the PLAN block and the call passes the certification policy, so select_k_routes is no longer reached at trips.py:325 with no planning_policy.
- **AC-5**: Given the workbench Tour Preview view opened in a real browser, when the operator fills the form (frontend/review.html:2149-2185) and presses generate, then the page issues exactly one network POST, renders 3 selectable options, and issues zero audio or authoring requests until an option is clicked.
- **AC-6**: Given that state, when the operator clicks one option, then the page issues exactly one further POST to the author endpoint carrying that option's identifier, and the rendered stops are the stops of the option the operator clicked — same POI ids in the same order.
- **AC-7**: Given identical inputs (start, end, lenses, duration, city), when the app path and the workbench path each run PLAN, then the two produce the same ordered stop sets and the same eta_seconds per option.
- **AC-8**: Given a plan whose chosen option is handed to the AUTHOR block, when authoring completes, then the composed route's POI ids, order, eta_seconds, vignettes and tourability are identical to the chosen option's — no re-derivation and no hand-restore, replacing trips.py:583-590 and the always-None tourability.
- **AC-9** (negative): Given the AUTHOR block's source, when its import and call graph is parsed, then it names no member of _PLANNING_CALLS (select_k_routes, choose_discrete_route, plan_premium_tour, certification_planning_policy, route_planning_budget, summarise_route, insertion_cost_seconds, generate) and imports no planning module.
- **AC-10** (negative): Given the compose path, when its call graph is parsed, then it obtains no UN-POLICIED route summary: any route it rebuilds passes the certification policy explicitly, so no call reaches the legacy 0.83 budget. NOTE: narrowed from the original wording (which demanded summarise_route vanish entirely) after the Block 2 contract proved the letter unachievable in Phase 1 — compose persists only POI ids, so it must rebuild a route and cannot simply stop summarising one. The criterion's REASON, no un-policied 0.83 budget on the compose path, is delivered in full; only the mechanism differs.
- **AC-11** (negative): Given the whole repository, when authoring.py is parsed, then PrebuiltRouteComposeUnit, PrebuiltRouteAuthoringPlan, PrebuiltRouteExecutor, prebuilt_route_sha256 and author_prebuilt_route are absent, AUTHORING_MAX_STOPS is absent from __all__, and a repository-wide search for each returns zero hits; the five already-shared helpers (_certification_compose_requests, candidate_compose_request_envelope, compose_input_sha256, _sentences_from_json, finalize_certification_composition) must still exist.
- **AC-12** (negative): Given the deleted Dart code, when mobile/ is searched, then BeatAudioPlayer and TripService.confirmTripAudio return zero hits, including in mobile/test/widgets/beat_audio_player_test.dart and mobile/test/services/trip_service_test.dart which exercise them today and must be deleted with them, with make flutter-test and make flutter-analyze green.
- **AC-13** (negative): Given a POST to the plan-only preview, when it returns 200, then the response contains no LLM-authored narration: narration_kind is not llm_candidate and no per-stop script text is present, because planning no longer authors.
- **AC-14** (negative): Given the whole src/ tree, when it is searched, then the symbols LEGACY_ROUTE_PLANNING_POLICY and RoutePlanningPolicy.is_legacy return zero hits, every parameter that defaulted to the legacy policy either requires an explicit policy or defaults to certification at 0.90/1.10 nominal 1.00, and no planning, tourability or quality path can obtain a 0.83-derived walk or audio budget. NOTE: this is a symbol-and-behaviour check, NOT a grep for the literal 0.83 — the ERR_SHORT constant at routing.py:43 has six live callers (routing.py:225,229,248 and density.py:38,303,400) whose fate is settled by step 6, so a literal grep could never pass.
- **AC-15** (negative): Given the whole src/ tree, when it is searched, then no stop-count ceiling survives: max_stops=8 gone from certification_planning_policy, the min(HARD_ANCHOR_CAP, duration // ANCHOR_CAP_DIVISOR) clamp gone, the 1 <= len(stops) <= AUTHORING_MAX_STOPS guard gone, and the planning_budget.max_stops or HARD_ANCHOR_CAP fallbacks at selection.py:1879 and :1907 gone with them.
- **AC-16**: Given a duration long enough that the time budget seats more than 15 stops in a dense start area, when PLAN runs, then it returns an option with more than 15 dwell stops and the AUTHOR block accepts it without raising. The acceptance agent reports the observed paid-call count, since duration alone now bounds it.
- **AC-17** (negative): Given the whole src/ tree, when it is searched, then _preview_stops returns zero hits and build_route_option (src/tour/options.py:51) is the only interleave implementation.
- **AC-18** (negative): Given a plan whose transits have no Valhalla receipt and no measured leg seconds, when the response is serialised on either surface, then it carries an explicit degradation row naming routing as the cause (a Degradation with a stable kind, plain-English human text, and component, per src/tour/degradations.py:44-67), and there is no code path on which such a route is returned with an empty degradations list.
- **AC-19** (negative): Given the character cap removed from the preview audio path, when a 12,000-character narration is posted to /audio/preview with a stub provider, then the provider receives all 12,000 characters — the text is not truncated.
- **AC-20** (negative): Given a routing client injected to fail every request, simulating ondoway-valhalla cold-starting or rebuilding tiles, when PLAN runs, then it returns 200 with 3 options built on estimated legs AND a routing degradation row; it must NOT raise PremiumRouteInfeasibleError, must NOT return 422, and must NOT return the route unlabelled. The routing client is stubbed in-process — the shared Valhalla container is never stopped.
- **AC-21**: Given that same failure injected behind the workbench, when the operator generates a tour, then the page visibly shows the routing degradation in the existing degradation panel with plain-English text and no identifiers, before the operator can click an option.
- **AC-22** (negative): Given a chosen option whose transits are estimated legs with no receipt, when it is handed to the AUTHOR block, then authoring proceeds and produces one script per dwell stop — the receipt bar lives in PLAN, never in AUTHOR.
- **AC-23**: Given a request with a start and no end, when PLAN runs, then it returns 3 options with no 4xx and no KeyError or None dereference, exercising the endpoint-pull reservation logic on the end-is-None side.
- **AC-24** (negative): Given a duration too short to seat any tourable stop from the given start, when PLAN runs, then it returns a structured 422 whose body has the reason/gap_minutes/alternatives shape of _refusal_detail with a reason naming the time budget; it must NOT return 200 with zero stops and must NOT return a bare string body.
- **AC-25**: Given a trip whose itinerary item already has an audio_url and whose narration is then edited, when the per-stop audio generation is called without force, then that stop's result status is generated, not skipped, matching the per-beat staleness contract.
- **AC-26** (negative): Given the same trip with narration unchanged and its stored hash current, when the same call is made without force, then the stop's status is skipped with reason already has audio and the TTS provider is invoked zero times; the existing self-heal when the artifact is missing must still fire.
- **AC-27**: Given the finished slice, when the ally tests are run, then they pass without a weakened assertion: test_tour_authoring_gates.py::test_the_preview_surface_runs_the_same_three_gates_as_the_phone and test_tour_authoring_gates.py::test_cross_stop_echo_is_suppressed unchanged, and test_premium_workbench_wiring.py::test_preview_uses_shared_premium_plan_and_finalizer re-pointed at the split rather than deleted.
- **AC-28**: Given the finished slice, when make lint is run unpiped and in full, then it prints zero errors.
- **AC-29**: Given the finished slice, when make test is run once, then every shard reports 0 failed and 0 skipped. A deselect, --ignore, or -k exclusion is a failed criterion.
- **AC-30** (negative): Given the finished slice, when the diff is read, then no new module file under src/tour/ and no new Makefile target were added — existing ones carry the change.

## Baseline (step 0)

- `make lint` — All checks passed! (ruff over src/ tests/ scripts/{9 files}), 2026-08-04.
- Commit: `a7df218c`.
- Step 0 of `/team` was skipped by explicit owner instruction; the owner's brief at
  `00-brief.md` IS the research and is verified at `a7df218c`. The planner re-verified every
  line reference the brief cites; all held except one drift: `tests/test_trip_api.py` does
  NOT structurally read Dart source (only mentions `trip_service.dart` in a comment) —
  `tests/test_no_doubles_on_human_surfaces.py` is the only Python test that does.
- Engine cap guard was green at plan time: `node .claude/team-engine.test.js` — all 91
  checks passed across 17 pathological shapes. Re-verified for THIS run below.

## This run's infra probe (2026-08-04, read-only)

- `docker ps`: `ondoway-neo4j` (dev, 7687), `ondoway-neo4j-test` (7688),
  `ondoway-neo4j-workbench` (7689), `ondoway-valhalla` (8002) all up.
- `make doctor` (`PREFLIGHT_AUTOFIX=0`, report-only, nothing started/installed): 21 of 22
  prerequisites OK, including `db-dev`/`db-test`/`db-workbench` each confirmed by a real
  bolt-protocol answer (not a `docker ps` guess), `dev-data` matching 3 committed cities, and
  `valhalla` healthy on :8002. The one miss, `port-8000`, is a pre-existing local dev-server
  process holding that port on this machine and is unrelated to test infra.
- `make lint`: All checks passed! (fresh run this session).
- `node .claude/team-engine.test.js`: exit 0, all 91 checks passed across 17 pathological
  shapes — the termination caps, the paid-bar one-shot, and the pre-fan-out gate order are
  verified for this run.

## Pinned per-step gate commands

Every step's `test_command` is a single pytest node id via `make test-file`
(the $0, container-starting rung: `PRE_PYTEST` brings up 7688 + dev data +
Valhalla). `gate_commands` below are re-derived from each step's `files[]`
per the fixed rule — `make lint` for any `src/`/`tests/`/`scripts/` file,
`make flutter-analyze` for any `mobile/` file, and a targeted `test-file`
node id (never the full `make test-workbench` shard) for any `frontend/`
file. `make test`, `make audit`, `make test-live` and `make test-workbench`
never appear in a per-step gate — they run once each at the phase/close
gate, never inside the per-step loop.

| Step | gate_commands |
| --- | --- |
| 1 | `make lint`, `make flutter-analyze` |
| 2 | `make lint` |
| 3 | `make lint` |
| 4 | `make lint` |
| 5 | `make lint` |
| 5.5 | `make lint` |
| 6 | `make lint` |
| 6.5 | `make lint` |
| 7 | `make lint` |
| 8 | `make lint` |
| 9 | `make lint` |
| 10 | `make lint` |
| 11 | `make lint` |
| 12 | `make lint`, `make test-file FILE="tests/test_workbench_ui.py::TestDetailViewAndEditing::test_tour_preview_generates_and_plays"` |
| 13 | `make lint`, `make test-file FILE="tests/test_workbench_ui.py::TestDetailViewAndEditing::test_standalone_tour_preview_renders_basic_lane_honestly"` |
| 14 | `make lint` |
| 15 | `make lint` |
| 16 | `make lint`, `make flutter-analyze` |
| 17 | `make lint` |
| 18 | `make lint` |

Note: steps 1's and 16's original ledger entries also listed `make flutter-test` as a gate.
That is a full Flutter shard, not the fast `flutter-analyze` static check, so per the fixed
derivation rule it is NOT reinstated as a per-step gate here — it belongs at the phase/close
gate (`make test`), same as `make test-workbench` does for frontend steps. Steps 12 and 13's
original entries listed `make test-workbench` (the full, minutes-long Playwright shard); both
are replaced above with a single targeted node id from the same file, which is faithful to
what those steps actually touch without paying for the whole shard on every attempt.
