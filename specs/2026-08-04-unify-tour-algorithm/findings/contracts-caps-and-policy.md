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
> **DEAD IN THIS FILE:** the recommendation to KEEP `quality_rubric.MAX_COMPOSED_STOPS = 8` and correct only its comment. The owner overruled it — remove the constant and its enforcement in step 5.5, alongside `src/tour/quality_rubric.py` and `tests/test_tour_quality_rubric.py`.

---

# Implementation contract — STEP 5 (stop ceiling) and STEP 6 (0.83 policy)

Written against commit `a7df218c`. Every claim below carries `file:line`. Nothing here
requires the implementer to infer, choose, or design. Where an owner decision is genuinely
required it is in **BLOCKING AMBIGUITY** at the end and nowhere else.

Measurements in this document were taken by importing the real, pure modules
(`src/tour/ordering.py`, `src/tour/routing.py`, `src/tour/contract.py`) in a hermetic
throwaway script — no database, no container, no provider, matching the hermeticity that
`tests/test_tour_ordering_heldkarp.py:1` already claims for the same function. No source
file was edited and no container was touched.

---

## 0. Executive summary of what changed relative to the ledger

Six findings materially change what steps 5 and 6 ARE. Each is proven below.

1. **Deleting `max_stops` from the certification policy, alone, breaks every certification
   tour.** `selection.py:2892-2893` raises `ValueError("certification repair requires an
   authorized stop cap")` when `planning_budget.max_stops is None`, and
   `selection.py:2830` returns `None` from every priced trial in the same case. That
   `ValueError` is caught at `trips.py:956` and returned as a 422
   `premium_route_infeasible` — i.e. the preview refuses every tour. Step 5 must change
   `selection.py:2830`, `:2892-2893` and `:2958` or it ships a total outage.
2. **The exponential orderer is not the worst cost — the repair loop that calls it is.**
   `_apply_certification_timebox_repair` (`selection.py:2870`) calls
   `_certification_route_trial` (`:2811`), which calls `held_karp_open` (`:2832`), once per
   (incumbent × candidate) pair — `selection.py:2949-2983`. Today that is bounded only
   because `max_stops=8` bounds the incumbents. Removing the cap makes the *number of
   exponential calls* grow with the stop count too.
3. **There is a seventh stop ceiling nobody listed**: `quality_rubric.py:180`
   `MAX_COMPOSED_STOPS: int = 8`, whose own comment sources it from
   `premium_tour.py (max_stops=8)`. It caps the C3 thinness floor at
   `8 × 850 × 0.5 = 3400` words (`quality_rubric.py:274-279`).
4. **`scripts/tour_batch_candidate.py` needs no change in step 5.** It calls
   `certification_planning_policy(policy_id=...)` (`scripts/tour_batch_candidate.py:54-57`)
   and passes no `max_stops`. Its presence in step 5's `files[]` is spurious.
5. **Q2 as written is refuted** (section 6). The real gap is `ERR_SHORT`'s six readers,
   principally `src/tour/density.py`, which is in no step's `files[]` at all.
6. **Q3 is worse than described** (section 7): after step 6 the collapse lets
   `CertificationPlanningInfeasibleError` escape `POST /trips/generate` **uncaught**
   (`trips.py:319-328` catches only `TourabilityRefusedError`) — a 500 to the phone, not a
   degraded 422. And the phone never parsed the alternatives payload in the first place; the
   surface that renders it is the workbench (`frontend/review.html:3281`).

---

## 1. Q1 — the exponential orderer. VERDICT AND CONTRACT.

### 1.1 The real complexity and the real constant (measured)

`held_karp_open` (`src/tour/ordering.py:19-102`). The DP is
`for mask in range(1 << n)` (`:67`) × `for i in range(n)` (`:69`) × `for j in range(n)`
(`:74`), so the transition count is exactly `2^n · n²`. Memory is two dense arrays of the
same shape, `dp` and `parent` (`ordering.py:62-63`), each `2^n` Python lists of `n` entries.

Measured on this machine, CPU 3.13.12, one call, random points in a 0.02° box around Paris:

| n | wall seconds | peak RSS (MB) | 2^n·n² | ns per transition |
|---|---|---|---|---|
| 12 | 0.023 | 36 | 589,824 | 38.8 |
| 15 | 0.241 | 54 | 7,372,800 | 32.6 |
| 16 | 0.555 | 76 | 16,777,216 | 33.1 |
| 17 | 1.222 | 123 | 37,879,808 | 32.3 |
| 18 | 2.841 | 217 | 84,934,656 | 33.5 |
| 19 | 6.529 | 430 | 189,267,968 | 34.5 |
| 20 | 14.458 | 846 | 419,430,400 | 34.5 |
| 21 | 31.562 | 1,751 | 924,844,032 | 34.1 |

**The real constant is ~34 ns per transition and ~40 bytes of resident memory per
`2^n · n` slot.** Both scale cleanly, so extrapolation is safe:

- n = 22 → ~68 s, ~3.5 GB
- n = 25 → ~12 min, ~33 GB — this machine has no such memory; it dies in swap
- n = 30 → ~9 hours, ~1.3 TB — not a slow test, an unkillable one

**What n makes it unacceptable: 17.** `tests/test_tour_ordering_heldkarp.py:133-144`
asserts `time.process_time() < 1.0` at `HARD_ANCHOR_CAP` points, and
`tests/test_tour_selection.py:612-616` asserts `HARD_ANCHOR_CAP <= 16` for exactly this
reason. 16 measures 0.555 s; 17 measures 1.222 s and breaks the existing guarantee.

**Multiply that by how often it is called.** `held_karp_open` has four call sites:
`selection.py:1933` (inside a `while True:` rescue-rollback loop, `:1929-1968`), `:2017`
(once per route), `:2832` (once per priced trial), `:3067` (inside the endpoint-pull
`while True:` loop, `:3052`). `_apply_certification_timebox_repair` calls
`_certification_route_trial` once for the base (`:2895`), once per pool candidate
(`:2958-2964`), and once per (incumbent × pool candidate) pair (`:2965-2983`). With the
current 8-stop cap and a Paris-sized eligible pool that is on the order of 10³ exponential
calls at n ≤ 9 (~2 ms each). Uncapped at n = 25 it is 10⁴ calls that individually cannot
complete. And `select_k_routes` (`selection.py:2147`) runs the whole of `select_route` up to
3 times (`:2168`, `:2183`), and the preview asks for K = 3 (`premium_tour.py:252-258`).

**Without a fix, step 5 does not produce a slow test. It produces a test that never
returns, and a non-returning test is not RED.** That is why Q1 gates step 5.

### 1.2 Is there already a cheaper orderer in the codebase?

No standalone one. A repository-wide search for `2-opt`, `two_opt`, `nearest_neighbour`,
`nearest_neighbor`, `or-opt`, `greedy_order` over `src/` returns zero hits. But the
**primitive** exists and is public and tested: `insertion_cost_seconds`
(`src/tour/routing.py:307-343`) returns `(best_extra_walk_seconds, best_insertion_index)`
for a candidate against an ordered list, honouring `round_trip` and the injected
`leg_seconds_fn`. It is already the ordering currency of the greedy (`selection.py:2509`
`_insertion`, `:2434` `_apply_fill_pass`).

**Therefore: do not invent 2-opt. Build the fallback out of `insertion_cost_seconds`.**
This is cheapest-insertion — the exact heuristic the greedy already uses, promoted to a
whole-set orderer. Measured, using the real `insertion_cost_seconds`:

| n | 16 | 20 | 25 | 30 | 40 | 60 | 100 | 150 |
|---|---|---|---|---|---|---|---|---|
| seconds | 0.001 | 0.002 | 0.003 | 0.005 | 0.010 | 0.034 | 0.152 | 0.508 |

At n = 40 it is **10 ms** against Held-Karp's ~4 days. It is O(n³) leg evaluations and stays
under a second to n ≈ 180, which is above the entire eligible Paris candidate pool.

### 1.3 THE CONTRACT

**Constant.** `src/tour/selection.py:265-273` currently reads:

```python
ANCHOR_CAP_DIVISOR: int = 10
# Outer anchors only — internal vignettes don't count. Raised 12→15 (2026-07-11)
# ... 15 keeps the EXACT Held-Karp order solver comfortably under its 1s guard
# (~249ms measured; 2^15·15^2 ≈ 7.4M transitions). Do NOT exceed 16 ...
HARD_ANCHOR_CAP: int = 15  # outer anchors only — internal vignettes don't count
```

Delete `ANCHOR_CAP_DIVISOR` and `HARD_ANCHOR_CAP` from `selection.py` entirely. Add to
`src/tour/ordering.py`, immediately after the imports (`ordering.py:16`):

```python
#: Most points the EXACT open-path Held-Karp solver may be handed. NOT a product
#: limit on tour length — duration is the only such bound. Purely a tractability
#: wall: the DP costs 2^n·n^2 transitions at a MEASURED ~34 ns each and holds
#: 2^n·n slots at ~40 bytes, so n=16 is 0.55 s / 76 MB, n=17 is 1.22 s / 123 MB
#: (past the sub-second guarantee tests/test_tour_ordering_heldkarp.py:133 pins),
#: and n=25 is ~12 minutes / ~33 GB — an unkillable test, not a slow one.
#: Above this, order_stops falls back to cheapest insertion; it never DROPS a
#: stop the time budget earned.
ORDERING_EXACT_MAX: int = 16
```

**New dispatcher and fallback, both in `src/tour/ordering.py` (no new module).** Exact
signatures:

```python
def cheapest_insertion_open(
    points: list[POI] | tuple[POI, ...],
    *,
    fixed_start: tuple[float, float],
    fixed_end: POI | None = None,
    round_trip: bool = False,
    routed_cost_fn: LegSecondsFn | None = None,
) -> list[POI]:
    """Cheapest-insertion order for ``points`` walking out of ``fixed_start``.

    O(n^3) leg evaluations through routing.insertion_cost_seconds — the same
    marginal-cost currency the greedy already uses (selection.py:2509). Not
    optimal; tractable at any n the corpus can produce (MEASURED 10 ms at n=40,
    0.51 s at n=150). Contract-identical to held_karp_open: same argument names,
    same ValueErrors, ``fixed_end`` pinned last, deterministic under input
    permutation (candidates are consumed in ascending id order and equal-cost
    insertions keep the earliest index, per insertion_cost_seconds' own
    strict ``<`` at routing.py:339).
    """


def order_stops(
    points: list[POI] | tuple[POI, ...],
    *,
    fixed_start: tuple[float, float],
    fixed_end: POI | None = None,
    round_trip: bool = False,
    routed_cost_fn: LegSecondsFn | None = None,
) -> list[POI]:
    """Order ``points`` exactly when tractable, by cheapest insertion above it.

    ``len(points) <= ORDERING_EXACT_MAX`` -> held_karp_open, byte-identical to
    today for every input the engine could previously produce. Above it ->
    cheapest_insertion_open. The tour KEEPS every stop the time budget earned;
    only the optimality guarantee is traded away.
    """
```

