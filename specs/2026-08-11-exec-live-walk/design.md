# exec-live 1.6a — Locked-screen audio walk (design)

**Date:** 2026-08-11
**Slice:** Roadmap 1.6 (`exec-live` + `exec-story`), first increment "1.6a"
**Track:** Client (Flutter, superpowers → build-to-device — NOT `/team`)
**Status:** design, awaiting review

## 1. Goal

Turn a prepared `GeneratedTrip` into a hands-free audio walk. The user starts the
tour and walks; each stop's story auto-fires on proximity while the phone is
**locked and in a pocket**. This is the screen that makes Slice 1 — "complete an
entire tour on your iPhone in one sitting" — actually true.

**Non-goal for this increment:** the map. The Slice-1 acceptance test is "screen
locked, phone in pocket," during which the map is never seen. The product hero is
"look up at the city, not down at the phone." The map (position + route +
`transit_polyline`) is the *next* slice, built on the real Slice-0.2 `MapView`
seam, which does not exist yet.

## 2. Why this is small

The hard part is already built and proven: `TourPlaybackService` (278 lines,
registered in `main.dart`, consumed by no screen) already does the 10 m geofence
trigger, auto-play on arrival, auto-advance on audio-complete, and the
approaching-next-stop nudge — driven through `LocationProvider` + `AudioProvider`.
The native locked-screen `AVAudioPlayer` path is proven (Slice 0, via a debug
harness). This slice is a **thin view over that engine** plus a real navigation
entry point. No engine changes are required.

## 3. Architecture — one screen, engine-driven, two visual states

`TourWalkPage` is a thin view over `TourPlaybackService`. The engine owns all
logic; the screen renders engine state and offers a few manual affordances. It
reads `context.watch<TourPlaybackService>()` for tour state and
`context.watch<LocationProvider>()` for the current GPS fix.

`TourState` drives which sub-view shows — this collapses the spec's separate
`exec-live` and `exec-story` screens into one screen with visual states:

| `TourState` + audio | Visual state | Shows |
| --- | --- | --- |
| `active`, not playing | **Walking** | Next-stop direction banner ("≈220 m → Pont Neuf" + bearing arrow), progress ("Stop 2 of 7") |
| `active`/`approaching`, playing | **Story** | Audio card: stop name, lens chip, playing indicator, Replay, Skip |
| `approaching` | **Nudge** (overlay) | "Approaching Louvre — Play now / Keep listening" → `acceptPendingStop()` / `dismissPending()` |
| `completed` | **Complete** | Minimal "Tour complete" panel + "Done" → `/explore` (rich recap is Slice 1.7) |

## 4. Navigation & entry

New full-screen route **`/trip/:tripId/walk`**, outside the tab shell, beside the
existing `/trip/:tripId`. The Review screen's "Start walking" passes the loaded
`GeneratedTrip` via go_router `extra`; the route builder falls back to
`TripService` fetch-by-`tripId` for a cold / deep-link entry.

