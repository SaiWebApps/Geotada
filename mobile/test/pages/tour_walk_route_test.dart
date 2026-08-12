@Tags(['vm'])
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:ondoway/models/trip.dart';
import 'package:ondoway/pages/tour_walk_page.dart';
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
      // The mini-router's first build happens synchronously inside
      // pumpWidget, before the router.go() below ever runs — without
      // initialExtra, `state.extra` is null on that first pass and the
      // builder's `state.extra! as GeneratedTrip` throws.
      initialExtra: trip,
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
