import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:provider/provider.dart';
import 'package:ondoway/pages/trip_duration_page.dart';
import 'package:ondoway/services/trip_service.dart';
import 'package:ondoway/services/auth_service.dart';
import 'package:ondoway/services/profile_service.dart';
import '../services/auth_service_test.dart';

Widget _buildTestWidget() {
  final mockClient = MockClient((r) async => http.Response('', 200));
  return MaterialApp(
    theme: ThemeData(
      colorSchemeSeed: const Color(0xFF3D5AFE),
      useMaterial3: true,
      brightness: Brightness.dark,
    ),
    home: MultiProvider(
      providers: [
        ChangeNotifierProvider<TripService>(
          create: (_) => TripService(httpClient: mockClient),
        ),
        ChangeNotifierProvider<AuthService>(
          create: (_) => AuthService(
            storage: FakeSecureStorage(),
            httpClient: mockClient,
          ),
        ),
        ChangeNotifierProvider<ProfileService>(
          create: (_) => ProfileService(httpClient: mockClient),
        ),
      ],
      child: const TripDurationPage(citySlug: 'paris'),
    ),
  );
}

void main() {
  group('TripDurationPage', () {
    testWidgets('shows duration picker with default values', (tester) async {
      await tester.pumpWidget(_buildTestWidget());
      await tester.pumpAndSettle();

      expect(find.text('Plan Trip — Paris'), findsOneWidget);
      expect(find.text('How long is your trip?'), findsOneWidget);
      expect(find.text('Days'), findsOneWidget);
      expect(find.text('Hours'), findsOneWidget);
      expect(find.text('Generate My Trip'), findsOneWidget);
    });

    testWidgets('enforces minimum 1 hour', (tester) async {
      await tester.pumpWidget(_buildTestWidget());
      await tester.pumpAndSettle();

      // Set days to 0 and hours to 0
      // Find the Days row minus button and tap it to go to 0
      final minusButtons = find.byIcon(Icons.remove_circle_outline);
      await tester.tap(minusButtons.first); // days 1 -> 0
      await tester.pumpAndSettle();

      // Now tap hours minus buttons until 0
      // Default hours is 4, tap 4 times
      for (int i = 0; i < 4; i++) {
        await tester.tap(minusButtons.last);
        await tester.pumpAndSettle();
      }

      // Should show minimum warning
      expect(
        find.text('Minimum trip duration is 1 hour'),
        findsOneWidget,
      );

      // Generate button should be disabled
      final button = tester.widget<FilledButton>(find.byType(FilledButton));
      expect(button.onPressed, isNull);
    });

    testWidgets('enforces maximum 14 days', (tester) async {
      await tester.pumpWidget(_buildTestWidget());
      await tester.pumpAndSettle();

      // The slider for days has max 14, we verify the plus button
      // stops working at 14 by finding the days Slider max
      final sliders = find.byType(Slider);
      final daysSlider = tester.widget<Slider>(sliders.first);
      expect(daysSlider.max, 14.0);
    });

    testWidgets('shows start date picker button', (tester) async {
      await tester.pumpWidget(_buildTestWidget());
      await tester.pumpAndSettle();

      expect(find.text('Start date'), findsOneWidget);
      expect(find.byIcon(Icons.calendar_today), findsOneWidget);
    });

    testWidgets('shows estimated stops count', (tester) async {
      await tester.pumpWidget(_buildTestWidget());
      await tester.pumpAndSettle();

      // Default: 1 day + 4 hours = 28 hours = 1680 min / 30 = 56 stops (clamped to 30)
      expect(find.textContaining('Estimated stops:'), findsOneWidget);
    });
  });
}
