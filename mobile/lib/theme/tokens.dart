import 'package:flutter/material.dart';

@immutable
class OndowayColors extends ThemeExtension<OndowayColors> {
  const OndowayColors({
    required this.accent,
    required this.accentDeep,
    required this.accentLight,
    required this.bg,
    required this.card,
    required this.panel,
    required this.ink,
    required this.inkSoft,
    required this.inkMute,
    required this.line,
    required this.lineSoft,
    required this.spark,
    required this.onAccent,
  });

  final Color accent, accentDeep, accentLight, bg, card, panel;
  final Color ink, inkSoft, inkMute, line, lineSoft, spark;
  final Color onAccent;

  static const light = OndowayColors(
    accent: Color(0xFF2C6CC0), accentDeep: Color(0xFF1E4F92), accentLight: Color(0xFF7BB2F5),
    bg: Color(0xFFE9E5DB), card: Color(0xFFFFFFFF), panel: Color(0xFFF6F4F0),
    ink: Color(0xFF20242C), inkSoft: Color(0xFF3A3F49), inkMute: Color(0xFF5B6069),
    line: Color(0xFFDED8CB), lineSoft: Color(0xFFE8E3D8), spark: Color(0xFFE8934A),
    onAccent: Color(0xFFFFFFFF),
  );

  static const dark = OndowayColors(
    accent: Color(0xFF7BB2F5), accentDeep: Color(0xFF4C86D6), accentLight: Color(0xFF7BB2F5),
    bg: Color(0xFF101218), card: Color(0xFF20242C), panel: Color(0xFF12151B),
    ink: Color(0xFFF6F4F0), inkSoft: Color(0xFFC7CBD3), inkMute: Color(0xFF8B909B),
    line: Color(0xFF2E333D), lineSoft: Color(0xFF252A33), spark: Color(0xFFE8934A),
    onAccent: Color(0xFF101218),
  );

  @override
  OndowayColors copyWith({Color? accent, Color? accentDeep, Color? accentLight, Color? bg,
      Color? card, Color? panel, Color? ink, Color? inkSoft, Color? inkMute, Color? line,
      Color? lineSoft, Color? spark, Color? onAccent}) {
    return OndowayColors(
      accent: accent ?? this.accent, accentDeep: accentDeep ?? this.accentDeep,
      accentLight: accentLight ?? this.accentLight, bg: bg ?? this.bg, card: card ?? this.card,
      panel: panel ?? this.panel, ink: ink ?? this.ink, inkSoft: inkSoft ?? this.inkSoft,
      inkMute: inkMute ?? this.inkMute, line: line ?? this.line, lineSoft: lineSoft ?? this.lineSoft,
      spark: spark ?? this.spark, onAccent: onAccent ?? this.onAccent,
    );
  }

  @override
  OndowayColors lerp(ThemeExtension<OndowayColors>? other, double t) {
    if (other is! OndowayColors) return this;
    return OndowayColors(
      accent: Color.lerp(accent, other.accent, t)!, accentDeep: Color.lerp(accentDeep, other.accentDeep, t)!,
      accentLight: Color.lerp(accentLight, other.accentLight, t)!, bg: Color.lerp(bg, other.bg, t)!,
      card: Color.lerp(card, other.card, t)!, panel: Color.lerp(panel, other.panel, t)!,
      ink: Color.lerp(ink, other.ink, t)!, inkSoft: Color.lerp(inkSoft, other.inkSoft, t)!,
      inkMute: Color.lerp(inkMute, other.inkMute, t)!, line: Color.lerp(line, other.line, t)!,
      lineSoft: Color.lerp(lineSoft, other.lineSoft, t)!, spark: Color.lerp(spark, other.spark, t)!,
      onAccent: Color.lerp(onAccent, other.onAccent, t)!,
    );
  }
}
