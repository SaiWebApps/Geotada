import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:ondoway/models/trip.dart';
import 'package:ondoway/services/providers.dart';

export 'package:ondoway/services/providers.dart'
    show LocationProvider, AudioProvider;

enum TourState { idle, active, approaching, completed }

class TourPlaybackService extends ChangeNotifier {
  final LocationProvider _locationService;
  final AudioProvider _audioService;

  List<ItineraryStop> _stops = [];
  int _currentStopIndex = -1;
  int? _pendingStopIndex;
  TourState _state = TourState.idle;
  double? _distanceToNext;

  VoidCallback? _locationListener;
  VoidCallback? _audioListener;

  // Getters
  TourState get state => _state;
  int get currentStopIndex => _currentStopIndex;
  int? get pendingStopIndex => _pendingStopIndex;
  double? get distanceToNext => _distanceToNext;
  ItineraryStop? get currentStop =>
      _currentStopIndex >= 0 && _currentStopIndex < _stops.length
          ? _stops[_currentStopIndex]
          : null;
  ItineraryStop? get nextStop => _currentStopIndex + 1 < _stops.length
      ? _stops[_currentStopIndex + 1]
      : null;
  bool get isActive =>
      _state != TourState.idle && _state != TourState.completed;
  bool get hasPendingStop => _pendingStopIndex != null;

  TourPlaybackService({
    required LocationProvider locationService,
    required AudioProvider audioService,
  })  : _locationService = locationService,
        _audioService = audioService;

  /// Start a tour with the given stops. Begins GPS tracking and geofence
  /// monitoring.
  Future<bool> startTour(List<ItineraryStop> stops) async {
    if (stops.isEmpty) return false;

    _stops = List.unmodifiable(stops);
    _currentStopIndex = 0;
    _pendingStopIndex = null;
    _state = TourState.active;

    // Activate the audio session while we are FOREGROUND. iOS grants session
    // activation only to a frontmost app; from a background geofence callback it
    // returns CannotInterruptOthers (560557684). Once active it survives lock, so
    // the fire path only needs to play. (No-op off iOS.)
    await _audioService.prepareSession();

    // Start GPS tracking — background:true so position updates keep arriving when
    // the screen locks and the phone is pocketed (Slice 0.3).
    final started = await _locationService.startTracking(background: true);
    if (!started) {
      _state = TourState.idle;
      notifyListeners();
      return false;
    }

    // Listen to position updates
    _locationListener = () => _onPositionUpdate();
    _locationService.addListener(_locationListener!);

    // Listen to audio completion
    _audioListener = () => _onAudioStateChanged();
    _audioService.addListener(_audioListener!);

    notifyListeners();
    return true;
  }

  /// Stop the tour, cancel tracking.
  void stopTour() {
    if (_locationListener != null) {
      _locationService.removeListener(_locationListener!);
      _locationListener = null;
    }
    if (_audioListener != null) {
      _audioService.removeListener(_audioListener!);
      _audioListener = null;
    }
    _locationService.stopTracking();
    _audioService.stop();
    _stops = [];
    _currentStopIndex = -1;
    _pendingStopIndex = null;
    _state = TourState.idle;
    _distanceToNext = null;
    notifyListeners();
  }

  /// Skip to a specific stop index.
  void skipToStop(int index) {
    if (index < 0 || index >= _stops.length) return;
    _currentStopIndex = index;
    _pendingStopIndex = null;
    _playCurrentStop();
  }

  /// Accept the pending stop (user tapped the "now approaching" nudge).
  void acceptPendingStop() {
    if (_pendingStopIndex != null) {
      _currentStopIndex = _pendingStopIndex!;
      _pendingStopIndex = null;
      _playCurrentStop();
    }
  }

  /// Dismiss the pending nudge (user wants to keep listening).
  void dismissPending() {
    _pendingStopIndex = null;
    _state = TourState.active;
    notifyListeners();
  }

