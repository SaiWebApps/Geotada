> # ⛔ OWNER RULINGS OVERRIDE THIS DOCUMENT — READ FIRST
>
> This contract was written BEFORE the owner answered the plan's open questions on
> 2026-08-04. Where this document and the rulings below disagree, **THE RULINGS WIN.**
> The authoritative copy of each is in `../state.json` under `decisions`, keyed
> `OWNER_RULING_1..5`. Do not follow a superseded instruction because it is more
> detailed — detail is not authority.
>
> 1. **Planning shows PLACES ONLY.** During route planning, on BOTH surfaces, an option
>    shows POI names, order, walking time and ETA — and NO descriptive text whatsoever.
>    No LLM glue, no vignette prose, no teaser text, no narration. All words arrive only
>    at script generation, after a route is picked. Planning therefore makes NO paid call.
> 2. **The workbench never asks a human to log in.** Phase 2 gives it a background
>    identity it uses silently. The Phase-1 no-login route is a stopgap for that, and the
>    operator's trigger is a **"Select / Build this tour"** button on each of the three
>    option cards.
> 3. **`frontend/tour-preview.html` is DELETED**, not re-pointed. Step 13 is a deletion
>    proof.
> 4. **The build-version stamp (`resolve_build_identity`) STAYS UNCHANGED.** It is what
>    makes a tour traceable to the code that built it. The fix belongs in the test setup,
>    which must declare itself a local build via the EXISTING
>    `ONDOWAY_ALLOW_DIRTY_LOCAL_BUILD=1` opt-in, exactly as `scripts/workbench.sh` does.
>    Do not bypass, weaken or delete the check.
> 5. **No stop limits. Period.** All SEVEN ceilings go, including
>    `quality_rubric.MAX_COMPOSED_STOPS`. Consequence accepted by the owner: the C3 check
>    stops flagging long tours, and duration alone bounds tour length everywhere.
>
> Also pinned: the new route is **`POST /trips/preview/author`** (never
> `/trips/preview/compose` — that name is already taken by the authenticated saved-trip
> route). Its option selector is `route_id`, a 12-hex plan fingerprint; a stale
> fingerprint is refused `409 plan_changed` rather than authoring an unseen tour.
>
> **DEAD IN THIS FILE:** every part of the step-8 behaviour table that folds vignette one-liner prose or narration cards into the PREVIEW payload. Vignette SELECTION may still influence which POIs are chosen; vignette PROSE must not reach a preview card. Step 7 passes the glue client OFF.

---

# Implementation contract — STEP 7, STEP 8, STEP 14

Written against the tree at `a7df218c` (the working tree at the time of writing; the only
uncommitted changes are two deleted `.claude/hooks/*.sh` files and one untracked markdown
file, none of which this contract touches).

**Every line number below was re-read from the live files, not copied from the brief.**
Where the brief drifted, it is called out inline under "BRIEF DRIFT".

This document is a contract, not a plan. The implementer must not choose, infer, or design
anything that is not written here. Anything genuinely undecidable is in the final section.

---

## 0. Ordering, and what has already changed by the time each step runs

The ledger (`state.json`) orders these steps as: `7` after `2` and `6`; `8` after `6`;
`14` after `11`.

By the time step 7 runs, steps 1–6 have landed. Two of them change lines this contract
quotes:

- **Step 5** deletes `max_stops=8` from `certification_planning_policy`
  (`src/tour/premium_tour.py:230-236`). So the implementer will see a
  `certification_planning_policy` with three keyword arguments, not four. Nothing in
  step 7 depends on that argument.
- **Step 6** deletes `LEGACY_ROUTE_PLANNING_POLICY` (`src/tour/routing.py:124-128`) and
  therefore changes the default of `select_k_routes`'s `planning_policy` parameter
  (`src/tour/selection.py:2153`). Step 7 always passes an explicit policy, so it is
  unaffected either way.

By the time step 14 runs, steps 7–13 have landed, including step 7's refactor of the
receipt bar into the named predicate this contract defines. Step 14 is written as an edit
to **step 7's** shape, and both shapes are given in full.

---

# STEP 7 — Block 1 returns three free plans instead of one

**Ledger:** id `7`, files `src/tour/premium_tour.py`, `tests/test_premium_workbench_wiring.py`.
**Proving test:** `tests/test_premium_workbench_wiring.py::test_block_one_returns_three_priced_free_plans`.
**Gate:** `make lint`.
**Criteria:** AC-1, AC-2, AC-3, AC-23.

## 7.1 The current code being replaced

`src/tour/premium_tour.py:239-355`, quoted in full for the parts that change. The
signature, verbatim, at `src/tour/premium_tour.py:239-247`:

```python
def plan_premium_tour(
    tour_input: TourInput,
    snapshot: CorpusSnapshot,
    *,
    routing_client: RoutingClient,
    planning_policy: RoutePlanningPolicy | None = None,
    generation_time: dt.datetime | None = None,
    authorities: PremiumAuthorityHashes = PREMIUM_AUTHORITIES,
) -> PremiumTourPlan:
```

Its body opens (`src/tour/premium_tour.py:250-275`):

```python
    policy = planning_policy or certification_planning_policy(policy_id=PREMIUM_MODULE_VERSION)
    routing_version = routing_client.routing_version()
    routes = select_k_routes(
        tour_input,
        snapshot,
        3,
        routing_client=routing_client,
        planning_policy=policy,
    )
    route = choose_discrete_route(routes)
    if (
        not route.pois
        or not route.routed
        or len(route.transits) != len(route.pois)
        or any(transit.valhalla_receipt is None for transit in route.transits)
    ):
        raise PremiumRouteInfeasibleError(
            "Premium planning requires a complete receipt-backed Valhalla route"
        )
    receipt_configs = {
        transit.valhalla_receipt.routing_config_sha256
        for transit in route.transits
        if transit.valhalla_receipt is not None
    }
    if receipt_configs != {VALHALLA_ROUTING_CONFIG_SHA256}:
        raise PremiumRouteInfeasibleError("route receipts use an unexpected routing config")
```

and continues at `src/tour/premium_tour.py:277-355` with the per-route work: the capped
beat plans, the vignette beats, the `BeatSequence`, the `generate(...)` call, the compose
requests, the candidate identity, the authoring plan, the compose units, and the
`PremiumTourPlan(...)` construction.

**One fact the brief does not state and which decides step 7's cost class:** the
`generate(...)` call at `src/tour/premium_tour.py:293-299` passes **no** `glue_client`, and
`generate`'s default is a **real, paid** Haiku client — `src/tour/generation.py:338`:

```python
    client = glue_client if glue_client is not None else HaikuGlueClient()
```

with the owner ruling explaining it at `src/tour/generation.py:328-337`. So Block 1 is not
$0 today, and building three plans instead of one triples that glue spend. This is
resolved below in 7.2 (an explicit parameter, default unchanged) and raised for the owner
in the BLOCKING AMBIGUITY section, because the brief's "BLOCK 1 — PLAN … NO LLM, NO spend"
(`00-brief.md:15-18`) and the live default cannot both be true.

## 7.2 Exact new and changed signatures

### 7.2.1 New: `_premium_route_refusal`

Insert **immediately after** `certification_planning_policy` (i.e. after
`src/tour/premium_tour.py:236`) and before `plan_premium_tour`:

```python
def _premium_route_refusal(route: Route) -> str | None:
    """Why this route cannot be planned as Premium, or None when it can.

    The exact bar ``plan_premium_tour`` enforced inline before the K=3 split. It is a
    predicate rather than a raise so a NON-CHOSEN flavour can be dropped from the
    options tuple while the CHOSEN one still refuses the whole request, which is what
    keeps the single-plan entry point's behaviour identical.
    """

    if (
        not route.pois
        or not route.routed
        or len(route.transits) != len(route.pois)
        or any(transit.valhalla_receipt is None for transit in route.transits)
    ):
        return "Premium planning requires a complete receipt-backed Valhalla route"
    receipt_configs = {
        transit.valhalla_receipt.routing_config_sha256
        for transit in route.transits
        if transit.valhalla_receipt is not None
    }
    if receipt_configs != {VALHALLA_ROUTING_CONFIG_SHA256}:
        return "route receipts use an unexpected routing config"
    return None
```

The two returned strings are **byte-identical** to the two messages raised today at
`src/tour/premium_tour.py:266-268` and `src/tour/premium_tour.py:275`. They are load-bearing:
`tests/test_trip_preview_contract.py:317-318` and `:628-629` assert on substrings of the
422 body that carries `str(exc)`.

### 7.2.2 New: `_plan_one_premium_route`

The whole of today's `src/tour/premium_tour.py:277-355` moves verbatim into this function.
Insert it after `_premium_route_refusal`:

```python
def _plan_one_premium_route(
    tour_input: TourInput,
    snapshot: CorpusSnapshot,
    route: Route,
    *,
    policy: RoutePlanningPolicy,
    routing_version: str,
    generation_time: dt.datetime | None,
    authorities: PremiumAuthorityHashes,
    glue_client: GlueClient | None,
) -> PremiumTourPlan:
```

Body: exactly `src/tour/premium_tour.py:277-355` as it stands, with **one** edit — the
`generate(...)` call gains the forwarded client. Current, `src/tour/premium_tour.py:293-299`:

```python
    source = generate(
        sequence,
        route,
        tour_input,
        now=generation_time or dt.datetime.now(dt.UTC),
        validate_output=False,
    )
```

Replacement:

```python
    source = generate(
        sequence,
        route,
        tour_input,
        glue_client=glue_client,
        now=generation_time or dt.datetime.now(dt.UTC),
        validate_output=False,
    )
```

`generate`'s `glue_client` parameter is `GlueClient | None = None` and `None` selects the
real Haiku client (`src/tour/generation.py:315`, `:338`), so passing `glue_client=None`
is byte-for-byte today's behaviour.

Add the import for the annotation at the top of the module, in isort position among the
existing relative imports (they run `.artifact`, `.authoring`, `.beat_select`,
`.candidate_authoring`, `.certification_provider`, `.contract`, `.generation`,
`.premium_authorities`, … at `src/tour/premium_tour.py:27-75`) — insert between
`.generation` (`:64`) and `.premium_authorities` (`:65`):

```python
from .glue_client import GlueClient
```

`GlueClient` is the Protocol at `src/tour/glue_client.py:41-44`.

### 7.2.3 New public entry point: `plan_premium_options`

Insert after `_plan_one_premium_route`:

```python
def plan_premium_options(
    tour_input: TourInput,
    snapshot: CorpusSnapshot,
    *,
    routing_client: RoutingClient,
    planning_policy: RoutePlanningPolicy | None = None,
    generation_time: dt.datetime | None = None,
    authorities: PremiumAuthorityHashes = PREMIUM_AUTHORITIES,
    glue_client: GlueClient | None = None,
) -> tuple[PremiumTourPlan, ...]:
    """BLOCK 1 — every flavour of one request, planned, with no per-stop authoring.

    Returns one plan per surviving flavour, CHOSEN FIRST. The chosen flavour is exactly
    what ``choose_discrete_route`` picks, so ``plan_premium_options(...)[0]`` is the plan
    ``plan_premium_tour`` has always returned for the same input. A flavour after the
    first that cannot clear the Premium route bar is DROPPED from the tuple; the chosen
    one refuses the whole request, as before.
    """

    policy = planning_policy or certification_planning_policy(policy_id=PREMIUM_MODULE_VERSION)
    routing_version = routing_client.routing_version()
    routes = select_k_routes(
        tour_input,
        snapshot,
        3,
        routing_client=routing_client,
        planning_policy=policy,
    )
    chosen = choose_discrete_route(routes)
    ordered = [chosen, *(
        route
        for route in routes
        if route is not chosen and not route_has_container_identity_stop(route)
    )]
    plans: list[PremiumTourPlan] = []
    for index, route in enumerate(ordered):
        refusal = _premium_route_refusal(route)
        if refusal is not None:
            if index == 0:
                raise PremiumRouteInfeasibleError(refusal)
            continue
        plans.append(
            _plan_one_premium_route(
                tour_input,
                snapshot,
                route,
                policy=policy,
                routing_version=routing_version,
                generation_time=generation_time,
                authorities=authorities,
                glue_client=glue_client,
            )
        )
    return tuple(plans)
```

`route_has_container_identity_stop` is `src/tour/selection.py:582-585` and must be added to
the existing `from .selection import (...)` block at `src/tour/premium_tour.py:68-74`, in
alphabetical position (after `choose_discrete_route`, before `select_k_routes`).

### 7.2.4 Changed: `plan_premium_tour`

Replace the whole of `src/tour/premium_tour.py:239-355` (signature and body) with:

```python
def plan_premium_tour(
    tour_input: TourInput,
    snapshot: CorpusSnapshot,
    *,
    routing_client: RoutingClient,
    planning_policy: RoutePlanningPolicy | None = None,
    generation_time: dt.datetime | None = None,
    authorities: PremiumAuthorityHashes = PREMIUM_AUTHORITIES,
    glue_client: GlueClient | None = None,
) -> PremiumTourPlan:
    """The ONE plan a single-route caller wants: the chosen flavour of Block 1.

    Deliberately a one-line delegate. The selection rule (``choose_discrete_route`` over
    the K=3 flavours) lives in ``plan_premium_options`` and nowhere else, so the batch
    runner and the two API surfaces cannot drift into different definitions of "the"
    route.
    """

    return plan_premium_options(
        tour_input,
        snapshot,
        routing_client=routing_client,
        planning_policy=planning_policy,
        generation_time=generation_time,
        authorities=authorities,
        glue_client=glue_client,
    )[0]
```

The signature is today's plus one keyword-only parameter with a behaviour-preserving
default. Every existing caller keeps working unchanged: `src/api/routes/trips.py:946-950`
and `scripts/tour_batch_candidate.py`'s `_plan_tour` (pinned by
`tests/test_premium_workbench_wiring.py:225-232`).

### 7.2.5 `__all__`

`src/tour/premium_tour.py:709-729` gains one entry, in the existing alphabetical order —
insert `"plan_premium_options",` immediately before `"plan_premium_tour",` (currently
`:725`).

## 7.3 How the contract guarantees bit-for-bit preservation, and how the test proves it

Three properties, each mechanical:

1. **Same route chosen.** `plan_premium_options` calls `choose_discrete_route(routes)` on
   the same `routes` list produced by the same `select_k_routes(...)` call with the same
   policy. `choose_discrete_route` (`src/tour/selection.py:588-594`) returns the first
   route with no container-identity stop. `ordered[0]` is literally that object, and the
   filter on the tail uses `route is not chosen` (object identity), so the chosen route
   can never appear twice nor be displaced.
2. **Same plan built from it.** `_plan_one_premium_route` is the moved body, unchanged
   except for the forwarded `glue_client`, which defaults to `None` = today's client.
3. **Same failures.** `_premium_route_refusal` returns the two exact message strings, and
   index 0 raises `PremiumRouteInfeasibleError` with them. `choose_discrete_route`'s own
   `ValueError("bounded candidates contain no route with all-discrete stops")` is raised
   by the unchanged call, before any plan is built. `TourabilityRefusedError` and
   `CertificationPlanningInfeasibleError` still escape from `select_k_routes` untouched,
   which is what keeps `tests/test_trip_preview_contract.py:270-319` and `:539-629` green.

The proving test pins property 1 and 2 *jointly* by asserting that
`plan_premium_tour(...)` and `plan_premium_options(...)[0]` produce the same
`route_record["route_sha256"]` and the same `candidate.model_dump(mode="json")` on the
same input — a hash over the full route model dump plus the candidate identity, which
binds the ordered POI set, every leg, and the grounded source.

## 7.4 The proving test

**File:** `tests/test_premium_workbench_wiring.py`
**Name:** `test_block_one_returns_three_priced_free_plans`

Add these imports at the top of that file (it currently imports only stdlib plus
`scripts.tour_batch_candidate` and `src.api.routes.trips`, `tests/test_premium_workbench_wiring.py:5-14`):

```python
import pytest

from src.tour import premium_tour
from src.tour.contract import POI, BeatRef, Route, TransitSegment
from src.tour.premium_tour import plan_premium_options, plan_premium_tour
from tests.test_tour_selection import _poi, _snap
from tests.test_trip_preview_contract import _FakeRoutingClient
```

(Importing fixtures across test modules is the established pattern here —
`tests/test_tour_flavours.py:40` does exactly this.)

### Stubs the test builds, named, with their data shape

1. **`_receipted_transit(from_id, to_id, from_lat, from_lng, to_lat, to_lng)`** — a module-level
   helper in the test file that returns a `TransitSegment` carrying a REAL, self-consistent
   `ValhallaLegReceipt`, by delegating to the existing fake:

   ```python
   def _receipted_transit(from_id, to_id, a_lat, a_lng, b_lat, b_lng) -> TransitSegment:
       seconds, distance_m, polyline, receipt = _FakeRoutingClient().route_with_receipt(
           a_lat, a_lng, b_lat, b_lng
       )
       return TransitSegment(
           from_poi_id=from_id,
           to_poi_id=to_id,
           distance_m=distance_m,
           walk_seconds=seconds,
           leg_seconds=seconds,
           leg_distance_m=distance_m,
           polyline=polyline,
           source="valhalla",
           valhalla_receipt=receipt,
       )
   ```

   `_FakeRoutingClient.route_with_receipt` is `tests/test_trip_preview_contract.py:142-185`;
   it builds a receipt whose hashes and canonical JSON validate against
   `ValhallaLegReceipt`'s model validator (`src/tour/contract.py:247-298`), and whose
   `routing_config_sha256` is the real `VALHALLA_ROUTING_CONFIG_SHA256`, so
   `_premium_route_refusal` returns None for it.

2. **Three hand-built `Route`s.** Nine POIs, three per route, disjoint stop sets, built
   with `_poi` from `tests/test_tour_selection.py`:

   ```python
   _BASE = (48.8568, 2.3414)

   def _three_routes():
       routes = []
       for f in range(3):
           pois = tuple(
               _poi(f"f{f}-p{i}", lat=_BASE[0] + 0.0006 * (f + 1), lng=_BASE[1] + 0.0008 * (i + 1))
               for i in range(3)
           )
           prev = _BASE
           transits = []
           for poi in pois:
               transits.append(
                   _receipted_transit(None, poi.id, prev[0], prev[1], poi.lat, poi.lng)
               )
               prev = (poi.lat, poi.lng)
           routes.append(
               Route(
                   pois=pois,
                   transits=tuple(transits),
                   total_walk_distance_m=sum(t.distance_m for t in transits),
                   total_walk_seconds=sum(t.walk_seconds for t in transits),
                   routed=True,
               )
           )
       return routes
   ```

   `routed=True` is required because `_premium_route_refusal` reads it, and hand-built
   `Route`s default it to `False` (`src/tour/contract.py:433`). `len(transits) == len(pois)`
   satisfies the transit-count arm. None of the nine POI names is one of its own areas
   (`_poi` sets `areas=()` unless told otherwise), so `choose_discrete_route` returns
   `routes[0]`.

3. **A snapshot** covering all nine POIs, each with three beats carrying a `script_body`
   so `generate` has something to voice and `_certification_compose_requests` produces one
   request per stop:

   ```python
   def _snapshot_for(routes):
       pois = [p for route in routes for p in route.pois]
       return _snap(
           pois,
           beats_by_poi={
               p.id: [
                   BeatRef(
                       id=f"{p.id}-b{i}",
                       poi_id=p.id,
                       est_spoken_seconds=120,
                       active_status="active",
                       script_body=f"Story {i} at {p.name}. It runs on a little.",
                   )
                   for i in range(3)
               ]
               for p in pois
           },
       )
   ```

4. **`_StubGlue`** — a glue client that records its calls and never touches a network:

   ```python
   class _StubGlue:
       def __init__(self) -> None:
           self.calls: list[tuple[str, str, str]] = []

       def stitch(self, category: str, context: str, request: str) -> str:
           self.calls.append((category, context, request))
           return "NO_GLUE"
   ```

   It satisfies the `GlueClient` protocol (`src/tour/glue_client.py:41-44`).

5. **`_poisoned_haiku`** — proves no real provider is constructed:
   `monkeypatch.setattr("src.tour.generation.HaikuGlueClient", _Poison)` where `_Poison.__init__`
   raises `AssertionError("Block 1 constructed a paid glue client")`.

6. **`_poisoned_executor`** — proves the compose provider is never reached:
   `monkeypatch.setattr("src.tour.premium_tour.AnthropicPremiumExecutor", _Poison)`.
   Planning never takes an executor, so this is a belt-and-braces assertion for AC-2.

7. **`fake_select_k_routes`** — monkeypatched onto the module under test so the test
   is hermetic and does not depend on the selector reaching three certification-feasible
   flavours on a synthetic corpus:

   ```python
   monkeypatch.setattr(premium_tour, "select_k_routes", lambda *a, **k: list(routes))
   ```

   `select_k_routes` is bound into `premium_tour`'s namespace at
   `src/tour/premium_tour.py:68-74`, so patching the module attribute is what the code
   under test resolves.

