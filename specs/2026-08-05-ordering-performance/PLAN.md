# Ordering Performance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.
>
> **Before you touch anything, read "Anti-Drift Protocol" below and create the ledger.**
> Every task ends with a number written into the ledger. A task without its number is not done.

**Goal:** Cut tour-planning cost from 191 seconds to under 2 seconds for a 120-minute request,
without removing a stop, deleting a test, thinning a fixture, or reinstating the stop cap.

**Architecture:** Three levers, applied in order, all inside code that already exists. (1) Retire
the exponential exact visiting-order solver from the hot path in favour of cheapest insertion plus
an Or-opt local search, using the exact solver itself as the test oracle. (2) Make the timebox
repair pass estimate cheaply and price exactly only its finalists, instead of fully ordering all
108-495 trials. (3) Give the repair search a wall-clock deadline so it can never spin, whatever a
future corpus contains.

**Tech Stack:** Python 3.13, pytest, ruff, uv. No new dependencies — OR-Tools is forbidden by the
tour-builder design and nothing here needs it.

---

## No new modules, no parallel paths, no dead code

**This constraint is load-bearing and overrides convenience everywhere below.** The plan creates
exactly two new files, both of them documents (`LEDGER.md`, `RESULT.md`). Every line of code and
every test extends something that already exists.

Concretely, this plan **must not** end with:

- a second ordering module that new code calls while old code still calls the first;
- a new `tests/test_tour_repair_bounds.py` counting repair trials while
  `tests/test_workbench_matches_the_app.py` assertion 8 already counts them;
- a new `tests/test_tour_ordering_cost.py` asserting a CPU ceiling while
  `tests/test_tour_ordering_heldkarp.py::test_cap_sized_input_under_a_second` already asserts one;
- `TIMEBOX_REPAIR_MAX_TRIALS` still defined after Task 5 makes it unreachable;
- a `consider()` wrapper that survives as a one-line pass-through to `record()`;
- a file named `test_tour_ordering_heldkarp.py` that mostly tests something other than Held-Karp.

Every one of those is a specific, checked outcome of a task below. **Task 7 Step 4 is a dead-code
sweep that must find nothing** — if it finds something, the task that created it was not finished.

**Already verified as safe (2026-08-05):** nothing in `src/` calls `held_karp_open` or
`cheapest_insertion_open` directly. `order_stops` is already the single entry point, and Task 3
adds a test that keeps it that way. The exact solver stays because it is *live production code*
for small stop counts, where it is both cheaper than the threshold and provably optimal — not
because it is a leftover.

---

## Scope

**In scope:** the three levers above. Together they produce working, shippable software: identical
tour *content* decisions, dramatically cheaper planning, and a hard guarantee against hanging.

**Deliberately deferred to their own plans** — each is an independent subsystem, and folding them
in here would produce a plan that cannot be verified as a unit:

- **Two-tier options (plan cheaply, refine on selection).** Today `plan_premium_options`
  (`src/tour/premium_tour.py:589`) fully plans three routes before the traveller sees a card, then
  discards two. Making option cards cheap and refining only the chosen route changes the API
  response contract and the Flutter client — user-facing, Tier 2+, needs a Product Owner pass. It
  is worth roughly another 3x on top of everything here, so it should follow, not precede.
- **The narration over-credit.** The planner books each stop against the whole tour's talking
  allowance while playback caps each stop at `MAX_DWELL_AUDIO_SECONDS = 270`
  (`src/tour/selection.py:220`). Fixing that arithmetic changes the shape of every tour and will
  move the reference tours, which needs human acceptance of a diff. Tracked as ERROR 3 in
  `specs/2026-08-04-unify-tour-algorithm/HANDOVER.md`. **Do not touch it in this plan** — if you
  do, every measurement below becomes uninterpretable, because you will not know which change
  moved which number.

