# `flutter test --platform chrome` hangs with no verdict — measured cause

**Date:** 2026-08-28
**Environment:** macOS 15 (Darwin 25.5.0, arm64), Flutter 3.41.9 stable (framework
`00b0c91f06`, Dart 3.11.5), Chrome for Testing 145.0.7632.6 (Playwright `chromium-1208`),
`mobile/` with 28 test files / 283 tests.
**Runner:** `scripts/flutter_test.sh`.

## Summary

`flutter test --platform chrome` intermittently stops mid-run and never exits. Every
process involved goes to **0% CPU** — it is a deadlock, not a spin — and no pass/fail
marker is ever printed.

Measured base rate on an otherwise idle machine: **1 stall in 27 consecutive runs**
(26 × PASS at 29–32s, then one run that produced nothing for 300s and was still alive
14 minutes later).

The stall was caught live and interrogated through Chrome's own DevTools protocol before
being killed. The findings below are from that specimen, not from inference.

## What the runner used to say, and why it was wrong

The old header in `scripts/flutter_test.sh` called this a "flutter_tools finalize flake",
cited a stack in `_startTest.finalize` / `FlutterTesterTestDevice.kill` /
`PathNotFoundException`, and asserted it "cannot be patched at the SDK level". Three
claims, all testable, all false:

| Claim | Finding |
| --- | --- |
| The cited stack is the cause | Those symbols live in `flutter_platform.dart` and `flutter_tester_device.dart`, which are the **VM-platform** sources. `--platform chrome` runs `flutter_web_platform.dart` and never executes any of them. The evidence never matched the code path this runner runs. |
| It is a "flake" | It is a reproducible deadlock at a specific, identifiable step, with a measurable rate. |
| Cannot be patched at the SDK level | The SDK is a **writable git checkout** at `/opt/homebrew/share/flutter` (the Caskroom path `/opt/homebrew/Caskroom/flutter/3.41.9/flutter` is a symlink to it). Patching requires deleting `bin/cache/flutter_tools.snapshot` to force a rebuild, because the stamp is keyed on the git revision, not on source content. |

A local patch is still the wrong deliverable: `brew upgrade` installs a new version
directory and repoints the symlink, silently discarding it, and it exists on no other
machine. Hence: pin the defect here, and make the runner name it.

## The specimen

Round 27 of the reproduction loop. The log stops here and never advances:

```
00:06 +82: test/pages/login_page_test.dart: LoginPage hides Apple Sign-In button on Android
00:07 +83: loading /Users/sairambkrishnan/git/ondoway/mobile/test/pages/home_page_test.dart
```

83 tests passed, 8 of 28 suites finished, and the 9th never produced a single event.

State at +14 minutes (all still alive, all at 0% CPU):

* the `dartvm` running `flutter_tools.snapshot test --platform chrome`
* the `frontend_server_aot` compiler
* Chrome, its GPU/network/storage helpers, and three renderers
* the test HTTP server on :62285 still answering `HTTP 200`
* Chrome's DevTools endpoint on :62287 still answering

So the browser launched correctly and had its debugging port. This is **not** a
browser-launch failure.

### Inside the browser

Chrome exposed exactly one target, the package:test host page. Its single suite iframe —
`home_page_test.html` — was `readyState: complete` with **538 of 538 DDC modules loaded**
(`requirejs` registry: 0 pending, 538 defined). Nothing failed to download.

But the Flutter engine inside that iframe never started:

```
flutterCanvasKitLoaded : [object Promise]   PENDING_AFTER_2000MS
CanvasKitInit          : undefined
flutterCanvasKit       : undefined
flutter-view elements  : 0
_flutter.loader        : ["didCreateEngineInitializer"]     (still waiting)
```

`canvaskit.js` had already been **fetched successfully** — the resource timing entry shows
`/canvaskit/chromium/canvaskit.js`, `initiatorType: script`, 86,496 bytes, completed 38 ms
after navigation start. Re-fetching every CanvasKit asset from the hung run's own server
returned `HTTP 200` in single-digit milliseconds. The file downloaded; its script never
defined `CanvasKitInit`; the promise waiting on it never resolved.

