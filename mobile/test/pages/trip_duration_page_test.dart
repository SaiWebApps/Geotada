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

Widget _buildTestWidget({
  TimeOfDay? initialStartTime,
  TimeOfDay? initialEndTime,
}) {
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
      child: TripDurationPage(
        citySlug: 'paris',
        initialStartTime: initialStartTime,
        initialEndTime: initialEndTime,
      ),
    ),
  );
}

void main() {
  group('TripDurationPage', () {
    testWidgets('shows date and time pickers', (tester) async {
      await tester.pumpWidget(_buildTestWidget());
      await tester.pumpAndSettle();

      expect(find.text('Paris'), findsOneWidget);
      expect(find.text('When are you visiting?'), findsOneWidget);
      expect(find.text('From'), findsOneWidget);
      expect(find.text('To (inclusive)'), findsOneWidget);
      expect(find.text('Generate My Trip'), findsOneWidget);
      expect(find.byIcon(Icons.calendar_today), findsNWidgets(2));
      expect(find.byIcon(Icons.access_time), findsNWidgets(2));
    });

    testWidgets('shows duration summary for valid range', (tester) async {
      await tester.pumpWidget(_buildTestWidget());
      await tester.pumpAndSettle();

      // Default: same day 09:00 to 18:00 = 9 hours
      expect(find.text('9 hours'), findsOneWidget);
    });

    testWidgets('generate button is enabled for valid range', (tester) async {
      await tester.pumpWidget(_buildTestWidget());
      await tester.pumpAndSettle();

      final button = tester.widget<FilledButton>(find.byType(FilledButton));
      expect(button.onPressed, isNotNull);
    });

    testWidgets('shows error when end is before start', (tester) async {
      // Start at 19:00, end at 18:00 — end is before start
      await tester.pumpWidget(_buildTestWidget(
        initialStartTime: const TimeOfDay(hour: 19, minute: 0),
        initialEndTime: const TimeOfDay(hour: 18, minute: 0),
      ));
      await tester.pumpAndSettle();

      expect(find.text('End must be after start'), findsOneWidget);
    });

    testWidgets('generate button disabled for invalid range', (tester) async {
      // Start at 19:00, end at 18:00 — invalid range
      await tester.pumpWidget(_buildTestWidget(
        initialStartTime: const TimeOfDay(hour: 19, minute: 0),
        initialEndTime: const TimeOfDay(hour: 18, minute: 0),
      ));
      await tester.pumpAndSettle();

      final button = tester.widget<FilledButton>(find.byType(FilledButton));
      expect(button.onPressed, isNull);
    });
  });
}
