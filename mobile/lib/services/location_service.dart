import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:geolocator/geolocator.dart';

class LocationService extends ChangeNotifier {
  Position? _lastPosition;
  String? _error;
  bool _isFetching = false;
  StreamSubscription<Position>? _positionSubscription;
  bool _isTracking = false;
  bool _lowAccuracy = false;

  Position? get lastPosition => _lastPosition;
  String? get error => _error;
  bool get isFetching => _isFetching;
  bool get isTracking => _isTracking;
  bool get lowAccuracy => _lowAccuracy;

  Future<Position?> getCurrentPosition() async {
    _isFetching = true;
    _error = null;
    notifyListeners();

    try {
      final serviceEnabled = await Geolocator.isLocationServiceEnabled();
      if (!serviceEnabled) {
        _error = 'Location services are disabled';
        _isFetching = false;
        notifyListeners();
        return null;
      }

      var permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
        if (permission == LocationPermission.denied) {
          _error = 'Location permission denied';
          _isFetching = false;
          notifyListeners();
          return null;
        }
      }

      if (permission == LocationPermission.deniedForever) {
        _error = 'Location permission permanently denied. '
            'Please enable in Settings.';
        _isFetching = false;
        notifyListeners();
        return null;
      }

      final position = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.high,
          timeLimit: Duration(seconds: 10),
        ),
      );

      _lastPosition = position;
      _isFetching = false;
      notifyListeners();
      return position;
    } catch (e) {
      _error = 'Failed to get location: $e';
      _isFetching = false;
      notifyListeners();
      return null;
    }
  }

  /// Start continuous position tracking.
  /// Uses adaptive polling: 5m distance filter, high accuracy, walking activity.
  Future<bool> startTracking() async {
    if (_isTracking) return true;

    final serviceEnabled = await Geolocator.isLocationServiceEnabled();
    if (!serviceEnabled) {
      _error = 'Location services are disabled';
      notifyListeners();
      return false;
    }

    var permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
      if (permission == LocationPermission.denied) {
        _error = 'Location permission denied';
        notifyListeners();
        return false;
      }
    }

    if (permission == LocationPermission.deniedForever) {
      _error =
          'Location permission permanently denied. Please enable in Settings.';
      notifyListeners();
      return false;
    }

    const locationSettings = LocationSettings(
      accuracy: LocationAccuracy.high,
      distanceFilter: 5, // Only emit when user moves 5+ meters
    );

    _positionSubscription = Geolocator.getPositionStream(
      locationSettings: locationSettings,
    ).listen(
      onPositionUpdate,
      onError: onPositionError,
    );

    _isTracking = true;
    _error = null;
    notifyListeners();
    return true;
  }

  /// Stop continuous position tracking.
  void stopTracking() {
    _positionSubscription?.cancel();
    _positionSubscription = null;
    _isTracking = false;
    _lowAccuracy = false;
    notifyListeners();
  }

  @visibleForTesting
  void onPositionUpdate(Position position) {
    _lastPosition = position;
    _lowAccuracy = position.accuracy > 25.0;
    _error = null;
    notifyListeners();
  }

  @visibleForTesting
  void onPositionError(dynamic error) {
    _error = 'Location tracking error: $error';
    notifyListeners();
  }

  @override
  void dispose() {
    stopTracking();
    super.dispose();
  }
}
