import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';
import 'package:ondoway/models/trip.dart';
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

class _TripItineraryContent extends StatelessWidget {
  final GeneratedTrip trip;

  const _TripItineraryContent({required this.trip});

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final textTheme = Theme.of(context).textTheme;
    final tripService = context.read<TripService>();

    return Scaffold(
      appBar: AppBar(
        title: Text(trip.tripName),
        backgroundColor: colorScheme.surface,
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            tooltip: 'Regenerate',
            onPressed: () {
              // Pop back to duration page for re-generation
              context.pop();
            },
          ),
        ],
      ),
      body: Column(
        children: [
          // Summary card
          _SummaryCard(trip: trip),
          // Stops list
          Expanded(
            child: ListView.builder(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              itemCount: trip.stops.length,
              itemBuilder: (context, index) {
                final stop = trip.stops[index];
                return _StopCard(stop: stop);
              },
            ),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () {
          tripService.saveTrip(trip);
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
    final textTheme = Theme.of(context).textTheme;

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
