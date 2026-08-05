> # ⛔ OWNER RULINGS OVERRIDE THIS DOCUMENT — READ FIRST
>
> This contract was written BEFORE the owner answered the plan's open questions on
> 2026-08-04. Where this document and the rulings below disagree, **THE RULINGS WIN.**
> The authoritative copy of each is in `../state.json` under `decisions`, keyed
> `OWNER_RULING_1..5`. Do not follow a superseded instruction because it is more
> detailed — detail is not authority.
>
> 1. **Planning shows PLACES ONLY.** During route planning, on BOTH surfaces, an option
>    shows POI names, order, walking time and ETA — and NO descriptive text whatsoever.
>    No LLM glue, no vignette prose, no teaser text, no narration. All words arrive only
>    at script generation, after a route is picked. Planning therefore makes NO paid call.
> 2. **The workbench never asks a human to log in.** Phase 2 gives it a background
>    identity it uses silently. The Phase-1 no-login route is a stopgap for that, and the
>    operator's trigger is a **"Select / Build this tour"** button on each of the three
>    option cards.
> 3. **`frontend/tour-preview.html` is DELETED**, not re-pointed. Step 13 is a deletion
>    proof.
> 4. **The build-version stamp (`resolve_build_identity`) STAYS UNCHANGED.** It is what
>    makes a tour traceable to the code that built it. The fix belongs in the test setup,
>    which must declare itself a local build via the EXISTING
>    `ONDOWAY_ALLOW_DIRTY_LOCAL_BUILD=1` opt-in, exactly as `scripts/workbench.sh` does.
>    Do not bypass, weaken or delete the check.
> 5. **No stop limits. Period.** All SEVEN ceilings go, including
>    `quality_rubric.MAX_COMPOSED_STOPS`. Consequence accepted by the owner: the C3 check
>    stops flagging long tours, and duration alone bounds tour length everywhere.
>
> Also pinned: the new route is **`POST /trips/preview/author`** (never
> `/trips/preview/compose` — that name is already taken by the authenticated saved-trip
> route). Its option selector is `route_id`, a 12-hex plan fingerprint; a stale
> fingerprint is refused `409 plan_changed` rather than authoring an unseen tour.
>
> **No section of this file is superseded.** The rulings above still bind it.

---

# Implementation contract — steps 1, 16, 17, 18

Ledger: `specs/2026-08-04-unify-tour-algorithm/state.json`. Verified against the working
tree at `a7df218c`. Every claim below carries `file:line` from a read performed in this
session. **This document is the whole specification for these four steps.** The
implementer chooses nothing.

No source file was edited while writing this. No container-touching command was run.

---

## 0. Ledger corrections you must apply before running these steps

### 0.1 Step 16's `files` list names a file that does not exist

`state.json:294` lists `mobile/lib/models/generated_trip.dart`. That path does not exist.
`mobile/lib/models/` contains exactly two files — `lens.dart` and `trip.dart` (directory
listing, this session). `class GeneratedTrip` is declared at
`mobile/lib/models/trip.dart:196`, and `TripService` imports it from there
(`mobile/lib/services/trip_service.dart:4`: `import 'package:ondoway/models/trip.dart';`).

Corrected step-16 `files` array, paste verbatim:

```json
["mobile/lib/models/trip.dart", "mobile/lib/services/trip_service.dart", "mobile/lib/pages/trip_itinerary_page.dart", "mobile/test/services/trip_service_test.dart", "mobile/test/pages/trip_itinerary_page_test.dart", "tests/test_no_doubles_on_human_surfaces.py"]
```

Two changes from the ledger: `generated_trip.dart` → `trip.dart` (the model actually
lives there), and `mobile/test/pages/trip_itinerary_page_test.dart` is ADDED, because
step 16 adds a rendered widget to `trip_itinerary_page.dart` and that is the file whose
widget tests cover that page.

### 0.2 Step 1 must also touch a file the ledger does not list

`mobile/test/pages/trip_itinerary_page_test.dart:64` contains the comment `/// in
beat_audio_player_test.dart.` — a cross-reference to a file step 1 deletes. Leaving it
is a doc that contradicts the code. Step 1 must edit that comment (§1.6). Add
`mobile/test/pages/trip_itinerary_page_test.dart` to step 1's `files`:

```json
["mobile/lib/widgets/beat_audio_player.dart", "mobile/lib/services/trip_service.dart", "mobile/test/widgets/beat_audio_player_test.dart", "mobile/test/services/trip_service_test.dart", "mobile/test/pages/trip_itinerary_page_test.dart", "tests/test_tour_one_engine.py"]
```

### 0.3 Step 17 must also touch a file the ledger does not list

Step 17's `files` (`state.json:309`) is right as far as it goes, but the file-level
docstring of `tests/test_audio_route_hardening.py:14-16` states the preview cap as a
live defence, and `tests/test_workbench_matches_the_app.py:59` and `:1411`/`:1425-1426`
name `AUDIO_PREVIEW_MAX_CHARS` in prose. Both files are already in step 17's list, so no
JSON change is needed — but §17.5 pins the exact prose edits, which are mandatory, not
optional.

### 0.4 Exists-today check on all four proving tests

Grep across `tests/` for each node id, this session:

| Step | Node id | Exists today? |
|---|---|---|
| 1 | `tests/test_tour_one_engine.py::test_the_unreferenced_mobile_audio_surfaces_are_gone` | **No** — zero hits for the function name anywhere under `tests/`. The file exists (`tests/test_tour_one_engine.py`, 41050 bytes). |
| 16 | `tests/test_no_doubles_on_human_surfaces.py::test_the_app_shows_what_degraded_rather_than_dropping_it` | **No** — zero hits. The file exists and holds exactly two tests today (`:68`, `:145`). |
| 17 | `tests/test_audio_route_hardening.py::TestPreviewSpendBounds::test_preview_voices_the_whole_narration_uncapped` | **No** — the method does not exist; the class does (`tests/test_audio_route_hardening.py:177`). |
| 18 | `tests/test_audio_stop_trip_api.py::TestGenerateTripStopAudio::test_edited_narration_invalidates_its_stop_audio` | **No** — the method does not exist; the class does (`tests/test_audio_stop_trip_api.py:131`). |

None of the four is a pre-existing green test. All four are genuine red-first proofs.

---

# STEP 1 — delete the two unreferenced mobile audio surfaces

**What it is in one sentence:** an audio player widget that no screen ever puts on the
page, and a service method that calls a server endpoint nobody calls, both deleted along
with the tests that are their only users.

## 1.1 Exact deletion list, with the search that proves no surviving caller

### D1 — whole file `mobile/lib/widgets/beat_audio_player.dart` (232 lines)

Deleted symbols, all declared in that file and nowhere else:

| Symbol | Declared at | Kind |
|---|---|---|
| `BeatAudioPlayer` | `mobile/lib/widgets/beat_audio_player.dart:15` | `class BeatAudioPlayer extends StatefulWidget` |
| `BeatAudioPlayer` unnamed constructor | `:20-25` | `const BeatAudioPlayer({super.key, required String beatId, String? audioUrl, double? durationSec})` |
| `BeatAudioPlayer.beatId` / `.audioUrl` / `.durationSec` | `:16`, `:17`, `:18` | `final String beatId;` · `final String? audioUrl;` · `final double? durationSec;` |
| `BeatAudioPlayer.createState` | `:27-28` | `@override State<BeatAudioPlayer> createState() => _BeatAudioPlayerState();` |
| `_BeatAudioPlayerState` | `:31` | `class _BeatAudioPlayerState extends State<BeatAudioPlayer>` |
| `_BeatAudioPlayerState._baseUrl` | `:32-35` | `static const _baseUrl = String.fromEnvironment('API_BASE_URL', defaultValue: 'http://localhost:8000/api/v1');` |
| `_BeatAudioPlayerState._triggerGeneration` | `:57` | `Future<void> _triggerGeneration() async` |
| `_BeatAudioPlayerState._startPolling` | `:72` | `void _startPolling()` |
| `_BeatAudioPlayerState._formatDuration` | `:97` | `String _formatDuration(double? seconds)` |
| `_BeatAudioPlayerState.build` | `:105-114` | `@override Widget build(BuildContext context)` |
| `_BeatAudioPlayerState._buildGenerateButton` | `:116` | `Widget _buildGenerateButton(ColorScheme colorScheme)` |
| `_BeatAudioPlayerState._buildPlayerControls` | `:151` | `Widget _buildPlayerControls(ColorScheme colorScheme)` |

