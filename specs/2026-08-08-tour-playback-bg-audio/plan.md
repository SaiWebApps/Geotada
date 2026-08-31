# Tour-playback Background Audio — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the real `AudioService`/`TourPlaybackService` play a tour stop's narration through a locked/pocketed iPhone, using Slice 0.3's proven `.playback`/`.duckOthers` foreground-activated session — and prove it on-device — without building the tour UI.

**Architecture:** A new foreground-only `prepareSession()` method on the `AudioProvider` seam invokes a small native `com.ondoway/audio_session` MethodChannel that activates a `.playback`/`.spokenAudio`/`.duckOthers` `AVAudioSession`. `TourPlaybackService.startTour` calls it before starting **background** location tracking; the existing 10m geofence then plays cached audio via just_audio on the already-active session, audible while locked. A debug-gated proof harness starts a real 2-stop tour to capture the on-device proof.

**Tech Stack:** Flutter, Dart, just_audio ^0.9.40, geolocator ^13.0.2, go_router, provider; iOS Swift (AVFoundation).

## Global Constraints

- Extend the existing app; **iOS-first**. Add **no new packages**.
- The `AudioProvider` change MUST be **backward compatible** — add a method; existing callers unchanged.
- Session config is exactly `.playback`, mode `.spokenAudio`, options `[.duckOthers]`; **activate only in the foreground** (background activation returns `CannotInterruptOthers` = 560557684).
- Geofence radius is **10m** (already implemented in `TourPlaybackService._onPositionUpdate`); do not change it.
- Background playback must use a **cached local file**, never a cold URL stream.
- On-device builds use `make flutter-device-profile` (AOT — the iOS-26 debug-JIT fix, Slice 0.3 `f133889`).
- All test runs go through Makefile targets (`make flutter-test`, `make flutter-analyze`) — never raw `flutter test`.
- `make flutter-clean` is required after any asset change.
- Keep the native channel in `AppDelegate.swift` (no new `.swift` file → no `project.pbxproj` registration needed).

---

## File Structure

- `mobile/lib/services/providers.dart` — add `prepareSession()` to `AudioProvider`.
- `mobile/lib/services/audio_service.dart` — implement `prepareSession()` (native channel call).
- `mobile/lib/services/tour_playback_service.dart` — `startTour` prepares session + tracks in background.
- `mobile/ios/Runner/AppDelegate.swift` — register the `com.ondoway/audio_session` channel.
- `mobile/test/services/mocks/mock_audio_service.dart` — add `prepareSession()` + call log.
- `mobile/test/services/mocks/mock_location_service.dart` — capture `background` flag + call log.
- `mobile/test/services/audio_session_prepare_test.dart` — **new**, channel-invocation test.
- `mobile/test/services/tour_playback_service_test.dart` — add the AC1 order/background test.
- `mobile/lib/spike/tour_playback_proof_page.dart` — **new**, debug proof harness.
- `mobile/lib/router.dart` — add the debug route for the harness.
- `mobile/assets/audio/arrived.mp3` + `mobile/pubspec.yaml` — bundled proof clip.

---

## Task 1: `AudioProvider.prepareSession()` seam + `AudioService` native-channel call

**Files:**
- Modify: `mobile/lib/services/providers.dart`
- Modify: `mobile/lib/services/audio_service.dart`
- Modify: `mobile/test/services/mocks/mock_audio_service.dart`
- Create: `mobile/test/services/audio_session_prepare_test.dart`

**Interfaces:**
- Produces: `Future<void> AudioProvider.prepareSession()` — activates the iOS audio session in the foreground; no-op off iOS; never throws.

- [ ] **Step 1: Add the method to the `AudioProvider` interface**

In `mobile/lib/services/providers.dart`, inside `abstract class AudioProvider`, after the `play(...)` declaration:

```dart
  /// Activate the iOS audio session (.playback/.duckOthers) so playback is
  /// audible through a locked screen. MUST be called from the foreground — iOS
  /// refuses session activation from a background callback
  /// (AVAudioSessionErrorCodeCannotInterruptOthers). No-op off iOS; never throws.
  Future<void> prepareSession();
```

- [ ] **Step 2: Implement it in `AudioService`**

