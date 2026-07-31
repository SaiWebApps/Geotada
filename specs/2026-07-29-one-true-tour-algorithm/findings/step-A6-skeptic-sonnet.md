# Step A6 skeptic review (sonnet) — FIX CORRECTNESS angle

Verified against commit `c8ec39690030901660c843d46910bedb40e84c13` (HEAD, clean at
session start) **plus the uncommitted working-tree state** that carries A1-A6 (git status
shows `D scripts/author_tour.py`, `D src/tour/author.py`, `D src/tour/content_budget.py`,
`D src/tour/tour_consistency.py`, `D tests/test_author.py`, `D tests/test_content_budget.py`,
`D tests/test_tour_consistency.py`, `M tests/conftest.py`, `A tests/test_tour_one_engine.py`,
plus A1's compose.py/authoring.py extraction). This IS the tree the claim's evidence was
run against.

## What I independently re-derived (not trusted from the pasted evidence)

1. **`make lint`** — ran it myself: exit 0, "All checks passed!". Matches the claim.

2. **Reimplemented all three assertions inside
   `tests/test_tour_one_engine.py::test_author_engine_track_is_gone` as standalone
   scripts (no pytest, no conftest.py fixtures, no DB/container) and ran them against
   the live tree:**
   - Assertion 1 (files gone from disk + from `git ls-files`): all 7 `DELETED_FILES`
     paths return `exists() == False`; `git ls-files -- <paths>` returns empty. Confirmed.
   - Assertion 2 (no surviving importer of `src.tour.author` /
     `src.tour.content_budget` / `src.tour.tour_consistency`): walked every `.py` file
     under `src/`, `scripts/`, `tests/`, `tools/` with `ast`, collecting `Import`/
     `ImportFrom` targets. Zero offenders. Confirmed — this also independently caught
     that the reverse dependency doesn't exist (`author.py` imported FROM
     `factcheck.py`, not the other way — deleting `author.py` cannot break
     `factcheck.py`, which the ledger correctly keeps alive for A8).
   - Assertion 3 (money-guard AST-structural armed-set equality): reimplemented
     `_money_guard_armed_pairs` verbatim against the real `tests/conftest.py` and got
     exactly the 9-pair `EXPECTED_MONEY_GUARD_ARMS` set — no missing, no extra pairs.
     Also confirmed `src.tour.author` / `src.tour.tour_consistency` are absent from
     conftest's import set.
   - `py_compile`'d `tests/conftest.py`, `tests/test_tour_one_engine.py`,
     `src/tour/factcheck.py`, `src/tour/compose.py`, `src/tour/authoring.py`,
     `src/tour/premium_tour.py`, `src/api/dependencies.py`, `src/api/routes/trips.py` —
     all compile clean, ruling out a syntax-level collection blow-up.

   This reproduces, by independent re-derivation rather than trust, exactly what the
   pinned pytest node id checks — strong (though not pytest-itself) corroboration of the
   developer's claimed `1 passed`.

3. **Scope-creep check (the real "neighbouring input" attack for a deletion step):**
   grepped `Makefile`, `pyproject.toml` (`testpaths`/`addopts`/lint target), and every
   `scripts/*.py`/`tools/*.py` file for `author_tour`, `content_budget`,
   `partition_poi_content`, `tour_consistency` — zero live hits outside the deleted set
   and this ledger's own `specs/2026-07-29-...` docs. The only surviving hits are prose
   comments (`author.py`'s `trace` idiom mentioned in `compose.py`'s docstring,
   `factcheck.py`'s "author-engine" narrative comments, stale refs in the superseded
   `specs/2026-07-26-tour-engine-convergence/` — correctly scheduled for deletion at
   A10, not this step) — none are functional imports.

