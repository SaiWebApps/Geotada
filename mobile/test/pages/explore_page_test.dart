import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:ondoway/pages/explore_page.dart';

Widget _wrapWithRouter() {
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
      await tester.pump();
      await tester.pump();

      expect(find.text('Paris'), findsOneWidget);
      expect(
        find.text('The city of light, scandal, and hidden stories'),
        findsOneWidget,
      );
      expect(find.text('FRANCE'), findsOneWidget);
    });

    testWidgets('tapping Paris navigates to plan-trip', (tester) async {
      await tester.pumpWidget(_wrapWithRouter());
      await tester.pump();
      await tester.pump();

      await tester.tap(find.text('Paris'));
      await tester.pump();
      await tester.pump();

      expect(find.text('Plan trip: paris'), findsOneWidget);
    });

    testWidgets('shows page header and description', (tester) async {
      await tester.pumpWidget(_wrapWithRouter());
      await tester.pump();
      await tester.pump();

      expect(find.text('Explore'), findsOneWidget);
      expect(
        find.text('Choose a city to begin your audio tour'),
        findsOneWidget,
      );
    });
  });
}
