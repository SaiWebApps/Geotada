# Slice 0.3 — iOS Background-Location Spike Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove on real iOS hardware that, with the phone pocketed and screen locked, walking within 10m of a target coordinate plays an audio clip — de-risking background location + background audio before Slice 1 depends on them.

**Architecture:** A pure-Dart `GeofenceTrigger` (Haversine distance + fire-once/re-arm) is fed by a background-capable `LocationService` (geolocator `AppleSettings`) through the existing `LocationProvider` seam. A debug-only screen captures a target, runs the trigger against background position updates, and plays a bundled clip on fire. iOS `UIBackgroundModes` enables both `location` (keeps updates flowing while locked) and `audio` (lets the clip play from the background window).

**Tech Stack:** Flutter, Dart, geolocator ^13.0.2, just_audio ^0.9.40, go_router, provider.

## Global Constraints

- Flutter, **extend the existing app** — iOS-first (this is Slice 0.3).
- Packages already in `pubspec.yaml`: `geolocator: ^13.0.2`, `just_audio: ^0.9.40`. Add no new packages.
- The `LocationProvider` seam change MUST be **backward compatible** — an optional named param, existing foreground callers unchanged.
- Permission: request **WhenInUse only**. Do NOT request "Always".
- Geofence: **10m** fire radius, **20m** re-arm radius (hysteresis absorbs GPS jitter).
- The spike screen is **debug-only** — reached via a `kDebugMode`-gated entry, never production navigation.
- `UIBackgroundModes` in Info.plist must contain **both** `location` and `audio`.
- No hardcoded colors — use `Theme.of(context).colorScheme.*` (project rule).
- Run everything through **make targets**: `make flutter-test`, `make flutter-analyze`, `make flutter-device`. Never raw `flutter test`/`flutter run`. Do NOT run Flutter tests in the background.
- Commit after each task.

---

## File Structure

- **Create** `mobile/lib/spike/geofence_trigger.dart` — pure Haversine + fire-once/re-arm. No Flutter/plugin imports.
- **Create** `mobile/test/spike/geofence_trigger_test.dart` — unit tests for the above.
- **Modify** `mobile/lib/services/providers.dart` — `startTracking` gains `{bool background = false}`.
- **Modify** `mobile/lib/services/location_service.dart` — honor `background` via `AppleSettings`.
- **Modify** `mobile/ios/Runner/Info.plist` — add `UIBackgroundModes`.
- **Create** `mobile/assets/audio/arrived.m4a` — the trigger clip. **Modify** `mobile/pubspec.yaml` assets.
- **Create** `mobile/lib/spike/location_spike_page.dart` — the debug screen.
- **Modify** `mobile/lib/router.dart` — add `/debug/location-spike`.
- **Modify** `mobile/lib/pages/login_page.dart` — add a `kDebugMode`-gated button to reach the spike.

---

### Task 1: Geofence trigger logic (pure Dart, TDD)

**Files:**
- Create: `mobile/lib/spike/geofence_trigger.dart`
- Test: `mobile/test/spike/geofence_trigger_test.dart`

**Interfaces:**
- Produces: `double haversineMeters(double lat1, double lng1, double lat2, double lng2)`; `class GeofenceTrigger({required double targetLat, required double targetLng, double radiusMeters = 10.0, double reArmMeters = 20.0})` with `double distanceTo(double lat, double lng)` and `bool update(double lat, double lng)` (returns true only on the armed entry crossing).

- [ ] **Step 1: Write the failing test**

Create `mobile/test/spike/geofence_trigger_test.dart`:

```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:ondoway/spike/geofence_trigger.dart';

void main() {
  group('haversineMeters', () {
    test('is zero for identical points', () {
      expect(haversineMeters(48.8566, 2.3522, 48.8566, 2.3522), closeTo(0, 0.001));
    });

    test('~111.19m per 0.001 degree of latitude', () {
      final d = haversineMeters(48.8566, 2.3522, 48.8576, 2.3522);
      expect(d, closeTo(111.19, 1.0));
    });
  });

  group('GeofenceTrigger', () {
    const lat = 48.8530;
    const lng = 2.3499;

    test('fires once on entering the radius', () {
      final t = GeofenceTrigger(targetLat: lat, targetLng: lng);
      expect(t.update(lat + 0.001, lng), isFalse); // ~111m out
      expect(t.update(lat, lng), isTrue); // at target
    });

    test('does not re-fire while still inside', () {
      final t = GeofenceTrigger(targetLat: lat, targetLng: lng);
      expect(t.update(lat, lng), isTrue);
      expect(t.update(lat, lng), isFalse);
      expect(t.update(lat + 0.00005, lng), isFalse); // ~5.5m jitter, still inside
    });

    test('re-arms only past reArmMeters, then fires again', () {
      final t = GeofenceTrigger(
          targetLat: lat, targetLng: lng, radiusMeters: 10, reArmMeters: 20);
      expect(t.update(lat, lng), isTrue); // fire
      expect(t.update(lat + 0.00015, lng), isFalse); // ~16.7m: between radius and reArm
      expect(t.update(lat, lng), isFalse); // back inside but NOT re-armed
      expect(t.update(lat + 0.0002, lng), isFalse); // ~22m: re-arms
      expect(t.update(lat, lng), isTrue); // fires again
    });
  });
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `make flutter-test`
Expected: FAIL — `geofence_trigger.dart` does not exist / `GeofenceTrigger` undefined.

- [ ] **Step 3: Write the minimal implementation**

Create `mobile/lib/spike/geofence_trigger.dart`:

```dart
import 'dart:math' as math;

/// Great-circle distance in meters between two lat/lng points (Haversine).
double haversineMeters(double lat1, double lng1, double lat2, double lng2) {
  const earthRadius = 6371000.0; // meters
  final dLat = _toRadians(lat2 - lat1);
  final dLng = _toRadians(lng2 - lng1);
  final a = math.sin(dLat / 2) * math.sin(dLat / 2) +
      math.cos(_toRadians(lat1)) *
          math.cos(_toRadians(lat2)) *
          math.sin(dLng / 2) *
          math.sin(dLng / 2);
  final c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a));
  return earthRadius * c;
}

double _toRadians(double degrees) => degrees * math.pi / 180.0;

/// Fires exactly once each time the device enters [radiusMeters] of the target,
/// and re-arms only after leaving [reArmMeters]. The gap between the two is
/// hysteresis: it absorbs GPS jitter around the boundary so one stop does not
/// double-fire.
class GeofenceTrigger {
  GeofenceTrigger({
    required this.targetLat,
    required this.targetLng,
    this.radiusMeters = 10.0,
    this.reArmMeters = 20.0,
  }) : assert(reArmMeters >= radiusMeters);

  final double targetLat;
  final double targetLng;
  final double radiusMeters;
  final double reArmMeters;

  bool _armed = true;

  double distanceTo(double lat, double lng) =>
      haversineMeters(targetLat, targetLng, lat, lng);