Imports removed with the file: `dart:async` (`:1`), `dart:convert` (`:2`),
`package:flutter/material.dart` (`:4`), `package:http/http.dart as http` (`:5`),
`package:provider/provider.dart` (`:6`), `package:ondoway/services/audio_service.dart`
(`:8`). No `export` directive anywhere in `mobile/lib` names this file.

**Proof of no surviving caller.** `grep -rn "BeatAudioPlayer\|beat_audio_player" mobile/
tests/ src/ scripts/` returns 13 lines and only 13. Twelve are inside the two files being
deleted (`mobile/lib/widgets/beat_audio_player.dart:15,20,28,31` and
`mobile/test/widgets/beat_audio_player_test.dart:6,53,57,72,91,113,133,151,166`). The
thirteenth is the prose comment `mobile/test/pages/trip_itinerary_page_test.dart:64`,
handled in §1.6. **No file under `mobile/lib` other than the widget itself mentions it.**

### D2 — `TripService.confirmTripAudio`, `mobile/lib/services/trip_service.dart:139-163`

Delete lines 139 through 163 inclusive — the four doc-comment lines and the method.
Current text, quoted verbatim from `mobile/lib/services/trip_service.dart:139-163`:

```dart
  /// POST /audio/generate-trip/{tripId} — trigger backend audio generation.
  ///
  /// Returns the generation response with counts of generated/skipped/failed.
  Future<Map<String, dynamic>> confirmTripAudio(
    String tripId,
    String accessToken,
  ) async {
    final response = await _httpClient.post(
      Uri.parse('$baseUrl/audio/generate-trip/$tripId'),
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer $accessToken',
      },
    );

    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    } else if (response.statusCode == 404) {
      throw TripServiceException('Trip not found');
    } else {
      throw TripServiceException(
        'Audio generation failed (${response.statusCode}): ${response.body}',
      );
    }
  }

```

Deleted signature, written out: `Future<Map<String, dynamic>> confirmTripAudio(String
tripId, String accessToken)` — two positional required parameters, returns a future of a
string-keyed dynamic map. No named parameters, no defaults.

**Nothing else in `trip_service.dart` is touched.** No import becomes unused:
`dart:convert` is still used at `:70`, `:112`, `:213`, `:217`, `:263`, `:267`, `:304`,
`:315`; `http` at `:3`/`:12`; `foundation` for `ChangeNotifier` at `:6`; the trip model
at `:4`.

**Proof of no surviving caller.** `grep -rn "confirmTripAudio" .` (excluding `.git` and
`build`) returns 9 lines. Four are spec prose (`00-brief.md:140`, `state.json:41`,
`run-context.md:115`, `ondoway-one-engine-handoff.md:128`). Two are the declaration and
one doc cross-reference inside `trip_service.dart` itself (`:142`, `:168`). Three are the
tests deleted in D4 (`mobile/test/services/trip_service_test.dart:276`, `:303`, `:319`,
plus their call sites `:295`, `:314`, `:327`). **No page, widget or service under
`mobile/lib` calls it.**

### D3 — whole file `mobile/test/widgets/beat_audio_player_test.dart` (177 lines)

Deleted with D1, because it is the widget's only consumer. Deleted symbols:
`_wrap` (`:8`), `_FakeAudioService` (`:25`, a local double that subclasses `AudioService`
and overrides `currentBeatId`/`isPlaying`/`play`), `main` (`:52`), and the seven
`testWidgets` cases at `:54`, `:69`, `:85`, `:106`, `:125`, `:147`, `:163`.

The `_FakeAudioService` in this file is NOT shared: `mobile/test/pages/trip_itinerary_page_test.dart:64-66`
declares its own class of the same name with a different constructor
(`_FakeAudioService({required super.httpClient})`). Deleting one does not break the other.

### D4 — three tests inside `mobile/test/services/trip_service_test.dart`

Delete lines 276 through 331 inclusive (the three `test(...)` blocks plus the blank line
that separates the last one from the next test). By name and current line:

| Test name | Line |
|---|---|
| `'confirmTripAudio sends POST to audio generate-trip endpoint'` | `:276` |
| `'confirmTripAudio throws on 404'` | `:303` |
| `'confirmTripAudio throws on 500'` | `:319` |

The very next test in the file, `'confirmTripStopAudio POSTs to the per-STOP generate
endpoint'` (`:332`), **stays** — it exercises the LIVE per-stop method
(`trip_service.dart:171`). The three `confirmTripStopAudio` tests at `:332`, `:361`,
`:374` all stay. So do every `composeTrip` and `generateDeeperDiveAudio` test.

No import in this file becomes unused after the deletion: `jsonEncode`/`jsonDecode`
(`:1`) are used at `:57` and elsewhere, `MockClient` (`:4`) throughout, `GeneratedTrip`
(`:5`) at `:232`/`:242`, `TripService` (`:6`) throughout.

## 1.2 The near-neighbours that are LIVE and must NOT be touched

The brief flags these at `00-brief.md:144-147`. Confirmed in the tree this session:

- **`/audio/generate-trip/{trip_id}` the SERVER endpoint** — `src/api/routes/audio.py:658`.
  Only the Dart *client wrapper* is dead. The endpoint has Python tests at
  `tests/test_audio_trip_api.py:119,152,158,170`, `tests/test_audio_route_hardening.py:387,405`
  and `tests/test_audio_stop_trip_api.py:467`. **Do not delete the route.**
- **`/audio/compare`, `/audio/eval`, `/audio/generate-batch`** — tested at
  `tests/test_audio_route_hardening.py:74`, `:80-83`, `:137-142`. Untouched by this step.
- **`checkAudioStatus`** — live inside the itinerary page's readiness poll at
  `mobile/lib/pages/trip_itinerary_page.dart:324` (called as
  `audioService.checkAudioStatus(TripService.baseUrl, stop.beatId)` in the legacy-stop
  fallback branch). It is a method on `AudioService`, not on `TripService`, and this step
  does not open `audio_service.dart` at all.

## 1.3 Call-site rewrites

**There are none.** Both deleted surfaces have zero call sites outside the tests removed
with them. That is the whole point of the step.

## 1.4 Signatures added

None. Step 1 is pure deletion plus the new proving test (§1.5) and one comment fix (§1.6).

## 1.5 The one proving test

**File:** `tests/test_tour_one_engine.py`
**Node id:** `test_the_unreferenced_mobile_audio_surfaces_are_gone`
**Exists today:** no.
**Command:** `make test-file FILE="tests/test_tour_one_engine.py::test_the_unreferenced_mobile_audio_surfaces_are_gone"`

Module-level, no class. Signature: `def test_the_unreferenced_mobile_audio_surfaces_are_gone() -> None:`

Stubs it builds: none — it is a filesystem-and-text sweep over the Dart tree, hermetic,
no fixtures, no database, no provider.

Assertions **in this order**:

