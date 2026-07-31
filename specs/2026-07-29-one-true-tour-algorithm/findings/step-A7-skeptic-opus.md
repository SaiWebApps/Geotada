# Step A7 — hostile skeptic (opus), angle: NEGATIVE SPACE

**Verified against:** `c8ec3969` (main) + the uncommitted A7 working tree
(staged deletion of the 5 scoreboard files, unstaged docstring edit in
`src/tour/narration_quality.py`). Read-only except `make lint`.

**Claim under attack:** A7 ("DELETE the compose scoreboard … craft_score …")
satisfies AC-1, proven by
`make test-file FILE="tests/test_tour_one_engine.py::test_compose_scoreboard_is_gone"`
plus a QA mutation verdict of REAL.

**Verdict: the 5-file deletion is real and I could not break it. The step as
NAMED is not done, and the piece it dropped (`craft_score`) is now owned by no
step in the ledger.**

---

## What I ran myself (the only shared-state-safe command)

- `make lint` -> exit 0, `All checks passed!` (re-derived, not taken on faith).

Everything else below is read-only `git show` / `git ls-files` / `ast` analysis
of the working tree; nothing touched 7687/7688/7689, Valhalla or :8001.

## Attacks that FAILED to break the deletion

1. **Whole-repo reference sweep (all file types, not just `*.py`)** for
   `compose_metrics`, `compose_snapshot`, `report-tour-issue`, `craft_score`,
   `test_compose_quality_eval`, `test_compose_metrics`. Live-tree hits are only:
   historical `Docs/bug-reports/*` and superseded `specs/*` (A10 deletes two of
   those folders), the two deliberate pin tables, and `craft_score`, which still
   exists. **No `Makefile` target, no `LIVE_TEST_FILES` entry, no `pyproject`
   entry, no `.claude/commands/*` and no `frontend/` reference points at a
   deleted path.** The "different entry point" attack found no entry point.
