#!/usr/bin/env bash
# Run Flutter widget tests on headless Chrome, and NAME what happens when they don't.
#
# WHY THIS EXISTS: `flutter test --platform chrome` can stop producing output and never
# exit. Until 2026-08-28 this file called that a "flutter_tools finalize flake" and
# retried it three times. Both halves of that were wrong.
#
#   * The stack the old comment cited — _startTest.finalize, FlutterTesterTestDevice.kill,
#     a PathNotFoundException on a temp listener — lives in flutter_platform.dart and
#     flutter_tester_device.dart, which are the VM-platform sources. `--platform chrome`
#     runs flutter_web_platform.dart and never executes any of it, so the label described
#     code the CHROME pass does not run. The VM-tagged pass added at the bottom of this
#     file DOES run those sources, which is why it carries a hard deadline of its own —
#     see VM_DEADLINE_SECONDS. It is bounded; nothing here is unbounded.
#   * "cannot be patched at the SDK level" was untrue. The SDK here is a writable git
#     checkout at /opt/homebrew/share/flutter (the Caskroom path is a symlink to it), and
#     a one-line timeout in it turns the hang into a bounded error. See the measured
#     cause below.
#
# WHAT ACTUALLY HAPPENS (2026-08-28, flutter 3.41.9, Chrome for Testing 145.0.7632.6).
# Measured rate on an idle machine: ONE stall in 27 consecutive runs. The stall was caught
# live and interrogated through Chrome's own DevTools protocol before being killed. Two
# distinct hangs exist; the runner tells them apart because they need different owners.
#
#   1. THE OBSERVED ONE (flutter/flutter#192014) — the engine wedges loading CanvasKit,
#      mid-run. The specimen stopped at "+83: loading test/pages/home_page_test.dart" and
#      never moved. Chrome, its renderers, the compiler and the dart process were all
#      ALIVE at 0% CPU: a deadlock, not a spin. Inside the browser the iframe had all 538 of
#      its modules, but window.flutterCanvasKitLoaded was still an UNRESOLVED promise and
#      CanvasKitInit was undefined — even though canvaskit.js had downloaded fine (86 KB in
#      1 ms). Console proof across the whole run: 9 suites started, 8 connected, and the
#      one that stalled is the one missing the "Falling back to CPU-only rendering" line
#      every healthy suite prints. Dart main() therefore never ran, so the suite never
#      opened its channel, so FlutterWebPlatform.load's `await controller.suite` — which
#      has no timeout, and holds a Pool(1) — never returned.
#
#   2. A SECOND, DETERMINISTICALLY PROVABLE ONE (flutter/flutter#192013) — the browser
#      launcher. flutter_tools picks the debugging port with
#      OperatingSystemUtils.findFreePort, whose own doc comment says
#      "the port returned by this function may become used before it is bound by its
#      intended user", then in ChromiumLauncher._spawnChromiumProcess (web/chrome.dart) does
#
#          await process.stderr … .firstWhere((l) => l.startsWith('DevTools listening'), …)
#
#      with no timeout, where the orElse fires only when stderr CLOSES. A Chromium that
#      loses that race prints "Cannot start http server for devtools." and stays up with
#      stderr open, satisfying neither exit condition. Occupying the chosen port on BOTH
#      loopback stacks reproduces this on demand.
#
# Full evidence, and the SDK patch proving the hang can be bounded there, are written up in
# docs/bug-reports/2026-08-28-flutter-test-chrome-hang.md.
#
# WHAT THIS RUNNER DOES ABOUT IT: it detects a stall as a stall — no growth in the log for
# STALL_SECONDS while the process is alive — prints WHICH of the two it is from the position
# in the log plus who holds the debugging port, and only THEN re-runs the suite — up to
# MAX_ATTEMPTS times. Both halves matter. The runner this replaced also retried, but blindly:
# it printed one vague sentence for every outcome, retried real crashes as readily as hangs,
# and destroyed the evidence each time, so the defect stayed folklore for months. Diagnosing
# without recovering would be the opposite failure: a green suite lost to a Flutter engine
# bug this repo cannot fix. So: bounded, diagnosed in full FIRST, then recovered — and never
# recovered for a real test failure or a crash. Every outcome below exits with a named
# verdict, and none of them is unbounded. The two phases carry SEPARATE budgets, because
# they cost wildly different amounts and one ceiling sized for both would be useless for
# either: the VM pass is bounded by VM_DEADLINE_SECONDS and the chrome phase by
# DEADLINE_SECONDS, whose clock restarts when that phase begins. The runner's true ceiling
# is their sum.
#
# CONCURRENCY (2026-06-12): two simultaneous runs used to corrupt each other — a shared log
# path crossed verdicts between runs, and a machine-wide pkill cleanup killed the OTHER
# run's Chrome mid-suite plus any unrelated process whose command line matched. Now: the
# log is per-run, cleanup kills only THIS run's process tree, and a /tmp mutex serializes
# concurrent invocations. That mutex is also the cheapest defence against the port race
# above, since the likeliest way to lose it is a second Chromium of our own.
set -u

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MOBILE_DIR="$REPO_DIR/mobile"
# Per-run log. macOS mktemp substitutes only a TRAILING run of X's, so no suffix.
LOG="$(mktemp /tmp/ondoway-flutter-test.XXXXXX)"
LOCK_DIR=/tmp/ondoway-flutter-test.lock
LOCK_WAIT="${FLUTTER_TEST_LOCK_WAIT:-900}"  # max seconds to wait on another run's lock
# A stall is silence, not slowness. The old runner spent a flat 120s TOTAL budget, so a
# run that was merely slow scored the same as one that was wedged. Measured here 2026-08-28:
# a warm run finishes in 31s, a cold one (`flutter clean` first) in 38s, and the longest
# window with NO output in either is 12s. Every threshold below is derived from those three
# numbers rather than guessed, because a guessed budget is what made the old runner call a
# slow run and a wedged one by the same name.
#   success, warm ......... 31s        stall threshold = 4x the longest working silence
#   success, cold ......... 38s        deadline        = 3 stalled attempts + one green run
#   longest silence ....... 12s        (stall threshold = 4 x 12 = 48s)
# 48s of silence is four times the worst window this suite produces while it is working,
# and a wedged run never recovers — the caught specimen sat unchanged for 14 minutes — so
# waiting longer buys nothing but a slower failure.
STALL_SECONDS="${FLUTTER_TEST_STALL_SECONDS:-48}"
# Attempts, and ONLY a stall gets a second one. Both hangs above are in Flutter's own
# engine and launcher: this repo cannot fix either, and `flutter test` exposes no
# --web-renderer or --web-browser-flag in 3.41.9 to design them out (--wasm swaps in skwasm
# but carries its own hang, flutter/flutter#177008). What the runner CAN guarantee is that
# neither one ever costs a green suite: the stall is bounded, diagnosed in full, and then
# the suite is re-run from scratch, up to MAX_ATTEMPTS. That is safe precisely because a
# stall happens at suite LOAD — no test has failed, nothing is half-applied, and a real
# test failure prints its marker and exits on the spot without ever reaching recovery.
#
# Three, not two, and the third was earned: validating the recovery on 2026-08-28 the wedge
# fired on the recovery attempt itself, at "+20: loading widget_test.dart" — the same
# signature as the wild specimen. At the measured 1-in-27 rate two attempts leave roughly
# 1 in 730 runs failing spuriously, three leave 1 in 20,000, and a stalled attempt costs
# about 61s, so three still land inside the deadline below with room for a green run.
MAX_ATTEMPTS="${FLUTTER_TEST_MAX_ATTEMPTS:-3}"
# A HARD ceiling on the whole runner, every attempt and all diagnosis included, sized from
# the measurements above rather than picked round:
#   three stalled attempts  3 x (13s startup + 48s silence)  = 183s
#   diagnosis + teardown, three times                 + 20s  = 203s
#   slack for a loaded machine                        + 57s  = 260s
# So 260s — under four and a half minutes for the worst case the design admits, against a
# target that could previously run forever. It has to cover THREE stalls, not two: sized for
# two, the guard below would refuse the third attempt for lack of room and the extra attempt
# would be dead weight. This is only the backstop; the stall detector is what should end a
# wedged run. It exists for a run that dribbles one byte every 40 seconds and so never trips
# the detector at all. Nothing here may outlive it, whatever else breaks.
DEADLINE_SECONDS="${FLUTTER_TEST_DEADLINE_SECONDS:-260}"
STARTED_AT=$(date +%s)
elapsed_total() { echo $(( $(date +%s) - STARTED_AT )); }
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