1. **Non-vacuity first.** Collect `mobile_lib = sorted((REPO / "mobile" / "lib").rglob("*.dart"))`
   and `mobile_test = sorted((REPO / "mobile" / "test").rglob("*.dart"))`. Assert both
   lists are non-empty, with a message saying the sweep is vacuous otherwise. Without
   this, a wrong root makes every absence assertion below pass for free.
2. **The widget file is gone.** `assert not (REPO / "mobile" / "lib" / "widgets" / "beat_audio_player.dart").exists()`.
3. **Its test file is gone.** `assert not (REPO / "mobile" / "test" / "widgets" / "beat_audio_player_test.dart").exists()`.
4. **No surviving mention of the widget.** Build
   `offenders = {str(p.relative_to(REPO)): line_no for p in mobile_lib + mobile_test for line_no, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1) if "BeatAudioPlayer" in line or "beat_audio_player" in line}`
   and assert it is empty, with the offending paths in the message.
5. **No surviving mention of the service method.** The same sweep for the exact string
   `"confirmTripAudio"`, asserted empty. **The substring must be `confirmTripAudio`, not
   `confirmTrip`** — `confirmTripStopAudio` is live and contains `confirmTrip`.
   Note that `"confirmTripAudio" in "confirmTripStopAudio"` is **False**, so the plain
   substring test is safe; do not switch to a looser pattern.
6. **The live neighbours survive.** Assert `"confirmTripStopAudio" in (REPO / "mobile" /
   "lib" / "services" / "trip_service.dart").read_text(encoding="utf-8")` and
   `"checkAudioStatus" in (REPO / "mobile" / "lib" / "pages" / "trip_itinerary_page.dart").read_text(encoding="utf-8")`.
   This is what stops an over-eager deletion passing the test.

**THE MUTATION (one line, production side).** Restore the deleted method by adding this
single line inside the body of `TripService` in `mobile/lib/services/trip_service.dart`:

```dart
  Future<void> confirmTripAudio(String t, String a) async {}
```

Assertion 5 goes RED and names `mobile/lib/services/trip_service.dart`. Remove the line →
GREEN. (A second, equally valid mutation: `git checkout
mobile/lib/widgets/beat_audio_player.dart` turns assertion 2 RED.)

## 1.6 The comment fix

`mobile/test/pages/trip_itinerary_page_test.dart:62-64` currently reads:

```dart
/// Records play calls without booting a real just_audio engine (which never
/// completes on the headless-web runner and hangs finalize). Mirrors the fake
/// in beat_audio_player_test.dart.
```

Replace line 64 exactly:

```dart
/// completes on the headless-web runner and hangs finalize).
```

(that is: delete the trailing sentence `Mirrors the fake` … `beat_audio_player_test.dart.`
and close the sentence after `finalize).`). Assertion 4 of the proving test fails if this
is skipped, because that comment contains `beat_audio_player`.

## 1.7 Gates

`make lint` (unpiped, in full) and `make flutter-analyze`. `make flutter-test` is a
phase gate, not a per-step gate, per `run-context.md:173-178`.

---

# STEP 16 — the phone surfaces the estimated-walking-legs warning

**What it is in one sentence:** the server already reports what quietly went wrong while
building a tour, the phone currently throws that report away on parse, and after this
step the traveller sees it as a card at the top of the itinerary.

**Depends on step 15**, which adds the `degradations` field to the `/trips/generate`
response. Step 16 must not ship before that field exists on the wire.

## 16.1 The wire shape this step consumes

`TripPreviewResponse` already carries it: `src/api/models/trips.py:358` —
`degradations: list[dict] = Field(default_factory=list)`, documented at `:350-357`. Each
element is `Degradation.as_dict()` (`src/tour/degradations.py:59-67`), whose keys are
exactly `kind`, `human`, `component`, `error_type`, `error_message`, `context`. The
traveller-facing register is `human`: "Plain English, no identifiers. What the reader
actually lost." (`src/tour/degradations.py:48-49`).

`TripGenerateResponse` (`src/api/models/trips.py:150-169`) does **not** carry it today —
that is step 15's job, adding the identical field with the identical default. Step 16
assumes the same key name (`degradations`) and the same row shape.

## 16.2 Exact model change — `mobile/lib/models/trip.dart`

Current `GeneratedTrip` field block, `mobile/lib/models/trip.dart:205-208`:

```dart
  // k-flavour RouteOptions from POST /trips/generate. GET /trips never
  // returns them, so absent parses to [] (back-compat) — the flavour picker
  // only shows for a just-generated trip.
  final List<RouteOption> options;
```

**Add immediately after line 208:**

```dart
  // Everything that quietly went worse while this tour was built — most often
  // that the walking times between stops were estimated rather than measured.
  // Each entry is the plain-English sentence the backend wrote for a human to
  // read (src/tour/degradations.py's `human` register); the machine-facing
  // fields are deliberately not parsed here. Absent or empty means nothing
  // degraded, which is a statement, not a silence.
  final List<String> degradationNotices;
```

**Field contract:** name `degradationNotices`, Dart type `List<String>`, non-nullable,
constructor default `const []`, so an older payload with no key parses to an empty list
rather than throwing.

**Constructor.** Current `mobile/lib/models/trip.dart:210-220` ends:

```dart
    required this.stops,
    this.options = const [],
  });
```

Replace those three lines with:

```dart
    required this.stops,
    this.options = const [],
    this.degradationNotices = const [],
  });
```

**The exact deserialisation line.** Current `mobile/lib/models/trip.dart:235-238`:

```dart
      options: ((json['options'] as List<dynamic>?) ?? const [])
          .map((o) => RouteOption.fromJson(o as Map<String, dynamic>))
          .toList(),
    );
```

Replace with:

```dart
      options: ((json['options'] as List<dynamic>?) ?? const [])
          .map((o) => RouteOption.fromJson(o as Map<String, dynamic>))
          .toList(),
      degradationNotices: [
        for (final row in (json['degradations'] as List<dynamic>?) ?? const [])
          if (row is Map<String, dynamic> &&
              (row['human'] as String?)?.trim().isNotEmpty == true)
            (row['human'] as String).trim(),
      ],
    );
```

Null-handling, stated exhaustively: a missing `degradations` key, a JSON `null`, a
non-list value that fails the `as List<dynamic>?` cast to null, an element that is not a
map, a map with no `human` key, and a map whose `human` is empty or whitespace — every
one of those yields no entry, and none of them throws. There is no code path on which
parsing a trip response can crash because of this field.

**`toJson`.** Current `mobile/lib/models/trip.dart:249-251`:

```dart
        'stops': stops.map((s) => s.toJson()).toList(),
        'options': options.map((o) => o.toJson()).toList(),
      };
```

Replace with:

```dart
        'stops': stops.map((s) => s.toJson()).toList(),
        'options': options.map((o) => o.toJson()).toList(),
        'degradations': [
          for (final notice in degradationNotices) {'human': notice},
        ],
      };
```

(Round-trips through the app's own local save path without losing the notices.)

## 16.3 No change to `trip_service.dart`'s parse call

`mobile/lib/services/trip_service.dart:71` already reads `final trip =
GeneratedTrip.fromJson(data);`, and `:114` does the same for the saved-trips list. Both
pick up the new field automatically. **No signature in `TripService` changes.** The file
stays in step 16's `files` list only because the proving test reads it (§16.6, assertion
6) — if the implementer finds no edit is needed there, that is the correct outcome, not a
miss.

## 16.4 The exact widget that renders it

**File:** `mobile/lib/pages/trip_itinerary_page.dart`.

Current body of `_TripItineraryContentState.build`, `mobile/lib/pages/trip_itinerary_page.dart:380-384`:

```dart
      body: Column(
        children: [
          _SummaryCard(trip: widget.trip),
          if (_isPreparing || _preparationDone) _buildProgressCard(colorScheme),
          if (_prepareError != null) _buildErrorCard(colorScheme),
```

Replace with:

```dart
      body: Column(
        children: [
          _SummaryCard(trip: widget.trip),
          if (widget.trip.degradationNotices.isNotEmpty)
            _DegradationCard(notices: widget.trip.degradationNotices),
          if (_isPreparing || _preparationDone) _buildProgressCard(colorScheme),
          if (_prepareError != null) _buildErrorCard(colorScheme),
```

**New widget**, added to the same file immediately before `class _SummaryCard extends
StatelessWidget {` (currently `mobile/lib/pages/trip_itinerary_page.dart:589`):

```dart
/// Shows, above the itinerary, whatever quietly went worse while this tour was
/// built. Each notice is the backend's plain-English sentence — no identifiers,
/// nothing for the traveller to decode. It renders only when there is at least
/// one notice, so a clean tour shows nothing at all.
class _DegradationCard extends StatelessWidget {
  final List<String> notices;

  const _DegradationCard({required this.notices});

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      color: colorScheme.tertiaryContainer,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(Icons.info_outline, color: colorScheme.onTertiaryContainer),
            const SizedBox(width: 8),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  for (final notice in notices)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 4),
                      child: Text(
                        notice,
                        style: TextStyle(color: colorScheme.onTertiaryContainer),
                      ),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
```

Exact signature added: `class _DegradationCard extends StatelessWidget` with
`final List<String> notices;` and `const _DegradationCard({required List<String> notices})`.
No colour literal — every colour comes from `Theme.of(context).colorScheme.*`, matching
`_buildErrorCard` at `mobile/lib/pages/trip_itinerary_page.dart:483-486` and the project
rule in `.claude/rules/flutter-ios.md`.

## 16.5 The exact traveller-facing text

The card renders the backend's own sentence — the phone invents no wording. **The
sentence the backend must produce for the estimated-legs case, and which a traveller
reads on this card, is exactly:**

> Walking times between stops are estimates, not measured routes, so the tour may run a
> little longer or shorter than it says.

That string is the `human` value of the routing degradation row created by step 14 in
`src/tour/premium_tour.py`. It names no service, no module, no identifier, and it tells
the traveller both the fact (these are estimates) and the consequence (the timing may
drift). Step 16 does not hard-code it — the phone renders whatever `human` arrives — but
the step-16 proving test asserts the *shape* (§16.6, assertion 5) and step 14 owns the
literal.

## 16.6 The one proving test

**File:** `tests/test_no_doubles_on_human_surfaces.py`
**Node id:** `test_the_app_shows_what_degraded_rather_than_dropping_it`
**Exists today:** no.
**Command:** `make test-file FILE="tests/test_no_doubles_on_human_surfaces.py::test_the_app_shows_what_degraded_rather_than_dropping_it"`

This file is the only Python test that structurally reads Dart source
(`run-context.md:94-97`), which is why the node id belongs here. Module-level, no class:
`def test_the_app_shows_what_degraded_rather_than_dropping_it() -> None:`

Stubs: none. It reads three files off disk. Hermetic, $0, no database.

Use the file's existing conventions: `REPO` (`:35`), `MOBILE_LIB` (`:36`), and plain
substring parsing — **no regex**, per the file's own docstring at `:24-27`, and every
absence assertion must be preceded by a proof that the sweep found something.

Assertions **in this order**:

1. **Non-vacuity.** Read `model = (MOBILE_LIB / "models" / "trip.dart").read_text(encoding="utf-8")`,
   `page = (MOBILE_LIB / "pages" / "trip_itinerary_page.dart").read_text(encoding="utf-8")`,
   `service = (MOBILE_LIB / "services" / "trip_service.dart").read_text(encoding="utf-8")`.
   Assert `"class GeneratedTrip" in model` and `"class TripItineraryPage" in page` and
   `"GeneratedTrip.fromJson" in service`, with a message saying the files moved and the
   guard is vacuous. This is what would have caught the `generated_trip.dart` error in
   the ledger.
2. **The wire key is read.** `assert "json['degradations']" in model` — the phone parses
   the field rather than dropping it.
3. **The parsed value is stored.** `assert "degradationNotices" in model`.
4. **The page renders it.** `assert "degradationNotices" in page` and
   `assert "_DegradationCard" in page`.
5. **The rendered text is the human register, not the machine one.** Assert
   `"row['human']" in model`, and assert that none of `"error_type"`, `"error_message"`,
   `"component"` appears in `page` — the traveller must never be shown an exception class
   or a component name.
6. **The service still parses through the model.** `assert "GeneratedTrip.fromJson" in service`
   (already asserted in 1; restate as the closing check that the notices reach the app by
   the ordinary parse path rather than a second, private one).

**THE MUTATION (one line, production side).** In `mobile/lib/models/trip.dart`, change
the deserialisation key from the real one to a name the server never sends:

```dart
        for (final row in (json['degradationz'] as List<dynamic>?) ?? const [])
```

Assertion 2 goes RED. Restore `json['degradations']` → GREEN. (Second valid mutation:
delete the `if (widget.trip.degradationNotices.isNotEmpty) _DegradationCard(...)` line
from the page → assertion 4 RED.)

## 16.7 Flutter-side coverage that must be added in the same step

`mobile/test/services/trip_service_test.dart` — add a case inside the existing
`group('TripService', ...)`:

```dart
    test('generateTrip surfaces the degradation notices the backend reported',
        () async {
      final client = MockClient((request) async {
        final body = _sampleTripResponse();
        body['degradations'] = [
          {
            'kind': 'routing_estimated_legs',
            'human': 'Walking times between stops are estimates, not measured '
                'routes, so the tour may run a little longer or shorter than it says.',
            'component': 'plan_premium_tour',
            'error_type': '',
            'error_message': '',
            'context': <String, String>{},
          },
        ];
        return http.Response(jsonEncode(body), 201);
      });

      final service = TripService(httpClient: client);
      final trip = await service.generateTrip(
        profileId: 'profile-abc',
        centerLat: 48.8566,
        centerLng: 2.3522,
        startDate: '2026-05-04',
        endDate: '2026-05-06',
        accessToken: 'token',
      );

      expect(trip.degradationNotices, hasLength(1));
      expect(trip.degradationNotices.single, contains('estimates'));
    });

    test('a response with no degradations key parses to no notices', () async {
      final client = MockClient(
        (request) async => http.Response(jsonEncode(_sampleTripResponse()), 201),
      );
      final service = TripService(httpClient: client);
      final trip = await service.generateTrip(
        profileId: 'profile-abc',
        centerLat: 48.8566,
        centerLng: 2.3522,
        startDate: '2026-05-04',
        endDate: '2026-05-06',
        accessToken: 'token',
      );
      expect(trip.degradationNotices, isEmpty);
    });
```

`mobile/test/pages/trip_itinerary_page_test.dart` — add one `testWidgets` case that
builds a `GeneratedTrip` carrying one notice, pumps the itinerary page the way the
existing cases in that file do, and asserts `find.text(<the notice>)` finds one widget;
and a second case with an empty `degradationNotices` asserting `find.byIcon(Icons.info_outline)`
finds nothing.

## 16.8 Gates

`make lint`, `make flutter-analyze`. `make flutter-test` at the phase gate.

---

# STEP 17 — delete the character cap on the preview audio path

Owner parameter 3 (`00-brief.md:192-196`): the cap "is an abuse bound on an anonymous
paid endpoint, not a quality setting". Deleting it means the workbench judges the whole
narration instead of a truncation.

## 17.1 Exactly what is DELETED

