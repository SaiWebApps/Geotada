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

## Known unrelated issue (do not conflate)
Empty lens page / "beta over" after magic-link login = the known prod-API gap
(workbench-gated endpoints 404 in prod). Separate task. See
[[project_mobile_prod_api_gap]].
