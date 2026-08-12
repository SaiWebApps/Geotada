import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:ondoway/models/lens.dart';
import 'package:ondoway/theme/dims.dart';
import 'package:ondoway/theme/tokens.dart';
import 'package:ondoway/widgets/lens_chip.dart';

class LensSelectionPage extends StatefulWidget {
  final bool isOnboarding;
  final String? userName;
  final Map<String, List<Lens>> lensesByParent;
  final Set<String> initialSelection;
  final void Function(Set<String> selectedIds)? onComplete;
  final void Function(Set<String> selectedIds)? onSave;

  const LensSelectionPage({
    super.key,
    required this.isOnboarding,
    this.userName,
    required this.lensesByParent,
    this.initialSelection = const {},
    this.onComplete,
    this.onSave,
  });

  @override
  State<LensSelectionPage> createState() => _LensSelectionPageState();
}

class _LensSelectionPageState extends State<LensSelectionPage> {
  late Set<String> _selected;

  @override
  void initState() {
    super.initState();
    _selected = Set<String>.from(widget.initialSelection);
  }

  void _toggle(String lensId) {
    setState(() {
      if (_selected.contains(lensId)) {
        if (!widget.isOnboarding && _selected.length <= 1) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('You need at least one lens')),
          );
          return;
        }
        _selected.remove(lensId);
      } else {
        _selected.add(lensId);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final canContinue = _selected.length >= 3;
    final colors = Theme.of(context).extension<OndowayColors>()!;

    return Scaffold(
      backgroundColor: colors.bg,
      body: SafeArea(
        bottom: false,
        child: Column(
          children: [
            _Header(
              c: colors,
              isOnboarding: widget.isOnboarding,
              userName: widget.userName,
              selectedCount: _selected.length,
              // Only offer a back affordance in edit mode — onboarding is a
              // forced first-run step with nowhere to go back to.
              onBack: widget.isOnboarding
                  ? null
                  : () => Navigator.of(context).maybePop(),
            ),
            // One flowing cloud of every interest — color + icon carry the
            // category, so it packs densely onto a single screen instead of a
            // sparse grid. Chips stay grouped by category via source order.
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
                child: Wrap(
                  spacing: 10,
                  runSpacing: 12,
                  children: [
                    for (final entry in widget.lensesByParent.entries)
                      for (final lens in entry.value)
                        LensChip(
                          name: lens.name,
                          label: lens.displayLabel,
                          selected: _selected.contains(lens.id),
                          onTap: () => _toggle(lens.id),
                        ),
                  ],
                ),
              ),
            ),
            _Footer(
              c: colors,
              isOnboarding: widget.isOnboarding,
              selectedCount: _selected.length,
              canContinue: canContinue,
              onContinue: () => widget.onComplete?.call(_selected),
              onSave: () => widget.onSave?.call(_selected),
            ),
          ],
        ),
      ),
    );
  }
}

TextStyle _fraunces(Color color, double size, FontWeight weight) => TextStyle(
    fontFamily: 'Fraunces', color: color, fontSize: size, fontWeight: weight, height: 1.05);

class _Header extends StatelessWidget {
  final OndowayColors c;
  final bool isOnboarding;
  final String? userName;
  final int selectedCount;
  final VoidCallback? onBack;
  const _Header({
    required this.c,
    required this.isOnboarding,
    required this.selectedCount,
    this.userName,
    this.onBack,
  });

  @override
  Widget build(BuildContext context) {
    final eyebrow = isOnboarding
        ? (userName != null && userName!.isNotEmpty
            ? 'WELCOME, ${userName!.toUpperCase()}'
            : 'LET’S PERSONALIZE')
        : 'PREFERENCES';
    final target = isOnboarding ? 3 : 1;
    final progress = (selectedCount / target).clamp(0.0, 1.0);
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 8, 20, 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Top bar: back (edit mode) + the debug escape hatch.
          SizedBox(
            height: 44,
            child: Row(
              children: [
                if (onBack != null)
                  _CircleIconButton(
                    c: c,
                    icon: Icons.arrow_back,
                    tooltip: 'Back',
                    onTap: onBack!,
                  ),
                const Spacer(),
                // Debug escape hatch (removed with the spike scaffolding): jumps
                // to the auth-exempt tour-playback proof screen when a persisted
                // session strands the tester here (prod lens API 404s).
                if (!kReleaseMode)
                  IconButton(
                    tooltip: 'Debug: tour playback proof',
                    icon: Icon(Icons.headphones, color: c.inkMute),
                    onPressed: () => context.push('/debug/tour-playback-proof'),
                  ),
              ],
            ),
          ),
          Text(
            eyebrow,
            style: TextStyle(
              fontFamily: 'Space Mono',
              color: c.accent,
              fontSize: 12,
              fontWeight: FontWeight.w700,
              letterSpacing: 2.0,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            isOnboarding ? 'What are you curious about?' : 'Your lenses',
            style: _fraunces(c.ink, 26, FontWeight.w600),
          ),
          if (isOnboarding) ...[
            const SizedBox(height: 12),
            // Live progress toward the 3-lens minimum.
            ClipRRect(
              borderRadius: BorderRadius.circular(Dims.radiusPill),
              child: LinearProgressIndicator(
                value: progress,
                minHeight: 6,
                backgroundColor: c.line,
                valueColor: AlwaysStoppedAnimation<Color>(c.accent),
              ),
            ),
          ],
          const SizedBox(height: 4),
        ],
      ),
    );
  }
}

class _CircleIconButton extends StatelessWidget {
  final OndowayColors c;
  final IconData icon;
  final String tooltip;
  final VoidCallback onTap;
  const _CircleIconButton({
    required this.c,
    required this.icon,
    required this.tooltip,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: tooltip,
      child: Material(
        color: c.card,
        shape: const CircleBorder(),
        child: InkWell(
          customBorder: const CircleBorder(),
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.all(9),
            child: Icon(icon, size: 22, color: c.ink),
          ),
        ),
      ),
    );
  }
}

class _Footer extends StatelessWidget {
  final OndowayColors c;
  final bool isOnboarding;
  final int selectedCount;
  final bool canContinue;
  final VoidCallback onContinue;
  final VoidCallback onSave;
  const _Footer({
    required this.c,
    required this.isOnboarding,
    required this.selectedCount,
    required this.canContinue,
    required this.onContinue,
    required this.onSave,
  });

  @override
  Widget build(BuildContext context) {
    final remaining = 3 - selectedCount;
    final status = (isOnboarding && !canContinue)
        ? 'Choose $remaining more'
        : '$selectedCount selected';
    return Container(
      padding: EdgeInsets.fromLTRB(24, 14, 24, 14 + MediaQuery.of(context).padding.bottom),
      decoration: BoxDecoration(
        color: c.panel,
        border: Border(top: BorderSide(color: c.line)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            status,
            style: TextStyle(
              fontFamily: 'Space Mono',
              color: (isOnboarding && !canContinue) ? c.accent : c.inkMute,
              fontSize: 13,
              letterSpacing: 0.5,
            ),
          ),
          const SizedBox(height: 10),
          if (isOnboarding)
            FilledButton(
              onPressed: canContinue ? onContinue : null,
              child: const Text('Continue'),
            )
          else
            FilledButton(
              onPressed: onSave,
              child: const Text('Save'),
            ),
        ],
      ),
    );
  }
}

