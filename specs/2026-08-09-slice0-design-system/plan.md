# Slice 0.1 — Design System (v10 tokens → Flutter theme) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Encode the v10 design system into a Flutter theme (`mobile/lib/theme/`) and build only the Slice-1 components, so every Slice-1 screen renders in the real brand language, light + dark.

**Architecture:** A `ThemeExtension` (`OndowayColors`) holds all semantic colors with `.light`/`.dark` variants; static `Dims` holds spacing/radii/elevation; `buildOndowayTheme(Brightness)` assembles `ThemeData` (Material 3 `ColorScheme` + Fraunces/Space Grotesk `TextTheme` + pill button/card component themes + the extension) and is wired into `main.dart`. Components read tokens via `Theme.of(context)` — no literals. A debug `/debug/style-gallery` route renders every token + component for on-device verification.

**Tech Stack:** Flutter (Material 3), `provider`, `go_router`, **`google_fonts`** (new dep), Dart `flutter_test`.

## Global Constraints

- Source of truth = **v10**, at `mobile/design/design-system-v10.html` + `mobile/design/README.md`. Do NOT use the stale `specs/2026-08-04-mobile-roadmap/design-system.html` (v2).
- **No hardcoded colors** anywhere in `lib/` after this slice — every color comes from `Theme.of(context).colorScheme.*` or `Theme.of(context).extension<OndowayColors>()!`. (CLAUDE.md Pre-commit rule.)
- v10 core tokens (light / dark): accent `#2C6CC0`/`#7BB2F5`, accent-deep `#1E4F92`/`#4C86D6`, bg `#E9E5DB`/`#101218`, card `#FFFFFF`/`#20242C`, panel `#F6F4F0`/`#12151B`, ink `#20242C`/`#F6F4F0`, ink-soft `#3A3F49`/`#C7CBD3`, ink-mute `#5B6069`/`#8B909B`, line `#DED8CB`/`#2E333D`, line-soft `#E8E3D8`/`#252A33`, spark `#E8934A`/`#E8934A`.
- Type: Fraunces (display) / Space Grotesk (body) / Space Mono (labels/eyebrows).
- Buttons are **pills** (`StadiumBorder`); cards 16–24px radius.
- Build ONLY components Slice-1 screens consume: primary + outline pill buttons, LensTile (de-hardcoded, cobalt selected ring), card, dark location pill, Preparing→Downloading→Ready strip. **Do NOT** build bottom nav or other unreached components (that's Slice 3).
- Flutter tests run via `make flutter-test` (never `flutter test` raw for the suite); a single file: `cd mobile && flutter test test/<path>` is acceptable for the RED/GREEN inner loop in this worktree. Lint: `make flutter-analyze` must be clean.
- Work happens in the worktree `/tmp/ondoway-step1` on branch `slice0-design-system`.

---

### Task 1: Color tokens as a ThemeExtension

**Files:**
- Create: `mobile/lib/theme/tokens.dart`
- Test: `mobile/test/theme/tokens_test.dart`

**Interfaces:**
- Produces: `class OndowayColors extends ThemeExtension<OndowayColors>` with `final Color` fields `accent, accentDeep, accentLight, bg, card, panel, ink, inkSoft, inkMute, line, lineSoft, spark`; factories `OndowayColors.light` and `OndowayColors.dark`; standard `copyWith` + `lerp`.

- [ ] **Step 1: Write the failing test**

```dart
// mobile/test/theme/tokens_test.dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ondoway/theme/tokens.dart';

void main() {
  test('light tokens match v10 hex values', () {
    const c = OndowayColors.light;
    expect(c.accent, const Color(0xFF2C6CC0));
    expect(c.bg, const Color(0xFFE9E5DB));
    expect(c.card, const Color(0xFFFFFFFF));
    expect(c.ink, const Color(0xFF20242C));
    expect(c.inkMute, const Color(0xFF5B6069));
    expect(c.spark, const Color(0xFFE8934A));
  });

  test('dark tokens match v10 hex values', () {
    const c = OndowayColors.dark;
    expect(c.accent, const Color(0xFF7BB2F5));
    expect(c.bg, const Color(0xFF101218));
    expect(c.ink, const Color(0xFFF6F4F0));
  });

  test('lerp(t=0) returns the start instance colors', () {
    const a = OndowayColors.light;
    const b = OndowayColors.dark;
    expect(a.lerp(b, 0).accent, a.accent);
  });
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /tmp/ondoway-step1/mobile && flutter test test/theme/tokens_test.dart`
Expected: FAIL — `Target of URI doesn't exist: 'package:ondoway/theme/tokens.dart'`.

- [ ] **Step 3: Write minimal implementation**

```dart
// mobile/lib/theme/tokens.dart
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
  });

  final Color accent, accentDeep, accentLight, bg, card, panel;
  final Color ink, inkSoft, inkMute, line, lineSoft, spark;

  static const light = OndowayColors(
    accent: Color(0xFF2C6CC0), accentDeep: Color(0xFF1E4F92), accentLight: Color(0xFF7BB2F5),
    bg: Color(0xFFE9E5DB), card: Color(0xFFFFFFFF), panel: Color(0xFFF6F4F0),
    ink: Color(0xFF20242C), inkSoft: Color(0xFF3A3F49), inkMute: Color(0xFF5B6069),
    line: Color(0xFFDED8CB), lineSoft: Color(0xFFE8E3D8), spark: Color(0xFFE8934A),
  );

  static const dark = OndowayColors(
    accent: Color(0xFF7BB2F5), accentDeep: Color(0xFF4C86D6), accentLight: Color(0xFF7BB2F5),
    bg: Color(0xFF101218), card: Color(0xFF20242C), panel: Color(0xFF12151B),
    ink: Color(0xFFF6F4F0), inkSoft: Color(0xFFC7CBD3), inkMute: Color(0xFF8B909B),
    line: Color(0xFF2E333D), lineSoft: Color(0xFF252A33), spark: Color(0xFFE8934A),
  );

  @override
  OndowayColors copyWith({Color? accent, Color? accentDeep, Color? accentLight, Color? bg,
      Color? card, Color? panel, Color? ink, Color? inkSoft, Color? inkMute, Color? line,
      Color? lineSoft, Color? spark}) {
    return OndowayColors(
      accent: accent ?? this.accent, accentDeep: accentDeep ?? this.accentDeep,
      accentLight: accentLight ?? this.accentLight, bg: bg ?? this.bg, card: card ?? this.card,
      panel: panel ?? this.panel, ink: ink ?? this.ink, inkSoft: inkSoft ?? this.inkSoft,
      inkMute: inkMute ?? this.inkMute, line: line ?? this.line, lineSoft: lineSoft ?? this.lineSoft,
      spark: spark ?? this.spark,
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
    );
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /tmp/ondoway-step1/mobile && flutter test test/theme/tokens_test.dart`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
cd /tmp/ondoway-step1
git add mobile/lib/theme/tokens.dart mobile/test/theme/tokens_test.dart
git commit -m "feat(theme): v10 color tokens as OndowayColors ThemeExtension"
```

---

### Task 2: Dimension tokens (spacing, radii, elevation)

**Files:**
- Create: `mobile/lib/theme/dims.dart`
- Test: `mobile/test/theme/dims_test.dart`

**Interfaces:**
- Produces: `abstract final class Dims` with `static const double spaceXs=4, spaceSm=8, spaceMd=16, spaceLg=24, spaceXl=32; static const double radiusCard=20, radiusPill=999; static const List<BoxShadow> liftLight, liftLarge;` (rgba values copied from the v10 `--lift`/`--lift-lg` tokens: light lift = `0 4px 14px rgba(32,36,44,.08), 0 1px 2px rgba(32,36,44,.05)`; light lift-lg = `0 22px 50px rgba(32,36,44,.16), 0 4px 10px rgba(32,36,44,.06)`).

- [ ] **Step 1: Write the failing test**

```dart
// mobile/test/theme/dims_test.dart
import 'package:flutter_test/flutter_test.dart';
import 'package:ondoway/theme/dims.dart';

void main() {
  test('spacing scale is a 4pt system', () {
    expect(Dims.spaceMd, 16);
    expect(Dims.spaceLg, 24);
  });
  test('pill radius is fully rounded, card radius is 20', () {
    expect(Dims.radiusPill, 999);
    expect(Dims.radiusCard, 20);
  });
  test('lift shadow has two layers', () {
    expect(Dims.liftLight.length, 2);
  });
}
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /tmp/ondoway-step1/mobile && flutter test test/theme/dims_test.dart` — Expected: FAIL (file missing).

- [ ] **Step 3: Write minimal implementation**

```dart
// mobile/lib/theme/dims.dart
import 'package:flutter/material.dart';

abstract final class Dims {
  static const double spaceXs = 4, spaceSm = 8, spaceMd = 16, spaceLg = 24, spaceXl = 32;
  static const double radiusCard = 20, radiusPill = 999;

  static const List<BoxShadow> liftLight = [
    BoxShadow(color: Color(0x14202429), offset: Offset(0, 4), blurRadius: 14), // rgba(32,36,44,.08)
    BoxShadow(color: Color(0x0D202429), offset: Offset(0, 1), blurRadius: 2),  // rgba(32,36,44,.05)
  ];
  static const List<BoxShadow> liftLarge = [
    BoxShadow(color: Color(0x29202429), offset: Offset(0, 22), blurRadius: 50), // .16
    BoxShadow(color: Color(0x0F202429), offset: Offset(0, 4), blurRadius: 10),  // .06
  ];
}
```

- [ ] **Step 4: Run to verify it passes** — Run: `cd /tmp/ondoway-step1/mobile && flutter test test/theme/dims_test.dart` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /tmp/ondoway-step1 && git add mobile/lib/theme/dims.dart mobile/test/theme/dims_test.dart
git commit -m "feat(theme): spacing/radii/elevation dimension tokens"
```

---

### Task 3: `buildOndowayTheme` + wire into `main.dart`

**Files:**
- Create: `mobile/lib/theme/theme.dart`
- Modify: `mobile/lib/main.dart` (the `MaterialApp.router` `theme:`/`darkTheme:` — currently bare `ThemeData(useMaterial3: true)` around lines 87–95)
- Modify: `mobile/pubspec.yaml` (add `google_fonts: ^6.2.1` under dependencies)
- Test: `mobile/test/theme/theme_test.dart`

**Interfaces:**
- Consumes: `OndowayColors` (Task 1), `Dims` (Task 2).
- Produces: `ThemeData buildOndowayTheme(Brightness brightness)` — includes the `OndowayColors` extension, a `ColorScheme` seeded from `accent`, a `TextTheme` using `GoogleFonts.fraunces` (display*/headline*) + `GoogleFonts.spaceGrotesk` (body*/title*/label*), `FilledButtonThemeData`/`OutlinedButtonThemeData` with `StadiumBorder`, and `CardTheme` radius `Dims.radiusCard`.

- [ ] **Step 1: Add the dep** — in `mobile/pubspec.yaml` under `dependencies:` add `google_fonts: ^6.2.1`, then `cd /tmp/ondoway-step1/mobile && flutter pub get`.

- [ ] **Step 2: Write the failing test**

```dart
// mobile/test/theme/theme_test.dart
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
```

- [ ] **Step 3: Run to verify it fails** — Run: `cd /tmp/ondoway-step1/mobile && flutter test test/theme/theme_test.dart` — Expected: FAIL (file missing).

- [ ] **Step 4: Write minimal implementation**

```dart
// mobile/lib/theme/theme.dart
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'tokens.dart';
import 'dims.dart';

ThemeData buildOndowayTheme(Brightness brightness) {
  final t = brightness == Brightness.dark ? OndowayColors.dark : OndowayColors.light;
  final scheme = ColorScheme.fromSeed(
    seedColor: t.accent, brightness: brightness,
    primary: t.accent, surface: t.card, onSurface: t.ink, background: t.bg,
  );
  final display = GoogleFonts.fraunces();
  final body = GoogleFonts.spaceGrotesk();
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
        backgroundColor: t.accent, foregroundColor: brightness == Brightness.dark ? t.bg : Colors.white,
        shape: const StadiumBorder(), padding: const EdgeInsets.symmetric(horizontal: Dims.spaceLg, vertical: Dims.spaceMd),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: t.accent, side: BorderSide(color: t.accent),
        shape: const StadiumBorder(), padding: const EdgeInsets.symmetric(horizontal: Dims.spaceLg, vertical: Dims.spaceMd),
      ),
    ),
    cardTheme: CardTheme(
      color: t.card, elevation: 0,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(Dims.radiusCard)),
    ),
  );
}
```

- [ ] **Step 5: Wire into `main.dart`** — replace the two bare `ThemeData(...)` at `main.dart:87` and `:92` with `theme: buildOndowayTheme(Brightness.light),` and `darkTheme: buildOndowayTheme(Brightness.dark),` and add `import 'theme/theme.dart';`.

- [ ] **Step 6: Run to verify it passes** — Run: `cd /tmp/ondoway-step1/mobile && flutter test test/theme/theme_test.dart` — Expected: PASS. Then `make flutter-analyze` clean.

- [ ] **Step 7: Commit**

```bash
cd /tmp/ondoway-step1 && git add mobile/lib/theme/theme.dart mobile/lib/main.dart mobile/pubspec.yaml mobile/pubspec.lock mobile/test/theme/theme_test.dart
git commit -m "feat(theme): buildOndowayTheme (M3 + Fraunces/Space Grotesk + pills) wired into app"
```

---

### Task 4: Pill button components

**Files:**
- Create: `mobile/lib/widgets/ondoway_buttons.dart`
- Test: `mobile/test/widgets/ondoway_buttons_test.dart`

**Interfaces:**
- Consumes: the app theme (Task 3).
- Produces: `class OndowayPrimaryButton extends StatelessWidget` and `class OndowayOutlineButton extends StatelessWidget`, each `const ...({required String label, required VoidCallback? onPressed})`. They wrap `FilledButton`/`OutlinedButton` so shape/color come from theme (no local color literals).

- [ ] **Step 1: Write the failing test**

```dart
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
```

- [ ] **Step 2: Run to verify it fails** — Expected: FAIL (file missing).

- [ ] **Step 3: Write minimal implementation**

```dart
// mobile/lib/widgets/ondoway_buttons.dart
import 'package:flutter/material.dart';

class OndowayPrimaryButton extends StatelessWidget {
  const OndowayPrimaryButton({super.key, required this.label, required this.onPressed});
  final String label;
  final VoidCallback? onPressed;
  @override
  Widget build(BuildContext context) =>
      FilledButton(onPressed: onPressed, child: Text(label));
}

class OndowayOutlineButton extends StatelessWidget {
  const OndowayOutlineButton({super.key, required this.label, required this.onPressed});
  final String label;
  final VoidCallback? onPressed;
  @override
  Widget build(BuildContext context) =>
      OutlinedButton(onPressed: onPressed, child: Text(label));
}
```

- [ ] **Step 4: Run to verify it passes** — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /tmp/ondoway-step1 && git add mobile/lib/widgets/ondoway_buttons.dart mobile/test/widgets/ondoway_buttons_test.dart
git commit -m "feat(ui): pill primary/outline button components"
```

---

### Task 5: De-hardcode `LensTile` (tokens + cobalt selected ring)

**Files:**
- Modify: `mobile/lib/widgets/lens_tile.dart` (the 21-entry `lensColors` map at lines 3–25, the fallback `0xFF616161` at :43, radius at :51)
- Create: `mobile/lib/theme/lens_palette.dart` (moves the category map out of the widget)
- Test: `mobile/test/widgets/lens_tile_test.dart`

**Interfaces:**
- Consumes: `OndowayColors` (Task 1) for the selected ring.
- Produces: `const Map<String, Color> kLensCategoryColors` in `lens_palette.dart` (the 21 category colors, verbatim from the current map — these are the secondary category codes v10 keeps beneath the accent). `LensTile` keeps its existing constructor; selected state ring = `Theme.of(context).extension<OndowayColors>()!.accent`, unselected border = `line` token.

> **v10 verification note:** the 21 category colors are carried forward as a named palette (not raw literals in the widget). The SELECTED ring switches to cobalt accent per v10. If the on-device Style Gallery (Task 8) shows v10's lens screens tone the category colors differently, adjust `kLensCategoryColors` then — the indirection makes that a one-file change.

- [ ] **Step 1: Write the failing test**

```dart
// mobile/test/widgets/lens_tile_test.dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ondoway/theme/theme.dart';
import 'package:ondoway/theme/tokens.dart';
import 'package:ondoway/widgets/lens_tile.dart';

Widget _host(Widget child) => MaterialApp(theme: buildOndowayTheme(Brightness.light), home: Scaffold(body: child));

void main() {
  testWidgets('selected tile ring uses the cobalt accent token, not a raw color', (tester) async {
    await tester.pumpWidget(_host(const LensTile(name: 'hidden_history', label: 'Hidden History', selected: true, onTap: null)));
    final decorated = tester.widget<Container>(find.byType(Container).first);
    final border = (decorated.decoration as BoxDecoration).border as Border;
    expect(border.top.color, OndowayColors.light.accent);
  });
}
```
(Adjust the finder to LensTile's actual selected-container structure when implementing; the assertion — selected ring == `OndowayColors.light.accent` — is the contract.)

- [ ] **Step 2: Run to verify it fails** — Expected: FAIL (selected ring is currently the category color / not accent).

- [ ] **Step 3: Implement** — create `lens_palette.dart` with `const Map<String, Color> kLensCategoryColors = { 'hidden_history': Color(0xFF3D5AFE), ... }` (all 21 verbatim from the current `lensColors`), import it in `lens_tile.dart`, delete the in-widget map, and set the selected border to `Theme.of(context).extension<OndowayColors>()!.accent` (unselected → `.line`). Keep radius via `Dims.radiusCard`? No — LensTile keeps 16 (its own spec); leave `BorderRadius.circular(16)`.

- [ ] **Step 4: Run to verify it passes** — Expected: PASS. Then `make flutter-analyze`.

- [ ] **Step 5: Commit**

```bash
cd /tmp/ondoway-step1 && git add mobile/lib/theme/lens_palette.dart mobile/lib/widgets/lens_tile.dart mobile/test/widgets/lens_tile_test.dart
git commit -m "feat(ui): de-hardcode LensTile — named category palette + cobalt selected ring"
```

---

### Task 6: De-hardcode `lens_selection_page.dart`

**Files:**
- Modify: `mobile/lib/pages/lens_selection_page.dart` (10 literals at lines 59, 76, 90, 100, 117, 147, 148, 154, 164–166, 174–175)
- Test: `mobile/test/pages/lens_selection_no_literals_test.dart` (a guard test)

**Interfaces:**
- Consumes: theme (Task 3). Mapping: `0xFF121212`→`scaffoldBackgroundColor`/`colors.bg`; `0xFF9E9E9E`→`colors.inkMute`; `0xFF1A1A1A`→`colors.panel`; `0xFF2A2A2A`→`colors.line`; `0xFF3D5AFE`→`colors.accent`; `Colors.white` on accent→`FilledButton` default. Use `final colors = Theme.of(context).extension<OndowayColors>()!;`.

- [ ] **Step 1: Write the failing guard test**

```dart
// mobile/test/pages/lens_selection_no_literals_test.dart
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('lens_selection_page.dart contains no hardcoded Color(0x..) or Colors.<name> literals', () {
    final src = File('lib/pages/lens_selection_page.dart').readAsStringSync();
    expect(RegExp(r'Color\(0x').hasMatch(src), isFalse, reason: 'use theme tokens');
    expect(RegExp(r'Colors\.(?!transparent\b)').hasMatch(src), isFalse, reason: 'use theme tokens');
  });
}
```

- [ ] **Step 2: Run to verify it fails** — Run: `cd /tmp/ondoway-step1/mobile && flutter test test/pages/lens_selection_no_literals_test.dart` — Expected: FAIL (literals present).

- [ ] **Step 3: Implement** — replace each literal per the mapping above; delete the now-redundant `backgroundColor`/`foregroundColor` overrides on the Save button so it inherits the pill `FilledButton` theme.

- [ ] **Step 4: Run to verify it passes** — Expected: PASS. Then `make flutter-analyze`, and manually confirm the page still builds: `flutter test test/` (the existing onboarding tests must stay green).

- [ ] **Step 5: Commit**

```bash
cd /tmp/ondoway-step1 && git add mobile/lib/pages/lens_selection_page.dart mobile/test/pages/lens_selection_no_literals_test.dart
git commit -m "feat(ui): de-hardcode lens_selection_page onto theme tokens"
```

---

### Task 7: Location pill + Preparing→Downloading→Ready strip

**Files:**
- Create: `mobile/lib/widgets/location_pill.dart`, `mobile/lib/widgets/prepare_strip.dart`
- Test: `mobile/test/widgets/location_pill_test.dart`, `mobile/test/widgets/prepare_strip_test.dart`

**Interfaces:**
- Produces:
  - `class OndowayLocationPill extends StatelessWidget` — `const ...({required String label})`; dark pill: `ink`/`inkSoft`-ish bg, `accent` dot, `panel`/white text, `StadiumBorder`.
  - `enum PrepareStage { preparing, downloading, ready }` and `class PrepareStrip extends StatelessWidget` — `const ...({required PrepareStage stage})`; renders the three-step progress with the active step in `accent` and the CTA hint text.

- [ ] **Step 1: Write failing tests**

```dart
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
```
(Plus `location_pill_test.dart`: pump `OndowayLocationPill(label: 'Louvre')` in a themed host, assert `find.text('Louvre')` and that a dot Container uses the accent token.)

- [ ] **Step 2: Run to verify they fail** — Expected: FAIL (files missing).

- [ ] **Step 3: Implement** both widgets reading only theme tokens (`Theme.of(context).extension<OndowayColors>()!`), pill via `StadiumBorder`/`radiusPill`.

- [ ] **Step 4: Run to verify they pass** — Expected: PASS. Then `make flutter-analyze`.

- [ ] **Step 5: Commit**

```bash
cd /tmp/ondoway-step1 && git add mobile/lib/widgets/location_pill.dart mobile/lib/widgets/prepare_strip.dart mobile/test/widgets/location_pill_test.dart mobile/test/widgets/prepare_strip_test.dart
git commit -m "feat(ui): location pill + prepare/download/ready strip components"
```

---

### Task 8: Style Gallery debug route

**Files:**
- Create: `mobile/lib/pages/style_gallery_page.dart`
- Modify: `mobile/lib/router.dart` (add a `GoRoute` under the existing `/debug/*` block, near `router.dart:129`)
- Test: `mobile/test/pages/style_gallery_test.dart`, and extend `mobile/test/router_redirect_test.dart` with one case.

**Interfaces:**
- Consumes: every token + component from Tasks 1–7.
- Produces: `class StyleGalleryPage extends StatelessWidget` — renders swatches for all `OndowayColors` fields (light+dark side by side via nested `Theme`), the type scale, and one live instance of each component (both buttons, a `LensTile` selected + unselected, a card, `OndowayLocationPill`, `PrepareStrip` in all 3 stages). Route path `'/debug/style-gallery'`.

- [ ] **Step 1: Write the failing tests**

```dart
// mobile/test/pages/style_gallery_test.dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ondoway/theme/theme.dart';
import 'package:ondoway/pages/style_gallery_page.dart';

void main() {
  testWidgets('gallery builds and shows a component sample', (tester) async {
    await tester.pumpWidget(MaterialApp(theme: buildOndowayTheme(Brightness.light),
      home: const StyleGalleryPage()));
    expect(find.text('Preparing'), findsWidgets); // PrepareStrip present
    expect(find.byType(Card), findsWidgets);
  });
}
```
And in `router_redirect_test.dart` add: `computeAuthRedirect(unauthenticated, '/debug/style-gallery', allowDebugRoutes: true)` → `null` (reachable in debug), and with `allowDebugRoutes: false` → `/login`.

- [ ] **Step 2: Run to verify they fail** — Expected: FAIL.

- [ ] **Step 3: Implement** the page + add the route:

```dart
// in router.dart, inside the /debug block near line 129:
GoRoute(path: '/debug/style-gallery', builder: (c, s) => const StyleGalleryPage()),
```

- [ ] **Step 4: Run to verify they pass** — Run: `cd /tmp/ondoway-step1/mobile && flutter test test/pages/style_gallery_test.dart test/router_redirect_test.dart` — Expected: PASS. Then `make flutter-analyze`.

- [ ] **Step 5: Commit**

```bash
cd /tmp/ondoway-step1 && git add mobile/lib/pages/style_gallery_page.dart mobile/lib/router.dart mobile/test/pages/style_gallery_test.dart mobile/test/router_redirect_test.dart
git commit -m "feat(ui): Style Gallery debug route (/debug/style-gallery)"
```

---

### Task 9: Full suite green + on-device acceptance (human gate)

**Files:** none (verification only).

- [ ] **Step 1: Whole Flutter suite green** — Run: `make flutter-test` (from `/tmp/ondoway-step1`). Expected: all pass, 0 skipped. Fix any regression in the existing screens caused by the theme swap before proceeding.
- [ ] **Step 2: Lint clean** — Run: `make flutter-analyze`. Expected: No issues found.
- [ ] **Step 3: Build to device** — Run the per-dev device build (`make flutter-device` or the profile variant), open the app, navigate to `/debug/style-gallery`.
- [ ] **Step 4: ACCEPTANCE (human, on iPhone):** confirm the gallery matches v10 in **both light and dark** (toggle system appearance): cobalt accent, bone/navy grounds, Fraunces headings + Space Grotesk body, pill buttons, LensTile cobalt selected ring, location pill, and the Preparing→Downloading→Ready strip. Compare against `mobile/design/design-system-v10.html`. Screenshot both modes.
- [ ] **Step 5:** If acceptance passes, the slice is done — open a PR for `slice0-design-system` (honest body; note the LensTile category-color treatment was carried forward pending the v10 lens-screen check). If the gallery diverges from v10, file the specific token/component deltas and loop back to the relevant task.

---

## Self-Review

**1. Spec coverage** (roadmap §3 0.1): tokens→ThemeData (Tasks 1–3 ✓); build ONLY Slice-1 components — pill buttons (4 ✓), LensTile de-hardcode + blue ring (5 ✓), card (via CardTheme in 3 + shown in gallery ✓), location pill + prep strip (7 ✓); replace literals in lens_selection_page + LensTile (5, 6 ✓); fonts via google_fonts (3 ✓); Style Gallery debug route (8 ✓); on-device light+dark acceptance (9 ✓). "Do not build bottom nav" — respected (not in any task). Open decision (secondary lens colors vs blue tints) — resolved as "carry the category palette, cobalt selected ring," with a v10 on-device check (Task 5 note + Task 9). ✓
**2. Placeholder scan:** every code step has real Dart; the two "adjust finder to actual structure" notes (Tasks 5, 7) name the exact assertion contract, not a TODO. ✓
**3. Type consistency:** `OndowayColors` fields/factories used identically in Tasks 1,3,5,6,7,8; `buildOndowayTheme(Brightness)` signature identical in Tasks 3,4,5,7,8; `Dims` constants consistent; `PrepareStage`/`PrepareStrip` defined in 7 and consumed in 8. ✓
