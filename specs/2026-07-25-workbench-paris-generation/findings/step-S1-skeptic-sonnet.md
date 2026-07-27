# Skeptic panel — Step S1 (LISTEN-scope port kill) — sonnet

**Verified against commit:** 930b1e201d8528cd9ae493df5111127715d12d6b (HEAD, working tree dirty
with S1's diff to `Makefile`, `scripts/workbench.sh`, `tests/test_premium_workbench_wiring.py`
present, exactly matching the evidence's stated diffstat).

**Angle:** FIX CORRECTNESS — is the change itself right, does the red-first test encode the
ORIGINAL failure mode or a strawman, would a plausible neighbouring input still break it.

## What I independently did

1. Read `run-context.md` in full (tier, AC-1..AC-5, D1/D3 decisions, pinned gate `make lint`).
2. Read the full diff (`git diff -- Makefile scripts/workbench.sh tests/test_premium_workbench_wiring.py`)
   and the resulting files in place.
3. Ran `make lint` myself (pure ruff, no shared state) — **exit 0**, `All checks passed!`, matching
   the evidence.
4. Independently reproduced the underlying OS-level mechanism the fix relies on, outside of pytest
   and outside any Make target (own listener/client Python processes + raw `lsof`, no shared
   container touched):

```
$ lsof -i:48173                      # old, unscoped selector
Python  5930 ... TCP localhost:48173 (LISTEN)
Python  5937 ... TCP localhost:58126->localhost:48173 (ESTABLISHED)
$ lsof -tiTCP:48173 -sTCP:LISTEN     # new, scoped selector
5930
$ kill 5930                          # only the scoped PID
listener alive? NO
client alive? YES
```
   This confirms, on this real Darwin machine, exactly the mechanism the test and the fix both
   depend on: `-sTCP:LISTEN` correctly excludes an ESTABLISHED client and isolates only the
   listener PID. Not fabricated — command and output above are from this run.
5. Traced whether S1 alone can make `make workbench` reach the state AC-3 literally describes.
   `grep -n "lsof\|_port_busy" scripts/deploy.py` shows line 84 still does
   `["lsof", f"-ti:{port}"]` — unscoped, the exact same defect class, unfixed by this step. Per
   `run-context.md` D3 this is intentionally deferred to S2/S4 ("S1 must land FIRST because it
   deletes the kill before EITHER shield falls"), so this is not a surprise, but it does mean AC-3
   as literally worded ("when `make workbench` runs to completion...") is **not yet true
   end-to-end** after S1 alone — `make workbench` invokes `_ensure-dev-data` → deploy.py's
   `_upload_areas_step` → `_port_busy(8000)`, which can still sys.exit early on the false-positive
   read of the Claude-desktop ghost socket, before workbench.sh's now-fixed kill code ever runs.

## Fix-correctness assessment

- The mechanism is correct and I reproduced it independently (above), not just re-read the
  developer's transcript. `lsof -tiTCP:${PORT} -sTCP:LISTEN` is a real, standard lsof state
  filter; it isolates the listener PID and only the listener PID.
- `scripts/workbench.sh` and the `flutter-ios` Makefile recipe both print PID+comm for every
  victim **before** the single `kill $PORT_KILL_PIDS` call (loop-then-kill, not
  interleaved-kill-per-pid) — satisfies AC-5's "prints before signalling" requirement exactly as
  worded, not just "eventually prints something."
- Neighbouring inputs I reasoned through and could not break the fix with: multiple simultaneous
  LISTEN PIDs on the port (word-split `for`/`kill` handles a multi-line PID list correctly, as
  seen in the raw lsof output format); a listener bound to `0.0.0.0` instead of `127.0.0.1`
  (`-tiTCP:PORT` has no host restriction, same as the old unscoped call, so no regression); a
  process that has already exited between `lsof` and `ps` (handled via `${cmd:-unknown}` fallback,
  doesn't crash the script because of `set -u` interacting with an always-assigned, possibly-empty
  var).
- The regression test's `_extract_port_free_snippet` correctly isolates the `else`-branch block up
  to (not including) `cd "$ROOT"` — I re-read the actual script text and confirmed the extracted
  span is syntactically self-contained (full `if...fi`, comments, no dangling continuation), which
  is why it can be run standalone as `PORT=$port\n{snippet}` in a subprocess as the test does.
- The Makefile-side regex assertion (`re.search(r"lsof\s+-tiTCP:8000\s+-sTCP:LISTEN", ...)` plus
  the "no unscoped `-ti:8000` remains" negative check) matches the actual `flutter-ios:` recipe
  text I read at `Makefile:361-374`.

## Caveats (advisory, not blocking)

1. **AC-3 is over-claimed as fully satisfied by S1 in isolation.** AC-3's literal antecedent is
   "when `make workbench` runs to completion." `scripts/deploy.py:84` (`_port_busy`) still uses the
   unscoped `lsof -ti:{port}` selector — confirmed present at HEAD via grep, unchanged by this
   step's diff, and explicitly named in the same run-context (D1, D3) as a defect deferred to S2.
   It doesn't kill anyone (it's a busy-check, not a kill), so it doesn't violate the letter of
   "ps -p 62717 still exits 0" directly — but it can make `make workbench` `sys.exit` before
   reaching completion at all, which means the AC-3 scenario as literally worded is not yet
   end-to-end provable, only its underlying *mechanism* is. This looks like the ledger's intended
   incremental-closure model (S1 lands the kill-scoping primitive; S2/S4 remove the other
   shields), not a functional bug in S1's own diff — but the claim under review states flatly
   "satisfies AC-1, AC-2, AC-3, AC-5" without that qualification, which slightly overstates what a
   single-file-scoped step can prove for AC-3. Rate this UNPROVEN-for-the-full-AC, not REFUTED —
   S1's own code and test are correct for what they claim to fix.
2. **The regression test proxies "CLOSED/TIME_WAIT" (the real-world Claude-desktop symptom
   measured in D1) with "ESTABLISHED"** rather than reproducing a CLOSED-state socket directly.
   This is a defensible engineering tradeoff (CLOSED/TIME_WAIT sockets are transient kernel
   artifacts that are impractical to hold open deterministically for a test), and the fix's
   mechanism is a blanket allow-list on `-sTCP:LISTEN` that doesn't special-case any particular
   non-LISTEN state, so passing for ESTABLISHED is good evidence the same predicate holds for
   CLOSED/TIME_WAIT too. Not a strawman, but also not a byte-for-byte reproduction of the exact
   measured symptom (two CLOSED sockets, PID 62717). Advisory only.

## Verdict

**CONFIRMED** for what S1 actually changes and claims about its own diff (AC-1, AC-2, AC-5, and
the underlying mechanism behind AC-3). I tried to break the LISTEN-scoping mechanism with
neighbouring inputs (multi-PID, non-127.0.0.1 host, already-exited PID, print-before-kill
ordering) and could not; I independently reproduced the core lsof mechanism outside of pytest and
it matched. The one real gap is evidentiary scope, not fix correctness: AC-3's literal "make
workbench runs to completion" antecedent is not yet true after S1 alone because
`scripts/deploy.py:84` still carries the same unscoped-lsof defect, deferred by design to S2. This
should be logged as a qualifier on the AC-3 claim, not treated as a rework trigger for S1.

## Attacks tried

- Re-derived the diff from git rather than trusting the pasted evidence.
- Independently reproduced the lsof LISTEN-vs-ESTABLISHED filtering behavior on this real machine
  with fresh subprocesses, outside pytest and outside any Make target.
- Grepped for every remaining unscoped `lsof -ti`/`xargs kill` occurrence in the repo to check
  whether S1's claimed scope (`Makefile`, `scripts/workbench.sh`) left a sibling instance
  (`scripts/deploy.py:84`) that could undermine the AC-3 claim.
- Read the test's snippet-extraction and regex-assertion logic against the actual current file
  contents to check it isn't matching stale/wrong text or a weaker invariant than claimed.
- Reasoned through neighbouring inputs (multi-PID, non-loopback host, race on already-exited PID,
  print-ordering) without executing anything that touches the shared 7687/7688/8001 containers.
- Ran `make lint` myself (exit 0) rather than trusting the pasted transcript.
- Did NOT run `make test-file` myself (shared 7687/8001-touching per CLAUDE.md); did NOT run
  `git stash` mutation myself to avoid disturbing the shared working tree while sibling skeptics
  are also inspecting it.
