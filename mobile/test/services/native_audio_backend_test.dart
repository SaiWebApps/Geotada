import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ondoway/services/native_audio_backend.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel('com.ondoway/native_audio');
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;

  final calls = <MethodCall>[];

  setUp(() {
    calls.clear();
    messenger.setMockMethodCallHandler(channel, (call) async {
      calls.add(call);
      switch (call.method) {
        case 'play':
          return 42.5; // duration seconds
        case 'getPosition':
          return 1500; // ms
        default:
          return null;
      }
    });
  });

  tearDown(() {
    messenger.setMockMethodCallHandler(channel, null);
  });

  /// Fires the native->Dart `onComplete` the way AVAudioPlayerDelegate does,
  /// by delivering a platform message the backend's handler is registered for.
  Future<void> fireNativeComplete() async {
    await messenger.handlePlatformMessage(
      channel.name,
      const StandardMethodCodec().encodeMethodCall(const MethodCall('onComplete')),
      (_) {},
    );
  }

  test('play invokes native "play" with the file path and returns duration',
      () async {
    final backend = NativeAudioBackend();
    final duration = await backend.play('/tmp/ondoway_audio/proof-1.mp3');

    expect(calls.single.method, 'play');
    expect(
      (calls.single.arguments as Map)['path'],
      '/tmp/ondoway_audio/proof-1.mp3',
    );
    expect(duration, const Duration(milliseconds: 42500));
  });

  test('pause / resume / stop invoke their native methods', () async {
    final backend = NativeAudioBackend();
    await backend.pause();
    await backend.resume();
    await backend.stop();
    expect(calls.map((c) => c.method), ['pause', 'resume', 'stop']);
  });

  test('getPosition returns the native currentTime as a Duration', () async {
    final backend = NativeAudioBackend();
    expect(await backend.getPosition(), const Duration(milliseconds: 1500));
  });

  test('onComplete callback fires when native reports completion', () async {
    final backend = NativeAudioBackend();
    var completed = 0;
    backend.onComplete = () => completed++;

    await fireNativeComplete();

    expect(completed, 1);
  });
}
