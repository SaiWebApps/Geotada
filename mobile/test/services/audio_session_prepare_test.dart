import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ondoway/services/audio_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel('com.ondoway/audio_session');

  test('prepareSession invokes "prepare" on the audio_session channel', () async {
    final calls = <String>[];
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
      calls.add(call.method);
      return null;
    });
    addTearDown(() {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, null);
    });

    await AudioService().prepareSession();

    expect(calls, ['prepare']);
  });
}
