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
# RETRY ONLY ON A HANG OR INFRA FLAKE — never on a real test failure. A genuine
# failure prints its marker immediately and exits 1 with no retry, so this never
# hides a broken test.
#
# CONCURRENCY (2026-06-12): two simultaneous runs used to corrupt each other — a
# shared log path crossed verdicts between runs, and the machine-wide pkill cleanup
# killed the OTHER run's Chrome mid-suite ("Connection closed before test suite
# loaded") plus any unrelated process whose command line matched the patterns.
# Now: the log is per-run, cleanup kills only THIS run's process tree, and a /tmp
# mutex serializes concurrent invocations.
set -u

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MOBILE_DIR="$REPO_DIR/mobile"
# Per-run log. macOS mktemp substitutes only a TRAILING run of X's, so no suffix.
LOG="$(mktemp /tmp/ondoway-flutter-test.XXXXXX)"
LOCK_DIR=/tmp/ondoway-flutter-test.lock
LOCK_WAIT="${FLUTTER_TEST_LOCK_WAIT:-900}"  # max seconds to wait on another run's lock
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

# Recursively list the descendant PIDs of $1, deepest first. Must run BEFORE the
# root is killed: once the dart process dies, its Chrome children reparent to
# launchd and pgrep -P can no longer reach them.
descendants() {
  local child
  for child in $(pgrep -P "$1" 2>/dev/null); do
    descendants "$child"
    printf '%s\n' "$child"
  done
}

# Kill THIS run's flutter process tree only (dart workers + the headless Chrome it
# launched live under $fpid). Never touches other runs or unrelated processes.
kill_run_tree() {
  [ -n "${fpid:-}" ] || return 0
  local pids
  pids="$(descendants "$fpid"; echo "$fpid")"
  # shellcheck disable=SC2086  # word-splitting the PID list is intended
  kill -9 $pids 2>/dev/null
  wait "$fpid" 2>/dev/null
  fpid=""
}

# Serialize concurrent invocations machine-wide. mkdir is atomic; the holder
# records its PID so a lock left by a crashed run is reclaimed instead of waited
# on forever. (Two waiters reclaiming at the same instant can race rm-vs-mkdir;
# for runs started by humans seconds apart that window is negligible.)
acquire_lock() {
  local waited=0 holder
  while ! mkdir "$LOCK_DIR" 2>/dev/null; do
    holder="$(cat "$LOCK_DIR/pid" 2>/dev/null || true)"
    if [ -n "$holder" ] && ! kill -0 "$holder" 2>/dev/null; then
      echo ">> reclaiming stale lock $LOCK_DIR (holder pid $holder is gone)" >&2
      rm -rf "$LOCK_DIR"
      continue
    fi
    if [ "$waited" -ge "$LOCK_WAIT" ]; then
      echo "FLUTTER TESTS BLOCKED — another run (pid ${holder:-unknown}) held $LOCK_DIR for ${LOCK_WAIT}s" >&2
      exit 1
    fi
    [ "$waited" -eq 0 ] && \
      echo ">> another flutter-test run holds $LOCK_DIR (pid ${holder:-unknown}) — waiting up to ${LOCK_WAIT}s" >&2
    sleep 2
    waited=$((waited + 2))
  done
  echo "$$" > "$LOCK_DIR/pid"
  LOCKED=1
}

LOCKED=0
finish() {
  kill_run_tree
  [ "$LOCKED" = 1 ] && rm -rf "$LOCK_DIR"
  rm -f "$LOG"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# "Connection closed before test suite loaded" = Chrome died before the suite ran
# (Chrome crash or an external kill) — infra, retryable, never a code failure.
infra_log()  { grep -q "Connection closed before test suite loaded" "$LOG" 2>/dev/null; }
passed_log() { grep -q "All tests passed!" "$LOG" 2>/dev/null \
  && ! grep -qE "Some tests failed|Failed to load|did not complete" "$LOG" 2>/dev/null; }
failed_log() { grep -qE "Some tests failed|Failed to load|did not complete" "$LOG" 2>/dev/null \
  && ! infra_log; }

acquire_lock

attempt=1
while [ "$attempt" -le "$MAX_ATTEMPTS" ]; do
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
    infra_log && break
    kill -0 "$fpid" 2>/dev/null || break   # process exited on its own
    i=$((i + 1))
  done
  kill_run_tree

  if passed_log; then
    cat "$LOG"
    echo "Flutter: all tests passed (attempt $attempt/$MAX_ATTEMPTS, ~$((i * 2))s; run-scoped dart workers + Chrome reaped)"
    exit 0
  fi
  if failed_log; then
    cat "$LOG"
    echo "FLUTTER TESTS FAILED (real failure, attempt $attempt) — see output above"
    exit 1
  fi
  if infra_log; then
    echo ">> attempt $attempt: Chrome connection closed before the suite loaded (infra flake, not a test failure) — retrying" >&2
  else
    echo ">> attempt $attempt produced no verdict in $((i * 2))s (flutter_tools finalize flake) — retrying" >&2
  fi
  sleep 1   # let the killed tree settle before relaunching
  attempt=$((attempt + 1))
done

cat "$LOG"
echo "FLUTTER TESTS INCOMPLETE — no clean verdict on all $MAX_ATTEMPTS attempts (flutter_tools hang or Chrome infra flake)" >&2
exit 1
