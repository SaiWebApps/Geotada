# Step A1 — hostile skeptic (opus), angle: NEGATIVE SPACE

**Verified against:** HEAD `c8ec3969` ("chore(certification): re-stamp the standard's pin
after the C11 demotion") plus the uncommitted A1 working tree — 12 tracked files modified,
3 untracked (`src/tour/authoring.py`, `tests/test_tour_authoring_extraction.py`,
`specs/.../findings/`). That matches the evidence bundle's own description of the tree.

**Verdict: the CHANGE survives every attack I ran. The PROOF does not.**
AC-2's substance is true — I re-derived both halves myself, offline. But the command the
claim cites as proof asserts neither half of AC-2, and I demonstrated that by executing the
gate's own verbatim code against a synthetic tree where the extraction plainly did not
happen. It passed.

---

## What I re-derived independently (read-only, zero shared state)

1. **`make lint` → exit 0**, run by me, unpiped. "All checks passed!".
2. **Byte-identity of all 12 moved names.** AST-extracted each top-level definition from
   `git show c8ec3969:src/tour/compose.py` and from the working-tree `src/tour/authoring.py`
   and compared the source segments byte-for-byte. All 12 identical, plus the two moved
   helpers `COMPOSE_MAX_OUTPUT_TOKENS` and `_compose_user_prompt`. The four constants that
   feed the hash — `COMPOSE_MODEL` (33 B), `CERTIFICATION_COMPOSE_MAX_OUTPUT_TOKENS` (67 B),
   `_COMPOSE_SYSTEM` (10 100 B), `_COMPOSE_OUTPUT_SCHEMA` (1 167 B) — are unchanged, and
   `premium_authoring_policy_sha256`'s own body in `premium_tour.py` is untouched by the diff.
   So the hash *cannot* have drifted.
3. **The pinned hash literal is anchored, not invented.**
   `ed5f149e…5611fd` appears in committed `data/certification/tour-batch-v1/plan.json` as
   `authoring_policy_sha256`, and that is the ONLY such value in `data/`.
4. **Importer set = 15**, exactly the pinned-3 + scheduled-12. Reproduced by grep and by AST.
5. **All 360 tracked `.py` files live under `src|tests|scripts|tools`** — the gate's
   `SCANNED_ROOTS` has no live blind directory.
6. **`compose.py` re-exports everything.** I collected the 90 top-level names `compose.py`
   now provides (defs + classes + assignments + imported aliases) and checked every name any
   file imports `from src.tour.compose`: zero missing. Its own tests still resolve.
7. **No import cycle.** Transitive AST walk from `src.tour.authoring` finds no path back to
   `src.tour.compose`.
8. **The monkeypatch targets did not move.** Every `setattr` on the compose module in
   `tests/conftest.py:102,115` and `tests/test_compose_provider.py:55,56,76` names
   `AnthropicComposeClient` / `OpenAIComposeClient`, both of which stay defined in
   `compose.py`. No patch silently became a no-op. `compose_client_for`'s
   `import src.tour.compose as _self` late-binding still resolves the real, patchable class.
9. **The 12/12 ledger cross-check is NOT circular.** `git diff state.json` in this working
   tree changes exactly two things: AC-2's text and A1's `status`. No later step's `files`
   array was touched, so the allowlist is checked against a scope the step did not author.
10. **The new test file is collected** by `_test-python` — it is not in `pyproject.toml`'s
    `--ignore` list.

---

## FINDING 1 (blocking the CLAIM, not the CODE) — the cited command proves neither half of AC-2

`state.json` step A1 `test_command` is exactly one node id:
`tests/test_tour_authoring_extraction.py::test_premium_imports_authoring_not_compose`.
That function is pure `ast` over `src/tour/premium_tour.py`. It **never imports anything**.

AC-2 has two conjuncts and the file has five tests. The three that actually assert AC-2 —
`test_authoring_policy_hash_is_byte_identical_after_the_move` (byte-identity half),
`test_remaining_compose_importers_are_pinned` and
`test_later_step_allowlist_matches_the_ledger` (importer half) — were **never executed**.
The evidence bundle itself labels its substitutes "manual, NOT a pytest run".

Hermetic reproduction (stdlib only, no repo state touched). I copied the gate file verbatim
into a synthetic tree so its `REPO_ROOT = parents[1]` resolved to the fake repo, gave it a
`premium_tour.py` with the exact post-fix import block, and then made the extraction a lie:

- `src/tour/authoring.py` = `this is not python (((` → **PASSED**.
- `src/tour/authoring.py` = an empty comment (none of the 12 names exist) plus a surviving
  `src/tour/still_needs_compose.py` importing compose three different ways →
  **all three structural tests PASSED**.

So the engine's A1 gate is green on a tree where `authoring.py` is unimportable, or empty,
and where a module that survives Track A still points at the file A8 deletes. The QA "REAL"
mutation verdict is genuine but narrow: it proves the import LINE in `premium_tour.py`
moved. It cannot reach the risk D4 names.

**Fix, $0:** change A1's `test_command` to the whole file,
`make test-file FILE="tests/test_tour_authoring_extraction.py"`. All five tests exist and
are written; they are simply not wired to the gate. (I could not run it — shared 7688/7687.)

## FINDING 2 (real, medium) — the AST importer scan cannot see three import spellings

`_imported_modules` maps `from src.tour import compose` and `from . import compose` to the
module `"src.tour"`, not `"src.tour.compose"`, and never inspects
`importlib.import_module("src.tour.compose")`. Demonstrated above: a survivor using all
three forms is invisible to `test_remaining_compose_importers_are_pinned`.

No file uses those forms for compose **today** (verified by grep across all four roots), so
nothing is currently broken. But the gate's entire stated purpose is "a missed extraction
fails at A1 and not at A8", and steps A2–A9 rewrite `dependencies.py`, `trips.py`,
`conftest.py` and the scripts. Any of those rewrites can reintroduce the edge in a spelling
the pin does not see, and the failure then surfaces at A8 as an ImportError — the exact
outcome A1 exists to prevent.

## FINDING 3 (real, low) — 3 of the 4 scripts A1 edited are outside A1's OWN gate

A1's pinned gate is `make lint`. `Makefile:105-109` lints `src/`, `tests/` and a nine-file
scripts allowlist. Of the four scripts A1 modified, only `scripts/tour_batch_candidate.py`
is in it. Not linted: `scripts/tour_batch_review.py`, `scripts/tour_text_candidate.py`,
`scripts/tour_text_candidate_review.py`. `tools/` is not linted at all.

I first believed `scripts/tour_text_candidate_review.py` was guarded by nothing; that was
WRONG and I am correcting it. `tests/test_tour_text_candidate_review_runner.py:11` does
`from scripts import tour_text_candidate_review as runner` — a spelling my first grep
pattern missed. All four edited scripts are in fact imported by a test in the python shard:
`test_tour_batch_review_runner.py`, `test_tour_text_candidate_runner.py`,
`test_tour_text_candidate_review_runner.py`.

So the residual gap is only detection LATENCY: a bad repoint in three of the four scripts
is invisible to A1's own gate and first surfaces at the A3 phase gate, two steps and one
`maxAttempts` budget later, where the run-context's named top risk (misattributing a red
shard) applies.

