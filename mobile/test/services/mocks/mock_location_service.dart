import 'package:ondoway/services/providers.dart';

/// Mock LocationService for unit testing.
/// Does not depend on geolocator plugin — simulates positions directly.
class MockLocationService extends LocationProvider {
  bool trackingWillSucceed = true;
  bool _isTracking = false;
  bool _lowAccuracy = false;
  MockPosition? _lastPosition;
  String? _error;
  bool? lastBackground;
  List<String>? callLog;

  @override
  MockPosition? get lastPosition => _lastPosition;
  String? get error => _error;
  @override
  bool get isTracking => _isTracking;
  @override
  bool get lowAccuracy => _lowAccuracy;

  @override
  Future<bool> startTracking({bool background = false}) async {
    lastBackground = background;
    callLog?.add('track');
    if (!trackingWillSucceed) {
      _error = 'Mock: tracking failed';
      notifyListeners();
      return false;
    }
    _isTracking = true;
    _error = null;
    notifyListeners();
    return true;
  }

  @override
  void stopTracking() {
    _isTracking = false;
    _lowAccuracy = false;
    notifyListeners();
  }

  /// Simulate receiving a position update.
  void simulatePosition(double latitude, double longitude,
      {double accuracy = 5.0}) {
    _lastPosition = MockPosition(
      latitude: latitude,
      longitude: longitude,
      accuracy: accuracy,
    );
    _lowAccuracy = accuracy > 25.0;
    notifyListeners();
  }
}

/// Minimal position class for testing (mirrors geolocator Position interface).
class MockPosition {
  final double latitude;
  final double longitude;
  final double accuracy;

  MockPosition({
    required this.latitude,
    required this.longitude,
    this.accuracy = 5.0,
  });
}
