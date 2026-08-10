// mobile/test/widgets/ondoway_buttons_test.dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ondoway/theme/theme.dart';
import 'package:ondoway/widgets/ondoway_buttons.dart';

void main() {
  testWidgets('primary button renders its label and fires onPressed', (tester) async {
    var tapped = false;
    await tester.pumpWidget(MaterialApp(
      theme: buildOndowayTheme(Brightness.light),
      home: Scaffold(body: OndowayPrimaryButton(label: 'Start', onPressed: () => tapped = true)),
    ));
    expect(find.text('Start'), findsOneWidget);
    await tester.tap(find.byType(OndowayPrimaryButton));
    expect(tapped, isTrue);
  });

  testWidgets('primary button is pill-shaped from theme', (tester) async {
    await tester.pumpWidget(MaterialApp(
      theme: buildOndowayTheme(Brightness.light),
      home: const Scaffold(body: OndowayPrimaryButton(label: 'Go', onPressed: null)),
    ));
    final btn = tester.widget<FilledButton>(find.byType(FilledButton));
    // Shape comes from theme, not a local override:
    expect(btn.style?.shape, isNull);
  });
}
