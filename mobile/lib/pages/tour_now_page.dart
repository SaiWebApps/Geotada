import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';
import 'package:ondoway/services/auth_service.dart';
import 'package:ondoway/services/location_service.dart';
import 'package:ondoway/services/profile_service.dart';
import 'package:ondoway/services/trip_service.dart';
import 'package:ondoway/theme/dims.dart';
import 'package:ondoway/theme/tokens.dart';

/// "Take a tour now" — the immediate path. Unlike the plan-for-later flow, it
/// asks exactly one thing (how long) and builds a tour from where the user is
/// standing right now. No dates, no start-point picker.
class TourNowPage extends StatefulWidget {
  final String citySlug;
  const TourNowPage({super.key, required this.citySlug});

  @override
  State<TourNowPage> createState() => _TourNowPageState();
}

class _DurationOption {
  final int minutes;
  final String label;
  final String descriptor;
  const _DurationOption(this.minutes, this.label, this.descriptor);
}

const _durations = <_DurationOption>[
  _DurationOption(30, '30 min', 'A quick loop'),
  _DurationOption(60, '1 hour', 'A short wander'),
  _DurationOption(90, '1½ hours', 'The classic'),
  _DurationOption(120, '2 hours', 'A deep dive'),
  _DurationOption(180, '3 hours', 'The full immersion'),
];

class _TourNowPageState extends State<TourNowPage> {
  static const _cityCoordinates = {
    'paris': (lat: 48.8566, lng: 2.3522),
  };

  int _selectedMinutes = 90;
  double? _lat;
  double? _lng;
  String _locationSource = 'pending'; // 'gps' | 'city_center' | 'pending'
  bool _resolved = false;
  bool _generating = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _resolveLocation());
  }

  Future<void> _resolveLocation() async {
    final position = await context.read<LocationService>().getCurrentPosition();
    if (!mounted) return;
    final coords = _cityCoordinates[widget.citySlug];

    if (position != null) {
      final withinCity = coords != null &&
          Geolocator.distanceBetween(
                position.latitude, position.longitude, coords.lat, coords.lng) <=
              50000;
      setState(() {
        // Standing in-city → use GPS. Elsewhere → the city we can actually tour.
        _lat = withinCity ? position.latitude : coords?.lat ?? position.latitude;
        _lng = withinCity ? position.longitude : coords?.lng ?? position.longitude;
        _locationSource = withinCity ? 'gps' : 'city_center';
        _resolved = true;
      });
    } else if (coords != null) {
      setState(() {
        _lat = coords.lat;
        _lng = coords.lng;
        _locationSource = 'city_center';
        _resolved = true;
      });
    } else {
      setState(() {
        _error = 'We could not find your location.';
        _resolved = true;
      });
    }
  }

  Future<void> _startTour() async {
    final tripService = context.read<TripService>();
    final profileId = context.read<ProfileService>().profileId;
    final token = context.read<AuthService>().accessToken;

    if (profileId == null || token == null) {
      setState(() => _error = 'Please log in first.');
      return;
    }
    if (_lat == null || _lng == null) {
      setState(() => _error = 'Location not available yet.');
      return;
    }

    setState(() {
      _generating = true;
      _error = null;
    });

    final now = DateTime.now();
    final today = '${now.year}-${_two(now.month)}-${_two(now.day)}';
    try {
      final trip = await tripService.generateTrip(
        profileId: profileId,
        centerLat: _lat!,
        centerLng: _lng!,
        startDate: today,
        endDate: today,
        accessToken: token,
        durationMin: _selectedMinutes,
        maxStops: (_selectedMinutes ~/ 30).clamp(3, 30),
        startTime: '${_two(now.hour)}:${_two(now.minute)}',
      );
      if (mounted) {
        setState(() => _generating = false);
        context.push('/trip/${trip.tripId}');
      }
    } on TripServiceException catch (e) {
      if (mounted) setState(() { _generating = false; _error = e.message; });
    } catch (_) {
      if (mounted) {
        setState(() { _generating = false; _error = 'Something went wrong. Please try again.'; });
      }
    }
  }

  static String _two(int n) => n.toString().padLeft(2, '0');

  @override
  Widget build(BuildContext context) {
    final c = Theme.of(context).extension<OndowayColors>()!;

    return Scaffold(
      backgroundColor: c.bg,
      body: SafeArea(
        bottom: false,
        child: Column(
          children: [
            _Header(c: c, onBack: () => Navigator.of(context).maybePop()),
            Expanded(
              child: ListView(
                padding: const EdgeInsets.fromLTRB(20, 4, 20, 24),
                children: [
                  _LocationStatus(c: c, source: _locationSource),
                  const SizedBox(height: Dims.spaceLg),
                  for (final d in _durations) ...[
                    _DurationCard(
                      c: c,
                      option: d,
                      selected: _selectedMinutes == d.minutes,
                      onTap: () => setState(() => _selectedMinutes = d.minutes),
                    ),
                    const SizedBox(height: Dims.spaceSm),
                  ],
                ],
              ),
            ),
            _Footer(
              c: c,
              generating: _generating,
              enabled: _resolved && _error == null && !_generating,
              error: _error,
              onStart: _startTour,
            ),
          ],
        ),
      ),
    );
  }
}

