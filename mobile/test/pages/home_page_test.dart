import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:ondoway/pages/profile_page.dart';
import 'package:ondoway/services/auth_service.dart';
import 'package:ondoway/services/lens_service.dart';
import 'package:ondoway/services/profile_service.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'dart:convert';
import '../services/auth_service_test.dart';

Widget _wrapProfilePage({
  required AuthService authService,
  ProfileService? profileService,
  LensService? lensService,
}) {
  final client = MockClient((r) async => http.Response('', 200));
  return MaterialApp(
    home: Scaffold(
      body: MultiProvider(
        providers: [
          ChangeNotifierProvider<AuthService>.value(value: authService),
          ChangeNotifierProvider<ProfileService>.value(
            value: profileService ?? ProfileService(httpClient: client),
          ),
          ChangeNotifierProvider<LensService>.value(
            value: lensService ?? LensService(httpClient: client),
          ),
        ],
        child: const ProfilePage(),
      ),
    ),
  );
}

void main() {
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
        _wrapProfilePage(authService: authService),
      );

      expect(find.text('demo@ondoway.app'), findsOneWidget);
    });

    testWidgets('has logout button', (tester) async {
      final authService = AuthService(
        storage: FakeSecureStorage(),
        httpClient: MockClient((r) async => http.Response('', 200)),
      );

      await tester.pumpWidget(
        _wrapProfilePage(authService: authService),
      );

      // Logout sits at the bottom of the scrolling profile list; scroll to it.
      await tester.scrollUntilVisible(
        find.byIcon(Icons.logout),
        300,
        scrollable: find.byType(Scrollable),
      );
      expect(find.byIcon(Icons.logout), findsOneWidget);
    });

    testWidgets('shows display name when loaded', (tester) async {
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
        if (request.url.path.contains('onboarding')) {
          return http.Response(
            jsonEncode({
              'profile_id': 'p1',
              'display_name': 'Demo User',
              'lens_count': 3,
            }),
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

      final profileService = ProfileService(httpClient: mockClient);
      await profileService.completeOnboarding(['a', 'b', 'c'], 'tok');

      await tester.pumpWidget(
        _wrapProfilePage(
          authService: authService,
          profileService: profileService,
        ),
      );

      expect(find.text('Demo User'), findsOneWidget);
    });

    testWidgets('shows selected lenses as chips', (tester) async {
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
        if (request.url.path.contains('onboarding')) {
          return http.Response(
            jsonEncode({
              'profile_id': 'p1',
              'display_name': 'Demo',
              'lens_count': 1,
            }),
            200,
          );
        }
        if (request.url.path.endsWith('/lenses')) {
          return http.Response(
            jsonEncode([
              {
                'id': 'parent1',
                'name': 'history',
                'display_label': 'History',
                'is_parent': true,
                'children': [
                  {
                    'id': 'lens1',
                    'name': 'dark_history',
                    'display_label': 'Dark History',
                    'is_parent': false,
                  },
                ],
              },
            ]),
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

      final profileService = ProfileService(httpClient: mockClient);
      await profileService.completeOnboarding(['lens1'], 'tok');

      final lensService = LensService(httpClient: mockClient);
      await lensService.fetchLenses();

      await tester.pumpWidget(
        _wrapProfilePage(
          authService: authService,
          profileService: profileService,
          lensService: lensService,
        ),
      );

      expect(find.text('Dark History'), findsOneWidget);
      expect(find.byType(Chip), findsOneWidget);
    });

    testWidgets('shows theme toggle with system selected by default', (tester) async {
      final authService = AuthService(
        storage: FakeSecureStorage(),
        httpClient: MockClient((r) async => http.Response('', 200)),
      );

      await tester.pumpWidget(
        _wrapProfilePage(authService: authService),
      );

      expect(find.byType(SegmentedButton<String>), findsOneWidget);
      expect(find.text('System'), findsOneWidget);
      expect(find.text('Light'), findsOneWidget);
      expect(find.text('Dark'), findsOneWidget);
    });

    testWidgets('theme toggle reflects stored preference', (tester) async {
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
        if (request.url.path.endsWith('/profile')) {
          return http.Response(
            jsonEncode({
              'profile_id': 'profile-1',
              'display_name': 'Demo',
              'selected_lens_ids': ['lens-1'],
              'theme_preference': 'dark',
            }),
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

      final profileService = ProfileService(httpClient: mockClient);
      await profileService.fetchProfile('tok');

      await tester.pumpWidget(
        _wrapProfilePage(
          authService: authService,
          profileService: profileService,
        ),
      );

      // The SegmentedButton should show 'dark' as selected
      final segmented = tester.widget<SegmentedButton<String>>(
        find.byType(SegmentedButton<String>),
      );
      expect(segmented.selected, {'dark'});
    });

    testWidgets('tapping light segment triggers update', (tester) async {
      String? capturedBody;
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
        if (request.url.path.endsWith('/profile')) {
          return http.Response(
            jsonEncode({
              'profile_id': 'profile-1',
              'display_name': 'Demo',
              'selected_lens_ids': ['lens-1'],
              'theme_preference': 'system',
            }),
            200,
          );
        }
        if (request.url.path.contains('/nodes/Profile/') && request.method == 'PUT') {
          capturedBody = request.body;
          return http.Response(
            jsonEncode({
              'id': 'profile-1',
              'labels': ['Profile'],
              'properties': {'display_name': 'Demo', 'theme_preference': 'light'},
            }),
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

      final profileService = ProfileService(httpClient: mockClient);
      await profileService.fetchProfile('tok');

      await tester.pumpWidget(
        _wrapProfilePage(
          authService: authService,
          profileService: profileService,
        ),
      );

      // Tap the 'Light' segment
      await tester.tap(find.text('Light'));
      await tester.pump();
      await tester.pump();

      expect(capturedBody, isNotNull);
      expect(capturedBody, contains('theme_preference'));
      expect(capturedBody, contains('light'));
    });

    testWidgets('display name edit shows TextField on tap', (tester) async {
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
        if (request.url.path.contains('onboarding')) {
          return http.Response(
            jsonEncode({
              'profile_id': 'p1',
              'display_name': 'Demo User',
              'lens_count': 1,
            }),
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

      final profileService = ProfileService(httpClient: mockClient);
      await profileService.completeOnboarding(['lens1'], 'tok');

      await tester.pumpWidget(
        _wrapProfilePage(
          authService: authService,
          profileService: profileService,
        ),
      );

      // Verify the display name is shown
      expect(find.text('Demo User'), findsOneWidget);

      // Tap the edit icon to enter editing mode
      await tester.tap(find.byIcon(Icons.edit_outlined));
      await tester.pump();
      await tester.pump();

      // TextField should now appear
      expect(find.byType(TextField), findsOneWidget);
    });

    testWidgets('display name edit saves on submit', (tester) async {
      String? capturedPutBody;
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
        if (request.url.path.endsWith('/profile')) {
          return http.Response(
            jsonEncode({
              'profile_id': 'profile-1',
              'display_name': 'Demo User',
              'selected_lens_ids': <String>[],
              'theme_preference': 'system',
            }),
            200,
          );
        }
        if (request.url.path.contains('/nodes/Profile/') && request.method == 'PUT') {
          capturedPutBody = request.body;
          return http.Response(
            jsonEncode({
              'id': 'profile-1',
              'labels': ['Profile'],
              'properties': {'display_name': 'New Name', 'theme_preference': 'system'},
            }),
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

      final profileService = ProfileService(httpClient: mockClient);
      await profileService.fetchProfile('tok');

      await tester.pumpWidget(
        _wrapProfilePage(
          authService: authService,
          profileService: profileService,
        ),
      );

      // Tap edit icon (use .first in case of multiple matches from rebuild)
      await tester.tap(find.byIcon(Icons.edit_outlined).first);
      await tester.pump();
      await tester.pump();

      // Clear the text field and enter new name
      final textField = find.byType(TextField);
      expect(textField, findsOneWidget);
      await tester.enterText(textField, 'New Name');

      // Submit by pressing the check icon
      await tester.tap(find.byIcon(Icons.check).first);
      await tester.pump();
      await tester.pump();

      // Verify PUT was called with the new name
      expect(capturedPutBody, isNotNull);
      expect(capturedPutBody, contains('display_name'));
      expect(capturedPutBody, contains('New Name'));
    });
  });
}
