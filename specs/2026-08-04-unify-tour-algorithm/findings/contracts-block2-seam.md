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
> **DEAD IN THIS FILE:** any handling that bypasses, weakens or removes the dirty-tree build-identity refusal. Ruling 4 keeps the check as-is; step 3 fixes the pytest setup to set `ONDOWAY_ALLOW_DIRTY_LOCAL_BUILD=1`. The open 503-vs-500 shape for an UNRESOLVABLE fingerprint still stands.

---

# Implementation contract — steps 2, 3, 4 (the Block-2 seam)

Written against the working tree at `a7df218c`. Every line reference below was read in
this session, not taken from the brief. Where the brief or the ledger has drifted from
the tree, the drift is called out inline.

**Scope.** Step 2 lifts the prebuilt-route plan construction into `src/tour/premium_tour.py`.
Step 3 re-points `POST /trips/{trip_id}/compose` onto it. Step 4 deletes
`src/tour/authoring.py:805-1038` and re-points every importer.

**Non-negotiable for the implementer.** Do not invent a signature, a parameter name, a
refusal string, or a test name that is not written out below. Two questions genuinely need
an owner decision and are in **BLOCKING AMBIGUITY** at the end; nothing else is left open.

---

## 0. Verified facts the three steps rest on

| # | Claim | Evidence |
| --- | --- | --- |
| F1 | The doomed seam is exactly `src/tour/authoring.py:805-1038`. Line 805 opens `@dataclass class PrebuiltRouteComposeUnit`; line 1038 is `return composition.script`. The brief's range is correct and has not drifted. | `src/tour/authoring.py:805`, `:1038` |
| F2 | `PremiumTourPlan` is a plain frozen dataclass with **no validators**, so it can be constructed field-by-field. Two existing test helpers already do exactly that. | `src/tour/premium_tour.py:193-227`; `tests/test_tour_authoring_gates.py:658-698`; `tests/test_never_silent_failures.py:188-223` |
| F3 | `PremiumComposeUnit` (`premium_tour.py:171-190`) and `PrebuiltRouteComposeUnit` (`authoring.py:805-816`) have the **same eight fields in the same order with the same types**. The premium one additionally has a `public_payload()` method (`:182-190`); the doomed one has none. Nothing reads a field the premium one lacks. | both dataclass bodies, read in full |
| F4 | The two route hashes are byte-identical. `route_summary`'s `route_sha256` is `sha256(json.dumps(route.model_dump(mode="json"), ensure_ascii=False, allow_nan=False, separators=(",",":"), sort_keys=True))` (`premium_tour.py:146` via `_sha256`/`_canonical_bytes` at `:81-92`). `prebuilt_route_sha256` (`authoring.py:844-854`) spells the identical call inline. Collapsing them changes no hash. | `premium_tour.py:81-92,146`; `authoring.py:844-854` |
| F5 | `generate()` sets `Script.inputs = tour_input` verbatim. So `source.inputs` **is** the tour input on every path, and the builder can derive it rather than take it as a parameter. This also removes the only way to hand `finalize_premium_tour` a mismatched pair, which `FinalTourBlueprint` rejects at `artifact.py:677-678`. | `src/tour/generation.py:424` |
| F6 | `generate()` builds `selected_pois` by iterating `route.pois` in order (`_flatten_pois`), so `script.selected_pois` ids always equal `route.pois` ids in order. `partition_final_script`'s first bar (`artifact.py:446-449`) is therefore satisfied by construction on **both** the preview and the compose path. | `src/tour/generation.py:415`; `src/tour/generation.py:1155-1175` |
| F7 | `PremiumTourPlan.snapshot` is read by **nothing** — only `snapshot_sha256` is consumed (by `finalize_premium_tour` at `premium_tour.py:675`). `route_record` is read only by `batch_payload` (`premium_tour.py:219`). | repo-wide grep for `.snapshot` / `route_record` over `src/ scripts/ tests/` |
| F8 | `PrebuiltRouteExecutor` (`authoring.py:835-841`) has zero references anywhere. `trips.py:492` injects `PremiumComposeExecutor`. `prebuilt_route_sha256` has exactly one caller, `authoring.py:891`, inside the block being deleted. | repo-wide grep, results reproduced in §4.2 |

---

# STEP 2 — lift the prebuilt-route plan construction into `premium_tour.py`

**File touched:** `src/tour/premium_tour.py`, `tests/test_premium_workbench_wiring.py`.
**Ledger `test_command`:** `make test-file FILE="tests/test_premium_workbench_wiring.py::test_plan_premium_tour_builds_its_units_through_the_shared_prebuilt_seam"` — confirmed absent from the tree today, so it is RED by construction.

## 2.1 The new function — exact signature

Insert **verbatim** into `src/tour/premium_tour.py`, positioned immediately after the
`PremiumTourPlan` dataclass (i.e. after current line 227) and immediately before
`certification_planning_policy` (current line 230). It must be defined before
`plan_premium_tour`, which will call it.

```python
def plan_premium_authoring(
    source: Script,
    beat_sequence: BeatSequence,
    route: Route,
    *,
    snapshot: CorpusSnapshot,
    snapshot_sha256: str,
    routing_version: str,
    policy_version: str,
    authorities: PremiumAuthorityHashes = PREMIUM_AUTHORITIES,
) -> PremiumTourPlan:
```

Rules the implementer may not vary:

* **`tour_input` is NOT a parameter.** The body sets `tour_input=source.inputs`. Evidence
  F5. Passing it separately reintroduces the mismatch `artifact.py:677-678` rejects.
* **`route_record` is NOT a parameter.** The body computes `route_summary(route)` once and
  uses the same value for both `route_record` and the candidate's `route_sha256`. Evidence
  F4 — this is the collapse of duplicated block C.
* `snapshot` is carried for shape parity only (F7); it is stored and never read.
* Keyword-only after `route` so no caller can transpose the four provenance strings.

## 2.2 The exact body

```python
    """Build every per-stop authoring request for an ALREADY-PLANNED route.

    THE ONE Block-2 plan builder. Pure and provider-free: no routing client, no
    selection, no LLM. It is called by ``plan_premium_tour`` (which plans the route
    first) and by ``POST /trips/{trip_id}/compose`` (whose route is already persisted),
    so the two surfaces cannot drift into separate per-stop request shapes again.

    ``tour_input`` is taken from ``source.inputs`` rather than accepted separately:
    ``generate`` writes it there verbatim (src/tour/generation.py:424), and
    ``FinalTourBlueprint`` refuses a script whose inputs differ from the blueprint's
    tour_input (src/tour/artifact.py:677-678), so a separate parameter could only ever
    introduce a mismatch.
    """

    _beats_by_id, stops, requests = _certification_compose_requests(source, beat_sequence, route)
    if stops[-1] >= len(route.pois):
        raise ValueError("the stitched script names a stop the prebuilt route lacks")
    # Exactly ONE unit per dwell stop. ``stops`` comes from the stitched script's
    # sentences, so a stop the stitch dropped simply would not appear — and a
    # missing TAIL stop passes every other bar: it is in order, it starts at 0,
    # and its highest index is in range. The plan would then hold fewer units
    # than the route has stops, a caller would reserve and spend for those, and
    # the trip would persist with its last stop never authored at all.
    if len(stops) != len(route.pois):
        raise ValueError("the prebuilt route needs one authoring unit per dwell stop")
    summary = route_summary(route)
    candidate = AuthoringCandidateIdentity.create(
        candidate_slot="A",
        contract_sha256=authorities.contract_sha256,
        reference_manifest_sha256=authorities.reference_manifest_sha256,
        calibration_manifest_sha256=authorities.calibration_manifest_sha256,
        grounded_source_sha256=sentences_payload_sha256(source.script),
        route_sha256=str(summary["route_sha256"]),
        authoring_policy_sha256=premium_authoring_policy_sha256(),
    )
    authoring = AuthoringCandidatePlan(
        candidate=candidate,
        stop_requests=tuple(
            AuthoringStopRequest.create(
                candidate=candidate,
                stop_index=stop_index,
                compose_input_sha256=compose_input_sha256(requests[stop_index]),
            )
            for stop_index in stops
        ),
    )
    units: list[PremiumComposeUnit] = []
    for stop_request in authoring.stop_requests:
        stop_index = stop_request.stop_index
        envelope, sdk_request = candidate_compose_request_envelope(
            requests[stop_index], stop_request, model=COMPOSE_MODEL
        )
        encoded = envelope.encode("utf-8")
        units.append(
            PremiumComposeUnit(
                stop_index=stop_index,
                poi_name=route.pois[stop_index].name,
                authorized_request=requests[stop_index],
                authoring_request=stop_request,
                request_sha256=_sha256(encoded),
                input_byte_count=len(encoded),
                output_token_ceiling=CERTIFICATION_COMPOSE_MAX_OUTPUT_TOKENS,
                sdk_request=sdk_request,
            )
        )
    return PremiumTourPlan(
        tour_input=source.inputs,
        snapshot=snapshot,
        snapshot_sha256=snapshot_sha256,
        route=route,
        route_record=summary,
        sequence=beat_sequence,
        source=source,
        candidate=candidate,
        authoring=authoring,
        units=tuple(units),
        routing_version=routing_version,
        policy_version=policy_version,
        authorities=authorities,
    )
```

