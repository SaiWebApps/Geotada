# exec-live 1.6a — Locked-screen audio walk — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the production `TourWalkPage` — a thin view over the already-built `TourPlaybackService` — that plays a `GeneratedTrip` as a hands-free audio walk (story auto-fires on proximity while the phone is locked).

**Architecture:** One full-screen page driven entirely by `TourState` + `AudioProvider.isPlaying`. The engine owns geofence/auto-play/auto-advance; the page renders state (walking banner ↔ story card ↔ approaching nudge ↔ completed panel) and offers Replay/Skip via `engine.skipToStop`. No map (next slice). No engine changes.

**Tech Stack:** Flutter, Provider, go_router. Existing `TourPlaybackService`, `AudioProvider`/`LocationProvider` seams, `MockAudioService`/`MockLocationService` test fakes.

## Global Constraints

- Design system only: `OndowayColors` / `Dims` / `buildOndowayTheme`. **No hardcoded colors** (use `Theme.of(context).colorScheme.*` or `OndowayColors`).
- No `google_fonts` (breaks the flutter_test HTTP sandbox); fonts are bundled.
- Run tests from the **repo root**: `make flutter-test`. Analyze: `make flutter-analyze`. **Never run Flutter in the background.**
- Tests that use `dart:io` (reading the JSON fixture) MUST be annotated `@Tags(['vm'])` (declared in `mobile/dart_test.yaml`; `scripts/flutter_test.sh` runs them on the VM platform).
- TDD: write the test, watch it fail, implement minimally, watch it pass. For each behavioral assertion, do an undo-test (revert the production line → the test goes RED → restore).
- Commit after each task with a `feat(mobile):` / `test(mobile):` message ending in the `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` trailer.
- The engine is fixed API: `startTour(List<ItineraryStop>)→Future<bool>`, `stopTour()`, `skipToStop(int)`, `acceptPendingStop()`, `dismissPending()`; getters `state`, `currentStop`, `nextStop`, `currentStopIndex`, `pendingStopIndex`, `distanceToNext`, `isActive`, `hasPendingStop`. `TourState { idle, active, approaching, completed }`.

---

### Task 1: Paris trip fixture + loader

**Files:**
- Create: `mobile/test/fixtures/paris_golden_trip.json`
- Create: `mobile/test/support/trip_fixture.dart`
- Test: `mobile/test/support/trip_fixture_test.dart`

**Interfaces:**
- Produces: `GeneratedTrip loadParisFixtureTrip()` — a 3-stop Paris trip, each stop with `audioUrl`, `lat`, `lng`, `audioDurationSec`. Consumed by Task 4/5 page tests.

- [ ] **Step 1: Write the fixture JSON**

`mobile/test/fixtures/paris_golden_trip.json` (shape matches `GeneratedTrip.fromJson` / `ItineraryStop.fromJson`; replace with a captured prod `GET /trips/{id}` later if available):

```json
{
  "trip_id": "fixture-paris-001",
  "trip_name": "Île de la Cité — a first walk",
  "profile_id": "fixture-profile",
  "total_stops": 3,
  "total_duration_min": 45,
  "anchor_count": 3,
  "flavour_count": 0,
  "stops": [
    {
      "sort_order": 0, "stop_id": "s0", "poi_id": "louvre", "poi_name": "The Louvre",
      "lat": 48.8606, "lng": 2.3376, "beat_id": "b0",
      "lens_name": "art_history", "lens_display": "Art & History",
      "duration_min": 15, "importance_tier": 1, "start_time": "10:00",
      "script_body": "Stand before the glass pyramid...",
      "audio_url": "https://cdn.example/louvre.mp3", "audio_duration_sec": 92.0,
      "transit_polyline": null, "extra_beat_ids": [], "extra_narration": null
    },
    {
      "sort_order": 1, "stop_id": "s1", "poi_id": "pontneuf", "poi_name": "Pont Neuf",
      "lat": 48.8570, "lng": 2.3410, "beat_id": "b1",
      "lens_name": "architecture", "lens_display": "Architecture",
      "duration_min": 10, "importance_tier": 2, "start_time": "10:20",
      "script_body": "The oldest standing bridge...",
      "audio_url": "https://cdn.example/pontneuf.mp3", "audio_duration_sec": 78.0,
      "transit_polyline": null, "extra_beat_ids": [], "extra_narration": null
    },
    {
      "sort_order": 2, "stop_id": "s2", "poi_id": "notredame", "poi_name": "Notre-Dame",
      "lat": 48.8530, "lng": 2.3499, "beat_id": "b2",
      "lens_name": "art_history", "lens_display": "Art & History",
      "duration_min": 20, "importance_tier": 1, "start_time": "10:35",
      "script_body": "The cathedral rises...",
      "audio_url": "https://cdn.example/notredame.mp3", "audio_duration_sec": 110.0,
      "transit_polyline": null, "extra_beat_ids": [], "extra_narration": null
    }
  ],
  "options": []
}
```

