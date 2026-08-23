// Phase 5 S5.11 — the minimal session screen (plan defect 12; design §4.6: it
// renders what the service holds and decides nothing). W5.2 R2.5: the question
// on screen ALWAYS as two big buttons with the default marked; R4 "what the
// screen shows": one or two lines — next stop and minutes, the finish clock —
// and the [Head back now] control; NEVER a pause length, a count, "you paused",
// "behind by N", a stopwatch. R1.1 / Nadia: [Head back now] on every screen.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';
import 'package:ondoway/models/trip.dart';
import 'package:ondoway/pages/session_page.dart';
import 'package:ondoway/services/tour_playback_service.dart';

import '../services/mocks/mock_audio_service.dart';
import '../services/mocks/mock_location_service.dart';

const double _degPerMeterLat = 1.0 / 111320.0;

ItineraryStop _stop(int n, {required double lat}) => ItineraryStop(
  sortOrder: n,
  stopId: 'item-$n',
  poiId: 'poi-$n',
  poiName: 'Stop $n',
  lat: lat,
  lng: 2.35,
  beatId: 'beat-$n',
  lensName: 'history',
  lensDisplay: 'History',
  durationMin: 5,
  importanceTier: 3,
  startTime: '',
  audioUrl: 'https://cdn.example.com/$n.mp3',
  audioDurationSec: 100,
  dwellSeconds: 300,
  // S7.3: the footprint this fixture assumed (the phone's old 40 m circle) is
  // now STATED on each stop, as the wire carries it.
  trigger: const StopTrigger(radiusM: 40),
);

const _question =
    'Keep your bench and be at Gare du Nord about 15:20, or sit 4 minutes and be there by 15:12?';

Widget _app(TourPlaybackService service) {
  final router = GoRouter(
    initialLocation: '/session/trip-1',
    routes: [
      GoRoute(
        path: '/session/:tripId',
        builder: (context, state) =>
            SessionPage(tripId: state.pathParameters['tripId']!),
      ),
      GoRoute(
        path: '/saved-trips',
        builder: (context, state) =>
            const Scaffold(body: Center(child: Text('Saved Trips'))),
      ),
    ],
  );
  return ChangeNotifierProvider<TourPlaybackService>.value(
    value: service,
    child: MaterialApp.router(routerConfig: router),
  );
}

