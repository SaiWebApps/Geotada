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
