# Step B1 — hostile skeptic (negative space)

- Repo: `/Users/sairambkrishnan/git/ondoway-rubric`
- Verified against commit: `b542af0b` ("fix(deps): restore the public-PyPI lock…") + uncommitted working tree
- Reviewed: 2026-07-29
- Angle: negative space — untested states of the world, other entry points, infra side effects
- Verdict: **REFUTED** (the narrow assertion re-derives; the step as shipped is not safe to sign off)

## 0. What re-derived

I executed the real test function in-process (`.venv/bin/python`, no DB, no container, no provider) —
`tests.test_tour_golden_consistency.test_fixture_ids_are_durable_slugs_and_internally_consistent`
called directly with the shipped fixtures and the real `data/paris/beats.json` corpus set: **GREEN**.
`make lint`: exit 0, `All checks passed!`. The 2 known-conflicting repair-input hints
(`cavaille_coll_organ` @0.909, `judgement_day_central_portal` @1.000 — the two the measured
wrong-beat memory names) were **re-adjudicated, not inherited**. Credit where due.

I could not re-run the pinned `make test-file` gate: a sibling skeptic is live and that target starts
7688/7687/Valhalla. And the working tree **mutated under me mid-review** (see F1), so the QA line
"working tree exactly matches the developer's stated 12-file diff — no residue" is no longer true of
the tree on disk.

## F1 — CONFIRMED (high): an out-of-scope, ungated edit to `scripts/tour_golden_diff.py` puts an unimportable module in the shipped Docker image

`scripts/tour_golden_diff.py` was **not** in the claim's 12-file evidence diff. It appeared in
`git status` during this review (`mtime Jul 29 19:55:30 2026`), and it is in **no step's `files` list**
in `state.json` (B1: fixtures ×2, repair-input, 4 test files. Not this).

It now carries a module-level `from tests.test_tour_golden_consistency import generated_stable_beat_ids`.
`tests/` is not COPY'd by the Dockerfile (`COPY src/`, `scripts/`, `frontend/`, `requirements.txt`) and
is explicitly excluded at `.dockerignore:16` (`tests/`). So the image ships a `scripts/` module that
raises `ModuleNotFoundError: No module named 'tests'` on import — the exact failure class
`tests/test_docker_image_contents.py` was written for after deploy `dep-d9e0ls3bc2fs73fo4gh0`.

The guard cannot see it: `_first_party_imports()` walks `SRC.rglob("*.py")` only. Pointing the repo's
**own** scanner at `scripts/` reports the break. Nor does `make lint` see it — `Makefile:105-108`
lints `src/ tests/` plus **eight named** script files, and `tour_golden_diff.py` is not one of them.
B1's only gate is `make lint`. The edit is therefore entirely ungated by construction.

Repro (executed, no shared state):
```
cd /Users/sairambkrishnan/git/ondoway-rubric && .venv/bin/python - <<'EOF'
import ast, sys
from pathlib import Path
sys.path.insert(0, "/Users/sairambkrishnan/git/ondoway-rubric")
from tests.test_docker_image_contents import REPO_ROOT, _copied_roots, _dockerignored
copied = _copied_roots(); missing = {}
for path in (REPO_ROOT/"scripts").rglob("*.py"):
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import): names=[a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level==0: names=[node.module.split(".")[0]]
        else: continue
        for n in names:
            if n in sys.stdlib_module_names: continue
            if (REPO_ROOT/n).is_dir() or (REPO_ROOT/f"{n}.py").is_file():
                if n not in copied or _dockerignored(n): missing.setdefault(n,set()).add(str(path.relative_to(REPO_ROOT)))
print(missing)
EOF
```
Output: `{'tests': ['scripts/tour_golden_diff.py']}`

Fix direction: move `generated_stable_beat_ids` into `src/tour/` (or a `scripts/` helper) and import it
from both sides; extend `test_docker_image_contents.py` to scan `scripts/` as well as `src/`; add
`scripts/tour_golden_diff.py` to the `make lint` target.