`order_stops` body, exactly:

```python
    if fixed_end is not None and round_trip:
        raise ValueError("fixed_end and round_trip are mutually exclusive")
    if len(points) <= ORDERING_EXACT_MAX:
        return held_karp_open(
            points,
            fixed_start=fixed_start,
            fixed_end=fixed_end,
            round_trip=round_trip,
            routed_cost_fn=routed_cost_fn,
        )
    return cheapest_insertion_open(
        points,
        fixed_start=fixed_start,
        fixed_end=fixed_end,
        round_trip=round_trip,
        routed_cost_fn=routed_cost_fn,
    )
```

`cheapest_insertion_open` body, exactly (it must not import from `selection`, which would
create a cycle; it uses only `routing`):

```python
    if fixed_end is not None and round_trip:
        raise ValueError("fixed_end and round_trip are mutually exclusive")
    pts = list(points)
    if len(pts) <= 1:
        return pts
    if fixed_end is not None and all(p.id != fixed_end.id for p in pts):
        raise ValueError(f"fixed_end {fixed_end.id!r} is not among the points")
    pool = sorted(
        (p for p in pts if fixed_end is None or p.id != fixed_end.id),
        key=lambda p: p.id,
    )
    ordered: list[POI] = []
    for cand in pool:
        _extra, idx = insertion_cost_seconds(
            cand,
            ordered,
            start_lat=fixed_start[0],
            start_lng=fixed_start[1],
            round_trip=round_trip,
            leg_seconds_fn=routed_cost_fn,
        )
        ordered.insert(idx, cand)
    if fixed_end is not None:
        ordered.append(fixed_end)
    return ordered
```

Add `insertion_cost_seconds` to the existing import at `ordering.py:16`:

```python
from .routing import LegSecondsFn, default_leg_seconds, insertion_cost_seconds
```

`default_leg_seconds` stays — `held_karp_open:48` still uses it.

**Caller rewrites.** All four `held_karp_open` call sites in `selection.py` become
`order_stops`; the keyword arguments are identical in every case, so each is a one-token
edit. Sites: `selection.py:1933`, `:2017`, `:2832`, `:3067`. The import at
`selection.py:56` changes from

```python
from .ordering import held_karp_open
```

to

```python
from .ordering import ORDERING_EXACT_MAX, order_stops
```

(`ORDERING_EXACT_MAX` is imported because `_apply_certification_timebox_repair` needs it —
see 2.4.) `held_karp_open` stays public and exercised by
`tests/test_tour_ordering_heldkarp.py`; only `selection` stops calling it directly.

**The bound that makes a pathological case FAIL rather than HANG.** Two independent
mechanisms, both required:

1. *Production:* `order_stops` can never enter an exponential branch, because the branch is
   guarded on `len(points)` before the call, not after.
2. *Test:* step 5's proving test asserts BOTH an equality (instant) and a CPU bound —
   see 3.3. The equality assertion is what makes the mutation go RED **in 1.2 s** rather
   than hanging, because it is written at n = 17, where Held-Karp still returns.

Do **not** add a wall-clock timeout in production code. Wall clock is load-dependent and
would make `make test` flaky on a contended host; `tests/test_tour_ordering_heldkarp.py:139`
already records that lesson verbatim ("`process_time` (CPU), not `perf_counter` (wall)").

---

## 2. STEP 5 — remove the stop ceiling. FULL DELETION AND REWRITE LIST.

### 2.0 Scope decision: SPLIT into step 5 and step 5.5, along the dependency line

The manager asked me to choose (a) split or (b) one strengthened test, and to prove the
tree is green between them if I split. **I choose (a), but NOT along the line the ledger
implies.**

Why not (b): a single node id binding all seven changes can only be an AST/grep test. A
grep test proves a constant is absent; it proves nothing about a 20-stop tour actually
planning, ordering and authoring. AC-16 is a behavioural criterion and deserves a
behavioural test.

Why not the obvious split (policy constant now, selection internals later): **it is not
green in between.** Removing `max_stops=8` from `certification_planning_policy`
(`premium_tour.py:234`) makes `planning_budget.max_stops` `None` for every certification
route, and `selection.py:2892-2893` then raises
`ValueError("certification repair requires an authorized stop cap")` on **every**
certification tour, which `trips.py:953-965` converts into a 422 on every preview. Proven
by reading `selection.py:1970-1982` (repair is invoked for every non-legacy policy) and
`:2892`.

The true dependency line is **planner-side vs authoring-side**:

- **Step 5 (planner-side).** Everything reachable from `RoutePlanningPolicy.max_stops` plus
  the Q1 ordering work. These are mutually dependent; there is no green intermediate.
- **Step 5.5 (authoring-side).** `AUTHORING_MAX_STOPS`, `MAX_CANDIDATE_STOPS`,
  `MAX_COMPOSED_STOPS`. **Green in isolation, proven:** each is read only inside its own
  module's own validator (`authoring.py:501`, `candidate_authoring.py:154,177`,
  `quality_rubric.py:276`); none is read by `selection`, `routing` or `premium_tour`; and
  each only *rejects* stop counts above 15/15/8, so removing them can only widen what is
  accepted. Nothing in `src/` asserts they exist. The only cross-module coupling is the two
  test-side identity assertions `AUTHORING_MAX_STOPS == selection.HARD_ANCHOR_CAP == 15`
  (`tests/test_tour_authoring_from_route.py:338` and `:358`), which step 5 must delete
  because it deletes `HARD_ANCHOR_CAP`; deleting those two assertion lines in step 5 leaves
  step 5.5's constants untouched and the file green.

Step 5.5 gets id `"5.5"` (the ledger schema supports an inserted non-integer id and forbids
renumbering), `depends_on: ["4"]` — it does **not** depend on 5 — `criterion_ids:
["AC-15"]`, and `gate_commands: ["make lint"]`.

### 2.1 STEP 5 — `src/tour/routing.py`

**Delete (a) the field, (b) the validation clause, (c) the classmethod kwarg, (d) the
budget field, (e) the budget assignment.**

Current, `routing.py:66-108` (quoted):

```python
    policy_id: str
    minimum_requested_fraction: float
    maximum_requested_fraction: float
    max_stops: int | None = None

    def __post_init__(self) -> None:
        values = (self.minimum_requested_fraction, self.maximum_requested_fraction)
        if not all(math.isfinite(value) and value > 0 for value in values):
            raise ValueError("planning fractions must be finite and positive")
        if self.minimum_requested_fraction > self.maximum_requested_fraction:
            raise ValueError("minimum planning fraction exceeds maximum")
        if self.max_stops is not None and not 1 <= self.max_stops <= 8:
            raise ValueError("certification planning supports one to eight stops")
...
    @classmethod
    def certification(
        cls,
        *,
        minimum_requested_fraction: float,
        maximum_requested_fraction: float,
        max_stops: int,
        policy_id: str,
    ) -> RoutePlanningPolicy:
        """Build from the frozen TIME band and authorized compose-stop limit."""

        if not policy_id or policy_id == "legacy-err-short-v1":
            raise ValueError("certification planning requires its frozen policy id")
        return cls(
            policy_id=policy_id,
            minimum_requested_fraction=minimum_requested_fraction,
            maximum_requested_fraction=maximum_requested_fraction,
            max_stops=max_stops,
        )
```

Replacement (step 5 only; step 6 removes `is_legacy` and the `"legacy-err-short-v1"`
guard — see 5.2):

```python
    policy_id: str
    minimum_requested_fraction: float
    maximum_requested_fraction: float

    def __post_init__(self) -> None:
        values = (self.minimum_requested_fraction, self.maximum_requested_fraction)
        if not all(math.isfinite(value) and value > 0 for value in values):
            raise ValueError("planning fractions must be finite and positive")
        if self.minimum_requested_fraction > self.maximum_requested_fraction:
            raise ValueError("minimum planning fraction exceeds maximum")
...
    @classmethod
    def certification(
        cls,
        *,
        minimum_requested_fraction: float,
        maximum_requested_fraction: float,
        policy_id: str,
    ) -> RoutePlanningPolicy:
        """Build from the frozen TIME band. Duration is the only stop bound."""

        if not policy_id or policy_id == "legacy-err-short-v1":
            raise ValueError("certification planning requires its frozen policy id")
        return cls(
            policy_id=policy_id,
            minimum_requested_fraction=minimum_requested_fraction,
            maximum_requested_fraction=maximum_requested_fraction,
        )
```

`RoutePlanningBudget`, `routing.py:111-121`: delete the field `max_stops: int | None`
(`:121`). `route_planning_budget`, `routing.py:154`: delete the line
`        max_stops=policy.max_stops,`.

Docstring correction, `routing.py:99` — `"""Build from the frozen TIME band and authorized
compose-stop limit."""` names a limit that no longer exists; replaced above.

**Proof of no surviving caller for `RoutePlanningPolicy.max_stops` / `certification(...,
max_stops=)`.** `grep -rn "max_stops" --include='*.py' src/ tests/ scripts/` returns, in
`src/`: `routing.py:69,77,96,107,121,154`, `premium_tour.py:234`, `selection.py:1699,1706,
1879,1907,2830,2892,2958`, and `api/models/trips.py:49` + `api/routes/trips.py:294`. The
last two are a **different** `max_stops` — the wire field on `TripGenerateRequest`, which
`trips.py:294` documents as accepted for back-compat and which `Docs/Markdown
Docs/API_REFERENCE.md:360` records as "INERT since M0b". **Do not touch it**; it is not a
planning cap, `mobile/lib/services/trip_service.dart:51` still sends it, and
`tests/test_trip_models.py:118-142` pins its validation.

### 2.2 STEP 5 — `src/tour/premium_tour.py`

Current, `premium_tour.py:230-236`:

```python
def certification_planning_policy(*, policy_id: str) -> RoutePlanningPolicy:
    return RoutePlanningPolicy.certification(
        minimum_requested_fraction=MIN_REQUESTED_FRACTION,
        maximum_requested_fraction=MAX_REQUESTED_FRACTION,
        max_stops=8,
        policy_id=policy_id,
    )
```

Replacement:

```python
def certification_planning_policy(*, policy_id: str) -> RoutePlanningPolicy:
    return RoutePlanningPolicy.certification(
        minimum_requested_fraction=MIN_REQUESTED_FRACTION,
        maximum_requested_fraction=MAX_REQUESTED_FRACTION,
        policy_id=policy_id,
    )
```

The public signature is unchanged, so `scripts/tour_batch_candidate.py:54-57` — the only
other caller — needs **no edit**. Remove `scripts/tour_batch_candidate.py` from step 5's
`files[]`.

