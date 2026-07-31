# Step A9 — hostile skeptic (opus), angle: NEGATIVE SPACE

**Stamp.** Verified against `HEAD = c8ec39690030901660c843d46910bedb40e84c13` (main) with the
Track A working tree applied: staged `64 files changed, 5501 insertions(+), 13838 deletions(-)`,
unstaged `15 files changed, 872 insertions(+), 1193 deletions(-)` — the unstaged diffstat matches
the developer's pasted A9 diffstat exactly, so I audited the same bytes the claim was made about.

**Verdict on the claim ("A9 satisfies AC-1 and AC-9"): CONFIRMED.** I attacked it from the
negative-space angle and could not refute the AC-1/AC-9 clauses. I did find one real, silent
side effect on a state of the world nothing in this ledger tests (F1), one scope/AC collision
(F2), and three advisories.

Only `make lint` was executed against shared-capable targets, per the concurrency constraint.
Everything else I ran is pure local file reading (`git grep`, `ast`, `json`).

---

## F1 (medium) — `Script.verify_report`'s deletion silently un-reads 13 saved tour artifacts

`src/tour/contract.py` `Script` is `model_config = ConfigDict(frozen=True, extra="forbid")`.
A9 removed the `verify_report` field from it. Thirteen artifacts already on disk still carry
that key:

```
data/london/tours/51-5080-0-1281-38min-1acbdb.json    ['verify_report']
data/london/tours/51-5080-0-1281-60min-284859.json    ['verify_report']
data/london/tours/51-5080-0-1281-60min-96ac58.json    ['verify_report']
data/london/tours/51-5080-0-1281-60min-ce64d7.json    ['verify_report']
data/paris/tours/48-8462-2-3464-75min-438633.json     ['verify_report']
data/paris/tours/48-8566-2-3522-90min-b30c46.json     ['verify_report']
data/paris/tours/48-8571-2-3592-90min-f110e0.json     ['verify_report']
data/paris/tours/48-8590-2-3620-90min-92ac2c.json     ['verify_report']
data/paris/tours/48-8606-2-3376-90min-aa521c.json     ['verify_report']
data/paris/tours/48-8635-2-3280-240min-624852.json    ['verify_report']
(13 total of 195 script-shaped JSON files scanned; every offending key is exactly `verify_report`)
```

`scripts/score_saved_tours.py:93-97` loads them with
`Script.model_validate(json.loads(path.read_text()))` inside `except Exception: return None`,
so those tours now land in the `UNREADABLE / UNSCOREABLE` bucket instead of raising. That
script is `make score-saved-tours` (Makefile:179-180, "$0, no DB, no containers") — the tool
that produced this project's rubric-calibration cohort figures.

Why no gate catches it: `data/*/tours/` is gitignored (`.gitignore:301`) and
`tests/test_tour_quality_rubric.py:1415,1535` *deliberately* excludes it
("machine-local output"). `make lint`, the pinned Playwright file, `_test-python`,
`_test-golden` and `_test-grade` all never read those files. The failure is swallowed by a
bare `except Exception`, so the only symptom is a shrinking cohort in a printed report.

This is precisely the untested state of the world: *artifacts written by the engine A9 just
deleted, sitting on disk, read by a $0 developer tool outside the bar.*

Proposed repro (safe: no DB, no container, no provider spend):
`make score-saved-tours SCORE_ARGS="--city paris"` → expect a non-empty
`UNREADABLE / UNSCOREABLE:` block naming the six paris files above.
I did not execute it (only `make lint` was permitted to me in this concurrent run); the two
preconditions — the on-disk keys and the `extra="forbid"` field set — I did execute and they
are pasted above.

Cheapest fix if accepted: keep `verify_report` out of the model but drop the key on load in
`score_saved_tours._load`, or re-narrow the `except Exception` so an unreadable artifact is
loud rather than a silent cohort shrink.

## F2 (low) — A9 changes the `/trips/preview` wire shape, which AC-8 says must not happen

A9 removes from the preview response: `quality.g4` (the whole block), `quality.stats.omission_stops_checked`,
`quality.stats.omission_findings`, and the `coverage_omission` entries in `quality.warnings`.
AC-8 states "the only behavior change on the preview surface is the documented echo-dedup pass."
These are observable wire keys disappearing, so the two statements cannot both be literally true.

Mitigating (I checked, so this is advisory, not a blocker): **no consumer breaks.**
`frontend/review.html` contains zero occurrences of `g4` or `omission`; `mobile/lib` (27 dart
files) does not parse `quality` at all, so AC-3's zero-mobile-diff holds functionally as well as
textually; `src/`, `tools/`, `fixtures/` and `data/` contain zero `g4` references. The right
resolution is to amend AC-8's wording (or record a carry-forward), not to restore the blocks.

## F3 (low) — the `review.html` half of A9 has no anti-over-deletion guard and no behavioral test

Two independent gaps stack:

1. The A9 assertion for the frontend is a substring-*absence* check
   (`stale_labels = [label for label in DEAD_WORKBENCH_LABELS if label in review_html]`) — the
   single text match in a file whose own docstring says "Structure is read with `ast` and
   `subprocess`, never a text/regex match." It stays GREEN if the *surviving* labels
   (`'Claude Opus 4.8'`, `composed`, `refused`, `basic_available`, `stitched`) are deleted too,
   or if `review.html` is emptied entirely. The eligibility half of this same step has an
   explicit anti-over-deletion set (`SURVIVING_ELIGIBILITY_NAMES`); the frontend half has none.
2. The pinned gate `tests/test_workbench_review_regressions.py` is 16 tests named
   `test_defect1..test_defect9` covering POI upload/merge/beats/TTS/lens flows. It asserts
   nothing about narrator or compose-status rendering. No test anywhere in `tests/` asserts the
   strings `Claude Opus 4.8`, `Narrator:` or the compose-status sentences.

So the frontend edit's proof is "the page still parses and the merge flows still work". That
is not nothing, but an over-deletion in `_providerLabel`/`_composeStatusLabel` is invisible to
every gate this step runs.

## F4 (low) — comments left contradicting the code A9 just shipped

- `src/api/models/trips.py:348-350` still documents `provider` as
  `('anthropic' | 'openai')`, "so the workbench can label an Opus-vs-ChatGPT comparison" —
  the exact label A9 deleted from `review.html`, under D9 loss 1.
- `src/tour/anthropic_client.py:4-6` still cites its founding bare-client sites as
  `compose.py:536`, `compose_correct.py:212`, `factcheck.py` x3 and `claim_repetition.py:349`.
  All four files are deleted by Track A.

CLAUDE.md: "A doc that contradicts the code gets corrected or deleted. Never left."
`anthropic_client.py` is D8-KEPT, so this needs an explicit ruling rather than a silent edit.

## F5 (low, pre-existing — NOT an A9 regression) — the money-guard "whole set" comment is false

`tests/test_tour_one_engine.py:70-76` claims the two surviving arms are "the WHOLE set of
billing clients the tree can still build." They are not: `src/tour/certification_provider.py`
imports `certification_compose_client`, `src/onboard/beat_draft.py:275` imports `compose_client`,
and `src/tour/verify.py:115`, `src/tour/glue_client.py:102`, `src/api/routes/feedback.py:175`
each build `judge_client` — none of which the fixture arms. I checked `git show HEAD:tests/conftest.py`
and the guard never armed them there either, so A9 did not shrink real coverage; the equality
assertion remains a valid drift detector. Only the justifying comment overstates, and AC-7's
"the non-live suite makes zero paid calls" rests on something broader than these two arms.

---

## Attacks that FAILED to break the claim

Listed so the CONFIRMED means something.

1. **`make lint` re-run by me** → exit 0, `All checks passed!`. Not taken on faith.
2. **Static cross-module import resolution over every tracked `.py` file** (my own AST script:
   resolve every `from src.* import NAME` / `import src.*` against the tree, absolute and
   relative): `clean: every src.* import resolves`, exit 0. No dangling importer of
   `compose_correct`, `verify_gate`, `claim_repetition`, or of the four deleted dependency hooks —
   the class of break `make lint` (F821 is intra-module) would NOT catch and the pinned A9 gate
   does not run either.
3. **Python files outside the test's `SCANNED_ROOTS`** (`src`, `scripts`, `tests`, `tools`) that
   could import a deleted module and keep the test green: `git ls-files '*.py'` filtered — there
   are none. The blind spot exists but is currently empty.
4. **Were the three deleted eligibility predicates actually dead?** Checked `HEAD:`, `:` (index)
   and worktree copies of `src/api/routes/trips.py`: no call site in any of the three. They were
   dead before this ledger began, not made dead by it. Genuine dead-code removal.
5. **Could the `git ls-files` tracked-check be gamed by an unstaged deletion?** No — the
   deletions are staged (`D ` in `git status`), and `git ls-files` reads the index, making the
   assertion *stricter* than a disk-only check, not weaker.
6. **Tracked fixtures that could turn `_test-golden`/`_test-grade` RED on the removed field/keys:**
   `fixtures/tour_golden/*.json` carry neither `verify_report` nor `g4`; a repo-wide scan of all
   script-shaped JSON found offenders only under the gitignored `data/*/tours/` (that is F1).
7. **Phone breakage from the preview shape change:** `mobile/lib` never parses `quality`,
   `g4`, `omission*`, `composed_partial` or `verify_report`.
8. **Legacy `composed_partial` still arriving from a persisted trip:** `_composeStatusLabel`
   falls back `[s] || s || '—'`, so it degrades to the raw key rather than crashing — and
   `compose_status` is computed fresh per request in `trips.py` (`"composed"` / `"basic_available"`),
   never read back out of Neo4j, so no live source of the removed value exists.
9. **`_providerLabel` losing the `'openai'` branch regressing a TTS-provider display:** its only
   call site passes `data.provider` (the narrator), not a voice provider. The comment's claim
   holds.
10. **Did A9 quietly drop a decision guard?** It deletes
    `test_g4_is_deliberately_dark_and_never_billed`, which asserted `check_tour_repetition(` was
    absent from `trips.py`. The replacement (module deleted + no importer anywhere + the judge's
    dependency hook gone) is strictly stronger than the string check it replaced. Not a
    weakening.