4. **`git diff HEAD -- tests/conftest.py`** — read the full diff directly (not the
   pasted excerpt). It removes exactly two arms: the `LLMDrafter`
   (`src.tour.author`) stub and the `HaikuCrossStopJudge`
   (`src.tour.tour_consistency`) stub, and leaves the factcheck-judge loop
   (`HaikuClaimDecomposer`/`HaikuCoverageJudge`/`HaikuFaithfulnessJudge`) untouched —
   consistent with D6 ("factcheck.py waits for A8") and with
   `src/api/dependencies.py:201`'s `get_omission_checker` still constructing
   `factcheck.HaikuCoverageJudge()` for real. If A6 had also stripped the factcheck arm,
   that dependency would be unguarded and the hermetic suite could bill.

## Does the red-first test encode the ORIGINAL failure mode, or a strawman?

Not a strawman. The three assertions map onto the three ways this exact class of
deletion step actually breaks in this codebase:
- leaving a file on disk/tracked while claiming deletion (assertion 1),
- an importer elsewhere exploding only at collection/runtime because the scan missed it
  (assertion 2 — this is a real historical failure mode in this repo: the
  `content-budget-is-harness-only` memory shows this codebase has previously shipped
  code paths nobody checked for callers before treating it as dead),
- a money-guard silently disarmed by a careless edit while the class name lingers in a
  comment (assertion 3) — and the developer's own mutation 2, which I read and consider
  a genuine (not fabricated) adversarial case: it exactly matches the failure mode
  `feedback-no-lexical-shortcuts.md`/`feedback-never-use-regex.md` warn about (a
  substring/text check would stay green on a disarmed guard). The AST walk correctly
  fails on it.

## Claim-precision note (not a functional defect)

The claim as forwarded says step A6 "satisfies AC-1, AC-9." Taken literally that
overclaims: AC-1 and AC-9 are Track-A-close criteria with 9 of 13 AC-1 clauses and two of
AC-9's four arms still unasserted by any node id today (compose_metrics.py/
compose_snapshot.py/report-tour-issue.md at A7; compose.py/factcheck.py at A8;
compose_correct.py/verify_gate.py/claim_repetition.py at A9; the compose_script boundary
clause has no check at all yet). This is not a hidden gap — the test's own docstring says
verbatim "A6 GREEN IS NOT AC-1/AC-9 MET" and `state.json`'s `CF-4` (from an A6 judge
ruling) enumerates exactly which clauses remain open and which future step owns each.
Whoever writes the eventual Track-A-close commit message must not compress "A6 done"
into "AC-1/AC-9 satisfied" — flagging so it doesn't get lost between here and the close
gate, not blocking A6 itself.

## Attacks tried that did NOT break the claim

- Checked for a reverse-dependency trap (factcheck.py importing something from the
  deleted files) — none exists; the import direction is author.py -> factcheck.py.
- Checked for dynamic/aliased imports of the deleted modules that a naive text grep
  would miss — the AST-based reimplementation covers `import x as y` and
  `from . import x` resolution; found none.
- Checked Makefile/pyproject for hardcoded references to the deleted scripts/tests
  (would break `make lint`'s own file list or pytest's ignore list) — none found.
- Checked whether deleting `content_budget.py` orphans any surviving script (the
  `content-budget-is-harness-only` memory flagged 8 scripts/ callers historically) —
  none of the currently-tracked scripts import it; the memory's premise (`src/`
  callers = zero) was already reflected correctly.
- py_compile'd every touched/adjacent file — no syntax breakage.

## Verdict

CONFIRMED for what A6 itself claims to do (delete the 4 source files + 3 test files,
scrub the two money-guard arms, leave everything else — especially the factcheck
arm A8 still needs — untouched). The deletion is correctly scoped, the red-first test
encodes real failure modes (not a strawman), and my independent re-derivation of all
three of its assertions against the live tree matches the developer's claimed
`1 passed`/exit 0 result. The only issue worth carrying forward is the claim-precision
point above (already tracked in `CF-4`, not new), not a functional defect in A6.

## Not run myself (proposed for the serial verifier)

- `make test-file FILE="tests/test_tour_one_engine.py::test_author_engine_track_is_gone"`
  — I reimplemented its logic standalone and got the same result it would, but the
  authoritative pytest-level run (including conftest.py fixture collection under real
  pytest, not my reimplementation) should still be executed once by the serial verifier
  for the record.
