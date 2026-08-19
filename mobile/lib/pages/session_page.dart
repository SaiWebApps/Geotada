import 'dart:async';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';
import 'package:ondoway/models/trip.dart';
import 'package:ondoway/services/tour_playback_service.dart';

/// THE MINIMAL SESSION SCREEN (Phase 5 S5.11; plan defect 12 — the phone had no
/// playback screen). It RENDERS what [TourPlaybackService] holds and decides
/// nothing (design §4.6): one or two lines — the next stop and its minutes, the
/// finish clock — the session's one line, a pending question as TWO BIG BUTTONS
/// with the default named in words (W5.2 R2.5, Rosemary: "two large buttons
/// under a thumb"), and [Head back now] on every screen (Nadia, R1.1). Never a
/// pause length, a count, "you paused", "behind by N" or a stopwatch (R4).
class SessionPage extends StatefulWidget {
  final String tripId;
  const SessionPage({super.key, required this.tripId});

  @override
  State<SessionPage> createState() => _SessionPageState();

  static String _minutes(int seconds) => ((seconds + 30) ~/ 60).toString();

  /// The first line of the screen: where you are, or the next stop and its
  /// minutes by the phone's own re-timing; "That was the walk." when done.
  /// Public so the demo transcript prints exactly what the screen shows.
  static String? nextLineFor(TourPlaybackService service) {
    if (service.state == TourState.completed) return 'That was the walk.';
    final etas = service.retimeRemaining();
    if (etas.isEmpty) return null;
    final next = etas.first;
    return next.secondsToArrival == 0
        ? "You're at ${next.stop.poiName}"
        : 'Next: ${next.stop.poiName} · ${_minutes(next.secondsToArrival)} min';
  }

  /// The finish clock: the phone's OWN re-timing while the walk runs (W5.13 —
  /// a precomputed line's clock is stale by the time it fires; the phone's is
  /// not), else the day's finish promise as planned.
  static String? finishLineFor(TourPlaybackService service) {
    final session = service.session;
    final name = session?.finishName ?? 'your finish';
    final eta = service.finishEtaSeconds;
    if (eta != null && service.state != TourState.completed) {
      final clock = service.dayFrameHhmm(eta);
      if (clock.isNotEmpty) return '$name by $clock';
    }
    final promises = session?.promises ?? const <SessionPromise>[];
    for (final p in promises) {
      if (p.kind == 'finish' && p.arrivesHhmm.isNotEmpty) {
        return '${p.name} by ${p.arrivesHhmm}';
      }
    }
    return null;
  }

}

class _SessionPageState extends State<SessionPage> {
  Timer? _ticker;

  @override
  void initState() {
    super.initState();
    // The geolocator sends no fix while nobody moves, so standing still is
    // measured by time passing: the screen ticks the service once a second.
    _ticker = Timer.periodic(const Duration(seconds: 1), (_) {
      if (!mounted) return;
      context.read<TourPlaybackService>().tick();
      setState(() {});
    });
  }

