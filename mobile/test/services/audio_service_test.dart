import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:ondoway/services/audio_service.dart';

void main() {
  // AudioService now owns a native MethodChannel (com.ondoway/native_audio),
  // and registering its handler needs an initialized binding — even for these
  // HTTP-only tests that construct the service but never play.
  TestWidgetsFlutterBinding.ensureInitialized();

  group('AudioService', () {
    test('checkAudioStatus returns parsed response on 200', () async {
      final client = MockClient((request) async {
        expect(request.url.path, contains('/audio/status/beat-1'));
        return http.Response(
          jsonEncode({
            'has_audio': true,
            'audio_url': 'https://cdn.example.com/beat-1.mp3',
            'duration_sec': 120,
            'is_stale': false,
          }),
          200,
        );
      });

      final service = AudioService(httpClient: client);
      final result = await service.checkAudioStatus(
        'http://localhost:8000/api/v1',
        'beat-1',
      );

      expect(result, isNotNull);
      expect(result!['has_audio'], true);
      expect(result['audio_url'], 'https://cdn.example.com/beat-1.mp3');
      expect(result['duration_sec'], 120);
      expect(result['is_stale'], false);
    });

    test('checkAudioStatus returns null on non-200 response', () async {
      final client = MockClient((request) async {
        return http.Response('not found', 404);
      });

      final service = AudioService(httpClient: client);
      final result = await service.checkAudioStatus(
        'http://localhost:8000/api/v1',
        'beat-nonexistent',
      );

      expect(result, isNull);
    });

    test('checkAudioStatus returns null on network error', () async {
      final client = MockClient((request) async {
        throw Exception('Network error');
      });

      final service = AudioService(httpClient: client);
      final result = await service.checkAudioStatus(
        'http://localhost:8000/api/v1',
        'beat-1',
      );

      expect(result, isNull);
    });

    test('checkStopAudioStatus hits the per-STOP endpoint and parses on 200',
        () async {
      final client = MockClient((request) async {
        expect(request.method, 'GET');
        // Per-stop endpoint, NOT the per-beat /audio/status/{beatId}.
        expect(request.url.path, contains('/audio/stop-status/stop-7'));
        return http.Response(
          jsonEncode({
            'stop_id': 'stop-7',
            'has_audio': true,
            'audio_url': 'https://cdn.example.com/stop-7.mp3',
            'duration_sec': 95,
          }),
          200,
        );
      });

      final service = AudioService(httpClient: client);
      final result = await service.checkStopAudioStatus(
        'http://localhost:8000/api/v1',
        'stop-7',
      );

      expect(result, isNotNull);
      expect(result!['has_audio'], true);
      expect(result['audio_url'], 'https://cdn.example.com/stop-7.mp3');
      expect(result['duration_sec'], 95);
    });

    test('checkStopAudioStatus returns null on 404', () async {
      final client = MockClient((request) async {
        return http.Response('not found', 404);
      });

      final service = AudioService(httpClient: client);
      final result = await service.checkStopAudioStatus(
        'http://localhost:8000/api/v1',
        'stop-missing',
      );

      expect(result, isNull);
    });

    test('checkStopAudioStatus returns null on network error', () async {
      final client = MockClient((request) async {
        throw Exception('Network error');
      });

      final service = AudioService(httpClient: client);
      final result = await service.checkStopAudioStatus(
        'http://localhost:8000/api/v1',
        'stop-7',
      );

      expect(result, isNull);
    });
  });

  group('BeatAudioInfo', () {
    test('stores beatId and audioUrl', () {
      const info = BeatAudioInfo(
        beatId: 'beat-123',
        audioUrl: 'https://audio.ondoway.com/beats/beat-123.mp3',
      );
      expect(info.beatId, 'beat-123');
      expect(info.audioUrl, 'https://audio.ondoway.com/beats/beat-123.mp3');
    });

    test('audioUrl can be null', () {
      const info = BeatAudioInfo(beatId: 'beat-456');
      expect(info.beatId, 'beat-456');
      expect(info.audioUrl, isNull);
    });
  });
}
