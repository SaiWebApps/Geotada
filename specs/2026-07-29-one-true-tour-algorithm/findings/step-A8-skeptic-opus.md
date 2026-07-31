# Step A8 — hostile skeptic (opus), NEGATIVE-SPACE angle

**Verified against:** HEAD `c8ec3969` ("chore(certification): re-stamp the standard's
pin after the C11 demotion") with the A8 working tree applied (72-line
`git status --short`, matching the developer's stated starting state).
**Date:** 2026-07-30. **Run mode:** concurrent with 2 sibling skeptics, so only
`make lint` and read-only `git`/`ast` analysis were executed here.

**Verdict: REFUTED.** Not on the fix's logic — the worktree code is right and the
pinned test is real — but on the artifact. The thing that was tested is not the
thing that would be committed, and the thing that would be committed does not
import.

---

## What I re-derived and could NOT break

- `make lint` -> exit 0, `All checks passed!` (re-run by me, unpiped).
- The pinned test body is genuinely structural: `ast` + `git ls-files` +
  `subprocess`, no text matching, six numbered checks, and check #1 asserts BOTH
  disk-absence and index-absence for the 12 deleted files.
- Check #3's equality (not containment) on `compose_gate`'s public surface is a
  real anti-regression: re-adding `compose_and_verify` as a `def` turns it red.
- Blast radius on the WORKTREE is clean. I re-ran the developer's negative
  scans independently and widened them:
  - No surviving `.py` under `src/`, `scripts/`, `tests/`, `tools/` imports
    `src.tour.compose` or `src.tour.factcheck` (full AST walk, relative imports
    resolved).
  - No `importlib.import_module(...)` / `__import__(...)` / string
    `monkeypatch.setattr("src.tour.compose...")` escape hatch anywhere — the
    only dynamic imports in the tree are in `test_poi_role_backfill.py`,
    `test_claim_repetition.py`, `test_audio_storage.py`, `test_onboard_boundary.py`,
    none of them naming a deleted module.
  - No non-Python reference survives: `frontend/` (only `data.compose_status`,
    the still-live preview field), `.claude/commands/tour-build.md` (zero
    occurrences of "compose", case-insensitive), `Makefile` (only the pruned
    `LIVE_TEST_FILES`), `render.yaml`/`pyproject` openai entries are A10's.
  - `ComposeVerificationError` still has a live producer
    (`src/tour/authoring.py:776`, `raise ComposeVerificationError(report, 1)`)
    and a live consumer (`src/api/routes/trips.py:791`), so AC-3's 422 shape and
    D9 loss (6) `attempts == 1` are both structurally intact.
  - `scripts/tour_build.py` still binds every name it uses after the rewrite;
    `script.validation` is set before its three read sites (`:359`, `:380`, `:381`)
    and `return 0 if passed else 1` preserves the module docstring's exit contract.

---

## F1 (BLOCKER, high) — the committable tree is broken; only the worktree was tested

A8's DELETIONS are staged. A8's compensating SOURCE EDITS are not.

```
$ git diff --name-only -- <A8's files[]>
Makefile
scripts/tour_build.py
src/api/dependencies.py
src/tour/compose_gate.py
src/tour/narration_quality.py
tests/conftest.py
tests/test_tour_one_engine.py
```

Seven of A8's own files differ between the index and the worktree. A plain
`git commit` produces the index tree. I materialised that exact tree with
`git checkout-index` (read-only; nothing in the repo touched) and it is dead:

```
index tree: src/tour/compose.py absent = True
index tree: src/api/dependencies.py:9  = from src.tour.compose import ComposeClient
index tree: tests/conftest.py:88       = import src.tour.compose as _compose_mod
```

Consequences of committing as-is:

1. `src/api/dependencies.py:9` is a MODULE-LEVEL import of a module that does not
   exist in that tree. `src.api` does not import at all — the whole API is dead
   on arrival, and this is byte-for-byte the `ModuleNotFoundError` the developer's
   own mutation run produced and then treated as the RED proof.
2. `tests/conftest.py:88` sits inside the `autouse` `_money_guard_no_live_compose`
   fixture, so EVERY non-`live` test in the suite errors at setup. `make test`
   collects and then dies wholesale.
3. Two more dangling first-party imports in the same tree:
   `dependencies.py:15`/`:199` -> `src.tour.factcheck`.
   Full index-tree scan of `src/ scripts/ tests/ tools/` finds exactly these two
   files and six import sites; no others.

This is not a nitpick about staging hygiene — it is the SAME blocker this ledger
already raised and closed twice. A6's recorded proof: "`git diff --name-only` over
the same 9 is EMPTY (index == worktree, closing round 1's non-committable-tree
blocker) ... so the tree a commit would produce is the tree that was tested."
A7's: "gone from disk AND the index (staged `D`, so the tree a commit would
produce is the tree that was tested)." A8 asserts neither and satisfies neither.

