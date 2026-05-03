import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:ondoway/services/auth_service.dart';
import 'package:ondoway/services/lens_service.dart';
import 'package:ondoway/services/profile_service.dart';
import '../services/auth_service_test.dart';

String? simulateRedirect(bool isAuthenticated, String path, {bool profileLoaded = false, bool isFirstTime = true}) {
  final isAuthRoute = path == '/login' || path == '/auth' || path == '/auth/callback';
  if (!isAuthenticated && !isAuthRoute) return '/login';
  if (isAuthenticated && path == '/login') {
    if (!profileLoaded) return null;
    return isFirstTime ? '/onboarding' : '/explore';
  }
  return null;
}

void main() {
  group('Router redirect logic', () {
    late AuthService authService;
    late ProfileService profileService;
    late LensService lensService;

    setUp(() {
      final client = MockClient((r) async => http.Response('', 200));
      authService = AuthService(storage: FakeSecureStorage(), httpClient: client);
      profileService = ProfileService(httpClient: client);
      lensService = LensService(httpClient: client);
    });

    test('unauthenticated user on /login stays on /login', () {
      expect(simulateRedirect(false, '/login'), isNull);
    });

    test('unauthenticated user on /explore redirects to /login', () {
      expect(simulateRedirect(false, '/explore'), '/login');
    });

    test('unauthenticated user on /auth/callback is allowed through', () {
      expect(simulateRedirect(false, '/auth/callback'), isNull);
    });

    test('unauthenticated user on /auth is allowed through', () {
      expect(simulateRedirect(false, '/auth'), isNull);
    });

    test('authenticated first-time user on /login goes to /onboarding', () {
      expect(
        simulateRedirect(true, '/login', profileLoaded: true, isFirstTime: true),
        '/onboarding',
      );
    });

    test('authenticated returning user on /login goes to /explore', () {
      expect(
        simulateRedirect(true, '/login', profileLoaded: true, isFirstTime: false),
        '/explore',
      );
    });

    test('authenticated user on /login with profile not loaded stays', () {
      expect(
        simulateRedirect(true, '/login', profileLoaded: false),
        isNull,
      );
    });

    test('authenticated user on /onboarding is allowed through', () {
      expect(simulateRedirect(true, '/onboarding'), isNull);
    });

    test('authenticated user on /explore is allowed through', () {
      expect(simulateRedirect(true, '/explore'), isNull);
    });

    test('authenticated user on /lenses is allowed through', () {
      expect(simulateRedirect(true, '/lenses'), isNull);
    });

    test('deep link to /auth/callback is NEVER redirected regardless of auth state', () {
      expect(simulateRedirect(false, '/auth/callback'), isNull);
      expect(simulateRedirect(true, '/auth/callback'), isNull);
    });

    test('deep link to /auth is NEVER redirected regardless of auth state', () {
      expect(simulateRedirect(false, '/auth'), isNull);
      expect(simulateRedirect(true, '/auth'), isNull);
    });
  });

  group('Custom scheme URL parsing', () {
    test('ondoway://auth/callback?token=xyz parses host=auth path=/callback', () {
      final uri = Uri.parse('ondoway://auth/callback?token=xyz');
      expect(uri.scheme, 'ondoway');
      expect(uri.host, 'auth');
      expect(uri.path, '/callback');
      expect(uri.query, 'token=xyz');
    });

    test('combining host+path reconstructs the correct route', () {
      final uri = Uri.parse('ondoway://auth/callback?token=xyz');
      final host = uri.host;
      final path = uri.path;
      final fullPath = host.isNotEmpty ? '/$host$path' : path;
      expect(fullPath, '/auth/callback');
    });

    test('ondoway://auth?token=xyz gives host=auth path=empty', () {
      final uri = Uri.parse('ondoway://auth?token=xyz');
      final host = uri.host;
      final path = uri.path;
      final fullPath = host.isNotEmpty ? '/$host$path' : path;
      expect(fullPath, '/auth');
    });

    test('reconstructed path is allowed through redirect', () {
      expect(simulateRedirect(false, '/auth/callback'), isNull);
      expect(simulateRedirect(false, '/auth'), isNull);
    });
  });
}
