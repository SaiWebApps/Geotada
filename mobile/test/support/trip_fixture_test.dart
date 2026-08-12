@Tags(['vm'])
library;

import 'package:flutter_test/flutter_test.dart';
import 'trip_fixture.dart';

void main() {
  test('paris fixture parses into a 3-stop trip with audio on every stop', () {
    final trip = loadParisFixtureTrip();
    expect(trip.stops.length, 3);
    expect(trip.stops.every((s) => s.audioUrl != null), true);
    expect(trip.stops.first.poiName, 'The Louvre');
    // Paris latitude band — guards against a malformed fixture.
    expect(trip.stops.every((s) => s.lat > 48.8 && s.lat < 48.9), true);
  });
}