# The failure regex is unchanged from the runner this replaced: it is production-proven,
# and none of mobile/'s test names contain any of these phrases (checked 2026-08-28), so a
# passing run cannot match it by accident.
passed_log() { grep -q "All tests passed!" "$LOG" 2>/dev/null \
  && ! grep -qE "Some tests failed|Failed to load|did not complete" "$LOG" 2>/dev/null; }
failed_log() { grep -qE "Some tests failed|Failed to load|did not complete" "$LOG" 2>/dev/null; }

# This run's PIDs as one comma-separated list ps will accept. Built here rather than
# inline because an empty descendant list would otherwise produce a leading comma and ps
# would reject the whole argument, silently costing the diagnosis its process tree.
run_pids_csv() {
  { descendants "$fpid"; echo "$fpid"; } | tr '\n' ',' | sed 's/,,*/,/g; s/^,//; s/,$//'
}

# How far the run got, in the reporter's own words: "<clock> +<passed>: <what>".
progress_line() { grep -oE "^[0-9]+:[0-9]+ \+[0-9]+[^:]*: .*" "$LOG" 2>/dev/null | tail -1; }
tests_done()    { progress_line | sed -nE 's/^[0-9]+:[0-9]+ \+([0-9]+).*/\1/p'; }

# Name the stall instead of retrying it. Each branch below is a DIFFERENT defect with a
# different owner, and the old runner printed one sentence for all of them.
diagnose_stall() {
  local secs="$1" attempt_no="$2" done_count line port holder
  line="$(progress_line)"
  done_count="$(tests_done)"

  echo "" >&2
  echo "FLUTTER TESTS STALLED (attempt $attempt_no of $MAX_ATTEMPTS) — no output for ${secs}s" >&2
  echo "and the process is still alive. This is a real deadlock, not a flake. What it was doing:" >&2
  echo "" >&2

  if [ -z "$line" ]; then
    echo "WHERE: before the first test suite was even announced — the web compile." >&2
    echo "       Suspect the compiler, not the browser. Re-run with --verbose to see" >&2
    echo "       which target it stopped on." >&2
  elif [ "${done_count:-0}" = "0" ]; then
    echo "WHERE: at the first 'loading' line, with zero tests completed." >&2
    echo "       This is the browser-launch stall documented at the top of this file:" >&2
    echo "       flutter_tools is waiting, with no timeout, for Chromium to print" >&2
    echo "       'DevTools listening' on stderr. A Chromium that cannot bind its" >&2
    echo "       debugging port never prints it and never exits." >&2
  else
    echo "WHERE: mid-suite, after ${done_count} tests passed." >&2
    echo "       The browser started and tests ran, so this is not the launch stall." >&2
    echo "       Suspect a suite that never signals completion: FlutterWebPlatform.load" >&2
    echo "       holds a Pool(1) released only by the suite's onDone." >&2
  fi
  echo "  last reporter line: ${line:-<none>}" >&2
  echo "" >&2

  # Who holds the debugging port this run's Chromium was told to use. When the launch
  # stall fires for real, this line names the process that won the race.
  port="$(ps -o command= -p "$(run_pids_csv)" 2>/dev/null \
          | sed -nE 's/.*--remote-debugging-port=([0-9]+).*/\1/p' | head -1)"
  if [ -n "$port" ]; then
    echo "  Chromium was told to use debugging port $port. Holder(s) of that port:" >&2
    holder="$(lsof -nP -iTCP:"$port" 2>/dev/null)"
    echo "${holder:-  (lsof reported nothing — Chromium never bound it)}" >&2
    echo "" >&2
  fi

  echo "  this run's process tree:" >&2
  # Order matters: send stdout to the real stderr FIRST, then silence stderr. Written the
  # other way round, `2>/dev/null >&2` points stdout at the already-silenced fd and the
  # tree vanishes — which is exactly what the first stall test caught.
  ps -o pid,ppid,etime,stat,command -p "$(run_pids_csv)" >&2 2>/dev/null
  echo "" >&2
  echo "  full log of the stalled run:" >&2
  cat "$LOG" >&2
}

