import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:ondoway/pages/login_page.dart';
import 'package:ondoway/services/auth_service.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import '../services/auth_service_test.dart';

Widget _wrapWithProviders(Widget child, {AuthService? authService}) {
  final service = authService ??
      AuthService(
        storage: FakeSecureStorage(),
        httpClient: MockClient((r) async => http.Response('', 200)),
      );

  return MaterialApp(
    home: ChangeNotifierProvider<AuthService>.value(
      value: service,
      child: child,
    ),
  );
}

void main() {
  group('LoginPage', () {
    testWidgets('renders email field and both buttons', (tester) async {
      await tester.pumpWidget(_wrapWithProviders(const LoginPage()));

      expect(find.text('Email address'), findsOneWidget);
      expect(find.text('Send Magic Link'), findsOneWidget);
      expect(find.text('Sign in with Google'), findsOneWidget);
    });

    testWidgets('shows validation error on empty email submit', (tester) async {
      await tester.pumpWidget(_wrapWithProviders(const LoginPage()));

      await tester.tap(find.text('Send Magic Link'));
      await tester.pumpAndSettle();

      expect(find.text('Please enter your email'), findsOneWidget);
    });

    testWidgets('shows validation error on invalid email', (tester) async {
      await tester.pumpWidget(_wrapWithProviders(const LoginPage()));

      await tester.enterText(find.byType(TextFormField), 'not-an-email');
      await tester.tap(find.text('Send Magic Link'));
      await tester.pumpAndSettle();

      expect(find.text('Please enter a valid email'), findsOneWidget);
    });

    testWidgets('shows check email screen after successful submit', (tester) async {
      final mockClient = MockClient((request) async {
        return http.Response('{"message":"Magic link sent"}', 200);
      });

      final authService = AuthService(
        storage: FakeSecureStorage(),
        httpClient: mockClient,
      );

      await tester.pumpWidget(_wrapWithProviders(const LoginPage(), authService: authService));

      await tester.enterText(find.byType(TextFormField), 'test@ondoway.app');
      await tester.tap(find.text('Send Magic Link'));
      await tester.pumpAndSettle();

      expect(find.text('Check your email'), findsOneWidget);
      expect(find.textContaining('test@ondoway.app'), findsOneWidget);
    });

    testWidgets('shows Ondoway branding', (tester) async {
      await tester.pumpWidget(_wrapWithProviders(const LoginPage()));

      expect(find.text('Ondoway'), findsOneWidget);
      expect(find.text('Your city, your story'), findsOneWidget);
    });
  });
}
