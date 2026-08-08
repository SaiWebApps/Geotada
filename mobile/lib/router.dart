import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:ondoway/pages/callback_page.dart';
import 'package:ondoway/pages/explore_page.dart';
import 'package:ondoway/pages/lens_selection_page.dart';
import 'package:ondoway/pages/login_page.dart';
import 'package:ondoway/pages/profile_page.dart';
import 'package:ondoway/pages/saved_trips_page.dart';
import 'package:ondoway/pages/trip_duration_page.dart';
import 'package:ondoway/pages/trip_itinerary_page.dart';
import 'package:ondoway/services/auth_service.dart';
import 'package:ondoway/services/lens_service.dart';
import 'package:ondoway/services/profile_service.dart';
import 'package:ondoway/spike/location_spike_page.dart';
import 'package:ondoway/widgets/app_shell.dart';
import 'package:provider/provider.dart';

final _shellNavigatorKey = GlobalKey<NavigatorState>();

/// Pure decision function for the router's auth redirect.
///
/// Reproduces the router's auth-gating logic outside of a go_router
/// [GoRouter.redirect] closure so it is unit-testable without constructing
/// real services. Auth routes (`/login`, `/auth`, `/auth/callback`) are
/// always exempt from the "must be authenticated" guard; debug routes
/// (`/debug/...`) are exempt only when [isDebug] is true, so production
/// behavior is unchanged.
String? computeAuthRedirect({
  required bool isAuthenticated,
  required bool profileLoaded,
  required bool profileIsFirstTime,
  required String path,
  required bool isDebug,
}) {
  final isAuthRoute =
      path == '/login' || path == '/auth' || path == '/auth/callback';
  final isExemptDebugRoute = isDebug && path.startsWith('/debug/');

  if (!isAuthenticated && !isAuthRoute && !isExemptDebugRoute) {
    return '/login';
  }

  if (isAuthenticated && path == '/login') {
    if (!profileLoaded) return null;
    return profileIsFirstTime ? '/onboarding' : '/explore';
  }

  return null;
}

GoRouter createRouter(
  AuthService authService,
  ProfileService profileService,
  LensService lensService,
) {
  return GoRouter(
    initialLocation: '/login',
    refreshListenable: authService,
    redirect: (context, state) {
      return computeAuthRedirect(
        isAuthenticated: authService.isAuthenticated,
        profileLoaded: profileService.isLoaded,
        profileIsFirstTime: profileService.isFirstTime,
        path: state.matchedLocation,
        isDebug: kDebugMode,
      );
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
        path: '/onboarding',
        builder: (context, state) {
          final ls = context.read<LensService>();
          final ps = context.read<ProfileService>();
          final as_ = context.read<AuthService>();
          return LensSelectionPage(
            isOnboarding: true,
            userName: as_.userEmail?.split('@')[0],
            lensesByParent: ls.childrenByParent,
            onComplete: (selectedIds) async {
              await ps.completeOnboarding(
                selectedIds.toList(),
                as_.accessToken!,
              );
              if (context.mounted) context.go('/explore');
            },
          );
        },
      ),
      // Full-screen trip planning routes (outside tab shell)
      GoRoute(
        path: '/plan-trip/:citySlug',
        builder: (context, state) {
          final citySlug = state.pathParameters['citySlug'] ?? 'paris';
          return TripDurationPage(citySlug: citySlug);
        },
      ),
      GoRoute(
        path: '/trip/:tripId',
        builder: (context, state) {
          final tripId = state.pathParameters['tripId'] ?? '';
          return TripItineraryPage(tripId: tripId);
        },
      ),
      GoRoute(
        path: '/debug/location-spike',
        builder: (context, state) => const LocationSpikePage(),
      ),
      StatefulShellRoute.indexedStack(
        builder: (context, state, navigationShell) {
          return AppShell(
            currentIndex: navigationShell.currentIndex,
            onTabChanged: (index) => navigationShell.goBranch(index),
            child: navigationShell,
          );
        },
        branches: [
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/explore',
                builder: (context, state) => const ExplorePage(),
              ),
            ],
          ),
          StatefulShellBranch(
            navigatorKey: _shellNavigatorKey,
            routes: [
              GoRoute(
                path: '/lenses',
                builder: (context, state) {
                  final ls = context.read<LensService>();
                  final ps = context.read<ProfileService>();
                  final as_ = context.read<AuthService>();
                  return LensSelectionPage(
                    isOnboarding: false,
                    lensesByParent: ls.childrenByParent,
                    initialSelection: ps.selectedLensIds.toSet(),
                    onSave: (selectedIds) async {
                      final current = ps.selectedLensIds.toSet();
                      final toAdd = selectedIds.difference(current);
                      final toRemove = current.difference(selectedIds);
                      // For now, re-run onboarding endpoint to replace all preferences
                      if (toAdd.isNotEmpty || toRemove.isNotEmpty) {
                        await ps.completeOnboarding(
                          selectedIds.toList(),
                          as_.accessToken!,
                        );
                      }
                      if (context.mounted) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(content: Text('Lenses saved')),
                        );
                      }
                    },
                  );
                },
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/saved-trips',
                builder: (context, state) => const SavedTripsPage(),
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/profile',
                builder: (context, state) => const ProfilePage(),
              ),
            ],
          ),
        ],
      ),
    ],
  );
}
