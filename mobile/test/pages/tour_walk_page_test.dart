@Tags(['vm'])
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ondoway/pages/tour_walk_page.dart';
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
}