- [ ] **Step 2: Write the loader**

`mobile/test/support/trip_fixture.dart`:

```dart
import 'dart:convert';
import 'dart:io';

import 'package:ondoway/models/trip.dart';

/// Loads the committed Paris trip fixture as a [GeneratedTrip].
/// Uses dart:io — any test calling this must be annotated `@Tags(['vm'])`.
GeneratedTrip loadParisFixtureTrip() {
  final raw = File('test/fixtures/paris_golden_trip.json').readAsStringSync();
  return GeneratedTrip.fromJson(jsonDecode(raw) as Map<String, dynamic>);
}
```

- [ ] **Step 3: Write the failing validity test**

`mobile/test/support/trip_fixture_test.dart`:

```dart
@Tags(['vm'])
library;

import 'package:flutter_test/flutter_test.dart';
import 'support/trip_fixture.dart';

void main() {
  test('paris fixture parses into a 3-stop trip with audio on every stop', () {
    final trip = loadParisFixtureTrip();
    expect(trip.stops.length, 3);
    expect(trip.stops.every((s) => s.audioUrl != null), true);
    expect(trip.stops.first.poiName, 'The Louvre');
    // Paris latitude band — guards against a malformed fixture.
    expect(trip.stops.every((s) => s.lat > 48.8 && s.lat < 48.9), true);
  });
}
```

Note: the import path is `support/trip_fixture.dart` because the test file lives in `test/support/`. Adjust to `../support/trip_fixture.dart` if the runner's working directory differs; the file path in the loader (`test/fixtures/...`) is relative to the package root, which is where `make flutter-test` runs.

- [ ] **Step 4: Run — expect FAIL then PASS**

Run: `make flutter-test` (or scope: `cd mobile && flutter test test/support/trip_fixture_test.dart --tags vm`).
Expected: fails first if the fixture/loader are absent or malformed; passes once both exist.

- [ ] **Step 5: Commit**

```bash
git add mobile/test/fixtures/paris_golden_trip.json mobile/test/support/trip_fixture.dart mobile/test/support/trip_fixture_test.dart
git commit -m "test(mobile): commit Paris trip fixture + loader for exec-live tests"
```

---

### Task 2: `NextStopBanner` + `formatDistance`

**Files:**
- Create: `mobile/lib/widgets/tour/next_stop_banner.dart`
- Test: `mobile/test/widgets/tour/next_stop_banner_test.dart`

**Interfaces:**
- Produces: `String formatDistance(double meters)`; `NextStopBanner({required String stopName, required double? distanceMeters})`.

- [ ] **Step 1: Write the failing test**

`mobile/test/widgets/tour/next_stop_banner_test.dart`:

```dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ondoway/widgets/tour/next_stop_banner.dart';

void main() {
  test('formatDistance rounds metres under 1km, uses km above', () {
    expect(formatDistance(0), '0 m');
    expect(formatDistance(219.4), '219 m');
    expect(formatDistance(1200), '1.2 km');
  });

  testWidgets('shows the stop name and distance', (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(body: NextStopBanner(stopName: 'Pont Neuf', distanceMeters: 220)),
    ));
    expect(find.textContaining('Pont Neuf'), findsOneWidget);
    expect(find.textContaining('220 m'), findsOneWidget);
  });

  testWidgets('shows a locating hint when distance is null', (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(body: NextStopBanner(stopName: 'Pont Neuf', distanceMeters: null)),
    ));
    expect(find.textContaining('Finding your location'), findsOneWidget);
  });
}
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd mobile && flutter test test/widgets/tour/next_stop_banner_test.dart`
Expected: FAIL ("NextStopBanner isn't defined" / "formatDistance isn't defined").