  void _onPositionUpdate() {
    final position = _locationService.lastPosition;
    if (position == null || _stops.isEmpty) return;

    final targetIndex = _currentStopIndex;
    if (targetIndex < 0 || targetIndex >= _stops.length) return;

    final target = _stops[targetIndex];
    final distance = haversineDistance(
      (position.latitude as num).toDouble(),
      (position.longitude as num).toDouble(),
      target.lat,
      target.lng,
    );
    _distanceToNext = distance;

    // Check geofence: 10m trigger radius (NORTHSTAR spec)
    if (distance <= 10.0 && !_audioService.isPlaying) {
      _playCurrentStop();
    }

    // Check if user is approaching the NEXT stop while current is playing
    if (_audioService.isPlaying && _currentStopIndex + 1 < _stops.length) {
      final nextTarget = _stops[_currentStopIndex + 1];
      final distToNext = haversineDistance(
        (position.latitude as num).toDouble(),
        (position.longitude as num).toDouble(),
        nextTarget.lat,
        nextTarget.lng,
      );
      if (distToNext <= 10.0 && _pendingStopIndex == null) {
        _pendingStopIndex = _currentStopIndex + 1;
        _state = TourState.approaching;
        notifyListeners();
      }
    }

    notifyListeners();
  }

  void _onAudioStateChanged() {
    // KE6: a completed "keep exploring here" deep-dive clip NEVER advances the
    // tour — it is served off the tour's time budget. Only scheduled per-stop
    // tour audio drives auto-advance, so bail before either advance path.
    if (_audioService.isDeeperDive) return;

    // When audio finishes playing, auto-advance if there's a pending stop
    if (!_audioService.isPlaying &&
        _audioService.currentBeatId != null &&
        _state == TourState.approaching &&
        _pendingStopIndex != null) {
      _currentStopIndex = _pendingStopIndex!;
      _pendingStopIndex = null;
      _state = TourState.active;
      _playCurrentStop();
    } else if (!_audioService.isPlaying &&
        _audioService.currentBeatId == _audioKeyOf(currentStop)) {
      // Audio completed for current stop — advance index for next geofence
      if (_currentStopIndex + 1 < _stops.length) {
        _currentStopIndex++;
        notifyListeners();
      } else {
        _state = TourState.completed;
        notifyListeners();
      }
    }
  }

  /// The audio cache/playback key for a stop: the per-stop ItineraryItem id
  /// (Step 1.4d) when present, falling back to the legacy per-beat id. Both the
  /// play call and the completion check below use this so they always agree.
  String? _audioKeyOf(ItineraryStop? stop) =>
      stop == null ? null : (stop.stopId ?? stop.beatId);

  void _playCurrentStop() {
    if (_currentStopIndex < 0 || _currentStopIndex >= _stops.length) return;
    final stop = _stops[_currentStopIndex];
    if (stop.audioUrl != null) {
      _audioService.play(_audioKeyOf(stop)!, stop.audioUrl!);
      _state = TourState.active;
      notifyListeners();
    }
  }

  /// Haversine formula — returns distance in meters between two lat/lng points.
  @visibleForTesting
  static double haversineDistance(
    double lat1,
    double lon1,
    double lat2,
    double lon2,
  ) {
    const earthRadius = 6371000.0; // meters
    final dLat = _toRadians(lat2 - lat1);
    final dLon = _toRadians(lon2 - lon1);
    final a = sin(dLat / 2) * sin(dLat / 2) +
        cos(_toRadians(lat1)) *
            cos(_toRadians(lat2)) *
            sin(dLon / 2) *
            sin(dLon / 2);
    final c = 2 * atan2(sqrt(a), sqrt(1 - a));
    return earthRadius * c;
  }

  static double _toRadians(double degrees) => degrees * pi / 180.0;

  @override
  void dispose() {
    stopTour();
    super.dispose();
  }
}
