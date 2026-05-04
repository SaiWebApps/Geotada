import 'package:flutter/foundation.dart';
import 'package:geolocator/geolocator.dart';

class LocationService extends ChangeNotifier {
  Position? _lastPosition;
  String? _error;
  bool _isFetching = false;

  Position? get lastPosition => _lastPosition;
  String? get error => _error;
  bool get isFetching => _isFetching;

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
}
