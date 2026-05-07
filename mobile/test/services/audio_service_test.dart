import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:ondoway/services/audio_service.dart';

void main() {
  group('AudioService', () {
    test('prefetchAudio downloads and caches beats', () async {
      final client = MockClient((request) async {
        // Simulate successful MP3 download
        return http.Response('fake-mp3-data', 200);
      });

      final service = AudioService(httpClient: client);
      final beats = [
        const BeatAudioInfo(
          beatId: 'beat-1',
          audioUrl: 'https://cdn.example.com/beat-1.mp3',
        ),
        const BeatAudioInfo(
          beatId: 'beat-2',
          audioUrl: 'https://cdn.example.com/beat-2.mp3',
        ),
      ];

      final count = await service.prefetchAudio(beats);

      expect(count, 2);
      expect(service.isCached('beat-1'), true);
      expect(service.isCached('beat-2'), true);
      expect(service.cachedBeatIds.length, 2);
    });

    test('prefetchAudio handles individual failures gracefully', () async {
      int callCount = 0;
      final client = MockClient((request) async {
        callCount++;
        if (callCount == 1) {
          return http.Response('fake-mp3-data', 200);
        }
        // Second call fails
        return http.Response('not found', 404);
      });

      final service = AudioService(httpClient: client);
      final beats = [
        const BeatAudioInfo(
          beatId: 'beat-1',
          audioUrl: 'https://cdn.example.com/beat-1.mp3',
        ),
        const BeatAudioInfo(
          beatId: 'beat-2',
          audioUrl: 'https://cdn.example.com/beat-2.mp3',
        ),
      ];

      final count = await service.prefetchAudio(beats);

      expect(count, 1);
      expect(service.isCached('beat-1'), true);
      expect(service.isCached('beat-2'), false);
    });

    test('prefetchAudio returns 0 for empty list', () async {
      final client = MockClient((request) async {
        return http.Response('', 200);
      });

      final service = AudioService(httpClient: client);
      final count = await service.prefetchAudio([]);

      expect(count, 0);
      expect(service.cachedBeatIds, isEmpty);
    });

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

    test('reset clears all cached state', () async {
      final client = MockClient((request) async {
        return http.Response('fake-mp3-data', 200);
      });

      final service = AudioService(httpClient: client);
      await service.prefetchAudio([
        const BeatAudioInfo(
          beatId: 'beat-1',
          audioUrl: 'https://cdn.example.com/beat-1.mp3',
        ),
      ]);

      expect(service.cachedBeatIds.length, 1);

      service.reset();

      expect(service.cachedBeatIds, isEmpty);
      expect(service.isCached('beat-1'), false);
    });

    test('isCached returns false for uncached beats', () {
      final client = MockClient((request) async {
        return http.Response('', 200);
      });

      final service = AudioService(httpClient: client);
      expect(service.isCached('nonexistent'), false);
    });
  });
}
