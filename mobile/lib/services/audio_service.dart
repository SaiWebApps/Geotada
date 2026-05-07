import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:just_audio/just_audio.dart';
import 'package:path_provider/path_provider.dart';

class AudioService extends ChangeNotifier {
  final AudioPlayer _player = AudioPlayer();
  final http.Client _httpClient;

  String? _currentBeatId;
  bool _isPlaying = false;
  bool _isBuffering = false;
  Duration _position = Duration.zero;
  Duration _duration = Duration.zero;

  AudioService({http.Client? httpClient})
      : _httpClient = httpClient ?? http.Client() {
    _player.playerStateStream.listen(_onPlayerStateChanged);
    _player.positionStream.listen(_onPositionChanged);
    _player.durationStream.listen(_onDurationChanged);
  }

  // Getters
  String? get currentBeatId => _currentBeatId;
  bool get isPlaying => _isPlaying;
  bool get isBuffering => _isBuffering;
  Duration get position => _position;
  Duration get duration => _duration;
  bool get isActive => _currentBeatId != null;

  /// Play audio for a beat. Uses cached file if available, otherwise streams from URL.
  Future<void> play(String beatId, String audioUrl) async {
    if (_currentBeatId == beatId && _isPlaying) return;

    _currentBeatId = beatId;
    _isBuffering = true;
    notifyListeners();

    try {
      final cachedPath = await _getCachedPath(beatId);
      if (cachedPath != null) {
        await _player.setFilePath(cachedPath);
      } else {
        await _player.setUrl(audioUrl);
      }
      await _player.play();
    } catch (e) {
      _isBuffering = false;
      notifyListeners();
      rethrow;
    }
  }

  Future<void> pause() async {
    await _player.pause();
  }

  Future<void> resume() async {
    await _player.play();
  }

  Future<void> stop() async {
    await _player.stop();
    _currentBeatId = null;
    _position = Duration.zero;
    _isPlaying = false;
    notifyListeners();
  }

  Future<void> seek(Duration position) async {
    await _player.seek(position);
  }

  /// Pre-fetch audio files for a list of beats to device cache.
  /// Returns the number of files successfully cached.
  Future<int> prefetchAudio(List<BeatAudioInfo> beats) async {
    final cacheDir = await _cacheDirectory();
    int cached = 0;

    for (final beat in beats) {
      if (beat.audioUrl == null) continue;
      final file = File('${cacheDir.path}/${beat.beatId}.mp3');
      if (await file.exists()) {
        cached++;
        continue;
      }
      try {
        final response = await _httpClient.get(Uri.parse(beat.audioUrl!));
        if (response.statusCode == 200) {
          await file.writeAsBytes(response.bodyBytes);
          cached++;
        }
      } catch (_) {
        // Skip failed downloads — audio will stream on demand
      }
    }
    return cached;
  }

  /// Check if a beat's audio is cached locally.
  Future<bool> isCached(String beatId) async {
    final path = await _getCachedPath(beatId);
    return path != null;
  }

  /// Clear all cached audio files.
  Future<void> clearCache() async {
    final dir = await _cacheDirectory();
    if (await dir.exists()) {
      await for (final entity in dir.list()) {
        if (entity is File && entity.path.endsWith('.mp3')) {
          await entity.delete();
        }
      }
    }
  }

  /// Total size of cached audio in bytes.
  Future<int> cacheSize() async {
    final dir = await _cacheDirectory();
    if (!await dir.exists()) return 0;
    int total = 0;
    await for (final entity in dir.list()) {
      if (entity is File && entity.path.endsWith('.mp3')) {
        total += await entity.length();
      }
    }
    return total;
  }

  @override
  void dispose() {
    _player.dispose();
    super.dispose();
  }

  // Private helpers

  Future<String?> _getCachedPath(String beatId) async {
    final dir = await _cacheDirectory();
    final file = File('${dir.path}/$beatId.mp3');
    if (await file.exists()) return file.path;
    return null;
  }

  Future<Directory> _cacheDirectory() async {
    final tempDir = await getTemporaryDirectory();
    final cacheDir = Directory('${tempDir.path}/ondoway_audio');
    if (!await cacheDir.exists()) {
      await cacheDir.create(recursive: true);
    }
    return cacheDir;
  }

  void _onPlayerStateChanged(PlayerState state) {
    _isPlaying = state.playing;
    _isBuffering = state.processingState == ProcessingState.loading ||
        state.processingState == ProcessingState.buffering;

    if (state.processingState == ProcessingState.completed) {
      _isPlaying = false;
      _position = _duration;
    }
    notifyListeners();
  }

  void _onPositionChanged(Duration position) {
    _position = position;
    notifyListeners();
  }

  void _onDurationChanged(Duration? duration) {
    _duration = duration ?? Duration.zero;
    notifyListeners();
  }
}

/// Minimal info needed for prefetching audio.
class BeatAudioInfo {
  final String beatId;
  final String? audioUrl;

  const BeatAudioInfo({required this.beatId, this.audioUrl});
}