# EVERY TEST FILE MUST BE EXECUTED BY ONE OF THE TWO PASSES.
#
# The two selectors below are complements: the chrome pass takes everything
# without the vm tag, the VM pass takes exactly the tagged ones. So the ONLY way
# a file can run in NEITHER is for chrome to refuse it on a @TestOn annotation
# while it carries no vm tag to make the VM pass select it.
#
# Measured 2026-08-30: mobile/test/pages/keep_exploring_golden_test.dart carried
# @TestOn('vm') and no @Tags(['vm']). The chrome pass skipped it, the VM pass did
# not select it, and it had been green by never executing for months — the one
# way a golden test can lie. Nothing false was ever said about it, so no reviewer
# of claims was ever going to find it; only a count of what runs can.
#
# Read from the annotations rather than from either pass's output, because a file
# that runs nowhere prints nothing to parse. This costs milliseconds and runs
# before the lock, so a mis-tagged file fails immediately instead of after a
# minute of waiting on another run.
orphan_tests=""
while IFS= read -r rel; do
  [ -n "$rel" ] && [ -f "$REPO_DIR/$rel" ] || continue
  grep -q '@TestOn' "$REPO_DIR/$rel" || continue
  grep -qE "@Tags\(.*'vm'" "$REPO_DIR/$rel" || orphan_tests="$orphan_tests $rel"
