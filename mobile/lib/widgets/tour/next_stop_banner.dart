import 'package:flutter/material.dart';
import 'package:ondoway/theme/dims.dart';

/// "220 m" under a kilometre, "1.2 km" above. Whole metres, one decimal km.
String formatDistance(double meters) {
  if (meters < 1000) return '${meters.round()} m';
  return '${(meters / 1000).toStringAsFixed(1)} km';
}

/// The walking-state banner: where you're headed and how far.
class NextStopBanner extends StatelessWidget {
  final String stopName;
  final double? distanceMeters;

  const NextStopBanner({
    super.key,
    required this.stopName,
    required this.distanceMeters,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final distanceLabel = distanceMeters == null
        ? 'Finding your location…'
        : '${formatDistance(distanceMeters!)} ahead';
    return Padding(
      padding: const EdgeInsets.all(Dims.spaceMd),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Next stop', style: theme.textTheme.labelMedium),
          const SizedBox(height: Dims.spaceXs),
          Text(stopName, style: theme.textTheme.headlineSmall),
          const SizedBox(height: Dims.spaceXs),
          Text(distanceLabel, style: theme.textTheme.bodyMedium),
        ],
      ),
    );
  }
}