- [ ] **Step 3: Implement**

`mobile/lib/widgets/tour/next_stop_banner.dart`:

```dart
import 'package:flutter/material.dart';
import 'package:ondoway/theme/dims.dart';

/// "220 m" under a kilometre, "1.2 km" above. Whole metres, one decimal km.
String formatDistance(double meters) {
  if (meters < 1000) return '${meters.round()} m';
  return '${(meters / 1000).toStringAsFixed(1)} km';
}

/// The walking-state banner: where you're headed and how far.
class NextStopBanner extends StatelessWidget {
  final String stopName;
  final double? distanceMeters;

  const NextStopBanner({
    super.key,
    required this.stopName,
    required this.distanceMeters,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final distanceLabel = distanceMeters == null
        ? 'Finding your location…'
        : '${formatDistance(distanceMeters!)} ahead';
    return Padding(
      padding: const EdgeInsets.all(Dims.md),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Next stop', style: theme.textTheme.labelMedium),
          const SizedBox(height: Dims.xs),
          Text(stopName, style: theme.textTheme.headlineSmall),
          const SizedBox(height: Dims.xs),
          Text(distanceLabel, style: theme.textTheme.bodyMedium),
        ],
      ),
    );
  }
}
```

Note: confirm the exact `Dims` constant names (`Dims.md`, `Dims.xs`) against `mobile/lib/theme/dims.dart` and adjust; if a token is missing use the nearest existing one — do not hardcode a pixel literal.

- [ ] **Step 4: Run to verify it passes**

Run: `cd mobile && flutter test test/widgets/tour/next_stop_banner_test.dart` → PASS.

- [ ] **Step 5: Commit**

```bash
git add mobile/lib/widgets/tour/next_stop_banner.dart mobile/test/widgets/tour/next_stop_banner_test.dart
git commit -m "feat(mobile): NextStopBanner (name + distance) for the tour walk screen"
```

---

### Task 3: `StopAudioCard`

**Files:**
- Create: `mobile/lib/widgets/tour/stop_audio_card.dart`
- Test: `mobile/test/widgets/tour/stop_audio_card_test.dart`

**Interfaces:**
- Consumes: `ItineraryStop` (`poiName`, `lensDisplay`).
- Produces: `StopAudioCard({required ItineraryStop stop, required bool isPlaying, required VoidCallback onReplay, required VoidCallback onSkip})`.

- [ ] **Step 1: Write the failing test**

`mobile/test/widgets/tour/stop_audio_card_test.dart`:

```dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ondoway/models/trip.dart';
import 'package:ondoway/widgets/tour/stop_audio_card.dart';

const _stop = ItineraryStop(
  sortOrder: 0, poiId: 'louvre', poiName: 'The Louvre',
  lat: 48.8606, lng: 2.3376, beatId: 'b0',
  lensName: 'art_history', lensDisplay: 'Art & History',
  durationMin: 15, importanceTier: 1, startTime: '10:00',
  audioUrl: 'https://cdn.example/louvre.mp3',
);

void main() {
  testWidgets('renders stop name, lens chip, and playing state', (tester) async {
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(body: StopAudioCard(
        stop: _stop, isPlaying: true, onReplay: () {}, onSkip: () {},
      )),
    ));
    expect(find.textContaining('The Louvre'), findsOneWidget);
    expect(find.textContaining('Art & History'), findsOneWidget);
    expect(find.textContaining('Playing'), findsOneWidget);
  });

  testWidgets('Replay and Skip fire their callbacks', (tester) async {
    var replayed = 0, skipped = 0;
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(body: StopAudioCard(
        stop: _stop, isPlaying: false,
        onReplay: () => replayed++, onSkip: () => skipped++,
      )),
    ));
    await tester.tap(find.byKey(const Key('tour-replay')));
    await tester.tap(find.byKey(const Key('tour-skip')));
    expect(replayed, 1);
    expect(skipped, 1);
  });
}
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd mobile && flutter test test/widgets/tour/stop_audio_card_test.dart` → FAIL ("StopAudioCard isn't defined").

