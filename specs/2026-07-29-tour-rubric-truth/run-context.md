# Run context: tour-rubric-truth (specs/2026-07-29-tour-rubric-truth)

## Tier
2

## approved_by_human
`true` (as literally recorded in `state.json`). `approved_at`: `2026-07-30T02:24:53Z`.
`approval_note`: "Owner said 'go' in chat after the full presentation. The go bundles: C8 stays 850 +
standing-position unit ruling (closes the open C8-unit question), C9 unchanged, C11 demoted to
report-only stat, overlap floors restated at 85% of resolved overlap, and the runs-first-from-worktree
order."

## Baseline (from state.json, verbatim)
- lint: `make lint -> All checks passed! (2026-07-29)`
- commit: RUNS FIRST, FROM A WORKTREE: `$HOME/git/ondoway-rubric`, branch cut from current main (with
  both approved spec ledgers committed) BEFORE the sibling consolidation ledger runs. The engine is
  invoked with repo=`$HOME/git/ondoway-rubric`. On completion: owner reviews + commits on the branch,
  merge to main --ff-only, delete the worktree + branch, and only then does the sibling start on the
  now-golden-green main. Never run concurrently with the sibling or any test suite (shared
  7687/7688/Valhalla).
- note: `make _test-golden` and the ile grade node are RED at baseline BY DESIGN — this ledger's whole
  job is to turn them green honestly. Root cause (measured): fixtures pin per-database ephemeral UUIDs
  (`b.id`, minted by `randomUUID()` at upload) — 0/65 exist in `data/paris/beats.json`, whose durable
  ids are slugs (`b.beat_id` / `stable_beat_id`). Never re-record fresh UUIDs (that laundering already
  happened once, commit 3d62713d) and never lower a floor to whatever the run produces.

## Decisions (from state.json, verbatim)
- **D1-durable-ids**: Fixtures re-key to `expected_stable_beat_ids` (slugs). The golden tests and
  grade test map generated `source_id -> stable_beat_id` via the `BeatSequence` they already hold
  (`BeatRef` carries both fields). Zero production-code change.
- **D2-resolution-method**: Tag->beat resolution re-runs the fixtures' own `script_body` method from
  the DOCUMENTS, exact-slug-suffix FIRST (24/93 resolve uniquely today), similarity only as fallback.
  The repair-input recovered from git 4ea26683 holds 64 DISTINCT machine-similarity resolutions (2
  known-conflicting) — they are hints, NOT human-vetted truth: similarity has measured wrong-beat
  failures at 0.909 and 1.000. PdV additionally needs its 25 fixture keys re-keyed to the document's
  real tags (only 8 match verbatim today). Unresolved tags go into a human-review queue file; nothing
  is silently auto-resolved.
- **D3-invariants-over-resolved-subset**: The internal-consistency test asserts over the RESOLVED
  subset: resolved ids are unique, all exist in `data/paris/beats.json`, count matches the restated
  `expected_beat_count`, and `expected_tag_resolution` covers the reachable set. It does NOT demand
  100% tag resolution — the queue is a first-class output.
- **D4-c8-ruling**: C8 KEEPS cap 850 per engine stop — the standing in-repo measurement
  (`quality_rubric.py:59-62`) rejected 750 because the certified-good corpus has stops at 757/761/808,
  and moving the cap re-blocks them for zero gain on new output (the engine's 270s dwell ceiling
  renders ~750 max anyway). ADDED: the unreachability pin test (a clean C8 on fresh output is the
  dwell ceiling at work, never evidence of a quality win), and the unit ruling recorded in the two
  decision-forcer tests: the human-reference calibration unit is the STANDING POSITION (human max
  367 — all pass); declared-stop aggregates (Conciergerie 901, Notre-Dame 1595) are eye-prose spans
  over many positions and are not a stop the engine builds. This CLOSES the open C8-unit question.
- **D5-c9-c11**: C9 stays EXACTLY as-is (WARN, cap 20): `quality_rubric.py:80-85` documents it as
  sound — it ranks the owner's gold (19.11) above machine output (median 23.2) and matches the online
  12-18-word ear-prose guidance; it fires on the empirical references because they are guidebook
  EYE-prose, recorded as by-design in the calibration expectation test. C11 is demoted to a
  report-only stat: it fires on 100% of human-vetted references but only 8-11% of machine tours — an
  inverted signal; the new decision-forcer test records the measurement. Net rubric behavior change
  across this whole ledger: C11 stops emitting findings. Nothing else moves. This is the anti-spin
  worst case honored: the algorithm and the rubric's blockers ship as-is.
- **D6-floors**: Overlap floors are restated deliberately against the resolved set (recommendation:
  floor = 85% of the resolved-tag overlap measured at repair time; today's floors of 42.6%/27.8%
  permit 57-72% silent drift and cannot fail). `GRADE_BASELINE` 0.65 is reconfirmed against the
  repaired fixtures. Owner may override the numbers at approval; approving the plan approves the
  recommendation.
- **D7-disjointness**: This ledger touches NO file the sibling consolidation ledger touches. The one
  shared file (`specs/2026-07-19-tour-quality-standard/01-standard.md`) is resolved by sequencing:
  THIS ledger edits §4/§5 rows first (it runs first and merges); the sibling deletes §6b afterwards on
  a main that already contains those edits. No concurrent edits, no merge conflict.
  `quality_rubric.py`, `selection.py` (comment only), `spatial_check.py` are this ledger's alone.

