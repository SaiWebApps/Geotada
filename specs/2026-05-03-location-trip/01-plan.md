# Location-Aware Trip Generation

## Problem
Trip generation currently uses hardcoded city-center coordinates. Beta testers should be able to generate a trip centered on where they actually are, and update an existing trip when they've moved to a new spot.

## Scope
1. Add `geolocator` package for device location (while-in-use permission only)
2. Create a `LocationService` following existing service pattern
3. Modify `TripDurationPage` to use device location instead of hardcoded city center (with fallback)
4. Add an "Update trip from here" button on `TripItineraryPage`

## Out of scope
- Always-on location tracking (Phase 2, for GPS-triggered audio)
- Background location updates
- Backend changes (the API already accepts lat/lng)

## Implementation Plan

### Step 1: Add dependency
**File:** `mobile/pubspec.yaml`
- Add `geolocator: ^13.0.2`

### Step 2: Create LocationService
**New file:** `mobile/lib/services/location_service.dart`
- Extends `ChangeNotifier` (same pattern as TripService, AuthService)
- `getCurrentPosition()` method:
  - Checks if location services enabled
  - Requests while-in-use permission if needed
  - Returns `Position` or null with error message
  - 10-second timeout to prevent simulator hang
- Distinguishes `denied` vs `deniedForever` (iOS doesn't re-prompt after denial)

### Step 3: Register in main.dart
**File:** `mobile/lib/main.dart`
- Add `LocationService` to MultiProvider

### Step 4: Modify TripDurationPage
**File:** `mobile/lib/pages/trip_duration_page.dart`
- In `_generateTrip()`: try device location first, fall back to city center coords
- Show brief note when falling back

### Step 5: Add "Update trip from here" button
**File:** `mobile/lib/pages/trip_itinerary_page.dart`
- `OutlinedButton.icon` with `Icons.my_location` below the summary card
- Re-calls `tripService.generateTrip()` with current lat/lng
- Shows snackbar error if location unavailable
- Uses `context.pushReplacement` to show new trip

### Step 6: iOS Info.plist — no change needed
Already contains `NSLocationWhenInUseUsageDescription` (line 41-42).

## Test Strategy
- **LocationService unit test:** Mock `GeolocatorPlatform` for happy path, denied, deniedForever, disabled
- **TripDurationPage test:** Verify device location used when available, city center fallback when denied
- **TripItineraryPage test:** Verify "Update from here" button visible, calls generateTrip with device coords
- All tests run via `make flutter-test` on headless Chrome

## Risks
- **iOS permission denial is permanent** — after first "Don't Allow", iOS returns `deniedForever`. Mitigation: show message to enable in Settings, never block trip generation.
- **Simulator needs fake location** — Xcode: Features > Location > Custom Location. Tests mock the platform.
- **No backend changes needed** — `TripGenerateRequest` already accepts `center_lat`, `center_lng`.

## Files touched
- `mobile/pubspec.yaml` (modify)
- `mobile/lib/services/location_service.dart` (new)
- `mobile/lib/main.dart` (modify)
- `mobile/lib/pages/trip_duration_page.dart` (modify)
- `mobile/lib/pages/trip_itinerary_page.dart` (modify)
- `mobile/test/services/location_service_test.dart` (new)
