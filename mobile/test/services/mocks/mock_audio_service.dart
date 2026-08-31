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

  /// S8.7: the platform's transport buttons, simulated.
  final StreamController<AudioRemoteCommand> _remoteCommands =
      StreamController<AudioRemoteCommand>.broadcast(sync: true);

  @override
  Stream<AudioRemoteCommand> get remoteCommands => _remoteCommands.stream;

  /// Simulate a press on the LOCK SCREEN. The buttons there reach the player
  /// first — the platform's transport moves it — and the app hears about it
  /// afterwards, which is the whole reason the command needs a door of its own.
  void simulateRemoteCommand(AudioRemoteCommand command) {
    final wants = command == AudioRemoteCommand.play;
    if (_isPlaying != wants && _currentBeatId != null) {
      _isPlaying = wants;
      notifyListeners();
    }
    _remoteCommands.add(command);
  }

  String? _currentBeatId;
  bool _isPlaying = false;
  bool _isDeeperDive = false;
  bool _isCompleted = false;
  int _playCount = 0;

  /// Every id handed to [play], in order — so a test can count REPLAYS of one
  /// piece (W7.13: a told chapter replays by tap, never by itself).
  final List<String> playedIds = [];

  /// S8.7: the title handed with each played id — what the lock screen would
  /// show. A test asserts it is the place's own name, never a stand-in.
  final Map<String, String?> titles = {};

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
  void play(
    String beatId,
    String audioUrl, {
    bool isDeeperDive = false,
    String? title,
  }) {
    if (_currentBeatId == beatId && _isPlaying) return;
    playedIds.add(beatId);
    titles[beatId] = title;
    _currentBeatId = beatId;
    _isDeeperDive = isDeeperDive;
    // The piece was accepted either way; whether it SOUNDS is what
    // [playSucceeds] decides.
    _isPlaying = playSucceeds;
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

  /// Every session door the tour opened or closed, in order: 'prepare' when
  /// the walk asked for the audio session, 'release' when it gave it back.
  /// The iOS session must be ACTIVATED from the foreground — iOS refuses it
  /// from a background callback — so which of these the tour calls, and when,
  /// is the difference between narration a locked phone plays and silence.
  final List<String> sessionCalls = [];

  /// A log SHARED with the location double, so a test can assert the ORDER of
  /// calls across both — `['prepare', 'track']`. Order is the whole assertion:
  /// the session has to be activated while the app is still in the foreground,
  /// before background tracking begins, or iOS refuses it later and the locked
  /// phone plays nothing. Two separate per-double logs could not express that.
  List<String>? callLog;

  /// When false, [play] records the piece but never reaches playing — the
  /// native player accepting the call and then failing to sound. The tour must
  /// hold its position through that: no phantom advance to the next stop.
  bool playSucceeds = true;

  int get prepareSessionCount =>
      sessionCalls.where((call) => call == 'prepare').length;

  int get releaseSessionCount =>
      sessionCalls.where((call) => call == 'release').length;

  @override
  Future<void> prepareSession() async {
    sessionCalls.add('prepare');
    callLog?.add('prepare');
  }

  @override
  Future<void> releaseSession() async {
    sessionCalls.add('release');
    callLog?.add('release');
  }

  /// Simulate audio completing playback — the piece reached its END on its own
  /// (a pause is NOT this: it leaves [isCompleted] false).
  void simulateComplete() {
    _isPlaying = false;
    _isCompleted = true;
    notifyListeners();
  }
}