  @override
  void dispose() {
    _ticker?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final service = context.watch<TourPlaybackService>();
    final colors = Theme.of(context).colorScheme;
    final text = Theme.of(context).textTheme;

    if (!service.isActive && service.state != TourState.completed) {
      return Scaffold(
        appBar: AppBar(title: const Text('Your walk')),
        body: const Center(child: Text('No walk is running.')),
      );
    }

    final question = service.pendingQuestion;
    final entry = service.selectedContingency;
    final finish = SessionPage.finishLineFor(service);
    final nextLine = SessionPage.nextLineFor(service);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Your walk'),
        actions: [
          if (service.screenOnly)
            IconButton(
              key: const Key('session-speaker'),
              tooltip: 'Hear it again',
              icon: const Icon(Icons.volume_up),
              onPressed: service.restoreVoice,
            ),
        ],
      ),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (nextLine != null)
                Text(
                  nextLine,
                  key: const Key('session-next-line'),
                  style: text.headlineSmall,
                ),
              if (finish != null)
                Padding(
                  padding: const EdgeInsets.only(top: 6),
                  child: Text(finish,
                      key: const Key('session-finish-line'),
                      style: text.titleMedium),
                ),
              if (service.screenText != null && service.screenText != question)
                Padding(
                  padding: const EdgeInsets.only(top: 14),
                  child: Text(service.screenText!,
                      key: const Key('session-screen-text'),
                      style: text.bodyLarge),
                ),
              if (service.screenOnly)
                Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Text(TourPlaybackService.kScreenOnlyLine,
                      key: const Key('session-screen-only'),
                      style: text.bodySmall
                          ?.copyWith(color: colors.onSurfaceVariant)),
                ),
              if (service.finishMovedLine != null)
                Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Text(service.finishMovedLine!,
                      key: const Key('session-finish-moved'),
                      style: text.bodyMedium),
                ),
              for (final notice in service.clockNotices)
                Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Text(notice,
                      style: text.bodySmall
                          ?.copyWith(color: colors.onSurfaceVariant)),
                ),
              if (question != null) ...[
                const SizedBox(height: 22),
                Text(question,
                    key: const Key('session-question'),
                    style: text.titleMedium),
                const SizedBox(height: 12),
                ..._armButtons(context, service, question, entry),
              ],
              const Spacer(),
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton.icon(
                      key: const Key('session-pause'),
                      onPressed: service.isPaused
                          ? service.resumeTour
                          : service.pauseTour,
                      icon: Icon(
                          service.isPaused ? Icons.play_arrow : Icons.pause),
                      label: Text(service.isPaused ? 'Carry on' : 'Pause'),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: FilledButton.tonalIcon(
                      key: const Key('session-head-back'),
                      onPressed: () => _headBackNow(context, service),
                      icon: const Icon(Icons.home_outlined),
                      label: const Text('Head back now'),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  /// The ONE question as two big buttons, the default named in words (R2.5).
  /// The arms are the two clauses of the one sentence; the arm that KEEPS the
  /// protected thing answers `keep`, the other `shorten`.
  static List<Widget> _armButtons(
    BuildContext context,
    TourPlaybackService service,
    String question,
    SessionContingency? entry,
  ) {
    final body = question.endsWith('?')
        ? question.substring(0, question.length - 1)
        : question;
    final parts = body.split(', or ');
    if (parts.length != 2) {
      return [
        FilledButton(
          key: const Key('session-arm-default'),
          onPressed: () => service.answerQuestion(entry?.defaultArm ?? 'keep'),
          child: const Text('Carry on as planned'),
        ),
      ];
    }
    final keepFirst = parts[0].toLowerCase().startsWith('keep');
    final arms = [
      (parts[0], keepFirst ? 'keep' : 'shorten'),
      (parts[1], keepFirst ? 'shorten' : 'keep'),
    ];
    return [
      for (final (label, arm) in arms)
        Padding(
          padding: const EdgeInsets.only(bottom: 10),
          child: SizedBox(
            height: 64,
            child: FilledButton(
              key: Key('session-arm-$arm'),
              style: arm == entry?.defaultArm
                  ? null
                  : FilledButton.styleFrom(
                      backgroundColor:
                          Theme.of(context).colorScheme.secondaryContainer,
                      foregroundColor:
                          Theme.of(context).colorScheme.onSecondaryContainer,
                    ),
              onPressed: () => service.answerQuestion(arm),
              child: Text(
                arm == entry?.defaultArm
                    ? '${_cap(label)} — this happens if you do nothing'
                    : _cap(label),
                textAlign: TextAlign.center,
              ),
            ),
          ),
        ),
    ];
  }

  static String _cap(String s) =>
      s.isEmpty ? s : '${s[0].toUpperCase()}${s.substring(1)}';

  /// [Head back now]: the phone measures, MATCHES the wrap-up entry the server
  /// precomputed for this stop, and applies it — a selection, never a decision.
  static void _headBackNow(BuildContext context, TourPlaybackService service) {
    if (service.state == TourState.completed) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('The walk is over — nothing left to head back from.')),
      );
      return;
    }
    service.requestWrapUp();
    final entry = service.matchContingency(service.measure());
    if (entry != null) {
      service.applyContingency(entry.contingencyId);
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Heading back — the day ends from here.')),
      );
      service.stopTour();
      context.go('/saved-trips');
    }
  }
}
