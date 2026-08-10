// mobile/test/theme/dims_test.dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ondoway/theme/dims.dart';

void main() {
  test('spacing scale is a 4pt system', () {
    expect(Dims.spaceXs, 4);
    expect(Dims.spaceSm, 8);
    expect(Dims.spaceMd, 16);
    expect(Dims.spaceLg, 24);
    expect(Dims.spaceXl, 32);
  });
  test('pill radius is fully rounded, card radius is 20', () {
    expect(Dims.radiusPill, 999);
    expect(Dims.radiusCard, 20);
  });
  test('liftLight shadow has correct layers and properties', () {
    expect(Dims.liftLight.length, 2);
    expect(Dims.liftLight[0].color, const Color(0x1420242C));
    expect(Dims.liftLight[0].offset, const Offset(0, 4));
    expect(Dims.liftLight[0].blurRadius, 14);
    expect(Dims.liftLight[1].color, const Color(0x0D20242C));
    expect(Dims.liftLight[1].offset, const Offset(0, 1));
    expect(Dims.liftLight[1].blurRadius, 2);
  });
  test('liftLarge shadow has correct layers and properties', () {
    expect(Dims.liftLarge.length, 2);
    expect(Dims.liftLarge[0].color, const Color(0x2920242C));
    expect(Dims.liftLarge[0].offset, const Offset(0, 22));
    expect(Dims.liftLarge[0].blurRadius, 50);
    expect(Dims.liftLarge[1].color, const Color(0x0F20242C));
    expect(Dims.liftLarge[1].offset, const Offset(0, 4));
    expect(Dims.liftLarge[1].blurRadius, 10);
  });
}
