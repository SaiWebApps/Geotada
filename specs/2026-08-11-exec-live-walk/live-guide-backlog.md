# Live Guide (walk screen) — outstanding functionality backlog

Screen 05 is visually styled (dark, premium player, banner) and the engine loop
(geofence → auto-play → auto-advance) works. But the screen has substantial real
functionality still to build. Captured here so it isn't lost. Grouped by area,
with the **tech decisions to settle** called out.

## 1. Map (the big one) — Slice 0.2 "MapView seam"
- **[TECH DECISION] Map plugin.** Currently `apple_maps_flutter` (iOS-only, native
  Apple Maps). Options: keep Apple Maps (iOS-only, no custom dark style, free),
  Google Maps (custom dark style + cross-platform, needs API key/billing), or
  Mapbox/`flutter_map` (full custom style, offline tiles, more work). The roadmap
  wants a swappable `MapView` wrapper (locked decision 8) so the plugin can change
  without touching Slice-1 screens. **Interim (now): basic Apple Map + pins.**
- **Dark map styling.** Wireframe 05 is a dark map. Apple Maps follows the *system*
  appearance, not the Flutter theme, so our dark screen currently shows a light map.
  True dark styling needs Google/Mapbox or forcing system dark.
- **Route polyline.** Draw `ItineraryStop.transitPolyline` (encoded polyline, already
  on the model) as the glowing route between stops. Falls back to nothing when the
  backend routing used haversine (polyline null).
- **Camera behavior.** Follow the user, orient to heading, auto-zoom to the next
  stop, frame the whole route on load.
- **User location marker + heading.** Show the walker's position + facing direction.
- **Offline tiles.** For the airplane-mode acceptance leg (Slice 1 offline story),
  map tiles must be cached/available offline — Apple Maps can't; needs Mapbox/offline.

## 2. In-transit vs at-stop behaviors (the state machine)
The engine has `idle / active / approaching / completed`, but the *screen* behavior
per state needs design + build:
- **In transit (walking, not playing):** map-forward, "head this way" guidance, the
  next-stop banner + distance, the walking Skip. What does the player show — minimized?
- **Approaching a stop:** the nudge (built) + should the map/camera react?
- **At a stop (audio playing):** the full now-playing player (built), map still visible.
- **[TECH DECISION] Turn-by-turn directions** ("Bear left, then straight on") — the
  wireframe shows these. They need a routing/nav engine (OSRM/Valhalla/MapKit
  directions) producing step-by-step maneuvers. Big. Today we only have straight-line
  distance-to-next. Decide: real turn-by-turn vs. simple "X m to <stop>" (current).
- **Bearing / direction arrow** to the next stop (deferred from 1.6a) — cheap
  (haversine bearing) if we skip full turn-by-turn.

## 3. Audio player — real controls
- **Live scrubber position.** The scrubber is currently visual (0:00 / -total). Live
  position + a real progress needs an `AudioProvider` seam extension exposing a
  position stream + duration (native `AVAudioPlayer` has both; the Dart seam doesn't
  expose them yet).
- **Seek.** Drag the scrubber to seek — needs the seam + native seek.
- **True pause / resume.** Center button currently `stop()`s (loses position). Needs
  pause/resume-from-position in the `AudioProvider` (native supports it; seam doesn't).
- **Prev / next semantics.** Prev currently replays the current stop; decide whether it
  should go to the previous stop. Next = skip to next (built).
- **Album art per stop/lens.** Currently a lens-colored headphones tile; wireframe uses
  real per-stop imagery.

## 4. Keep-exploring extras (KE)
- `ItineraryStop.extraBeatIds` / `extraNarration` — the "keep exploring here" deep-dive
  the menu (☰) icon in the player hints at. On-demand extra audio off the tour budget.

## 5. Completion
- Rich `complete-summary` (Slice 1.7) — route recap, time, stops, feedback. Current
  completed panel is minimal.

---

## Priority / sequencing suggestion
1. **Now:** basic Apple Map + stop pins (real, not a graphic). ✅ this pass.
2. **Next high-value:** settle the map-plugin tech decision (Apple vs Google vs Mapbox)
   + build the swappable `MapView` seam; then route polyline + camera-follow.
3. **Then:** the audio seam extension (position/seek/pause) for a real scrubber.
4. **Later:** turn-by-turn directions (only if we commit to a routing engine),
   offline tiles, KE extras, rich completion.
