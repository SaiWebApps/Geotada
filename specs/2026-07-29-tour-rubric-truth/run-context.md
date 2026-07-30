# Tour rubric truth — run context

**Tier 2**, set mechanically: touches `src/tour/quality_rubric.py`, `src/tour/spatial_check.py`,
`src/tour/selection.py` (comment) — `src/tour/` row. Panel P=2, acceptance runs.

**approved_by_human: false** — not approved until the owner says go in chat.

**Runs from a WORKTREE:** `$HOME/git/ondoway-rubric`, branch cut from main only AFTER the
sibling ledger `specs/2026-07-29-one-true-tour-algorithm` completes and its commits land.
The engine is invoked with `repo=$HOME/git/ondoway-rubric`. Strictly serial with the
sibling and with any other suite (shared 7687/7688 Neo4j + Valhalla; `make test-file` starts
and writes to them). After the close: merge to main `--ff-only` (rebase in the worktree
first if main moved), then DELETE the worktree and its branch (Worktree Cleanup rule).

**File disjointness with the sibling is a hard invariant** (state.json D7): this ledger
owns quality_rubric.py, spatial_check.py, selection.py, the golden fixtures + golden/grade
tests, and standard §4/§5. It must not touch authoring.py, trips.py, or anything the
sibling edits. The standard's §6b will already be deleted by the sibling — do not resurrect.

**The one-sentence design:** re-key the golden fixtures from per-database ephemeral UUIDs
to durable slug ids and re-resolve their tags honestly (exact-suffix first, similarity
fallback, human queue for the rest), turning `_test-golden`/`_test-grade` green without
laundering; then record three measured rubric rulings — C8 unchanged at 850 with its
unreachability pinned and the standing-position unit ruling closing the open question, C9
unchanged and documented as by-design on eye-prose, C11 demoted to a report-only stat (the
only behavior change in the whole ledger).

**Anti-spin is a rule of this ledger, not a vibe:** the algorithm is NOT touched, no
threshold is tuned iteratively, every change carries a measurement already recorded in
state.json's decisions, and the worst case — everything ships as-is with only the fixtures
repaired — is an acceptable outcome the owner has pre-approved.

## Decisions (verbatim from state.json)

- **D1-durable-ids:** Fixtures re-key to expected_stable_beat_ids (slugs). The golden tests
  and grade test map generated source_id -> stable_beat_id via the BeatSequence they already
  hold (BeatRef carries both fields). Zero production-code change.
- **D2-resolution-method:** Tag->beat resolution re-runs the fixtures' own script_body method
  from the DOCUMENTS, exact-slug-suffix FIRST (24/93 resolve uniquely today), similarity only
  as fallback. The repair-input recovered from git 4ea26683 holds 64 DISTINCT
  machine-similarity resolutions (2 known-conflicting) — they are hints, NOT human-vetted
  truth: similarity has measured wrong-beat failures at 0.909 and 1.000. PdV additionally
  needs its 25 fixture keys re-keyed to the document's real tags (only 8 match verbatim
  today). Unresolved tags go into a human-review queue file; nothing is silently
  auto-resolved.
- **D3-invariants-over-resolved-subset:** The internal-consistency test asserts over the
  RESOLVED subset: resolved ids are unique, all exist in data/paris/beats.json, count matches
  the restated expected_beat_count, and expected_tag_resolution covers the reachable set. It
  does NOT demand 100% tag resolution — the queue is a first-class output.
- **D4-c8-ruling:** C8 KEEPS cap 850 per engine stop — the standing in-repo measurement
  (quality_rubric.py:59-62) rejected 750 because the certified-good corpus has stops at
  757/761/808, and moving the cap re-blocks them for zero gain on new output (the engine's
  270s dwell ceiling renders ~750 max anyway). ADDED: the unreachability pin test (a clean C8
  on fresh output is the dwell ceiling at work, never evidence of a quality win), and the
  unit ruling recorded in the two decision-forcer tests: the human-reference calibration unit
  is the STANDING POSITION (human max 367 — all pass); declared-stop aggregates (Conciergerie
  901, Notre-Dame 1595) are eye-prose spans over many positions and are not a stop the engine
  builds. This CLOSES the open C8-unit question.
- **D5-c9-c11:** C9 stays EXACTLY as-is (WARN, cap 20): quality_rubric.py:80-85 documents it
  as sound — it ranks the owner's gold (19.11) above machine output (median 23.2) and matches
  the online 12-18-word ear-prose guidance; it fires on the empirical references because they
  are guidebook EYE-prose, recorded as by-design in the calibration expectation test. C11 is
  demoted to a report-only stat: it fires on 100% of human-vetted references but only 8-11%
  of machine tours — an inverted signal; the new decision-forcer test records the
  measurement. Net rubric behavior change across this whole ledger: C11 stops emitting
  findings. Nothing else moves. This is the anti-spin worst case honored: the algorithm and
  the rubric's blockers ship as-is.
- **D6-floors:** Overlap floors are restated deliberately against the resolved set
  (recommendation: floor = 85% of the resolved-tag overlap measured at repair time; today's
  floors of 42.6%/27.8% permit 57-72% silent drift and cannot fail). GRADE_BASELINE 0.65 is
  reconfirmed against the repaired fixtures. Owner may override the numbers at approval;
  approving the plan approves the recommendation.
- **D7-disjointness:** This ledger touches NO file the sibling consolidation ledger touches.
  The one shared file in early drafts (specs/2026-07-19-tour-quality-standard/01-standard.md)
  is resolved by sequencing: the sibling deletes §6b first on main; this ledger edits §4/§5
  rows afterwards in the worktree. quality_rubric.py, selection.py (comment only),
  spatial_check.py are this ledger's alone.

## Acceptance criteria (verbatim from state.json)

