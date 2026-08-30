import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:ondoway/models/lens.dart';
import 'package:ondoway/services/lens_service.dart';

// The nested taxonomy shape returned by the public GET /api/v1/lenses:
// a list of parent lenses, each carrying its own children[]. Replaces the old
// two-call /nodes/Lens + /edges/IS_PARENT_OF join.
final _mockLensesResponse = [
  {
    'id': 'p1',
    'name': 'history',
    'display_label': 'History',
    'is_parent': true,
    'children': [
      {'id': 'c1', 'name': 'hidden_history', 'display_label': 'Hidden History', 'is_parent': false},
      {'id': 'c2', 'name': 'dark_history', 'display_label': 'Dark History', 'is_parent': false},
    ],
  },
  {
    'id': 'p2',
    'name': 'arts_culture',
    'display_label': 'Arts & Culture',
    'is_parent': true,
    'children': [
      {'id': 'c3', 'name': 'street_art', 'display_label': 'Street Art', 'is_parent': false},
    ],
  },
];

MockClient _createMockClient() {
  return MockClient((request) async {
    if (request.url.path.endsWith('/lenses')) {
      return http.Response(jsonEncode(_mockLensesResponse), 200);
    }
    return http.Response('Not found', 404);
  });
}

void main() {
  group('Lens model', () {
    test('fromApiJson parses a parent from the /lenses shape', () {
      final lens = Lens.fromApiJson(_mockLensesResponse[0] as Map<String, dynamic>);
      expect(lens.id, 'p1');
      expect(lens.name, 'history');
      expect(lens.displayLabel, 'History');
      expect(lens.isParent, true);
    });

    test('fromApiJson parses a child from the /lenses shape', () {
      final child = (_mockLensesResponse[0]['children'] as List).first as Map<String, dynamic>;
      final lens = Lens.fromApiJson(child);
      expect(lens.id, 'c1');
      expect(lens.name, 'hidden_history');
      expect(lens.displayLabel, 'Hidden History');
      expect(lens.isParent, false);
    });
  });

  group('LensService', () {
    test('fetchLenses loads the nested taxonomy and groups children by parent', () async {
      final service = LensService(httpClient: _createMockClient());
      await service.fetchLenses();

      expect(service.isLoaded, true);
      expect(service.allLenses.length, 5); // 2 parents + 3 children
      expect(service.selectableLenses.length, 3);
      expect(service.childrenByParent.keys.length, 2);
      expect(service.childrenByParent['History']!.length, 2);
      expect(service.childrenByParent['Arts & Culture']!.length, 1);
    });

    test('fetchLenses hits the public /lenses endpoint, not the workbench node/edge routes', () async {
      final requestedPaths = <String>[];
      final service = LensService(
        httpClient: MockClient((request) async {
          requestedPaths.add(request.url.path);
          return http.Response(jsonEncode(_mockLensesResponse), 200);
        }),
      );
      await service.fetchLenses();

      expect(requestedPaths.any((p) => p.endsWith('/lenses')), true,
          reason: 'must call the new public /lenses endpoint');
      expect(requestedPaths.any((p) => p.contains('/nodes/') || p.contains('/edges/')), false,
          reason: 'must NOT call the workbench endpoints (they 404 in prod)');
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
