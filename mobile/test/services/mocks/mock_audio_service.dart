import 'dart:async';

import 'package:ondoway/services/providers.dart';

/// Mock AudioService for unit testing.
/// Tracks play calls without actual audio playback.
class MockAudioService extends AudioProvider {
  /// S7.9: the platform's interruptions, simulated (a call, a nav prompt).
  final StreamController<AudioInterruptionKind> _interruptions =
      StreamController<AudioInterruptionKind>.broadcast(sync: true);

  @override
  Stream<AudioInterruptionKind> get interruptions => _interruptions.stream;

  /// Simulate what the audio session would report. A pause-kind interruption
  /// also pauses the player, as iOS does before telling the app.
  void simulateInterruption(AudioInterruptionKind kind) {
    if (kind == AudioInterruptionKind.pauseBegin && _isPlaying) {
      _isPlaying = false;
      notifyListeners();
    }
    _interruptions.add(kind);
  }

  String? _currentBeatId;
  bool _isPlaying = false;
  bool _isDeeperDive = false;
  bool _isCompleted = false;
  int _playCount = 0;

  /// Every id handed to [play], in order — so a test can count REPLAYS of one
  /// piece (W7.13: a told chapter replays by tap, never by itself).
  final List<String> playedIds = [];

  @override
  String? get currentBeatId => _currentBeatId;
  @override
  bool get isPlaying => _isPlaying;
  @override
  bool get isDeeperDive => _isDeeperDive;
  @override
  bool get isCompleted => _isCompleted;
  int get playCount => _playCount;

  @override
  void play(String beatId, String audioUrl, {bool isDeeperDive = false}) {
    if (_currentBeatId == beatId && _isPlaying) return;
    playedIds.add(beatId);
    _currentBeatId = beatId;
    _isDeeperDive = isDeeperDive;
    _isPlaying = true;
    _isCompleted = false;
    _playCount++;
    notifyListeners();
  }

  @override
  Future<void> pause() async {
    if (!_isPlaying) return;
    _isPlaying = false;
    notifyListeners();
  }

  @override
  Future<void> resume() async {
    if (_isPlaying || _currentBeatId == null) return;
    _isPlaying = true;
    notifyListeners();
  }

  @override
  void stop() {
    _isPlaying = false;
    _isCompleted = false;
    _currentBeatId = null;
    _isDeeperDive = false;
    notifyListeners();
  }

  /// S7.6: where the last seek landed (the keep-listening tap), for tests.
  Duration? lastSeek;

  /// S7.8 (W7.2 R6): the length the PLAYER knows for the loaded file — a test
  /// sets it to stand in for the real player's decoded duration. Zero = unknown.
  @override
  Duration duration = Duration.zero;

  @override
  Future<void> seek(Duration position) async {
    lastSeek = position;
  }

  /// Simulate audio completing playback — the piece reached its END on its own
  /// (a pause is NOT this: it leaves [isCompleted] false).
  void simulateComplete() {
    _isPlaying = false;
    _isCompleted = true;
    notifyListeners();
  }
}
