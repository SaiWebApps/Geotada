import 'package:flutter/foundation.dart';

/// Abstract interface for location tracking.
/// Allows mocking in tests without depending on geolocator.
abstract class LocationProvider extends ChangeNotifier {
  dynamic get lastPosition;
  bool get isTracking;
  bool get lowAccuracy;
  Future<bool> startTracking({bool background = false});
  void stopTracking();
}

/// Abstract interface for audio playback.
/// Allows mocking in tests without depending on an audio plugin.
abstract class AudioProvider extends ChangeNotifier {
  String? get currentBeatId;
  bool get isPlaying;

  /// True while the currently-playing source is a "keep exploring here"
  /// deep-dive clip (KE6). The tour auto-advance MUST NOT fire when this is set
  /// — a deep dive is served off the tour budget and never moves the itinerary.
  bool get isDeeperDive;

  /// Play [audioUrl] under [beatId]. Set [isDeeperDive] for on-demand
  /// "keep exploring here" audio so completion does not auto-advance the tour.
  void play(String beatId, String audioUrl, {bool isDeeperDive = false});
  void stop();
}
