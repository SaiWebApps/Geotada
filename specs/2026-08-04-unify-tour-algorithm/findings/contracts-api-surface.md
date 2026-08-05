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
> **DEAD IN THIS FILE:** any preview-response field classification that KEEPS per-stop descriptive text, narration or vignette prose in the plan-only response. Under ruling 1 the plan-only response carries places, order, timings, tourability and degradations — no prose.

---

# Implementation contract — the HTTP surface (steps 9, 10, 11, 15)

Written against the tree at `a7df218c`. Every claim below carries `file:line`.
This document is a contract: implement it literally. Where it says "exact
replacement block", that block is the code, not a sketch.

---

## 0. Node-id existence check (the defect a hostile judge found on step 3)

Step 3's proving test already exists and passes today
(`tests/test_trip_api.py:650` — `test_compose_authors_per_stop_and_keeps_the_wire_contract`),
so it is a regression pin, not a proof. My four were checked the same way, by
grepping each name across every `*.py` in the repo:

| Step | Node id | Target file | Exists today? |
| --- | --- | --- | --- |
| 9 | `test_generate_plans_through_the_shared_block_one` | `tests/test_trip_api.py` | **No** — zero hits repo-wide |
| 10 | `test_preview_returns_three_options_and_spends_nothing` | `tests/test_trip_preview_contract.py` | **No** — zero hits repo-wide |
| 11 | `test_preview_compose_authors_only_the_chosen_option` | `tests/test_trip_preview_contract.py` | **No** — zero hits repo-wide |
| 15 | `test_generate_and_compose_report_what_degraded` | `tests/test_trip_api.py` | **No** — zero hits repo-wide |

Command run: `grep -rn "<name>" --include='*.py' .` for each of the four, plus a
prefix sweep `grep -rn "def test_generate_plans\|def test_preview_returns_three\|def test_preview_compose_authors\|def test_generate_and_compose" --include='*.py' .`
whose only hit was step 3's pre-existing
`tests/test_trip_api.py:650`. No step of mine needs renaming or re-pointing on
this ground: each of the four is a genuinely new function, RED by collection
error before the work starts. Each also carries a named MUTATION below, so
"RED because it does not exist" is not the only proof of teeth.

---

## 1. Interfaces this contract CONSUMES from steps 7 and 8

Steps 9-11 sit downstream of steps 7 and 8, whose contracts are written by
another agent. Everything below assumes exactly these two shapes. If step 7's or
step 8's contract names them differently, **only the name changes** — the
call-site arity and the fields consumed are load-bearing here.

**From step 7** (`src/tour/premium_tour.py`), Block 1:

```python
def plan_premium_tour(
    tour_input: TourInput,
    snapshot: CorpusSnapshot,
    *,
    routing_client: RoutingClient,
    planning_policy: RoutePlanningPolicy | None = None,
    generation_time: dt.datetime | None = None,
    authorities: PremiumAuthorityHashes = PREMIUM_AUTHORITIES,
) -> tuple[PremiumTourPlan, ...]   # exactly 3 plans, ranked, index 0 best
```

Today it returns ONE `PremiumTourPlan` (`src/tour/premium_tour.py:239-355`),
selecting a single route via `choose_discrete_route(routes)`
(`src/tour/premium_tour.py:259`). Step 7 makes it return all three. Fields this
contract reads off each plan, all present today: `.route`
(`premium_tour.py:198`), `.sequence` (`:203`), `.source` (`:204`), `.units`
(`:205`).

**From step 8** (`src/tour/options.py:51`), the single interleave:

```python
build_route_option(route, script, beats_by_id, *, route_id: str, snapshot) -> RouteOption
```

Signature unchanged (`src/tour/options.py:51-58`). Step 8 folds the leg and
vignette narration cards (today `_preview_stops`, `src/api/routes/trips.py:734`)
into it, so each `RouteOptionStop` carries the narration text and the `"leg"`
band. This contract reads only `RouteOption.route_id`, `.stops`, `.eta_seconds`
(`src/tour/contract.py:576-591`) and never inspects the stop element type — so a
change to `RouteOptionStop`'s field set inside step 8 does not invalidate
anything here.

**Not touched by this contract:** `TripPreviewStop`
(`src/api/models/trips.py:256-287`) and `TripPreviewBasicTour`
(`:311-317`). Step 8 owns whatever they become when `_preview_stops` is deleted;
step 11 carries `basic_tour` through with *whatever type step 8 leaves it*.

---

## 2. STEP 9 — the app's generate endpoint plans through Block 1

### 2.1 What is wrong today

`POST /trips/generate` plans with `select_k_routes(tour_input, snapshot, 3,
routing_client=routing_client)` and **no** `planning_policy`
(`src/api/routes/trips.py:325`), so it takes the parameter default
`LEGACY_ROUTE_PLANNING_POLICY` (`src/tour/selection.py:2153`) — 0.83 flat. It
then takes `flavours[0]` (`trips.py:326`), never calling
`choose_discrete_route`, and never checking Valhalla receipts. That is the ~20%
less walking and audio the phone plans than the workbench.

### 2.2 Wire contract — BEFORE and AFTER

**Unchanged**: method `POST`, path `/api/v1/trips/generate`, status `201`
(`trips.py:280`), auth `Depends(get_current_user)` (`trips.py:283`).

**Request** `TripGenerateRequest` (`src/api/models/trips.py:29-99`) — **NO
CHANGE**, all 16 fields identical:

| Field | Type | Required | Default | Validation |
| --- | --- | --- | --- | --- |
| `profile_id` | `str` | yes | — | — |
| `center_lat` | `float` | yes | — | `ge=-90, le=90` |
| `center_lng` | `float` | yes | — | `ge=-180, le=180` |
| `end_lat` | `float \| None` | no | `None` | `ge=-90, le=90` |
| `end_lng` | `float \| None` | no | `None` | `ge=-180, le=180` |
| `radius_m` | `int` | no | `3000` | `le=10000`; inert (`trips.py:294-296`) |
| `max_stops` | `int` | no | `10` | `le=30`; inert |
| `duration_min` | `int \| None` | no | `None` | `ge=1, le=600` |
| `start_date` | `str` | yes | — | — |
| `end_date` | `str` | yes | — | — |
| `start_time` | `str` | no | `"09:00"` | HH:MM validator (`models/trips.py:77-90`) |
| `kid_friendly_only` | `bool` | no | `False` | inert |
| `trip_name` | `str \| None` | no | `None` | — |
| `lenses` | `list[str] \| None` | no | `None` | `normalize_lenses` (`models/trips.py:92-99`) |
| `round_trip` | `bool` | no | `False` | — |
| `city_slug` | `str` | no | `"paris"` | `_validate_city_slug` (`models/trips.py:14-26`) |

**Response** `TripGenerateResponse` (`src/api/models/trips.py:150-169`) — no
field change at step 9 (step 15 adds `degradations`). All 10 fields keep their
names, types and defaults. What changes is only the VALUE of `stops` and
`options`: they are now Block 1's output.

**Status codes** — unchanged set:

| Code | When | Exact body |
| --- | --- | --- |
| 201 | success | `TripGenerateResponse` |
| 404 | profile not owned/absent (`trips.py:304-305`) | `{"detail": "Profile '<id>' not found"}` |
| 422 | `TourInput` contradiction (`trips.py:184-193`) | `{"detail": {"reason": "invalid_tour_input", "errors": [{"loc": [...], "msg": "..."}]}}` |
| 422 | tourability refusal (`trips.py:327-328`) | `{"detail": _refusal_detail(exc)}` — `{reason, gap_minutes, alternatives[]}`, quoted at `trips.py:207-221` |
| 422 | infeasible premium route (NEW at step 9, see 2.4) | `{"detail": {"reason": "premium_route_infeasible", "detail": str(exc), "gap_minutes": None, "alternatives": []}}` |
| 422 | empty route (`trips.py:333-337`) | `{"detail": "No tourable POIs reachable from this start for the requested duration."}` — **kept verbatim** |

### 2.3 Exact handler rewrite

**Current block, `src/api/routes/trips.py:318-366`:**

