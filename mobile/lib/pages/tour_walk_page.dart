import 'package:apple_maps_flutter/apple_maps_flutter.dart';
import 'package:flutter/material.dart';
import 'package:ondoway/models/trip.dart';
import 'package:ondoway/services/tour_playback_service.dart';
import 'package:ondoway/theme/dims.dart';
import 'package:ondoway/theme/theme.dart';
import 'package:ondoway/theme/tokens.dart';
import 'package:provider/provider.dart';

/// Full-screen hands-free audio walk (wireframe 05 · Live guide) — a dark,
/// audio-led screen: a basic Apple Map with stop pins behind a next-stop banner
/// and a premium now-playing player. A thin view over [TourPlaybackService]:
/// the engine owns geofence/auto-play/advance. Dark map styling, the route
/// polyline, camera-follow and a live scrubber are tracked in
/// specs/2026-08-11-exec-live-walk/live-guide-backlog.md.
class TourWalkPage extends StatefulWidget {
  final GeneratedTrip trip;
  const TourWalkPage({super.key, required this.trip});

  @override
  State<TourWalkPage> createState() => _TourWalkPageState();
}

class _TourWalkPageState extends State<TourWalkPage> {
  // See prior note: cached in didChangeDependencies so dispose() doesn't do a
  // Provider ancestor lookup on a possibly-deactivated element.
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
      if (!mounted) return;
      _engine?.startTour(widget.trip.stops);
    });
  }

  @override
  void dispose() {
    _engine?.stopTour();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final engine = context.watch<TourPlaybackService>();
    final audio = context.watch<AudioProvider>();
    final stop = engine.currentStop;

    // The live guide is always dark, regardless of the app theme.
    return Theme(
      data: buildOndowayTheme(Brightness.dark),
      child: Builder(builder: (context) {
        final c = Theme.of(context).extension<OndowayColors>()!;
        return Scaffold(
          backgroundColor: c.bg,
          body: Stack(
            fit: StackFit.expand,
            children: [
              _MapBackdrop(
                stops: widget.trip.stops,
                currentIndex: engine.currentStopIndex,
              ),
              SafeArea(
                child: engine.state == TourState.completed
                    ? _CompletePanel(
                        c: c, onDone: () => Navigator.of(context).maybePop())
                    : Stack(
                        children: [
                          // Always-available exit from the immersive walk.
                          Align(
                            alignment: Alignment.topLeft,
                            child: Padding(
                              padding: const EdgeInsets.all(8),
                              child: _WalkExitButton(
                                c: c,
                                onTap: () => Navigator.of(context).maybePop(),
                              ),
                            ),
                          ),
                          if (stop != null)
                            Align(
                              alignment: Alignment.bottomCenter,
                              child: audio.isPlaying
                                  ? _NowPlayingPlayer(
                                      c: c,
                                      stop: stop,
                                      index: engine.currentStopIndex,
                                      total: widget.trip.stops.length,
                                      isPlaying: true,
                                      onPrev: () => engine
                                          .skipToStop(engine.currentStopIndex),
                                      onPlayPause: () => audio.stop(),
                                      onNext: () => engine.skipToStop(
                                          engine.currentStopIndex + 1),
                                    )
                                  : _WalkingBar(
                                      c: c,
                                      noAudio: stop.audioUrl == null,
                                      onSkip: () => engine.skipToStop(
                                          engine.currentStopIndex + 1),
                                    ),
                            ),
                          if (stop == null)
                            Center(
                              child: Text('Preparing your walk…',
                                  style: TextStyle(color: c.inkSoft)),
                            ),
                          if (engine.hasPendingStop && engine.nextStop != null)
                            Align(
                              alignment: Alignment.center,
                              child: _ApproachingNudge(
                                c: c,
                                stopName: engine.nextStop!.poiName,
                                onAccept: engine.acceptPendingStop,
                                onDismiss: engine.dismissPending,
                              ),
                            ),
                        ],
                      ),
              ),
            ],
          ),
        );
      }),
    );
  }
}

/// Cobalt to match the wireframe's route + play button (the dark theme's accent
/// is a lighter blue used for the softer glow).
Color get _cobalt => OndowayColors.light.accent;

String _clock(double? seconds) {
  final s = (seconds ?? 0).round();
  final m = s ~/ 60;
  final r = s % 60;
  return '$m:${r.toString().padLeft(2, '0')}';
}

