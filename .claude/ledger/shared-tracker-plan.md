# Shared tracker — the one source of truth every agent reads and writes

Created 2026-08-31. Status: **All five phases DONE and green 2026-09-01. Uncommitted —
the owner commits.** The owner approved building in phase order and told the assistant
not to stop between phases.

## Carry — one open item, and it is a design gap I introduced

The four text carries recorded here on 2026-09-01 (a dead `AGENTS.md` reference,
a wrong `CLAUDE.md` rule number, a citation to a contract that no longer exists,
and stale `team.md:NN` line numbers in the table below) were all fixed the same
day. One remains:

- **A Tier 0 step cannot honestly pass the ladder.** Not because `validateCommand`
  refuses it — it does not; a `Docs/x.md` step with a well-formed
  `make test-file FILE="…::…"` validates fine. The problem is the atomic rule the
  engine actually enforces: a step is proved by one command that goes RED before the
  change and GREEN after, and the QA gate reverts the change to confirm the test really
  goes red. No prose-only edit can make a pytest node id do that, and `deriveGates`
  hands a docs step only `make lint`, which proves nothing about prose. So `team.md`'s
  tier table offers a Tier 0 that the red-first protocol and the undo test cannot
  certify. Open: decide what proves a docs change, or say plainly that Tier 0 work does
  not go through `/team`.

The two commands that gate this work — read the counts from the run, never from here,
which is the mistake this file already made once:

    node .claude/team-engine.test.js
    .venv/bin/python -m pytest .claude/hooks/tests/ -o addopts= -q

This file lives under `.claude/ledger/` and not under `specs/` because everything it
describes is agent supervision, not product. Nothing here ships in the tour app, and
nothing here belongs in `make test`. Precedent: `.claude/team-engine.test.js:6-9`.

`.gitignore:253` ignores `.claude/*` with an allowlist beneath it, and
`.gitignore:257` already allows `.claude/ledger/`. That directory did not exist yet.
It is where this whole build lands.

## The problem, in one line

Every record of what an agent did is written by that same agent, in prose, into a
file it can reformat at will. There is no place the owner can look that an agent
did not author.

## What the owner asked for

A live sprint-and-issue tracker that all agents share and write to and read from.
One source of truth that is not memory and not a transient markdown file. Plus a
live dashboard showing the top level, the current micro level, and the state
machine of agents looping. Plus a manager that forces a replan when progress
declines.

## Owner ruling on the schema file, 2026-08-31

Deleting `specs/_templates/team-state.schema.json` was my inference, not the guard's.
It is tracked in git and referenced by the preflight prompt in `.claude/team-engine.js`
and by Step 4 of `.claude/commands/team.md`. The owner ruled on it: **agreed, delete
it.** Both references move onto the database in P2. This is settled — do not re-raise it.

**A note on citations in this file.** P0 inserted a hundred-odd lines into
`.claude/team-engine.js` and broke every `path:NN` reference below it — caught by the
shadow, not by me. References here now name the SYMBOL or the section, not the line,
for the same reason the engine's own `dkey` is line-free: lines shift after a fix.

## The two decisions, locked by the owner 2026-08-31

1. **Extend `/team` and `.claude/team-engine.js` in place.** No second engine.
2. **Get it right inside Ondoway first.** Extracting a reusable kit for other
   projects is explicitly OUT OF SCOPE for this work.

## The third decision, forced by the no-flinch rule

**The database is the only place status lives. Every other copy is deleted.**

Two copies are deleted, not deprecated:

1. **`state.json` as a status store.** It is exactly the "transient file" the owner
   named. The plan, the steps, the acceptance criteria, the approval and every status
   move into the database. `specs/_templates/team-state.schema.json` is deleted; the
   SQLite schema is the contract. Existing `specs/*/state.json` files stay on disk as
   history of finished runs — nothing reads them after this change, and there is no
   import and no fallback path.

2. **The engine's in-memory status mirror — the `scribe` helper in
   `.claude/team-engine.js`.** The `live.status = status` write-back is deleted, and
   `statusOf` no longer reads `L.steps`. Instead `track` prints the full current status of every issue on every
   write, and the engine's dependency check uses that response. The engine holds the
   database's own answer from a moment ago, not a copy it maintains itself.

   This removes the cause of the stranding bug rather than guarding it: the bug was
   that the mirror could go stale against the file. With no mirror, there is nothing
   to go stale. The existing guard check `dependency-unblocks-dependents` in
   `.claude/team-engine.test.js` is rewritten to assert the engine uses the returned
   status, and its stub returns status from a fake database.

