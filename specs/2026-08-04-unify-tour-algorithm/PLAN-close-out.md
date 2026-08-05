# Unify Tour Algorithm — Close-Out Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Get the finished-but-uncommitted tour-unification work protected, fix the
fixed-destination (A→B) refusal it exposed, pass the owner-ordered close-out gate, and merge
to `main` — then hand the owner a measured narration decision.

**Architecture:** Four phases, strictly ordered. Phase 0 protects 8,359 uncommitted lines
behind a safety commit. Phase 1 fixes a units error in `src/tour/selection.py` that makes every
A→B request refuse; its proving test is already written and RED in the tree. Phase 2 runs the
full close-out gate and merges. Phase 3 measures the test slowdown and produces the numbers the
owner needs for the narration-over-credit decision, which is deliberately NOT made here.

**Tech Stack:** Python 3 / pytest / ruff, Flutter (Dart) widget tests, Playwright browser
shard, Neo4j (7687 dev / 7688 test / 7690 test2 / 7691 test3), Valhalla routing, Make as the
only supported command surface.

---

## Read this before you touch anything

**You are finishing someone else's run.** The previous session built 17 steps, proved them,
found four defects, and then stopped without committing. Four things about that will bite you
if you do not know them:

1. **Nothing is committed.** `git diff --stat HEAD` shows 54 files, +8,359 / −2,616. There is
   no commit anywhere holding this work. Phase 0 exists solely to fix that, and it comes before
   everything else.

2. **`make format` is a landmine.** It runs `ruff format` over every lint path and rewrote 123
   files last time it was tried. The repo has never been `ruff format`-clean and no gate
   enforces it. **Never run `make format` in this plan.** To fix a scoped lint error use
   `uv run ruff check --fix-only <single file>` and record that you did — it is a raw
   invocation, which this project normally forbids.

3. **A comment in the code already describes a fix that was never applied.**
   `src/tour/selection.py:1738-1751` explains, in past tense, why the greedy walk budget must
   be a walk budget — but line 1753 still assigns the old wrong value. The fix lane was killed
   after writing the comment and the failing test, before writing the code. Do not read that
   comment and conclude the work is done. Read the *code*.

4. **The last run's worst failure was a correct prediction rated harmless.**
   `findings/contracts-caps-and-policy.md:1099` predicts the exact A→B breakage you are about
   to fix and records its risk as "none". When this plan tells you to check something, check
   it — do not trust a confident-sounding note, including this one.

**Cost discipline.** `make audit` is the only command that spends provider money. It runs
exactly once, in Task 12, never inside a loop. `make test-file` costs no provider money but is
NOT read-only: it starts the shared Neo4j containers and Valhalla and writes to the dev graph.
Assume exclusive use of local containers while this plan runs.

**Always tee long commands.** Piping a long run through `tail` alone shows nothing until it
finishes; that is how the last run went blind for an hour. Every long command in this plan is
written as `... 2>&1 | tee logs/<name>.log | tail -40`.

---

## File Structure

| File | Responsibility | This plan |
| --- | --- | --- |
| `src/tour/selection.py` | Stop selection, greedy seating, reach pre-filter | Modify 2 sites: `:1752-1757` (greedy walk budget), `:1547-1552` (reach radius) |
| `tests/test_tour_certification_selection.py` | Certification-arm selection unit tests | 1 test already present and RED at `:730`; add 1 new test for the reach radius |
| `tests/test_trip_api.py` | API-level trip generation | Read-only — `TestTripGenerateFixedDestination` at `:502` is the acceptance check |
| `specs/2026-08-04-unify-tour-algorithm/state.json` | The step ledger | Modify: mark steps 4–18 completed |
| `logs/` | Run logs so progress is visible live | Create (gitignored) |

Only two production lines change in this whole plan. Everything else is proof, gating, and
bookkeeping. If you find yourself editing a third production site, stop and report it — that is
the "blast radius exceeded the declared file list" failure that cost the last run its schedule.

---

## Phase 0 — Protect the work

### Task 1: Safety commit on a branch

**Files:** none created or modified — this is a git operation over the existing working tree.

**Why this is not a normal commit.** The project's pre-commit checklist requires `make test`
green. It cannot be green right now: `tests/test_tour_certification_selection.py:730` is a
proving test deliberately left RED until Task 3 lands. So waiting for green means doing the
whole A→B fix with 8,359 lines unprotected. This commit is a **save point on a branch, not a
ship**. `main` is untouched. The full bar is still required before Task 13 merges anything.

