import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:ondoway/services/profile_service.dart';

MockClient _firstTimeUserClient() {
  return MockClient((request) async {
    if (request.url.path.contains('/edges/HAS_PROFILE')) {
      return http.Response(
        jsonEncode({'items': [], 'total': 0, 'skip': 0, 'limit': 10}),
        200,
      );
    }
    return http.Response('Not found', 404);
  });
}

MockClient _returningUserClient({
  String profileId = 'profile-1',
  List<String> lensTargetIds = const ['lens-a', 'lens-b', 'lens-c'],
  String? themePreference,
}) {
  return MockClient((request) async {
    if (request.url.path.contains('/edges/HAS_PROFILE')) {
      return http.Response(
        jsonEncode({
          'items': [
            {'id': 'edge-hp', 'type': 'HAS_PROFILE', 'source_id': 'user-1', 'target_id': profileId, 'properties': {}}
          ],
          'total': 1,
          'skip': 0,
          'limit': 10,
        }),
        200,
      );
    }
    if (request.url.path.contains('/nodes/Profile/')) {
      final props = <String, dynamic>{'display_name': 'Test User'};
      if (themePreference != null) {
        props['theme_preference'] = themePreference;
      }
      return http.Response(
        jsonEncode({
          'id': profileId,
          'labels': ['Profile'],
          'properties': props,
        }),
        200,
      );
    }
    if (request.url.path.contains('/edges/PREFERS_LENS')) {
      return http.Response(
        jsonEncode({
          'items': lensTargetIds
              .map((id) => {
                    'id': 'edge-$id',
                    'type': 'PREFERS_LENS',
                    'source_id': profileId,
                    'target_id': id,
                    'properties': {},
                  })
              .toList(),
          'total': lensTargetIds.length,
          'skip': 0,
          'limit': 200,
        }),
        200,
      );
    }
    return http.Response('Not found', 404);
  });
}

MockClient _onboardingClient() {
  return MockClient((request) async {
    if (request.url.path.contains('/edges/HAS_PROFILE')) {
      return http.Response(
        jsonEncode({'items': [], 'total': 0, 'skip': 0, 'limit': 10}),
        200,
      );
    }
    if (request.url.path.contains('/onboarding/complete')) {
      final body = jsonDecode(request.body) as Map<String, dynamic>;
      final lensIds = body['lens_ids'] as List<dynamic>;
      return http.Response(
        jsonEncode({
          'profile_id': 'new-profile-1',
          'display_name': 'Testuser',
          'lens_count': lensIds.length,
        }),
        200,
      );
    }
    return http.Response('Not found', 404);
  });
}

