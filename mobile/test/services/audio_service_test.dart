import 'package:flutter_test/flutter_test.dart';
import 'package:ondoway/services/audio_service.dart';

void main() {
  group('BeatAudioInfo', () {
    test('stores beatId and audioUrl', () {
      const info = BeatAudioInfo(beatId: 'beat-1', audioUrl: 'https://example.com/audio.mp3');
      expect(info.beatId, 'beat-1');
      expect(info.audioUrl, 'https://example.com/audio.mp3');
    });

    test('audioUrl can be null', () {
      const info = BeatAudioInfo(beatId: 'beat-2');
      expect(info.beatId, 'beat-2');
      expect(info.audioUrl, isNull);
    });

    test('const constructor allows compile-time lists', () {
      const beats = [
        BeatAudioInfo(beatId: 'b1', audioUrl: 'url1'),
        BeatAudioInfo(beatId: 'b2'),
        BeatAudioInfo(beatId: 'b3', audioUrl: 'url3'),
      ];
      expect(beats.length, 3);
      expect(beats.where((b) => b.audioUrl != null).length, 2);
    });
  });

  // Note: AudioService instantiation tests are skipped in Chrome because
  // just_audio requires platform channels (dart:ffi) not available in the
  // browser test environment. These are exercised on iOS simulator via
  // integration tests.
}
