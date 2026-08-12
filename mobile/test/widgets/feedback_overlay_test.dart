import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:ondoway/services/auth_service.dart';
import 'package:ondoway/services/feedback_service.dart';
import 'package:ondoway/theme/theme.dart';
import 'package:ondoway/widgets/app_shell.dart';
import 'package:ondoway/widgets/feedback_overlay.dart';
import 'package:provider/provider.dart';

import '../services/auth_service_test.dart';

/// Renders a button that opens the FeedbackSheet in a modal — the same way
/// Profile's "Send feedback" tile now surfaces it (feedback moved out of the
/// nav when the nav dropped to Explore/Trips/Profile).
Widget _wrap({FeedbackService? feedbackService, AuthService? authService}) {
  final defaultClient = MockClient((r) async => http.Response('', 200));
  return MultiProvider(
    providers: [
      ChangeNotifierProvider<FeedbackService>.value(
        value: feedbackService ?? FeedbackService(httpClient: defaultClient),
      ),
      ChangeNotifierProvider<AuthService>.value(
        value: authService ??
            AuthService(storage: FakeSecureStorage(), httpClient: defaultClient),
      ),
    ],
    child: MaterialApp(
      theme: buildOndowayTheme(Brightness.light),
      home: Scaffold(
        body: Builder(
          builder: (ctx) => Center(
            child: ElevatedButton(
              onPressed: () => showModalBottomSheet<void>(
                context: ctx,
                isScrollControlled: true,
                useSafeArea: true,
                builder: (_) => const FeedbackSheet(),
              ),
              child: const Text('open feedback'),
            ),
          ),
        ),
      ),
    ),
  );
}

Future<void> _openSheet(WidgetTester tester) async {
  await tester.tap(find.text('open feedback'));
  await tester.pumpAndSettle();
}

void main() {
  group('FeedbackSheet', () {
    testWidgets('opening shows the sheet with a text field', (tester) async {
      await tester.pumpWidget(_wrap());
      await _openSheet(tester);
      expect(find.text('Send Feedback'), findsOneWidget);
      expect(find.byType(TextField), findsOneWidget);
    });

    testWidgets('submit button disabled when text empty', (tester) async {
      await tester.pumpWidget(_wrap());
      await _openSheet(tester);
      final button = tester.widget<FilledButton>(
        find.widgetWithText(FilledButton, 'Submit'),
      );
      expect(button.onPressed, isNull);
    });

    testWidgets('submit button enabled after typing', (tester) async {
      await tester.pumpWidget(_wrap());
      await _openSheet(tester);
      await tester.enterText(find.byType(TextField), 'The map is broken');
      await tester.pump();
      final button = tester.widget<FilledButton>(
        find.widgetWithText(FilledButton, 'Submit'),
      );
      expect(button.onPressed, isNotNull);
    });

    testWidgets('submit calls feedback service', (tester) async {
      var feedbackCalled = false;
      final mockClient = MockClient((request) async {
        if (request.url.path.contains('/feedback')) {
          feedbackCalled = true;
          return http.Response(
            jsonEncode({
              'issue_url': 'https://github.com/SaiWebApps/Ondoway/issues/42',
              'issue_number': 42,
              'title': '[Bug] Map is broken',
            }),
            201,
          );
        }
        return http.Response('', 404);
      });

      await tester
          .pumpWidget(_wrap(feedbackService: FeedbackService(httpClient: mockClient)));
      await _openSheet(tester);
      await tester.enterText(find.byType(TextField), 'The map is broken');
      await tester.pump();
      await tester.tap(find.widgetWithText(FilledButton, 'Submit'));
      await tester.pump(const Duration(milliseconds: 100));
      await tester.pumpAndSettle();

      expect(feedbackCalled, isTrue);
    });
  });

  group('AppShell floating nav', () {
    testWidgets('shows Explore/Trips/Profile and no Feedback item',
        (tester) async {
      await tester.pumpWidget(MaterialApp(
        theme: buildOndowayTheme(Brightness.light),
        home: AppShell(
          currentIndex: 0,
          onTabChanged: (_) {},
          child: const Scaffold(body: Text('content')),
        ),
      ));

      expect(find.text('Explore'), findsOneWidget); // active pill label
      expect(find.byIcon(Icons.map_outlined), findsOneWidget); // Trips
      expect(find.byIcon(Icons.person_outline), findsOneWidget); // Profile
      expect(find.text('Feedback'), findsNothing);
      expect(find.byIcon(Icons.mic_outlined), findsNothing);
    });

    testWidgets('tapping a nav item reports its branch index', (tester) async {
      int? tapped;
      await tester.pumpWidget(MaterialApp(
        theme: buildOndowayTheme(Brightness.light),
        home: AppShell(
          currentIndex: 0,
          onTabChanged: (i) => tapped = i,
          child: const Scaffold(body: Text('content')),
        ),
      ));

      await tester.tap(find.byIcon(Icons.person_outline)); // Profile -> branch 2
      expect(tapped, 2);
    });
  });
}
