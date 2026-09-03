---
description: Plan a feature until there are zero unknowns, then build it in demoable milestone commits. Walks the real code path (reading every function on it), produces a plan where nothing is a guess, shows you the plan and the dashboard, and waits for "go". Invoke as `/team <feature request or plan>`.
argument-hint: "<the feature request, in plain English>"
---

You are running `$ARGUMENTS` through the Ondoway team process. It has two
halves. The front half produces a plan so grounded in the actual code that
implementation holds **zero surprises** — the plan is never adjusted once
execution starts. The back half, entered only after the human says **go** in
chat, executes that plan in demoable milestone commits with a live dashboard.

A plan built from excerpts and priors collapses mid-implementation; the
process below makes the plan's raw material *discoveries about this codebase*,
so a plan without real reading behind it is visibly empty.

---

# Phase 1 — the goal, in one line

State the goal in product terms, tied straight to user experience. Not "add a
column to the POI table" but "The tour should factor in opening and closing
hours of places." Every milestone in the plan must trace back to this line; a
step that doesn't serve it gets cut.

Then name the artifact the end user actually receives (the narration heard,
the screen read) and make Phase 2's walk reach that surface. A goal met in
the engine's data but absent from what the person sees or hears is not met —
acceptance judges the artifact, so the plan must cover it from the start.

If the human handed you a plan rather than a request, extract the goal from it
first, then treat their plan as a *draft* subject to the same walk as anything
else. You verify it against the code; you never execute it on trust.

# Phase 2 — walk the code path (yourself — the walk is never delegated)

**First, write the guess down.** Before looking at any code, write three lines
from what you currently believe: where this probably lives, what probably
exists already, what you'd probably have to build. This is not the plan — it
is the thing the walk exists to break. Every place the code turns out to
differ from this guess is a surprise you just prevented from happening
mid-implementation, and those discoveries are the walk's product.

Then walk:

1. **Sync and explore.** `codegraph sync`, then `codegraph explore "<the
   goal>"` — it returns the relevant functions' verbatim, line-numbered
   source plus their call paths in one command, so reading the path costs a
   command, not an afternoon. `codegraph node <symbol>` gives one function
   with its caller/callee trail; `codegraph node --file <path>` reads a whole
   file with line numbers and dependents; `codegraph callers <symbol>` and
   `codegraph impact <symbol>` give the blast radius.
   `Agent(subagent_type:'Explore')` may help locate code across surfaces, but
   it reads excerpts — it points, you read.

2. **Name the path.** Entry point (API route, CLI, screen, pipeline stage) to
   output, every function in call order.

3. **Read every function on the path — plus its callers and the tests that
   pin it.** For each one, record a one-line **contract as read**: what comes
   in, what goes out, and what it fails open (or closed) on. The fail-open
   branches are the part an excerpt never shows and the part that breaks
   plans. Source is read with `Read` or codegraph's verbatim output — never
   summarized from `grep`/`head`/`sed`/`tail` fragments; those tools are for
   logs and data. When a milestone CHANGES a function's signature or calling
   contract, enumerate that symbol's callers across the WHOLE repo
   (`codegraph callers`, plus a grep over `src/`, `scripts/` and `tests/`) —
   never just the file you walked; the caller you didn't list is the
   mid-implementation surprise.

4. **Simulate inputs through the path.** Pick 2–3 concrete inputs (a real
   POI, a real tour request, a thin/degraded case) and trace each one
   function by function using the contracts you just recorded: what comes in,
   what happens to it today, what comes out. The gap between today's output
   and the goal's output IS the feature.

5. **Find the extension point.** For everything missing, find the existing
   function/module that should grow to cover it (CLAUDE.md invariant 1: never
   build it twice; workbench and app share one implementation). Record the
   search you ran to prove no sibling already does this. A new file or new
   function is the *last* resort and needs a sentence justifying why no
   existing one could be extended.

6. **Resolve every unknown NOW.** If you don't know what a function returns
   for some input — run it, run its test, or query the DB. If you don't know
   whether a Make target exists — grep the live Makefile. Nothing is deferred
   to "verify during implementation". An unknown left in the plan is a
   surprise scheduled for later.

**Close the walk with "What the walk found":** the diff between your
three-line guess and reality — what already exists that you'd have rebuilt,
what works differently than assumed, where the real gap turned out to be.
This section *leads* the plan artifact and is what the human reads first. A
walk that surprised you nowhere means either you already knew this code — or
you didn't actually read it; on code you haven't worked in this session,
treat zero surprises as a sign to walk again, wider.

# Phase 3 — the plan artifact

