import 'dart:async';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:ondoway/models/trip.dart';
import 'package:ondoway/services/providers.dart';

export 'package:ondoway/services/providers.dart'
    show LocationProvider, AudioProvider;

enum TourState { idle, active, approaching, completed }

/// The phone's MEASURED divergence, as facts (design §4.6). Every field is a
/// number the phone observed or an id it stands at; none is a decision. The
/// service matches these against the session's contingency triggers, in server
/// order, and takes the first that fits — it never weighs one entry against another.
class Divergence {
  final int? minutesLate;
  final int? minutesEarly;
  final int? minutesLeft;
  final String? skippedStopId;
  final String? wrapUpFromStopId;
  final String? atRiskStopId;

  /// The stop the person is at or has just left (W5.12): a late/early/minutes-
  /// left band is the server's answer FROM that stop, so an entry names it and
  /// the phone matches it. Null = the position is unknown; the band alone
  /// decides (the S5.9 lookup).
  final String? atStopId;

  const Divergence({
    this.minutesLate,
    this.minutesEarly,
    this.minutesLeft,
    this.skippedStopId,
    this.wrapUpFromStopId,
    this.atRiskStopId,
    this.atStopId,
  });
}

/// One remaining stop's re-timed clocks, in seconds from NOW (Phase 5 S5.10) —
/// the output of the phone's one re-timing expression, [TourPlaybackService.retimeRemaining].
class StopEta {
  final ItineraryStop stop;
  final int secondsToArrival;
  final int secondsToDeparture;
  const StopEta(this.stop, this.secondsToArrival, this.secondsToDeparture);
}

class _Fix {
  final double lat;
  final double lng;
  final DateTime at;
  const _Fix(this.lat, this.lng, this.at);
}

class TourPlaybackService extends ChangeNotifier {
  final LocationProvider _locationService;
  final AudioProvider _audioService;

  // ---- Phase 5 S5.10: the phone's ARITHMETIC (design §4.1/§4.3) ----------
  // Learned pace, learned listening rate, pause as information, and the ONE
  // re-timing expression. Numbers the phone measured; never a decision.

  /// Inside this circle the person is AT the stop: no leg, no pace training,
  /// no lateness (W5.2: "wandering inside a stop is not a divergence").
  static const double kStopCircleM = 40.0;

  /// Moving seconds needed before the learned pace replaces the preset
  /// (§4.1 "within the first ~15 minutes": five minutes of actual walking).
  static const int kPaceLearnAfterSeconds = 300;

  /// A segment slower than this is standing (a crossing, a conversation);
  /// faster is not walking (a bus). Neither trains the pace.
  static const double kMinWalkingMps = 0.4;
  static const double kMaxWalkingMps = 3.0;

  /// The same straight-line correction the server's estimate uses
  /// (src/tour/routing.py HAVERSINE_CORRECTION) — one number, both sides.
  static const double kHaversineCorrection = 1.35;

  /// The base speed the wire's pace multiplier is on (routing.py PACE_KMH).
  static const double kServerPaceKmh = 3.0;

  final DateTime Function() _now;
  DateTime? _startedAt;
  // The TOUR clock starts at the first play or the first step off the square
  // (W5.2 R1.3; W5.14 Fiona & Dev: "our tour clock ran from 15:00 while we
  // stood on the square"); the WALL clock starts at the tap.
  DateTime? _tourClockStartedAt;
  _Fix? _firstFix;
  // The TWO clocks (§4.3): the wall keeps spending through a pause; the tour
  // clock is suspended by it. A pause is information, never lateness.
  int _pausedSeconds = 0;
  DateTime? _pausedAt;
  int _pauseCount = 0;
  int _longestPauseSeconds = 0;
  // Learned pace: moving metres over moving seconds, on walking legs only.
  double _movingMeters = 0;
  double _movingSeconds = 0;
  _Fix? _lastFix;
  // Learned listening rate: wall seconds spent listening over stated seconds
  // (a replay adds wall time against the same stated length; a faster
  // playback speed spends less wall time on it).
  double _statedListened = 0;
  double _wallListened = 0;
  final Set<String> _statedKeys = {};
  DateTime? _playingSince;
  String? _playingKey;
  // Skip = unplayed AND unopened (a piece read on the screen was not skipped).
  final Set<String> _played = {};
  final Set<String> _opened = {};
  String? _lastSkippedPoiId;
  bool _wrapUpRequested = false;
  // THE SEAM's phone half: what the phone REPORTED about a clock gap. Lines
  // for the screen; nothing is ever corrected from them.
  final List<String> _clockNotices = [];

  // ---- Phase 5 S5.11: announcement etiquette (design §4.4; W5.2 R3/R4) ----
  /// Standing still this long at a stop before a moment can be "natural" — the
  /// settling period the panel named (shaking out rain, looking up: R3).
  static const int kSettleSeconds = 30;

  /// A fix this far from the last one is movement.
  static const double kStillRadiusM = 8.0;

  /// R4 — the day-long screen-only switch, per party: after the second pause
  /// of the day, or one pause longer than this (couple: 10 min; family: 5).
  static const int kLongPauseCoupleSeconds = 600;
  static const int kLongPauseFamilySeconds = 300;

  /// The one plain sentence said once when the switch flips (Aiko, Camille).
  static const String kScreenOnlyLine =
      "I'll keep this on the screen from here — tap the speaker to hear it again.";

  // The speech QUEUE (§4.4.1): at most one line waiting to be said, and it is
  // already on the screen. A newer line replaces an older one unsaid (a stale
  // sentence EXPIRES undelivered — R3); the question is the one line that
  // survives to the next moment, said once (R2.5, R4).
  String? _queuedLine;
  String? _queuedLineAudioUrl; // S6.8: the line's pre-voiced file, when it has one
  bool _queuedIsQuestion = false;
  bool _questionSpoken = false;
  final List<String> _spoken = [];
  DateTime? _stillSince;
  bool _pieceEndedNaturally = false;
  bool _transcriptOpen = false;
  // R4: pauses per stop (solo: two pauses inside ONE stop silence that stop).
  final Map<String, int> _pausesAtStop = {};
  bool _voiceRestored = false;
  bool _screenOnlyAnnounced = false;
  bool _pausedMidPiece = false;

  List<ItineraryStop> _stops = [];
  // The day as planned — the list handed to [startTour]. Every entry the phone
  // applies is an ordered subset of THIS (§4.7: it cannot add what it does not
  // hold), so ids are always mapped over it, never over the working list.
  List<ItineraryStop> _planned = [];
  int _currentStopIndex = -1;
  int? _pendingStopIndex;
  TourState _state = TourState.idle;
  double? _distanceToNext;

  // THE LIVING SESSION the phone holds (Phase 5, design §4.6/§4.7): the plan
  // the server sent and its contingency set. The phone SELECTS from it — the
  // one method that changes the current plan is [applyContingency], and its
  // only decision input is a server contingency id.
  SessionPlan? _session;
  SessionContingency? _selected;
  String? _screenText;
  String? _pendingQuestion;

  // ---- Phase 6 S6.4: the CLOSE (design §5.3; W6.2 R8) ----------------------
  // [Head back now] is the seam the person made: the current SENTENCE finishes,
  // the piece does not; then the stretch's close — one line — then the way home
  // on the screen; then nothing. The close is narrator CONTENT: it plays as its
  // own pre-voiced file when the wire carries one (S6.8), else it is handed to
  // the one door and is on the screen either way (§4.4.2).
  String? _closeLine;
  String? _threadLine;
  final List<String> _closesPlayed = [];
  Timer? _sentenceEndTimer;
  ItineraryStop? _closePending;
  bool _closePendingIsFull = false; // S6.6/S6.8: the pending cut is a FULL piece