- [ ] **Step 3: Implement**

`mobile/lib/widgets/tour/stop_audio_card.dart`:

```dart
import 'package:flutter/material.dart';
import 'package:ondoway/models/trip.dart';
import 'package:ondoway/theme/dims.dart';

/// The story-state card: what's playing now + manual Replay/Skip.
class StopAudioCard extends StatelessWidget {
  final ItineraryStop stop;
  final bool isPlaying;
  final VoidCallback onReplay;
  final VoidCallback onSkip;

  const StopAudioCard({
    super.key,
    required this.stop,
    required this.isPlaying,
    required this.onReplay,
    required this.onSkip,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      margin: const EdgeInsets.all(Dims.md),
      child: Padding(
        padding: const EdgeInsets.all(Dims.md),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (stop.lensDisplay.isNotEmpty)
              Chip(label: Text(stop.lensDisplay)),
            const SizedBox(height: Dims.xs),
            Text(stop.poiName, style: theme.textTheme.headlineSmall),
            const SizedBox(height: Dims.xs),
            Text(isPlaying ? 'Playing…' : 'Paused', style: theme.textTheme.bodyMedium),
            const SizedBox(height: Dims.sm),
            Row(
              children: [
                TextButton.icon(
                  key: const Key('tour-replay'),
                  onPressed: onReplay,
                  icon: const Icon(Icons.replay),
                  label: const Text('Replay'),
                ),
                const Spacer(),
                TextButton.icon(
                  key: const Key('tour-skip'),
                  onPressed: onSkip,
                  icon: const Icon(Icons.skip_next),
                  label: const Text('Skip'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
```

- [ ] **Step 4: Run to verify it passes** → PASS.

- [ ] **Step 5: Commit**

```bash
git add mobile/lib/widgets/tour/stop_audio_card.dart mobile/test/widgets/tour/stop_audio_card_test.dart
git commit -m "feat(mobile): StopAudioCard (now-playing + Replay/Skip) for the tour walk screen"
```

---

### Task 4: `TourWalkPage` — lifecycle + walking/story rendering

**Files:**
- Modify: `mobile/lib/main.dart:68` (expose `audioService` as `AudioProvider`)
- Create: `mobile/lib/pages/tour_walk_page.dart`
- Test: `mobile/test/pages/tour_walk_page_test.dart`

**Interfaces:**
- Consumes: `TourPlaybackService`, `AudioProvider` (from context); `GeneratedTrip`, `NextStopBanner`, `StopAudioCard`.
- Produces: `TourWalkPage({required GeneratedTrip trip})`.

- [ ] **Step 1: Expose `AudioProvider` in main.dart**

Change the redundant second audio registration so the same instance is also available under its interface (existing `AudioService` consumers are untouched by the first registration):

```dart
// mobile/lib/main.dart — line ~68, was: ChangeNotifierProvider.value(value: audioService),
ChangeNotifierProvider<AudioProvider>.value(value: audioService),
```

Add the import if not present: `import 'package:ondoway/services/providers.dart';`.

- [ ] **Step 2: Write the failing test**

`mobile/test/pages/tour_walk_page_test.dart`:

```dart
@Tags(['vm'])
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ondoway/pages/tour_walk_page.dart';
import 'package:ondoway/services/providers.dart';
import 'package:ondoway/services/tour_playback_service.dart';
import 'package:provider/provider.dart';

import '../services/mocks/mock_audio_service.dart';
import '../services/mocks/mock_location_service.dart';
import '../support/trip_fixture.dart';

Widget _harness({
  required MockLocationService loc,
  required MockAudioService audio,
  required TourPlaybackService engine,
  required Widget child,
}) {
  return MultiProvider(
    providers: [
      ChangeNotifierProvider<LocationProvider>.value(value: loc),
      ChangeNotifierProvider<AudioProvider>.value(value: audio),
      ChangeNotifierProvider<TourPlaybackService>.value(value: engine),
    ],
    child: MaterialApp(home: child),
  );
}

void main() {
  testWidgets('walking state shows the next-stop banner; arriving plays audio and shows the story card',
      (tester) async {
    final trip = loadParisFixtureTrip();
    final loc = MockLocationService();
    final audio = MockAudioService();
    final engine = TourPlaybackService(locationService: loc, audioService: audio);

    await tester.pumpWidget(_harness(
      loc: loc, audio: audio, engine: engine,
      child: TourWalkPage(trip: trip),
    ));
    await tester.pumpAndSettle(); // let startTour() settle

    // Walking: heading to the first stop, no audio yet.
    expect(find.textContaining('The Louvre'), findsOneWidget);
    expect(audio.playCount, 0);

    // Walk into the first stop's geofence.
    loc.simulatePosition(48.8606, 2.3376);
    await tester.pumpAndSettle();

    expect(audio.playCount, 1);           // engine auto-played the stop
    expect(find.textContaining('Playing'), findsOneWidget); // story card
  });

  testWidgets('Skip advances to the next stop', (tester) async {
    final trip = loadParisFixtureTrip();
    final loc = MockLocationService();
    final audio = MockAudioService();
    final engine = TourPlaybackService(locationService: loc, audioService: audio);

    await tester.pumpWidget(_harness(
      loc: loc, audio: audio, engine: engine, child: TourWalkPage(trip: trip)));
    await tester.pumpAndSettle();

    // Arrive at stop 0 so the audio card (with Skip) is showing.
    loc.simulatePosition(48.8606, 2.3376);
    await tester.pumpAndSettle();
    expect(engine.currentStopIndex, 0);

    await tester.tap(find.byKey(const Key('tour-skip')));
    await tester.pumpAndSettle();
    expect(engine.currentStopIndex, 1);
  });
}
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd mobile && flutter test test/pages/tour_walk_page_test.dart --tags vm`
Expected: FAIL ("TourWalkPage isn't defined").

- [ ] **Step 4: Implement the page (walking/story only)**

`mobile/lib/pages/tour_walk_page.dart`:

```dart
import 'package:flutter/material.dart';
import 'package:ondoway/models/trip.dart';
import 'package:ondoway/services/providers.dart';
import 'package:ondoway/services/tour_playback_service.dart';
import 'package:ondoway/widgets/tour/next_stop_banner.dart';
import 'package:ondoway/widgets/tour/stop_audio_card.dart';
import 'package:provider/provider.dart';

/// Full-screen hands-free audio walk. A thin view over [TourPlaybackService]:
/// the engine owns geofence/auto-play/auto-advance; this renders its state.
class TourWalkPage extends StatefulWidget {
  final GeneratedTrip trip;
  const TourWalkPage({super.key, required this.trip});

  @override
  State<TourWalkPage> createState() => _TourWalkPageState();
}

class _TourWalkPageState extends State<TourWalkPage> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<TourPlaybackService>().startTour(widget.trip.stops);
    });
  }

  @override
  void dispose() {
    // The engine tears down tracking + releases the ducked audio session.
    context.read<TourPlaybackService>().stopTour();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final engine = context.watch<TourPlaybackService>();
    final audio = context.watch<AudioProvider>();
    final stop = engine.currentStop;

    return Scaffold(
      appBar: AppBar(title: Text(widget.trip.tripName)),
      body: SafeArea(
        child: stop == null
            ? const Center(child: Text('Preparing your walk…'))
            : Column(
                children: [
                  _ProgressText(
                    index: engine.currentStopIndex,
                    total: widget.trip.stops.length,
                  ),
                  Expanded(
                    child: Center(
                      child: audio.isPlaying
                          ? StopAudioCard(
                              stop: stop,
                              isPlaying: true,
                              onReplay: () => engine.skipToStop(engine.currentStopIndex),
                              onSkip: () => engine.skipToStop(engine.currentStopIndex + 1),
                            )
                          : NextStopBanner(
                              stopName: stop.poiName,
                              distanceMeters: engine.distanceToNext,
                            ),
                    ),
                  ),
                ],
              ),
      ),
    );
  }
}

class _ProgressText extends StatelessWidget {
  final int index;
  final int total;
  const _ProgressText({required this.index, required this.total});

  @override
  Widget build(BuildContext context) {
    final n = index < 0 ? 1 : index + 1;
    return Padding(
      padding: const EdgeInsets.all(12),
      child: Text('Stop $n of $total', style: Theme.of(context).textTheme.labelLarge),
    );
  }
}
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd mobile && flutter test test/pages/tour_walk_page_test.dart --tags vm` → PASS.

