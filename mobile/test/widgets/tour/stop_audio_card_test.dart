import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ondoway/models/trip.dart';
import 'package:ondoway/widgets/tour/stop_audio_card.dart';

const _stop = ItineraryStop(
  sortOrder: 0, poiId: 'louvre', poiName: 'The Louvre',
  lat: 48.8606, lng: 2.3376, beatId: 'b0',
  lensName: 'art_history', lensDisplay: 'Art & History',
  durationMin: 15, importanceTier: 1, startTime: '10:00',
  audioUrl: 'https://cdn.example/louvre.mp3',
);

void main() {
  testWidgets('renders stop name, lens chip, and playing state', (tester) async {
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(body: StopAudioCard(
        stop: _stop, isPlaying: true, onReplay: () {}, onSkip: () {},
      )),
    ));
    expect(find.textContaining('The Louvre'), findsOneWidget);
    expect(find.textContaining('Art & History'), findsOneWidget);
    expect(find.textContaining('Playing'), findsOneWidget);
  });

  testWidgets('Replay and Skip fire their callbacks', (tester) async {
    var replayed = 0, skipped = 0;
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(body: StopAudioCard(
        stop: _stop, isPlaying: false,
        onReplay: () => replayed++, onSkip: () => skipped++,
      )),
    ));
    await tester.tap(find.byKey(const Key('tour-replay')));
    await tester.tap(find.byKey(const Key('tour-skip')));
    expect(replayed, 1);
    expect(skipped, 1);
  });
}
