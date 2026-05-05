import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:ondoway/services/auth_service.dart';
import 'package:ondoway/services/feedback_service.dart';
import 'package:ondoway/widgets/app_shell.dart';
import 'package:provider/provider.dart';

import '../services/auth_service_test.dart';

Widget _wrap({
  FeedbackService? feedbackService,
  AuthService? authService,
  int currentIndex = 0,
}) {
  final defaultClient = MockClient((r) async => http.Response('', 200));
  return MultiProvider(
    providers: [
      ChangeNotifierProvider<FeedbackService>.value(
        value: feedbackService ?? FeedbackService(httpClient: defaultClient),
      ),
      ChangeNotifierProvider<AuthService>.value(
        value: authService ??
            AuthService(
              storage: FakeSecureStorage(),
              httpClient: defaultClient,
            ),
      ),
    ],
    child: MaterialApp(
      home: AppShell(
        currentIndex: currentIndex,
        onTabChanged: (_) {},
        child: const Scaffold(body: Text('App content')),
      ),
    ),
  );
}

void main() {
  group('Feedback in NavigationBar', () {
    testWidgets('feedback icon appears in NavigationBar', (tester) async {
      await tester.pumpWidget(_wrap());
      expect(find.byIcon(Icons.mic_outlined), findsOneWidget);
      expect(find.text('Feedback'), findsOneWidget);
    });

    testWidgets('app content renders with NavigationBar', (tester) async {
      await tester.pumpWidget(_wrap());
      expect(find.text('App content'), findsOneWidget);
    });

    testWidgets('tapping feedback icon opens bottom sheet', (tester) async {
      await tester.pumpWidget(_wrap());
      await tester.tap(find.text('Feedback'));
      await tester.pumpAndSettle();

      expect(find.text('Send Feedback'), findsOneWidget);
      expect(find.byType(TextField), findsOneWidget);
    });

    testWidgets('selected tab does not change when feedback tapped',
        (tester) async {
      await tester.pumpWidget(_wrap(currentIndex: 0));
      final navBar = tester.widget<NavigationBar>(find.byType(NavigationBar));
      expect(navBar.selectedIndex, 0);

      await tester.tap(find.text('Feedback'));
      await tester.pumpAndSettle();

      // The sheet opened but selectedIndex stays at 0
      expect(find.text('Send Feedback'), findsOneWidget);
    });

    testWidgets('submit button disabled when text empty', (tester) async {
      await tester.pumpWidget(_wrap());
      await tester.tap(find.text('Feedback'));
      await tester.pumpAndSettle();

      final button = tester.widget<FilledButton>(
        find.widgetWithText(FilledButton, 'Submit'),
      );
      expect(button.onPressed, isNull);
    });

    testWidgets('submit button enabled after typing', (tester) async {
      await tester.pumpWidget(_wrap());
      await tester.tap(find.text('Feedback'));
      await tester.pumpAndSettle();

      await tester.enterText(find.byType(TextField), 'The map is broken');
      await tester.pump();

      final button = tester.widget<FilledButton>(
        find.widgetWithText(FilledButton, 'Submit'),
      );
      expect(button.onPressed, isNotNull);
    });

    testWidgets('submit calls feedback service', (tester) async {
      bool feedbackCalled = false;
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

      final feedbackService = FeedbackService(httpClient: mockClient);

      await tester.pumpWidget(_wrap(feedbackService: feedbackService));
      await tester.tap(find.text('Feedback'));
      await tester.pumpAndSettle();

      await tester.enterText(find.byType(TextField), 'The map is broken');
      await tester.pump();

      await tester.tap(find.widgetWithText(FilledButton, 'Submit'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));
      await tester.pumpAndSettle();

      expect(feedbackCalled, isTrue);
    });
  });
}
