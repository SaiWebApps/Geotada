# Slice 0.3 — iOS Background-Location Spike (design)

> **Status:** Approved design · 2026-08-07
> **Slice:** 0.3 of the mobile roadmap (`specs/2026-08-04-mobile-roadmap/roadmap.md`).
> **Track:** client / on-device — runs the superpowers loop (writing-plans → build-to-device),
> NOT `/team`. See [[project_team_drives_backend_only]].
> **Device:** Adam's iPhone, bundle `com.ondoway.app.adam` (see [[project_ios_per_dev_signing]]).

## Why this first

It is the single highest-risk unknown in the whole mobile build. The golden-path walk
(Slice 1.6) is "look up at the city, not down at the phone" — phone **pocketed, screen off**.
iOS suspends foreground-only location the moment the screen locks, so the 10m stop geofence
would never fire pocketed. If this can't be made to work on real hardware, the product premise
is in question. De-risk it while it is cheap to pivot.

Today's `LocationService` (`mobile/lib/services/location_service.dart:106-116`) uses a plain
foreground `LocationSettings(accuracy: high, distanceFilter: 5)` — no background capability —
and Info.plist (`mobile/ios/Runner/Info.plist`) has the location usage strings but **no
`UIBackgroundModes`**. So this is genuinely unproven on this app.

## Success criterion (the spike's whole point)

On real hardware, with the **screen locked and the phone in a pocket**, walking within **10m**
of a target coordinate **plays an audio clip out loud**. Chosen deliberately: playing audio is
what the real tour does at every stop, so this one proof clears **both** hard iOS unknowns at
once — background *location delivery* AND background *audio playback* (which needs its own
`UIBackgroundModes: audio` + a background-capable `AVAudioSession`).

## Approach (settled)

**Continuous background location updates + in-Dart distance check.** geolocator delivers
positions while backgrounded; the app Haversine-computes distance to the target and fires at
≤10m. Native iOS *region monitoring* is rejected: its regions are coarse (~100m minimum
reliable radius) and capped at 20 — the wrong tool for 10m stop precision.

## Components

### 1. iOS config
- Add `UIBackgroundModes` to `mobile/ios/Runner/Info.plist` with **both** `location` and
  `audio`. (`location` keeps the app running for position updates while suspended/locked;
  `audio` lets `just_audio` start/continue playback from that background window.)
- The usage strings `NSLocationWhenInUseUsageDescription` and
  `NSLocationAlwaysAndWhenInUseUsageDescription` already exist — no change.

### 2. `LocationService` background mode (real, reusable — kept)
- Extend the `LocationProvider` seam (`mobile/lib/services/providers.dart:5-11`) minimally:
  `Future<bool> startTracking({bool background = false})` — optional param, **backward
  compatible**, existing foreground callers unaffected.
- When `background: true`, `LocationService` builds geolocator **`AppleSettings`**:
  `allowBackgroundLocationUpdates: true`, `pauseLocationUpdatesAutomatically: false`,
  `showBackgroundLocationIndicator: true`, `activityType: otherNavigation`,
  `accuracy: high`, `distanceFilter: 5`. Otherwise the existing plain `LocationSettings`.
- Exposed through the seam so Slice 1.6 reuses it verbatim behind `LocationProvider`.

### 3. Debug "Location Spike" screen (kept behind a debug route — field-test tool)
- **"Set target = my current spot"** captures the current position as the target.
- Live **distance-to-target** readout + Start/Stop (visible when the phone is in hand).
- On Start: `startTracking(background: true)`, then on each position compute distance; at
  **≤10m**, fire **once** (debounced) → play a bundled audio clip via `just_audio`.
- An on-screen **event log** the walk can be audited from after the phone comes out of the
  pocket: it records **every background position update** (timestamp, coords, accuracy) AND each
  **fire** (timestamp, distance at fire). The position rows prove updates kept arriving while
  locked; the fire rows prove the trigger fired.
- Reached via a debug route, not production navigation.

### 4. Trigger logic isolated from `TourPlaybackService`
- The distance + fire-once debounce is a small **standalone** unit, NOT
  `TourPlaybackService`. The spike's question is "does iOS deliver location + let us play audio
  while pocketed?" — isolate that from the engine so the engine is not a confounding variable.
  Wiring the real `TourPlaybackService` (which already has 10m geofence logic) is a separate,
  lower-risk step afterward.

## Decisions (approved)

- **Permission = WhenInUse** + `allowBackgroundLocationUpdates` + the background mode (shows the
  blue location pill). Sufficient to prove pocketed firing; "Always" is a later production
  upgrade, out of scope here.
- **Isolate from `TourPlaybackService`** for the spike (above).
- **Test method:** set target at your current spot → lock + pocket → walk ~30–50m away and back
  → it sounds off on re-entering 10m. Short, repeatable, no special route.

## Testing

- **Unit (TDD):** the pure Dart is unit-tested first, RED→GREEN — Haversine distance for known
  coordinate pairs, and the fire-once debounce (fires at ≤10m, does NOT re-fire while still
  inside, re-arms after leaving). No geolocator/hardware dependency (uses the `LocationProvider`
  seam / injected positions).
- **Manual on-device acceptance (the gate that matters):** the background-hardware behavior
  cannot be unit-tested. Proof = the walk above on `com.ondoway.app.adam`, screen-locked and
  pocketed, captured with a screen-recording or photo + the on-screen fired-log. Repeat to
  confirm it is reliable, not a fluke.

## Acceptance criteria (objective)

1. `UIBackgroundModes` in Info.plist contains `location` and `audio`.
2. Unit tests for Haversine distance + fire-once debounce pass (RED before, GREEN after).
3. On device, with the app **backgrounded and the screen locked**, the event log shows
   background **position-update rows with advancing timestamps** during the locked window —
   proving updates kept arriving, not just that a fire happened.
4. With the phone **pocketed and screen locked**, walking away ~30–50m and back **plays the
   audio clip** on re-entering 10m — reproduced at least twice.
5. The background tracking is reachable through the `LocationProvider` seam (Slice 1.6 can call
   `startTracking(background: true)` with no screen-layer changes).

## Explicitly out of scope

- Wiring `TourPlaybackService` / the real tour (separate step).
- "Always" permission upgrade + its provisional-always prompt flow.
- Multi-stop itineraries, the exec-live UI, map rendering.
- Android background location + foreground service (Slice 10).
- Battery-consumption tuning beyond the sensible `AppleSettings` defaults above.

## What is kept vs throwaway

- **Kept:** the `LocationService` background mode (production seam, reused by 1.6) and the debug
  Location Spike screen (ongoing field-test tool behind a debug flag).
- **Incidental:** the bundled test audio clip.
