import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class AuthService extends ChangeNotifier {
  static const _apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://localhost:8000/api/v1',
  );
  static const _baseUrl = '$_apiBaseUrl/auth';
  static const _accessTokenKey = 'access_token';
  static const _refreshTokenKey = 'refresh_token';

  final FlutterSecureStorage _storage;
  final http.Client _httpClient;

  String? _accessToken;
  String? _userId;
  String? _userEmail;
  bool _isLoading = false;

  AuthService({
    FlutterSecureStorage? storage,
    http.Client? httpClient,
  })  : _storage = storage ?? const FlutterSecureStorage(),
        _httpClient = httpClient ?? http.Client();

  bool get isAuthenticated => _accessToken != null;
  String? get accessToken => _accessToken;
  String? get userId => _userId;
  String? get userEmail => _userEmail;
  bool get isLoading => _isLoading;

  Future<void> tryRestoreSession() async {
    final token = await _storage.read(key: _accessTokenKey);
    if (token == null) return;

    _accessToken = token;
    try {
      await _fetchMe();
    } catch (_) {
      _accessToken = null;
      _userId = null;
      await _storage.delete(key: _accessTokenKey);
      await _storage.delete(key: _refreshTokenKey);
    }
    notifyListeners();
  }

  Future<void> requestMagicLink(String email) async {
    _isLoading = true;
    notifyListeners();

    try {
      final resp = await _httpClient.post(
        Uri.parse('$_baseUrl/magic-link/request'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'email': email}),
      );

      if (resp.statusCode != 200) {
        throw AuthException('Failed to send magic link: ${resp.body}');
      }
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> verifyMagicLink(String token) async {
    _isLoading = true;
    notifyListeners();

    try {
      final resp = await _httpClient.post(
        Uri.parse('$_baseUrl/magic-link/verify'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'token': token}),
      );

      if (resp.statusCode != 200) {
        throw AuthException('Magic link verification failed: ${resp.body}');
      }

      final data = jsonDecode(resp.body) as Map<String, dynamic>;
      await _storeTokens(data['access_token'], data['refresh_token']);
      await _fetchMe();
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> loginWithGoogle(String idToken) async {
    _isLoading = true;
    notifyListeners();

    try {
      final resp = await _httpClient.post(
        Uri.parse('$_baseUrl/google'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'id_token': idToken}),
      );

      if (resp.statusCode != 200) {
        throw AuthException('Google login failed: ${resp.body}');
      }

      final data = jsonDecode(resp.body) as Map<String, dynamic>;
      await _storeTokens(data['access_token'], data['refresh_token']);
      await _fetchMe();
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> logout() async {
    _accessToken = null;
    _userId = null;
    _userEmail = null;
    await _storage.delete(key: _accessTokenKey);
    await _storage.delete(key: _refreshTokenKey);
    notifyListeners();
  }

  Future<void> _fetchMe() async {
    if (_accessToken == null) return;

    final resp = await _httpClient.get(
      Uri.parse('$_baseUrl/me'),
      headers: {'Authorization': 'Bearer $_accessToken'},
    );

    if (resp.statusCode != 200) {
      throw AuthException('Failed to fetch user: ${resp.body}');
    }

    final data = jsonDecode(resp.body) as Map<String, dynamic>;
    _userId = data['id'] as String?;
    _userEmail = data['email'] as String?;
    notifyListeners();
  }

  Future<void> _storeTokens(String accessToken, String refreshToken) async {
    _accessToken = accessToken;
    await _storage.write(key: _accessTokenKey, value: accessToken);
    await _storage.write(key: _refreshTokenKey, value: refreshToken);
  }
}

class AuthException implements Exception {
  final String message;
  AuthException(this.message);

  @override
  String toString() => message;
}