void main() {
  const base = 48.85;
  final stops = [
    _stop(0, lat: base),
    _stop(1, lat: base + 300 * _degPerMeterLat),
    _stop(2, lat: base + 600 * _degPerMeterLat),
  ];
  final session = SessionPlan(
    tripId: 'trip-1',
    planVersion: 1,
    stops: stops,
    promises: const [
      SessionPromise(
          promiseId: 'finish', kind: 'finish', name: 'Gare du Nord',
          arrivesHhmm: '15:20', protected: true),
    ],
    retimeToleranceSeconds: 180,
    dayStartHhmm: '09:00',
    // The finish is Stop 2 itself (a round trip back to it), 600 m north.
    finishLat: base + 600 * _degPerMeterLat,
    finishLng: 2.35,
    finishName: 'Gare du Nord',
    contingencies: const [
      SessionContingency(
        contingencyId: 'v1-q',
        trigger: {'kind': 'promise_at_risk', 'stop_id': 'poi-1'},
        planVersion: 1,
        stopIds: ['poi-1', 'poi-2'],
        screenText: _question,
        question: _question,
        defaultArm: 'keep',
        alternateStopIds: ['poi-2'],
        finishHhmm: '15:20',
      ),
      SessionContingency(
        contingencyId: 'v1-w0',
        trigger: {'kind': 'wrap_up_from', 'stop_id': 'poi-0'},
        planVersion: 1,
        stopIds: [],
        screenText: 'Straight to Gare du Nord · Gare du Nord about 14:40',
        finishHhmm: '14:40',
      ),
    ],
  );

  testWidgets('the question is two big buttons with the default named in words; '
      '[Head back now] is on the screen; the lines carry no pause count or '
      'stopwatch', (tester) async {
    var now = DateTime(2026, 8, 19, 9, 0);
    final gps = MockLocationService();
    final service = TourPlaybackService(
      locationService: gps,
      audioService: MockAudioService(),
      now: () => now,
    );
    await service.startTour(stops);
    service.holdSession(session);
    gps.simulatePosition(base - 25 * _degPerMeterLat, 2.35);
    service.pauseTour();
    now = now.add(const Duration(minutes: 3));
    service.resumeTour();
    expect(service.applyContingency('v1-q'), isTrue);

    await tester.pumpWidget(_app(service));
    await tester.pump();

    expect(find.byKey(const Key('session-next-line')), findsOneWidget);
    // The finish clock is the PHONE's re-timing (W5.13), not a stale server line.
    final finishLine = tester.widget<Text>(find.byKey(const Key('session-finish-line')));
    expect(finishLine.data, startsWith('Gare du Nord by '));
    expect(finishLine.data, isNot('Gare du Nord by 15:20'));
    expect(find.byKey(const Key('session-question')), findsOneWidget);
    expect(find.byKey(const Key('session-arm-keep')), findsOneWidget);
    expect(find.byKey(const Key('session-arm-shorten')), findsOneWidget);
    expect(
      find.textContaining('this happens if you do nothing'),
      findsOneWidget,
      reason: 'the default is named in words (R2.5)',
    );
    expect(find.byKey(const Key('session-head-back')), findsOneWidget);
    // Nothing on the screen names the pause, a count or a stopwatch (R4).
    for (final t in find.byType(Text).evaluate()) {
      final data = (t.widget as Text).data ?? '';
      if (data == 'Pause' || data == 'Carry on') continue; // the control itself
      expect(data.toLowerCase(), isNot(contains('paus')));
      expect(data.toLowerCase(), isNot(contains('behind by')));
      expect(data, isNot(matches(RegExp(r'\d\d:\d\d:\d\d'))));
    }
    // Answering: the shorten arm applies the alternate — the screen decided nothing.
    await tester.tap(find.byKey(const Key('session-arm-shorten')));
    await tester.pump();
    expect(service.pendingQuestion, isNull);
    expect(find.byKey(const Key('session-arm-keep')), findsNothing);
    expect(service.nextStop?.poiId, 'poi-2');
    // [Head back now]: the wrap-up entry the server precomputed for this stop.
    await tester.tap(find.byKey(const Key('session-head-back')));
    await tester.pump();
    expect(service.selectedContingency?.contingencyId, 'v1-w0');
    expect(find.text('Straight to Gare du Nord · Gare du Nord about 14:40'),
        findsOneWidget);
    // Straight home: the phone's finish clock moves earlier than with the stops.
    final after = tester.widget<Text>(find.byKey(const Key('session-finish-line')));
    expect(after.data, startsWith('Gare du Nord by '));
    expect(after.data!.compareTo(finishLine.data!) < 0, isTrue,
        reason: 'wrap-up: ${after.data} should be earlier than ${finishLine.data}');
    await tester.pumpWidget(const SizedBox());
  });

  // Phase 7 S7.5 (design §5.6; W7.2 R2 — Fiona & Dev, Nadia): at a stop whose
  // arrival hour prices a line, a couple's piece waits for a TAP; the screen
  // carries the offer and the tap plays it. The screen renders what the service
  // holds and decides nothing.
  testWidgets('at a queued stop a couple sees the offer and the tap plays the piece',
      (tester) async {
    var now = DateTime(2026, 8, 19, 9, 0);
    final gps = MockLocationService();
    final audio = MockAudioService();
    final service = TourPlaybackService(
      locationService: gps,
      audioService: audio,
      now: () => now,
    );
    final queued = [
      ItineraryStop(
        sortOrder: 0, stopId: 'item-0', poiId: 'poi-0', poiName: 'Sainte-Chapelle',
        lat: base, lng: 2.35, beatId: 'beat-0', lensName: 'history',
        lensDisplay: 'History', durationMin: 5, importanceTier: 5, startTime: '',
        audioUrl: 'https://cdn.example.com/0.mp3', audioDurationSec: 100,
        dwellSeconds: 300,
        trigger: const StopTrigger(radiusM: 30, queueSeconds: 28 * 60),
      ),
    ];
    await service.startTour(queued);
    service.holdSession(SessionPlan(
      tripId: 'trip-1', planVersion: 1, stops: queued,
      retimeToleranceSeconds: 180, dayStartHhmm: '09:00', party: 'couple',
      placement: const PlacementPolicy(ownPlaceM: 60, queuePiece: 'tap'),
    ));
    gps.simulatePosition(base + 10 * _degPerMeterLat, 2.35); // in the line
    now = now.add(const Duration(seconds: 40));
    service.tick();
    expect(audio.isPlaying, isFalse);

    await tester.pumpWidget(_app(service));
    await tester.pump();
    expect(find.byKey(const Key('session-armed-offer')), findsOneWidget);
    expect(find.textContaining('Sainte-Chapelle'), findsWidgets);
    await tester.tap(find.byKey(const Key('session-armed-offer')));
    await tester.pump();
    expect(audio.isPlaying, isTrue);
    expect(find.byKey(const Key('session-armed-offer')), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });

  // Phase 7 S7.7 (B) (design §5.6 "segments"; W7.2 R4): under a roof a chapter is
  // offered on the screen — the tap plays it; the screen renders the offer the
  // service holds and decides nothing.
  testWidgets('an indoor chapter is offered on the screen and the tap plays it',
      (tester) async {
    var now = DateTime(2026, 8, 19, 9, 0);
    final gps = MockLocationService();
    final audio = MockAudioService();
    final service = TourPlaybackService(
      locationService: gps,
      audioService: audio,
      now: () => now,
    );
    final marquee = [
      ItineraryStop(
        sortOrder: 0, stopId: 'item-0', poiId: 'nd', poiName: 'Notre-Dame Cathedral',
        lat: base, lng: 2.35, beatId: 'beat-0', lensName: 'history',
        lensDisplay: 'History', durationMin: 25, importanceTier: 5, startTime: '',
        audioUrl: 'https://cdn.example.com/0.mp3', audioDurationSec: 100,
        dwellSeconds: 1500,
        trigger: const StopTrigger(radiusM: 100),
        segments: const [
          StopSegment(label: 'Inside', lat: base, lng: 2.35, radiusM: 60, indoor: true,
              narration: 'The nave.', audioUrl: 'https://cdn.example.com/inside.mp3'),
        ],
      ),
    ];
    await service.startTour(marquee);
    gps.simulatePosition(base - 200 * _degPerMeterLat, 2.35);
    gps.simulatePosition(base, 2.35); // arrive: the story
    audio.simulateComplete();
    now = now.add(const Duration(seconds: 40));
    service.tick();
    expect(audio.isPlaying, isFalse, reason: 'under a roof nothing starts itself');

    await tester.pumpWidget(_app(service));
    await tester.pump();
    expect(find.byKey(const Key('session-chapter-offer')), findsOneWidget);
    expect(find.textContaining('Inside'), findsWidgets);
    await tester.tap(find.byKey(const Key('session-chapter-offer')));
    await tester.pump();
    expect(audio.currentBeatId, 'item-0-seg-0');
    expect(find.byKey(const Key('session-chapter-offer')), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('with no walk running the screen says so and offers nothing to '
      'decide', (tester) async {
    final service = TourPlaybackService(
      locationService: MockLocationService(),
      audioService: MockAudioService(),
    );
    await tester.pumpWidget(_app(service));
    await tester.pump();
    expect(find.text('No walk is running.'), findsOneWidget);
    expect(find.byKey(const Key('session-head-back')), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });
}
