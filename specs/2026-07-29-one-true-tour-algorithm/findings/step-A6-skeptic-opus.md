# Step A6 — hostile skeptic (opus), angle: NEGATIVE SPACE — ROUND 2

Stamped against base commit `c8ec3969` (`main`) with the A6 change-set in the
working tree. Index state re-derived by hand this round: the 4 track files and
the 3 test files are staged-deleted, `tests/conftest.py` is staged-modified
(`M `), `tests/test_tour_one_engine.py` is staged-added (`A `).

Ran concurrently with 2 sibling skeptics. The only command I executed against
shared state was `make lint` (pure ruff). Everything else is read-only
`git show` / `git ls-files` / `grep` / file reading. Two proposed reproductions
are marked PROPOSED and were NOT run.

This supersedes the round-1 opus write-up at this path. Round 1's two blocking
findings are re-verified below as FIXED; the file is replaced rather than kept,
per the cleanup ruling.

## Verdict

The deletion holds. I could not break it: there is no surviving entry point of
any kind — import, dynamic import, Makefile shard, skill, docs command, API
`engine=` selector, frontend toggle — that reaches the deleted track. What is
still untested is not the deletion; it is (a) the index/worktree split the gate
reads from, which is the exact hole that produced round 1's blocker and which
still has no check, and (b) the fact that the money-guard assertion proves the
guard's SOURCE, never its APPLICATION.

## Round-1 findings: both FIXED, re-derived

- **R1-F1 (index skew — the committable tree could not collect).** FIXED.
  `git show :tests/conftest.py` now contains no `src.tour.author` /
  `src.tour.tour_consistency` import (grep exit 1), and `git ls-files` lists
  `tests/test_tour_one_engine.py`. The tree `git commit` would write is
  internally consistent.
- **R1-F2 (money-guard clause was a substring check).** FIXED, and fixed
  properly: `_money_guard_armed_pairs` (`tests/test_tour_one_engine.py:131-181`)
  now parses `monkeypatch.setattr` CALLS out of the fixture body, resolves the
  module alias through the fixture's own `import ... as`, expands the
  `for _judge_name in (...)` loop, and compares for EQUALITY against nine pairs.
  Deleting the arming line at `tests/conftest.py:209` now drifts the set and goes
  RED. The developer's PROOF 2 is a fair demonstration of that.

## F1 (MEDIUM, UNPROVEN — repro proposed, index-mutating) — the gate reads file existence from the INDEX and conftest from the WORKTREE, so the round-1 blocker has no recurrence guard

`test_author_engine_track_is_gone` mixes two different sources of truth:

- clause 1 (`:187-191`) reads `git ls-files` — the **index**;
- clause 3 (`:210`) reads `(REPO_ROOT / "tests" / "conftest.py").read_text()` —
  the **worktree**.

So the gate is green whenever the worktree conftest is correct, regardless of
what the index holds. Round 1 proved that is not hypothetical: the step landed
in exactly that state (worktree conftest fixed, index conftest still importing
the deleted modules), which would have committed a Python shard that cannot
collect a single non-live test. The repair was a manual `git add`. **No check
was added.** A7, A8 and A9 each edit `tests/conftest.py` again, and each of
their gates is `make lint` alone plus a node id built the same way — the same
skew re-arms with nothing to catch it before the paid close gate.

Cheapest durable fix: have clause 3 read conftest from the index
(`git show :tests/conftest.py`), or assert index==worktree for every file in the
step's scope. Either is a few lines in the same helper style the file already
uses.

PROPOSED repro (serial verifier ONLY, never while a sibling holds the repo;
restore immediately):
`git restore --staged tests/conftest.py && make test-file FILE="tests/test_tour_one_engine.py::test_author_engine_track_is_gone" ; git add tests/conftest.py`
Expected: **PASS** while the indexed conftest is the HEAD version that imports
two deleted modules. I did not run it — it mutates the shared index.

## F2 (LOW, UNPROVEN — repro proposed) — the money-guard check proves the fixture's SOURCE, not that it RUNS

`_money_guard_armed_pairs` takes the `FunctionDef` and walks its body. It never
looks at `fixture.decorator_list`, and it cannot see control flow. Therefore all
nine arms can be fully disarmed with A6's node id still GREEN by:

- deleting `autouse=True` at `tests/conftest.py:67` (one token — no test names
  this fixture, so it simply stops running), or
- inserting an early `return` at the top of the fixture body (every
  `monkeypatch.setattr` call stays in the AST).

This is the same class of hole as round-1's F2, one level up: the fix moved from
"does the text mention it" to "is the call written", but never reached "does the
guard take effect". It matters because `src/api/dependencies.py:201` still
constructs `factcheck.HaikuCoverageJudge()` for real on the product path.

Compensating control — I checked, and it is real:
`tests/test_trips_spend_and_authz.py:233 test_product_authoring_factory_is_offline_in_the_non_live_suite`
constructs the product factory and asserts it returns `OfflinePremiumExecutor`.
It is a RUNTIME assertion, it is not on any Track A deletion list, and it goes
RED the moment the autouse fixture stops running. That is why this is LOW, not a
blocker. Note that the other three runtime pins
(`test_compose_provider.py`, `test_compose_omission_detection.py`,
`test_compose_corrector_optin.py`) are all deleted at A8/A9, so after A9 that
single test is the whole runtime money-guard bar.

PROPOSED repro (serial verifier): delete `autouse=True` from
`tests/conftest.py:67`, run
`make test-file FILE="tests/test_tour_one_engine.py::test_author_engine_track_is_gone"`.
Expected: **PASS** with every money guard off. Restore the token afterwards.