### Assertions, in order

```python
def test_block_one_returns_three_priced_free_plans(monkeypatch) -> None:
    routes = _three_routes()
    snapshot = _snapshot_for(routes)
    tour_input = TourInput(start=_BASE, duration_min=60, city_slug="paris")
    monkeypatch.setattr(premium_tour, "select_k_routes", lambda *a, **k: list(routes))
    monkeypatch.setattr("src.tour.generation.HaikuGlueClient", _Poison)
    monkeypatch.setattr(premium_tour, "AnthropicPremiumExecutor", _Poison)
    glue = _StubGlue()

    plans = plan_premium_options(
        tour_input,
        snapshot,
        routing_client=_FakeRoutingClient(),
        glue_client=glue,
    )

    # 1. THREE plans, one per flavour.
    assert len(plans) == 3

    # 2. They are the three DISTINCT flavours, in the order the selector produced them,
    #    chosen first.
    assert [[p.id for p in plan.route.pois] for plan in plans] == [
        [p.id for p in route.pois] for route in routes
    ]

    # 3. Every plan is a complete, authorable plan — one compose unit per dwell stop.
    for plan in plans:
        assert len(plan.units) == len(plan.route.pois)
        assert plan.policy_version == PREMIUM_MODULE_VERSION

    # 4. NOTHING was authored and no paid client was constructed. The stub glue is the
    #    only narration client that ran.
    assert glue.calls, "the stub glue client must be the one that was used"

    # 5. THE PRESERVATION PIN: the single-plan entry point returns exactly plans[0].
    single = plan_premium_tour(
        tour_input,
        snapshot,
        routing_client=_FakeRoutingClient(),
        glue_client=glue,
    )
    assert single.route_record["route_sha256"] == plans[0].route_record["route_sha256"]
    assert single.candidate.model_dump(mode="json") == plans[0].candidate.model_dump(mode="json")
    assert [u.stop_index for u in single.units] == [u.stop_index for u in plans[0].units]

    # 6. AC-23: start with no end plans without a 4xx-shaped failure.
    assert tour_input.end is None
```

`PREMIUM_MODULE_VERSION` and `TourInput` must be imported in the test file alongside the
rest.

### THE MUTATION

The one-line production edit that must turn this test RED:

> In `plan_premium_options`, change
> `ordered = [chosen, *(...)]`
> to
> `ordered = [chosen]`

With that edit the loop plans one route, `len(plans) == 3` fails at assertion 1, and
assertion 2 fails too. The test therefore cannot pass without the fan-out actually
existing.

A second, independent mutation for the preservation half: change
`return plan_premium_options(...)[0]` in `plan_premium_tour` to `[-1]`. Assertion 5 goes
RED while assertions 1–4 stay green, so the preservation pin is not a passenger of the
fan-out pin.

---

# STEP 8 — Fold the preview interleave into the shared options builder

**Ledger:** id `8`, files `src/tour/options.py`, `src/tour/contract.py`,
`src/api/routes/trips.py`, `tests/test_tour_flavours.py`, `tests/test_trip_preview_vignettes.py`.
**Proving test:** `tests/test_tour_flavours.py::test_build_route_option_carries_the_leg_and_vignette_narration_cards`.
**Gate:** `make lint`.
**Criteria:** AC-17, AC-30.

**BRIEF DRIFT:** the brief says `_preview_stops` is at `trips.py:734`, called at `975` and
`1113` (`00-brief.md:113-117`). All three still hold exactly. It also says
`build_route_option` is `src/tour/options.py:51` called only at `trips.py:451-460` — both
still hold.

## 8.1 The two structures being merged

- `_preview_stops` — `src/api/routes/trips.py:734-867`. Produces `list[TripPreviewStop]`.
- `build_route_option` — `src/tour/options.py:51-123`, with helpers `_build_stop`
  (`:126-161`), `_vignette_stop` (`:164-188`), `_lens_coverage_note` (`:191-215`).
  Produces one `RouteOption` of `RouteOptionStop`s.

## 8.2 Exact field lists

### 8.2.1 `RouteOptionStop` — before

`src/tour/contract.py:545-561`, verbatim:

| field | type | default |
| --- | --- | --- |
| `poi_id` | `str` | required |
| `name` | `str` | required |
| `lat` | `float` | required |
| `lng` | `float` | required |
| `lens` | `str \| None` | `None` |
| `visit_or_walk_past` | `Literal["visit", "walk_past"]` | `"visit"` |
| `minutes` | `int` (`ge=0`) | `0` |
| `band` | `Literal["dwell", "vignette"]` | `"dwell"` |
| `spotlight` | `float` (`ge=0`) | `0.0` |

### 8.2.2 `RouteOptionStop` — after

Two new fields, one widened `Literal`. Nothing is removed and nothing changes type.

| field | type | default | where the value comes from |
| --- | --- | --- | --- |
| `poi_id` | `str` | required | unchanged for dwell/vignette. For a **leg** card: the poi id of the stop the walk ARRIVES at (`sp.id`), matching the lat/lng `_preview_stops` already used at `trips.py:831-832`. |
| `name` | `str` | required | unchanged for dwell/vignette. For a **leg** card: `f"Walk to {sp.name}"` — `trips.py:830`. |
| `lat` | `float` | required | leg card: `sp.lat` — `trips.py:831`. |
| `lng` | `float` | required | leg card: `sp.lng` — `trips.py:832`. |
| `lens` | `str \| None` | `None` | unchanged. Leg card: `None`. |
| `visit_or_walk_past` | `Literal["visit","walk_past"]` | `"visit"` | unchanged. Leg card: `"walk_past"`. |
| `minutes` | `int` (`ge=0`) | `0` | unchanged for dwell/vignette. Leg card: `round(_leg_walk_s.get(i, 0) / 60)` — `trips.py:834`, fed by `trips.py:799-801`. |
| `band` | `Literal["dwell", "vignette", "leg"]` | `"dwell"` | **widened.** `"leg"` from `trips.py:835`. |
| `spotlight` | `float` (`ge=0`) | `0.0` | unchanged for dwell/vignette (`options.py:160`, `:187`). Leg card: `0.0` — `trips.py:836`. |
| **`narration`** | `str` | `""` | **new.** dwell: `per_stop.get(i, "")` — `trips.py:860`, built at `trips.py:794`. vignette: `one_liner_by_poi[poi.id]` — `trips.py:848`, built at `trips.py:813-818`. leg: `leg_text` — `trips.py:833`, built at `trips.py:795`+`:825`. |
| **`has_deeper_dive`** | `bool` | `False` | **new.** dwell: `bool(overflow_by_poi.get(sp.id))` — `trips.py:864`. vignette and leg: always `False` — `trips.py:849-852` and `:827-837` never set it. |

Exact replacement for `src/tour/contract.py:545-561`:

```python
class RouteOptionStop(BaseModel):
    """One ordered card inside a RouteOption (§2.8).

    THREE bands, and a card is exactly one of them:
    - ``dwell`` — a stop the tourist stands at. ``minutes`` is its dwell time.
    - ``vignette`` — a walk-past one-liner. ``minutes`` is always 0.
    - ``leg`` — narration spoken WHILE WALKING into the next dwell stop (product
      ruling 2026-07-19: "Audio overlaps the walking. It is a part of the tour
      experience."). ``minutes`` is the WALK's duration, so a six-minute walk sits
      next to seven seconds of narration and the gap is visible rather than averaged
      away. Its ``poi_id``/``lat``/``lng`` are the ARRIVAL stop's, and its ``name``
      reads "Walk to <that stop>". A consumer matching POI ids must therefore filter
      to ``band == "dwell"``; a leg card deliberately repeats its arrival stop's id
      rather than inventing one.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    poi_id: str
    name: str
    lat: float
    lng: float
    lens: str | None = None  # dominant lens of the stop's beats; None if unlensed
    visit_or_walk_past: Literal["visit", "walk_past"] = "visit"
    minutes: int = Field(default=0, ge=0)
    band: Literal["dwell", "vignette", "leg"] = "dwell"
    spotlight: float = Field(default=0.0, ge=0)
    # The text this card voices. Empty only for a dwell stop whose stop_idx carried no
    # stationary sentence. A leg card is NEVER emitted with empty narration, and a
    # vignette card is never emitted without a voiceable one-liner.
    narration: str = ""
    # KE9: this dwell stop has "keep exploring here" extras — beats the time budget
    # capped out. Always False on vignette and leg cards.
    has_deeper_dive: bool = False
```

`RouteOption` (`src/tour/contract.py:564-591`) is **unchanged**.

The mobile client is safe: `RouteOptionStop.fromJson` parses `band` as a plain `String`
with a `'dwell'` fallback (`mobile/lib/models/trip.dart:145-152`), and `_FlavourTile`
counts `option.stops.where((s) => s.band == 'dwell')`
(`mobile/lib/pages/trip_itinerary_page.dart:561-562`), so leg cards neither crash the
parser nor inflate the stop count.

## 8.3 Exact signature change: `build_route_option`

Current, `src/tour/options.py:51-58`:

```python
def build_route_option(
    route: Route,
    script: Script,
    beats_by_id: dict[str, BeatRef],
    *,
    route_id: str,
    snapshot: CorpusSnapshot,
) -> RouteOption:
```

Replacement:

```python
def build_route_option(
    route: Route,
    script: Script,
    beats_by_id: dict[str, BeatRef],
    *,
    route_id: str,
    snapshot: CorpusSnapshot,
    sequence: BeatSequence,
) -> RouteOption:
```

`sequence` is **required**, keyword-only, with **no default**, for the same reason
`finalize_premium_tour`'s `faithfulness_checker` has none
(`src/tour/premium_tour.py:636-642`): an optional narration source is exactly how a caller
silently gets a card list with no narration and nobody notices. Its two consumed members:

- `sequence.vignette_beats` — `dict[int, tuple[BeatRef, ...]]`, `src/tour/contract.py:479`.
  Supplies the chosen vignette beat per leg, which is what `_preview_stops` received as its
  third positional argument (`trips.py:735`, fed from `seq.vignette_beats` at `trips.py:970`).
- `sequence.overflow_by_poi` — `dict[str, tuple[str, ...]]`, `src/tour/contract.py:485`.
  Supplies the deeper-dive flag, which is what `_preview_stops` received as its fifth
  positional argument (`trips.py:735`, fed from `dict(seq.overflow_by_poi)` at `trips.py:971`).

Add to the import at `src/tour/options.py:19`:

```python
from .contract import POI, BeatRef, BeatSequence, Route, RouteOption, RouteOptionStop, Script
```

and two more imports at module scope (both are already imported *inside* `_preview_stops`
at `trips.py:750-751`; hoisting them to module scope in `options.py` is required because
`options.py` has no function-local import convention):

```python
from src.audio.tts_normalize import normalize_dashes_for_reading

from .generation import is_walk_concurrent, vignette_one_liner_text
```

Import-cycle check: `src/tour/generation.py` imports from `.contract`, `.beat_select`,
`.validation`, `.glue_client`, `.reflection`, `.routing` — it does **not** import
`.options`, and `.options` is imported today only by `src/api/routes/trips.py:59` and the
tests. `src/audio/tts_normalize.py` imports nothing from `src/tour`. No cycle.

## 8.4 THE FIELD-BY-FIELD EQUIVALENCE TABLE

Every behaviour `_preview_stops` has that `build_route_option` lacks, with the exact source
lines and the exact target location in the merged function. **Seventeen rows.** A missed row
here is a silent user-visible regression.

| # | Behaviour | Source (`src/api/routes/trips.py`) | Target in merged `build_route_option` |
| --- | --- | --- | --- |
| B1 | Split each stop's sentences into walk-concurrent (leg) and stationary (dwell) using the shared `is_walk_concurrent` predicate | `:783-791` | New block immediately after `lenses_fs = frozenset(...)` (`options.py:85`), before `dwell_stops` is built |
| B2 | Suppress a sentence sourced from a vignette beat from BOTH buckets — it is voiced by its own card (the "bleed" fix) | `:758`, `:786-787` | Same new block; `vignette_beat_ids = {b.id for beats in sequence.vignette_beats.values() for b in beats}` |
| B3 | Join each bucket and display-normalise dashes so the printed text matches the audio | `:794-795` | Same new block, producing `per_stop: dict[int, str]` and `per_leg: dict[int, str]` |
| B4 | Per-leg walk seconds, routed when present else the haversine fallback | `:799-801` | Same new block, producing `leg_walk_seconds: dict[int, int]` |
| B5 | Vignette one-liner text via the SHARED `vignette_one_liner_text` helper, so the card never diverges from what the tourist hears | `:802-818` | Same new block, producing `one_liner_by_poi: dict[str, str]` |
| B6 | The POI-name map that the one-liner's clause cap needs covers BOTH seated `route.pois` and walk-past `route.vignettes` POIs | `:809-812` | Same block, verbatim |
| B7 | The one-liner is dash-normalised too | `:818` | Same block, verbatim |
| B8 | A leg card is emitted ONLY when its text is non-empty — an empty card would imply content that does not exist | `:825-826` | Inside the interleave loop, before the vignette emission |
| B9 | The leg card precedes the vignettes and the dwell stop of the same index | `:825-853` ordering | Interleave loop order becomes: **leg → vignettes → dwell**. `build_route_option` today is vignettes → dwell (`options.py:98-103`) |
| B10 | Leg card fields: `name="Walk to {sp.name}"`, `lat/lng` = arrival stop's, `band="leg"`, `spotlight=0.0`, `minutes=round(walk_s/60)` | `:828-837` | New `_leg_stop(...)` helper in `options.py` |
| B11 | A vignette POI with no voiceable beat is DROPPED — what is not voiced is not shown | `:840-841` | `_vignette_stop` gains the one-liner argument; the loop skips a POI absent from `one_liner_by_poi` |
| B12 | Vignette card narration is the one-liner | `:848` | `_vignette_stop`'s `narration=` |
| B13 | Dwell card narration is the stationary bucket, defaulting to `""` | `:860` | `_build_stop`'s `narration=` |
| B14 | Dwell `has_deeper_dive` from a non-empty overflow entry | `:864` | `_build_stop`'s `has_deeper_dive=bool(sequence.overflow_by_poi.get(sp.id))` |
| B15 | Vignette and leg cards never carry `has_deeper_dive` | `:842-853`, `:827-838` (field never set → model default `False`) | Field left at its `False` default in `_vignette_stop` and `_leg_stop` |
| B16 | `sort_order` is a 1-based running counter over the EMITTED cards, not over dwell stops | `:829`, `:845`, `:856` (`len(out) + 1`) | NOT a `RouteOptionStop` field. Computed by the API adapter in 8.6 as `enumerate(option.stops, start=1)`, which is the identical sequence because both count emitted cards |
| B17 | Vignette spotlight passes `lenses_fs or None`, `build_route_option` passes `lenses_fs` | `:851` vs `options.py:187` | **No change needed.** `lens_relevance` opens with `interest = lenses or frozenset()` (`src/tour/selection.py:3351`), so an empty frozenset and `None` are the same input. Keep `options.py`'s form |

### Two places where the merged function is a deliberate SUPERSET of `_preview_stops`

Both are stated here so the implementer does not "fix" them back:

- **S1 — closing-leg vignettes.** `_preview_stops` iterates `for i, sp in enumerate(script.selected_pois)`
  (`trips.py:821`) and therefore can never emit a vignette on the closing leg (index
  `len(stops)`). `build_route_option` does (`options.py:104-107`), and
  `tests/test_tour_flavours.py:541-559` pins it. The merged function keeps
  `build_route_option`'s behaviour, gated by B11 (only if voiceable). The preview gains a
  card for a walk-past the audio already voices.
- **S2 — real spotlight on dwell cards.** `_preview_stops` hard-codes `spotlight=0.0` for
  dwell stops (`trips.py:863`). `build_route_option` computes the real score
  (`options.py:143-149`, `:160`). The merged function keeps the computed score, so the
  preview wire gains a non-zero dwell spotlight — the value `/trips/generate` has always
  carried. No test asserts `spotlight == 0` for a preview dwell stop;
  `tests/test_trip_preview_vignettes.py:88` only asserts `> 0` on the vignette.

### The output-type mapping: `RouteOptionStop` → `TripPreviewStop`, field by field

`TripPreviewStop` is `src/api/models/trips.py:256-287`. It is **unchanged** by this step.

| `TripPreviewStop` field | value |
| --- | --- |
| `sort_order: int` | `index + 1` over the emitted cards (B16) |
| `poi_name: str` | `stop.name` |
| `lat: float` | `stop.lat` |
| `lng: float` | `stop.lng` |
| `narration: str` | `stop.narration` |
| `minutes: int` | `stop.minutes` |
| `band: Literal["dwell","vignette","leg"]` | `stop.band` — the two Literals are now identical sets |
| `spotlight: float` | `stop.spotlight` |
| `has_deeper_dive: bool` | `stop.has_deeper_dive` |

`RouteOptionStop.poi_id`, `.lens` and `.visit_or_walk_past` have no `TripPreviewStop`
counterpart and are dropped by the adapter, exactly as today (the preview never carried
them).

## 8.5 The merged `src/tour/options.py`

Replace `src/tour/options.py:51-188` (`build_route_option`, `_build_stop`, `_vignette_stop`)
with the following. `dominant_lens` (`:32-48`) and `_lens_coverage_note` (`:191-215`) are
untouched.

```python
def build_route_option(
    route: Route,
    script: Script,
    beats_by_id: dict[str, BeatRef],
    *,
    route_id: str,
    snapshot: CorpusSnapshot,
    sequence: BeatSequence,
) -> RouteOption:
    """Assemble one flavour's RouteOption from its Route + Script + BeatSequence.

    THE ONE INTERLEAVE. This absorbed the fourth copy that lived in the API layer as
    ``trips._preview_stops`` (deleted 2026-08-04): the preview and the flavour cards
    were two implementations of the same ordering, and they had already drifted — the
    preview split walk-concurrent narration onto its own card and the option builder
    did not, so the workbench and the phone disagreed about what a "stop" is.

    THREE KINDS OF CARD, in walking order:
      leg      — what the tourist hears WHILE WALKING into the next dwell stop. Emitted
                 only when the walk actually carries narration; an empty card would
                 imply content that does not exist. ``minutes`` is the WALK.
      vignette — a walk-past one-liner on that leg, voiced through the SAME helper the
                 audio path uses, so the printed line and the spoken line cannot drift.
                 A vignette POI with no voiceable beat is not shown, because it is not
                 heard either.
      dwell    — the stop itself, with the stationary narration and the deeper-dive flag.

    eta_seconds is unchanged and still counts routed legs (or the pace-corrected
    haversine) plus every dwell: a vignette or leg card costs no elapsed time.
    """
    require_materialized_snapshot(snapshot, operation="route-option assembly")
    roles = {p.id: p.poi_role for p in route.pois}
    pois_by_id: dict[str, POI] = {p.id: p for p in route.pois}
    lenses_fs = frozenset(script.inputs.lenses or ())

    # --- narration, split the way the tourist experiences it -------------------
    # A vignette's line is voiced by its OWN card below, so it is stripped from the
    # dwell card it was folded into (_build_transit emits it at the ARRIVAL stop's
    # stop_idx). ``is_walk_concurrent`` is the SHARED predicate quality_rubric's time
    # model uses, so a sentence shown on a leg card is exactly a sentence the rubric
    # scored as costing no elapsed time.
    vignette_beat_ids = {b.id for beats in sequence.vignette_beats.values() for b in beats}
    dwell_sents: dict[int, list[str]] = {}
    leg_sents: dict[int, list[str]] = {}
    for sentence in script.script:
        if sentence.source_type == "beat" and sentence.source_id in vignette_beat_ids:
            continue
        bucket = leg_sents if is_walk_concurrent(sentence, vignette_beat_ids) else dwell_sents
        bucket.setdefault(sentence.stop_idx, []).append(sentence.text)
    # Display-normalize dashes so the text READS the way the audio SOUNDS (a comma
    # pause, not a dangling stroke).
    per_stop = {idx: normalize_dashes_for_reading(" ".join(t)) for idx, t in dwell_sents.items()}
    per_leg = {idx: normalize_dashes_for_reading(" ".join(t)) for idx, t in leg_sents.items()}
    leg_walk_seconds = {
        i: int(t.leg_seconds if t.leg_seconds is not None else t.walk_seconds)
        for i, t in enumerate(route.transits)
    }
    # The clause cap inside vignette_one_liner_text keeps the POI's own name in a
    # shortened line, and vignette POIs are walk-past (route.vignettes), NOT seated
    # route.pois — so the name map must cover both or the cap falls back to the run-on.
    poi_name_by_id = {p.id: p.name for p in route.pois}
    for vignette_pois in route.vignettes.values():
        for vignette_poi in vignette_pois:
            poi_name_by_id.setdefault(vignette_poi.id, vignette_poi.name)
    one_liner_by_poi: dict[str, str] = {}
    for beats in sequence.vignette_beats.values():
        for beat in beats:
            text = vignette_one_liner_text(beat.script_body, poi_name_by_id.get(beat.poi_id, ""))
            if text:
                one_liner_by_poi[beat.poi_id] = normalize_dashes_for_reading(text)

    # --- the interleave --------------------------------------------------------
    interleaved: list[RouteOptionStop] = []
    for i, sp in enumerate(script.selected_pois):
        leg_text = per_leg.get(i, "").strip()
        if leg_text:
            interleaved.append(
                _leg_stop(sp, narration=leg_text, walk_seconds=leg_walk_seconds.get(i, 0))
            )
        interleaved.extend(
            _vignette_stop(
                vp,
                lenses=lenses_fs,
                snapshot=snapshot,
                narration=one_liner_by_poi[vp.id],
            )
            for vp in route.vignettes.get(i, ())
            if vp.id in one_liner_by_poi
        )
        interleaved.append(
            _build_stop(
                sp,
                poi=pois_by_id.get(sp.id),
                role=roles.get(sp.id, "stop"),
                beats_by_id=beats_by_id,
                lenses=lenses_fs,
                snapshot=snapshot,
                narration=per_stop.get(i, ""),
                has_deeper_dive=bool(sequence.overflow_by_poi.get(sp.id)),
            )
        )
    interleaved.extend(
        _vignette_stop(
            vp,
            lenses=lenses_fs,
            snapshot=snapshot,
            narration=one_liner_by_poi[vp.id],
        )
        for vp in route.vignettes.get(len(script.selected_pois), ())
        if vp.id in one_liner_by_poi
    )
    stops = tuple(interleaved)
    eta_seconds = sum(
        (t.leg_seconds if t.leg_seconds is not None else t.walk_seconds) for t in route.transits
    ) + sum(sp.dwell_seconds for sp in script.selected_pois)

    return RouteOption(
        route_id=route_id,
        stops=stops,
        route_polyline=route.route_polyline,
        eta_seconds=eta_seconds,
        lens_summary=dict(script.lens_coverage),
        flow_score=route.flow_score,
        backtrack_ratio=route.backtrack_ratio,
        degraded=route.reach.degraded if route.reach is not None else False,
        lens_coverage_note=_lens_coverage_note(route.pois, lenses=lenses_fs, snapshot=snapshot),
    )
```

