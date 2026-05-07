import 'package:ondoway/services/providers.dart';

/// Mock AudioService for unit testing.
/// Tracks play calls without actual audio playback.
class MockAudioService extends AudioProvider {
  String? _currentBeatId;
  bool _isPlaying = false;
  int _playCount = 0;

  @override
  String? get currentBeatId => _currentBeatId;
  @override
  bool get isPlaying => _isPlaying;
  int get playCount => _playCount;

  @override
  void play(String beatId, String audioUrl) {
    if (_currentBeatId == beatId && _isPlaying) return;
    _currentBeatId = beatId;
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
    notifyListeners();
  }

  /// Simulate audio completing playback.
  void simulateComplete() {
    _isPlaying = false;
    notifyListeners();
  }
}
