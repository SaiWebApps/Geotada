import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:ondoway/models/trip.dart';

class TripService extends ChangeNotifier {
  static const baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://localhost:8000/api/v1',
  );

  final http.Client _httpClient;
  List<GeneratedTrip> _savedTrips = [];
  GeneratedTrip? _lastGenerated;
  bool _isGenerating = false;
  String? _error;

  TripService({http.Client? httpClient})
      : _httpClient = httpClient ?? http.Client();

  List<GeneratedTrip> get savedTrips => List.unmodifiable(_savedTrips);
  GeneratedTrip? get lastGenerated => _lastGenerated;
  bool get isGenerating => _isGenerating;
  String? get error => _error;

  /// POST /trips/generate — generate an optimized trip itinerary.
  Future<GeneratedTrip> generateTrip({
    required String profileId,
    required double centerLat,
    required double centerLng,
    required String startDate,
    required String endDate,
    required String accessToken,
    int radiusM = 3000,
    int maxStops = 10,
    int? durationMin,
    String startTime = '09:00',
    bool kidFriendlyOnly = false,
    String? tripName,
  }) async {
    _isGenerating = true;
    _error = null;
    notifyListeners();

    try {
      final body = <String, dynamic>{
        'profile_id': profileId,
        'center_lat': centerLat,
        'center_lng': centerLng,
        'radius_m': radiusM,
        'max_stops': maxStops,
        'start_date': startDate,
        'end_date': endDate,
        'start_time': startTime,
        'kid_friendly_only': kidFriendlyOnly,
      };
      if (durationMin != null) body['duration_min'] = durationMin;
      if (tripName != null) body['trip_name'] = tripName;

      final response = await _httpClient.post(
        Uri.parse('$baseUrl/trips/generate'),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $accessToken',
        },
        body: jsonEncode(body),
      );

      if (response.statusCode == 201) {
        final data = jsonDecode(response.body) as Map<String, dynamic>;
        final trip = GeneratedTrip.fromJson(data);
        _lastGenerated = trip;
        _isGenerating = false;
        notifyListeners();
        return trip;
      } else if (response.statusCode == 404) {
        throw TripServiceException('Profile not found');
      } else if (response.statusCode == 422) {
        final detail = _extractDetail(response.body);
        throw TripServiceException(detail);
      } else {
        throw TripServiceException(
          'Trip generation failed (${response.statusCode}): ${response.body}',
        );
      }
    } catch (e) {
      _isGenerating = false;
      if (e is TripServiceException) {
        _error = e.message;
        notifyListeners();
        rethrow;
      }
      _error = e.toString();
      notifyListeners();
      rethrow;
    }
  }

  /// GET /trips?profile_id=... — fetch all saved trips for a profile.
  Future<List<GeneratedTrip>> fetchSavedTrips(
    String profileId,
    String accessToken,
  ) async {
    final response = await _httpClient.get(
      Uri.parse('$baseUrl/trips?profile_id=$profileId'),
      headers: {
        'Authorization': 'Bearer $accessToken',
      },
    );

    if (response.statusCode == 200) {
      final data = jsonDecode(response.body) as List<dynamic>;
      _savedTrips = data
          .map((t) => GeneratedTrip.fromJson(t as Map<String, dynamic>))
          .toList();
      notifyListeners();
      return _savedTrips;
    } else if (response.statusCode == 404) {
      throw TripServiceException('Profile not found');
    } else {
      throw TripServiceException(
        'Failed to fetch trips (${response.statusCode})',
      );
    }
  }

  /// Add a generated trip to the saved list (local state).
  void saveTrip(GeneratedTrip trip) {
    _savedTrips = [..._savedTrips, trip];
    notifyListeners();
  }

  /// Remove a trip from the saved list by ID.
  void deleteTrip(String tripId) {
    _savedTrips = _savedTrips.where((t) => t.tripId != tripId).toList();
    notifyListeners();
  }

  /// POST /audio/generate-trip/{tripId} — trigger backend audio generation.
  ///
  /// Returns the generation response with counts of generated/skipped/failed.
  Future<Map<String, dynamic>> confirmTripAudio(
    String tripId,
    String accessToken,
  ) async {
    final response = await _httpClient.post(
      Uri.parse('$baseUrl/audio/generate-trip/$tripId'),
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer $accessToken',
      },
    );

    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    } else if (response.statusCode == 404) {
      throw TripServiceException('Trip not found');
    } else {
      throw TripServiceException(
        'Audio generation failed (${response.statusCode}): ${response.body}',
      );
    }
  }

  /// POST /audio/generate-trip-stops/{tripId} — trigger PER-STOP narration audio
  /// (Phase 1, Step 1.4d). Voices each stop's stitched narration (cold-open →
  /// beats → transit → closing), keyed by ItineraryItem id — the per-stop
  /// replacement for [confirmTripAudio]'s per-primary-beat generation.
  ///
  /// Returns the generation response with counts of generated/skipped/failed.
  Future<Map<String, dynamic>> confirmTripStopAudio(
    String tripId,
    String accessToken,
  ) async {
    final response = await _httpClient.post(
      Uri.parse('$baseUrl/audio/generate-trip-stops/$tripId'),
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer $accessToken',
      },
    );

    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    } else if (response.statusCode == 404) {
      throw TripServiceException('Trip not found');
    } else {
      throw TripServiceException(
        'Stop audio generation failed (${response.statusCode}): ${response.body}',
      );
    }
  }

  /// POST /trips/{tripId}/compose — compose the picked flavour (Phase 4
  /// Step 4.10). Body: {"route_id": routeId}. Returns the re-persisted stops
  /// with FRESH stop_ids (narration is the composed text, audio_url is null —
  /// audio is generated afterwards by the existing per-stop flow).
  ///
  /// Throws [ComposeVerificationException] when the backend REFUSES the
  /// flavour (422 compose_verification_failed) so the caller can offer the
  /// remaining flavours.
  Future<List<ItineraryStop>> composeTrip(
    String tripId,
    String routeId,
    String accessToken,
  ) async {
    final response = await _httpClient.post(
      Uri.parse('$baseUrl/trips/$tripId/compose'),
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer $accessToken',
      },
      body: jsonEncode({'route_id': routeId}),
    );

    if (response.statusCode == 200) {
      final data = jsonDecode(response.body) as Map<String, dynamic>;
      return (data['stops'] as List<dynamic>)
          .map((s) => ItineraryStop.fromJson(s as Map<String, dynamic>))
          .toList();
    } else if (response.statusCode == 404) {
      throw TripServiceException('Trip or route not found');
    } else if (response.statusCode == 409) {
      throw TripServiceException('Trip already composed');
    } else if (response.statusCode == 422) {
      final detail = _detailMap(response.body);
      if (detail?['reason'] == 'compose_verification_failed') {
        throw ComposeVerificationException(
          attempts: (detail?['attempts'] as num?)?.toInt(),
        );
      }
      throw TripServiceException('Compose failed (422): ${response.body}');
    } else {
      throw TripServiceException(
        'Compose failed (${response.statusCode}): ${response.body}',
      );
    }
  }

  /// Clear all local state.
  void reset() {
    _savedTrips = [];
    _lastGenerated = null;
    _isGenerating = false;
    _error = null;
    notifyListeners();
  }

  String _extractDetail(String body) {
    try {
      final data = jsonDecode(body) as Map<String, dynamic>;
      return data['detail'] as String? ?? body;
    } catch (_) {
      return body;
    }
  }

  /// Structured error detail ({"detail": {...}}) or null when detail is a
  /// plain string / body is not JSON.
  Map<String, dynamic>? _detailMap(String body) {
    try {
      final data = jsonDecode(body) as Map<String, dynamic>;
      final detail = data['detail'];
      return detail is Map<String, dynamic> ? detail : null;
    } catch (_) {
      return null;
    }
  }
}

class TripServiceException implements Exception {
  final String message;
  TripServiceException(this.message);

  @override
  String toString() => message;
}

/// The backend REFUSED a flavour: /compose returned 422 with
/// detail.reason == "compose_verification_failed" (VERIFY failed after the
/// recompose attempt). The user should pick another flavour.
class ComposeVerificationException extends TripServiceException {
  final String reason;
  final int? attempts;

  ComposeVerificationException({this.attempts})
      : reason = 'compose_verification_failed',
        super('This flavour failed verification');
}