In `mobile/lib/services/audio_service.dart`, add the import at the top:

```dart
import 'package:flutter/services.dart';
```

Add the channel field near `_playerInstance`:

```dart
  static const MethodChannel _sessionChannel =
      MethodChannel('com.ondoway/audio_session');
```

Add the method (near `play`):

```dart
  @override
  Future<void> prepareSession() async {
    try {
      await _sessionChannel.invokeMethod<void>('prepare');
    } catch (e) {
      debugPrint('AudioService.prepareSession failed: $e');
    }
  }
```

- [ ] **Step 3: Add `prepareSession()` to the mock (keeps the suite compiling) with a call log**

In `mobile/test/services/mocks/mock_audio_service.dart`, add fields after `_playCount`:

```dart
  int prepareSessionCount = 0;
  List<String>? callLog;
```

Add the override:

```dart
  @override
  Future<void> prepareSession() async {
    prepareSessionCount++;
    callLog?.add('prepare');
  }
```

- [ ] **Step 4: Write the failing test for the channel invocation**

Create `mobile/test/services/audio_session_prepare_test.dart`:

```dart
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ondoway/services/audio_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel('com.ondoway/audio_session');

  test('prepareSession invokes "prepare" on the audio_session channel', () async {
    final calls = <String>[];
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
      calls.add(call.method);
      return null;
    });
    addTearDown(() {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, null);
    });

    await AudioService().prepareSession();

    expect(calls, ['prepare']);
  });
}
```

- [ ] **Step 5: Run the suite to verify the new test currently passes and nothing broke**

Run: `make flutter-test`
Expected: PASS (new test green; existing suite still green — the mock update keeps it compiling).

- [ ] **Step 6: Mutation-prove the test**

Temporarily comment out the `await _sessionChannel.invokeMethod<void>('prepare');` line in `audio_service.dart`, run `make flutter-test`, and confirm `audio_session_prepare_test.dart` goes **RED** (`calls` is empty). Restore the line; confirm GREEN.

- [ ] **Step 7: Analyze + commit**

```bash
make flutter-analyze
git add mobile/lib/services/providers.dart mobile/lib/services/audio_service.dart mobile/test/services/mocks/mock_audio_service.dart mobile/test/services/audio_session_prepare_test.dart
git commit -m "feat(audio): AudioProvider.prepareSession() — foreground iOS session activation"
```

---

## Task 2: `TourPlaybackService.startTour` prepares the session + tracks in background (AC1)

**Files:**
- Modify: `mobile/lib/services/tour_playback_service.dart:56-63`
- Modify: `mobile/test/services/mocks/mock_location_service.dart`
- Modify: `mobile/test/services/tour_playback_service_test.dart`

**Interfaces:**
- Consumes: `AudioProvider.prepareSession()` (Task 1); `LocationProvider.startTracking({bool background})`.

- [ ] **Step 1: Add capture fields to the location mock**

In `mobile/test/services/mocks/mock_location_service.dart`, add fields after `_error`:

```dart
  bool? lastBackground;
  List<String>? callLog;
```

In `startTracking`, record them at the very top of the method body (before the `trackingWillSucceed` check):

```dart
    lastBackground = background;
    callLog?.add('track');
```

- [ ] **Step 2: Write the failing test (AC1)**

In `mobile/test/services/tour_playback_service_test.dart`, inside the `group('TourPlaybackService lifecycle', ...)` block, add:

```dart
    test('startTour prepares the audio session before background tracking (AC1)',
        () async {
      final log = <String>[];
      audioService.callLog = log;
      locationService.callLog = log;
      final stops = [
        _makeStop(
          sortOrder: 1,
          beatId: 'b1',
          lat: 48.8584,
          lng: 2.2945,
          audioUrl: 'https://example.test/1.mp3',
        ),
      ];

      await service.startTour(stops);

      expect(log, ['prepare', 'track']);
      expect(locationService.lastBackground, isTrue);
      expect(audioService.prepareSessionCount, 1);
    });
```

- [ ] **Step 3: Run it to verify it fails**

Run: `make flutter-test`
Expected: FAIL — current `startTour` never calls `prepareSession` (log is `['track']`) and calls `startTracking()` without `background` (`lastBackground` is `false`).