**Why the pinned test cannot catch it.** Check #1 asks disk-absence AND
index-absence for the twelve DELETED paths. It never asks index==worktree for the
SURVIVING paths. A mixed state — deletions staged, repairs unstaged — is the one
state that passes every one of the six checks while being uncommittable. The
developer's mutation evidence actually documents this hole without naming it:
their first RED was an `ImportError` at conftest collection, which they explained
as "the reverted `dependencies.py` still imports the already-deleted
`src.tour.compose`". That is a description of the index tree's permanent state.

**Fix:** `git add -A` the seven files (or restage the whole step scope) and
re-run the pinned node id, then re-assert `git diff --name-only` over A8's
`files[]` is EMPTY, exactly as A6/A7 did.

Reproduction (hermetic, read-only, executed by me, exit 1):

```
rm -rf $SCRATCH/idx && mkdir -p $SCRATCH/idx \
  && git checkout-index -a --prefix=$SCRATCH/idx/ \
  && python3 -c "<print dependencies.py:9 / conftest.py:88 / compose.py existence; exit 1 if broken>"
```

---

## F2 (medium) — "satisfies AC-1, AC-9, AC-10" is false as stated

The step's own test docstring says it: "NONE OF THIS IS AC-1/AC-9 MET ON ITS OWN."
Measured on the tree:

- **AC-1** names 13 paths absent from `git ls-files`. Four are still tracked after
  A8: `src/tour/compose_correct.py`, `src/tour/verify_gate.py`,
  `src/tour/claim_repetition.py`, `scripts/tour_text_candidate_review.py` (A9/A10).
- **AC-9** requires `src/api/dependencies.py` to hold no `get_correction_client`
  and no `get_claim_repetition_judge`. Both are still defined (`:132`, `:154`),
  and the corrector money-guard arm is still armed by design.
- **AC-10** has five clauses (API_REFERENCE.md, `01-standard.md` §6b, two spec
  directories, `render.yaml`/`test_render_manifest`/`pyproject` openai). A8's
  `files[]` contains none of them; its only AC-10 contribution is `make tour-build`,
  and see F4.

A8 CONTRIBUTES to AC-1/AC-9/AC-10 (that is what `criterion_ids` many-to-many
means). It does not satisfy any of them. The claim as written would let a reader
close three acceptance criteria that are still open.

---

## F3 (medium) — `craft_score` is now zero-caller dead code and its docstring lies

`grep craft_score src/ scripts/` returns hits only inside
`src/tour/narration_quality.py` itself. Zero production callers.

`narration_quality.py:353-356` currently reads: "`compose.py:~1067` — a RANKER
only ... This is craft_score's ONLY surviving caller as of Track A step A6 ...
`compose.py` itself is scheduled for deletion at A8, after which this function has
zero production callers", and the closing paragraph says "only the lower-stakes
best-of-N ranker in compose.py remains." A8 IS that step. `compose.py` is gone.
The docstring now describes a caller that A8 itself deleted — a doc that
contradicts the code, which CLAUDE.md says gets corrected or deleted, never left.

D9 loss (5) is "the compose-metrics scoreboard **+ craft_score**"; A7's own proof
records CF-5 assigning ownership of craft_score's deletion to A8. A8 deleted
neither `craft_score` nor its six tests in `tests/test_narration_quality.py`, and
did not correct the docstring. No later step's `files[]` contains
`src/tour/narration_quality.py`, so the consented loss is again unowned.

---

## F4 (UNPROVEN, medium) — AC-10's only A8 clause was never executed

