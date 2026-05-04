import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

class FeedbackService extends ChangeNotifier {
  static const _baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://localhost:8000/api/v1',
  );

  final http.Client _httpClient;
  bool _isSubmitting = false;
  String? _lastIssueUrl;
  String? _error;

  FeedbackService({http.Client? httpClient})
      : _httpClient = httpClient ?? http.Client();

  bool get isSubmitting => _isSubmitting;
  String? get lastIssueUrl => _lastIssueUrl;
  String? get error => _error;

  Future<FeedbackResult> submit({
    required String transcript,
    String currentRoute = '',
    String devicePlatform = '',
    String deviceOsVersion = '',
    String appVersion = '',
    String? userEmail,
  }) async {
    _isSubmitting = true;
    _error = null;
    notifyListeners();

    try {
      final body = <String, dynamic>{
        'transcript': transcript,
        'current_route': currentRoute,
        'device_platform': devicePlatform,
        'device_os_version': deviceOsVersion,
        'app_version': appVersion,
      };
      if (userEmail != null) body['user_email'] = userEmail;

      final response = await _httpClient.post(
        Uri.parse('$_baseUrl/feedback'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(body),
      );

      if (response.statusCode == 201) {
        final data = jsonDecode(response.body) as Map<String, dynamic>;
        final result = FeedbackResult(
          issueUrl: data['issue_url'] as String,
          issueNumber: data['issue_number'] as int,
          title: data['title'] as String,
        );
        _lastIssueUrl = result.issueUrl;
        _isSubmitting = false;
        notifyListeners();
        return result;
      } else {
        throw FeedbackException(
          'Feedback submission failed (${response.statusCode})',
        );
      }
    } catch (e) {
      _isSubmitting = false;
      if (e is FeedbackException) {
        _error = e.message;
        notifyListeners();
        rethrow;
      }
      _error = e.toString();
      notifyListeners();
      rethrow;
    }
  }
}

class FeedbackResult {
  final String issueUrl;
  final int issueNumber;
  final String title;

  FeedbackResult({
    required this.issueUrl,
    required this.issueNumber,
    required this.title,
  });
}

class FeedbackException implements Exception {
  final String message;
  FeedbackException(this.message);

  @override
  String toString() => message;
}
