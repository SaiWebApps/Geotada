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

  group('RouteOptionStop', () {
    test('fromJson parses the picker subset', () {
      final stop = RouteOptionStop.fromJson({
        'poi_id': 'poi-1',
        'name': 'Eiffel Tower',
        'lat': 48.8584,
        'lng': 2.2945,
        'lens': 'dark_history',
        'visit_or_walk_past': 'visit',
        'minutes': 12,
        'band': 'vignette',
        'spotlight': 3.5,
      });

      expect(stop.name, 'Eiffel Tower');
      expect(stop.band, 'vignette');
      expect(stop.minutes, 12);
      expect(stop.spotlight, 3.5);
    });

    test('fromJson defaults band/minutes/spotlight (backend contract defaults)',
        () {
      final stop = RouteOptionStop.fromJson({'name': 'Louvre'});

      expect(stop.band, 'dwell');
      expect(stop.minutes, 0);
      expect(stop.spotlight, 0.0);
    });

    test('toJson round-trips', () {
      const original = RouteOptionStop(
        name: 'Notre-Dame',
        band: 'vignette',
        minutes: 4,
        spotlight: 1.25,
      );

      final rebuilt = RouteOptionStop.fromJson(original.toJson());

      expect(rebuilt.name, original.name);
      expect(rebuilt.band, original.band);
      expect(rebuilt.minutes, original.minutes);
      expect(rebuilt.spotlight, original.spotlight);
    });
  });

  group('RouteOption', () {
    Map<String, dynamic> sampleOptionJson() => {
          'route_id': 'trip-1-opt2',
          'stops': [
            {'name': 'Eiffel Tower', 'band': 'dwell', 'minutes': 10},
            {'name': 'Champ de Mars', 'band': 'vignette', 'minutes': 2},
          ],
          // Fields the picker ignores but the API sends (§2.8):
          'stop_audio': <String, dynamic>{},
          'route_polyline': 'abc123',
          'eta_seconds': 5400,
          'lens_summary': {'dark_history': 2},
          'flow_score': 0.9,
          'backtrack_ratio': 0.1,
          'degraded': false,
          'profiles': <String>[],
          'offline_package': null,
          'lens_coverage_note': 'Dark History runs thin after stop 3',
        };

    test('fromJson parses route_id, stops, eta, lens_coverage_note', () {
      final option = RouteOption.fromJson(sampleOptionJson());

      expect(option.routeId, 'trip-1-opt2');
      expect(option.stops.length, 2);
      expect(option.stops[0].name, 'Eiffel Tower');
      expect(option.stops[0].band, 'dwell');
      expect(option.stops[1].band, 'vignette');
      expect(option.etaSeconds, 5400);
      expect(option.lensCoverageNote, 'Dark History runs thin after stop 3');
    });

    test('fromJson defaults lens_coverage_note to null when absent', () {
      final json = sampleOptionJson()..remove('lens_coverage_note');
      expect(RouteOption.fromJson(json).lensCoverageNote, isNull);
    });

    test('toJson round-trips', () {
      final original = RouteOption.fromJson(sampleOptionJson());
      final rebuilt = RouteOption.fromJson(original.toJson());

      expect(rebuilt.routeId, original.routeId);
      expect(rebuilt.stops.length, original.stops.length);
      expect(rebuilt.stops[1].band, 'vignette');
      expect(rebuilt.etaSeconds, original.etaSeconds);
      expect(rebuilt.lensCoverageNote, original.lensCoverageNote);
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

    test('fromJson parses k RouteOptions from generate response', () {
      final json = {
        'trip_id': 'trip-opt',
        'trip_name': 'Options Trip',
        'profile_id': 'profile-1',
        'total_stops': 0,
        'total_duration_min': 0,
        'anchor_count': 0,
        'flavour_count': 0,
        'stops': <dynamic>[],
        'options': [
          {
            'route_id': 'trip-opt-opt1',
            'stops': [
              {'name': 'A', 'band': 'dwell', 'minutes': 5},
            ],
            'eta_seconds': 3600,
          },
          {
            'route_id': 'trip-opt-opt2',
            'stops': <dynamic>[],
            'eta_seconds': 4200,
            'lens_coverage_note': 'note',
          },
        ],
      };

      final trip = GeneratedTrip.fromJson(json);

      expect(trip.options.length, 2);
      expect(trip.options[0].routeId, 'trip-opt-opt1');
      expect(trip.options[0].stops.single.name, 'A');
      expect(trip.options[1].etaSeconds, 4200);
      expect(trip.options[1].lensCoverageNote, 'note');
    });

    test('fromJson defaults options to empty list when absent (GET /trips)',
        () {
      final json = {
        'trip_id': 'trip-saved',
        'trip_name': 'Saved Trip',
        'profile_id': 'profile-1',
        'total_stops': 0,
        'total_duration_min': 0,
        'anchor_count': 0,
        'flavour_count': 0,
        'stops': <dynamic>[],
      };

      expect(GeneratedTrip.fromJson(json).options, isEmpty);
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