## F3 (LOW, verified read-only) — A6 deleted the only runtime pin for two money-guard arms that SURVIVE

`git show HEAD:tests/test_author.py` :58-73 held
`test_money_guard_author_engine_clients_are_offline_stubs_in_suite`, the only
test asserting that `HaikuClaimDecomposer()` and `HaikuFaithfulnessJudge()`
construct as offline stubs on the `client=None` path. A6 deleted that file while
keeping both arms in conftest (they are rows 7 and 9 of
`EXPECTED_MONEY_GUARD_ARMS`). After A6, the only runtime pin over the factcheck
trio covers `HaikuCoverageJudge` alone
(`tests/test_compose_omission_detection.py:43`), and that file dies at A8.

Live spend risk today: none that I can find. Nothing under `src/` constructs the
decomposer or the faithfulness judge — `dependencies.py:201`'s
`factcheck.HaikuCoverageJudge()` is the only product construction in the tree.
So this is latent coverage loss on two arms that are themselves dead until A8
deletes `factcheck.py`. Recording it because A6's node id asserts those two arms
must REMAIN, while nothing any longer proves they WORK.

## F4 (LOW, documentary) — "satisfies AC-1, AC-9" is false, and the repo already says so

The claim handed to this panel says A6 "satisfies AC-1, AC-9". The gate file's
own docstring (`tests/test_tour_one_engine.py:25`) says "A6 GREEN IS NOT
AC-1/AC-9 MET", and `state.json`'s carry-forward CF-4 enumerates 9 of AC-1's 13
paths and 5 AC-9 clauses as having no executable check anywhere on the tree.
A6 discharges its slice — 4 deletions plus 2 money-guard arms. Nothing in the
code is wrong here; the sentence is. It must not be recorded as closing either
criterion.

## F5 (LOW, advisory, design-wide) — proving a pure-filesystem assertion boots three containers and re-seeds the shared dev graph

`test_author_engine_track_is_gone` touches no database. Its pinned gate command
does: `Makefile:147-151` runs `_ensure-test-db`, `_ensure-dev-data`
(writes the shared 7687 DEV graph), `valhalla-up`, and
`find tests src -name __pycache__ -exec rm -rf {} +` before pytest. So the
cheapest rung of the ladder cannot run at all if Valhalla is half-started, and
running it beside a sibling session's suite both re-seeds their graph and rips
`__pycache__` out from under their interpreter. Inherited from the Makefile, not
introduced by A6, and already written down in CLAUDE.md — restated because this
step's whole proof rides on it.

## Attacks that FAILED to break the claim

- **Any surviving reference, by any mechanism.** Word-boundary grep across the
  whole repo minus `specs/` and `Docs/` for `author_tour`, `content_budget`,
  `tour_consistency`, `src.tour.author`, `LLMDrafter`, `HaikuCrossStopJudge`
  returns exactly three files: `tests/conftest.py` (a historical comment),
  `tests/test_tour_authoring_extraction.py` (the A6 allowlist row) and the gate
  test's own constants. Zero import edges, zero call sites.
- **A different entry point.** No `Makefile` target, no `LIVE_TEST_FILES` /
  `GOLDEN_TEST_FILES` / `GRADE_TEST_FILES` / `INVARIANT_TEST_FILES` row, no
  `.claude/commands/*.md` skill, no `pyproject` script or per-file ignore, no
  `render.yaml` entry names any deleted file. There is no `engine="author"`
  selector anywhere in `src/`, `frontend/` or `mobile/lib` — the author track
  really had no product surface.
- **Python outside the AST scan's roots.** `git ls-files "*.py"` outside
  `src/ tests/ scripts/ tools/` returns nothing, and there is no top-level
  `*.py`. The four scanned roots are the whole Python tree today.
- **Collateral damage to the A1 gate.** `test_remaining_compose_importers_are_pinned`
  only applies its lower bound to the three PINNED importers, so
  `scripts/author_tour.py` vanishing from the importer set cannot fail it; and
  `test_later_step_allowlist_matches_the_ledger` still finds
  `scripts/author_tour.py` inside A6's `files` in `state.json`. Both remain
  satisfiable after the deletion.
- **Conftest blast radius.** The diff is surgical: only the author and
  cross-stop arms are removed, plus a comment rewrite of the factcheck arm
  header. The premium-executor + faithfulness arm (:117-135) is outside every
  hunk, so AC-9's byte-untouched clause holds today even though CF-4 correctly
  notes nothing asserts it. `_OfflineDecomposer` / `_TrustingJudge`, still used
  by the surviving arms, were kept. No test imports a name from
  `tests.conftest` that A6 removed.
- **`make lint`** — re-ran it myself: exit 0, `All checks passed!`, over the
  same file list the run-context pins. (Noted: three scripts this ledger has
  already modified — `tour_batch_review.py`, `tour_text_candidate.py`,
  `tour_text_candidate_review.py` — are outside lint's scope. They are covered
  by pytest at the phase gate, so this is a gate-scope remark, not a defect.)
- **Stale `__pycache__` resurrection.** Python cannot import a deleted module
  from a leftover `__pycache__/*.pyc` (no sourceless fallback since PEP 3147),
  and `make test-file` deletes those caches anyway.
- **Docs left pointing at a deleted script.** `specs/2026-07-18-tour-qa-campaign/`
  (`PHASE-C-RESULTS.md:3,185`, `BASELINE-TABLE.md:3`) still cites
  `scripts/author_tour.py` as the tool that produced its numbers. AC-10 only
  deletes the two 2026-07-26 folders. Historical-record prose about a past run,
  not an instruction, so I am not calling it a finding — but it is the shape of
  thing the cleanup ruling targets.