## Everything this work touches lives under `.claude/`

The tracker's job is to make the assistant's own record trustworthy. Its failure
would mean the record is untrustworthy, not that the tour product is broken. So:

- The command is `.claude/ledger/track.py`.
- The database file is `.claude/ledger/tracker.db`, with a `.gitignore` line of its
  own — it is binary and churns on every write, so it is never committed.
- Its tests go in `.claude/hooks/tests/`, the established home for guard tests, which
  already holds eight of them.
- The hook that blocks direct writes to the database stays in `.claude/hooks/`.
- The product tree — `src/`, `mobile/lib/`, `tests/`, `scripts/`, `frontend/` — is not
  touched by any phase below.

## What already exists (read this turn, cited)

- `.claude/commands/team.md` — the front half. Plans into atomic steps, prices the
  fan-out, shows the human, waits for "go".
- `.claude/team-engine.js` — the back half. Preflight → Build → Gate → Challenge →
  Rule → PhaseGate → Close, with real termination caps.
- `.claude/team-engine.test.js` — pathological modes guarding those caps, plus (since
  P0) direct checks on the validators. It prints its own shape and check counts; read
  them from the run, never from here.

So this is an extension job. It maps onto the owner's requested pipeline:

| Owner's role | Where it already lives |
|---|---|
| Initializer | `.claude/settings.json` registers `code-grounding-guard.py` on `UserPromptSubmit` with the status message "codegraph sync: the index every agent reads from" |
| PM | `team.md` Step 2 — requirements, now written as stories. The human approval gate is separate: Step 4 ends the turn and waits, Step 5 records the go-ahead with `track approve` |
| Planner | `team.md` Step 3 — the atomic steps under each story |
| QA | the `gate:` agent call in the step loop — `GATE_RESULT` plus the UNDO TEST |
| Implementer | the `build:` agent call in the step loop |
| Verifier | the `gate:` → `challenge:` → `rule:` sequence in the step loop |
| Manager | `team.md` calls the front half the "PLANNER-MANAGER", but nothing measures progress or forces a replan. **That does not exist.** |
| Shared database | **does not exist** |
| Dashboard | Two product surfaces exist. `make dashboard` is the Neo4j graph dashboard (`src/server.py:1`, port 8080 at `:19`, one route `/api/status` at `:90`). `make workbench` is the tour editor's surface (`scripts/workbench.sh:2-3`, API on port 8000, opens `frontend/review.html`). Nothing shows agent state. **That does not exist.** |

## The crack this work closes

The `scribe` helper in `.claude/team-engine.js` spawns a **haiku agent** and asks it to
edit `state.json`: *"Use a small python/jq edit, never a rewrite from memory."* An
agent writes the record of its own step's outcome. The same shape repeats at the final
status write in the step loop and at the `scribe:run` call that writes the run summary.

The owner's instinct is exactly right: the record must not be authored by the thing
being recorded.

## Honest statement of what can and cannot be enforced

`.claude/team-engine.js:65-66` records a measured fact: **PreToolUse hooks do NOT
fire inside the Workflow runtime.** A hook therefore cannot block a workflow-spawned
agent from writing wherever it likes.

So enforcement has three layers, strongest first:

1. **`track` re-derives instead of trusting.** When an agent claims a step is done,
   `track` re-runs the step's own test command and records the exit code **it**
   observed. An agent's claim never becomes a row on its own word.
2. **A main-session hook** blocks direct writes to the database file. This covers the
   interactive session, not the workflow.
3. **Prompts** tell workflow agents to use `track`. This is persuasion, not a gate.

Stated in the same idiom the engine already uses for `ALLOWED_REPRO`
(`.claude/team-engine.js:57-66`): layer 3 *refuses to pay attention*, it never
*refuses to run*. Layer 1 is what actually makes lying useless.

## Tier

Touches `.claude/` → **Tier 3** by the path table in `.claude/commands/team.md`.
That means a skeptic panel of three and human sign-off.

## The five phases

### P0 — DONE 2026-09-01. Uncommitted; the owner commits.

`/team` could not build this, because a step touching `.claude/` was refused before a
single agent ran: `test_command` had to be exactly
`make test-file FILE="<path>::<pytest node id>"`, and a step proved by
`node .claude/team-engine.test.js` aborted the whole run as `invalid_commands`. There
was also no `gate_commands` branch for `.claude/` at all.

