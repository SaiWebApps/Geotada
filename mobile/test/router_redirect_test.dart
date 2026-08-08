import 'package:flutter_test/flutter_test.dart';
import 'package:ondoway/router.dart';

void main() {
  group('computeAuthRedirect', () {
    test(
        'unauthenticated + /debug/location-spike + allowDebugRoutes:true → null '
        '(the bug: must NOT redirect)', () {
      final result = computeAuthRedirect(
        isAuthenticated: false,
        profileLoaded: false,
        profileIsFirstTime: false,
        path: '/debug/location-spike',
        allowDebugRoutes: true,
      );
      expect(result, isNull);
    });

    test(
        'unauthenticated + /debug/location-spike + allowDebugRoutes:false → /login '
        '(release still guards it)', () {
      final result = computeAuthRedirect(
        isAuthenticated: false,
        profileLoaded: false,
        profileIsFirstTime: false,
        path: '/debug/location-spike',
        allowDebugRoutes: false,
      );
      expect(result, '/login');
    });

    test('unauthenticated + /explore → /login (existing guard preserved)', () {
      final result = computeAuthRedirect(
        isAuthenticated: false,
        profileLoaded: false,
        profileIsFirstTime: false,
        path: '/explore',
        allowDebugRoutes: true,
      );
      expect(result, '/login');
    });

    test('unauthenticated + /login → null', () {
      final result = computeAuthRedirect(
        isAuthenticated: false,
        profileLoaded: false,
        profileIsFirstTime: false,
        path: '/login',
        allowDebugRoutes: true,
      );
      expect(result, isNull);
    });

    test(
        'authenticated + /login + profileLoaded:true + firstTime:true → '
        '/onboarding', () {
      final result = computeAuthRedirect(
        isAuthenticated: true,
        profileLoaded: true,
        profileIsFirstTime: true,
        path: '/login',
        allowDebugRoutes: false,
      );
      expect(result, '/onboarding');
    });

    test(
        'authenticated + /login + profileLoaded:true + firstTime:false → '
        '/explore', () {
      final result = computeAuthRedirect(
        isAuthenticated: true,
        profileLoaded: true,
        profileIsFirstTime: false,
        path: '/login',
        allowDebugRoutes: false,
      );
      expect(result, '/explore');
    });

    test('authenticated + /login + profileLoaded:false → null', () {
      final result = computeAuthRedirect(
        isAuthenticated: true,
        profileLoaded: false,
        profileIsFirstTime: false,
        path: '/login',
        allowDebugRoutes: false,
      );
      expect(result, isNull);
    });
  });
}
