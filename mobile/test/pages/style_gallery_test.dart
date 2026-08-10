import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ondoway/theme/theme.dart';
import 'package:ondoway/pages/style_gallery_page.dart';

void main() {
  testWidgets('gallery builds and shows a component sample', (tester) async {
    await tester.pumpWidget(MaterialApp(
      theme: buildOndowayTheme(Brightness.light),
      home: const StyleGalleryPage(),
    ));
    expect(find.text('Preparing'), findsWidgets); // PrepareStrip present
    expect(find.byType(Card), findsWidgets);
  });
}
