import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:ondoway/pages/explore_page.dart';

Widget _wrapWithRouter({String? lastPushedRoute}) {
  final router = GoRouter(
    initialLocation: '/explore',
    routes: [
      GoRoute(
        path: '/explore',
        builder: (context, state) => const ExplorePage(),
      ),
      GoRoute(
        path: '/plan-trip/:citySlug',
        builder: (context, state) => Scaffold(
          body: Text('Plan trip: ${state.pathParameters['citySlug']}'),
        ),
      ),
    ],
  );
  return MaterialApp.router(
    routerConfig: router,
    theme: ThemeData(
      colorSchemeSeed: const Color(0xFF3D5AFE),
      useMaterial3: true,
      brightness: Brightness.dark,
    ),
  );
}

void main() {
  group('ExplorePage', () {
    testWidgets('shows Paris city card', (tester) async {
      await tester.pumpWidget(_wrapWithRouter());
      await tester.pumpAndSettle();

      expect(find.text('Paris'), findsOneWidget);
      expect(
        find.text('The city of light, scandal, and hidden stories'),
        findsOneWidget,
      );
      expect(find.text('France'), findsOneWidget);
    });

    testWidgets('greyed-out cities show Coming soon', (tester) async {
      await tester.pumpWidget(_wrapWithRouter());
      await tester.pumpAndSettle();

      expect(find.text('London'), findsOneWidget);
      expect(find.text('Tokyo'), findsOneWidget);
      // Both should display "Coming soon"
      expect(find.text('Coming soon'), findsNWidgets(2));
    });

    testWidgets('tapping Paris navigates to plan-trip', (tester) async {
      await tester.pumpWidget(_wrapWithRouter());
      await tester.pumpAndSettle();

      // Find and tap the Paris card
      await tester.tap(find.text('Paris'));
      await tester.pumpAndSettle();

      // Should navigate to plan-trip page
      expect(find.text('Plan trip: paris'), findsOneWidget);
    });

    testWidgets('tapping London does not navigate', (tester) async {
      await tester.pumpWidget(_wrapWithRouter());
      await tester.pumpAndSettle();

      await tester.tap(find.text('London'));
      await tester.pumpAndSettle();

      // Should still be on explore page
      expect(find.text('Explore'), findsOneWidget);
      expect(find.text('Paris'), findsOneWidget);
    });

    testWidgets('shows page header and description', (tester) async {
      await tester.pumpWidget(_wrapWithRouter());
      await tester.pumpAndSettle();

      expect(find.text('Explore'), findsOneWidget);
      expect(
        find.text('Choose a city to begin your audio tour'),
        findsOneWidget,
      );
    });
  });
}
