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

/// Builds a single itinerary stop card in isolation — the exact `_StopCard`
/// the itinerary list renders. Exposed only so golden/screenshot tests can
/// render one card (with or without "keep exploring here" extras) without
/// pumping the whole page. Not part of the app's public surface.
@visibleForTesting
Widget buildStopCardForTest(ItineraryStop stop) => _StopCard(stop: stop);

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

  /// Phase 4 Step 4.10: set once the user has picked a flavour (composed) or
  /// dismissed the picker (keeping options[0], the persisted default) — the
  /// sheet never interposes twice.
  bool _flavourResolved = false;

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
    // Phase 4 Step 4.10: the flavour picker interposes BEFORE the existing
    // confirm/poll/prefetch flow — only when the just-generated trip carries
    // RouteOptions (GET /trips never returns them, so the restart/saved path
    // keeps the legacy flow untouched).
    if (!_flavourResolved && widget.trip.options.isNotEmpty) {
      final composedStops = await _pickFlavour();
      if (!mounted) return;
      setState(() {
        _flavourResolved = true;
        // Non-null -> /compose re-persisted the stops: FRESH stop_ids,
        // composed narration, audio nulled. Rebuild the page's list so the
        // audio flow below runs against the NEW stop_ids.
        // Null -> sheet dismissed: keep options[0], the persisted default.
        if (composedStops != null) _stops = composedStops;
      });
    }
    await _runPrepareFlow();
  }

  /// Shows the flavour bottom sheet; resolves with the composed stops, or
  /// null when the sheet is dismissed (keep the default flavour). A 422
  /// refusal keeps the sheet open with the remaining flavours.
  Future<List<ItineraryStop>?> _pickFlavour() {
    final tripService = context.read<TripService>();
    final authService = context.read<AuthService>();
    final messenger = ScaffoldMessenger.of(context);

    return showModalBottomSheet<List<ItineraryStop>>(
      context: context,
      builder: (sheetContext) {
        final navigator = Navigator.of(sheetContext);
        // (original 1-based flavour number, option) — refused flavours drop
        // out, but the surviving labels keep their numbers.
        final remaining = [
          for (var i = 0; i < widget.trip.options.length; i++)
            (i + 1, widget.trip.options[i]),
        ];
        var composing = false;

        return StatefulBuilder(
          builder: (context, setSheetState) {
            final textTheme = Theme.of(context).textTheme;

            Future<void> compose(RouteOption option) async {
              setSheetState(() => composing = true);
              try {
                final stops = await tripService.composeTrip(
                  widget.trip.tripId,
                  option.routeId,
                  authService.accessToken!,
                );
                navigator.pop(stops);
              } on ComposeVerificationException {
                messenger.showSnackBar(
                  const SnackBar(
                    content: Text('This flavour failed verification'),
                  ),
                );
                setSheetState(() {
                  composing = false;
                  remaining.removeWhere(
                    (entry) => entry.$2.routeId == option.routeId,
                  );
                });
                // Every flavour refused — fall back to the persisted default.
                if (remaining.isEmpty) navigator.pop(null);
              } catch (e) {
                messenger.showSnackBar(
                  SnackBar(content: Text('Could not prepare flavour: $e')),
                );
                setSheetState(() => composing = false);
              }
            }

            return SafeArea(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
                    child: Text(
                      'Choose your tour flavour',
                      style: textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ),
                  if (composing) const LinearProgressIndicator(),
                  for (final (number, option) in remaining)
                    _FlavourTile(
                      number: number,
                      option: option,
                      enabled: !composing,
                      onTap: () => compose(option),
                    ),
                  const SizedBox(height: 8),
                ],
              ),
            );
          },
        );
      },
    );
  }

  /// The pre-existing Confirm & Prepare flow: save the trip, trigger per-stop
  /// audio generation, poll + prefetch until every stop has audio.
  Future<void> _runPrepareFlow() async {
    if (!mounted) return;
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
      await tripService.confirmTripStopAudio(
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

          // Per-stop narration (Step 1.4d): poll + cache by the ItineraryItem
          // id, falling back to the legacy per-beat id only when a stop has no
          // stopId (old data) — same key playback uses, so the cache hits.
          final audioKey = stop.stopId ?? stop.beatId;
          final status = stop.stopId != null
              ? await audioService.checkStopAudioStatus(
                  TripService.baseUrl,
                  stop.stopId!,
                )
              : await audioService.checkAudioStatus(
                  TripService.baseUrl,
                  stop.beatId,
                );

          if (status != null && status['has_audio'] == true) {
            final url = status['audio_url'] as String;
            // Prefetch the audio file to local cache, keyed to match playback.
            await audioService.prefetchAudio([
              BeatAudioInfo(beatId: audioKey, audioUrl: url),
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
          if (widget.trip.degradationNotices.isNotEmpty)
            _DegradationCard(notices: widget.trip.degradationNotices),
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

/// One row in the flavour picker: label, DWELL stop count (band == "dwell"
/// only), eta minutes, and the lens_coverage_note when present.
class _FlavourTile extends StatelessWidget {
  final int number;
  final RouteOption option;
  final bool enabled;
  final VoidCallback onTap;

  const _FlavourTile({
    required this.number,
    required this.option,
    required this.enabled,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final dwellCount =
        option.stops.where((s) => s.band == 'dwell').length;
    final etaMin = (option.etaSeconds / 60).round();
    final note = option.lensCoverageNote;

    return ListTile(
      enabled: enabled,
      leading: CircleAvatar(
        backgroundColor: colorScheme.primaryContainer,
        child: Text(
          '$number',
          style: TextStyle(
            color: colorScheme.onPrimaryContainer,
            fontWeight: FontWeight.bold,
          ),
        ),
      ),
      title: Text('Flavour $number'),
      subtitle: Text(
        note == null
            ? '$dwellCount dwell stops · $etaMin min'
            : '$dwellCount dwell stops · $etaMin min\n$note',
      ),
      onTap: onTap,
    );
  }
}

/// Shows, above the itinerary, whatever quietly went worse while this tour was
/// built. Each notice is the backend's plain-English sentence — no identifiers,
/// nothing for the traveller to decode. It renders only when there is at least
/// one notice, so a clean tour shows nothing at all.
class _DegradationCard extends StatelessWidget {
  final List<String> notices;

  const _DegradationCard({required this.notices});

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      color: colorScheme.tertiaryContainer,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(Icons.info_outline, color: colorScheme.onTertiaryContainer),
            const SizedBox(width: 8),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  for (final notice in notices)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 4),
                      child: Text(
                        notice,
                        style: TextStyle(color: colorScheme.onTertiaryContainer),
                      ),
                    ),
                ],
              ),
            ),
          ],
        ),
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