Note the closing-leg key changed from `route.vignettes.get(len(dwell_stops), ())`
(`options.py:106`) to `route.vignettes.get(len(script.selected_pois), ())`. These are the
same number — `dwell_stops` was built one-per-`script.selected_pois` (`options.py:86-96`) —
but the list no longer exists as a separate variable.

The three stop helpers:

```python
def _build_stop(
    sp,
    *,
    poi: POI | None,
    role: str,
    beats_by_id: dict[str, BeatRef],
    lenses: frozenset[str],
    snapshot: CorpusSnapshot,
    narration: str,
    has_deeper_dive: bool,
) -> RouteOptionStop:
```

Body: exactly `src/tour/options.py:142-161` with two extra keyword arguments on the
`RouteOptionStop(...)` construction:

```python
        narration=narration,
        has_deeper_dive=has_deeper_dive,
```

```python
def _vignette_stop(
    poi: POI,
    *,
    lenses: frozenset[str],
    snapshot: CorpusSnapshot,
    narration: str,
) -> RouteOptionStop:
```

Body: exactly `src/tour/options.py:177-188` plus `narration=narration,` on the
construction. `has_deeper_dive` is left at its `False` default (B15).

```python
def _leg_stop(sp, *, narration: str, walk_seconds: int) -> RouteOptionStop:
    """The walk INTO ``sp``, as its own card.

    Product ruling 2026-07-19: "Audio overlaps the walking. It is a part of the tour
    experience." ``minutes`` is the WALK's duration, not the narration's, so a
    six-minute walk carrying seven seconds of narration shows the gap instead of
    averaging it away. The card borrows the arrival stop's identity and coordinates
    rather than inventing a POI id.
    """
    return RouteOptionStop(
        poi_id=sp.id,
        name=f"Walk to {sp.name}",
        lat=sp.lat,
        lng=sp.lng,
        lens=None,
        visit_or_walk_past="walk_past",
        minutes=round(walk_seconds / 60),
        band="leg",
        spotlight=0.0,
        narration=narration,
    )
```

## 8.6 Exact call-site rewrites in `src/api/routes/trips.py`

### 8.6.1 Delete `_preview_stops` entirely

Delete `src/api/routes/trips.py:734-867` (the whole function, including its docstring and
its two function-local imports at `:750-751`). Nothing else references it inside the module;
the only other reference in the repository is `tests/test_trip_preview_vignettes.py:7`,
rewritten in 8.7.

### 8.6.2 Add the wire adapter

Insert in its place (same position in the file, so `_tourability_payload` at `:870` still
follows it):

```python
def _preview_cards(option: RouteOption) -> list[TripPreviewStop]:
    """The shared option's cards on the preview wire, one for one.

    THE INTERLEAVE ITSELF IS NOT HERE. It is ``src/tour/options.build_route_option``,
    the one implementation both surfaces use; this only renames the fields the preview
    model spells differently and numbers the cards. ``sort_order`` counts EMITTED cards
    (leg, vignette and dwell alike), which is what the workbench renders in order.
    """
    return [
        TripPreviewStop(
            sort_order=index,
            poi_name=stop.name,
            lat=stop.lat,
            lng=stop.lng,
            narration=stop.narration,
            minutes=stop.minutes,
            band=stop.band,
            spotlight=stop.spotlight,
            has_deeper_dive=stop.has_deeper_dive,
        )
        for index, stop in enumerate(option.stops, start=1)
    ]
```

Add `RouteOption` to the `src.tour.contract` import block at `src/api/routes/trips.py:49-54`,
in alphabetical order (after `Route`).

### 8.6.3 Call site 1 — the Basic-tour fallback

Current, `src/api/routes/trips.py:974-975`:

```python
    def _basic_tour_fallback(*, reason: str, rejection: CandidateRejection) -> TripPreviewResponse:
        basic_stops = _preview_stops(basic_script, route, vignette_beats, snapshot, overflow_by_poi)
```

Replacement:

```python
    def _basic_tour_fallback(*, reason: str, rejection: CandidateRejection) -> TripPreviewResponse:
        basic_stops = _preview_cards(
            build_route_option(
                route,
                basic_script,
                beats_by_id,
                route_id="preview-opt1",
                snapshot=snapshot,
                sequence=seq,
            )
        )
```

This requires `beats_by_id` to exist before the closure is defined. Insert it into the
block at `src/api/routes/trips.py:967-972`, which currently reads:

```python
    route = premium_plan.route
    seq = premium_plan.sequence
    basic_script = premium_plan.source
    vignette_beats = seq.vignette_beats
    overflow_by_poi = dict(seq.overflow_by_poi)
    provider = premium_executor.provider_name
```

Replacement:

```python
    route = premium_plan.route
    seq = premium_plan.sequence
    basic_script = premium_plan.source
    beats_by_id = {ref.id: ref for refs in snapshot.beats_by_poi.values() for ref in refs}
    provider = premium_executor.provider_name
```

`vignette_beats` and `overflow_by_poi` were used ONLY as `_preview_stops` arguments (at
`:975` and `:1113`) and are now read from `seq` inside `build_route_option`; leaving them
would be dead locals and `make lint` (F841 is not in the enabled rule set, but the unused
assignment is still scaffolding) — delete both lines. Verify with
`grep -n "vignette_beats\|overflow_by_poi" src/api/routes/trips.py` after the edit: the
only surviving hits must be in `generate_trip` (`:352-360`) and `compose_trip`
(`:599-604`), which build their own.

The `beats_by_id` expression is the exact one already used twice in this module
(`src/api/routes/trips.py:368` and `:675`).

### 8.6.4 Call site 2 — the composed preview

Current, `src/api/routes/trips.py:1113`:

```python
    stops = _preview_stops(script, route, vignette_beats, snapshot, overflow_by_poi)
```

Replacement:

```python
    stops = _preview_cards(
        build_route_option(
            route,
            script,
            beats_by_id,
            route_id="preview-opt1",
            snapshot=snapshot,
            sequence=seq,
        )
    )
```

`script` here is `premium_result.blueprint.script` (`:1082`). Its `selected_pois` — and
therefore `overflow_beat_ids` — survive composition, because
`finalize_certification_composition` builds the composed Script with
`stitched.model_copy(update={"script": ..., "total_audio_seconds": ..., "validation": ...})`
(`src/tour/authoring.py:656-662`), leaving `selected_pois` untouched. `seq` is the same
`BeatSequence` the plan was built from, so `sequence.overflow_by_poi` matches that script
exactly.

### 8.6.5 Call site 3 — `/trips/generate`'s option list

Current, `src/api/routes/trips.py:344-366`:

```python
    scripts = []
    for flavour in flavours:
        # C9 governor v4 seam: caps a dominating stop, overflow -> keep-exploring.
        capped = build_poi_beat_plans_capped(
            flavour, snapshot, lenses=lenses, end_is_none=tour_input.end is None
        )
        plans = tuple(pb for pb, _ in capped)
        overflow_by_poi = {pb.poi_id: ov for pb, ov in capped if ov}
        vignette_beats = select_vignette_beats(
            flavour.vignettes, snapshot.beats_by_poi, lenses=lenses
        )
        scripts.append(
            generate(
                BeatSequence(
                    poi_beats=tuple(plans),
                    vignette_beats=vignette_beats,
                    overflow_by_poi=overflow_by_poi,
                ),
                flavour,
                tour_input,
            )
        )
    script = scripts[0]
```

Replacement (the `BeatSequence` is retained rather than discarded):

```python
    scripts = []
    sequences = []
    for flavour in flavours:
        # C9 governor v4 seam: caps a dominating stop, overflow -> keep-exploring.
        capped = build_poi_beat_plans_capped(
            flavour, snapshot, lenses=lenses, end_is_none=tour_input.end is None
        )
        plans = tuple(pb for pb, _ in capped)
        overflow_by_poi = {pb.poi_id: ov for pb, ov in capped if ov}
        vignette_beats = select_vignette_beats(
            flavour.vignettes, snapshot.beats_by_poi, lenses=lenses
        )
        sequence = BeatSequence(
            poi_beats=tuple(plans),
            vignette_beats=vignette_beats,
            overflow_by_poi=overflow_by_poi,
        )
        sequences.append(sequence)
        scripts.append(generate(sequence, flavour, tour_input))
    script = scripts[0]
```