  /// Seconds a tapped piece may keep playing to reach its sentence end before
  /// it is cut anyway — a person who tapped is not made to wait out a
  /// forty-second sentence (Fiona: "five seconds is the whole budget").
  static const int kSentenceEndCapSeconds = 12;

  VoidCallback? _locationListener;
  VoidCallback? _audioListener;

  // Getters
  TourState get state => _state;
  int get currentStopIndex => _currentStopIndex;
  int? get pendingStopIndex => _pendingStopIndex;
  double? get distanceToNext => _distanceToNext;
  ItineraryStop? get currentStop =>
      _currentStopIndex >= 0 && _currentStopIndex < _stops.length
          ? _stops[_currentStopIndex]
          : null;
  ItineraryStop? get nextStop => _currentStopIndex + 1 < _stops.length
      ? _stops[_currentStopIndex + 1]
      : null;
  bool get isActive =>
      _state != TourState.idle && _state != TourState.completed;
  bool get hasPendingStop => _pendingStopIndex != null;
  SessionPlan? get session => _session;
  SessionContingency? get selectedContingency => _selected;
  /// The one line the screen shows for the current state (§4.4.2 — everything
  /// spoken is also on screen; a fabric change is on screen only).
  String? get screenText => _screenText;
  /// The ONE question, when a selected entry carries one (§4.2); null otherwise.
  String? get pendingQuestion => _pendingQuestion;
  /// The close the last wrap-up put on the screen (S6.4) — the stretch's own
  /// line, or the day's when no piece was playing. Null until a wrap-up.
  String? get closeLine => _closeLine;

  /// S6.5 (W6.2 R5): the THREAD of the pair the session just made — one
  /// sentence, on screen through the leg, spoken once at a standing seam.
  String? get threadLine => _threadLine;

  /// S6.6 (design §5.5; W6.2 R3, 9/11 by name): THE LINGER RULE — a linger
  /// OFFERS the full telling on the screen, silently; a TAP plays it. Never
  /// auto-play on stillness. The offer shows only at a standing seam INSIDE the
  /// stop's circle, after the stop's own tight piece ended on its own — never
  /// while paused, never mid-piece, never at an unplanned place (only planned
  /// stops carry a full telling), and it names its cost (Marcus: "Full telling
  /// · 7 min"). Null when the stop has no authored full telling: the offer
  /// simply never appears there.
  String? get fullTellingOffer {
    final stop = _offeredFullStop();
    if (stop == null) return null;
    return 'Full telling · ${stop.fullTellingMinutes} min';
  }

  ItineraryStop? _offeredFullStop() {
    if (!isNaturalMoment) return null;
    final fix = _lastFix;
    if (fix == null) return null;
    final stop = _stopUnderfoot(fix);
    if (stop == null || stop.fullNarration == null) return null;
    final key = _audioKeyOf(stop);
    // The tight telling comes first: no offer before its piece has ENDED on its
    // own (isNaturalMoment's not-begun arm must not offer).
    if (key == null || !_played.contains(key) || !_pieceEndedNaturally) return null;
    return stop;
  }

  /// The TAP on the offer: play the voiced full telling (the on-demand door's
  /// artifact — S6.6 makes it the authored full telling, never the raw dump).
  /// A second piece at this stop, through the player's own door.
  void playFullTelling(String audioUrl, {num? durationSec}) {
    final stop = _offeredFullStop();
    if (stop == null) return;
    _pieceEndedNaturally = false;
    _fullPieceDurationSec = durationSec;
    _audioService.play('${_audioKeyOf(stop)!}-full', audioUrl, isDeeperDive: true);
    notifyListeners();
  }

  num? _fullPieceDurationSec; // S6.8: the playing full telling's length

  /// "AGAIN" is a separate control from "more" (W6.2 R3, 8 personas by name:
  /// the re-listen is not the full telling): replay THIS stop's tight piece.
  void playAgain() {
    final fix = _lastFix;
    final stop = fix == null ? null : _stopUnderfoot(fix);
    if (stop == null || stop.audioUrl == null) return;
    _pieceEndedNaturally = false;
    _audioService.play(_audioKeyOf(stop)!, stop.audioUrl!);
    notifyListeners();
  }
  /// Every close this session played or said, in order (for the screen's
  /// record and for tests).
  List<String> get closesPlayed => List.unmodifiable(_closesPlayed);

  TourPlaybackService({
    required LocationProvider locationService,
    required AudioProvider audioService,
    DateTime Function()? now,
  })  : _locationService = locationService,
        _audioService = audioService,
        _now = now ?? DateTime.now;

  // ---- S5.10 getters: the measured numbers -------------------------------

  /// Real seconds since the tour started (a pause does NOT stop this one).
  int get wallElapsedSeconds =>
      _startedAt == null ? 0 : _now().difference(_startedAt!).inSeconds;
  int get _openPauseSeconds =>
      _pausedAt == null ? 0 : _now().difference(_pausedAt!).inSeconds;

  /// The tour clock: seconds since the first play or the first step off the
  /// square, minus every pause since (§4.3). Zero while the person still
  /// stands where they started.
  int get tourElapsedSeconds {
    final from = _tourClockStartedAt;
    if (from == null) return 0;
    return max(
      0,
      _now().difference(from).inSeconds - _pausedSeconds - _openPauseSeconds,
    );
  }

  /// The tour clock has started (first play or first step off the square).
  bool get tourClockRunning => _tourClockStartedAt != null;

  void _startTourClockIfNeeded() {
    _tourClockStartedAt ??= _now();
  }

  // ---- W5.14 Q3: a firm or wall finish that has moved ----------------------
  String? _finishMovedLine;
  int? _finishMovedNoticedAt;

  /// One screen line when a FIRM or WALL finish has moved past the tolerance
  /// (W5.14 Q3, the panel's majority: "one line on the screen at the next
  /// moment, never spoken, never a question"; Fiona & Dev's 18:00 became 18:53
  /// in silence). An OPEN day's finish moves in silence — nobody asked for that
  /// clock. Re-issued only when the finish moves again by more than the
  /// tolerance.
  String? get finishMovedLine => _finishMovedLine;

  void _checkFinishMoved() {
    if (!isActive) {
      _finishMovedLine = null; // a walk that is over has no finish to defend
      return;
    }
    final session = _session;
    final eta = finishEtaSeconds;
    if (session == null ||
        eta == null ||
        _startedAt == null ||
        session.plannedEndHhmm.length != 5 ||
        session.endHardness == 'open') {
      return;
    }
    final nowClock = dayFrameHhmm(eta);
    if (nowClock.isEmpty) return;
    // Only a finish that moved LATER is news (R1.4: early days lengthen what is
    // there in silence).
    final gap = _hhmmGapSeconds(nowClock, session.plannedEndHhmm);
    if (gap <= session.retimeToleranceSeconds) {
      _finishMovedLine = null;
      _finishMovedNoticedAt = null;
      return;
    }
    final last = _finishMovedNoticedAt;
    if (last != null && (gap - last).abs() <= session.retimeToleranceSeconds) {
      return; // said once; the clock line on screen keeps moving
    }
    _finishMovedNoticedAt = gap;
    _finishMovedLine = '${_cap(session.finishName)} now looks like $nowClock, '
        'not ${session.plannedEndHhmm}.';
  }

  static String _cap(String s) =>
      s.isEmpty ? s : '${s[0].toUpperCase()}${s.substring(1)}';
  bool get isPaused => _pausedAt != null;
  int get pauseCount => _pauseCount;
  int get longestPauseSeconds => max(_longestPauseSeconds, _openPauseSeconds);

  /// The preset: the speed this day was planned at (from the session).
  double get presetPaceMps =>
      (_session?.walkingPaceKmh ?? kServerPaceKmh) / 3.6;

