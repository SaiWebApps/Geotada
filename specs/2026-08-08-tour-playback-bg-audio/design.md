# Tour-playback background audio — session seam + on-device proof (design)

> **Status:** Approved design · 2026-08-08
> **Slice:** follow-on to Slice 0.3 (`specs/2026-08-07-bg-location-spike/`); feeds the
> mobile roadmap (`specs/2026-08-04-mobile-roadmap/roadmap.md`).
> **Track:** client / on-device — runs the superpowers loop (writing-plans → build-to-device),
> NOT `/team`. See [[project_team_drives_backend_only]].
> **Device:** Adam's iPhone, bundle `com.ondoway.app.adam` (see [[project_ios_per_dev_signing]]).

## Why this now

Slice 0.3 proved the *mechanism* on a throwaway spike screen: a pocketed, screen-locked phone
fires a 10m geofence and plays audio (branch `slice0-bg-location-spike`, PR #15). But the proof
used a **bundled WAV played as raw bytes through a native `AVAudioPlayer`** — not the real
audio path. The production services are untouched by that fix:

- `mobile/lib/services/audio_service.dart` uses **just_audio** and **never configures
  `AVAudioSession`** (no `setCategory`/`setActive` anywhere) — so on a locked screen it would be
  silenced, exactly the root cause the spike diagnosed.
- `mobile/lib/services/tour_playback_service.dart` already owns the geofence state machine (10m
  trigger, approaching-nudge, auto-advance) but calls `startTracking()` **foreground-only**
  (`tour_playback_service.dart:58`) — no `background: true`.
- `TourPlaybackService` is wired as a provider (`mobile/lib/main.dart:23`) but **nothing calls
  `.startTour()`** yet — the engine exists and is unit-tested; the live playback UI does not.

This slice carries the *proven session architecture* into the real `AudioService`/
`TourPlaybackService` and proves it against those services — before any tour-playback UI is
built on top of an unproven audio path.

## Success criterion (the slice's whole point)

On real hardware, screen **locked** and phone **pocketed**, walking within **10m** of a tour
stop whose audio is **cached** plays that stop's narration **out loud through the lock screen**,
via the real `AudioService.play(...)` / `TourPlaybackService` path — with other audio ducked,
and with auto-advance to the next stop still working while locked.

## The technical crux

The spike went native + raw-bytes because just_audio was *silent when locked* — **but that test
predated the session fix.** just_audio (AVPlayer under the hood) plays in the background given
(a) `UIBackgroundModes: audio` — already present, Slice 0.3 — and (b) an **active
`.playback` session**, which nothing in production currently establishes. With a
foreground-activated `.playback`/`.duckOthers` session, just_audio should now play locked while
retaining all the rich state the UI binds to (`isPlaying`, `position`, `duration`,
`isBuffering`, `currentBeatId`, `isDeeperDive`). Whether it actually does is **the one real
unknown**, so this design bakes in an on-device proof and names the fallback rather than
guessing.

## Approach (settled)

**Fix the session, keep just_audio.** Add foreground `.playback`/`.duckOthers` activation via a
small native channel owned by `AudioService`; pass `background: true` from
`TourPlaybackService.startTour`; play from a **cached local file** on the geofence fire; verify
on-device. Preserves every just_audio state binding and the whole existing UI.

Rejected:
- **Port the spike literally** (native raw-bytes playback in production) — re-implements
  seek/position/duration/buffering from native callbacks; only justified if the proof below
  fails, and then as its own follow-up.
- **Swap just_audio for another library** — large blast radius on caching + UI bindings, no
  evidence it is needed.

## Components (all small, additive)

### 1. Native `audio_session` channel (iOS)
Promote the spike's proven `prepare` into a named, single-purpose channel
(`com.ondoway/audio_session`, method `prepare`):
`setCategory(.playback, mode: .spokenAudio, options: [.duckOthers])` then `setActive(true)`.
Category is configured at launch (not activated); **activation happens only on `prepare`, called
from the foreground**. This is byte-for-byte the mechanism proven in Slice 0.3
(`af35902`). The spike's raw-bytes `play` method is **not** carried over — just_audio plays.
Registered on `engineBridge.applicationRegistrar.messenger()` (the UIScene-safe messenger, per
Slice 0.3).

### 2. `AudioService.prepareSession()`
A new method on the `AudioProvider` interface (`mobile/lib/services/providers.dart`) and
`AudioService`. Invokes the native channel; wrapped in try/catch so a failure is logged but does
not throw; a no-op on non-iOS. Behind the interface so `TourPlaybackService` tests mock it.

### 3. `TourPlaybackService.startTour()` — two lines
- `await _audioService.prepareSession()` **before** starting tracking (runs in the foreground,
  the only state iOS grants session activation).
- `startTracking(background: true)` instead of the current foreground-only call.
The geofence (10m) and auto-advance logic already exist and are unchanged.

### 4. Cached-file playback (reliability, not new code)
Background playback must be a **local cached file**, not a cold URL stream (network + buffering
from a background callback is unreliable). `AudioService.play` already prefers a cached path
(`audio_service.dart:68-73`); the proof pre-caches its clip via `prefetchAudio`. Building the
full production prefetch *policy* (when/what to cache for a real tour) is **out of scope**.

### 5. Debug-gated proof harness (`!kReleaseMode`)
A debug screen/affordance that constructs two `ItineraryStop`s (target = current position, plus
a nearby second), ensures the clip is cached, and calls `tourPlaybackService.startTour([...])`,
logging `TourState`/distance. Reuses Slice 0.3's spike-screen patterns. This is the instrument
that captures the on-device proof; it is not shipped UI.

## Data flow (fire path)

Foreground `startTour` → `prepareSession()` (session active, ducking) + `startTracking(background:
true)` → screen locks → CLLocation updates keep arriving → `_onPositionUpdate` Haversine-computes
distance → ≤10m and not already playing → `_playCurrentStop` → `AudioService.play(cachedFile)` on
the already-active session → audible through the lock screen → on completion `_onAudioStateChanged`
advances the stop index → next stop fires the same way.

## Error handling

- `prepareSession()` failure: logged, tour still starts (audio may be silent — surfaced in the
  harness log, never a silent success).
- Background tracking failure: `startTour` returns `false` (existing behaviour).
- just_audio play error: existing rethrow/notify path (`audio_service.dart:75-79`).

## Testing

- **Unit (`make flutter-test`):** with a mock `AudioProvider`, `startTour` invokes
  `prepareSession()` **exactly once and before** `startTracking`, and passes `background: true`.
  Undo-test (mutation): revert either change and the new assertion goes RED.
- **On-device proof (the real bar):** locked + pocketed, cached clip; entering 10m plays
  narration audibly; other audio ducks and restores; stop-2 auto-advance works while locked.
  Captured with event-log transcript / screenshots.
- **Regression:** full `make flutter-test` green (0 skipped), `make flutter-analyze` clean.

## Acceptance criteria

- **AC1** (unit): `TourPlaybackService.startTour` calls `AudioService.prepareSession()` once,
  before `startTracking`, and calls `startTracking(background: true)`. Mutation-proven.
- **AC2** (device): screen locked + pocketed, entering 10m of a **cached** stop plays its
  narration audibly through the lock screen via the real `AudioService`/`TourPlaybackService`.
- **AC3** (device): other audio (music/podcast) ducks during narration and restores after.
- **AC4** (device): after stop 1 completes, reaching stop 2 (still locked) auto-plays it.
- **AC5**: `make flutter-test` green (0 skipped); `make flutter-analyze` clean.
- **Contingency AC** (if AC2 fails): the slice delivers the seam + the **negative** proof + a
  written follow-up scope for native file-path playback (rejected Approach 2). No silent
  success is claimed.

## Non-goals (named follow-ups)

- Full tour-playback / now-playing UI (its own slice — it depends on this proven seam).
- Lock-screen "Now Playing" controls (`MPNowPlayingInfoCenter` / `MPRemoteCommandCenter`).
- Call/Siri/other-app **interruption** handling (`AVAudioSession` interruption notifications).
- Android.
- The full production audio-prefetch policy.

## Constraints

- Extend the existing app; iOS-first. Add **no new packages** (geolocator, just_audio already
  present).
- The `AudioProvider` seam change must be backward compatible (add a method; existing callers
  unchanged).
- On-device dev uses `make flutter-device-profile` (AOT — the iOS-26 debug-JIT crash fix from
  Slice 0.3, `f133889`).
- New `.swift` code must be registered in `Runner.xcodeproj/project.pbxproj` if placed in a new
  file (per CLAUDE.md); keeping the channel in `AppDelegate.swift` avoids that churn.
