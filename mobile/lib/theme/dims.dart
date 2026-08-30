import 'package:flutter/material.dart';

abstract final class Dims {
  static const double spaceXs = 4, spaceSm = 8, spaceMd = 16, spaceLg = 24, spaceXl = 32;
  static const double radiusCard = 20, radiusPill = 999;

  static const List<BoxShadow> liftLight = [
    BoxShadow(color: Color(0x1420242C), offset: Offset(0, 4), blurRadius: 14), // rgba(32,36,44,.08)
    BoxShadow(color: Color(0x0D20242C), offset: Offset(0, 1), blurRadius: 2),  // rgba(32,36,44,.05)
  ];
  static const List<BoxShadow> liftLarge = [
    BoxShadow(color: Color(0x2920242C), offset: Offset(0, 22), blurRadius: 50), // rgba(32,36,44,.16)
    BoxShadow(color: Color(0x0F20242C), offset: Offset(0, 4), blurRadius: 10),  // rgba(32,36,44,.06)
  ];
}
