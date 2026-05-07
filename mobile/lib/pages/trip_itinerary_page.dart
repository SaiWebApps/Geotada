import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';
import 'package:ondoway/models/trip.dart';
import 'package:ondoway/services/auth_service.dart';
import 'package:ondoway/services/location_service.dart';
import 'package:ondoway/services/profile_service.dart';
import 'package:ondoway/services/tour_playback_service.dart';
import 'package:ondoway/services/trip_service.dart';
import 'package:ondoway/widgets/beat_audio_player.dart';

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

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final tripService = context.read<TripService>();
    final tourPlayback = context.watch<TourPlaybackService>();
    final hasAudio = widget.trip.stops.any((s) => s.audioUrl != null);

    return Scaffold(
      appBar: AppBar(
        title: Text(widget.trip.tripName),
        backgroundColor: colorScheme.surface,
        actions: [
          if (tourPlayback.isActive)
            IconButton(
              icon: const Icon(Icons.stop_circle_outlined),
              tooltip: 'Stop Tour',
              onPressed: () => tourPlayback.stopTour(),
            ),
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
          if (tourPlayback.isActive)
            _TourStatusBanner(tourPlayback: tourPlayback)
          else if (hasAudio)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: SizedBox(
                width: double.infinity,
                child: ElevatedButton.icon(
                  onPressed: () async {
                    final started =
                        await tourPlayback.startTour(widget.trip.stops);
                    if (!started && context.mounted) {
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(
                          content: Text(
                            'Could not start tour. Check location permissions.',
                          ),
                        ),
                      );
                    }
                  },
                  icon: const Icon(Icons.headphones),
                  label: const Text('Start Tour'),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: colorScheme.primary,
                    foregroundColor: colorScheme.onPrimary,
                  ),
                ),
              ),
            ),
          if (tourPlayback.state == TourState.completed)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              child: Card(
                color: colorScheme.tertiaryContainer,
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Row(
                    children: [
                      Icon(Icons.check_circle,
                          color: colorScheme.onTertiaryContainer),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Text(
                          'Tour complete!',
                          style: TextStyle(
                            color: colorScheme.onTertiaryContainer,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                      TextButton(
                        onPressed: () => tourPlayback.stopTour(),
                        child: Text(
                          'Dismiss',
                          style: TextStyle(
                            color: colorScheme.onTertiaryContainer,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
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
              itemCount: widget.trip.stops.length,
              itemBuilder: (context, index) {
                final stop = widget.trip.stops[index];
                return _StopCard(stop: stop);
              },
            ),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () {
          tripService.saveTrip(widget.trip);
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Trip saved!')),
          );
          context.go('/saved-trips');
        },
        icon: const Icon(Icons.bookmark_add),
        label: const Text('Save Trip'),
        backgroundColor: colorScheme.primary,
        foregroundColor: colorScheme.onPrimary,
      ),
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
      child: ExpansionTile(
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
            const Spacer(),
            Text(
              stop.startTime,
              style: textTheme.titleSmall?.copyWith(
                fontWeight: FontWeight.bold,
                color: colorScheme.primary,
              ),
            ),
          ],
        ),
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (stop.scriptBody != null)
                  SelectableText(
                    stop.scriptBody!,
                    style: textTheme.bodyMedium?.copyWith(
                      color: colorScheme.onSurface,
                    ),
                  )
                else
                  Text(
                    'Script not yet generated',
                    style: textTheme.bodyMedium?.copyWith(
                      fontStyle: FontStyle.italic,
                      color: colorScheme.onSurfaceVariant,
                    ),
                  ),
                const SizedBox(height: 8),
                BeatAudioPlayer(
                  beatId: stop.beatId,
                  audioUrl: stop.audioUrl,
                  durationSec: stop.audioDurationSec,
                ),
                const SizedBox(height: 8),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _TourStatusBanner extends StatelessWidget {
  final TourPlaybackService tourPlayback;

  const _TourStatusBanner({required this.tourPlayback});

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    if (tourPlayback.state == TourState.approaching &&
        tourPlayback.hasPendingStop) {
      final pendingStop =
          tourPlayback.pendingStopIndex != null ? tourPlayback.nextStop : null;
      return Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
        child: Card(
          color: colorScheme.secondaryContainer,
          child: InkWell(
            onTap: () => tourPlayback.acceptPendingStop(),
            borderRadius: BorderRadius.circular(12),
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Row(
                children: [
                  Icon(Icons.near_me,
                      color: colorScheme.onSecondaryContainer),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      'Arriving at ${pendingStop?.poiName ?? "next stop"}'
                      ' — tap to switch',
                      style: TextStyle(
                        color: colorScheme.onSecondaryContainer,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ),
                  IconButton(
                    icon: Icon(Icons.close,
                        color: colorScheme.onSecondaryContainer, size: 20),
                    onPressed: () => tourPlayback.dismissPending(),
                    padding: EdgeInsets.zero,
                    constraints: const BoxConstraints(),
                  ),
                ],
              ),
            ),
          ),
        ),
      );
    }

    // Active state: walking to next stop
    final distance = tourPlayback.distanceToNext;
    final nextStop = tourPlayback.currentStop;
    final distanceText = distance != null ? '${distance.round()}m away' : '';

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      child: Card(
        color: colorScheme.primaryContainer,
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            children: [
              Icon(Icons.directions_walk,
                  color: colorScheme.onPrimaryContainer),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  'Walking to ${nextStop?.poiName ?? "next stop"}'
                  '${distanceText.isNotEmpty ? " — $distanceText" : ""}',
                  style: TextStyle(
                    color: colorScheme.onPrimaryContainer,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
