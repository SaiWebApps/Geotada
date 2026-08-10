// mobile/test/widgets/location_pill_test.dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ondoway/theme/theme.dart';
import 'package:ondoway/theme/tokens.dart';
import 'package:ondoway/widgets/location_pill.dart';

Widget _host(Widget child) =>
    MaterialApp(theme: buildOndowayTheme(Brightness.light), home: Scaffold(body: child));

void main() {
  testWidgets('renders the label and an accent-colored dot', (tester) async {
    await tester.pumpWidget(_host(const OndowayLocationPill(label: 'Louvre')));

    expect(find.text('Louvre'), findsOneWidget);

    final dot = tester.widget<Container>(find.byKey(const Key('ondoway-location-pill-dot')));
    final decoration = dot.decoration as BoxDecoration;
    expect(decoration.color, OndowayColors.light.accent);
  });
}