- [ ] **Step 1: Confirm what you are about to commit**

Run:
```bash
git status --short && git diff --stat HEAD | tail -3
```
Expected: 54 files listed; final line reading `54 files changed, 8359 insertions(+), 2616 deletions(-)`.

If the counts differ materially from that, **stop and report** — someone has changed the tree
since this plan was written, and the rest of the plan's line numbers may be stale.

- [ ] **Step 2: Create the log directory and make sure it is ignored**

Run:
```bash
mkdir -p logs && grep -qxF 'logs/' .gitignore || echo 'logs/' >> .gitignore
```

- [ ] **Step 3: Create the branch**

Run:
```bash
git checkout -b unify-tour-algorithm-closeout
```
Expected: `Switched to a new branch 'unify-tour-algorithm-closeout'`

- [ ] **Step 4: Commit everything as a save point**

Run:
```bash
git add -A && git commit -F- <<'EOF'
wip(tour): save point for the tour-algorithm unification before close-out

Steps 4-18 of specs/2026-08-04-unify-tour-algorithm are built and individually
proven but were never committed. This commit exists to make 8,359 lines of
finished work recoverable; it is NOT a claim that the bar is met.

Known RED, deliberately:
  tests/test_tour_certification_selection.py::
    test_fixed_destination_greedy_is_capped_by_the_walk_budget_not_the_total_ceiling

That test is the executable contract for the A->B units bug this work exposed
(src/tour/selection.py:1753 caps WALKING with a TOTAL-ACTIVE-TIME ceiling).
It goes green in the close-out plan's Task 3.

make lint: clean. node .claude/team-engine.test.js: 91/91.
make test: NOT run to completion; the full bar runs before any merge to main.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

- [ ] **Step 5: Verify the save point exists and the tree is clean**

Run:
```bash
git log --oneline -1 && git status --short | wc -l
```
Expected: the new commit hash and subject, then `0`.

**If this step shows anything other than 0**, files were missed. Report before continuing.

---

## Phase 1 — Fix the A→B refusal

**The bug in one sentence:** the cap on how long the planner may *walk* was set to the ceiling
on *total tour time* (walking plus talking), so at 90 minutes it was allowed 6,000 seconds of
walking against a 2,160-second walking allowance — and then refused its own over-long answer.

**Measured evidence from the last run, on the live Paris dev graph at 90 minutes** (band
4,860–5,940 s):

| | stops | walk | narration | total | in band |
| --- | --- | --- | --- | --- | --- |
| open route, no fixed end | 9 | 3,452 s | 1,921 s | 5,373 s | yes |
| fixed end, as the engine builds it today | 15 | 5,258 s | 2,579 s | 7,837 s | **no** |
| the open route's own 9 stops, priced with the destination pinned | 9 | 3,452 s | 1,921 s | 5,373 s | **yes** |

The third row is the proof that a valid answer exists and the engine already knows it: pinning
the destination costs nothing. The engine simply bolts on six more stops it cannot afford.

### Task 2: See the failure for yourself before changing anything

**Files:** none — observation only.

- [ ] **Step 1: Run the proving test and watch it fail**

Run:
```bash
make test-file FILE="tests/test_tour_certification_selection.py::test_fixed_destination_greedy_is_capped_by_the_walk_budget_not_the_total_ceiling" TEST_PROFILE=test2 2>&1 | tee logs/task2-red.log | tail -40
```
Expected: `1 failed`. The assertion message names the real numbers, in the form:
`greedy handed on N stops implying <big>s of walking against a 2160s walking allocation (total-active ceiling 6000s)`

**Record the two numbers** from that message (stop count and implied walking seconds) in your
report. They are your before-measurement, and Task 3 must move them.

- [ ] **Step 2: Confirm the two production lines still say what this plan expects**

Run:
```bash
sed -n '1752,1757p;1547,1552p' src/tour/selection.py
```
Expected to contain `greedy_walk_budget = certification_total_ceiling` and
`reach_walk_minutes = certification_total_ceiling / 60.0`.

If either line differs, **stop and re-read the file** — the line numbers in this plan came from
a snapshot and the code may have moved.

### Task 3: Make the walking cap a walking budget

**Files:**
- Modify: `src/tour/selection.py:1752-1757`
- Test: `tests/test_tour_certification_selection.py:730` (already written, currently RED)

- [ ] **Step 1: Apply the fix**

Replace lines 1752–1757 of `src/tour/selection.py`:

```python
    if certification_fixed_end:
        greedy_walk_budget = certification_total_ceiling
    elif input.round_trip:
        greedy_walk_budget = walk_budget
    else:
        greedy_walk_budget = int(walk_budget * (1.0 - ENDPOINT_PULL_RESERVED_BUDGET_FRACTION))
