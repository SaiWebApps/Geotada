# Step A4 — hostile skeptic (NEGATIVE SPACE angle)

**Stamp.** HEAD `c8ec39690030901660c843d46910bedb40e84c13`
("chore(certification): re-stamp the standard's pin after the C11 demotion"),
working tree DIRTY with the uncommitted A1-A4 changes;
`git diff HEAD | shasum -a 256` = `ef4e942c2d617af315c3b1299a668f02bdf967c9ad2d10af5427503e0a734e20`.
Ran concurrently with 2 other skeptics, so the only command I executed myself is
`make lint`. Everything else is proposed for the serial verifier and is marked
`repro_verified=false`.

**Re-derived myself:** `make lint` -> exit 0, "All checks passed!". The evidence
bundle's item 1 reconciles.

**Verdict on the claim as stated:** the mutation evidence is sound and I could not
break the refusal half of AC-5. The claim is nonetheless INCOMPLETE, and one of the
gaps (F1) is the shape that ships a 100%-refusing endpoint with a green suite.

---

## F1 (HIGH, UNPROVEN) — the ACCEPTANCE half of AC-5 is vacuous; nothing proves a REWRITTEN tour can pass the three gates

AC-5's own guard against "wire the gates to reject everything" is
`test_a_faithful_tour_still_composes`
(`/Users/sairambkrishnan/git/ondoway/tests/test_tour_authoring_gates.py:429`). Its
`_EchoExecutor` returns the stitch back **byte-identically**. Two things follow:

1. `verify_faithfulness` short-circuits verbatim corpus text —
   `passes_sentence_unit_shortcut` at
   `/Users/sairambkrishnan/git/ondoway/src/tour/verify.py:217`, "canonical corpus
   text, unchanged — trivially faithful". The test module's OWN `_RewritingExecutor`
   docstring says the same thing and is the reason that double exists. So on the echo
   tour the faithfulness gate makes essentially zero entailment decisions (only
   `GLUE_REFLECTION` glue is exempt from the shortcut).
2. That test does NOT override `get_faithfulness_checker`, so it gets the product
   dependency — and the conftest money-guard rebinds
   `src.tour.verify.HaikuFaithfulnessChecker` to `MockFaithfulnessChecker`
   (`tests/conftest.py`, the :117-135 arm), which returns `True` for everything
   (`src/tour/verify.py:83-85`). `get_faithfulness_checker` does its import INSIDE the
   function (`src/api/dependencies.py:149`), so the patch is picked up.

The proved matrix is therefore:

| | trusting checker | rejecting checker |
|---|---|---|
| unrewritten text | 200 (proved) | — |
| rewritten text | **NOT TESTED** | 422 (proved) |

The empty cell is production. And A3 removed the safety valve that used to cover it:
the pre-cutover `compose_script` ran "EXACTLY one bounded recompose steered by that
report" (`git show HEAD:src/tour/compose.py`, `compose_script` docstring at line
1341); `author_prebuilt_route` is "Exactly one call per unit — no retries"
(`src/tour/authoring.py:859`) and `COMPOSE_ATTEMPTS = 1` is a literal in
`src/api/routes/trips.py`. So A4 restores the full teeth to a path that now has ONE
fewer chance to satisfy them, and no test at any tier drives that path with a
genuinely rewriting executor plus a non-trusting checker.

The ledger consents to "attempts becomes constant 1" (D9 loss 6) as a **wire-field**
loss. The behavioural loss — a tour that used to be rescued by the second steered
attempt is now an immediate, unrecoverable 422 — is not measured anywhere, and A4's
"gate parity" wording papers over it.

**Not reproducible cheaply.** The missing test is a fourth double: an executor that
rewrites beat sentences while preserving their claims (the existing
`_RewritingExecutor` already does exactly this — it keeps the original text inside the
rewrite) driven against the DEFAULT (trusting) checker, asserting 200. That is one
`_override_dep` call away and it is the cell that decides whether the endpoint works.
Proposed follow-up gate, for the serial verifier once such a test exists:
`make test-file FILE="tests/test_tour_authoring_gates.py"`.

## F2 (MEDIUM, UNPROVEN) — the new blanket `except ValueError` makes a structural refusal wire-identical to a verification refusal, and one reachable shape is a PERMANENT 422

