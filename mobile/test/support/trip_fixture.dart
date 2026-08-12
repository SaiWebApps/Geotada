import 'dart:convert';
import 'dart:io';

import 'package:ondoway/models/trip.dart';

/// Loads the committed Paris trip fixture as a [GeneratedTrip].
/// Uses dart:io — any test calling this must be annotated `@Tags(['vm'])`.
GeneratedTrip loadParisFixtureTrip() {
  final raw = File('test/fixtures/paris_golden_trip.json').readAsStringSync();
  return GeneratedTrip.fromJson(jsonDecode(raw) as Map<String, dynamic>);
}
