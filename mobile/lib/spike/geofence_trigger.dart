import 'dart:math' as math;

/// Great-circle distance in meters between two lat/lng points (Haversine).
double haversineMeters(double lat1, double lng1, double lat2, double lng2) {
  const earthRadius = 6371000.0; // meters
  final dLat = _toRadians(lat2 - lat1);
  final dLng = _toRadians(lng2 - lng1);
  final a = math.sin(dLat / 2) * math.sin(dLat / 2) +
      math.cos(_toRadians(lat1)) *
          math.cos(_toRadians(lat2)) *
          math.sin(dLng / 2) *
          math.sin(dLng / 2);
  final c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a));
  return earthRadius * c;
}

double _toRadians(double degrees) => degrees * math.pi / 180.0;

/// Fires exactly once each time the device enters [radiusMeters] of the target,
/// and re-arms only after leaving [reArmMeters]. The gap between the two is
/// hysteresis: it absorbs GPS jitter around the boundary so one stop does not
/// double-fire.
class GeofenceTrigger {
  GeofenceTrigger({
    required this.targetLat,
    required this.targetLng,
    this.radiusMeters = 10.0,
    this.reArmMeters = 20.0,
  }) : assert(reArmMeters >= radiusMeters);

  final double targetLat;
  final double targetLng;
  final double radiusMeters;
  final double reArmMeters;

  bool _armed = true;

  double distanceTo(double lat, double lng) =>
      haversineMeters(targetLat, targetLng, lat, lng);

  /// Feed each new position. Returns true only on the update that crosses into
  /// the radius while armed.
  bool update(double lat, double lng) {
    final d = distanceTo(lat, lng);
    if (_armed && d <= radiusMeters) {
      _armed = false;
      return true;
    }
    if (!_armed && d >= reArmMeters) {
      _armed = true;
    }
    return false;
  }
}