  /// The person's own pace, once enough walking has been measured; else null.
  double? get learnedPaceMps => _movingSeconds >= kPaceLearnAfterSeconds
      ? _movingMeters / _movingSeconds
      : null;
  double get paceMps => learnedPaceMps ?? presetPaceMps;

  /// The learned pace as the wire's multiplier on the server's base speed
  /// (>= 1.0 slows; the planner does not plan faster than its base).
  double? get observedPace {
    final learned = learnedPaceMps;
    if (learned == null || learned <= 0) return null;
    return max(1.0, (kServerPaceKmh / 3.6) / learned);
  }

  /// Wall seconds spent listening per stated second, once a whole piece has
  /// been heard (>= 60 s stated); 1.0 until then. Clamped to the wire's range.
  double get listeningRate => _statedListened >= 60
      ? (_wallListened / _statedListened).clamp(0.5, 3.0)
      : 1.0;

  /// What the phone reported about a clock gap (S5.10's seam), for the screen.
  List<String> get clockNotices => List.unmodifiable(_clockNotices);

  /// Start a tour with the given stops. Begins GPS tracking and geofence
  /// monitoring.
  Future<bool> startTour(List<ItineraryStop> stops) async {
    if (stops.isEmpty) return false;

    _stops = List.unmodifiable(stops);
    _planned = _stops;
    _currentStopIndex = 0;
    _pendingStopIndex = null;
    _state = TourState.active;
    _startedAt = _now();
    _tourClockStartedAt = null;
    _firstFix = null;
    _finishMovedLine = null;
    _finishMovedNoticedAt = null;
    _pausedSeconds = 0;
    _pausedAt = null;
    _pauseCount = 0;
    _longestPauseSeconds = 0;
    _movingMeters = 0;
    _movingSeconds = 0;
    _lastFix = null;
    _statedListened = 0;
    _wallListened = 0;
    _statedKeys.clear();
    _playingSince = null;
    _playingKey = null;
    _played.clear();
    _opened.clear();
    _lastSkippedPoiId = null;
    _wrapUpRequested = false;
    _clockNotices.clear();
    _closeLine = null;
    _threadLine = null;
    _closesPlayed.clear();
    _sentenceEndTimer?.cancel();
    _sentenceEndTimer = null;
    _closePending = null;
    _queuedLine = null;
    _queuedLineAudioUrl = null;
    _queuedIsQuestion = false;
    _questionSpoken = false;
    _spoken.clear();
    _stillSince = null;
    _pieceEndedNaturally = false;
    _transcriptOpen = false;
    _pausesAtStop.clear();
    _voiceRestored = false;
    _screenOnlyAnnounced = false;

    // Start GPS tracking
    final started = await _locationService.startTracking();
    if (!started) {
      _state = TourState.idle;
      notifyListeners();
      return false;
    }

    // Listen to position updates
    _locationListener = () => _onPositionUpdate();
    _locationService.addListener(_locationListener!);

    // Listen to audio completion
    _audioListener = () => _onAudioStateChanged();
    _audioService.addListener(_audioListener!);

    notifyListeners();
    return true;
  }

  /// Stop the tour, cancel tracking.
  void stopTour() {
    if (_locationListener != null) {
      _locationService.removeListener(_locationListener!);
      _locationListener = null;
    }
    if (_audioListener != null) {
      _audioService.removeListener(_audioListener!);
      _audioListener = null;
    }
    _locationService.stopTracking();
    _audioService.stop();
    _sentenceEndTimer?.cancel();
    _sentenceEndTimer = null;
    _closePending = null;
    _stops = [];
    _planned = [];
    _currentStopIndex = -1;
    _pendingStopIndex = null;
    _state = TourState.idle;
    _distanceToNext = null;
    _startedAt = null;
    _tourClockStartedAt = null;
    _pausedAt = null;
    notifyListeners();
  }

  // ---- S5.10: pause as information (design §4.3) --------------------------

  /// Pause the tour: the audio through the provider door, and the TOUR clock
  /// suspended — the wall keeps spending. Repeated pauses are counted for the
  /// screen-only switch (S5.11, W5.2 R4); they are never lateness.
  void pauseTour() {
    if (_startedAt == null || _pausedAt != null) return;
    _pausedAt = _now();
    _pauseCount++;
    final key = _audioKeyOf(currentStop);
    if (key != null) _pausesAtStop[key] = (_pausesAtStop[key] ?? 0) + 1;
    // A piece cut off mid-way is not a seam (R3); a conversation after a
    // piece ended on its own leaves that seam where it was.
    _pausedMidPiece = _audioService.isPlaying;
    if (_pausedMidPiece) _pieceEndedNaturally = false;
    _audioService.pause();
    _maybeAnnounceScreenOnly();
    notifyListeners();
  }

  void resumeTour() {
    final at = _pausedAt;
    if (at == null) return;
    final length = _now().difference(at).inSeconds;
    _pausedSeconds += length;
    if (length > _longestPauseSeconds) _longestPauseSeconds = length;
    _pausedAt = null;
    if (_pausedMidPiece) _audioService.resume(); // the piece comes back untouched
    _pausedMidPiece = false;
    _maybeAnnounceScreenOnly();
    _checkFinishMoved();
    // Unpause, reconciled (R3): a natural moment ONLY when play resumes at a
    // stop with the piece not yet started — one sentence BEFORE the piece.
    _drainSpeech();
    notifyListeners();
  }

  /// The transcript is open on the screen (Paulo): no voice while reading.
  void setTranscriptOpen(bool open) {
    _transcriptOpen = open;
    if (!open) _drainSpeech();
    notifyListeners();
  }

  /// A clock tick from the screen (or a timer): standing still is measured by
  /// time passing without a fix moving, and the geolocator's distance filter
  /// sends no fix while nobody moves — so the moment must be re-checked here.
  void tick() {
    if (_startedAt == null) return;
    _checkFinishMoved();
    _drainSpeech();
  }

  // ---- S5.11: THE QUEUE and the natural moment ---------------------------

  /// What the session has said aloud, in order (for the screen's own record
  /// and for tests). Every line here was on the screen first.
  List<String> get spoken => List.unmodifiable(_spoken);
  String? get queuedLine => _queuedLine;

  /// R4 — the session's own voice goes to the screen for the rest of the day
  /// (the NARRATION is never muted, and the question is still said once):
  /// couple / family / second-language after the SECOND pause of the day or one
  /// pause longer than ten minutes (family: five); solo, take-it-easy, no party:
  /// no day-long switch on a count. Undone by one touch ([restoreVoice]).
  bool get screenOnly {
    if (_voiceRestored) return false;
    final party = _session?.party;
    if (party == 'couple' || party == 'family') {
      final long = party == 'family'
          ? kLongPauseFamilySeconds
          : kLongPauseCoupleSeconds;
      return _pauseCount >= 2 || longestPauseSeconds > long;
    }
    return false;
  }

  /// Solo / take-it-easy: two pauses inside ONE stop silence THAT stop only
  /// (Rosemary, Greta).
  bool get currentStopSilenced {
    final key = _audioKeyOf(currentStop);
    return key != null && (_pausesAtStop[key] ?? 0) >= 2;
  }

  /// One touch on the speaker: the voice comes back for the day.
  void restoreVoice() {
    _voiceRestored = true;
    notifyListeners();
  }

  void _maybeAnnounceScreenOnly() {
    if (!screenOnly || _screenOnlyAnnounced) return;
    _screenOnlyAnnounced = true;
    // On the screen as its own caption while the switch is on (the page reads
    // [screenOnly]); it never replaces the plan's line. Said once, in one plain
    // sentence, at the next natural moment — and it
    // may displace a waiting fabric line, never the question.
    if (!_queuedIsQuestion) {
      _queuedLine = kScreenOnlyLine;
      _queuedIsQuestion = false;
    }
  }