Current, `src/api/routes/trips.py:451-460`:

```python
    options = [
        build_route_option(
            flavour,
            fl_script,
            beats_by_id,
            route_id=f"{result['trip_id']}-opt{i + 1}",
            snapshot=snapshot,
        )
        for i, (flavour, fl_script) in enumerate(zip(flavours, scripts, strict=True))
    ]
```

Replacement:

```python
    options = [
        build_route_option(
            flavour,
            fl_script,
            beats_by_id,
            route_id=f"{result['trip_id']}-opt{i + 1}",
            snapshot=snapshot,
            sequence=fl_sequence,
        )
        for i, (flavour, fl_script, fl_sequence) in enumerate(
            zip(flavours, scripts, sequences, strict=True)
        )
    ]
```

## 8.7 Test changes required by step 8

### 8.7.1 `tests/test_trip_preview_vignettes.py` — re-point at the shared builder

Every one of the twelve tests in this file calls `_preview_stops(script, route,
vignette_beats, snapshot, overflow_by_poi)`. Re-point each through a single module-level
helper added to that file, so the assertions (which are the real spec) are untouched:

```python
from src.api.routes.trips import _preview_cards
from src.tour.contract import BeatSequence
from src.tour.options import build_route_option


def _preview_stops(script, route, vignette_beats, snapshot, overflow_by_poi):
    """The shape the API produces, through the ONE shared interleave."""
    beats_by_id = {b.id: b for beats in snapshot.beats_by_poi.values() for b in beats}
    return _preview_cards(
        build_route_option(
            route,
            script,
            beats_by_id,
            route_id="test-opt1",
            snapshot=snapshot,
            sequence=BeatSequence(
                poi_beats=(),
                vignette_beats=vignette_beats,
                overflow_by_poi=overflow_by_poi,
            ),
        )
    )
```

Delete the `from src.api.routes.trips import _preview_stops` import at
`tests/test_trip_preview_vignettes.py:7`.

Two fixture edits are then required:

- `test_deeper_dive_flag_reflects_overflow_by_poi` (`:135-157`) passes
  `{"d0": ("extra-b1", "extra-b2")}`; the helper above threads it into
  `BeatSequence.overflow_by_poi`, which is what `build_route_option` reads. **No change.**
- `_snapshot` (`:65-68`) returns a snapshot containing ONLY the vignette POI. The merged
  builder reads `snapshot.beats_for(...)` for the vignette's dominant lens (`options.py:177`)
  and `spotlight(poi, ...)` for its score — both already worked in `_preview_stops` off the
  same snapshot (`trips.py:851`). `require_materialized_snapshot` is a no-op because
  `place_manifest is None` (`src/tour/selection.py:552-553`). **No change.**
- Every dwell-card assertion still holds because dwell narration, band and order are B13/B9
  transplants. The one assertion that must be RE-CHECKED by the implementer:
  `test_vignette_interleaves_before_its_leg_destination` asserts
  `[s.band for s in stops] == ["dwell", "vignette", "dwell"]` (`:82`). Under B9 the leg card
  comes FIRST when a leg carries text; this fixture's script has only two `GLUE_PACING`
  sentences (`:43-47`), and `GLUE_PACING` is not in `CONCURRENT_GLUE_LABELS`, so no leg card
  is emitted and the expectation is unchanged.

### 8.7.2 `tests/test_tour_flavours.py` — pass the sequence, and the new proving test

Nine call sites of `build_route_option` in this file (`:373`, `:394`, `:405`, `:434`,
`:447`, `:464`, `:503`, `:521-524`, `:536`, `:557`). Each gains `sequence=...`:

- The plain fixtures (`test_build_route_option_maps_engine_outputs`,
  `test_route_option_contract_round_trips`,
  `test_build_route_option_populates_spotlight_and_band_per_stop`,
  `test_build_route_option_lens_dims_off_genre_stop_to_vignette`,
  `test_route_option_lens_coverage_note_none_without_lens`,
  `test_route_option_lens_coverage_note_reflects_corridor_density`,
  `test_route_option_empty_vignettes_is_todays_output`) pass
  `sequence=BeatSequence(poi_beats=())`.
- `test_route_option_interleaves_vignette_after_leg_origin` (`:499-512`) and
  `test_route_option_dwell_stops_and_eta_unchanged_by_vignettes` (`:515-529`) pass
  `sequence=BeatSequence(poi_beats=(), vignette_beats={1: (vbeat,)})`. `_route_script_with_vignette`
  (`:475-496`) must return `vbeat` as well so both tests can build it; change its return
  to `return route, script, beats_by_id, snapshot, vbeat` and update both call sites.
  `vbeat.script_body` is `"A quiet fountain from another century. It still runs."`
  (`:485`), so `vignette_one_liner_text` yields the first sentence and B11 keeps the card.
- `test_route_option_leg0_and_closing_leg_vignette_positions` (`:541-559`) passes
  `sequence=BeatSequence(poi_beats=(), vignette_beats={0: (vb0,), 2: (vb9,)})` where `vb0`
  and `vb9` are the two `BeatRef`s already constructed inline at `:553-554` — lift them to
  named locals.
- `test_route_option_round_trips_with_explicit_spotlight_fields` (`:562-583`) constructs
  `RouteOptionStop` directly and does not call the builder. **No change** — the two new
  fields have defaults.

### 8.7.3 The proving test

**File:** `tests/test_tour_flavours.py`
**Name:** `test_build_route_option_carries_the_leg_and_vignette_narration_cards`

Stubs, all in that file, reusing `_hand_built_route_and_script` (`:328-368`):

- **The route:** the hand-built two-stop route, with one vignette POI on leg 1 — i.e.
  `_route_script_with_vignette`'s route (`v1` "Fountain", tier 2, on leg 1).
- **The script:** the hand-built script with its `script` tuple replaced by three
  sentences, so all three card kinds are exercised at once:

  ```python
  script = script.model_copy(update={"script": (
      Sentence(text="Anchor story.", source_id="GLUE_PACING", source_type="glue", stop_idx=0),
      Sentence(text="From Anchor, head on to Passby, about a minute away.",
               source_id="GLUE_NAV", source_type="glue", stop_idx=1),
      Sentence(text="A quiet fountain from another century.",
               source_id="vb1", source_type="beat", stop_idx=1),
      Sentence(text="Passby story.", source_id="GLUE_PACING", source_type="glue", stop_idx=1),
  )})
  ```

  `GLUE_NAV` is in `CONCURRENT_GLUE_LABELS` so `is_walk_concurrent` routes it to the leg
  bucket (`src/tour/generation.py:87-89`); `vb1` is a vignette beat id so it is stripped
  from the dwell card (B2) and voiced only by the vignette card.
- **The sequence:** `BeatSequence(poi_beats=(), vignette_beats={1: (vbeat,)},
  overflow_by_poi={"p1": ("extra-1",)})`.
- **The transits:** the hand-built ones (`:333-337`) — leg 1 has `walk_seconds=486` and no
  `leg_seconds`, so the leg card must read `round(486 / 60) == 8` minutes.

Assertions, in order:

```python
def test_build_route_option_carries_the_leg_and_vignette_narration_cards():
    route, script, beats_by_id, snapshot, vbeat = _route_script_with_vignette()
    script = script.model_copy(update={"script": (...)})   # as above
    sequence = BeatSequence(
        poi_beats=(),
        vignette_beats={1: (vbeat,)},
        overflow_by_poi={"p1": ("extra-1",)},
    )

    opt = build_route_option(
        route, script, beats_by_id, route_id="rt", snapshot=snapshot, sequence=sequence
    )

    # 1. THE ORDER: leg into a stop, then that leg's vignettes, then the stop.
    assert [(s.band, s.name) for s in opt.stops] == [
        ("dwell", "Anchor"),
        ("leg", "Walk to Passby"),
        ("vignette", "Fountain"),
        ("dwell", "Passby"),
    ]

    # 2. THE LEG CARD carries the walking narration and the WALK's duration.
    leg = opt.stops[1]
    assert "head on to Passby" in leg.narration
    assert leg.minutes == 8          # the 486s leg, not the narration's length
    assert leg.spotlight == 0.0
    assert leg.poi_id == "p2"        # the arrival stop's identity, never an invented id
    assert leg.has_deeper_dive is False

    # 3. THE VIGNETTE CARD voices the one-liner, at zero minutes.
    vignette = opt.stops[2]
    assert vignette.narration == "A quiet fountain from another century."
    assert vignette.minutes == 0
    assert vignette.has_deeper_dive is False

    # 4. NO DOUBLE-VOICING: neither the leg line nor the vignette line survives on a
    #    dwell card.
    assert opt.stops[3].narration == "Passby story."
    assert opt.stops[0].narration == "Anchor story."

    # 5. THE DEEPER-DIVE FLAG rides the dwell card whose POI had overflow.
    assert opt.stops[0].has_deeper_dive is True
    assert opt.stops[3].has_deeper_dive is False

    # 6. Cards cost no elapsed time: eta is unchanged from the no-narration build.
    assert opt.eta_seconds == 600 + 486 + 300 + 60
```

Add `Sentence` to the `src.tour.contract` import at `tests/test_tour_flavours.py:16-28`.

### THE MUTATION

> In `build_route_option`, change
> `bucket = leg_sents if is_walk_concurrent(sentence, vignette_beat_ids) else dwell_sents`
> to
> `bucket = dwell_sents`

The `GLUE_NAV` sentence then falls into the dwell bucket, no leg card is emitted, and
assertion 1 fails on the card list while assertion 4 fails on `"Passby story."`. This is
the same mutation `tests/test_trip_preview_vignettes.py:228-229` names for the old copy,
now pointed at the surviving one.

Second, independent mutation for the drop rule (B11): change
`if vp.id in one_liner_by_poi` to `if True` in both vignette comprehensions —
`tests/test_trip_preview_vignettes.py::test_unvoiceable_vignette_is_not_shown` (`:124-132`)
goes RED. Third, for the deeper-dive transplant (B14): change
`has_deeper_dive=bool(sequence.overflow_by_poi.get(sp.id))` to `has_deeper_dive=False` —
assertion 5 goes RED.

---

# STEP 14 — Estimated walking legs become a labelled degradation

**Ledger:** id `14`, files `src/tour/premium_tour.py`, `tests/test_trip_preview_contract.py`.
**Proving test:** `tests/test_trip_preview_contract.py::test_estimated_legs_are_labelled_not_silently_shipped`.
**Gate:** `make lint`.
**Criteria:** AC-18, AC-20, AC-22.

