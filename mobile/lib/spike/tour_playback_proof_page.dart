import 'dart:io';
import 'dart:math';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';
import 'package:ondoway/models/trip.dart';
import 'package:ondoway/services/audio_service.dart';
import 'package:ondoway/services/location_service.dart';
import 'package:ondoway/services/tour_playback_service.dart';

/// Debug-only harness proving the PRODUCTION tour-playback path plays audio
/// through a locked screen. Two stops are placed ~15m and ~30m ahead of the
/// current position; the tester locks the phone, pockets it, and walks forward.
class TourPlaybackProofPage extends StatefulWidget {
  const TourPlaybackProofPage({super.key});

  @override
  State<TourPlaybackProofPage> createState() => _TourPlaybackProofPageState();
}

class _TourPlaybackProofPageState extends State<TourPlaybackProofPage>
    with WidgetsBindingObserver {
  final List<String> _log = [];

  /// Compass label -> bearing in degrees clockwise from north.
  static const Map<String, double> _directions = {
    'N': 0,
    'NE': 45,
    'E': 90,
    'SE': 135,
    'S': 180,
    'SW': 225,
    'W': 270,
    'NW': 315,
  };
  String _selectedDir = 'N';

  // Instrumentation: refs + listeners that append a timestamped timeline so we
  // can read AFTER the walk whether the geofence fired WHILE locked (a location
  // question) vs. fired-but-stayed-silent (an audio question). The _log list
  // accumulates even while backgrounded — the listeners still run; only the
  // repaint defers to foreground.
  LocationService? _loc;
  AudioService? _audio;
  TourPlaybackService? _tour;
  bool _wiredListeners = false;

  String get _ts {
    final n = DateTime.now();
    String p(int x) => x.toString().padLeft(2, '0');
    return '${p(n.hour)}:${p(n.minute)}:${p(n.second)}';
  }

  void _onLocTick() {
    final d = _tour?.distanceToNext;
    _add('$_ts  pos  d=${d?.toStringAsFixed(1) ?? "—"}m  '
        'state=${_tour?.state.name}  idx=${_tour?.currentStopIndex}  '
        'playing=${_audio?.isPlaying}');
  }

  void _onAudioTick() {
    _add('$_ts  AUDIO  playing=${_audio?.isPlaying}  '
        'buffering=${_audio?.isBuffering}  beat=${_audio?.currentBeatId}');
  }

  void _add(String line) {
    if (!mounted) return;
    setState(() => _log.insert(0, line));
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // 'paused' ≈ screen locked / pocketed; 'resumed' ≈ unlocked. These bracket
    // the locked window in the log so we can see whether pos/AUDIO events land
    // inside it.
    _add('$_ts  ===== LIFECYCLE ${state.name} =====');
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _loc?.removeListener(_onLocTick);
    _audio?.removeListener(_onAudioTick);
    super.dispose();
  }

  /// Point [meters] from (lat,lng) along [bearingDeg] (clockwise from north).
  /// Flat-earth approximation — fine at the ~30m scale of this proof.
  (double, double) _offsetAlongBearing(
      double lat, double lng, double meters, double bearingDeg) {
    final b = bearingDeg * pi / 180.0;
    final dLat = (meters * cos(b)) / 111320.0;
    final dLng = (meters * sin(b)) / (111320.0 * cos(lat * pi / 180.0));
    return (lat + dLat, lng + dLng);
  }

  // Mirrors AudioService's cache convention (temp/ondoway_audio/<beatId>.mp3) so
  // startTour plays a LOCAL file, not a cold URL stream. We reuse the spike's
  // bundled WAV written under a .mp3 name: iOS AVFoundation content-sniffs the
  // header, so the extension is only a hint and playback works. Debug only.
  Future<void> _cacheClip(String beatId) async {
    final bytes = await rootBundle.load('assets/audio/arrived.wav');
    final dir = Directory('${(await getTemporaryDirectory()).path}/ondoway_audio');
    if (!await dir.exists()) await dir.create(recursive: true);
    await File('${dir.path}/$beatId.mp3')
        .writeAsBytes(bytes.buffer.asUint8List());
  }

  Future<void> _startProof() async {
    final location = context.read<LocationService>();
    final tour = context.read<TourPlaybackService>();
    final audio = context.read<AudioService>();
    _loc = location;
    _tour = tour;
    _audio = audio;
    if (!_wiredListeners) {
      location.addListener(_onLocTick);
      audio.addListener(_onAudioTick);
      _wiredListeners = true;
    }

    final started = await location.startTracking(background: true);
    if (!started) {
      _add('Could not get location permission/tracking.');
      return;
    }
    // Give the fix a moment to arrive.
    await Future<void>.delayed(const Duration(seconds: 2));
    final pos = location.lastPosition;
    if (pos == null) {
      _add('No position yet — try again.');
      return;
    }
    location.stopTracking(); // startTour restarts it in background.

    await _cacheClip('proof-1');
    await _cacheClip('proof-2');

    final bearing = _directions[_selectedDir]!;
    final s1 = _offsetAlongBearing(pos.latitude, pos.longitude, 15.5, bearing);
    final s2 = _offsetAlongBearing(pos.latitude, pos.longitude, 31.0, bearing);
    final stops = [
      _proofStop(1, 'proof-1', s1.$1, s1.$2),
      _proofStop(2, 'proof-2', s2.$1, s2.$2),
    ];

    final ok = await tour.startTour(stops);
    _add(ok
        ? 'Tour started. Lock the phone, pocket it, walk $_selectedDir '
            '~15m then ~30m.'
        : 'startTour failed.');
  }

  ItineraryStop _proofStop(int order, String beatId, double lat, double lng) =>
      ItineraryStop(
        sortOrder: order,
        stopId: beatId,
        poiId: 'proof-poi-$order',
        poiName: 'Proof Stop $order',
        lat: lat,
        lng: lng,
        beatId: beatId,
        lensName: 'history',
        lensDisplay: 'History',
        durationMin: 1,
        importanceTier: 3,
        startTime: '09:0$order',
        audioUrl: 'cached://$beatId', // unused: cache hit wins in AudioService
      );

  @override
  Widget build(BuildContext context) {
    final tour = context.watch<TourPlaybackService>();
    return Scaffold(
      appBar: AppBar(title: const Text('Tour Playback Proof (debug)')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('State: ${tour.state}'),
            Text('Current stop index: ${tour.currentStopIndex}'),
            Text(tour.distanceToNext == null
                ? 'Distance to next: —'
                : 'Distance to next: ${tour.distanceToNext!.toStringAsFixed(1)} m'),
            const SizedBox(height: 12),
            const Text('Walk direction'),
            const SizedBox(height: 4),
            Wrap(
              spacing: 8,
              children: _directions.keys.map((d) {
                return ChoiceChip(
                  label: Text(d),
                  selected: _selectedDir == d,
                  onSelected: (_) => setState(() => _selectedDir = d),
                );
              }).toList(),
            ),
            const SizedBox(height: 12),
            FilledButton(
              onPressed: _startProof,
              child: Text('Prepare & start proof tour ($_selectedDir)'),
            ),
            const SizedBox(height: 8),
            OutlinedButton(
              onPressed: () {
                tour.stopTour();
                _add('Tour stopped.');
              },
              child: const Text('Stop'),
            ),
            const Divider(),
            const Text('Event log'),
            Expanded(
              child: ListView.builder(
                itemCount: _log.length,
                itemBuilder: (_, i) => Text(_log[i],
                    style: Theme.of(context).textTheme.bodySmall),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