  /// R3 — the observable proxy for "a natural moment": at a STOP (inside its
  /// circle, or the last stop's), a SEAM in the audio (nothing playing; the
  /// piece ended on its own OR the first piece has not begun), standing still
  /// for the settling period, not paused, transcript closed. NEVER on a walking
  /// leg, never mid-piece, never on stillness alone.
  bool get isNaturalMoment {
    if (_startedAt == null || _pausedAt != null || _transcriptOpen) return false;
    if (_audioService.isPlaying) return false;
    final fix = _lastFix;
    if (fix == null) return false;
    final still = _stillSince;
    if (still == null ||
        _now().difference(still).inSeconds < kSettleSeconds) {
      return false;
    }
    final at = _stopUnderfoot(fix);
    if (at == null) return false;
    final key = _audioKeyOf(at);
    final notBegun = key != null && !_played.contains(key);
    return _pieceEndedNaturally || notBegun;
  }

  ItineraryStop? _stopUnderfoot(_Fix fix) {
    if (_stops.isEmpty || _currentStopIndex < 0) return null;
    for (final i in [_currentStopIndex, _currentStopIndex - 1]) {
      if (i < 0 || i >= _stops.length) continue;
      final stop = _stops[i];
      if (haversineDistance(fix.lat, fix.lng, stop.lat, stop.lng) <=
          kStopCircleM) {
        return stop;
      }
    }
    return null;
  }

  /// Say the waiting line if this is a natural moment. The QUESTION is said
  /// once even under screen-only (Théo, Camille: "a question I cannot hear is a
  /// decision made for me"); a fabric line under screen-only, or at a stop the
  /// person has silenced, stays on the screen.
  void _drainSpeech() {
    final line = _queuedLine;
    if (line == null || !isNaturalMoment) return;
    // Under screen-only only the question and the switch's own one sentence
    // are said (R4: "said once in one plain sentence").
    final isSwitchLine = line == kScreenOnlyLine;
    if (!_queuedIsQuestion &&
        !isSwitchLine &&
        (screenOnly || currentStopSilenced)) {
      return;
    }
    if (_queuedIsQuestion && _questionSpoken) {
      _queuedLine = null;
      return;
    }
    _queuedLine = null;
    if (_queuedIsQuestion) _questionSpoken = true;
    _queuedIsQuestion = false;
    // S6.8 (owner ruling: the tour's own voice): a line with a pre-voiced file
    // plays through the narrator's door; only file-less lines use the plain
    // voice. Same seam, same etiquette either way.
    final url = _queuedLineAudioUrl;
    _queuedLineAudioUrl = null;
    if (url != null) {
      _audioService.play('session-line', url, isDeeperDive: true);
    } else {
      _spoken.add(line);
      _audioService.speak(line);
    }
    notifyListeners();
  }

  void _queue(String line, {required bool isQuestion, String? audioUrl}) {
    if (_queuedIsQuestion && !isQuestion) return; // the question outranks
    _queuedLine = line;
    _queuedLineAudioUrl = audioUrl;
    _queuedIsQuestion = isQuestion;
    if (isQuestion) _questionSpoken = false;
    _drainSpeech();
  }

  /// The person read this stop's transcript on the screen (Paulo): a stop
  /// opened is not a stop skipped, even if its audio never played.
  void noteTranscriptOpened(ItineraryStop stop) {
    final key = _audioKeyOf(stop);
    if (key != null) _opened.add(key);
  }

  /// [Head back now] — the one control the person has (W5.2 R1.1/R4): the
  /// measured divergence names the current stop as the wrap-up point.
  void requestWrapUp() {
    _wrapUpRequested = true;
    notifyListeners();
  }

  // ---- S5.10: THE ONE re-timing expression --------------------------------

  /// THE phone's ONE re-timing expression (S5.10's seam; design §4.1): seconds
  /// from NOW to each remaining stop's arrival and departure — from the last
  /// fix, at the learned pace with the server's own straight-line correction,
  /// spending at each stop the longer of its planned visit and its narration
  /// at the learned listening rate (the server's `stop_seconds` rule). Nothing
  /// else on the phone spells a clock; the server's `stop_clocks` is the other
  /// side of the seam, and [holdSession] compares the two.
  List<StopEta> retimeRemaining() {
    if (_stops.isEmpty || _currentStopIndex < 0) return const [];
    final from = _currentStopIndex.clamp(0, _stops.length - 1);
    final fix = _lastFix;
    double? lat = fix?.lat;
    double? lng = fix?.lng;
    if (fix == null && from > 0) {
      lat = _stops[from - 1].lat;
      lng = _stops[from - 1].lng;
    }
    var cursor = 0;
    final out = <StopEta>[];
    for (var i = from; i < _stops.length; i++) {
      final stop = _stops[i];
      var walk = 0;
      if (lat != null && lng != null) {
        final d = haversineDistance(lat, lng, stop.lat, stop.lng);
        final atTheStop = i == from && fix != null && d <= kStopCircleM;
        walk = atTheStop ? 0 : _walkSeconds(d);
      }
      final arrival = cursor + walk;
      final says = ((stop.audioDurationSec ?? 0) * listeningRate).round();
      final departure = arrival + max<int>(stop.plannedVisitSeconds, says);
      out.add(StopEta(stop, arrival, departure));
      cursor = departure;
      lat = stop.lat;
      lng = stop.lng;
    }
    return out;
  }

  /// Seconds from NOW to the day's finish — a VIEW of [retimeRemaining] (the
  /// last departure plus the walk to the finish at the learned pace), never a
  /// second expression. The finish is where the session says the day ends; with
  /// no finish held (an open walk) the day ends at its last stop's departure.
  /// Null before anything can be re-timed.
  int? get finishEtaSeconds {
    final session = _session;
    final etas = retimeRemaining();
    final double lat;
    final double lng;
    var cursor = 0;
    if (etas.isNotEmpty) {
      cursor = etas.last.secondsToDeparture;
      lat = etas.last.stop.lat;
      lng = etas.last.stop.lng;
    } else if (_lastFix != null) {
      lat = _lastFix!.lat;
      lng = _lastFix!.lng;
    } else {
      return null;
    }
    final fLat = session?.finishLat;
    final fLng = session?.finishLng;
    if (fLat == null || fLng == null) return cursor;
    return cursor + _walkSeconds(haversineDistance(lat, lng, fLat, fLng));
  }

  /// THE walk arithmetic, spelled once: straight-line metres with the server's
  /// own correction, at the pace in force.
  int _walkSeconds(double meters) =>
      (meters * kHaversineCorrection / paceMps).round();

  /// A phone clock in the DAY's frame — the frame the server's clocks live in:
  /// the day's start plus the WALL elapsed plus [secondsFromNow]. "" when the
  /// held session has no day start.
  String dayFrameHhmm(int secondsFromNow) =>
      _frameHhmm(wallElapsedSeconds + secondsFromNow);

  String _frameHhmm(int secondsFromDayStart) {
    final start = _session?.dayStartHhmm ?? '';
    if (start.length != 5) return '';
    final h = int.tryParse(start.substring(0, 2));
    final m = int.tryParse(start.substring(3, 5));
    if (h == null || m == null) return '';
    final total = ((h * 60 + m) * 60 + secondsFromDayStart) % 86400;
    final hh = (total ~/ 3600).toString().padLeft(2, '0');
    final mm = ((total % 3600) ~/ 60).toString().padLeft(2, '0');
    return '$hh:$mm';
  }

