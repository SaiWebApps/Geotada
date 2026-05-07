import 'dart:async';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';
import 'package:ondoway/models/trip.dart';
import 'package:ondoway/services/audio_service.dart';
import 'package:ondoway/services/auth_service.dart';
import 'package:ondoway/services/location_service.dart';
import 'package:ondoway/services/profile_service.dart';
import 'package:ondoway/services/trip_service.dart';

class TripItineraryPage extends StatelessWidget {
  final String tripId;

  const TripItineraryPage({super.key, required this.tripId});

  @override
  Widget build(BuildContext context) {
    final tripService = context.watch<TripService>();
    final trip = tripService.lastGenerated;

    if (trip == null || trip.tripId != tripId) {
      // Try to find in saved trips
      final saved = tripService.savedTrips
          .where((t) => t.tripId == tripId)
          .toList();
      if (saved.isNotEmpty) {
        return _TripItineraryContent(trip: saved.first);
      }
      return Scaffold(
        appBar: AppBar(title: const Text('Trip')),
        body: const Center(child: Text('Trip not found')),
      );
    }

    return _TripItineraryContent(trip: trip);
  }
}

class _TripItineraryContent extends StatefulWidget {
  final GeneratedTrip trip;

  const _TripItineraryContent({required this.trip});

  @override
  State<_TripItineraryContent> createState() =>
      _TripItineraryContentState();
}

class _TripItineraryContentState extends State<_TripItineraryContent> {
  bool _isUpdating = false;
  bool _isPreparing = false;
  bool _preparationDone = false;
  int _audioReady = 0;
  String? _prepareError;
  Timer? _pollTimer;

  /// Tracks which stops have had their audio URL resolved.
  late List<ItineraryStop> _stops;

  @override
  void initState() {
    super.initState();
    _stops = List.of(widget.trip.stops);
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    super.dispose();
  }

