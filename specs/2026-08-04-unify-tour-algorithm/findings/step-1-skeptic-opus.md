# Step 1 — hostile skeptic (negative space)

**Verified against:** HEAD `a7df218c` plus the step-1 staged diff
(`git diff --cached --stat` = 6 files, 93 insertions, 494 deletions:
`mobile/lib/services/trip_service.dart` 28, `mobile/lib/widgets/beat_audio_player.dart` -232,
`mobile/test/pages/trip_itinerary_page_test.dart` 3, `mobile/test/services/trip_service_test.dart` -56,
`mobile/test/widgets/beat_audio_player_test.dart` -177, `tests/test_tour_one_engine.py` 91).
**Date:** 2026-08-04. **Angle:** negative space — untested states of the world.

## Verdict

**UNPROVEN.** The deletion itself is clean: I could not find a surviving reference to
`BeatAudioPlayer`, `beat_audio_player` or `TripService.confirmTripAudio` anywhere in
executable code, and the anti-over-deletion half of the test is real. But AC-12 names
**two** green gates, `make flutter-test` and `make flutter-analyze`, and only one of
them was run. One verified side effect of the diff is also unowned.

## Findings

### 1. AC-12's `make flutter-test` clause has never been run (medium)

AC-12 verbatim: "...must be deleted with them, **with make flutter-test and make
flutter-analyze green**." The evidence bundle contains `make lint`,
`make flutter-analyze`, and the Python node-id test. No Flutter test run appears
anywhere.

The ledger itself disagrees with the run sheet. `state.json` step 1 lists
`gate_commands: ["make lint", "make flutter-analyze", "make flutter-test"]`;
`run-context.md` (the pinned table at lines 279-280, justified at 301-307) normalizes
`make flutter-test` away as "not a derivable rule from files[]". The result is that
the one gate AC-12 names by hand has no owner at step level.

Why analyze is not a substitute: `mobile/analysis_options.yaml` sets no `exclude`, so
`flutter analyze` does read `mobile/test`, which proves the four edited Dart files still
COMPILE. It executes nothing. Step 1 deleted a whole suite file
(`mobile/test/widgets/beat_audio_player_test.dart`, 177 lines) and three tests out of
`mobile/test/services/trip_service_test.dart`; only an execution of the suite shows the
remaining 19 `jsonEncode`-using cases in that file and the `_FakeAudioService` page test
still pass and that `scripts/flutter_test.sh` still reaches its "All tests passed!"
marker.

Proposed (NOT run here — it writes `mobile/.dart_tool` and takes a machine-wide
`/tmp/ondoway-flutter-test.lock`, so it must not race the concurrent skeptic):

    make flutter-test

Assessment: low probability of a red, zero proof of a green. Until it runs, "step 1
satisfies AC-12" is a claim about half of AC-12.

### 2. The diff silently invalidated a line citation in a file it did not touch (low, verified)

`tests/test_trip_api.py:663` documents the phone's 422 compose-verification parse:

    (mobile/lib/services/trip_service.dart:227-229 reads exactly those two);

