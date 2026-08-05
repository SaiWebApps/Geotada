# Step 2 skeptic review (fix correctness) — Sonnet 5, re-run

Verified against commit `a7df218c` (HEAD) with the step's own diff still uncommitted in
the working tree (`git status`: `M src/tour/premium_tour.py`,
`M tests/test_premium_workbench_wiring.py`). A stale copy of this same file already
existed at this path from an earlier pass (timestamped 15:53 today); I did not trust it
— I re-derived every claim below myself, and one of its findings (Finding 2, "only one
of the two refusal branches is tested") turned out to be **factually wrong against the
current working tree**: the test file now covers both branches. That is exactly the
failure mode this protocol exists to catch, so I am not carrying that finding forward.

Read-only checks: `git diff`, `git show`, `grep`, `Read`, plus two live commands I ran
myself because they are safe (pure ruff, and a hermetic pytest probe against a throwaway
file in the scratchpad — no repo file touched, no DB, no container). I did not touch
`git stash`, any DB, container, or `make test-file` against the real repo — those are
shared state and a sibling skeptic is running concurrently.

## Verdict: UNPROVEN as literally stated ("step 2 satisfies AC-1") — the code itself is
CONFIRMED correct and the pinned test is CONFIRMED non-strawman; the overclaim is scope,
not a code defect.

## What I independently re-derived

1. Read the full diff of `src/tour/premium_tour.py` and
   `tests/test_premium_workbench_wiring.py` (`git diff HEAD -- <file>`).
2. Traced `plan_premium_authoring`'s two `ValueError` checks back to
   `authoring.py:875-884` (`plan_prebuilt_route_authoring`) line by line — the guard
   conditions, the raise messages, and the surrounding candidate/unit construction are a
   verbatim port, not a rewrite.
3. Confirmed the stop-count guard `AUTHORING_MAX_STOPS` (1-15) is not silently dropped:
   it still fires inside the shared, **unmodified** `_certification_compose_requests`
   helper (`authoring.py:501`, `git diff HEAD -- src/tour/authoring.py` is empty), which
   both the old inline code and the new function call identically.
4. Confirmed `tour_input=source.inputs` (new) is behaviorally identical to the old
   explicit `tour_input=tour_input` parameter for the only current caller
   (`plan_premium_tour`): `generate()` sets `Script.inputs = tour_input` verbatim at
   `src/tour/generation.py:424` (read directly), matching the new docstring's own
   citation.
5. Confirmed `route_summary(route)["route_sha256"]` (new call site, moved unchanged)
   uses the identical canonicalization as `authoring.py`'s
   `prebuilt_route_sha256` (`json.dumps(..., sort_keys=True, separators=(",", ":"),
   ensure_ascii=False, allow_nan=False)` in both) — no hash drift between the two
   parallel implementations for the same route.
6. Read the pinned test's two `pytest.raises` blocks (lines 456-467) and their fixture
   helpers `_renumber_stop`/`_drop_stop` (lines 385-415) directly. Both refusal branches
   ARE exercised, each with a fixture shaped to hit only that branch (`_renumber_stop`
   keeps the script the same LENGTH as the route so it trips the out-of-range check, not
   the count check; `_drop_stop` removes a stop's sentences entirely so it trips the
   count check). The docstring's own justification for the second check — "a missing
   TAIL stop passes every other bar: in order, starts at 0, highest index in range" — is
   correct and is exactly what `_drop_stop(stitched, len(route.pois) - 1)` constructs.
   Neither fixture is a strawman; both trace to a documented real production path
   (`_renumber_stop`'s docstring cites `authoring.py`'s `_certification_compose_requests`
   never range-checking stop indices against `route.pois`, which I confirmed by reading
   that function).
7. Independently attacked the "one construction site" AST check (lines 469-484): it
   walks every `FunctionDef` in the module, including nested ones, and for each collects
   `PremiumComposeUnit(...)` calls anywhere in its subtree. A re-inlined loop inside
   `plan_premium_tour` (nested or not) would add a second name to `builders` and fail the
   `builders == {"plan_premium_authoring"}` assertion. I could not construct a
   plausible edit that dodges it without literally moving the construction into a
   separate module (which is a repo-wide AC-1 question already owned by step 4, not
   something this test needs to catch).
8. **Ran `make lint` myself**: exit 0, "All checks passed!" over `src/ tests/
   scripts/{9 files}` — matches the reported evidence exactly.
9. **Independently reproduced the mutation's exit code**, which the evidence packet
   asserts but I had reason to doubt at first. I built a hermetic throwaway pytest probe
   in the scratchpad (a one-file module with a bad import, touching no repo file, DB, or
   container) and ran it two ways:
   - Bare file path (`pytest test_bad_import.py`) → **exit 2** (`ExitCode.INTERRUPTED`),
     which I confirmed by reading `_pytest/main.py`'s `wrap_session`: `Session.Interrupted`
     subclasses `KeyboardInterrupt`, not `Failed`, so a collection-error interruption maps
     to exit 2, not 4. This did NOT match the evidence packet's claimed "exit_code: 4."
   - **Node-id selector** (`pytest test_bad_import.py::test_never_runs`, matching the
     exact shape of the pinned command, which selects a specific test function) →
     **exit 4** (`ExitCode.USAGE_ERROR`), with `ERROR: found no collectors for
     ...::test_never_runs` plus the identical `ImportError while importing test
     module ... collected 0 items / 1 error` shape reported in the evidence.
   The second run is the one that matches the real pinned command
   (`FILE="tests/....py::test_plan_premium_tour_builds_its_units_through_the_shared_prebuilt_seam"`),
   and it reproduces the claimed exit code and output shape exactly. I also confirmed
   `scripts/dev_env.py`'s `execute()` uses `os.execvpe`, which replaces the process image
   and cannot alter a child's exit code, so `make test-file`'s reported code is pytest's
   raw code with no Makefile-level transformation. **This is a genuine, code-level
   reproduction of the claimed mutation evidence, not a restatement of the pasted text.**

## Finding 1 — the literal claim "step 2 satisfies AC-1" is an overclaim of scope, not a
code defect

AC-1 (verbatim, `run-context.md`): "...and no second implementation of either exists."

`src/tour/authoring.py` is untouched by this diff (`git diff HEAD --stat -- src/tour/authoring.py`
is empty) and still defines and exports the full parallel implementation AC-1's negative
clause forbids: `PrebuiltRouteComposeUnit`, `PrebuiltRouteAuthoringPlan`,
`PrebuiltRouteExecutor`, `prebuilt_route_sha256`, `plan_prebuilt_route_authoring`,
`author_prebuilt_route`, `AUTHORING_MAX_STOPS` in `__all__` — all confirmed present by
`grep` against the file at HEAD-plus-working-tree.

This is not a surprise the ledger itself is hiding: `state.json`'s step table maps AC-1 to
**four** steps — 2, 4, 7, 11 — and step 4's own name is "Delete the second authoring seam
and re-point every test that imported it." AC-11, the criterion that specifically demands
`PrebuiltRoute*` return zero hits repo-wide, belongs to step 4 alone, not step 2. So the
plan's own design is cumulative and step 2 building the new seam while the old one still
exists is expected, not a slip.

**Rule: REFUTED** for the literal claim "step 2 satisfies AC-1" if that is being read as
"AC-1 is now fully true." **CONFIRMED** for the narrower, accurate claim: "step 2
correctly and faithfully lifts the prebuilt-route plan construction into
`premium_tour.py` as a shared builder, proven by a pinned test that is not a strawman."
If step 2 is being tracked as "1 of 4 steps toward AC-1, this step's own scope proven,"
the evidence fully supports that framing.

## Attacks tried against the lifted code itself (all failed — CONFIRMED)

- Stop-cap silently dropped? No — still enforced by the unchanged shared helper both
  builders call.
- `tour_input=source.inputs` a hidden behavior change? No — proven equivalent for the
  only reachable caller via a direct read of `generation.py:424`.
- `route_summary` recomputation hash drift vs. the old `prebuilt_route_sha256`? No —
  identical canonicalization, confirmed by reading both functions.
- Re-inlined `PremiumComposeUnit(...)` construction slipping past the "one site" check?
  No — the AST walk covers nested function bodies too.
- Strawman refusal tests? No — both `ValueError` branches are exercised by fixtures
  that are individually targeted to trip exactly one branch each, and the docstring's
  justification for the second branch matches what its fixture actually constructs.
- Evidence-chain exit code (4) for the undo-test fabricated or mismatched? No — I
  reproduced it myself from first principles (pytest source + a hermetic probe matching
  the exact node-id command shape), independent of the pasted transcript.

## Not independently reproduced against the real repo (proposed for the serial verifier)

I did not run `make test-file` against this repo's actual files since it starts the
shared 7688/7687 containers and Valhalla, and a sibling skeptic runs concurrently. My
own hermetic probe (item 9 above) reproduces the *mechanism* (pytest's exit-code
behavior for a node-id-selected import failure) but not this repo's specific test file
or fixtures.

- `make test-file FILE="tests/test_premium_workbench_wiring.py::test_plan_premium_tour_builds_its_units_through_the_shared_prebuilt_seam"`
  — expect PASS (green), given the diff and test content I read directly.

## Bottom line for the parent orchestrator

The code in `src/tour/premium_tour.py` is a correct, faithful lift; I attacked it from
several angles (stop-cap, hash equivalence, re-inline evasion, tour_input substitution,
strawman-test suspicion, evidence-chain exit-code suspicion) and it held up under every
one, including an independent from-scratch reproduction of the mutation's exit code
rather than trusting the pasted transcript. The only real defect is in the CLAIM's
wording: "step 2 satisfies AC-1" should read "step 2 (of 2/4/7/11) toward AC-1 — this
step's own scope proven; the repo-wide 'no second implementation' clause remains false
until step 4 deletes `authoring.py`'s `PrebuiltRoute*` family." That is a tracking/
reporting fix, not rework.