### Del-1 — the constant and its comment, `src/api/routes/audio.py:114-118`

Current text, verbatim:

```python
# Cap on the text a single PUBLIC preview request may voice. The provider chunks
# at MAX_TTS_CHARS (4000) internally, so the old 20000 model cap meant ONE
# anonymous request fanned out into five billed calls by design. 20000 was
# chosen for the internal keep-exploring path, not this public one.
_PREVIEW_MAX_CHARS = int(os.getenv("AUDIO_PREVIEW_MAX_CHARS", "6000"))
```

All five lines deleted. With them goes the only read of the `AUDIO_PREVIEW_MAX_CHARS`
environment variable in the repository (grep: it appears nowhere else in `src/`,
`scripts/`, `frontend/` or `config/`).

### Del-2 — the call site, `src/api/routes/audio.py:304-307`

Current text, verbatim:

```python

    # Bound the per-request fan-out: the provider chunks at 4000 chars, so an
    # uncapped 20000-char body becomes five billed calls.
    text = _cap_narration(body.text, _PREVIEW_MAX_CHARS)
```

Replace those four lines (including the leading blank line at `:304`, which is a stray
double blank ruff will otherwise flag) with:

```python
    text = body.text
```

`text` stays a local name because it is used twice below — in the cache key
(`src/api/routes/audio.py:310`) and in the provider call (`:315`). Do not inline it.

### Del-3 — the docstring sentence that claims the cap, `src/api/routes/audio.py:290-298`

Current, verbatim:

```python
    """Generate a TTS audio preview from raw text. Returns audio/mpeg bytes.

    This route is deliberately anonymous — the public tour-preview page calls it
    with no credentials. Its rate limit was DELETED on 2026-07-31 by owner order,
    so the only things now bounding what an anonymous caller can spend are a text
    cap well under the model limit and a content-hash cache that stops a replayed
    payload being re-billed. This docstring ships in the OpenAPI schema; keep it
    honest.
    """
```

Replace with:

```python
    """Generate a TTS audio preview from raw text. Returns audio/mpeg bytes.

    This route is deliberately anonymous — the public tour-preview page calls it
    with no credentials. Its rate limit was DELETED on 2026-07-31 by owner order,
    and its text cap was deleted on 2026-08-04 by owner order so the workbench
    judges the whole narration rather than a truncation. The only thing now
    bounding what an anonymous caller can spend is the content-hash cache that
    stops a replayed payload being re-billed, plus the request model's own
    20000-character ceiling. A real bound belongs on the AUTHENTICATED user; the
    workbench moves onto that path in Phase 2. This docstring ships in the
    OpenAPI schema; keep it honest.
    """
```

### Del-4 — the test that pins the deleted constant

`tests/test_audio_route_hardening.py:180-201`, the whole method
`test_preview_caps_text_below_the_20000_model_limit`. It monkeypatches the constant at
`:183` (`monkeypatch.setattr(audio_routes, "_PREVIEW_MAX_CHARS", 500)`) and asserts
truncation at `:201`. It **must** be deleted in this step; leaving it turns the suite red
with an `AttributeError` on a nonexistent attribute. Its replacement is the step's
proving test (§17.4), which lives in the same class and asserts the opposite.

## 17.2 Exactly what SURVIVES — do not delete these

- **`_cap_narration`, `src/api/routes/audio.py:192-205`.** Signature unchanged:
  `def _cap_narration(text: str, max_chars: int = _KEEP_EXPLORING_MAX_CHARS) -> str:`.
  It has a second, live caller — the keep-exploring path at
  `src/api/routes/audio.py:958` (`narration = _cap_narration(narration)`), which relies
  on the default argument. Deleting the helper breaks that path.
- **`_KEEP_EXPLORING_MAX_CHARS = 20000`, `src/api/routes/audio.py:189`.** It is the
  default of the surviving helper. Untouched.
- **The in-process preview cache.** `_PREVIEW_CACHE_MAX_ENTRIES` (`:123`),
  `_preview_cache` (`:124`), `_preview_cache_lock` (`:125`), `_preview_cache_get`
  (`:143-148`), `_preview_cache_put` (`:151-158`), and the cache block at `:309-318`.
  **Your reading is correct and I confirm it:** the cache is a re-billing guard, not a
  length bound. Its own comment says so at `:120-122` — "so a replayed identical payload
  is never re-billed" — and it is keyed on the sha256 of `provider.name`, `voice_id` and
  the text (`:309-311`), which bounds *repeats*, never *size*. Removing it would
  re-introduce paid duplicate calls, which is not what parameter 3 asks for. It stays.
- **`AudioPreviewRequest.text`'s own ceiling**, `src/api/models/audio.py:13`:
  `text: str = Field(..., min_length=1, max_length=20000)`. This is a Pydantic request-
  validation bound, not the preview path's cap, and parameter 3 names only
  `_PREVIEW_MAX_CHARS` / `_cap_narration` on the preview path (`00-brief.md:192-193`).
  **It stays at 20000.** See §17.6 — this bounds the proving test's payload size.
- **`AUDIO_PREVIEW_CACHE_ENTRIES`** as an env name. Still read at `:123`.
- **The two surviving cache tests**, `tests/test_audio_route_hardening.py:203` and `:226`.

## 17.3 Every test that references the deleted constant

Grep for `_PREVIEW_MAX_CHARS` and `AUDIO_PREVIEW_MAX_CHARS` across `tests/`, this session
— four locations, all inside step 17's declared files:

| File:line | What it is | Action |
|---|---|---|
| `tests/test_audio_route_hardening.py:183` | live `monkeypatch.setattr` on the constant | deleted with the whole method (§17.1 Del-4) |
| `tests/test_audio_route_hardening.py:14-16` | file docstring, defect 4: "a 20000-char body that fans out into five billed chunk calls" | rewrite (§17.5) |
| `tests/test_workbench_matches_the_app.py:59` | prose: "caps text at `AUDIO_PREVIEW_MAX_CHARS` (6000)" | rewrite (§17.5) |
| `tests/test_workbench_matches_the_app.py:1411`, `:1425-1426` | prose in test 7's docstring and its UNDO note | rewrite (§17.5) |

**Test 7 itself (`test_the_workbench_does_not_tune_the_audio_path_behind_productions_back`,
`tests/test_workbench_matches_the_app.py:1405`) stays green with no logic change.** It
derives the steering set from `os.getenv` reads found by `ast` in the participating
modules (`:1478-1484`) and then asserts the workbench sets none of them unpinned
(`:1486-1494`). Deleting one `os.getenv` shrinks that set by one; the non-vacuity
assertion at `:1484` (`assert steering, ...`) still holds because `AUDIO_STORAGE`,
`AUDIO_STORAGE_PATH`, `AUDIO_PREVIEW_CACHE_ENTRIES`, `OPENAI_API_KEY`, `OPENAI_VOICE`,
`ELEVENLABS_*` and the compare-cache vars are all still read on that path.

## 17.4 The one proving test

**File:** `tests/test_audio_route_hardening.py`
**Node id:** `TestPreviewSpendBounds::test_preview_voices_the_whole_narration_uncapped`
**Exists today:** no (the class exists at `:177`; the method does not).
**Command:** `make test-file FILE="tests/test_audio_route_hardening.py::TestPreviewSpendBounds::test_preview_voices_the_whole_narration_uncapped"`

Signature: `def test_preview_voices_the_whole_narration_uncapped(self, prod_client) -> None:`
— it is a method on the existing `class TestPreviewSpendBounds` (`:177`) and takes the
existing `prod_client` fixture (`:57-62`), which builds a prod-shaped app with
`WORKBENCH_API_ENABLED=false`. It needs no `monkeypatch`, no database, no Neo4j marker.
The autouse `_temp_audio_storage` fixture (`:35-38`) applies as it does to every test in
the file.