2. **Repo-wide AST import scan** (every `*.py` in the tree, deliberately WIDER
   than the test's `SCANNED_ROOTS = src/scripts/tests/tools`) for
   `src.tour.compose_metrics` / `tools.compose_snapshot`: zero hits in the live
   tree. `git ls-files '*.py'` confirms there are no tracked Python files
   outside those four roots, so the test's narrower scan is not hiding an
   importer.
3. **Smuggling attack** — a path-pinned deletion test passes if the code merely
   MOVES. I grepped every public symbol of the deleted module
   (`ComposeMetrics`, `compute_compose_metrics`, `quality_violations`,
   `metric_regressions`) across `src/ tests/ scripts/ tools/ frontend/ Makefile`:
   zero hits. The capability is gone, not relocated.
4. **D6's ordering premise** ("before its `compose_gate` imports die") is real
   and now consistent: the deleted `compose_metrics.py:43` was
   `from .compose_gate import _bad_stops`; `compose_gate.py` still defines
   `_bad_stops` at :88 and uses it at :111, so nothing dangles and no unused
   private helper appears (lint agrees).
5. **Collateral on an EARLIER step's gate.** A7 deletes two files that A1's
   `tests/test_tour_authoring_extraction.py` names in
   `COMPOSE_IMPORTERS_DELETED_BY_A_LATER_STEP`. That test does NOT require the
   twelve to still be importers (its lower bound covers only
   `PINNED_COMPOSE_IMPORTERS`, the three), and
   `test_later_step_allowlist_matches_the_ledger` requires each name to appear
   in the owning step's `files` — A7's `files` lists both. So A7 does not turn
   A1 red *by reading*. Nobody re-ran it; see "proposed verifications".
6. **Collection blast radius.** `pyproject`'s `testpaths = ["tests"]` means the
   gitignored worktree copies (finding 3) are not collected; no orphan fixture
   directory was left behind — the deleted eval's fixtures were inline module
   constants.
7. **AC-1's literal predicate right now:** `git ls-files --` for all five paths
   returns empty. They are absent from the index, not merely from disk.

## Findings

### F1 (medium) — `craft_score` is now orphaned and NO step may delete it

A7's own name and `files` scope promise craft_score's deletion, and D9's
consented loss (5) is "the compose-metrics scoreboard **+ craft_score**". The
developer deferred it (documented in a docstring) because `src/tour/compose.py:84`
still imports it and compose.py dies at A8. That reasoning is correct — but:

    A1 ... A6: narration_quality.py in files: []
    A7  in_progress | ['src/tour/narration_quality.py', 'tests/test_narration_quality.py']
    A8, A9, A10: narration_quality.py in files: []

**A7 is the only step in the whole ledger scoped to `narration_quality.py`.**
Under the engine's file-scope rule, A8's developer may not touch it. So after A8
deletes `compose.py` (craft_score's last production caller — `compose.py:84`,
`:1055`), `craft_score` and its six tests in `tests/test_narration_quality.py`
survive Track A as dead code that lint cannot flag (exported in `__all__`, tested).
D9 loss (5) goes unfulfilled and the ledger contains no `carry_forward` entry
recording it — CF-1..CF-4 mention neither `craft_score` nor `narration_quality`.
The only record is an **unstaged** docstring edit that attributes the situation
to step A6, not A7.

This does not refute "AC-1 is satisfied" (AC-1 never names craft_score); it
refutes "the step is done as written". Fix is cheap: add a carry-forward, or add
`src/tour/narration_quality.py` + `tests/test_narration_quality.py` to A8's
`files`.

### F2 (low) — the undo-test drove only one of the test's two clauses

`test_compose_scoreboard_is_gone` asserts (a) not on disk, then (b) not in
`git ls-files`. AC-1's literal wording is (b). The QA mutation
(`git checkout HEAD -- …`) restores both index and worktree, so assertion (a)
fires first and (b) was never observed red. The realistic human error — `rm`
without `git rm`, leaving the path staged — is exactly what (b) exists to catch.
Proposed mutation (serial verifier only, restore afterwards):
`git checkout HEAD -- src/tour/compose_metrics.py && rm src/tour/compose_metrics.py && make test-file FILE="tests/test_tour_one_engine.py::test_compose_scoreboard_is_gone"`
expected: RED on "…are still tracked by git; `git rm` them."
then `git rm -q --cached src/tour/compose_metrics.py` to restore.

### F3 (low) — a live sibling worktree still holds every "deleted" file

`git worktree list` shows
`/Users/sairambkrishnan/git/ondoway/.claude/worktrees/ecstatic-hawking-d4f171`
detached at `b542af0b`. It contains working copies of all five deleted files,
including `tools/compose_snapshot.py`, whose `__main__` prints
`ONDOWAY_…=1 python -m tools.compose_snapshot --live` — a live-spend path the
ledger claims is gone. It is gitignored (`.gitignore:253 .claude/*`), outside
`testpaths`, and outside the test's `SCANNED_ROOTS`, so it cannot make the gate
lie. But "deleted" is tree-local: an agent grepping this repo still finds the
scoreboard, and the worktree-cleanup rule in CLAUDE.md says it should not be
sitting there. Do not remove it blind — it may belong to a concurrent session.

### F4 (low) — `tools/` is now an empty package plus stale bytecode

`git ls-files tools/` -> `tools/__init__.py` only. `tools/__pycache__/` still
holds `compose_snapshot` bytecode; `make test-file`'s cache purge is
`find tests src -name __pycache__`, so `tools/` is never cleared. Not
importable without the source (PEP 3147), so not exploitable — but it is
scaffolding the pre-commit checklist says to delete.

### F5 (low) — "satisfies AC-1" is an overclaim of scope

A7 delivers 3 of AC-1's 13 named paths (`compose_metrics.py`,
`tools/compose_snapshot.py`, `.claude/commands/report-tour-issue.md`) and none
of AC-1's boundary clause (no `compose_script` import edge; premium-only
provider construction). CF-4 already says exactly this. Record the step as
"A7's slice of AC-1", never as AC-1 met.

## Proposed verifications I was not allowed to run (shared state)

- `make test-file FILE="tests/test_tour_authoring_extraction.py"` — A1's gate,
  not re-run since A7 deleted two files it names. My read says green.
- `make test-file FILE="tests/test_narration_quality.py"` — A7 scoped this file
  and the evidence never ran it (docstring-only edit, so expected green).
- `make test-file FILE="tests/test_tour_one_engine.py::test_compose_scoreboard_is_gone"`
  — independent re-derivation of the claimed green.
- F2's index-only mutation, above.