void main() {
  group('ProfileService', () {
    test('fetchProfile does not set isFirstTime on 401 (auth failure)', () async {
      final service = ProfileService(
        httpClient: MockClient((request) async {
          return http.Response('{"detail":"Unauthorized"}', 401);
        }),
      );

      await service.fetchProfile('user-1', 'bad-token');

      // Should NOT mark as first-time or loaded — auth layer needs to handle this
      expect(service.isLoaded, false);
      expect(service.isFirstTime, true); // default, but isLoaded=false means router won't act on it
    });

    test('detects first-time user (no profile)', () async {
      final service = ProfileService(httpClient: _firstTimeUserClient());
      await service.fetchProfile('user-1', 'token');

      expect(service.isFirstTime, true);
      expect(service.isLoaded, true);
      expect(service.profileId, isNull);
      expect(service.selectedLensIds, isEmpty);
    });

    test('detects returning user with lenses', () async {
      final service = ProfileService(httpClient: _returningUserClient());
      await service.fetchProfile('user-1', 'token');

      expect(service.isFirstTime, false);
      expect(service.isLoaded, true);
      expect(service.profileId, 'profile-1');
      expect(service.selectedLensIds, ['lens-a', 'lens-b', 'lens-c']);
    });

    test('detects half-onboarded user (profile, no lenses) as first-time', () async {
      final service = ProfileService(
        httpClient: _returningUserClient(lensTargetIds: []),
      );
      await service.fetchProfile('user-1', 'token');

      expect(service.isFirstTime, true);
      expect(service.profileId, 'profile-1');
    });

    test('completeOnboarding stores profile and lenses', () async {
      final service = ProfileService(httpClient: _onboardingClient());
      await service.fetchProfile('user-1', 'token');
      expect(service.isFirstTime, true);

      await service.completeOnboarding(
        ['lens-1', 'lens-2', 'lens-3'],
        'token',
      );

      expect(service.isFirstTime, false);
      expect(service.profileId, 'new-profile-1');
      expect(service.displayName, 'Testuser');
      expect(service.selectedLensIds.length, 3);
    });

    test('completeOnboarding throws on API failure', () async {
      final service = ProfileService(
        httpClient: MockClient((r) async => http.Response('error', 500)),
      );

      expect(
        () => service.completeOnboarding(['a', 'b', 'c'], 'token'),
        throwsA(isA<ProfileServiceException>()),
      );
    });

    test('reset clears all state', () async {
      final service = ProfileService(httpClient: _returningUserClient());
      await service.fetchProfile('user-1', 'token');
      expect(service.isFirstTime, false);

      service.reset();

      expect(service.isFirstTime, true);
      expect(service.isLoaded, false);
      expect(service.profileId, isNull);
      expect(service.selectedLensIds, isEmpty);
    });

    test('isLoaded is false before fetch', () {
      final service = ProfileService(httpClient: _firstTimeUserClient());
      expect(service.isLoaded, false);
    });

    test('fetchProfile reads theme_preference from profile node', () async {
      final service = ProfileService(
        httpClient: _returningUserClient(themePreference: 'dark'),
      );
      await service.fetchProfile('user-1', 'token');

      expect(service.themePreference, 'dark');
    });

    test('fetchProfile defaults themePreference to null for new profiles', () async {
      final service = ProfileService(
        httpClient: _returningUserClient(themePreference: null),
      );
      await service.fetchProfile('user-1', 'token');

      expect(service.themePreference, isNull);
    });

    test('updateThemePreference sends PUT and updates state', () async {
      String? capturedBody;
      final client = MockClient((request) async {
        if (request.url.path.contains('/edges/HAS_PROFILE')) {
          return http.Response(
            jsonEncode({
              'items': [
                {'id': 'e1', 'type': 'HAS_PROFILE', 'source_id': 'user-1', 'target_id': 'profile-1', 'properties': {}}
              ],
              'total': 1, 'skip': 0, 'limit': 10,
            }),
            200,
          );
        }
        if (request.url.path.contains('/nodes/Profile/') && request.method == 'GET') {
          return http.Response(
            jsonEncode({
              'id': 'profile-1',
              'labels': ['Profile'],
              'properties': {'display_name': 'Test'},
            }),
            200,
          );
        }
        if (request.url.path.contains('/nodes/Profile/') && request.method == 'PUT') {
          capturedBody = request.body;
          return http.Response(
            jsonEncode({
              'id': 'profile-1',
              'labels': ['Profile'],
              'properties': {'display_name': 'Test', 'theme_preference': 'light'},
            }),
            200,
          );
        }
        if (request.url.path.contains('/edges/PREFERS_LENS')) {
          return http.Response(
            jsonEncode({'items': [], 'total': 0, 'skip': 0, 'limit': 200}),
            200,
          );
        }
        return http.Response('Not found', 404);
      });

      final service = ProfileService(httpClient: client);
      await service.fetchProfile('user-1', 'token');
      await service.updateThemePreference('light', 'token');

      expect(service.themePreference, 'light');
      expect(capturedBody, contains('theme_preference'));
      expect(capturedBody, contains('light'));
    });

    test('updateThemePreference reverts on API failure', () async {
      final client = MockClient((request) async {
        if (request.url.path.contains('/edges/HAS_PROFILE')) {
          return http.Response(
            jsonEncode({
              'items': [
                {'id': 'e1', 'type': 'HAS_PROFILE', 'source_id': 'user-1', 'target_id': 'profile-1', 'properties': {}}
              ],
              'total': 1, 'skip': 0, 'limit': 10,
            }),
            200,
          );
        }
        if (request.url.path.contains('/nodes/Profile/') && request.method == 'GET') {
          return http.Response(
            jsonEncode({
              'id': 'profile-1',
              'labels': ['Profile'],
              'properties': {'display_name': 'Test', 'theme_preference': 'dark'},
            }),
            200,
          );
        }
        if (request.url.path.contains('/nodes/Profile/') && request.method == 'PUT') {
          return http.Response('Server error', 500);
        }
        if (request.url.path.contains('/edges/PREFERS_LENS')) {
          return http.Response(
            jsonEncode({'items': [], 'total': 0, 'skip': 0, 'limit': 200}),
            200,
          );
        }
        return http.Response('Not found', 404);
      });

      final service = ProfileService(httpClient: client);
      await service.fetchProfile('user-1', 'token');
      expect(service.themePreference, 'dark');

      expect(
        () => service.updateThemePreference('light', 'token'),
        throwsA(isA<ProfileServiceException>()),
      );

      // Wait for the future to settle so the revert takes effect
      await Future.delayed(Duration.zero);
      expect(service.themePreference, 'dark');
    });

    test('updateThemePreference is no-op when profileId is null', () async {
      final service = ProfileService(httpClient: _firstTimeUserClient());
      await service.fetchProfile('user-1', 'token');
      expect(service.profileId, isNull);

      // Should not throw, just return
      await service.updateThemePreference('dark', 'token');
      expect(service.themePreference, isNull);
    });

    test('reset clears themePreference', () async {
      final service = ProfileService(
        httpClient: _returningUserClient(themePreference: 'dark'),
      );
      await service.fetchProfile('user-1', 'token');
      expect(service.themePreference, 'dark');

      service.reset();
      expect(service.themePreference, isNull);
    });
  });
}