Owner parameter 4 is RESOLVED to labelled degradation (`00-brief.md:198-217`,
`run-context.md:49-58`). It is not re-opened here.

## 14.1 The four conditions, separated by cause

All four live in the single `if` at `src/tour/premium_tour.py:260-268` today, and in
`_premium_route_refusal` after step 7. Two are structural faults in the plan itself; two
are statements about the routing service.

| Arm | Exact condition | Line at HEAD | After step 14 |
| --- | --- | --- | --- |
| A1 | `not route.pois` | `src/tour/premium_tour.py:261` | **HARD REFUSAL.** A route with no stops is not a tour; there is nothing to label |
| A2 | `not route.routed` | `src/tour/premium_tour.py:262` | **DEGRADATION.** `routed` is `bool(transits) and all(t.source == "valhalla" for t in transits)` (`src/tour/routing.py:452`) — it is false precisely when at least one leg fell back to haversine |
| A3 | `len(route.transits) != len(route.pois)` | `src/tour/premium_tour.py:263` | **HARD REFUSAL.** A stop with no leg, or a leg with no stop, breaks the index alignment every downstream consumer assumes (`route_summary`'s `enumerate`, `src/tour/premium_tour.py:153-163`; the leg-walk map in step 8's `build_route_option`) |
| A4 | `any(transit.valhalla_receipt is None for transit in route.transits)` | `src/tour/premium_tour.py:264` | **DEGRADATION.** Same cause as A2, one leg at a time |
| A5 | `receipt_configs != {VALHALLA_ROUTING_CONFIG_SHA256}` | `src/tour/premium_tour.py:274-275` | **DEGRADATION.** The service answered with a routing setup this build was not compiled against |

**The trap, and it must not be implemented naively.** `receipt_configs` is the empty set
when no transit has a receipt (`src/tour/premium_tour.py:269-273`), and
`set() != {VALHALLA_ROUTING_CONFIG_SHA256}` is `True`. So a fully-unreceipted route trips
A5 as well as A2/A4, and would record two degradations describing one outage. A5 must
therefore be guarded by `if receipt_configs and ...`.

## 14.2 Exact replacement for step 7's `_premium_route_refusal`

Replace the function defined in 7.2.1 with these two:

```python
#: A route whose leg times are estimated rather than measured. ONE kind for the whole
#: outage — ``summarize`` collapses repeats into one row with a count
#: (src/tour/degradations.py:152-166), and an operator does not need it per leg.
ESTIMATED_LEGS_DEGRADATION = "walking_times_estimated"
#: The routing service answered, but with a setup this build was not compiled against.
ROUTING_CONFIG_DEGRADATION = "routing_setup_unexpected"


def _premium_route_refusal(route: Route) -> str | None:
    """Why this route is STRUCTURALLY unplannable, or None.

    Only the two faults in the plan's own shape refuse. A route with no stops is not a
    tour, and a leg count that does not match the stop count breaks the index alignment
    every consumer downstream assumes.

    MISSING ROUTE MEASUREMENTS DO NOT REFUSE (owner ruling 2026-08-04). The walking
    engine is a real production service that can cold-start, restart or rebuild its
    map, and a refusal here would take tour generation down for every user for the
    duration of that. It is labelled instead — see ``_record_routing_degradations`` —
    so the silent substitution is gone without the outage taking the product with it.
    """

    if not route.pois:
        return "Premium planning requires a route with at least one stop"
    if len(route.transits) != len(route.pois):
        return "Premium planning requires one walking leg per stop"
    return None


def _record_routing_degradations(route: Route) -> None:
    """Label a route whose walking times were estimated rather than measured.

    A no-op outside a degradation scope (src/tour/degradations.py:137-139), so the
    batch runner and unit tests are unaffected; the API surfaces open one per request.
    """

    estimated = [
        index
        for index, transit in enumerate(route.transits)
        if transit.valhalla_receipt is None
    ]
    if estimated or not route.routed:
        record(
            kind=ESTIMATED_LEGS_DEGRADATION,
            human=(
                "Walking times between stops are estimates, not measured routes, so "
                "the tour may run a little longer or shorter than it says."
            ),
            component="premium_tour.plan_premium_options",
            cause=(
                f"The routing service returned no measured route for {len(estimated)} "
                f"of {len(route.transits)} legs. Those legs fell back to straight-line "
                "distance scaled by HAVERSINE_CORRECTION at PACE_KMH "
                "(src/tour/routing.py:41-53), which cannot see rivers, walls or closed "
                "streets, so a leg across an unbridged gap is understated. Check that "
                "ondoway-valhalla is up and has finished building its tiles."
            ),
            estimated_legs=str(len(estimated)),
            total_legs=str(len(route.transits)),
            fully_measured=str(route.routed).lower(),
        )
    receipt_configs = {
        transit.valhalla_receipt.routing_config_sha256
        for transit in route.transits
        if transit.valhalla_receipt is not None
    }
    if receipt_configs and receipt_configs != {VALHALLA_ROUTING_CONFIG_SHA256}:
        record(
            kind=ROUTING_CONFIG_DEGRADATION,
            human=(
                "Walking times for this tour were worked out with different settings "
                "than this version expects, so they may be a little off."
            ),
            component="premium_tour.plan_premium_options",
            cause=(
                f"Leg receipts carry {len(receipt_configs)} distinct routing-config "
                "hashes; this build expects exactly VALHALLA_ROUTING_CONFIG_SHA256 "
                "(src/tour/routing_client.py). The deployed Valhalla configuration and "
                "the one compiled into this build have diverged."
            ),
            expected_setups="1",
            observed_setups=str(len(receipt_configs)),
        )
```

### The exact `Degradation` that results

`record` (`src/tour/degradations.py:124-149`) constructs `Degradation`
(`src/tour/degradations.py:42-67`). Every field of the primary case:

| field | value |
| --- | --- |
| `kind` | `"walking_times_estimated"` |
| `human` | `"Walking times between stops are estimates, not measured routes, so the tour may run a little longer or shorter than it says."` |
| `component` | `"premium_tour.plan_premium_options"` |
| `error_type` | `""` (no `error=` is passed; `src/tour/degradations.py:145`) |
| `error_message` | `""` (same) |
| `context["cause"]` | the operator sentence in the code above — the routing service, the straight-line substitution, and what to check |
| `context["estimated_legs"]` | `"<n>"` |
| `context["total_legs"]` | `"<m>"` |
| `context["fully_measured"]` | `"false"` |

**The `human` string is PINNED VERBATIM by coordinator ruling and must not be reworded.**
One sentence, consequence first. It names no identifier, no file, no service and no
internal cause; it does not say the tour is broken and does not invite a retry, because
the tour is usable and only its timing is approximate. It reads correctly with no
surrounding context, which it must: it is rendered in three places — the workbench
degradation panel, the phone itinerary page, and the raw API response.

**The cause lives in `context["cause"]`, not in `human`.** `Degradation` already has a
home for it: `context: dict[str, str]` (`src/tour/degradations.py:57`), whose documented
purpose is "anything else worth pasting" for the Claude-facing register
(`src/tour/degradations.py:22-26`). **No extension to the dataclass is needed, and none
should be made.** The other two free-text fields, `error_type` and `error_message`, are
explicitly the exception's class and message (`src/tour/degradations.py:53-56`,
`:145-147`); there is no exception here, and synthesising one to make the text render
would put a fabricated error class on the wire.

For the config case: `kind="routing_setup_unexpected"`, same `component`, empty
`error_type`/`error_message`, and
`context={"cause": "...", "expected_setups": "1", "observed_setups": "<n>"}`.

### 14.2.1 The cause is in the JSON but NOT on the workbench screen today

Named explicitly, because it was asked for and because "present in the response" is not
the same as "an operator can see it".

`buildDegradationPanel` (`frontend/review.html:3472-3545`) renders, per row:

| field | where |
| --- | --- |
| `human` | the primary on-screen line, largest and first — `frontend/review.html:3532-3535` |
| `component` | the quieter monospace technical line — `:3538-3541` |
| `count` | appended to that line as "happened N times" — `:3539` |
| `error_type`, `error_message` | appended to that same line, **only when `error_type` is truthy** — `:3541` |
| `kind` | **not rendered on screen** — clipboard only, `:3513` |
| `context` | **not rendered on screen** — clipboard only, `:3516-3517` |

So with this contract as written, an operator staring at the panel sees the traveller
sentence and `premium_tour.plan_premium_options`, and must press "Copy report for Claude"
(`frontend/review.html:3492-3521`) and paste it somewhere to read the cause. The cause is
never lost — it is in the API response and in the copied report — but it is one click away
rather than on screen.

**This is a cross-step dependency, not something step 14 can fix:** `frontend/review.html`
is step 12's file, and the web-surfaces contract
(`specs/2026-08-04-unify-tour-algorithm/findings/contracts-web-surfaces.md:429`) currently
records `buildDegradationPanel` as **UNCHANGED**. The smallest change that makes the cause
visible is one block appended inside the existing `rows.forEach` at
`frontend/review.html:3527-3543`, after the `tech` line:

```javascript
      // The CAUSE, for an operator debugging a bad tour. `human` is deliberately the
      // traveller's sentence and carries no diagnosis, so without this the operator has
      // to copy the report to a clipboard to learn why anything degraded.
      if (r.context && r.context.cause) {
        const cause = document.createElement('div');
        cause.textContent = r.context.cause;
        cause.style.cssText = 'font-size:0.75rem;color:#c2836a;margin-top:2px;';
        row.appendChild(cause);
      }
```

Recommendation: the web-surfaces agent adds exactly that to step 12 and drops the
"UNCHANGED" verdict on `buildDegradationPanel`. If it is not added, step 14 still lands
and AC-18 is still met (the row exists, with a stable kind, plain-English `human`, and a
`component`, which is exactly what AC-18 asks for) — the operator simply reads the cause
from the copied report instead of the screen.

## 14.3 Exact call-site rewrite inside `plan_premium_options`

Step 7 left this loop (7.2.3):

```python
    for index, route in enumerate(ordered):
        refusal = _premium_route_refusal(route)
        if refusal is not None:
            if index == 0:
                raise PremiumRouteInfeasibleError(refusal)
            continue
        plans.append(
```

Replacement:

```python
    for index, route in enumerate(ordered):
        refusal = _premium_route_refusal(route)
        if refusal is not None:
            if index == 0:
                raise PremiumRouteInfeasibleError(refusal)
            continue
        _record_routing_degradations(route)
        plans.append(
```

`record` is already imported at `src/tour/premium_tour.py:25`
(`from src.tour.degradations import in_current_context, record`). No new import.