Stubs it builds — one, a recording fake provider, patched in exactly as the neighbouring
tests do at `:193`, `:214`, `:236`:

```python
        seen: list[str] = []

        class _FakePaid:
            name = "openai"

            def generate(self, text, voice_id=None):
                seen.append(text)
                return b"mp3"
```

Assertions **in this order**:

1. Build the payload: `narration = ("word " * 4000)[:12000]` — 12000 characters, which is
   twice the deleted 6000 cap and inside the request model's surviving 20000 ceiling.
   Assert `len(narration) == 12000` first, so a payload that silently came out short
   cannot make the real assertion pass for free.
2. POST it: inside `with patch.object(audio_routes, "get_provider", return_value=_FakePaid()):`,
   call `prod_client.post("/api/v1/audio/preview", json={"text": narration, "provider": "openai"})`.
3. `assert resp.status_code == 200, resp.text`.
4. `assert len(seen) == 1` — the route calls the provider exactly once (the provider's own
   internal chunking at `src/audio/provider.py` is below this seam and is not this test's
   business).
5. **The load-bearing one:** `assert seen[0] == narration` — byte-for-byte, not a length
   comparison. A `>=` on length would pass on a cap set anywhere above 12000; equality
   cannot.

**THE MUTATION (one line, production side).** In `src/api/routes/audio.py`, change the
new `text = body.text` back to a capped assignment:

```python
    text = _cap_narration(body.text, 6000)
```

Assertion 5 goes RED with a 6000-vs-12000 mismatch. Restore `text = body.text` → GREEN.

## 17.5 The prose edits, exactly

**`tests/test_audio_route_hardening.py:14-16`**, currently:

```
4. /audio/preview had no cache and a 20000-char body that fans out into five
   billed chunk calls. (The rate limit this file also used to guard was DELETED
   on 2026-07-31 by owner order, along with its tests.)
```

Replace with:

```
4. /audio/preview had no cache, so a replayed identical payload was billed again.
   (The rate limit this file used to guard was DELETED on 2026-07-31 by owner
   order, along with its tests; the text cap was DELETED on 2026-08-04 by owner
   order so the workbench judges the whole narration, and the test that pinned it
   was replaced by the one that pins the opposite.)
```

**`tests/test_workbench_matches_the_app.py:58-65`**, currently opening:

```
* **THE PREVIEW ROUTE IS NOT THE TOURIST'S ROUTE.** ``ttsPlay`` POSTs to
  ``/audio/preview``, which caps text at ``AUDIO_PREVIEW_MAX_CHARS`` (6000) and
  serves from an in-process cache; the tourist's app gets audio from
  ``generate_stop_audio``, which has no cap and writes to storage. Test 7 stops
  the workbench LOWERING the cap behind production's back, but the two paths
  genuinely differ today and only an output-equality run (same narration through
  both, compare bytes and duration) would prove otherwise. That needs a live
  provider and is not a $0 check.
```

Replace the first four sentences so it reads:

```
* **THE PREVIEW ROUTE IS NOT THE TOURIST'S ROUTE.** ``ttsPlay`` POSTs to
  ``/audio/preview``, which serves from an in-process cache; the tourist's app
  gets audio from ``generate_stop_audio``, which writes to storage. Neither path
  truncates any more — the preview text cap was deleted 2026-08-04 — but the two
  paths genuinely differ today and only an output-equality run (same narration
  through both, compare bytes and duration) would prove otherwise. That needs a
  live provider and is not a $0 check.
```

**`tests/test_workbench_matches_the_app.py:1408-1413`**, currently:

```
    Test 6 compares variables production PINS. The nastier version sets one it
    does not: ``OPENAI_VOICE=alloy`` gives the owner a completely genuine, fully
    billed call to api.openai.com in a voice no tourist will ever hear, and
    ``AUDIO_PREVIEW_MAX_CHARS=800`` silently truncates every long stop. Neither
    value is a registry key, so the old "is this value a known implementation?"
    classification could never see either one.
```

Replace `AUDIO_PREVIEW_MAX_CHARS=800` with `AUDIO_PREVIEW_CACHE_ENTRIES=0`, and the
clause `silently truncates every long stop` with `silently re-bills every replayed
stop` — both remain real, currently-read env vars, so the example stays true.

**`tests/test_workbench_matches_the_app.py:1425-1426`**, currently:

```
    UNDO TEST: add OPENAI_VOICE, AUDIO_PREVIEW_MAX_CHARS or
    AUDIO_PREVIEW_CACHE_ENTRIES to scripts/workbench.sh or the profile -> RED.
```

Replace with:

```
    UNDO TEST: add OPENAI_VOICE or AUDIO_PREVIEW_CACHE_ENTRIES to
    scripts/workbench.sh or the profile -> RED.
```

## 17.6 Blast-radius summary

| | Symbol | file:line | Fate |
|---|---|---|---|
| Cap constant | `_PREVIEW_MAX_CHARS` | `src/api/routes/audio.py:118` | **deleted** |
| Its env var | `AUDIO_PREVIEW_MAX_CHARS` | same line, sole read in repo | **deleted** |
| Cap call site | `text = _cap_narration(body.text, _PREVIEW_MAX_CHARS)` | `src/api/routes/audio.py:307` | **deleted**, becomes `text = body.text` |
| Capping helper | `_cap_narration` | `src/api/routes/audio.py:192` | **stays** — keep-exploring caller at `:958` |
| Helper's default | `_KEEP_EXPLORING_MAX_CHARS` | `src/api/routes/audio.py:189` | **stays** |
| Re-billing cache | `_preview_cache*`, `_PREVIEW_CACHE_MAX_ENTRIES` | `src/api/routes/audio.py:123-158`, `:309-318` | **stays** (confirmed: guard against re-billing, not a length bound) |
| Request ceiling | `max_length=20000` | `src/api/models/audio.py:13` | **stays** |
| Pinning test | `test_preview_caps_text_below_the_20000_model_limit` | `tests/test_audio_route_hardening.py:180-201` | **deleted** |
| Cache tests | `:203`, `:226` | same file | **stay** |
| Env-tuning test 7 | `:1405` | `tests/test_workbench_matches_the_app.py` | **stays green, no logic change** |

## 17.7 Gate

`make lint`, unpiped and in full.

---

# STEP 18 — add the missing content hash to the per-stop audio path

Owner parameter 5 (`00-brief.md:219-222`): the per-stop path is the only generation path
without a content hash, so editing a stop's narration leaves the stale audio in place.

## 18.1 The digest input, taken from the path that already does this

The keep-exploring path builds its hash at `src/api/routes/audio.py:972-974`, verbatim:

```python
    narration_hash = hashlib.sha256(
        f"{provider_name or ''}\x00{voice_id or ''}\x00{narration}".encode()
    ).hexdigest()
```

**Step 18 uses exactly that digest input.**

- **Input string:** `f"{provider_name or ''}\x00{voice_id or ''}\x00{narration}"`
- **Field order:** provider name, then voice id, then narration. Never any other order.
- **Separator:** a single NUL byte, `\x00`, between each pair of fields. Two separators
  in the string, one after the provider and one after the voice.
- **`None` handling:** an unset provider or voice contributes the empty string, via
  `or ''`. It does not contribute the literal `"None"`.
- **Encoding:** `.encode()` — UTF-8, Python's default.
- **Digest:** `hashlib.sha256(...).hexdigest()`, a 64-character lowercase hex string.

