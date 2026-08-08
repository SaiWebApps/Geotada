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

  @override
  Future<void> prepareSession() async {
    prepareSessionCount++;
    callLog?.add('prepare');
  }

  @override
  void play(String beatId, String audioUrl, {bool isDeeperDive = false}) {
    if (_currentBeatId == beatId && _isPlaying) return;
    _currentBeatId = beatId;
    _isDeeperDive = isDeeperDive;
    _isPlaying = true;
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