`src/api/routes/trips.py` compose_trip now ends its authoring `try` with a catch-all
`except ValueError` that emits `{"reason": "compose_verification_failed", "attempts":
1, "untraceable": 0, "forbidden": 0, "provenance": 0, "faithfulness": 0}`. Every one
of these raises `ValueError` into it:

- `src/tour/authoring.py:497` — `1 <= len(stops) <= AUTHORING_MAX_STOPS`;
- `src/tour/authoring.py:789` — `stops[-1] >= len(route.pois)`;
- `src/tour/authoring.py:797` — `len(stops) != len(route.pois)` (a dwell stop the
  stitch dropped — the code's own comment describes exactly this case);
- `src/tour/authoring.py:878-888` — provider model mismatch, `max_tokens` stop reason,
  unparseable payload;
- `src/api/routes/trips.py:226-227` — `_spend_precheck`'s own `planned_calls < 1`
  guard, which is inside the same `try`.

A stitch CAN drop a stop: `generate` threads `consumed_beat_ids` through
`_build_transit` and `_build_anchor_block`
(`src/tour/generation.py:348-368`), so a stop whose beats were all consumed by an
earlier transit contributes no sentence and its `stop_idx` never enters `by_stop`.
Pre-cutover that composed and returned 200; now it is a 422. And it is a PERMANENT
422 for that trip: compose_trip rebuilds the pick "from the poi ids persisted at
generate time — NEVER re-running selection", so the phone's "refused flavour -> try
another" UX (D2) hits the identical ValueError every time. The user's only exit is
regenerating the trip.

The pinned test's only discriminator between this branch and a real gate refusal is
the `_refusal_detail` caplog check (`tests/test_tour_authoring_gates.py:328-332`) —
a **test-side** guard. Nothing on the wire distinguishes them, so neither the phone
nor an operator can.

**Proposed repro (do not run alongside a sibling):** a hermetic unit that builds a
`Script` missing one dwell stop's sentences and calls
`plan_prebuilt_route_authoring`, asserting the `ValueError`; then the endpoint-level
version. Nearest existing target to point the verifier at:
`make test-file FILE="tests/test_tour_authoring_from_route.py"` (AC-4's seam suite) —
I expect it GREEN, which is the point: the shape is not covered there.

## F3 (MEDIUM, UNPROVEN) — the pinned AC-5 gate command is not skip-proof

Two independent skip paths guard the pinned node id:

- `@needs_neo4j` — `pytest.mark.skipif(not _neo4j_available())`, `tests/conftest.py:318`;
- the module `live_neo4j` fixture — `pytest.skip(...)` when `open_dev_driver()` returns
  None, `tests/test_tour_authoring_gates.py:82-89`.

`make test-file` is `uv run pytest "$(FILE)" -o addopts= -v` (`Makefile:143-149`) with
nothing that converts a skip into a failure. So `exit 0` from the pinned command does
not mean the gate ran. The evidence bundle's run shows `1 passed in 41.32s`, so THIS
run really executed — the finding is about the durability of the gate, not this
measurement. It is the "a /status that answers is not a service that routes" case:
`_ensure-dev-data` bringing 7687 up is not the same as 7687 holding the Paris content
this module needs.

Related fixture fragility, same negative space: the whole proof is conditional on the
current content of the **shared 7687 dev graph** — `len(before["stops"]) > 1` and
`inventor.stops_invented` non-empty are asserted precisely because the fixture tour
could stop exercising the clauses. CLAUDE.md states `make test-file` WRITES to that
shared graph, so a sibling session can move this gate's ground truth.

## F4 (LOW-MEDIUM, CONFIRMED coverage loss) — the deletion took a guard the docstring did not authorise losing

Deleting `tests/test_compose_gate_forbidden_scan.py` is authorised by its own
docstring, but the file held FIVE tests, not one. Two were guards, not pins:

- `test_the_forbidden_phrase_scan_does_catch_invented_content` — still covered:
  `grep -rl "new_proper_noun\|new_year" tests/` -> `tests/test_tour_validation.py`. No loss.
- `test_the_default_verifier_still_runs_the_full_scan` — asserted
  `build_full_verifier`'s `base_validator` default IS `validate_script`, explicitly
  "Guards against a 'fix' that... [makes] both paths blind". **`grep -rn "base_validator"
  tests/` now returns NOTHING.** I ran that grep at the stamped tree.

A surviving consumer of that default exists and D7 keeps it:
`scripts/tour_build.py:339` — `build_full_verifier(beat_sequence, beats_by_id)`.
The A4 path is immune (it passes `base_validator` explicitly and calls
`validate_script` by name at `src/tour/authoring.py:637`), which is exactly why
nothing in A4 would go red if that default were flipped.

Cheapest fix: re-home that one assertion (three lines) into
`tests/test_tour_validation.py` before A8 deletes the rest of the compose tests.

## F5 (MEDIUM advisory, forward risk) — "parity" is claimed while the cross-stop dedup that used to run INSIDE the gated loop is absent

`grep -n dedup src/api/routes/trips.py` returns nothing, and `author_prebuilt_route`
has no dedup. Pre-cutover, `_dedup_composed` ran inside `compose_script` **before**
verify (`git show HEAD:src/tour/compose.py`, line 805) with the comment "verify (with
the coverage baseline) runs next, so a drop that would lose a fact fails closed".

A5/AC-6 owns restoring it. The warning to record NOW: the only place the endpoint can
put dedup after this cutover is AFTER `author_prebuilt_route` returns — i.e. AFTER the
coverage gate — which silently drops the fail-closed ordering the old path had. If A5
does that, a dedup that deletes the last realisation of a claim ships unnoticed, and
A4's coverage gate will still be green.

---

## Attacks I ran that FAILED to break the claim

- **"provenance is 0 by construction"** — `author_prebuilt_route` never passes
  `chunk_text_by_slug`, so `build_full_verifier` no-ops provenance
  (`src/tour/compose_gate.py:340`). But the pre-cutover call site never passed it to
  `compose_script` either (`git show HEAD:src/tour/compose.py` compose_script
  signature; the old trips.py call passed only `client=` and
  `faithfulness_checker=`). PARITY HOLDS. Not an A4 regression.
- **"the coverage baseline was narrowed"** — `_certification_compose_requests`
  builds `beats_by_id` from `poi_beats` only (`src/tour/authoring.py:491`); the old
  `build_compose_request` did the identical thing (`git show
  HEAD:src/tour/compose.py:150`). Byte-for-byte the same baseline. REFUTED.
- **"traceability was loosened by `allowed_derived_source_ids`"** — the authorized set
  is derived from the stitch's own non-beat `source_id`s plus `GLUE_REFLECTION`
  (`src/tour/authoring.py:615-620`), a subset of `GLUE_LABELS`, so it is at least as
  strict as `validate_script`'s half. REFUTED.
- **"a second entry point persists composed narration ungated"** —
  `route_script_to_stops` has exactly two callers, both in `src/api/routes/trips.py`
  (generate at :529, compose at :844); `author_prebuilt_route` has exactly one product
  caller. `/trips/preview` and the batch/certification paths never write
  `ItineraryItem` narration. REFUTED.
- **"the new `except ValueError` shadows the gate branch"** —
  `ComposeVerificationError(Exception)` (`src/tour/compose_gate.py:38`) is not a
  `ValueError`, and it is caught first anyway. REFUTED.
- **"the coverage clause of the pinned test is satisfiable without the coverage
  gate"** — no. With `enforce_claim_coverage=False`, `_ClaimBlurringExecutor`'s output
  is traceable, carries no new proper noun/year, and passes the trusting checker, so
  the endpoint would return 200 and the clause would fail. The clause is genuinely
  load-bearing independent of its caplog guard. REFUTED.
- **"walk-past vignette beats are outside `beats_by_id`, so their content is ungated
  for faithfulness and coverage"** — TRUE (`src/tour/verify.py:212-216` continues when
  no cited beat resolves; `validate_source_traceability` accepts them because
  `known_beat_ids` includes `vignette_beats`). But identical before the cutover.
  Pre-existing hole, NOT introduced by A4.
- **"concurrent double-compose violates 'stops byte-unchanged'"** — the 409
  `already_composed` read and `mark_trip_composed` write are not atomic, so two
  in-flight composes can both proceed. Real, but it predates the cutover and the
  spend-precheck move belongs to A3/AC-7.
- **`make lint`** — re-ran it myself, exit 0.