```

with:

```python
    if certification_fixed_end or input.round_trip:
        greedy_walk_budget = walk_budget
    else:
        greedy_walk_budget = int(walk_budget * (1.0 - ENDPOINT_PULL_RESERVED_BUDGET_FRACTION))
```

This is exactly what the comment immediately above it (`:1738-1751`) already says should
happen: the endpoint-pull reserve is subtracted only on the open one-way shape, because that is
the only shape that runs the endpoint-pull post-step. A round trip and a fixed destination both
get the whole walking allocation.

**Do not touch** `MAX_DWELL_AUDIO_SECONDS`, the 270-vs-1080 narration credit, the band, or any
stop ceiling. Those are separate decisions and two of them belong to the owner.

- [ ] **Step 2: Run the proving test and watch it pass**

Run:
```bash
make test-file FILE="tests/test_tour_certification_selection.py::test_fixed_destination_greedy_is_capped_by_the_walk_budget_not_the_total_ceiling" TEST_PROFILE=test2 2>&1 | tee logs/task3-green.log | tail -20
```
Expected: `1 passed`.

- [ ] **Step 3: Mutation test — prove the test is real**

Put the bug back:

```python
    if certification_fixed_end:
        greedy_walk_budget = certification_total_ceiling
    elif input.round_trip:
        greedy_walk_budget = walk_budget
    else:
        greedy_walk_budget = int(walk_budget * (1.0 - ENDPOINT_PULL_RESERVED_BUDGET_FRACTION))
```

Run the same command as Step 2.
Expected: `1 failed`. If it still passes, the test is not testing your change — **stop and
report**, do not proceed.

Then restore the Step 1 fix and re-run.
Expected: `1 passed`.

- [ ] **Step 4: Confirm the companion test still passes**

The sibling test pins that the *open* arm keeps its 0.75 endpoint-pull reserve — that is what
stops this fix leaking into ordinary tours.

Run:
```bash
make test-file FILE="tests/test_tour_certification_selection.py" TEST_PROFILE=test2 2>&1 | tee logs/task3-file.log | tail -20
```
Expected: `15 passed` (was 1 failed / 14 passed).

- [ ] **Step 5: Lint**

Run:
```bash
make lint
```
Expected: `All checks passed.` Never pipe this through `head` or `tail`.

- [ ] **Step 6: Commit**

```bash
git add src/tour/selection.py && git commit -F- <<'EOF'
fix(tour): cap the greedy on the WALK budget, not the total-active ceiling

A->B requests refused universally. greedy_walk_budget was set to
certification_total_ceiling, which bounds walking PLUS narration: at 90 minutes
that handed the greedy 6000 walking seconds against a 2160s walking allocation.
The greedy could therefore spend the whole tour's elapsed budget on walking
before one second of narration was counted, seat ~15 stops, and breach the band
by construction -- so the planner refused its own answer. Measured the same day
on the live Paris dev graph: a 90-minute walk ending 27 m from its own start
seated 15 stops and 5787 s of walking, then refused.

The endpoint-pull reserve stays subtracted on the open one-way arm alone, which
is the only shape that runs the endpoint-pull post-step.

Proven by tests/test_tour_certification_selection.py::
  test_fixed_destination_greedy_is_capped_by_the_walk_budget_not_the_total_ceiling
RED before, GREEN after, mutation-confirmed.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

### Task 4: Derive the reach radius from the walking envelope

**Files:**
- Modify: `src/tour/selection.py:1547-1552`
- Test: `tests/test_tour_certification_selection.py` (new test, added next to its sibling)

**Why this needs its own test.** The Task 3 proving test replaces `_reach_predicate` with a
stub that accepts everything, so it cannot see the reach radius at all. Fix Task 3 alone and
the suite goes green with half the contract delivered. That is exactly the kind of half-fix
this plan exists to prevent.

**The numbers, and how they were obtained.** At 90 minutes the total-active ceiling is 6,000 s
= 100 min, giving `(100 × 3.0 km/h × 1000) / 60 / 1.35` = **3,704 m**. The walking envelope is
`90 × 1.00 × 0.40` = 36 min, giving **1,333 m**. Constants: `PACE_KMH = 3.0` and
`HAVERSINE_CORRECTION = 1.35` (`src/tour/routing.py:48-49`), `WALK_FRACTION = 0.40`.