Why the provider and voice are in the digest and not just the text: the same comment at
`src/api/routes/audio.py:968-971` records the defect it fixes — without them, "a client
requesting a different voice/provider silently gets audio generated with the ORIGINAL
voice." The per-stop path takes provider and voice from the same request body
(`src/api/routes/audio.py:827-828`), so it has the identical exposure.

This deliberately differs from the per-beat digest, which is text-only
(`src/audio/pipeline.py:117-119`: `hashlib.sha256(text.encode()).hexdigest()`). The
per-beat path has no per-request voice override, so it has nothing to discriminate on.
Do not copy the per-beat form here.

## 18.2 The helper added

Add to `src/api/routes/audio.py`, immediately after `_artifact_missing` ends at `:184`
and before the `_KEEP_EXPLORING_MAX_CHARS` block at `:186`:

```python
def _stop_narration_hash(
    narration: str, provider_name: str | None, voice_id: str | None
) -> str:
    """Content key for a stop's tour audio: (provider, voice, narration).

    The same digest input the keep-exploring path uses below, so the two
    staleness guards on ItineraryItem cannot drift apart. Provider and voice are
    part of the key because both are per-request overrides: without them a caller
    asking for a different voice would silently be handed audio in the old one.
    """
    return hashlib.sha256(
        f"{provider_name or ''}\x00{voice_id or ''}\x00{narration}".encode()
    ).hexdigest()
```

Exact signature: `def _stop_narration_hash(narration: str, provider_name: str | None,
voice_id: str | None) -> str:` — three positional parameters, no defaults, no keyword-only
markers, returns `str`.

Then replace the keep-exploring inline digest at `src/api/routes/audio.py:972-974` with a
call to it, so there is one implementation and not two:

```python
    narration_hash = _stop_narration_hash(narration, provider_name, voice_id)
```

(The surrounding comment block at `:964-971` stays; it explains the design and is still
accurate.) This is a behaviour-identical refactor — same digest input, same output — and
it is what makes "cannot drift" a fact rather than a hope. The existing keep-exploring
cache test `tests/test_audio_stop_trip_api.py:285` proves it still behaves.

## 18.3 The exact property name written to the graph

**`audio_script_hash`**, on the `ItineraryItem` node.

The name is not invented: `audio_script_hash` is the per-beat path's property name
(`00-brief.md:132`, implemented via `src/audio/pipeline.py:117-133`), and it sits beside
`keep_exploring_audio_hash` on the same `ItineraryItem` exactly as `audio_url` sits beside
`keep_exploring_audio_url` (`src/api/routes/audio.py:1007-1009` vs `:867-868`). There is
no collision: the two hashes are different properties covering different artifacts.

## 18.4 The exact Cypher clause that READS it

Current, `src/api/routes/audio.py:813-824`:

```python
    rows = session.run(
        """
        MATCH (t:Trip {id: $trip_id})-[:HAS_STOP]->(item:ItineraryItem)
        OPTIONAL MATCH (item)-[:AT_POI]->(poi:POI)
        RETURN item.id AS stop_id,
               item.narration AS narration,
               item.audio_url AS audio_url,
               poi.name AS poi_name
        ORDER BY item.sort_order
        """,
        trip_id=trip_id,
    )
```

Replace with:

```python
    rows = session.run(
        """
        MATCH (t:Trip {id: $trip_id})-[:HAS_STOP]->(item:ItineraryItem)
        OPTIONAL MATCH (item)-[:AT_POI]->(poi:POI)
        RETURN item.id AS stop_id,
               item.narration AS narration,
               item.audio_url AS audio_url,
               item.audio_script_hash AS audio_script_hash,
               poi.name AS poi_name
        ORDER BY item.sort_order
        """,
        trip_id=trip_id,
    )
```

One added `RETURN` term, `item.audio_script_hash AS audio_script_hash`, placed after
`audio_url` and before `poi_name`. Nothing else in the query changes. `stops = [dict(r)
for r in rows]` at `:825` picks the key up with no edit. A node that has never had the
property returns `None`.

## 18.5 The exact Cypher clause that WRITES it

Current, `src/api/routes/audio.py:866-872`:

```python
        session.run(
            "MATCH (item:ItineraryItem {id: $sid}) "
            "SET item.audio_url = $url, item.audio_duration_sec = $dur",
            sid=stop_id,
            url=gen.audio_url,
            dur=gen.duration_sec,
        )
```

Replace with:

```python
        session.run(
            "MATCH (item:ItineraryItem {id: $sid}) "
            "SET item.audio_url = $url, item.audio_duration_sec = $dur, "
            "    item.audio_script_hash = $hash",
            sid=stop_id,
            url=gen.audio_url,
            dur=gen.duration_sec,
            hash=narration_hash,
        )
```

The write happens only after `generate_stop_audio` succeeded (it is below the
`except PipelineError` `continue` at `src/api/routes/audio.py:863-865`), so a failed
generation never records a hash that would suppress the retry.

## 18.6 The exact skip condition

Current, `src/api/routes/audio.py:840-854`:

```python
        # "Has a url" is not "has audio": with AUDIO_STORAGE=local the bytes sit
        # on the container's ephemeral disk while the url persists in Neo4j, so
        # after a redeploy every stop skips here forever and the tour plays
        # silence. Treat a verifiably-missing artifact as no-audio so a plain
        # (non-force) regeneration self-heals.
        if stop["audio_url"] and not force and not _artifact_missing(stop["audio_url"]):
            results.append(
                StopAudioResultItem(
                    stop_id=stop_id,
                    status="skipped",
                    reason="already has audio",
                    audio_url=stop["audio_url"],
                )
            )
            continue
```

Replace with:

```python
        narration_hash = _stop_narration_hash(narration, provider_name, voice_id)
        # A skip needs BOTH halves to hold, and either one alone is a known bug:
        #   - url without hash: edit a stop's narration and the stale audio
        #     survives forever, which is the defect this guard closes.
        #   - hash without url: nothing has been voiced yet, so there is nothing
        #     to skip.
        # "Has a url" is also not "has audio": with AUDIO_STORAGE=local the bytes
        # sit on the container's ephemeral disk while the url persists in Neo4j,
        # so after a redeploy every stop would skip here forever and the tour
        # plays silence. Treat a verifiably-missing artifact as no-audio so a
        # plain (non-force) regeneration self-heals.
        if (
            stop["audio_url"]
            and stop["audio_script_hash"] == narration_hash
            and not force
            and not _artifact_missing(stop["audio_url"])
        ):
            results.append(
                StopAudioResultItem(
                    stop_id=stop_id,
                    status="skipped",
                    reason="already has audio",
                    audio_url=stop["audio_url"],
                )
            )
            continue
```

**The skip condition is "url exists AND hash matches", never either alone** — both terms
are conjuncts of the same `if`, and the `force` and artifact-existence terms are ANDed
alongside them, not substituted for them.

`narration_hash` must be computed at that point and not earlier: it is the first line
after the empty-narration guard at `src/api/routes/audio.py:835-839`, so `narration` is
known non-empty, and `provider_name`/`voice_id` are already resolved above the loop at
`:827-828`. The same local is then used by the write at §18.5, inside the same loop
iteration.

The `reason` string stays exactly `"already has audio"` — AC-26 pins that wording, and
`StopAudioResultItem.reason` is a free-form `str | None` (`src/api/models/audio.py:166`).

## 18.7 How the existing self-heal keeps working, and the proof it still fires

The self-heal is the `not _artifact_missing(stop["audio_url"])` term
(`src/api/routes/audio.py:845`, helper at `:161-184`). It survives **verbatim** — the
edit above adds a conjunct and reorders none of the existing ones.