**What was planned, and why it changed.** The plan said "teach preflight" — meaning
reword the preflight agent's prompt. That would have been unguarded by construction:
`command_valid` was decided by the preflight AGENT from prose rules, and
`.claude/team-engine.test.js` **stubs that agent**, so no check could ever reach the
rule. A prompt-only fix is a rule with no test.

**What landed instead.** Validation moved out of the prompt and into the engine as two
pure functions, `validateCommand` and `deriveGates`, sitting between marker comments so
the guard can lift them out and call them with no engine running. The engine overwrites
whatever the agent reported before the `invalid_commands` gate reads it.

- A step whose files are **all** under `.claude/` is a supervision step, proved by
  `node .claude/team-engine.test.js` or by
  `uv run pytest .claude/hooks/tests/<file>.py -o addopts= -v`.
- A step whose files are **all** product code keeps the exact `make test-file` shape,
  and a bare `-k`, `LIVE=1`, or a missing node id are still refused.
- A **mixed** step is refused and must be split: one step, one kind, or the gate is
  ambiguous.
- Gates derive from the files. A supervision step is gated by the thing that proves it;
  an engine edit additionally re-runs the engine guard, because the close gate never
  does.

The one check that could not move is "does this Make target exist in the live Makefile" —
that needs a filesystem the workflow runtime does not have. It stays with the agent, and
it is now the only validation left in the prompt.

**Proof.** `node .claude/team-engine.test.js` went from `3 of 98 checks FAILED` to
green. That was P0's own count; P2 and P4 have since added shapes and checks, so read the current figures from the run rather than from here. The shape P0 added is
`supervision-step`; the new direct checks are `validator:*` and `gates:*`.

**Cost, banked.** One LLM judgement per run became string comparison, and every future
run stops paying a model to read a command line.

### P1 — DONE 2026-09-01. Uncommitted; the owner commits.

`.claude/ledger/track.py` and `.claude/hooks/tests/test_track.py` are built and green. `.claude/ledger/tracker.db` and its WAL siblings are gitignored — the
schema is version-controlled in `track.py`, the rows are this machine's run.

The refusal works. `step-status --status completed` runs the issue's own command
itself, reads the exit code from `subprocess.run`, and declines the row unless it is 0.
There is deliberately no flag to supply an exit code, because a flag to supply one is a
flag to lie with. A refused claim still writes its `test_runs` row and still prints the
full status set, so a caller that loses learns as much as one that wins.

Two more refusals landed with it: a story cannot reach `Done` while any issue under it
is unfinished, and an issue cannot be added to a story that does not exist. `events` is
append-only, enforced by SQLite triggers rather than by convention.

`track serve` is NOT built — it is P3, and it renders `.claude/ledger/dashboard-mockup.html`.

#### What P1 built, in full

- `.claude/ledger/track.py`, using Python's stdlib `sqlite3` in WAL mode. No new
  dependency and no product dependency at all. It is invoked as
  `python3 .claude/ledger/track.py`, the same way the twelve Python hook ENTRIES in
  `.claude/settings.json` are invoked — twelve entries, nine distinct files, because
  three guards are registered twice. The other two entries are shell scripts,
  `team-gate.sh` and `render-deploy-watch.sh`.
- One database file per checkout: `.claude/ledger/tracker.db`, plus its `.gitignore`
  line.