done <<EOF
$(git -C "$REPO_DIR" ls-files 'mobile/test/*_test.dart')
EOF
if [ -n "$orphan_tests" ]; then
  echo "FLUTTER TESTS REFUSED — these files would run in NEITHER pass:" >&2
  for _t in $orphan_tests; do echo "    $_t" >&2; done
  echo "" >&2
  echo "Each declares @TestOn, so the chrome pass (--exclude-tags vm) skips it, and" >&2
  echo "carries no @Tags(['vm']), so the VM pass (--tags vm) does not select it. A test" >&2
  echo "that runs in neither pass is not a passing test; it is a test that never ran," >&2
  echo "and it reports green forever. Add @Tags(['vm']) beside the @TestOn — both" >&2
  echo "annotations are load-bearing — or remove the @TestOn." >&2
  exit 1
fi

acquire_lock

# One whole run of the suite. Sets $outcome to PASS | FAIL | STALL | NOVERDICT, $ec to the
# exit code of a run that finished, and $stalled_for to the silence that tripped a stall.
run_once() {
  : > "$LOG"
  # --exclude-tags vm: tests tagged @Tags(['vm']) use dart:io — a source guard
  # that File().readAsStringSync()s a lib file, a fixture loaded off disk — and
  # dart:io does not exist under the JS platform, so they throw Unsupported
  # operation here. They are not skipped: the VM pass below runs them on the
  # native engine, and both passes must be green. mobile/dart_test.yaml declares
  # the tag and describes exactly this pair.
  ( cd "$MOBILE_DIR" \
      && NO_PROXY=pub.dev,*.pub.dev no_proxy=pub.dev,*.pub.dev \
         flutter test --platform chrome --exclude-tags vm >"$LOG" 2>&1 ) &
  fpid=$!

  # Let the run exit on its own. The runner this replaced killed the tree the instant the
  # marker appeared, which saved about ten seconds and leaked one Chromium profile
  # directory into $TMPDIR per green run — the tool deletes those in the shutdown hooks a
  # SIGKILL skips.
  local quiet=0 last=0 size
  while kill -0 "$fpid" 2>/dev/null; do
    sleep 2
    size=$(wc -c < "$LOG" 2>/dev/null || echo 0)
    if [ "$size" -gt "$last" ]; then
      last="$size"
      quiet=0
    else
      quiet=$((quiet + 2))
    fi
    if [ "$quiet" -ge "$STALL_SECONDS" ]; then
      stalled_for="$quiet"
      outcome=STALL
      return
    fi
    if [ "$(elapsed_total)" -ge "$DEADLINE_SECONDS" ]; then
      outcome=DEADLINE
      return
    fi
  done
  wait "$fpid"
  ec=$?
  # The run is reaped. Clear the handle so the EXIT trap cannot signal a recycled PID.
  fpid=""

  if passed_log; then
    outcome=PASS
  elif failed_log; then
    outcome=FAIL
  else
    outcome=NOVERDICT
  fi
}