**Honesty note:** those two figures were computed by hand from the constants, not observed from
a run. They match the previous session's independently measured 3,704 m / 1,333 m, which is
good corroboration but not proof. **Treat the first RED run as the authority** — if it reports
different numbers, use the reported ones and say so in your report.

**Why narrowing the radius cannot exclude a legitimate candidate:** a fixed-end candidate only
earns candidacy if the routed detour A → poi → B fits inside the walk budget. The poi → B leg
is never negative, so A → poi alone already fits the walk budget, which is precisely the 1,333 m
envelope. Anything outside that radius could never have survived the corridor filter that runs
immediately after. The wide radius bought nothing and cost a candidate pool roughly twice the
size (95 POIs against 47 on the open arm).

- [ ] **Step 1: Check which names the test file already imports**

Run:
```bash
sed -n '1,60p' tests/test_tour_certification_selection.py
```

You need `math`, `envelope_radius_m`, `route_planning_budget`, `TourInput`, `select_route`,
`pytest`, and the file's local `_policy` / `_poi` / `_snapshot` helpers. Most are already
there — `route_planning_budget` and `TourInput` are used by the test at `:730`. Add only what
is genuinely missing, in isort order.

- [ ] **Step 2: Write the failing test**

Add this immediately after
`test_fixed_destination_greedy_is_capped_by_the_walk_budget_not_the_total_ceiling`
(it ends at `:811`) and before `test_open_route_greedy_still_reserves_budget_for_the_endpoint_pull`.

**Insert it between those two named neighbours, not at end-of-file** — three separate lanes
appending at EOF is what produced merge conflicts last run.

```python
def test_fixed_destination_reach_radius_comes_from_the_walk_envelope(monkeypatch):
    """The reach pre-filter bounds WALKING, so the walk envelope must size it.

    REGRESSION (2026-08-04). The fixed-destination arm derived its reach radius
    from ``certification_total_ceiling`` — walking PLUS narration — giving
    3704 m at 90 minutes where the walking envelope is 1333 m. That admitted a
    candidate pool roughly twice the size (95 POIs against 47 on the open arm),
    every one of which the corridor filter then had to price.

    Narrowing it excludes nothing legitimate. A fixed-end candidate earns
    candidacy only if the routed detour A → poi → B fits the walk budget, and
    the poi → B leg is never negative, so A → poi alone already fits the walk
    envelope. Anything beyond this radius could not have survived the corridor
    filter that runs immediately afterwards.

    Companion to the greedy-budget test above, which cannot see this: that test
    stubs ``_reach_predicate`` out entirely, so the radius is invisible to it.
    """
    import src.tour.selection as selection_module

    class StopAfterReachError(Exception):
        pass

    policy = _policy()
    budget = route_planning_budget(90, policy)
    expected_radius_m = envelope_radius_m(90, round_trip=False, planning_policy=policy)
    assert int(expected_radius_m) == 1333
    assert int(budget.walk_envelope_minutes) == 36

    captured: dict[str, float] = {}

    def capture_reach(_origin, radius_m, iso_minutes, _routing_client):
        captured["radius_m"] = radius_m
        captured["iso_minutes"] = iso_minutes
        raise StopAfterReachError

    monkeypatch.setattr(selection_module, "_reach_predicate", capture_reach)

    pois = [
        _poi(f"detour-{index}", x=0.0016637, y=offset, audio=270)
        for index, offset in enumerate(
            (0.0053, -0.0053, 0.0045, -0.0045, 0.0037, -0.0037, 0.0029, -0.0029)
        )
    ]
    snapshot = _snapshot(pois, {poi.id: 270 for poi in pois})
    tour_input = TourInput(
        start=(0.0, 0.0),
        end=(0.0, 0.0033274),
        duration_min=90,
        city_slug="test",
    )

    with pytest.raises(StopAfterReachError):
        select_route(tour_input, snapshot, planning_policy=policy)

    assert captured["radius_m"] == pytest.approx(expected_radius_m), (
        f"fixed-destination reach used {captured['radius_m']:.0f} m against a "
        f"{expected_radius_m:.0f} m walking envelope"
    )
    assert captured["iso_minutes"] == math.ceil(budget.walk_envelope_minutes)
```

- [ ] **Step 3: Run it and watch it fail**

Run:
```bash
make test-file FILE="tests/test_tour_certification_selection.py::test_fixed_destination_reach_radius_comes_from_the_walk_envelope" TEST_PROFILE=test2 2>&1 | tee logs/task4-red.log | tail -30
```
Expected: `1 failed`, with the assertion message reporting roughly `3704 m` against `1333 m`.