Note the one deliberate difference from `plan_prebuilt_route_authoring`: the
`authoring_policy_sha256` is **computed** (`premium_authoring_policy_sha256()`) rather than
injected. The injection existed only to avoid an import cycle from the leaf module
`authoring.py` back to `premium_tour.py` (`authoring.py:868-871`). Inside `premium_tour.py`
the function is local, so the cycle does not exist and the parameter is dead weight.

## 2.3 The call-site rewrite inside `plan_premium_tour`

**Current, `src/tour/premium_tour.py:293-355`** (quoted from `source = generate(` to the
closing paren of the return):

```python
    source = generate(
        sequence,
        route,
        tour_input,
        now=generation_time or dt.datetime.now(dt.UTC),
        validate_output=False,
    )
    _beats, stops, requests = _certification_compose_requests(source, sequence, route)
    summary = route_summary(route)
    candidate = AuthoringCandidateIdentity.create(
        candidate_slot="A",
        contract_sha256=authorities.contract_sha256,
        reference_manifest_sha256=authorities.reference_manifest_sha256,
        calibration_manifest_sha256=authorities.calibration_manifest_sha256,
        grounded_source_sha256=sentences_payload_sha256(source.script),
        route_sha256=str(summary["route_sha256"]),
        authoring_policy_sha256=premium_authoring_policy_sha256(),
    )
    authoring = AuthoringCandidatePlan(
        candidate=candidate,
        stop_requests=tuple(
            AuthoringStopRequest.create(
                candidate=candidate,
                stop_index=stop_index,
                compose_input_sha256=compose_input_sha256(requests[stop_index]),
            )
            for stop_index in stops
        ),
    )
    units: list[PremiumComposeUnit] = []
    for stop_request in authoring.stop_requests:
        stop_index = stop_request.stop_index
        envelope, sdk_request = candidate_compose_request_envelope(
            requests[stop_index], stop_request, model=COMPOSE_MODEL
        )
        encoded = envelope.encode("utf-8")
        units.append(
            PremiumComposeUnit(
                stop_index=stop_index,
                poi_name=route.pois[stop_index].name,
                authorized_request=requests[stop_index],
                authoring_request=stop_request,
                request_sha256=_sha256(encoded),
                input_byte_count=len(encoded),
                output_token_ceiling=CERTIFICATION_COMPOSE_MAX_OUTPUT_TOKENS,
                sdk_request=sdk_request,
            )
        )
    return PremiumTourPlan(
        tour_input=tour_input,
        snapshot=snapshot,
        snapshot_sha256=exact_snapshot_sha256(snapshot),
        route=route,
        route_record=summary,
        sequence=sequence,
        source=source,
        candidate=candidate,
        authoring=authoring,
        units=tuple(units),
        routing_version=routing_version,
        policy_version=policy.policy_id,
        authorities=authorities,
    )
```

**Replacement — the exact replacement block, not a description:**

```python
    source = generate(
        sequence,
        route,
        tour_input,
        now=generation_time or dt.datetime.now(dt.UTC),
        validate_output=False,
    )
    return plan_premium_authoring(
        source,
        sequence,
        route,
        snapshot=snapshot,
        snapshot_sha256=exact_snapshot_sha256(snapshot),
        routing_version=routing_version,
        policy_version=policy.policy_id,
        authorities=authorities,
    )
```

Nothing else in `plan_premium_tour` changes: the two `PremiumRouteInfeasibleError` bars
(`:260-268`, `:274-275`), `build_poi_beat_plans_capped`, `select_vignette_beats` and the
`BeatSequence` build (`:277-292`) all stay exactly where they are.

## 2.4 `__all__`

Add `"plan_premium_authoring"` to `src/tour/premium_tour.py:709-729`, in alphabetical
position between `"plan_premium_tour"` and `"premium_authoring_policy_sha256"` — i.e. the
list becomes `..., "finalize_premium_tour", "plan_premium_authoring", "plan_premium_tour", ...`.
(Alphabetically `plan_premium_authoring` sorts before `plan_premium_tour`.) Nothing is
removed from `__all__` in step 2.

## 2.5 Behaviour that must be preserved bit-for-bit

1. **`request_sha256` per unit is unchanged.** It is `sha256` over the envelope from
   `candidate_compose_request_envelope`, which binds `candidate_id` and `request_id`
   (`authoring.py:427-434`). `candidate_id` derives from `route_sha256`, which F4 proves
   identical either way. Any change here silently invalidates committed certification data.
2. **The two refusals keep their exact messages**, because live callers match on them:
   `"the stitched script names a stop the prebuilt route lacks"` and
   `"the prebuilt route needs one authoring unit per dwell stop"`. Both are `ValueError`.
   `tests/test_tour_authoring_from_route.py:334,399,411` match on the substring
   `"one authoring unit per dwell stop"`.
3. **`plan_premium_tour`'s existing refusals stay ahead of the builder.** The receipt bar
   and the transit-count bar must still fire before any request is built.

## 2.6 New-behaviour hazard the implementer must not paper over

`plan_premium_tour` today has **no** one-unit-per-dwell-stop guard. After delegation it
inherits both refusals. If a premium plan could ever produce a stitched script with fewer
distinct `stop_idx` values than the route has POIs, this converts a previously-passing
plan into a `ValueError`.

That is the right outcome and is not a new refusal class: such a plan already dies later,
at `src/tour/artifact.py:739-741` — `"composition trace must cover every routed stop
exactly once"` — after paying for every stop it did author. The guard moves an existing
failure earlier and makes it free. **State this in the commit message; do not weaken the
guard to avoid it.**

## 2.7 The one proving test

**Node id:** `tests/test_premium_workbench_wiring.py::test_plan_premium_tour_builds_its_units_through_the_shared_prebuilt_seam`

`tests/test_premium_workbench_wiring.py` today imports only `importlib.util, inspect,
socket, subprocess, sys, time, pathlib`, `scripts.tour_batch_candidate` and
`src.api.routes.trips` (`:1-16`). Add at module scope:

```python
import ast
import pytest
from src.tour import premium_tour
from src.tour.premium_tour import plan_premium_authoring
from tests.test_tour_authoring_from_route import _drop_stop, _prebuilt
```

**Fixtures/stubs it builds.** None of its own. It reuses
`tests/test_tour_authoring_from_route.py::_prebuilt` (`:160-262`) and `::_drop_stop`
(`:265-273`), which are pure and provider-free: `_prebuilt(n, round_trip=..., routed=...,
sentences_per_stop=...)` returns `(Script, BeatSequence, Route)` where the route has `n`
POIs `p0..p{n-1}`, `n` transits (`n+1` when `round_trip=True`), one `BeatRef` per
`sentences_per_stop` per stop, and one stitched `Sentence` per beat carrying
`stop_idx=index`. No DB, no container, no provider.

**Exact assertions, in order:**

```python
def test_plan_premium_tour_builds_its_units_through_the_shared_prebuilt_seam() -> None:
    """AC-1 — ONE Block-2 plan builder, and plan_premium_tour goes through it.

    UNDO: change ``if len(stops) != len(route.pois):`` to ``if False:`` in
    ``plan_premium_authoring`` and the tail-stop refusal below goes RED. Re-inline the
    unit loop into ``plan_premium_tour`` and the single-construction-site assertion
    goes RED.
    """
    # 1. The shared builder produces a REAL PremiumTourPlan from a prebuilt route.
    stitched, sequence, route = _prebuilt(4, round_trip=True, sentences_per_stop=2)
    assert len(route.transits) == len(route.pois) + 1

    plan = plan_premium_authoring(
        stitched,
        sequence,
        route,
        snapshot=None,
        snapshot_sha256="0" * 64,
        routing_version="offline-test",
        policy_version="offline-test",
    )
    assert isinstance(plan, premium_tour.PremiumTourPlan)
    assert plan.route is route
    assert plan.source is stitched
    assert plan.sequence is sequence
    assert plan.tour_input is stitched.inputs
    assert [unit.stop_index for unit in plan.units] == [0, 1, 2, 3]
    assert [unit.poi_name for unit in plan.units] == [poi.name for poi in route.pois]
    assert len(plan.authoring.stop_requests) == len(route.pois)
    # The candidate binds the SAME route hash the plan record reports.
    assert plan.candidate.route_sha256 == plan.route_record["route_sha256"]

    # 2. Both refusals survive the lift, with their exact messages.
    with pytest.raises(ValueError, match="one authoring unit per dwell stop"):
        plan_premium_authoring(
            _drop_stop(stitched, len(route.pois) - 1),
            sequence,
            route,
            snapshot=None,
            snapshot_sha256="0" * 64,
            routing_version="offline-test",
            policy_version="offline-test",
        )

    # 3. ONE construction site. plan_premium_tour must delegate, not re-inline.
    module = ast.parse(inspect.getsource(premium_tour))
    builders = {
        node.name
        for node in ast.walk(module)
        if isinstance(node, ast.FunctionDef)
        for call in ast.walk(node)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == "PremiumComposeUnit"
    }
    assert builders == {"plan_premium_authoring"}, (
        "PremiumComposeUnit is constructed in more than one place, so the Block-2 "
        f"plan builder has been duplicated again: {sorted(builders)}"
    )
    assert "plan_premium_authoring(" in inspect.getsource(premium_tour.plan_premium_tour)
```

