#!/usr/bin/env bash
# Run Flutter widget tests on headless Chrome — reliably and fast.
#
# WHY THIS EXISTS: flutter_tools' test runner has an intermittent finalize/cleanup
# flake (stack traces inside package:flutter_tools: _startTest.finalize /
# FlutterTesterTestDevice.kill / a PathNotFoundException deleting its own temp
# listener). When it fires, the process never prints "All tests passed!" and hangs
# until killed. It is NOT in our test code (zero web-only imports; both the VM and
# Chrome platforms exhibit it) and cannot be patched at the SDK level.
#
# STRATEGY: stream output to a log, decide pass/fail the instant the marker appears
# (so a clean run finishes in ~20-30s, not the SDK's post-completion hang), and
# RETRY ONLY ON A HANG — never on a real test failure. A genuine failure prints its
# marker immediately and exits 1 with no retry, so this never hides a broken test.
set -u

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MOBILE_DIR="$REPO_DIR/mobile"
LOG=/tmp/ondoway-flutter-test.log
# Resolve a browser for `flutter test --platform chrome` PORTABLY. Precedence:
#   1) a caller-set CHROME_EXECUTABLE (honored verbatim);
#   2) a local Playwright "Chrome for Testing" (macOS or Linux, any version);
#   3) empty -> let flutter auto-detect system Chrome (/Applications, PATH google-chrome).
# Wildcards are unquoted (so they glob); the spaces in the bundle name stay quoted.
CHROME="${CHROME_EXECUTABLE:-}"
if [ -z "$CHROME" ]; then
  for _c in "$HOME/Library/Caches/ms-playwright/"chromium-[0-9]*"/chrome-mac"*"/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing" \
            "$HOME/.cache/ms-playwright/"chromium-[0-9]*"/chrome-linux/chrome"; do
    [ -x "$_c" ] && { CHROME="$_c"; break; }
  done
fi
MAX_ATTEMPTS="${FLUTTER_TEST_MAX_ATTEMPTS:-3}"
ITERS="${FLUTTER_TEST_ITERS:-60}"   # per attempt: ITERS * 2s budget (60 -> 120s)

# Kill the leaked dart workers + headless Chrome. The bracket patterns
# (flutter_tools[.]snapshot / frontend[_]server_aot) match the dart processes but
# NOT this script's own command line, so we never kill ourselves.
cleanup() {
  pkill -f "flutter_tools[.]snapshot" 2>/dev/null
  pkill -f "frontend[_]server_aot" 2>/dev/null
  pkill -f "Google Chrome for Testing" 2>/dev/null
}

passed_log() { grep -q "All tests passed!" "$LOG" 2>/dev/null \
  && ! grep -qE "Some tests failed|Failed to load|did not complete" "$LOG" 2>/dev/null; }
failed_log() { grep -qE "Some tests failed|Failed to load|did not complete" "$LOG" 2>/dev/null; }

attempt=1
while [ "$attempt" -le "$MAX_ATTEMPTS" ]; do
  cleanup; sleep 1                      # clean slate before each attempt
  : > "$LOG"
  [ -n "$CHROME" ] && export CHROME_EXECUTABLE="$CHROME"
  ( cd "$MOBILE_DIR" \
      && NO_PROXY=pub.dev,*.pub.dev no_proxy=pub.dev,*.pub.dev \
         flutter test --platform chrome >"$LOG" 2>&1 ) &
  fpid=$!
  i=0
  while [ "$i" -lt "$ITERS" ]; do
    sleep 2
    passed_log && break
    failed_log && break
    kill -0 "$fpid" 2>/dev/null || break   # process exited on its own
    i=$((i + 1))
  done
  kill -9 "$fpid" 2>/dev/null
  cleanup

  if passed_log; then
    cat "$LOG"
    echo "Flutter: all tests passed (attempt $attempt/$MAX_ATTEMPTS, ~$((i * 2))s; dart workers + Chrome reaped)"
    exit 0
  fi
  if failed_log; then
    cat "$LOG"
    echo "FLUTTER TESTS FAILED (real failure, attempt $attempt) — see output above"
    exit 1
  fi
  echo ">> attempt $attempt produced no verdict in $((i * 2))s (flutter_tools finalize flake) — retrying" >&2
  attempt=$((attempt + 1))
done

cat "$LOG"
echo "FLUTTER TESTS INCOMPLETE — hung with no verdict on all $MAX_ATTEMPTS attempts (flutter_tools flake)" >&2
exit 1
