import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:provider/provider.dart';
import 'package:ondoway/main.dart';
import 'package:ondoway/router.dart';
import 'package:ondoway/services/auth_service.dart';
import 'package:ondoway/services/lens_service.dart';
import 'package:ondoway/services/profile_service.dart';
import 'services/auth_service_test.dart';

void main() {
  testWidgets('OndowayApp renders login page when unauthenticated', (tester) async {
    final mockClient = MockClient((r) async => http.Response('', 200));
    final authService = AuthService(
      storage: FakeSecureStorage(),
      httpClient: mockClient,
    );
    final profileService = ProfileService(httpClient: mockClient);
    final lensService = LensService(httpClient: mockClient);
    final router = createRouter(authService, profileService, lensService);

    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider<AuthService>.value(value: authService),
          ChangeNotifierProvider<LensService>.value(value: lensService),
          ChangeNotifierProvider<ProfileService>.value(value: profileService),
        ],
        child: OndowayApp(router: router),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Ondoway'), findsOneWidget);
  });
}
