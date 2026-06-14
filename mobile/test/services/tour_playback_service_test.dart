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
