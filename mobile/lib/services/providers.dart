import 'package:flutter/foundation.dart';

/// Abstract interface for location tracking.
/// Allows mocking in tests without depending on geolocator.
abstract class LocationProvider extends ChangeNotifier {
  dynamic get lastPosition;
  bool get isTracking;
  bool get lowAccuracy;
  Future<bool> startTracking();
  void stopTracking();
}

/// Abstract interface for audio playback.
/// Allows mocking in tests without depending on an audio plugin.
abstract class AudioProvider extends ChangeNotifier {
  String? get currentBeatId;
  bool get isPlaying;
  void play(String beatId, String audioUrl);
  void stop();
}
