import 'dart:io';
import 'package:apple_maps_flutter/apple_maps_flutter.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';
import 'package:ondoway/models/trip.dart';
import 'package:ondoway/services/audio_service.dart';
import 'package:ondoway/services/location_service.dart';
import 'package:ondoway/services/tour_playback_service.dart';

/// Debug-only proof harness that lets you DROP YOUR OWN STOPS on a map instead
/// of walking a guessed bearing. Tap the map to place numbered pins wherever you
/// like (space them out so each trigger is unambiguous), start the tour, then
/// walk to each pin — its narration fires ONCE as you enter the radius. Same
/// production path as the linear proof (native locked playback + auto-advance),
/// just with self-placed, well-spaced stops so you can actually SEE it working.
class TourPinProofPage extends StatefulWidget {
  const TourPinProofPage({super.key});

  @override
  State<TourPinProofPage> createState() => _TourPinProofPageState();
}

class _TourPinProofPageState extends State<TourPinProofPage> {
  final List<LatLng> _pins = [];
  final List<String> _log = [];
  LatLng? _center;

  LocationService? _loc;
  AudioService? _audio;
  TourPlaybackService? _tour;
  bool _wiredListeners = false;

  // Wider than production's 10m: real GPS cross-track walks straight past a bare
  // 10m radius. 20m trips reliably while still requiring the walker to approach.
  static const double _triggerRadiusMeters = 20.0;

  @override
  void initState() {
    super.initState();
    _resolveCenter();
  }

  String get _ts {
    final n = DateTime.now();
    String p(int x) => x.toString().padLeft(2, '0');
    return '${p(n.hour)}:${p(n.minute)}:${p(n.second)}';
  }

  void _add(String line) {
    if (!mounted) return;
    setState(() => _log.insert(0, line));
  }

  Future<void> _resolveCenter() async {
    final location = context.read<LocationService>();
    final started = await location.startTracking(background: false);
    if (!started) {
      _add('Could not get location — grant permission and reopen.');
      return;
    }
    await Future<void>.delayed(const Duration(seconds: 2));
    final pos = location.lastPosition;
    location.stopTracking();
    if (pos == null) {
      _add('No position yet — reopen the page.');
      return;
    }
    setState(() => _center = LatLng(pos.latitude, pos.longitude));
  }

  void _onMapTap(LatLng position) {
    final tour = context.read<TourPlaybackService>();
    if (tour.isActive) return; // don't edit stops mid-tour
    setState(() => _pins.add(position));
    _add('$_ts  Dropped stop ${_pins.length} '
        '(${position.latitude.toStringAsFixed(5)}, '
        '${position.longitude.toStringAsFixed(5)})');
  }

  void _clearPins() {
    final tour = context.read<TourPlaybackService>();
    if (tour.isActive) return;
    setState(_pins.clear);
    _add('$_ts  Cleared stops');
  }

  // Mirrors AudioService's cache convention (temp/ondoway_audio/<beatId>.mp3) so
  // the tour plays a LOCAL file. Reuses the bundled proof clip. Debug only.
  Future<void> _cacheClip(String beatId) async {
    final bytes = await rootBundle.load('assets/audio/arrived.wav');
    final dir = Directory('${(await getTemporaryDirectory()).path}/ondoway_audio');
    if (!await dir.exists()) await dir.create(recursive: true);
    await File('${dir.path}/$beatId.mp3')
        .writeAsBytes(bytes.buffer.asUint8List());
  }

  Future<void> _startTour() async {
    if (_pins.isEmpty) {
      _add('Drop at least one stop first.');
      return;
    }
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

    final stops = <ItineraryStop>[];
    for (var i = 0; i < _pins.length; i++) {
      final beatId = 'pin-${i + 1}';
      await _cacheClip(beatId);
      stops.add(_pinStop(i + 1, beatId, _pins[i]));
    }

    final ok = await tour.startTour(stops);
    _add(ok
        ? 'Tour started with ${stops.length} stop(s), fires within '
            '${_triggerRadiusMeters.toStringAsFixed(0)}m. Lock, pocket, walk to each pin.'
        : 'startTour failed.');
  }

