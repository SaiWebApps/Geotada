import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:ondoway/models/trip.dart';
import 'package:ondoway/pages/callback_page.dart';
import 'package:ondoway/pages/explore_page.dart';
import 'package:ondoway/pages/lens_selection_page.dart';
import 'package:ondoway/pages/login_page.dart';
import 'package:ondoway/pages/profile_page.dart';
import 'package:ondoway/pages/saved_trips_page.dart';
import 'package:ondoway/pages/style_gallery_page.dart';
import 'package:ondoway/pages/tour_now_page.dart';
import 'package:ondoway/pages/tour_walk_page.dart';
import 'package:ondoway/pages/trip_duration_page.dart';
import 'package:ondoway/pages/trip_itinerary_page.dart';
import 'package:ondoway/services/auth_service.dart';
import 'package:ondoway/services/lens_service.dart';
import 'package:ondoway/services/profile_service.dart';
import 'package:ondoway/spike/location_spike_page.dart';
import 'package:ondoway/spike/tour_playback_proof_page.dart';
import 'package:ondoway/spike/tour_pin_proof_page.dart';
import 'package:ondoway/theme/dims.dart';
import 'package:ondoway/widgets/app_shell.dart';
import 'package:provider/provider.dart';

/// Builds the lens editor (edit mode) shown when a signed-in user edits their
/// preferences from Profile. Pushed as a top-level route (not a tab) so it has
/// a normal back stack and returns to Profile on save/back.
Widget _buildLensEditor(BuildContext context) {
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
      try {
        // For now, re-run onboarding endpoint to replace all preferences
        if (toAdd.isNotEmpty || toRemove.isNotEmpty) {
          await ps.completeOnboarding(
            selectedIds.toList(),
            as_.accessToken!,
            refresh: () async =>
                (await as_.refreshSession()) ? as_.accessToken : null,
          );
        }
        if (!context.mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Lenses saved')),
        );
        // Return to Profile — saving is done, don't strand the user here.
        if (context.canPop()) context.pop();
      } on ProfileServiceException catch (e) {
        if (!context.mounted) return;
        if (e.statusCode == 401 || e.statusCode == 403) {
          // Session is unrecoverable (refresh failed) — back to login.
          await as_.logout();
        } else {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('Could not save — please try again.'),
            ),
          );
        }
      }
    },
  );
}

/// Pure decision function for the router's auth redirect.
///
/// Reproduces the router's auth-gating logic outside of a go_router
/// [GoRouter.redirect] closure so it is unit-testable without constructing
/// real services. Auth routes (`/login`, `/auth`, `/auth/callback`) are
/// always exempt from the "must be authenticated" guard; debug routes
/// (`/debug/...`) are exempt only when [allowDebugRoutes] is true (debug and
/// profile builds, never release), so production behavior is unchanged.
String? computeAuthRedirect({
  required bool isAuthenticated,
  required bool profileLoaded,
  required bool profileIsFirstTime,
  required String path,
  required bool allowDebugRoutes,
}) {
  final isAuthRoute =
      path == '/login' || path == '/auth' || path == '/auth/callback';
  final isExemptDebugRoute = allowDebugRoutes && path.startsWith('/debug/');

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
        // Debug affordances (the location-spike screen) are reachable in debug
        // AND profile builds — profile is what we use for on-device iOS 26
        // testing — but never in release.
        allowDebugRoutes: !kReleaseMode,
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
              try {
                await ps.completeOnboarding(
                  selectedIds.toList(),
                  as_.accessToken!,
                  refresh: () async =>
                      (await as_.refreshSession()) ? as_.accessToken : null,
                );
                if (context.mounted) context.go('/explore');
              } on ProfileServiceException catch (e) {
                if (!context.mounted) return;
                if (e.statusCode == 401 || e.statusCode == 403) {
                  // Session is unrecoverable (refresh failed) — back to login.
                  await as_.logout();
                } else {
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(
                      content: Text('Could not save your lenses — please try again.'),
                    ),
                  );
                }
              }
            },
          );
        },
      ),
      // Full-screen trip planning routes (outside tab shell)
      // Immediate: "Take a tour now" — one question (how long), builds from GPS.
      GoRoute(
        path: '/tour-now/:citySlug',
        builder: (context, state) =>
            TourNowPage(citySlug: state.pathParameters['citySlug'] ?? 'paris'),
      ),
      // Plan for later: dates, start-point picker, multi-day.
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
      // Lens editor (edit mode) — a pushed full-screen route, so Profile's
      // "Edit" gives a real back stack instead of stranding the user in a tab.
      GoRoute(
        path: '/lenses',
        builder: (context, state) => _buildLensEditor(context),
      ),
      GoRoute(
        path: '/trip/:tripId/walk',
        builder: (context, state) {
          // Golden path: "Start walking" pushes here with the already-loaded
          // GeneratedTrip as `extra` — no service round-trip needed.
          final extra = state.extra;
          if (extra is GeneratedTrip) return TourWalkPage(trip: extra);
          // Cold/deep-link entry (no `extra`, e.g. a fresh app launch on this
          // URL): TripService has no fetch-by-id, so there is nothing to hydrate
          // from here. Send the user back to a place they CAN start a walk from.
          return const _TourWalkFallback();
        },
      ),
      GoRoute(
        path: '/debug/location-spike',
        builder: (context, state) => const LocationSpikePage(),
      ),
      GoRoute(
        path: '/debug/tour-playback-proof',
        builder: (context, state) => const TourPlaybackProofPage(),
      ),
      GoRoute(
        path: '/debug/tour-pin-proof',
        builder: (context, state) => const TourPinProofPage(),
      ),
      GoRoute(
        path: '/debug/style-gallery',
        builder: (context, state) => const StyleGalleryPage(),
      ),
      GoRoute(
        // Debug-only design preview: renders ExplorePage inside the shell (so the
        // floating pill nav shows), without the auth gate.
        path: '/debug/explore-preview',
        builder: (context, state) => AppShell(
          currentIndex: 0,
          onTabChanged: (_) {},
          child: const ExplorePage(),
        ),
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

/// Graceful landing for `/trip/:tripId/walk` reached without a trip in hand
/// (a cold start or deep link, not the in-app "Start walking" button). There
/// is no fetch-by-id to hydrate from — `TripService` only generates, composes,
/// and lists saved trips — so this points the user back to a screen that can
/// actually start a walk instead of crashing on a null trip.
class _TourWalkFallback extends StatelessWidget {
  const _TourWalkFallback();

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Walking tour')),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(Dims.spaceLg),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text('Open this walk from your trip'),
              const SizedBox(height: Dims.spaceMd),
              FilledButton(
                onPressed: () => context.go('/saved-trips'),
                child: const Text('Go to your saved trips'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