Add both `kind` constants to `__all__` (`src/tour/premium_tour.py:709-729`), in
alphabetical position: `"ESTIMATED_LEGS_DEGRADATION",` and
`"ROUTING_CONFIG_DEGRADATION",` before `"EphemeralReceiptSink",` (module-level
SCREAMING_CASE sorts before CamelCase under the existing ASCII ordering in that list).

### Where the degradation reaches the wire

`/trips/preview` already opens the collection scope and attaches the rows:
`src/api/routes/trips.py:916-919`. Nothing else is needed on that surface.

`/trips/generate` and `/trips/{id}/compose` do **not** open a scope today, so
`record` is a no-op there (`src/tour/degradations.py:137-139`). Step 15 of the ledger
("The generate and compose responses report what degraded, like the preview already
does") is what carries AC-18's "on either surface" — it is explicitly out of step 14's
files.

### AC-22 is satisfied without any further edit

Authoring on a receiptless route already works: `FinalTourBlueprint`'s own validator
guards its receipt-config check with `if receipt_config_hashes and ...`
(`src/tour/artifact.py:679-687`), so an empty set passes. `execute_premium_plan` and
`finalize_premium_tour` never read `valhalla_receipt`. The receipt bar lives in PLAN and
nowhere else.

## 14.4 The proving test

**File:** `tests/test_trip_preview_contract.py`
**Name:** `test_estimated_legs_are_labelled_not_silently_shipped`

### The stub it builds

One new class in that file, placed immediately after `_FakeRoutingClient`
(`tests/test_trip_preview_contract.py:117-194`):

```python
class _ReceiptlessRoutingClient(_FakeRoutingClient):
    """The walking service answering with no measurement — a cold start or a tile rebuild.

    Deliberately returns the SAME leg seconds as its parent so the route that gets
    planned is identical: the only difference on the wire is that the legs are
    estimates. A stub that also changed the times would prove nothing about labelling,
    because a different route would be selected. Nothing here stops or touches the
    shared Valhalla container.
    """

    def route_with_receipt(self, from_lat, from_lng, to_lat, to_lng):
        seconds = self.leg_seconds(from_lat, from_lng, to_lat, to_lng)
        return seconds, haversine_m(from_lat, from_lng, to_lat, to_lng), None, None
```

Returning `polyline=None` makes `_transit` set `source="haversine"` and leave
`leg_distance_m` at `None` (`src/tour/routing.py:384-397`), which makes `Route.routed`
`False` (`src/tour/routing.py:452`) and every `valhalla_receipt` `None`. `leg_seconds` is
still populated, so selection's budget arithmetic — and therefore the chosen stop set — is
byte-identical to the receipted run.

The fixture needs the client swapped in, which `make_client` hard-codes at
`tests/test_trip_preview_contract.py:251`. Add an optional parameter to that fixture:

```python
    def _make(records_by_kind, routing_client=_FakeRoutingClient) -> TestClient:
        monkeypatch.setattr("src.api.routes.trips.RoutingClient", routing_client)
```

with the rest of `_make` (`:252-260`) unchanged. Every existing caller passes one
argument and is unaffected.

### Assertions, in order

```python
def test_estimated_legs_are_labelled_not_silently_shipped(make_client):
    """A tour built on estimated walking times ships, and SAYS SO.

    The walking service is a real production dependency that can cold-start or rebuild
    its map (render.yaml:98-124). Refusing would take tour generation down for every
    user during that; shipping silently is worse, because the leg time drives the whole
    time budget and the audio is paced to it. So it ships, labelled.
    """
    client = make_client(_green_cluster_records(), routing_client=_ReceiptlessRoutingClient)

    r = client.post(
        "/api/v1/trips/preview",
        json={"center_lat": START[0], "center_lng": START[1], "duration_min": 30},
    )

    # 1. IT SHIPS. Not a 422, not a PremiumRouteInfeasibleError.
    assert r.status_code == 200, r.text
    body = r.json()

    # 2. IT SAYS SO — one labelled row, on the existing channel.
    rows = {row["kind"]: row for row in body["degradations"]}
    assert "walking_times_estimated" in rows, body["degradations"]
    row = rows["walking_times_estimated"]

    # 3. THE TRAVELLER'S SENTENCE, pinned verbatim. It is rendered on the phone, in the
    #    workbench panel and in the raw response, so it must read alone — and it must not
    #    imply the tour is broken or ask anyone to retry.
    assert row["human"] == (
        "Walking times between stops are estimates, not measured routes, so the tour "
        "may run a little longer or shorter than it says."
    )
    for token in ("valhalla", "receipt", "haversine", "service", "retry", "_", "()"):
        assert token not in row["human"].lower(), row["human"]

    # 4. THE OPERATOR'S CAUSE, in the structured half where it belongs — never stuffed
    #    into the sentence above.
    assert row["component"] == "premium_tour.plan_premium_options"
    assert "routing service" in row["context"]["cause"]
    assert "straight-line" in row["context"]["cause"]
    assert int(row["context"]["estimated_legs"]) > 0
    assert row["context"]["fully_measured"] == "false"

    # 5. ONE ROW, NOT ONE PER LEG — and no second row blaming the routing SETUP, which
    #    is a different fault and must not fire just because no receipt exists.
    assert "routing_setup_unexpected" not in rows, body["degradations"]

    # 6. AUTHORING STILL RAN on the estimated route: the receipt bar lives in PLAN.
    assert body["candidate_eligible"] is True
    assert body["stops"]


def test_a_route_with_no_stops_is_still_a_hard_refusal(make_client):
    """Structural faults did NOT become degradations. An empty route is not a tour."""
    from src.tour import premium_tour

    assert premium_tour._premium_route_refusal(
        Route(pois=(), transits=(), total_walk_distance_m=0, total_walk_seconds=0)
    ) is not None
```

`Route` and `haversine_m` are already available (`haversine_m` is imported at
`tests/test_trip_preview_contract.py:47`; add `Route` to the `src.tour.contract` import at
`:45`).

### THE MUTATION

> In `_record_routing_degradations`, change
> `if estimated or not route.routed:`
> to
> `if False:`

The response still returns 200, so assertion 1 stays green, and assertion 2 goes RED —
proving the test measures the LABEL and not merely the absence of a refusal.

The complementary mutation, proving the non-refusal half: in `_premium_route_refusal`, add
back `or any(transit.valhalla_receipt is None for transit in route.transits)` to the
structural condition. Assertion 1 goes RED with a 422 and
`detail["reason"] == "premium_route_infeasible"`.

A third, proving the two registers stay separated: delete the `cause=(...)` keyword from
the `record(...)` call. Assertions 1–3 stay green and assertion 4 goes RED, so a future
edit cannot quietly drop the operator's diagnosis while the traveller's sentence still
reads fine. (`cause` reaches `Degradation.context` through `record`'s `**context: str`
catch-all, `src/tour/degradations.py:130`, `:147` — no signature change is involved.)

A fourth, proving the empty-set trap is really handled: change
`if receipt_configs and receipt_configs != {VALHALLA_ROUTING_CONFIG_SHA256}:` to
`if receipt_configs != {VALHALLA_ROUTING_CONFIG_SHA256}:`. Assertion 5 goes RED, because
a fully-unreceipted route would then also be reported as a routing-setup mismatch.

---

# BLOCKING AMBIGUITY

Two items. Both need the owner, not the implementer.

## BA-1 — "BLOCK 1 is $0" is not true today, and step 7 multiplies the cost by three

The brief says Block 1 has "NO LLM, NO spend" (`00-brief.md:15-18`) and AC-2 requires that
"a provider that raises on any call is never invoked". But `plan_premium_tour` calls
`generate(...)` with no glue client (`src/tour/premium_tour.py:293-299`), and `generate`'s
default is the **real, paid** `HaikuGlueClient` — changed to real-by-default by owner
ruling on 2026-07-31 and restored two days ago in `db26f4c3` ("premium narration has been
dead since 2026-07-31; restore it"), with the reasoning at `src/tour/generation.py:328-337`.
So Block 1 makes several Haiku calls per plan today, and planning three flavours instead
of one triples that. (The phone's `/trips/generate` already pays this three times over —
`src/api/routes/trips.py:344-365` loops `generate` per flavour — so step 7 makes the
preview match the phone rather than inventing a new cost.)

**My contract does not decide this.** It threads an explicit `glue_client` parameter with
a `None` default, which is byte-for-byte today's behaviour, and makes the step-7 test pass
a stub so the test itself is $0. That leaves the product question open.

**Recommendation:** keep real glue in Block 1 (the owner's 2026-07-31 ruling is more
specific and more recent than the brief's one-line cost sketch), and accept 3× glue at
plan time. If the owner instead wants Block 1 genuinely free, the change is one line at
the `plan_premium_options` default (`glue_client: GlueClient | None = MockGlueClient()`),
and it should be made at step 10 — the endpoint step where AC-2 and AC-13 are actually
gated — not here.

## BA-2 — AC-13 forbids per-stop script text in the plan-only preview, and step 8 puts narration on the option card

AC-13 (`run-context.md:116`): "the response contains no LLM-authored narration:
`narration_kind` is not `llm_candidate` and no per-stop script text is present, because
planning no longer authors." Step 8's own ledger test name is
`test_build_route_option_carries_the_leg_and_vignette_narration_cards`. Both cannot be
read literally at once: after step 10 the preview response IS the option list, and the
option list will carry narration.

**Recommendation:** read AC-13 as "no **LLM-authored** narration" (its own words), which
the stitched, deterministic narration satisfies as long as BA-1 resolves toward a non-LLM
glue client in Block 1. If BA-1 resolves the other way (real Haiku glue at plan time),
AC-13 must be amended at approval to say "no per-stop **composed** narration", because the
stitched text will contain Haiku-written transition sentences. This is an acceptance-criteria
edit, not a code decision, and it belongs to step 10's author — but it is recorded here
because step 8 is what puts the field on the wire.

## Note, not a blocker — the leg card's `poi_id`

A leg card must have a `poi_id` (`RouteOptionStop.poi_id` is required and
`extra="forbid"`). I have contracted it to the ARRIVAL stop's id, matching the lat/lng and
name `_preview_stops` already borrowed from that stop (`src/api/routes/trips.py:830-832`),
rather than inventing a synthetic id — "no fabricated values" wins. The consequence is that
a poi id appears twice in `RouteOption.stops` when its arrival leg carries narration, so
AC-6 and AC-8's "same POI ids in the same order" checks must filter `band == "dwell"`.
This is documented in the `RouteOptionStop` docstring in 8.2.2 so a later reader cannot
miss it.
