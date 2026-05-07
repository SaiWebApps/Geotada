import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:provider/provider.dart';

import 'package:ondoway/services/audio_service.dart';

/// Compact audio player control for a single beat.
///
/// Shows play/pause + progress + duration when audio is available,
/// or a "Generate" button that triggers server-side TTS and polls
/// until the audio URL becomes available.
class BeatAudioPlayer extends StatefulWidget {
  final String beatId;
  final String? audioUrl;
  final double? durationSec;

  const BeatAudioPlayer({
    super.key,
    required this.beatId,
    this.audioUrl,
    this.durationSec,
  });

  @override
  State<BeatAudioPlayer> createState() => _BeatAudioPlayerState();
}

class _BeatAudioPlayerState extends State<BeatAudioPlayer> {
  static const _baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://localhost:8000/api/v1',
  );

  String? _audioUrl;
  double? _durationSec;
  bool _isGenerating = false;
  Timer? _pollTimer;
  final http.Client _httpClient = http.Client();

  @override
  void initState() {
    super.initState();
    _audioUrl = widget.audioUrl;
    _durationSec = widget.durationSec;
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    _httpClient.close();
    super.dispose();
  }

  Future<void> _triggerGeneration() async {
    setState(() => _isGenerating = true);

    try {
      await _httpClient.post(
        Uri.parse('$_baseUrl/audio/generate/${widget.beatId}'),
      );
      _startPolling();
    } catch (_) {
      if (mounted) {
        setState(() => _isGenerating = false);
      }
    }
  }

  void _startPolling() {
    _pollTimer = Timer.periodic(const Duration(seconds: 3), (_) async {
      try {
        final response = await _httpClient.get(
          Uri.parse('$_baseUrl/audio/status/${widget.beatId}'),
        );
        if (response.statusCode == 200) {
          final data = jsonDecode(response.body) as Map<String, dynamic>;
          if (data['has_audio'] == true) {
            _pollTimer?.cancel();
            if (mounted) {
              setState(() {
                _audioUrl = data['audio_url'] as String?;
                _durationSec = (data['duration_sec'] as num?)?.toDouble();
                _isGenerating = false;
              });
            }
          }
        }
      } catch (_) {
        // Keep polling on transient errors
      }
    });
  }

  String _formatDuration(double? seconds) {
    if (seconds == null || seconds <= 0) return '0:00';
    final totalSeconds = seconds.round();
    final minutes = totalSeconds ~/ 60;
    final secs = totalSeconds % 60;
    return '$minutes:${secs.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    if (_audioUrl == null) {
      return _buildGenerateButton(colorScheme);
    }

    return _buildPlayerControls(colorScheme);
  }

  Widget _buildGenerateButton(ColorScheme colorScheme) {
    return SizedBox(
      height: 48,
      child: Center(
        child: _isGenerating
            ? Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: colorScheme.primary,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Text(
                    'Generating audio...',
                    style: TextStyle(color: colorScheme.onSurfaceVariant),
                  ),
                ],
              )
            : TextButton.icon(
                onPressed: _triggerGeneration,
                icon: Icon(Icons.graphic_eq, color: colorScheme.primary),
                label: Text(
                  'Generate Audio',
                  style: TextStyle(color: colorScheme.primary),
                ),
              ),
      ),
    );
  }

  Widget _buildPlayerControls(ColorScheme colorScheme) {
    final audioService = context.watch<AudioService>();
    final isThisBeatActive = audioService.currentBeatId == widget.beatId;
    final isPlaying = isThisBeatActive && audioService.isPlaying;
    final isBuffering = isThisBeatActive && audioService.isBuffering;

    // Progress calculation
    double progress = 0.0;
    if (isThisBeatActive && audioService.duration.inMilliseconds > 0) {
      progress = audioService.position.inMilliseconds /
          audioService.duration.inMilliseconds;
    }

    // Duration display: use service duration if active, else stored durationSec
    final displayDuration = isThisBeatActive &&
            audioService.duration.inMilliseconds > 0
        ? _formatDuration(audioService.duration.inSeconds.toDouble())
        : _formatDuration(_durationSec);

    return SizedBox(
      height: 48,
      child: Row(
        children: [
          // Play/pause/buffering button
          SizedBox(
            width: 48,
            height: 48,
            child: isBuffering
                ? Center(
                    child: SizedBox(
                      width: 24,
                      height: 24,
                      child: CircularProgressIndicator(
                        strokeWidth: 2.5,
                        color: colorScheme.primary,
                      ),
                    ),
                  )
                : IconButton(
                    icon: Icon(
                      isPlaying ? Icons.pause_circle_filled : Icons.play_circle_filled,
                      color: colorScheme.primary,
                    ),
                    iconSize: 32,
                    padding: EdgeInsets.zero,
                    onPressed: () {
                      if (isPlaying) {
                        audioService.pause();
                      } else if (isThisBeatActive) {
                        audioService.resume();
                      } else {
                        audioService.play(widget.beatId, _audioUrl!);
                      }
                    },
                  ),
          ),
          const SizedBox(width: 8),
          // Progress bar
          Expanded(
            child: LinearProgressIndicator(
              value: progress.clamp(0.0, 1.0),
              backgroundColor: colorScheme.surfaceContainerHighest,
              valueColor: AlwaysStoppedAnimation<Color>(colorScheme.primary),
              minHeight: 4,
              borderRadius: BorderRadius.circular(2),
            ),
          ),
          const SizedBox(width: 12),
          // Duration label
          Text(
            displayDuration,
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: colorScheme.onSurfaceVariant,
                  fontFeatures: const [FontFeature.tabularFigures()],
                ),
          ),
          const SizedBox(width: 4),
        ],
      ),
    );
  }
}
