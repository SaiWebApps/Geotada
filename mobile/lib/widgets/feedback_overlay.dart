import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:ondoway/services/auth_service.dart';
import 'package:ondoway/services/feedback_service.dart';
import 'package:provider/provider.dart';
import 'package:speech_to_text/speech_to_text.dart' as stt;

class FeedbackOverlay extends StatelessWidget {
  final Widget child;
  const FeedbackOverlay({super.key, required this.child});

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        child,
        const Positioned(
          right: 16,
          bottom: 96,
          child: _FeedbackFab(),
        ),
      ],
    );
  }
}

class _FeedbackFab extends StatelessWidget {
  const _FeedbackFab();

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return FloatingActionButton.small(
      heroTag: 'feedback_fab',
      onPressed: () => _showFeedbackSheet(context),
      backgroundColor: colorScheme.tertiary,
      foregroundColor: colorScheme.onTertiary,
      child: const Icon(Icons.feedback_outlined),
    );
  }

  void _showFeedbackSheet(BuildContext context) {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      builder: (sheetContext) => const _FeedbackSheet(),
    );
  }
}

class _FeedbackSheet extends StatefulWidget {
  const _FeedbackSheet();

  @override
  State<_FeedbackSheet> createState() => _FeedbackSheetState();
}

class _FeedbackSheetState extends State<_FeedbackSheet> {
  final _controller = TextEditingController();
  final _speech = stt.SpeechToText();
  bool _isSubmitting = false;
  bool _isListening = false;
  bool _speechAvailable = false;

  @override
  void initState() {
    super.initState();
    _initSpeech();
  }

  Future<void> _initSpeech() async {
    try {
      _speechAvailable = await _speech.initialize(
        onError: (error) {
          if (mounted) setState(() => _isListening = false);
        },
      );
    } catch (_) {
      _speechAvailable = false;
    }
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    _speech.stop();
    _controller.dispose();
    super.dispose();
  }

  void _toggleListening() {
    if (_isListening) {
      _speech.stop();
      setState(() => _isListening = false);
    } else {
      _speech.listen(
        onResult: (result) {
          if (mounted) {
            setState(() {
              _controller.text = result.recognizedWords;
              _controller.selection = TextSelection.fromPosition(
                TextPosition(offset: _controller.text.length),
              );
            });
          }
        },
        listenFor: const Duration(seconds: 30),
        pauseFor: const Duration(seconds: 3),
      );
      setState(() => _isListening = true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Padding(
      padding: EdgeInsets.only(
        left: 24,
        right: 24,
        top: 24,
        bottom: MediaQuery.of(context).viewInsets.bottom + 24,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            'Send Feedback',
            style: Theme.of(context).textTheme.titleLarge,
          ),
          const SizedBox(height: 8),
          Text(
            'Tap the mic to speak, or type your feedback.',
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  color: colorScheme.onSurfaceVariant,
                ),
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _controller,
            maxLines: 4,
            minLines: 2,
            textCapitalization: TextCapitalization.sentences,
            decoration: InputDecoration(
              hintText: _isListening
                  ? 'Listening...'
                  : 'Type or tap mic to speak...',
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
              ),
              suffixIcon: _speechAvailable
                  ? IconButton(
                      onPressed: _isSubmitting ? null : _toggleListening,
                      icon: Icon(
                        _isListening ? Icons.stop_circle : Icons.mic,
                        color: _isListening
                            ? colorScheme.error
                            : colorScheme.primary,
                      ),
                    )
                  : null,
            ),
            onChanged: (_) => setState(() {}),
          ),
          if (_isListening)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: LinearProgressIndicator(
                color: colorScheme.error,
                backgroundColor: colorScheme.errorContainer,
              ),
            ),
          const SizedBox(height: 16),
          FilledButton.icon(
            onPressed:
                _controller.text.trim().isEmpty || _isSubmitting
                    ? null
                    : _submit,
            icon: _isSubmitting
                ? SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: colorScheme.onPrimary,
                    ),
                  )
                : const Icon(Icons.send),
            label: Text(_isSubmitting ? 'Submitting...' : 'Submit'),
          ),
        ],
      ),
    );
  }

  Future<void> _submit() async {
    if (_isListening) {
      _speech.stop();
      setState(() => _isListening = false);
    }

    final text = _controller.text.trim();
    if (text.isEmpty) return;

    setState(() => _isSubmitting = true);

    try {
      final feedbackService = context.read<FeedbackService>();
      final authService = context.read<AuthService>();

      String platform = 'unknown';
      switch (defaultTargetPlatform) {
        case TargetPlatform.iOS:
          platform = 'iOS';
        case TargetPlatform.android:
          platform = 'Android';
        default:
          platform = 'web';
      }

      final result = await feedbackService.submit(
        transcript: text,
        devicePlatform: platform,
        appVersion: '0.1.0',
        userEmail: authService.userEmail,
      );

      if (mounted) {
        Navigator.of(context).pop();
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Feedback submitted: ${result.title}'),
            duration: const Duration(seconds: 4),
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        setState(() => _isSubmitting = false);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Failed to submit: $e'),
            backgroundColor: Theme.of(context).colorScheme.error,
          ),
        );
      }
    }
  }
}
