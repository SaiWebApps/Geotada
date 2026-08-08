import 'package:flutter_test/flutter_test.dart';
import 'package:ondoway/router.dart';

void main() {
  group('computeAuthRedirect', () {
    test(
        'unauthenticated + /debug/location-spike + isDebug:true → null '
        '(the bug: must NOT redirect)', () {
      final result = computeAuthRedirect(
        isAuthenticated: false,
        profileLoaded: false,
        profileIsFirstTime: false,
        path: '/debug/location-spike',
        isDebug: true,
      );
      expect(result, isNull);
    });

    test(
        'unauthenticated + /debug/location-spike + isDebug:false → /login '
        '(release still guards it)', () {
      final result = computeAuthRedirect(
        isAuthenticated: false,
        profileLoaded: false,
        profileIsFirstTime: false,
        path: '/debug/location-spike',
        isDebug: false,
      );
      expect(result, '/login');
    });

    test('unauthenticated + /explore → /login (existing guard preserved)', () {
      final result = computeAuthRedirect(
        isAuthenticated: false,
        profileLoaded: false,
        profileIsFirstTime: false,
        path: '/explore',
        isDebug: true,
      );
      expect(result, '/login');
    });

    test('unauthenticated + /login → null', () {
      final result = computeAuthRedirect(
        isAuthenticated: false,
        profileLoaded: false,
        profileIsFirstTime: false,
        path: '/login',
        isDebug: true,
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
        isDebug: false,
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
        isDebug: false,
      );
      expect(result, '/explore');
    });

    test('authenticated + /login + profileLoaded:false → null', () {
      final result = computeAuthRedirect(
        isAuthenticated: true,
        profileLoaded: false,
        profileIsFirstTime: false,
        path: '/login',
        isDebug: false,
      );
      expect(result, isNull);
    });
  });
}