  ItineraryStop _pinStop(int order, String beatId, LatLng at) => ItineraryStop(
        sortOrder: order,
        stopId: beatId,
        poiId: 'pin-poi-$order',
        poiName: 'Pin Stop $order',
        lat: at.latitude,
        lng: at.longitude,
        beatId: beatId,
        lensName: 'history',
        lensDisplay: 'History',
        durationMin: 1,
        importanceTier: 3,
        startTime: '09:0$order',
        audioUrl: 'cached://$beatId', // unused: cache hit wins in AudioService
        // The footprint rides the STOP, exactly as a server-placed one does —
        // there is no service-wide radius to set. Wider than a real doorway on
        // purpose: measured GPS cross-track is about ten metres, so a walker can
        // cross a bare 10 m circle without one fix landing inside it, and the
        // proof would prove nothing.
        trigger: const StopTrigger(radiusM: _triggerRadiusMeters),
      );

  void _onLocTick() {
    final d = _tour?.distanceToNext;
    _add('$_ts  pos  d=${d?.toStringAsFixed(1) ?? "—"}m  '
        'state=${_tour?.state.name}  idx=${_tour?.currentStopIndex}  '
        'playing=${_audio?.isPlaying}');
  }

  String? _lastAudioSig;
  void _onAudioTick() {
    final sig = 'playing=${_audio?.isPlaying}  buffering=${_audio?.isBuffering}'
        '  beat=${_audio?.currentBeatId}';
    if (sig == _lastAudioSig) return;
    _lastAudioSig = sig;
    _add('$_ts  AUDIO  $sig');
  }

  @override
  void dispose() {
    _loc?.removeListener(_onLocTick);
    _audio?.removeListener(_onAudioTick);
    super.dispose();
  }

  Set<Annotation> _annotations() {
    return {
      for (var i = 0; i < _pins.length; i++)
        Annotation(
          annotationId: AnnotationId('pin-${i + 1}'),
          position: _pins[i],
          infoWindow: InfoWindow(title: 'Stop ${i + 1}'),
        ),
    };
  }

  @override
  Widget build(BuildContext context) {
    final tour = context.watch<TourPlaybackService>();
    return Scaffold(
      appBar: AppBar(title: const Text('Tour Pin Proof (debug)')),
      body: Column(
        children: [
          if (_center == null)
            const Expanded(
              flex: 3,
              child: Center(child: CircularProgressIndicator()),
            )
          else
            Expanded(
              flex: 3,
              child: AppleMap(
                initialCameraPosition: CameraPosition(target: _center!, zoom: 16),
                onTap: _onMapTap,
                myLocationEnabled: true,
                annotations: _annotations(),
              ),
            ),
          Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text('Stops: ${_pins.length}   ·   State: ${tour.state.name}   ·   '
                    'idx: ${tour.currentStopIndex}'),
                Text(tour.distanceToNext == null
                    ? 'Distance to next: —'
                    : 'Distance to next: ${tour.distanceToNext!.toStringAsFixed(1)} m'),
                const SizedBox(height: 8),
                Row(
                  children: [
                    Expanded(
                      child: FilledButton(
                        onPressed: tour.isActive ? null : _startTour,
                        child: const Text('Start tour'),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: OutlinedButton(
                        onPressed: tour.isActive ? null : _clearPins,
                        child: const Text('Clear pins'),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: OutlinedButton(
                        onPressed: () {
                          tour.stopTour();
                          _add('$_ts  Tour stopped.');
                        },
                        child: const Text('Stop'),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
          Expanded(
            flex: 2,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12),
              child: ListView.builder(
                itemCount: _log.length,
                itemBuilder: (_, i) => Text(_log[i],
                    style: Theme.of(context).textTheme.bodySmall),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