- [ ] **Step 4: Implement the wiring**

In `mobile/lib/services/tour_playback_service.dart`, replace the tracking block in `startTour` (currently lines ~56-63):

```dart
    // Start GPS tracking
    final started = await _locationService.startTracking();
```

with:

```dart
    // Activate the audio session while we are FOREGROUND. iOS grants session
    // activation only to a frontmost app; from a background geofence callback it
    // returns CannotInterruptOthers (560557684). Once active it survives lock, so
    // the fire path only needs to play. (No-op off iOS.)
    await _audioService.prepareSession();

    // Start GPS tracking — background:true so position updates keep arriving when
    // the screen locks and the phone is pocketed (Slice 0.3).
    final started = await _locationService.startTracking(background: true);
```

- [ ] **Step 5: Run it to verify it passes**

Run: `make flutter-test`
Expected: PASS — `log == ['prepare', 'track']`, `lastBackground == true`.

- [ ] **Step 6: Mutation-prove both halves**

1. Change `startTracking(background: true)` back to `startTracking()`, run `make flutter-test` → the AC1 test goes **RED** on `lastBackground`. Restore.
2. Delete the `await _audioService.prepareSession();` line, run `make flutter-test` → the AC1 test goes **RED** (`log == ['track']`). Restore. Confirm GREEN.

- [ ] **Step 7: Analyze + commit**

```bash
make flutter-analyze
git add mobile/lib/services/tour_playback_service.dart mobile/test/services/mocks/mock_location_service.dart mobile/test/services/tour_playback_service_test.dart
git commit -m "feat(tour): startTour activates session + tracks in background (AC1)"
```

---

## Task 3: Native `com.ondoway/audio_session` channel

**Files:**
- Modify: `mobile/ios/Runner/AppDelegate.swift`

**Interfaces:**
- Consumes: the Dart call `MethodChannel('com.ondoway/audio_session').invokeMethod('prepare')` (Task 1).
- Produces: an active `.playback`/`.duckOthers` session on `prepare`.

> No Flutter unit test — this is Swift. It compiles in the Task 4 device build and is functionally proven by the Task 4 on-device run. Verify by code review that it mirrors the Slice 0.3 `bg_audio` `prepare` exactly (same category/mode/options, same messenger).

- [ ] **Step 1: Register the channel**

In `mobile/ios/Runner/AppDelegate.swift`, inside `didInitializeImplicitFlutterEngine`, after `registerBackgroundAudioChannel(messenger)`:

```swift
    registerAudioSessionChannel(messenger)
```

- [ ] **Step 2: Add the handler**

Add this method to `AppDelegate` (below `registerBackgroundAudioChannel`):

```swift
  /// Foreground-only audio-session activation for the PRODUCTION tour-playback
  /// path (just_audio owns actual playback here — no raw bytes). `prepare`
  /// activates the .playback/.duckOthers session while the app is frontmost; it
  /// then survives lock, so a background geofence fire plays without
  /// re-activating (which returns CannotInterruptOthers). Same mechanism proven
  /// in the Slice 0.3 spike, minus the raw-bytes `play`.
  private func registerAudioSessionChannel(_ messenger: FlutterBinaryMessenger) {
    let channel = FlutterMethodChannel(
      name: "com.ondoway/audio_session", binaryMessenger: messenger)
    channel.setMethodCallHandler { call, result in
      guard call.method == "prepare" else {
        result(FlutterMethodNotImplemented)
        return
      }
      let session = AVAudioSession.sharedInstance()
      do {
        try session.setCategory(.playback, mode: .spokenAudio, options: [.duckOthers])
        try session.setActive(true)
        result(nil)
      } catch {
        result(FlutterError(code: "audio_session", message: "\(error)", details: nil))
      }
    }
  }
```

- [ ] **Step 3: Commit**

```bash
git add mobile/ios/Runner/AppDelegate.swift
git commit -m "feat(ios): com.ondoway/audio_session channel — foreground .playback/.duckOthers activation"
```

---

## Task 4: Debug proof harness + on-device proof (AC2–AC5)