## FINDING 4 (advisory, low) — the gate crashes instead of asserting on an unparseable file

`test_remaining_compose_importers_are_pinned` calls `ast.parse` on every file under the four
roots with no guard. In my synthetic run it raised an uncaught `SyntaxError`, not an
`AssertionError`. It still goes red, so this is cosmetic, but the failure message points at
`ast.py` rather than at the offending file.

## FINDING 5 (advisory, low) — the docstring names a ledger key that does not exist

`test_later_step_allowlist_matches_the_ledger`'s docstring says each file "must appear in
the `files_allowed` of the step". The code correctly reads `step["files"]`, and `files` is
the real key. Cosmetic, but it is the one test whose whole point is that a renamed field
must not become a silent all-pass.

---

## Attacks that FAILED to break it

- Import cycle `authoring → … → compose`: none exists.
- Missing re-export breaking `compose.py`'s own surviving tests: zero missing across 90 names.
- Monkeypatch target silently relocated into `authoring` (a no-op patch): none; all patched
  names stayed in `compose.py`.
- Prompt/schema drift during the move: byte-identical, and the pinned hash literal is
  corroborated by committed certification data.
- Circular self-justification (A1 editing later steps' `files` scope to make its own
  allowlist pass): refuted — the diff touches only AC-2's text and A1's status.
- Importers hiding outside `SCANNED_ROOTS`: all 360 tracked `.py` files are inside them.
- Test file silently uncollected by the python shard: it is collected.
- Reconciling the evidence's numbers: 15 importers, 12 modified + 3 untracked paths, and the
  ad-hoc 12/12 cross-check all reproduce exactly.

## Not tested by anyone, and out of my reach here

`make test-file` starts the shared 7687/7688/Valhalla containers; two sibling skeptics were
running concurrently, so I ran only `make lint`. Nothing in this evidence chain shows the
repository's real `src/tour/authoring.py` being *imported* by a Python process. Byte-identity
is proven statically; importability is not.
