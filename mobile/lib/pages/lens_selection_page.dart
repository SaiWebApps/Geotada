import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:ondoway/models/lens.dart';
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

    return Scaffold(
      backgroundColor: const Color(0xFF121212),
      body: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(24, 24, 24, 0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          widget.isOnboarding
                              ? 'Welcome, ${widget.userName ?? "Explorer"}'
                              : 'Your Lenses',
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 28,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                      ),
                      // Debug escape hatch (removed with the spike scaffolding):
                      // jumps to the auth-exempt tour-playback proof screen when a
                      // persisted session strands the tester here (prod lens API
                      // 404s). Header-right so it overlaps no tile or Continue.
                      if (!kReleaseMode)
                        IconButton(
                          tooltip: 'Debug: tour playback proof',
                          icon: const Icon(Icons.headphones,
                              color: Color(0xFF9E9E9E)),
                          onPressed: () =>
                              context.push('/debug/tour-playback-proof'),
                        ),
                    ],
                  ),
                  if (widget.isOnboarding) ...[
                    const SizedBox(height: 8),
                    const Text(
                      'Pick at least 3 — you can always change these later.',
                      style: TextStyle(color: Color(0xFF9E9E9E), fontSize: 15),
                    ),
                  ],
                  const SizedBox(height: 20),
                ],
              ),
            ),
            Expanded(
              child: ListView(
                padding: const EdgeInsets.symmetric(horizontal: 24),
                children: [
                  for (final entry in widget.lensesByParent.entries) ...[
                    Padding(
                      padding: const EdgeInsets.only(top: 16, bottom: 8),
                      child: Text(
                        entry.key.toUpperCase(),
                        style: const TextStyle(
                          color: Color(0xFF9E9E9E),
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
            Container(
              padding: const EdgeInsets.all(16),
              decoration: const BoxDecoration(
                color: Color(0xFF1A1A1A),
                border: Border(top: BorderSide(color: Color(0xFF2A2A2A))),
              ),
              child: Row(
                children: [
                  Text(
                    '${_selected.length} selected',
                    style: const TextStyle(color: Color(0xFF9E9E9E), fontSize: 15),
                  ),
                  const Spacer(),
                  if (widget.isOnboarding)
                    FilledButton(
                      onPressed: canContinue
                          ? () => widget.onComplete?.call(_selected)
                          : null,
                      style: FilledButton.styleFrom(
                        backgroundColor: canContinue
                            ? const Color(0xFF3D5AFE)
                            : const Color(0xFF2A2A2A),
                        foregroundColor: Colors.white,
                      ),
                      child: const Text('Continue'),
                    )
                  else
                    FilledButton(
                      onPressed: () => widget.onSave?.call(_selected),
                      style: FilledButton.styleFrom(
                        backgroundColor: const Color(0xFF3D5AFE),
                        foregroundColor: Colors.white,
                      ),
                      child: const Text('Save'),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