## F2 — CONFIRMED (high): `grade.py` still keys on the DELETED `expected_beat_ids` and fails OPEN to a perfect score

B1 removed `expected_beat_ids` from both fixtures. `src/tour/grade.py:75` still reads it, with a
`.get("expected_beat_ids", [])` default, and `_recall` (`grade.py:52-56`) returns **1.0 when nothing is
expected**. Grading a re-keyed fixture directly therefore awards a perfect beat_overlap for an engine
that emitted **zero beats**. The only thing holding this honest is one ad-hoc shim dict literal at
`tests/test_tour_grade.py:138` (`{**fixture, "expected_beat_ids": fixture["expected_stable_beat_ids"]}`).
Nothing tests the un-shimmed path; one forgotten kwarg in any future caller silently converts the
golden bar into a pass — the precise laundering the ledger's baseline note forbids.

Repro (executed, no shared state):
```
cd /Users/sairambkrishnan/git/ondoway-rubric && .venv/bin/python -c "
import json,sys; sys.path.insert(0,'.')
from src.tour.grade import grade_tour
fx=json.load(open('fixtures/tour_golden/ile_oneway_90min.json'))
print(grade_tour(generated_poi_names=fx['expected_pois'], generated_beat_ids=[],
  generated_spine_area=fx['expected_spine_area'], validation_passed=True, fixture=fx).breakdown())"
```
Output: `score=1.000 (poi_recall=1.00 beat_overlap=1.00 spine=1 validation=1) PASS @ baseline 0.65`

Fix direction: make `grade_tour` read `expected_stable_beat_ids` and **require** the key (KeyError, not
`.get`), or make `_recall` return 0.0 on an empty expected set. Delete the shim.

## F3 — CONFIRMED (medium-high): the B1 guard is GREEN on a fixture that resolves NOTHING

Executed the real test function with `expected_tag_resolution={}`, every document tag moved to
`unresolved_tags`, `expected_stable_beat_ids=[]`, `expected_beat_count=0`: **GREEN**. D3 says the guard
"does not demand 100% tag resolution"; it also does not demand *any*. Combined with F2, "queue
everything" scores 1.000. There is no coverage floor anywhere in AC-1.

## F4 — CONFIRMED (medium): the guard cannot tell a correct resolution from a wrong one

Executed with every Île tag re-pointed at a Place-des-Vosges beat and vice versa (counts and
uniqueness preserved): **GREEN**. Example accepted mapping:
`F:bell_trapdoor_pillars -> paris_place_des_vosges_dark_history_pariswalks_richelieu_ban_six_man_duel`
(a Notre-Dame bell tag resolving to a Richelieu duelling ban). Invariant 2 checks corpus **membership**
only, never that the beat has anything to do with the tag.

Live relevance, measured on the shipped fixtures: **30/51** Île and **18/24** PdV resolutions have **no**
exact-slug-suffix candidate in the corpus — they came from similarity or by hand. **14** of them are
inherited verbatim from `repair-input` at machine similarity **< 0.95** (lowest 0.805,
`V:bouquinistes_seasoning`), i.e. produced by the method this repo has measured picking a WRONG beat at
0.909. AC-1's *text* is satisfied; AC-1's *purpose* ("durable ids", not "plausible ids") is not proven
for those 48 mappings by anything in B1.

## F5 — CONFIRMED (medium): B1 silently weakens the Île overlap bar by 30% before B3 restates anything

Île's expected set went 47 unique ids → **31**; PdV's 18 → **21**. Both floors are unchanged literals:
`OVERLAP_REGRESSION_FLOOR = 20 / 47` (`test_tour_golden_ile.py:33`) and `5 / 18`
(`test_tour_golden_pdv.py:37`). At 42.55% of 31, Île now needs **14** hits where it needed **20** —
a 30% weaker absolute bar, achieved purely by shrinking the denominator, with no code change. The
denominators `47` and `18` now name sets that exist nowhere in the repo. D6 promises restatement in B3;
B1 is nonetheless being signed off today with the bar already lowered.

