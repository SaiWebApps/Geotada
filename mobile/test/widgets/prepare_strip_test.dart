// mobile/test/widgets/prepare_strip_test.dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ondoway/theme/theme.dart';
import 'package:ondoway/theme/tokens.dart';
import 'package:ondoway/widgets/prepare_strip.dart';

void main() {
  testWidgets('shows the three stage labels and marks the active one', (tester) async {
    await tester.pumpWidget(MaterialApp(theme: buildOndowayTheme(Brightness.light),
      home: const Scaffold(body: PrepareStrip(stage: PrepareStage.downloading))));
    expect(find.text('Preparing'), findsOneWidget);
    expect(find.text('Downloading'), findsOneWidget);
    expect(find.text('Ready'), findsOneWidget);

    final activeStyle = tester.widget<Text>(find.text('Downloading')).style;
    expect(activeStyle?.color, OndowayColors.light.accent);
    expect(activeStyle?.fontWeight, FontWeight.w700);

    final inactiveStyle = tester.widget<Text>(find.text('Preparing')).style;
    expect(inactiveStyle?.color, OndowayColors.light.inkMute);
    expect(inactiveStyle?.fontWeight, FontWeight.w400);
  });

  testWidgets('active stage tracks a different value (ready)', (tester) async {
    await tester.pumpWidget(MaterialApp(theme: buildOndowayTheme(Brightness.light),
      home: const Scaffold(body: PrepareStrip(stage: PrepareStage.ready))));

    final activeStyle = tester.widget<Text>(find.text('Ready')).style;
    expect(activeStyle?.color, OndowayColors.light.accent);
    expect(activeStyle?.fontWeight, FontWeight.w700);

    final inactiveStyle = tester.widget<Text>(find.text('Downloading')).style;
    expect(inactiveStyle?.color, OndowayColors.light.inkMute);
    expect(inactiveStyle?.fontWeight, FontWeight.w400);
  });
}