**Files:**
- Create: `mobile/assets/audio/arrived.mp3` (short spoken MP3, e.g. "You have arrived.")
- Modify: `mobile/pubspec.yaml` (register the asset)
- Create: `mobile/lib/spike/tour_playback_proof_page.dart`
- Modify: `mobile/lib/router.dart`

**Interfaces:**
- Consumes: `TourPlaybackService.startTour`, `LocationService`, `AudioProvider` (via `providers.dart` provider wiring in `main.dart`).

- [ ] **Step 1: Add the bundled clip + register it**

Place a short MP3 at `mobile/assets/audio/arrived.mp3`. In `mobile/pubspec.yaml`, under `flutter: assets:`, add:

```yaml
    - assets/audio/arrived.mp3
```

Then:

```bash
make flutter-clean
```

- [ ] **Step 2: Write the harness page**

Create `mobile/lib/spike/tour_playback_proof_page.dart`:

```dart
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:geolocator/geolocator.dart';
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';
import 'package:ondoway/models/trip.dart';
import 'package:ondoway/services/location_service.dart';
import 'package:ondoway/services/tour_playback_service.dart';

/// Debug-only harness proving the PRODUCTION tour-playback path plays audio
/// through a locked screen. Two stops are placed ~15m and ~30m ahead of the
/// current position; the tester locks the phone, pockets it, and walks forward.
class TourPlaybackProofPage extends StatefulWidget {
  const TourPlaybackProofPage({super.key});

  @override
  State<TourPlaybackProofPage> createState() => _TourPlaybackProofPageState();
}

class _TourPlaybackProofPageState extends State<TourPlaybackProofPage> {
  final List<String> _log = [];

  void _add(String line) {
    if (!mounted) return;
    setState(() => _log.insert(0, line));
  }

  // Mirrors AudioService's cache convention (temp/ondoway_audio/<beatId>.mp3) so
  // startTour plays a LOCAL file, not a cold URL stream. Debug harness only.
  Future<void> _cacheClip(String beatId) async {
    final bytes = await rootBundle.load('assets/audio/arrived.mp3');
    final dir = Directory('${(await getTemporaryDirectory()).path}/ondoway_audio');
    if (!await dir.exists()) await dir.create(recursive: true);
    await File('${dir.path}/$beatId.mp3')
        .writeAsBytes(bytes.buffer.asUint8List());
  }

  Future<void> _startProof() async {
    final location = context.read<LocationService>();
    final tour = context.read<TourPlaybackService>();

    final started = await location.startTracking(background: true);
    if (!started) {
      _add('Could not get location permission/tracking.');
      return;
    }
    // Give the fix a moment to arrive.
    await Future<void>.delayed(const Duration(seconds: 2));
    final pos = location.lastPosition as Position?;
    if (pos == null) {
      _add('No position yet — try again.');
      return;
    }
    location.stopTracking(); // startTour restarts it in background.

    await _cacheClip('proof-1');
    await _cacheClip('proof-2');

    // ~0.00014 deg latitude ≈ 15.5m per step, due north.
    final stops = [
      _proofStop(1, 'proof-1', pos.latitude + 0.00014, pos.longitude),
      _proofStop(2, 'proof-2', pos.latitude + 0.00028, pos.longitude),
    ];

    final ok = await tour.startTour(stops);
    _add(ok
        ? 'Tour started. Lock the phone, pocket it, walk NORTH ~15m then ~30m.'
        : 'startTour failed.');
  }

  ItineraryStop _proofStop(int order, String beatId, double lat, double lng) =>
      ItineraryStop(
        sortOrder: order,
        stopId: beatId,
        poiId: 'proof-poi-$order',
        poiName: 'Proof Stop $order',
        lat: lat,
        lng: lng,
        beatId: beatId,
        lensName: 'history',
        lensDisplay: 'History',
        durationMin: 1,
        importanceTier: 3,
        startTime: '09:0$order',
        audioUrl: 'cached://$beatId', // unused: cache hit wins in AudioService
      );

  @override
  Widget build(BuildContext context) {
    final tour = context.watch<TourPlaybackService>();
    return Scaffold(
      appBar: AppBar(title: const Text('Tour Playback Proof (debug)')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('State: ${tour.state}'),
            Text('Current stop index: ${tour.currentStopIndex}'),
            Text(tour.distanceToNext == null
                ? 'Distance to next: —'
                : 'Distance to next: ${tour.distanceToNext!.toStringAsFixed(1)} m'),
            const SizedBox(height: 12),
            FilledButton(
              onPressed: _startProof,
              child: const Text('Prepare & start proof tour'),
            ),
            const SizedBox(height: 8),
            OutlinedButton(
              onPressed: () {
                tour.stopTour();
                _add('Tour stopped.');
              },
              child: const Text('Stop'),
            ),
            const Divider(),
            const Text('Event log'),
            Expanded(
              child: ListView.builder(
                itemCount: _log.length,
                itemBuilder: (_, i) => Text(_log[i],
                    style: Theme.of(context).textTheme.bodySmall),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
```

