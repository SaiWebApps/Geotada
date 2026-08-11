import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

class ProfileService extends ChangeNotifier {
  static const _apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://localhost:8000/api/v1',
  );
  static const _authBaseUrl = '$_apiBaseUrl/auth';

  final http.Client _httpClient;

  String? _profileId;
  String? _displayName;
  String? _themePreference;
  List<String> _selectedLensIds = [];
  bool _isFirstTime = true;
  bool _isLoaded = false;

  ProfileService({http.Client? httpClient})
      : _httpClient = httpClient ?? http.Client();

  String? get profileId => _profileId;
  String? get displayName => _displayName;
  String? get themePreference => _themePreference;
  List<String> get selectedLensIds => List.unmodifiable(_selectedLensIds);
  bool get isFirstTime => _isFirstTime;
  bool get isLoaded => _isLoaded;

  /// Loads the caller's profile from the public `GET /api/v1/profile` (bearer).
  ///
  /// The endpoint resolves the user from the token and returns the profile in
  /// one call — `{profile_id, display_name, selected_lens_ids, theme_preference}`
  /// — replacing the old `/edges/HAS_PROFILE` + `/nodes/Profile` +
  /// `/edges/PREFERS_LENS` trio, which is workbench-gated and 404s in prod
  /// (project_mobile_prod_api_gap). 404 = no profile yet (first-time). 401/403 =
  /// auth failure — left unloaded so the auth layer can refresh and retry.
  Future<void> fetchProfile(String accessToken) async {
    final resp = await _httpClient.get(
      Uri.parse('$_apiBaseUrl/profile'),
      headers: {'Authorization': 'Bearer $accessToken'},
    );

    if (resp.statusCode == 401 || resp.statusCode == 403) {
      // Auth failed — don't treat as "new user"; leave unloaded so the auth
      // layer can attempt refresh and retry.
      return;
    }

    if (resp.statusCode != 200) {
      // 404 (no profile yet) or any other non-200: first-time user.
      _isFirstTime = true;
      _isLoaded = true;
      notifyListeners();
      return;
    }

    final data = jsonDecode(resp.body) as Map<String, dynamic>;
    _profileId = data['profile_id'] as String?;
    _displayName = data['display_name'] as String?;
    _themePreference = data['theme_preference'] as String?;
    _selectedLensIds = (data['selected_lens_ids'] as List<dynamic>)
        .map((e) => e as String)
        .toList();

    _isFirstTime = _selectedLensIds.isEmpty;
    _isLoaded = true;
    notifyListeners();
  }

  Future<void> completeOnboarding(
    List<String> lensIds,
    String accessToken,
  ) async {
    final resp = await _httpClient.post(
      Uri.parse('$_authBaseUrl/onboarding/complete'),
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer $accessToken',
      },
      body: jsonEncode({'lens_ids': lensIds}),
    );

    if (resp.statusCode != 200) {
      throw ProfileServiceException(
        'Onboarding failed: ${resp.body}',
      );
    }

    final data = jsonDecode(resp.body) as Map<String, dynamic>;
    _profileId = data['profile_id'] as String;
    _displayName = data['display_name'] as String;
    _selectedLensIds = List<String>.from(lensIds);
    _isFirstTime = false;
    notifyListeners();
  }

  Future<void> updateLenses(
    List<String> addIds,
    List<String> removeEdgeIds,
    String accessToken,
  ) async {
    final headers = {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer $accessToken',
    };

    for (final lensId in addIds) {
      await _httpClient.post(
        Uri.parse('$_apiBaseUrl/edges/PREFERS_LENS'),
        headers: headers,
        body: jsonEncode({
          'source': {'label': 'Profile', 'id': _profileId},
          'target': {'label': 'Lens', 'id': lensId},
        }),
      );
    }

    for (final edgeId in removeEdgeIds) {
      await _httpClient.delete(
        Uri.parse('$_apiBaseUrl/edges/PREFERS_LENS/$edgeId'),
        headers: headers,
      );
    }

    notifyListeners();
  }

  Future<void> updateDisplayName(String name, String accessToken) async {
    if (_profileId == null) return;
    final resp = await _httpClient.put(
      Uri.parse('$_apiBaseUrl/nodes/Profile/$_profileId'),
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer $accessToken',
      },
      body: jsonEncode({
        'properties': {'display_name': name},
      }),
    );
    if (resp.statusCode != 200) {
      throw ProfileServiceException('Failed to update name: ${resp.body}');
    }
    _displayName = name;
    notifyListeners();
  }

  Future<void> updateThemePreference(String preference, String accessToken) async {
    if (_profileId == null) return;
    final previous = _themePreference;
    _themePreference = preference;
    notifyListeners();

    try {
      final resp = await _httpClient.put(
        Uri.parse('$_apiBaseUrl/nodes/Profile/$_profileId'),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $accessToken',
        },
        body: jsonEncode({
          'properties': {'theme_preference': preference},
        }),
      );
      if (resp.statusCode != 200) {
        _themePreference = previous;
        notifyListeners();
        throw ProfileServiceException(
          'Failed to update theme: ${resp.body}',
        );
      }
    } catch (e) {
      if (e is! ProfileServiceException) {
        _themePreference = previous;
        notifyListeners();
      }
      rethrow;
    }
  }

  void reset() {
    _profileId = null;
    _displayName = null;
    _themePreference = null;
    _selectedLensIds = [];
    _isFirstTime = true;
    _isLoaded = false;
    notifyListeners();
  }
}

class ProfileServiceException implements Exception {
  final String message;
  ProfileServiceException(this.message);

  @override
  String toString() => message;
}
