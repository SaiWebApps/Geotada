// mobile/test/widgets/lens_tile_test.dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ondoway/theme/theme.dart';
import 'package:ondoway/theme/tokens.dart';
import 'package:ondoway/widgets/lens_tile.dart';

Widget _host(Widget child) =>
    MaterialApp(theme: buildOndowayTheme(Brightness.light), home: Scaffold(body: child));

void main() {
  testWidgets('selected tile ring uses the cobalt accent token, not a raw color', (tester) async {
    await tester.pumpWidget(_host(LensTile(
      name: 'hidden_history',
      displayLabel: 'Hidden History',
      isSelected: true,
      onTap: () {},
    )));

    // LensTile's own container is an AnimatedContainer; its rendered Container
    // (the first one in the tree — the checkmark badge is a second, nested
    // Container that only appears when selected) carries the ring border.
    final decorated = tester.widget<Container>(find.byType(Container).first);
    final border = (decorated.decoration as BoxDecoration).border as Border;
    expect(border.top.color, OndowayColors.light.accent);
  });

  testWidgets('unselected tile has no accent ring', (tester) async {
    await tester.pumpWidget(_host(LensTile(
      name: 'hidden_history',
      displayLabel: 'Hidden History',
      isSelected: false,
      onTap: () {},
    )));

    final decorated = tester.widget<Container>(find.byType(Container).first);
    final border = (decorated.decoration as BoxDecoration).border as Border;
    expect(border.top.color, OndowayColors.light.line);
  });
}
