import 'package:flutter/material.dart';

const lensColors = <String, Color>{
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
    final color = lensColors[name] ?? const Color(0xFF616161);

    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        decoration: BoxDecoration(
          color: color,
          borderRadius: BorderRadius.circular(16),
          border: isSelected
              ? Border.all(color: Colors.white, width: 2)
              : null,
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
