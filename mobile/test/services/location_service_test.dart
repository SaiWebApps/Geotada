import 'package:flutter_test/flutter_test.dart';
import 'package:geolocator/geolocator.dart';
import 'package:ondoway/services/location_service.dart';

Position _makePosition({double accuracy = 10.0}) => Position(
      latitude: 48.8566,
      longitude: 2.3522,
      timestamp: DateTime.now(),
      accuracy: accuracy,
      altitude: 0.0,
      altitudeAccuracy: 0.0,
      heading: 0.0,
      headingAccuracy: 0.0,
      speed: 0.0,
      speedAccuracy: 0.0,
    );

void main() {
  group('LocationService initial state', () {
    late LocationService service;

    setUp(() {
      service = LocationService();
    });

    test('isTracking is false', () {
      expect(service.isTracking, false);
    });

    test('lowAccuracy is false', () {
      expect(service.lowAccuracy, false);
    });

    test('lastPosition is null', () {
      expect(service.lastPosition, isNull);
    });

    test('isFetching is false', () {
      expect(service.isFetching, false);
    });

    test('error is null', () {
      expect(service.error, isNull);
    });
  });

  group('LocationService.stopTracking', () {
    test('sets isTracking to false', () {
      final service = LocationService();
      service.stopTracking();
      expect(service.isTracking, false);
    });

    test('resets lowAccuracy to false', () {
      final service = LocationService();
      service.stopTracking();
      expect(service.lowAccuracy, false);
    });

    test('notifies listeners', () {
      final service = LocationService();
      var notified = false;
      service.addListener(() => notified = true);
      service.stopTracking();
      expect(notified, true);
    });

    test('is idempotent (multiple calls do not throw)', () {
      final service = LocationService();
      service.stopTracking();
      service.stopTracking();
      expect(service.isTracking, false);
    });
  });

  group('LocationService.onPositionUpdate', () {
    test('sets lowAccuracy to true when accuracy > 25m', () {
      final service = LocationService();
      service.onPositionUpdate(_makePosition(accuracy: 30.0));
      expect(service.lowAccuracy, true);
    });

    test('sets lowAccuracy to false when accuracy < 25m', () {
      final service = LocationService();
      service.onPositionUpdate(_makePosition(accuracy: 10.0));
      expect(service.lowAccuracy, false);
    });

    test('sets lowAccuracy to false when accuracy == 25m (boundary)', () {
      final service = LocationService();
      service.onPositionUpdate(_makePosition(accuracy: 25.0));
      expect(service.lowAccuracy, false);
    });

    test('updates lastPosition', () {
      final service = LocationService();
      final pos = _makePosition(accuracy: 5.0);
      service.onPositionUpdate(pos);
      expect(service.lastPosition, pos);
    });

    test('clears error', () {
      final service = LocationService();
      service.onPositionError('some error');
      expect(service.error, isNotNull);

      service.onPositionUpdate(_makePosition());
      expect(service.error, isNull);
    });

    test('notifies listeners', () {
      final service = LocationService();
      var notified = false;
      service.addListener(() => notified = true);
      service.onPositionUpdate(_makePosition());
      expect(notified, true);
    });
  });

  group('LocationService.onPositionError', () {
    test('sets error message', () {
      final service = LocationService();
      service.onPositionError('GPS signal lost');
      expect(service.error, 'Location tracking error: GPS signal lost');
    });

    test('notifies listeners', () {
      final service = LocationService();
      var notified = false;
      service.addListener(() => notified = true);
      service.onPositionError('timeout');
      expect(notified, true);
    });
  });

  group('LocationService.dispose', () {
    test('does not throw when not tracking', () {
      final service = LocationService();
      expect(() => service.dispose(), returnsNormally);
    });
  });
}
