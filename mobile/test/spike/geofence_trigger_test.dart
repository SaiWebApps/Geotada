import 'package:flutter_test/flutter_test.dart';
import 'package:ondoway/spike/geofence_trigger.dart';

void main() {
  group('haversineMeters', () {
    test('is zero for identical points', () {
      expect(haversineMeters(48.8566, 2.3522, 48.8566, 2.3522), closeTo(0, 0.001));
    });

    test('~111.19m per 0.001 degree of latitude', () {
      final d = haversineMeters(48.8566, 2.3522, 48.8576, 2.3522);
      expect(d, closeTo(111.19, 1.0));
    });
  });

  group('GeofenceTrigger', () {
    const lat = 48.8530;
    const lng = 2.3499;

    test('fires once on entering the radius', () {
      final t = GeofenceTrigger(targetLat: lat, targetLng: lng);
      expect(t.update(lat + 0.001, lng), isFalse); // ~111m out
      expect(t.update(lat, lng), isTrue); // at target
    });

    test('does not re-fire while still inside', () {
      final t = GeofenceTrigger(targetLat: lat, targetLng: lng);
      expect(t.update(lat, lng), isTrue);
      expect(t.update(lat, lng), isFalse);
      expect(t.update(lat + 0.00005, lng), isFalse); // ~5.5m jitter, still inside
    });

    test('re-arms only past reArmMeters, then fires again', () {
      final t = GeofenceTrigger(
          targetLat: lat, targetLng: lng, radiusMeters: 10, reArmMeters: 20);
      expect(t.update(lat, lng), isTrue); // fire
      expect(t.update(lat + 0.00015, lng), isFalse); // ~16.7m: between radius and reArm
      expect(t.update(lat, lng), isFalse); // back inside but NOT re-armed
      expect(t.update(lat + 0.0002, lng), isFalse); // ~22m: re-arms
      expect(t.update(lat, lng), isTrue); // fires again
    });
  });
}
