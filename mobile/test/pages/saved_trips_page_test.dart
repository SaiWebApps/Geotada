import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:provider/provider.dart';
import 'package:ondoway/models/trip.dart';
import 'package:ondoway/pages/saved_trips_page.dart';
import 'package:ondoway/services/trip_service.dart';

Widget _buildTestWidget({TripService? tripService}) {
  final mockClient = MockClient((r) async => http.Response('', 200));
  return MaterialApp(
    theme: ThemeData(
      colorSchemeSeed: const Color(0xFF3D5AFE),
      useMaterial3: true,
      brightness: Brightness.dark,
    ),
    home: ChangeNotifierProvider<TripService>.value(
      value: tripService ?? TripService(httpClient: mockClient),
      child: const Scaffold(body: SavedTripsPage()),
    ),
  );
}

GeneratedTrip _sampleTrip({String id = 'trip-1', String name = 'Paris Day Trip'}) {
  return GeneratedTrip(
    tripId: id,
    tripName: name,
    profileId: 'profile-1',
    totalStops: 5,
    totalDurationMin: 120,
    anchorCount: 1,
    flavourCount: 4,
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
    ],
  );
}

void main() {
  group('SavedTripsPage', () {
    testWidgets('shows empty state when no trips', (tester) async {
      await tester.pumpWidget(_buildTestWidget());
      await tester.pumpAndSettle();

      expect(find.text('No saved trips yet'), findsOneWidget);
      expect(find.byIcon(Icons.luggage_outlined), findsOneWidget);
      expect(
        find.text('Generate a trip from the Explore tab to get started.'),
        findsOneWidget,
      );
    });

    testWidgets('shows trip cards when trips exist', (tester) async {
      final mockClient = MockClient((r) async => http.Response('', 200));
      final service = TripService(httpClient: mockClient);
      service.saveTrip(_sampleTrip());
      service.saveTrip(_sampleTrip(id: 'trip-2', name: 'Evening Walk'));

      await tester.pumpWidget(_buildTestWidget(tripService: service));
      await tester.pumpAndSettle();

      expect(find.text('Paris Day Trip'), findsOneWidget);
      expect(find.text('Evening Walk'), findsOneWidget);
      expect(find.text('No saved trips yet'), findsNothing);
    });

    testWidgets('shows stop count and duration in trip cards', (tester) async {
      final mockClient = MockClient((r) async => http.Response('', 200));
      final service = TripService(httpClient: mockClient);
      service.saveTrip(_sampleTrip());

      await tester.pumpWidget(_buildTestWidget(tripService: service));
      await tester.pumpAndSettle();

      expect(find.textContaining('5 stops'), findsOneWidget);
      expect(find.textContaining('120 min'), findsOneWidget);
    });
  });
}
