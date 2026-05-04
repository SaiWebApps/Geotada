import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:ondoway/pages/explore_page.dart';
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
  group('ExplorePage', () {
    testWidgets('shows Paris city card', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: const ExplorePage(),
          theme: ThemeData(
            colorSchemeSeed: const Color(0xFF3D5AFE),
            useMaterial3: true,
            brightness: Brightness.dark,
          ),
        ),
      );
      expect(find.text('Paris'), findsOneWidget);
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
        if (request.url.path.contains('/nodes/Lens')) {
          return http.Response(
            jsonEncode({
              'items': [
                {
                  'id': 'lens1',
                  'labels': ['Lens'],
                  'properties': {
                    'id': 'lens1',
                    'name': 'dark_history',
                    'display_label': 'Dark History',
                    'is_parent': false,
                  },
                },
              ],
              'total': 1,
              'skip': 0,
              'limit': 200,
            }),
            200,
          );
        }
        if (request.url.path.contains('/edges/IS_PARENT_OF')) {
          return http.Response(
            jsonEncode({'items': [], 'total': 0, 'skip': 0, 'limit': 200}),
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
        if (request.url.path.contains('/edges/HAS_PROFILE')) {
          return http.Response(
            jsonEncode({
              'items': [
                {'id': 'e1', 'type': 'HAS_PROFILE', 'source_id': 'user-1', 'target_id': 'profile-1', 'properties': {}}
              ],
              'total': 1, 'skip': 0, 'limit': 10,
            }),
            200,
          );
        }
        if (request.url.path.contains('/nodes/Profile/')) {
          return http.Response(
            jsonEncode({
              'id': 'profile-1',
              'labels': ['Profile'],
              'properties': {'display_name': 'Demo', 'theme_preference': 'dark'},
            }),
            200,
          );
        }
        if (request.url.path.contains('/edges/PREFERS_LENS')) {
          return http.Response(
            jsonEncode({
              'items': [
                {'id': 'e-l1', 'type': 'PREFERS_LENS', 'source_id': 'profile-1', 'target_id': 'lens-1', 'properties': {}}
              ],
              'total': 1, 'skip': 0, 'limit': 200,
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
      await profileService.fetchProfile('user-1', 'tok');

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
        if (request.url.path.contains('/edges/HAS_PROFILE')) {
          return http.Response(
            jsonEncode({
              'items': [
                {'id': 'e1', 'type': 'HAS_PROFILE', 'source_id': 'user-1', 'target_id': 'profile-1', 'properties': {}}
              ],
              'total': 1, 'skip': 0, 'limit': 10,
            }),
            200,
          );
        }
        if (request.url.path.contains('/nodes/Profile/') && request.method == 'GET') {
          return http.Response(
            jsonEncode({
              'id': 'profile-1',
              'labels': ['Profile'],
              'properties': {'display_name': 'Demo', 'theme_preference': 'system'},
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
        if (request.url.path.contains('/edges/PREFERS_LENS')) {
          return http.Response(
            jsonEncode({
              'items': [
                {'id': 'e-l1', 'type': 'PREFERS_LENS', 'source_id': 'profile-1', 'target_id': 'lens-1', 'properties': {}}
              ],
              'total': 1, 'skip': 0, 'limit': 200,
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
      await profileService.fetchProfile('user-1', 'tok');

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
        if (request.url.path.contains('/edges/HAS_PROFILE')) {
          return http.Response(
            jsonEncode({
              'items': [
                {'id': 'e1', 'type': 'HAS_PROFILE', 'source_id': 'user-1', 'target_id': 'profile-1', 'properties': {}}
              ],
              'total': 1, 'skip': 0, 'limit': 10,
            }),
            200,
          );
        }
        if (request.url.path.contains('/nodes/Profile/') && request.method == 'GET') {
          return http.Response(
            jsonEncode({
              'id': 'profile-1',
              'labels': ['Profile'],
              'properties': {'display_name': 'Demo User', 'theme_preference': 'system'},
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
        if (request.url.path.contains('/edges/PREFERS_LENS')) {
          return http.Response(
            jsonEncode({
              'items': [],
              'total': 0, 'skip': 0, 'limit': 200,
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
      await profileService.fetchProfile('user-1', 'tok');

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
