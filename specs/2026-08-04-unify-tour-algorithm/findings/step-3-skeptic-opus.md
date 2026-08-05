# Step 3 skeptic (negative space) — hostile review, round 2

Verified against: HEAD `a7df218c0ce3ca28df2e31df895f80e5ea3a7ef5` **plus the uncommitted
working tree** (`git diff HEAD | md5` = `3812addfde6b4f264f529e8af5fe77be`, 16 entries in
`git status --porcelain=v1`). Date 2026-08-04. Angle: negative space — states of the world
that were not tested, the same code path reached by another entry point, side effects of
the fix on infrastructure and on coverage.

Executed by me in this session: `make lint` (exit 0, "All checks passed!") and read-only
`git show` / `git diff` / `grep` / `awk`. Everything that touches the shared 7687/7688
graph, Valhalla or :8001 is PROPOSED for the serial verifier, per the concurrency rule.

**Round-1 finding F1 is now REFUTED and withdrawn.** The dirty-tree opt-in has moved from
a module fixture in `tests/test_trip_api.py` to a suite-wide `os.environ.setdefault` at
`tests/conftest.py:64`, which is what OWNER RULING 4 asked for. Every pytest shard in
`make test` (`_test-python`, `_test-golden`, `_test-grade`, `_test-invariants`,
`test-workbench`, `test-live`) collects under `tests/`, so all of them get it.

---

## N1 (high) — AC-8 is claimed and not delivered; the step changed none of it

AC-8 verbatim: the composed route's "POI ids, order, eta_seconds, vignettes and
tourability are identical to the chosen option's — no re-derivation and no hand-restore,
**replacing trips.py:583-590** and the always-None tourability."