Step 1 removed 25 lines above that point. Reproduced read-only:

    git show HEAD:mobile/lib/services/trip_service.dart | sed -n '227,229p'
    -> if (detail?['reason'] == 'compose_verification_failed') { ... attempts ...

    sed -n '227,229p' mobile/lib/services/trip_service.dart
    -> String? provider, / String? voiceId, / }) async {   # generateDeeperDiveAudio

The citation now points at an unrelated method. Nothing catches this: `make lint` is
ruff over `src/ tests/ scripts/`, which does not check prose; `flutter analyze` does not
read Python; the pinned test scans for three symbols only.

This does not violate AC-12's letter, so it should not block the step. It does violate
the standing rule that a document contradicting the code gets corrected, and the
ledger's own contract note (`findings/contracts-mobile-and-audio.md:72`) flagged exactly
this class of stale cross-reference — the developer fixed the one inside
`trip_itinerary_page_test.dart` and missed the one its line deletions caused. One-line
fix: cite the symbol (`ComposeVerificationException` / `compose_verification_failed`)
instead of a line range.

### 3. The proving test searches a narrower tree than AC-12 describes (low, unproven)

AC-12 says "when **mobile/** is searched". `tests/test_tour_one_engine.py` searches
`mobile/lib/**/*.dart` plus `mobile/test/**/*.dart`. Today those are the only two
directories in the repo holding Dart (verified by `find mobile -name '*.dart'`), so the
sets coincide and the test is not vacuous. The gap is forward-looking: a reintroduction
under a standard-but-absent `mobile/integration_test/`, or a mention in a non-Dart file
under `mobile/` (pubspec, README, iOS project), passes this test while failing AC-12 as
written. Not reproduced — the reproduction requires creating a file under `mobile/`,
which would corrupt the concurrent skeptic's `flutter analyze`. Cheap remedy: root the
sweep at `mobile/` with an explicit skip of `.dart_tool`, `build`, `ios`, `android`.

### 4. The verdict depends on git index state, not only on the code (low, unproven)

The test asserts the two files are absent from `git ls-files`. That is a genuine
strengthening while the work is uncommitted — and the engine never commits, so the whole
ledger runs in exactly that window. The untested state: a plain `git reset` (unstage,
non-destructive, common) restores both paths to the index while leaving them absent from
disk, turning the test RED with `still tracked by git` even though every line of source
is correct. Symmetrically, a patch applied with `git apply` and no `--index` reproduces
it. I did not run this: mutating the shared index while a sibling skeptic reads the same
worktree is precisely the collision the panel rules forbid. Advisory only — the
assertion is defensible; the operator just needs to know a red here can mean "unstaged",
not "unfixed".

### 5. Step 1's test pins two symbols in files step 16 owns (low, unproven)

The anti-over-deletion block asserts `mobile/lib/services/trip_service.dart` still
contains `confirmTripStopAudio` and `mobile/lib/pages/trip_itinerary_page.dart` still
contains `checkAudioStatus`. `trip_itinerary_page.dart` is not in step 1's `files[]`,
and `checkAudioStatus` is on run-context's explicit out-of-scope list. Step 16 of this
same ledger edits both `trip_service.dart` and `trip_itinerary_page.dart`. If step 16
renames or relocates either symbol, step 1's test goes red and reads as a step-16
regression rather than a stale pin. Not a defect today; a coupling the ledger should
know about.

### 6. A purely static assertion now costs the shared containers (low, advisory)

The new test touches no database: it is file existence, `git ls-files`, and substring
scans over Dart text. Its gate, `make test-file`, declares
`PRE_PYTEST := uv python-deps db-test db-dev dev-data valhalla` (`Makefile:49`), so
running it starts Neo4j 7687 and 7688, writes dev data into the shared 7687 graph, and
brings up Valhalla — for a step whose entire content is deleting Dart files. That is the
build system working as designed, not a bug in the diff, but it means this step's "$0"
gate mutates shared state a sibling session may be using.

## What I attacked and could not break

- **Surviving references, repo-wide, all file types.** `grep -rn` for `BeatAudioPlayer`,
  `beat_audio_player`, `confirmTripAudio` across the tree (excluding `.git`,
  `.dart_tool`, `build`, `node_modules`): zero hits in any executable file. Every
  remaining hit is in this ledger's own markdown/`state.json` or the untracked
  `ondoway-one-engine-handoff.md`.
- **The false-positive trap.** `"confirmTripAudio" in "confirmTripStopAudio"` is False;
  the live per-stop method survives at `trip_service.dart` and is called from
  `trip_itinerary_page.dart:286`.
- **A different Python entry point onto Dart source.** Only
  `tests/test_no_doubles_on_human_surfaces.py` structurally reads Dart; it asserts
  `mobile/lib` never imports `mobile/test`, which the deletion cannot affect.
  `tests/test_audio_route_hardening.py` reads `render.yaml`, not Dart.
- **A dead-route guard firing on the backend side.** After step 1 nothing in the phone
  calls `POST /audio/generate-trip/{trip_id}` (`src/api/routes/audio.py:658`). It is not
  in the admin-gated list at `audio.py:60-71`, and no test asserts a caller for it, so
  nothing turns red. Worth a later cleanup decision; it is out of this step's scope.
- **A stale mock left behind.** `mobile/test/pages/trip_itinerary_page_test.dart:240`
  mentions "generate-trip for setup" — read in full, it mocks `/trips/generate` and
  `/audio/generate-trip-stops/`, both live. Not stale.
- **An empty test directory.** `mobile/test/widgets/` still holds
  `feedback_overlay_test.dart`, so no runner is handed an empty glob.
- **The lint gate.** `make lint` re-run unpiped: exit 0, "All checks passed!".
- **Index state.** `git ls-files | grep -c beat_audio_player` = 0, so the staged
  deletion is a real `git rm`, not a worktree-only removal.