/// Circular close button that exits the immersive walk. Sits over the dark map,
/// so it carries its own translucent scrim for contrast.
class _WalkExitButton extends StatelessWidget {
  final OndowayColors c;
  final VoidCallback onTap;
  const _WalkExitButton({required this.c, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.black.withValues(alpha: 0.45),
      shape: const CircleBorder(),
      child: InkWell(
        customBorder: const CircleBorder(),
        onTap: onTap,
        child: const Tooltip(
          message: 'End walk',
          child: Padding(
            padding: EdgeInsets.all(9),
            child: Icon(Icons.close, size: 22, color: Colors.white),
          ),
        ),
      ),
    );
  }
}

/// The real map behind the guide: a basic Apple Map centered on the current
/// stop, with a pin per stop. Dark map styling + the route polyline +
/// camera-follow are tracked in live-guide-backlog.md (the MapView seam).
class _MapBackdrop extends StatelessWidget {
  final List<ItineraryStop> stops;
  final int currentIndex;
  const _MapBackdrop({required this.stops, required this.currentIndex});

  @override
  Widget build(BuildContext context) {
    if (stops.isEmpty) return const ColoredBox(color: Colors.black);
    final idx = (currentIndex >= 0 && currentIndex < stops.length) ? currentIndex : 0;
    final center = stops[idx];
    return AppleMap(
      initialCameraPosition: CameraPosition(
        target: LatLng(center.lat, center.lng),
        zoom: 15,
      ),
      myLocationEnabled: true,
      annotations: {
        for (final s in stops)
          Annotation(
            annotationId: AnnotationId(s.stopId ?? s.beatId),
            position: LatLng(s.lat, s.lng),
            infoWindow: InfoWindow(title: s.poiName),
          ),
      },
    );
  }
}

class _NowPlayingPlayer extends StatelessWidget {
  final OndowayColors c;
  final ItineraryStop stop;
  final int index;
  final int total;
  final bool isPlaying;
  final VoidCallback onPrev;
  final VoidCallback onPlayPause;
  final VoidCallback onNext;
  const _NowPlayingPlayer({
    required this.c,
    required this.stop,
    required this.index,
    required this.total,
    required this.isPlaying,
    required this.onPrev,
    required this.onPlayPause,
    required this.onNext,
  });