### 2.3 STEP 5 — `src/tour/selection.py`, the clamp and the two fallbacks

**(a) Constants.** Delete `selection.py:261-273` in full (the `§5 Q5` comment block,
`ANCHOR_CAP_DIVISOR: int = 10`, the `HARD_ANCHOR_CAP` rationale comment, and
`HARD_ANCHOR_CAP: int = 15`). Both symbols move out of the module; the tractability role
they used to carry is now `ordering.ORDERING_EXACT_MAX` (1.3).

**(b) The clamp.** Current, `selection.py:1696-1707`:

```python
    walk_budget = planning_budget.walk_budget_seconds
    audio_budget = planning_budget.audio_target_seconds
    max_anchors = min(HARD_ANCHOR_CAP, max(1, input.duration_min // ANCHOR_CAP_DIVISOR))
    if planning_budget.max_stops is not None:
        # A coordinate-only B can materialize as one additional sentinel.  Reserve
        # that slot up front; the bounded repair may use it for a real destination
        # POI when B snaps to one of the selected stops.
        reserved_for_b = 1 if input.end is not None else 0
        max_anchors = min(
            max_anchors,
            max(1, planning_budget.max_stops - reserved_for_b),
        )
```

Replacement:

```python
    walk_budget = planning_budget.walk_budget_seconds
    audio_budget = planning_budget.audio_target_seconds
```

`max_anchors` is then undefined. Its only readers are the greedy's own loop guard — locate
every `max_anchors` reference between `selection.py:1719` and `:1845` and delete each guard
clause, leaving the walk-budget and audio-budget termination conditions (`selection.py:1842-
1845`) as the only stopping rules. **This is the change that implements owner parameter 1:
duration becomes the only bound.**

**(c) The two `or HARD_ANCHOR_CAP` fallbacks.** Current, `selection.py:1879` and `:1907`:

```python
                    hard_anchor_cap=planning_budget.max_stops or HARD_ANCHOR_CAP,
```

```python
        hard_anchor_cap=planning_budget.max_stops or HARD_ANCHOR_CAP,
```

Delete both **keyword arguments**, and delete the parameter and every branch that reads it:

- `_apply_fill_pass` (`selection.py:2434`): delete parameter `hard_anchor_cap: int,`
  (`:2446`); delete the docstring bullet `      - route hits ``hard_anchor_cap``;`
  (`:2464`); at `:2537` change
  `            if len(selected) >= hard_anchor_cap or consumed_audio >= floor_audio:` to
  `            if consumed_audio >= floor_audio:`; at `:2565` change
  `            if cand.id in seated or len(selected) >= hard_anchor_cap:` to
  `            if cand.id in seated:`.
- `_apply_endpoint_pull` (`selection.py:3031`): delete parameter `hard_anchor_cap: int,`
  (`:3041`); delete the whole first `if` block `:3053-3060` (the drop-to-fit-under-cap
  branch) and the whole second `if` block `:3062-3063` (`return list(selected)  # endpoint
  won't fit under cap with allowed drops`); update the docstring at `:3045-3048`, which
  currently promises "dropping at most ENDPOINT_PULL_MAX_DROPS weak incumbents to fit
  walk-budget + anchor-cap" — the anchor-cap half is gone, the walk-budget half at
  `:3081-3089` survives unchanged.

  After deleting both `if` blocks the `while True:` at `:3052` has no `continue` before the
  ordering call; that is correct — the loop still iterates via the drop at `:3088-3089`.

**(d) The `max_stops` guards inside the certification trial and repair — NOT in the ledger,
and load-bearing.** Current, `selection.py:2830-2831`:

```python
    if planning_budget.max_stops is None or len(materialized) > planning_budget.max_stops:
        return None
```

Replacement: **delete both lines.** Every stop set is now priceable.

Current, `selection.py:2892-2893`:

```python
    if planning_budget.max_stops is None:
        raise ValueError("certification repair requires an authorized stop cap")
```

Replacement: **delete both lines.**

Current, `selection.py:2958`:

```python
    if base is not None and len(base.ordered) < planning_budget.max_stops:
```

Replacement:

```python
    if base is not None:
```

**(e) Bounding the repair so a pathological case fails rather than hangs.** Add, next to the
other repair constants, immediately above `_apply_certification_timebox_repair`
(`selection.py:2870`):

```python
#: Most (incumbent, candidate) exchange trials the timebox repair will price.
#: Each trial runs a full exact-or-fallback ordering plus a capped beat-plan
#: pricing (selection.py:2832,2853), so the enumeration at :2965-2983 is
#: |selected| x |pool| trials. Until 2026-08-04 that was bounded only by the
#: 8-stop planning cap; with duration as the sole stop bound it is not bounded
#: at all. The pool is already score-sorted (:2951-2957) and the incumbents are
#: id-sorted (:2965), so truncating at a fixed count is deterministic.
TIMEBOX_REPAIR_MAX_TRIALS: int = 4000
```

and, inside `consider` (`selection.py:2907`), as its first statement:

```python
        if len(observed) >= TIMEBOX_REPAIR_MAX_TRIALS:
            return
```

`observed` (`selection.py:2905`) already counts every priced trial (`:2923`), so this needs
no new counter. **See BLOCKING AMBIGUITY B1 for the number 4000.**

### 2.4 STEP 5 — the ordering dispatcher call sites

Per 1.3: `selection.py:56` import rewrite, and `held_karp_open` → `order_stops` at
`selection.py:1933`, `:2017`, `:2832`, `:3067`. `ORDERING_EXACT_MAX` is imported for the
step-5 test only if the test reaches it through `selection`; prefer importing it from
`src.tour.ordering` in the test and **not** importing it into `selection` at all. Corrected
import line for `selection.py:56`:

```python
from .ordering import order_stops
```

### 2.5 STEP 5.5 — the authoring-side ceilings

**`src/tour/authoring.py`.** Delete `authoring.py:127-135` in full — the `#:` comment block
and `AUTHORING_MAX_STOPS = 15`. Delete `"AUTHORING_MAX_STOPS",` from `__all__`
(`authoring.py:1042`). Current, `authoring.py:501-502`:

```python
    if not 1 <= len(stops) <= AUTHORING_MAX_STOPS:
        raise ValueError("authoring supports one to fifteen stops")
```

Replacement:

```python
    if not stops:
        raise ValueError("authoring requires at least one stop")
```

The lower bound must survive: `_certification_compose_requests` builds `requests` keyed by
stop index (`authoring.py:510-511`) and an empty stop list would silently produce an empty
authoring plan. Step 4 already deletes `authoring.py:802` (the comment
`# 3. Eight stops.  Selection may seat up to ``AUTHORING_MAX_STOPS``.`) with the second
seam; if step 4 has not, delete it here.

**`src/tour/candidate_authoring.py`.** Delete `candidate_authoring.py:11-17` (the `#:`
comment and `MAX_CANDIDATE_STOPS = 15`). Current, `:153-154` and `:176-177`:

```python
    stop_requests: tuple[AuthoringStopRequest, ...] = Field(
        ..., min_length=1, max_length=MAX_CANDIDATE_STOPS
    )
```

```python
    responses: tuple[AuthoringStopResponse, ...] = Field(
        ..., min_length=1, max_length=MAX_CANDIDATE_STOPS
    )
```

Replacements — drop only `max_length`, keep `min_length=1`:

```python
    stop_requests: tuple[AuthoringStopRequest, ...] = Field(..., min_length=1)
```

```python
    responses: tuple[AuthoringStopResponse, ...] = Field(..., min_length=1)
```

**`src/tour/quality_rubric.py`.** Current, `:176-180`:

```python
#: INHERITED. The engine composes at most eight stops — premium_tour.py (``max_stops=8``)
#: and routing.py ("certification planning supports one to eight stops"). Named here so
#: the C3 floor can be capped by what a tour may PHYSICALLY hold; see
#: ``c3_audio_floor_seconds``.
MAX_COMPOSED_STOPS: int = 8
```

Every sentence of that comment is false after step 5. Replacement:

```python
#: JUDGEMENT, 2026-08-04. The number of stops a tour may PHYSICALLY hold, used only to
#: cap the C3 thinness floor (``c3_audio_floor_seconds``) so the floor cannot demand
#: more words than a tour can contain. It is NOT a planning limit and no longer mirrors
#: one: the planner's stop ceiling was deleted 2026-08-04 and duration is now the only
#: bound. 8 is retained as the C3 capacity assumption because moving it changes which
#: tours C3 blocks, which is a rubric-calibration decision, not a consequence of
#: removing the planning cap.
MAX_COMPOSED_STOPS: int = 8
```

**Note this is deliberately a comment-only change**: `MAX_COMPOSED_STOPS` keeps the value 8.
Raising it raises the C3 floor for long tours and would change which tours block — see
BLOCKING AMBIGUITY B2.

### 2.6 STEP 5 — the one proving test

**File:** `tests/test_workbench_matches_the_app.py`
**Function:** `test_the_preview_stop_cap_and_the_persisted_stop_cap_are_pinned` is
**renamed** to `test_duration_is_the_only_stop_bound_on_the_planning_path` (the ledger's
`test_command` must be updated to the new node id).
**Node id:** `tests/test_workbench_matches_the_app.py::test_duration_is_the_only_stop_bound_on_the_planning_path`

It replaces `:2002-2053` in full. What it builds and asserts, in order:

1. **Stubs.** A `CorpusSnapshot` of 40 tier-5 POIs on a 0.0004° lattice around
   `PDV = (48.85675, 2.341033)`, each with 2 active beats — the same construction as
   `tests/test_tour_selection.py:595-605`, which today proves the cap binds. A
   `TourInput(start=PDV, duration_min=400, city_slug="paris")`. No routing client
   (haversine legs), no provider.
2. `route = select_route(inp, snap, planning_policy=certification_planning_policy(policy_id="test"))`
3. `assert len(route.pois) > 15` — **the AC-16 behaviour.** Under the old clamp this is 15.
4. `assert len(route.pois) == len({p.id for p in route.pois})` — no duplicate seating once
   the cap stops truncating.
5. **Q1 dispatch, exactly:** with 17 deliberately collinear-but-shuffled POIs,
   `assert order_stops(pts, fixed_start=PDV) == cheapest_insertion_open(pts, fixed_start=PDV)`
   and `assert order_stops(pts, fixed_start=PDV) != held_karp_open(pts, fixed_start=PDV)`
   (the point set is chosen so the two differ — a set where cheapest insertion is provably
   suboptimal; `tests/test_tour_ordering_heldkarp.py:73` already builds such a "seesaw").
6. **Q1 CPU bound:** `t0 = time.process_time(); order_stops(40 points, fixed_start=PDV);
   assert time.process_time() - t0 < 1.0`.