The widget is `TourWalkPage({required GeneratedTrip trip})` so tests inject a
fixture directly. `startTour(trip.stops)` is called once in `initState`;
`stopTour()` in `dispose` (which the engine already implements — it releases the
ducked audio session so the tourist's own audio returns).

## 5. Components

Each is a focused, independently testable unit.

- **`TourWalkPage`** (stateful) — owns the start/stop lifecycle, reads engine +
  location, switches sub-views on `TourState`.
- **`NextStopBanner`** — pure widget `(stop, distanceMeters, bearingDegrees)` →
  name + distance + arrow.
- **`StopAudioCard`** — `(stop, isPlaying)` → name, `lensDisplay` chip, playing
  indicator, **Replay** (`audio.play(key, url)`), **Skip**
  (`engine.skipToStop(currentIndex + 1)`).
- **`ApproachingNudge`** — Accept / Dismiss → engine.
- **`TourProgressBar`** — "Stop N of M" from `currentStopIndex` / `stops.length`.
- **`geo.dart`** (pure, new, standalone) — `distanceTo()` (haversine) + `bearingTo()`
  for the banner. Kept independent so it touches no existing file; the engine's own
  `@visibleForTesting` haversine is left untouched. De-duping the two copies is an
  optional later cleanup, not part of this slice.

All styled through the Slice-0 design system (`OndowayColors` / `Dims` /
`buildOndowayTheme`). No hardcoded colors.

## 6. Data flow

`GeneratedTrip.stops` → `startTour(stops)`. The engine reads `LocationProvider` /
`AudioProvider` (both already registered in `main.dart`) and plays `stop.audioUrl`
keyed by `stopId ?? beatId`. The screen never touches audio/location directly
except reading `LocationProvider.lastPosition` to compute the banner's distance +
bearing to `currentStop` (pure `geo.dart`; no engine change).

## 7. The fixture

`mobile/test/fixtures/paris_golden_trip.json` — a captured real trip response
(3–5 Paris stops, each with `lat`/`lng`, `audioUrl`, `audioDurationSec`).

- **Primary:** capture one live `GET /trips/{id}` from prod and commit it.
- **Fallback** (if capture isn't feasible in-session): hand-author a realistic
  3-stop Paris fixture with the same shape.

The fixture is used only by widget tests. The on-device walk uses a live-generated
trip from prod (the golden path: login → lens → build-now → review → walk).

## 8. Error / edge handling

- **No `audioUrl` on a stop** — engine already no-ops (`_playCurrentStop` guards);
  screen shows "No audio for this stop" and Skip advances.
- **Location permission denied / no fix** — banner shows "Finding your location…";
  the walk is still drivable via Skip. (Background-location permission is Slice
  0.3's proven path; not re-solved here.)
- **Empty stops** — `startTour` returns false; screen shows an error + back.
- **Terminal stop** — engine sets `completed` and releases the session; screen
  shows the minimal completion panel.
- **Locked / backgrounded** — the point of the slice: audio continues via the
  native player; the screen is simply not visible. No screen code may assume
  foreground.
- **Airplane mode** — not implemented here (offline prefetch is Slice 1's prefetch
  story); the design must not break if `audioUrl` is later a cached path.

## 9. Testing

- **Widget tests (hermetic, inside `make flutter-test`):** `TourWalkPage` +
  fixture trip + **fake** `LocationProvider`/`AudioProvider` + the real
  `TourPlaybackService`. Assert: renders current stop; driving fake GPS to a
  stop's coords triggers `audio.play`; `isPlaying` → story view; Skip →
  `skipToStop`; `approaching` shows the nudge and Accept/Dismiss hit the engine;
  `completed` shows the panel. Each behavioral assertion gets an undo-test.
- **Pure-helper tests:** `distanceTo` / `bearingTo` against known Paris coords.
- **On-device acceptance (the real bar, not automatable):** generate a real trip
  on prod → walk it in Paris, **screen locked, phone in pocket** → audio auto-fires
  per stop, banner updates → screenshot/transcript per stop. Airplane-mode leg is
  tracked but owned by the prefetch story, not this slice.

## 10. Explicitly out of scope (YAGNI)

Map + `transit_polyline` rendering (next slice, real 0.2 seam) · precise audio
scrubber and true pause/resume (needs an `AudioProvider` seam extension — Replay /
Skip only for now) · rich completion recap (Slice 1.7) · keep-exploring deep-dive
extras (KE) · route-flavour options.

## 11. Engine / seam changes

**None required.** Everything comes off existing getters/methods
(`state`, `currentStop`, `nextStop`, `currentStopIndex`, `skipToStop`,
`acceptPendingStop`, `dismissPending`, `stopTour`). The only new shared code is the
pure `geo.dart`. Exposing `distanceToNext` from the engine is a trivial future
follow-up if a live engine-sourced readout is ever wanted; not needed now.

## 12. Branch / worktree plan (implementation-time)

Build on a **clean branch off `main`** in its own worktree — exec-live must not sit
on top of the parked `fix-onboarding-replace-lenses` backend commit. Retire the two
`/tmp` mobile worktrees (`ondoway-step1`, `ondoway-onboarding`) once their proven
commits are landed, returning to a single working tree.