  /// The phone's own clock for the stop it is heading to, in the day's frame
  /// — the observation it sends with a replan (the server compares, reports,
  /// never adopts). Null when nothing can be re-timed yet.
  String? get phoneNextStopHhmm {
    final etas = retimeRemaining();
    if (etas.isEmpty) return null;
    final clock = dayFrameHhmm(etas.first.secondsToArrival);
    return clock.isEmpty ? null : clock;
  }

  static int _hhmmGapSeconds(String a, String b) {
    final am = int.parse(a.substring(0, 2)) * 60 + int.parse(a.substring(3, 5));
    final bm = int.parse(b.substring(0, 2)) * 60 + int.parse(b.substring(3, 5));
    var diff = am - bm;
    if (diff > 12 * 60) diff -= 24 * 60;
    if (diff < -12 * 60) diff += 24 * 60;
    return diff * 60;
  }

  String? _serverClockFor(String poiId) {
    final session = _session;
    if (session == null) return null;
    for (final stop in session.stops) {
      if (stop.poiId == poiId && stop.startTime.length == 5) {
        return stop.startTime;
      }
    }
    return null;
  }

  /// The phone's MEASURED divergence, as facts (design §4.6) — what
  /// [matchContingency] takes. Lateness and earliness on the TOUR clock (§4.3:
  /// a pause is never lateness); minutes left on the WALL clock (the platform
  /// clock keeps moving through a pause and the number on screen moves with it
  /// — Marcus, W5.2 R4); a skip only for a stop neither played nor opened; a
  /// protected promise at risk when its tour-frame arrival runs past the plan
  /// by more than the tolerance.
  Divergence measure() {
    // A walk that is over has nothing left to diverge from (W5.13: a finished
    // day still matched a promise entry when poked).
    if (!isActive) return const Divergence();
    final etas = retimeRemaining();
    final session = _session;
    int? late;
    int? early;
    int? left;
    String? atRisk;
    if (session != null && etas.isNotEmpty && session.dayStartHhmm.length == 5) {
      final next = etas.first;
      final planned = _serverClockFor(next.stop.poiId);
      if (planned != null) {
        final gap = _hhmmGapSeconds(
          _frameHhmm(tourElapsedSeconds + next.secondsToArrival),
          planned,
        );
        if (gap > 0) late = gap ~/ 60;
        if (gap < 0) early = (-gap) ~/ 60;
      }
      // Minutes left on the WALL clock: to the day's planned end (an open day's
      // bands count down to it — R1.3), else to the finish promise's clock.
      var end = session.plannedEndHhmm.length == 5 ? session.plannedEndHhmm : '';
      if (end.isEmpty) {
        for (final promise in session.promises) {
          if (promise.kind == 'finish' && promise.arrivesHhmm.length == 5) {
            end = promise.arrivesHhmm;
            break;
          }
        }
      }
      if (end.isNotEmpty) left = -_hhmmGapSeconds(dayFrameHhmm(0), end) ~/ 60;
      for (final eta in etas) {
        for (final promise in session.promises) {
          if (!promise.protected ||
              promise.promiseId != eta.stop.poiId ||
              promise.arrivesHhmm.length != 5) {
            continue;
          }
          final gap = _hhmmGapSeconds(
            _frameHhmm(tourElapsedSeconds + eta.secondsToArrival),
            promise.arrivesHhmm,
          );
          if (gap > session.retimeToleranceSeconds) atRisk = promise.promiseId;
        }
        if (atRisk != null) break;
      }
    }
    // The stop the person is at or has just left: underfoot if inside a circle,
    // else the last stop passed (a leg is "from" the stop behind it).
    final fix = _lastFix;
    final underfoot = fix == null ? null : _stopUnderfoot(fix);
    final behind = _currentStopIndex > 0 && _currentStopIndex - 1 < _stops.length
        ? _stops[_currentStopIndex - 1]
        : null;
    return Divergence(
      minutesLate: late,
      minutesEarly: early,
      minutesLeft: left,
      skippedStopId: _lastSkippedPoiId,
      wrapUpFromStopId:
          _wrapUpRequested && isActive ? currentStop?.poiId : null,
      atRiskStopId: atRisk,
      atStopId: (underfoot ?? behind ?? currentStop)?.poiId,
    );
  }

  /// THE SESSION CLOCK SEAM, phone half (S5.10; design §4.6): on every version
  /// the server hands over — the reconnect path — the phone's own re-timing is
  /// COMPARED with the server's clock for the next stop, in the day's frame. A
  /// gap beyond the session's tolerance is REPORTED — a line for the screen —
  /// and never corrected: nothing here assigns into the phone's clocks, its
  /// learned rates, or the server's plan. The reader who is tempted to "fix"
  /// the phone from the server here is looking at the silent-divergence bug
  /// §4.6 exists to prevent.
  void _compareClockWithServer(SessionPlan session) {
    if (_startedAt == null || _lastFix == null) return; // nothing measured yet
    final etas = retimeRemaining();
    if (etas.isEmpty) return;
    final next = etas.first;
    final phone = dayFrameHhmm(next.secondsToArrival);
    final server = _serverClockFor(next.stop.poiId);
    if (phone.isEmpty || server == null) return;
    final gap = _hhmmGapSeconds(phone, server);
    if (gap.abs() <= session.retimeToleranceSeconds) return;
    final minutes = (gap.abs() / 60).round();
    final direction = gap > 0 ? 'later' : 'earlier';
    _clockNotices.add(
      'Your phone reckons ${next.stop.poiName} about $minutes minutes '
      '$direction than the plan says. The phone keeps its own clock; the gap '
      'is shown, not hidden.',
    );
  }

  /// Hold the session the server sent (design §4.7: the phone carries the
  /// current plan and its contingency set so it can act offline, only from
  /// what it already holds). Replaces the held session on every new version.
  void holdSession(SessionPlan session) {
    _session = session;
    _selected = null;
    _pendingQuestion = null;
    _screenText = null;
    _compareClockWithServer(session);
    // THE PROMISE TIER ON THE LIVE PATH (W5.14): a live replan that could not
    // keep everything the person asked for within the clock carries the ONE
    // question as an entry of kind "live" — applied at once (its default in
    // force, the two big buttons on the screen), never re-matched later.
    for (final entry in session.contingencies) {
      if (entry.kind == 'live') {
        applyContingency(entry.contingencyId);
        break;
      }
    }
    notifyListeners();
  }

  /// Match the phone's MEASURED divergence against the held contingency set and
  /// return the FIRST entry, in server order, whose trigger fits — a band
  /// lookup or an id equality, nothing else. Null when nothing matches: the
  /// phone then carries on and re-times (design §4.6's arithmetic fallback).
  SessionContingency? matchContingency(Divergence divergence) {
    final session = _session;
    if (session == null) return null;
    for (final entry in session.contingencies) {
      if (_triggerMatches(entry, divergence)) return entry;
    }
    return null;
  }

  static bool _inBand(List<int>? band, int? value) =>
      band != null && value != null && value >= band[0] && value < band[1];

  static bool _fromHere(SessionContingency entry, Divergence d) =>
      d.atStopId == null ||
      entry.triggerStopId == null ||
      entry.triggerStopId == d.atStopId;

  static bool _triggerMatches(SessionContingency entry, Divergence d) {
    switch (entry.kind) {
      case 'running_late':
        return _fromHere(entry, d) && _inBand(entry.bandMinutes, d.minutesLate);
      case 'running_early':
        return _fromHere(entry, d) && _inBand(entry.bandMinutes, d.minutesEarly);
      case 'minutes_left':
        return _fromHere(entry, d) && _inBand(entry.bandMinutes, d.minutesLeft);
      case 'stop_skipped':
        return d.skippedStopId != null && entry.triggerStopId == d.skippedStopId;
      case 'wrap_up_from':
        return d.wrapUpFromStopId != null &&
            entry.triggerStopId == d.wrapUpFromStopId;
      case 'promise_at_risk':
        return d.atRiskStopId != null && entry.triggerStopId == d.atRiskStopId;
      default:
        return false;
    }
  }

