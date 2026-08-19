import 'dart:convert';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:just_audio/just_audio.dart';
import 'package:path_provider/path_provider.dart';
import 'package:ondoway/services/providers.dart';

export 'package:ondoway/services/providers.dart' show BeatAudioInfo;

class AudioService extends ChangeNotifier implements AudioProvider {
  final http.Client _httpClient;
  AudioPlayer? _playerInstance;

  String? _currentBeatId;
  bool _isPlaying = false;
  bool _isBuffering = false;
  bool _isDeeperDive = false;
  bool _isCompleted = false;
  Duration _position = Duration.zero;
  Duration _duration = Duration.zero;

  AudioService({http.Client? httpClient})
      : _httpClient = httpClient ?? http.Client();

  /// The just_audio player, created lazily on first playback. HTTP-only
  /// operations (checkAudioStatus, prefetch, cache queries) never touch it,
  /// so they don't boot the audio engine / its platform channels — which also
  /// lets them run in plain unit tests without a Flutter binding.
  AudioPlayer get _player {
    final existing = _playerInstance;
    if (existing != null) return existing;
    final player = AudioPlayer();
    player.playerStateStream.listen(_onPlayerStateChanged);
    player.positionStream.listen(_onPositionChanged);
    player.durationStream.listen(_onDurationChanged);
    _playerInstance = player;
    return player;
  }

  // Getters
  @override
  String? get currentBeatId => _currentBeatId;
  @override
  bool get isPlaying => _isPlaying;
  @override
  bool get isCompleted => _isCompleted;
  @override
  bool get isDeeperDive => _isDeeperDive;
  bool get isBuffering => _isBuffering;
  Duration get position => _position;
  Duration get duration => _duration;
  bool get isActive => _currentBeatId != null;

  /// Play audio for a beat. Uses cached file if available, otherwise streams from URL.
  ///
  /// Set [isDeeperDive] for on-demand "keep exploring here" audio (KE6); the flag
  /// is tracked so tour auto-advance can skip completion of a deep-dive clip.
  @override
  Future<void> play(
    String beatId,
    String audioUrl, {
    bool isDeeperDive = false,
  }) async {
    if (_currentBeatId == beatId && _isPlaying) return;

    _currentBeatId = beatId;
    _isDeeperDive = isDeeperDive;
    _isBuffering = true;
    _isCompleted = false;
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

  @override
  Future<void> pause() async {
    await _player.pause();
  }

  @override
  Future<void> resume() async {
    await _player.play();
  }

  /// The session's own voice (design §4.4). The phone carries no text-to-speech
  /// plugin today, so this door is SILENT: every line reaches it only after it
  /// is on the screen (§4.4.2), and "mute beats graceful" (§4.4.4). Wiring a
  /// voice is one implementation here; the etiquette (when a line may be said —
  /// W5.2 R3/R4) lives in TourPlaybackService and does not change with it.
  @override
  Future<void> speak(String sentence) async {}

  @override
  Future<void> stop() async {
    await _player.stop();
    _currentBeatId = null;
    _isDeeperDive = false;
    _position = Duration.zero;
    _isPlaying = false;
    _isCompleted = false;
    notifyListeners();
  }

  Future<void> seek(Duration position) async {
    await _player.seek(position);
  }

  /// Pre-fetch audio files for a list of beats to device cache.
  /// Returns the number of files successfully cached.
  @override
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

  /// Check audio status for a specific beat via the backend API.
  Future<Map<String, dynamic>?> checkAudioStatus(
    String baseUrl,
    String beatId,
  ) async {
    try {
      final resp = await _httpClient.get(
        Uri.parse('$baseUrl/audio/status/$beatId'),
      );
      if (resp.statusCode == 200) {
        return jsonDecode(resp.body) as Map<String, dynamic>;
      }
    } catch (_) {}
    return null;
  }

  /// Check PER-STOP audio status by ItineraryItem id (Phase 1, Step 1.4d).
  ///
  /// Additive to [checkAudioStatus] (per-beat): GET /audio/stop-status/{stopId}
  /// reads the per-stop narration audio persisted by /audio/generate-trip-stops,
  /// so the itinerary flow polls/plays per stop. Returns the parsed body
  /// ({has_audio, audio_url, duration_sec}) on 200, null otherwise.
  Future<Map<String, dynamic>?> checkStopAudioStatus(
    String baseUrl,
    String stopId,
  ) async {
    try {
      final resp = await _httpClient.get(
        Uri.parse('$baseUrl/audio/stop-status/$stopId'),
      );
      if (resp.statusCode == 200) {
        return jsonDecode(resp.body) as Map<String, dynamic>;
      }
    } catch (_) {}
    return null;
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
    _playerInstance?.dispose();
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

    _isCompleted = state.processingState == ProcessingState.completed;
    if (_isCompleted) {
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
