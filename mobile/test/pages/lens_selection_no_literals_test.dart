import 'dart:io';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('lens_selection_page.dart contains no hardcoded Color(0x..) or Colors.<name> literals', () {
    final src = File('lib/pages/lens_selection_page.dart').readAsStringSync();
    expect(RegExp(r'Color\(0x').hasMatch(src), isFalse, reason: 'use theme tokens');
    expect(RegExp(r'Colors\.(?!transparent\b)').hasMatch(src), isFalse, reason: 'use theme tokens');
  });
}
