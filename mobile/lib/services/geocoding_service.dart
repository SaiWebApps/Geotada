import 'package:flutter/services.dart';

class GeocodingService {
  static const _channel = MethodChannel('com.ondoway/geocoding');

  Future<GeocodingResult?> search(String query) async {
    try {
      final result = await _channel.invokeMethod<Map>('search', query);
      if (result == null) return null;
      return GeocodingResult(
        lat: (result['lat'] as num).toDouble(),
        lng: (result['lng'] as num).toDouble(),
        name: result['name'] as String? ?? query,
      );
    } on PlatformException {
      return null;
    }
  }
}

class GeocodingResult {
  final double lat;
  final double lng;
  final String name;

  const GeocodingResult({
    required this.lat,
    required this.lng,
    required this.name,
  });
}
