import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:ondoway/pages/explore_page.dart';
import 'package:ondoway/pages/profile_page.dart';
import 'package:ondoway/services/auth_service.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'dart:convert';
import '../services/auth_service_test.dart';

void main() {
  group('ExplorePage', () {
    testWidgets('shows placeholder message', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(home: ExplorePage()),
      );
      expect(find.text('Your first tour starts here'), findsOneWidget);
    });
  });

  group('ProfilePage', () {
    testWidgets('shows email when authenticated', (tester) async {
      final mockClient = MockClient((request) async {
        if (request.url.path.contains('verify')) {
          return http.Response(
            jsonEncode({
              'access_token': 'tok',
              'refresh_token': 'ref',
              'token_type': 'bearer',
            }),
            200,
          );
        }
        if (request.url.path.contains('/me')) {
          return http.Response(
            jsonEncode({'id': '1', 'email': 'demo@ondoway.app'}),
            200,
          );
        }
        return http.Response('', 404);
      });

      final authService = AuthService(
        storage: FakeSecureStorage(),
        httpClient: mockClient,
      );

      await authService.verifyMagicLink('tok');

      await tester.pumpWidget(
        MaterialApp(
          home: ChangeNotifierProvider<AuthService>.value(
            value: authService,
            child: const ProfilePage(),
          ),
        ),
      );

      expect(find.text('demo@ondoway.app'), findsOneWidget);
    });

    testWidgets('has logout button', (tester) async {
      final authService = AuthService(
        storage: FakeSecureStorage(),
        httpClient: MockClient((r) async => http.Response('', 200)),
      );

      await tester.pumpWidget(
        MaterialApp(
          home: ChangeNotifierProvider<AuthService>.value(
            value: authService,
            child: const ProfilePage(),
          ),
        ),
      );

      expect(find.byIcon(Icons.logout), findsOneWidget);
    });
  });
}
