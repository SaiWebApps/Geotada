import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:provider/provider.dart';
import 'package:ondoway/models/trip.dart';
import 'package:ondoway/pages/trip_itinerary_page.dart';
import 'package:ondoway/services/trip_service.dart';

GeneratedTrip _sampleTrip({
  String id = 'trip-1',
  String name = 'Paris Day Trip',
}) {
  return GeneratedTrip(
    tripId: id,
    tripName: name,
    profileId: 'profile-1',
    totalStops: 7,
    totalDurationMin: 90,
    anchorCount: 1,
    flavourCount: 6,
    stops: const [
      ItineraryStop(
        sortOrder: 1,
        poiId: 'poi-1',
        poiName: 'Eiffel Tower',
        lat: 48.8584,
        lng: 2.2945,
        beatId: 'beat-1',
        lensName: 'dark_history',
        lensDisplay: 'Dark History',
        durationMin: 5,
        importanceTier: 5,
        startTime: '09:00',
      ),
      ItineraryStop(
        sortOrder: 2,
        poiId: 'poi-2',
        poiName: 'Notre-Dame',
        lat: 48.8530,
        lng: 2.3499,
        beatId: 'beat-2',
        lensName: 'historic_arch',
        lensDisplay: 'Historic Architecture',
        durationMin: 4,
        importanceTier: 3,
        startTime: '09:30',
      ),
    ],
  );
}

Widget _buildTestWidget({
  required TripService tripService,
  String tripId = 'trip-1',
}) {
  final router = GoRouter(
    initialLocation: '/trip/$tripId',
    routes: [
      GoRoute(
        path: '/trip/:tripId',
        builder: (context, state) => ChangeNotifierProvider<TripService>.value(
          value: tripService,
          child: TripItineraryPage(tripId: state.pathParameters['tripId']!),
        ),
      ),
      GoRoute(
        path: '/saved-trips',
        builder: (context, state) => const Scaffold(
          body: Center(child: Text('Saved Trips')),
        ),
      ),
    ],
  );
  return MaterialApp.router(
    routerConfig: router,
    theme: ThemeData(
      colorSchemeSeed: const Color(0xFF3D5AFE),
      useMaterial3: true,
      brightness: Brightness.dark,
    ),
  );
}

void main() {
  group('TripItineraryPage', () {
    late TripService tripService;

    setUp(() {
      final mockClient = MockClient((r) async => http.Response('', 200));
      tripService = TripService(httpClient: mockClient);
    });

    testWidgets('renders trip summary card', (tester) async {
      final trip = _sampleTrip();
      tripService.saveTrip(trip);

      await tester.pumpWidget(_buildTestWidget(
        tripService: tripService,
        tripId: trip.tripId,
      ));
      await tester.pump();
      await tester.pump();

      // Summary card shows total stops, duration, anchors, and flavour labels
      expect(find.text('Stops'), findsOneWidget);
      expect(find.text('Duration'), findsOneWidget);
      expect(find.text('Anchors'), findsOneWidget);
      expect(find.text('Flavour'), findsOneWidget);
      // Values: 7 stops, 1h 30m duration, 1 anchor, 6 flavour
      expect(find.text('7'), findsOneWidget);
      expect(find.text('1h 30m'), findsOneWidget);
      expect(find.text('6'), findsOneWidget);
    });

    testWidgets('renders stop cards with POI names and times', (tester) async {
      final trip = _sampleTrip();
      tripService.saveTrip(trip);

      await tester.pumpWidget(_buildTestWidget(
        tripService: tripService,
        tripId: trip.tripId,
      ));
      await tester.pump();
      await tester.pump();

      expect(find.text('Eiffel Tower'), findsOneWidget);
      expect(find.text('Notre-Dame'), findsOneWidget);
      expect(find.text('09:00'), findsOneWidget);
      expect(find.text('09:30'), findsOneWidget);
    });

    testWidgets('shows lens chip on stop cards', (tester) async {
      final trip = _sampleTrip();
      tripService.saveTrip(trip);

      await tester.pumpWidget(_buildTestWidget(
        tripService: tripService,
        tripId: trip.tripId,
      ));
      await tester.pump();
      await tester.pump();

      expect(find.text('Dark History'), findsOneWidget);
      expect(find.text('Historic Architecture'), findsOneWidget);
    });

    testWidgets('save trip FAB calls tripService.saveTrip', (tester) async {
      // Use lastGenerated path (trip in lastGenerated, not in savedTrips)
      final mockClient = MockClient((request) async {
        if (request.url.path.contains('/trips/generate')) {
          return http.Response(
            '{"trip_id":"trip-gen","trip_name":"Generated","profile_id":"p1",'
            '"total_stops":1,"total_duration_min":30,"anchor_count":0,"flavour_count":1,'
            '"stops":[{"sort_order":1,"poi_id":"poi-1","poi_name":"Test POI",'
            '"lat":48.85,"lng":2.34,"beat_id":"b1","lens_name":"a","lens_display":"A",'
            '"duration_min":5,"importance_tier":3,"start_time":"09:00"}]}',
            201,
          );
        }
        return http.Response('', 200);
      });
      final service = TripService(httpClient: mockClient);

      // Generate a trip so lastGenerated is set
      await service.generateTrip(
        profileId: 'p1',
        centerLat: 48.85,
        centerLng: 2.34,
        startDate: '2026-05-04',
        endDate: '2026-05-04',
        accessToken: 'tok',
      );

      expect(service.lastGenerated, isNotNull);
      expect(service.savedTrips, isEmpty);

      await tester.pumpWidget(_buildTestWidget(
        tripService: service,
        tripId: 'trip-gen',
      ));
      await tester.pump();
      await tester.pump();

      // Tap the Save Trip FAB
      await tester.tap(find.text('Save Trip'));
      await tester.pump();

      // saveTrip should have been called — verify savedTrips is no longer empty
      expect(service.savedTrips.length, 1);
      expect(service.savedTrips.first.tripId, 'trip-gen');
    });

    testWidgets('shows anchor indicator for importance_tier 5', (tester) async {
      final trip = _sampleTrip();
      tripService.saveTrip(trip);

      await tester.pumpWidget(_buildTestWidget(
        tripService: tripService,
        tripId: trip.tripId,
      ));
      await tester.pump();
      await tester.pump();

      // The summary card has an Icons.star (size 20) for the Anchors section
      // AND the stop card shows Icons.star (size 16) for anchor stops.
      // Both should be present — verify at least the small one for the stop card.
      final starIcons = find.byIcon(Icons.star);
      expect(starIcons, findsNWidgets(2)); // one in summary, one on stop card
    });

    testWidgets('shows trip not found for unknown tripId', (tester) async {
      await tester.pumpWidget(_buildTestWidget(
        tripService: tripService,
        tripId: 'nonexistent',
      ));
      await tester.pump();
      await tester.pump();

      expect(find.text('Trip not found'), findsOneWidget);
    });
  });
}