  /// THE ONE METHOD THAT CHANGES THE CURRENT PLAN — and its only decision input
  /// is a server contingency id (design §4.6: the phone SELECTS, it never
  /// DECIDES). Re-orders the remaining stops to the entry's stops (a subset of
  /// the planned day, in the server's order), puts the entry's screen text on
  /// screen, and surfaces its question if it carries one; the answer is applied
  /// through [answerQuestion]. Returns false when the id is not in the held set.
  bool applyContingency(String contingencyId) {
    final session = _session;
    if (session == null) return false;
    SessionContingency? entry;
    for (final held in session.contingencies) {
      if (held.contingencyId == contingencyId) {
        entry = held;
        break;
      }
    }
    if (entry == null) return false;
    _selected = entry;
    _screenText = entry.screenText;
    _pendingQuestion = entry.question;
    // §4.2: a fabric change is absorbed SILENTLY — on the screen, never said.
    // The ONE question is the one line the session speaks (R2.5): queued to a
    // natural moment, on the screen already as two big buttons.
    final question = entry.question;
    if (question != null) {
      _queue(question, isQuestion: true);
    } else if (_queuedIsQuestion == false) {
      _queuedLine = null; // a superseded fabric line expires unsaid (R3)
    }
    if (entry.kind == 'wrap_up_from') {
      _wrapUp(entry);
    }
    if (entry.question == null) {
      _reorderRemaining(entry, entry.stopIds);
    } else if (entry.defaultArm == 'shorten') {
      // The safe default is already in force until answered (§4.2).
      _reorderRemaining(
          entry,
          entry.alternateStopIds.isNotEmpty
              ? entry.alternateStopIds
              : entry.stopIds);
    } else {
      _reorderRemaining(entry, entry.stopIds);
    }
    notifyListeners();
    return true;
  }

  /// Apply the person's answer to the ONE question of the selected entry:
  /// `keep` = the entry's stops (the protected thing kept), `shorten` = its
  /// alternate. Silence applies the entry's own default (§4.2).
  void answerQuestion(String arm) {
    final entry = _selected;
    if (entry == null || entry.question == null) return;
    final chosen = arm == 'shorten' && entry.alternateStopIds.isNotEmpty
        ? entry.alternateStopIds
        : entry.stopIds;
    _pendingQuestion = null;
    if (_queuedIsQuestion) {
      _queuedLine = null; // answered on the screen: nothing left to say
      _queuedIsQuestion = false;
    }
    _reorderRemaining(entry, chosen);
    notifyListeners();
  }

  // ---- S6.4: the tap is the seam -------------------------------------------

  /// Seconds from [position] to the END OF THE CURRENT SENTENCE of [stop]'s
  /// piece — arithmetic over the stop's own narration (its word count per
  /// sentence against the file's length), capped at [kSentenceEndCapSeconds].
  /// Zero when the stop carries no narration or no length, or the position is
  /// past the last boundary. THE phone's one way of finding a sentence end
  /// (W6.2 R8: "the current sentence finishes — never a cut word").
  @visibleForTesting
  static double secondsToSentenceEnd(ItineraryStop stop, Duration position) {
    final text = stop.narration;
    final length = stop.audioDurationSec;
    if (text == null || text.trim().isEmpty || length == null || length <= 0) {
      return 0;
    }
    final sentences = text
        .split(RegExp(r'(?<=[.!?])\s+'))
        .where((s) => s.trim().isNotEmpty)
        .toList();
    final words = sentences.map((s) => s.trim().split(RegExp(r'\s+')).length).toList();
    final total = words.fold<int>(0, (a, b) => a + b);
    if (total == 0) return 0;
    final at = position.inMilliseconds / 1000.0;
    var cumulative = 0;
    for (final w in words) {
      cumulative += w;
      final boundary = length * cumulative / total;
      if (boundary > at) {
        return min(boundary - at, kSentenceEndCapSeconds.toDouble());
      }
    }
    return 0;
  }

  /// [Head back now] applied (the matched wrap-up entry): if THIS stop's piece
  /// is playing, let its sentence end, then cut it and play the stop's close;
  /// if nothing is playing, the DAY's close (the last planned stop's) goes on
  /// the screen at once and is said at the next natural moment. The way home
  /// is the entry's screen line and is never spoken. Nothing else follows.
  void _wrapUp(SessionContingency entry) {
    final stop = currentStop;
    // S6.6/S6.8: the FULL TELLING is a stretch of its own (§7.4.5 — every
    // prefix ends decently): a tap mid-full finishes ITS sentence by ITS own
    // arithmetic and plays ITS close. The playing KEY names its stop — the
    // tour pointer may already sit a stop ahead (the tight completing advances
    // it while the person lingers where they stand).
    ItineraryStop? fullStop;
    if (_audioService.isPlaying) {
      final playingKey = _audioService.currentBeatId;
      for (final s in _planned) {
        final k = _audioKeyOf(s);
        if (k != null && playingKey == '$k-full') {
          fullStop = s;
          break;
        }
      }
    }
    if (fullStop != null && (fullStop.fullCloseText ?? '').isNotEmpty) {
      _closeLine = fullStop.fullCloseText;
      _closePending = fullStop;
      _closePendingIsFull = true;
      final wait = secondsToSentenceEnd(
        _fullArithmeticStop(fullStop),
        _audioService.position,
      );
      _sentenceEndTimer?.cancel();
      if (wait <= 0) {
        finishSentenceNow();
      } else {
        _sentenceEndTimer = Timer(
          Duration(milliseconds: (wait * 1000).round()),
          finishSentenceNow,
        );
      }
      return;
    }
    final playingThis = stop != null &&
        _audioService.isPlaying &&
        _audioService.currentBeatId == _audioKeyOf(stop) &&
        (stop.closeText ?? '').isNotEmpty;
    if (playingThis) {
      _closeLine = stop.closeText;
      _closePending = stop;
      final wait = secondsToSentenceEnd(stop, _audioService.position);
      _sentenceEndTimer?.cancel();
      if (wait <= 0) {
        finishSentenceNow();
      } else {
        _sentenceEndTimer = Timer(
          Duration(milliseconds: (wait * 1000).round()),
          finishSentenceNow,
        );
      }
      return;
    }
    // No piece playing: the day's close — the last planned stop's — on screen
    // now; said at the next natural moment (never on a leg, §4.4.1), through
    // the queue like every session line. A stale queued fabric line expires.
    final last = _planned.isNotEmpty ? _planned.last : stop;
    final dayClose = last?.closeText ?? stop?.closeText;
    if (dayClose == null || dayClose.isEmpty) return;
    _closeLine = dayClose;
    if (!_queuedIsQuestion) {
      _queuedLine = dayClose;
      // S6.8: the day's close in the narrator's own voice when the wire
      // carries its file.
      _queuedLineAudioUrl =
          (last?.closeText == dayClose ? last?.closeAudioUrl : stop?.closeAudioUrl);
      _queuedIsQuestion = false;
    }
    _closesPlayed.add(dayClose);
    _drainSpeech();
  }

  /// The sentence end has come (or the cap): cut the piece and play the close.
  /// Public so a test — and the timer — reach the same door.
  @visibleForTesting
  void finishSentenceNow() {
    _sentenceEndTimer?.cancel();
    _sentenceEndTimer = null;
    final stop = _closePending;
    final wasFull = _closePendingIsFull;
    _closePending = null;
    _closePendingIsFull = false;
    if (stop == null) return;
    final key = _audioKeyOf(stop);
    final playingKey = wasFull && key != null ? '$key-full' : key;
    if (_audioService.isPlaying && _audioService.currentBeatId == playingKey) {
      _audioService.stop();
    }
    _pieceEndedNaturally = false; // a cut is not a seam for anything else (R3)
    if (wasFull) {
      _playFullClose(stop);
    } else {
      _playClose(stop);
    }
  }