## Acceptance criteria (verbatim)
- **AC-1**: Given both golden fixtures, then every `expected_stable_beat_id` is a slug that exists in
  `data/paris/beats.json`, zero UUID-shaped ids remain, and the internal-consistency test over the
  resolved subset is green (unique, counted, tag-resolution-covered).
- **AC-2** (negative): Given the resolution rerun, then every exact-slug-suffix match is used before
  any similarity fallback, the 2 known-conflicting repair-input mappings are re-adjudicated rather
  than inherited, and a human-review queue file exists listing exactly the still-unresolved tags — no
  silent auto-resolution.
- **AC-3** (negative): Given the live dev graph (7687) and Valhalla, then
  `tests/test_tour_golden_ile.py::test_ile_golden_overlap`,
  `tests/test_tour_golden_pdv.py::test_pdv_golden_overlap` and
  `tests/test_tour_grade.py::test_broken_golden_drops_below_baseline` are green, with floors restated
  per D6 — never lowered to whatever the run produced.
- **AC-4**: Given the C8 ruling, then the cap is unchanged at 850, the unreachability pin test is green
  (`MAX_DWELL_AUDIO_SECONDS=270` makes C8 inert on fresh engine output), and the two former
  decision-forcer tests record the standing-position unit ruling instead of forcing.
- **AC-5** (negative): Given the C9/C11 ruling, then C9's behavior and cap are byte-unchanged with the
  eye-prose firing recorded as by-design, C11 emits a report stat and zero Findings, and
  `make score-human-tours` shows zero BLOCKER findings on the human references at position granularity
  while the gold text still passes everything applicable.
- **AC-6** (negative): Given the stale claims found by measurement, then `spatial_check.py`'s
  docstring no longer claims S1 is wired into `score_tour`, `selection.py`'s drift comment is
  corrected, and standard §4/§5 rows match the shipped constants — no doc contradicts the code.

criteria_uncovered: **none** — every AC (AC-1..AC-6) is cited by at least one step's `criterion_ids`
(B1: AC-1, B2: AC-2, B3: AC-3, B4: AC-4, B5: AC-5+AC-6).

## Steps and pinned gate commands

| Step | test_command (pinned) | command_valid | gate_commands |
|---|---|---|---|
| B1 | `make test-file FILE="tests/test_tour_golden_consistency.py::test_fixture_ids_are_durable_slugs_and_internally_consistent"` | true | `make lint` |
| B2 | `make test-file FILE="tests/test_tour_golden_consistency.py::test_every_resolved_tag_exists_in_the_corpus"` | true | `make lint` |
| B3 | `make test-file FILE="tests/test_tour_golden_ile.py::test_ile_golden_overlap"` | true | `make lint` |
| B4 | `make test-file FILE="tests/test_tour_quality_rubric.py::test_c8_cannot_fire_on_engine_output_and_the_unit_ruling_is_recorded"` | true | `make lint` |
| B5 | `make test-file FILE="tests/test_tour_quality_rubric.py::test_c11_reports_a_stat_but_emits_no_finding"` | true | `make lint` |

All five match the required shape exactly: `make test-file FILE="<path>::<node id>"`, no bare `-k`, no
`LIVE=1`. `test-file` exists live at `Makefile:141`. `tests/test_tour_golden_consistency.py` does not
exist yet on disk — that is expected: it is B1's own deliverable, not a pre-existing target being
mis-cited (checked against the `state.json` schema's stale-target hazard, e.g. the now-gone
`test-local`/`test-collect`).

No step touches `mobile/` or `frontend/`, so no step needs `make flutter-analyze` or a targeted
workbench node id. Every step touches `tests/` (and B4/B5 also touch `src/`), so every gate is
`make lint` (`Makefile:104-106` covers `src/ tests/ scripts/{5 files}`). Never `make test`, `make audit`,
`make test-live`, or `make test-workbench` in a per-step gate — those are phase/close gates only.

## Infra probe (read-only, 2026-07-29)
- `docker ps`: `ondoway-neo4j` (dev, 7687, healthy), `ondoway-neo4j-test` (7688, healthy),
  `ondoway-neo4j-workbench` (7689, healthy), `ondoway-valhalla` (8002, healthy) — all four containers
  up.
- HTTP reachability confirmed: dev 7474→200, test 7475→200, workbench 7476→200, Valhalla
  `/status`→200. This confirms the services *answer*, not that `make test-file` necessarily routes to
  them correctly (`config/profiles/{local,test,workbench}` exist and are the presumed routing, but were
  not exercised end-to-end here).
- `make lint`: `All checks passed!` — clean.
- `node .claude/team-engine.test.js`: exit 0, `all 91 checks passed across 17 pathological shapes.`

## infra booleans (for the ledger)
- test_db: true (7688 container healthy, HTTP 200)
- dev_data: true (7687 container healthy, HTTP 200; presence of seeded dev data not independently
  re-verified beyond container reachability)
- valhalla: true (8002 `/status` → 200)
- lint_clean: true
- engine_guard: true (`node .claude/team-engine.test.js` exit 0)
