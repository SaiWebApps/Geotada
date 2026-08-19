import 'package:ondoway/services/providers.dart';

/// Mock AudioService for unit testing.
/// Tracks play calls without actual audio playback.
class MockAudioService extends AudioProvider {
  String? _currentBeatId;
  bool _isPlaying = false;
  bool _isDeeperDive = false;
  bool _isCompleted = false;
  int _playCount = 0;

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

  /// Simulate audio completing playback — the piece reached its END on its own
  /// (a pause is NOT this: it leaves [isCompleted] false).
  void simulateComplete() {
    _isPlaying = false;
    _isCompleted = true;
    notifyListeners();
  }
}
