# Tour-playback background audio — DIAGNOSIS & handoff (2026-08-08)

> Read this first. It is the proven root cause + recommended fix for the
> "no audio while locked" problem, captured for a fresh conversation.
> Branch: `tour-playback-bg-audio` (stacked on `slice0-bg-location-spike` / PR #15).

## Symptom
On-device (iPhone 15 Pro Max, iOS 26.5.2, AOT profile build), a tour stop's
narration does **not** play through a locked/pocketed screen via the production
`AudioService` (just_audio). Earlier it appeared to "play on unlock."

## What is PROVEN (with on-device evidence — do not re-litigate)
From the instrumented proof harness (`lib/spike/tour_playback_proof_page.dart`),
a walk with the phone locked 19:15:53 → 19:17:16 (`LIFECYCLE paused`→`resumed`):

1. **Background location works while locked.** `pos` updates arrive every 3–4s
   with real-time advancing timestamps across the entire locked window. The app
   stays alive (timestamps are spread, not bunched at resume). NOT a location or
   background-execution problem.
2. **The geofence fires while locked.** `AUDIO playing=true beat=proof-1` at
   19:15:59 — inside the locked window. `TourPlaybackService._onPositionUpdate`
   → `_playCurrentStop` → `AudioService.play` all ran locked.
3. **The audio session is correctly active.** The tester's **podcast ducked**
   the moment playback started — that only happens if our
   `.playback`/`.duckOthers` session (`AudioService.prepareSession` →
   `com.ondoway/audio_session` native channel) activated. `prepareSession` WORKS.
4. **just_audio produces NO audible output in the background.** just_audio
   reports `playing=true` and position advances for the whole locked window, but
   **no narration was heard**, and the podcast **never un-ducked** (just_audio
   held the session open, "playing" silence). In the FOREGROUND the same cached
   clip plays fine.
5. **Slice 0.3 proved a native `AVAudioPlayer` DOES play locked** on this device
   (commit `af35902`, `com.ondoway/bg_audio` `play` raw-bytes path).

### Also found (separate product decision, not the audio bug)
- **10m geofence is too tight for real GPS.** A clean walk missed a stop by 0.2m
  (closest approach 10.2m vs 10.0m). `TourPlaybackService.triggerRadiusMeters`
  is now configurable (default 10.0 preserved); the proof uses 20m. Decide
  whether production should widen the default and/or go accuracy-aware.

## ROOT CAUSE
just_audio's `AVPlayer` does not emit audio while the app is backgrounded /
screen-locked on iOS 26, even with a correctly-active `.playback`/`.duckOthers`
`AVAudioSession`. Session activation is not the gap (ducking proves it); the gap
is just_audio's background output path itself.

## RECOMMENDED FIX (the plan's named contingency)
Play tour audio through a **native file-path player**, not just_audio, for
background-capable playback:

1. Extend the native channel (`AppDelegate.swift`) with a `playFile(path)`
   method using `AVAudioPlayer(contentsOf:)` — the Slice 0.3-proven path that
   plays locked. (bg_audio already plays raw bytes; add a file-path variant, or
   generalize `com.ondoway/audio_session`.)
2. Route `AudioService.play(...)` (at least during an active tour) through the
   native player when a cached file exists, and **bridge state back** to
   `AudioService` — `isPlaying`, position, duration, and **completion** — because
   `TourPlaybackService._onAudioStateChanged` relies on completion to auto-advance
   stops, and the UI (`beat_audio_player.dart`) binds to `isPlaying`/position.
3. Keep `prepareSession()` (it works) — the native player plays on that session.
4. Re-run the proof harness locked to confirm audible narration + duck/restore +
   auto-advance (AC2/AC3/AC4).

Investigate-first alternatives to weigh before committing to the above:
- A just_audio background config that fixes output (note: the `audio_session`
  Dart package SIGBUS-crashes on iOS 26 per Slice 0.3 — likely a dead end).
- Whether just_audio's iOS `AVQueuePlayer` needs `automaticallyWaitsToMinimizeStalling`
  / an explicit remote-command/now-playing setup to output in background.
Native `AVAudioPlayer` is the safe bet (already proven); the above are only worth
a short spike if avoiding native state-bridging is deemed valuable.

## Branch state (all committed, `make flutter-test` 231 green, analyze clean)
- `e32c8c6` AudioProvider.prepareSession() (works — keep)
- `167de8e` startTour → prepare + background:true, AC1 (keep)
- `c67bd54` com.ondoway/audio_session native channel (works — keep)
- `196812c`+ proof harness, debug entry buttons, direction picker, instrumentation
- `9f67504` configurable geofence radius (keep; decide default separately)

## Scaffolding to remove when the slice lands (all `!kReleaseMode`)
- `lib/spike/tour_playback_proof_page.dart` + its route in `lib/router.dart`
- login-page "Tour Proof" FAB (`lib/pages/login_page.dart`)
- lens-page headphones IconButton (`lib/pages/lens_selection_page.dart`)

## IMPLEMENTED 2026-08-08 — internally tested, ON-DEVICE PROOF STILL OWED
The recommended fix is written and passes every off-device check. It is NOT yet
proven to fix the bug: the bug's resolution can only be shown on a real locked
iPhone (below). Framing per judge ruling: "implemented + internally tested;
on-device locked proof is the remaining gate" — NOT "fixed".

Changes (branch `tour-playback-bg-audio`, uncommitted):
- NEW `mobile/lib/services/native_audio_backend.dart` — Dart wrapper over
  MethodChannel `com.ondoway/native_audio`: `play(path)->Duration`,
  pause/resume/stop/seek/getPosition, and an `onComplete` callback.
- `mobile/lib/services/audio_service.dart` — on iOS with a cached file, `play()`
  routes through the native backend instead of just_audio, and bridges back
  `isPlaying` (set on play), `duration` (native play return), `position` (300ms
  poll — UI only), and **completion** (native `onComplete` → isPlaying=false,
  position=duration, notify → drives tour auto-advance). pause/resume/stop/seek
  route to whichever backend is active. just_audio kept for URL streaming +
  non-iOS. A `@visibleForTesting cachedPathResolver` seam keeps the routing
  logic testable on the web test runner (no dart:io).
- `mobile/ios/Runner/AppDelegate.swift` — `com.ondoway/native_audio` channel:
  `AVAudioPlayer(contentsOf:)` file player + `AVAudioPlayerDelegate`;
  `audioPlayerDidFinishPlaying` pushes `onComplete`. Player + channel held
  strongly. Session activation unchanged (existing `prepare` path).

Evidence: `make flutter-test` 238 passed / 0 failed / 0 skipped (was 231; +7).
`make flutter-analyze` clean. Completion-bridge test mutation-proven (revert →
RED). `flutter build ios --simulator --debug` → built (Swift compiles).

### The on-device proof (run this to close the slice)
`make flutter-device-profile`, open the debug "Tour Proof" harness
(`lib/spike/tour_playback_proof_page.dart`), start the proof, then **lock the
phone and pocket-walk** ~30m then ~55m along the chosen bearing. Confirm:
- **AC2** narration for stop 1 is AUDIBLE through the locked screen (the fix);
- **AC3** the tester's own music/podcast ducks while narration plays and
  UN-ducks when it ends (native player releases the ducked session);
- **AC4 — the critical one** the tour AUTO-ADVANCES and stop 2's narration is
  audible **within the same continuous locked window** (do not unlock between
  stops). This proves the native→Dart `onComplete` wakes the backgrounded
  isolate while locked — the symmetric trap to the original bug. Hearing only
  stop 1 does NOT prove AC4.

### First device run (20:00, E walk) FAILED — two bugs found + fixed
The log showed `AUDIO playing=false buffering=true → buffering=false beat=proof-1`
then an immediate `idx=0 → idx=1` with **`playing` never true**. Root causes:
1. **Native player threw on the proof clip.** `AppDelegate.swift` used
   `AVAudioPlayer(contentsOf:url)`, whose URL initializer picks a decoder from the
   file EXTENSION. The harness caches a WAV under a `.mp3` name (and the app caches
   all narration as `.mp3`), so the WAV bytes under `.mp3` threw. FIX: load the
   bytes and use `AVAudioPlayer(data:)`, which content-sniffs the header — the exact
   path Slice 0.3 proved plays locked. Data held strongly (`filePlayerData`).
2. **A failed/not-yet-started play looked like a completion.**
   `TourPlaybackService._onAudioStateChanged` advanced on a bare `!isPlaying`, which
   is also true during the buffering notify and after a throw — so the tour jumped
   to stop 2 before any audio played (masked before because just_audio always
   reached `playing=true`). FIX: completion is now a genuine `playing:true→false`
   TRANSITION (`_audioWasPlaying`). Regression test + mutation added.

Re-verified: `make flutter-test` 239 passed / 0 / 0; analyze clean; simulator build
compiles. The locked-walk proof below still has to confirm the fix on-device.

### Second device run (20:30, E walk) — audio PLAYS; two more bugs fixed
`AUDIO playing=true beat=proof-1` appeared (AC2 audible locked, user-confirmed)
and idx advanced 0→1 only after a true→false transition (AC4 mechanics correct).
But: (a) the terminal stop replayed on every GPS tick, and (b) the podcast never
un-ducked. Fixed:
1. **Fire each stop once.** `TourPlaybackService._triggeredStops` (a Set) guards
   the geofence; a stop auto-plays once and never replays while lingering (the
   terminal stop never advances, so it re-fired forever). Reset on start/stop.
2. **Release the ducked session on tour end.** `.duckOthers` was activated once
   and never deactivated, so other audio stayed ducked forever — even after Stop.
   New `com.ondoway/audio_session` `deactivate` (`setActive(false,
   .notifyOthersOnDeactivation)`), exposed as `AudioProvider.releaseSession()`,
   called on `stopTour()` and on tour completion. (Between-stop un-duck during
   silent walks is NOT done yet — it needs background REactivation, which is the
   risky path; deferred. Today the podcast stays ducked for the whole active tour
   and resumes when the tour ends.)

Also added a **map pin-drop proof mode** (`lib/spike/tour_pin_proof_page.dart`,
route `/debug/tour-pin-proof`, reached from a button on the linear proof page):
tap the map to drop your own well-spaced stops, walk to each, one trigger apiece
— so proximity triggering is unambiguous instead of a guessed 30m/55m bearing.

Re-verified: `make flutter-test` 243 / 0 / 0 (+4 tests: fire-once,
release-on-complete, release-on-stop, deactivate-channel; two mutation-proven);
analyze clean; simulator build compiles.

### Known minor follow-up (does not block the proof)
After a NATURAL completion, `_nativeActive` stays true and the native player
sits at end-of-clip. The important transitions are fine (next stop re-enters the
native path; a URL stop calls `_stopNative()`), but a manual resume on a
just-finished clip plays from the end (silent) rather than replaying. Cosmetic;
fix if the manual player UX needs it.

## Known unrelated issue (do not conflate)
Empty lens page / "beta over" after magic-link login = the known prod-API gap
(workbench-gated endpoints 404 in prod). Separate task. See
[[project_mobile_prod_api_gap]].