```python
    snapshot = load_paris_corpus(driver, city_slug=tour_input.city_slug)
    try:
        # M2/M3: the client supplies routed leg costs + polylines when the
        # local Valhalla container is up; with it down every call falls back
        # to haversine instantly. M6: up to 3 diverse flavours; flavours[0]
        # is the trip that persists.
        with RoutingClient() as routing_client:
            flavours = select_k_routes(tour_input, snapshot, 3, routing_client=routing_client)
        route = flavours[0]
    except TourabilityRefusedError as exc:
        raise HTTPException(422, _refusal_detail(exc)) from exc

    # A non-RED assessment can still yield an empty route (e.g. YELLOW by fill
    # ratio with no tier-3+ anchor candidates). Refuse before persisting —
    # never create a zero-stop Trip.
    if not route.pois:
        raise HTTPException(
            422,
            "No tourable POIs reachable from this start for the requested duration.",
        )

    # Per flavour: beat plan (merging beats demoted into a host POI — same
    # sequence as scripts/tour_build.py) and Script. scripts[0] drives the
    # persisted trip; every flavour becomes a RouteOption. Track B: each
    # flavour's walk-past vignettes get ONE voiceable beat and the stitcher
    # voices the one-liner inside the leg narration.
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

**Exact replacement block:**

```python
    snapshot = load_paris_corpus(driver, city_slug=tour_input.city_slug)
    try:
        # ONE ALGORITHM. Block 1 (plan_premium_tour) is the only planner on either
        # surface: it applies the certification walk budget (0.90-1.10, nominal
        # 1.00) and returns the same three diverse flavours the workbench shows.
        # The un-policied select_k_routes call that used to live here silently took
        # LEGACY_ROUTE_PLANNING_POLICY's 0.83 flat budget, so the phone planned
        # about 20% less walking and audio than the workbench for the same request.
        # Block 1 is provider-free: nothing below spends until /compose runs.
        with RoutingClient() as routing_client:
            plans = plan_premium_tour(tour_input, snapshot, routing_client=routing_client)
    except TourabilityRefusedError as exc:
        raise HTTPException(422, _refusal_detail(exc)) from exc
    except (
        CertificationPlanningInfeasibleError,
        PremiumRouteInfeasibleError,
        ValueError,
    ) as exc:
        raise HTTPException(422, _infeasible_detail(exc)) from exc

    flavours = [plan.route for plan in plans]
    scripts = [plan.source for plan in plans]
    route = flavours[0]
    script = scripts[0]

    # A non-RED assessment can still yield an empty route (e.g. YELLOW by fill
    # ratio with no tier-3+ anchor candidates). Refuse before persisting —
    # never create a zero-stop Trip.
    if not route.pois:
        raise HTTPException(
            422,
            "No tourable POIs reachable from this start for the requested duration.",
        )
```

Notes the developer must not deviate from:

- The per-flavour `build_poi_beat_plans_capped` / `select_vignette_beats` /
  `generate` loop is DELETED here, not moved: Block 1 already does exactly that
  work per plan (`src/tour/premium_tour.py:277-299`), and running it twice is
  the duplication this ledger exists to remove.
- `overflow_by_poi` is no longer computed in this handler. Its only remaining
  consumer in `generate_trip` is none — the local `overflow_by_poi` at
  `trips.py:351` never leaves the loop today. Confirm with `make lint` (F841).
- `build_poi_extra_beats` at `trips.py:371-376` is UNCHANGED and still runs; it
  reads `flavours[0]` and `script.selected_pois`, both of which still exist.
- The `options` construction at `trips.py:451-460` is UNCHANGED — it already
  calls the shared `build_route_option` over `zip(flavours, scripts)`.
- Imports: ADD `plan_premium_tour` is already imported (`trips.py:66`);
  `PremiumRouteInfeasibleError` already imported (`trips.py:63`);
  `CertificationPlanningInfeasibleError` already imported (`trips.py:74`).
  REMOVE `select_k_routes` from the `src.tour.selection` import list
  (`trips.py:80`) **only if** no other call site in this module remains — at
  step 9 `trips.py:325` was its last use, so it must be removed or ruff F401
  fails `make lint`.
- `generate`, `BeatSequence`, `select_vignette_beats`,
  `build_poi_beat_plans_capped` are still used by `compose_trip`
  (`trips.py:595-606`), so their imports stay.

### 2.4 New shared refusal helper

Add once, next to `_refusal_detail` (`trips.py:196-221`), and use it from all
three handlers (generate, plan-only preview, author):

```python
def _infeasible_detail(exc: Exception) -> dict:
    """Structured 422 body for a planning refusal that is not a density RED.

    Same three keys as ``_refusal_detail`` — reason / gap_minutes / alternatives
    — so a client parses one shape whichever refusal it hit. ``detail`` names the
    cause in the engine's own words, which for a too-short duration is the time
    budget it could not seat ("required 3240-3960s"). ``gap_minutes`` is None
    here: this family of refusals measures seconds of route, not a fixed
    destination's overshoot.
    """
    return {
        "reason": "premium_route_infeasible",
        "detail": str(exc),
        "gap_minutes": None,
        "alternatives": [],
    }
```

This is byte-compatible with the body the preview returns today
(`trips.py:958-965`) plus one added key, so the two existing tests that read it
(`tests/test_trip_preview_contract.py:315-319` and `:626-629`) stay green
verbatim.

### 2.5 Proving test — step 9

- **File**: `tests/test_trip_api.py`
- **Function**: `test_generate_plans_through_the_shared_block_one`
- **Node id**: `tests/test_trip_api.py::test_generate_plans_through_the_shared_block_one`
- **Placement**: module level, decorated `@needs_neo4j`, immediately after
  `ile_response` (`tests/test_trip_api.py:173-182`) so it reuses the module
  fixtures.

Stubs built — none new. It uses the existing module fixtures: `client`
(`:119-133`, live 7687 graph, bearer token), `snapshot` (`:136-138`,
`load_paris_corpus` over the live graph), and the real `RoutingClient`
(`src/tour/routing_client.py`), exactly as `ile_engine_route` (`:141-155`) does.
Data shape is the live Paris corpus at `ILE_START = (48.8568, 2.3414)`,
`ILE_DURATION_MIN = 90` (`:49-50`).

Assertions, in this order:

1. `resp = client.post("/api/v1/trips/generate", json=_body(NOLENS_PROFILE_ID))`;
   `assert resp.status_code == 201`.
2. Call Block 1 directly with the identical input:
   `TourInput(start=ILE_START, duration_min=ILE_DURATION_MIN, city_slug="paris",
   lenses=None, round_trip=False)`, then
   `with RoutingClient() as rc: plans = plan_premium_tour(ti, snapshot, routing_client=rc)`.
3. `assert len(plans) == 3` and `assert len(body["options"]) == 3` — Block 1's
   arity reaches the wire (AC-4).
4. For each `i` in `range(3)`: the option's dwell POI ids equal the plan's route
   POI ids, in order —
   `[s["poi_id"] for s in body["options"][i]["stops"] if s["band"] == "dwell"] == [p.id for p in plans[i].route.pois]`.
   This is the AC-7 identity: the phone's options ARE Block 1's plans.
5. For each `i`: `body["options"][i]["eta_seconds"] > 0` and equals the
   `eta_seconds` of `build_route_option(plans[i].route, plans[i].source,
   beats_by_id, route_id=body["options"][i]["route_id"], snapshot=snapshot)`.
6. The persisted trip mirrors option 0:
   `[s["poi_id"] for s in body["stops"]] == [p.id for p in plans[0].route.pois]`.
7. Diversity survived the change: pairwise Jaccard over the three dwell sets is
   `< 0.60` (the constant at `src/tour/selection.py:246-247`).

- **MUTATION** (one line of production code, `src/api/routes/trips.py`, in the
  replacement block of 2.3): change

  ```python
      route = flavours[0]
  ```
  to
  ```python
      route = flavours[-1]
  ```

  The persisted stops then come from option 3 while `options[0]` is still option
  1, so assertion 6 fails. It is deterministically RED because assertion 7 (and
  the pre-existing `test_options_surface_k_flavours`,
  `tests/test_trip_api.py:205-231`) already prove the three options share less
  than 60% of their stops, so `flavours[-1]` cannot coincide with `flavours[0]`.

---

## 3. STEP 10 — the preview endpoint becomes PLAN-ONLY and spends nothing

### 3.1 Wire contract — BEFORE and AFTER

**Unchanged**: method `POST`, path `/api/v1/trips/preview`, status `200`,
anonymous (no `get_current_user` dependency — `trips.py:897-903`).

**Request** `TripPreviewRequest` (`src/api/models/trips.py:195-253`) — **NO
CHANGE**, all 8 fields identical:

| Field | Type | Required | Default | Validation |
| --- | --- | --- | --- | --- |
| `center_lat` | `float` | yes | — | `ge=-90, le=90` |
| `center_lng` | `float` | yes | — | `ge=-180, le=180` |
| `end_lat` | `float \| None` | no | `None` | `ge=-90, le=90` |
| `end_lng` | `float \| None` | no | `None` | `ge=-180, le=180` |
| `duration_min` | `int \| None` | no | `None` | `ge=1, le=600` |
| `lenses` | `list[str] \| None` | no | `None` | `validate_lenses` — unknown lens is a 422 (`models/trips.py:213-249`) |
| `round_trip` | `bool` | no | `False` | — |
| `city_slug` | `str` | no | `"paris"` | `_validate_city_slug` |

**Response** `TripPreviewResponse` (`src/api/models/trips.py:320-370`) — every
field, with a verdict. Nothing on this list is left to judgement:

| # | Field (today) | Line | Verdict | Why |
| --- | --- | --- | --- | --- |
| 1 | `spine_area: str \| None = None` | `:328` | **KEPT** | a property of the route, known at plan time |
| 2 | `total_audio_min: int` | `:329` | **DROPPED** | three options now, so one number is a lie; per-option time is `RouteOption.eta_seconds` |
| 3 | `stops: list[TripPreviewStop]` | `:330` | **DROPPED** | replaced by `options[].stops`; a single flat stop list cannot express three options |
| 4 | `candidate_eligible: bool = False` | `:331` | **DROPPED** | nothing is authored, so there is no candidate to be eligible |
| 5 | `candidate_status: Literal[...] \| None` | `:332` | **DROPPED** | same |
| 6 | `narration_kind: Literal["llm_candidate","none"]` | `:333` | **DROPPED** | AC-13: no LLM narration exists on this response, and an always-`"none"` field advertises a lane that cannot fire |
| 7 | `basic_tour: TripPreviewBasicTour \| None` | `:334` | **DROPPED** | the Basic lane is a *fallback from authoring*; it moves whole to the author route (step 11) |
| 8 | `lens_coverage_note: str \| None` | `:337` | **DROPPED** | dead today — both call sites pass `None` (`trips.py:987`, `:1123`); the live per-corridor note is already on `RouteOption.lens_coverage_note` (`contract.py:591`, filled at `options.py:122`) |
| 9 | `tourability: TripPreviewTourability \| None` | `:339` | **KEPT** | computed by planning (`trips.py:870-894`); the 2026-07-02 thin-tour disclosure |
| 10 | `compose_status: str \| None` | `:343` | **DROPPED** | nothing composed |
| 11 | `candidate_rejection: CandidateRejection \| None` | `:347` | **DROPPED** | no candidate |
| 12 | `provider: str \| None` | `:350` | **DROPPED** | no narrator ran |
| 13 | `degradations: list[dict]` | `:358` | **KEPT** | AC-18/AC-20: the routing degradation is discovered in PLAN and must ship on the PLAN response |
| 14 | `narration_quality: dict \| None` | `:362` | **DROPPED** | scores authored narration |
| 15 | `quality: dict \| None` | `:370` | **DROPPED** | `score_tour` runs on the authored script today (`trips.py:1082` + `:1105`); moving it to the plan would change what it judges |
| 16 | `options: list[RouteOption]` | — | **ADDED** | the three plans; `Field(default_factory=list)`, element type `src.tour.contract.RouteOption` |

Resulting model, in full — this is the exact replacement for
`src/api/models/trips.py:320-370`:

```python
class TripPreviewResponse(BaseModel):
    """The PLAN, and nothing else — three route options, no narration, no spend.

    BLOCK 1 of the two-block split. This endpoint selects POIs, orders and routes
    them, and prices the walk; it makes zero provider calls, so its output is free
    and it is what the operator chooses FROM. Authoring one chosen option is a
    separate call (POST /trips/preview/author). Everything that described authored
    narration — the stop list, the narrator, the candidate lane, the Basic
    fallback, the quality verdicts — moved there with it.
    """

    spine_area: str | None = None
    # The three flavours: same lens, duration, start and end; different POIs and
    # route (src/tour/selection.py:246-247). Each carries its own stops, eta and
    # per-corridor lens note. options[0] is the engine's own first pick.
    options: list[RouteOption] = Field(default_factory=list)
    # None = GREEN (no warning needed). RED never reaches a 200 response.
    tourability: TripPreviewTourability | None = None
    # EVERYTHING THAT SILENTLY DEGRADED while PLANNING this tour (owner ruling
    # 2026-07-31). A route built on estimated walking legs rather than measured
    # ones is labelled here rather than shipped silently. Empty list means nothing
    # degraded, which is a real statement rather than an absence.
    # See src/tour/degradations.py.
    degradations: list[dict] = Field(default_factory=list)