**The mutation — the precise one-line edit to production code that must turn this RED:**

> In `src/tour/premium_tour.py::plan_premium_authoring`, change
> `    if len(stops) != len(route.pois):`
> to
> `    if False:`

Assertion block 2 then fails with `DID NOT RAISE ValueError`. A second, independent
one-line mutation for assertion block 3: change the `return plan_premium_authoring(...)`
in `plan_premium_tour` back to the inlined loop — not one line, so use instead: add
`    units = [PremiumComposeUnit(**{})]` as the first statement of `plan_premium_tour`'s
body → `builders` becomes `{"plan_premium_authoring", "plan_premium_tour"}` → RED.

## 2.8 Ordering hazards inside step 2

None. `plan_premium_authoring` is added, `plan_premium_tour` is re-pointed, and
`authoring.py` is untouched. The tree is green at every intermediate save if the new
function is written before the delegation.

---

# STEP 3 — route `POST /trips/{trip_id}/compose` through Block 2

**Files touched:** `src/api/routes/trips.py`, `tests/test_trip_api.py`.
**Ledger `test_command` (re-pointed by the planner-manager mid-flight):**
`make test-file FILE="tests/test_trip_api.py::test_compose_plans_and_authors_through_the_shared_premium_seam"` — confirmed absent from `tests/` today, so RED by construction.

## 3.1 The blueprint risk flagged in run-context — resolved, and the flag is inverted

Run-context warns that `finalize_premium_tour` builds a blueprint that "rejects a leg
assignment index at or beyond the transit count", and that "a persisted round-trip route
has one extra transit."

**That is safe, and the concern points the wrong way.** Evidence, line by line:

* `src/tour/artifact.py:489` — `if assignment.placement == "leg" and assignment.index >= len(route.transits): raise`.
* `src/tour/artifact.py:487` — every `assignment.index` must equal its sentence's `stop_idx`.
* `src/tour/artifact.py:482` — every `sentence.stop_idx` must be `< len(route.pois)`.
* `src/tour/routing.py:423-437` — `summarise_route` appends one transit per POI, plus one
  more when `round_trip` and the POI list is non-empty.

So `len(route.transits)` is `len(route.pois)` for A→B and `len(route.pois) + 1` for a
round trip. Because `stop_idx < len(route.pois) <= len(route.transits)` always, the check
at `:489` can never fire on a `summarise_route` route. An **extra** transit makes the bound
looser, not tighter. The deleted seam's own comment (`authoring.py:796-798`) says the same
thing about the transit shape — it lists it as a bar `plan_premium_tour` applies at
`premium_tour.py:263`, which lives **before** the builder and is not part of Block 2.

The other three blueprint bars are also satisfied by construction on the compose path:

| Bar | Where | Why compose satisfies it |
| --- | --- | --- |
| `script.selected_pois` ids must equal `route.pois` ids in order | `artifact.py:446-449` | F6 — `generate()` builds `selected_pois` by iterating `route.pois` |
| composition trace must cover every routed stop exactly once | `artifact.py:739-741` | `plan_premium_authoring` refuses unless `len(stops) == len(route.pois)` (§2.2) |
| Valhalla receipt config must match the build fingerprint | `artifact.py:679-687` | guarded by `if receipt_config_hashes` — a haversine-degraded persisted route has **no** receipts, so the set is empty and the check is skipped; a freshly-routed one carries `VALHALLA_ROUTING_CONFIG_SHA256`, which is exactly what `BuildFingerprint` is given at `premium_tour.py:683` |
| script inputs must equal blueprint tour_input | `artifact.py:677-678` | F5 plus §2.1's "no `tour_input` parameter" |

**Verdict: no special handling is required for the round-trip transit shape.** The compose
path may call `finalize_premium_tour` directly.

## 3.2 The real hazard step 3 introduces: `resolve_build_identity`

`finalize_premium_tour` defaults `build_identity` to `resolve_build_identity()`
(`premium_tour.py:655`), which **raises `ValueError("Premium fingerprint requires a clean
local git tree")`** on any dirty local tree unless `ONDOWAY_ALLOW_DIRTY_LOCAL_BUILD=1` is
set (`premium_tour.py:588-592`). Only `scripts/workbench.sh:72` sets that variable; nothing
in the Makefile or `tests/conftest.py` does.

Compose does not resolve a build identity today. If step 3 lets the default fire inside the
existing `try`, a dirty developer tree turns every compose into a 422 labelled
`compose_verification_failed` — blaming the narrator for an environment fault, and turning
the existing regression pin RED for a reason that has nothing to do with narration.

The preview path already solved this: it resolves the identity **before** any spend and
maps a failure to its own named outcome (`trips.py:995-1008`). Compose must do the same.
See **BLOCKING AMBIGUITY B2** for the one open question (which HTTP shape).

## 3.3 Exact call-site rewrite

### 3.3.1 Imports

**Current, `src/api/routes/trips.py:42`:**

```python
from src.tour.authoring import author_prebuilt_route, plan_prebuilt_route_authoring
```

**Replacement:** delete the line entirely.

**Current, `src/api/routes/trips.py:60-69`:**

```python
from src.tour.premium_tour import (
    EphemeralReceiptSink,
    PremiumComposeExecutor,
    PremiumRouteInfeasibleError,
    execute_premium_plan,
    finalize_premium_tour,
    plan_premium_tour,
    premium_authoring_policy_sha256,
    resolve_build_identity,
)
```

**Replacement:**

```python
from src.tour.premium_tour import (
    PREMIUM_MODULE_VERSION,
    EphemeralReceiptSink,
    PremiumComposeExecutor,
    PremiumRouteInfeasibleError,
    certification_planning_policy,
    execute_premium_plan,
    exact_snapshot_sha256,
    finalize_premium_tour,
    plan_premium_authoring,
    plan_premium_tour,
    resolve_build_identity,
)
```

`premium_authoring_policy_sha256` is dropped because §2.1 removed the injection parameter;
after this step it has **no** caller in `src/`. Do **not** delete the function — it is
still used by `premium_tour.py:678` and by `tests/test_tour_authoring_gates.py`.

### 3.3.2 The route rebuild

**Current, `src/api/routes/trips.py:568-578`:**

```python
    spine = pick_spine_area(tour_input.start[0], tour_input.start[1], picked, snapshot)
    with RoutingClient() as routing_client:
        route = summarise_route(
            picked,
            start_lat=tour_input.start[0],
            start_lng=tour_input.start[1],
            round_trip=tour_input.round_trip,
            duration_min=tour_input.duration_min,
            spine_area=spine,
            routing_client=routing_client,
        )
```

**Replacement:**

```python
    spine = pick_spine_area(tour_input.start[0], tour_input.start[1], picked, snapshot)
    # The SAME certification walk budget the phone and the workbench plan with
    # (0.90-1.10, nominal 1.00). Rebuilding the persisted pick with no policy is the
    # third route into the legacy 0.83 flat budget, which step 6 deletes outright.
    planning_policy = certification_planning_policy(policy_id=PREMIUM_MODULE_VERSION)
    with RoutingClient() as routing_client:
        routing_version = routing_client.routing_version()
        route = summarise_route(
            picked,
            start_lat=tour_input.start[0],
            start_lng=tour_input.start[1],
            round_trip=tour_input.round_trip,
            duration_min=tour_input.duration_min,
            spine_area=spine,
            routing_client=routing_client,
            planning_policy=planning_policy,
        )
```

`routing_version` **must** be captured inside the `with` block: `RoutingClient` is a context
manager and the plan needs the value after it closes. See **BLOCKING AMBIGUITY B1** for
AC-10's literal "`summarise_route` does not appear" clause, which this does not satisfy.

### 3.3.3 The authoring block

**Current, `src/api/routes/trips.py:608-637`:**