Inside `compose_trip` (src/api/routes/trips.py:486-768) all three named things survive:

    awk 'NR>=486 && NR<=768' src/api/routes/trips.py \
      | grep -n "summarise_route(\|anchor_restore\|tourability\|routing_version()"
    -> 93: routing_version = routing_client.routing_version()
       94: route = summarise_route(          # file line 579 — the re-derivation
      114: if anchor_restore:                # file line 599
      115: route = route.model_copy(update=anchor_restore)   # the hand-restore
      (zero matches for "tourability")

The only edit to that block in this diff is the added `planning_policy=`. The compose
response model `TripComposeResponse` (src/api/models/trips.py:180-192) carries no
tourability and no eta at all. The run-context narrows AC-10 explicitly; it narrows
nothing for AC-8. The step's own test asserts `len(stops) == n_stops` and nothing about
order, eta, vignettes or tourability.

Verdict: the claim "step 3 satisfies AC-8" is false as written.

## N2 (high) — step 3 makes AC-8's identity *worse*: compose now plans on a different
   time budget than the option the user picked

`/trips/generate` still calls `select_k_routes(tour_input, snapshot, 3,
routing_client=routing_client)` with **no** `planning_policy` (src/api/routes/trips.py:325),
so every persisted option is derived under `LEGACY_ROUTE_PLANNING_POLICY` — the flat 0.83
budget (src/tour/routing.py:124-128). Compose now rebuilds that same pick under
`certification_planning_policy(...)`, whose nominal fraction is (0.90+1.10)/2 = 1.00
(src/tour/premium_tour.py:323-329, src/tour/routing.py:81-84).

`summarise_route` turns the policy into the Route's `target_audio_seconds` and
`err_short_total_seconds` (routing.py:443-452), and `generate()` copies the latter into
the script as `total_planned_seconds` (src/tour/generation.py:420). So the composed tour
is budgeted against a ~20% longer tour than the option it was picked from, and
`quality_rubric` reads `err_short_total_seconds` as a time-budget ceiling
(quality_rubric.py:438-461).

This is defensible as a way-station — step 6 deletes the legacy policy and AC-4 fixes
trips.py:325 — but it is the exact opposite of "identical to the chosen option's", and
until those steps land the two halves of one tour disagree about how long it is. Nothing
in the step's test notices, because no assertion compares a generate-time figure to a
compose-time one.

## N3 (high) — a Valhalla that is half-started now turns compose into an unhandled 500

New line src/api/routes/trips.py:578: `routing_version = routing_client.routing_version()`.

`RoutingClient.routing_version` (src/tour/routing_client.py:183-200) is the one method
with no degradation path: it does `self._client.get("/status")`, `raise_for_status()`, and
raises `ValueError` if the payload omits a version. It sits **outside** both `try` blocks
in `compose_trip`, so `httpx.ConnectError` (container down), `HTTPStatusError` (cold
start, tiles rebuilding) and that `ValueError` all escape as a 500.

Before this diff compose never called it — `git show HEAD:src/tour/authoring.py`'s
`author_prebuilt_route` block contains no `routing_version` and no build identity — and
`summarise_route` degrades to haversine legs, so compose returned 200 during a Valhalla
outage. `ondoway-valhalla` is a real network service (`render.yaml:98-124`), and this
run's own Param 4 decision is "labelled degradation, not hard refusal, because a hard
refusal would take tour generation down app-wide during an outage". Compose has just
joined the hard-refusal side, on the authenticated endpoint that burns the trip's one-shot
compose budget.

No cheap reproduction exists: `config/profiles/test` pins `VALHALLA_URL` and Make overlays
the profile atomically, so an ambient override never reaches pytest, and stopping the
shared container is forbidden. Advisory, with the citations above. Bounded fix: treat an
unresolvable routing version exactly like the unresolvable fingerprint one line below it —
503 with a named reason — or record a routing degradation.

## N4 (medium) — the new seam adds four engine-fault classes that all land on the phone as
   "the narrator wrote something untraceable"

The old seam returned `composition.script` and stopped (`git show
HEAD:src/tour/authoring.py`, end of `author_prebuilt_route`). `finalize_premium_tour`
(src/tour/premium_tour.py:700-752) additionally builds a `BuildFingerprint`, remaps
playback assignments fail-closed, constructs a `FinalTourBlueprint`, and runs
`validate_llm_composed_blueprint`, raising a bare `ValueError(ineligibility)` when the
blueprint is not certification-eligible (artifact.py:962-987).

`compose_trip`'s `except ValueError` maps every one of those to **422
`compose_verification_failed` with `untraceable=0, forbidden=0, provenance=0,
faithfulness=0`** — a refusal whose four cause counters are all zero, which the phone
renders as a narration refusal. That is precisely the mislabelling the developer's own
comment forbids six lines earlier for the fingerprint case ("must never be relabelled
compose_verification_failed — that code means 'the narrator wrote something untraceable'
and would blame the writer for an engine fault").

I could not name a concrete route shape that triggers it, so this is a bounded advisory,
not a blocker. It is negative space by construction: the step's test uses an executor that
echoes the stitched script with one prefix added — the friendliest possible input to the
blueprint layer.

## N5 (medium) — the two ally tests AC-27 freezes now guard a seam no live surface uses

`tests/test_tour_authoring_gates.py:758` (`test_cross_stop_echo_is_suppressed`) and
`:886` (`test_the_preview_surface_runs_the_same_three_gates_as_the_phone`) prove gate
parity between two named surfaces, and their own text names surface 1 as "the persisted
`POST /trips/{id}/compose` engine — `author_prebuilt_route`" (line 772). They call
`author_prebuilt_route` directly, so after this step they still pass — while no longer
saying anything about the endpoint they name. AC-27 requires both to remain "unchanged",
so this coverage loss is scheduled to be invisible: the tests stay green forever and the
compose endpoint's cross-stop de-dup and three-gate parity go unproven from the moment
this diff lands.

`test_the_preview_surface_runs_the_same_three_gates_as_the_phone` also asserts over
`inspect.signature(author_prebuilt_route).parameters` (line 529), i.e. it pins the knob
set of a function that is no longer on any live path.

Verified by reading; `grep -rn "author_prebuilt_route" tests/test_tour_authoring_gates.py`
shows the direct calls at 749, 810, 929 and none through the endpoint.

## N6 (medium) — the half of the diff that "lets the test suite declare itself a local
   build" has no executed red-first proof, and no test covers the check it disarms

The QA mutation reverted `src/api/routes/trips.py` only, and says so: it did not
separately run the conftest half. So the claim's second clause is proven by prediction,
not by execution. Its predicted red (`assert os.environ.get(ALLOW_DIRTY_LOCAL_BUILD_ENV)
== "1"`) is also environment-dependent — it stays GREEN with the conftest line deleted in
any shell that already exports the variable, which is exactly the shell of anyone who has
been running `scripts/workbench.sh`.

Separately, the opt-in is now armed for the whole suite and **nothing tests the refusal it
disarms**: `grep -rn "resolve_build_identity" tests/` returns only monkeypatches
(test_trip_preview_contract.py:253, test_trips_spend_and_authz.py:139/226,
test_trip_api.py:751) and the conftest comment. No test anywhere asserts that a dirty tree
without the opt-in raises. If that refusal regresses to always-allow, every test still
passes.

## N7 (advisory) — the untested entry points

The claim rests on ONE node id. Four other tests drive the same rebuilt code path through
a different module and were not run against this diff:

    make test-file FILE="tests/test_tour_authoring_gates.py::test_a_faithful_tour_still_composes"
    make test-file FILE="tests/test_tour_authoring_gates.py::test_the_endpoint_consults_the_real_checker_even_though_entailment_only_advises"
    make test-file FILE="tests/test_tour_authoring_gates.py::test_a_tour_with_deleted_facts_composes_because_coverage_only_advises"
    make test-file FILE="tests/test_tour_authoring_gates.py::test_invented_glue_is_refused_and_the_trip_is_untouched"

They are the only tests that push a rewriting, a fact-blurring and an inventing executor
through the **endpoint** (not through the seam directly), so they are the only existing
coverage of N4's new blueprint layer on real Paris data. I have no prediction of red for
them — that is the point of asking for them to be run. `tests/test_trip_api.py`'s own
`test_compose_authors_per_stop_and_keeps_the_wire_contract` (line 794) is in the same
position for the 422/409/404 wire contract.

## What I attacked and could NOT break

- **Suite-wide env leakage.** `setdefault` at conftest import; every `make test` pytest
  shard collects under `tests/`, and subprocesses inherit it. `_test-cloud` is not pytest
  and authors nothing. `scripts/workbench.sh` sets it itself. No shard is missed.
- **The opt-in escaping to a deployment.** `resolve_build_identity` takes the deploy branch
  whenever `RENDER_GIT_COMMIT`/`GIT_COMMIT_SHA` is set and re-raises on a dirty tree if
  `RENDER_GIT_COMMIT` is present (premium_tour.py:624-640). The suite-wide default cannot
  reach Render.
- **`faithfulness_checker=None`.** The endpoint dependency is `FaithfulnessChecker | None`
  and `finalize_premium_tour` has no default — but `None` is accepted downstream and means
  "trusting mock" (authoring.py:561, 583-584), so the sibling compose tests that inject no
  checker do not crash. No 500 here.
- **New concurrency at the seam.** `execute_premium_plan` uses
  `ThreadPoolExecutor(max_workers=min(6, len(units)))`; `git show
  HEAD:src/tour/authoring.py` shows the old `author_prebuilt_route` used the identical
  `max_workers: int = 6` and the same `min(...)`. No new burst on the provider.
- **Lost receipts.** The old seam had no receipt sink at all, so `EphemeralReceiptSink()`
  discards nothing that was previously kept.
- **A second legacy-0.83 route into the compose path.** The two un-policied
  `route_planning_budget(duration_min)` calls left in the tree (selection.py:997, :2613)
  sit in `_closer_b_alternative` and `_isochrone_walk_minutes`, both selection-only;
  compose does not select. AC-10's substance holds on the compose path.
- **`HTTPException(503, {...}, headers={"Retry-After": "30"})`** matches FastAPI's
  positional `(status_code, detail, headers)` signature.
- **Lint.** `make lint` run unpiped and in full by me: exit 0. AC-28 holds.
- **New provider spend.** Nothing in the diff adds a paid call; the executor is injected
  and the non-live suite's factory is the offline one.

## Verdict on the claim

- **AC-8: REFUTED** (N1) — the re-derivation, the hand-restore and the missing tourability
  are all still there, and N2 shows the step widens the plan/compose divergence it was
  supposed to close.
- **AC-10: substance holds, proof does not.** No un-policied budget reaches compose, but
  the only assertions are `"planning_policy=planning_policy" in source` and
  `"certification_planning_policy(" in source`, which any identically-named variable bound
  to any policy satisfies. Nothing asserts the fractions that actually reached
  `summarise_route`.
- **Mutation verdict REAL is accurate but thin**: the reverted-file run fails at the first
  of five source-grep assertions, and the conftest half of the diff was never mutated.
- Independently: compose gained an unhandled hard dependency on Valhalla (N3) and four new
  engine-fault classes that report as narration refusals (N4), and the two ally tests that
  are contractually frozen now guard a dead seam (N5).