```

`RouteOption` is already imported in this module (`src/api/models/trips.py:11`).

**Status codes** for the plan-only endpoint:

| Code | When | Exact body |
| --- | --- | --- |
| 200 | success | `TripPreviewResponse` above |
| 422 | request-model validation (unknown lens, out-of-range lat) | FastAPI's own `{"detail": [ ... ]}` — unchanged |
| 422 | `TourInput` contradiction (end + round_trip) | `{"detail": {"reason": "invalid_tour_input", "errors": [...]}}` (`trips.py:184-193`) |
| 422 | tourability refusal | `{"detail": {"reason": <str(exc)>, "gap_minutes": <float\|None>, "alternatives": [...]}}` (`trips.py:207-221`) |
| 422 | duration too short to seat a stop / infeasible route | `{"detail": {"reason": "premium_route_infeasible", "detail": <engine text>, "gap_minutes": None, "alternatives": []}}` (§2.4) |

**Codes that DISAPPEAR from this endpoint** (they move to the author route in
step 11): `503` + `Retry-After` on provider throttle and `502` on other provider
faults (`trips.py:122-129`, reached today through `trips.py:1013`). A plan makes
no provider call, so neither is reachable.

### 3.2 Error mapping — what MOVES and what STAYS

The run-context names four things as moving. Precisely:

| Concern | Today | Plan-only handler | Author handler (step 11) |
| --- | --- | --- | --- |
| `_upstream_provider_errors` 502/503 (`trips.py:112-129`, used at `:1013`) | preview | **REMOVED** — unreachable, planning is provider-free (AC-2) | **PRESENT**, wrapping the execute + finalize pair, verbatim |
| Tourability refusal → 422 `_refusal_detail` (`trips.py:951-952`) | preview | **STAYS** — AC-24: planning is where a too-short duration is discovered | **ALSO PRESENT** — the author route re-plans, so it can see the same exception |
| Infeasible-route family → 422 (`trips.py:953-965`) | preview | **STAYS**, now via `_infeasible_detail` | **ALSO PRESENT**, identical |
| `resolve_build_identity()` pre-check → Basic lane (`trips.py:1001-1010`) | preview | **REMOVED** — a build fingerprint identifies an authored artifact; a plan authors nothing | **MOVES** here verbatim |
| `_basic_tour_fallback` (`trips.py:974-994`) | preview | **REMOVED** | **MOVES** here |
| Catch-all `except Exception` → Basic lane + the four log blocks (`trips.py:1027-1080`) | preview | **REMOVED** | **MOVES** here verbatim, including every log line |

**AC-24 in detail.** A duration too short to seat any tourable stop surfaces from
Block 1 as `CertificationPlanningInfeasibleError` — the live proof is
`tests/test_trip_preview_contract.py:270-319`, where a 60-minute request against
a lone anchor returns 422 with `"required 3240-3960s" in detail["detail"]`. The
plan-only handler must keep that branch. With `_infeasible_detail` the body gains
`gap_minutes: None`, so it has the reason / gap_minutes / alternatives shape
AC-24 asks for while the two existing assertions still pass unmodified. The
"reason naming the time budget" is carried by `detail`, in the engine's own
words; see BLOCKING AMBIGUITY B-1.

### 3.3 Exact handler rewrite

**Current block**: `src/api/routes/trips.py:897-1153` — the whole of
`preview_trip` plus `_preview_trip_impl`, from `@router.post("/trips/preview"...)`
through the closing `)` of the `TripPreviewResponse(...)` return at `:1153`.

**Exact replacement block** (`_preview_stops` at `:734-867` is already gone,
deleted by step 8; `_tourability_payload` at `:870-894` is unchanged and stays):

```python
_PREVIEW_ROUTE_ID = re.compile(r"^preview-([0-9a-f]{12})-opt(\d+)$")


