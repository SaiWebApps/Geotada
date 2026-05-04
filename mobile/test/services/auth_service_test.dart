import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:ondoway/services/auth_service.dart';

// flutter_secure_storage doesn't work in tests, so we use a simple in-memory mock
class FakeSecureStorage extends FlutterSecureStorage {
  final Map<String, String> _store = {};

  FakeSecureStorage() : super();

  @override
  Future<void> write({
    required String key,
    required String? value,
    IOSOptions? iOptions,
    AndroidOptions? aOptions,
    LinuxOptions? lOptions,
    WebOptions? webOptions,
    MacOsOptions? mOptions,
    WindowsOptions? wOptions,
  }) async {
    if (value != null) {
      _store[key] = value;
    }
  }

  @override
  Future<String?> read({
    required String key,
    IOSOptions? iOptions,
    AndroidOptions? aOptions,
    LinuxOptions? lOptions,
    WebOptions? webOptions,
    MacOsOptions? mOptions,
    WindowsOptions? wOptions,
  }) async {
    return _store[key];
  }

  @override
  Future<void> delete({
    required String key,
    IOSOptions? iOptions,
    AndroidOptions? aOptions,
    LinuxOptions? lOptions,
    WebOptions? webOptions,
    MacOsOptions? mOptions,
    WindowsOptions? wOptions,
  }) async {
    _store.remove(key);
  }
}

