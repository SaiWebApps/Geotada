import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:audio_session/audio_session.dart';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:just_audio/just_audio.dart';
import 'package:just_audio_background/just_audio_background.dart';
import 'package:path_provider/path_provider.dart';
import 'package:ondoway/services/providers.dart';

export 'package:ondoway/services/providers.dart' show BeatAudioInfo;

class AudioService extends ChangeNotifier implements AudioProvider {
  final http.Client _httpClient;
  AudioPlayer? _playerInstance;

  // ---- Phase 7 S7.9 (W7.2 R5): the audio SESSION and its interruptions -----
  // The session is configured for SPOKEN playback (background audio — the
  // walk keeps talking pocketed; iOS ducks us for a navigation prompt on its
  // own and interrupts us for a call or another app's music). The platform's
  // events are TRANSLATED here into the provider's one door; the policy is the
  // playback service's. Ducking is mechanics and stays here.
  bool _sessionReady = false;
  bool _ducked = false;
  bool _interrupted = false;
  final StreamController<AudioInterruptionKind> _interruptions =
      StreamController<AudioInterruptionKind>.broadcast();

  @override
  Stream<AudioInterruptionKind> get interruptions => _interruptions.stream;

  Future<void> _ensureSession() async {
    if (_sessionReady) return;
    _sessionReady = true;
    try {
      final session = await AudioSession.instance;
      await session.configure(const AudioSessionConfiguration.speech());
      session.interruptionEventStream.listen((event) {
        if (event.begin) {
          if (event.type == AudioInterruptionType.duck) {
            _ducked = true;
            _player.setVolume(0.25);
            _interruptions.add(AudioInterruptionKind.duckBegin);
          } else {
            // S8.7: the platform is TAKING the audio, so the pause that follows
            // is not a button anyone pressed. Held while it lasts so the remote
            // door below stays quiet — an interruption is never their pause.
            _interrupted = true;
            _interruptions.add(AudioInterruptionKind.pauseBegin);
          }
        } else {
          if (_ducked) {
            _ducked = false;
            _player.setVolume(1.0);
          }
          _interrupted = false;
          _interruptions.add(AudioInterruptionKind.ended);
        }
      });
    } catch (_) {
      // No session on this platform (a plain unit test, the web): the piece
      // still plays; there is simply nothing to translate.
    }
  }

  // ---- Phase 8 S8.7: THE LOCK SCREEN, translated (persona 09, Fiona & Dev) --
  // just_audio_background owns the platform's command centre: a press on the
  // lock screen, the earbud or the car moves the PLAYER and tells the app
  // afterwards. So the app's own INTENT is remembered here, and a reported
  // state that disagrees with it is the platform's doing — that disagreement IS
  // the command, and it goes out of the one door for the playback service to
  // answer. Nothing here decides anything: the policy (the tour's clock
  // suspended beside the audio) is TourPlaybackService's, exactly as with the
  // interruptions above.
  bool _appWantsPlaying = false;
  final StreamController<AudioRemoteCommand> _remoteCommands =
      StreamController<AudioRemoteCommand>.broadcast();

  @override
  Stream<AudioRemoteCommand> get remoteCommands => _remoteCommands.stream;

  void _translateRemoteCommand(PlayerState state) {
    // An interruption's pause is the platform TAKING the audio (S7.9), not a
    // button; loading and finishing are the app's own business either way.
    if (_interrupted ||
        state.processingState == ProcessingState.idle ||
        state.processingState == ProcessingState.completed) {
      return;
    }
    if (state.playing == _appWantsPlaying) return;
    _appWantsPlaying = state.playing;
    _remoteCommands.add(
      state.playing ? AudioRemoteCommand.play : AudioRemoteCommand.pause,
    );
  }

  /// What the lock screen SHOWS while [beatId] plays (S8.7). The title is the
  /// caller's real name for the piece — the place, the chapter, the line being
  /// said; with none, the piece's own id stands in and nothing is invented.
  static MediaItem _mediaItem(String beatId, String? title) =>
      MediaItem(id: beatId, title: title ?? beatId);

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
  /// operations (checkStopAudioStatus, prefetch, cache queries) never touch it,
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
  @override
  Duration get position => _position;
  /// S7.8: the player's decoded length, through the provider door (R6).
  @override
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
    String? title,
  }) async {
    if (_currentBeatId == beatId && _isPlaying) return;
    await _start(
      beatId,
      audioUrl,
      isDeeperDive: isDeeperDive,
      from: null,
      title: title,
    );
  }

  /// Phase 7 S7.6 (W7.2 R3): the keep-listening tap at a door resumes the cut
  /// piece from the START of its cut sentence — the source is set, the player
  /// seeks, then plays; never a cut word. `void` because the provider's door is
  /// synchronous; the work is the same one start path [play] uses.
  @override
  void playFrom(String beatId, String audioUrl, Duration from, {String? title}) {
    _start(beatId, audioUrl, isDeeperDive: false, from: from, title: title);
  }

  /// THE one start path: source (the cache, else the URL), an optional seek,
  /// play. [play] and [playFrom] are its two doors.
  Future<void> _start(
    String beatId,
    String audioUrl, {
    required bool isDeeperDive,
    required Duration? from,
    String? title,
  }) async {
    _currentBeatId = beatId;
    _isDeeperDive = isDeeperDive;
    _isBuffering = true;
    _isCompleted = false;
    notifyListeners();

    try {
      await _ensureSession(); // S7.9: spoken playback, interruptions heard
      // S8.7: every source carries its MediaItem tag, or the lock screen has
      // nothing to show and just_audio_background refuses the source outright.
      final tag = _mediaItem(beatId, title);
      final cachedPath = await _getCachedPath(beatId);
      if (cachedPath != null) {
        await _player.setAudioSource(AudioSource.file(cachedPath, tag: tag));
      } else {
        await _player.setAudioSource(
          AudioSource.uri(Uri.parse(audioUrl), tag: tag),
        );
      }
      if (from != null && from > Duration.zero) {
        await _player.seek(from);
      }
      _appWantsPlaying = true; // S8.7: the intent, before the player reports it
      await _player.play();
    } catch (e) {
      _isBuffering = false;
      notifyListeners();
      rethrow;
    }
  }

  @override
  Future<void> pause() async {
    _appWantsPlaying = false; // S8.7: ours, so it is not read back as a command
    await _player.pause();
  }

  @override
  Future<void> resume() async {
    _appWantsPlaying = true;
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
    _appWantsPlaying = false; // S8.7
    await _player.stop();
    _currentBeatId = null;
    _isDeeperDive = false;
    _position = Duration.zero;
    _isPlaying = false;
    _isCompleted = false;
    notifyListeners();
  }

  @override
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

  /// Check PER-STOP audio status by ItineraryItem id (Phase 1, Step 1.4d) —
  /// THE status poll (the per-beat one was deleted at Phase 7 S7.10).
  ///
  /// GET /audio/stop-status/{stopId} reads the per-stop narration audio
  /// persisted by /audio/generate-trip-stops, so the itinerary flow polls/plays
  /// per stop. Returns the parsed body ({has_audio, audio_url, duration_sec})
  /// on 200, null otherwise.
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
    _interruptions.close();
    _remoteCommands.close();
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
    _translateRemoteCommand(state); // S8.7: the lock screen, heard here
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