## F6 — Advisory: no bound on the `structurally_unreachable` escape hatch, and two coupling holes

- One bulk group (`{"tags": [20 resolved Île tags], "reason": "the algorithm just does not"}`) shrinks
  Île's expected set **31 → 11** and the test stays **GREEN** (executed).
- Flipping every PdV excuse group to `_status: "RECOVERED"` also stays **GREEN** (executed). The
  `_status` skip is an unaudited toggle on what counts as reachable.
- The test hard-reads `Docs/tour-builder/empirical-tours/{01-place-des-vosges,02-ile-de-la-cite-notre-dame}.md`,
  which appear in **no** step's `files` list, and `document_tags` raises on any parse-shape change. B1
  goes red on a doc edit that has nothing to do with the fixtures.

## F7 — Advisory: 21 corpus slugs are never uploaded to any graph, and B1 would accept them as durable

`scripts/db_parity.py:80-82` uploads only `beat_id`-bearing, non-blocked, POI-linkable beats:
1562 slugs in `data/paris/beats.json`, **1541** reach the graph, **21 never do**. B1 validates pins
against the unfiltered file, so a pin on one of those 21 would be green here and unreachable at
runtime forever. Measured: **0** are pinned today. Latent, worth an assertion against the linkable set.

## F8 — Advisory: B1's own gate is not read-only, and serialization is not actually holding

`make test-file` pulls `_ensure-test-db`/`_ensure-dev-data`/`valhalla-up` (`Makefile:144-146`) for a test
that needs no database, and `scripts/ensure_dev_data.py:56-69` **re-deploys `data/` into the shared 7687
dev graph** on any parity drift. The run-context's mitigation is "never run concurrently with the
sibling" — and the working tree changed under me during this very review (F1), so that discipline is
demonstrably not being held.

## Attacks that FAILED to break the claim

- Executed the real test function on the shipped fixtures: GREEN. The pass is driven by fixture data.
- Exact-slug-suffix rule (D2): searched all 75 resolutions for a case where an exact-suffix candidate
  existed in the corpus but a different beat was pinned — **0 violations** on both fixtures.
- The 2 known-conflicting repair-input hints (0.909 / 1.000) were re-adjudicated, not inherited.
- Every repair-input hint's `beat_id` exists in `data/paris/beats.json` — 0 phantom slugs.
- `data/paris/beats.json` has 1562 beats and 1562 **unique** slugs — no duplicate-slug collapse.
- `data/paris/beats.json` is git-tracked and not gitignored; `ensure_dev_data` does not rewrite it, so
  the pinned set cannot drift under a suite run.
- `BeatRef.stable_beat_id` is genuinely `b.beat_id` from the graph (`selection.py:633`), and
  `db_parity` compares graph `b.beat_id` against the file — so file↔graph slug agreement is enforced
  by the infra the gate invokes.
- Pinned ids checked against db_parity's uploadable/linkable set: 0 unreachable-by-construction pins.
- `iter_strings` walks dict keys as well as values, so a UUID hidden in a note or key is caught.

## Proposed for the serial verifier (I was forbidden to run these)

1. `make test-file FILE="tests/test_tour_golden_consistency.py::test_fixture_ids_are_durable_slugs_and_internally_consistent"`
   — re-derive the pinned gate on the tree as it now stands (13 modified files, not 12).
2. `make test-file FILE="tests/test_docker_image_contents.py::test_src_first_party_imports_are_shipped_in_image"`
   — expected GREEN, which is the point: it proves the guard is blind to F1.
3. `make golden-diff FIXTURE=ile_oneway_90min` — the other entry point to the same fixtures, now
   silently repaired out-of-scope; confirm it prints a non-zero overlap and no `WARNING: … no
   stable_beat_id` block.
