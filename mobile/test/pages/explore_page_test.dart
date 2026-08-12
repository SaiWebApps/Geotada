import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:ondoway/pages/explore_page.dart';
import 'package:ondoway/services/profile_service.dart';
import 'package:ondoway/services/trip_service.dart';
import 'package:ondoway/theme/theme.dart';
import 'package:provider/provider.dart';

Widget _wrap() {
  final client = MockClient((r) async => http.Response('', 200));
  final router = GoRouter(
    initialLocation: '/explore',
    routes: [
      GoRoute(path: '/explore', builder: (c, s) => const ExplorePage()),
      GoRoute(
        path: '/tour-now/:citySlug',
        builder: (c, s) =>
            Scaffold(body: Text('Tour now: ${s.pathParameters['citySlug']}')),
      ),
      GoRoute(
        path: '/plan-trip/:citySlug',
        builder: (c, s) =>
            Scaffold(body: Text('Plan trip: ${s.pathParameters['citySlug']}')),
      ),
    ],
  );
  return MultiProvider(
    providers: [
      ChangeNotifierProvider<ProfileService>.value(
          value: ProfileService(httpClient: client)),
      ChangeNotifierProvider<TripService>.value(
          value: TripService(httpClient: client)),
    ],
    child: MaterialApp.router(
      routerConfig: router,
      theme: buildOndowayTheme(Brightness.light),
    ),
  );
}

void main() {
  group('ExplorePage', () {
    testWidgets('shows the editorial hero (location pill + CTA) and plan card',
        (tester) async {
      await tester.pumpWidget(_wrap());
      await tester.pump();

      expect(find.text('You are in Paris'), findsOneWidget);
      expect(find.text('Take a tour now'), findsOneWidget);
      expect(find.text('Plan a tour for later'), findsOneWidget);
    });

    testWidgets('tapping "Take a tour now" navigates to the immediate tour-now flow',
        (tester) async {
      await tester.pumpWidget(_wrap());
      await tester.pump();

      await tester.tap(find.text('Take a tour now'));
      await tester.pumpAndSettle();

      expect(find.text('Tour now: paris'), findsOneWidget);
    });

    testWidgets('resume card is hidden when there are no saved trips',
        (tester) async {
      await tester.pumpWidget(_wrap());
      await tester.pump();

      // No saved trips -> the "Pick up where you left off" section is omitted.
      expect(find.text('Pick up where you left off'), findsNothing);
    });
  });
}