```python
    # ONE ALGORITHM. This persisted endpoint no longer owns a whole-tour composer:
    # it authors the route it just rebuilt through the same per-stop seam that
    # /trips/preview and the batch runner use, and keeps its fail-before-mutation
    # contract (nothing below this block writes until authoring has passed VERIFY).
    # Planning is provider-free, so the exact physical call count is known before a
    # single call is billed.
    try:
        plan = plan_prebuilt_route_authoring(
            stitched,
            seq,
            route,
            authoring_policy_sha256=premium_authoring_policy_sha256(),
        )
        # The spend reservation is the REAL number of calls this compose will make
        # (one per dwell stop), and it happens HERE — after the already-composed 409
        # above, so a duplicate compose reserves nothing and calls nobody.
        with _upstream_provider_errors():
            # GATE PARITY (D3). The per-stop finalizer was built for the
            # certification replay and defaults to structural checks only; this
            # path PERSISTS an unreviewed tour, so it keeps the exact three gates
            # the whole-tour composer ran for it — real entailment, the
            # stitch-derived coverage baseline, and the full validate_script scan.
            # Parity, not escalation: no check here that was not here before.
            composed = author_prebuilt_route(
                plan,
                executor=premium_executor,
                faithfulness_checker=faithfulness_checker,
                enforce_claim_coverage=True,
                scan_glue_for_invention=True,
            )
```

**Replacement:**

```python
    # ONE ALGORITHM, ONE SEAM. This persisted endpoint authors the route it just
    # rebuilt through the SAME Block-2 seam /trips/preview and the batch runner use:
    # plan_premium_authoring -> execute_premium_plan -> finalize_premium_tour. It
    # keeps its fail-before-mutation contract (nothing below this block writes until
    # authoring has passed VERIFY). Planning is provider-free, so the exact physical
    # call count is known before a single call is billed.
    #
    # The three anti-hallucination gates are no longer this call site's to choose:
    # finalize_premium_tour hard-codes enforce_claim_coverage and
    # scan_glue_for_invention ON and gives faithfulness_checker no default
    # (src/tour/premium_tour.py:627-654), so a live surface cannot silently omit one.
    #
    # Resolved BEFORE the try and before any spend: an unresolvable build fingerprint
    # (dirty local tree, malformed deploy SHA) is an environment fault, not an
    # authoring failure, and must never be relabelled compose_verification_failed —
    # that code means "the narrator wrote something untraceable" and would blame the
    # writer for an engine fault. Same reasoning as /trips/preview at :995-1008.
    try:
        build_identity = resolve_build_identity()
    except Exception as exc:
        logging.getLogger("ondoway.api").exception(
            "Compose could not resolve a build fingerprint for trip=%s", trip_id
        )
        raise HTTPException(
            503,
            {"reason": "build_fingerprint_unavailable", "detail": str(exc)},
            headers={"Retry-After": "30"},
        ) from exc

    try:
        plan = plan_premium_authoring(
            stitched,
            seq,
            route,
            snapshot=snapshot,
            snapshot_sha256=exact_snapshot_sha256(snapshot),
            routing_version=routing_version,
            policy_version=planning_policy.policy_id,
        )
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
            composed = premium_result.blueprint.script
```

Everything from `except ComposeVerificationError as exc:` (`:638`) to the end of the handler
(`:731`) is **unchanged**. `composed` remains a `Script`, so `composed.selected_pois`
(`:687`), `route_script_to_stops(composed.selected_pois, ..., script=composed, ...)`
(`:691-697`) and the whole persistence tail keep working untouched.

### 3.3.4 The stale comment at `:476-481`

**Current:**

```python
# The per-stop authoring seam fires exactly ONE physical call per dwell stop and
# never retries (src/tour/authoring.py::author_prebuilt_route), so the attempt count
```

**Replacement:**

```python
# The per-stop authoring seam fires exactly ONE physical call per dwell stop and
# never retries (src/tour/premium_tour.py::execute_premium_plan), so the attempt count
```

A comment naming a deleted symbol is exactly the stale-doc trap the project rules forbid.

## 3.4 Behaviour that must be preserved bit-for-bit

1. **`faithfulness_checker` comes from `Depends(get_faithfulness_checker)` at
   `trips.py:493`** and is forwarded verbatim. This is the same value `/trips/preview`
   forwards at `trips.py:1023`. `finalize_premium_tour` requires it positionally-by-keyword
   and passes it on with `enforce_claim_coverage=True, scan_glue_for_invention=True`
   hard-coded (`premium_tour.py:648-654`) — identical to what compose passes by hand today
   at `trips.py:634-636`. **The three gates run with the same arguments before and after.**
2. **The 422 refusal body is byte-identical on the wire.** `ComposeVerificationError` is
   raised by the same shared finalizer (`authoring.py:782`) reached through
   `finalize_premium_composition` (`premium_tour.py:533-542`), so the existing handler at
   `trips.py:638-649` still produces
   `{"reason": "compose_verification_failed", "attempts", "untraceable", "forbidden",
   "provenance", "faithfulness"}`. The phone reads `reason` and `attempts`
   (`mobile/lib/services/trip_service.dart:227-229`).
3. **`ValueError` still becomes a 422 with the non-leaking shape** (`trips.py:650-673`).
   The new sources of `ValueError` are `plan_premium_authoring`'s two refusals and
   `validate_llm_composed_blueprint`'s ineligibility string (`premium_tour.py:703-705`).
   Both are genuine "this flavour cannot be authored" refusals, which is what that branch
   is for.
4. **404 / 409 / ownership behaviour** (`trips.py:512-539`) is untouched, and the spend
   still happens strictly after the already-composed 409.
5. **`TripComposeResponse`** (`trips.py:726-731`) and `COMPOSE_ATTEMPTS = 1` are unchanged.

## 3.5 What step 3 does NOT deliver

The ledger assigns AC-8 to step 3. Step 3 delivers only the "no hand-restore of the
authored narration" half. It does **not** deliver "eta_seconds, vignettes and tourability
identical to the chosen option" — `trips.py:580-590` still hand-restores vignettes and the
anchor identity, and `summarise_route` never sets `tourability` (`routing.py:444-453`;
the field defaults to `None` at `contract.py:425`). That half needs the persisted-option
work in steps 9-11. **Record this in the step's persist note; do not claim AC-8 closed.**

## 3.6 The one proving test (new node id)

**Node id:** `tests/test_trip_api.py::test_compose_plans_and_authors_through_the_shared_premium_seam`

Placed immediately **before** `test_compose_authors_per_stop_and_keeps_the_wire_contract`
(currently `tests/test_trip_api.py:650`). It is RED today by construction: assertion 1
fails because `compose_trip`'s source names `author_prebuilt_route`, not
`finalize_premium_tour`.

**Fixtures/stubs.** Reuses the module's existing `client` and `cutover_trip` fixtures
(`tests/test_trip_api.py:642-648` — one freshly generated, not-yet-composed live-corpus
trip), the existing `_PerStopCountingExecutor` (`:578-604`, cost-bearing, echoes the
stitch, records `stop_index` per call under a lock), and the existing `_override_dep` /
`_clear_dep` helpers (`:628-640`). It adds one new $0 double at module scope:

```python
class _CountingChecker:
    """Records every entailment question asked. Approves everything, so it changes
    no verdict — it only proves the gate CONSULTED a checker."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def entails(self, premise: str, hypothesis: str) -> bool:
        self.calls.append((premise, hypothesis))
        return True
```

> Implementation note: mirror the method name and arity of
> `src/tour/verify.py`'s `FaithfulnessChecker` protocol. Read it before writing this class
> and match it exactly; if the live protocol differs from `entails(premise, hypothesis)`,
> the class follows the protocol, not this document.

**Exact assertions, in order:**

```python
@needs_neo4j
def test_compose_plans_and_authors_through_the_shared_premium_seam(
    client, live_neo4j, cutover_trip
) -> None:
    """AC-10 (in substance) — compose runs Block 2, not a second authoring seam.

    UNDO: change ``faithfulness_checker=faithfulness_checker`` to
    ``faithfulness_checker=None`` in ``compose_trip`` and assertion 3 goes RED.
    Revert ``finalize_premium_tour(`` to ``author_prebuilt_route(`` and assertion 1
    goes RED.
    """
    # 1. STRUCTURAL: the handler's own source names the shared seam and nothing else.
    source = inspect.getsource(trips.compose_trip)
    assert "plan_premium_authoring(" in source
    assert "execute_premium_plan(" in source
    assert "finalize_premium_tour(" in source
    assert "author_prebuilt_route(" not in source
    assert "plan_prebuilt_route_authoring(" not in source

    # 2. The route rebuild carries the certification walk budget, never the flat legacy
    #    one — the third route into the 0.83 budget the brief names.
    assert "planning_policy=planning_policy" in source
    assert "certification_planning_policy(" in source

    # 3. BEHAVIOURAL: composing consults the injected faithfulness checker. Only
    #    finalize_premium_tour makes that non-optional, so this is what proves the
    #    endpoint went through it rather than round a gate-optional seam.
    trip_id = cutover_trip["trip_id"]
    n_stops = len(cutover_trip["stops"])
    assert n_stops > 1
    checker = _CountingChecker()
    executor = _PerStopCountingExecutor()
    exec_target = _override_dep(client, "get_premium_compose_executor", executor)
    check_target = _override_dep(client, "get_faithfulness_checker", checker)
    try:
        resp = client.post(
            f"/api/v1/trips/{trip_id}/compose", json={"route_id": f"{trip_id}-opt1"}
        )
    finally:
        _clear_dep(client, exec_target)
        _clear_dep(client, check_target)
    assert resp.status_code == 200, resp.text
    assert sorted(executor.stop_calls) == list(range(n_stops))
    assert checker.calls, (
        "compose never consulted the injected faithfulness checker — it is not "
        "going through finalize_premium_tour, which is the only thing that makes "
        "the checker impossible to omit"
    )
    assert len(resp.json()["stops"]) == n_stops
```

