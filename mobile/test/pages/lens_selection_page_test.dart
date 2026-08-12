import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ondoway/models/lens.dart';
import 'package:ondoway/pages/lens_selection_page.dart';
import 'package:ondoway/theme/theme.dart';

final _testLenses = <String, List<Lens>>{
  'History': [
    Lens(id: 'l1', name: 'hidden_history', displayLabel: 'Hidden History', isParent: false),
    Lens(id: 'l2', name: 'dark_history', displayLabel: 'Dark History', isParent: false),
    Lens(id: 'l3', name: 'war_conflict', displayLabel: 'War & Conflict', isParent: false),
    Lens(id: 'l4', name: 'social_change', displayLabel: 'Social Change', isParent: false),
  ],
};

Widget _wrap(Widget child) {
  return MaterialApp(theme: buildOndowayTheme(Brightness.light), home: child);
}

void main() {
  group('LensSelectionPage onboarding mode', () {
    testWidgets('shows welcome header with user name', (tester) async {
      await tester.pumpWidget(_wrap(LensSelectionPage(
        isOnboarding: true,
        userName: 'Sairam',
        lensesByParent: _testLenses,
      )));
      expect(find.text('WELCOME, SAIRAM'), findsOneWidget);
    });

    testWidgets('shows subtitle in onboarding mode', (tester) async {
      await tester.pumpWidget(_wrap(LensSelectionPage(
        isOnboarding: true,
        lensesByParent: _testLenses,
      )));
      expect(find.textContaining('Pick at least 3'), findsOneWidget);
    });

    testWidgets('renders all lens tiles', (tester) async {
      await tester.pumpWidget(_wrap(LensSelectionPage(
        isOnboarding: true,
        lensesByParent: _testLenses,
      )));
      expect(find.text('Hidden History'), findsOneWidget);
      expect(find.text('Dark History'), findsOneWidget);
      expect(find.text('War & Conflict'), findsOneWidget);
      expect(find.text('Social Change'), findsOneWidget);
    });

    testWidgets('renders category headers', (tester) async {
      await tester.pumpWidget(_wrap(LensSelectionPage(
        isOnboarding: true,
        lensesByParent: _testLenses,
      )));
      expect(find.text('HISTORY'), findsOneWidget);
    });

    testWidgets('continue button disabled with fewer than 3 selected', (tester) async {
      await tester.pumpWidget(_wrap(LensSelectionPage(
        isOnboarding: true,
        lensesByParent: _testLenses,
      )));

      final button = tester.widget<FilledButton>(find.widgetWithText(FilledButton, 'Continue'));
      expect(button.onPressed, isNull);
    });

    testWidgets('continue button enables after 3 selections', (tester) async {
      Set<String>? result;
      await tester.pumpWidget(_wrap(LensSelectionPage(
        isOnboarding: true,
        lensesByParent: _testLenses,
        onComplete: (ids) => result = ids,
      )));

      await tester.tap(find.text('Hidden History'));
      await tester.tap(find.text('Dark History'));
      await tester.pump();

      await tester.ensureVisible(find.text('War & Conflict'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('War & Conflict'));
      await tester.pump();

      await tester.ensureVisible(find.text('Continue'));
      await tester.pumpAndSettle();
      final button = tester.widget<FilledButton>(find.widgetWithText(FilledButton, 'Continue'));
      expect(button.onPressed, isNotNull);

      await tester.tap(find.text('Continue'));
      await tester.pump();
      expect(result, {'l1', 'l2', 'l3'});
    });

    testWidgets('shows selection count', (tester) async {
      await tester.pumpWidget(_wrap(LensSelectionPage(
        isOnboarding: true,
        lensesByParent: _testLenses,
      )));

      // Onboarding footer coaches toward the 3-lens minimum rather than a bare count.
      expect(find.text('Choose 3 more'), findsOneWidget);
      await tester.tap(find.text('Hidden History'));
      await tester.pump();
      expect(find.text('Choose 2 more'), findsOneWidget);
    });

    testWidgets('tapping selected tile deselects it', (tester) async {
      await tester.pumpWidget(_wrap(LensSelectionPage(
        isOnboarding: true,
        lensesByParent: _testLenses,
      )));

      await tester.tap(find.text('Hidden History'));
      await tester.pump();
      expect(find.text('Choose 2 more'), findsOneWidget);

      await tester.tap(find.text('Hidden History'));
      await tester.pump();
      expect(find.text('Choose 3 more'), findsOneWidget);
    });
  });

  group('LensSelectionPage edit mode', () {
    testWidgets('shows "Your Lenses" header', (tester) async {
      await tester.pumpWidget(_wrap(LensSelectionPage(
        isOnboarding: false,
        lensesByParent: _testLenses,
        initialSelection: {'l1', 'l3'},
      )));
      expect(find.text('Your lenses'), findsOneWidget);
    });

    testWidgets('does not show subtitle', (tester) async {
      await tester.pumpWidget(_wrap(LensSelectionPage(
        isOnboarding: false,
        lensesByParent: _testLenses,
      )));
      expect(find.textContaining('Pick at least'), findsNothing);
    });

    testWidgets('shows Save button instead of Continue', (tester) async {
      await tester.pumpWidget(_wrap(LensSelectionPage(
        isOnboarding: false,
        lensesByParent: _testLenses,
      )));
      expect(find.text('Save'), findsOneWidget);
      expect(find.text('Continue'), findsNothing);
    });

    testWidgets('pre-selects initial lenses', (tester) async {
      await tester.pumpWidget(_wrap(LensSelectionPage(
        isOnboarding: false,
        lensesByParent: _testLenses,
        initialSelection: {'l1', 'l4'},
      )));
      expect(find.text('2 selected'), findsOneWidget);
    });

    testWidgets('shows snackbar when trying to deselect last lens', (tester) async {
      await tester.pumpWidget(_wrap(LensSelectionPage(
        isOnboarding: false,
        lensesByParent: _testLenses,
        initialSelection: {'l1'},
      )));

      await tester.tap(find.text('Hidden History'));
      await tester.pump();
      expect(find.text('You need at least one lens'), findsOneWidget);
      expect(find.text('1 selected'), findsOneWidget);
    });
  });
}
