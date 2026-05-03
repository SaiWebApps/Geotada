import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:ondoway/models/lens.dart';

class LensService extends ChangeNotifier {
  static const _baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://localhost:8000/api/v1',
  );

  final http.Client _httpClient;

  List<Lens> _allLenses = [];
  Map<String, List<Lens>> _childrenByParent = {};
  bool _isLoaded = false;

  LensService({http.Client? httpClient})
      : _httpClient = httpClient ?? http.Client();

  List<Lens> get allLenses => _allLenses;
  Map<String, List<Lens>> get childrenByParent => _childrenByParent;
  bool get isLoaded => _isLoaded;

  List<Lens> get selectableLenses =>
      _allLenses.where((l) => !l.isParent).toList();

  Future<void> fetchLenses() async {
    final lensResp = await _httpClient.get(
      Uri.parse('$_baseUrl/nodes/Lens?limit=200'),
    );
    if (lensResp.statusCode != 200) {
      throw LensServiceException('Failed to fetch lenses: ${lensResp.body}');
    }

    final lensData = jsonDecode(lensResp.body) as Map<String, dynamic>;
    final items = lensData['items'] as List<dynamic>;
    _allLenses = items.map((j) => Lens.fromApiJson(j as Map<String, dynamic>)).toList();

    final edgeResp = await _httpClient.get(
      Uri.parse('$_baseUrl/edges/IS_PARENT_OF?limit=200'),
    );
    if (edgeResp.statusCode != 200) {
      throw LensServiceException('Failed to fetch lens hierarchy: ${edgeResp.body}');
    }

    final edgeData = jsonDecode(edgeResp.body) as Map<String, dynamic>;
    final edges = edgeData['items'] as List<dynamic>;

    final parentById = <String, Lens>{};
    final childById = <String, Lens>{};
    for (final lens in _allLenses) {
      if (lens.isParent) {
        parentById[lens.id] = lens;
      } else {
        childById[lens.id] = lens;
      }
    }

    _childrenByParent = {};
    for (final edge in edges) {
      final e = edge as Map<String, dynamic>;
      final parentId = e['source_id'] as String;
      final childId = e['target_id'] as String;
      final parent = parentById[parentId];
      final child = childById[childId];
      if (parent != null && child != null) {
        _childrenByParent
            .putIfAbsent(parent.displayLabel, () => [])
            .add(child);
      }
    }

    _isLoaded = true;
    notifyListeners();
  }
}

class LensServiceException implements Exception {
  final String message;
  LensServiceException(this.message);

  @override
  String toString() => message;
}
