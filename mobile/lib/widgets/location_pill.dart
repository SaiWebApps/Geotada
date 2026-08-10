import 'package:flutter/material.dart';

import '../theme/dims.dart';
import '../theme/tokens.dart';

/// A dark, stadium-shaped pill showing a place name with an accent dot,
/// e.g. for "currently near" location chips.
class OndowayLocationPill extends StatelessWidget {
  const OndowayLocationPill({super.key, required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    final tokens = Theme.of(context).extension<OndowayColors>()!;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: Dims.spaceMd, vertical: Dims.spaceSm),
      decoration: ShapeDecoration(
        color: tokens.ink,
        shape: const StadiumBorder(),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            key: const Key('ondoway-location-pill-dot'),
            width: 8,
            height: 8,
            decoration: BoxDecoration(color: tokens.accent, shape: BoxShape.circle),
          ),
          const SizedBox(width: Dims.spaceSm),
          Text(
            label,
            style: TextStyle(color: tokens.panel, fontWeight: FontWeight.w600),
          ),
        ],
      ),
    );
  }
}