`inspect` and `trips` must be importable in `tests/test_trip_api.py`; add
`import inspect` and `from src.api.routes import trips` at module scope if absent.

**The mutation — the precise one-line edit that must turn this RED:**

> In `src/api/routes/trips.py::compose_trip`, change
> `                faithfulness_checker=faithfulness_checker,`
> to
> `                faithfulness_checker=None,`

Assertion 3 then fails: `checker.calls` is empty. This is a real mutation — it is exactly
the omission the `finalize_premium_tour` docstring (`premium_tour.py:636-642`) says cost
the workbench its entailment gate for three days.

Second, independent one-line mutation for assertion 1: change `finalize_premium_tour(` to
`finalize_premium_composition(` in `compose_trip` → assertion 1 RED.

## 3.7 The fate of the existing regression pin

`tests/test_trip_api.py:650` `test_compose_authors_per_stop_and_keeps_the_wire_contract`
must **stay green and must not be weakened** (AC-27's standard). I read the whole test body
(`:650-771`) and traced each assertion against the new call graph.

**The planner-manager's premise here is wrong, and I have to say so plainly because it
changes what gets edited.** The concern was that "`finalize_premium_tour` refuses
differently", so the 422 branch's `reason` / `attempts` / `untraceable` fields would stop
being produced. They are still produced, unchanged, because both paths reach the identical
refusal:

* today: `author_prebuilt_route` → `finalize_certification_composition` → `raise
  ComposeVerificationError(report, 1)` (`authoring.py:1028-1037`, raise at `:782`)
* after: `finalize_premium_tour` → `finalize_premium_composition` → **the same**
  `finalize_certification_composition` (`premium_tour.py:533-542`) → the same raise at
  `authoring.py:782`

`_HallucinatingExecutor` (`tests/test_trip_api.py:604-626`) forges an untraceable citation,
which fails the traceability half of VERIFY inside that shared finalizer. The exception is
raised **before** `finalize_premium_tour` reaches any blueprint code
(`premium_tour.py:648` is its first statement). The existing handler at `trips.py:638-649`
is untouched, so the body is still
`{"reason": "compose_verification_failed", "attempts": 1, "untraceable": >0, ...}`.

**Assertion-by-assertion verdict:**

| Lines | Assertion | Verdict |
| --- | --- | --- |
| `:690-699` | 404 for unknown trip and unknown `route_id` | survives unchanged — handler `:512-539` untouched |
| `:703` | `before_route is None` | survives unchanged |
| `:711` | 422 status | survives unchanged (§3.4.2) |
| `:713` | `detail["reason"] == "compose_verification_failed"` | **survives unchanged** — same shared finalizer, same raise |
| `:714` | `detail["attempts"] >= 1` | survives unchanged — `COMPOSE_ATTEMPTS`/`exc.attempts` both 1 |
| `:715` | `detail["untraceable"] > 0` | **survives unchanged** — `exc.report.untraceable_sentences` is non-empty for a forged citation |
| `:716` | refusal leaves the trip untouched | survives unchanged — nothing writes before `replace_trip_stops` at `:700` |
| `:723-732` | one physical call per dwell stop via `_PerStopCountingExecutor` | survives unchanged — `execute_premium_plan` fans out one unit per stop (`premium_tour.py:460-461`) exactly as `author_prebuilt_route` did |
| `:740-761` | wire contract: `trip_id`, `route_id`, `attempts`, fresh stop ids, `audio is None`, every stop narrated, `extra_narration` paired with `extra_beat_ids` | survives unchanged — the persistence tail `:675-731` is not edited |
| `:763-770` | duplicate compose is a 409 that calls nobody | survives unchanged |

**Zero assertions in that test are re-pointed, and zero are weakened.** The one thing that
would break it is the `resolve_build_identity` hazard of §3.2 — and only because a dirty
local tree would 503 before authoring. That is precisely why §3.3.3 resolves the identity
in its own `try` with its own status code, ahead of the paid path.

**Required check before persisting step 3:** re-run
`make test-file FILE="tests/test_trip_api.py::test_compose_authors_per_stop_and_keeps_the_wire_contract"`
and confirm it is green both before and after. If it goes red, the cause is §3.2, not the
refusal shape.

## 3.8 Ordering hazards inside step 3

1. `plan_premium_authoring` must exist first — step 3 `depends_on: ["2"]` already encodes
   this.
2. Delete the `src.tour.authoring` import line **in the same edit** that removes the last
   `author_prebuilt_route(` call, or ruff `F401` fails `make lint`.
3. Do **not** delete anything from `src/tour/authoring.py` in step 3. The three test files
   still import the doomed names at module scope; deleting early collect-errors the suite.
4. Capture `routing_version` inside the `with RoutingClient()` block.

---

# STEP 4 — delete the second authoring seam and re-point every importer

**Files touched:** `src/tour/authoring.py`, `tests/test_tour_authoring_from_route.py`,
`tests/test_tour_authoring_gates.py`, `tests/test_never_silent_failures.py`,
`tests/test_tour_one_engine.py`.
**Ledger `test_command`:** `make test-file FILE="tests/test_tour_one_engine.py::test_the_second_authoring_seam_is_gone"` — confirmed absent today, RED by construction.
**Criteria (per the ledger fix):** AC-1, AC-9, AC-11, AC-22, AC-27, AC-28, AC-29.

## 4.1 Exact deletion list

Delete `src/tour/authoring.py:785-1038` — that is the section banner comment at `:785-802`
through `return composition.script` at `:1038`. Symbol by symbol:

| Symbol | Lines | Verified caller-free by |
| --- | --- | --- |
| the `# The author-a-prebuilt-route seam` banner + D5 rationale comment | `authoring.py:785-802` | comment only |
| `PrebuiltRouteComposeUnit` | `authoring.py:805-816` | `grep -rn 'PrebuiltRouteComposeUnit' --include='*.py' --include='*.md' --include='*.js' --include='*.json' --include='*.html' --include='*.dart' .` — after step 4's test edits, hits only in `specs/` prose and `ondoway-one-engine-handoff.md` (untracked scratch at repo root) |
| `PrebuiltRouteAuthoringPlan` | `authoring.py:819-832` | same grep |
| `PrebuiltRouteExecutor` | `authoring.py:835-841` | same grep — **already zero references today** (F8) |
| `prebuilt_route_sha256` | `authoring.py:844-854` | same grep — one caller, `authoring.py:891`, inside the deleted block (F8) |
| `plan_prebuilt_route_authoring` | `authoring.py:857-931` | same grep — callers are `trips.py:615` (removed in step 3) and the three test files (re-pointed in this step) |
| `author_prebuilt_route` | `authoring.py:934-1038` | same grep — callers are `trips.py:631` (removed in step 3) and the three test files |

**`__all__` entries to remove** from `src/tour/authoring.py:1041-1058`:
`"AUTHORING_MAX_STOPS"`, `"PrebuiltRouteAuthoringPlan"`, `"PrebuiltRouteComposeUnit"`,
`"PrebuiltRouteExecutor"`, `"author_prebuilt_route"`, `"plan_prebuilt_route_authoring"`,
`"prebuilt_route_sha256"`. The surviving `__all__` is exactly:

```python
__all__ = [
    "CERTIFICATION_COMPOSE_MAX_OUTPUT_TOKENS",
    "COMPOSE_MAX_OUTPUT_TOKENS",
    "COMPOSE_MODEL",
    "CertificationComposition",
    "CompletedCertificationComposeUnit",
    "ComposeRequest",
    "candidate_compose_request_envelope",
    "compose_input_sha256",
    "finalize_certification_composition",
]
```

`AUTHORING_MAX_STOPS` leaves `__all__` per AC-11 but **the constant itself stays** at
`authoring.py:135`: it is still enforced at `authoring.py:501` and read by
`tests/test_tour_authoring_from_route.py:338,358` and
`tests/test_workbench_matches_the_app.py:2039`. Step 5 deletes the guard; step 4 does not.
`from src.tour.authoring import AUTHORING_MAX_STOPS` keeps working regardless of `__all__` —
`__all__` only governs `import *`.

**Imports in `authoring.py` that must go with the block.** After deleting `:785-1038`,
run `make lint`; any name in the module's import block that ruff now reports as `F401`
must be removed. Based on a read of the deleted body, the candidates are `Protocol` (from
`typing`), `ThreadPoolExecutor`, `record` / `in_current_context` (from
`src.tour.degradations`), `PhysicalProviderResponse`, `AuthoringStopResponse`,
`AuthoringCandidateResponseSet`, `AuthoringCandidateIdentity`, `AuthoringCandidatePlan`,
`AuthoringStopRequest`, `PREMIUM_AUTHORITIES`, `PremiumAuthorityHashes`,
`FaithfulnessChecker` and `Route`. **Do not delete any of these on the strength of this
list — several are also used above line 785.** Let ruff name them; that is the enforcement.
`AUTHORING_MAX_STOPS`'s own definition and `_certification_compose_requests` stay.

**The five already-shared helpers must still exist** (AC-11): `_certification_compose_requests`
(`:489`), `candidate_compose_request_envelope` (`:413`), `compose_input_sha256` (`:400`),
`_sentences_from_json` (`:455`), `finalize_certification_composition` (`:553`).

## 4.2 The function-scoped planner prohibition — exact new helper

`tests/test_tour_authoring_from_route.py:55-124` guards the seam by parsing the **whole**
of `src/tour/authoring.py` for planning imports and calls. That guard cannot move to
`premium_tour.py`: that module legitimately imports `selection`, `routing`, `routing_client`
and `beat_select` at `:66-74` for `plan_premium_tour`, so a module-scope check would be
vacuously red forever.

The replacement walks **only** the Block-2 function bodies.

**The forbidden-name set is unchanged.** Quoted verbatim from
`tests/test_tour_authoring_from_route.py:73-85`:

```python
#: Planning entry points, by the name they are CALLED under (bare or attribute).
_PLANNING_CALLS = frozenset(
    {
        "select_k_routes",
        "choose_discrete_route",
        "plan_premium_tour",
        "certification_planning_policy",
        "route_planning_budget",
        "summarise_route",
        "insertion_cost_seconds",
        "generate",
    }
)
```

`_PLANNING_MODULES` (`:60-71`) is also kept verbatim, but is now applied only to imports
that appear **inside** a Block-2 function body — a function-local
`from .selection import select_k_routes` is the one import shape a call-graph check would
otherwise miss.

**The exact new helper.** Replaces `_SEAM_PATH` (`:55`),
`_seam_import_and_call_graph` (`:88-112`) and `_assert_the_seam_cannot_reach_the_planner`
(`:115-124`) in `tests/test_tour_authoring_from_route.py`:

```python
_SEAM_PATH = Path(__file__).resolve().parents[1] / "src" / "tour" / "premium_tour.py"

#: The Block-2 functions. Everything the AUTHOR block is allowed to be, by name.
#: The module as a whole legitimately imports the planner for ``plan_premium_tour``
#: (src/tour/premium_tour.py:66-74), so a module-scope guard here would be vacuously
#: red. The prohibition is therefore FUNCTION-SCOPED: these bodies, and nothing else.
_BLOCK_TWO_FUNCTIONS = frozenset(
    {
        "plan_premium_authoring",
        "execute_premium_plan",
        "finalize_premium_composition",
        "finalize_premium_tour",
    }
)


def _block_two_import_and_call_graph() -> tuple[set[str], set[str]]:
    """Every name the Block-2 function BODIES import and call, parsed — not matched.

    ``ast`` is used deliberately: a text search over the file would silently return
    an empty match on any shape it did not anticipate and the guard would pass by
    accident. Nested function definitions inside a Block-2 body (``invoke`` inside
    ``execute_premium_plan``) are walked too, because that is where a fan-out worker
    would reach a planner from.
    """
    tree = ast.parse(_SEAM_PATH.read_text(encoding="utf-8"), filename=str(_SEAM_PATH))
    bodies = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name in _BLOCK_TWO_FUNCTIONS
    ]
    assert {node.name for node in bodies} == _BLOCK_TWO_FUNCTIONS, (
        "a Block-2 function was renamed or removed, so this guard now watches less "
        f"than it claims: found {sorted(node.name for node in bodies)}"
    )
    imported: set[str] = set()
    called: set[str] = set()
    for body in bodies:
        for node in ast.walk(body):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported.update(alias.name.split("."))
            elif isinstance(node, ast.ImportFrom):
                imported.update((node.module or "").split("."))
                for alias in node.names:
                    imported.add(alias.name)
            elif isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name):
                    called.add(func.id)
                elif isinstance(func, ast.Attribute):
                    called.add(func.attr)
    return imported, called


def _assert_the_seam_cannot_reach_the_planner() -> None:
    imported, called = _block_two_import_and_call_graph()
    assert not imported & _PLANNING_MODULES, (
        "a Block-2 function imports a route-PLANNING module: "
        f"{sorted(imported & _PLANNING_MODULES)}"
    )
    assert not called & _PLANNING_CALLS, (
        "a Block-2 function calls a route-PLANNING entry point: "
        f"{sorted(called & _PLANNING_CALLS)}"
    )
```

**Verified green against the post-step-2 tree.** I read all four function bodies. The
names they call are: `_certification_compose_requests`, `route_summary`,
`AuthoringCandidateIdentity.create`, `sentences_payload_sha256`, `_sha256`,
`_canonical_bytes`, `AuthoringCandidatePlan`, `AuthoringStopRequest.create`,
`compose_input_sha256`, `candidate_compose_request_envelope`, `encode`, `append`,
`PremiumComposeUnit`, `PremiumTourPlan`, `ValueError`, `len`, `tuple`, `str`,
`before_call`, `after_call`, `record`, `in_current_context`, `ThreadPoolExecutor`, `map`,
`min`, `execute`, `json.loads`, `_sentences_from_json`, `zip`, `AuthoringStopResponse`,
`CompletedCertificationComposeUnit`, `AuthoringCandidateResponseSet`,
`finalize_certification_composition`, `finalize_premium_composition`,
`resolve_build_identity`, `frozenset`, `derive_playback_assignments`,
`remap_provider_playback_assignments`, `BuildFingerprint`, `build_final_blueprint`,
`validate_llm_composed_blueprint`, `PremiumTourResult`, `TypeError`, `isinstance`,
`enumerate`. **None intersects `_PLANNING_CALLS`.** No Block-2 body contains an import
statement. `route_summary` is a pure hash/record over an already-built route, not a
planner, and is deliberately absent from `_PLANNING_CALLS`.

## 4.3 The seven tests in `tests/test_tour_authoring_from_route.py`, re-pointed one by one

Shared prerequisite edits:

* **Module docstring (`:1-22`)** — rewrite. It names `src/tour/authoring.py` and describes
  a seam that no longer exists. It must now describe Block 2 in `premium_tour.py` and say
  that the planner prohibition is function-scoped and why.
* **Imports (`:32-53`)** — replace
  `from src.tour.authoring import (AUTHORING_MAX_STOPS, COMPOSE_MODEL, author_prebuilt_route, plan_prebuilt_route_authoring)`
  with
  ```python
  from src.tour.authoring import AUTHORING_MAX_STOPS, COMPOSE_MODEL
  from src.tour.premium_tour import (
      EphemeralReceiptSink,
      execute_premium_plan,
      finalize_premium_composition,
      plan_premium_authoring,
  )
  ```
  and delete the now-unused `from src.tour.premium_tour import premium_authoring_policy_sha256`
  (`:53`).
* **`_plan` (`:276-282`)** — replace:
  ```python
  def _plan(stitched: Script, sequence: BeatSequence, route: Route):
      return plan_premium_authoring(
          stitched,
          sequence,
          route,
          snapshot=None,
          snapshot_sha256="0" * 64,
          routing_version="offline-test",
          policy_version="offline-test",
      )
  ```
* **New `_author` helper**, replacing every `author_prebuilt_route(plan, executor=X)` call.
  `author_prebuilt_route` returned a `Script`; Block 2's equivalent is execute-then-finalize,
  and `finalize_premium_composition` returns a `CertificationComposition` whose `.script`
  is that same `Script`:
  ```python
  def _author(plan, executor) -> Script:
      """Block 2's execute-then-finalize, returning the Script the old seam returned.

      ``finalize_premium_composition`` rather than ``finalize_premium_tour``: the
      latter builds a certification blueprint and resolves a git build fingerprint,
      neither of which this file's claim (the AUTHOR block never re-plans) involves.
      """
      responses = execute_premium_plan(
          plan, executor=executor, receipt_sink=EphemeralReceiptSink()
      )
      return finalize_premium_composition(plan, responses).script
  ```
* **`_forbid_planning` (`:285-290`)** — unchanged. It monkeypatches `selection.select_k_routes`
  and `selection.choose_discrete_route`, which is still the right runtime belt to the AST
  brace.

| # | Test | Line | Re-point |
| --- | --- | --- | --- |
| 1 | `test_prebuilt_route_authors_without_replanning` | `:293` | `_assert_the_seam_cannot_reach_the_planner()` now uses the new helper (§4.2). `plan = _plan(...)` unchanged (helper rewritten). `plan.route is route` unchanged. `script = author_prebuilt_route(plan, executor=executor)` at `:320` → `script = _author(plan, executor)`. Same at `:342` and `:351`. The `AUTHORING_MAX_STOPS == selection.HARD_ANCHOR_CAP == 15` assertion at `:338` is unchanged (constant survives step 4). Every other assertion unchanged. Rename to `test_the_author_block_never_replans` and update the docstring to say the guard is function-scoped over `premium_tour.py`. |
| 2 | `test_prebuilt_route_authors_fifteen_stops` | `:356` | `:366` `author_prebuilt_route(plan, executor=executor)` → `_author(plan, executor)`. Nothing else. |
| 3 | `test_prebuilt_route_authors_a_single_stop` | `:371` | `:376` → `_author(_plan(stitched, sequence, route), executor)`. |
| 4 | `test_prebuilt_route_authors_receiptless_haversine_legs` | `:381` | `:391` → `_author(...)`. This is AC-22's home: the receipt bar lives in `plan_premium_tour` (`premium_tour.py:260-275`), never in Block 2, and `plan_premium_authoring` reads no receipt evidence. Docstring updated to name `plan_premium_tour`'s bar rather than "the seam's". |
| 5 | `test_prebuilt_route_refuses_a_stop_the_stitch_forgot` | `:396` | Body unchanged — `_plan` is rewritten, and §2.5 preserves the exact match string `"one authoring unit per dwell stop"`. |
| 6 | `test_prebuilt_route_refuses_a_gap_in_the_middle_of_the_stitch` | `:403` | Body unchanged, same reason. |
| 7 | `test_prebuilt_route_refuses_more_than_the_anchor_cap` | `:415` | Body unchanged. The `"one to fifteen stops"` refusal comes from `_certification_compose_requests` at `authoring.py:501-502`, which step 4 does **not** touch. **Step 5 re-points this test at the time budget**; step 4 must leave it asserting the raise, or step 5 has nothing to turn from red to green. |

## 4.4 `tests/test_tour_authoring_gates.py`

* `:43` — delete `author_prebuilt_route, plan_prebuilt_route_authoring` from the
  `src.tour.authoring` import; keep `COMPOSE_MODEL`. Add `plan_premium_authoring`,
  `execute_premium_plan` and `EphemeralReceiptSink` to the existing
  `from src.tour.premium_tour import (...)` block at `:59-65`.
* `_preview_surface_plan` (`:658-698`) — **delete it entirely.** Its whole job was
  converting a `PrebuiltRouteAuthoringPlan` into a `PremiumTourPlan`; after step 2,
  `plan_premium_authoring` returns a `PremiumTourPlan` directly. Every
  `_preview_surface_plan(plan)` call site (`:825`, `:~915`) becomes just `plan`.
* `:718-723`, `:801-806`, `:914-919` — the three `plan_prebuilt_route_authoring(...)`
  calls become `plan_premium_authoring(stitched, sequence, route, snapshot=None,
  snapshot_sha256="0"*64, routing_version="offline-test", policy_version="offline-test")`.
* `:749`, `:810`, `:929` — the three `author_prebuilt_route(...)` calls. These carry gate
  kwargs, so they become explicit execute-then-finalize:
  ```python
  responses = execute_premium_plan(
      plan, executor=executor, receipt_sink=EphemeralReceiptSink()
  )
  composition = finalize_premium_composition(
      plan,
      responses,
      faithfulness_checker=phone_checker,
      enforce_claim_coverage=True,
      scan_glue_for_invention=True,
  )
  ```
* `test_the_certification_replay_keeps_its_own_gate_defaults` (`:508-534`) — the
  `finalize_certification_composition` half (`:521-527`) is **unchanged**. The
  `author_prebuilt_route` half (`:529-533`) must be re-pointed at
  `finalize_premium_composition`, whose parameters (`premium_tour.py:464-471`) carry the
  same three names with the same `None/False/False` defaults. **This is not a weakening**:
  the claim ("the certification replay's gate defaults are untouched") is asserted against
  the function certification actually calls.
* **AC-27 allies at `:758` and `:886` keep every assertion unchanged.** Only the two
  surface-1 driver calls inside them change from `author_prebuilt_route` to
  execute-then-finalize; every `assert` line is byte-identical. Confirm this by diffing —
  if any `assert` in either test changes, step 4 has failed AC-27.

## 4.5 `tests/test_never_silent_failures.py`

* `:61-64` — delete `author_prebuilt_route, plan_prebuilt_route_authoring` from the import;
  keep `COMPOSE_MODEL`.
* `_as_premium_plan` (`:188-223`) — **delete it entirely**, same reason as
  `_preview_surface_plan`.
* `:344-346`, `:398-403`, `:492-494` — `plan_prebuilt_route_authoring(...)` →
  `plan_premium_authoring(...)` with the four provenance kwargs; the resulting object IS
  the premium plan, so `premium_plan = _as_premium_plan(authoring_plan)` (`:347`, `:404`,
  `:495`) collapses to a single `plan` variable.
* `:378`, `:424`, `:519` — `author_prebuilt_route(...)` calls.

**Honest consequence, which must be recorded and not hidden.** This module exists to pin
that **two** fan-out sites each carry `in_current_context`. After the deletion there is
**one** fan-out (`premium_tour.py:460-461`); `authoring.py:980-981` is gone. The
authoring-site assertions at `:375-390`, `:424-431` and `:519-527` no longer have a second
site to test and must be deleted, not retargeted at the same site twice — a duplicated
assertion is a fake guard. The module docstring's four-mutation table (`:36-45`) must lose
its `authoring.py` row.

**This is a genuine reduction in what the file guards, and it is correct**: the second site
is gone, so there is nothing left to prove about it. Say so in the persist note. The
surviving premium-site assertions still bind `in_current_context`'s presence, proven by the
mutation already recorded at `:39-40`.

## 4.6 The one proving test, and how it binds all seven re-points

**Node id:** `tests/test_tour_one_engine.py::test_the_second_authoring_seam_is_gone`

The file already has every tool this needs: `_python_files()` (`:106-113`, walks `src`,
`scripts`, `tests`, `tools`), `_imported_modules` (`:88-103`), `_tracked_files` (`:116-120`)
and the `ast` + `subprocess` house style.

```python
#: The second authoring seam, deleted in this step. Every name must vanish from the
#: whole tree, not merely from ``src/`` — three test modules imported them at module
#: scope, so a half-done deletion collect-errors the suite rather than failing cleanly.
DELETED_SEAM_NAMES = frozenset(
    {
        "PrebuiltRouteComposeUnit",
        "PrebuiltRouteAuthoringPlan",
        "PrebuiltRouteExecutor",
        "prebuilt_route_sha256",
        "plan_prebuilt_route_authoring",
        "author_prebuilt_route",
    }
)

#: The five already-shared helpers the deletion must NOT take with it (AC-11).
SURVIVING_AUTHORING_HELPERS = frozenset(
    {
        "_certification_compose_requests",
        "candidate_compose_request_envelope",
        "compose_input_sha256",
        "_sentences_from_json",
        "finalize_certification_composition",
    }
)


def test_the_second_authoring_seam_is_gone() -> None:
    """AC-1 / AC-9 / AC-11 / AC-22 — one Block-2 seam, and the tree knows it.

    UNDO: any of the three named in the mutation list below turns this RED.
    """
    authoring = REPO_ROOT / "src" / "tour" / "authoring.py"
    tree = ast.parse(authoring.read_text(encoding="utf-8"), filename=str(authoring))

    # 1. The six symbols are not DEFINED in authoring.py any more.
    defined = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.ClassDef))
    }
    assert not defined & DELETED_SEAM_NAMES, sorted(defined & DELETED_SEAM_NAMES)

    # 2. The five shared helpers survive.
    assert SURVIVING_AUTHORING_HELPERS <= defined, sorted(
        SURVIVING_AUTHORING_HELPERS - defined
    )

    # 3. __all__ carries neither them nor AUTHORING_MAX_STOPS.
    exported = {
        elt.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name) and target.id == "__all__"
        for elt in node.value.elts
        if isinstance(elt, ast.Constant)
    }
    assert exported, "authoring.py lost its __all__ entirely"
    assert not exported & DELETED_SEAM_NAMES
    assert "AUTHORING_MAX_STOPS" not in exported

    # 4. REPOSITORY-WIDE: no file under src/ scripts/ tests/ tools/ still names any
    #    of them — as an import, a call, or a bare reference. This is the clause that
    #    binds the test re-points: an un-re-pointed test module is a hit here.
    offenders: dict[str, set[str]] = {}
    for path in _python_files():
        if path.name == "test_tour_one_engine.py":
            continue  # this file names them as data, on purpose
        file_tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        named = {
            node.id for node in ast.walk(file_tree) if isinstance(node, ast.Name)
        } | {
            alias.name
            for node in ast.walk(file_tree)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        } | {
            node.attr for node in ast.walk(file_tree) if isinstance(node, ast.Attribute)
        }
        hit = named & DELETED_SEAM_NAMES
        if hit:
            offenders[str(path.relative_to(REPO_ROOT))] = hit
    assert not offenders, (
        "the second authoring seam still has live references, so the deletion is "
        f"half-done and the suite will collect-error: {offenders}"
    )

    # 5. The AUTHOR block cannot reach a planner — the function-scoped guard, run
    #    from here too so the deletion and the prohibition share one node id.
    from tests.test_tour_authoring_from_route import (
        _assert_the_seam_cannot_reach_the_planner,
    )

    _assert_the_seam_cannot_reach_the_planner()
```

### Why this is ONE atomic step, and how every change is bound

I considered the three options the planner-manager put and chose **(c) — it is genuinely
one atomic change** — because (a) and (b) are provably unavailable:

* **(a) is unavailable.** Re-pointing step 4's command at the planner-prohibition test in
  `test_tour_authoring_from_route.py` would not be RED before the change. After step 2,
  `plan_premium_authoring` already exists and the four Block-2 bodies already call no
  planner (§4.2 lists every name they call). A re-pointed prohibition test would pass on
  the pre-step-4 tree. A green-before test proves nothing.
* **(b) is unavailable for the seven re-points.** All three test modules import the doomed
  names at **module scope** — `tests/test_tour_authoring_from_route.py:33-38`,
  `tests/test_tour_authoring_gates.py:43`, `tests/test_never_silent_failures.py:61-64` — so
  the instant `authoring.py:805-1038` goes, all three collect-error. None of the seven can
  legally land later. (`tests/test_tour_authoring_gates.py:520` also has a function-local
  import of `author_prebuilt_route`; it must be fixed in the same edit.)
* **(c) holds, and clause 4 is the binding mechanism.** The repository-wide AST scan walks
  `tests/` as well as `src/` (`_python_files()`, `test_tour_one_engine.py:106-113`). So
  reverting **any single one** of the re-points reintroduces a hit and turns the step's own
  proving command RED. That is not an argument — it is the same mechanism AC-11 already
  specifies ("a repository-wide search for each returns zero hits").

**The mutations, one per distinct behaviour step 4 changes:**

| # | Behaviour changed | One-line revert that turns the proving command RED |
| --- | --- | --- |
| M1 | the six symbols are deleted from `authoring.py` | add `def author_prebuilt_route(*a, **k): ...` at the end of `src/tour/authoring.py` → clause 1 RED |
| M2 | `__all__` is pruned | add `"author_prebuilt_route",` back into `src/tour/authoring.py`'s `__all__` → clause 3 RED |
| M3 | the five shared helpers survive | rename `def compose_input_sha256(` to `def compose_input_sha256_(` in `src/tour/authoring.py` → clause 2 RED |
| M4 | re-point #1, `test_tour_authoring_from_route.py` | restore `script = author_prebuilt_route(plan, executor=executor)` at its line → clause 4 RED, naming that file |
| M5 | re-points #2-#7, same file | same shape — restore any one `author_prebuilt_route(` or `plan_prebuilt_route_authoring(` call → clause 4 RED |
| M6 | re-point, `test_tour_authoring_gates.py` | restore `author_prebuilt_route,` in the `src.tour.authoring` import at `:43` → clause 4 RED |
| M7 | re-point, `test_never_silent_failures.py` | restore `author_prebuilt_route,` in the import at `:62` → clause 4 RED |
| M8 | the planner prohibition is function-scoped and still holds | add `    from .selection import select_k_routes` as the first statement of `plan_premium_authoring`'s body in `src/tour/premium_tour.py` → clause 5 RED |

**UNBOUND — stated plainly rather than papered over.** The proving command binds that each
re-pointed test *stops naming the deleted symbols*. It does **not** bind that each
re-pointed test still *asserts the same thing*. Someone could gut
`test_the_author_block_never_replans`'s body to `pass` and clause 4 would stay green.

Two mitigations, both required for step 4:

1. Add to step 4's `gate_commands`:
   `make test-file FILE="tests/test_tour_authoring_from_route.py::test_the_author_block_never_replans"`.
   That file's own docstring (`:19-22`) already says this node id carries every clause, so
   reverting a clause turns the gate red.
2. Step 4's skeptic panel must be handed the assertion-level diff of all three test files
   with the instruction: *any deleted or weakened `assert` is a finding*. AC-27 names the
   two ally tests in `test_tour_authoring_gates.py` explicitly; §4.4 requires them to be
   `assert`-line-identical.

## 4.7 Ordering hazards inside step 4

The tree is RED in the middle of this step no matter what. The order that keeps the red
window to a single save:

1. Rewrite `tests/test_tour_authoring_from_route.py` (helpers first, then the seven tests).
2. Rewrite `tests/test_tour_authoring_gates.py`, including the function-local import at `:520`.
3. Rewrite `tests/test_never_silent_failures.py`, deleting the second-site assertions.
4. **Only now** delete `src/tour/authoring.py:785-1038` and prune `__all__`.
5. Run `make lint` and remove the `F401` imports it names in `authoring.py`.
6. Add `test_the_second_authoring_seam_is_gone` to `tests/test_tour_one_engine.py`.

Steps 1-3 leave the tree green (both the old and the new callables exist). Step 4 is the
only moment it can break, and step 6 is what proves it did not.

Because step 4 now cites AC-28 and AC-29: `make lint` unpiped and in full is a gate
command, and the phase gate after step 4 must run the full suite — the three edited test
modules are the ones most likely to collect-error, and a collect error is not visible from
a single node-id run.

---

# BLOCKING AMBIGUITY

## B1 — AC-10's literal wording versus what Phase 1 can actually deliver (step 3)

**The problem.** AC-10 says: *"Given the compose path, when the same parse is applied to
it, then `summarise_route` does not appear."* Step 3 cannot satisfy that literally. Compose
persists only a list of POI ids (`trips.py:541-550`), so it **must** rebuild a `Route`
before anything can author it. The only in-scope way to build one from an ordered POI list
is `summarise_route` (`routing.py:400`); `select_k_routes` and `plan_premium_tour` are
planners and are forbidden by the two-block design. Persisting the full route instead is
explicitly Phase 2 (`state.json` `out_of_scope`: workbench persistence), and steps 9-11 are
what make an option carry its own route.

**What §3.3.2 does deliver** is AC-10's stated *reason* in full: "today it is called at
`trips.py:570-578` with no policy, which is the third route into the legacy 0.83 budget."
After step 3 it is called **with** `certification_planning_policy(...)`, so no compose can
obtain a 0.83 walk budget. Step 6 then deletes `LEGACY_ROUTE_PLANNING_POLICY`
(`routing.py:124-128`) and makes the parameter unavoidable.

**Recommendation.** Narrow AC-10 to: *"no call to `summarise_route` on the compose path
omits an explicit certification planning policy"*, and move the literal removal of the name
to the step that gives a persisted option its own route (step 9 or 11). The alternative —
hiding the call behind a wrapper in `src/tour/` so a source parse of `compose_trip` stops
seeing the name — satisfies the letter and defeats the purpose, and I recommend against it.

## B2 — the HTTP shape for an unresolvable build fingerprint on compose (step 3)

**The problem.** `finalize_premium_tour` resolves a git build fingerprint that compose has
never needed (§3.2). Its failure is an environment fault and must not be reported as
`compose_verification_failed`. `/trips/preview` answers this by falling back to the Basic
lane with `CandidateRejectionCode.BUILD_FINGERPRINT_UNAVAILABLE` (`trips.py:995-1008`).
Compose has no Basic lane — it either authors and persists, or it refuses — so it needs a
status code, and the phone parses only `detail["reason"]` and `detail["attempts"]`
(`mobile/lib/services/trip_service.dart:227-229`).

**Options.**
1. `503 {"reason": "build_fingerprint_unavailable", "detail": ...}` with `Retry-After: 30`
   — what §3.3.3 is written for. Truthful, retryable, and distinct from a narration
   refusal. The phone shows a generic error because it does not know this `reason`.
2. Let it raise → bare 500. Loud and truthful, but strands the phone with no retry hint
   and reproduces the pattern a prior ledger already flagged as a defect
   (`specs/2026-08-03-premium-tour-crash-never-silent`, D7).
3. Give compose a `PremiumBuildIdentity` it constructs itself, never calling
   `resolve_build_identity`. Removes the failure mode entirely, but writes a provenance
   claim that is not measured — the exact class of lie `resolve_build_identity`'s docstring
   (`premium_tour.py:569-573`) exists to prevent.

**Recommendation: option 1.** It needs no mobile change and no new module, and it keeps the
`compose_verification_failed` code meaning only what it says.

**Note for whoever answers.** Whichever is chosen, `ONDOWAY_ALLOW_DIRTY_LOCAL_BUILD=1` is
today set only by `scripts/workbench.sh:72`. Nothing in the Makefile or `tests/conftest.py`
sets it, so **every compose test in `make test` will 503 on a dirty developer tree** once
step 3 lands. Either the compose test fixtures inject a `build_identity`, or the pytest
targets must export that variable. This is the single most likely way step 3 turns the
suite red for a reason unrelated to the change.