**If it fails on `int(expected_radius_m) == 1333` instead**, the constants differ from this
plan's arithmetic. Read the reported value, use it, and note the correction in your report.

- [ ] **Step 4: Apply the fix**

Replace lines 1547–1552 of `src/tour/selection.py`:

```python
    if certification_fixed_end:
        reach_walk_minutes = certification_total_ceiling / 60.0
        radius_m = (
            reach_walk_minutes * PACE_KMH * 1000.0
        ) / 60.0 / HAVERSINE_CORRECTION
        iso_minutes = max(1, math.ceil(reach_walk_minutes))
```

with:

```python
    if certification_fixed_end:
        # The reach pre-filter bounds WALKING, so the walking envelope sizes it —
        # not the total-active ceiling, which also covers narration. A fixed-end
        # candidate must satisfy A → poi → B inside the walk budget anyway, and
        # the poi → B leg is never negative, so nothing inside the corridor
        # filter's reach lies outside this radius. A round trip halves the
        # envelope; a fixed destination is never a round trip.
        reach_walk_minutes = planning_budget.walk_envelope_minutes
        radius_m = envelope_radius_m(
            input.duration_min,
            round_trip=False,
            planning_policy=planning_policy,
        )
        iso_minutes = max(1, math.ceil(reach_walk_minutes))
```

- [ ] **Step 5: Run it and watch it pass**

Run the same command as Step 3.
Expected: `1 passed`.

- [ ] **Step 6: Mutation test**

Put the old four lines back, re-run Step 3's command, expect `1 failed`. Restore the fix,
re-run, expect `1 passed`. If the mutation does not go RED, **stop and report**.

- [ ] **Step 7: Whole file, then lint**

Run:
```bash
make test-file FILE="tests/test_tour_certification_selection.py" TEST_PROFILE=test2 2>&1 | tee logs/task4-file.log | tail -20
make lint
```
Expected: `16 passed`, then `All checks passed.`

If `PACE_KMH` or `HAVERSINE_CORRECTION` is now an unused import in `selection.py`, ruff will
say so (F401). Fix it with `uv run ruff check --fix-only src/tour/selection.py` — **not**
`make format`.

- [ ] **Step 8: Commit**

```bash
git add src/tour/selection.py tests/test_tour_certification_selection.py && git commit -F- <<'EOF'
fix(tour): size the fixed-end reach radius from the walking envelope

The fixed-destination arm derived its reach radius from the total-active
ceiling (walking plus narration), giving 3704 m at 90 minutes where the
walking envelope is 1333 m -- a candidate pool roughly twice the size (95 POIs
against 47 on the open arm) for the corridor filter to price.

Nothing legitimate is excluded: a fixed-end candidate must satisfy
A -> poi -> B within the walk budget, and the poi -> B leg is never negative,
so A -> poi alone already fits the envelope.

Its sibling test cannot cover this -- it stubs _reach_predicate out entirely --
so this adds a test that captures the radius the planner actually asks for.
RED before, GREEN after, mutation-confirmed.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

### Task 5: Acceptance — the A→B request the user actually makes

**Files:** none modified. This is the acceptance check for Phase 1.

**KNOWN TRAP, handle explicitly.** `test_ab_request_route_ends_at_b` asserts two separate
things: that the request succeeds, and that the API's stop order equals a bare `select_route`
call. The diagnosis proved only that the *refusal* is wrong. It did **not** prove the ordering
equality holds once the refusal is gone. If the test still fails on that second assertion, that
is a **different question** — report it with the actual output and stop. **Do not weaken the
assertion to reach green.**

- [ ] **Step 1: Run the fixed-destination API tests**

Run:
```bash
make test-file FILE="tests/test_trip_api.py::TestTripGenerateFixedDestination" TEST_PROFILE=test2 2>&1 | tee logs/task5-ab.log | tail -40
```
Expected: all pass, `test_ab_request_route_ends_at_b` among them.

- [ ] **Step 2: Report the shape of the route, not just a pass**

From the log, report stops / walk / narration / total for the A→B case. The previous session's
expected shape is 9 stops, ~3,452 s walking, ~1,921 s narration, ~5,373 s total, inside the
4,860–5,940 s band. A pass with a wildly different shape is worth flagging even though it is
green.

### Task 6: Prove ordinary tours did not move

**Files:** none modified.

This is the guard on the whole of Phase 1. The fix must be invisible to every tour that does
not name a destination.

- [ ] **Step 1: Golden reference tours**

Run:
```bash
make _test-golden 2>&1 | tee logs/task6-golden.log | tail -30
```
Expected: 9 passed. This is the same shard `make test` runs.

- [ ] **Step 2: Grade checks**

Run:
```bash
make _test-grade 2>&1 | tee logs/task6-grade.log | tail -30
```
Expected: 15 passed.

**If any golden tour moved**, stop. Phase 1 was supposed to change only the fixed-destination
arm. A moved golden means it leaked into the open path — report the diff with
`make golden-diff FIXTURE=<name>` and do not re-baseline.

- [ ] **Step 3: Commit nothing, report**

Nothing changed in this task. Post the two results as your Phase 1 close-out and consult the
judge agent before moving to Phase 2 — that is a phase transition, which the Judge Protocol
requires. Paste its ruling.

---

## Phase 2 — Pass the close-out gate and merge

The previous run wrote itself a binding 10-rung checklist and stopped partway. Phase 2 is that
checklist. **A failure at any rung stops the close** — fix it and restart from that rung.

### Task 7: Bring the ledger in line with reality

**Files:**
- Modify: `specs/2026-08-04-unify-tour-algorithm/state.json`

The ledger still records steps 4–18 as `pending` although all of them were built and proven.
Rung 1 of the checklist requires every step marked completed with real proof. A ledger that
disagrees with the tree is the "stale document is worse than none" trap the project rules name
explicitly.

- [ ] **Step 1: Confirm the discrepancy**

Run:
```bash
python3 -c "
import json
d = json.load(open('specs/2026-08-04-unify-tour-algorithm/state.json'))
for s in d['steps']:
    print(s['id'], s['status'])
