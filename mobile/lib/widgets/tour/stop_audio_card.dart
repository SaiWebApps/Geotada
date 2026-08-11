import 'package:flutter/material.dart';
import 'package:ondoway/models/trip.dart';
import 'package:ondoway/theme/dims.dart';

/// The story-state card: what's playing now + manual Replay/Skip.
class StopAudioCard extends StatelessWidget {
  final ItineraryStop stop;
  final bool isPlaying;
  final VoidCallback onReplay;
  final VoidCallback onSkip;

  const StopAudioCard({
    super.key,
    required this.stop,
    required this.isPlaying,
    required this.onReplay,
    required this.onSkip,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      margin: const EdgeInsets.all(Dims.spaceMd),
      child: Padding(
        padding: const EdgeInsets.all(Dims.spaceMd),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (stop.lensDisplay.isNotEmpty)
              Chip(label: Text(stop.lensDisplay)),
            const SizedBox(height: Dims.spaceXs),
            Text(stop.poiName, style: theme.textTheme.headlineSmall),
            const SizedBox(height: Dims.spaceXs),
            Text(isPlaying ? 'Playing…' : 'Paused', style: theme.textTheme.bodyMedium),
            const SizedBox(height: Dims.spaceSm),
            Row(
              children: [
                TextButton.icon(
                  key: const Key('tour-replay'),
                  onPressed: onReplay,
                  icon: const Icon(Icons.replay),
                  label: const Text('Replay'),
                ),
                const Spacer(),
                TextButton.icon(
                  key: const Key('tour-skip'),
                  onPressed: onSkip,
                  icon: const Icon(Icons.skip_next),
                  label: const Text('Skip'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