7. **Absence, AST, in one assertion:** parse `src/tour/premium_tour.py`,
   `src/tour/routing.py` and `src/tour/selection.py`; assert no `ast.keyword` named
   `max_stops`, no `ast.Assign` to `HARD_ANCHOR_CAP` or `ANCHOR_CAP_DIVISOR`, and no
   `ast.Attribute` named `max_stops` on a `planning_budget`/`policy` receiver, appear in
   any of the three.

**THE MUTATION (one line, must turn it RED):** restore `selection.py:1698` to

```python
    max_anchors = min(HARD_ANCHOR_CAP, max(1, input.duration_min // ANCHOR_CAP_DIVISOR))
```

Assertion 3 goes RED (15 is not > 15) and assertion 7 goes RED (the `HARD_ANCHOR_CAP` name
reappears). Runtime of the RED run: under a second.

### 2.7 STEP 5 — per-change revert table (the manager's requirement)

| # | Change | Exact one-line revert | Does the step-5 command go RED? |
|---|---|---|---|
| 1 | `max_anchors` clamp deleted (`selection.py:1698`) | restore the `min(HARD_ANCHOR_CAP, ...)` line | **YES** — assertions 3 and 7 |
| 2 | `max_stops=8` deleted (`premium_tour.py:234`) | re-add `max_stops=8,` | **YES** — assertion 7 (AST keyword) and assertion 3 (clamps to 7 via `:1699-1707`) |
| 3 | `RoutePlanningPolicy.max_stops` field (`routing.py:69`) | re-add `max_stops: int | None = None` | **NO alone** (field with no writer is inert) — **bound only via #2**; the AST check at assertion 7 covers it only because the field name appears as `ast.Attribute` in `selection`. Reverting the field WITHOUT #2 is a no-op the test cannot see. **Marked BOUND-ONLY-JOINTLY.** |
| 4 | `__post_init__` 1..8 clause (`routing.py:77-78`) | re-add the clause | **NO** — unreachable once no caller passes `max_stops`. **UNBOUND.** Justified: it is dead code by construction after #2 and #3; `make lint` catches nothing, and the AST check does not read `routing.__post_init__`. *Recommended remedy: extend assertion 7's AST parse to assert the literal string `"certification planning supports one to eight stops"` is absent from `src/tour/routing.py`.* With that one extra assertion this row becomes **YES**. |
| 5 | `hard_anchor_cap` param + branches (`selection.py:2446,2537,2565,3041,3053-3063,1879,1907`) | re-add the parameter and its `:2537` guard | **YES** — a re-added `hard_anchor_cap` parameter with no caller passing it is a `TypeError` at `:1894`; and if the keyword is restored too, assertion 3 goes RED (fill pass re-clamps to 15) |
| 6 | `_certification_route_trial` `max_stops` guard (`selection.py:2830`) | restore `if planning_budget.max_stops is None or ...: return None` | **YES** — with `max_stops` gone from the budget this is an `AttributeError`; with it restored, every trial returns `None` and `:2995` raises `CertificationPlanningInfeasibleError`, so `select_route` at step 2 raises and assertion 3 never runs |
| 7 | repair `ValueError` guard (`selection.py:2892-2893`) | restore it | **YES** — same mechanism as #6 |
| 8 | `order_stops` dispatch (`ordering.py`, 4 call sites) | set `ORDERING_EXACT_MAX = 17` | **YES in 1.2 s** — assertion 5's inequality flips and assertion 6's CPU bound is exceeded. This is why assertion 5 is written at n = 17 and not n = 25: at 25 the mutated code would never return, and a hang is not RED |
| 9 | `TIMEBOX_REPAIR_MAX_TRIALS` guard (`selection.py:2907`) | delete the early return | **NO** — the 40-POI lattice does not reach 4000 trials. **UNBOUND.** *Recommended remedy: a second assertion in the same test that monkeypatches `TIMEBOX_REPAIR_MAX_TRIALS` to 3 and asserts `select_route` still returns a route rather than raising.* With it, **YES**. |

