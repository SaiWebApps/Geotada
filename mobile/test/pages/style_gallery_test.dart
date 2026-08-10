import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:ondoway/main.dart';
import 'package:ondoway/pages/style_gallery_page.dart';
import 'package:ondoway/router.dart';
import 'package:ondoway/services/auth_service.dart';
import 'package:ondoway/services/feedback_service.dart';
import 'package:ondoway/services/lens_service.dart';
import 'package:ondoway/services/profile_service.dart';
import 'package:ondoway/theme/theme.dart';
import 'package:provider/provider.dart';
import '../services/auth_service_test.dart';

void main() {
  testWidgets('gallery builds and shows a component sample', (tester) async {
    await tester.pumpWidget(MaterialApp(
      theme: buildOndowayTheme(Brightness.light),
      home: const StyleGalleryPage(),
    ));
    expect(find.text('Preparing'), findsWidgets); // PrepareStrip present
    expect(find.byType(Card), findsWidgets);
  });

  testWidgets(
      'the real router resolves /debug/style-gallery to StyleGalleryPage '
      '(the GoRoute exists and is reachable in debug)', (tester) async {
    final mockClient = MockClient((r) async => http.Response('', 200));
    final authService = AuthService(
      storage: FakeSecureStorage(),
      httpClient: mockClient,
    );
    final profileService = ProfileService(httpClient: mockClient);
    final lensService = LensService(httpClient: mockClient);
    final feedbackService = FeedbackService(httpClient: mockClient);
    final router = createRouter(authService, profileService, lensService);

    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider<AuthService>.value(value: authService),
          ChangeNotifierProvider<LensService>.value(value: lensService),
          ChangeNotifierProvider<ProfileService>.value(value: profileService),
          ChangeNotifierProvider<FeedbackService>.value(value: feedbackService),
        ],
        child: OndowayApp(router: router),
      ),
    );
    await tester.pumpAndSettle();

    // kReleaseMode is false under the test harness, so allowDebugRoutes is true
    // and the unauthenticated guard does not redirect this debug route away.
    router.go('/debug/style-gallery');
    await tester.pumpAndSettle();

    expect(find.byType(StyleGalleryPage), findsOneWidget);
  });
}
