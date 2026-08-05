# Step 2 hostile review — negative space

**Verified against:** HEAD `a7df218c0ce3ca28df2e31df895f80e5ea3a7ef5`, plus the
uncommitted step-2 working tree:
`src/tour/premium_tour.py` blob `4b2ef76ad2af70e3a3e1dbbfb4fd555521b83216`,
`tests/test_premium_workbench_wiring.py` blob `47fef6e389bd7ca3844639c4b8b2ab39f9d59ffd`.
Reviewer angle: NEGATIVE SPACE. Ran `make lint` myself (exit 0). Everything
container-touching is PROPOSED, never executed — a sibling skeptic is running
concurrently.

**Verdict: the code change and its test survive attack. The claim attached to
them — "satisfies AC-1" — does not.**

---

## F1 (REFUTED claim, medium) — AC-1 is not satisfied; a second Block-2 seam is still live

AC-1 requires "no second implementation of either exists". A byte-for-byte
sibling of the new `plan_premium_authoring` is still in the tree and still on
the live persisted-compose route:

```
$ grep -rn "author_prebuilt_route\|plan_prebuilt_route_authoring" src/api/routes/trips.py src/tour/authoring.py
src/api/routes/trips.py:42:from src.tour.authoring import author_prebuilt_route, plan_prebuilt_route_authoring
src/api/routes/trips.py:615:        plan = plan_prebuilt_route_authoring(
src/api/routes/trips.py:631:            composed = author_prebuilt_route(
src/tour/authoring.py:857:def plan_prebuilt_route_authoring(
src/tour/authoring.py:934:def author_prebuilt_route(
```

`authoring.py:872-884` holds the same two `ValueError` guards, comment text
included, that step 2 added to `premium_tour.py:255-266`. So step 2 did not
unify two builders; it created a third copy of one and pointed only the preview
planner at it. The other copy still authors every persisted trip.

AC-1 also opens with "Given the repository **at the end of this slice**" and
covers a second clause step 2 never touches (exactly one callable produces the
K=3 route options). The ledger assigns AC-1 to step 2 *and* step 4; only step 4
deletes the duplicate. The honest step-2 statement is "advances AC-1", not
"satisfies AC-1".

## F2 (medium) — the "one construction site" assertion only sees one module

`tests/test_premium_workbench_wiring.py:470` parses
`inspect.getsource(premium_tour)`. A `PremiumComposeUnit` built anywhere else —
`src/api/routes/trips.py`, a new `src/tour` module, a helper — leaves
`builders == {"plan_premium_authoring"}` GREEN. That is exactly the duplication
AC-1 forbids, and it is exactly what step 3 (which edits `trips.py`) is at risk
of. Two test files already construct the dataclasses by hand
(`tests/test_never_silent_failures.py:197,208`,
`tests/test_tour_authoring_gates.py:672,683`), so a repo-wide scope is not free —
but the guard should walk `src/` and allow the one function, not walk one module.

## F3 (medium, forward hazard) — `stops[-1]` is only safe because of a guard this same ledger deletes

New code, `src/tour/premium_tour.py:253-255`:

```python
_beats_by_id, stops, requests = _certification_compose_requests(source, beat_sequence, route)
if stops[-1] >= len(route.pois):
```

`stops` is non-empty today only because `_certification_compose_requests`
(`src/tour/authoring.py:501`) raises first:

```python
if not 1 <= len(stops) <= AUTHORING_MAX_STOPS:
    raise ValueError("authoring supports one to fifteen stops")
```

AC-15 orders that whole guard removed, and step 5.5 owns it
(`files: src/tour/authoring.py`, `criterion_ids: [AC-15, AC-16]`). With the
lower bound gone, an empty stitched script reaches `stops[-1]` and raises
**IndexError**. `src/api/routes/trips.py:951-963` catches
`TourabilityRefusedError`, `CertificationPlanningInfeasibleError`,
`PremiumRouteInfeasibleError` and bare `ValueError` — not `IndexError` — so the
workbench preview turns a structured 422 into an unhandled 500. Step 2's own
test cannot bind this: every fixture it builds has stops. Remedy is one line —
`if not stops or stops[-1] >= len(route.pois)` — and one assertion.

