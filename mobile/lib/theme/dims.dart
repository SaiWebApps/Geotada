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