> If `context.read<TourPlaybackService>()` throws (not provided in the widget tree), confirm `main.dart:71` registers it with `ChangeNotifierProvider.value` above `MaterialApp.router` — it does. No change expected.

- [ ] **Step 3: Add the debug route**

In `mobile/lib/router.dart`, add the import near the existing spike import (line ~15):

```dart
import 'package:ondoway/spike/tour_playback_proof_page.dart';
```

Add a `GoRoute` next to the existing `/debug/location-spike` route (line ~126):

```dart
      GoRoute(
        path: '/debug/tour-playback-proof',
        builder: (context, state) => const TourPlaybackProofPage(),
      ),
```

`allowDebugRoutes: !kReleaseMode` (line ~69) already gates all `/debug/*` routes.

- [ ] **Step 4: Static-analyze + full suite (AC5)**

Run: `make flutter-analyze` → expect clean.
Run: `make flutter-test` → expect all green, **0 skipped**.

- [ ] **Step 5: Build to device (AOT profile)**

Run: `make flutter-device-profile`
On the phone, navigate to the proof screen (route `/debug/tour-playback-proof`).

- [ ] **Step 6: On-device proof (AC2–AC4) — capture evidence**

1. Start a podcast/music playing (for the duck check).
2. Tap **Prepare & start proof tour**.
3. **Lock the phone, pocket it.** Walk north ~15m, pause, then continue to ~30m.
4. Confirm and record (photo of the event log + a note):
   - **AC2:** stop 1's narration plays audibly **through the lock screen** at ~10m.
   - **AC3:** the podcast/music **ducks** during narration and **restores** after.
   - **AC4:** after stop 1 completes, reaching stop 2 (still locked) **auto-plays** it.

- [ ] **Step 7: Commit the harness (only after the proof)**

```bash
git add mobile/lib/spike/tour_playback_proof_page.dart mobile/lib/router.dart mobile/pubspec.yaml mobile/assets/audio/arrived.mp3
git commit -m "test(spike): on-device proof harness for locked tour-playback audio"
```

---

## Contingency (if AC2 fails on-device)

If narration is **silent when locked** even with the active session, do NOT patch blindly — the design's rejected Approach 2 becomes a follow-up:
1. Record the exact symptom (silent? errors in the log? plays only when unlocked?) and any `audio_session`/just_audio error.
2. Write a short follow-up scope for **native file-path playback** (extend the `bg_audio` channel to play a file path, route `TourPlaybackService` playback through native, bridge `isPlaying`/position/duration back to `AudioService` state).
3. This slice then ships Tasks 1–3 (the seam) + the **negative** on-device finding — no silent success.

---

## Self-Review (done by plan author)

- **Spec coverage:** AC1 → Task 2; AC2/AC3/AC4 → Task 4 Step 6; AC5 → Task 4 Step 4; native session (design §1) → Task 3; `prepareSession` seam (design §2) → Task 1; `startTour` change (design §3) → Task 2; cached-file playback (design §4) → Task 4 Steps 1–2; harness (design §5) → Task 4. Contingency AC → Contingency section. ✅
- **Placeholder scan:** none — every step has concrete code or an exact command. ✅
- **Type consistency:** `prepareSession()` signature identical in interface (Task 1.1), impl (Task 1.2), and both mocks; `startTracking(background: true)` matches `LocationProvider` signature; `ItineraryStop` constructor fields match `mobile/lib/models/trip.dart`. ✅
```
