# S1 hostile skeptic — NEGATIVE SPACE angle

- **Verified against:** HEAD `930b1e201d8528cd9ae493df5111127715d12d6b` ("refactor: make test and env targets self-contained")
  plus the uncommitted S1 diff (`M Makefile`, `M scripts/workbench.sh`, `M tests/test_premium_workbench_wiring.py`).
- **Date:** 2026-07-25
- **Claim under attack:** S1 satisfies AC-1, AC-2, AC-3, AC-5, proven by
  `make test-file FILE="tests/test_premium_workbench_wiring.py::test_launchers_kill_only_listening_sockets"`
  plus a QA mutation verdict of REAL.
- **Constraint:** running concurrently with 2 other skeptics. I ran only `make lint` (exit 0)
  and hermetic scratchpad probes (own subprocesses, own ephemeral ports, no shared container,
  no repo Make target other than `lint`). All live `lsof`/`ps` probes were read-only —
  no `kill` was ever piped at a real host PID.

## Verdict: UNPROVEN

The *behaviour* of AC-1/AC-2/AC-5 holds — I re-derived it myself, by executing BOTH launcher
implementations, not by trusting the test. But the cited test does **not** prove AC-3, the
criterion the whole fix exists for; and the fix introduces a real, reproduced regression in
the "half-started service" state that no AC and no test covers.

---

## F1 (HIGH) — "AC-3 is proven by this test" is REFUTED. A green-keeping mutant re-kills PID 62717.

AC-3's failure mode is a **CLOSED, client-side** socket. The test only ever creates an
**ESTABLISHED** one (`_CLIENT_SRC` connects and holds). The comment at
`tests/test_premium_workbench_wiring.py:118-120` asserts these are "the same defect class";
they are not the same lsof *state*, and the test's selector-guard is therefore permeable in
exactly the AC-3 direction.

Mutant selector `lsof -tiTCP:${PORT} -sTCP:LISTEN,CLOSED` (a one-token edit of the shipped line):

```
PART A (the shipped test's own assertions, run against the MUTANT selector):
  AC-1 listener killed : True
  AC-2 client alive    : True
  AC-5 pid+comm printed: True
  => shipped test would be GREEN on the mutant

PART B (a process holding ONLY a CLOSED socket on the port, like PID 62717):
Python  7100  ...  TCP localhost:58153 (CLOSED)
  ghost alive after MUTANT : False  (AC-3 requires True)
```

And live, read-only, against the actual ghost the fix was written for:

```
$ lsof -tiTCP:8000 -sTCP:LISTEN           # shipped selector
(exit 1)                                   -> empty, correct
$ lsof -tiTCP:8000 -sTCP:LISTEN,CLOSED    # mutant the test cannot see
62717
$ ps -p 62717 -o pid=,comm=
62717 /Applications/Claude.app/.../Claude Helper
```

So a future edit can re-introduce the exact original defect — killing the user's Claude
desktop app — with `test_launchers_kill_only_listening_sockets` still green. The test guards
the ESTABLISHED case only. The QA "REAL" verdict proves the test detects the *unscoped* form,
not the AC-3 state.

**Fix:** add a CLOSED-socket fixture (bind without listen, or a client whose peer has gone
away) and assert that holder survives; or assert the literal selector text
`-sTCP:LISTEN` with no additional states.

## F2 (MEDIUM) — "AC-2 is proven by this test" is REFUTED as a proof: the assertion passes vacuously.

The test sleeps a hard-coded `time.sleep(0.5)` for the client to reach ESTABLISHED, and its
only pre-check is `assert _alive(client)` — *process* liveness, never *socket* state. If the
client subprocess's interpreter startup exceeds ~0.5 s (routine on a machine running the
shared-container suite), the launcher block runs while no client socket exists at all, and
`_alive(client)` is then evaluated **before** the client's `connect()` even fires.

Replayed with the test's helpers copied verbatim, client startup 1.0 s:

```
t=0.58s  sockets on the port AT THE MOMENT the launcher block runs:
Python  7609 ...  TCP localhost:58168 (LISTEN)
  -> NO ESTABLISHED client socket exists. AC-2's fixture was never created.
t=1.44s  AC-2 assertion evaluated here: _alive(client)=True -> TEST PASSES
t=3.03s  client returncode=1  (it later died of ConnectionRefused; the assertion had already passed)
```

Consequence for the evidence chain: the QA mutation verdict is *also* timing-dependent. In this
vacuous window the unscoped-lsof mutant selects only the listener, the client is not killed,
and the undo-test would report **FAKE**, not RED. The developer's RED transcript is real but
is a property of that machine at that instant, not of the test.

**Fix:** have the client write a readiness byte on a pipe after `connect()`, or poll
`lsof -iTCP:$PORT -sTCP:ESTABLISHED` until the client socket is visible, before running the snippet.

## F3 (MEDIUM) — New regression, unguarded by any AC: a half-started server on :8000 is no longer freed, and it does block bind.

`scripts/workbench.sh:25` still says "Free the port in case a stale uvicorn is lingering". After
LISTEN-scoping, that is no longer true for a server that has `bind()`-ed but not yet `listen()`-ed
— lsof reports it as `(CLOSED)`, the same state the fix deliberately excludes. Measured:

```
--- lsof -i:58132 (half-started, bound-not-listening) ---
Python  6477 ...  TCP localhost:58132 (CLOSED)
--- NEW code selection: lsof -tiTCP:58132 -sTCP:LISTEN ---   (exit 1)   -> selects NOTHING
--- OLD code selection: lsof -ti:58132 ---                   6477       -> old code freed it
--- does the half-started socket BLOCK a fresh bind? ---
BIND_FAIL -> [Errno 48] Address already in use
--- run the NEW port-free block (from workbench.sh) ---
    (NEW code selected NOTHING)
RESULT: half-started process STILL ALIVE after new block
--- after NEW block, can uvicorn bind? ---
BIND_FAIL -> [Errno 48] Address already in use   <-- launcher's uvicorn would FAIL to bind
```

