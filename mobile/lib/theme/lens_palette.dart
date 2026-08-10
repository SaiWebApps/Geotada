import 'package:flutter/material.dart';

/// Category tile fill colors, keyed by lens `name`. These are the secondary
/// category codes v10 keeps beneath the accent — moved out of `LensTile` so
/// they can be retuned in one file without touching widget code.
///
/// Retuned 2026-08-09 (taste pass): the originals were the raw Material palette
/// (90-100% saturation), which read louder than the cobalt brand accent and
/// violated the "one accent, harmonized secondary set" rule. Each hue is
/// preserved for wayfinding but pulled to <=46% saturation and a tight
/// lightness band, so the 21 categories now read as one muted family that sits
/// BENEATH cobalt rather than competing with it.
const Map<String, Color> kLensCategoryColors = <String, Color>{
  'hidden_history': Color(0xFF4A4F86),
  'war_conflict': Color(0xFFA74C4C),
  'dark_history': Color(0xFF643B96),
  'social_change': Color(0xFFB08041),
  'historic_arch': Color(0xFF369289),
  'modern_design': Color(0xFF3D81A5),
  'music_heritage': Color(0xFFA63F67),
  'visual_art': Color(0xFFAE7840),
  'street_art': Color(0xFF709252),
  'film_tv': Color(0xFF804399),
  'historic_cuisine': Color(0xFFB05C41),
  'markets_street_food': Color(0xFFBD674C),
  'local_legends': Color(0xFF4E8751),
  'literary_heritage': Color(0xFF5F6E75),
  'famous_residents': Color(0xFFB08741),
  'historic_worship': Color(0xFF338A7F),
  'sacred_traditions': Color(0xFF89469B),
  'parks_gardens': Color(0xFF538B56),
  'waterways_views': Color(0xFF3B7AA0),
  'historic_markets': Color(0xFFAA653F),
  'science_tech': Color(0xFF3D6EA6),
};
