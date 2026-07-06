import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:ondoway/services/audio_service.dart';
import 'package:ondoway/widgets/beat_audio_player.dart';

Widget _wrap({
  required Widget child,
  AudioService? audioService,
}) {
  return MaterialApp(
    home: Scaffold(
      body: ChangeNotifierProvider<AudioService>.value(
        value: audioService ?? AudioService(),
        child: child,
      ),
    ),
  );
}

/// Reports playback state without booting a real just_audio player. A real
/// `AudioService.play()` awaits `just_audio` loading a (fake) URL, which never
/// completes on the headless-web test runner and hangs the suite.
class _FakeAudioService extends AudioService {
  _FakeAudioService({String? activeBeatId, bool playing = false})
      : _activeBeatId = activeBeatId,
        _playing = playing;

  String? _activeBeatId;
  final bool _playing;

  @override
  String? get currentBeatId => _activeBeatId;

  @override
  bool get isPlaying => _playing;

  @override
  Future<void> play(
    String beatId,
    String audioUrl, {
    bool isDeeperDive = false,
  }) async {
    // Record the call without booting a real just_audio engine (which never
    // completes on the headless-web test runner and hangs finalize).
    _activeBeatId = beatId;
    notifyListeners();
  }
}

void main() {
  group('BeatAudioPlayer', () {
    testWidgets('renders play button when audioUrl is provided', (tester) async {
      await tester.pumpWidget(
        _wrap(
          child: const BeatAudioPlayer(
            beatId: 'beat-1',
            audioUrl: 'https://example.com/audio.mp3',
            durationSec: 90.0,
          ),
        ),
      );

      expect(find.byIcon(Icons.play_circle_filled), findsOneWidget);
      expect(find.text('1:30'), findsOneWidget);
    });

    testWidgets('shows Generate button when audioUrl is null', (tester) async {
      await tester.pumpWidget(
        _wrap(
          child: const BeatAudioPlayer(
            beatId: 'beat-1',
            audioUrl: null,
            durationSec: null,
          ),
        ),
      );

      expect(find.text('Generate Audio'), findsOneWidget);
      expect(find.byIcon(Icons.graphic_eq), findsOneWidget);
      expect(find.byIcon(Icons.play_circle_filled), findsNothing);
    });

    testWidgets('play button triggers AudioService.play', (tester) async {
      final audioService = _FakeAudioService();

      await tester.pumpWidget(
        _wrap(
          audioService: audioService,
          child: const BeatAudioPlayer(
            beatId: 'beat-1',
            audioUrl: 'https://example.com/audio.mp3',
            durationSec: 90.0,
          ),
        ),
      );

      await tester.tap(find.byIcon(Icons.play_circle_filled));
      await tester.pump();

      // After tapping play, AudioService should show this beat as active
      expect(audioService.currentBeatId, 'beat-1');
    });

    testWidgets('shows pause icon when beat is active and playing',
        (tester) async {
      final audioService = _FakeAudioService(activeBeatId: 'beat-1', playing: true);

      await tester.pumpWidget(
        _wrap(
          audioService: audioService,
          child: const BeatAudioPlayer(
            beatId: 'beat-1',
            audioUrl: 'https://example.com/audio.mp3',
            durationSec: 90.0,
          ),
        ),
      );

      expect(find.byIcon(Icons.pause_circle_filled), findsOneWidget);
      expect(find.byIcon(Icons.play_circle_filled), findsNothing);
    });

    testWidgets('shows play icon when a different beat is active',
        (tester) async {
      final audioService =
          _FakeAudioService(activeBeatId: 'beat-other', playing: true);

      await tester.pumpWidget(
        _wrap(
          audioService: audioService,
          child: const BeatAudioPlayer(
            beatId: 'beat-1',
            audioUrl: 'https://example.com/audio.mp3',
            durationSec: 90.0,
          ),
        ),
      );

      // This beat should show play (not pause) since it's not the active beat
      expect(find.byIcon(Icons.play_circle_filled), findsOneWidget);
      expect(find.byIcon(Icons.pause_circle_filled), findsNothing);
    });


    testWidgets('formats duration correctly for various values',
        (tester) async {
      await tester.pumpWidget(
        _wrap(
          child: const BeatAudioPlayer(
            beatId: 'beat-1',
            audioUrl: 'https://example.com/audio.mp3',
            durationSec: 65.0,
          ),
        ),
      );

      // 65 seconds = 1:05
      expect(find.text('1:05'), findsOneWidget);
    });

    testWidgets('formats zero duration as 0:00', (tester) async {
      await tester.pumpWidget(
        _wrap(
          child: const BeatAudioPlayer(
            beatId: 'beat-1',
            audioUrl: 'https://example.com/audio.mp3',
            durationSec: 0.0,
          ),
        ),
      );

      expect(find.text('0:00'), findsOneWidget);
    });
  });
}