class _StopCard extends StatefulWidget {
  final ItineraryStop stop;

  const _StopCard({required this.stop});

  @override
  State<_StopCard> createState() => _StopCardState();
}

class _StopCardState extends State<_StopCard> {
  bool _generatingDeeperDive = false;
  String? _deeperDiveError;

  ItineraryStop get stop => widget.stop;

  /// KE7: generate + play the stop's "keep exploring here" deep-dive audio.
  /// Plays as a DEEPER-DIVE source (KE6) so completion never auto-advances the
  /// tour. status=='failed' comes back as a caught [KeepExploringException].
  Future<void> _keepExploring() async {
    final tripService = context.read<TripService>();
    final audioService = context.read<AudioService>();

    setState(() {
      _generatingDeeperDive = true;
      _deeperDiveError = null;
    });

    try {
      final result = await tripService.generateDeeperDiveAudio(
        stop.stopId ?? stop.beatId,
      );
      if (!mounted) return;
      setState(() => _generatingDeeperDive = false);
      final url = result.audioUrl;
      if (url == null) {
        setState(() => _deeperDiveError = 'No audio was returned');
        return;
      }
      // Key off the stop so this clip is distinct from the scheduled per-stop
      // tour audio; isDeeperDive keeps auto-advance from firing on completion.
      await audioService.play(
        '${stop.stopId ?? stop.beatId}-keep-exploring',
        url,
        isDeeperDive: true,
      );
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _generatingDeeperDive = false;
        _deeperDiveError = e is TripServiceException ? e.message : e.toString();
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final textTheme = Theme.of(context).textTheme;
    final isAnchor = stop.importanceTier == 5;
    final hasExtras = stop.extraBeatIds.isNotEmpty;

    return Card(
      margin: const EdgeInsets.symmetric(vertical: 4),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          ListTile(
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
                  padding:
                      const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
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
          // KE7: only stops with un-voiced extras offer a deeper dive.
          if (hasExtras) _buildKeepExploring(colorScheme, textTheme),
        ],
      ),
    );
  }

  Widget _buildKeepExploring(ColorScheme colorScheme, TextTheme textTheme) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton.icon(
              onPressed: _generatingDeeperDive ? null : _keepExploring,
              icon: _generatingDeeperDive
                  ? SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: colorScheme.primary,
                      ),
                    )
                  : Icon(Icons.explore, size: 18, color: colorScheme.primary),
              label: Text(
                _generatingDeeperDive
                    ? 'Preparing...'
                    : 'Keep exploring here',
                style: TextStyle(color: colorScheme.primary),
              ),
            ),
          ),
          if (_deeperDiveError != null)
            Padding(
              padding: const EdgeInsets.only(left: 8, top: 4),
              child: Text(
                _deeperDiveError!,
                style: textTheme.bodySmall?.copyWith(color: colorScheme.error),
              ),
            ),
        ],
      ),
    );
  }
}