  /// S6.6/S6.8: the full telling's own close — its file through the narrator's
  /// door when voiced, else the one silent door; on the screen either way.
  void _playFullClose(ItineraryStop stop) {
    final text = stop.fullCloseText;
    if (text == null || text.isEmpty) return;
    _closeLine = text;
    _closesPlayed.add(text);
    final key = _audioKeyOf(stop);
    final url = stop.fullCloseAudioUrl;
    if (url != null && key != null) {
      _audioService.play('$key-full-close', url, isDeeperDive: true);
    } else {
      _spoken.add(text);
      _audioService.speak(text);
    }
    notifyListeners();
  }

  /// The close of [stop]: its pre-voiced file through the narrator's own door
  /// when the wire carries one (S6.8 — keyed `<stop>-close`, played as a deeper
  /// dive so completion never auto-advances the tour), else said through the
  /// one silent door; on the screen already either way (§4.4.2).
  /// The full telling's sentence arithmetic rides the SAME static function as
  /// the tight's, over the full's own text and length (S6.6/S6.8).
  ItineraryStop _fullArithmeticStop(ItineraryStop stop) => ItineraryStop(
        sortOrder: stop.sortOrder,
        poiId: stop.poiId,
        poiName: stop.poiName,
        lat: stop.lat,
        lng: stop.lng,
        lensName: stop.lensName,
        lensDisplay: stop.lensDisplay,
        durationMin: stop.durationMin,
        importanceTier: stop.importanceTier,
        startTime: stop.startTime,
        narration: stop.fullNarration,
        audioDurationSec: _fullPieceDurationSec?.toDouble(),
      );

  void _playClose(ItineraryStop stop) {
    final text = stop.closeText;
    if (text == null || text.isEmpty) return;
    _closeLine = text;
    _closesPlayed.add(text);
    final key = _audioKeyOf(stop);
    final url = stop.closeAudioUrl;
    if (url != null && key != null) {
      _audioService.play('$key-close', url, isDeeperDive: true);
    } else {
      _spoken.add(text);
      _audioService.speak(text);
    }
    notifyListeners();
  }

  /// The day from the entry's trigger onward becomes the entry's ordered
  /// subset of the planned day. An entry's stops are the day AFTER its trigger
  /// stop — a late/early band "from stop k" lists the stops after k (k stays);
  /// a skip "of k" lists the stops after k (k goes); a promise-at-risk lists
  /// the day from the stop before the promise. Everything before that point is
  /// kept as it stands. A stop id the phone does not hold is skipped, never
  /// invented (§4.7: it cannot add narration it does not hold).
  void _reorderRemaining(SessionContingency entry, List<String> stopIdsInOrder) {
    if (_stops.isEmpty) return;
    final triggerId = entry.triggerStopId;
    var keepCount = _currentStopIndex < 0 ? 0 : _currentStopIndex;
    if (triggerId != null) {
      final at = _stops.indexWhere(
          (s) => s.poiId == triggerId || s.stopId == triggerId);
      if (at >= 0) {
        // skip "of k": k goes (exclusive). promise-at-risk about j: the
        // server's answer is FROM the stop before j and its stops start after
        // that stop, so everything before j stays. A band "from k": k stays.
        keepCount = entry.kind == 'stop_skipped' || entry.kind == 'promise_at_risk'
            ? at
            : at + 1;
      }
    }
    final done = _stops.take(keepCount).toList();
    final byPoi = {for (final s in _planned) s.poiId: s};
    final byStop = {
      for (final s in _planned)
        if (s.stopId != null) s.stopId!: s
    };
    final remaining = <ItineraryStop>[];
    for (final id in stopIdsInOrder) {
      final stop = byStop[id] ?? byPoi[id];
      if (stop != null && !done.contains(stop) && !remaining.contains(stop)) {
        remaining.add(stop);
      }
    }
    _stops = List.unmodifiable([...done, ...remaining]);
    if (_currentStopIndex >= _stops.length) {
      _currentStopIndex = _stops.length - 1;
    }
    _threadForNewPair(entry, keepCount);
  }

  /// S6.5 (design §5.4; W6.2 R5, 11/11): when a reorder makes two stops
  /// consecutive that the plan never had consecutive, the writer's THREAD for
  /// that pair — authored at compose time, riding the arriving stop as
  /// `threadLines[predecessor name]` — goes on the screen for the whole leg
  /// and into the speech queue for the next standing seam (departure; the one
  /// lost on the move is waiting at the standstill). The pair the plan already
  /// had keeps its thread inside the arriving stop's own narration. No line
  /// for the pair means silence — none rather than glue. A wrap-up threads
  /// nothing: the close owns that seam (R8), and the question outranks the
  /// thread in the queue (R2.5).
  void _threadForNewPair(SessionContingency entry, int keepCount) {
    _threadLine = null;
    if (entry.kind == 'wrap_up_from') return;
    if (keepCount <= 0 || keepCount >= _stops.length) return;
    final from = _stops[keepCount - 1];
    final next = _stops[keepCount];
    final plannedIdx = _planned.indexWhere((s) => s.poiId == from.poiId);
    final plannedNext = plannedIdx >= 0 && plannedIdx + 1 < _planned.length
        ? _planned[plannedIdx + 1]
        : null;
    if (plannedNext != null && plannedNext.poiId == next.poiId) return;
    final line = next.threadLines?[from.poiName];
    if (line == null || line.isEmpty) return;
    _threadLine = line;
    _queue(line, isQuestion: false, audioUrl: next.threadAudioUrls?[from.poiName]);
  }

  /// Prefetch the audio of every stop the held session may play (design §4.7:
  /// the alternates and their audio, prefetched during walks) through the
  /// EXISTING per-stop cache — the same key playback uses (`_audioKeyOf`).
  Future<int> prefetchSessionAudio() {
    final session = _session;
    if (session == null) return Future.value(0);
    return _audioService.prefetchAudio([
      for (final stop in session.stops)
        if (_audioKeyOf(stop) != null)
          BeatAudioInfo(beatId: _audioKeyOf(stop)!, audioUrl: stop.audioUrl),
    ]);
  }

  /// Skip to a specific stop index.
  void skipToStop(int index) {
    if (index < 0 || index >= _stops.length) return;
    // Skip = unplayed AND unopened (S5.10): a stop passed over with its piece
    // neither played nor read on the screen is the skip the set answers.
    for (var i = max(0, _currentStopIndex); i < index; i++) {
      final key = _audioKeyOf(_stops[i]);
      if (key != null && !_played.contains(key) && !_opened.contains(key)) {
        _lastSkippedPoiId = _stops[i].poiId;
      }
    }
    _currentStopIndex = index;
    _pendingStopIndex = null;
    _pieceEndedNaturally = false; // a skip is not a seam (R3)
    _playCurrentStop();
  }

  /// Accept the pending stop (user tapped the "now approaching" nudge).
  void acceptPendingStop() {
    if (_pendingStopIndex != null) {
      _currentStopIndex = _pendingStopIndex!;
      _pendingStopIndex = null;
      _playCurrentStop();
    }
  }

  /// Dismiss the pending nudge (user wants to keep listening).
  void dismissPending() {
    _pendingStopIndex = null;
    _state = TourState.active;
    notifyListeners();
  }

