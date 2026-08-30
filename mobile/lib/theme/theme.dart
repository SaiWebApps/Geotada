import 'package:flutter/material.dart';
import 'tokens.dart';
import 'dims.dart';

ThemeData buildOndowayTheme(Brightness brightness) {
  final t = brightness == Brightness.dark ? OndowayColors.dark : OndowayColors.light;
  final scheme = ColorScheme.fromSeed(
    seedColor: t.accent, brightness: brightness,
    primary: t.accent, surface: t.card, onSurface: t.ink,
  );
  const display = TextStyle(fontFamily: 'Fraunces');
  const body = TextStyle(fontFamily: 'Space Grotesk');
  final base = ThemeData(useMaterial3: true, brightness: brightness, colorScheme: scheme);

  return base.copyWith(
    scaffoldBackgroundColor: t.bg,
    extensions: [t],
    textTheme: base.textTheme.copyWith(
      displayLarge: display.copyWith(color: t.ink), displayMedium: display.copyWith(color: t.ink),
      headlineLarge: display.copyWith(color: t.ink), headlineMedium: display.copyWith(color: t.ink),
      titleLarge: body.copyWith(color: t.ink, fontWeight: FontWeight.w600),
      bodyLarge: body.copyWith(color: t.ink), bodyMedium: body.copyWith(color: t.inkSoft),
      labelLarge: body.copyWith(color: t.ink, fontWeight: FontWeight.w600),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: t.accent, foregroundColor: t.onAccent,
        shape: const StadiumBorder(), padding: const EdgeInsets.symmetric(horizontal: Dims.spaceLg, vertical: Dims.spaceMd),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: t.accent, side: BorderSide(color: t.accent),
        shape: const StadiumBorder(), padding: const EdgeInsets.symmetric(horizontal: Dims.spaceLg, vertical: Dims.spaceMd),
      ),
    ),
    cardTheme: CardThemeData(
      color: t.card, elevation: 0,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(Dims.radiusCard)),
    ),
  );
}
