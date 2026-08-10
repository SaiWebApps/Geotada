import 'package:flutter/material.dart';

import '../theme/dims.dart';
import '../theme/lens_palette.dart';
import '../theme/theme.dart';
import '../theme/tokens.dart';
import '../widgets/lens_tile.dart';
import '../widgets/location_pill.dart';
import '../widgets/ondoway_buttons.dart';
import '../widgets/prepare_strip.dart';

/// Debug-only page (`/debug/style-gallery`) that renders every design-system
/// token and component in one place for on-device visual verification.
/// Never linked from product navigation — reachable only via the `/debug/*`
/// route block, which is itself gated out of release builds.
class StyleGalleryPage extends StatelessWidget {
  const StyleGalleryPage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Style Gallery')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(Dims.spaceLg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _SectionHeader('Colors — light'),
            const SizedBox(height: Dims.spaceSm),
            Theme(
              data: buildOndowayTheme(Brightness.light),
              child: const _ColorSwatchRow(),
            ),
            const SizedBox(height: Dims.spaceLg),
            _SectionHeader('Colors — dark'),
            const SizedBox(height: Dims.spaceSm),
            Theme(
              data: buildOndowayTheme(Brightness.dark),
              child: const _ColorSwatchRow(),
            ),
            const SizedBox(height: Dims.spaceXl),
            _SectionHeader('Type scale'),
            const SizedBox(height: Dims.spaceSm),
            const _TypeScale(),
            const SizedBox(height: Dims.spaceXl),
            _SectionHeader('Buttons'),
            const SizedBox(height: Dims.spaceSm),
            Wrap(
              spacing: Dims.spaceMd,
              runSpacing: Dims.spaceMd,
              children: [
                OndowayPrimaryButton(label: 'Primary', onPressed: () {}),
                OndowayOutlineButton(label: 'Outline', onPressed: () {}),
              ],
            ),
            const SizedBox(height: Dims.spaceXl),
            _SectionHeader('Lens tile'),
            const SizedBox(height: Dims.spaceSm),
            Row(
              children: [
                Expanded(
                  child: SizedBox(
                    height: 120,
                    child: LensTile(
                      name: 'historic_arch',
                      displayLabel: 'Historic Architecture',
                      isSelected: true,
                      onTap: () {},
                    ),
                  ),
                ),
                const SizedBox(width: Dims.spaceMd),
                Expanded(
                  child: SizedBox(
                    height: 120,
                    child: LensTile(
                      name: 'street_art',
                      displayLabel: 'Street Art',
                      isSelected: false,
                      onTap: () {},
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: Dims.spaceXl),
            _SectionHeader('Lens categories (all 21)'),
            const SizedBox(height: Dims.spaceSm),
            const _LensCategorySwatches(),
            const SizedBox(height: Dims.spaceXl),
            _SectionHeader('Card'),
            const SizedBox(height: Dims.spaceSm),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(Dims.spaceMd),
                child: Text(
                  'Sample card content',
                  style: Theme.of(context).textTheme.bodyLarge,
                ),
              ),
            ),
            const SizedBox(height: Dims.spaceXl),
            _SectionHeader('Location pill'),
            const SizedBox(height: Dims.spaceSm),
            const OndowayLocationPill(label: 'Le Marais, Paris'),
            const SizedBox(height: Dims.spaceXl),
            _SectionHeader('Prepare strip'),
            const SizedBox(height: Dims.spaceSm),
            const PrepareStrip(stage: PrepareStage.preparing),
            const SizedBox(height: Dims.spaceSm),
            const PrepareStrip(stage: PrepareStage.downloading),
            const SizedBox(height: Dims.spaceSm),
            const PrepareStrip(stage: PrepareStage.ready),
          ],
        ),
      ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  const _SectionHeader(this.label);
  final String label;

  @override
  Widget build(BuildContext context) {
    return Text(label, style: Theme.of(context).textTheme.titleLarge);
  }
}

class _ColorSwatchRow extends StatelessWidget {
  const _ColorSwatchRow();

  @override
  Widget build(BuildContext context) {
    final tokens = Theme.of(context).extension<OndowayColors>()!;
    final swatches = <String, Color>{
      'accent': tokens.accent,
      'accentDeep': tokens.accentDeep,
      'accentLight': tokens.accentLight,
      'bg': tokens.bg,
      'card': tokens.card,
      'panel': tokens.panel,
      'ink': tokens.ink,
      'inkSoft': tokens.inkSoft,
      'inkMute': tokens.inkMute,
      'line': tokens.line,
      'lineSoft': tokens.lineSoft,
      'spark': tokens.spark,
      'onAccent': tokens.onAccent,
    };

    return Container(
      color: tokens.bg,
      padding: const EdgeInsets.all(Dims.spaceMd),
      child: Wrap(
        spacing: Dims.spaceMd,
        runSpacing: Dims.spaceMd,
        children: [
          for (final entry in swatches.entries)
            Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  width: 56,
                  height: 56,
                  decoration: BoxDecoration(
                    color: entry.value,
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: tokens.line),
                  ),
                ),
                const SizedBox(height: Dims.spaceXs),
                Text(
                  entry.key,
                  style: TextStyle(color: tokens.ink, fontSize: 11),
                ),
              ],
            ),
        ],
      ),
    );
  }
}

class _LensCategorySwatches extends StatelessWidget {
  const _LensCategorySwatches();

  @override
  Widget build(BuildContext context) {
    final tokens = Theme.of(context).extension<OndowayColors>()!;
    return Wrap(
      spacing: Dims.spaceMd,
      runSpacing: Dims.spaceMd,
      children: [
        for (final entry in kLensCategoryColors.entries)
          SizedBox(
            width: 96,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  height: 44,
                  decoration: BoxDecoration(
                    color: entry.value,
                    borderRadius: BorderRadius.circular(10),
                  ),
                ),
                const SizedBox(height: Dims.spaceXs),
                Text(
                  entry.key,
                  style: TextStyle(color: tokens.inkMute, fontSize: 10),
                ),
              ],
            ),
          ),
      ],
    );
  }
}

class _TypeScale extends StatelessWidget {
  const _TypeScale();

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Display large', style: text.displayLarge),
        Text('Headline large', style: text.headlineLarge),
        Text('Title large', style: text.titleLarge),
        Text('Body large', style: text.bodyLarge),
        Text('Body medium', style: text.bodyMedium),
        Text('Label large', style: text.labelLarge),
      ],
    );
  }
}
