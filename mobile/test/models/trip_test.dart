import 'package:flutter_test/flutter_test.dart';
import 'package:ondoway/models/trip.dart';

void main() {
  group('ItineraryStop', () {
    test('fromJson parses all fields correctly', () {
      final json = {
        'sort_order': 1,
        'stop_id': 'item-789',
        'poi_id': 'poi-123',
        'poi_name': 'Eiffel Tower',
        'lat': 48.8584,
        'lng': 2.2945,
        'beat_id': 'beat-456',
        'lens_name': 'dark_history',
        'lens_display': 'Dark History',
        'duration_min': 5,
        'importance_tier': 5,
        'start_time': '09:00',
        'transit_polyline': 'encodedpolyline6',
      };

      final stop = ItineraryStop.fromJson(json);

      expect(stop.sortOrder, 1);
      expect(stop.stopId, 'item-789');
      expect(stop.poiId, 'poi-123');
      expect(stop.poiName, 'Eiffel Tower');
      expect(stop.lat, 48.8584);
      expect(stop.lng, 2.2945);
      expect(stop.beatId, 'beat-456');
      expect(stop.lensName, 'dark_history');
      expect(stop.lensDisplay, 'Dark History');
      expect(stop.durationMin, 5);
      expect(stop.importanceTier, 5);
      expect(stop.startTime, '09:00');
      expect(stop.transitPolyline, 'encodedpolyline6');
    });

    test('fromJson defaults transitPolyline to null when absent', () {
      final json = {
        'sort_order': 1,
        'poi_id': 'poi-123',
        'poi_name': 'Eiffel Tower',
        'lat': 48.8584,
        'lng': 2.2945,
        'beat_id': 'beat-456',
        'lens_name': 'dark_history',
        'lens_display': 'Dark History',
        'duration_min': 5,
        'importance_tier': 5,
        'start_time': '09:00',
      };
      expect(ItineraryStop.fromJson(json).transitPolyline, isNull);
    });

    test('fromJson defaults stopId to null when absent', () {
      final json = {
        'sort_order': 1,
        'poi_id': 'poi-123',
        'poi_name': 'Eiffel Tower',
        'lat': 48.8584,
        'lng': 2.2945,
        'beat_id': 'beat-456',
        'lens_name': 'dark_history',
        'lens_display': 'Dark History',
        'duration_min': 5,
        'importance_tier': 5,
        'start_time': '09:00',
      };
      expect(ItineraryStop.fromJson(json).stopId, isNull);
    });

    test('fromJson handles integer lat/lng values', () {
      final json = {
        'sort_order': 2,
        'poi_id': 'poi-789',
        'poi_name': 'Notre-Dame',
        'lat': 48,
        'lng': 2,
        'beat_id': 'beat-012',
        'lens_name': 'architecture',
        'lens_display': 'Architecture',
        'duration_min': 3,
        'importance_tier': 4,
        'start_time': '09:05',
      };

      final stop = ItineraryStop.fromJson(json);

      expect(stop.lat, 48.0);
      expect(stop.lng, 2.0);
    });

    test('toJson round-trips correctly', () {
      final original = ItineraryStop(
        sortOrder: 1,
        poiId: 'poi-1',
        poiName: 'Test POI',
        lat: 48.8,
        lng: 2.3,
        beatId: 'beat-1',
        lensName: 'scandal',
        lensDisplay: 'Scandal',
        durationMin: 4,
        importanceTier: 3,
        startTime: '10:00',
      );

      final json = original.toJson();
      final rebuilt = ItineraryStop.fromJson(json);

      expect(rebuilt.sortOrder, original.sortOrder);
      expect(rebuilt.poiId, original.poiId);
      expect(rebuilt.poiName, original.poiName);
      expect(rebuilt.lat, original.lat);
      expect(rebuilt.lng, original.lng);
    });
  });

  group('GeneratedTrip', () {
    test('fromJson parses full response with stops', () {
      final json = {
        'trip_id': 'trip-abc',
        'trip_name': 'Trip (2026-05-04)',
        'profile_id': 'profile-xyz',
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

      final trip = GeneratedTrip.fromJson(json);

      expect(trip.tripId, 'trip-abc');
      expect(trip.tripName, 'Trip (2026-05-04)');
      expect(trip.profileId, 'profile-xyz');
      expect(trip.totalStops, 2);
      expect(trip.totalDurationMin, 8);
      expect(trip.anchorCount, 1);
      expect(trip.flavourCount, 1);
      expect(trip.stops.length, 2);
      expect(trip.stops[0].poiName, 'Eiffel Tower');
      expect(trip.stops[1].poiName, 'Louvre');
    });

    test('fromJson handles empty stops list', () {
      final json = {
        'trip_id': 'trip-empty',
        'trip_name': 'Empty Trip',
        'profile_id': 'profile-1',
        'total_stops': 0,
        'total_duration_min': 0,
        'anchor_count': 0,
        'flavour_count': 0,
        'stops': [],
      };

      final trip = GeneratedTrip.fromJson(json);

      expect(trip.tripId, 'trip-empty');
      expect(trip.totalStops, 0);
      expect(trip.stops, isEmpty);
    });

    test('toJson round-trips correctly', () {
      final original = GeneratedTrip(
        tripId: 'trip-rt',
        tripName: 'Round Trip',
        profileId: 'prof-1',
        totalStops: 1,
        totalDurationMin: 5,
        anchorCount: 1,
        flavourCount: 0,
        stops: const [
          ItineraryStop(
            sortOrder: 1,
            poiId: 'poi-rt',
            poiName: 'Test',
            lat: 48.0,
            lng: 2.0,
            beatId: 'beat-rt',
            lensName: 'test',
            lensDisplay: 'Test',
            durationMin: 5,
            importanceTier: 5,
            startTime: '09:00',
          ),
        ],
      );

      final json = original.toJson();
      final rebuilt = GeneratedTrip.fromJson(json);

      expect(rebuilt.tripId, original.tripId);
      expect(rebuilt.tripName, original.tripName);
      expect(rebuilt.stops.length, 1);
      expect(rebuilt.stops[0].poiId, 'poi-rt');
    });
  });
}