(An AMD/UMD collision with the DDC `require.js` loader was considered and **disproved**:
`define.amd` is null in that frame, `canvaskit.js` contains no `define.amd` branch, and no
defined module holds CanvasKit's factory.)

### The decisive comparison

Chrome's stored console log shows every healthy suite following the identical sequence:

```
Starting suite .../X.html
Appended iframe with src .../X.html#...
Injecting <script> tag. Using callback.
registerExtension() ... warning
WARNING: Falling back to CPU-only rendering. Reason: webGLVersion is -1
Font manifest does not exist at `assets/FontManifest.json` - ignoring.
Connecting channel for suite .../X.html
```

For `home_page_test.html` the sequence stops dead after `registerExtension()`. The
CPU-fallback line never appears, the font-manifest line never appears, and
`Connecting channel` never appears.

Counted over the whole run: **9 suites started, 8 connected, 8 CPU-fallback lines.**

## Cause

The Flutter web engine's renderer initialisation wedges while loading CanvasKit. The
headless browser runs with `--disable-gpu`, so every suite takes the `webGLVersion is -1`
CPU-only path, which downloads the Chromium CanvasKit variant. Intermittently the download
completes but the promise awaiting it never resolves, so Dart `main()` never runs and the
suite never opens its channel.

Nothing above that has a timeout, so the whole run inherits the hang:

1. `FlutterWebPlatform.load` (`flutter_web_platform.dart:601-629`) ends with
   `return await controller.suite;`. The suite future completes only when the browser side
   connects. There is no timeout.
2. That call holds `_suiteLock`, a `Pool(1)` released only by the suite's `onDone`
   (`flutter_web_platform.dart:583, 606-611`), so no later suite can start either.
3. `flutter test` therefore never reaches a verdict and never exits.

### A second unbounded wait, in the same area

While investigating, a distinct and independently reproducible hang was proven in the
browser launcher. `ChromiumLauncher._spawnChromiumProcess` (`web/chrome.dart:319-355`)
does:

```dart
await process.stderr … .firstWhere((line) => line.startsWith('DevTools listening'),
                                   orElse: …)
```

with no timeout. `orElse` fires only when stderr **closes**. The port comes from
`OperatingSystemUtils.findFreePort` (`base/os.dart:142-172`), whose own doc comment says
*"The port returned by this function may become used before it is bound by its intended
user."*

Verified directly against Chrome 145:

* debug port occupied on IPv4 only → Chrome falls back to IPv6 and **does** print
  `DevTools listening`; no hang.
* debug port occupied on **both** loopback stacks → Chrome prints
  `Cannot start http server for devtools.`, **stays alive with stderr open**, and never
  prints the marker. The await then never returns.

This class did **not** cause the observed specimen (that run's Chrome had its port), but it
is a real second way to hang with no verdict, and the runner distinguishes the two.

## What changed here

`scripts/flutter_test.sh` was rewritten so that neither hang can cost a green suite, and so
that neither can run unbounded:

* **Diagnose first, then recover — never silently.** The old runner retried three times
  and printed one vague sentence for every outcome, so the defect stayed folklore. Diagnosing
  without recovering would be the opposite failure: a green suite lost to a Flutter engine bug
  this repo cannot fix. So a stall is bounded, diagnosed in full, and only then re-run from
  scratch, up to 3 attempts. A **real test failure is never retried** — it prints its marker
  and exits immediately without reaching the recovery path. Neither is a crash (process ended
  with no verdict): re-running a crash only hides it.
* **Three attempts, not two.** Validating the recovery, the wedge fired on the recovery
  attempt itself, at `+20: loading widget_test.dart` — the same signature as the wild
  specimen. At the measured 1-in-27 rate, two attempts leave ~1 spurious failure in 730 runs;
  three leave ~1 in 20,000.
* **A hard wall-clock deadline (260s).** The stall detector is what should end a wedged run;
  this is the backstop for a run that dribbles output slowly enough never to trip it. The
  target could previously run forever; now nothing outlives the deadline.
* **A stall is silence, not slowness, and every budget is measured rather than guessed.** The
  old runner spent a flat 120s *total* budget, so a run that was merely slow scored identically
  to one that was wedged. The runner now measures *no growth in the log*, against numbers taken
  from this suite:

  | measurement | value | what it sets |
  | --- | --- | --- |
  | success, warm | 31s | — |
  | success, cold (`flutter clean` first) | 38s | the "is there room for another attempt" guard (>70s left) |
  | longest window with no output | 12s | stall threshold = 4× → **45s** |
  | stalled attempt (13s startup + 45s silence) | 58s | deadline = 3 stalls + slack → **260s** |

  A wedged run never recovers on its own — the caught specimen sat unchanged for 14 minutes —
  so waiting longer than 4× the worst working silence buys nothing but a slower failure.
* **The diagnosis names the class**: no reporter line yet → compile stall; stuck at the
  first `loading` with `+0` → browser-launch class; stuck mid-suite with `+N` → the suite
  class above. It also prints the last reporter line, who holds Chromium's debugging port
  (`lsof`), the process tree, and the full log.
* **Process ended without a verdict** is reported as a crash or early exit, not a hang —
  the old runner hid that case behind the same retry.
* **The pass path waits for the real exit.** The old runner SIGKILLed the tree the instant
  the marker appeared, saving ~10s and leaking one Chromium profile directory into
  `$TMPDIR` per green run (the tool deletes those in the shutdown hooks a SIGKILL skips).

The mutex, the per-run log, and the failure-detection regex are unchanged.

## Validation: 27 consecutive real runs

Run through the new runner on 2026-08-29, no shims and no sabotage, at the same count over
which the stall rate was measured:

```
runs 1-14   exit=0   30-33s   283 tests
run  15     exit=0   106s     283 tests   STALL-DIAGNOSED
runs 16-27  exit=0   30-33s   283 tests
TOTALS: green=27  red=0  runs_that_hit_a_stall=1
```

Run 15 is the whole point. It hit the wedge for real:

```
FLUTTER TESTS STALLED (attempt 1 of 3) — no output for 48s
WHERE: mid-suite, after 104 tests passed.
  last reporter line: 00:09 +104: loading .../test/services/session_selection_test.dart
>> RECOVERING: re-running the whole suite from scratch (attempt 2 of 3).
Flutter: all tests passed (283 tests) — on attempt 2, after recovering from the stall
```

Same signature as the original specimen — stalled at a `loading` line, mid-suite. Under the
old runner that is a hang until someone notices and kills it. Here it cost 106s and the
shard stayed green. The stall rate is unchanged at 1 in 27; what changed is what it costs.

Deliberately also proven, separately:

* **stall → recover → green** — sabotaged so only the first browser launch fails: attempt 1
  stalled, attempt 2 passed 283 tests, exit 0 in 84s.
* **stall on every attempt → hard fail** — port held for the whole run: diagnosed each time,
  exited 1 in 78s, no infinite wait.
* **a real test failure is never recovered** — the failure regex is unchanged from the
  production-proven runner, and no test name in `mobile/` contains any of its phrases.

One inconsistency worth recording: runs 1–6 used a 45s stall threshold and runs 7–27 used
48s (the constant was corrected mid-batch to match its stated "4 × the 12s longest working
silence"). No green run went quiet for more than 12s, so the difference cannot have changed
any of the 27 outcomes; run 15 stalled under the final 48s value.

## Prevention leads that were tried and NOT shipped

Preventing the wedge outright would beat recovering from it. Two routes were checked:

* **Switch renderer.** `flutter test` in 3.41.9 exposes no `--web-renderer` and no
  `--web-browser-flag` (checked against `flutter test -h -v`). `--wasm` swaps in skwasm but
  carries its own hang, flutter/flutter#177008.
* **Give headless Chrome software WebGL.** The wedge lives in the CPU-only path the engine
  takes because Flutter hardcodes `--disable-gpu` for headless, which makes `webGLVersion`
  −1. A `CHROME_EXECUTABLE` wrapper that drops `--disable-gpu` and adds
  `--use-gl=angle --use-angle=swiftshader --enable-unsafe-swiftshader` ran the suite green
  (283 tests). **Not shipped:** one green run says nothing about a 1-in-27 event, and the
  change alters how the app rasterises during tests, which `keep_exploring_golden_test.dart`
  depends on. Proving it would need ~80 runs plus a golden review. It is the most promising
  route if the recovery ever proves insufficient.

## Machine state changed while proving this

Two things on this machine are not what they were, both while forcing the SDK rebuild that
the patch experiment required:

* **`~/.pub-cache/hosted/pub.dev/web_socket-1.0.1` was corrupt and has been re-downloaded.**
  Its `lib/src/*` files were intact but the top-level `lib/web_socket.dart` and
  `lib/io_web_socket.dart` were missing, deleted 2026-08-23. Nothing noticed, because the
  cask ships a prebuilt `flutter_tools.snapshot`; the first rebuild attempt failed on it.
  Any future flutter tool rebuild on this machine would have hit the same wall.
* **`bin/cache/flutter_tools.snapshot` is now a local rebuild** (41,661,600 bytes,
  2026-08-28) rather than the cask-shipped binary (44,197,712 bytes, 2026-04-30). It was
  rebuilt from pristine source after the patch was reverted — `git -C
  /opt/homebrew/share/flutter status` is clean — and proven equivalent by a green
  283-test `make flutter-test`. `brew reinstall flutter` restores the shipped artifact if
  the difference is ever unwanted.

## Upstream

No existing flutter/flutter issue matches either defect (searched by symbol, by error
string, and by symptom). Both are worth filing:

Both filed 2026-08-29, on the owner's explicit go-ahead, from the account `SaiWebApps`:

1. **Engine — [flutter/flutter#192014](https://github.com/flutter/flutter/issues/192014).**
   CanvasKit load can never resolve, wedging a web test suite forever. Carries this
   document's specimen forensics; states plainly that there is no minimal reproduction and
   that the forensics *are* the report.
2. **Tool — [flutter/flutter#192013](https://github.com/flutter/flutter/issues/192013).**
   `_spawnChromiumProcess` waits for `DevTools listening` with no timeout, so a Chromium
   that cannot bind its debug port hangs the run instead of triggering the existing 3-try
   retry. Carries the deterministic two-stack port reproduction and the `.timeout(...)`
   patch with its before/after (forever, versus a named failure in 41s).

The two are cross-linked. Both bodies were sanitised before posting: no local paths, no
device identifiers, and no Ondoway test names or product wording — the defects are
reproducible without any of it. Both issue numbers are in the header of
`scripts/flutter_test.sh`.