  Future<void> _updateFromHere() async {
    final locationService = context.read<LocationService>();
    final tripService = context.read<TripService>();
    final authService = context.read<AuthService>();
    final profileService = context.read<ProfileService>();

    setState(() => _isUpdating = true);

    final position = await locationService.getCurrentPosition();
    if (position == null) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              locationService.error ?? 'Could not get location',
            ),
          ),
        );
        setState(() => _isUpdating = false);
      }
      return;
    }

    try {
      final now = DateTime.now();
      final dateStr =
          '${now.year}-${now.month.toString().padLeft(2, '0')}'
          '-${now.day.toString().padLeft(2, '0')}';
      final timeStr =
          '${now.hour.toString().padLeft(2, '0')}'
          ':${now.minute.toString().padLeft(2, '0')}';

      final newTrip = await tripService.generateTrip(
        profileId: profileService.profileId!,
        centerLat: position.latitude,
        centerLng: position.longitude,
        startDate: dateStr,
        endDate: dateStr,
        accessToken: authService.accessToken!,
        startTime: timeStr,
      );
      if (mounted) {
        context.pushReplacement('/trip/${newTrip.tripId}');
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed to regenerate: $e')),
        );
        setState(() => _isUpdating = false);
      }
    }
  }

  Future<void> _confirmAndPrepareAudio() async {
    final tripService = context.read<TripService>();
    final authService = context.read<AuthService>();
    final audioService = context.read<AudioService>();

    // Step 1: Save trip locally (only if not already saved)
    final alreadySaved = tripService.savedTrips.any(
      (t) => t.tripId == widget.trip.tripId,
    );
    if (!alreadySaved) {
      tripService.saveTrip(widget.trip);
    }

    // Step 2: Determine which stops need audio
    final stopsWithoutAudio =
        _stops.where((s) => s.audioUrl == null).toList();
    final totalStops = _stops.length;

    setState(() {
      _isPreparing = true;
      _prepareError = null;
      _audioReady = totalStops - stopsWithoutAudio.length;
    });

    if (stopsWithoutAudio.isEmpty) {
      // All stops already have audio — skip generation
      setState(() {
        _isPreparing = false;
        _preparationDone = true;
        _audioReady = totalStops;
      });
      return;
    }

    // Step 3: Trigger backend audio generation
    try {
      await tripService.confirmTripAudio(
        widget.trip.tripId,
        authService.accessToken!,
      );
    } catch (e) {
      setState(() {
        _prepareError = e.toString();
        _isPreparing = false;
      });
      return;
    }

    // Step 4: Poll for readiness (max 60 seconds = 20 attempts * 3s)
    int attempts = 0;
    const maxAttempts = 20;

    _pollTimer = Timer.periodic(
      const Duration(seconds: 3),
      (timer) async {
        attempts++;
        int ready = 0;

        for (int i = 0; i < _stops.length; i++) {
          final stop = _stops[i];
          if (stop.audioUrl != null) {
            ready++;
            continue;
          }

          final status = await audioService.checkAudioStatus(
            TripService.baseUrl,
            stop.beatId,
          );

          if (status != null && status['has_audio'] == true) {
            final url = status['audio_url'] as String;
            // Prefetch the audio file to local cache
            await audioService.prefetchAudio([
              BeatAudioInfo(beatId: stop.beatId, audioUrl: url),
            ]);
            // Update the stop's audio URL
            _stops[i] = stop.copyWith(audioUrl: url);
            ready++;
          }
        }

        if (!mounted) {
          timer.cancel();
          return;
        }

        setState(() {
          _audioReady = ready;
        });

        if (ready >= _stops.length || attempts >= maxAttempts) {
          timer.cancel();
          _pollTimer = null;
          setState(() {
            _isPreparing = false;
            _preparationDone = true;
          });
        }
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return Scaffold(
      appBar: AppBar(
        title: Text(widget.trip.tripName),
        backgroundColor: colorScheme.surface,
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            tooltip: 'Regenerate',
            onPressed: () {
              context.pop();
            },
          ),
        ],
      ),
      body: Column(
        children: [
          _SummaryCard(trip: widget.trip),
          if (_isPreparing || _preparationDone) _buildProgressCard(colorScheme),
          if (_prepareError != null) _buildErrorCard(colorScheme),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                onPressed: _isUpdating ? null : _updateFromHere,
                icon: _isUpdating
                    ? SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: colorScheme.primary,
                        ),
                      )
                    : const Icon(Icons.my_location),
                label: Text(
                  _isUpdating
                      ? 'Updating...'
                      : 'Update trip from here',
                ),
              ),
            ),
          ),
          const SizedBox(height: 8),
          Expanded(
            child: ListView.builder(
              padding: const EdgeInsets.symmetric(
                horizontal: 16,
                vertical: 8,
              ),
              itemCount: _stops.length,
              itemBuilder: (context, index) {
                final stop = _stops[index];
                return _StopCard(stop: stop);
              },
            ),
          ),
        ],
      ),
      floatingActionButton: _buildFab(colorScheme),
    );
  }

  Widget _buildProgressCard(ColorScheme colorScheme) {
    final totalStops = _stops.length;
    final progress = totalStops > 0 ? _audioReady / totalStops : 0.0;
    final allReady = _audioReady >= totalStops;

    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      color: allReady
          ? colorScheme.primaryContainer
          : colorScheme.surfaceContainerHighest,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(
                  allReady ? Icons.check_circle : Icons.headphones,
                  color: allReady
                      ? colorScheme.onPrimaryContainer
                      : colorScheme.onSurfaceVariant,
                  size: 20,
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    allReady
                        ? 'Audio ready! Start your tour'
                        : _isPreparing
                            ? 'Preparing audio... $_audioReady/$totalStops'
                            : 'Audio ready for $_audioReady/$totalStops stops. '
                                'Start anyway?',
                    style: TextStyle(
                      color: allReady
                          ? colorScheme.onPrimaryContainer
                          : colorScheme.onSurfaceVariant,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ),
              ],
            ),
            if (_isPreparing) ...[
              const SizedBox(height: 12),
              LinearProgressIndicator(
                value: progress,
                backgroundColor: colorScheme.surfaceContainerHighest,
                valueColor: AlwaysStoppedAnimation(colorScheme.primary),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildErrorCard(ColorScheme colorScheme) {
    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      color: colorScheme.errorContainer,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            Icon(Icons.error_outline, color: colorScheme.onErrorContainer),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                _prepareError!,
                style: TextStyle(color: colorScheme.onErrorContainer),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildFab(ColorScheme colorScheme) {
    if (_preparationDone) {
      return FloatingActionButton.extended(
        onPressed: () {
          // Navigate to tour playback (for now, go to saved-trips)
          context.go('/saved-trips');
        },
        icon: const Icon(Icons.play_arrow),
        label: const Text('Start Tour'),
        backgroundColor: colorScheme.primary,
        foregroundColor: colorScheme.onPrimary,
      );
    }

    return FloatingActionButton.extended(
      onPressed: _isPreparing ? null : _confirmAndPrepareAudio,
      icon: _isPreparing
          ? SizedBox(
              width: 20,
              height: 20,
              child: CircularProgressIndicator(
                strokeWidth: 2,
                color: colorScheme.onPrimary,
              ),
            )
          : const Icon(Icons.headphones),
      label: Text(_isPreparing ? 'Preparing...' : 'Confirm & Prepare'),
      backgroundColor:
          _isPreparing ? colorScheme.surfaceContainerHighest : colorScheme.primary,
      foregroundColor:
          _isPreparing ? colorScheme.onSurfaceVariant : colorScheme.onPrimary,
    );
  }
}

class _SummaryCard extends StatelessWidget {
  final GeneratedTrip trip;

  const _SummaryCard({required this.trip});

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return Card(
      margin: const EdgeInsets.all(16),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceAround,
          children: [
            _SummaryItem(
              icon: Icons.pin_drop,
              label: 'Stops',
              value: '${trip.totalStops}',
              color: colorScheme.primary,
            ),
            _SummaryItem(
              icon: Icons.timer,
              label: 'Duration',
              value: _formatDuration(trip.totalDurationMin),
              color: colorScheme.secondary,
            ),
            _SummaryItem(
              icon: Icons.star,
              label: 'Anchors',
              value: '${trip.anchorCount}',
              color: colorScheme.tertiary,
            ),
            _SummaryItem(
              icon: Icons.auto_awesome,
              label: 'Flavour',
              value: '${trip.flavourCount}',
              color: colorScheme.primary,
            ),
          ],
        ),
      ),
    );
  }

  String _formatDuration(int minutes) {
    final hours = minutes ~/ 60;
    final mins = minutes % 60;
    if (hours > 0 && mins > 0) return '${hours}h ${mins}m';
    if (hours > 0) return '${hours}h';
    return '${mins}m';
  }
}

