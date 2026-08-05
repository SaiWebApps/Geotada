# Carry-forward action items — unify-tour-algorithm

Deviations, deferrals and drift found DURING execution. Nothing here is a reason to
stop and re-plan; each item names the step that already owns it. Anything that turns
out to own no step gets one added here explicitly rather than silently absorbed.

Convention: `[OWNED BY step N]` = already in the ledger, no new work.
`[UNOWNED]` = nobody owns it; decide before close.

---

## A1 — Compose hard-refuses on a Valhalla version failure; the locked decision says degrade
**[UNOWNED — belongs with step 14/15]**

Step 3 added a guarded `503 routing_version_unavailable` around
`routing_client.routing_version()` (`src/api/routes/trips.py:592-602`). The guard is
right — unguarded it escaped as a generic 500, or worse was relabelled
`compose_verification_failed`, which blames the narrator for a container that is
merely still booting.

But `run-context.md` locks the Valhalla receipt bar to **labelled degradation, not
hard refusal**, precisely because `ondoway-valhalla` is a real Render service that
cold-starts and rebuilds tiles (`render.yaml:98-124`), and a hard refusal takes tour
generation down app-wide during an outage. Compose currently refuses where the
decision says it should degrade.

Note the asymmetry is defensible and may be the right end state: every walking leg
already falls back to a straight-line estimate, but the routing VERSION is provenance
— it binds the authored tour to the engine that measured it. Resolve explicitly in
step 14 (which owns AC-18/AC-20) rather than leaving two answers in the tree.

## A2 — Generate still plans on the legacy 0.83 budget while compose now plans at 1.00
**[OWNED BY step 9 — AC-4]**

`src/api/routes/trips.py:327` calls `select_k_routes(...)` with no `planning_policy`,
which defaults to `LEGACY_ROUTE_PLANNING_POLICY` (`src/tour/selection.py:2153`,
`src/tour/routing.py:124-128`, `ERR_SHORT = 0.83` at `routing.py:43`). Step 3 moved
compose to certification (0.90/1.10, nominal 1.00). The two ends therefore disagree
until step 9 lands.

Blast radius is narrower than it looks: `planning_policy` reaches only
`Route.target_audio_seconds` and `Route.err_short_total_seconds`
(`src/tour/routing.py:443-451`), thence `Script.total_planned_seconds` and the
rubric's time ceiling. It does NOT move the stop set, the order, or per-stop dwell —
the audio governor caps on `MAX_DWELL_AUDIO_SECONDS` and a relative domination rule
(`src/tour/selection.py:1288-1296`), not on the route budget. So it corrupts the
tour's DECLARED length, not its shape.

## A3 — AC-8 is a two-step criterion; step 3 delivers half by design
**[OWNED BY steps 9-11 — already assigned in state.json]**

Two hostile skeptics independently marked step 3 as "AC-8 REFUTED". Both are correct
on the facts and both missed that the plan already says so:
`findings/contracts-block2-seam.md:727-734` states step 3 delivers only half of AC-8,
that identical `eta_seconds`/`vignettes`/`tourability` needs "the persisted-option
work in steps 9-11", and verbatim: **"Record this in the step's persist note; do not
claim AC-8 closed."** `state.json` assigns AC-8 to step 3 AND step 11.

Still open at the end of step 3, all inside steps 9-11's declared file scope:
- `trips.py:603-612` re-derives the whole route via `summarise_route`.
- `trips.py:616-619` re-derives vignettes and patches them on with `model_copy`.
  `select_vignettes` (`src/tour/selection.py:3483`) has exactly ONE caller in all of
  `src/` — this line. Generate never calls it; selection populates `Route.vignettes`
  internally (`src/tour/selection.py:2114`). It is a genuine second implementation,
  and it lowercases the lens set where generate uses the raw one.
- `trips.py:623-624` hand-restores anchor identity via `model_copy`.
- `Route.tourability` is unconditionally `None` on this path: `summarise_route` never
  sets it (`src/tour/routing.py:444-453`), only selection attaches it
  (`src/tour/selection.py:3596-3604`), and `TripComposeResponse`
  (`src/api/models/trips.py:180-192`) has no field to carry it.

Concrete change list for steps 9-11 (all existing files, so AC-30 stays green):
1. `src/tour/routing.py::summarise_route` — add keyword-only `vignettes`,
   `tourability`, `start_anchor_poi_id`, `fixed_end_poi_id`, defaulting to today's
   behaviour, passed into the `Route(...)` build at :444-453. This is what makes "no
   hand-restore" literally true: build the route right once instead of patching twice.
2. `src/tour/options.py` — extract the inline ETA expression (:114-117) into a
   module-level `option_eta_seconds(route, script)` and call it from
   `build_route_option`. Generate must persist the ETA before `build_route_option`
   runs (that builder needs a trip id that only exists after `create_trip_with_stops`),
   and duplicating the formula would recreate the exact drift AC-8 forbids.