"
```
Expected: steps 1–3 `completed`, steps 4–18 `pending`.

- [ ] **Step 2: Read one completed step to learn the proof format**

Run:
```bash
python3 -c "
import json
d = json.load(open('specs/2026-08-04-unify-tour-algorithm/state.json'))
print(json.dumps(d['steps'][2], indent=2)[:2000])
"
```

Match whatever fields step 3 carries (proof command, result, notes). Do not invent a new shape.

- [ ] **Step 3: Mark steps 4–18 completed, each with its real proving command**

Edit `state.json` so each of steps 4–18 carries `"status": "completed"` and the proof fields in
the same shape as step 3, citing the command that actually proved it. The per-step proof
commands are recorded in `HANDOVER.md` Part 1 under "The ledger".

**Do not fabricate a proof line for a step you cannot trace to a real command.** If a step's
proof cannot be found, mark it completed with a note saying the proof was not recoverable and
name it in your report. An honest gap beats an invented citation.

- [ ] **Step 4: Verify the file is still valid JSON against its schema**

Run:
```bash
python3 -c "
import json
d = json.load(open('specs/2026-08-04-unify-tour-algorithm/state.json'))
pend = [s['id'] for s in d['steps'] if s['status'] != 'completed']
print('valid json; still not completed:', pend or 'none')
"
```
Expected: `still not completed: none`

- [ ] **Step 5: Commit**

```bash
git add specs/2026-08-04-unify-tour-algorithm/state.json && git commit -m "docs(specs): mark steps 4-18 completed with their proving commands

The ledger recorded every step after 3 as pending although all were built and
individually proven. Rung 1 of the close-out requires the ledger to match the
tree; a spec that disagrees with the code is read as current by the next
session and acted on.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

### Task 8: Lint and the engine guard

**Files:** none modified.

- [ ] **Step 1: Lint, unpiped**

Run:
```bash
make lint
```
Expected: `All checks passed.` Never through `head` or `tail`. "Pre-existing" is not an
exemption.

- [ ] **Step 2: The team-engine cap guard**

Run:
```bash
node .claude/team-engine.test.js
```
Expected: `91/91`, exit 0. This lives outside `make test` by design, so it only runs when you
run it. Never edit the guard to make it pass.

### Task 9: The full suite — get the real failure list

**Files:** none modified.

**This is the rung the last run skipped**, and its own notes call that the single thing that
made the run take as long as it did. It scoped repairs from whatever failures happened to be
reported instead of from a full-suite run, so files nobody had examined kept surfacing.

Budget roughly **two hours**. The suite has been measured at 1 h 48 m and it costs provider
money (it includes the live-provider shard and read-only cloud parity).

- [ ] **Step 1: Run the whole suite, logged so you can watch it**

Run:
```bash
make test 2>&1 | tee logs/task9-fullsuite.log | tail -60
```
Expected: `✓ Every definitive test shard passed.`