Two rows (#4 and #9) are unbound as the test stands. Both have a stated one-assertion
remedy. **Implement both remedies**; do not ship the step with an unbound change.

### 2.8 STEP 5.5 — the one proving test and its revert table

**File:** `tests/test_tour_candidate_authoring.py`
**Function:** `test_no_authoring_surface_imposes_a_stop_ceiling`
**Node id:** `tests/test_tour_candidate_authoring.py::test_no_authoring_surface_imposes_a_stop_ceiling`

Builds `_wide_plan(20)` (the existing helper at `tests/test_tour_candidate_authoring.py:190`
takes a stop count) and asserts, in order:

1. `AuthoringCandidatePlan` with 20 stop requests validates — no `ValidationError`.
2. `AuthoringCandidateResponseSet` with 20 responses validates.
3. `_certification_compose_requests` over a 20-stop stitched script returns 20 requests.
4. `_certification_compose_requests` over an empty stitched script raises
   `ValueError("authoring requires at least one stop")`.
5. AST: `MAX_CANDIDATE_STOPS` and `AUTHORING_MAX_STOPS` are absent from
   `src/tour/candidate_authoring.py` and `src/tour/authoring.py`, and
   `"AUTHORING_MAX_STOPS"` is absent from `authoring.__all__`.

| Change | Exact revert | RED? |
|---|---|---|
| `max_length=MAX_CANDIDATE_STOPS` on `stop_requests` (`candidate_authoring.py:154`) | re-add `, max_length=15` | **YES** — assertion 1 |
| same on `responses` (`:177`) | re-add `, max_length=15` | **YES** — assertion 2 |
| `1 <= len(stops) <= AUTHORING_MAX_STOPS` (`authoring.py:501`) | restore the line | **YES** — assertion 3 |
| the `if not stops` lower bound | delete it | **YES** — assertion 4 |
| `MAX_COMPOSED_STOPS` comment (`quality_rubric.py:176-180`) | restore the old comment | **NO** — a comment. **UNBOUND, and correctly so:** the value does not change, so there is no behaviour to bind. It is a documentation correction required by the "a doc that contradicts the code gets corrected or deleted" rule, verified by reading the diff, not by a test. |

---

## 3. STEP 5 — every other test that must move, with its reason

Node ids and the exact change. None can wait for a later step, because each names a symbol
step 5 deletes and would fail at **collection** or import time.

| Node id | Change | Why it cannot wait |
|---|---|---|
| `tests/test_tour_selection.py::test_long_tour_seats_more_than_the_old_twelve_stop_cap` (`:590-609`) | delete `assert n <= HARD_ANCHOR_CAP` (`:609`); keep `assert n > 12` | `HARD_ANCHOR_CAP` no longer importable — `tests/test_tour_selection.py:15` |
| `tests/test_tour_selection.py` line 15 import block | remove `HARD_ANCHOR_CAP` from the import | module-level `ImportError` collects the whole file RED |
| `tests/test_tour_selection.py::test_phase7_fill_pass_respects_hard_anchor_cap` (`:1450-1468`) | **delete the test**; its subject is gone. Carry its intent forward by adding `assert len(route.pois) > 12` to the >15-stop assertion in step 5's proving test | asserts the deleted clamp |
| `tests/test_tour_selection.py::test_hard_anchor_cap_stays_within_held_karp_timing_ceiling` (`:612-616`) | **rewrite** to `assert ORDERING_EXACT_MAX <= 16`, importing from `src.tour.ordering`. Docstring updated to name the dispatcher | same guarantee, new owner |
| `tests/test_tour_selection.py` (`:585-587`) — the anonymous long-duration assertion inside the test above `:590` | replace `assert len(route.pois) <= HARD_ANCHOR_CAP` (`:587`) with `assert len(route.pois) == len({p.id for p in route.pois})` | deleted symbol |
| `tests/test_tour_selection.py` (`:2299`, `:2368`) | remove `HARD_ANCHOR_CAP` from the local import and pass no `hard_anchor_cap=` to `_apply_fill_pass` | the parameter is deleted → `TypeError` |
| `tests/test_tour_selection.py:2458` | comment mentions `ANCHOR_CAP_DIVISOR`; correct it | stale doc |
| `tests/test_tour_ordering_heldkarp.py::test_cap_sized_input_under_a_second` (`:133-144`) | replace `HARD_ANCHOR_CAP` with `ORDERING_EXACT_MAX` at `:136`, `:144`, and the import at `:21` (now `from src.tour.ordering import ORDERING_EXACT_MAX`) | `from src.tour.selection import HARD_ANCHOR_CAP` (`:21`) is an `ImportError` |
| `tests/test_tour_certification_selection.py` (`:63`, `:76`, `:87`, `:92`, `:272`) | delete `max_stops=2` / `max_stops=8` kwargs (`:63`, `:76`), delete `assert budget.max_stops == 8` (`:87`), delete the `max_stops=9` rejection case (`:88-93`), delete `assert len(trial.ordered) <= policy.max_stops` (`:272`) | `certification()` no longer accepts the kwarg → `TypeError` at collection of the fixtures |
| `tests/test_tour_authoring_from_route.py` (`:338`, `:358`) | delete both `assert AUTHORING_MAX_STOPS == selection.HARD_ANCHOR_CAP == 15` lines and the `AUTHORING_MAX_STOPS` import at `:34` | `HARD_ANCHOR_CAP` gone. **Note:** step 4 deletes most of this file with the second authoring seam; if `:338`/`:358` are already gone, this row is a no-op — verify before editing |
| `tests/test_workbench_matches_the_app.py` docstring (file header) | the file docstring records the 8-vs-15 divergence as a known gap; rewrite it to record that both ceilings were removed on 2026-08-04 and duration is the only bound | the test that pinned it is being replaced; leaving the docstring makes the file self-contradictory |

**Step 5.5 test moves:** `tests/test_tour_candidate_authoring.py:182-202`
(`MAX_CANDIDATE_STOPS == 15`, `_wide_plan(MAX_CANDIDATE_STOPS)`, and
`_wide_plan(MAX_CANDIDATE_STOPS + 1)` expecting a rejection) is replaced wholesale by the
step-5.5 proving test in 2.8. `tests/test_tour_authoring_from_route.py::
test_prebuilt_route_refuses_more_than_the_anchor_cap` (`:415-418`) is deleted — if step 4
has not already deleted it with `author_prebuilt_route`.

---

## 4. Q2 — VERDICT. The original premise is REFUTED; here is the real gap.

### 4.1 The judge is right about C7. Traced, not asserted.

The C7 ceiling is `route.err_short_total_seconds` (`quality_rubric.py:438`, `:441`, `:449`,
`:454`, `:461`). That field is not a constant: `summarise_route` stamps it at
`routing.py:451`:

```python
        err_short_total_seconds=budget.nominal_elapsed_seconds,
```

and `budget` comes from `route_planning_budget(duration_min, planning_policy)`
(`routing.py:443`), whose `nominal_elapsed_seconds` is
`round(requested_seconds * policy.nominal_requested_fraction)` (`routing.py:141`), with
`nominal_requested_fraction = (min + max) / 2` (`routing.py:80-84`).

Arithmetic at 60 minutes:

- Legacy (0.83 / 0.83): nominal = 0.83, ceiling = `round(3600 × 0.83)` = **2988 s**.
- Certification (0.90 / 1.10): nominal = 1.00, ceiling = `round(3600 × 1.00)` = **3600 s**.

The ceiling **rises by 612 s (20.5%)**. C7 fires only when
`actual_total_s > route.err_short_total_seconds` (`quality_rubric.py:454`). A route that
passed C7 at 2988 s cannot fail it at 3600 s. **Nothing breaches. Q2's "unified tours
breach their own ceiling check" is false**, and the comment at `quality_rubric.py:441-448`
was written for exactly this reason — `:443` says the message "used to interpolate
ERR_SHORT (83%) as a literal", past tense, and `tests/test_tour_quality_rubric.py:1625-1636`
guards the corrected behaviour with a fixture commented `# a 60-min request planned at
1.00`. **Retire Q2 in its original form.**

### 4.2 The real gap: `ERR_SHORT` has six readers, and one of them is the tourability gate

`grep -rnw ERR_SHORT src/` returns exactly nine lines: the definition (`routing.py:43`),
the two legacy-policy fractions (`routing.py:126-127`, deleted by step 6), three helper
bodies (`routing.py:225`, `:229`, `:248`), two density bodies (`density.py:303`, `:400`),
and one stale comment (`quality_rubric.py:147`). Plus the import at `density.py:38` and two
further stale comments at `quality_rubric.py:393`, `:443`.

**The tourability path, traced.** `select_route` calls `assess_tourability(input, snapshot)`
at `selection.py:1421` — **with no policy argument**, because `density.assess_snapshot`
(`density.py:277`) and `density.assess` (`density.py:163`) do not take one. Inside `assess`:

- `density.py:178`: `walk_radius_m = envelope_radius_m(duration_min, round_trip=round_trip)`
  — no policy, so it takes the default at `routing.py:208`.
- `density.py:211`: `target_audio_s = _target_audio_seconds(duration_min)`, whose body
  (`density.py:303`) is `round(duration_min * ERR_SHORT * AUDIO_FRACTION * 60)` — a bare
  constant that no policy can reach.
- `density.py:212`: `fill_ratio = audio_capacity_s / target_audio_s`, which drives `_status`
  (`density.py:332-388`) and therefore GREEN / YELLOW / **RED refusal**.
- `density.py:391-401`: `_duration_where_fill_equals_one` uses `ERR_SHORT` again
  (`:400`) for the "max supportable duration" the refusal recommends.
- `density.py:418-419`: two more no-policy `envelope_radius_m` calls in the one-way
  suggestion.

**Numbers at 60 minutes, one-way.**

| quantity | today (legacy default) | after step 6 (certification default) |
|---|---|---|
| planner walk envelope, `routing.py:217-221` | `60 × 0.83 × 0.40 = 19.92` min → **737.8 m** | `60 × 1.00 × 0.40 = 24.0` min → **888.9 m** |
| planner audio budget, `routing.py:151-153` | `round(3600 × 0.83 × 0.60)` = **1793 s** | `round(3600 × 1.00 × 0.60)` = **2160 s** |
| density `walk_radius_m`, `density.py:178` | 737.8 m | **888.9 m** (follows the changed default) |
| density `target_audio_s`, `density.py:303` | 1793 s | **1793 s — unchanged, still 0.83** |

**So after step 6, density's radius follows the new policy but density's audio target does
not.** Two errors of *opposite sign*:

- The radius grows 20.5%, so `audio_capacity_s` (summed over a disc of area ∝ r²) grows by
  up to 1.45× on a radially uniform pool — pushing `fill_ratio` **up**.
- The target stays at 1793 while the planner now aims at 2160 — also pushing `fill_ratio`
  **up** relative to what the planner actually needs, by a factor of 2160/1793 = **1.205**.

Both errors overstate feasibility. Net on a uniform pool: `fill_ratio` reads ~1.75× the
honest value, so the gate says GREEN on a pool holding barely half the audio the planner
will try to fill. That is not a crash — it is a **thin tour served as healthy**, which is
precisely the failure `density.py:1-27` exists to prevent.

The same 1793 leaks into `selection.py:2129-2137`, the C11a "delivered thin" banner, which
compares delivered audio against `GREEN_THIN_DELIVERY_FRAC × assessment.target_audio_seconds`
— the legacy number. The banner therefore under-fires by 20% on every unified tour.

**Answer to "does density.py have to join step 6's file scope": YES, and it is not optional
even for compilation.** `envelope_radius_m`'s default parameter (`routing.py:208`) names
`LEGACY_ROUTE_PLANNING_POLICY`, which step 6 deletes. `density.py:178`, `:418`, `:419` call
it with no policy. If `density.py` is not in scope, either the module fails to import (the
default references a deleted name) or it silently switches policy — and
`tests/test_tour_density.py:88-89` and `:201-202` pin those exact radii, so the step goes
RED without an edit to a file it does not own.

### 4.3 STEP 6 CONTRACT for the six `ERR_SHORT` call sites

**`src/tour/routing.py:224-248`.** Three helpers gain a policy parameter defaulting to
certification. Add, immediately after `RoutePlanningBudget` (`routing.py:122`):

```python
DEFAULT_ROUTE_PLANNING_POLICY = RoutePlanningPolicy(
    policy_id="certification-nominal-v1",
    minimum_requested_fraction=MIN_REQUESTED_FRACTION,
    maximum_requested_fraction=MAX_REQUESTED_FRACTION,
)
```

This is the single object that replaces `LEGACY_ROUTE_PLANNING_POLICY` at all four of its
default sites (`routing.py:133`, `:208`, `:253`, `:409`) and at `selection.py:1378`,
`:2153`. Nominal fraction = (0.90 + 1.10)/2 = **1.00**, exactly owner parameter 2.

Current, `routing.py:224-229` and `:247-248`:

```python
def err_short_total_seconds(duration_min: int) -> int:
    return round(duration_min * ERR_SHORT * 60)


def target_audio_seconds(duration_min: int) -> int:
    return round(duration_min * ERR_SHORT * AUDIO_FRACTION * 60)
...
def walk_budget_seconds(duration_min: int) -> int:
    return round(duration_min * ERR_SHORT * WALK_FRACTION * 60)
```

Replacement — all three delegate to the budget, so a policy can never be bypassed again:

```python
def planned_total_seconds(
    duration_min: int,
    policy: RoutePlanningPolicy = DEFAULT_ROUTE_PLANNING_POLICY,
) -> int:
    """Total active seconds the planner aims at. Was ``err_short_total_seconds``;
    renamed because it is no longer err-SHORT — the nominal fraction is 1.00."""
    return route_planning_budget(duration_min, policy).nominal_elapsed_seconds


def target_audio_seconds(
    duration_min: int,
    policy: RoutePlanningPolicy = DEFAULT_ROUTE_PLANNING_POLICY,
) -> int:
    return route_planning_budget(duration_min, policy).audio_target_seconds


def walk_budget_seconds(
    duration_min: int,
    policy: RoutePlanningPolicy = DEFAULT_ROUTE_PLANNING_POLICY,
) -> int:
    return route_planning_budget(duration_min, policy).walk_budget_seconds
```

`governor_allowance_seconds` (`routing.py:232-244`) gains the same parameter and forwards
it at `:244`. **It has zero callers in `src/`** — `grep -rnw governor_allowance_seconds src/`
returns only its own definition; the live governor recomputes the same expression inline at
`selection.py:1745` from the policy-derived `audio_budget`. Its only readers are
`tests/test_tour_routing.py:304-320`, whose pinned values (`298` at d=30, `896` at d=90)
**will change** to the 1.00-nominal figures (`360` and `1080`) and must be updated in
step 6.

`smallest_duration_min_for_walk_seconds` (`routing.py:251-270`) has a **live inconsistency
that step 6 must fix**: its fast path at `:265` calls the bare `walk_budget_seconds(1)`
while its loop at `:268` uses `route_planning_budget(d, planning_policy)`. Replace `:265`
with

```python
    if target_seconds <= route_planning_budget(1, planning_policy).walk_budget_seconds:
```

and change its default at `:253` to `DEFAULT_ROUTE_PLANNING_POLICY`.

**Then delete `ERR_SHORT` itself (`routing.py:43`)** and correct the three comments that
name it: `routing.py:60` ("The default policy preserves the legacy 0.83 planner exactly"),
`routing.py:212` ("walk_min = duration x 0.83 x 0.40"), and `quality_rubric.py:147`.
`quality_rubric.py:393` and `:443` are historical notes about the C7 correction and may
keep the name in prose provided they read as history; rewrite `:393` to name
`Route.err_short_total_seconds` as a policy-stamped field rather than a 0.83 derivation.

**`src/tour/density.py`.** `assess`, `assess_snapshot`, `_target_audio_seconds` and
`_duration_where_fill_equals_one` gain the policy. Exact signatures:

```python
def assess(
    tour_input: TourInput,
    pois: Iterable[POI],
    beats_by_poi: dict[str, tuple[BeatRef, ...]],
    *,
    planning_policy: RoutePlanningPolicy = DEFAULT_ROUTE_PLANNING_POLICY,
) -> TourabilityAssessment:


def assess_snapshot(
    tour_input: TourInput,
    snapshot: CorpusSnapshot,
    *,
    planning_policy: RoutePlanningPolicy = DEFAULT_ROUTE_PLANNING_POLICY,
) -> TourabilityAssessment:


def _target_audio_seconds(
    duration_min: int, planning_policy: RoutePlanningPolicy
) -> int:
    """The planner's own audio target — the SAME number selection fills."""
    return route_planning_budget(duration_min, planning_policy).audio_target_seconds


def _duration_where_fill_equals_one(
    audio_capacity_s: int, planning_policy: RoutePlanningPolicy
) -> int:
```

Body edits: `density.py:178` becomes
`envelope_radius_m(duration_min, round_trip=round_trip, planning_policy=planning_policy)`;
`:211` becomes `_target_audio_seconds(duration_min, planning_policy)`; `:245` becomes
`_duration_where_fill_equals_one(audio_capacity_s, planning_policy)`; `:251-257` passes
`planning_policy=planning_policy` into `_suggest_one_way_destination`, which gains the same
keyword-only parameter and forwards it to both `envelope_radius_m` calls at `:418-419`;
`:400` becomes
`seconds_per_minute = route_planning_budget(1, planning_policy).audio_target_seconds`.
Import block `density.py:36-42`: drop `ERR_SHORT`, add `RoutePlanningPolicy`,
`DEFAULT_ROUTE_PLANNING_POLICY`, `route_planning_budget`. `AUDIO_FRACTION` becomes unused —
drop it too (F401).

**Caller rewrite, `src/tour/selection.py:1421`.** Current:

```python
    assessment = assess_tourability(input, snapshot)
```

Replacement:

```python
    assessment = assess_tourability(input, snapshot, planning_policy=planning_policy)
```

This is the single line that makes the tourability gate and the planner speak the same
currency. `scripts/tour_build.py:31` imports `assess_snapshot`; because the parameter is
keyword-only with a certification default, that call site needs no edit — verify by reading
its call and confirming it passes positionally only `(tour_input, snapshot)`.

**`scripts/score_saved_tours.py:52`, `:89`.** It reconstructs the C7 ceiling with
`err_short_total_seconds(script.inputs.duration_min)`. After the rename that import breaks;
change both to `planned_total_seconds`. **This is a real behaviour change and must be
stated in the diff:** every saved tour scored by `make score-saved-tours` is now judged
against a 1.00 ceiling instead of 0.83, i.e. **C7 becomes 20.5% more permissive on the
whole historical corpus**. The script's own docstring at `:28-30` claims the reconstruction
"cannot drift from the engine's" — that claim only stays true if the rename is applied; if
it is not, the script keeps a 0.83 ceiling while the engine plans at 1.00 and the docstring
becomes false. Correct the docstring to name the policy.

### 4.4 The exact replacement for AC-14, and the command that verifies it

AC-14 as written ("`LEGACY_ROUTE_PLANNING_POLICY` and the 0.83 flat policy return zero
hits") is satisfiable *only if* `ERR_SHORT` is deleted, which the ledger never says. With
the contract above it becomes satisfiable, but "0.83 returns zero hits" is still a bad
check — a future unrelated 0.83 in a comment would fail it, and it says nothing about
defaults.

**Replacement wording:**

> **AC-14** (negative): Given the whole `src/` tree, when it is searched, then
> `LEGACY_ROUTE_PLANNING_POLICY`, `ERR_SHORT`, the policy id `legacy-err-short-v1` and the
> property `RoutePlanningPolicy.is_legacy` each return zero hits; and every function
> parameter annotated `RoutePlanningPolicy` either has no default or defaults to
> `DEFAULT_ROUTE_PLANNING_POLICY`, whose nominal fraction is exactly 1.00. No code path
> can obtain a walk, audio, or elapsed budget derived from any fraction other than the
> certification band 0.90–1.10.

**The exact verifying command** (read-only, no container, seconds):

```bash
make test-file FILE="tests/test_tour_one_engine.py::test_no_code_path_can_obtain_a_legacy_planning_budget"
```

and, as the human-readable cross-check that the test encodes:

```bash
grep -rnwE 'ERR_SHORT|LEGACY_ROUTE_PLANNING_POLICY|is_legacy' src/ ; \
grep -rn 'legacy-err-short-v1' src/
```

Both must print nothing and exit 1. The test itself must not be a grep: it must
`ast.parse` every file under `src/`, collect every `ast.arg` whose annotation is
`RoutePlanningPolicy` or `RoutePlanningPolicy | None`, and assert each default is either
absent, `None`, or the `Name` `DEFAULT_ROUTE_PLANNING_POLICY`; then assert
`route_planning_budget(60).nominal_elapsed_seconds == 3600` and
`route_planning_budget(60).audio_target_seconds == 2160`, which is the behavioural half a
grep cannot give.

---

## 5. STEP 6 — the branch collapse. FULL TABLE.

`planning_policy.is_legacy` (`routing.py:87-88`) gates seven branches. Every one, with the
surviving arm and the caller-visible consequence.

| # | file:line | Predicate | Which arm survives | Behaviour change for a caller that took the legacy arm | Exception type change |
|---|---|---|---|---|---|
| 1 | `selection.py:1410` | `certification_fixed_end = input.end is not None and not planning_policy.is_legacy` | becomes `certification_fixed_end = input.end is not None` | Every fixed-destination request now uses the certification reach model: REACH radius from `certification_total_ceiling` (`:1509-1513`) instead of `envelope_radius_m` (`:1515-1519`), and the greedy walk budget becomes the total elapsed ceiling (`:1713`) instead of `walk_budget × 0.75` (`:1717`). A→B tours get materially more reach. | none |
| 2 | `selection.py:1441` | `reachability_ceiling = budget if is_legacy else max_elapsed + tolerance` | certification arm: `planning_budget.maximum_elapsed_seconds + TIMEBOX_MATERIALITY_TOLERANCE_SECONDS` | At 60 min the A→B reachability ceiling rises from `walk_budget_seconds` = 1195 s (legacy) to `round(3600×1.10) + 60` = **4020 s**. Destinations previously refused as unreachable now plan. **This is a large widening — flag it to the acceptance agent.** | none — both arms raise `TourabilityRefusedError` |
| 3 | `selection.py:1449-1461` | `suggested_duration` via `smallest_duration_min_for_walk_seconds` vs the `maximum_elapsed_seconds` loop | the loop (`:1454-1461`) | The `extend` alternative's recommended duration shrinks, because the certification ceiling is ~3.4× the legacy walk budget. `smallest_duration_min_for_walk_seconds` loses its only `src/` caller (`selection.py:1450`) and its import at `selection.py:73` — **delete both, and delete the function at `routing.py:251-270`**; `tests/test_tour_feasibility.py:105-129,195` must move with it | none |
| 4 | `selection.py:1914` | `rescue_candidates = corridor_rescue_candidates if is_legacy or certification_fixed_end else []` | `corridor_rescue_candidates if input.end is not None else []` (identical, since #1 makes `certification_fixed_end == (input.end is not None)`) | **none for A→B.** For open/round-trip walks the legacy arm supplied corridor rescue candidates and the certification arm supplied `[]`; after the collapse open walks get `[]`. That is a genuine narrowing of the fill pass's rescue pool on open walks | none |
| 5 | `selection.py:1970` | `if not planning_policy.is_legacy:` gates `_apply_certification_timebox_repair` | repair always runs | Every open and round-trip walk now goes through the bounded add/exchange repair (`selection.py:2870-3014`), which previously ran only on the preview path. Cost: see 1.1 and BLOCKING AMBIGUITY B1 | **YES — this is the arm that introduces `CertificationPlanningInfeasibleError` (`selection.py:2995`) onto the phone's path.** See section 6 |
| 6 | `selection.py:2071` | `if not is_legacy or input.end is not None:` gates the final band check | the block always runs | Every route is band-checked after ordering, not only fixed-end ones | see #7 |
| 7 | `selection.py:2087-2106` | `if not is_legacy and not within_planning_timebox(...)` → `CertificationPlanningInfeasibleError`; `if is_legacy and final_elapsed > elapsed_ceiling` → `TourabilityRefusedError` | **certification arm only.** Delete `:2097-2106` in full | A fixed-destination route that overshoots after final routing previously raised `TourabilityRefusedError` with the message "Fixed-destination route exceeds the elapsed-time ceiling after final routing"; it now raises `CertificationPlanningInfeasibleError`. **And the new check is two-sided** — `within_planning_timebox` (`routing.py:158-168`) refuses a route that is too SHORT as well as too long. A 60-min request now refuses below `round(3600×0.90) − 60` = 3180 s of active time | **YES — `TourabilityRefusedError` → `CertificationPlanningInfeasibleError`** |

Also delete: `routing.py:87-88` (`is_legacy`), `routing.py:124-128`
(`LEGACY_ROUTE_PLANNING_POLICY`), the `policy_id == "legacy-err-short-v1"` guard at
`routing.py:101-102` (nothing can construct that id any more), and the `LEGACY_...` import
at `selection.py:60`. Change the defaults at `selection.py:1378` and `:2153` to
`DEFAULT_ROUTE_PLANNING_POLICY`.

Also delete the two remaining **no-policy** `route_planning_budget` calls in `selection.py`,
which are legacy leaks the brief never named:

- `selection.py:996-1000`: `route_planning_budget(duration_min).walk_budget_seconds`
  (the `_closer_b_alternative` fallback). Give `_closer_b_alternative` a
  `planning_policy: RoutePlanningPolicy` keyword-only parameter and pass
  `planning_policy` from the call site at `selection.py:1480-1490`.
- `selection.py:2609-2617`: `route_planning_budget(duration_min).walk_envelope_minutes`
  (the `_isochrone_walk_minutes` fallback). Same treatment; its live caller
  (`selection.py:1520-1524`) already passes `walk_minutes=`, so the fallback is reached only
  by tests — but it must not read a deleted default.

### 5.1 STEP 6 — the one proving test

**File:** `tests/test_tour_one_engine.py` (created by step 1; already in the ledger)
**Function:** `test_the_legacy_err_short_planner_is_gone`
**Node id:** `tests/test_tour_one_engine.py::test_the_legacy_err_short_planner_is_gone`

Stubs: none beyond `ast` and the pure `routing` module — it is hermetic and sub-second.
Assertions, in order:

1. `route_planning_budget(60).nominal_elapsed_seconds == 3600` (was 2988).
2. `route_planning_budget(60).audio_target_seconds == 2160` (was 1793).
3. `route_planning_budget(60).walk_budget_seconds == 1440` (was 1195).
4. `envelope_radius_m(60, round_trip=False) == pytest.approx(888.9, rel=1e-3)`
   (was 737.8).
5. `density._target_audio_seconds(60, DEFAULT_ROUTE_PLANNING_POLICY) ==
   route_planning_budget(60).audio_target_seconds` — **the Q2 equality: the gate and the
   planner speak the same number.**
6. AST over every file under `src/`: zero occurrences of the names `ERR_SHORT`,
   `LEGACY_ROUTE_PLANNING_POLICY`, `is_legacy`, and zero string constants equal to
   `"legacy-err-short-v1"`.
7. Every `RoutePlanningPolicy`-annotated parameter default in `src/` is absent, `None`, or
   `DEFAULT_ROUTE_PLANNING_POLICY` (the AC-14 check from 4.4).

**THE MUTATION:** change `routing.py`'s new `DEFAULT_ROUTE_PLANNING_POLICY` to

```python
DEFAULT_ROUTE_PLANNING_POLICY = RoutePlanningPolicy(
    policy_id="certification-nominal-v1",
    minimum_requested_fraction=0.83,
    maximum_requested_fraction=0.83,
)
```

Assertions 1–5 all go RED. Runtime: milliseconds.

### 5.2 STEP 6 — per-change revert table, and the 6.5 split

The manager asked the same under-gating question for step 6. **Step 6 stays ONE step for
the policy work**, because `route_planning_budget`'s and `envelope_radius_m`'s defaults are
shared by `routing`, `selection` and `density`: there is no ordering of those three files
that leaves the tree green in between (deleting the constant breaks the other two at
import; changing the default without re-pointing `density._target_audio_seconds` produces
the mismatch of 4.2, which `tests/test_tour_density.py:88-89` catches immediately). **A
step 6.5 carries the two changes that genuinely are independent and genuinely are
unbound by step 6's test.**

| # | Change | Exact one-line revert | RED? |
|---|---|---|---|
| 1 | `DEFAULT_ROUTE_PLANNING_POLICY` at 0.90/1.10 | set both fractions to 0.83 | **YES** — assertions 1–5 |
| 2 | `LEGACY_ROUTE_PLANNING_POLICY` deleted (`routing.py:124-128`) | re-add the constant | **YES** — assertion 6 |
| 3 | `is_legacy` deleted (`routing.py:87-88`) | re-add the property | **YES** — assertion 6 |
| 4 | `density._target_audio_seconds` re-pointed (`density.py:303`) | restore `round(duration_min * ERR_SHORT * AUDIO_FRACTION * 60)` | **YES** — assertion 5 (1793 ≠ 2160) and assertion 6 (`ERR_SHORT` reappears) |
| 5 | `envelope_radius_m` default (`routing.py:208`) | point it back at a 0.83 policy | **YES** — assertion 4 |
| 6 | `selection.py:1421` threads the policy into density | drop `planning_policy=planning_policy` | **NO** — the default is already certification, so the numbers match. **UNBOUND.** *Remedy: an eighth assertion that calls `select_route` with a deliberately non-default policy (0.50/0.50) over a stub snapshot and asserts `route.tourability.target_audio_seconds == round(duration_min*60*0.50*0.60)`.* With it, **YES**. Implement the remedy. |
| 7 | branch collapse rows 1,2,4,5,6,7 of section 5 | restore any single `is_legacy` reference | **YES for all six** — assertion 6 is a name search over `src/`, and every one of those branches names `is_legacy` |
| 8 | `smallest_duration_min_for_walk_seconds` deleted | re-add the function | **NO** — an unreferenced function. **UNBOUND.** *Remedy: add its name to assertion 6's forbidden-name set.* |
| 9 | `scripts/score_saved_tours.py` rename | restore `err_short_total_seconds` | **NO** — `scripts/` is outside the test's `src/` walk. **UNBOUND → this is step 6.5.** |
| 10 | `quality_rubric.py:147,393` comment corrections | restore the comments | **NO** — comments. **UNBOUND → step 6.5**, verified by diff review, not by a test |

**Step 6.5:** id `"6.5"`, `depends_on: ["6"]`, `files: ["scripts/score_saved_tours.py",
"src/tour/quality_rubric.py", "tests/test_tour_quality_rubric.py"]`, `criterion_ids:
["AC-14"]`, `gate_commands: ["make lint"]`, `test_command: make test-file
FILE="tests/test_tour_quality_rubric.py::test_the_saved_tour_scorer_reconstructs_the_current_planning_ceiling"`.
That test imports `scripts/score_saved_tours.py`'s `_route_from` helper (or its
reconstruction expression) and asserts the reconstructed
`Route.err_short_total_seconds` for a 60-minute artifact equals
`route_planning_budget(60).nominal_elapsed_seconds` = 3600. **Mutation:** restore the old
`err_short_total_seconds` call → 2988 ≠ 3600 → RED. Green between 6 and 6.5: yes — the
scorer is a `##`-documented make target (`make score-saved-tours`, `Makefile:255`) and is
not in `make test`.

### 5.3 STEP 6 — every other test that must move

| Node id | Change | Why it cannot wait |
|---|---|---|
| `tests/test_tour_selection.py::test_explicit_legacy_planning_policy_is_byte_identical_to_default` (`:638-653`) | **delete the test** | its whole subject is the deleted constant; `:640` imports it |
| `tests/test_tour_selection.py::test_fixed_end_final_exact_elapsed_guard_catches_post_order_drift` (`:1428-1447`) | change the expected exception from `TourabilityRefusedError` / `match="elapsed-time ceiling after final routing"` to `CertificationPlanningInfeasibleError` / `match="post-selection transforms moved the exact route outside the band"` | it pins the exact refusal arm row 7 deletes |
| `tests/test_tour_selection.py::test_tour_stays_within_walk_and_audio_budget` (`:1248-1311`) | `walk_budget_seconds(60)` becomes 1440 and `err_short_total_seconds` 3600; update `:1310-1311` | the helpers' values move |
| `tests/test_tour_routing.py` (`:84`, `:95`, `:100`, `:105`, `:109-121`, `:304-320`) | `assert ERR_SHORT == 0.83` deleted; `err_short_total_seconds(60) == 2988` → `planned_total_seconds(60) == 3600`; `walk_budget_seconds(60) == 1195` → `1440`; `target_audio_seconds(60) == 1793` → `2160`; envelope radii and the four `governor_allowance_seconds` pins updated | every pinned number moves; `ERR_SHORT` no longer imports (`:12`) |
| `tests/test_tour_density.py` (`:88-89`, `:98`, `:201-202`, `:432`, `:519`) | radii 737.8 → 888.9, `target_audio_seconds` 1793 → 2160 | density's numbers move |
| `tests/test_tour_feasibility.py` (`:29`, `:31-32`, `:105-129`, `:145`, `:175-176`, `:195`, `:208`, `:299`, `:517-593`) | `smallest_duration_min_for_walk_seconds` is deleted → delete `:105-129` and `:195`; every `walk_budget_seconds(d)` expectation moves to the 1.00 nominal | imports a deleted symbol |
| `tests/test_tour_b_materialization.py` (`:30`, `:135`, `:327`, `:340`, `:347`, `:422`) | budget and radius helpers move | pinned values |
| `tests/test_tour_flavours.py` (`:270`, `:288`) | `walk_budget_seconds(duration_min)` budget assertion moves to 1.00 nominal | pinned value |
| `tests/test_tour_certification_selection.py` (`:85`, `:127`, `:191`) | `budget.walk_budget_seconds == 2160` is already the certification number and stays; verify after the `max_stops` removal of step 5 | dependency on step 5 |
| `tests/test_tour_quality_rubric.py` (`:707-769`, `:1577`, `:1625-1636`) | docstrings that derive the C7 ceiling from `ERR_SHORT` must be rewritten to name the policy; the fixtures at `:2988` stay valid as *literals* on a hand-built `Route` and need no numeric change | stale docs that will read as current |
| `tests/test_tour_invariants_live.py:67` | comment names `smallest_duration_min_for_walk_seconds` | deleted symbol |

---

## 6. Q3 — the refusal the traveller sees. VERDICT AND CONTRACT.

### 6.1 What actually happens today, read from the source

**The arm that changes** is section 5's row 7: `selection.py:2097-2106` raises
`TourabilityRefusedError` with a message and — critically — **no `alternatives` and no
`gap_minutes`**, because `TourabilityRefusedError.__init__` (`density.py:134-145`) defaults
`gap_minutes=None` and `alternatives=()`. The surviving certification arm
(`selection.py:2090-2096`) raises `CertificationPlanningInfeasibleError`, which
(`selection.py:424-446`) has **no `alternatives` attribute at all**.

So the manager's framing is right in substance and slightly off in detail: the payload was
already empty on the arm being deleted. **The alternatives that actually matter are on a
different arm** — the Step-2.2a fixed-destination refusal at `selection.py:1493-1502`,
which carries `gap_minutes` plus `loop`/`extend`/`closer_b`. That arm survives the collapse
(both sides of its own `is_legacy` branches raise `TourabilityRefusedError`), so **the
"try a shorter or looped walk" alternatives are NOT lost**. What IS lost is a refusal
*type* the API knows how to handle.

**The two real defects:**

1. **`POST /trips/generate` returns 500, not 422.** `trips.py:319-328` wraps
   `select_k_routes` in `except TourabilityRefusedError` **only**. Section 5 row 5 makes
   `_apply_certification_timebox_repair` run on every request, and it raises
   `CertificationPlanningInfeasibleError` (`selection.py:2995`) — an exception with no
   handler on that route. FastAPI turns it into an unhandled 500. `trips.py:944-965` shows
   the preview endpoint already catching it; the generate endpoint never needed to.
2. **The phone never parsed the structured refusal in the first place.**
   `TripService.generateTrip` handles 422 at `mobile/lib/services/trip_service.dart:78-80`
   by calling `_extractDetail` (`:302-309`), whose body is
   `return data['detail'] as String? ?? body;`. `_refusal_detail` (`trips.py:207-221`)
   returns a **Map**, so the Dart cast `as String?` throws a `TypeError`, which the
   enclosing `catch (_)` at `:306` swallows, returning `body` — the raw JSON string — as
   the user-facing message. `_detailMap` (`:313-321`), the method that *would* parse it, is
   called only from the compose path (`:226-227`) and only for
   `reason == 'compose_verification_failed'`. A repository-wide search of `mobile/lib/` for
   `alternatives`, `gap_minutes`, `shorter` or `loop` returns **zero hits**.
3. **The surface that does render alternatives is the workbench**, at
   `frontend/review.html:3281`: `if (detail && typeof detail === 'object' &&
   Array.isArray(detail.alternatives)) renderTourRefusal(detail);`, and
   `renderTourRefusal` (`:3297-3325`) maps `loop`/`extend`/`closer_b` to plain English.
   Because the preview's `CertificationPlanningInfeasibleError` handler
   (`trips.py:958-965`) emits `"alternatives": []` — an array — the branch **fires** and the
   operator is shown `detail.reason`, which for that handler is the literal identifier
   `"premium_route_infeasible"` (`trips.py:961`), with no alternatives beneath it. That is
   the exact "identifier shown to a human" failure the run-context forbids in AC-21.

### 6.2 THE CONTRACT (lands in step 6, because step 6 deletes the legacy arm)

**(a) Give the certification refusal the same payload shape.** `selection.py:424-446`,
current signature:

```python
    def __init__(
        self,
        *,
        policy_id: str,
        minimum_elapsed_seconds: int,
        maximum_elapsed_seconds: int,
        best_elapsed_seconds: int | None,
        reason: str,
    ) -> None:
```

Replacement:

```python
    def __init__(
        self,
        *,
        policy_id: str,
        minimum_elapsed_seconds: int,
        maximum_elapsed_seconds: int,
        best_elapsed_seconds: int | None,
        reason: str,
        gap_minutes: int | None = None,
        alternatives: tuple[FeasibilityAlternative, ...] = (),
    ) -> None:
```

with `self.gap_minutes = gap_minutes` and `self.alternatives = alternatives` added to the
body (before the `super().__init__` at `:442`). `FeasibilityAlternative` is already imported
into `selection` at `:54`. The message string at `:442-446` is unchanged.

**(b) Construct the alternatives at both raise sites.** Add, immediately above
`class CertificationPlanningInfeasibleError` (`selection.py:424`), a module-level helper:

```python
def _band_alternatives(
    *,
    input: TourInput,
    planning_policy: RoutePlanningPolicy,
    best_elapsed_seconds: int | None,
) -> tuple[tuple[FeasibilityAlternative, ...], int | None]:
    """The loop/extend pair for a route that cannot reach its frozen band.

    Mirrors the Step-2.2a construction at selection.py:1462-1474 exactly, so both
    refusals reach the surface in the same shape. ``extend`` uses the same ceiling
    walk the fixed-end branch already uses at :1454-1461. Returns
    ``((), None)`` when there is nothing actionable to offer.
    """
    if best_elapsed_seconds is None:
        return (), None
    budget = route_planning_budget(input.duration_min, planning_policy)
    overshoot = best_elapsed_seconds - budget.maximum_elapsed_seconds
    gap_minutes = math.ceil(overshoot / 60) if overshoot > 0 else None
    suggested = 1
    while (
        route_planning_budget(suggested, planning_policy).maximum_elapsed_seconds
        + TIMEBOX_MATERIALITY_TOLERANCE_SECONDS
        < best_elapsed_seconds
    ):
        suggested += 1
    alternatives = (
        FeasibilityAlternative(
            kind="extend", duration_min=suggested, drop_end=False
        ),
    )
    if input.end is not None:
        alternatives = (
            FeasibilityAlternative(
                kind="loop", duration_min=input.duration_min, drop_end=True
            ),
            *alternatives,
        )
    return alternatives, gap_minutes
```

Both raise sites pass its output. `selection.py:2090-2096` becomes:

```python
            alternatives, gap_minutes = _band_alternatives(
                input=input,
                planning_policy=planning_policy,
                best_elapsed_seconds=final_elapsed,
            )
            raise CertificationPlanningInfeasibleError(
                policy_id=planning_policy.policy_id,
                minimum_elapsed_seconds=planning_budget.minimum_elapsed_seconds,
                maximum_elapsed_seconds=elapsed_ceiling,
                best_elapsed_seconds=final_elapsed,
                reason="post-selection transforms moved the exact route outside the band",
                alternatives=alternatives,
                gap_minutes=gap_minutes,
            )
```

`selection.py:2995-3001` takes the same treatment with `best_elapsed_seconds=best`.

**(c) Generalise the API refusal body.** `trips.py:196-221`, current signature:

```python
def _refusal_detail(exc: TourabilityRefusedError) -> dict:
```

Replacement:

```python
def _refusal_detail(
    exc: TourabilityRefusedError | CertificationPlanningInfeasibleError,
) -> dict:
```

The body is unchanged — it already reads only `str(exc)`, `exc.gap_minutes` and
`exc.alternatives`, all three of which the new constructor supplies. Add one line at the top
of the returned dict so a surface can distinguish the causes without parsing prose:

```python
        "cause": (
            "time_budget"
            if isinstance(exc, CertificationPlanningInfeasibleError)
            else "tourability"
        ),
```

The docstring at `:197-206` must be updated to say both refusals share the shape.

**(d) Catch it on the phone's route.** `trips.py:327-328`, current:

```python
    except TourabilityRefusedError as exc:
        raise HTTPException(422, _refusal_detail(exc)) from exc
```

Replacement:

```python
    except (TourabilityRefusedError, CertificationPlanningInfeasibleError) as exc:
        raise HTTPException(422, _refusal_detail(exc)) from exc
```

`CertificationPlanningInfeasibleError` is already imported at `trips.py:74`.

**(e) Stop the preview showing an identifier to a human.** `trips.py:953-965`, current:

```python
    except (
        CertificationPlanningInfeasibleError,
        PremiumRouteInfeasibleError,
        ValueError,
    ) as exc:
        raise HTTPException(
            422,
            {
                "reason": "premium_route_infeasible",
                "detail": str(exc),
                "alternatives": [],
            },
        ) from exc
```

Replacement:

```python
    except CertificationPlanningInfeasibleError as exc:
        raise HTTPException(422, _refusal_detail(exc)) from exc
    except (PremiumRouteInfeasibleError, ValueError) as exc:
        raise HTTPException(
            422,
            {
                "cause": "routing",
                "reason": (
                    "This walk could not be routed on the street network. "
                    "Try a different start, or try again in a moment."
                ),
                "gap_minutes": None,
                "alternatives": [],
            },
        ) from exc
```

`renderTourRefusal` (`frontend/review.html:3300-3325`) then receives plain English in
`detail.reason` on both arms and renders the loop/extend list on the band arm. **No
workbench edit is required for this** — the existing branch at `:3281` already handles it —
which keeps step 6 inside `src/` and `tests/` and off the `make test-workbench` gate.

**(f) Leave the Dart alone in Phase 1, but record it.** Fixing
`_extractDetail` so the phone renders the alternatives is a real user-facing improvement
and is **out of step 6's scope** (`mobile/` is in no step-6 file list, and the ledger's
Phase 1 is algorithm-only). What step 6 must NOT do is make it worse: with (d) in place the
phone gets a 422 with a JSON body instead of a 500 with a stack trace, which is strictly
better than today on the new failure mode and identical to today on the old one. Carry
forward, in one sentence, to whoever owns Phase 2: *`TripService._extractDetail`
(`mobile/lib/services/trip_service.dart:302-309`) cannot read a structured refusal — it
casts a Map to String, throws, and shows the raw JSON body; `_detailMap` at `:313` is the
method it should use.*

### 6.3 The Q3 assertions inside step 6's proving test

Add to `test_the_legacy_err_short_planner_is_gone`, or as a sibling node id in the same
file if it grows too long (`test_a_band_refusal_reaches_both_surfaces_with_alternatives`):

1. Construct `CertificationPlanningInfeasibleError(..., best_elapsed_seconds=4200,
   alternatives=_band_alternatives(...)[0])` and assert `_refusal_detail(exc)` returns
   `{"cause": "time_budget", "reason": <str>, "gap_minutes": <int>, "alternatives":
   [{"kind": "extend", ...}]}`.
2. Assert `_refusal_detail` accepts a `TourabilityRefusedError` unchanged — the existing
   shape is preserved byte-for-byte.
3. Assert the `except` tuple at `trips.py:327` names both types, by `ast.parse` of
   `src/api/routes/trips.py`.
4. Assert no `HTTPException` body constructed anywhere in `src/api/routes/trips.py` has a
   `"reason"` whose value is a string constant matching `^[a-z_]+$` — i.e. no identifier is
   ever shown to a human. **Mutation:** restore `"reason": "premium_route_infeasible"` →
   RED.

---

## 7. Count of symbols slated for deletion

**Step 5 (planner-side), 14 symbols/clauses:** `RoutePlanningPolicy.max_stops` field;
its `__post_init__` 1..8 clause; the `max_stops` parameter of
`RoutePlanningPolicy.certification`; `RoutePlanningBudget.max_stops`; the `max_stops=`
assignment in `route_planning_budget`; the `max_stops=8` literal in
`certification_planning_policy`; `selection.ANCHOR_CAP_DIVISOR`;
`selection.HARD_ANCHOR_CAP`; the `max_anchors` clamp block; the `hard_anchor_cap` parameter
of `_apply_fill_pass`; the `hard_anchor_cap` parameter of `_apply_endpoint_pull`; the two
anchor-cap `if` blocks inside `_apply_endpoint_pull`; the `max_stops` guard in
`_certification_route_trial`; the `max_stops` guard in
`_apply_certification_timebox_repair`. Plus 4 additions (`ORDERING_EXACT_MAX`,
`order_stops`, `cheapest_insertion_open`, `TIMEBOX_REPAIR_MAX_TRIALS`).

**Step 5.5 (authoring-side), 4:** `AUTHORING_MAX_STOPS`; its `__all__` entry; the
`1 <= len(stops) <= AUTHORING_MAX_STOPS` guard; `MAX_CANDIDATE_STOPS` (and the two
`max_length` bindings that read it).

**Step 6, 8 symbols plus 7 branches:** `ERR_SHORT`; `LEGACY_ROUTE_PLANNING_POLICY`;
`RoutePlanningPolicy.is_legacy`; the `"legacy-err-short-v1"` guard in `certification`;
`err_short_total_seconds` (renamed to `planned_total_seconds`);
`smallest_duration_min_for_walk_seconds`; `density.AUDIO_FRACTION` import;
`selection`'s `LEGACY_ROUTE_PLANNING_POLICY` import. Seven `is_legacy` branches per the
table in section 5. Plus 1 addition (`DEFAULT_ROUTE_PLANNING_POLICY`) and 1 helper
(`_band_alternatives`).

**Total slated for deletion across both steps and their splits: 26 named symbols or
clauses, plus 7 branch arms.**

---

## 8. BLOCKING AMBIGUITY

Two items. Neither can be settled from the code; both change tourist-visible output.

**B1 — `TIMEBOX_REPAIR_MAX_TRIALS = 4000` is my recommendation, not a derivation.**
The certification timebox repair prices `|selected| × |eligible pool|` trials
(`selection.py:2949-2983`), each one a full ordering plus a capped beat-plan pricing. Today
that product is bounded by the 8-stop cap; after step 5 it is bounded by nothing. I cannot
measure the real eligible-pool size without the graph, and I am forbidden from starting the
containers. **4000 is chosen so that it cannot bind on anything reachable today** (8
incumbents × a Paris pool that the corpus documentation puts near 300 POIs ≈ 2400 trials),
while bounding tomorrow. If the true pool is larger than 500, 4000 silently truncates the
repair on tours that pass today, which would move certified output.

*Recommendation:* accept 4000 for step 5 and require the acceptance agent to report, from a
real preview run, the observed `len(observed)` at close. If it exceeds 3000, raise the
constant to 3× the observed maximum before Phase 1 closes. *Alternative the owner may
prefer:* skip the repair entirely once the stop set exceeds `ORDERING_EXACT_MAX`, on the
grounds that a route with 17+ stops has already spent its budget and has nothing to gain
from an ADD pass. That is cheaper and simpler but means long tours lose band repair
entirely, so more of them will refuse.

**B2 — `quality_rubric.MAX_COMPOSED_STOPS` stays at 8, and that is a deliberate
under-correction.** It caps the C3 thinness floor at
`8 × 850 × 0.5 = 3400` words ≈ 22.7 min of audio (`quality_rubric.py:274-279`). With the
planning cap gone, a 25-stop tour can physically hold far more, so the cap now makes C3
**weaker than it should be** on long tours — a thin 300-minute tour will pass C3 that
should not. Raising it changes which tours BLOCK, which is a rubric calibration decision
with the same weight as the `MIN_AUDIO_FRAC_OF_REQUESTED` measurement recorded at
`quality_rubric.py:145-174`, and it is not a consequence of removing a planning cap.

*Recommendation:* leave the value at 8 in Phase 1, correct the comment as specified in 2.5
so it no longer claims a planning ceiling that does not exist, and raise a separate
rubric-calibration item. Do **not** let an implementer bump it silently because the number 8
appears in a deletion list.
