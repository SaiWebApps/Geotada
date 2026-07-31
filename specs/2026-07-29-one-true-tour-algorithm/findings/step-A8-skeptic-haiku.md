# Skeptic Panel: Step A8 Evidence Review

**Model:** Claude Haiku 4.5  
**Date:** 2026-07-30  
**Verified against commit:** HEAD (c8ec3969), baseline ca02868e  
**Task:** Hostile review of evidence that step A8 "DELETE the whole-tour composer" satisfies AC-1, AC-9, AC-10

## Summary

**Overall verdict:** REFUTED

The claim that step A8 satisfies AC-1, AC-9, and AC-10 is **false**. While AC-1 and AC-9 requirements are met, **AC-10 requirements are incomplete**. Four AC-10 obligations remain unfinished:

1. `specs/2026-07-26-tour-engine-convergence/` must be deleted but **still exists**
2. `specs/2026-07-26-tour-rubric-recalibration/` must be deleted but **still exists**
3. Standard `01-standard.md`'s §6b must be deleted but **still exists** (line 372)
4. `pyproject.toml`'s `openai` dependency must be removed but **still listed**
5. `render.yaml`'s `OPENAI_API_KEY` must be removed but **still present**

The provided test (`test_whole_tour_composer_is_gone`) checks only the code/file deletions (AC-1, AC-9, and 1 of 7 AC-10 clauses), not the documentation and configuration changes that AC-10 explicitly requires.

## Evidence Chain Analysis

### Verified ✓

**make lint (exit 0):** I ran `make lint` myself; zero ruff errors confirmed.

**File deletions (AC-1, AC-9 code):** I verified manually that all claimed deletions are complete:
- `src/tour/compose.py` — deleted from disk and git ✓
- `src/tour/factcheck.py` — deleted from disk and git ✓
- 10 other compose-related test files — all deleted ✓
- No surviving file imports `src.tour.compose` or `src.tour.factcheck` ✓
- No src/ or scripts/ file reaches `compose_script` or `compose_script_per_chapter` ✓

**compose_gate reduction (AC-9/AC-10 partial):** I verified the module exports exactly two public names:
- `ComposeVerificationError` (class) ✓
- `build_full_verifier` (function) ✓

**conftest.py arms (AC-9):** I verified:
- Premium-executor + faithfulness arm is byte-identical to test requirement ✓
- Compose-client and factcheck arms correctly removed ✓
- Dependencies.py has `get_compose_client` and `get_omission_checker` removed ✓

**Makefile LIVE_TEST_FILES (AC-10 partial):** I verified:
- No deleted files listed in LIVE_TEST_FILES ✓
- All listed files exist on disk ✓

### Unverified — Test Mutation

The evidence claims a RED mutation: reverting source files while keeping `compose.py` deleted causes an `ImportError` at conftest collection. I cannot verify this myself (it touches the shared 7688 database), but the logic is sound: if `dependencies.py` reverts to importing `compose`, and `compose.py` is deleted, collection fails. The supplementary mutation (restoring `compose.py`) shows the test's own assertion logic catches the regression. This is a plausible red-first proof, but **unverified by me**.

### Refuted ✗ — AC-10 Documentation/Configuration Requirements

AC-10 from `run-context.md:162-169`:

> Given the docs and config after Track A, then `Docs/Markdown Docs/API_REFERENCE.md` describes the per-stop compose engine, standard `01-standard.md`'s §6b (whole-tour-vs-per-chapter divergence) is **deleted**, `specs/2026-07-26-tour-engine-convergence/` and `specs/2026-07-26-tour-rubric-recalibration/` are **deleted**, `render.yaml`'s `OPENAI_API_KEY` and `test_render_manifest`'s openai entries and `pyproject`'s openai dependency are **removed** (iff zero remaining importers), and `make tour-build` runs the $0 stitch+render harness.

I checked the actual state of the repo:

| AC-10 Requirement | Status | Evidence |
|---|---|---|
| `specs/2026-07-26-tour-engine-convergence/` deleted | **NOT MET** | Directory still exists on disk |
| `specs/2026-07-26-tour-rubric-recalibration/` deleted | **NOT MET** | Directory still exists on disk |
| `01-standard.md`'s §6b deleted | **NOT MET** | Section still present at line 372: `## 6b. Remaining divergence — the app compose path` |
| `render.yaml` OPENAI_API_KEY removed | **NOT MET** | Still present: `- key: OPENAI_API_KEY` |
| `pyproject.toml` openai removed | **NOT MET** | Still present: `"openai>=1.40"` |
| `make tour-build` runs $0 stitch+render | **PARTIALLY CHECKED** | Test verifies compose_gate reduction but not the tool's actual invocation |

All five of these items remain **incomplete**.

## Attacks Tried

1. ✓ Ran `make lint` myself to verify exit code
2. ✓ Checked disk and git index for deletions (file presence, `git ls-files`)
3. ✓ Parsed Python AST to verify imports, module APIs, conftest fixture structure
4. ✓ Parsed Makefile to check LIVE_TEST_FILES
5. ✓ String-matched exact byte sequence in conftest for AC-9(d) requirement
6. ✓ Checked for whole-tour entry point access via AST walk of src/ and scripts/
7. Proposed (but did not run): `make test-file FILE="tests/test_tour_one_engine.py::test_whole_tour_composer_is_gone"` — blocked by shared DB concurrency

## Conclusion

The test (`test_whole_tour_composer_is_gone`) is well-designed and **successfully verifies AC-1 and AC-9**, but it **does not verify AC-10 in full**. The test contains no assertions about:
- Deletion of the two `specs/2026-07-26-*` folders
- Deletion of `01-standard.md` §6b
- Removal of OPENAI entries from `render.yaml` or `pyproject.toml`

These AC-10 requirements remain **unmet in the repository**. The claim that step A8 "satisfies AC-1, AC-9, AC-10" is therefore **refuted**. The step satisfies AC-1 and AC-9, but does not satisfy AC-10.

The missing work is out of scope for the A8 step definition (which focuses on code/file deletions), but it is explicitly listed as an AC-10 requirement that must be met by end of Track A. The evidence chain is broken at the AC-10 verification level: the test does not and cannot prove what it claims.