Write the plan to `.claude/runs/{YYYY-MM-DD}-{slug}/plan.md` (gitignored by
the `.claude/*` rule — it is this run's scratch, never product). It opens with
**What the walk found**, then has one section per **milestone**, where a
milestone is a demoable slice: after it lands, the human can be shown
something real that works. Each milestone becomes exactly one commit.

Every milestone section must contain, in this order:

1. **What the human will see** when this milestone is demoed, in one sentence.
2. **Code path table** — every function this milestone touches or extends:
   `function — file:line-range — contract as read` (from Phase 2 step 3; a
   row you cannot fill from your own reading is a row you cannot plan on).
3. **Input traces** — the 2–3 concrete inputs from Phase 2: today's behavior
   at each step, and the exact line where the new behavior attaches.
4. **Extension point** — the ONE existing function/module being extended, and
   the duplication check that proved nothing else already does this.
5. **Unit tests** — pytest node ids (or `mobile/test/` / workbench
   equivalents), what each asserts, and why it is red before this milestone
   and green after.
6. **Integration tests** — what proves the extended path works end-to-end
   with its real neighbors (DB, Valhalla, providers per project policy).
7. **Functional test / demo command** — the command (or workbench/app action)
   that shows the milestone working, runnable by the human.
8. **Commit message** — written now, not after.

**The finished-plan discriminator.** A plan is done when nothing in it is a
guess. Scan your own plan for `TBD`, `likely`, `should`, `probably`, `verify
later`, `assuming` — any of these means Phase 2 isn't finished; go back and
resolve it against the running code. Every factual claim about this repo in
the plan carries a `file:line` you actually read this session. And **one
mechanism per extension point**: an "or", "either", or "whichever" between
design alternatives means you haven't decided, and an undecided seam is
exactly where mid-implementation surprises come from — decide now, against
the code.

Two completeness checks, done yourself:

- A milestone that doesn't trace to the Phase 1 goal → cut it.
- A part of the goal covered by no milestone → gap: add a milestone or move it
  explicitly out of scope.

# Phase 4 — alignment check, record, present, and WAIT

First re-read the goal line, then the milestone list: does executing exactly
these milestones produce exactly what the goal says — nothing less, nothing
extra? Fix mismatches before showing anything.

Then record the plan in the tracker (it is the one record no agent can
reformat, and it feeds the dashboard):

```
python3 .claude/ledger/track.py feature-add --slug {slug} --title "…" --for-whom "…" --tier 1
python3 .claude/ledger/track.py story-add --feature {slug} --id S1 --text "…" --said-by owner
python3 .claude/ledger/track.py issue-add --story S1 --id M1 --name "…" --test-command "…" --files src/… tests/…
```

One `story-add` per user story in the human's own words; one `issue-add` per
milestone, carrying its demo/test command and files.

Tier is one line, by the paths touched (highest wins): **1** = `src/`,
`tests/`, `scripts/`; **2** = tour content, `mobile/`, `src/api/routes/`,
`frontend/`; **3** = `Makefile`, `.claude/`, deploy/infra, DB/data.

**Start the dashboard now** — run it, don't mention it — in the background:

```
python3 .claude/ledger/track.py serve --port 8010
```

It prints its URL as JSON on the first line. Paste that URL as the FIRST line
of your reply. The human watches the feature build up piece by piece there;
that is the dashboard's entire point.

Present, in one screen:

1. The goal (one line) and what is explicitly out of scope.
2. **What the walk found** — the discoveries, briefly.
3. The stories, each in the human's own words.
4. The milestones: name, what the demo shows, the test command. (Full traces
   stay in `plan.md` — link it, don't paste it.)
5. One plain question:

> Say **go** to build this, or tell me what to change. Nothing has been built
> yet.

**End your turn and wait.** No approval exists until the human says so in
chat. If they ask for changes, amend the plan and the tracker rows and
re-present.

# Phase 5 — execute, one milestone at a time (after "go")

Record the approval first — you are transcribing their decision, never making
it:

```
python3 .claude/ledger/track.py approve --feature {slug} --by owner
```

Then for each milestone, in dependency order:

1. `step-status --id M{n} --status in_progress`.
2. Write the failing test from the plan; see it red.
3. Make the change the plan specified — at the exact attachment points the
   plan named. Before modifying any source file, read the ENTIRE file
   (CLAUDE.md rule 5) — Phase 2 read the path; modification needs the whole
   file's context, current as of now.
4. Test green, then `make lint`. (Per-file test runs: `make test-file
   FILE=tests/test_x.py` — foreground, read the result; never poll a log.)
5. **Demo it**: run the milestone's demo command and show the human the
   output (screenshot, transcript, or the command itself to click). Every
   milestone shows the feature further along — that's what the dashboard and
   the demo are for.
6. Commit — the message written in Phase 3. `step-status --status completed`.

**If reality diverges from the plan — stop.** A wrong signature, a test that
was supposed to be red but is green, a function that doesn't behave as the
plan traced: that is a *planning* failure, and improvising a fix on the spot
is how half-baked implementations happen. Say plainly what the plan got
wrong, re-walk the affected path (Phase 2 rules), amend the plan and tracker
for the remaining milestones, and show the human the diff in the plan before
continuing. A divergence hidden is worse than a divergence found.

Run the full bar (`make audit`) once, after the last milestone — not between
steps.

# Phase 6 — the end-to-end demo

Run the whole feature the way the human would use it — the real tour, the
real screen, the real workbench page — and show them. Not "tests pass": *it
works*, visibly. For tier 2+ work, also run
`Agent(subagent_type:'acceptance')` on the produced artifact and
`Agent(subagent_type:'qa')` for the undo test on the new tests, and paste
their verdicts. The human, not you, decides it's done.

---

## Rules

- **The walk is yours.** Locating code may be delegated; reading it may not.
- **Read functions whole, through tools that show them whole** — `Read` and
  codegraph's verbatim output. Excerpt-planning is the root failure this
  command exists to prevent; before *modifying* a file, CLAUDE.md rule 5
  (entire file) applies.
- **Extend, never duplicate** (CLAUDE.md invariant 1). Every milestone names
  its extension point and the search that cleared it.
- **No guesses survive Phase 3.** Unknowns are resolved by running things
  now, never deferred.
- **The plan never changes silently.** After "go", any divergence stops the
  line and is shown to the human as a plan amendment.
- **You never bless your own plan.** The human approves in chat; `track
  approve` records, it never decides.
- Genuine product trade-offs are escalated as a crisp either/or with a
  recommendation — never guessed silently, never buried.
- Open-ended discovery ("find and fix whatever's wrong") is the wrong task
  for this command — use `Skill(proactive-audit)`.
