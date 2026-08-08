import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:geolocator/geolocator.dart';
import 'package:provider/provider.dart';
import 'package:ondoway/services/location_service.dart';
import 'package:ondoway/services/providers.dart';
import 'package:ondoway/spike/geofence_trigger.dart';

class LocationSpikePage extends StatefulWidget {
  const LocationSpikePage({super.key});

  @override
  State<LocationSpikePage> createState() => _LocationSpikePageState();
}

class _LocationSpikePageState extends State<LocationSpikePage> {
  // Native background-audio channel: just_audio does not reliably play from a
  // background geofence callback on iOS (needs an active AVAudioSession the Dart
  // side can't hold). We hand the clip bytes to a native AVAudioPlayer instead.
  static const MethodChannel _bgAudio = MethodChannel('com.ondoway/bg_audio');
  final List<String> _log = [];
  GeofenceTrigger? _trigger;
  LocationProvider? _location;
  bool _tracking = false;
  double? _distance;

  @override
  void initState() {
    super.initState();
    _location = context.read<LocationService>();
    _location!.addListener(_onLocation);
  }

  @override
  void dispose() {
    _location?.removeListener(_onLocation);
    _location?.stopTracking();
    super.dispose();
  }

  void _add(String line) {
    setState(() => _log.insert(0, line));
  }

  Future<void> _setTarget() async {
    final pos = _location!.lastPosition as Position?;
    if (pos == null) {
      _add('No position yet — start tracking first, then set target.');
      return;
    }
    _trigger = GeofenceTrigger(targetLat: pos.latitude, targetLng: pos.longitude);
    _add('Target set: ${pos.latitude.toStringAsFixed(6)}, '
        '${pos.longitude.toStringAsFixed(6)}');
  }

  Future<void> _start() async {
    // Activate the audio session while we are FOREGROUND. iOS only grants the
    // .playback session to a frontmost app; once active it survives lock and
    // backgrounding, so the geofence callback can play without re-activating
    // (which fails with CannotInterruptOthers from the background).
    try {
      await _bgAudio.invokeMethod<void>('prepare');
      _add('Audio session prepared (active, ducking).');
    } catch (e) {
      _add('Audio prepare error: $e');
    }
    final ok = await _location!.startTracking(background: true);
    if (!mounted) return;
    setState(() => _tracking = ok);
    _add(ok ? 'Background tracking started.' : 'Tracking failed to start.');
  }

  void _onLocation() {
    final pos = _location!.lastPosition as Position?;
    if (pos == null) return;
    final t = _trigger;
    final now = TimeOfDay.now();
    final stamp = '${now.hour}:${now.minute.toString().padLeft(2, '0')}';
    if (t == null) {
      _add('$stamp  pos ${pos.latitude.toStringAsFixed(6)},'
          '${pos.longitude.toStringAsFixed(6)} (±${pos.accuracy.toStringAsFixed(0)}m)');
      return;
    }
    final d = t.distanceTo(pos.latitude, pos.longitude);
    setState(() => _distance = d);
    _add('$stamp  ${d.toStringAsFixed(1)}m  (±${pos.accuracy.toStringAsFixed(0)}m)');
    if (t.update(pos.latitude, pos.longitude)) {
      _add('$stamp  *** FIRED at ${d.toStringAsFixed(1)}m — playing clip ***');
      _playClip();
    }
  }

  Future<void> _playClip() async {
    try {
      final bytes = await rootBundle.load('assets/audio/arrived.wav');
      await _bgAudio.invokeMethod<void>('play', bytes.buffer.asUint8List());
    } catch (e) {
      if (!mounted) return;
      _add('Audio error: $e');
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Location Spike (debug)')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              _distance == null
                  ? 'Distance to target: —'
                  : 'Distance to target: ${_distance!.toStringAsFixed(1)} m',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: FilledButton(
                    onPressed: _tracking ? null : _start,
                    child: const Text('Start tracking'),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: OutlinedButton(
                    onPressed: _setTarget,
                    child: const Text('Set target = here'),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),
            Text('Event log', style: Theme.of(context).textTheme.labelLarge),
            const Divider(),
            Expanded(
              child: Container(
                color: scheme.surfaceContainerHighest,
                child: ListView.builder(
                  itemCount: _log.length,
                  itemBuilder: (_, i) => Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                    child: Text(_log[i],
                        style: Theme.of(context).textTheme.bodySmall),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
