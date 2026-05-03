import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart' show visibleForTesting;
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';
import 'package:ondoway/services/trip_service.dart';
import 'package:ondoway/services/auth_service.dart';
import 'package:ondoway/services/profile_service.dart';

class TripDurationPage extends StatefulWidget {
  final String citySlug;

  /// Optional initial times for testing validation logic.
  @visibleForTesting
  final TimeOfDay? initialStartTime;
  @visibleForTesting
  final TimeOfDay? initialEndTime;

  const TripDurationPage({
    super.key,
    required this.citySlug,
    this.initialStartTime,
    this.initialEndTime,
  });

  @override
  State<TripDurationPage> createState() => _TripDurationPageState();
}

class _TripDurationPageState extends State<TripDurationPage> {
  late DateTime _startDate;
  late TimeOfDay _startTime;
  late DateTime _endDate;
  late TimeOfDay _endTime;
  bool _isLoading = false;
  String? _error;

  static const _cityCoordinates = {
    'paris': (lat: 48.8566, lng: 2.3522),
  };

  @override
  void initState() {
    super.initState();
    final now = DateTime.now();
    _startDate = DateTime(now.year, now.month, now.day + 1);
    _startTime = widget.initialStartTime ?? const TimeOfDay(hour: 9, minute: 0);
    _endDate = DateTime(now.year, now.month, now.day + 1);
    _endTime = widget.initialEndTime ?? const TimeOfDay(hour: 18, minute: 0);
  }

  String get _cityDisplayName {
    switch (widget.citySlug) {
      case 'paris':
        return 'Paris';
      default:
        return widget.citySlug[0].toUpperCase() + widget.citySlug.substring(1);
    }
  }

  DateTime get _startDateTime => DateTime(
        _startDate.year, _startDate.month, _startDate.day,
        _startTime.hour, _startTime.minute);

  DateTime get _endDateTime => DateTime(
        _endDate.year, _endDate.month, _endDate.day,
        _endTime.hour, _endTime.minute);

  int get _totalMinutes => _endDateTime.difference(_startDateTime).inMinutes;

  bool get _isMultiDay => _endDate.isAfter(_startDate);

  String? get _validationError {
    if (_endDateTime.isBefore(_startDateTime) || _endDateTime.isAtSameMomentAs(_startDateTime)) {
      return 'End must be after start';
    }
    if (_totalMinutes < 60) {
      return 'Minimum trip duration is 1 hour';
    }
    if (_totalMinutes > 14 * 24 * 60) {
      return 'Maximum trip duration is 14 days';
    }
    return null;
  }

  bool get _isValid => _validationError == null;

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
      final trip = await tripService.generateTrip(
        profileId: profileId,
        centerLat: coords.lat,
        centerLng: coords.lng,
        startDate: _formatDate(_startDate),
        endDate: _formatDate(_endDate),
        accessToken: token,
        durationMin: _totalMinutes,
        maxStops: (_totalMinutes ~/ 30).clamp(3, 30),
        startTime: _formatTime(_startTime),
      );