class _SummaryItem extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;
  final Color color;

  const _SummaryItem({
    required this.icon,
    required this.label,
    required this.value,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final colorScheme = Theme.of(context).colorScheme;

    return Column(
      children: [
        Icon(icon, color: color, size: 20),
        const SizedBox(height: 4),
        Text(
          value,
          style: textTheme.titleMedium?.copyWith(
            fontWeight: FontWeight.bold,
            color: colorScheme.onSurface,
          ),
        ),
        Text(
          label,
          style: textTheme.bodySmall?.copyWith(
            color: colorScheme.onSurfaceVariant,
          ),
        ),
      ],
    );
  }
}

class _StopCard extends StatelessWidget {
  final ItineraryStop stop;

  const _StopCard({required this.stop});

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final textTheme = Theme.of(context).textTheme;
    final isAnchor = stop.importanceTier == 5;

    return Card(
      margin: const EdgeInsets.symmetric(vertical: 4),
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: isAnchor
              ? colorScheme.primaryContainer
              : colorScheme.surfaceContainerHighest,
          child: Text(
            '${stop.sortOrder}',
            style: TextStyle(
              color: isAnchor
                  ? colorScheme.onPrimaryContainer
                  : colorScheme.onSurfaceVariant,
              fontWeight: FontWeight.bold,
            ),
          ),
        ),
        title: Row(
          children: [
            Expanded(
              child: Text(
                stop.poiName,
                style: textTheme.titleSmall?.copyWith(
                  fontWeight: FontWeight.w600,
                  color: colorScheme.onSurface,
                ),
              ),
            ),
            if (stop.audioUrl != null)
              Icon(Icons.volume_up, size: 16, color: colorScheme.primary),
            if (isAnchor)
              Icon(Icons.star, size: 16, color: colorScheme.tertiary),
          ],
        ),
        subtitle: Row(
          children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
              decoration: BoxDecoration(
                color: colorScheme.secondaryContainer,
                borderRadius: BorderRadius.circular(12),
              ),
              child: Text(
                stop.lensDisplay,
                style: textTheme.labelSmall?.copyWith(
                  color: colorScheme.onSecondaryContainer,
                ),
              ),
            ),
            const SizedBox(width: 8),
            Text(
              '${stop.durationMin} min',
              style: textTheme.bodySmall?.copyWith(
                color: colorScheme.onSurfaceVariant,
              ),
            ),
          ],
        ),
        trailing: Text(
          stop.startTime,
          style: textTheme.titleSmall?.copyWith(
            fontWeight: FontWeight.bold,
            color: colorScheme.primary,
          ),
        ),
      ),
    );
  }
}
