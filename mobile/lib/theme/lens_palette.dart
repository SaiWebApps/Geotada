import 'package:flutter/material.dart';

/// Category tile fill colors, keyed by lens `name`. These are the secondary
/// category codes v10 keeps beneath the accent — moved out of `LensTile` so
/// they can be retuned in one file without touching widget code.
const Map<String, Color> kLensCategoryColors = <String, Color>{
  'hidden_history': Color(0xFF3D5AFE),
  'war_conflict': Color(0xFFD32F2F),
  'dark_history': Color(0xFF4A148C),
  'social_change': Color(0xFFFF8F00),
  'historic_arch': Color(0xFF00897B),
  'modern_design': Color(0xFF0288D1),
  'music_heritage': Color(0xFFC2185B),
  'visual_art': Color(0xFFF57C00),
  'street_art': Color(0xFF689F38),
  'film_tv': Color(0xFF7B1FA2),
  'historic_cuisine': Color(0xFFE64A19),
  'markets_street_food': Color(0xFFFF7043),
  'local_legends': Color(0xFF2E7D32),
  'literary_heritage': Color(0xFF455A64),
  'famous_residents': Color(0xFFFFA000),
  'historic_worship': Color(0xFF00695C),
  'sacred_traditions': Color(0xFF8E24AA),
  'parks_gardens': Color(0xFF388E3C),
  'waterways_views': Color(0xFF0277BD),
  'historic_markets': Color(0xFFE65100),
  'science_tech': Color(0xFF1565C0),
};
