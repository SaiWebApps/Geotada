# Skeptic panel — step A4 (gate parity on the persisted path) — FIX CORRECTNESS angle

Verified against: HEAD `c8ec39690030901660c843d46910bedb40e84c13` (main, clean at HEAD;
working tree carries the uncommitted A1-A4 changes under review — 16 files modified, 4
new/deleted under `src/`, `tests/`, `scripts/`).

## What I could and could not do

Per the concurrent-skeptic constraints I was given, I could run `make lint` myself
(pure ruff, no shared state) but was told to PROPOSE, not run, anything touching the
shared 7688/7687 Neo4j containers or Valhalla — including the pinned gate command
`make test-file FILE="tests/test_tour_authoring_gates.py::test_unfaithful_output_is_refused_and_trip_untouched"`.
So my method was: re-derive correctness from the source, not from the pasted transcript.

- `make lint` (run by me, this session): exit 0, "All checks passed!" — matches the
  claim's pasted evidence.
- The pinned pytest node id and its RED/GREEN mutation cycle: **not independently
  executed by me**. I read the developer's transcript but did not reproduce it.

## Static/code-review attacks attempted (fix-correctness angle)

1. **Does the call site actually wire the three gates, and are they load-bearing?**
   Read `src/api/routes/trips.py:784-789` — `compose_trip()` calls
   `author_prebuilt_route(plan, executor=premium_executor, faithfulness_checker=faithfulness_checker,
   enforce_claim_coverage=True, scan_glue_for_invention=True)`. Confirmed these three
   kwargs exist and are non-default (defaults on `author_prebuilt_route`/
   `finalize_certification_composition` are `None`/`False`/`False` — the pre-fix,
   gate-off state the claim's mutation reproduces).

2. **Are the three gates independently load-bearing (not just present but functionally
   wired), so a partial-unwiring regression would still be caught by the ONE pinned
   test?** Traced `finalize_certification_composition` (`src/tour/authoring.py:528-654`):
   - `faithfulness_checker` flows into `build_full_verifier(..., faithfulness_checker=faithfulness_checker)`
     (`compose_gate.py:331`: `checker = faithfulness_checker or MockFaithfulnessChecker()`).
   - `enforce_claim_coverage` gates whether `expected_claim_ids=claims_realized_by(stitched, beats_by_id)`
     is passed at all (`None` -> coverage is a no-op per `compose_gate.py:341-345`).
   - `scan_glue_for_invention` gates whether the nested `validate_authorized_sources`
     closure overlays `validate_script(...).forbidden_phrase_hits` onto the traceability-only
     report (`authoring.py:630-639`).
   Each is an independent short-circuit. Since the pinned test drives THREE distinct
   $0 doubles (`_RewritingExecutor` for faithfulness, `_ClaimBlurringExecutor` for
   coverage, `_InventingGlueExecutor` for invention) as three sequential blocks inside
   one node id, unwiring any ONE of the three kwargs — not just all three, as the
   developer's mutation did — independently fails one of the three blocks (verified by
   reading each double's design and each block's assertions, e.g. the coverage block
   asserts `resp.status_code == 422` before checking gate-specific counts, so a
   coverage-only regression alone flips that to 200 and fails immediately).

3. **Is the deleted characterization test's own stated deletion condition actually
   met, or is this a premature/strawman deletion riding on the unrelated D4
   extraction?** Read the deleted `tests/test_compose_gate_forbidden_scan.py` at HEAD
   (`git show HEAD:tests/test_compose_gate_forbidden_scan.py`). Its pinned assertion
   (`test_certification_validator_delegates_only_to_traceability`) requires the nested
   `validate_authorized_sources` closure body to be EXACTLY one statement:
   `return validate_source_traceability(...)`. The current closure in
   `src/tour/authoring.py:622-639` has an assignment, a conditional early-return, and a
   final `model_copy` — i.e. more than one statement — so the AST-based structural
   check this file pinned would genuinely go RED under the current code. This is a real
   structural change caused by the D3 gate itself, not merely the D4 file-move (which
   would have broken the test's import, not its assertion). The deletion is justified.

4. **Coverage-baseline soundness**: confirmed `plan_prebuilt_route_authoring(source=stitched, ...)`
   (called from `trips.py` with the PRE-compose `stitched = generate(seq, route, tour_input)`)
   is what flows into `finalize_certification_composition`'s `stitched` argument, so
   `claims_realized_by(stitched, beats_by_id)` is genuinely the pre-compose baseline
   D3 describes — not a self-referential baseline computed from the (possibly gutted)
   composed output.

5. **Faithfulness short-circuit vs. the `_RewritingExecutor` double**: confirmed
   `passes_sentence_unit_shortcut` (`src/tour/verify.py:253-281`) requires an EXACT
   normalized match to a contiguous run of the beat's `script_body`; the double's
   `"Here is the thing, " + text` prefix cannot match, so the sentence is provably
   routed to the injected checker rather than silently short-circuited as verbatim
   — i.e. the fixture is not a strawman that would pass even with the checker unwired.

6. **Byte-unchanged persistence claim**: read `compose_trip()` end to end —
   `replace_trip_stops`/`mark_trip_composed` occur strictly after the
   `try/except ComposeVerificationError/except ValueError` block that wraps
   `author_prebuilt_route`, so a refusal genuinely cannot reach the write path.

7. **$0 claim**: confirmed via `tests/conftest.py`'s autouse `_money_guard_no_live_compose`
   fixture (applies to this non-`live`-marked module) that `AnthropicPremiumExecutor` and
   `HaikuFaithfulnessChecker` are monkeypatched to offline stubs by default, and the
   pinned test overrides both dependencies directly with in-test doubles anyway, so no
   path in this test can reach a billing SDK.

None of these attacks found a defect in the fix's logic. I could not find a plausible
neighbouring input (partial gate unwiring, one-stop trip guarded against by the test's
own `len(before["stops"]) > 1` assertion, a coverage-only regression, a forbidden-scan-only
regression) that the pinned test would fail to catch, based on static reading alone.

## What I did NOT verify (the actual gap)

- I did not execute `make test-file FILE="tests/test_tour_authoring_gates.py::test_unfaithful_output_is_refused_and_trip_untouched"`
  myself, either in the fixed state or with the three kwargs reverted. The developer's
  pasted RED/GREEN transcript is internally consistent with the source I read, but is
  unverified by me directly — it requires the live Paris dev Neo4j graph (module-scoped
  `live_neo4j` fixture, `open_dev_driver()`), which I was told not to touch concurrently.
- I did not check whether `make lint`'s clean pass on MY run reflects the exact same tree
  the developer's transcript describes (both are the current uncommitted working tree, so
  they should coincide, but I did not diff against a saved copy of "the tree at their
  claimed pass").

## Verdict

Static code review across the call site, the seam, the finalizer, the deleted
characterization test's own pinned condition, the coverage-baseline provenance, and the
money-guard chain found no defect and no strawman in the red-first test's design — it
genuinely encodes three independent original failure modes (silently-dropped
faithfulness, coverage, and forbidden-phrase-scan gates) with fixture design that
provably reaches each gate rather than short-circuiting around it. `make lint` was
independently re-run and passed. The dynamic pinned-test reproduction itself (the load-
bearing RED-before/GREEN-after evidence) was NOT independently executed by me this
session per the shared-container restriction; I am proposing it to the serial verifier
rather than fabricating a result.
