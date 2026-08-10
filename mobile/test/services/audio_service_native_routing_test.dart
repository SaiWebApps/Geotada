import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ondoway/services/audio_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const nativeChannel = MethodChannel('com.ondoway/native_audio');
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;

  final calls = <MethodCall>[];

  // Injected cache resolver: beat-1 is "cached" at this path, nothing else is.
  // Keeps the test off the real filesystem so it runs on the web test runner.
  Future<String?> resolver(String beatId) async =>
      beatId == 'beat-1' ? '/cache/ondoway_audio/beat-1.mp3' : null;

  setUp(() {
    debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
    calls.clear();
    messenger.setMockMethodCallHandler(nativeChannel, (call) async {
      calls.add(call);
      switch (call.method) {
        case 'play':
          return 30.0; // seconds
        case 'getPosition':
          return 0;
        default:
          return null;
      }
    });
  });

  tearDown(() {
    debugDefaultTargetPlatformOverride = null;
    messenger.setMockMethodCallHandler(nativeChannel, null);
  });

  Future<void> fireNativeComplete() async {
    await messenger.handlePlatformMessage(
      nativeChannel.name,
      const StandardMethodCodec()
          .encodeMethodCall(const MethodCall('onComplete')),
      (_) {},
    );
  }

  test('cached-file playback on iOS routes to the native player, not just_audio',
      () async {
    final service = AudioService(cachedPathResolver: resolver);
    addTearDown(service.dispose);

    await service.play('beat-1', 'https://cdn.example.com/beat-1.mp3');

    final playCall = calls.singleWhere((c) => c.method == 'play');
    expect((playCall.arguments as Map)['path'], '/cache/ondoway_audio/beat-1.mp3');
    expect(service.isPlaying, isTrue);
    expect(service.currentBeatId, 'beat-1');
    expect(service.duration, const Duration(seconds: 30));

    await service.stop();
  });

  test('native completion flips isPlaying false so the tour can auto-advance',
      () async {
    final service = AudioService(cachedPathResolver: resolver);
    addTearDown(service.dispose);

    await service.play('beat-1', 'https://cdn.example.com/beat-1.mp3');
    expect(service.isPlaying, isTrue);

    await fireNativeComplete();

    expect(service.isPlaying, isFalse);
    // currentBeatId is retained (matches just_audio) so the tour engine's
    // completion check can identify which stop just finished.
    expect(service.currentBeatId, 'beat-1');
    expect(service.position, service.duration);
  });

  test('stop halts the native player and clears state', () async {
    final service = AudioService(cachedPathResolver: resolver);
    addTearDown(service.dispose);

    await service.play('beat-1', 'https://cdn.example.com/beat-1.mp3');
    await service.stop();

    expect(calls.any((c) => c.method == 'stop'), isTrue);
    expect(service.isPlaying, isFalse);
    expect(service.currentBeatId, isNull);
  });
}