      if (mounted) {
        context.push('/trip/${trip.tripId}');
      }
    } on TripServiceException catch (e) {
      if (mounted) setState(() { _isLoading = false; _error = e.message; });
    } catch (e) {
      if (mounted) setState(() { _isLoading = false; _error = 'Something went wrong. Please try again.'; });
    }
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;
    final validation = _validationError;

    return Scaffold(
      appBar: AppBar(
        title: Text(_cityDisplayName),
        backgroundColor: cs.surface,
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'When are you visiting?',
                style: tt.headlineSmall?.copyWith(
                  fontWeight: FontWeight.bold,
                  color: cs.onSurface,
                ),
              ),
              const SizedBox(height: 32),

              _DateTimeSection(
                label: 'From',
                date: _startDate,
                time: _startTime,
                onDateTap: () => _pickDate(isStart: true),
                onTimeTap: () => _pickTime(isStart: true),
              ),
              const SizedBox(height: 24),

              _DateTimeSection(
                label: 'To (inclusive)',
                date: _endDate,
                time: _endTime,
                onDateTap: () => _pickDate(isStart: false),
                onTimeTap: () => _pickTime(isStart: false),
              ),
              const SizedBox(height: 16),

              if (_isValid)
                Text(
                  _formatDurationSummary(),
                  style: tt.bodyLarge?.copyWith(color: cs.onSurfaceVariant),
                ),

              if (validation != null)
                Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Text(
                    validation,
                    style: tt.bodySmall?.copyWith(color: cs.error),
                  ),
                ),

              if (_error != null)
                Padding(
                  padding: const EdgeInsets.only(top: 16),
                  child: Text(
                    _error!,
                    style: tt.bodyMedium?.copyWith(color: cs.error),
                  ),
                ),

              const SizedBox(height: 40),

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
                            color: cs.onPrimary,
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

  String _formatDurationSummary() {
    final days = _endDate.difference(_startDate).inDays;
    final hours = _totalMinutes ~/ 60;
    final mins = _totalMinutes % 60;

    if (days > 0) {
      final nightWord = days == 1 ? 'night' : 'nights';
      final dayWord = (days + 1) == 1 ? 'day' : 'days';
      return '${days + 1} $dayWord, $days $nightWord';
    }
    if (hours > 0 && mins > 0) return '$hours h $mins min';
    if (hours > 0) return '$hours hour${hours > 1 ? 's' : ''}';
    return '$mins min';
  }

  Future<void> _pickDate({required bool isStart}) async {
    final initial = isStart ? _startDate : _endDate;
    final picked = await showDatePicker(
      context: context,
      initialDate: initial,
      firstDate: DateTime.now(),
      lastDate: DateTime.now().add(const Duration(days: 365)),
    );
    if (picked != null) {
      setState(() {
        if (isStart) {
          _startDate = picked;
          if (_endDate.isBefore(_startDate)) _endDate = _startDate;
        } else {
          _endDate = picked;
        }
      });
    }
  }

  Future<void> _pickTime({required bool isStart}) async {
    final initial = isStart ? _startTime : _endTime;
    final picked = await showTimePicker(context: context, initialTime: initial);
    if (picked != null) {
      setState(() {
        if (isStart) {
          _startTime = picked;
        } else {
          _endTime = picked;
        }
      });
    }
  }

  String _formatDate(DateTime d) =>
      '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

  String _formatTime(TimeOfDay t) =>
      '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}';
}

class _DateTimeSection extends StatelessWidget {
  final String label;
  final DateTime date;
  final TimeOfDay time;
  final VoidCallback onDateTap;
  final VoidCallback onTimeTap;

  const _DateTimeSection({
    required this.label,
    required this.date,
    required this.time,
    required this.onDateTap,
    required this.onTimeTap,
  });

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;
    final months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                     'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    final weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    final dateStr = '${weekdays[date.weekday - 1]}, ${months[date.month - 1]} ${date.day}';
    final timeStr = '${time.hour.toString().padLeft(2, '0')}:${time.minute.toString().padLeft(2, '0')}';

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: tt.titleMedium?.copyWith(color: cs.onSurface)),
        const SizedBox(height: 8),
        Row(
          children: [
            Expanded(
              flex: 3,
              child: OutlinedButton.icon(
                onPressed: onDateTap,
                icon: const Icon(Icons.calendar_today, size: 18),
                label: Text(dateStr),
                style: OutlinedButton.styleFrom(
                  minimumSize: const Size(0, 48),
                  alignment: Alignment.centerLeft,
                ),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              flex: 2,
              child: OutlinedButton.icon(
                onPressed: onTimeTap,
                icon: const Icon(Icons.access_time, size: 18),
                label: Text(timeStr),
                style: OutlinedButton.styleFrom(
                  minimumSize: const Size(0, 48),
                  alignment: Alignment.centerLeft,
                ),
              ),
            ),
          ],
        ),
      ],
    );
  }
}