- [ ] **Step 6: Undo-test**

Temporarily change `onSkip` to `() {}` → re-run → the "Skip advances" test goes RED. Restore → GREEN.

- [ ] **Step 7: Commit**

```bash
git add mobile/lib/main.dart mobile/lib/pages/tour_walk_page.dart mobile/test/pages/tour_walk_page_test.dart
git commit -m "feat(mobile): TourWalkPage walking/story states driven by TourPlaybackService"
```

---

### Task 5: `TourWalkPage` — approaching nudge + completed panel

**Files:**
- Modify: `mobile/lib/pages/tour_walk_page.dart`
- Modify: `mobile/test/pages/tour_walk_page_test.dart`

**Interfaces:**
- Consumes: `engine.hasPendingStop`, `engine.state == TourState.completed`, `engine.acceptPendingStop()`, `engine.dismissPending()`, `engine.nextStop`.

- [ ] **Step 1: Write the failing tests (append to the page test file)**

```dart
  testWidgets('approaching the next stop shows the nudge; Play now accepts it',
      (tester) async {
    final trip = loadParisFixtureTrip();
    final loc = MockLocationService();
    final audio = MockAudioService();
    final engine = TourPlaybackService(locationService: loc, audioService: audio);

    await tester.pumpWidget(_harness(
      loc: loc, audio: audio, engine: engine, child: TourWalkPage(trip: trip)));
    await tester.pumpAndSettle();

    loc.simulatePosition(48.8606, 2.3376); // arrive stop 0 -> audio plays
    await tester.pumpAndSettle();
    // Walk into stop 1's radius while stop 0 audio still "plays".
    loc.simulatePosition(48.8570, 2.3410);
    await tester.pumpAndSettle();

    expect(engine.hasPendingStop, true);
    expect(find.byKey(const Key('tour-nudge-accept')), findsOneWidget);

    await tester.tap(find.byKey(const Key('tour-nudge-accept')));
    await tester.pumpAndSettle();
    expect(engine.currentStopIndex, 1);
  });

  testWidgets('completed tour shows the done panel', (tester) async {
    final trip = loadParisFixtureTrip();
    final loc = MockLocationService();
    final audio = MockAudioService();
    final engine = TourPlaybackService(locationService: loc, audioService: audio);

    await tester.pumpWidget(_harness(
      loc: loc, audio: audio, engine: engine, child: TourWalkPage(trip: trip)));
    await tester.pumpAndSettle();

    // Jump to the final stop, play it, then complete -> engine goes `completed`.
    engine.skipToStop(2);
    await tester.pumpAndSettle();
    audio.simulateComplete();
    await tester.pumpAndSettle();

    expect(engine.state, TourState.completed);
    expect(find.textContaining('Tour complete'), findsOneWidget);
  });
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd mobile && flutter test test/pages/tour_walk_page_test.dart --tags vm`
Expected: the two new tests FAIL (`tour-nudge-accept` not found; "Tour complete" not found).

- [ ] **Step 3: Implement — add completed + nudge to `build`**

Replace the `body:` expression so a completed state short-circuits, and an approaching state overlays a nudge:

