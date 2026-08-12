import 'package:flutter/material.dart';

import '../theme/dims.dart';
import '../theme/lens_palette.dart';
import '../theme/tokens.dart';

/// A single interest chip: category-tinted when unselected, filled with its
/// category color + a check when selected. Flows in a Wrap so the picker packs
/// densely onto one screen instead of a sparse grid of big squares. Colored
/// literals live here (not the guarded selection page) exactly as [LensTile] does.
class LensChip extends StatelessWidget {
  final String name;
  final String label;
  final bool selected;
  final VoidCallback onTap;

  const LensChip({
    super.key,
    required this.name,
    required this.label,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final c = Theme.of(context).extension<OndowayColors>()!;
    final color = kLensCategoryColors[name] ?? const Color(0xFF616169);
    final glyph = kLensCategoryIcons[name] ?? Icons.place_outlined;
    final bg = selected ? color : color.withValues(alpha: 0.12);
    final fg = selected ? Colors.white : c.ink;
    final iconColor = selected ? Colors.white : color;

    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 160),
        curve: Curves.easeOut,
        padding: const EdgeInsets.fromLTRB(14, 11, 16, 11),
        decoration: BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.circular(Dims.radiusPill),
          border: Border.all(
            color: selected ? color : color.withValues(alpha: 0.45),
            width: 1.5,
          ),
          boxShadow: selected ? Dims.liftLight : null,
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(glyph, size: 18, color: iconColor),
            const SizedBox(width: 8),
            Text(
              label,
              style: TextStyle(
                fontFamily: 'Space Grotesk',
                fontSize: 14,
                fontWeight: FontWeight.w600,
                color: fg,
              ),
            ),
            if (selected) ...[
              const SizedBox(width: 6),
              const Icon(Icons.check, size: 16, color: Colors.white),
            ],
          ],
        ),
      ),
    );
  }
}