AC-10 says "`make tour-build` runs the $0 stitch+render harness." The evidence for
that is `make lint` plus a test that reads ASTs. The test's own check #3 comment
claims the reduced gate surface "is what makes `make tour-build` the $0
stitch+render harness of D7/AC-10" — absence of an import is not proof that a
script runs.

The rewritten stage also changed observable behaviour that no test covers: the old
path raised `ComposeVerificationError` and returned 1 BEFORE writing anything;
the new path writes `{gen_id}.json` and `{gen_id}.md` into
`data/{city}/tours/` and THEN returns 1. A refused tour is now persisted as an
artifact. That may be desirable for an editorial harness, but it is an unasserted
behaviour change on a `make` target AC-10 names.

Proposed for the serial verifier (touches the 7687 dev graph + Valhalla, so I did
not run it):
`make tour-build ARGS="--start 'Notre-Dame' --duration 60 --city-slug paris"`
Expect: exit 0 or 1 with a `validation: PASS/FAIL` line and the two artifacts
written; any traceback refutes AC-10 outright.

---

## F5 (UNPROVEN, medium) — the Python shard was never run against A8

A8 deletes 8 test files, deletes 2 `src/` modules, and edits the autouse
money-guard fixture that arms every non-live test. The executed evidence is
`make lint` plus one pure-AST node id. Static analysis proves no `ImportFrom`/
`Import` edge survives; it cannot prove the suite still COLLECTS and PASSES
(fixture resolution, `pytest.importorskip`, plugin registration, deleted-module
fixtures consumed by surviving tests).

Proposed for the serial verifier: `make _test-python`.
Expect: 0 failed, 0 skipped, and a collected count ~8 files lower than the 2605
recorded in the ledger's last close-gate run. Note that run already carried two
out-of-scope failures (`TestForceCreate::test_force_create_results_in_two_nodes`,
`TestProvenanceUploadAndBackfill::test_full_upload_preserves_audio_url_on_reupload`)
which must not be absorbed into A8's verdict.

---

## F6 (advisory, low) — stale `--ignore` pointing at a file A8 deleted

`pyproject.toml:75` still carries `--ignore=tests/test_tour_compose_live.py` in
`addopts`. A8 deleted that file and `pyproject.toml` is not in A8's `files[]`, so
no step removes it. pytest tolerates a nonexistent `--ignore` path, so I am NOT
claiming a break — this is residue, and CLAUDE.md's "no scaffolding left behind"
applies to it.

## F7 (advisory, low) — check #3 has a re-export blind spot

`_public_top_level_names` counts only `ClassDef`/`FunctionDef`/`AsyncFunctionDef`/
`Assign`/`AnnAssign`. A future
`from .somewhere import compose_and_verify` inside `compose_gate.py` would restore
the ladder to the module's public surface and the equality assertion would stay
green. Not the current state; recorded so the next person who touches that file
knows the guard's edge.

---

## Attacks that FAILED to break the claim

- Hunted a surviving importer of the deleted modules across `src/`, `scripts/`,
  `tests/`, `tools/` with a full AST walk including relative-import resolution and
  function-body imports — none.
- Hunted a dynamic/string escape (`importlib`, `__import__`,
  `monkeypatch.setattr("src.tour.compose...")`, `patch("src.tour.factcheck...")`)
  — none.
- Hunted non-Python entry points: Makefile targets, `pyproject`, `render.yaml`,
  `frontend/review.html`, `.claude/commands/tour-build.md`, the `/tour-build`
  skill — none reference deleted code (only the stale `--ignore` in F6).
- Checked whether `scripts/tour_build.py` still binds `Script`, `HaikuGlueClient`,
  `MockGlueClient`, `args.haiku` after the excision — all still used and imported.
- Checked whether `ComposeVerificationError` was orphaned by the gate reduction —
  it is raised at `authoring.py:776` and caught at `trips.py:791`, so AC-3's 422
  and D9(6)'s constant `attempts == 1` hold.
- Checked whether removing 5 money-guard arms disarmed a still-reachable billing
  path — both removed modules are gone, so the arms were unreachable; the
  surviving four-row set is what the test pins by equality.
- Re-ran `make lint` myself: exit 0.
