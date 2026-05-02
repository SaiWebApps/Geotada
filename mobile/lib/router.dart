import 'package:go_router/go_router.dart';
import 'package:ondoway/pages/callback_page.dart';
import 'package:ondoway/pages/home_page.dart';
import 'package:ondoway/pages/login_page.dart';
import 'package:ondoway/services/auth_service.dart';

GoRouter createRouter(AuthService authService) {
  return GoRouter(
    initialLocation: '/login',
    redirect: (context, state) {
      final isAuthenticated = authService.isAuthenticated;
      final isLoggingIn = state.matchedLocation == '/login';
      final isCallback = state.matchedLocation == '/auth/callback' ||
          state.matchedLocation == '/auth';

      if (!isAuthenticated && !isLoggingIn && !isCallback) {
        return '/login';
      }
      if (isAuthenticated && isLoggingIn) {
        return '/home';
      }
      return null;
    },
    routes: [
      GoRoute(
        path: '/login',
        builder: (context, state) => const LoginPage(),
      ),
      GoRoute(
        path: '/auth',
        builder: (context, state) {
          final token = state.uri.queryParameters['token'] ?? '';
          return CallbackPage(token: token);
        },
      ),
      GoRoute(
        path: '/auth/callback',
        builder: (context, state) {
          final token = state.uri.queryParameters['token'] ?? '';
          return CallbackPage(token: token);
        },
      ),
      GoRoute(
        path: '/home',
        builder: (context, state) => const HomePage(),
      ),
    ],
  );
}