While it runs, read `logs/task9-fullsuite.log` for live progress. Do **not** poll a clock and
report "still running" — that is the visibility failure from last time.

- [ ] **Step 2: If anything fails, take the whole list before fixing anything**

Run:
```bash
grep -E "^(FAILED|ERROR)" logs/task9-fullsuite.log | tee logs/task9-failures.txt
```

Fix from **that** list, not from whatever you noticed first. Re-run the full suite after the
batch. 0 failed and 0 skipped is the bar — a skip is a failure in disguise, so diagnose it
rather than accepting it. No `--ignore`, no `-k` exclusion, no splitting a composite target.

**Watch for one known latent bug:** any module-scoped authenticated fixture can outlive its own
60-minute login token now that the suite is slower. `tests/test_trip_api.py` already had this
fixed by minting a fresh bearer per request. A `401 Invalid or expired token` where the test
expects something else is this bug, not a product fault.

### Task 10: Real-browser proof of the workbench

**Files:** none modified. Screenshots are the deliverable.

Code reading and unit tests are explicitly **not** sufficient for a user-facing claim. The
browser shard never ran in the last pass because it sits behind the failing Python shard.

- [ ] **Step 1: Run the browser shard in isolation**

Nothing else may touch containers while this runs — a sibling suite racing it on the shared
graph manufactures phantom failures, which is exactly what happened last time.

Run:
```bash
make test-workbench 2>&1 | tee logs/task10-workbench.log | tail -40
```
Expected: 66 passed. The previous best was 65 of 66, and that one failure was container
contention rather than a defect.

- [ ] **Step 2: Capture the two screenshots the close-out requires**

Capture, from a real browser run:
1. The three option cards in the new pick-then-build workbench flow (step 12's behaviour).
2. The degradation banner appearing **before any card is clickable** — this is acceptance
   criterion AC-21, and the ordering is the whole point of it.

The banner text must read exactly:

> Walking times between stops are estimates, not measured routes, so the tour may run a little
> longer or shorter than it says.

Report both screenshots to the user. A behaviour claim without a picture is not proof.

### Task 11: Phone proof on a simulator

**Files:** none modified. A screenshot is the deliverable.

The phone-side warning is currently proven only by a widget test that mounts the page and finds
the sentence — not by a device.

- [ ] **Step 1: Open the simulator panel before building**

Use the iOS Simulator control tool's `attach` action first, so the user can watch. It is cheap
and opens instantly on a booted device.

- [ ] **Step 2: Build and run the app**

Run:
```bash
make flutter-ios 2>&1 | tee logs/task11-ios.log | tail -40
```

- [ ] **Step 3: Generate a tour with routing stubbed down, and screenshot the warning card**

The warning must show the same sentence as Task 10, Step 2, verbatim. Report the screenshot.

### Task 12: The paid audit — exactly once

**Files:** none modified.

- [ ] **Step 1: Consult the judge first**

`make audit` spends real money and this is a phase transition. Consult the judge agent, state
that Tasks 8–11 are green with evidence, and paste its ruling.

- [ ] **Step 2: Run it once**

Run:
```bash
make audit 2>&1 | tee logs/task12-audit.log | tail -80
```
Expected: lint clean, then `✓ Every definitive test shard passed.`

**Once. Never inside a loop.** If it fails, fix the cause and consult the judge again before
re-running — a second audit is a second bill.

### Task 13: Read the diff, then merge

**Files:** none modified until the merge.

- [ ] **Step 1: Read the entire diff against the ledger**

Run:
```bash
git diff main...HEAD --stat | tee logs/task13-diff-stat.log
git diff main...HEAD > logs/task13-diff-full.log
```

Read `logs/task13-diff-full.log` in full. Every change must be intentional and traceable to a
ledger step. Check specifically for: no hardcoded colors (use `Theme.of(context).colorScheme.*`),
no fabricated field names or IDs, and no scaffolding left behind.

- [ ] **Step 2: Confirm no scratch files survive**

Run:
```bash
git status --short && ls scratchpad/ 2>/dev/null
```
Expected: clean tree; no scratch directory in the repo.

- [ ] **Step 3: Judge consult before the merge**

Merging to `main` is both a commit and a state-changing action. Consult the judge with the
audit result and the diff review. Paste the ruling.

- [ ] **Step 4: Merge**

Run:
```bash
git checkout main && git merge --no-ff unify-tour-algorithm-closeout
```

- [ ] **Step 5: Clean up**

Run:
```bash
git branch -d unify-tour-algorithm-closeout
git worktree list
docker network ls --filter name=ondoway --format '{{.Name}}'
```

Remove any `.claude/worktrees/agent-*` worktree, any `worktree-agent-*` branch, and any
orphaned network or volume the run created. **Name each resource before you remove it** and say
how you know it is not a sibling session's.

Verified 2026-08-05: no worktrees and no `worktree-agent-*` branches currently exist, so this is
expected to be a no-op. Confirm rather than assume.

---

## Phase 3 — Measure the slowdown, hand over the decision

### Task 14: Measure, then present the narration decision

**Files:**
- Create: `specs/2026-08-04-unify-tour-algorithm/NARRATION-DECISION.md`

**Do not fix the narration over-credit in this plan.** The owner chose to decide with numbers
in hand. Your job is to produce the numbers, not the fix.

**The mechanism, for your own understanding:** when deciding whether to seat another stop, the
planner credits that stop with up to the *whole tour's* narration allowance (720 s at 60
minutes). When the tour is spoken, every stop is capped at `MAX_DWELL_AUDIO_SECONDS` = 270 s. A
rich place is booked at up to five times what a tourist hears. The planner believes the
listening budget is full after about a third of the stops, the tour lands short, and the repair
pass closes the gap by reaching for distant stops. Measured across sixteen configurations from
30 to 120 minutes: inside the walking allowance before repair every time, over it after repair
every time, by 4% to 37%.

