import 'package:flutter/material.dart';

import '../theme/dims.dart';
import '../theme/lens_palette.dart';
import '../theme/tokens.dart';

/// A single interest chip: category-tinted when unselected, filled with its
/// category color + a check when selected. Flows in a Wrap so the picker packs
/// densely onto one screen instead of a sparse grid of big squares.
///
/// Motion (the difference between "a list of pills" and "engaging"): each chip
/// staggers in on mount (fade + rise + scale, delayed by [index]) and pops
/// slightly when selected. Both collapse to static under reduce-motion.
/// Colored literals live here (not the guarded selection page) as [LensTile] does.
class LensChip extends StatefulWidget {
  final String name;
  final String label;
  final bool selected;
  final int index;
  final VoidCallback onTap;

  const LensChip({
    super.key,
    required this.name,
    required this.label,
    required this.selected,
    required this.index,
    required this.onTap,
  });

  @override
  State<LensChip> createState() => _LensChipState();
}

class _LensChipState extends State<LensChip> with SingleTickerProviderStateMixin {
  // One controller spans the whole reveal window; each chip animates only during
  // its [Interval] slice, so the stagger needs no per-chip timer (which would
  // leave a pending timer in widget tests).
  static const int _windowMs = 720;
  late final AnimationController _entrance;
  late final Animation<double> _reveal;

  @override
  void initState() {
    super.initState();
    _entrance = AnimationController(
        vsync: this, duration: const Duration(milliseconds: _windowMs), value: 0);
    final start = (widget.index.clamp(0, 12) * 28) / _windowMs;
    final end = (start + 380 / _windowMs).clamp(0.0, 1.0);
    _reveal = CurvedAnimation(
        parent: _entrance, curve: Interval(start, end, curve: Curves.easeOutCubic));
    _entrance.forward();
  }

  @override
  void dispose() {
    _entrance.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final c = Theme.of(context).extension<OndowayColors>()!;
    final reduce = MediaQuery.maybeOf(context)?.disableAnimations ?? false;
    final color = kLensCategoryColors[widget.name] ?? const Color(0xFF616169);
    final glyph = kLensCategoryIcons[widget.name] ?? Icons.place_outlined;
    final selected = widget.selected;
    final bg = selected ? color : color.withValues(alpha: 0.16);
    final fg = selected ? Colors.white : c.ink;
    final iconColor = selected ? Colors.white : color;

    final chip = GestureDetector(
      onTap: widget.onTap,
      child: AnimatedScale(
        duration: const Duration(milliseconds: 170),
        curve: Curves.easeOutBack,
        scale: selected ? 1.05 : 1.0,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 160),
          curve: Curves.easeOut,
          padding: const EdgeInsets.fromLTRB(14, 11, 16, 11),
          decoration: BoxDecoration(
            color: bg,
            borderRadius: BorderRadius.circular(Dims.radiusPill),
            border: Border.all(
              color: selected ? color : color.withValues(alpha: 0.6),
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
                widget.label,
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
      ),
    );

    if (reduce) return chip;

    return AnimatedBuilder(
      animation: _reveal,
      child: chip,
      builder: (context, child) {
        final t = _reveal.value;
        return Opacity(
          opacity: t,
          child: Transform.translate(
            offset: Offset(0, (1 - t) * 10),
            child: Transform.scale(scale: 0.94 + 0.06 * t, child: child),
          ),
        );
      },
    );
  }
}
