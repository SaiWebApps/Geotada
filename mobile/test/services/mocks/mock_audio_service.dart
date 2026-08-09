import 'package:ondoway/services/providers.dart';

/// Mock AudioService for unit testing.
/// Tracks play calls without actual audio playback.
class MockAudioService extends AudioProvider {
  String? _currentBeatId;
  bool _isPlaying = false;
  bool _isDeeperDive = false;
  int _playCount = 0;
  int prepareSessionCount = 0;
  List<String>? callLog;

  @override
  String? get currentBeatId => _currentBeatId;
  @override
  bool get isPlaying => _isPlaying;
  @override
  bool get isDeeperDive => _isDeeperDive;
  int get playCount => _playCount;

  int releaseSessionCount = 0;

  @override
  Future<void> prepareSession() async {
    prepareSessionCount++;
    callLog?.add('prepare');
  }

  @override
  Future<void> releaseSession() async {
    releaseSessionCount++;
    callLog?.add('release');
  }

  /// When false, [play] mimics a play that fails to start (e.g. the native
  /// player throwing): it records the beat and buffering-style notify but never
  /// sets isPlaying. Reproduces the on-device regression where a failed play
  /// looked like a completion and phantom-advanced the tour.
  bool playSucceeds = true;

  @override
  void play(String beatId, String audioUrl, {bool isDeeperDive = false}) {
    if (_currentBeatId == beatId && _isPlaying) return;
    _currentBeatId = beatId;
    _isDeeperDive = isDeeperDive;
    _isPlaying = playSucceeds;
    _playCount++;
    notifyListeners();
  }

  void pause() {
    if (!_isPlaying) return;
    _isPlaying = false;
    notifyListeners();
  }

  void resume() {
    if (_isPlaying || _currentBeatId == null) return;
    _isPlaying = true;
    notifyListeners();
  }

  @override
  void stop() {
    _isPlaying = false;
    _currentBeatId = null;
    _isDeeperDive = false;
    notifyListeners();
  }

  /// Simulate audio completing playback.
  void simulateComplete() {
    _isPlaying = false;
    notifyListeners();
  }
}
