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

  Future<void> fetchProfile(String userId, String accessToken) async {
    final headers = {'Authorization': 'Bearer $accessToken'};

    final profileResp = await _httpClient.get(
      Uri.parse('$_apiBaseUrl/edges/HAS_PROFILE?source_id=$userId&limit=10'),
      headers: headers,
    );

    if (profileResp.statusCode != 200) {
      _isFirstTime = true;
      _isLoaded = true;
      notifyListeners();
      return;
    }

    final profileData = jsonDecode(profileResp.body) as Map<String, dynamic>;
    final profileEdges = profileData['items'] as List<dynamic>;

    if (profileEdges.isEmpty) {
      _isFirstTime = true;
      _isLoaded = true;
      notifyListeners();
      return;
    }

    _profileId = profileEdges[0]['target_id'] as String;

    final nodeResp = await _httpClient.get(
      Uri.parse('$_apiBaseUrl/nodes/Profile/$_profileId'),
      headers: headers,
    );
    if (nodeResp.statusCode == 200) {
      final nodeData = jsonDecode(nodeResp.body) as Map<String, dynamic>;
      final props = nodeData['properties'] as Map<String, dynamic>;
      _displayName = props['display_name'] as String?;
      _themePreference = props['theme_preference'] as String?;
    }

    final lensResp = await _httpClient.get(
      Uri.parse('$_apiBaseUrl/edges/PREFERS_LENS?source_id=$_profileId&limit=200'),
      headers: headers,
    );

    if (lensResp.statusCode == 200) {
      final lensData = jsonDecode(lensResp.body) as Map<String, dynamic>;
      final lensEdges = lensData['items'] as List<dynamic>;
      _selectedLensIds = lensEdges
          .map((e) => (e as Map<String, dynamic>)['target_id'] as String)
          .toList();
    }

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
