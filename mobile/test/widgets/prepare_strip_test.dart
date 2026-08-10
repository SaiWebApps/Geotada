// mobile/test/widgets/prepare_strip_test.dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ondoway/theme/theme.dart';
import 'package:ondoway/widgets/prepare_strip.dart';

void main() {
  testWidgets('shows the three stage labels and marks the active one', (tester) async {
    await tester.pumpWidget(MaterialApp(theme: buildOndowayTheme(Brightness.light),
      home: const Scaffold(body: PrepareStrip(stage: PrepareStage.downloading))));
    expect(find.text('Preparing'), findsOneWidget);
    expect(find.text('Downloading'), findsOneWidget);
    expect(find.text('Ready'), findsOneWidget);
  });
}