void main() {
  group('AuthService', () {
    late AuthService authService;
    late MockClient mockClient;

    test('requestMagicLink sends correct POST', () async {
      mockClient = MockClient((request) async {
        expect(request.url.path, '/api/v1/auth/magic-link/request');
        expect(request.method, 'POST');
        final body = jsonDecode(request.body);
        expect(body['email'], 'test@ondoway.app');
        return http.Response('{"message":"Magic link sent"}', 200);
      });

      authService = AuthService(
        storage: FakeSecureStorage(),
        httpClient: mockClient,
      );

      await authService.requestMagicLink('test@ondoway.app');
    });

    test('verifyMagicLink stores tokens and fetches user', () async {
      mockClient = MockClient((request) async {
        if (request.url.path.contains('verify')) {
          return http.Response(
            jsonEncode({
              'access_token': 'test-access',
              'refresh_token': 'test-refresh',
              'token_type': 'bearer',
            }),
            200,
          );
        }
        if (request.url.path.contains('/me')) {
          return http.Response(
            jsonEncode({
              'id': 'user-1',
              'email': 'test@ondoway.app',
            }),
            200,
          );
        }
        return http.Response('Not found', 404);
      });

      authService = AuthService(
        storage: FakeSecureStorage(),
        httpClient: mockClient,
      );

      await authService.verifyMagicLink('magic-token');

      expect(authService.isAuthenticated, true);
      expect(authService.userId, 'user-1');
      expect(authService.userEmail, 'test@ondoway.app');
    });

    test('logout clears authentication state', () async {
      mockClient = MockClient((request) async {
        if (request.url.path.contains('verify')) {
          return http.Response(
            jsonEncode({
              'access_token': 'tok',
              'refresh_token': 'ref',
              'token_type': 'bearer',
            }),
            200,
          );
        }
        if (request.url.path.contains('/me')) {
          return http.Response(
            jsonEncode({'id': '1', 'email': 'a@b.com'}),
            200,
          );
        }
        return http.Response('', 404);
      });

      authService = AuthService(
        storage: FakeSecureStorage(),
        httpClient: mockClient,
      );

      await authService.verifyMagicLink('tok');
      expect(authService.isAuthenticated, true);

      await authService.logout();
      expect(authService.isAuthenticated, false);
      expect(authService.userEmail, null);
    });

    test('isAuthenticated is false initially', () {
      authService = AuthService(
        storage: FakeSecureStorage(),
        httpClient: MockClient((r) async => http.Response('', 200)),
      );

      expect(authService.isAuthenticated, false);
    });

    test('requestMagicLink throws on API failure', () async {
      mockClient = MockClient((request) async {
        return http.Response('{"detail":"error"}', 500);
      });

      authService = AuthService(
        storage: FakeSecureStorage(),
        httpClient: mockClient,
      );

      expect(
        () => authService.requestMagicLink('test@ondoway.app'),
        throwsA(isA<AuthException>()),
      );
    });

    test('loginWithGoogle sends correct POST', () async {
      mockClient = MockClient((request) async {
        if (request.url.path.contains('/google')) {
          expect(request.method, 'POST');
          final body = jsonDecode(request.body);
          expect(body['id_token'], 'google-id-token');
          return http.Response(
            jsonEncode({
              'access_token': 'g-access',
              'refresh_token': 'g-refresh',
              'token_type': 'bearer',
            }),
            200,
          );
        }
        if (request.url.path.contains('/me')) {
          return http.Response(
            jsonEncode({'id': 'g1', 'email': 'google@gmail.com'}),
            200,
          );
        }
        return http.Response('', 404);
      });

      authService = AuthService(
        storage: FakeSecureStorage(),
        httpClient: mockClient,
      );

      await authService.loginWithGoogle('google-id-token');

      expect(authService.isAuthenticated, true);
      expect(authService.userEmail, 'google@gmail.com');
    });

    test('tryRestoreSession restores from stored token', () async {
      final storage = FakeSecureStorage();
      await storage.write(key: 'access_token', value: 'stored-tok');

      mockClient = MockClient((request) async {
        if (request.url.path.contains('/me')) {
          expect(request.headers['Authorization'], 'Bearer stored-tok');
          return http.Response(
            jsonEncode({'id': 'u1', 'email': 'restored@ondoway.app'}),
            200,
          );
        }
        return http.Response('', 404);
      });

      authService = AuthService(storage: storage, httpClient: mockClient);
      await authService.tryRestoreSession();

      expect(authService.isAuthenticated, true);
      expect(authService.userEmail, 'restored@ondoway.app');
    });

    test('tryRestoreSession clears expired token', () async {
      final storage = FakeSecureStorage();
      await storage.write(key: 'access_token', value: 'expired-tok');
      await storage.write(key: 'refresh_token', value: 'expired-ref');

      mockClient = MockClient((request) async {
        return http.Response('{"detail":"Token expired"}', 401);
      });

      authService = AuthService(storage: storage, httpClient: mockClient);
      await authService.tryRestoreSession();

      expect(authService.isAuthenticated, false);
      expect(await storage.read(key: 'access_token'), null);
      expect(await storage.read(key: 'refresh_token'), null);
    });

    test('tryRestoreSession does nothing when no stored token', () async {
      final storage = FakeSecureStorage();

      mockClient = MockClient((request) async {
        fail('should not make any HTTP calls');
      });

      authService = AuthService(storage: storage, httpClient: mockClient);
      await authService.tryRestoreSession();

      expect(authService.isAuthenticated, false);
    });

    test('loginWithApple sends correct POST to /apple', () async {
      mockClient = MockClient((request) async {
        if (request.url.path.contains('/apple')) {
          expect(request.method, 'POST');
          final body = jsonDecode(request.body);
          expect(body['identity_token'], 'apple-identity-token');
          return http.Response(
            jsonEncode({
              'access_token': 'a-access',
              'refresh_token': 'a-refresh',
              'token_type': 'bearer',
            }),
            200,
          );
        }
        if (request.url.path.contains('/me')) {
          return http.Response(
            jsonEncode({'id': 'a1', 'email': 'apple@icloud.com'}),
            200,
          );
        }
        return http.Response('', 404);
      });

      authService = AuthService(
        storage: FakeSecureStorage(),
        httpClient: mockClient,
      );

      await authService.loginWithAppleWithToken('apple-identity-token');

      expect(authService.isAuthenticated, true);
      expect(authService.userEmail, 'apple@icloud.com');
    });
  });
}