  void _onPositionUpdate() {
    final position = _locationService.lastPosition;
    if (position == null || _stops.isEmpty) return;

    final targetIndex = _currentStopIndex;
    if (targetIndex < 0 || targetIndex >= _stops.length) return;

    final target = _stops[targetIndex];
    final lat = (position.latitude as num).toDouble();
    final lng = (position.longitude as num).toDouble();
    final distance = haversineDistance(lat, lng, target.lat, target.lng);
    _distanceToNext = distance;
    final before = _lastFix;
    _firstFix ??= _Fix(lat, lng, _now());
    // The first step off the square starts the tour clock (R1.3); standing
    // where you started is not the tour yet.
    if (_tourClockStartedAt == null &&
        (haversineDistance(_firstFix!.lat, _firstFix!.lng, lat, lng) >
                kStopCircleM ||
            distance <= kStopCircleM)) {
      _startTourClockIfNeeded();
    }
    _learnPace(lat, lng, distance);
    // Standing still is measured from the last fix that MOVED (R3).
    if (before == null ||
        haversineDistance(before.lat, before.lng, lat, lng) > kStillRadiusM) {
      _stillSince = _now();
    }
    // Walking away from a stop is not a seam: on a leg nothing is said.
    if (_lastFix != null && _stopUnderfoot(_lastFix!) == null) {
      _pieceEndedNaturally = false;
    }
    _checkFinishMoved();
    _drainSpeech();

    // Check geofence: 10m trigger radius (NORTHSTAR spec)
    if (distance <= 10.0 && !_audioService.isPlaying) {
      _playCurrentStop();
    }

    // Check if user is approaching the NEXT stop while current is playing
    if (_audioService.isPlaying && _currentStopIndex + 1 < _stops.length) {
      final nextTarget = _stops[_currentStopIndex + 1];
      final distToNext = haversineDistance(
        (position.latitude as num).toDouble(),
        (position.longitude as num).toDouble(),
        nextTarget.lat,
        nextTarget.lng,
      );
      if (distToNext <= 10.0 && _pendingStopIndex == null) {
        _pendingStopIndex = _currentStopIndex + 1;
        _state = TourState.approaching;
        notifyListeners();
      }
    }

    notifyListeners();
  }

  void _onAudioStateChanged() {
    // KE6: a completed "keep exploring here" deep-dive clip NEVER advances the
    // tour — it is served off the tour's time budget. Only scheduled per-stop
    // tour audio drives auto-advance, so bail before either advance path.
    if (_audioService.isDeeperDive) return;
    _observeListening();
    // A piece that ended ON ITS OWN is a seam (R3) — the player says
    // completed, not merely "not playing": a pause is neither a seam nor an
    // ending (W5.13: it used to be read as one and the tour jumped a stop).
    if (_audioService.isPlaying) {
      _pieceEndedNaturally = false;
    } else if (_audioService.isCompleted) {
      _pieceEndedNaturally = true;
    }

    // When a piece COMPLETES, auto-advance if there's a pending stop
    if (_audioService.isCompleted &&
        _audioService.currentBeatId != null &&
        _state == TourState.approaching &&
        _pendingStopIndex != null) {
      _creditStated(currentStop);
      _currentStopIndex = _pendingStopIndex!;
      _pendingStopIndex = null;
      _state = TourState.active;
      _playCurrentStop();
    } else if (_audioService.isCompleted &&
        _audioService.currentBeatId == _audioKeyOf(currentStop)) {
      // Audio completed for current stop — advance index for next geofence
      _creditStated(currentStop);
      if (_currentStopIndex + 1 < _stops.length) {
        _currentStopIndex++;
        notifyListeners();
      } else {
        _state = TourState.completed;
        notifyListeners();
      }
    }
    _drainSpeech();
  }

  /// The audio cache/playback key for a stop: the per-stop ItineraryItem id
  /// (Step 1.4d) when present, falling back to the legacy per-beat id. Both the
  /// play call and the completion check below use this so they always agree.
  String? _audioKeyOf(ItineraryStop? stop) =>
      stop == null ? null : (stop.stopId ?? stop.beatId);

  void _playCurrentStop() {
    if (_currentStopIndex < 0 || _currentStopIndex >= _stops.length) return;
    final stop = _stops[_currentStopIndex];
    if (stop.audioUrl != null) {
      _startTourClockIfNeeded(); // the first play starts the tour clock (R1.3)
      _threadLine = null; // the leg is over: the next story begins (S6.5)
      _audioService.play(_audioKeyOf(stop)!, stop.audioUrl!);
      _state = TourState.active;
      notifyListeners();
    }
  }

  // ---- S5.10: the two learners -------------------------------------------

  /// Train the pace on this fix: moving minutes on WALKING LEGS only. A
  /// low-accuracy fix (> 25 m, the provider's own flag) breaks the chain and
  /// trains nothing; inside the current stop's circle or the last stop's the
  /// person is wandering, not walking; standing still and vehicle speeds are
  /// neither; a pause trains nothing.
  void _learnPace(double lat, double lng, double distanceToTarget) {
    final now = _now();
    if (_locationService.lowAccuracy) {
      _lastFix = null;
      return;
    }
    final last = _lastFix;
    _lastFix = _Fix(lat, lng, now);
    if (last == null || _pausedAt != null) return;
    final dt = now.difference(last.at).inMilliseconds / 1000.0;
    if (dt <= 0 || dt > 120) return;
    if (distanceToTarget <= kStopCircleM) return;
    if (_currentStopIndex > 0) {
      final prev = _stops[_currentStopIndex - 1];
      if (haversineDistance(lat, lng, prev.lat, prev.lng) <= kStopCircleM) {
        return;
      }
    }
    final meters = haversineDistance(last.lat, last.lng, lat, lng);
    final mps = meters / dt;
    if (mps < kMinWalkingMps || mps > kMaxWalkingMps) return;
    _movingMeters += meters;
    _movingSeconds += dt;
  }

  /// Wall time spent listening, per piece: playing starts a span, anything
  /// else (pause, completion, stop) closes it. A replay opens a new span
  /// against the same stated length.
  void _observeListening() {
    final now = _now();
    final key = _audioService.currentBeatId;
    if (_audioService.isPlaying) {
      if (_playingSince == null || _playingKey != key) {
        _closeListening(now);
        _playingSince = now;
        _playingKey = key;
        if (key != null) _played.add(key);
      }
    } else {
      _closeListening(now);
    }
  }

  void _closeListening(DateTime now) {
    final since = _playingSince;
    if (since == null) return;
    _wallListened += now.difference(since).inMilliseconds / 1000.0;
    _playingSince = null;
  }

  /// A piece completed for [stop]: its stated length counts ONCE (a replay is
  /// more wall time against the same stated seconds — that IS the rate).
  void _creditStated(ItineraryStop? stop) {
    if (stop == null) return;
    final key = _audioKeyOf(stop);
    final stated = stop.audioDurationSec;
    if (key == null || stated == null || stated <= 0) return;
    if (_statedKeys.add(key)) _statedListened += stated;
  }

  /// Haversine formula — returns distance in meters between two lat/lng points.
  @visibleForTesting
  static double haversineDistance(
    double lat1,
    double lon1,
    double lat2,
    double lon2,
  ) {
    const earthRadius = 6371000.0; // meters
    final dLat = _toRadians(lat2 - lat1);
    final dLon = _toRadians(lon2 - lon1);
    final a = sin(dLat / 2) * sin(dLat / 2) +
        cos(_toRadians(lat1)) *
            cos(_toRadians(lat2)) *
            sin(dLon / 2) *
            sin(dLon / 2);
    final c = 2 * atan2(sqrt(a), sqrt(1 - a));
    return earthRadius * c;
  }

  static double _toRadians(double degrees) => degrees * pi / 180.0;

  @override
  void dispose() {
    stopTour();
    super.dispose();
  }
}
