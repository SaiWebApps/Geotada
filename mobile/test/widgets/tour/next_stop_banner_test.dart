import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ondoway/widgets/tour/next_stop_banner.dart';

void main() {
  test('formatDistance rounds metres under 1km, uses km above', () {
    expect(formatDistance(0), '0 m');
    expect(formatDistance(219.4), '219 m');
    expect(formatDistance(1200), '1.2 km');
  });

  testWidgets('shows the stop name and distance', (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(body: NextStopBanner(stopName: 'Pont Neuf', distanceMeters: 220)),
    ));
    expect(find.textContaining('Pont Neuf'), findsOneWidget);
    expect(find.textContaining('220 m'), findsOneWidget);
  });

  testWidgets('shows a locating hint when distance is null', (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(body: NextStopBanner(stopName: 'Pont Neuf', distanceMeters: null)),
    ));
    expect(find.textContaining('Finding your location'), findsOneWidget);
  });
}