def _preview_plan_fingerprint(plans) -> str:
    """Stable 12-hex identity of ONE plan result: the three options, in order.

    The author route re-derives the plan from the same request body, and this is
    what proves the option it authors is the option the operator was shown.
    Corpus or routing drift between the two calls changes the fingerprint, and the
    author route then refuses (409) rather than silently authoring a different
    tour. Ordered POI ids are the whole identity of an option — everything else
    (eta, dwell, vignettes) is a pure function of them plus the routing responses.
    """
    payload = json.dumps(
        [[poi.id for poi in plan.route.pois] for plan in plans],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def _plan_options(plans, snapshot, *, fingerprint: str) -> list:
    """The three plans as RouteOptions, through the ONE shared interleave."""
    beats_by_id = {ref.id: ref for refs in snapshot.beats_by_poi.values() for ref in refs}
    return [
        build_route_option(
            plan.route,
            plan.source,
            beats_by_id,
            route_id=f"preview-{fingerprint}-opt{i + 1}",
            snapshot=snapshot,
        )
        for i, plan in enumerate(plans)
    ]


def _plan_preview(tour_input: TourInput, driver: Driver):
    """BLOCK 1 for the anonymous surface: plan, refuse, or hand back three options.

    Shared by the plan-only preview and by the author route, which re-derives the
    same plan before authoring the option it was handed. Provider-free and $0.
    """
    snapshot = load_paris_corpus(driver, city_slug=tour_input.city_slug)
    try:
        with RoutingClient() as routing_client:
            plans = plan_premium_tour(tour_input, snapshot, routing_client=routing_client)
    except TourabilityRefusedError as exc:
        raise HTTPException(422, _refusal_detail(exc)) from exc
    except (
        CertificationPlanningInfeasibleError,
        PremiumRouteInfeasibleError,
        ValueError,
    ) as exc:
        raise HTTPException(422, _infeasible_detail(exc)) from exc
    return snapshot, plans


@router.post("/trips/preview", response_model=TripPreviewResponse)
def preview_trip(
    body: TripPreviewRequest,
    driver: Driver = Depends(get_driver),
):
    """Plan the tour. Three options, no narrator, no spend.

    BLOCK 1 of the two-block split: start (required), end (optional), lenses and
    timing in; three routed options out. It selects POIs, orders and routes them,
    computes ETA, dwell, vignettes and tourability, and calls no provider — so the
    operator chooses among real routes before anything is paid for. Authoring the
    chosen option is POST /trips/preview/author.

    OWNER RULING 2026-07-31: "Don't just log errors. Actually show them in the
    workbench UI. Otherwise, they're invisible." The degradation scope is opened
    here so a route built on estimated walking legs rather than measured ones is
    reported on the wire rather than in a log file nobody opens.
    """
    with degradation_scope() as collected:
        tour_input = _build_tour_input(
            start=(body.center_lat, body.center_lng),
            duration_min=body.duration_min or DEFAULT_DURATION_MIN,
            city_slug=body.city_slug,
            lenses=body.lenses or None,
            round_trip=body.round_trip,
            end=_end_point(body.end_lat, body.end_lng),
        )
        snapshot, plans = _plan_preview(tour_input, driver)
        options = _plan_options(
            plans, snapshot, fingerprint=_preview_plan_fingerprint(plans)
        )
        result = TripPreviewResponse(
            spine_area=plans[0].route.spine_area,
            options=options,
            tourability=_tourability_payload(plans[0].route.tourability),
        )
        rows = summarize(collected)
    return result.model_copy(update={"degradations": rows}) if rows else result
```

Mechanical consequences the developer must carry out in the same step:

- ADD `import hashlib` to the module header (`trips.py:5-9` block). `json` and
  `re` are already imported (`:5`, `:7`).
- The `request: Request` parameter is DROPPED from the preview route: it is
  unused today (`trips.py:899`, passed to `_preview_trip_impl` and never read).
  `Request` stays imported — `compose_trip` still takes it (`trips.py:486`).
- The `premium_executor` and `faithfulness_checker` dependencies are DROPPED
  from this route (`trips.py:902-903`). Both are still used by `compose_trip`
  (`trips.py:492-493`) and by the author route in step 11, so the imports of
  `get_premium_compose_executor`, `get_faithfulness_checker`,
  `PremiumComposeExecutor` and `FaithfulnessChecker` all stay.
- Imports that become unused at step 10 and MUST be removed or `make lint` fails
  (F401): `TripPreviewBasicTour`, `TripPreviewStop` (`trips.py:36`, `:39`) —
  only if step 11 does not re-add them; since step 11 does re-add
  `TripPreviewBasicTour`, remove it at step 10 and re-add it at step 11, or leave
  the step-10 diff lint-clean by checking `make lint` and acting on what it says.
  Also `score_narration` (`:58`), `score_tour` (`:70`), `EphemeralReceiptSink`,
  `execute_premium_plan`, `finalize_premium_tour`, `resolve_build_identity`
  (`:61-68`), `CandidateRejection`, `CandidateRejectionCode` (`:44-47`) — all
  move to step 11, so at step 10 they are dead. `sys` (`:8`) is used only by the
  catch-all log block (`trips.py:1049`) and returns in step 11.
  **Rule: run `make lint` unpiped and delete exactly what it names — do not
  guess this list.**
- `build_route_option` is already imported (`trips.py:59`).

### 3.4 Collateral — tests that go RED at step 10 and are NOT in its `files[]`

This is a real gap in the ledger and must be raised at approval, not absorbed
silently. The ledger lists only `tests/test_trip_preview_contract.py` and
`tests/test_premium_workbench_wiring.py` for step 10. These also break:

| File:line | What it reads | Required action |
| --- | --- | --- |
| `tests/test_trip_api.py:489-518` `TestPreviewTrip::test_preview_returns_per_stop_narration` | `candidate_eligible`, `narration_kind`, `stops`, `basic_tour`, `total_audio_min` | re-point at `options[0]["stops"]`; the LLM-lane half moves to the author route |
| `tests/test_workbench_matches_the_app.py:1971-1979` | asserts `{"candidate_eligible","basic_tour"} <= TripPreviewResponse.model_fields` | re-point at the author response model (§4.2) |
| `tests/test_workbench_matches_the_app.py:1889-1902` | iterates `TripPreviewResponse.model_fields` against `generateTourPreview` | survives mechanically (fewer fields), but re-point together with step 12 |
| `tests/test_trip_models.py:372-441` | constructs `TripPreviewResponse(total_audio_min=..., stops=[...])` | re-point at the new field set |
| `tests/test_trips_spend_and_authz.py:220-300` | `candidate_eligible`, `compose_status`, `basic_tour["reason"]` | re-point at the author route |
| `tests/test_workbench_ui.py:2266-2340` | Playwright stub bodies carrying `candidate_eligible`/`narration_kind`/`compose_status` | step 12 owns these; they must move in the same phase |

### 3.5 Tests INSIDE `tests/test_trip_preview_contract.py` — per-test verdict

| Test (line) | Verdict at step 10 |
| --- | --- |
| `test_preview_single_stop_that_cannot_fill_timebox_is_structured_422` (`:270`) | **UNCHANGED** — still 422, same reason and detail substring |
| `test_preview_round_trip_plus_end_is_422_not_500` (`:322`) | **UNCHANGED** |
| `test_preview_green_multi_stop_has_null_tourability_and_multiple_stops` (`:365`) | **RE-POINTED**: `_available_stops(body)` (`:56-59`) is replaced by `body["options"][0]["stops"]`; the `tourability is None` and per-stop-narration assertions are kept verbatim |
| `test_preview_returns_a_traced_premium_candidate_from_the_shared_path` (`:479`) | **MOVES to step 11** — it asserts the authored lane. Deleted at step 10, re-created at step 11 against `/trips/preview/author` with the same assertions |
| `test_preview_never_scores_or_returns_mixed_fallback_as_an_llm_candidate` (`:497`) | **MOVES to step 11**, same treatment |
| `test_preview_green_pool_but_materially_thin_delivery_is_422` (`:539`) | **UNCHANGED** |
| `_available_stops` helper (`:56-59`) | **DELETED** — its `candidate_eligible` branch no longer exists |

`tests/test_premium_workbench_wiring.py:212-222`
(`test_preview_uses_shared_premium_plan_and_finalizer`, AC-27/Q5) is **re-pointed,
not deleted**, to:

```python
def test_preview_uses_shared_premium_plan_and_finalizer() -> None:
    """The two blocks are two functions, and neither does the other's job."""
    plan_source = inspect.getsource(trips.preview_trip)
    assert "plan_premium_tour(" in inspect.getsource(trips._plan_preview)
    assert "execute_premium_plan(" not in plan_source
    assert "finalize_premium_tour(" not in plan_source

    author_source = inspect.getsource(trips.author_preview_tour)
    assert "execute_premium_plan(" in author_source
    assert "finalize_premium_tour(" in author_source
    assert "compose_script_per_chapter(" not in author_source
    assert "select_route(" not in author_source
```

Note this is one test spanning both steps: at step 10 it asserts only the first
block (the author half is added at step 11).

### 3.6 Proving test — step 10

- **File**: `tests/test_trip_preview_contract.py`
- **Function**: `test_preview_returns_three_options_and_spends_nothing`
- **Node id**: `tests/test_trip_preview_contract.py::test_preview_returns_three_options_and_spends_nothing`
- **Placement**: after `_green_cluster_records` (`:445-476`).

Stubs built:

- `make_client` fixture (`:246-262`) — existing: `_FakeDriver` (`:109-114`) over
  canned Cypher records, `_FakeRoutingClient` (`:117-194`, deterministic
  pace-corrected haversine with a full `ValhallaLegReceipt`), and
  `resolve_build_identity` monkeypatched.
  **Delete the `resolve_build_identity` monkeypatch line (`:252-255`) at step 10**
  — the plan-only route no longer imports that name, so the `monkeypatch.setattr`
  would raise `AttributeError`. Step 11 re-adds it.
- `_green_cluster_records()` (`:445`) — existing: six tier-5 POIs 40-90 m apart,
  five 240-second beats each.
- **NEW** `_ExplodingExecutor`, defined in this module immediately above the
  test:

  ```python
  class _ExplodingExecutor:
      """Any provider call at all is the failure this test exists to catch."""

      cost_bearing = True
      provider_name = "anthropic"

      def execute(self, unit):  # noqa: ARG002 - the call itself is the failure
          raise AssertionError("the plan-only preview called the narrator")
  ```

  Installed with
  `client.app.dependency_overrides[get_premium_compose_executor] = _ExplodingExecutor`
  (the same mechanism as `:516`), and removed in a `finally`.

Assertions, in this order:

1. `r = client.post("/api/v1/trips/preview", json={"center_lat": START[0],
   "center_lng": START[1], "duration_min": 30})`; `assert r.status_code == 200,
   r.text` — the exploding executor never fired, which is the $0 proof (AC-2).
2. `body = r.json()`; `assert len(body["options"]) == 3`.
3. Each option's `route_id` matches `^preview-[0-9a-f]{12}-opt[123]$`, and the
   twelve-hex fingerprint is the SAME across all three.
4. Each option has a non-empty `stops` list and `eta_seconds > 0`.
5. Pairwise Jaccard over the three dwell stop-id sets is `< 0.60`
   (`src/tour/selection.py:246-247`) — AC-3.
6. `assert body["degradations"] == []` — the field exists and is a real
   statement, not an absence.
7. AC-13, spelled out: for every key in
   `{"stops", "narration_kind", "basic_tour", "candidate_eligible",
   "candidate_status", "candidate_rejection", "compose_status", "provider",
   "narration_quality", "quality", "total_audio_min", "lens_coverage_note"}`,
   `assert key not in body`.
8. No authored text leaked into the options: no stop in any option carries a key
   named `"script"` or `"script_body"`.
9. AC-24, in the same node id: a second POST with the lone-anchor records from
   `test_preview_single_stop_that_cannot_fill_timebox_is_structured_422`
   (`:281-303`) and `duration_min=60` returns `422`, and
   `set(detail) >= {"reason", "gap_minutes", "alternatives"}`,
   `detail["gap_minutes"] is None`, `detail["alternatives"] == []`, and
   `"required" in detail["detail"]` — the time budget is named.

- **MUTATION** (one line of production code, `src/api/routes/trips.py`, inserted
  into `preview_trip` immediately after the `_plan_options(...)` call):

  ```python
          execute_premium_plan(plans[0], executor=premium_executor, receipt_sink=EphemeralReceiptSink())
  ```

  Re-introducing any authoring call makes `_ExplodingExecutor` raise, so
  assertion 1 fails with a 500. This is exactly the fix being undone: "the
  preview spends nothing".

---

## 4. STEP 11 — a sibling ANONYMOUS route authors the one option chosen

> **CONDITIONAL ON OWNER APPROVAL.** Open question Q4 (`state.json:19`,
> `run-context.md:78-79`) — "a second anonymous paid route for the Phase-1
> window" — has NOT been answered. This route is anonymous and paid, so it
> inherits the exposure recorded at `trips.py:132-143`: nothing bounds what an
> unauthenticated caller can spend, and step 5 removes the stop cap, so duration
> alone bounds the number of paid calls. Phase 2 closes this by moving the
> workbench onto authenticated `/trips/generate` + `/trips/{id}/compose`. If the
> owner refuses Q4, **step 11 is not implemented and step 12 is blocked**; the
> workbench cannot author at all in the Phase-1 window. This contract is written
> so that an approval is immediately actionable, and it changes nothing until
> that approval exists.

### 4.1 The route

- **Method / path**: `POST /api/v1/trips/preview/author`
- **Module**: a new route function in `src/api/routes/trips.py`. No new file
  (AC-30).
- **Function name**: `author_preview_tour`
- **Auth**: none, matching `/trips/preview`.
- **Dependencies**: `driver: Driver = Depends(get_driver)`,
  `premium_executor: PremiumComposeExecutor = Depends(get_premium_compose_executor)`,
  `faithfulness_checker: FaithfulnessChecker | None = Depends(get_faithfulness_checker)`
  — the same three the preview carries today (`trips.py:901-903`).

### 4.2 Request model — exact

Add to `src/api/models/trips.py`, immediately after `TripPreviewRequest`
(`:195-253`):

```python
class TripPreviewAuthorRequest(TripPreviewRequest):
    """The SAME plan inputs, plus which of the three options to author.

    It subclasses the preview request rather than restating it: the author route
    re-derives the plan, so every field that fed the plan must be echoed back
    unchanged, and one shared definition is what guarantees "unchanged" (including
    the unknown-lens 422 at TripPreviewRequest.validate_lenses).
    """

    route_id: str = Field(
        ...,
        description="The chosen option's route_id, copied verbatim from the "
        "preview response: 'preview-<12 hex>-optN'. The hex is the plan's "
        "fingerprint; N selects the option. A fingerprint that no longer matches "
        "a freshly derived plan is a 409, never a silently different tour.",
    )
```

Full field list for the request — 9 fields, 8 inherited plus 1:

| Field | Type | Required | Default | Validation |
| --- | --- | --- | --- | --- |
| `center_lat` | `float` | yes | — | `ge=-90, le=90` |
| `center_lng` | `float` | yes | — | `ge=-180, le=180` |
| `end_lat` | `float \| None` | no | `None` | `ge=-90, le=90` |
| `end_lng` | `float \| None` | no | `None` | `ge=-180, le=180` |
| `duration_min` | `int \| None` | no | `None` | `ge=1, le=600` |
| `lenses` | `list[str] \| None` | no | `None` | `validate_lenses` (`models/trips.py:213-249`) |
| `round_trip` | `bool` | no | `False` | — |
| `city_slug` | `str` | no | `"paris"` | `_validate_city_slug` |
| `route_id` | `str` | **yes** | — | must match `^preview-[0-9a-f]{12}-opt(\d+)$`; a non-match is a 422 (§4.4) |

The selector is deliberately the single `route_id` string, which is exactly the
shape `TripComposeRequest.route_id` already uses on the persisted path
(`models/trips.py:172-177`, parsed at `trips.py:536-539`). One field, one regex,
one precedent.

### 4.3 Response model — exact

Add to `src/api/models/trips.py`, after `TripPreviewResponse`. Every field name
and type is lifted unchanged from today's `TripPreviewResponse` so no client
field is invented; the verdict column says where each came from.

| # | Field | Type | Default | Source |
| --- | --- | --- | --- | --- |
| 1 | `route_id` | `str` | required | ADDED — echo of the request, like `TripComposeResponse.route_id` (`models/trips.py:190`) |
| 2 | `option` | `RouteOption \| None` | `None` | ADDED — the AUTHORED option: same POI ids, order, eta, vignettes as the plan option, with the authored narration on its stops. This is what proves AC-8 on the wire |
| 3 | `spine_area` | `str \| None` | `None` | KEPT from `TripPreviewResponse:328` |
| 4 | `total_audio_min` | `int` | required | KEPT from `:329` |
| 5 | `candidate_eligible` | `bool` | `False` | KEPT from `:331` |
| 6 | `candidate_status` | `Literal["premium_candidate_eligible_for_certification"] \| None` | `None` | KEPT from `:332` |
| 7 | `narration_kind` | `Literal["llm_candidate", "none"]` | `"none"` | KEPT from `:333` |
| 8 | `basic_tour` | `TripPreviewBasicTour \| None` | `None` | KEPT from `:334`, with whatever element type step 8 left on it |
| 9 | `tourability` | `TripPreviewTourability \| None` | `None` | KEPT from `:339` |
| 10 | `compose_status` | `str \| None` | `None` | KEPT from `:343` |
| 11 | `candidate_rejection` | `CandidateRejection \| None` | `None` | KEPT from `:347` |
| 12 | `provider` | `str \| None` | `None` | KEPT from `:350` |
| 13 | `degradations` | `list[dict]` | `default_factory=list` | KEPT from `:358` |
| 14 | `narration_quality` | `dict \| None` | `None` | KEPT from `:362` |
| 15 | `quality` | `dict \| None` | `None` | KEPT from `:370` |

Dropped relative to today's `TripPreviewResponse`: `stops` (the authored stops
are `option.stops`, through the one shared interleave — AC-17) and
`lens_coverage_note` (dead; the live one is on `RouteOption`).

```python
class TripAuthoredTourResponse(BaseModel):
    """BLOCK 2's output: the ONE option the operator chose, now narrated.

    Never re-plans. Its POI ids, order, eta_seconds and vignettes are the chosen
    option's, unchanged — only the narration is new. The Basic lane, the narrator
    name and the quality verdicts live here because they describe authored text,
    which the plan-only preview no longer has.
    """

    route_id: str
    option: RouteOption | None = None
    spine_area: str | None = None
    total_audio_min: int
    candidate_eligible: bool = False
    candidate_status: Literal["premium_candidate_eligible_for_certification"] | None = None
    narration_kind: Literal["llm_candidate", "none"] = "none"
    basic_tour: TripPreviewBasicTour | None = None
    tourability: TripPreviewTourability | None = None
    compose_status: str | None = None
    candidate_rejection: CandidateRejection | None = None
    provider: str | None = None
    degradations: list[dict] = Field(default_factory=list)
    narration_quality: dict | None = None
    quality: dict | None = None
```

### 4.4 Status codes and exact bodies

| Code | When | Exact body |
| --- | --- | --- |
| 200 | authored | `TripAuthoredTourResponse` with `candidate_eligible=True`, `narration_kind="llm_candidate"`, `compose_status="composed"`, `option` set |
| 200 | authoring failed or was ineligible (Basic lane) | `TripAuthoredTourResponse` with `candidate_eligible=False`, `narration_kind="none"`, `compose_status="basic_available"`, `option=None`, `basic_tour` set, `candidate_rejection` set — byte-identical in shape to `_basic_tour_fallback` today (`trips.py:974-994`) |
| 422 | request-model validation | FastAPI's own `{"detail": [...]}` |
| 422 | `route_id` does not match the regex | `{"detail": {"reason": "invalid_route_id", "route_id": <as sent>}}` |
| 422 | `TourInput` contradiction | `{"detail": {"reason": "invalid_tour_input", "errors": [...]}}` |
| 422 | tourability refusal on the re-derived plan | `{"detail": {"reason": <str(exc)>, "gap_minutes": ..., "alternatives": [...]}}` |
| 422 | infeasible route on the re-derived plan | `{"detail": {"reason": "premium_route_infeasible", "detail": ..., "gap_minutes": None, "alternatives": []}}` |
| 404 | option number outside `1..len(plans)` | `{"detail": {"reason": "unknown_option", "route_id": <as sent>, "options": <len(plans)>}}` |
| 409 | fingerprint mismatch — the plan moved under the operator | `{"detail": {"reason": "plan_changed", "route_id": <as sent>, "current_route_id": "preview-<new hex>-opt<N>"}}` |
| 502 | provider fault (`trips.py:128-129`) | `{"detail": "LLM provider error: ..."}` |
| 503 | provider throttle (`trips.py:122-127`) | `{"detail": "LLM provider rate limited: ..."}` + header `Retry-After: 30` |

404-not-403 reasoning does not apply here: there is no ownership to conceal.
`unknown_option` is a 404 to mirror the persisted path's unknown-`route_id`
handling (`trips.py:539`).

### 4.5 Exact handler

```python
@router.post("/trips/preview/author", response_model=TripAuthoredTourResponse)
def author_preview_tour(
    body: TripPreviewAuthorRequest,
    driver: Driver = Depends(get_driver),
    premium_executor: PremiumComposeExecutor = Depends(get_premium_compose_executor),
    faithfulness_checker: FaithfulnessChecker | None = Depends(get_faithfulness_checker),
):
    """Author EXACTLY the option the operator chose. Never re-plans it.

    BLOCK 2 of the split, on the anonymous surface. It re-derives the free plan
    from the same request body, checks the plan is still the one the operator was
    shown (the fingerprint inside route_id), and authors that one option — one
    zero-retry provider call per dwell stop. Nothing here chooses a route: the
    route arrived with the request.

    ANONYMOUS AND PAID, for the Phase-1 window only. Per the note at
    trips.py:132-143 nothing bounds what an unauthenticated caller spends here,
    and with the stop cap removed the duration is the only bound on the paid call
    count. Phase 2 closes this by moving the workbench onto the authenticated
    /trips/generate + /trips/{id}/compose pair.
    """
    with degradation_scope() as collected:
        result = _author_preview_impl(body, driver, premium_executor, faithfulness_checker)
        rows = summarize(collected)
    return result.model_copy(update={"degradations": rows}) if rows else result


def _author_preview_impl(
    body: TripPreviewAuthorRequest,
    driver: Driver,
    premium_executor: PremiumComposeExecutor,
    faithfulness_checker: FaithfulnessChecker | None,
) -> TripAuthoredTourResponse:
    match = _PREVIEW_ROUTE_ID.match(body.route_id)
    if match is None:
        raise HTTPException(422, {"reason": "invalid_route_id", "route_id": body.route_id})
    chosen_fingerprint, option_n = match.group(1), int(match.group(2))

    tour_input = _build_tour_input(
        start=(body.center_lat, body.center_lng),
        duration_min=body.duration_min or DEFAULT_DURATION_MIN,
        city_slug=body.city_slug,
        lenses=body.lenses or None,
        round_trip=body.round_trip,
        end=_end_point(body.end_lat, body.end_lng),
    )
    snapshot, plans = _plan_preview(tour_input, driver)
    if not 1 <= option_n <= len(plans):
        raise HTTPException(
            404,
            {"reason": "unknown_option", "route_id": body.route_id, "options": len(plans)},
        )
    # THE OPERATOR'S OPTION, OR NOTHING. Planning is free and deterministic given
    # the same corpus and the same routing answers, but neither is frozen between
    # the two calls: a beat upload or a Valhalla restart moves the plan. The
    # fingerprint makes that visible instead of authoring a tour the operator
    # never saw and could not tell apart.
    fingerprint = _preview_plan_fingerprint(plans)
    if fingerprint != chosen_fingerprint:
        raise HTTPException(
            409,
            {
                "reason": "plan_changed",
                "route_id": body.route_id,
                "current_route_id": f"preview-{fingerprint}-opt{option_n}",
            },
        )

    plan = plans[option_n - 1]
    route = plan.route
    beats_by_id = {ref.id: ref for refs in snapshot.beats_by_poi.values() for ref in refs}
    provider = premium_executor.provider_name

    def _basic_tour_fallback(
        *, reason: str, rejection: CandidateRejection
    ) -> TripAuthoredTourResponse:
        return TripAuthoredTourResponse(
            route_id=body.route_id,
            option=None,
            spine_area=route.spine_area,
            total_audio_min=0,
            candidate_eligible=False,
            narration_kind="none",
            basic_tour=TripPreviewBasicTour(
                reason=reason,
                total_audio_min=round(plan.source.total_audio_seconds / 60),
                stops=_basic_tour_stops(plan, beats_by_id, snapshot),
            ),
            tourability=_tourability_payload(route.tourability),
            compose_status="basic_available",
            candidate_rejection=rejection,
            provider=provider,
            narration_quality=None,
            quality=None,
        )

    # Resolved BEFORE any physical call: an unresolvable build fingerprint (dirty
    # local tree, malformed deploy SHA) is an environment/config fault, not an LLM
    # authoring failure — it must never be folded into the generic provider-failure
    # branch below, which would both mislabel the cause and hide that ZERO provider
    # spend happened.
    try:
        build_identity = resolve_build_identity()
    except Exception as exc:
        return _basic_tour_fallback(
            reason="llm_candidate_ineligible",
            rejection=CandidateRejection(
                code=CandidateRejectionCode.BUILD_FINGERPRINT_UNAVAILABLE,
                detail=str(exc),
            ),
        )

    try:
        with _upstream_provider_errors():
            physical_responses = execute_premium_plan(
                plan,
                executor=premium_executor,
                receipt_sink=EphemeralReceiptSink(),
            )
            premium_result = finalize_premium_tour(
                plan,
                physical_responses,
                faithfulness_checker=faithfulness_checker,
                build_identity=build_identity,
            )
    except HTTPException:
        raise
    except Exception:
        <<< the ENTIRE except-block body from trips.py:1028-1080, verbatim,
            including the four logging blocks and the closing
            return _basic_tour_fallback(reason="llm_generation_failed", ...) >>>

    script = premium_result.blueprint.script
    narration = " ".join(s.text for s in script.script)
    q = score_narration(narration)
    narration_quality = { <<< the 10 keys from trips.py:1086-1097, verbatim >>> }
    rubric = score_tour(script, route, snapshot.beats_by_poi, beat_sequence=plan.sequence)

    # AC-8: the AUTHORED option is the CHOSEN option with new narration — same POI
    # ids, same order, same eta_seconds, same vignettes. It is built by the one
    # shared interleave from the SAME route object the plan produced, so there is
    # nothing to re-derive and nothing to hand-restore.
    authored_option = build_route_option(
        route,
        script,
        beats_by_id,
        route_id=body.route_id,
        snapshot=snapshot,
    )
    return TripAuthoredTourResponse(
        route_id=body.route_id,
        option=authored_option,
        spine_area=route.spine_area,
        total_audio_min=round(script.total_audio_seconds / 60),
        candidate_eligible=True,
        candidate_status="premium_candidate_eligible_for_certification",
        narration_kind="llm_candidate",
        basic_tour=None,
        tourability=_tourability_payload(route.tourability),
        compose_status="composed",
        candidate_rejection=None,
        provider=provider,
        narration_quality=narration_quality,
        quality={ <<< the 5 keys from trips.py:1129-1151, verbatim >>> },
    )
```

Two placeholders above are literal copy-outs, not designs — copy the lines from
the file, unchanged:

- `<<< the ENTIRE except-block body from trips.py:1028-1080 >>>` — the
  log-before-swallowing block, all four loops (`UNTRACEABLE`, `UNFAITHFUL`,
  `DROPPED-FACT`) and the final `return _basic_tour_fallback(...)`. The two
  `body.city_slug` / `body.duration_min` arguments at `trips.py:1040-1041` still
  resolve; `len(premium_plan.units)` at `:1042` becomes `len(plan.units)`.
- `<<< the 10 keys / the 5 keys >>>` — the `narration_quality` dict
  (`trips.py:1086-1097`) and the `quality` dict (`trips.py:1129-1151`), copied
  character for character.

`_basic_tour_stops(plan, beats_by_id, snapshot)` is whatever step 8 leaves as the
producer of `TripPreviewBasicTour.stops` after `_preview_stops` is deleted. If
step 8 makes `TripPreviewBasicTour.stops` a `RouteOption`, pass
`build_route_option(route, plan.source, beats_by_id, route_id=body.route_id,
snapshot=snapshot)` and adjust the model accordingly — **this contract does not
choose that shape**; it consumes it.

### 4.6 Determinism — the honest verdict

The author route re-runs the free planner and must land on the same option N.
What guarantees the rebuild, and what does not:

**Guaranteed identical, given identical inputs.** The planning path is a pure
function of `(TourInput, CorpusSnapshot, routing answers)`:

- `select_k_routes` → `select_route` with a deterministic diversity penalty
  (`src/tour/selection.py:2168-2190`); no `random`, no `uuid`, no clock. A
  repository-wide grep over `src/tour/*.py` for `import random`, `random.`,
  `uuid`, `time.time()` and `datetime.now` returns exactly two hits, both
  clock-only: `src/tour/generation.py:424` (`generated_at` metadata on the
  Script) and `src/tour/premium_tour.py:297` (which passes that clock in).
  Neither feeds route selection, ordering, or any hash used for identity —
  `grounded_source_sha256` is computed over the sentences alone
  (`premium_tour.py:308`, `sentences_payload_sha256`).
- The corpus load is explicitly ordered (`ORDER BY p.id`,
  `src/tour/selection.py:607-624`) with the stated reason: "snapshot.pois must be
  identical across two loads of the same graph or greedy tie-breaks drift between
  runs".

**Every input the client must echo back**, all of them carried by
`TripPreviewAuthorRequest` inheriting `TripPreviewRequest`: `center_lat`,
`center_lng`, `end_lat`, `end_lng`, `duration_min`, `lenses`, `round_trip`,
`city_slug`. Sending a different value for any of them changes the plan. The
workbench must send the byte-identical body it sent to `/trips/preview` (step 12
owns that).

**Not guaranteed — the correctness hole, stated plainly.** Two inputs are NOT
under the client's control and are NOT frozen between the two calls:

1. **The corpus.** `load_paris_corpus` reads the live graph on each call
   (`trips.py:943`, and again in the author route). A beat upload, a POI edit or
   a dedup run between the two calls changes the candidate pool and therefore the
   options.
2. **Valhalla.** Leg times come from a live network dependency
   (`render.yaml:98-124`, `ondoway-valhalla`, a Render private service that can
   cold-start, restart or rebuild tiles). A restart changes measured legs to
   estimated ones, which changes the time budget and therefore the seated stops.

So the rebuild **cannot be guaranteed identical**. That is why the option
selector carries a fingerprint rather than a bare index: the mismatch is
*detected* and refused with 409 `plan_changed` instead of authoring — and
charging for — a tour the operator never saw and could not distinguish on screen.
Detection is not prevention. Prevention needs the plan to be held between the two
calls (server-side, or signed and echoed in full), which is persistence, and
persistence is explicitly Phase 2 (`00-brief.md:49-54`). Recorded here as a known
residual, not resolved.

A third, smaller source: Python's per-process string hash randomization would
matter only if a set's iteration order leaked into route output. I did not audit
all 3000 lines of `src/tour/selection.py` for that, so I do not assert it is
clean — but it cannot affect this route within one server process, where the seed
is fixed, and the fingerprint would catch it across processes.

### 4.7 Proving test — step 11

- **File**: `tests/test_trip_preview_contract.py`
- **Function**: `test_preview_compose_authors_only_the_chosen_option`
- **Node id**: `tests/test_trip_preview_contract.py::test_preview_compose_authors_only_the_chosen_option`

Stubs built:

- `make_client` (`:246-262`) with the `resolve_build_identity` monkeypatch line
  RESTORED (it was removed at step 10) — now targeting
  `src.api.routes.trips.resolve_build_identity`, which the author route imports.
- `_green_cluster_records()` (`:445`).
- **NEW** `_CountingExecutor` in this module — modelled on
  `tests/test_trip_api.py:579-603`:

  ```python
  class _CountingExecutor:
      """Records which stop each physical call was for; echoes the stitch back."""

      cost_bearing = True
      provider_name = "anthropic"

      def __init__(self) -> None:
          self.stop_calls: list[int] = []
          self._lock = threading.Lock()

      def execute(self, unit):
          with self._lock:
              self.stop_calls.append(unit.stop_index)
          body = json.dumps(
              {"sentences": [s.model_dump(mode="json") for s in unit.authorized_request.stitched.script]},
              ensure_ascii=False, separators=(",", ":"), sort_keys=True,
          ).encode("utf-8")
          return PhysicalProviderResponse(
              body=body, input_tokens=0, output_tokens=0, latency_ms=0,
              model=COMPOSE_MODEL, provider_request_id=f"offline-{unit.stop_index}",
              stop_reason="end_turn",
          )
  ```

  New imports for the test module: `threading`,
  `from src.tour.authoring import COMPOSE_MODEL`,
  `from src.tour.certification_provider import PhysicalProviderResponse`.

Assertions, in this order:

1. `plan = client.post("/api/v1/trips/preview", json=PLAN_BODY)`; 200; three
   options. `chosen = plan.json()["options"][1]` — option **2**, never option 1,
   so "authored the first one regardless" cannot pass.
2. Install `_CountingExecutor` via
   `client.app.dependency_overrides[get_premium_compose_executor]`.
3. `r = client.post("/api/v1/trips/preview/author", json={**PLAN_BODY,
   "route_id": chosen["route_id"]})`; `assert r.status_code == 200, r.text`.
4. `assert sorted(exec_.stop_calls) == list(range(n_dwell))` where `n_dwell` is
   the number of `band == "dwell"` stops in `chosen` — one paid call per dwell
   stop, no retries, none for any other option.
5. AC-8, the whole of it in one line:
   `assert body["option"]["stops"] == chosen["stops"]` is NOT asserted (narration
   differs). Instead assert field by field:
   - `body["option"]["route_id"] == chosen["route_id"]`
   - `[s["poi_id"] for s in body["option"]["stops"]] == [s["poi_id"] for s in chosen["stops"]]`
   - `[s["band"] for s in body["option"]["stops"]] == [s["band"] for s in chosen["stops"]]`
   - `body["option"]["eta_seconds"] == chosen["eta_seconds"]`
   - `body["option"]["lens_coverage_note"] == chosen["lens_coverage_note"]`
6. `body["narration_kind"] == "llm_candidate"`, `body["compose_status"] ==
   "composed"`, `body["candidate_eligible"] is True`, `body["provider"] ==
   "anthropic"`, `body["basic_tour"] is None`, `body["quality"] is not None`,
   `body["narration_quality"] is not None`.
7. Unknown option: same body with `route_id` ending `-opt9` → `404`, and
   `detail["reason"] == "unknown_option"`.
8. Malformed selector: `route_id="not-a-route-id"` → `422`, and
   `detail["reason"] == "invalid_route_id"`.
9. Stale fingerprint: `route_id="preview-000000000000-opt2"` → `409`, and
   `detail["reason"] == "plan_changed"`, and `exec_.stop_calls` is unchanged from
   step 4 — a refused author costs nothing.

- **MUTATION** (one line of production code, in `_author_preview_impl`): change

  ```python
      plan = plans[option_n - 1]
  ```
  to
  ```python
      plan = plans[0]
  ```

  Option 1 is authored while `route_id` says option 2, so assertion 5's POI-id
  equality fails. Deterministically RED: assertion 5's list comes from the
  preview's own option 2, and the three options share under 60% of their stops by
  construction (`src/tour/selection.py:246-247`), so option 1's ordered ids cannot
  equal option 2's.

Also created at step 11 (moved from step 10, §3.5), against the author route
with their assertions otherwise unchanged:
`test_preview_returns_a_traced_premium_candidate_from_the_shared_path`
(from `:479`) and
`test_preview_never_scores_or_returns_mixed_fallback_as_an_llm_candidate`
(from `:497`, whose `FailingExecutor` at `:503-508` moves with it).

---

## 5. STEP 15 — generate and compose report what degraded

### 5.1 Field deltas — exact

**`TripGenerateResponse`** (`src/api/models/trips.py:150-169`), 10 fields today:

| # | Field | Verdict |
| --- | --- | --- |
| 1 | `trip_id: str` | KEPT |
| 2 | `trip_name: str` | KEPT |
| 3 | `profile_id: str` | KEPT |
| 4 | `total_stops: int` | KEPT |
| 5 | `total_duration_min: int` | KEPT |
| 6 | `anchor_count: int` | KEPT |
| 7 | `flavour_count: int` | KEPT |
| 8 | `lens_coverage: dict[str, int]` | KEPT |
| 9 | `stops: list[GeneratedStop]` | KEPT |
| 10 | `options: list[RouteOption]` | KEPT |
| 11 | `degradations: list[dict]` | **ADDED** |

**`TripComposeResponse`** (`src/api/models/trips.py:180-192`), 4 fields today:

| # | Field | Verdict |
| --- | --- | --- |
| 1 | `trip_id: str` | KEPT |
| 2 | `route_id: str` | KEPT |
| 3 | `attempts: int` | KEPT |
| 4 | `stops: list[GeneratedStop]` | KEPT |
| 5 | `degradations: list[dict]` | **ADDED** |

The added field is identical on both, and identical to the one already on the
preview response (`models/trips.py:358`) — same name, same type, same default, so
one client parser reads all three:

```python
    # EVERYTHING THAT SILENTLY DEGRADED while building this tour (owner ruling
    # 2026-07-31: "Don't just log errors. Actually show them in the workbench UI.
    # Otherwise, they're invisible."). Each row carries BOTH registers — `human`
    # is plain English with no identifiers, `error_type`/`error_message`/
    # `component`/`context` are what gets pasted to Claude to fix it. Empty list
    # means nothing degraded, which is a real statement rather than an absence.
    # The preview has carried this since 2026-07-31; the phone's two endpoints
    # dropped it on the floor. See src/tour/degradations.py.
    degradations: list[dict] = Field(default_factory=list)
```

`list_trips` also constructs `TripGenerateResponse` (`trips.py:1176-1188`) and is
NOT changed: the default makes the added field absent-safe there, and a stored
trip has no live degradations to report.

### 5.2 Exact handler rewrites

Both follow the pattern the preview already uses (`trips.py:912-919`): the route
function becomes a thin wrapper owning the collection scope, and the body moves
to an `_impl` that never threads a collector.

**Generate.** Rename `generate_trip` (`trips.py:281`) to `_generate_trip_impl`,
dropping its decorator and its `Depends(...)` defaults (they become plain
positional parameters `body, current_user, session, driver`), and add above it:

```python
@router.post("/trips/generate", response_model=TripGenerateResponse, status_code=201)
def generate_trip(
    body: TripGenerateRequest,
    current_user: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
    driver: Driver = Depends(get_driver),
):
    """Generate a trip, and hand back everything that quietly degraded doing it.

    OWNER RULING 2026-07-31: a soft failure that only reaches a log file is
    indistinguishable from success to the person looking at the screen. The
    workbench has shown these since then; the phone's own generate call threw
    them away, so a tour planned on estimated walking legs looked identical to one
    planned on measured ones.

    The real work is ``_generate_trip_impl``; this wrapper owns the collection
    scope so the implementation never threads a collector through, and so a
    threaded fan-out cannot leak one request's degradations into another's.
    """
    with degradation_scope() as collected:
        result = _generate_trip_impl(body, current_user, session, driver)
        rows = summarize(collected)
    return result.model_copy(update={"degradations": rows}) if rows else result
```

**Compose.** Identically: rename `compose_trip` (`trips.py:485`) to
`_compose_trip_impl` and add the wrapper, preserving every parameter including
`request: Request` and `trip_id: str`:

```python
@router.post("/trips/{trip_id}/compose", response_model=TripComposeResponse)
def compose_trip(
    request: Request,
    trip_id: str,
    body: TripComposeRequest,
    current_user: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
    driver: Driver = Depends(get_driver),
    premium_executor: PremiumComposeExecutor = Depends(get_premium_compose_executor),
    faithfulness_checker: FaithfulnessChecker | None = Depends(get_faithfulness_checker),
):
    """Compose a trip, and hand back everything that quietly degraded doing it.

    Same collection scope as generate and preview — see generate_trip. The
    per-stop fan-out records inside worker threads, which is why the scope must be
    opened OUTSIDE it (src/tour/degradations.py:86-121).
    """
    with degradation_scope() as collected:
        result = _compose_trip_impl(
            request, trip_id, body, current_user, session, driver,
            premium_executor, faithfulness_checker,
        )
        rows = summarize(collected)
    return result.model_copy(update={"degradations": rows}) if rows else result
```

Nothing inside either `_impl` changes. Both raise `HTTPException` on refusal, and
an exception propagates out of the `with` block exactly as it does in the preview
today — a refusal carries no degradations, which is unchanged behaviour.

### 5.3 Proving test — step 15

- **File**: `tests/test_trip_api.py`
- **Function**: `test_generate_and_compose_report_what_degraded`
- **Node id**: `tests/test_trip_api.py::test_generate_and_compose_report_what_degraded`
- **Placement**: module level, `@needs_neo4j`, after
  `test_compose_authors_per_stop_and_keeps_the_wire_contract` (`:650`).

Stubs built:

- `client` (`:119-133`) and `cutover_trip` (`:641-646`) — existing fixtures.
- **NEW** a `monkeypatch` wrapper that records one degradation from inside the
  request, so the test proves the CHANNEL rather than any particular engine
  failure:

  ```python
  def _recording_corpus_loader(monkeypatch):
      from src.api.routes import trips as trips_route

      real = trips_route.load_paris_corpus

      def _wrapped(*args, **kwargs):
          record(
              kind="test_probe",
              human="A probe recorded one degradation so the channel can be seen.",
              component="tests.test_trip_api",
          )
          return real(*args, **kwargs)

      monkeypatch.setattr(trips_route, "load_paris_corpus", _wrapped)
  ```

  Import: `from src.tour.degradations import record`.

Assertions, in this order:

1. With the wrapper installed, `POST /api/v1/trips/generate` → 201, and
   `[row["kind"] for row in body["degradations"]] == ["test_probe"]`, and the row
   carries `human`, `component`, `error_type`, `error_message`, `context` and
   `count` — the six keys `summarize` emits (`src/tour/degradations.py:159-166`).
2. `POST /api/v1/trips/{cutover_trip}/compose` with `route_id =
   f"{trip_id}-opt1"` → 200, and the same one-row assertion on
   `body["degradations"]`.
3. Without the wrapper (a second, clean generate), `body["degradations"] == []` —
   the field is a real empty statement, not a missing key.

- **MUTATION** (one line of production code, in `generate_trip`): change

  ```python
      return result.model_copy(update={"degradations": rows}) if rows else result
  ```
  to
  ```python
      return result
  ```

  The row is collected and then dropped, which is precisely the defect ("logged,
  never shown"), and assertion 1 goes RED.

---

## 6. BLOCKING AMBIGUITY

**B-1 — AC-24's "a reason naming the time budget" (LOW, default is safe).**
AC-24 requires the too-short refusal to carry the reason / gap_minutes /
alternatives shape "with a reason naming the time budget". Today the machine
`reason` for this refusal is the constant `"premium_route_infeasible"`
(`trips.py:961`) and the human text naming the seconds ("required 3240-3960s") is
in `detail` — proven by the live assertion at
`tests/test_trip_preview_contract.py:318`. **Recommendation: keep
`reason="premium_route_infeasible"` and add `gap_minutes: None` (§2.4).** It
satisfies the shape, names the budget in `detail`, and keeps two existing tests
green verbatim. Changing the machine `reason` string instead would break those
two and give clients a new enum value for no gain. Proceed on the recommendation
unless the owner says the machine `reason` itself must change.

**B-2 — Q4: the second anonymous paid route (HIGH, genuinely blocking step 11).**
`/trips/preview/author` is anonymous and paid, and with the stop cap removed
(param 1) only the requested duration bounds the number of paid calls a stranger
can trigger. This is the exposure already recorded in the code at
`trips.py:132-143`. **Recommendation: approve it for the Phase-1 window**, because
without it the workbench has no way to author at all once the preview goes
plan-only, and step 12 is blocked; the exposure is not new (today's
`/trips/preview` already authors anonymously on every call) and Phase 2 closes it
by moving the workbench onto the authenticated pair. If the owner refuses, steps
11-13 must be re-planned and Phase 2's auth work pulled forward.

**B-3 — step 10's `files[]` is short by six test files (MEDIUM).**
`state.json` lists only `tests/test_trip_preview_contract.py` and
`tests/test_premium_workbench_wiring.py` for step 10, but dropping twelve fields
from `TripPreviewResponse` turns six other files RED; §3.4 names each with its
line. `tests/test_workbench_matches_the_app.py:1971-1979` asserts
`candidate_eligible` and `basic_tour` are literally members of
`TripPreviewResponse.model_fields`, so it cannot survive the step untouched.
**Recommendation: add `tests/test_trip_api.py`, `tests/test_trip_models.py`,
`tests/test_trips_spend_and_authz.py` and `tests/test_workbench_matches_the_app.py`
to step 10's `files[]`** (the two Playwright files belong with step 12). Left as
is, step 10 lands and the phase gate fails on files the step was never allowed to
touch.