  /// Feed each new position. Returns true only on the update that crosses into
  /// the radius while armed.
  bool update(double lat, double lng) {
    final d = distanceTo(lat, lng);
    if (_armed && d <= radiusMeters) {
      _armed = false;
      return true;
    }
    if (!_armed && d >= reArmMeters) {
      _armed = true;
    }
    return false;
  }
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `make flutter-test`
Expected: PASS — all four `geofence_trigger_test.dart` tests green (and the rest of the suite unaffected).

- [ ] **Step 5: Verify no analyzer regressions**

Run: `make flutter-analyze`
Expected: "No issues found!"

- [ ] **Step 6: Commit**

```bash
git add mobile/lib/spike/geofence_trigger.dart mobile/test/spike/geofence_trigger_test.dart
git commit -m "feat(spike): geofence trigger — haversine distance + fire-once/re-arm"
```

---

### Task 2: iOS background modes (Info.plist)

**Files:**
- Modify: `mobile/ios/Runner/Info.plist`

- [ ] **Step 1: Add the `UIBackgroundModes` array**

In `mobile/ios/Runner/Info.plist`, inside the top-level `<dict>` (e.g. right after the existing `NSLocationAlwaysAndWhenInUseUsageDescription` block), add:

```xml
	<key>UIBackgroundModes</key>
	<array>
		<string>location</string>
		<string>audio</string>
	</array>
```

- [ ] **Step 2: Verify the plist is still valid and the keys are present**

Run:
```bash
plutil -lint mobile/ios/Runner/Info.plist
/usr/libexec/PlistBuddy -c "Print :UIBackgroundModes" mobile/ios/Runner/Info.plist
```
Expected: `OK` from `plutil`, and the array prints `location` and `audio`.

- [ ] **Step 3: Commit**

```bash
git add mobile/ios/Runner/Info.plist
git commit -m "feat(spike): enable iOS background location + audio modes"
```

---

### Task 3: Background-capable LocationService

**Files:**
- Modify: `mobile/lib/services/providers.dart:9`
- Modify: `mobile/lib/services/location_service.dart:79,106-116`

**Interfaces:**
- Consumes: none.
- Produces: `Future<bool> LocationProvider.startTracking({bool background = false})`. When `background` is true, `LocationService` streams with `AppleSettings(allowBackgroundLocationUpdates: true, ...)`.

- [ ] **Step 1: Widen the seam (backward compatible)**

In `mobile/lib/services/providers.dart`, change the `LocationProvider` method:

```dart
  Future<bool> startTracking({bool background = false});
```

- [ ] **Step 2: Honor `background` in the implementation**

In `mobile/lib/services/location_service.dart`, change the signature at line 79 to `Future<bool> startTracking({bool background = false}) async {` and replace the `const locationSettings = LocationSettings(...)` block (lines 106-109) with:

```dart
    final LocationSettings locationSettings = background
        ? AppleSettings(
            accuracy: LocationAccuracy.high,
            distanceFilter: 5,
            allowBackgroundLocationUpdates: true,
            pauseLocationUpdatesAutomatically: false,
            showBackgroundLocationIndicator: true,
            activityType: ActivityType.otherNavigation,
          )
        : const LocationSettings(
            accuracy: LocationAccuracy.high,
            distanceFilter: 5,
          );
```

`AppleSettings` and `ActivityType` come from geolocator. If the analyzer reports them undefined, add `import 'package:geolocator_apple/geolocator_apple.dart';` at the top (it is already a transitive dependency).

- [ ] **Step 3: Verify it compiles clean**

Run: `make flutter-analyze`
Expected: "No issues found!" (a red here means the `AppleSettings` import needs adding per Step 2.)

- [ ] **Step 4: Verify existing tests still pass**

Run: `make flutter-test`
Expected: PASS — the optional param is backward compatible; existing `LocationService`/`LocationProvider` callers and mocks are unaffected.

- [ ] **Step 5: Commit**

```bash
git add mobile/lib/services/providers.dart mobile/lib/services/location_service.dart
git commit -m "feat(spike): background-capable location tracking via AppleSettings"
```

---

### Task 4: Trigger audio asset

**Files:**
- Create: `mobile/assets/audio/arrived.m4a`
- Modify: `mobile/pubspec.yaml:20-21`

- [ ] **Step 1: Generate the clip (reproducible, macOS)**

Run:
```bash
mkdir -p mobile/assets/audio
say -o /tmp/arrived.aiff "You have arrived at the test point"
afconvert /tmp/arrived.aiff mobile/assets/audio/arrived.m4a -d aac -f m4af
```

- [ ] **Step 2: Register the asset directory**

In `mobile/pubspec.yaml`, under `flutter: assets:` (currently only `- assets/images/`), add:

```yaml
    - assets/audio/
```

- [ ] **Step 3: Resolve packages and clean the asset cache**

Run: `make flutter-clean`
Expected: completes without error (required after any asset change per project rules).

- [ ] **Step 4: Commit**

```bash
git add mobile/assets/audio/arrived.m4a mobile/pubspec.yaml
git commit -m "feat(spike): bundled trigger audio clip"
```

---

### Task 5: Debug Location Spike screen + entry

**Files:**
- Create: `mobile/lib/spike/location_spike_page.dart`
- Modify: `mobile/lib/router.dart` (add a route to the `GoRoute` list)
- Modify: `mobile/lib/pages/login_page.dart` (add a `kDebugMode`-gated button)

**Interfaces:**
- Consumes: `LocationProvider.startTracking(background: true)` and `.lastPosition` (Task 3); `GeofenceTrigger` (Task 1); `assets/audio/arrived.m4a` (Task 4).
- Produces: a `LocationSpikePage` widget reachable at `/debug/location-spike`.

- [ ] **Step 1: Create the debug screen**

Create `mobile/lib/spike/location_spike_page.dart`:

```dart
import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import 'package:just_audio/just_audio.dart';
import 'package:provider/provider.dart';
import 'package:ondoway/services/providers.dart';
import 'package:ondoway/spike/geofence_trigger.dart';

class LocationSpikePage extends StatefulWidget {
  const LocationSpikePage({super.key});

  @override
  State<LocationSpikePage> createState() => _LocationSpikePageState();
}

class _LocationSpikePageState extends State<LocationSpikePage> {
  final AudioPlayer _player = AudioPlayer();
  final List<String> _log = [];
  GeofenceTrigger? _trigger;
  LocationProvider? _location;
  bool _tracking = false;
  double? _distance;

  @override
  void initState() {
    super.initState();
    _location = context.read<LocationProvider>();
    _location!.addListener(_onLocation);
  }

  @override
  void dispose() {
    _location?.removeListener(_onLocation);
    _location?.stopTracking();
    _player.dispose();
    super.dispose();
  }

  void _add(String line) {
    setState(() => _log.insert(0, line));
  }

  Future<void> _setTarget() async {
    final pos = _location!.lastPosition as Position?;
    if (pos == null) {
      _add('No position yet — start tracking first, then set target.');
      return;
    }
    _trigger = GeofenceTrigger(targetLat: pos.latitude, targetLng: pos.longitude);
    _add('Target set: ${pos.latitude.toStringAsFixed(6)}, '
        '${pos.longitude.toStringAsFixed(6)}');
  }

  Future<void> _start() async {
    final ok = await _location!.startTracking(background: true);
    setState(() => _tracking = ok);
    _add(ok ? 'Background tracking started.' : 'Tracking failed to start.');
  }

  void _onLocation() {
    final pos = _location!.lastPosition as Position?;
    if (pos == null) return;
    final t = _trigger;
    final now = TimeOfDay.now();
    final stamp = '${now.hour}:${now.minute.toString().padLeft(2, '0')}';
    if (t == null) {
      _add('$stamp  pos ${pos.latitude.toStringAsFixed(6)},'
          '${pos.longitude.toStringAsFixed(6)} (±${pos.accuracy.toStringAsFixed(0)}m)');
      return;
    }
    final d = t.distanceTo(pos.latitude, pos.longitude);
    setState(() => _distance = d);
    _add('$stamp  ${d.toStringAsFixed(1)}m  (±${pos.accuracy.toStringAsFixed(0)}m)');
    if (t.update(pos.latitude, pos.longitude)) {
      _add('$stamp  *** FIRED at ${d.toStringAsFixed(1)}m — playing clip ***');
      _playClip();
    }
  }

  Future<void> _playClip() async {
    try {
      await _player.setAsset('assets/audio/arrived.m4a');
      await _player.play();
    } catch (e) {
      _add('Audio error: $e');
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Location Spike (debug)')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              _distance == null
                  ? 'Distance to target: —'
                  : 'Distance to target: ${_distance!.toStringAsFixed(1)} m',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: FilledButton(
                    onPressed: _tracking ? null : _start,
                    child: const Text('Start tracking'),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: OutlinedButton(
                    onPressed: _setTarget,
                    child: const Text('Set target = here'),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),
            Text('Event log', style: Theme.of(context).textTheme.labelLarge),
            const Divider(),
            Expanded(
              child: Container(
                color: scheme.surfaceContainerHighest,
                child: ListView.builder(
                  itemCount: _log.length,
                  itemBuilder: (_, i) => Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                    child: Text(_log[i],
                        style: Theme.of(context).textTheme.bodySmall),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
```

- [ ] **Step 2: Register the route**

In `mobile/lib/router.dart`, add to the top-level `routes:` list (alongside the other `GoRoute`s near line 45) — add the import `import 'package:ondoway/spike/location_spike_page.dart';` at the top of the file, then:

```dart
      GoRoute(
        path: '/debug/location-spike',
        builder: (context, state) => const LocationSpikePage(),
      ),
```

- [ ] **Step 3: Add a debug-only entry from the login screen**

`mobile/lib/pages/login_page.dart` already imports `flutter/foundation.dart` (`kDebugMode`) and `go_router` (`context.push`), and its `build` returns a `Scaffold(` at line 49 with a `body:` but no `floatingActionButton`. Add a debug-only FAB as the first argument to that `Scaffold` — exact and structure-independent:

```dart
    return Scaffold(
      floatingActionButton: kDebugMode
          ? FloatingActionButton.extended(
              onPressed: () => context.push('/debug/location-spike'),
              icon: const Icon(Icons.explore),
              label: const Text('Location Spike'),
            )
          : null,
      body: SafeArea(
```

(The `body: SafeArea(` line shown is the existing next line — insert the `floatingActionButton:` block immediately after `return Scaffold(`.)

- [ ] **Step 4: Verify it compiles clean**

Run: `make flutter-analyze`
Expected: "No issues found!"

- [ ] **Step 5: Commit**

```bash
git add mobile/lib/spike/location_spike_page.dart mobile/lib/router.dart mobile/lib/pages/login_page.dart
git commit -m "feat(spike): debug location-spike screen + kDebugMode entry"
```

---

### Task 6: On-device acceptance (the hardware gate)

This task has **no unit test** — it is the manual proof the whole spike exists for. It produces evidence, not a commit.

- [ ] **Step 1: Build to your device**

Run: `make flutter-device`
Expected: the app installs and launches on your iPhone (bundle `com.ondoway.app.adam`). Points at prod — fine, the spike screen needs no API.

- [ ] **Step 2: Open the spike + grant permission**

On the login screen tap the **Location Spike** debug FAB → tap **Start tracking** → grant location **"While Using"** when prompted. Confirm the event log starts showing `pos …` rows and the blue location pill appears.

- [ ] **Step 3: Set target + verify foreground firing first**

Tap **Set target = here**. Walk ~30–50m away and back with the screen ON. Confirm: the distance readout updates, and the clip plays (and log shows `*** FIRED ***`) when you re-enter 10m. This isolates a foreground failure from a background one.

- [ ] **Step 4: The real gate — pocketed + screen-locked**

Tap **Set target = here** again at a spot. **Lock the screen and put the phone in your pocket.** Walk ~30–50m away and back. Expected: **the clip plays out loud** on re-entry, screen still locked.

- [ ] **Step 5: Reproduce + capture evidence**

Repeat Step 4 a second time. Capture proof: a screen-recording/photo of the event log afterward showing background `pos …` rows with advancing timestamps during the locked window (accept. criterion #3) and two `*** FIRED ***` rows (criterion #4).

- [ ] **Step 6: Verdict**

If the clip fired both times while pocketed/locked: the spike is PROVEN — background location + background audio both work on this hardware. Record the outcome (and any battery/accuracy observations) in `specs/2026-08-07-bg-location-spike/design.md` under a new "## Result" section, then report to the user for the acceptance gate. If it did NOT fire pocketed: STOP and diagnose (permission level, `allowBackgroundLocationUpdates`, `UIBackgroundModes`, audio-session category) before claiming anything.