3. `src/api/routes/trips.py::generate_trip` (:401-410) — persist `vignettes`,
   `tourability` and `eta_seconds` per flavour.
4. `src/api/routes/trips.py::compose_trip` — read those back with `entry.get(...)` so
   the legacy fail-open branch survives, rehydrate vignette POIs from `pois_by_id`,
   pass all four into `summarise_route`, then DELETE :616-619 and :623-624 and drop
   `select_vignettes` from the import at :83 (it becomes unused; ruff F401 will say so).

## A4 — AC-8 needs an honest narrowing on `eta_seconds`
**[UNOWNED — decide before close, precedent exists]**

Bit-identical `eta_seconds` is not achievable and should not be attempted. ETA is
routed leg seconds plus dwell. The option's legs were measured by Valhalla at generate
time; compose re-measures live, possibly days later, possibly against rebuilt tiles,
possibly on haversine during an outage — which AC-20 explicitly requires to stay a
200. Guaranteeing identity would mean persisting every transit's leg seconds, distance
and polyline per flavour and never re-measuring, freezing a stale measurement onto a
tour composed much later.

AC-10 already carries exactly this kind of narrowing note, so the precedent is set.
Proposed wording:

> "…the composed route's POI ids, order, vignettes and tourability are identical to
> the chosen option's, and its eta_seconds is the option's persisted value carried
> through rather than re-measured. NOTE: narrowed from the original wording. Compose
> re-measures walking legs live because a route composed days after it was planned
> must reflect the current road network and must survive a Valhalla outage per AC-20,
> so a re-derived ETA cannot be bit-identical; the criterion's REASON — the user is
> authored the tour they picked, not a silently different one — is delivered in full
> by passing the option's declared ETA through."

Two secondary caveats for whoever writes the proving test:
- `tourability` is `None` for every GREEN tour by design
  (`src/tour/selection.py:3596-3604`), so an equality assertion is vacuous unless the
  fixture is YELLOW or delivered-thin. Test-design requirement, not an impossibility.
- `TripComposeResponse` carries neither `eta_seconds` nor `tourability`. AC-8 says
  "the composed route's", not "the response's", so asserting in-process is defensible.
  Making it visible to the phone means two additive fields on that model.

## A5 — Stale line citation left by step 1
**[UNOWNED — trivial, fix when next in that file]**

`tests/test_trip_api.py:663` cites `trip_service.dart:227-229`. After step 1's
deletion those lines are `:201-203`.

## A6 — Step 3's proving test asserts none of AC-8's identity
**[OWNED BY step 11]**

`tests/test_trip_api.py::test_compose_plans_and_authors_through_the_shared_premium_seam`
has eight assertions: five source-greps, one env check, one 503 check, one
checker-consulted check. Its own docstring claims only AC-10. When step 11 closes
AC-8, extend it (or add a sibling) to compare the composed route against the persisted
option — same POI ids in order, same vignette leg-to-id map, same tourability payload,
same `eta_seconds`. Mutation proof: re-introduce `select_vignettes(...)` and the
vignette-equality assertion must go RED.

---

## Infrastructure added during this run (not in the original ledger)

Per-worktree pytest graphs, so concurrent lanes cannot wipe each other's fixtures.
Extends existing mechanisms; no new module, no new Makefile target.

- `docker-compose.yml` — `neo4j-test2` (:7690) and `neo4j-test3` (:7691), heap-capped
  768m/256m because a third UNcapped Neo4j killed dockerd on 2026-07-02.
- `config/profiles/test2`, `config/profiles/test3` — copies of `test` on the new ports.
- `scripts/preflight.py` — two rows in the existing `DATABASES` tuple, which
  auto-generates the `db-test2`/`db-test3` requirements with probes and repairs.
  `_prerequisite_sets` now also reads `NAME ?= value` literal defaults, so
  `db-$(TEST_PROFILE)` resolves instead of reading as a nonexistent requirement.
- `Makefile` — `TEST_PROFILE ?= test`; `TEST_EXEC` and `PRE_PYTEST` both key on it, so
  an override cannot run against a graph that was never started. `make test` and
  `make audit` are deliberately NOT parameterised: the definitive bar always runs on
  the canonical graph.
- `scripts/dev_env.py` — profile choices now derived from `config/profiles/` on disk
  instead of a restated literal list, so adding a profile cannot leave it behind.
- `tests/conftest.py` — 7690/7691 added to `_TEST_PORT_ALLOWLIST`. Dev (7687) and
  workbench (7689) stay out; the workbench suite asserts exact state on 7689 and would
  be broken by a wipe it did not perform.

Proven: `make lint` clean; `tests/test_preflight.py` 71 passed; the same
database-wiping test ran on :7690 and :7691 SIMULTANEOUSLY, both passing in 49s each
(equal wall time = genuine parallelism, not queuing).
