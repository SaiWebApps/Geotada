import 'package:flutter/material.dart';

import '../theme/lens_palette.dart';
import '../theme/tokens.dart';

class LensTile extends StatelessWidget {
  final String name;
  final String displayLabel;
  final bool isSelected;
  final VoidCallback onTap;

  const LensTile({
    super.key,
    required this.name,
    required this.displayLabel,
    required this.isSelected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final color = kLensCategoryColors[name] ?? const Color(0xFF616161);
    final tokens = Theme.of(context).extension<OndowayColors>()!;
    final ringColor = isSelected ? tokens.accent : tokens.line;

    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        decoration: BoxDecoration(
          color: color,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: ringColor, width: isSelected ? 2 : 1),
        ),
        child: Stack(
          children: [
            Positioned(
              left: 12,
              bottom: 12,
              right: 40,
              child: Text(
                displayLabel,
                style: const TextStyle(
                  color: Colors.white,
                  fontWeight: FontWeight.bold,
                  fontSize: 15,
                ),
              ),
            ),
            if (isSelected)
              Positioned(
                top: 8,
                right: 8,
                child: Container(
                  width: 24,
                  height: 24,
                  decoration: const BoxDecoration(
                    color: Colors.white,
                    shape: BoxShape.circle,
                  ),
                  child: Icon(Icons.check, size: 16, color: color),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
