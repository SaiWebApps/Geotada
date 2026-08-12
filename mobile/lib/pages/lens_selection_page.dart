import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:ondoway/models/lens.dart';
import 'package:ondoway/theme/tokens.dart';
import 'package:ondoway/widgets/lens_tile.dart';

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
            ),
            Expanded(
              child: ListView(
                padding: const EdgeInsets.fromLTRB(24, 4, 24, 24),
                children: [
                  for (final entry in widget.lensesByParent.entries) ...[
                    Padding(
                      padding: const EdgeInsets.only(top: 16, bottom: 8),
                      child: Text(
                        entry.key.toUpperCase(),
                        style: TextStyle(
                          fontFamily: 'Space Mono',
                          color: colors.inkMute,
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                          letterSpacing: 1.2,
                        ),
                      ),
                    ),
                    GridView.count(
                      crossAxisCount: 2,
                      shrinkWrap: true,
                      physics: const NeverScrollableScrollPhysics(),
                      mainAxisSpacing: 12,
                      crossAxisSpacing: 12,
                      childAspectRatio: 1.4,
                      children: entry.value.map((lens) {
                        return LensTile(
                          name: lens.name,
                          displayLabel: lens.displayLabel,
                          isSelected: _selected.contains(lens.id),
                          onTap: () => _toggle(lens.id),
                        );
                      }).toList(),
                    ),
                  ],
                ],
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
  const _Header({required this.c, required this.isOnboarding, this.userName});

  @override
  Widget build(BuildContext context) {
    final eyebrow = isOnboarding
        ? (userName != null && userName!.isNotEmpty
            ? 'WELCOME, ${userName!.toUpperCase()}'
            : 'LET’S PERSONALIZE')
        : 'PREFERENCES';
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 20, 24, 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
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
                    const SizedBox(height: 8),
                    Text(
                      isOnboarding ? 'What are you\ncurious about?' : 'Your lenses',
                      style: _fraunces(c.ink, 30, FontWeight.w600),
                    ),
                  ],
                ),
              ),
              // Debug escape hatch (removed with the spike scaffolding): jumps to
              // the auth-exempt tour-playback proof screen when a persisted session
              // strands the tester here (prod lens API 404s).
              if (!kReleaseMode)
                IconButton(
                  tooltip: 'Debug: tour playback proof',
                  icon: Icon(Icons.headphones, color: c.inkMute),
                  onPressed: () => context.push('/debug/tour-playback-proof'),
                ),
            ],
          ),
          if (isOnboarding) ...[
            const SizedBox(height: 10),
            Text(
              'Pick at least 3 — you can always change these later.',
              style: TextStyle(
                  fontFamily: 'Space Grotesk', color: c.inkMute, fontSize: 15, height: 1.3),
            ),
          ],
          const SizedBox(height: 12),
        ],
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
