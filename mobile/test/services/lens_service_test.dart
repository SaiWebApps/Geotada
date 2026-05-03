import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:ondoway/models/lens.dart';
import 'package:ondoway/services/lens_service.dart';

final _mockLensItems = [
  {'id': 'p1', 'labels': ['Lens'], 'properties': {'name': 'history', 'display_label': 'History', 'is_parent': true}},
  {'id': 'p2', 'labels': ['Lens'], 'properties': {'name': 'arts_culture', 'display_label': 'Arts & Culture', 'is_parent': true}},
  {'id': 'c1', 'labels': ['Lens'], 'properties': {'name': 'hidden_history', 'display_label': 'Hidden History', 'is_parent': false}},
  {'id': 'c2', 'labels': ['Lens'], 'properties': {'name': 'dark_history', 'display_label': 'Dark History', 'is_parent': false}},
  {'id': 'c3', 'labels': ['Lens'], 'properties': {'name': 'street_art', 'display_label': 'Street Art', 'is_parent': false}},
];

final _mockEdgeItems = [
  {'id': 'e1', 'type': 'IS_PARENT_OF', 'source_id': 'p1', 'target_id': 'c1', 'properties': {}},
  {'id': 'e2', 'type': 'IS_PARENT_OF', 'source_id': 'p1', 'target_id': 'c2', 'properties': {}},
  {'id': 'e3', 'type': 'IS_PARENT_OF', 'source_id': 'p2', 'target_id': 'c3', 'properties': {}},
];

MockClient _createMockClient() {
  return MockClient((request) async {
    if (request.url.path.contains('/nodes/Lens')) {
      return http.Response(
        jsonEncode({
          'items': _mockLensItems,
          'total': _mockLensItems.length,
          'skip': 0,
          'limit': 200,
        }),
        200,
      );
    }
    if (request.url.path.contains('/edges/IS_PARENT_OF')) {
      return http.Response(
        jsonEncode({
          'items': _mockEdgeItems,
          'total': _mockEdgeItems.length,
          'skip': 0,
          'limit': 200,
        }),
        200,
      );
    }
    return http.Response('Not found', 404);
  });
}

void main() {
  group('Lens model', () {
    test('fromApiJson parses correctly', () {
      final lens = Lens.fromApiJson(_mockLensItems[0] as Map<String, dynamic>);
      expect(lens.id, 'p1');
      expect(lens.name, 'history');
      expect(lens.displayLabel, 'History');
      expect(lens.isParent, true);
    });

    test('fromApiJson handles child lens', () {
      final lens = Lens.fromApiJson(_mockLensItems[2] as Map<String, dynamic>);
      expect(lens.id, 'c1');
      expect(lens.name, 'hidden_history');
      expect(lens.displayLabel, 'Hidden History');
      expect(lens.isParent, false);
    });
  });

  group('LensService', () {
    test('fetchLenses loads and groups lenses by parent', () async {
      final service = LensService(httpClient: _createMockClient());
      await service.fetchLenses();

      expect(service.isLoaded, true);
      expect(service.allLenses.length, 5);
      expect(service.selectableLenses.length, 3);
      expect(service.childrenByParent.keys.length, 2);
      expect(service.childrenByParent['History']!.length, 2);
      expect(service.childrenByParent['Arts & Culture']!.length, 1);
    });

    test('selectableLenses excludes parents', () async {
      final service = LensService(httpClient: _createMockClient());
      await service.fetchLenses();

      final names = service.selectableLenses.map((l) => l.name).toList();
      expect(names, contains('hidden_history'));
      expect(names, contains('dark_history'));
      expect(names, contains('street_art'));
      expect(names, isNot(contains('history')));
      expect(names, isNot(contains('arts_culture')));
    });

    test('fetchLenses handles API failure', () async {
      final service = LensService(
        httpClient: MockClient((r) async => http.Response('error', 500)),
      );
      expect(() => service.fetchLenses(), throwsA(isA<LensServiceException>()));
    });

    test('isLoaded is false before fetch', () {
      final service = LensService(httpClient: _createMockClient());
      expect(service.isLoaded, false);
      expect(service.allLenses, isEmpty);
    });
  });
}
