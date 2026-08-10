import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ondoway/theme/theme.dart';
import 'package:ondoway/theme/tokens.dart';

void main() {
  test('light theme carries the OndowayColors extension with v10 accent', () {
    final t = buildOndowayTheme(Brightness.light);
    final c = t.extension<OndowayColors>();
    expect(c, isNotNull);
    expect(c!.accent, const Color(0xFF2C6CC0));
    expect(t.brightness, Brightness.light);
  });

  test('dark theme uses the dark token set', () {
    final t = buildOndowayTheme(Brightness.dark);
    expect(t.extension<OndowayColors>()!.bg, const Color(0xFF101218));
  });

  test('buttons are pill-shaped (StadiumBorder)', () {
    final t = buildOndowayTheme(Brightness.light);
    final shape = t.filledButtonTheme.style?.shape?.resolve({});
    expect(shape, isA<StadiumBorder>());
  });
}