```dart
      body: SafeArea(
        child: engine.state == TourState.completed
            ? _CompletePanel(onDone: () => Navigator.of(context).maybePop())
            : Stack(
                children: [
                  stop == null
                      ? const Center(child: Text('Preparing your walk…'))
                      : Column(
                          children: [
                            _ProgressText(
                              index: engine.currentStopIndex,
                              total: widget.trip.stops.length,
                            ),
                            Expanded(
                              child: Center(
                                child: audio.isPlaying
                                    ? StopAudioCard(
                                        stop: stop,
                                        isPlaying: true,
                                        onReplay: () => engine.skipToStop(engine.currentStopIndex),
                                        onSkip: () => engine.skipToStop(engine.currentStopIndex + 1),
                                      )
                                    : NextStopBanner(
                                        stopName: stop.poiName,
                                        distanceMeters: engine.distanceToNext,
                                      ),
                              ),
                            ),
                          ],
                        ),
                  if (engine.hasPendingStop && engine.nextStop != null)
                    Align(
                      alignment: Alignment.bottomCenter,
                      child: _ApproachingNudge(
                        stopName: engine.nextStop!.poiName,
                        onAccept: engine.acceptPendingStop,
                        onDismiss: engine.dismissPending,
                      ),
                    ),
                ],
              ),
      ),
```

Add the two private widgets to the file:

```dart
class _ApproachingNudge extends StatelessWidget {
  final String stopName;
  final VoidCallback onAccept;
  final VoidCallback onDismiss;
  const _ApproachingNudge({
    required this.stopName, required this.onAccept, required this.onDismiss});

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.all(16),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text('Approaching $stopName', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceEvenly,
              children: [
                TextButton(
                  onPressed: onDismiss,
                  child: const Text('Keep listening'),
                ),
                FilledButton(
                  key: const Key('tour-nudge-accept'),
                  onPressed: onAccept,
                  child: const Text('Play now'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _CompletePanel extends StatelessWidget {
  final VoidCallback onDone;
  const _CompletePanel({required this.onDone});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text('Tour complete', style: Theme.of(context).textTheme.headlineSmall),
          const SizedBox(height: 12),
          FilledButton(onPressed: onDone, child: const Text('Done')),
        ],
      ),
    );
  }
}
```

- [ ] **Step 4: Run to verify all page tests pass** → PASS.

- [ ] **Step 5: Undo-test**

Change `if (engine.hasPendingStop ...)` to `if (false ...)` → the nudge test goes RED. Restore → GREEN.

- [ ] **Step 6: Commit**

```bash
git add mobile/lib/pages/tour_walk_page.dart mobile/test/pages/tour_walk_page_test.dart
git commit -m "feat(mobile): approaching-nudge + completed panel on TourWalkPage"
```

---

### Task 6: Route `/trip/:tripId/walk` + entry from the itinerary

**Files:**
- Modify: `mobile/lib/router.dart`
- Modify: `mobile/lib/pages/trip_itinerary_page.dart` (add a "Start walking" button)
- Test: `mobile/test/pages/tour_walk_route_test.dart`

**Interfaces:**
- Consumes: `TourWalkPage`, `GeneratedTrip`, `TripService` (existing fetch-by-id).

- [ ] **Step 1: Write the failing route test**

`mobile/test/pages/tour_walk_route_test.dart`:

```dart
@Tags(['vm'])
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:ondoway/models/trip.dart';
import 'package:ondoway/pages/tour_walk_page.dart';
import 'package:ondoway/services/providers.dart';
import 'package:ondoway/services/tour_playback_service.dart';
import 'package:provider/provider.dart';

import '../services/mocks/mock_audio_service.dart';
import '../services/mocks/mock_location_service.dart';
import '../support/trip_fixture.dart';

void main() {
  testWidgets('navigating to /trip/:id/walk with a trip extra renders TourWalkPage',
      (tester) async {
    final trip = loadParisFixtureTrip();
    final loc = MockLocationService();
    final audio = MockAudioService();
    final engine = TourPlaybackService(locationService: loc, audioService: audio);

    final router = GoRouter(
      initialLocation: '/trip/${trip.tripId}/walk',
      routes: [
        GoRoute(
          path: '/trip/:tripId/walk',
          builder: (context, state) =>
              TourWalkPage(trip: state.extra! as GeneratedTrip),
        ),
      ],
    );

    await tester.pumpWidget(MultiProvider(
      providers: [
        ChangeNotifierProvider<LocationProvider>.value(value: loc),
        ChangeNotifierProvider<AudioProvider>.value(value: audio),
        ChangeNotifierProvider<TourPlaybackService>.value(value: engine),
      ],
      child: MaterialApp.router(routerConfig: router),
    ));
    // extra isn't passed by initialLocation; drive it explicitly:
    router.go('/trip/${trip.tripId}/walk', extra: trip);
    await tester.pumpAndSettle();

    expect(find.byType(TourWalkPage), findsOneWidget);
  });
}
```

