import 'package:flutter/material.dart';

import '../theme/dims.dart';
import '../theme/tokens.dart';

/// The three stages a tour download/build passes through before playback.
enum PrepareStage { preparing, downloading, ready }

const Map<PrepareStage, String> _stageLabels = {
  PrepareStage.preparing: 'Preparing',
  PrepareStage.downloading: 'Downloading',
  PrepareStage.ready: 'Ready',
};

/// Horizontal Preparing -> Downloading -> Ready progress strip. The active
/// stage's label is rendered in the accent color; the others in a muted ink.
class PrepareStrip extends StatelessWidget {
  const PrepareStrip({super.key, required this.stage});

  final PrepareStage stage;

  @override
  Widget build(BuildContext context) {
    final tokens = Theme.of(context).extension<OndowayColors>()!;

    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        for (final entry in _stageLabels.entries) ...[
          if (entry.key != _stageLabels.keys.first) ...[
            const SizedBox(width: Dims.spaceSm),
            Icon(Icons.chevron_right, size: 16, color: tokens.lineSoft),
            const SizedBox(width: Dims.spaceSm),
          ],
          Text(
            entry.value,
            style: TextStyle(
              color: entry.key == stage ? tokens.accent : tokens.inkMute,
              fontWeight: entry.key == stage ? FontWeight.w700 : FontWeight.w400,
            ),
          ),
        ],
      ],
    );
  }
}