[ -n "$CHROME" ] && export CHROME_EXECUTABLE="$CHROME"

# The VM pass, first. Tests tagged @Tags(['vm']) cannot run under chrome — the
# chrome pass above excludes them — so they run here on flutter's native engine.
# `tester` is that engine's name; `vm` is a tag, not a --platform value. BOTH
# passes must succeed for this target to succeed. It runs first so a source
# guard that fails is the first thing on screen.
#
# It carries NO stall detector but it does carry a HARD DEADLINE, and the two are
# not the same tool. The stall detector watches for silence, and a wedged tester
# run is not necessarily silent — the finalize hang named at the top of this file
# lives in exactly the VM-platform sources this pass executes. Silence-based
# detection cannot see that; a deadline can. Without one this pass could hang
# forever holding the lock, which is the disease this whole runner exists to
# cure.
#
# THE BUDGET, MEASURED 2026-08-30 rather than guessed — and the first version of
# this line WAS guessed, at 60s, from a warm number that did not survive contact:
#
#   green, cold ........... 312s   (5:12 wall, including `flutter pub get`)
#   green, warm ........... 342s   (5:41 wall — WARM IS NOT FASTER, see below)
#
# `--tags vm` does not select 18 tests and skip the rest cheaply. It LOADS all 46
# files under mobile/test, compiles every one of them for the tester engine, and
# only then filters by tag. That compile is the whole cost and it is not cached
# between runs, which is why a second consecutive run is no faster than the first.
# 18 tests take seconds; getting to them takes five and a half minutes.
#
# So: worst measured green 342s, doubled for a loaded machine, rounded up. 900s
# is bounded, which is the only property that matters here — a wedged run ends in
# fifteen minutes instead of never, and a healthy one has 2.6x its worst observed
# cost in hand.
VM_DEADLINE_SECONDS="${FLUTTER_VM_DEADLINE:-900}"

echo ">> running VM-tagged tests (flutter test --platform tester --tags vm)" >&2
( cd "$MOBILE_DIR" \
    && NO_PROXY=pub.dev,*.pub.dev no_proxy=pub.dev,*.pub.dev \
       flutter test --platform tester --tags vm ) &
vm_pid=$!
vm_waited=0
while kill -0 "$vm_pid" 2>/dev/null; do
  sleep 1
  vm_waited=$((vm_waited + 1))
  if [ "$vm_waited" -ge "$VM_DEADLINE_SECONDS" ]; then
    echo "" >&2
    echo "FLUTTER VM-TAGGED TESTS HIT THEIR ${VM_DEADLINE_SECONDS}s DEADLINE." >&2
    echo "This pass runs flutter_platform.dart / flutter_tester_device.dart — the sources" >&2
    echo "the finalize hang documented at the top of this file actually lives in. A run" >&2
    echo "that wedges there can keep printing, so the silence detector would never see it." >&2
    echo "Killed rather than left to hold the lock. Read the output above; do not re-run" >&2
    echo "blind." >&2
    # Sweep the TREE, in kill_run_tree's own idiom. Killing $vm_pid alone is not
    # enough: a non-interactive shell has no job control, so the `( … ) &`
    # subshell shares this script's process group — there is no group of its own
    # to signal — and bash does not exec the workload in place. $vm_pid is the
    # subshell; the flutter and dart processes are its CHILDREN, and killing the
    # parent would orphan exactly the wedged run this deadline exists to end.
    # Descendants must be listed BEFORE the root dies or they reparent away.
    vm_pids="$(descendants "$vm_pid"; echo "$vm_pid")"
    # shellcheck disable=SC2086  # word-splitting the PID list is intended
    kill -9 $vm_pids 2>/dev/null
    wait "$vm_pid" 2>/dev/null
    exit 1
  fi
done
wait "$vm_pid"
vm_rc=$?
if [ "$vm_rc" -ne 0 ]; then
  echo "FLUTTER VM-TAGGED TESTS FAILED (exit $vm_rc) — see output above." >&2
  exit 1
fi

