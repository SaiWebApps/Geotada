import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';
import 'package:ondoway/services/trip_service.dart';
import 'package:ondoway/services/auth_service.dart';
import 'package:ondoway/services/profile_service.dart';

class TripDurationPage extends StatefulWidget {
  final String citySlug;

  const TripDurationPage({super.key, required this.citySlug});

  @override
  State<TripDurationPage> createState() => _TripDurationPageState();
}

class _TripDurationPageState extends State<TripDurationPage> {
  int _days = 1;
  int _hours = 4;
  DateTime _startDate = DateTime.now();
  bool _isLoading = false;
  String? _error;

  static const _cityCoordinates = {
    'paris': (lat: 48.8566, lng: 2.3522),
  };

  String get _cityDisplayName {
    switch (widget.citySlug) {
      case 'paris':
        return 'Paris';
      default:
        return widget.citySlug[0].toUpperCase() + widget.citySlug.substring(1);
    }
  }

  int get _totalMinutes => (_days * 24 * 60) + (_hours * 60);
  bool get _isValid => _totalMinutes >= 60;

  int get _maxStops {
    // Roughly 1 stop per 30 minutes of trip duration
    final stops = _totalMinutes ~/ 30;
    return stops.clamp(3, 30);
  }

  Future<void> _generateTrip() async {
    if (!_isValid) return;

    final tripService = context.read<TripService>();
    final authService = context.read<AuthService>();
    final profileService = context.read<ProfileService>();

    final coords = _cityCoordinates[widget.citySlug];
    if (coords == null) {
      setState(() => _error = 'City not supported');
      return;
    }

    final profileId = profileService.profileId;
    final token = authService.accessToken;
    if (profileId == null || token == null) {
      setState(() => _error = 'Please log in first');
      return;
    }

    setState(() {
      _isLoading = true;
      _error = null;
    });

    try {
      final endDate = _startDate.add(Duration(days: _days > 0 ? _days : 1));
      final trip = await tripService.generateTrip(
        profileId: profileId,
        centerLat: coords.lat,
        centerLng: coords.lng,
        startDate: _formatDate(_startDate),
        endDate: _formatDate(endDate),
        accessToken: token,
        durationMin: _totalMinutes,
        maxStops: _maxStops,
      );

      if (mounted) {
        context.push('/trip/${trip.tripId}');
      }
    } on TripServiceException catch (e) {
      if (mounted) {
        setState(() {
          _isLoading = false;
          _error = e.message;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _isLoading = false;
          _error = 'Something went wrong. Please try again.';
        });
      }
    }
  }

  String _formatDate(DateTime d) =>
      '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final textTheme = Theme.of(context).textTheme;

    return Scaffold(
      appBar: AppBar(
        title: Text('Plan Trip — $_cityDisplayName'),
        backgroundColor: colorScheme.surface,
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'How long is your trip?',
                style: textTheme.headlineSmall?.copyWith(
                  fontWeight: FontWeight.bold,
                  color: colorScheme.onSurface,
                ),
              ),
              const SizedBox(height: 32),

              // Days picker
              _buildNumberRow(
                label: 'Days',
                value: _days,
                min: 0,
                max: 14,
                onChanged: (v) => setState(() => _days = v),
              ),
              const SizedBox(height: 24),

              // Hours picker
              _buildNumberRow(
                label: 'Hours',
                value: _hours,
                min: 0,
                max: 23,
                onChanged: (v) => setState(() => _hours = v),
              ),
              const SizedBox(height: 16),

              // Duration summary
              Text(
                'Total: ${_formatDuration()}',
                style: textTheme.bodyLarge?.copyWith(
                  color: colorScheme.onSurfaceVariant,
                ),
              ),
              if (!_isValid)
                Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Text(
                    'Minimum trip duration is 1 hour',
                    style: textTheme.bodySmall?.copyWith(
                      color: colorScheme.error,
                    ),
                  ),
                ),

              const SizedBox(height: 32),

              // Start date picker
              Text(
                'Start date',
                style: textTheme.titleMedium?.copyWith(
                  color: colorScheme.onSurface,
                ),
              ),
              const SizedBox(height: 12),
              OutlinedButton.icon(
                onPressed: _pickStartDate,
                icon: const Icon(Icons.calendar_today),
                label: Text(_formatDate(_startDate)),
                style: OutlinedButton.styleFrom(
                  minimumSize: const Size(double.infinity, 48),
                ),
              ),

              const SizedBox(height: 32),

              // Estimated stops
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Row(
                    children: [
                      Icon(Icons.pin_drop, color: colorScheme.primary),
                      const SizedBox(width: 12),
                      Text(
                        'Estimated stops: $_maxStops',
                        style: textTheme.bodyLarge,
                      ),
                    ],
                  ),
                ),
              ),

              const SizedBox(height: 32),

              // Error display
              if (_error != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: 16),
                  child: Text(
                    _error!,
                    style: textTheme.bodyMedium?.copyWith(
                      color: colorScheme.error,
                    ),
                  ),
                ),

              // Generate button
              SizedBox(
                width: double.infinity,
                height: 56,
                child: FilledButton(
                  onPressed: _isValid && !_isLoading ? _generateTrip : null,
                  child: _isLoading
                      ? SizedBox(
                          height: 24,
                          width: 24,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            color: colorScheme.onPrimary,
                          ),
                        )
                      : const Text(
                          'Generate My Trip',
                          style: TextStyle(fontSize: 16),
                        ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildNumberRow({
    required String label,
    required int value,
    required int min,
    required int max,
    required ValueChanged<int> onChanged,
  }) {
    final colorScheme = Theme.of(context).colorScheme;
    final textTheme = Theme.of(context).textTheme;

    return Row(
      children: [
        SizedBox(
          width: 80,
          child: Text(
            label,
            style: textTheme.titleMedium?.copyWith(
              color: colorScheme.onSurface,
            ),
          ),
        ),
        IconButton(
          onPressed: value > min ? () => onChanged(value - 1) : null,
          icon: const Icon(Icons.remove_circle_outline),
        ),
        SizedBox(
          width: 48,
          child: Text(
            '$value',
            textAlign: TextAlign.center,
            style: textTheme.headlineSmall?.copyWith(
              fontWeight: FontWeight.bold,
              color: colorScheme.onSurface,
            ),
          ),
        ),
        IconButton(
          onPressed: value < max ? () => onChanged(value + 1) : null,
          icon: const Icon(Icons.add_circle_outline),
        ),
        Expanded(
          child: Slider(
            value: value.toDouble(),
            min: min.toDouble(),
            max: max.toDouble(),
            divisions: max - min,
            onChanged: (v) => onChanged(v.round()),
          ),
        ),
      ],
    );
  }

  String _formatDuration() {
    if (_days > 0 && _hours > 0) {
      return '$_days day${_days > 1 ? 's' : ''}, $_hours hour${_hours > 1 ? 's' : ''}';
    } else if (_days > 0) {
      return '$_days day${_days > 1 ? 's' : ''}';
    } else {
      return '$_hours hour${_hours > 1 ? 's' : ''}';
    }
  }

  Future<void> _pickStartDate() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: _startDate,
      firstDate: DateTime.now(),
      lastDate: DateTime.now().add(const Duration(days: 365)),
    );
    if (picked != null) {
      setState(() => _startDate = picked);
    }
  }
}
