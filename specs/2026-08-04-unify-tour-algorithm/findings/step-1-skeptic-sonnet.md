# Step 1 skeptic review — fix correctness (Sonnet panelist)

Verified against: commit `a7df218c0ce3ca28df2e31df895f80e5ea3a7ef5` (HEAD, matches the
run-context baseline) plus the staged, uncommitted step-1 diff over
`mobile/lib/services/trip_service.dart`, `mobile/lib/widgets/beat_audio_player.dart`
(deleted), `mobile/test/services/trip_service_test.dart`,
`mobile/test/widgets/beat_audio_player_test.dart` (deleted),
`mobile/test/pages/trip_itinerary_page_test.dart`, `tests/test_tour_one_engine.py`.
`git diff --cached --stat` on those six files: `93 insertions(+), 494 deletions(-)` —
matches the claimed evidence packet exactly.

## Angle: fix correctness — does the change do what AC-12 requires, and does the pinned
regression test encode the real failure mode or a strawman?

## What I independently re-derived (not re-read)

- `make lint`: ran it myself this session. Exit 0, `All checks passed!` — matches the claim.
- `git diff --cached -- tests/test_tour_one_engine.py`, `trip_service.dart`,
  `trip_service_test.dart`, `trip_itinerary_page_test.dart`: read the full staged diffs
  directly, not the pasted evidence.
- Repo-wide `grep -rn` (not just `mobile/`) for `confirmTripAudio` and `BeatAudioPlayer` /
  `beat_audio_player`: outside this task's own spec/findings prose (which quotes the
  identifiers as text) and the new test's own string-literal constants, the only remaining
  hits are in `tests/test_tour_one_engine.py` itself (the token list) — zero hits in any
  `.dart` or `.py` source file. Confirms the deletion is complete, not just "mostly".
- Checked the sweep's scope for blind spots: confirmed via `find` that every git-tracked
  `.dart` file under `mobile/` lives under `mobile/lib/` or `mobile/test/` (no
  `integration_test/`, no dart files elsewhere) — so the test's two `rglob` roots
  (`mobile/lib`, `mobile/test`) are exhaustive over the real tree, not a partial sample that
  happens to miss something.
- Checked for indirect breakage a plain text sweep could miss: no `*.mocks.dart` or
  `*.g.dart` generated file anywhere under `mobile/` mentions either symbol (there are no
  `@GenerateMocks` declarations in the test suite at all, so there is no generated mock of
  `TripService` that would need its abstract member removed).
- Brace-balance check on `mobile/test/services/trip_service_test.dart` after the three
  `confirmTripAudio` test blocks were cut: 68 `{` / 68 `}` — the deletion didn't leave a
  dangling block or orphaned closing brace.
- Confirmed the doc-comment edit on `confirmTripStopAudio` reads correctly after the
  deletion ("the per-stop replacement for the retired per-primary-beat generation" — no
  longer references the removed method by name via a Dart-doc `[confirmTripAudio]` link
  that would now point at nothing).

## Finding 1 (informational, not a defect) — a prior panelist's Finding 1 is now stale

An earlier pass over this same step (`findings/step-1-skeptic-opus.md` and an earlier
version of this file, both dated today) flagged a dangling doc-comment reference in
`mobile/test/pages/trip_itinerary_page_test.dart:64` — "Mirrors the fake in
beat_audio_player_test.dart" — pointing at a file this step deletes. I re-checked that file
against the diff currently staged: the sentence is gone.

```
git diff --cached -- mobile/test/pages/trip_itinerary_page_test.dart
```
shows the developer already removed exactly that clause:
```
-/// completes on the headless-web runner and hangs finalize). Mirrors the fake
-/// in beat_audio_player_test.dart.
+/// completes on the headless-web runner and hangs finalize).
```
and `grep -n "beat_audio_player" mobile/test/pages/trip_itinerary_page_test.dart` on the
current worktree returns zero hits. The gap the earlier finding described has already been
closed in the diff I am reviewing. Not something I get credit for finding — just confirming
it is genuinely fixed, not merely claimed fixed.

## Finding 2 (advisory, not a repro) — the demonstrated mutation only exercises ONE of the
test's two failure paths

The developer's QA mutation reverted BOTH dead surfaces in one shot
(`git checkout HEAD -- mobile/lib/services/trip_service.dart
mobile/lib/widgets/beat_audio_player.dart`), then re-ran the pinned test and got:

```
AssertionError: ['mobile/lib/widgets/beat_audio_player.dart'] still exist on disk;
step 1 deletes them outright.
```

That is the test's assertion #2 (file-existence), which fires and aborts the function
*before* assertion #4/#5 (the `BeatAudioPlayer`/`confirmTripAudio` text sweep) ever run,
because pytest stops at the first failing `assert`. So the demonstrated red-first run proves
the file-existence half of the test works. It does not empirically prove the text-sweep
half works — that half is only supported by reading the source and reasoning about it
(`DEAD_MOBILE_SERVICE_METHOD = "confirmTripAudio"` would appear in a restored
`trip_service.dart` and get caught at assertion #5), never by an actual red run.

This matters for "does the test encode the original failure mode, not a strawman": the
original failure mode this step targets is dead code left behind — a plausible
*future* regression is someone re-adding `confirmTripAudio` to `trip_service.dart` alone
(e.g. restoring the mobile call site without restoring the widget), which the file-existence
check would NOT catch (the widget file would still be gone) — only the text-sweep would.
That specific path was never exercised red.

I did not run this myself (`make test-file` is on the propose-only list for this concurrent
panel). Proposed repro for the serial verifier — a narrower, single-file mutation that
isolates the untested assertion:

```
git checkout HEAD -- mobile/lib/services/trip_service.dart
make test-file FILE="tests/test_tour_one_engine.py::test_the_unreferenced_mobile_audio_surfaces_are_gone"
# expect: RED, this time via the DEAD_MOBILE_SERVICE_METHOD assertion (method_offenders),
# NOT the file-existence assertion, since beat_audio_player.dart stays deleted.
git checkout -- mobile/lib/services/trip_service.dart   # re-apply the staged fix
git diff --cached --stat -- mobile/lib/services/trip_service.dart  # confirm restored byte-identical
```

This is advisory: I have no reproduction showing the text-sweep assertion actually fails to
catch this case — the source reads as if it will catch it correctly — so this does not
refute the claim. It is a real gap in what the submitted mutation evidence actually proved,
not a defect in the fix.

## Finding 3 (advisory, out of this step's scope) — the backend counterpart is now orphaned

`src/api/routes/audio.py:658` still defines `POST /audio/generate-trip/{trip_id}`, whose
only real caller was the now-deleted `TripService.confirmTripAudio`. A comment at
`audio.py:67` already lists `generate-trip*` alongside the routes with "no product caller"
in one place but at `audio.py:790/803` still calls it "the per-primary-beat
`/audio/generate-trip`" as if it's a live sibling of `generate-trip-stops`. This route is
not in step 1's declared file scope (`state.json` step 1 `files[]` lists only the six Dart
and Python-test files reviewed above), and AC-12 is worded as a mobile/Dart-only criterion
("Given the deleted Dart code, when mobile/ is searched..."), so leaving the backend route
alone is a legitimate scoping choice, not a defect in this diff. Flagging it only so it
isn't lost: nothing in the 30 acceptance criteria or the "out of scope" list in
run-context.md appears to claim this backend route either, so unless a later step's file
scope covers `src/api/routes/audio.py`, this endpoint will ship as reachable dead code with
zero callers on either surface.

## Verdict

I tried to break the claim by: re-running `make lint` myself instead of trusting the pasted
exit code; grepping the whole repo (not just the files touched) for both dead identifiers
before and after the diff; checking for generated mocks, barrel files, and integration-test
directories a text-only sweep could miss; checking brace balance across the edited test
file; and tracing whether the earlier panelist's dangling-comment finding was actually fixed
or just claimed fixed (it was actually fixed). All of that held — the deletion is complete,
syntactically clean, and matches AC-12's letter.

The one substantive gap I found (Finding 2) is about the STRENGTH of the submitted mutation
evidence, not the correctness of the fix: the observed red-first run only proves the
file-existence assertion is load-bearing, not the text-sweep assertion, because the two
dead surfaces were reverted together. I have no verified reproduction that the text-sweep
half is actually broken — reading the source, it should catch the narrower case too — so
this does not refute AC-12 being satisfied. It is a legitimate, unrun objection I could not
execute myself under this panel's concurrency rules; it is included as a proposed repro for
the serial verifier, not as a blocker.

**CONFIRMED**, with Finding 2 logged as an advisory gap in the mutation evidence (proposed,
unrun repro attached) and Finding 3 logged as an advisory out-of-scope observation. Neither
is a verified reproduction of a break in step 1's diff or in AC-12 as literally worded.
