import 'package:flutter/material.dart';
import 'package:ondoway/models/trip.dart';
import 'package:ondoway/services/tour_playback_service.dart';
import 'package:ondoway/theme/dims.dart';
import 'package:ondoway/theme/theme.dart';
import 'package:ondoway/theme/tokens.dart';
import 'package:provider/provider.dart';

/// Full-screen hands-free audio walk (wireframe 05 · Live guide) — a dark,
/// audio-led screen: a glowing route backdrop (a placeholder for the real
/// MapView seam), a next-stop banner, and a premium now-playing player. A thin
/// view over [TourPlaybackService]: the engine owns geofence/auto-play/advance.
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
              const _RouteBackdrop(),
              SafeArea(
                child: engine.state == TourState.completed
                    ? _CompletePanel(
                        c: c, onDone: () => Navigator.of(context).maybePop())
                    : Stack(
                        children: [
                          if (stop != null)
                            Align(
                              alignment: Alignment.topCenter,
                              child: _DirectionBanner(
                                c: c,
                                headingStop: stop,
                                nextStop: engine.nextStop,
                                distanceMeters: engine.distanceToNext,
                                noAudio: stop.audioUrl == null,
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

class _RouteBackdrop extends StatelessWidget {
  const _RouteBackdrop();

  @override
  Widget build(BuildContext context) {
    final c = Theme.of(context).extension<OndowayColors>()!;
    return DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [c.panel, c.bg],
        ),
      ),
      child: CustomPaint(painter: _RoutePainter(c.accent), size: Size.infinite),
    );
  }
}

class _RoutePainter extends CustomPainter {
  final Color color;
  _RoutePainter(this.color);

  @override
  void paint(Canvas canvas, Size size) {
    final path = Path();
    final x = size.width * 0.5;
    path.moveTo(x + 40, size.height * 0.25);
    path.cubicTo(
      x + 40, size.height * 0.4,
      x - 90, size.height * 0.45,
      x - 60, size.height * 0.6,
    );
    path.cubicTo(
      x - 40, size.height * 0.72,
      x + 30, size.height * 0.72,
      x, size.height * 0.85,
    );

    final glow = Paint()
      ..color = color.withValues(alpha: 0.35)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 10
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 8);
    canvas.drawPath(path, glow);

    // Dotted core along the path.
    final metrics = path.computeMetrics().toList();
    final dot = Paint()..color = color;
    for (final m in metrics) {
      for (double d = 0; d < m.length; d += 16) {
        final pos = m.getTangentForOffset(d)?.position;
        if (pos != null) canvas.drawCircle(pos, 3, dot);
      }
    }
  }

  @override
  bool shouldRepaint(covariant _RoutePainter old) => old.color != color;
}

class _DirectionBanner extends StatelessWidget {
  final OndowayColors c;
  final ItineraryStop headingStop;
  final ItineraryStop? nextStop;
  final double? distanceMeters;
  final bool noAudio;
  const _DirectionBanner({
    required this.c,
    required this.headingStop,
    required this.nextStop,
    required this.distanceMeters,
    required this.noAudio,
  });

  @override
  Widget build(BuildContext context) {
    final dist = distanceMeters == null
        ? 'Finding your location…'
        : distanceMeters! < 1000
            ? '${distanceMeters!.round()} m to ${headingStop.poiName}'
            : '${(distanceMeters! / 1000).toStringAsFixed(1)} km to ${headingStop.poiName}';
    return Container(
      margin: const EdgeInsets.all(Dims.spaceMd),
      padding: const EdgeInsets.all(Dims.spaceMd),
      decoration: BoxDecoration(
        color: c.card.withValues(alpha: 0.92),
        borderRadius: BorderRadius.circular(Dims.radiusCard),
      ),
      child: Row(
        children: [
          Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(
              color: _cobalt,
              borderRadius: BorderRadius.circular(Dims.spaceSm + Dims.spaceXs),
            ),
            child: const Icon(Icons.navigation_rounded,
                color: Colors.white, size: 22),
          ),
          const SizedBox(width: Dims.spaceMd),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  noAudio ? 'No audio here — keep walking' : 'Head to your stop',
                  style: TextStyle(
                      color: c.ink,
                      fontFamily: 'Space Grotesk',
                      fontWeight: FontWeight.w600,
                      fontSize: 15),
                ),
                const SizedBox(height: 2),
                Text(dist, style: TextStyle(color: c.inkMute, fontSize: 13)),
              ],
            ),
          ),
        ],
      ),
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
  final VoidCallback onSkip;
  const _WalkingBar({required this.c, required this.onSkip});

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
            child: Text('Walk to the next stop — audio starts on arrival',
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