- [ ] **Step 1: Re-measure the four timing rows**

Run each and record wall-clock time:
```bash
time make test-file FILE="tests/test_trip_api.py" TEST_PROFILE=test2 2>&1 | tee logs/task14-tripapi.log | tail -5
time make test-file FILE="tests/test_tour_flavours.py" TEST_PROFILE=test2 2>&1 | tee logs/task14-flavours.log | tail -5
time make test-file FILE="tests/test_tour_b_materialization.py" TEST_PROFILE=test2 2>&1 | tee logs/task14-bmat.log | tail -5
```

The full Python shard figure comes from Task 9's log — do not re-run the suite for this.

- [ ] **Step 2: Fill in the comparison**

| | before the unification | after (last run) | now |
| --- | --- | --- | --- |
| full Python shard | ~15 min (899 s) | 1 h 48 m (6,509 s) | *measure* |
| `tests/test_trip_api.py` alone | — | 33 m 53 s | *measure* |
| `tests/test_tour_flavours.py` | < 2 s | ~4 m 30 s | *measure* |
| `tests/test_tour_b_materialization.py` | < 1 s | ~1 m | *measure* |

Phase 1 narrowed the fixed-end candidate pool from roughly 95 POIs to 47, so some improvement
is expected on any file exercising A→B. Report what actually happened, including "no change".

- [ ] **Step 3: Write the decision document**

Create `specs/2026-08-04-unify-tour-algorithm/NARRATION-DECISION.md` containing:

1. The measured table from Step 2.
2. Whether the A→B fix moved the timings at all, stated plainly.
3. The three options, in plain English: fix the arithmetic (tours change shape, reference tours
   move, needs a human to accept a diff); leave it (tours keep somewhat less talking and more
   walking than designed); or attack the slowdown some other way.
4. Your recommendation with its reason.

**Write it for someone who has never opened this repo.** No identifiers as sentence subjects.

- [ ] **Step 4: Present it and stop**

Post the summary to the user and **end the turn**. This decision is the owner's. If they choose
the fix, that is a new plan with its own re-baselining step — the golden tours **will** move,
and they must be reviewed and accepted by a human rather than auto-updated.

---

## Deliberately out of scope

- **The narration over-credit fix.** Owner's decision, Task 14 produces the input.
- **`make format` taking a `FILE=` argument.** A real Makefile gap — the repo has a formatter
  no gate enforces and nobody can safely run — but the previous session ruled it outside this
  work and that still holds. Worth its own small ledger later.
- **The two extra test databases** (`neo4j-test2` :7690, `neo4j-test3` :7691). Already decided:
  they stay. They were used simultaneously during the last run to stop parallel lanes wiping
  each other's fixtures, and this plan uses `TEST_PROFILE=test2` throughout for the same reason.

## The one-time cost to expect after deploy

Stop audio now carries a content fingerprint so edited words get re-voiced. Existing stops have
no fingerprint, so the first non-forced run after deploy re-voices every existing stop once.
This is deliberate: treating "no fingerprint" as "still fresh" would silently recreate the
staleness bug the fingerprint removes.