  @override
  Widget build(BuildContext context) {
    final n = index < 0 ? 1 : index + 1;
    final durationSec = stop.audioDurationSec;
    return Container(
      margin: const EdgeInsets.all(Dims.spaceMd),
      padding: const EdgeInsets.all(Dims.spaceLg),
      decoration: BoxDecoration(
        color: c.card,
        borderRadius: BorderRadius.circular(28),
        border: Border.all(color: c.line),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 60,
                height: 60,
                decoration: BoxDecoration(
                  color: c.spark.withValues(alpha: 0.85),
                  borderRadius: BorderRadius.circular(Dims.spaceMd),
                ),
                child: const Icon(Icons.headphones_rounded, color: Colors.white),
              ),
              const SizedBox(width: Dims.spaceMd),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    if (stop.lensDisplay.isNotEmpty)
                      Text(
                        stop.lensDisplay.toUpperCase(),
                        style: TextStyle(
                            color: c.spark,
                            fontFamily: 'Space Mono',
                            fontSize: 11,
                            letterSpacing: 1.2,
                            fontWeight: FontWeight.w700),
                      ),
                    const SizedBox(height: Dims.spaceXs),
                    Text(
                      stop.poiName,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                          color: c.ink,
                          fontFamily: 'Fraunces',
                          fontSize: 22,
                          height: 1.1,
                          fontWeight: FontWeight.w600),
                    ),
                    const SizedBox(height: Dims.spaceXs),
                    Text('Stop $n of $total',
                        style: TextStyle(color: c.inkMute, fontSize: 13)),
                  ],
                ),
              ),
              Icon(Icons.menu_rounded, color: c.inkMute),
            ],
          ),
          const SizedBox(height: Dims.spaceMd),
          // Scrubber (visual — live position awaits an AudioProvider seam).
          Row(
            children: [
              Text(_clock(0), style: TextStyle(color: c.inkMute, fontSize: 12)),
              Expanded(
                child: Padding(
                  padding:
                      const EdgeInsets.symmetric(horizontal: Dims.spaceSm),
                  child: ClipRRect(
                    borderRadius: BorderRadius.circular(Dims.radiusPill),
                    child: LinearProgressIndicator(
                      value: 0.28,
                      minHeight: 4,
                      backgroundColor: c.line,
                      valueColor: AlwaysStoppedAnimation<Color>(_cobalt),
                    ),
                  ),
                ),
              ),
              Text('-${_clock(durationSec)}',
                  style: TextStyle(color: c.inkMute, fontSize: 12)),
            ],
          ),
          const SizedBox(height: Dims.spaceMd),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              IconButton(
                key: const Key('tour-replay'),
                onPressed: onPrev,
                icon: Icon(Icons.skip_previous_rounded, color: c.ink, size: 32),
              ),
              const SizedBox(width: Dims.spaceLg),
              GestureDetector(
                key: const Key('tour-playpause'),
                onTap: onPlayPause,
                child: Container(
                  width: 68,
                  height: 68,
                  decoration: BoxDecoration(
                    color: _cobalt,
                    shape: BoxShape.circle,
                    boxShadow: [
                      BoxShadow(
                        color: _cobalt.withValues(alpha: 0.5),
                        blurRadius: 20,
                        spreadRadius: 1,
                      ),
                    ],
                  ),
                  child: Icon(
                    isPlaying ? Icons.pause_rounded : Icons.play_arrow_rounded,
                    color: Colors.white,
                    size: 34,
                  ),
                ),
              ),
              const SizedBox(width: Dims.spaceLg),
              IconButton(
                key: const Key('tour-skip'),
                onPressed: onNext,
                icon: Icon(Icons.skip_next_rounded, color: c.ink, size: 32),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _WalkingBar extends StatelessWidget {
  final OndowayColors c;
  final bool noAudio;
  final VoidCallback onSkip;
  const _WalkingBar(
      {required this.c, required this.onSkip, this.noAudio = false});

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.all(Dims.spaceMd),
      padding: const EdgeInsets.symmetric(
          horizontal: Dims.spaceLg, vertical: Dims.spaceMd),
      decoration: BoxDecoration(
        color: c.card,
        borderRadius: BorderRadius.circular(Dims.radiusPill),
        border: Border.all(color: c.line),
      ),
      child: Row(
        children: [
          Icon(Icons.directions_walk_rounded, color: c.inkSoft),
          const SizedBox(width: Dims.spaceSm),
          Expanded(
            child: Text(
                noAudio
                    ? 'No audio here — walk to the next stop'
                    : 'Walk to the next stop — audio starts on arrival',
                style: TextStyle(color: c.inkSoft, fontSize: 13)),
          ),
          TextButton(
            key: const Key('tour-walking-skip'),
            onPressed: onSkip,
            child: const Text('Skip'),
          ),
        ],
      ),
    );
  }
}

class _ApproachingNudge extends StatelessWidget {
  final OndowayColors c;
  final String stopName;
  final VoidCallback onAccept;
  final VoidCallback onDismiss;
  const _ApproachingNudge({
    required this.c,
    required this.stopName,
    required this.onAccept,
    required this.onDismiss,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.all(Dims.spaceMd),
      padding: const EdgeInsets.all(Dims.spaceLg),
      decoration: BoxDecoration(
        color: c.card,
        borderRadius: BorderRadius.circular(Dims.radiusCard),
        border: Border.all(color: c.line),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text('Approaching $stopName',
              style: TextStyle(
                  color: c.ink,
                  fontFamily: 'Fraunces',
                  fontSize: 18,
                  fontWeight: FontWeight.w600)),
          const SizedBox(height: Dims.spaceMd),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceEvenly,
            children: [
              TextButton(
                  onPressed: onDismiss, child: const Text('Keep listening')),
              FilledButton(
                key: const Key('tour-nudge-accept'),
                onPressed: onAccept,
                child: const Text('Play now'),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _CompletePanel extends StatelessWidget {
  final OndowayColors c;
  final VoidCallback onDone;
  const _CompletePanel({required this.c, required this.onDone});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.check_circle_outline_rounded, color: c.accent, size: 56),
          const SizedBox(height: Dims.spaceMd),
          Text('Tour complete',
              style: TextStyle(
                  color: c.ink,
                  fontFamily: 'Fraunces',
                  fontSize: 26,
                  fontWeight: FontWeight.w600)),
          const SizedBox(height: Dims.spaceMd),
          FilledButton(onPressed: onDone, child: const Text('Done')),
        ],
      ),
    );
  }
}