- Tables:
  - `features` — one row per feature, in plain words. What it is for, who for, the
    tier, and when it was created. Tier lives here because it is set once for the
    whole approved batch, mechanically from the paths the work touches.
  - `stories` — **one row per user story, in the user's own words**, written by the PM
    and belonging to a feature. This is the unit the dashboard is organised around
    (owner's ruling 2026-08-31: "divide by feature / story"). A story carries which
    state it is in — PM, Planner, QA, Implementer, Verifier, Done — and how many times
    it has been sent back.
  - `criteria` — the acceptance criteria, one row each, belonging to a story.
  - `issues` — one row per step, belonging to a story. Status, owner role, test
    command, files, depends_on, attempts, the criteria it covers.
  - `events` — append-only. Every state transition, with who, when, and why. This is
    what draws the state machine on the dashboard. Never updated, never deleted.
  - `test_runs` — command, exit code as observed by `track` itself, output excerpt,
    timestamp.
  - `approvals` — the human's go-aheads, as rows.
- Subcommands: `track init`, `track feature-add`, `track story-add`, `track issue-add`,
  `track step-status`, `track approve`, `track show`, `track health`, `track serve`.
- `track step-status --status completed` **refuses** unless it re-ran that issue's test
  command itself and saw exit 0. That refusal is the whole design.
- A story only moves to its next state when every issue under it is completed, so a
  story cannot be advanced by an agent's say-so either.
- Every write subcommand prints the full current status of every story and issue under
  the feature, so a caller never needs to keep its own copy.
- Tests in `.claude/hooks/tests/test_track.py`, out of `make test`.

### P2 — DONE 2026-09-01. Uncommitted.

Landed in the engine, guard still green:

- **`scribe` is gone.** Its three call sites now run `writeStatus`, a courier handed an
  exact `python3 .claude/ledger/track.py step-status --id … --status …` command line.
  A courier cannot editorialise a flag, and `track` re-derives a pass by running the
  test itself, so it cannot promote a step by asserting anything either.
- **The in-memory mirror is deleted.** `statusOf` reads `liveStatus`, a map seeded once
  from preflight and refreshed only from what `track` prints back. Nothing in the engine
  assigns a status it invented, so there is nothing left to go stale — the cause of the
  8-of-10 stranding is removed rather than guarded.
- **The run-summary agent is deleted outright.** It merged a JSON blob into
  `state.json`'s `run` key; that store is gone, and everything it held is already an
  `events` or `test_runs` row written by something that observed it. One fewer agent per
  run — the fan-out estimate dropped by one across every shape.
- The harness stub that matched `scribe` is now a fake database keyed on the `track:`
  label, so `dependency-unblocks-dependents` proves the engine reads the returned set.

The front half landed with it: `.claude/commands/team.md` Step 4 writes the feature,
its stories and their issues through `track`; Step 5's approval is `track approve`; the
preflight agent reads `track show --json`; and `specs/_templates/team-state.schema.json`
is deleted. The engine's own abort messages no longer name `state.json` either — the two
that told a human to go and edit it now tell them to run `track approve`.

#### What P2 covers, in full

- `.claude/commands/team.md` Step 4 writes the feature, its stories and their issues
  with `track feature-add`, `track story-add` and `track issue-add`, instead of writing
  `state.json`. The PM writes the stories in the user's own words; the Planner hangs
  issues off them.
- The preflight agent call reads the feature with `track show --json` instead of reading
  `state.json`.
- The approval gate — the `approved_by_human !== true` refusal before fan-out — reads
  approval from the `approvals` table instead. `track approve` is the only way a row
  lands there, and it records who approved and when.
- All three `scribe` sites become the agent's own last command, not a separate call:
  the in_progress write at the top of the step loop, the final status write at the
  bottom of it, and the `scribe:run` summary at close. The agent already has a shell;
  `track` re-derives, so it cannot lie in the row it writes.
- Delete the `scribe` helper and its `live.status = status` mirror; `statusOf` reads the
  status set returned by the most recent `track` call.
- Delete `specs/_templates/team-state.schema.json`.
- Rewrite the harness stub that matches on the `scribe` label prefix in
  `.claude/team-engine.test.js` to be a fake database returning issue status, and
  rewrite `dependency-unblocks-dependents` to assert the engine uses that returned
  status.
- **Carry from P0:** `.claude/commands/team.md` still calls the
  `make test-file FILE="<path>::<node id>"` shape "non-negotiable", and
  `specs/_templates/team-state.schema.json` pins it as a regex. Both are fixed now: the
  prose is rewritten and the template is deleted. The ENGINE accepts supervision steps now;
  the front half still tells a planner it cannot write one. P2 fixes the prose, and
  deleting the template removes the pattern with it.

### P3 — DONE 2026-09-01. Uncommitted.

`track serve` is built, tested by `.claude/hooks/tests/test_track_serve.py`, and renders
the story-first page the owner approved. It opens the database read-only through a
`file:…?mode=ro` URI, so a bug in a handler cannot turn the dashboard into one more
surface an agent could use to look finished — and a test asserts the file's bytes are
unchanged after serving.

It refuses to bind 8000, 8001, 8080, 7687 or 7688 by name, with the reason. Binding one
would take a running service down and the failure would look like the dashboard working.
`--port 0` lets the OS pick and the bound port is printed, so a caller never guesses.

#### What P3 covers, in full

**Three views, three different named users. This is the one exemption to "never build
it twice", and every user is named here in those words.**

- `make workbench` (`scripts/workbench.sh:2-3`, API on port 8000, opens
  `frontend/review.html`). Its user is **the tour editor**, working on Ondoway tours.
- `make dashboard` (`src/server.py:1`, port 8080 at `:19`). Its user is **the person
  inspecting the Neo4j graph** — node and relationship counts, traversals, one route
  `/api/status` at `src/server.py:90`. It cannot serve the editor: it exposes no
  `/api/v1`, which is what `review.html` calls (`scripts/workbench.sh:5-7`).
- `track serve` serves the agent view. Its user is **the owner watching agents build
  software**, who needs to see whether a run is progressing or spinning.

None of the three shows another's data, and none can answer another's question. The
agent view therefore does not extend `src/server.py`, and it must not bind **8000**
(the editor's API), **8080** (the graph dashboard) or **:8001**. Its port is pinned in
this phase.

- `track serve` — stdlib HTTP server, read-only, polls the database.
- **The story is the organising unit at every level**, never the step. Four bands, top
  to bottom:
  1. **The feature**, in plain words, with its stories as chips and one line saying
     whether the feature is at risk and which story put it there.
  2. **One state machine per story**, drawn in the owner's role names — PM → Planner →
     QA → Implementer → Verifier → Done — with the loop-backs shown: Verifier sends a
     story back to the Implementer to fix, and the Manager sends it back to the Planner
     to replan. A story's code steps sit collapsed underneath its own machine.
  3. **The active story's detail** — which step, which agent, the exact command.
  4. **The event log**, every row tagged with the story it belongs to — or with the
     feature, for the events that belong to the whole batch rather than one story.
- A stuck machine names its story; that story names its feature. That is the whole
  bigger-picture link, and it is why nothing on this page is labelled by step id.
- `.claude/ledger/dashboard-mockup.html` is this phase's rendering template. The owner
  approved it 2026-09-01 ("Love it") after the story-first rebuild. Build P3 against it.
- Agents never write to the dashboard. It only reads the database.

### P4 — DONE 2026-09-01. Uncommitted.

`track health` computes progress and the replan decision from the event log and the
recorded exit codes — never from anything an agent said. Three triggers, all arithmetic:
a story sent back twice without moving, a test that went green then red, an issue piling
up attempts with no state change.

The engine calls it between steps on the phase-gate cadence, through a courier told not
to interpret the answer. On a trigger the run stops with `replan_required`, names the
story, and does not spend the close bar. Guarded by the `replan-required` mode and the
three `manager-*` checks.

The REPLAN is an agent. The DECISION to replan is never an agent.

#### What P4 covers, in full

- Progress is **computed, never reported**. `track health` derives it from the event
  history alone.
- Replan triggers are arithmetic, not judgment:
  - a test that went green then red,
  - an issue reopened twice,
  - N attempts on one step with no state change.
- The engine's phase-gate courier calls `track health` between steps. On a trigger the
  engine aborts with `stopped: 'replan_required'` and the run stops.
- The **replan** is an agent. The **decision to replan** is never an agent.
- A new cap means a new entry in `MODES` and the matching entry in `REQUIRED_MODES` in
  `.claude/team-engine.test.js`. That pair is what the check
  `covers-every-pathological-mode` enforces mechanically — it compares the two lists
  and nothing else. A row in the header coverage table is asked for by that check's
  failure message, not enforced by it, so it is on whoever adds the cap to write.

## What every step of this work must carry as its gate

The engine's own guard runs at **preflight only** — the preflight prompt tells the agent
to run it and set `infra.engine_guard`, and the `engine_guard !== true` refusal reads
that before fan-out. The close gate never re-runs it.

So every step that edits `.claude/team-engine.js` must run
`node .claude/team-engine.test.js` as its gate, and every step that edits
`.claude/ledger/track.py` must run
`uv run pytest .claude/hooks/tests/test_track.py -o addopts= -v`. Neither belongs in
`make test`: `pyproject.toml` sets `testpaths = ["tests"]`, so `.claude/hooks/tests/`
is outside the product suite by construction.

Since P0, `deriveGates` handles half of that automatically. For a supervision step it
copies the step's own `test_command` into its gates, and it ADDS
`node .claude/team-engine.test.js` whenever `files[]` touches the engine — so an engine
edit cannot ship without the guard that proves its termination caps, even if the planner
forgets. The tracker's own test command is still the planner's to name; `deriveGates`
only propagates what the step already declares.

## Out of scope

- Extracting a portable kit for other projects (owner's decision 2).
- Changing the model assignments in the engine.
- Any change under `src/`, `mobile/lib/`, `tests/`, `scripts/` or `frontend/`.
- Any commit. The engine never commits; the human does.