# Restart the clock for the chrome phase. DEADLINE_SECONDS is sized above from
# chrome's own numbers alone — three stalled attempts plus a green run — and
# elapsed_total() counts from script start, so without this reset a legitimate
# five-minute VM pass would leave the chrome pass already over budget and it
# would abandon itself on its first poll, blaming a deadline it never used a
# second of. The two phases are bounded separately and deliberately: VM by
# VM_DEADLINE_SECONDS, chrome by DEADLINE_SECONDS from here.
STARTED_AT=$(date +%s)

attempt=1
while :; do
  outcome=""
  ec=0
  stalled_for=0
  run_once

  if [ "$outcome" = DEADLINE ]; then
    echo "" >&2
    echo "FLUTTER TESTS ABANDONED — the runner hit its ${DEADLINE_SECONDS}s hard deadline" >&2
    echo "on attempt $attempt while the process was still producing occasional output, so the" >&2
    echo "stall detector never tripped. That combination is not either hang documented at the" >&2
    echo "top of this file; treat it as a new one and keep the log below." >&2
    echo "  last reporter line: $(progress_line)" >&2
    kill_run_tree
    cat "$LOG" >&2
    exit 1
  fi

  if [ "$outcome" = STALL ]; then
    diagnose_stall "$stalled_for" "$attempt"
    kill_run_tree
    # Only start another attempt if a GREEN one could still finish inside the deadline —
    # 38s for a cold run, plus slack. Gating on the stalled-attempt cost instead would
    # refuse the last attempt precisely when it is most likely to be the one that passes.
    if [ "$attempt" -lt "$MAX_ATTEMPTS" ] \
       && [ $(( DEADLINE_SECONDS - $(elapsed_total) )) -gt 70 ]; then
      echo "" >&2
      echo ">> RECOVERING: re-running the whole suite from scratch (attempt $((attempt + 1)) of $MAX_ATTEMPTS)." >&2
      echo "   This is not the blind retry this runner used to do. Only a STALL reaches this" >&2
      echo "   line, the diagnosis above was printed in full first, and a real test failure" >&2
      echo "   exits immediately without ever getting here." >&2
      attempt=$((attempt + 1))
      sleep 2
      continue
    fi
    echo "" >&2
    if [ "$attempt" -ge "$MAX_ATTEMPTS" ]; then
      echo "FLUTTER TESTS STALLED ON ALL $attempt OF $MAX_ATTEMPTS ATTEMPTS, in $(elapsed_total)s." >&2
      echo "That is not the intermittent engine wedge (measured at 1 run in 27) — something is" >&2
      echo "reproducibly stuck. Read the diagnosis above rather than re-running." >&2
    else
      echo "FLUTTER TESTS STALLED on attempt $attempt, and there is not enough of the" >&2
      echo "${DEADLINE_SECONDS}s deadline left ($(( DEADLINE_SECONDS - $(elapsed_total) ))s) to run a whole second attempt." >&2
      echo "Not started: a recovery the deadline would cut off mid-suite proves nothing." >&2
    fi
    exit 1
  fi

  cat "$LOG"
  passed_count="$(tests_done)"

  case "$outcome" in
    PASS)
      if [ "$attempt" -gt 1 ]; then
        echo "Flutter: all tests passed (${passed_count:-0} tests) — on attempt $attempt, after recovering from the stall diagnosed above."
      else
        echo "Flutter: all tests passed (exited cleanly, ${passed_count:-0} tests)"
      fi
      exit 0
      ;;
    FAIL)
      echo "FLUTTER TESTS FAILED — a real test failure. Not retried. See the output above." >&2
      exit 1
      ;;
    *)
      # Alive-and-silent is the STALL branch, so reaching here means the process ENDED
      # without printing a verdict. That is a crash, not a hang, and it is not recovered:
      # re-running a crash just hides it, which is what the old "no verdict … retrying"
      # did three times over before giving up with the same sentence.
      echo "" >&2
      echo "FLUTTER TESTS ENDED WITH NO VERDICT — exit code $ec, after ${passed_count:-0} tests." >&2
      echo "The process finished on its own without printing a pass or fail marker, so this is" >&2
      echo "a crash or an early exit, not a hang. It is not retried. Full output is above." >&2
      exit 1
      ;;
  esac
done
