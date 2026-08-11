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
}