Note: this test validates the builder contract in isolation (a mini-router), not the app router, to stay hermetic. The real wiring is Step 3.

- [ ] **Step 2: Run to verify it fails** — FAIL until `TourWalkPage` import/route compile cleanly (it already exists from Task 4; the test mainly guards the `extra`→`trip` contract). If it passes immediately, tighten it to assert `find.text(trip.tripName)`.

- [ ] **Step 3: Add the real route to `router.dart`**

Inside the top-level `routes: [...]` list (alongside the existing full-screen `/trip/:tripId`), add:

```dart
GoRoute(
  path: '/trip/:tripId/walk',
  builder: (context, state) {
    final extra = state.extra;
    if (extra is GeneratedTrip) return TourWalkPage(trip: extra);
    // Cold/deep-link entry: fetch by id via the existing service.
    final tripId = state.pathParameters['tripId'] ?? '';
    return _TourWalkLoader(tripId: tripId);
  },
),
```

Add imports: `import 'package:ondoway/pages/tour_walk_page.dart';` and `import 'package:ondoway/models/trip.dart';`. Implement `_TourWalkLoader` as a small `FutureBuilder` over the existing `TripService` fetch-by-id (mirror how `TripItineraryPage` loads a trip in `mobile/lib/pages/trip_itinerary_page.dart:87+`); show a spinner while loading, `TourWalkPage(trip:)` when ready.

- [ ] **Step 4: Add the "Start walking" entry button**

In `mobile/lib/pages/trip_itinerary_page.dart`, where the loaded `GeneratedTrip` is in scope, add a primary button:

```dart
FilledButton.icon(
  onPressed: () => context.push('/trip/${trip.tripId}/walk', extra: trip),
  icon: const Icon(Icons.directions_walk),
  label: const Text('Start walking'),
),
```

Match the surrounding widget style; use the design-system button if that's the established pattern on this page.

- [ ] **Step 5: Run the full suite + analyze**

```bash
make flutter-analyze
make flutter-test
```
Expected: analyzer clean; full suite green (existing 271 + the new tests).

- [ ] **Step 6: Commit**

```bash
git add mobile/lib/router.dart mobile/lib/pages/trip_itinerary_page.dart mobile/test/pages/tour_walk_route_test.dart
git commit -m "feat(mobile): route + itinerary entry point for the tour walk screen"
```

---

## On-device acceptance (after all tasks — the real bar)

Not automatable; this is the Slice-1 proof:
1. Build to device: `make flutter-device-profile`.
2. Golden path on prod: log in (magic link) → pick lenses → build-now (generate) → review → **Start walking**.
3. **Lock the screen, put the phone in your pocket, walk the route in Paris.** Audio must auto-fire at each stop; the progress + banner must update. Screenshot/transcript per stop.
4. Repeat one leg in airplane mode to confirm cached audio still plays (offline-prefetch story; tracked, not owned by this slice).

## Self-review notes

- **Spec coverage:** §3 states → Tasks 4–5; §4 nav → Task 6; §5 components → Tasks 2–5; §7 fixture → Task 1; §9 tests → every task + on-device section; §11 "no engine changes" → honored (page reads existing getters; the only lib change outside new files is the 1-line `main.dart` provider-type exposure, which is not an engine change).
- **Deviations from the design (approved refinements):** bearing arrow + `geo.dart` dropped (engine already exposes `distanceToNext`; direction ships with the map slice); one additive `main.dart` line exposes `audioService` as `AudioProvider` for testability.
- **Deferred:** map/`transit_polyline`, true pause/resume, rich completion recap (Slice 1.7), airplane-mode prefetch impl.