- **AC-1:** Given both golden fixtures, then every expected_stable_beat_id is a slug that
  exists in data/paris/beats.json, zero UUID-shaped ids remain, and the internal-consistency
  test over the resolved subset is green (unique, counted, tag-resolution-covered).
- **AC-2** (negative): Given the resolution rerun, then every exact-slug-suffix match is used
  before any similarity fallback, the 2 known-conflicting repair-input mappings are
  re-adjudicated rather than inherited, and a human-review queue file exists listing exactly
  the still-unresolved tags — no silent auto-resolution.
- **AC-3** (negative): Given the live dev graph (7687) and Valhalla, then
  tests/test_tour_golden_ile.py::test_ile_golden_overlap,
  tests/test_tour_golden_pdv.py::test_pdv_golden_overlap and
  tests/test_tour_grade.py::test_broken_golden_drops_below_baseline are green, with floors
  restated per D6 — never lowered to whatever the run produced.
- **AC-4:** Given the C8 ruling, then the cap is unchanged at 850, the unreachability pin
  test is green (MAX_DWELL_AUDIO_SECONDS=270 makes C8 inert on fresh engine output), and the
  two former decision-forcer tests record the standing-position unit ruling instead of
  forcing.
- **AC-5** (negative): Given the C9/C11 ruling, then C9's behavior and cap are byte-unchanged
  with the eye-prose firing recorded as by-design, C11 emits a report stat and zero Findings,
  and make score-human-tours shows zero BLOCKER findings on the human references at position
  granularity while the gold text still passes everything applicable.
- **AC-6** (negative): Given the stale claims found by measurement, then
  spatial_check.py's docstring no longer claims S1 is wired into score_tour, selection.py's
  drift comment is corrected, and standard §4/§5 rows match the shipped constants — no doc
  contradicts the code.

`criteria_uncovered` = [] — every AC id (AC-1..AC-6) is claimed by at least one step
(B1=AC-1, B2=AC-2, B3=AC-3, B4=AC-3, B5=AC-4, B6=AC-5+AC-6).

## Baseline

- `make lint` -> `All checks passed!` (re-verified 2026-07-29, this preflight run).
- `commit`: RUNS FROM A WORKTREE `$HOME/git/ondoway-rubric`, branch cut from main AFTER
  `specs/2026-07-29-one-true-tour-algorithm` completes and is committed. Never run
  concurrently with the sibling ledger or any test suite (shared 7687/7688/Valhalla).
- `make _test-golden` and the Île grade node are RED at baseline BY DESIGN — this ledger's
  whole job is to turn them green honestly. Root cause (measured): fixtures pin
  per-database ephemeral UUIDs (b.id, minted by randomUUID() at upload) — 0/65 exist in
  data/paris/beats.json, whose durable ids are slugs (b.beat_id / stable_beat_id). Never
  re-record fresh UUIDs (that laundering already happened once, commit 3d62713d) and never
  lower a floor to whatever the run produces.
- Infra probe (this preflight run): `docker ps` shows `ondoway-neo4j` (7687, dev),
  `ondoway-neo4j-test` (7688, test), `ondoway-neo4j-workbench` (7689, workbench) and
  `ondoway-valhalla` (8002) all up. `node .claude/team-engine.test.js` exits 0 (91/91 checks,
  17 pathological shapes). `make lint` clean. Containers answering does not by itself prove
  dev-data seeding or Valhalla routing for this specific fixture set — that is exercised the
  first time a step actually runs `make test-file`.

## Pinned gate commands (derived from each step's files[])

All six steps' `files[]` are confined to `fixtures/`, `tests/`, `src/tour/`, and
`specs/2026-07-19-tour-quality-standard/01-standard.md` — no `mobile/` or `frontend/` files
in any step, so no step needs `make flutter-analyze` or a workbench node id. Every step's
gate is:

- **B1** (`fixtures/tour_golden/*.json`, `fixtures/tour_golden/repair-input`,
  `tests/test_tour_golden_consistency.py`, `tests/test_tour_golden_ile.py`,
  `tests/test_tour_golden_pdv.py`, `tests/test_tour_grade.py`): `make lint`
- **B2** (`fixtures/tour_golden/*.json`, `fixtures/tour_golden/repair-input`,
  `tests/test_tour_golden_consistency.py`): `make lint`
- **B3** (`fixtures/tour_golden/ile_oneway_90min.json`,
  `tests/test_tour_golden_ile.py`): `make lint`
- **B4** (`fixtures/tour_golden/pdv_round_trip_60min.json`,
  `tests/test_tour_golden_pdv.py`, `tests/test_tour_grade.py`): `make lint`
- **B5** (`src/tour/quality_rubric.py`, `src/tour/selection.py`,
  `tests/test_tour_quality_rubric.py`, `specs/.../01-standard.md`): `make lint`
- **B6** (`src/tour/quality_rubric.py`, `src/tour/spatial_check.py`,
  `tests/test_tour_quality_rubric.py`, `specs/.../01-standard.md`): `make lint`

Never `make test`, `make audit`, `make test-live`, or `make test-workbench` as a per-step
gate — those are minutes-long shared-resource shards, reserved for phase/close gates only.

Executor notes:
- Never re-record UUIDs into fixtures and never lower a floor to whatever the run produced
  (both launderings are named and banned in state.json).
- repair-input is recovered via `git checkout 4ea26683 -- fixtures/tour_golden/repair-input`
  (shared object store — works in the worktree). Its 64 resolutions are machine hints, not
  truth.
- B3/B4 need the live 7687 dev graph + Valhalla (make test-file provides both).
- Editing quality_rubric.py can redden tests/test_spatial_check.py:651-691 (source-text
  inspection) — keep `check_script_spatial_claims(` unwired.
