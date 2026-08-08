import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';
import 'package:ondoway/models/trip.dart';
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

class _TourPlaybackProofPageState extends State<TourPlaybackProofPage> {
  final List<String> _log = [];

  void _add(String line) {
    if (!mounted) return;
    setState(() => _log.insert(0, line));
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

    // ~0.00014 deg latitude ≈ 15.5m per step, due north.
    final stops = [
      _proofStop(1, 'proof-1', pos.latitude + 0.00014, pos.longitude),
      _proofStop(2, 'proof-2', pos.latitude + 0.00028, pos.longitude),
    ];

    final ok = await tour.startTour(stops);
    _add(ok
        ? 'Tour started. Lock the phone, pocket it, walk NORTH ~15m then ~30m.'
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
            FilledButton(
              onPressed: _startProof,
              child: const Text('Prepare & start proof tour'),
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
