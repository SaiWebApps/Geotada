import 'package:flutter/material.dart';
import 'package:ondoway/models/trip.dart';
import 'package:ondoway/services/tour_playback_service.dart';
import 'package:ondoway/theme/dims.dart';
import 'package:ondoway/widgets/tour/next_stop_banner.dart';
import 'package:ondoway/widgets/tour/stop_audio_card.dart';
import 'package:provider/provider.dart';

/// Full-screen hands-free audio walk. A thin view over [TourPlaybackService]:
/// the engine owns geofence/auto-play/auto-advance; this renders its state.
class TourWalkPage extends StatefulWidget {
  final GeneratedTrip trip;
  const TourWalkPage({super.key, required this.trip});

  @override
  State<TourWalkPage> createState() => _TourWalkPageState();
}

class _TourWalkPageState extends State<TourWalkPage> {
  // Captured in didChangeDependencies rather than looked up in dispose():
  // by the time dispose() runs, this widget's own element may already be
  // deactivated (e.g. during a full-tree teardown), and Provider's ancestor
  // lookup asserts the calling element is still active. Caching the
  // reference avoids that lookup entirely.
  TourPlaybackService? _engine;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _engine = context.read<TourPlaybackService>();
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _engine?.startTour(widget.trip.stops);
    });
  }

  @override
  void dispose() {
    // The engine tears down tracking + releases the ducked audio session.
    _engine?.stopTour();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final engine = context.watch<TourPlaybackService>();
    final audio = context.watch<AudioProvider>();
    final stop = engine.currentStop;

    return Scaffold(
      appBar: AppBar(title: Text(widget.trip.tripName)),
      body: SafeArea(
        child: engine.state == TourState.completed
            ? _CompletePanel(onDone: () => Navigator.of(context).maybePop())
            : Stack(
                children: [
                  stop == null
                      ? const Center(child: Text('Preparing your walk…'))
                      : Column(
                          children: [
                            _ProgressText(
                              index: engine.currentStopIndex,
                              total: widget.trip.stops.length,
                            ),
                            Expanded(
                              child: Center(
                                child: audio.isPlaying
                                    ? StopAudioCard(
                                        stop: stop,
                                        isPlaying: true,
                                        onReplay: () => engine.skipToStop(engine.currentStopIndex),
                                        onSkip: () => engine.skipToStop(engine.currentStopIndex + 1),
                                      )
                                    : NextStopBanner(
                                        stopName: stop.poiName,
                                        distanceMeters: engine.distanceToNext,
                                      ),
                              ),
                            ),
                          ],
                        ),
                  if (engine.hasPendingStop && engine.nextStop != null)
                    Align(
                      alignment: Alignment.bottomCenter,
                      child: _ApproachingNudge(
                        stopName: engine.nextStop!.poiName,
                        onAccept: engine.acceptPendingStop,
                        onDismiss: engine.dismissPending,
                      ),
                    ),
                ],
              ),
      ),
    );
  }
}

class _ApproachingNudge extends StatelessWidget {
  final String stopName;
  final VoidCallback onAccept;
  final VoidCallback onDismiss;
  const _ApproachingNudge({
    required this.stopName, required this.onAccept, required this.onDismiss});

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.all(Dims.spaceMd),
      child: Padding(
        padding: const EdgeInsets.all(Dims.spaceMd),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text('Approaching $stopName', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: Dims.spaceSm),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceEvenly,
              children: [
                TextButton(
                  onPressed: onDismiss,
                  child: const Text('Keep listening'),
                ),
                FilledButton(
                  key: const Key('tour-nudge-accept'),
                  onPressed: onAccept,
                  child: const Text('Play now'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _CompletePanel extends StatelessWidget {
  final VoidCallback onDone;
  const _CompletePanel({required this.onDone});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text('Tour complete', style: Theme.of(context).textTheme.headlineSmall),
          const SizedBox(height: Dims.spaceSm + Dims.spaceXs),
          FilledButton(onPressed: onDone, child: const Text('Done')),
        ],
      ),
    );
  }
}

class _ProgressText extends StatelessWidget {
  final int index;
  final int total;
  const _ProgressText({required this.index, required this.total});

  @override
  Widget build(BuildContext context) {
    final n = index < 0 ? 1 : index + 1;
    return Padding(
      padding: const EdgeInsets.all(Dims.spaceMd),
      child: Text('Stop $n of $total', style: Theme.of(context).textTheme.labelLarge),
    );
  }
}