Mechanically: when the local artifact is gone, `_artifact_missing` returns `True`
(`src/api/routes/audio.py:182`, `return not storage.exists(key)`), so
`not _artifact_missing(...)` is `False`, so the whole `and` chain is `False` regardless of
the new hash term, so the code falls through to `generate_stop_audio` and re-voices. The
new conjunct can only ever make the condition *more* likely to be `False`, i.e. more
likely to regenerate — it can never suppress a regeneration the old code would have done.
That is a property of `and`, and it is why this ordering is safe.

Proof it still fires, required in this step:

- The three existing unit tests of the helper stay untouched and green:
  `tests/test_audio_route_hardening.py:310`, `:313`, `:317-324`.
- **End-to-end proof, which does not exist today and must be added:** phase 3 of the
  step-18 proving test (§18.8, assertions 8-10) deletes the artifact off disk while
  leaving the row's `audio_url` and its now-current `audio_script_hash` in place, and
  asserts the stop regenerates. Without that phase, nothing anywhere proves the self-heal
  survives contact with the new hash term — the existing coverage tests
  `_artifact_missing` in isolation, never through the endpoint.

## 18.8 The one proving test

**File:** `tests/test_audio_stop_trip_api.py`
**Node id:** `TestGenerateTripStopAudio::test_edited_narration_invalidates_its_stop_audio`
**Exists today:** no (the class exists at `:131`; the method does not).
**Command:** `make test-file FILE="tests/test_audio_stop_trip_api.py::TestGenerateTripStopAudio::test_edited_narration_invalidates_its_stop_audio"`

Signature: `def test_edited_narration_invalidates_its_stop_audio(self, client, clean_driver,
_temp_audio_storage) -> None:` — a method on the existing `@needs_neo4j class
TestGenerateTripStopAudio` (`:130-131`), taking the same three fixtures its neighbours
take (`:132-134`). It uses the module's `_seed` helper (`:54-88`), its `_Recorder` stub
(`:32-44`), its `_item_audio` reader (`:120-127`), and the constants `TRIP_ID` (`:19`),
`N1` (`:20`) and `N2` (`:21`).

Stubs it builds: one `_Recorder()` per call phase, patched exactly as the neighbours do —
`with patch("src.audio.pipeline.get_provider", return_value=recorder):`
(`tests/test_audio_stop_trip_api.py:137`). No network, no paid provider; the recorder
returns a real silent WAV from `MockTTSProvider` (`:44`).

Assertions **in this order**:

*Phase 1 — establish the baseline.*
1. `_seed(clean_driver)`, then POST `/api/v1/audio/generate-trip-stops/{TRIP_ID}` with
   `{"provider": "mock"}` under a first `_Recorder`. Assert `resp.status_code == 200` and
   `resp.json()["generated"] == 2` — the same shape the neighbouring test asserts at
   `:145`, so a broken seed cannot make the rest pass vacuously.
2. Assert the hash was actually written: read
   `MATCH (i:ItineraryItem {id: $sid}) RETURN i.audio_script_hash AS h` for
   `f"{TRIP_ID}-item1"` and assert the value is a 64-character string. **This is the
   assertion that fails first if the write clause was forgotten.**

*Phase 2 — edit one stop's narration, leave the other alone.*
3. Run `MATCH (i:ItineraryItem {id: $sid}) SET i.narration = $n` for `f"{TRIP_ID}-item1"`
   with a new text, e.g. `"Settle in. Welcome to the Eiffel Tower, rewritten."`. Do not
   touch `audio_url`, `audio_script_hash`, or item2.
4. POST the same endpoint again with a second `_Recorder`, **no `force`**. Assert 200.
5. **AC-25:** `data["generated"] == 1` and the one generated result's `stop_id` is
   `f"{TRIP_ID}-item1"` — the edited stop re-voiced.
6. **AC-26:** `data["skipped"] == 2` and the result for `f"{TRIP_ID}-item2"` has
   `status == "skipped"` and `reason == "already has audio"` — the untouched stop did not.
7. **The provider-call proof, load-bearing:** `recorder2.texts == ["Settle in. Welcome to
   the Eiffel Tower, rewritten."]` — exactly one TTS call, carrying exactly the new text.
   `N2` must not appear. A count-only assertion would pass if the wrong stop regenerated.

*Phase 3 — the self-heal still fires (§18.7).*
8. Read item2's `audio_url`, map it to its path under `_temp_audio_storage` by stripping
   the `/api/v1/audio/files/` prefix (`src/api/routes/audio.py:140`), and `unlink()` the
   file. Assert the file no longer exists before proceeding, so a wrong path cannot make
   the next assertion pass by accident.
9. POST again with a third `_Recorder`, no `force`. Assert 200.
10. Assert item2's result `status == "generated"` and that `recorder3.texts == [N2]` —
    the stop whose bytes vanished re-voiced even though its stored hash was current.
    This is the assertion that a naive "hash matches → skip" rewrite would fail.

**THE MUTATION (one line, production side).** In `src/api/routes/audio.py`, drop the hash
conjunct from the skip condition — change

```python
            and stop["audio_script_hash"] == narration_hash
```

to

```python
            and True
```

Assertion 5 goes RED (`generated == 0`, not `1`) and assertion 7 goes RED (`recorder2.texts
== []`). Restore the conjunct → GREEN.

*Second, independent mutation, for the self-heal half:* delete
`and not _artifact_missing(stop["audio_url"])` → assertion 10 goes RED.

## 18.9 The neighbouring tests, and why they stay green

- `tests/test_audio_stop_trip_api.py:132` `test_generates_one_artifact_per_stop_from_narration`
  — first call on fresh rows; no stored hash, so nothing skips. Unaffected.
- `tests/test_audio_stop_trip_api.py:162` `test_second_call_skips_existing` — the first
  call now writes the hash, the second computes the same hash from the same narration,
  same provider (`"mock"` in both bodies) and same voice (absent in both), so it still
  reports `generated == 0`, `skipped == 3`. **Unaffected — but only because provider and
  voice are identical across the two calls, which they are (`:166` and `:172` post the
  same body).**
- `tests/test_audio_stop_trip_api.py:285` `test_second_call_returns_cached_url_no_retts` —
  keep-exploring; the §18.2 refactor is digest-identical, so it stays green and is itself
  the proof that the refactor did not change behaviour.

## 18.10 Consequence worth stating, not a blocker

Rows written before this ships have no `audio_script_hash`, so `None == narration_hash` is
`False` and the first non-force call after deploy re-voices every existing stop once. That
is a paid one-time re-voice on production data. It is the same contract the per-beat path
already has (`src/audio/pipeline.py:131-133`: "no hash was ever stored (legacy audio
predating the hash feature)" is treated as stale), and AC-26 speaks only of a stop "whose
stored hash is current", so the acceptance criteria already assume this. **Recommendation:
accept it, and say so out loud at the close checkpoint** so nobody is surprised by the
bill. Do not add a "no hash means fresh" escape — that is precisely the silent-staleness
shape this step exists to remove.

## 18.11 Gate

`make lint`, unpiped and in full.

---

# BLOCKING AMBIGUITY

**One, and it is small.** §16.5 fixes the traveller-facing sentence for the estimated-legs
degradation, but the literal string is written by **step 14** in `src/tour/premium_tour.py`
(ledger `state.json:258-272`), not by step 16. If step 14's implementer writes a different
sentence, step 16 still works — the phone renders whatever `human` arrives — but the
wording the traveller reads will be step 14's, not the one specified here.

**Recommendation:** treat the sentence in §16.5 as the owner-facing wording and have
step 14 use it verbatim. It states the fact and the consequence, names no service and no
module, and reads at the level `src/tour/degradations.py:48-49` requires. If the owner
prefers different words, changing them is a one-line edit in step 14 and needs no change
to step 16 at all.

Nothing else in these four steps requires an owner decision.
