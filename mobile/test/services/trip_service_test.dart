import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:ondoway/models/trip.dart';
import 'package:ondoway/services/trip_service.dart';

Map<String, dynamic> _sampleTripResponse() => {
      'trip_id': 'trip-123',
      'trip_name': 'Trip (2026-05-04)',
      'profile_id': 'profile-abc',
      'total_stops': 2,
      'total_duration_min': 8,
      'anchor_count': 1,
      'flavour_count': 1,
      'stops': [
        {
          'sort_order': 1,
          'poi_id': 'poi-1',
          'poi_name': 'Eiffel Tower',
          'lat': 48.8584,
          'lng': 2.2945,
          'beat_id': 'beat-1',
          'lens_name': 'dark_history',
          'lens_display': 'Dark History',
          'duration_min': 5,
          'importance_tier': 5,
          'start_time': '09:00',
        },
        {
          'sort_order': 2,
          'poi_id': 'poi-2',
          'poi_name': 'Louvre',
          'lat': 48.8606,
          'lng': 2.3376,
          'beat_id': 'beat-2',
          'lens_name': 'scandal',
          'lens_display': 'Scandal & Intrigue',
          'duration_min': 3,
          'importance_tier': 3,
          'start_time': '09:05',
        },
      ],
    };

void main() {
  group('TripService', () {
    test('generateTrip sends correct POST body', () async {
      Map<String, dynamic>? capturedBody;

      final client = MockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, contains('/trips/generate'));
        expect(request.headers['Content-Type'], 'application/json');
        expect(request.headers['Authorization'], 'Bearer test-token');
        capturedBody = jsonDecode(request.body) as Map<String, dynamic>;
        return http.Response(jsonEncode(_sampleTripResponse()), 201);
      });

      final service = TripService(httpClient: client);
      await service.generateTrip(
        profileId: 'profile-abc',
        centerLat: 48.8566,
        centerLng: 2.3522,
        startDate: '2026-05-04',
        endDate: '2026-05-06',
        accessToken: 'test-token',
        radiusM: 3000,
        maxStops: 10,
        durationMin: 480,
        startTime: '09:00',
      );

      expect(capturedBody, isNotNull);
      expect(capturedBody!['profile_id'], 'profile-abc');
      expect(capturedBody!['center_lat'], 48.8566);
      expect(capturedBody!['center_lng'], 2.3522);
      expect(capturedBody!['radius_m'], 3000);
      expect(capturedBody!['max_stops'], 10);
      expect(capturedBody!['duration_min'], 480);
      expect(capturedBody!['start_date'], '2026-05-04');
      expect(capturedBody!['end_date'], '2026-05-06');
      expect(capturedBody!['start_time'], '09:00');
      expect(capturedBody!['kid_friendly_only'], false);
    });

    test('generateTrip returns parsed GeneratedTrip on 201', () async {
      final client = MockClient((request) async {
        return http.Response(jsonEncode(_sampleTripResponse()), 201);
      });

      final service = TripService(httpClient: client);
      final trip = await service.generateTrip(
        profileId: 'profile-abc',
        centerLat: 48.8566,
        centerLng: 2.3522,
        startDate: '2026-05-04',
        endDate: '2026-05-06',
        accessToken: 'token',
      );

      expect(trip.tripId, 'trip-123');
      expect(trip.tripName, 'Trip (2026-05-04)');
      expect(trip.totalStops, 2);
      expect(trip.stops.length, 2);
      expect(trip.stops[0].poiName, 'Eiffel Tower');
      expect(service.lastGenerated, isNotNull);
      expect(service.isGenerating, false);
    });

    test('generateTrip throws on 404 (profile not found)', () async {
      final client = MockClient((request) async {
        return http.Response(
          jsonEncode({'detail': "Profile 'bad-id' not found"}),
          404,
        );
      });

      final service = TripService(httpClient: client);

      expect(
        () => service.generateTrip(
          profileId: 'bad-id',
          centerLat: 48.8566,
          centerLng: 2.3522,
          startDate: '2026-05-04',
          endDate: '2026-05-06',
          accessToken: 'token',
        ),
        throwsA(isA<TripServiceException>()),
      );
    });

    test('generateTrip throws on 422 (no POIs in radius)', () async {
      final client = MockClient((request) async {
        return http.Response(
          jsonEncode(
            {'detail': 'No POIs found within the specified radius and filters'},
          ),
          422,
        );
      });

      final service = TripService(httpClient: client);

      expect(
        () => service.generateTrip(
          profileId: 'profile-abc',
          centerLat: 0.0,
          centerLng: 0.0,
          startDate: '2026-05-04',
          endDate: '2026-05-06',
          accessToken: 'token',
        ),
        throwsA(isA<TripServiceException>()),
      );
    });

    test('generateTrip sets error message on failure', () async {
      final client = MockClient((request) async {
        return http.Response(
          jsonEncode({'detail': 'No POIs found within the specified radius and filters'}),
          422,
        );
      });

      final service = TripService(httpClient: client);

      try {
        await service.generateTrip(
          profileId: 'profile-abc',
          centerLat: 0.0,
          centerLng: 0.0,
          startDate: '2026-05-04',
          endDate: '2026-05-06',
          accessToken: 'token',
        );
      } catch (_) {}

      expect(service.error, contains('No POIs found'));
      expect(service.isGenerating, false);
    });

    test('fetchSavedTrips returns list of trips', () async {
      final client = MockClient((request) async {
        expect(request.method, 'GET');
        expect(request.url.queryParameters['profile_id'], 'profile-abc');
        return http.Response(
          jsonEncode([_sampleTripResponse()]),
          200,
        );
      });

      final service = TripService(httpClient: client);
      final trips = await service.fetchSavedTrips('profile-abc', 'token');

      expect(trips.length, 1);
      expect(trips[0].tripId, 'trip-123');
      expect(service.savedTrips.length, 1);
    });

    test('fetchSavedTrips returns empty list when no trips', () async {
      final client = MockClient((request) async {
        return http.Response(jsonEncode([]), 200);
      });

      final service = TripService(httpClient: client);
      final trips = await service.fetchSavedTrips('profile-abc', 'token');

      expect(trips, isEmpty);
      expect(service.savedTrips, isEmpty);
    });

    test('fetchSavedTrips throws on 404', () async {
      final client = MockClient((request) async {
        return http.Response(
          jsonEncode({'detail': 'Profile not found'}),
          404,
        );
      });

      final service = TripService(httpClient: client);

      expect(
        () => service.fetchSavedTrips('bad-id', 'token'),
        throwsA(isA<TripServiceException>()),
      );
    });

    test('saveTrip adds trip to savedTrips list', () {
      final service = TripService(httpClient: MockClient((r) async => http.Response('', 200)));
      final trip = GeneratedTrip.fromJson(_sampleTripResponse());

      service.saveTrip(trip);

      expect(service.savedTrips.length, 1);
      expect(service.savedTrips[0].tripId, 'trip-123');
    });

    test('deleteTrip removes trip by ID', () {
      final service = TripService(httpClient: MockClient((r) async => http.Response('', 200)));
      final trip = GeneratedTrip.fromJson(_sampleTripResponse());

      service.saveTrip(trip);
      expect(service.savedTrips.length, 1);

      service.deleteTrip('trip-123');
      expect(service.savedTrips, isEmpty);
    });

    test('reset clears all state', () async {
      final client = MockClient((request) async {
        return http.Response(jsonEncode(_sampleTripResponse()), 201);
      });

      final service = TripService(httpClient: client);
      await service.generateTrip(
        profileId: 'profile-abc',
        centerLat: 48.8566,
        centerLng: 2.3522,
        startDate: '2026-05-04',
        endDate: '2026-05-06',
        accessToken: 'token',
      );
      service.saveTrip(service.lastGenerated!);
      expect(service.savedTrips, isNotEmpty);

      service.reset();

      expect(service.savedTrips, isEmpty);
      expect(service.lastGenerated, isNull);
      expect(service.isGenerating, false);
      expect(service.error, isNull);
    });

    test('confirmTripAudio sends POST to audio generate-trip endpoint',
        () async {
      final client = MockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, contains('/audio/generate-trip/trip-123'));
        expect(request.headers['Authorization'], 'Bearer test-token');
        return http.Response(
          jsonEncode({
            'trip_id': 'trip-123',
            'generated': 5,
            'skipped': 2,
            'failed': 0,
            'results': [],
          }),
          200,
        );
      });

      final service = TripService(httpClient: client);
      final result = await service.confirmTripAudio('trip-123', 'test-token');

      expect(result['trip_id'], 'trip-123');
      expect(result['generated'], 5);
      expect(result['skipped'], 2);
      expect(result['failed'], 0);
    });

    test('confirmTripAudio throws on 404', () async {
      final client = MockClient((request) async {
        return http.Response(
          jsonEncode({'detail': 'Trip not found'}),
          404,
        );
      });

      final service = TripService(httpClient: client);

      expect(
        () => service.confirmTripAudio('bad-id', 'token'),
        throwsA(isA<TripServiceException>()),
      );
    });

    test('confirmTripAudio throws on 500', () async {
      final client = MockClient((request) async {
        return http.Response('Internal Server Error', 500);
      });

      final service = TripService(httpClient: client);

      expect(
        () => service.confirmTripAudio('trip-123', 'token'),
        throwsA(isA<TripServiceException>()),
      );
    });

    test('confirmTripStopAudio POSTs to the per-STOP generate endpoint',
        () async {
      final client = MockClient((request) async {
        expect(request.method, 'POST');
        // Per-stop endpoint, NOT the per-beat /audio/generate-trip/{id}.
        expect(request.url.path, contains('/audio/generate-trip-stops/trip-123'));
        expect(request.headers['Authorization'], 'Bearer test-token');
        return http.Response(
          jsonEncode({
            'trip_id': 'trip-123',
            'generated': 4,
            'skipped': 1,
            'failed': 0,
            'results': [],
          }),
          200,
        );
      });

      final service = TripService(httpClient: client);
      final result =
          await service.confirmTripStopAudio('trip-123', 'test-token');

      expect(result['trip_id'], 'trip-123');
      expect(result['generated'], 4);
      expect(result['skipped'], 1);
      expect(result['failed'], 0);
    });

    test('confirmTripStopAudio throws on 404', () async {
      final client = MockClient((request) async {
        return http.Response(jsonEncode({'detail': 'Trip not found'}), 404);
      });

      final service = TripService(httpClient: client);

      expect(
        () => service.confirmTripStopAudio('bad-id', 'token'),
        throwsA(isA<TripServiceException>()),
      );
    });

    test('confirmTripStopAudio throws on 500', () async {
      final client = MockClient((request) async {
        return http.Response('Internal Server Error', 500);
      });

      final service = TripService(httpClient: client);

      expect(
        () => service.confirmTripStopAudio('trip-123', 'token'),
        throwsA(isA<TripServiceException>()),
      );
    });

    test('composeTrip POSTs route_id to the compose endpoint and parses stops',
        () async {
      Map<String, dynamic>? capturedBody;

      final client = MockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, contains('/trips/trip-123/compose'));
        expect(request.headers['Content-Type'], 'application/json');
        expect(request.headers['Authorization'], 'Bearer test-token');
        capturedBody = jsonDecode(request.body) as Map<String, dynamic>;
        return http.Response(
          jsonEncode({
            'trip_id': 'trip-123',
            'route_id': 'trip-123-opt2',
            'attempts': 1,
            'stops': [
              {
                'sort_order': 1,
                // FRESH stop_id — stops are re-persisted by /compose.
                'stop_id': 'item-new-1',
                'poi_id': 'poi-1',
                'poi_name': 'Eiffel Tower',
                'lat': 48.8584,
                'lng': 2.2945,
                'beat_id': 'beat-1',
                'beat_ids': ['beat-1'],
                'lens_name': 'dark_history',
                'lens_display': 'Dark History',
                'duration_min': 5,
                'importance_tier': 5,
                'start_time': '09:00',
                'narration': 'Composed narration.',
                'audio_url': null,
                'audio_duration_sec': null,
                'dwell_seconds': 300,
                'transit_polyline': null,
              },
            ],
          }),
          200,
        );
      });

      final service = TripService(httpClient: client);
      final stops = await service.composeTrip(
        'trip-123',
        'trip-123-opt2',
        'test-token',
      );

      expect(capturedBody, {'route_id': 'trip-123-opt2'});
      expect(stops.length, 1);
      expect(stops[0].stopId, 'item-new-1');
      expect(stops[0].poiName, 'Eiffel Tower');
      // Audio is generated AFTER compose by the per-stop flow.
      expect(stops[0].audioUrl, isNull);
    });

    test(
        'composeTrip throws ComposeVerificationException on 422 '
        'compose_verification_failed', () async {
      final client = MockClient((request) async {
        return http.Response(
          jsonEncode({
            'detail': {
              'reason': 'compose_verification_failed',
              'attempts': 2,
            },
          }),
          422,
        );
      });

      final service = TripService(httpClient: client);

      expect(
        () => service.composeTrip('trip-123', 'trip-123-opt1', 'token'),
        throwsA(
          isA<ComposeVerificationException>()
              .having((e) => e.reason, 'reason', 'compose_verification_failed')
              .having((e) => e.attempts, 'attempts', 2),
        ),
      );
    });

    test('composeTrip throws plain TripServiceException on 404', () async {
      final client = MockClient((request) async {
        return http.Response(
          jsonEncode({'detail': 'Trip not found'}),
          404,
        );
      });

      final service = TripService(httpClient: client);

      await expectLater(
        () => service.composeTrip('bad-id', 'bad-id-opt1', 'token'),
        throwsA(
          isA<TripServiceException>().having(
            (e) => e is ComposeVerificationException,
            'is not a verification refusal',
            isFalse,
          ),
        ),
      );
    });

    test('composeTrip throws plain TripServiceException on 409 '
        'already_composed', () async {
      final client = MockClient((request) async {
        return http.Response(
          jsonEncode({
            'detail': {'reason': 'already_composed', 'route_id': 'r1'},
          }),
          409,
        );
      });

      final service = TripService(httpClient: client);

      await expectLater(
        () => service.composeTrip('trip-123', 'trip-123-opt1', 'token'),
        throwsA(
          isA<TripServiceException>().having(
            (e) => e is ComposeVerificationException,
            'is not a verification refusal',
            isFalse,
          ),
        ),
      );
    });
  });
}