**Predecessor:** this plan closes ERROR 2 in
`specs/2026-08-04-unify-tour-algorithm/HANDOVER.md` ("the test suite is roughly ten times
slower"). Its acceptance bar — full Python shard under 30 minutes, zero tests deleted, skipped or
deselected, no fixture made thinner — is inherited verbatim by Task 7.

---

## Anti-Drift Protocol

This exists because the failure mode on work like this is not a wrong edit. It is an agent that
tries a variation, sees a number move the wrong way, tries another variation, and burns an hour
without ever saying it is stuck.

### The ledger

**Create `specs/2026-08-05-ordering-performance/LEDGER.md` as your very first action**, with this
exact content:

```markdown
# Ordering Performance — Execution Ledger

Update this after EVERY state transition. Post the same three lines to the user.

| Task | State | Attempts | Measured number | Note |
| --- | --- | --- | --- | --- |
| 0 Cost ceilings, red on purpose | PENDING | 0 | — | |
| 1 Or-opt local search | PENDING | 0 | — | |
| 2 Calibrate the quality bar | PENDING | 0 | — | |
| 3 Wire into the fallback path | PENDING | 0 | — | |
| 4 Lower the exact threshold | PENDING | 0 | — | |
| 5 Filter-then-refine the repair | PENDING | 0 | — | |
| 6 Wall-clock deadline | PENDING | 0 | — | |
| 7 Close-out and dead-code sweep | PENDING | 0 | — | |
```

### The state machine

Every task walks exactly this path. No task may skip a state.

```
PENDING ──► RED ──► GREEN ──► PROVEN ──► RIPPLED ──► DONE
                │       │        │          │
                └───────┴────────┴──────────┴──► BLOCKED (stop; hand back)
```

| State | Means | You may leave it only when |
| --- | --- | --- |
| `PENDING` | Not started | — |
| `RED` | The new test exists and FAILS for the stated reason | The failure message matches what the task says to expect |
| `GREEN` | The implementation makes that test pass | The named command exits 0 |
| `PROVEN` | The undo test passed: revert the implementation, the test goes RED again, restore it, GREEN again | You have pasted both outputs |
| `RIPPLED` | Every ripple check in the task passed, or its deviation is recorded with a number | All ripple commands run, none silently skipped |
| `DONE` | Lint clean, judge consulted, committed | `make lint` is zero errors and the judge ruled PROCEED |
| `BLOCKED` | Stop. Do not continue to the next task. | Never — hand back to the human |

### Hard rules

1. **Exactly one task may be in flight.** Everything else is `PENDING`, `DONE`, or `BLOCKED`.
2. **Two attempts, then stop.** If a transition fails twice, set the task `BLOCKED`, write what
   you tried and what the numbers were, and hand back. Do not try a third variation. Do not move
   to another task "while thinking about it".
3. **Never move a threshold to make a test pass.** Every numeric constant here is either fixed by
   the plan or set by an explicit stated rule from a measurement. If a test fails and your
   instinct is to relax the assertion, that is the `BLOCKED` signal. (Task 2 Step 2 is the one
   sanctioned exception, and only for the one constant it names.)
4. **Never touch the reference tours.** If a golden test fails, set `BLOCKED` and report the
   before/after overlap numbers. Baselines are updated by a human, never by the executor.
5. **Never delete, skip, or deselect a test to reach green.** The predecessor's acceptance bar
   forbids it explicitly. Retargeting a test at the behaviour that replaced the one it pinned is
   allowed, and each such retarget is named as a step below — inventing one that is not named is
   not.
6. **Every command goes through a Makefile target.** No raw `uv run pytest` or `pytest`.
   `make test-file FILE=` takes a pytest node id, never `-k` — the Makefile has no
   `PYTEST_ARGS` passthrough, so `-k` is eaten as `--keep-going`.
7. **No scratch scripts.** Every measurement is a committed test. A previous session on this exact
   question left a throwaway benchmark behind; do not repeat that.
8. **Consult the judge before every commit** and paste the ruling.
9. **Stage files by name, never by directory.** The working tree this plan starts from carries a
   large unrelated changeset — 50-plus modified files from the 2026-08-04 tour-algorithm
   unification, including 32 under `tests/`. A `git add tests/` or `git add -A` would sweep all of
   it into your commit. Every staging command below names its files explicitly; keep it that way,
   and run `git diff --staged --stat` before each commit to confirm only your files are there.

### The progress post

After every state transition, post exactly three lines:

```
Task N — <state>. <the number you measured, with units>.
Next: <the single next state transition>.
Risk: <one sentence, or "none">.
```

### Running alongside other work

Every command uses `TEST_PROFILE=test2` so this work does not collide with a sibling session on
the shared 7688 graph. If `make preflight-list` does not offer `db-test2`, drop the override and
assume exclusive use of the local containers.

---

## File Structure

Five files change. None is created.

| File | Responsibility | Change |
| --- | --- | --- |
| `src/tour/ordering.py` | Deciding visiting order. Owns the exact solver, the heuristic, and the one dispatcher every caller uses. | Modify — add the local search, retune the threshold |
| `src/tour/selection.py` | Choosing which stops to seat, and repairing a route outside its time band. | Modify — filter-then-refine, deadline, delete the dead trial ceiling |
| `tests/test_tour_ordering_heldkarp.py` → `tests/test_tour_ordering.py` | Every ordering test: correctness, quality against the oracle, and cost. | Rename + modify |
| `tests/test_tour_selection.py` | The selection suite. Already owns the fixtures both new selection tests need. | Modify — add the deadline test |
| `tests/test_workbench_matches_the_app.py` | Proves the workbench and the phone plan identically. Assertions 5, 6 and 8 pin ordering dispatch and repair bounds. | Modify — retarget three assertions at the behaviour that replaces what they pin |

`ordering.py` is 202 lines and single-responsibility; it stays one file. `selection.py` is over
3,000 lines and does too much, but splitting it is not this plan's job — a performance fix does
not need surrounding cleanup.

---

### Task 0: Cost ceilings, red on purpose

**Files:**
- Rename: `tests/test_tour_ordering_heldkarp.py` → `tests/test_tour_ordering.py`
- Modify: `tests/test_tour_ordering.py` (header, plus replace one test with three)
- Modify: `src/tour/ordering.py:22` (the docstring reference to the old filename)

Every later task is judged against numbers that already exist. Without them, "did that help?"
becomes a judgment call, and judgment calls are where drift starts.

- [ ] **Step 1: Rename the file and fix every reference to it**

The file is about to stop being Held-Karp-specific. A name that contradicts its contents is the
same trap as a stale document.

```bash
git mv tests/test_tour_ordering_heldkarp.py tests/test_tour_ordering.py
```

```bash
grep -rn "test_tour_ordering_heldkarp" src tests scripts specs Makefile
```

Expected: one hit, `src/tour/ordering.py:22`. Change that line to read
`#: (past the sub-second guarantee tests/test_tour_ordering.py pins),`. If the grep returns any
other hit, fix that too — a dangling reference is exactly the stale pointer this plan forbids.

- [ ] **Step 2: Replace the file header**

Replace lines 1-8 of `tests/test_tour_ordering.py` with:

```python
"""ORDER — the visiting-order step, end to end. Hermetic: no DB, no engine run.

Covers all three pieces and the one dispatcher that chooses between them:
``held_karp_open`` (exact, provably optimal, exponential), ``cheapest_insertion_open``
(cheap, mediocre), ``improve_order_or_opt`` (cheap, close to optimal), and
``order_stops``, which every caller uses and which nothing outside this module
may bypass.

PROVE: on the seesaw fixture the exact solver beats greedy nearest-neighbour with
zero direction reversals and honors fixed_end; for every n in 4..8 its cost equals
the itertools.permutations brute-force optimum (open, round-trip, and asymmetric
variants); the cheap path lands within a MEASURED small ratio of that same proven
optimum; and one ordering call stays inside a per-call CPU budget at every n the
corpus can produce.

COST CEILINGS. Measured 2026-08-05, BEFORE any change, so a regression shows up as
a number rather than as a feeling:

    exact solver, n=10    3.6 ms      n=13   46.6 ms
    exact solver, n=16  556.2 ms      n=17    1.27 s

One 120-minute planning request made 495 ordering calls at n up to 17 and spent
191 seconds — 100% of the run — inside this step. That 500x multiplier is why the
budget below is a per-CALL figure and not a user-visible latency figure.
"""
```

- [ ] **Step 3: Replace `test_cap_sized_input_under_a_second` with the real ceilings**

Delete `test_cap_sized_input_under_a_second` entirely (lines 132-146) — the three tests below
subsume it, and leaving both would be two tests asserting one thing with different numbers. In
its place put:

```python
#: CPU seconds ``order_stops`` may spend on ONE call. The repair pass makes
#: hundreds per request, so this carries a ~500x multiplier behind it.
ORDER_CALL_CPU_CEILING_S: float = 0.05


def _cpu_seconds(fn, *args, **kwargs) -> float:
    """CPU time, never wall clock: a contended host must not make these flaky.

    These guard against an ALGORITHMIC regression — an exponent creeping back
    into the hot path — not against the machine's current load.
    """
    t0 = time.process_time()
    fn(*args, **kwargs)
    return time.process_time() - t0


@pytest.mark.parametrize("n", [12, 16, 20, 25, 30, 40])
def test_one_ordering_call_stays_under_the_per_call_budget(n: int):
    """n must stop driving cost exponentially. n=25 is the case this plan exists
    to make possible at all: under the exact solver alone it is roughly 12
    minutes and 33 GB, which is an unkillable test rather than a slow one.
    """
    pts = _random_points(n, seed=200 + n)
    elapsed = _cpu_seconds(order_stops, pts, fixed_start=START)
    assert elapsed < ORDER_CALL_CPU_CEILING_S, (
        f"n={n} took {elapsed * 1000:.1f} ms CPU, budget "
        f"{ORDER_CALL_CPU_CEILING_S * 1000:.0f} ms"
    )


def test_a_realistic_request_worth_of_ordering_calls_fits_in_two_seconds():
    """A per-call budget alone can still be multiplied into minutes by the repair
    pass, so pin the aggregate too.

    ONE 120-minute request made 495 ordering calls on 2026-08-05 at n up to 17.
    n=16 is the size that decides the bill: 17 is already above the dispatch
    threshold and takes the cheap path, so measuring there measures nothing.

    Ten calls scaled to 495, rather than 495 calls: while this is RED the honest
    figure is about 275 seconds, and a test that takes four minutes to fail is a
    test people quietly stop running.
    """
    pts = _random_points(16, seed=316)
    t0 = time.process_time()
    for _ in range(10):
        order_stops(pts, fixed_start=START)
    per_call = (time.process_time() - t0) / 10
    projected = per_call * 495
    assert projected < 2.0, (
        f"495 calls project to {projected:.1f} s CPU at n=16 "
        f"({per_call * 1000:.1f} ms each)"
    )


def test_the_exact_threshold_is_small_enough_to_be_called_in_a_loop():
    """``ORDERING_EXACT_MAX`` is the only remaining exponential surface, and it
    is inside a loop that runs hundreds of times. Pin it so raising it back
    requires editing this assertion deliberately.
    """
    assert ORDERING_EXACT_MAX <= 16
    pts = _random_points(ORDERING_EXACT_MAX, seed=99)
    elapsed = _cpu_seconds(order_stops, pts, fixed_start=START)
    assert elapsed < ORDER_CALL_CPU_CEILING_S, (
        f"the exact solver at its own threshold n={ORDERING_EXACT_MAX} took "
        f"{elapsed * 1000:.1f} ms CPU"
    )
    assert len(order_stops(pts, fixed_start=START)) == ORDERING_EXACT_MAX
```

Extend the import at line 19 so `order_stops` is available:

```python
from src.tour.ordering import ORDERING_EXACT_MAX, held_karp_open, order_stops
```

- [ ] **Step 4: Run it and record which assertions fail**

```bash
make test-file FILE="tests/test_tour_ordering.py" TEST_PROFILE=test2
```

Expected: **FAIL** on `test_one_ordering_call_stays_under_the_per_call_budget` for n=16 and up,
on the 495-call aggregate, and on the threshold test. The `n=25` case may take minutes — that is
the finding, not a hang. If it has not returned in 15 minutes, interrupt and record "n=25 did not
return", which is the same evidence.

Every pre-existing test in the file must still PASS. If one does not, the rename or the header
edit broke something.

**This task is RED-only and stays RED.** Do not implement anything. Its job is the scoreboard.

- [ ] **Step 5: Record the numbers, lint, judge, commit**

Put the measured milliseconds per `n` in the ledger.

```bash
make lint
```

Expected: zero errors. Judge, paste the ruling, then:

```bash
git add tests/test_tour_ordering.py src/tour/ordering.py specs/2026-08-05-ordering-performance/
git commit -m "test(ordering): one home for every ordering test, with cost ceilings red on purpose"
```

**Contract:** a rename, a header, and one test replaced by three. **Ripple:** the rename. Step 1's
grep is the ripple check, and it must come back clean.
**State after this task: DONE**, noted in the ledger as "RED BY DESIGN".

---

### Task 1: The Or-opt local search

**Files:**
- Modify: `src/tour/ordering.py` (imports; new function between `cheapest_insertion_open` and
  `order_stops`)
- Modify: `tests/test_tour_ordering.py` (imports plus three tests)

**Why Or-opt and not the textbook 2-opt:** 2-opt improves a route by reversing a whole segment.
That is only cheap when going A to B costs the same as B to A. Here it does not — this module is
documented as directed throughout and routed walking legs are asymmetric — so a reversal would
have to re-price every leg inside the reversed run, which is exactly the saving that made it
attractive. Or-opt instead *relocates* a short run without reversing it, so only three legs change
and the direction of travel inside the run is untouched.

- [ ] **Step 1: Write the failing tests**

Extend the import in `tests/test_tour_ordering.py`:

```python
from src.tour.ordering import (
    ORDERING_EXACT_MAX,
    cheapest_insertion_open,
    held_karp_open,
    improve_order_or_opt,
    order_stops,
)
```

Append to the end of the file:

```python
#: Worst ratio of (insertion + Or-opt) walking cost to the PROVEN optimum,
#: MEASURED across the seeds below. Set once by the rule in
#: specs/2026-08-05-ordering-performance/PLAN.md Task 2. Raising it to make a
#: test pass is forbidden: a regression here means the improver got worse.
OR_OPT_MAX_EXCESS_RATIO: float = 1.05


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
def test_or_opt_lands_close_to_the_proven_optimum(seed: int):
    """The exact solver is the ORACLE here, not the shipped path.

    Held-Karp is provably optimal, so it can price exactly how much the cheap
    path gives away. This is the entire justification for retiring the exact
    solver from the hot path: if the gap is too small for a walker to notice,
    the exponent is not buying anything.
    """
    pts = _random_points(10, seed=seed)
    optimum = _path_cost(held_karp_open(pts, fixed_start=START))
    rough = cheapest_insertion_open(pts, fixed_start=START)
    improved = improve_order_or_opt(rough, fixed_start=START)

    assert sorted(p.id for p in improved) == sorted(p.id for p in pts)
    improved_cost = _path_cost(improved)
    assert improved_cost <= _path_cost(rough), "the improver made the walk LONGER"
    assert improved_cost <= optimum * OR_OPT_MAX_EXCESS_RATIO, (
        f"seed={seed}: {improved_cost:.0f}s vs optimum {optimum:.0f}s "
        f"= {improved_cost / optimum:.4f}x, ceiling {OR_OPT_MAX_EXCESS_RATIO}x"
    )


def test_or_opt_honors_fixed_end_and_asymmetric_costs():
    """``fixed_end`` is the endpoint-pull contract: B stays last. And the improver
    must not assume symmetry — a silent segment reversal would win on a symmetric
    metric and lose on this one.
    """
    end = SEESAW[2]
    improved = improve_order_or_opt(
        SEESAW, fixed_start=START, fixed_end=end, routed_cost_fn=_eastbound_penalty
    )
    assert improved[-1].id == "e2"
    assert sorted(p.id for p in improved) == sorted(p.id for p in SEESAW)
    assert _path_cost(improved, fn=_eastbound_penalty) <= _path_cost(
        SEESAW, fn=_eastbound_penalty
    )


def test_or_opt_is_deterministic_and_keeps_the_contract_errors():
    """Same stops, same answer, whatever order they arrived in. A route that
    changes between two identical requests is a support ticket.
    """
    pts = _random_points(9, seed=77)
    first = improve_order_or_opt(pts, fixed_start=START)
    second = improve_order_or_opt(list(reversed(pts)), fixed_start=START)
    assert [p.id for p in first] == [p.id for p in second]

    assert improve_order_or_opt([], fixed_start=START) == []
    single = [SEESAW[0]]
    assert improve_order_or_opt(single, fixed_start=START) == single
    with pytest.raises(ValueError, match="mutually exclusive"):
        improve_order_or_opt(
            SEESAW, fixed_start=START, fixed_end=SEESAW[0], round_trip=True
        )
    with pytest.raises(ValueError, match="not among the points"):
        improve_order_or_opt(SEESAW[:3], fixed_start=START, fixed_end=SEESAW[4])
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
make test-file FILE="tests/test_tour_ordering.py" TEST_PROFILE=test2
```

Expected: **collection error** — `ImportError: cannot import name 'improve_order_or_opt'`. That is
the correct RED. Anything else means the import edit is wrong.

- [ ] **Step 3: Write the implementation**

Replace lines 13-16 of `src/tour/ordering.py`:

```python
from __future__ import annotations

from itertools import pairwise

from .contract import POI
from .routing import LegSecondsFn, default_leg_seconds, insertion_cost_seconds
```

Insert after `cheapest_insertion_open` ends (line 162) and before `def order_stops`:

```python
#: Longest run of stops the improver picks up and moves elsewhere. Three is the
#: standard Or-opt window: it covers the stranded single stop, the stranded pair,
#: and the short spur, which is where insertion order actually goes wrong.
OR_OPT_MAX_SEGMENT: int = 3

#: Full sweeps before the improver gives up. It also stops the moment a sweep
#: finds nothing, so this binds only on pathological input — it is the
#: termination guarantee, not the expected work.
OR_OPT_MAX_PASSES: int = 8


def improve_order_or_opt(
    order: list[POI] | tuple[POI, ...],
    *,
    fixed_start: tuple[float, float],
    fixed_end: POI | None = None,
    round_trip: bool = False,
    routed_cost_fn: LegSecondsFn | None = None,
) -> list[POI]:
    """Shorten a visiting order by relocating short runs of stops.

    Or-opt, deliberately NOT 2-opt: it MOVES a run of 1..``OR_OPT_MAX_SEGMENT``
    stops elsewhere and never REVERSES one. Reversal is the classic cheap
    improvement move, but it is cheap only when leg costs are symmetric. They are
    not here — this module is directed throughout and routed walking legs are
    asymmetric — so a reversal would have to re-price every leg inside the
    reversed run, which is the saving that made it attractive.

    Every leg is priced ONCE into a matrix and the search then runs over index
    lists, so re-costing a candidate is n array lookups rather than n calls into
    the routing layer.

    Contract-identical to ``held_karp_open``: same argument names, the same two
    ValueErrors, ``fixed_end`` pinned last, and EVERY input stop present in the
    output. Deterministic: segments are scanned in index order and a destination
    is taken only when STRICTLY cheaper, so ties keep the incumbent and a
    permuted input yields the same answer.
    """
    if fixed_end is not None and round_trip:
        raise ValueError("fixed_end and round_trip are mutually exclusive")
    pts = list(order)
    if fixed_end is not None and all(p.id != fixed_end.id for p in pts):
        raise ValueError(f"fixed_end {fixed_end.id!r} is not among the points")

    movable = [p for p in pts if fixed_end is None or p.id != fixed_end.id]
    tail = [fixed_end] if fixed_end is not None else []
    if len(movable) < 2:
        return [*movable, *tail]

    cost = routed_cost_fn or default_leg_seconds
    start_lat, start_lng = fixed_start
    n = len(movable)
    from_start = [cost(start_lat, start_lng, p.lat, p.lng) for p in movable]
    leg = [
        [0 if i == j else cost(a.lat, a.lng, b.lat, b.lng) for j, b in enumerate(movable)]
        for i, a in enumerate(movable)
    ]
    # One terminal covers both shapes: a pinned B is walked to from the last
    # movable stop, and a round trip walks back to the origin. An open path has
    # no closing leg at all, so its terminal costs are zero.
    if fixed_end is not None:
        terminal: tuple[float, float] | None = (fixed_end.lat, fixed_end.lng)
    elif round_trip:
        terminal = fixed_start
    else:
        terminal = None
    to_terminal = (
        [cost(p.lat, p.lng, terminal[0], terminal[1]) for p in movable]
        if terminal is not None
        else [0] * n
    )

    def path_cost(seq: list[int]) -> float:
        total = float(from_start[seq[0]])
        for a, b in pairwise(seq):
            total += leg[a][b]
        return total + to_terminal[seq[-1]]

    seq = list(range(n))
    best = path_cost(seq)
    for _ in range(OR_OPT_MAX_PASSES):
        improved = False
        for seg_len in range(1, min(OR_OPT_MAX_SEGMENT, n - 1) + 1):
            i = 0
            while i + seg_len <= len(seq):
                segment = seq[i : i + seg_len]
                rest = [*seq[:i], *seq[i + seg_len :]]
                best_j: int | None = None
                for j in range(len(rest) + 1):
                    if j == i:
                        continue  # putting it straight back is not a move
                    candidate = path_cost([*rest[:j], *segment, *rest[j:]])
                    if candidate < best - 1e-9:
                        best_j, best = j, candidate
                if best_j is not None:
                    seq = [*rest[:best_j], *segment, *rest[best_j:]]
                    improved = True
                i += 1
        if not improved:
            break
    return [*(movable[i] for i in seq), *tail]
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
make test-file FILE="tests/test_tour_ordering.py" TEST_PROFILE=test2
```

Expected: PASS, **except possibly** `test_or_opt_lands_close_to_the_proven_optimum` on some seeds.
**That is not a failure of this task** — it means the 1.05 starting value needs calibrating, which
is Task 2. Record the worst ratio the message printed and move on without changing anything.

If any *other* test fails, that is a real defect. Two attempts, then `BLOCKED`.

- [ ] **Step 5: Undo test (the PROVEN transition)**

Replace the body of `improve_order_or_opt` with `return list(order)`. Re-run Step 4.
`test_or_opt_lands_close_to_the_proven_optimum` and
`test_or_opt_honors_fixed_end_and_asymmetric_costs` must go RED. Restore, confirm GREEN, paste
both outputs into the ledger.

If the tests still pass with the improver neutered, they are fake and this task is `BLOCKED`.

- [ ] **Step 6: Lint, judge, commit**

```bash
make lint
```

```bash
git add src/tour/ordering.py tests/test_tour_ordering.py
git commit -m "feat(ordering): Or-opt local search, proven against the exact optimum"
```

**Contract:** one function added, called by nothing yet. **Ripple: none** — no existing caller
changes and no tour output moves. That isolation is deliberate: the risky new algorithm lands
here, the risky wiring lands in Task 3, and they can be judged separately.
**Ripple check:** re-run Task 0's cost tests; they must fail in exactly the same places as before,
with no new failures.

---

### Task 2: Calibrate the quality bar

**Files:**
- Modify: `tests/test_tour_ordering.py` (the `OR_OPT_MAX_EXCESS_RATIO` constant)
- Modify: `src/tour/ordering.py` (only if Step 3 escalation triggers)

This task exists so the acceptable gap is a *measured* number with a stated derivation rule,
rather than something an agent nudged upward until green. **Hard rule 3 does not apply to this one
constant, and only within this task.**

- [ ] **Step 1: Read the worst ratio out of Task 1 Step 4**

The assertion prints `= N.NNNNx` per failing seed. If every seed passed at 1.05, write "1.05 held,
no calibration needed" in the ledger and skip to Step 4.

- [ ] **Step 2: Apply the rule**

```
new_ratio = ceil(worst_observed * 100) / 100 + 0.02
```

Worked example: worst observed 1.0731 → ceil(107.31)/100 = 1.08 → **1.10**. The 0.02 is headroom
so an unrelated routing change does not turn this into a flaky test.

**HARD CEILING: if `new_ratio` would exceed 1.15, do NOT set it — go to Step 3.** 1.15 is the line
because cheapest insertion *alone* is typically 15-25% above optimal. A local search that cannot
beat 15% has not earned its place, and the honest response is a better move set, not a looser test.

- [ ] **Step 3: Escalation — only if Step 2 hit the ceiling**

Add a second move type to the *existing* function; do not add a second improver alongside it.
Insert into `src/tour/ordering.py` immediately after `improve_order_or_opt`:

```python
def _two_opt_pass(seq: list[int], *, path_cost, best: float) -> tuple[list[int], float, bool]:
    """One sweep of segment-reversal moves, each re-priced in full.

    The textbook 2-opt evaluates a reversal in O(1) by assuming a reversed run
    costs the same backwards as forwards. That assumption is false here, so this
    re-costs the whole candidate. O(n) per move rather than O(1), which is why it
    is the SECOND move type: it runs only when Or-opt alone cannot reach the bar.
    """
    improved = False
    for i in range(len(seq) - 1):
        for j in range(i + 2, len(seq) + 1):
            candidate = [*seq[:i], *reversed(seq[i:j]), *seq[j:]]
            cost = path_cost(candidate)
            if cost < best - 1e-9:
                seq, best, improved = candidate, cost, True
    return seq, best, improved
```

Then inside `improve_order_or_opt`, replace the trailing `if not improved: break` with:

```python
        if not improved:
            seq, best, improved = _two_opt_pass(seq, path_cost=path_cost, best=best)
        if not improved:
            break
```

Re-run Task 1 Step 4, then return to Step 2 with the new worst ratio. **If the ceiling is still
exceeded, the task is `BLOCKED`** — do not invent a third move type. Report and hand back.

- [ ] **Step 4: Set the constant and re-run**

Edit `OR_OPT_MAX_EXCESS_RATIO` to the Step 2 value, and add a line to its comment recording the
worst ratio you actually observed, in this form (substituting your number for 1.0731):

```python
#: MEASURED across seeds 1-10 at n=10 on 2026-08-05: worst was 1.0731.
```

```bash
make test-file FILE="tests/test_tour_ordering.py" TEST_PROFILE=test2
```

Expected: PASS, all tests.

- [ ] **Step 5: Translate the ratio into walking metres, and record it**

The ledger number here is not the ratio — it is what the ratio *costs a walker*. A 90-minute tour
walks about 3,452 seconds. Compute `(ratio - 1) * 3452` and record it as "gives away N seconds of
extra walking on a 90-minute tour".

**If N exceeds `TIMEBOX_MATERIALITY_TOLERANCE_SECONDS` (60, at `src/tour/routing.py:59`), say so
explicitly in the ledger and in your progress post.** It does not block — the routing code's own
definition of an immaterial difference is the right yardstick, and the human should see it either
way.

- [ ] **Step 6: Lint, judge, commit**

```bash
make lint
```

```bash
git add src/tour/ordering.py tests/test_tour_ordering.py
git commit -m "test(ordering): pin the local search quality bar to its measured value"
```

**Ripple: none** — still nothing calls the improver.

---

### Task 3: Wire the improver into the heuristic path

**Files:**
- Modify: `src/tour/ordering.py:173-201` (the `order_stops` docstring and body)
- Modify: `tests/test_tour_ordering.py` (two new tests)
- Modify: `tests/test_workbench_matches_the_app.py:2085-2093, 2170-2176` (docstring, UNDO note,
  assertion 5)

The first task that changes a real tour. It changes only tours **above** the current threshold of
16 stops, which today get plain cheapest insertion with no improvement at all — so it can only
make long tours better.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_tour_ordering.py`:

```python
def test_order_stops_improves_its_heuristic_answer_above_the_exact_threshold():
    """Above the threshold the dispatcher must not ship raw insertion order.

    Before 2026-08-05 it did, so a longer, more expensive tour got a visibly
    worse walk than a short one — the opposite of what a traveller expects.
    """
    n = ORDERING_EXACT_MAX + 6
    pts = _random_points(n, seed=500)
    raw = cheapest_insertion_open(pts, fixed_start=START)
    shipped = order_stops(pts, fixed_start=START)

    assert sorted(p.id for p in shipped) == sorted(p.id for p in pts)
    assert _path_cost(shipped) < _path_cost(raw), (
        "order_stops returned the unimproved insertion order"
    )


def test_nothing_outside_this_module_calls_a_solver_directly():
    """``order_stops`` is the ONE entry point, and this keeps it that way.

    A planning path that calls ``held_karp_open`` itself re-arms the exponential
    hang the dispatcher exists to prevent; one that calls
    ``cheapest_insertion_open`` itself silently skips the improvement pass. Both
    are the same failure: a second route through code that already has an owner.
    Tests may call the pieces directly — that is how the oracle works — so only
    src/ is scanned.
    """
    import pathlib

    src = pathlib.Path(__file__).resolve().parents[1] / "src"
    offenders = [
        f"{path.relative_to(src.parent)}:{lineno}"
        for path in src.rglob("*.py")
        if path.name != "ordering.py"
        for lineno, line in enumerate(path.read_text().splitlines(), start=1)
        if "held_karp_open(" in line or "cheapest_insertion_open(" in line
    ]
    assert not offenders, (
        "these bypass order_stops and must call it instead: " + ", ".join(offenders)
    )
```

- [ ] **Step 2: Run them to verify they fail**

```bash
make test-file FILE="tests/test_tour_ordering.py::test_order_stops_improves_its_heuristic_answer_above_the_exact_threshold" TEST_PROFILE=test2
```

Expected: FAIL — "order_stops returned the unimproved insertion order".

```bash
make test-file FILE="tests/test_tour_ordering.py::test_nothing_outside_this_module_calls_a_solver_directly" TEST_PROFILE=test2
```

Expected: **PASS already** — verified 2026-08-05 that no production code bypasses the dispatcher.
This one is a ratchet, not a fix. Record "already clean" in the ledger.

- [ ] **Step 3: Write the implementation**

In `src/tour/ordering.py`, replace lines 195-201 (`return cheapest_insertion_open(...)`) with:

```python
    rough = cheapest_insertion_open(
        points,
        fixed_start=fixed_start,
        fixed_end=fixed_end,
        round_trip=round_trip,
        routed_cost_fn=routed_cost_fn,
    )
    return improve_order_or_opt(
        rough,
        fixed_start=fixed_start,
        fixed_end=fixed_end,
        round_trip=round_trip,
        routed_cost_fn=routed_cost_fn,
    )
```

And replace the first paragraph of the docstring (lines 173-178):

```python
    """Order ``points`` exactly when tractable, cheaply and then improved above it.

    ``len(points) <= ORDERING_EXACT_MAX`` -> ``held_karp_open``, provably optimal
    and, at that size, cheaper than the budget in
    tests/test_tour_ordering.py::test_the_exact_threshold_is_small_enough_to_be_called_in_a_loop.
    Above it -> cheapest insertion followed by ``improve_order_or_opt``, which
    lands within a measured small ratio of that same proven optimum. The tour
    KEEPS every stop the time budget earned; only the optimality GUARANTEE is
    traded away, and only for a difference no walker can perceive.
```

Also update the module docstring, lines 3-6, which still says the heuristic path is plain
cheapest insertion:

```python
The greedy's insertion order is a by-product of selection, not an optimum;
§3.2's ORDER step fixes that. ``order_stops`` is the entry point every caller
uses: it orders EXACTLY (Held-Karp) while that is cheap, and by cheapest
insertion plus an Or-opt local search above it. No OR-Tools (the design forbids
the dependency).
```

- [ ] **Step 4: Run them to verify they pass**

```bash
make test-file FILE="tests/test_tour_ordering.py" TEST_PROFILE=test2
```

Expected: PASS, whole file.

- [ ] **Step 5: Undo test**

Revert `order_stops` to returning `cheapest_insertion_open(...)` directly. The new test must go
RED. Restore, confirm GREEN, paste both.

- [ ] **Step 6: Retarget the workbench assertion this breaks**

`tests/test_workbench_matches_the_app.py` assertion 5 pins that above the threshold the dispatcher
returns *exactly* cheapest-insertion order. That is now false by design — it returns the improved
order. **This is a named, sanctioned retarget under hard rule 5**, because the assertion's real
subject is "which solver ran", not "insertion specifically".

Replace lines 2170-2176:

```python
    # 5. THE DISPATCH: above the tractability wall the cheap path runs, and its
    #    answer is a genuinely DIFFERENT order from the exact solver's — so this
    #    observes which solver ran rather than trusting the branch. Since
    #    2026-08-05 the cheap path is insertion PLUS an Or-opt improvement pass,
    #    so it matches neither raw insertion nor Held-Karp.
    probe = _probe_points(_ORDERING_PROBE_N, _ORDERING_PROBE_SEED)
    assert _ORDERING_PROBE_N > ORDERING_EXACT_MAX
    dispatched = [p.id for p in _order_stops(probe, fixed_start=_PDV)]
    assert dispatched == [
        p.id
        for p in improve_order_or_opt(
            cheapest_insertion_open(probe, fixed_start=_PDV), fixed_start=_PDV
        )
    ]
    assert dispatched != [p.id for p in held_karp_open(probe, fixed_start=_PDV)], (
        "the dispatcher handed 17 points to the EXACT solver; that is the "
        "exponential path this fallback exists to keep off the planner"
    )
```

Add `improve_order_or_opt` to that test's local import at line 2097:

```python
    from src.tour.ordering import (
        ORDERING_EXACT_MAX,
        cheapest_insertion_open,
        held_karp_open,
        improve_order_or_opt,
    )
```

And fix the two stale lines in its docstring (2085-2086 and 2092), which now describe behaviour
that no longer exists:

```python
    ``ordering.order_stops`` orders EXACTLY up to ``ORDERING_EXACT_MAX`` points,
    and by cheapest insertion plus an Or-opt improvement pass above it, and never
    drops a stop either way.
```

```python
      * delete the ``improve_order_or_opt`` call in ``order_stops`` -> assertion 5;
```

- [ ] **Step 7: Ripple checks**

**What can move:** any tour whose stop set exceeds 16, which the 2026-08-05 measurement showed
happens at 120-minute requests and above.

```bash
make test-file FILE="tests/test_workbench_matches_the_app.py" TEST_PROFILE=test2
```

```bash
make test-file FILE="tests/test_tour_flavours.py" TEST_PROFILE=test2
```

```bash
make test-file FILE="tests/test_tour_selection.py" TEST_PROFILE=test2
```

```bash
make test-file FILE="tests/test_tour_invariants_live.py" TEST_PROFILE=test2
```

**How to address a failure:** a route-order change that keeps every stop and keeps the tour in
band is the intended effect. If a test asserts an exact stop *sequence* above 16 stops, it was
pinning the exact solver's output; widen it to the property it actually cares about (all stops
present, in band, no detour) and say why in the commit message. **A test asserting a stop SET or a
time BAND must not be touched — if one of those fails, `BLOCKED`.**

Then confirm the scoreboard moved:

```bash
make test-file FILE="tests/test_tour_ordering.py::test_one_ordering_call_stays_under_the_per_call_budget" TEST_PROFILE=test2
```

Expected: `n=20`, `25`, `30`, `40` now PASS. `n=16` still fails — that is Task 4.

- [ ] **Step 8: Lint, judge, commit**

```bash
make lint
```

```bash
git add src/tour/ordering.py tests/test_tour_ordering.py tests/test_workbench_matches_the_app.py
git commit -m "feat(ordering): long tours get an improved walk, not raw insertion order"
```

---

### Task 4: Lower the exact threshold

**Files:**
- Modify: `src/tour/ordering.py:18-26` (`ORDERING_EXACT_MAX` and its comment)
- Modify: `tests/test_workbench_matches_the_app.py:2091` (one UNDO line)

The highest-ripple task, and the one that collects the win. At 16 stops the exact solver costs
556 ms; the repair pass calls it hundreds of times per request. At 10 stops it costs 3.6 ms.

- [ ] **Step 1: The test already exists — run it and watch it fail**

```bash
make test-file FILE="tests/test_tour_ordering.py::test_the_exact_threshold_is_small_enough_to_be_called_in_a_loop" TEST_PROFILE=test2
```

Expected: FAIL — "the exact solver at its own threshold n=16 took ~556 ms CPU" against the 50 ms
budget.

- [ ] **Step 2: Write the implementation**

Replace lines 18-26 of `src/tour/ordering.py`:

```python
#: Most points the EXACT open-path Held-Karp solver may be handed. NOT a product
#: limit on tour length — duration is the only such bound. Purely a cost wall.
#:
#: The DP costs 2^n·n^2 transitions. MEASURED 2026-08-05: n=10 is 3.6 ms, n=12 is
#: 20.4 ms, n=13 is 46.6 ms, n=16 is 556 ms, n=17 is 1.27 s, and n=25 is roughly
#: 12 minutes and 33 GB — an unkillable test, not a slow one.
#:
#: 10 rather than 16 because this is not called once per tour. The timebox repair
#: prices between 108 and 495 candidate stop sets per request, each ordering from
#: scratch, so the per-call figure carries a ~500x multiplier. At 16 that is 275
#: seconds of ordering for one 120-minute request; at 10 it is under two.
#:
#: Below this the exact solver is kept because it is genuinely BETTER and free at
#: that size, not because it is a leftover: it returns the provably shortest walk
#: for the tour lengths people most often ask for. Above it, order_stops falls
#: back to cheapest insertion plus an Or-opt local search that lands within a
#: measured small ratio of this solver's optimum. Neither path DROPS a stop the
#: time budget earned.
ORDERING_EXACT_MAX: int = 10
```

- [ ] **Step 3: Run it to verify it passes**

```bash
make test-file FILE="tests/test_tour_ordering.py" TEST_PROFILE=test2
```

Expected: **every test in the file PASSES**, including the 495-call aggregate. This is the moment
the headline number lands. Record the aggregate in the ledger.

- [ ] **Step 4: Undo test**

Set `ORDERING_EXACT_MAX` back to 16. The threshold test and the 495-call aggregate must go RED.
Restore, confirm GREEN, paste both.

- [ ] **Step 5: Fix the stale UNDO instruction this invalidates**

`tests/test_workbench_matches_the_app.py:2091` reads
`* set ``ORDERING_EXACT_MAX = 17`` -> assertions 5 and 6;`. With the threshold at 10 that
instruction no longer produces the effect it claims. Change it to:

```python
      * set ``ORDERING_EXACT_MAX`` above ``_ORDERING_PROBE_N`` -> assertions 5 and 6;
```

- [ ] **Step 6: Ripple checks — this is the big one**

**What can move:** every tour whose stop set is 11 to 16 — which the 2026-08-05 measurement showed
is 60-minute (9 stops) through 120-minute (17 stops) requests. That is most of the suite's
planning tests, and possibly the reference tours.

```bash
make test-file FILE="tests/test_tour_selection.py" TEST_PROFILE=test2
```

```bash
make test-file FILE="tests/test_tour_flavours.py" TEST_PROFILE=test2
```

```bash
make test-file FILE="tests/test_tour_certification_selection.py" TEST_PROFILE=test2
```

```bash
make test-file FILE="tests/test_tour_routing.py" TEST_PROFILE=test2
```

```bash
make test-file FILE="tests/test_workbench_matches_the_app.py" TEST_PROFILE=test2
```

Then the reference tours, the check that matters most:

```bash
make _test-golden
```

`tests/test_tour_golden_ile.py::test_ile_golden_overlap` asserts a beat-ID overlap **floor**, not
an exact sequence, so a small ordering change may well stay above it. **Record the actual overlap
figure whether or not it passes.**

**How to address a failure:**
- A test asserting an exact stop *sequence*: widen it to the property it cares about, as in Task 3.
- **A golden overlap floor breach: `BLOCKED`.** Do not update the baseline. Report before and
  after and hand back.
- **A time-band failure (`CertificationPlanningInfeasibleError`): `BLOCKED`.** A slightly longer
  walk pushed a route out of band, which is product-visible and needs the human.
- If failures are broad, the fallback position is `ORDERING_EXACT_MAX = 13` (46.6 ms, still 12x
  better than 16). Try that value **once**. If it also fails, `BLOCKED`.

- [ ] **Step 7: Lint, judge, commit**

```bash
make lint
```

The judge consult is not a formality here — this task changes tour output. Paste the ruling.

```bash
git add src/tour/ordering.py tests/test_workbench_matches_the_app.py
git commit -m "perf(ordering): exact solving only below 11 stops; the repair calls it 495x"
```

---

### Task 5: Filter, then refine, in the repair pass

**Files:**
- Modify: `src/tour/selection.py:2934` (delete `TIMEBOX_REPAIR_MAX_TRIALS`, add
  `REPAIR_REFINE_TOP_N`)
- Modify: `src/tour/selection.py:2997-3010` and `:3037-3057` (delete two dead guards and the thin
  `consider` wrapper)
- Modify: `src/tour/selection.py:3080-3095` (the enumeration)
- Modify: `tests/test_workbench_matches_the_app.py:2220-2246` (retarget assertion 8)

Task 4 made each ordering call cheap. This one stops making so many. The repair currently fully
orders and prices every add, every drop, and every swap — 108 to 495 trials, nearly all obviously
bad.

**The dead code this creates, and must therefore delete in the same task:**
`TIMEBOX_REPAIR_MAX_TRIALS = 4000` exists only because the enumeration ran away. Once the
shortlist bounds the work at `REPAIR_REFINE_TOP_N`, that ceiling can never be reached. Leaving it
would be a constant that looks load-bearing and is not — the exact trap this plan forbids. Its two
guards (`src/tour/selection.py:3002` and `:3043`) go with it. The `observed` list stays: it is
still read at `:3124` and `:3129` for the no-eligible-trial diagnostic.

- [ ] **Step 1: Write the failing test — by retargeting the one that already exists**

`tests/test_workbench_matches_the_app.py` assertion 8 already counts repair pricing calls. Do not
write a second test that counts them. Replace lines 2220-2246 with:

```python
    # 8. The repair's own bound is real, not decoration. Deleting the stop ceiling
    #    also removed what used to bound its |incumbents| x |pool| enumeration.
    #    Until 2026-08-05 the bound was TIMEBOX_REPAIR_MAX_TRIALS, a ceiling of
    #    4000 that only stopped a runaway; now REPAIR_REFINE_TOP_N bounds the work
    #    ALWAYS, by estimating every candidate cheaply and exactly pricing only the
    #    finalists.
    #
    #    Asserting "a route still comes back" is NOT enough on its own — that is
    #    also true when the bound is deleted. So this counts the pricing calls the
    #    repair actually makes. MEASURED on this fixture: 321 unbounded.
    priced: list[int] = []
    real_trial = selection._certification_route_trial

    def _counting_trial(*args, **kwargs):
        priced.append(1)
        return real_trial(*args, **kwargs)

    monkeypatch.setattr(selection, "_certification_route_trial", _counting_trial)
    bounded = select_route(inp, snap, planning_policy=no_cap_policy)
    assert bounded.pois, (
        "bounding the timebox repair made planning refuse outright; the bound "
        "must degrade the repair, never fail the request"
    )
    assert len(priced) < 60, (
        f"the timebox repair priced {len(priced)} trials with REPAIR_REFINE_TOP_N "
        f"= {selection.REPAIR_REFINE_TOP_N}, so the filter is not engaged "
        f"(unbounded on this fixture is 321)"
    )
```

Note what changed: no `monkeypatch.setattr(selection, "TIMEBOX_REPAIR_MAX_TRIALS", 3)`. The bound
is now always on, so the test no longer has to squeeze anything to observe it.

Update that test's UNDO note at line 2093 in the same edit:

```python
      * raise ``REPAIR_REFINE_TOP_N`` above the shortlist size -> assertion 8.
```

- [ ] **Step 2: Run it to verify it fails**

```bash
make test-file FILE="tests/test_workbench_matches_the_app.py" TEST_PROFILE=test2
```

Expected: FAIL — `AttributeError: ... has no attribute 'REPAIR_REFINE_TOP_N'`, or the count
assertion firing in the hundreds. Record the count; it is this task's before-number.

- [ ] **Step 3: Write the implementation**

Replace `TIMEBOX_REPAIR_MAX_TRIALS: int = 4000` at `src/tour/selection.py:2934` with:

```python
#: How many candidate stop sets the repair PRICES exactly, out of the hundreds it
#: enumerates. Every add and swap is first scored with the cheap marginal-walk
#: estimate ``insertion_cost_seconds`` already computes for the greedy; only the
#: finalists nearest the middle of the time band are then ordered and priced for
#: real. Drops are priced exactly regardless — there are only |stops| of them.
#:
#: Replaces TIMEBOX_REPAIR_MAX_TRIALS (4000), which was a runaway ceiling rather
#: than a bound: it was reached only in pathological cases, so in every normal
#: request the repair still paid for hundreds of exponential orderings.
REPAIR_REFINE_TOP_N: int = 12
```

Delete the guard at `:3002`, so `record` opens:

```python
        if trial is None:
            return
```

Delete the `consider` closure entirely (`:3037-3057`). After the guard above is removed it is a
one-line pass-through to `record`, called from exactly one place, and the shortlist loop below
calls `record` directly.

Replace the enumeration at `:3080-3095` — the `if base is not None:` add-loop through the end of
the `for incumbent ...` loop — with:

```python
    def estimate_elapsed(retained: list[POI], added: POI, reference_walk: int) -> int:
        """Cheap ranking estimate for one add-or-swap candidate.

        Prices the added stop's marginal walk by INSERTION into the existing
        order rather than by re-solving the order, and its audio by the same
        capped-beat rule emission uses. Wrong in detail on purpose: its only job
        is to rank, so the exact pricing below runs a dozen times rather than
        several hundred.
        """
        extra_walk, _idx = insertion_cost_seconds(
            added,
            retained,
            start_lat=input.start[0],
            start_lng=input.start[1],
            round_trip=input.round_trip,
            leg_seconds_fn=leg_seconds_fn,
        )
        audio = sum(
            planned_capped_audio_seconds(
                poi, snapshot, interest or None, MAX_DWELL_AUDIO_SECONDS
            )
            for poi in (*retained, added)
        )
        return reference_walk + extra_walk + audio

    # Enumerate every shape the repair has always considered, but only ESTIMATE
    # here. The sort key's second element is the candidate's stop-set identity, so
    # two equally-promising candidates always resolve the same way and one request
    # cannot return two different tours on two runs.
    nominal = (
        planning_budget.minimum_elapsed_seconds + planning_budget.maximum_elapsed_seconds
    ) // 2
    shortlist: list[tuple[int, tuple[str, ...], list[POI], POI, int]] = []

    def offer(retained: list[POI], candidate: POI, reference_walk: int) -> None:
        trial_selected = [*retained, candidate]
        shortlist.append(
            (
                abs(estimate_elapsed(retained, candidate, reference_walk) - nominal),
                tuple(sorted(poi.id for poi in trial_selected)),
                trial_selected,
                candidate,
                reference_walk,
            )
        )

    if base is not None:
        for candidate in pool:
            offer(list(selected), candidate, base.walk_seconds)
    for incumbent in sorted(selected, key=lambda poi: poi.id):
        retained = [poi for poi in selected if poi.id != incumbent.id]
        retained_trial = _certification_route_trial(
            retained,
            input=input,
            snapshot=snapshot,
            interest=interest,
            leg_seconds_fn=leg_seconds_fn,
            planning_budget=planning_budget,
            pulled_endpoint_id=pulled_endpoint_id,
        )
        reference_walk_seconds = (
            retained_trial.walk_seconds if retained_trial is not None else 0
        )
        # The DROP itself is a solution, not merely a pricing reference. Every
        # other move holds the stop count (exchange) or raises it (add), so
        # without this a route that overshoots the ceiling has NO move that
        # shortens it and the whole option is refused — the 2026-08-04 collapse to
        # a single walk. A removal adds no walk and no audio, so it is never a
        # walk-slog, and it still has to beat every other in-band trial on
        # ``rank`` to be chosen.
        if retained and incumbent.id != protected_end_id:
            record(retained_trial)
        for candidate in pool:
            offer(retained, candidate, reference_walk_seconds)

    shortlist.sort(key=lambda row: (row[0], row[1]))
    for _distance, _key, trial_selected, added, reference_walk in (
        shortlist[:REPAIR_REFINE_TOP_N]
    ):
        record(
            _certification_route_trial(
                trial_selected,
                input=input,
                snapshot=snapshot,
                interest=interest,
                leg_seconds_fn=leg_seconds_fn,
                planning_budget=planning_budget,
                pulled_endpoint_id=pulled_endpoint_id,
            ),
            added=added,
            reference_walk_seconds=reference_walk,
        )
```

Confirm `insertion_cost_seconds` is in `selection.py`'s `from .routing import ...` line; add it if
not.

- [ ] **Step 4: Run it to verify it passes**

```bash
make test-file FILE="tests/test_workbench_matches_the_app.py" TEST_PROFILE=test2
```

Expected: PASS. Record the new pricing count.

- [ ] **Step 5: Undo test**

Set `REPAIR_REFINE_TOP_N = 100000`. Assertion 8 must go RED. Restore, confirm GREEN, paste both.

- [ ] **Step 6: Prove the dead code is gone**

```bash
grep -rn "TIMEBOX_REPAIR_MAX_TRIALS\|def consider" src tests
```

Expected: **no output at all.** Any hit means this task is not finished.

- [ ] **Step 7: Ripple checks**

**What can move:** the repair may now choose a *different* route, because the cheap estimate can
rank a candidate out of the finalists whose exact price would have been better. This is the one
genuinely behaviour-changing approximation in the plan.

```bash
make test-file FILE="tests/test_tour_certification_selection.py" TEST_PROFILE=test2
```

```bash
make test-file FILE="tests/test_tour_selection.py" TEST_PROFILE=test2
```

```bash
make test-file FILE="tests/test_tour_feasibility.py" TEST_PROFILE=test2
```

```bash
make _test-golden
```

**How to address a failure:**
- A route landing in a *different but still valid* position in the band: acceptable; record the
  before and after elapsed seconds.
- **A route now OUT of band, or a refusal where there was none: `BLOCKED`.** The estimate is too
  crude. Report which candidate was filtered out and what its exact price was. The fix is a better
  estimate or a larger `REPAIR_REFINE_TOP_N`, and that call belongs to the human.
- **A golden overlap floor breach: `BLOCKED`**, exactly as in Task 4.

- [ ] **Step 8: Lint, judge, commit**

```bash
make lint
```

```bash
git add src/tour/selection.py tests/test_workbench_matches_the_app.py
git commit -m "perf(selection): repair estimates hundreds of trials and prices twelve"
```

---

### Task 6: The wall-clock deadline

**Files:**
- Modify: `src/tour/selection.py` (`REPAIR_TIME_BUDGET_SECONDS`, and the finalist loop)
- Modify: `tests/test_tour_selection.py` (two new tests — it already owns the fixtures)

Tasks 3-5 made planning fast for the corpus we measured. This makes it impossible to hang on one
we have not. It is the structural answer to "the algorithm must not spin forever", and it replaces
a stop cap — a *proxy* for compute — with the real thing.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_tour_selection.py`. It already defines `PDV`, `_poi`, `_snap`,
`_density_fillers` and `select_route`, so no new fixture is needed — but it imports *names from*
the selection module rather than the module itself, so add this to its import block first:

```python
from src.tour import selection
```

Then append:

```python
def test_the_repair_stops_pricing_when_its_clock_expires(monkeypatch):
    """A tour must still come back when the clock runs out.

    The repair degrades in QUALITY under time pressure — it keeps the best answer
    it has already found — and never in AVAILABILITY. A traveller notices a
    request that never returns; they cannot notice a route a few seconds' walk
    longer than one a slower search would have found.

    This counts pricings rather than timing the call. A wall-clock assertion is
    flaky on a contended host, and "did the clock actually cut the search short"
    is a counting question anyway.
    """
    priced: list[int] = []
    real_trial = selection._certification_route_trial

    def _counting_trial(*args, **kwargs):
        priced.append(1)
        return real_trial(*args, **kwargs)

    monkeypatch.setattr(selection, "_certification_route_trial", _counting_trial)
    snap = _snap(_density_fillers(PDV))
    inp = TourInput(start=PDV, duration_min=60, city_slug="paris", round_trip=False)

    full = select_route(inp, snap)
    assert full.pois
    with_budget = len(priced)

    priced.clear()
    monkeypatch.setattr(selection, "REPAIR_TIME_BUDGET_SECONDS", 0.0)
    expired = select_route(inp, snap)
    assert expired.pois, "an expired budget must degrade the answer, not refuse"
    assert len(priced) < with_budget, (
        f"an expired clock priced {len(priced)} trials, the same as the "
        f"{with_budget} a full budget prices — the deadline is not enforced"
    )


def test_the_default_repair_budget_is_a_safety_net_not_a_governor():
    """A deadline that fires in normal operation is a silent quality regression."""
    assert selection.REPAIR_TIME_BUDGET_SECONDS >= 5.0
```

A budget of exactly `0.0` puts the deadline in the past before the loop runs, so no finalist is
priced at all — deterministic on any machine, and it does not need a large corpus to observe.

- [ ] **Step 2: Run them to verify they fail**

```bash
make test-file FILE="tests/test_tour_selection.py::test_the_default_repair_budget_is_a_safety_net_not_a_governor" TEST_PROFILE=test2
```

Expected: FAIL — `AttributeError: module 'src.tour.selection' has no attribute
'REPAIR_TIME_BUDGET_SECONDS'`.

- [ ] **Step 3: Write the implementation**

Add beside `REPAIR_REFINE_TOP_N` in `src/tour/selection.py`:

```python
#: Wall-clock seconds the timebox repair may spend before it settles for the best
#: answer it has already found. This is the honest replacement for the stop
#: ceilings deleted on 2026-08-04: those bounded COMPUTE by bounding a PRODUCT
#: quantity, which is why removing them for good product reasons uncapped the
#: compute too and nothing was watching. A clock bounds the thing that actually
#: needs bounding, and degrades in quality rather than in availability.
#:
#: 15 s is a safety net, not a governor: after 2026-08-05 a 120-minute request
#: prices its whole shortlist in well under two seconds, so this fires only on a
#: corpus shape we have never seen.
REPAIR_TIME_BUDGET_SECONDS: float = 15.0
```

Immediately after the `base = _certification_route_trial(...)` assignment near `:2960`:

```python
    deadline = time.monotonic() + REPAIR_TIME_BUDGET_SECONDS
```

Guard **both** phases, because both scale with the corpus. First, the enumeration — add as the
opening line of `offer` from Task 5:

```python
    def offer(retained: list[POI], candidate: POI, reference_walk: int) -> None:
        if time.monotonic() > deadline:
            return  # the shortlist so far is smaller but still valid
```

Then the finalist loop:

```python
    for _distance, _key, trial_selected, added, reference_walk in (
        shortlist[:REPAIR_REFINE_TOP_N]
    ):
        if time.monotonic() > deadline:
            # Out of time. Everything banked so far is still a valid answer and
            # the ranking below picks the best of them. Stopping here costs at
            # most the finalists we did not reach, never the route itself.
            break
```

Guarding only the finalist loop would leave the guarantee half-built: the estimate is cheap per
candidate but there are |stops| x |pool| of them, so on a corpus far larger than Paris's the
enumeration alone could outrun any budget the loop below it respects.

Add `import time` to `selection.py`'s top-level imports if absent.

- [ ] **Step 4: Run them to verify they pass**

```bash
make test-file FILE="tests/test_tour_selection.py" TEST_PROFILE=test2
```

Expected: the whole file PASSES.

- [ ] **Step 5: Undo test**

Remove **both** deadline checks — the one in `offer` and the one in the finalist loop.
`test_the_repair_stops_pricing_when_its_clock_expires` must go RED, because an expired clock will
now price exactly as many trials as a full budget does. Restore, confirm GREEN, paste both.

Then remove them **one at a time** and confirm the test goes RED for each. If removing the `offer`
guard alone leaves it green, the enumeration guard is untested — say so in the ledger rather than
claiming a guarantee you have not shown. It does not block: the finalist guard is the one that
bounds the expensive phase, and the enumeration guard is defence against a corpus we do not have
to hand.

- [ ] **Step 6: Ripple checks**

**What can move:** nothing, under the default budget. That is exactly what to verify.

```bash
make test-file FILE="tests/test_tour_flavours.py" TEST_PROFILE=test2
```

```bash
make test-file FILE="tests/test_tour_certification_selection.py" TEST_PROFILE=test2
```

**How to address a failure:** if any result *changes* after adding the deadline, the default is
too tight for a real workload. Raise it to 30 s **once** and re-run. If it still bites, `BLOCKED`
— a deadline that fires in normal operation is a hidden quality regression and the human needs the
numbers.

- [ ] **Step 7: Lint, judge, commit**

```bash
make lint
```

```bash
git add src/tour/selection.py tests/test_tour_selection.py
git commit -m "feat(selection): bound the repair by a clock, not by a product knob"
```

---

### Task 7: Close-out and dead-code sweep

**Files:**
- Create: `specs/2026-08-05-ordering-performance/RESULT.md`
- Delete: `specs/2026-08-05-ordering-performance/LEDGER.md`
- Modify: `specs/2026-08-04-unify-tour-algorithm/HANDOVER.md`

- [ ] **Step 1: Re-measure the four rows the predecessor left open**

Exactly the rows `specs/2026-08-04-unify-tour-algorithm/HANDOVER.md` ERROR 2 demands:

```bash
time make test-file FILE="tests/test_trip_api.py" TEST_PROFILE=test2
```

```bash
time make test-file FILE="tests/test_tour_flavours.py" TEST_PROFILE=test2
```

```bash
time make test-file FILE="tests/test_tour_b_materialization.py" TEST_PROFILE=test2
```

- [ ] **Step 2: Run the full definitive bar, once**

```bash
make test
```

The only run of it in this plan, and `make audit` inside it is the only paid command. Never in a
loop. Record total wall-clock time and the failure count.

- [ ] **Step 3: Write the result document**

Create `specs/2026-08-05-ordering-performance/RESULT.md` containing, in order:

1. This table, filled in:

| | before the unification | after it (2026-08-04) | now |
| --- | --- | --- | --- |
| full Python shard | ~15 min (899 s) | 1 h 48 m (6,509 s) | *measure* |
| `tests/test_trip_api.py` alone | — | 33 m 53 s | *measure* |
| `tests/test_tour_flavours.py` | < 2 s | ~4 m 30 s | *measure* |
| `tests/test_tour_b_materialization.py` | < 1 s | ~1 m | *measure* |
| one 120-min planning request | — | 191 s | *measure* |

2. What the local search gives away, in seconds of extra walking on a 90-minute tour (Task 2
   Step 5).
3. The reference-tour overlap figures before and after (Task 4 Step 6).
4. Whether the predecessor's acceptance bar is met — full Python shard under 30 minutes, zero
   tests deleted, skipped or deselected, no fixture thinned. State it as a yes or a no.
5. The two deferred plans named in Scope, one sentence each on what they would still buy.

Write it for someone who has never opened this repo. No identifiers as sentence subjects.

- [ ] **Step 4: The dead-code sweep — this must find nothing**

Run all four. Any output at all means an earlier task was left unfinished; go back and finish it
rather than explaining the leftover.

```bash
grep -rn "TIMEBOX_REPAIR_MAX_TRIALS\|test_tour_ordering_heldkarp\|def consider\|_bench_ordering" src tests scripts Makefile
```

```bash
grep -rn "cheapest insertion above it\|by cheapest insertion above" src tests
```

**`specs/` is deliberately not swept.** Two kinds of hit live there and neither is a dangling
pointer: the 2026-08-04 folder's findings and ledger are a historical record of what an earlier
investigation saw at the time, and rewriting a record to match later code misrepresents it; and
`PLAN.md` itself narrates the rename as an instruction and contains this very grep, so sweeping it
would make the check chase its own tail.

```bash
make lint
```

```bash
git status --porcelain
```

The first two must print nothing — the first catches constants, files and helpers this plan
retired; the second catches prose that still describes the pre-2026-08-05 fallback. `make lint`
must be zero errors. `git status` must show no untracked scratch files, probe scripts, or log
dumps.

- [ ] **Step 5: Retire the ledger**

```bash
git rm specs/2026-08-05-ordering-performance/LEDGER.md
```

Keep `PLAN.md` and `RESULT.md`.

- [ ] **Step 6: Judge, commit**

```bash
git add specs/2026-08-05-ordering-performance/
git commit -m "docs(ordering): close out ERROR 2 with measured before-and-after"
```

- [ ] **Step 7: Correct the predecessor**

In `specs/2026-08-04-unify-tour-algorithm/HANDOVER.md`, change ERROR 2's
`**Status:** OPEN. No fix attempted; it needs a product decision first.` to a one-line pointer at
`specs/2026-08-05-ordering-performance/RESULT.md` carrying the headline number. A document that
contradicts the code is an active trap for the next session.

```bash
git add specs/2026-08-04-unify-tour-algorithm/HANDOVER.md
git commit -m "docs(handover): ERROR 2 is closed; point at the measured result"
```

---

## What this plan does NOT do

Stated so nobody rediscovers them as gaps:

- **The stop cap stays deleted.** The 2026-08-05 measurement showed the uncapped planner settles at
  roughly one stop per seven minutes rather than running away, and that density gives the walker
  less silent walking between stops, not a more rushed tour. The per-stop audio ceiling, untouched
  here, is what protects against rushing. Reinstating the cap to buy speed would pay for
  performance with the traveller's experience, and this plan buys the same speed for free.
- **Option cards are still fully planned before the traveller picks one.** Deferred; see Scope.
- **The narration over-credit is untouched.** Deferred; see Scope.
- **`selection.py` is still over 3,000 lines.** A performance fix does not need surrounding
  cleanup.