Degradation is not silent — `scripts/workbench.sh:53-65` waits 30 s then prints
"port ${PORT} busy" — but the port-freeing step itself prints **nothing** when it selects
nothing, so the operator gets a 30-second stall and a generic hint instead of a diagnosis.
`make flutter-ios` has no such wait at all: it backgrounds uvicorn, `sleep 2`, and launches
Flutter against a dead API.

Field probability is low (the bind→listen window in uvicorn is short); the state is reachable
from a crashed/aborted startup. Not a demo blocker, but the comment overstates the code.

**Fix (cheap):** `else echo "    :${PORT} has no LISTEN-state owner"; fi`, and/or additionally
select `-sTCP:CLOSED` **restricted to sockets whose LOCAL port is ${PORT}** (which excludes
client-side ghosts like 62717, whose local port is 5444x).

## F4 (LOW) — AC-3's literal text is unreachable at S1, so it cannot be "satisfied" by this step.

AC-3 reads "when **make workbench runs to completion**, then `ps -p 62717` still exits 0."
`make workbench` -> `_ensure-dev-data` -> `scripts/ensure_dev_data.py` -> `scripts/deploy.py`.
`_port_busy` (`scripts/deploy.py:82-85`) is still the unscoped form, and live right now:

```
$ lsof -ti:8000
62717            -> _port_busy(8000) == True
```

`data/new_york/areas.json` has 37 entries, so `_upload_areas_step` is entered and
`scripts/deploy.py:117` `sys.exit`s. `make workbench` therefore never reaches
`scripts/workbench.sh` at all. The "nothing is killed" half of AC-3 holds trivially (deploy.py
only *reads*), but the "runs to completion" half is S2's. The step should claim AC-1/AC-2/AC-5
and defer AC-3 to the S2 gate. No end-to-end `make workbench` was run by anyone.

## F5 (LOW) — The pinned S1 gate `make lint` cannot fail on either of S1's source files.

`Makefile:103-106`: ruff runs over `src/ tests/ scripts/dev_env.py scripts/ensure_dev_data.py
scripts/db_parity.py scripts/check_audio_setup.py scripts/tour_batch_candidate.py`. Neither
`Makefile` nor `scripts/workbench.sh` is in that set, and there is no shellcheck target
(`grep -n shellcheck Makefile` -> no match). The step's pinned $0 gate is structurally
incapable of registering a defect in the two files S1 changed. The evidence packet concedes
this ("hand-diffed/verified separately") — that concession is the finding: there is no
mechanism, only a claim.

---

## Attacks that FAILED (the confirmation is worth something because of these)

1. **"The Makefile recipe is only regex-matched, so it might not actually work."** I extracted
   the real `flutter-ios` port-kill block from the repo Makefile verbatim, port-substituted it
   into a scratch Makefile with the repo's `SHELL := /bin/bash`, and executed it against a real
   listener + a real ESTABLISHED client. Result: `rc=0`, printed
   `Freeing :58145 — killing stale listener PID 6740 (/…/Python)`, listener dead, client alive.
   AC-1/AC-2/AC-5 hold for the Makefile launcher **by execution**, not by grep. (The test's
   regex asserts nothing about the Makefile printing anything, so AC-5 for that entry point is
   unasserted — but the code is correct.)
2. **"`set -e` + `pipefail` will abort the launcher when `ps` races a just-exited PID."**
   `scripts/workbench.sh:8` is `set -u` only — no `-e`, no `-o pipefail`. Cannot abort.
   Make recipes get plain `bash -c` (no `.ONESHELL`, default `.SHELLFLAGS`), and the compound
   line's exit status is the `if`/`|| true`, so a non-matching `lsof` (exit 1) cannot fail the recipe.
3. **"lsof ORs its selection options, so `-sTCP:LISTEN` may not actually filter `-i`."**
   Falsified on this box (lsof 4.91): live `lsof -tiTCP:8000 -sTCP:LISTEN` returns empty while
   `lsof -i:8000` shows two client-side CLOSED sockets for PID 62717 — the state filter does AND.
4. **"Another unscoped kill survives somewhere else."** `grep -rn lsof` across the repo:
   the only remaining unscoped form in executable code is `scripts/deploy.py:84`, which is a
   read-only busy *check*, not a kill, and is explicitly S2's scope. The human-facing advice
   string at `scripts/workbench.sh:80` was updated consistently.
5. **"IPv6/dual-stack listener escapes the selector."** Both launchers start uvicorn with
   `--host 127.0.0.1`; `-iTCP:PORT` covers v4 and v6 regardless.
6. **"The reuse branch skips the fix."** The `curl healthz` short-circuit at
   `scripts/workbench.sh:21` bypasses the kill entirely — but that is the pre-existing branch
   and killing nothing is the safe direction for AC-2/AC-3.
7. **`make lint`** — re-run by me: exit 0, "All checks passed!". Reconciles with the evidence.

## Residual, no reproduction (advisory only)

- The test kills **every** LISTEN-state PID on a port chosen by `_free_port()` (bind-to-0,
  close, re-bind). On a box where sibling sessions are explicitly expected (CLAUDE.md), that is
  an unbounded `kill` against a PID the test does not own. The race is narrow — if a sibling
  grabbed the port first, the fixture's own bind fails and the test raises
  `RuntimeError("listener fixture never came up")` before any kill — so I could not construct a
  reproduction. Flagged, not blocking.
