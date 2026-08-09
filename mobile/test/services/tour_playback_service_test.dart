import 'package:flutter_test/flutter_test.dart';
import 'package:ondoway/models/trip.dart';
import 'package:ondoway/services/tour_playback_service.dart';

import 'mocks/mock_audio_service.dart';
import 'mocks/mock_location_service.dart';

ItineraryStop _makeStop({
  required int sortOrder,
  required String beatId,
  required double lat,
  required double lng,
  String? audioUrl,
  String? stopId,
}) {
  return ItineraryStop(
    sortOrder: sortOrder,
    stopId: stopId,
    poiId: 'poi-$sortOrder',
    poiName: 'Stop $sortOrder',
    lat: lat,
    lng: lng,
    beatId: beatId,
    lensName: 'history',
    lensDisplay: 'History',
    durationMin: 5,
    importanceTier: sortOrder == 1 ? 5 : 3,
    startTime: '09:0$sortOrder',
    audioUrl: audioUrl,
  );
}

void main() {
  group('TourPlaybackService.haversineDistance', () {
    test('returns 0 for same point', () {
      final d = TourPlaybackService.haversineDistance(
        48.8584, 2.2945, 48.8584, 2.2945,
      );
      expect(d, closeTo(0.0, 0.01));
    });

    test('returns correct distance for known points', () {
      // Eiffel Tower to Arc de Triomphe: ~2.2 km
      final d = TourPlaybackService.haversineDistance(
        48.8584, 2.2945, // Eiffel Tower
        48.8738, 2.2950, // Arc de Triomphe (approx)
      );
      expect(d, closeTo(1713, 50)); // ~1.7 km
    });

    test('returns correct short distance (within geofence)', () {
      // Two points ~5 meters apart
      // 0.00005 degrees latitude ~ 5.5 meters
      final d = TourPlaybackService.haversineDistance(
        48.858400, 2.294500,
        48.858445, 2.294500,
      );
      expect(d, closeTo(5.0, 1.0));
    });

    test('handles antipodal points', () {
      // North pole to south pole: ~20,000 km
      final d = TourPlaybackService.haversineDistance(
        90.0, 0.0, -90.0, 0.0,
      );
      expect(d, closeTo(20015086, 1000));
    });
  });

  group('TourPlaybackService lifecycle', () {
    late MockLocationService locationService;
    late MockAudioService audioService;
    late TourPlaybackService service;

    setUp(() {
      locationService = MockLocationService();
      audioService = MockAudioService();
      service = TourPlaybackService(
        locationService: locationService,
        audioService: audioService,
      );
    });

    tearDown(() {
      service.dispose();
    });

    test('initial state is idle', () {
      expect(service.state, TourState.idle);
      expect(service.currentStopIndex, -1);
      expect(service.currentStop, isNull);
      expect(service.nextStop, isNull);
      expect(service.isActive, false);
      expect(service.hasPendingStop, false);
      expect(service.distanceToNext, isNull);
    });

    test('startTour with empty stops returns false', () async {
      final result = await service.startTour([]);
      expect(result, false);
      expect(service.state, TourState.idle);
    });

    test('startTour prepares the audio session before background tracking (AC1)',
        () async {
      final log = <String>[];
      audioService.callLog = log;
      locationService.callLog = log;
      final stops = [
        _makeStop(
          sortOrder: 1,
          beatId: 'b1',
          lat: 48.8584,
          lng: 2.2945,
          audioUrl: 'https://example.test/1.mp3',
        ),
      ];

      await service.startTour(stops);

      expect(log, ['prepare', 'track']);
      expect(locationService.lastBackground, isTrue);
      expect(audioService.prepareSessionCount, 1);
    });

    test('startTour with valid stops sets state to active', () async {
      locationService.trackingWillSucceed = true;
      final stops = [
        _makeStop(
          sortOrder: 1,
          beatId: 'beat-1',
          lat: 48.8584,
          lng: 2.2945,
          audioUrl: 'https://cdn.ondoway.com/beat-1.mp3',
        ),
        _makeStop(
          sortOrder: 2,
          beatId: 'beat-2',
          lat: 48.8606,
          lng: 2.3376,
          audioUrl: 'https://cdn.ondoway.com/beat-2.mp3',
        ),
      ];

      final result = await service.startTour(stops);

      expect(result, true);
      expect(service.state, TourState.active);
      expect(service.currentStopIndex, 0);
      expect(service.currentStop, isNotNull);
      expect(service.currentStop!.beatId, 'beat-1');
      expect(service.isActive, true);
      expect(locationService.isTracking, true);
    });

    test('startTour returns false when tracking fails', () async {
      locationService.trackingWillSucceed = false;
      final stops = [
        _makeStop(
          sortOrder: 1,
          beatId: 'beat-1',
          lat: 48.8584,
          lng: 2.2945,
          audioUrl: 'https://cdn.ondoway.com/beat-1.mp3',
        ),
      ];

      final result = await service.startTour(stops);

      expect(result, false);
      expect(service.state, TourState.idle);
    });

    test('stopTour resets all state', () async {
      locationService.trackingWillSucceed = true;
      final stops = [
        _makeStop(
          sortOrder: 1,
          beatId: 'beat-1',
          lat: 48.8584,
          lng: 2.2945,
          audioUrl: 'https://cdn.ondoway.com/beat-1.mp3',
        ),
      ];

      await service.startTour(stops);
      service.stopTour();

      expect(service.state, TourState.idle);
      expect(service.currentStopIndex, -1);
      expect(service.currentStop, isNull);
      expect(service.nextStop, isNull);
      expect(service.isActive, false);
      expect(service.pendingStopIndex, isNull);
      expect(service.distanceToNext, isNull);
      expect(locationService.isTracking, false);
    });

    test('skipToStop updates currentStopIndex', () async {
      locationService.trackingWillSucceed = true;
      final stops = [
        _makeStop(
          sortOrder: 1,
          beatId: 'beat-1',
          lat: 48.8584,
          lng: 2.2945,
          audioUrl: 'https://cdn.ondoway.com/beat-1.mp3',
        ),
        _makeStop(
          sortOrder: 2,
          beatId: 'beat-2',
          lat: 48.8606,
          lng: 2.3376,
          audioUrl: 'https://cdn.ondoway.com/beat-2.mp3',
        ),
        _makeStop(
          sortOrder: 3,
          beatId: 'beat-3',
          lat: 48.8530,
          lng: 2.3499,
          audioUrl: 'https://cdn.ondoway.com/beat-3.mp3',
        ),
      ];

      await service.startTour(stops);
      service.skipToStop(2);

      expect(service.currentStopIndex, 2);
      expect(service.currentStop!.beatId, 'beat-3');
      expect(audioService.currentBeatId, 'beat-3');
    });

    test('plays per-stop audio addressed by stopId (not beatId)', () async {
      // Step 1.4d: when a stop carries a per-stop ItineraryItem id, the playback
      // key is the stopId — the per-stop narration — not the legacy beatId.
      locationService.trackingWillSucceed = true;
      final stops = [
        _makeStop(
          sortOrder: 1,
          beatId: 'beat-1',
          stopId: 'stop-1',
          lat: 48.8584,
          lng: 2.2945,
          audioUrl: 'https://cdn.ondoway.com/stop-1.mp3',
        ),
        _makeStop(
          sortOrder: 2,
          beatId: 'beat-2',
          stopId: 'stop-2',
          lat: 48.8606,
          lng: 2.3376,
          audioUrl: 'https://cdn.ondoway.com/stop-2.mp3',
        ),
      ];

      await service.startTour(stops);
      service.skipToStop(1);

      // The play key is the stopId, not the beatId.
      expect(service.currentStop!.beatId, 'beat-2');
      expect(audioService.currentBeatId, 'stop-2');

      // Completion uses the SAME key, so auto-advance still fires.
      audioService.simulateComplete();
      expect(service.currentStopIndex, greaterThanOrEqualTo(1));
    });

    test('falls back to beatId for the play key when stopId is null', () async {
      // Legacy stops with no per-stop id keep playing by beatId — no regression.
      locationService.trackingWillSucceed = true;
      final stops = [
        _makeStop(
          sortOrder: 1,
          beatId: 'beat-1',
          lat: 48.8584,
          lng: 2.2945,
          audioUrl: 'https://cdn.ondoway.com/beat-1.mp3',
        ),
        _makeStop(
          sortOrder: 2,
          beatId: 'beat-2',
          lat: 48.8606,
          lng: 2.3376,
          audioUrl: 'https://cdn.ondoway.com/beat-2.mp3',
        ),
      ];

      await service.startTour(stops);
      service.skipToStop(1);

      expect(audioService.currentBeatId, 'beat-2');
    });

    test('skipToStop ignores invalid index', () async {
      locationService.trackingWillSucceed = true;
      final stops = [
        _makeStop(
          sortOrder: 1,
          beatId: 'beat-1',
          lat: 48.8584,
          lng: 2.2945,
          audioUrl: 'https://cdn.ondoway.com/beat-1.mp3',
        ),
      ];

      await service.startTour(stops);
      service.skipToStop(5); // out of bounds

      expect(service.currentStopIndex, 0);
    });

    test('skipToStop ignores negative index', () async {
      locationService.trackingWillSucceed = true;
      final stops = [
        _makeStop(
          sortOrder: 1,
          beatId: 'beat-1',
          lat: 48.8584,
          lng: 2.2945,
          audioUrl: 'https://cdn.ondoway.com/beat-1.mp3',
        ),
      ];

      await service.startTour(stops);
      service.skipToStop(-1);

      expect(service.currentStopIndex, 0);
    });

    test('acceptPendingStop advances to pending', () async {
      locationService.trackingWillSucceed = true;
      final stops = [
        _makeStop(
          sortOrder: 1,
          beatId: 'beat-1',
          lat: 48.8584,
          lng: 2.2945,
          audioUrl: 'https://cdn.ondoway.com/beat-1.mp3',
        ),
        _makeStop(
          sortOrder: 2,
          beatId: 'beat-2',
          lat: 48.8606,
          lng: 2.3376,
          audioUrl: 'https://cdn.ondoway.com/beat-2.mp3',
        ),
      ];

      await service.startTour(stops);

      // Simulate: play current stop, then user arrives at next
      audioService.play('beat-1', 'https://cdn.ondoway.com/beat-1.mp3');

      // Simulate position at stop 2 (within 10m)
      locationService.simulatePosition(48.8606, 2.3376);

      expect(service.state, TourState.approaching);
      expect(service.pendingStopIndex, 1);

      service.acceptPendingStop();

      expect(service.currentStopIndex, 1);
      expect(service.pendingStopIndex, isNull);
      expect(audioService.currentBeatId, 'beat-2');
    });

    test('dismissPending clears pending and returns to active', () async {
      locationService.trackingWillSucceed = true;
      final stops = [
        _makeStop(
          sortOrder: 1,
          beatId: 'beat-1',
          lat: 48.8584,
          lng: 2.2945,
          audioUrl: 'https://cdn.ondoway.com/beat-1.mp3',
        ),
        _makeStop(
          sortOrder: 2,
          beatId: 'beat-2',
          lat: 48.8606,
          lng: 2.3376,
          audioUrl: 'https://cdn.ondoway.com/beat-2.mp3',
        ),
      ];

      await service.startTour(stops);

      // Simulate: play current stop, then user arrives at next
      audioService.play('beat-1', 'https://cdn.ondoway.com/beat-1.mp3');
      locationService.simulatePosition(48.8606, 2.3376);

      expect(service.state, TourState.approaching);
      expect(service.hasPendingStop, true);

      service.dismissPending();

      expect(service.state, TourState.active);
      expect(service.pendingStopIndex, isNull);
      expect(service.hasPendingStop, false);
      // Still at stop 0
      expect(service.currentStopIndex, 0);
    });

    test('geofence triggers auto-play when user enters radius', () async {
      locationService.trackingWillSucceed = true;
      final stops = [
        _makeStop(
          sortOrder: 1,
          beatId: 'beat-1',
          lat: 48.8584,
          lng: 2.2945,
          audioUrl: 'https://cdn.ondoway.com/beat-1.mp3',
        ),
      ];

      await service.startTour(stops);

      // User is far away — no auto-play
      locationService.simulatePosition(48.8600, 2.2945);
      expect(audioService.isPlaying, false);

      // User enters geofence (within 10m)
      locationService.simulatePosition(48.8584, 2.2945);
      expect(audioService.isPlaying, true);
      expect(audioService.currentBeatId, 'beat-1');
    });

    test('geofence radius is configurable — fires at the wider proof radius',
        () async {
      final wideService = TourPlaybackService(
        locationService: locationService,
        audioService: audioService,
        triggerRadiusMeters: 20.0,
      );
      addTearDown(wideService.dispose);

      final stops = [
        _makeStop(
          sortOrder: 1,
          beatId: 'beat-1',
          lat: 48.8584,
          lng: 2.2945,
          audioUrl: 'https://cdn.ondoway.com/beat-1.mp3',
        ),
      ];
      await wideService.startTour(stops);

      // ~15.5m north of the stop: OUTSIDE the default 10m, INSIDE the 20m radius.
      locationService.simulatePosition(48.8584 + 0.00014, 2.2945);
      expect(audioService.isPlaying, true);
      expect(audioService.currentBeatId, 'beat-1');
    });

    test('does not auto-play if audio already playing', () async {
      locationService.trackingWillSucceed = true;
      final stops = [
        _makeStop(
          sortOrder: 1,
          beatId: 'beat-1',
          lat: 48.8584,
          lng: 2.2945,
          audioUrl: 'https://cdn.ondoway.com/beat-1.mp3',
        ),
      ];

      await service.startTour(stops);

      // Already playing
      audioService.play('beat-1', 'https://cdn.ondoway.com/beat-1.mp3');

      // Enter geofence again — should not restart
      locationService.simulatePosition(48.8584, 2.2945);
      // isPlaying is still true (not restarted)
      expect(audioService.isPlaying, true);
      expect(audioService.playCount, 1);
    });

    test('tour-audio completion auto-advances to the next stop (KE6 control)',
        () async {
      // Control for the KE6 guard: a completed SCHEDULED per-stop tour clip
      // still advances the itinerary index.
      locationService.trackingWillSucceed = true;
      final stops = [
        _makeStop(
          sortOrder: 1,
          beatId: 'beat-1',
          stopId: 'stop-1',
          lat: 48.8584,
          lng: 2.2945,
          audioUrl: 'https://cdn.ondoway.com/stop-1.mp3',
        ),
        _makeStop(
          sortOrder: 2,
          beatId: 'beat-2',
          stopId: 'stop-2',
          lat: 48.8606,
          lng: 2.3376,
          audioUrl: 'https://cdn.ondoway.com/stop-2.mp3',
        ),
      ];

      await service.startTour(stops);
      // Play the current stop's SCHEDULED audio (keyed by the stop key, NOT
      // deeper-dive), then complete it.
      service.skipToStop(0);
      expect(service.currentStopIndex, 0);
      expect(audioService.isDeeperDive, isFalse);

      audioService.simulateComplete();

      // Scheduled tour audio finished -> advance to the next stop.
      expect(service.currentStopIndex, 1);
    });

    test('deeper-dive completion does NOT auto-advance the tour (KE6)',
        () async {
      locationService.trackingWillSucceed = true;
      final stops = [
        _makeStop(
          sortOrder: 1,
          beatId: 'beat-1',
          stopId: 'stop-1',
          lat: 48.8584,
          lng: 2.2945,
          audioUrl: 'https://cdn.ondoway.com/stop-1.mp3',
        ),
        _makeStop(
          sortOrder: 2,
          beatId: 'beat-2',
          stopId: 'stop-2',
          lat: 48.8606,
          lng: 2.3376,
          audioUrl: 'https://cdn.ondoway.com/stop-2.mp3',
        ),
      ];

      await service.startTour(stops);
      expect(service.currentStopIndex, 0);

      // User taps "Keep exploring here" — a DEEPER-DIVE clip plays off-budget.
      audioService.play(
        'stop-1-keep-exploring',
        'https://cdn.ondoway.com/stop-1-ke.mp3',
        isDeeperDive: true,
      );
      expect(audioService.isDeeperDive, isTrue);

      // Deep-dive clip finishes.
      audioService.simulateComplete();

      // The tour MUST NOT advance — the index stays on the current stop.
      expect(service.currentStopIndex, 0);
      expect(service.state, isNot(TourState.completed));
    });

    test('deeper-dive completion does not advance even when a stop is pending '
        '(KE6)', () async {
      // Guards the FIRST advance branch (approaching + pendingStopIndex): a
      // deep dive completing mid-approach must not steal the auto-advance.
      locationService.trackingWillSucceed = true;
      final stops = [
        _makeStop(
          sortOrder: 1,
          beatId: 'beat-1',
          lat: 48.8584,
          lng: 2.2945,
          audioUrl: 'https://cdn.ondoway.com/beat-1.mp3',
        ),
        _makeStop(
          sortOrder: 2,
          beatId: 'beat-2',
          lat: 48.8606,
          lng: 2.3376,
          audioUrl: 'https://cdn.ondoway.com/beat-2.mp3',
        ),
      ];

      await service.startTour(stops);
      // Scheduled current-stop audio playing, then user reaches next stop.
      audioService.play('beat-1', 'https://cdn.ondoway.com/beat-1.mp3');
      locationService.simulatePosition(48.8606, 2.3376);
      expect(service.state, TourState.approaching);
      expect(service.pendingStopIndex, 1);

      // A deep-dive clip takes over and completes.
      audioService.play(
        'stop-1-keep-exploring',
        'https://cdn.ondoway.com/stop-1-ke.mp3',
        isDeeperDive: true,
      );
      audioService.simulateComplete();

      // Still at stop 0; the pending nudge is untouched (no auto-advance).
      expect(service.currentStopIndex, 0);
      expect(service.pendingStopIndex, 1);
    });

    test('stop without audioUrl does not trigger play', () async {
      locationService.trackingWillSucceed = true;
      final stops = [
        _makeStop(
          sortOrder: 1,
          beatId: 'beat-1',
          lat: 48.8584,
          lng: 2.2945,
          audioUrl: null, // no audio
        ),
      ];

      await service.startTour(stops);
      locationService.simulatePosition(48.8584, 2.2945);

      expect(audioService.isPlaying, false);
      expect(audioService.currentBeatId, isNull);
    });
  });
}
