@Tags(['vm'])
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ondoway/models/trip.dart';
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

// The walk screen carries a one-second HEARTBEAT: standing still is measured by
// time passing, because the geolocator sends no fix while nobody moves. A
// repeating timer means this tree never "settles" — pumpAndSettle advances the
// fake clock and the ticker fires again, forever — so these tests pump explicit
// frames instead. That is a property of the screen, not a workaround.
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
    await tester.pump(const Duration(milliseconds: 350)); // let startTour() settle

    // Walking: heading to the first stop, no audio yet -> the walking bar shows.
    expect(find.byKey(const Key('tour-walking-skip')), findsOneWidget);
    expect(audio.playCount, 0);

    // Walk into the first stop's geofence.
    loc.simulatePosition(48.8606, 2.3376);
    await tester.pump(const Duration(milliseconds: 350));

    expect(audio.playCount, 1); // engine auto-played the stop
    // Story: the now-playing player shows the stop title + transport controls.
    expect(find.textContaining('The Louvre'), findsWidgets);
    expect(find.byKey(const Key('tour-playpause')), findsOneWidget);
  });

  testWidgets('Skip advances to the next stop', (tester) async {
    final trip = loadParisFixtureTrip();
    final loc = MockLocationService();
    final audio = MockAudioService();
    final engine = TourPlaybackService(locationService: loc, audioService: audio);

    await tester.pumpWidget(_harness(
      loc: loc, audio: audio, engine: engine, child: TourWalkPage(trip: trip)));
    await tester.pump(const Duration(milliseconds: 350));

    // Arrive at stop 0 so the audio card (with Skip) is showing.
    loc.simulatePosition(48.8606, 2.3376);
    await tester.pump(const Duration(milliseconds: 350));
    expect(engine.currentStopIndex, 0);

    await tester.tap(find.byKey(const Key('tour-skip')));
    await tester.pump(const Duration(milliseconds: 350));
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
    await tester.pump(const Duration(milliseconds: 350));

    loc.simulatePosition(48.8606, 2.3376); // arrive stop 0 -> audio plays
    await tester.pump(const Duration(milliseconds: 350));
    // Walk into stop 1's radius while stop 0 audio still "plays".
    loc.simulatePosition(48.8570, 2.3410);
    await tester.pump(const Duration(milliseconds: 350));

    expect(engine.hasPendingStop, true);
    expect(find.byKey(const Key('tour-nudge-accept')), findsOneWidget);

    await tester.tap(find.byKey(const Key('tour-nudge-accept')));
    await tester.pump(const Duration(milliseconds: 350));
    expect(engine.currentStopIndex, 1);
  });

  testWidgets('completed tour shows the done panel', (tester) async {
    final trip = loadParisFixtureTrip();
    final loc = MockLocationService();
    final audio = MockAudioService();
    final engine = TourPlaybackService(locationService: loc, audioService: audio);

    await tester.pumpWidget(_harness(
        loc: loc, audio: audio, engine: engine, child: TourWalkPage(trip: trip)));
    await tester.pump(const Duration(milliseconds: 350));

    // Jump to the final stop, play it, then complete -> engine goes `completed`.
    engine.skipToStop(2);
    await tester.pump(const Duration(milliseconds: 350));
    audio.simulateComplete();
    await tester.pump(const Duration(milliseconds: 350));

    expect(engine.state, TourState.completed);
    expect(find.textContaining('Tour complete'), findsOneWidget);
  });

  testWidgets('walking state has a manual Skip that advances without a geofence hit',
      (tester) async {
    final trip = loadParisFixtureTrip();
    final loc = MockLocationService();
    final audio = MockAudioService();
    final engine = TourPlaybackService(locationService: loc, audioService: audio);

    await tester.pumpWidget(_harness(
        loc: loc, audio: audio, engine: engine, child: TourWalkPage(trip: trip)));
    await tester.pump(const Duration(milliseconds: 350));

    // Still walking: no GPS fix yet, no audio playing.
    expect(engine.currentStopIndex, 0);
    expect(audio.isPlaying, false);

    await tester.tap(find.byKey(const Key('tour-walking-skip')));
    await tester.pump(const Duration(milliseconds: 350));

    expect(engine.currentStopIndex, 1);
  });

  testWidgets('a stop with no audio shows "No audio for this stop" alongside Skip',
      (tester) async {
    const noAudioStop = ItineraryStop(
      sortOrder: 0,
      poiId: 'poi-no-audio',
      poiName: 'Silent Courtyard',
      lat: 48.8606,
      lng: 2.3376,
      beatId: 'beat-no-audio',
      lensName: 'history',
      lensDisplay: 'History',
      durationMin: 5,
      importanceTier: 1,
      startTime: '10:00',
      audioUrl: null,
    );
    final trip = GeneratedTrip(
      tripId: 'trip-no-audio',
      tripName: 'No Audio Trip',
      profileId: 'profile-1',
      totalStops: 1,
      totalDurationMin: 5,
      anchorCount: 1,
      flavourCount: 1,
      stops: const [noAudioStop],
    );
    final loc = MockLocationService();
    final audio = MockAudioService();
    final engine = TourPlaybackService(locationService: loc, audioService: audio);

    await tester.pumpWidget(_harness(
        loc: loc, audio: audio, engine: engine, child: TourWalkPage(trip: trip)));
    await tester.pump(const Duration(milliseconds: 350));

    expect(find.textContaining('No audio here'), findsOneWidget);
    expect(find.byKey(const Key('tour-walking-skip')), findsOneWidget);
  });

  testWidgets('dismissing the nudge clears hasPendingStop and hides the nudge',
      (tester) async {
    final trip = loadParisFixtureTrip();
    final loc = MockLocationService();
    final audio = MockAudioService();
    final engine = TourPlaybackService(locationService: loc, audioService: audio);

    await tester.pumpWidget(_harness(
        loc: loc, audio: audio, engine: engine, child: TourWalkPage(trip: trip)));
    await tester.pump(const Duration(milliseconds: 350));

    loc.simulatePosition(48.8606, 2.3376); // arrive stop 0 -> audio plays
    await tester.pump(const Duration(milliseconds: 350));
    // Walk into stop 1's radius while stop 0 audio still "plays".
    loc.simulatePosition(48.8570, 2.3410);
    await tester.pump(const Duration(milliseconds: 350));

    expect(engine.hasPendingStop, true);

    await tester.tap(find.text('Keep listening'));
    await tester.pump(const Duration(milliseconds: 350));

    expect(engine.hasPendingStop, false);
    expect(find.byKey(const Key('tour-nudge-accept')), findsNothing);
  });
}
