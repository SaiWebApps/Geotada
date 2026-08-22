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

  /// True when the current piece has reached its END on its own. Not the same
  /// as "not playing": a paused piece is not playing and has not completed
  /// (W5.13: pausing was read as completion and the tour jumped a stop). The
  /// default is false so a double that never completes need not implement it.
  bool get isCompleted => false;

  /// True while the currently-playing source is a "keep exploring here"
  /// deep-dive clip (KE6). The tour auto-advance MUST NOT fire when this is set
  /// — a deep dive is served off the tour budget and never moves the itinerary.
  bool get isDeeperDive;

  /// Where the current piece is, from its start (Phase 6 S6.4): the session
  /// uses it to stop a piece at the end of its CURRENT SENTENCE on [Head back
  /// now] — never a cut word, never the whole piece (W6.2 R8). The default is
  /// zero so a double that does not track position need not implement it.
  Duration get position => Duration.zero;

  /// Play [audioUrl] under [beatId]. Set [isDeeperDive] for on-demand
  /// "keep exploring here" audio so completion does not auto-advance the tour.
  void play(String beatId, String audioUrl, {bool isDeeperDive = false});
  void stop();

  /// Pause / resume the current piece. Phase 5 (design §4.3): the tour's own
  /// pause goes through this door so the session can suspend its clock beside
  /// the audio; the defaults do nothing so a double that never pauses need not
  /// implement them.
  Future<void> pause() => Future.value();
  Future<void> resume() => Future.value();

  /// Say one sentence of the SESSION's own voice (design §4.4) — never a story.
  /// The playback service hands a line here only at a natural moment (W5.2 R3)
  /// and only after it is already on the screen (§4.4.2). The default is silent:
  /// the phone has no voice plugin today, and "mute beats graceful" (§4.4.4) —
  /// wiring a voice is one implementation behind this door.
  Future<void> speak(String sentence) => Future.value();

  /// Pre-fetch audio files to the device cache; returns how many are cached.
  /// Phase 5 (design §4.7): the session prefetches its alternates' audio through
  /// this same door. The default caches nothing, so a test double that never
  /// caches need not implement it.
  Future<int> prefetchAudio(List<BeatAudioInfo> beats) => Future.value(0);
}

/// Minimal info needed for prefetching audio.
class BeatAudioInfo {
  final String beatId;
  final String? audioUrl;

  const BeatAudioInfo({required this.beatId, this.audioUrl});
}