TextStyle _fraunces(Color color, double size, FontWeight weight) => TextStyle(
    fontFamily: 'Fraunces', color: color, fontSize: size, fontWeight: weight, height: 1.05);

class _Header extends StatelessWidget {
  final OndowayColors c;
  final VoidCallback onBack;
  const _Header({required this.c, required this.onBack});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 8, 20, 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            height: 44,
            child: Align(
              alignment: Alignment.centerLeft,
              child: Material(
                color: c.card,
                shape: const CircleBorder(),
                child: InkWell(
                  customBorder: const CircleBorder(),
                  onTap: onBack,
                  child: Padding(
                    padding: const EdgeInsets.all(9),
                    child: Icon(Icons.arrow_back, size: 22, color: c.ink),
                  ),
                ),
              ),
            ),
          ),
          const SizedBox(height: 4),
          Text('TAKE A TOUR NOW',
              style: TextStyle(
                  fontFamily: 'Space Mono',
                  color: c.accent,
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 2.0)),
          const SizedBox(height: 6),
          Text('How long do you\nhave?', style: _fraunces(c.ink, 30, FontWeight.w600)),
          const SizedBox(height: 8),
        ],
      ),
    );
  }
}

class _LocationStatus extends StatelessWidget {
  final OndowayColors c;
  final String source;
  const _LocationStatus({required this.c, required this.source});

  @override
  Widget build(BuildContext context) {
    final (label, resolving) = switch (source) {
      'gps' => ('Starting where you\'re standing', false),
      'city_center' => ('Starting from central Paris', false),
      _ => ('Finding you…', true),
    };
    return Row(
      children: [
        if (resolving)
          SizedBox(
            width: 14,
            height: 14,
            child: CircularProgressIndicator(strokeWidth: 2, color: c.accent),
          )
        else
          Container(
            width: 10,
            height: 10,
            decoration: BoxDecoration(color: c.accent, shape: BoxShape.circle),
          ),
        const SizedBox(width: Dims.spaceSm),
        Text(label,
            style: TextStyle(
                fontFamily: 'Space Grotesk',
                color: c.inkSoft,
                fontSize: 14,
                fontWeight: FontWeight.w500)),
      ],
    );
  }
}

class _DurationCard extends StatelessWidget {
  final OndowayColors c;
  final _DurationOption option;
  final bool selected;
  final VoidCallback onTap;
  const _DurationCard({
    required this.c,
    required this.option,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 160),
        curve: Curves.easeOut,
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 16),
        decoration: BoxDecoration(
          color: selected ? c.accent : c.card,
          borderRadius: BorderRadius.circular(Dims.radiusCard),
          border: Border.all(color: selected ? c.accent : c.line, width: 1.5),
          boxShadow: selected ? Dims.liftLight : null,
        ),
        child: Row(
          children: [
            Text(option.label,
                style: _fraunces(selected ? c.onAccent : c.ink, 22, FontWeight.w600)),
            const SizedBox(width: Dims.spaceMd),
            Expanded(
              child: Text(option.descriptor,
                  style: TextStyle(
                      fontFamily: 'Space Grotesk',
                      color: selected ? c.onAccent.withValues(alpha: 0.85) : c.inkMute,
                      fontSize: 14)),
            ),
            Icon(
              selected ? Icons.radio_button_checked : Icons.radio_button_unchecked,
              color: selected ? c.onAccent : c.line,
              size: 22,
            ),
          ],
        ),
      ),
    );
  }
}

class _Footer extends StatelessWidget {
  final OndowayColors c;
  final bool generating;
  final bool enabled;
  final String? error;
  final VoidCallback onStart;
  const _Footer({
    required this.c,
    required this.generating,
    required this.enabled,
    required this.error,
    required this.onStart,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.fromLTRB(20, 14, 20, 14 + MediaQuery.of(context).padding.bottom),
      decoration: BoxDecoration(
        color: c.panel,
        border: Border(top: BorderSide(color: c.line)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (error != null) ...[
            Text(error!,
                textAlign: TextAlign.center,
                style: TextStyle(
                    fontFamily: 'Space Grotesk',
                    color: Theme.of(context).colorScheme.error,
                    fontSize: 13)),
            const SizedBox(height: 10),
          ],
          FilledButton(
            onPressed: enabled ? onStart : null,
            child: generating
                ? const SizedBox(
                    width: 22,
                    height: 22,
                    child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                  )
                : const Text('Start tour'),
          ),
        ],
      ),
    );
  }
}