## F4 (low, structural) — AC-9 cannot be met by re-pointing the seam guard at premium_tour.py

AC-9 requires the AUTHOR block to import no planning module and name no planning
entry point. The locked decision puts the AUTHOR block in `premium_tour.py`, and
step 2 now puts the Block-2 *plan builder* there too. Measured with `ast` on the
current file:

```
planning MODULES imported by premium_tour.py: ['beat_select', 'routing', 'routing_client', 'selection']
planning CALLS made by premium_tour.py:       ['certification_planning_policy', 'choose_discrete_route', 'generate', 'select_k_routes']
```

`tests/test_tour_authoring_from_route.py` pins `_SEAM_PATH =
src/tour/authoring.py` and asserts both sets are empty. Step 4 lists that file
for editing; if it simply re-points `_SEAM_PATH` at `premium_tour.py` the test
goes red on four modules and four calls. Step 4 must narrow the guard to the
AUTHOR functions' own call graph (`execute_premium_plan`,
`finalize_premium_tour`), and say so, or AC-9 fails on a technicality. Note also
that `authoring.py:864-870` documents the leaf placement as deliberate
("importing it back into this leaf would close an import cycle"); step 2 inverts
that layering, which is legitimate under the locked decision but should be
recorded, not silent.

## F5 (low) — the delegation itself is bound only by a substring

The only assertion about `plan_premium_tour` is
`assert "plan_premium_authoring(" in inspect.getsource(premium_tour.plan_premium_tour)`
(`:484`). The call is positional — `plan_premium_authoring(source, sequence, route, ...)`
against `def plan_premium_authoring(source, beat_sequence, route, ...)`. Swap
`sequence` and `route` and both the pinned node id and `make lint` stay green;
the break surfaces only in `make test-workbench`, the one shard this ledger
bans from per-step gates. The step's gate list is `make lint` alone, and nothing
in it executes `plan_premium_tour`.

---

## Attacks that FAILED (the confirmation half)

1. **"The two new refusals break the live preview."** They are new to
   `plan_premium_tour`. Traced `src/tour/generation.py:352-390`: stop 0 always
   gets a cold open (synthesized fallback), every stop_idx > 0 always gets at
   least one sentence from `_build_transit` (a corpus transit beat, a glue nav
   line, or the graceful-arrival line for a beatless fixed-end sentinel), and
   both dedup passes (`src/tour/claim_dedup.py:256,316`) skip anything whose
   `source_type != "beat"` and never empty a beat. `build_poi_beat_plans`
   (`selection.py:1107-1111`) emits one plan per route POI, beatless ones
   included. So `len(stops) == len(route.pois)` holds and the guard cannot fire.
   Could not break it.
2. **"`tour_input=source.inputs` is not the old `tour_input`."**
   `generate()` writes `inputs=tour_input` verbatim (`generation.py:421`) and
   only `model_copy(update={"validation": ...})` after. Identical. Could not
   break it.
3. **"The plan fingerprint moved."** `route_summary`'s `route_sha256`
   (`premium_tour.py:146`) and the old `prebuilt_route_sha256`
   (`authoring.py:844-853`) are both sha256 over `route.model_dump(mode="json")`
   with `sort_keys=True, separators=(",",":"), ensure_ascii=False,
   allow_nan=False`. Byte-identical. Could not break it.
4. **"Empty `stops` crashes today."** Blocked by `authoring.py:501` today; see
   F3 for when that stops being true.
5. **"An existing test was weakened to fit."** `git diff --numstat` on
   `tests/test_premium_workbench_wiring.py` = **227 added, 0 deleted**. No
   existing assertion touched.
6. **"The new ValueError escapes as a 500."** `trips.py:955-963` catches bare
   `ValueError` and returns 422. Could not break it.
7. **"The two guards are one guard wearing two hats."** They are distinctly
   bound: `_renumber_stop` yields `stops=[0,1,2,7]` (length 4, top index out of
   range → first guard only); `_drop_stop` yields `stops=[0,1,2]` (top index in
   range, length short → second guard only). The docstring's undo-test table is
   accurate.
8. **`make lint` re-run by me**: exit 0, "All checks passed!" over
   `src/ tests/ scripts/{9 files}`. AC-28 evidence re-derived.
