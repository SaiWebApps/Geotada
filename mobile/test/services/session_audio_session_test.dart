import 'package:flutter_test/flutter_test.dart';
import 'package:ondoway/models/trip.dart';
import 'package:ondoway/services/tour_playback_service.dart';

import 'mocks/mock_audio_service.dart';
import 'mocks/mock_location_service.dart';

/// The iOS audio session, opened and given back by the WALK.
///
/// iOS refuses to activate an audio session from a background callback, so the
/// activation has to happen in the foreground, at the moment the tour starts.
/// Until it does, the native player that is the only thing audible through a
/// locked screen has no active session to play on. And a session left active
/// keeps the `.duckOthers` category in force, so the tourist's own music stays
/// quiet long after the walk is over.
ItineraryStop _stop(int order, String id) => ItineraryStop(
      sortOrder: order,
      stopId: id,
      poiId: 'poi-$id',
      poiName: 'Stop $order',
      lat: 48.86,
      lng: 2.34,
      beatId: 'beat-$id',
      lensName: 'hidden_history',
      lensDisplay: 'Hidden History',
      durationMin: 10,
      importanceTier: 1,
      startTime: '09:00',
      audioUrl: 'https://cdn.example.com/$id.mp3',
    );

void main() {
  late MockAudioService audio;
  late MockLocationService location;
  late TourPlaybackService engine;

  setUp(() {
    audio = MockAudioService();
    location = MockLocationService();
    engine = TourPlaybackService(locationService: location, audioService: audio);
  });

  test('starting a tour asks for the audio session, in the foreground', () async {
    await engine.startTour([_stop(0, 's1'), _stop(1, 's2')]);
    expect(audio.callLog, ['prepare']);
  });

  test('stopping a tour gives the session back', () async {
    await engine.startTour([_stop(0, 's1'), _stop(1, 's2')]);
    engine.stopTour();
    expect(audio.callLog, ['prepare', 'release']);
  });

  test('a tour that finishes on its own gives the session back too', () async {
    // The last stop's piece completing is the walk ending without anyone
    // pressing stop. Without a release here the ducking outlives the tour.
    // The piece has to have PLAYED first: the engine advances on the
    // completion of the stop it is standing at, matched by audio key.
    await engine.startTour([_stop(0, 's1')]);
    audio.play('s1', 'https://cdn.example.com/s1.mp3');
    audio.simulateComplete();

    expect(engine.state, TourState.completed);
    expect(audio.callLog, ['prepare', 'release']);
  });
}
