# Tour-Algorithm Redesign — Implementation Plan (Phases 1–8)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps
> use checkbox (`- [ ]`) syntax for tracking. Execution runs through the `/team` ledger
> flow (`CLAUDE.md` §4): each phase becomes one ledger, never eight at once.

**Goal:** Land the redesign of `specs/2026-08-07-tour-algorithm-redesign/01-design.md` —
from clock-native planning (Phase 1) to the meet-or-beat release gate (Phase 8) — with
every phase closed by a demo the owner watches or hears.

> **PHASE 0 WAS REMOVED, 2026-08-07, BY OWNER ORDER, AND IS NOT COMING BACK.** It proposed
> landing the in-flight time model by auditing the existing suite, re-baselining the
> goldens and driving `make audit` to green. Every one of those is work aimed at the tree
> as it is; this is a redesign, and it made the inherited tests the deliverable. The tell
> was its demo: D0 was "the flagship tour plans end to end", which is a demonstration of
> what already works. Every other demo in this plan shows a behaviour that did not exist
> before.
>
> **What was real inside it, and where it now lives.** The uncommitted time-model work —
> the change from *walking + talking* to *walking + being somewhere* — is the pricing
> engine under promises-and-fabric and genuinely must land first. It is a COMMIT, not a
> phase. **Phase 1 opens by committing it, with the inherited suite red and no requirement
> that it be otherwise** (§0.7). Phase 1 is the first phase that cannot function without
> it: `contract.py`, `routing.py::route_planning_budget` and `selection.py` all carry both
> changes.
>
> **No phase of this plan takes "the existing suite is green" as its goal.** A phase's
> deliverable is a behaviour the design names, proven by tests written FROM the design;
> inherited tests that stand in the way are deleted first (§0.1, §0.7).

**Architecture:** One planner (`src/tour/selection.py::select_route`) generalises from
"one protected endpoint" to "a set of protected promises on a clock, connected by
fabric" (design §3). One replan brain stays on the server; the phone only selects from a
precomputed contingency set (§4.6). Data rows 6.1–6.9 land through the established
audited-enrichment pattern (`scripts/poi_visit_duration.py` + its command doc + its
structural test). Every seam that must not fork gets a source-scanning test in the
`tests/test_tour_one_engine.py` genre.

**Tech stack:** Python (FastAPI + Neo4j + Valhalla), pytest via `make test-file
FILE=<node id>` (never `-k`), Flutter for the phone, Playwright for the workbench.
Everything runs through Makefile targets with preflight lines.

**Status of this document:** Phases 1–2 are step-level and executable now, against the
tree at base `c8a35a75` + the uncommitted time-model work. **Phases 3–8 are deliberately
coarser** — per design §9, each phase is re-planned at step level only once the phase
before it has demoed, with its files read in full at that moment, against the tree as it
then is. A step-level plan for Phase 5 written today would be a plan written from memory
of code that will have changed — Failure 2 wearing a different hat.

---

## 0. The binding rules (read before executing anything)

These operationalise design §10 and the owner's instructions of 2026-08-07. They bind
every session and every subagent that executes any part of this plan.

### 0.1 Tests derive from the NEW design — the owner's ruling, 2026-08-07

Stated by the owner in exactly these terms: we are doing a huge redesign, so tests are
defined from the new design; stop forcing current tests to fit; if that means throwing
out current tests and writing new ones from scratch, do so.

Operationally:

1. **Every new gating test cites its source** — a persona file and line, a section of
   `01-design.md`, a rule id in the quality standard (S1–S10, P1–P7, C1–C12, G1–G8), or
   a named panel finding. A test citing nothing may not gate (design §7.5).
   `tests/test_tour_visit_time.py` is the house model: every test docstring quotes the
   persona line it enforces.
2. **An old test that pins the old algorithm's behaviour is DELETED, not adapted.**
   Frozen stop orderings, absolute overlap hit-counts, duration sweeps calibrated to old
   constants, stop-count assertions — all of it. If the new design still needs the
   *invariant* underneath (e.g. "two cost paths must agree"), the replacement is written
   fresh from the design with a citation, asserting the invariant, never the snapshot.
3. **A test is NEVER edited to make it pass.** A wrong test is a written decision with a
   reason, recorded in the phase ledger, escalated if disputed — never a quiet edit.
4. Deleting a test file wholesale is an expected outcome, not an escalation.
5. **A green existing suite is never a deliverable.** No phase's goal, acceptance
   criterion, or demo may be "`make audit` passes" or "the red tests are green". The bar
   at a phase close is the phase's own demo plus the tests that phase WROTE from the
   design. Tests inherited from before the redesign either earn a citation or are
   deleted; time spent nursing one back to green is time not spent building the design.

### 0.2 Read-before-plan (design §10.1)

- A step may not enter a ledger until every file it will change has been read end to
  end. §1 below records the evidence for every Phase 1–2 step in this plan.
- **A discovery during implementation that this plan did not know is a PLAN DEFECT:
  stop, log it in the phase ledger, amend this plan, then continue. Never absorb it
  silently.**
- Files still not read in full (they are touched only by Phases 3+ and are a hard
  precondition on planning any step that touches them, at re-plan time):
  `src/tour/quality_certification.py`, `src/tour/artifact.py`,
  `src/tour/place_materialization.py`, `src/tour/claim_dedup.py`,
  `src/tour/validation.py`, `src/tour/degradations.py`, `src/tour/spatial_check.py`,
  `frontend/review.html`, `mobile/lib/pages/trip_itinerary_page.dart`,
  `mobile/lib/services/trip_service.dart`, `mobile/lib/services/audio_service.dart`,
  `src/tour/generation.py` *(read in full 2026-08-07, session 2, for the dedup fixes)*,
  `src/tour/beat_select.py`, ~~`src/tour/density.py`~~ *(read in full at the Phase 2
  re-plan, 2026-08-07 — see §3's ledger addendum)*,
  `src/tour/authoring.py`, `src/tour/premium_tour.py`, `src/tour/options.py` (partial
  reads or unread — see §1 for exactly what was read).

### 0.3 Atomic steps, declared breakage, budgets (design §10.2–10.6)

- A code step is ONE file-scoped change proven by exactly ONE executable command that
  goes RED before and GREEN after: `make test-file FILE=<pytest node id>`, never `-k`.
- The undo test is mandatory per step: revert → RED, restore → GREEN, all four runs
  pasted into the ledger.
- Each step declares which tests it expects to turn red and which later step turns them
  green. **A red test not on the declared list is an immediate stop.** A phase may not
  close with declared breakage outstanding.
- Step budget: two attempts at one mechanism, three mechanisms maximum, then stop and
  report all three errors verbatim. No fourth attempt.
- Work items (marked `W`) are measurement, audit, decision, demo, or commit gates — they
  produce evidence artifacts, not code diffs, and are exempt from the RED→GREEN form.
  Turn gates (marked `T`) end the session's turn and wait for the owner in chat.

### 0.4 Never build it twice (design §10.8)

- Every step that creates a new file, module, or function carries the mandatory field
  **Extends** — the existing thing considered and why it could not be extended. No
  answer, no step.
- `make dedup-review` gates every PHASE close, not just commits.
- Seams that must not fork get a SOURCE-SCANNING test (a behaviour test cannot see a
  duplicate). The genre exemplar is `tests/test_tour_one_engine.py`; new deletion
  guards extend that file rather than inventing a mechanism.
- A replaced path is deleted in the SAME phase that replaces it, never "later".

### 0.5 Demos close phases; suites do not

A phase is done when the owner has watched or heard its named demo (design §9). The
first work item of every phase builds or extends the harness that shows the before and
the after (§10.9). Any change that reshapes what a tourist experiences goes through the
eleven-persona panel BEFORE it is decided (`CLAUDE.md` §1.10); the panel of 2026-08-07
(`03-panel-findings.md`) covers the design itself, not future deviations from it.

### 0.6 Tree-state safety

- Base commit `c8a35a75`. ~274 changed paths, NOTHING committed, no rollback point. The
  owner also carries ~172 uncommitted files of their own. **Never run `git checkout`,
  `restore`, `stash`, `reset`, or `clean` on a tracked file.** Commits stage explicit
  path lists — never `git add -A`, never `git add .`.
- A lane never touches another lane's containers or the shared Valhalla
  (`CLAUDE.md` §3 R2).
- Two documents in this repo were found lying about state on 2026-08-07 (a handoff
  claiming a decision ON that the code holds OFF; a comment claiming pace 4.5 while the
  code holds 3.0). **Verify every state claim against the code before acting on it.**
  This plan records code-verified state only; where it relies on an unverified claim it
  says so.

### 0.7 Step kinds — and exactly which rules each kind IGNORES

Every step carries a kind tag. **The tag says which rules do not apply to it.** Nobody
executing this plan should have to ask, and nobody should have to be told twice.

**Two inherited rules are suspended for the WHOLE plan, every step, no exceptions:**

1. **`CLAUDE.md` §5's "the bar is `make test`: every shard, 0 failures, 0 skips" DOES NOT
   APPLY here, and neither does its "the step 0 baseline must be green before work
   starts".** The inherited suite is red on purpose and stays red while the redesign
   lands. No step is blocked, delayed, re-scoped or re-planned because a test written
   before this redesign is failing. Do not run `make test` to decide whether to proceed.
2. **`CLAUDE.md` §8's pre-commit item "`make test` passes every shard" DOES NOT APPLY.**
   Commits land with the inherited suite red.

**The full bar returns as a gate at PHASE 8, and only there** — the phase whose deliverable
IS the gates. By then every inherited test has been deleted or re-derived from the design,
so `make audit` green means something again. Before that it means only that nothing new
was built.

**THE PHASE CLOSE BAR** — the complete list of what must be green to close phases 1–7:

- the tests THAT PHASE WROTE, all green;
- the WHOLE `tests/` tree once, on the final code, with the dev graph and Valhalla
  up — FREE tests only (`-m "not paid and not recorded"`, §0.9.2); `paid` and
  `recorded` tests run only where the phase touched them, and the judge reads the
  pasted log rather than re-running paid tests (owner ruling 2026-08-22: the whole
  suite was being run several times per close against real model calls). AMENDED at
  the Phase 6 close (2026-08-21): the judge made the whole-tree run a PROVE-FIRST
  condition, and it found ten failures the phase's own files did not cover (five
  fixtures hand-sized for the old stop ceiling in OTHER files, one rule the phase
  changed that an older test in another file still asserted, and four red since the
  Phase 5 commit — its seam import and its underfill line — because Phase 5's close
  ran only its own files too). "The tests that phase wrote" is necessary, not
  sufficient; the whole tree is run ONCE, never twice. **PLAN DEFECT 21, found by the
  Phase 7 judge (2026-08-23, §0.2):** the words above say "the WHOLE tests/ tree" but
  the command cannot deliver it — pyproject declares no `paid`/`recorded` marker (the
  `-m` flag deselects nothing) and its addopts `--ignore` the ten golden / grade /
  invariants / live / cloud files, so `pytest tests/` is the HERMETIC SHARD only.
  AMENDED: a phase close runs the hermetic shard ONCE **plus the three FREE excluded
  shards** (`_test-golden`, `_test-grade`, `_test-invariants`) once each, with any red
  DISPOSED in writing (an 05-audit row, a parent-commit comparison, or a fix) — and
  paid/recorded live files still only where the phase touched them;
- `make lint`, zero errors;
- `make dedup-review` clean (§0.4 — the anti-fork guard, never suspended);
- the phase's DEMO, watched or heard by the owner.

That is the whole list. `make audit` is not on it.

**The kinds:**

| Tag | What it is | What it IGNORES |
|---|---|---|
| `[DEMOLISH]` | Deletes inherited tests, or a code path the design replaces | §0.3's RED→GREEN form, the mandatory undo test, "a red test not on the declared list is an immediate stop", and §0.4's **Extends** field. A deletion has nothing to extend and nothing to undo-test. Its proof is that a NAMED SURVIVOR still collects and `make lint` is clean |
| `[BUILD]` | Writes new behaviour plus the test that proves it | Nothing beyond the two suspensions above. Full discipline: RED→GREEN on one node id, the undo test, **Extends**, and a citation (§0.1.1). This is where the rigour lives |
| `[DATA]` | An enrichment pass over the corpus | The RED→GREEN form and the undo test — a data pass has no unit under test. KEEPS: the structural test, the one-sentence justification per value, and human review. Its cost is stated in one clause and spent, never raised as a question (`CLAUDE.md` §1.12) |
| `[GATE]` | A measurement, a capability probe, a persona panel, a demo, a judge consult | All of §0.3 — it produces evidence, not a diff. It never has a `test_command` |

**Every phase OPENS with its `[DEMOLISH]` step.** Clearing the inherited tests that stand
in front of a phase's deliverable is the first thing that phase does, never a cleanup
afterwards. Doing it in the other order is what turns a redesign into a repair job, and it
is the exact mistake that killed the former Phase 0.

**Before deleting a whole test FILE, check who imports its fixtures.** Measured
2026-08-07, four couplings exist and none is declared anywhere: `tests/test_tour_selection.py`
exports `_snap`, `_poi`, `PDV`, `_density_fillers`, `_auto_beat_seconds` to
`test_tour_visit_time.py`, `test_tour_one_engine.py`, `test_tour_flavours.py` and
`test_tour_b_materialization.py`; `test_workbench_matches_the_app.py` imports `_client`
and `_dense_snap` from `test_tour_flavours.py`; `test_compose_gate_verifier.py` imports
five private fixtures from `test_claim_dedup.py`. A test that cannot import does not fail
loudly — it vanishes. Move the shared helper first, then delete.

**The demolition lists are already measured.** Six audits in this folder
(`05-audit-*.md`, 2026-08-07) classify all 69 tour-engine test files function by function
— load-bearing with its citation, pins-the-old-algorithm, or fake — and tag each deletion
with the phase that kills it. A phase's `[DEMOLISH]` step reads its rows from there rather
than re-deriving them.

### 0.8 How this plan gets sabotaged — the ten general modes

Every step below also carries its OWN sabotage list. These ten are the ones available at
every step, so they are written once. Each is paired with **the tell** — the observable
thing you are doing at the moment you have gone wrong. Check the tell, not your intent.

1. **Running `make test` (or a full shard) to decide whether to proceed.**
   *Tell:* you are reading a failure list you did not write. Suspended by §0.7 for the
   whole plan. The only suites that gate anything here are the ones this phase wrote.
2. **Nursing an inherited test back to green instead of deleting it.**
   *Tell:* you are adjusting a number inside an existing test, or re-deriving a fixture so
   an old assertion holds. §0.1.2 — that test is DELETED. This is the failure that killed
   Phase 0 and it is the most likely one to recur.
3. **Editing a test to make it pass.**
   *Tell:* an assertion changed and no written reason exists. §0.1.3. If the invariant
   genuinely survives, the replacement is written FRESH with a citation and the old one is
   deleted — never edited in place.
4. **Treating an unexpected red as an immediate stop when the audit already killed it.**
   *Tell:* you are about to escalate a test that appears in an `05-audit-*.md` DELETE row.
   Check the audits before stopping. §0.3's stop rule exists for genuine surprises.
5. **Writing a replacement test that proves nothing.**
   *Tell:* you cannot name the single production line that, if deleted, turns your new
   test red. Measured example, 2026-08-07: the proposed "routed and haversine orderings
   must agree" replacement would have compared two paths that compute the SAME formula —
   rigorous-looking and vacuous. If you cannot name that line, do not write the test.
6. **Deleting a test file whose private fixtures another file imports.**
   *Tell:* you did not map the file's helper importers with /graphify and read those
   files in full (§0.9.1 — grep is forbidden). A test that cannot import does not fail
   loudly; it vanishes. Four such couplings exist today and §0.7 names them.
7. **Adding a new file, function or constant that answers an existing question.**
   *Tell:* the **Extends** field is empty, or it says "different concern" without naming
   the thing considered. This project already paid for the tour algorithm existing twice.
8. **Declaring a step done from a code read.**
   *Tell:* no command output is pasted. §0.3 and `CLAUDE.md` §1.11. A user-facing claim
   needs a real run, not a passing unit test.
9. **Raising cost as a question.**
   *Tell:* you are writing a sentence containing "this spends" followed by a question
   mark, or deferring a check because it needs a live provider. State the number in one
   clause and run it (`CLAUDE.md` §1.12).
10. **Re-opening a decision this plan already made, or asking the owner to re-specify it.**
    *Tell:* you are drafting a question whose answer is in §0 or in the phase's own
    Delivers paragraph. Read it and proceed.

### 0.9 How the work is done — owner rulings of 2026-08-22 (bind every session and every agent)

**0.9.1 Reading.** `grep`, regex, `head`, `tail`, `sed -n` and every other snippet or
excerpt read are FORBIDDEN. A question about the codebase (which files touch what, who
imports whom, where a behaviour lives, which tests depend on a module) goes to
`/graphify` first (`graphify-out/` exists), and then every file involved is loaded and
READ WHOLE, start to end. A partial read is not a read. Every change gets the
**"every site" sweep**: graphify lists every constructor, copier, serializer, reader and
fixture that touches the thing; each is read in full and updated or explicitly cleared
before the step is called complete (the Phase 6 copy helper that dropped every new field,
and the ten failures in files the phase never opened, are the class this prevents).

**0.9.2 Tests and cost.** (a) Per step, ONLY the relevant tests run: the step's own test
command plus the existing tests that depend on the code the step touched — found with
`/graphify` (dependents of the touched modules) and read in full. Never the whole suite
per step; never the whole suite twice. (b) Every test is annotated: `paid` (a real model
call, always costs), `recorded` (replays a recorded real answer; costs only when
re-recorded), or nothing (free). A paid or recorded test runs only when its step touches
it. (c) At a phase close the whole `tests/` tree runs ONCE, free tests only (§0.7);
paid/recorded only those the phase touched. (d) Record-and-replay lives in the TEST
HARNESS ONLY: the replay switch is in `tests/conftest.py`, recordings are readable files
under `tests/`, committed; "no new recordings" is the default, so a missing or stale
recording FAILS LOUDLY and never falls through to a live call; re-recording is an
explicit flag, one paid call, the new file visible in the diff; assertions are about
structure and rules, not exact wording; nothing under `src/` or `mobile/lib/` knows
recordings exist, and the product guards ("every selectable provider really leaves the
machine", "pressing Listen leaves the machine") stay green. (e) Model calls whose role is
to CHECK, CLASSIFY or FORMAT (never to write narration) — and the duplicate-work
reviewer — use Haiku 4.5, by configuration only; the writer model is never swapped (the
pipeline refuses a mismatched writer by design). (f) No spend gates, no counters, no
ceremony: the annotation and the per-step rule ARE the mechanism.

**0.9.3 Managing parallel work (the manager / agents model; the manager is the session).**
Prefer the harness workflow runner for any fan-out (the owner may say "use a workflow":
it journals every agent's return on disk). Otherwise, in this order, every step
mandatory: (1) roster file FIRST — `specs/…/phase<N>-agents.md`, one row per agent: ID,
task in one sentence, task file, the output file it MUST write, spawn time, deadline,
status; no row, no spawn. (2) Every agent writes its result to its named output file in
the fixed shape (status; what it did; files touched; commands run with pasted output;
what it could not do) — no file, not done. (3) Batches of at most 4, one batch at a time;
no new batch until every row is `done` or `abandoned`. (4) Spawn, then immediately record
the real agent ID. (5) Never infer from silence — state is read from the output file or
the harness task output, never remembered. (6) On every agent event, re-read the roster,
update that row, and verify the claim against its pasted evidence before `done`; a claim
without pasted output is `unverified`. (7) Before acting on a batch's results, list every
row and its status in the transcript; a row `running` with no file past its deadline is
reconciled first (read the task output; if dead, respawn the SAME task file under a new
ID, record the old row `abandoned` with the reason). (8) Lost? Stop spawning, rebuild the
roster from disk (output files + harness task list are the truth), then continue; "I think
agent X was doing…" is forbidden language. (9) The manager does no agent work while a
batch is open except reading, verifying and recording; taking over a row is written in
the roster. (10) Close each batch with a ledger paragraph: spawned / done / abandoned,
what each produced, how each output was verified.

**0.9.4 Error-class rules (from the Phase 6 ledger).** (a) Partial reading/verification:
§0.9.1's sweep and §0.7's whole-tree run. (b) Claims ahead of mechanism: no "fixed"
without the mutation shown at the real site (red without the fix, green with it,
restored byte-identical); nothing enters the ledger or a report without pasted output;
a hostile self-check on your own claims BEFORE the judge. (c) Misread measurement /
wrong cause: before any behaviour change, a one-sentence hypothesis with its prediction,
then a controlled before/after on one fixture with one variable moved; prediction fails →
no patch, look again. (d) Environment assumptions: a written pre-flight at session start
and after any restart, commands pasted (`make db-up DB=dev`, `make db-up DB=test`,
`make valhalla-up`; `make api` and tokens through the Render-overlay wrapper; tests under
the test profile); read a make target in full before invoking it. (e) Temporary
mutations and scratch: scratch only in the session scratchpad; every mutation restored
from a saved copy and `cmp`-checked; working-tree status checked before every test run
and before the judge. (f) Losing the thread: §0.9.3; the ledger entry written at the
moment of each step; at any time the session can state steps done of total, current
step, blocker, last verified number.

**0.9.5 Cleanup.** Any temporary file or resource is removed once the session or the
relevant agent is DEFINITIVELY done with it: agent task and output files after the
batch's ledger paragraph has recorded them (the ledger keeps the record); scratch and
measurement scripts that are not the step's evidence; containers, worktrees, simulator
state and tokens the phase created (infrastructure removals go through the judge, §0.6);
working files under `specs/` that are not the ledger, the plan, the evidence or the
panel verdicts. A phase close includes the cleanup, listed in the ledger.

**0.9.6 No duplication; modularity.** The repo's `CLAUDE.md` (re-created 2026-08-22 as
coding rules only) binds: before writing any function, module, file or code path, find
the existing one that answers the question and EXTEND it; the workbench and the app run
the EXACT SAME code for everything they share (one algorithm, one construction site,
imported by both — the parallel workbench/app routing copies of the past were the
defect); one module one concern, one function one job; no mocks, fakes or stubs in
product code. §0.4's **Extends** field is how every step proves it.

---

## 1. Read-evidence ledger (Phases 1–2)

Per design §10.1: path, line count read (= full file), and the working-tree blob hash
(`git hash-object`) at read time, 2026-08-07, tree at base `c8a35a75` + uncommitted
work. If a file's hash differs at execution time, the file changed since planning:
re-read it before executing any step that touches it, and treat any surprise as a plan
defect (§0.2).

| file | lines | blob sha |
|---|---|---|
| specs/2026-08-07-tour-algorithm-redesign/01-design.md | 643 | 247ef767 |
| specs/2026-08-07-tour-algorithm-redesign/03-panel-findings.md | 300 | e80f8f15 |
| specs/2026-07-19-tour-quality-standard/01-standard.md | 502 | a171f3ba |
| docs/personas/00-what-these-are-for.md | 84 | b6e6aa66 |
| docs/personas/01-architecture-pilgrim.md | 84 | 4e0c5088 |
| docs/personas/02-dark-history-walker.md | 101 | a04a7397 |
| docs/personas/03-family-with-children.md | 48 | 041ba6ae |
| docs/personas/04-layover-sprinter.md | 53 | 8e517fec |
| docs/personas/05-step-free-visitor.md | 61 | a6bc5fa5 |
| docs/personas/06-resident-novelty-seeker.md | 50 | ea058a17 |
| docs/personas/07-rainy-tuesday.md | 50 | 97387462 |
| docs/personas/08-second-language-listener.md | 80 | 1a2aade2 |
| docs/personas/09-couple-who-would-rather-talk.md | 82 | 0e5f67fe |
| docs/personas/10-day-two-of-five.md | 72 | 7b41b0e5 |
| docs/personas/11-solo-after-dark.md | 83 | 5d39adcc |
| src/tour/selection.py | 4149 | 92621198 |
| src/tour/routing.py | 603 | 8c139665 |
| src/tour/routing_client.py | 246 | 0df98ca8 |
| src/tour/visit_time.py | 116 | aaae2040 |
| tests/test_one_time_currency.py | 101 | a97dd745 |
| tests/test_tour_selection.py | 3291 | 5d72d0b0 |
| tests/test_tour_visit_time.py | 360 | 74953557 |
| tests/test_tour_golden_ile.py | 179 | 1f38dbdb |
| tests/test_tour_golden_pdv.py | 197 | 03ca9c8f |
| tests/test_tour_golden_consistency.py | 358 | d1242824 |
| scripts/tour_golden_diff.py | 160 | 1a185714 |
| scripts/measure_planned_audio.py | 127 | b77c3e9b |
| scripts/tour_build.py | 686 | 51475665 |
| Makefile | 698 | a23c60c6 |
| fixtures/tour_golden/ile_oneway_90min.json | 248 | f4fd41dc |
| fixtures/tour_golden/pdv_round_trip_60min.json | 102 | c100cf8c |
| src/api/crud/trips.py | 384 | 4d878a19 |
| src/api/routes/audio.py | 1043 | 096e4ac7 |
| tests/test_trip_adapter.py | 147 | 787fd759 |
| tests/test_audio_trip_api.py | 173 | 79d4c4e3 |
| tests/test_tour_one_engine.py | 1816 | 68102350 |

(Phase 1–2 files — `src/tour/contract.py`, `src/tour/corpus_places.py`,
`src/api/models/trips.py`, `src/api/routes/trips.py`, `scripts/poi_visit_duration.py`,
`.claude/commands/poi-visit-duration.md`, `tests/test_poi_visit_duration.py`,
`scripts/upload_paris.py`, `src/tour/options.py`, `src/seed/users.py` — are appended to
this table in §3's own ledger rows, read the same way.)

---

## 2. PHASE 1 — Clock-native planning. Demo **D1, "the Tuesday proof"**.

**Delivers:** the planner learns what day and time it is. Opening days + hours (data row
6.1) and place category (6.7) land through the established enrichment pattern;
`TourInput` gains the real clock and end-hardness; a POI that is closed for the whole
visit window is excluded with a recorded reason.

**Demo D1:** the same request run for a Monday and for a Tuesday, side by side; the
closed museum is absent on Tuesday, with a printed reason naming its hours and their
source.

**Kill criterion:** if audited opening-hours coverage lands below the threshold —
**≥ 90 % of the POIs a human reviewer marks as genuinely gated (ticketed interiors,
museums, churches with doors) carry hours with a defensible basis sentence** —
clock-native planning is scoped to daylight + end-hardness only and 6.1 becomes its own
phase, exactly as design §9 provides.

**One deliberate deviation from the §9 row, stated:** the row lists "forecast fetch"
in Phase 1. The forecast's first consumer is Phase 3 (rain-priced legs and stops, 6.6 /
6.8). A fetcher with no consumer is a layer, not a vertical slice, and §10.7 forbids
layer phases — so the forecast fetch moves to Phase 3 with its consumer. Aiko loses
nothing: her Tuesday-closure failure (her step 6, "the failure that matters most in
this whole document") is exactly what D1 demonstrates.

**Additional read evidence for this phase** (all end-to-end, hashes at 2026-08-07):
`src/tour/contract.py` 873 (71867dd0), `src/tour/corpus_places.py` 659 (55e94b04),
`src/api/models/trips.py` 457 (42dd40a4), `src/api/routes/trips.py` 1459 (cd2c885d),
`scripts/poi_visit_duration.py` 399 (2516a798), `.claude/commands/poi-visit-duration.md`
242 (f7e1fdbd), `tests/test_poi_visit_duration.py` 333 (38b08a13),
`scripts/upload_paris.py` 535 (073c1870).

### Steps

- [x] `[DEMOLISH]` **D1.0 — Delete the inherited tests that stand in front of Phase 1.
  THIS IS THE FIRST THING PHASE 1 DOES (§0.7).** Rows are already measured — read them
  from `05-audit-C-trips-serving.md`, `05-audit-D-workbench.md`, `05-audit-F-certification.md`
  and `05-audit-G-data-misc.md` rather than re-deriving. The set:

  - `tests/test_tour_batch_regression_manifest.py::test_accepted_paris_request_is_preserved_exactly`
    — pins `TourInput.model_dump(exclude_none=True)` to an exact four-key dict.
    `end_hardness="firm"` is not None, so it lands in the dump and this goes RED the moment
    S1.2 runs. **The plan previously said S1.2 had no declared breakage. That was wrong.**
  - `tests/test_tour_certification_selection.py::test_certification_policy_derives_one_midpoint_budget_from_frozen_inputs`
    — five literals (4860/5400/5940/2160/3240) derived from ONE two-sided band. Design
    §2.3 replaces that band with three different answers (`wall`/`firm`/`open`).
  - `…::test_certification_fixed_end_reachability_uses_total_ceiling` — its own sibling
    three tests down proves this IS the defect it describes.
  - `…::test_final_timebox_accepts_only_immaterial_whole_minute_rounding_drift` — asserts
    a tour 60 seconds PAST the ceiling is legal. Directly contradicts Marcus
    (`docs/personas/04-layover-sprinter.md`: a duration is a ceiling never to cross) and
    makes `wall` unimplementable.
  - `tests/test_trip_preview_contract.py::test_preview_single_stop_that_cannot_fill_timebox_is_structured_422`
    and `::test_preview_green_pool_but_materially_thin_delivery_is_422` — pin
    `"required 3240-3960s"` and `"best eligible bounded route 2403s"`, i.e. the
    fill-the-requested-time band design §8.3 deletes.
  - The `minimum_requested_fraction == 0.90` pin wherever it is asserted — §8.3 again.
  - `tests/test_workbench_ui.py::test_tour_preview_thin_delivery_renders_disclosure_note`
    — asserts a 2-minute tour against a 30-minute request MUST show "Short tour". Under
    `open` (§2.3) a short day is correct, not thin. Camille's line is the citation.
  - Strip, do not delete, two literals in otherwise load-bearing tests:
    `budget.maximum_elapsed_seconds == 19800` and `== 3600`.

  **Two owner-visible items this step surfaces and MUST NOT resolve quietly:**
  (i) `MAX_REQUESTED_FRACTION: float = 1.10` (`src/tour/routing.py:87`, consumed by
  `premium_tour.py:328` into the frozen batch policy) — a tour may legally run 10 % OVER
  what was asked. It contradicts persona 04. It needs an owner decision, not an edit.
  *(Plan defect fixed 2026-08-07: this item previously cited
  `data/certification/tour-batch-v1/contract.json` and its `change_protocol`; neither
  exists. Logged in phase1-ledger.md.)* (ii) See C1.0's sabotage list for the
  certification-hash trap.

  **Proof (§0.7: a DEMOLISH step has no RED→GREEN and no undo test):** `make lint` clean,
  and `make test-file FILE="tests/test_tour_visit_time.py::test_a_stop_is_never_shorter_than_what_it_says_or_what_it_is_worth"`
  still collects and passes — a named survivor proving nothing was broken by import.

  **How this step gets sabotaged.** *Adjusting* those literals to the new numbers instead
  of deleting the tests — the tell is that you typed a number into an existing assertion.
  *Deleting a whole file without grepping its `_helper` names* (§0.7 lists four live
  couplings). *Stopping* because a red appeared that this list does not name — check the
  audits first; they cover all 69 files. *Quietly bumping* `maximum_requested_fraction` to
  1.0 to make the contradiction go away — that is a product decision wearing a config
  edit's clothes.

- [ ] `[GATE]` **C1.0 — SKIPPED BY OWNER ORDER (2026-08-07 session: "wherever the plan
  talks about commits — ignore that"). Nothing is committed; the tree still has no
  rollback point, and the certification-hash trap below still applies whenever a
  commit does happen.** — Commit the in-flight time model, with the inherited suite red.
  The uncommitted 45-file change from *walking + talking* to *walking + being somewhere*
  is the pricing engine everything later depends on, and there is currently NO ROLLBACK
  POINT for it. Commit it together with D1.0's deletions, as one legible commit: the new
  clock, and the tests that pinned the old one, gone. Explicit path list only — the owner
  carries ~172 unrelated uncommitted files; `git status` is read after staging and before
  committing. Judge consult first (`CLAUDE.md` §2).

  **How this step gets sabotaged.** Running `make test` first and refusing to commit
  because it is red — §0.7 suspends that bar; red is the expected state. `git add -A` or
  `git add .`, which sweeps the owner's work into your commit. Any `git checkout`,
  `restore`, `stash`, `reset` or `clean` on a tracked file (§0.6) — there is no rollback
  point, so one of those destroys work permanently. **And the non-obvious one:** adding
  fields to `TourInput` changes every `request_sha256` and the `manifest_sha256` in
  `data/certification/tour-batch-v1/plan.json`, because they hash
  `tour_input.model_dump(mode="json")` without `exclude_none`. This does NOT appear as a
  red shard — it appears later as "stored provider batch differs from its reconstructed
  authoring plan" from `make tour-batch-review-plan`. **Re-sealing that batch to make the
  error go away destroys the meet-or-beat control arm Phase 8 needs.** Declare it in the
  commit message; §7.3 re-seals it deliberately at Phase 8.

- [x] `[GATE]` **W1.1 — Before-picture.** Run the current harness twice on a corridor with a
  Tuesday-closed anchor (start `"Musée d'Orsay"`, 180 min, round trip — Rosemary's own
  geography), dated in prose Monday vs Tuesday. The two outputs are identical — the
  measurement that the planner cannot tell days apart. Recorded in the phase ledger.

  **How this step gets sabotaged.** Running it once and asserting the second run "would be
  identical" — the point is the measurement, so run both. Running against a graph with no
  data, where both outputs are empty and identical for the wrong reason — check the stop
  count is non-zero. Recording a summary instead of the two verbatim breakdowns; W1.10
  compares against these exact bytes.

- [x] `[BUILD]` **S1.2 — `TourInput` learns the clock and end hardness.**
  **File:** `src/tour/contract.py`. Add `start_datetime: str | None = None` (ISO 8601;
  None = today's dateless behaviour, which keeps every existing caller and golden
  byte-identical) and `end_hardness: Literal["wall", "firm", "open"] = "firm"`
  (design §2.3). A validator rejects a malformed datetime with a plain message.
  **New test file:** `tests/test_tour_clock.py` — all Phase 1 clock tests live here.
  **Extends:** considered `tests/test_tour_selection.py` (3,291 lines of planner
  behaviour, much of it pre-audit) and `tests/test_tour_contract.py` (NOT read end to
  end, so no step may touch it, §0.2). A new file carries one new question — *does the
  planner know what time it is?* — spanning contract, data, and filter; the model is
  `tests/test_tour_visit_time.py`, one clock-hand per file, every test citing its
  source.
  **Command:** `make test-file FILE=tests/test_tour_clock.py::test_tour_input_carries_the_clock_and_end_hardness`
  RED (fields absent — `extra="forbid"` raises) → GREEN. Cites design §2.2 ("the start
  is soft — Fiona & Dev stood reading a menu for twelve minutes", 09- step 1), §2.3
  (Marcus's 16:40 wall, 04-; Camille's "is 15:00 a wall or a wish?", panel; Julien's
  leavable-blank clock, panel).
  **Declared breakage:** none — both fields default to today's behaviour.

  **How this step gets sabotaged.** Declaring "declared breakage: none" — D1.0 exists because that claim was wrong. Making `start_datetime` a `datetime` instead of an ISO string: `test_tour_input_end_round_trips_through_model_dump` does `TourInput(**inp.model_dump())`, and only a string round-trips. Copying `POI`'s config — `TourInput` is `extra="forbid"` and `POI` is `extra="ignore"`, which behave OPPOSITELY; the forbid is what makes this step's RED real, and `test_tour_input_rejects_extra_keys` is the only guard that it is still on, so name it here. Replacing `_end_round_trip_mutex` with a new `model_validator(mode="after")` instead of ADDING to the chain.

- [x] `[BUILD]` **S1.3a — The API models carry them.** **File:** `src/api/models/trips.py`. Add
  `start_datetime` + `end_hardness` to BOTH `TripGenerateRequest` and
  `TripPreviewRequest`, with the same reasoning the `max_stop_minutes` field records
  verbatim: neither model declares `model_config`, so an undeclared field would be
  silently dropped. Test (same file `tests/test_tour_clock.py`): value carried, not
  dropped; a bad `end_hardness` is a 422. RED→GREEN.

  **How this step gets sabotaged.** Adding the field to `TripGenerateRequest` and forgetting `TripPreviewRequest`, or the reverse. Assuming an undeclared field is carried — neither model declares `model_config`, so an undeclared field is SILENTLY DROPPED and the layer above still looks fine. Testing the happy value only, and not the 422 on a bad `end_hardness`.

- [x] `[BUILD]` **S1.3b — The routes thread them.** **File:** `src/api/routes/trips.py`. Pass
  both fields through `_build_tour_input` at all three construction sites
  (`generate_trip`, `preview_trip`, `_author_preview_impl`), persist them in
  `tour_input_json` at generate, and restore them in `compose_trip` with the
  `.get(...)` fail-open shape `max_stop_minutes` already uses (a trip saved before the
  key existed composes exactly as it always did). Test: round-trip through the
  persisted-inputs path, hermetic. RED→GREEN.

  **How this step gets sabotaged.** Threading through one or two of the THREE construction sites (`generate_trip`, `preview_trip`, `_author_preview_impl`) instead of all three; the missed one degrades silently. Restoring from `tour_input_json` with a direct key access instead of the fail-open `.get(...)` shape `max_stop_minutes` already uses — that 500s every trip saved before the key existed. Persisting at generate but never restoring at compose.

- [x] `[BUILD]` **S1.3c — The harness accepts them.** **File:** `scripts/tour_build.py`. Add
  `--date`/`--time`/`--end-hardness` flags feeding the same fields, and a
  **clock-exclusions section** in `_print_breakdown` (prints each excluded POI with
  its reason once S1.6 records them; prints "none" before that). Proof: the flags
  parse and a dateless run is byte-identical to today's (assert in
  `tests/test_tour_clock.py` via the harness's argument parser, hermetic).

  **How this step gets sabotaged.** Changing default output so a dateless run is no longer byte-identical to today's — that destroys W1.1's before-picture as a comparison, and the demo with it. Printing the exclusions section only when there ARE exclusions, so the Monday and Tuesday runs have different shapes and cannot be read side by side; print "none". **And first: `scripts/tour_build.py` CHANGED after this plan's read ledger was taken** (recorded blob `51475665`, working tree holds `514c7566`). §0.2 makes re-reading it end to end a precondition of touching it.

- [x] `[DATA]` **S1.4a — The opening-hours pass.** **Create:** `scripts/poi_opening_hours.py`.
  **Extends:** considered extending `scripts/poi_visit_duration.py` — rejected: that
  script's contract is one question (visit capacity) with its own prompt, calibration
  and retry loop, and its header documents the one-script-per-command precedent this
  follows. What IS reused is the pattern, mechanically: load `poi-raw.json` + keep the
  original bytes, refuse-to-write-on-reformat (`dump_pois`'s round-trip guard, lifted
  verbatim), batch → structurally validate → one retry of failures only → exit nonzero
  while anything is unpriced. Source hierarchy per design 6.1: OSM `opening_hours`
  where OSM has the place, an audited model pass otherwise, and the field trio per
  POI: `opening_hours` (structured week table, e.g. `{"tue": []}` for a Tuesday
  closure), `opening_hours_source` (`"osm" | "ai"`), `opening_hours_basis` (the
  one-sentence argument, per the house style). `null` hours = not gated (streets,
  squares, bridges) — the same load-bearing null `visit_seconds_inside` uses.

  **How this step gets sabotaged.** Folding it into `scripts/poi_visit_duration.py` — that script answers one question with its own prompt and calibration; this is a second question. Losing the round-trip byte guard from `dump_pois`, so the script silently reformats `poi-raw.json` and the diff becomes unreviewable. Writing hours for places that are not gated — a street, a square, a bridge takes `null`, and that null is load-bearing: it means "never clock-excluded", which is the safe direction. Retrying the whole batch instead of only the failures. Exiting 0 while anything is unpriced.

- [x] `[BUILD]` **S1.4b — Its structural test.** **Create:** `tests/test_poi_opening_hours.py`,
  mirroring `tests/test_poi_visit_duration.py` (its own header invites the sibling):
  a `CITIES_WITH_OPENING_HOURS` allow-list; every gated POI carries source + basis;
  tables parse; no zero-length open window; **and the three-hop plumbing tests** —
  hop 1: `LOAD_PARIS_POIS_CYPHER` asks the graph for the new fields; hop 2/3:
  `_snapshot_from_records` carries them onto a `POI` that declares them; an unpriced
  record lands on safe defaults (None = never clock-excluded — the safe direction).
  **Command:** `make test-file FILE=tests/test_poi_opening_hours.py` — RED (hop tests
  fail: Cypher and contract know nothing of the fields).
  **Declared breakage:** this file stays red until S1.5b turns it green. Nothing else.

  **How this step gets sabotaged.** Asserting a particular POI's real opening hours. Nobody in this repo can adjudicate Paris facts, and `tests/test_poi_visit_duration.py` forbids it in writing — the justification sentence plus human review is the mechanism, not the test. Writing checks that are VACUOUSLY GREEN on an unpriced corpus: the two presence checks are what say the pass ran, and one is deliberately duplicated because a guard that goes quiet when its data disappears is not a guard. Testing the three plumbing hops together so a failure cannot name the hop — hop 1 is `"p.<field>" in LOAD_PARIS_POIS_CYPHER`, hops 2-3 assert VALUES on a `POI` built by `_snapshot_from_records`. Omitting the allow-list, or REMOVING a slug from it to reach green (forbidden in that file's own words).

- [x] `[BUILD]` **S1.4c — The Make target.** **File:** `Makefile`. `poi-opening-hours` target,
  `$(PREFLIGHT) --label poi-opening-hours $(PRE_PY) render-key` +
  `$(RENDER_LOCAL_EXEC)`, exactly like `poi-visit-duration`. Proof:
  `make test-file FILE=tests/test_preflight.py` stays green (it fails any
  `##`-documented target with no preflight line — add it correctly or it says so).

  **How this step gets sabotaged.** Omitting the `@$(PREFLIGHT) --label` line — `tests/test_preflight.py` fails any documented target without one. Fetching Render credentials without declaring `render-key`. Adding the target but not adding it to `.PHONY` AND to `Docs/MAKE_TARGETS.md`; a guard requires both lists to match the Makefile exactly, and three targets are already out of sync today.

- [x] `[BUILD]` **S1.4d — The upload carries the fields.** **File:** `scripts/upload_paris.py`.
  Add `opening_hours` (JSON-encoded string, the `physical_cues` precedent for
  structured values), `opening_hours_source`, `opening_hours_basis`, and S1.7's
  `place_category` to **both** hardcoded property lists — the param dict AND the
  Cypher `SET` list; the file's own comment warns they must agree or the field
  silently never reaches the graph. No defaults: absence stays absent, per the
  visit-capacity precedent recorded in that file. Proof: hop-style assertion added to
  `tests/test_poi_opening_hours.py` reading the script source for both lists (the
  `test_golden_diff_cli_reads_the_durable_key` genre).

  **How this step gets sabotaged.** Adding the field to the param dict but not the Cypher `SET` list, or the reverse. The file's own comment warns the two must agree or the field SILENTLY NEVER REACHES THE GRAPH, and nothing above this layer notices. Adding a default so "absent" becomes a value — absence stays absent, per the visit-capacity precedent in that file.

- [x] `[BUILD]` **S1.5a — The POI contract declares the fields.** **File:**
  `src/tour/contract.py` — `opening_hours: str | None`, `opening_hours_source:
  str | None`, `opening_hours_basis: str = ""`, `place_category: str = ""` on `POI`,
  additive with the visit-capacity comment style. Proof: part of S1.4b's hop tests.

  **How this step gets sabotaged.** Forgetting a field and not noticing. `POI` is `extra="ignore"` (`contract.py:115`), so an unknown keyword is DISCARDED WITHOUT ERROR. The test must assert VALUES on a built `POI`, never merely that construction succeeded.

- [x] `[BUILD]` **S1.5b — The loader returns and carries them.** **File:**
  `src/tour/selection.py` — extend `LOAD_PARIS_POIS_CYPHER`'s RETURN list and
  `_snapshot_from_records`'s explicit constructor list (the file's own comment: "THREE
  PLACES CAN EAT THESE FIELDS SILENTLY, and all three are closed" — this step keeps
  all three closed for the new fields).
  **Command (GREEN):** `make test-file FILE=tests/test_poi_opening_hours.py` — the
  whole file passes. Undo test: revert S1.5b → hop tests RED → restore → GREEN.

  **How this step gets sabotaged.** Extending the Cypher `RETURN` list but not `_snapshot_from_records`'s explicit constructor list, or the reverse. That file's own comment says THREE places can eat these fields silently and all three are currently closed; this step keeps all three closed. Landing an unpriced record on something other than the safe default.

- [x] `[BUILD]` **S1.6a — The Route records clock exclusions.** **File:**
  `src/tour/contract.py`. `clock_exclusions: tuple[ClockExclusion, ...] = ()` on
  `Route` (poi_id, name, plain-English reason) — additive metadata in the `vignettes`
  mould; a small frozen `ClockExclusion` model beside it. **Extends:** the disclosure
  belongs on the Route for the same reason `elapsed_shortfall_seconds`'s comment
  gives — a disclosure that rides a channel which is null in its own case discloses
  nothing.

  **How this step gets sabotaged.** Putting the disclosure on a channel that is null in exactly its own case — the `elapsed_shortfall_seconds` lesson: a disclosure riding a field that is empty when the disclosed thing happened discloses nothing. Carrying ids only; without the plain-English reason and the source, D1's demo has nothing to show.

- [x] `[BUILD]` **S1.6b — The clock filter.** **File:** `src/tour/selection.py`. In
  `select_route`'s candidate loop (beside the zero-beat and container-identity
  filters), when `input.start_datetime` is set: a POI whose opening table is CLOSED
  for the entire visit window (start → start + duration) leaves the dwell pool and is
  recorded on `clock_exclusions` with its reason and source. No datetime → no
  filtering, byte-identical pool (the identity default that keeps every existing test
  and golden green).
  **Tests** (in `tests/test_tour_clock.py`, hermetic constructed snapshot):
  Tuesday-closed POI + Tuesday request → excluded AND recorded with a reason naming
  Tuesday; Monday request → seated; no datetime → seated. Cites
  `docs/personas/05-step-free-visitor.md` (final bullet: the identical request one day
  earlier spends 24 of her 54 walking minutes reaching a locked door),
  `07-rainy-tuesday.md` step 6, design 6.1 ("Aiko's locked door, Rosemary's Tuesday").
  **Command:** `make test-file FILE=tests/test_tour_clock.py` RED→GREEN.
  **Declared breakage:** none (identity default).

  **How this step gets sabotaged.** Filtering when no datetime is set. That changes every existing tour and every golden, silently. No datetime means byte-identical to today, and that identity default is the entire reason this step declares no breakage. Excluding a place closed for PART of the visit window rather than all of it. Recording an exclusion without its reason and source. Putting the filter anywhere but the candidate loop beside the zero-beat and container-identity filters, which forks the admission rule.

- [x] `[BUILD]` **S1.6c — End hardness reaches the budget.** **File:** `src/tour/routing.py`.
  `route_planning_budget` (the one home of the time arithmetic) takes the hardness:
  `open` drops the minimum-elapsed floor to zero — a two-ish-hours request is never
  padded toward a number nobody defended (design §2.3, Julien; design 8.3 finishes
  "fill-the-requested-time" deletion); `wall` plans to a 0.95 ceiling so the plan
  carries visible spare minutes (Marcus: "2h40 of tour with 20 minutes of slack" beats
  "3h00 exactly", 04- bullet 2); `firm` is byte-identical to today. Threading from
  `TourInput` via `select_route`'s existing `planning_policy` derivation. Tests cite
  those lines; RED→GREEN; declared breakage: none (firm default).

  **How this step gets sabotaged.** Making `firm` behave differently from today — it must be byte-identical. Implementing `wall` as a hard truncation instead of planning to a 0.95 ceiling so the plan carries VISIBLE spare minutes; Marcus asked for "2h40 with 20 minutes of slack", not a tour cut at 3h00. Writing the arithmetic anywhere but `route_planning_budget`, the one home of it. If the test asserting a tour 60 seconds past the ceiling is legal is still green when you arrive here, D1.0 did not run — stop and run it.

- [x] `[DATA]` **S1.7 — Place category (6.7), cheap derivation.** **Create:**
  `scripts/poi_place_category.py` + `tests/test_poi_place_category.py`.
  **Extends:** the design prices 6.7 as "cheap derivation" — deterministic, $0, no
  model call: closed vocabulary (`gallery | museum | church | square | arcade |
  market | park | garden | bridge | street | monument | other`) derived from name
  tokens, description, and `poi_role`, written to `poi-raw.json` as
  `place_category`. Not folded into S1.4a because one script answers one question and
  this one is free to re-run. Test: every Paris POI categorised; vocabulary closed;
  pinned precedents (Place des Vosges → square, Sainte-Chapelle → church, Galerie
  Vivienne → arcade — Greta's and Aiko's own anchors). Consumer lands in Phase 3
  (category-diverse replacement, the yesterday question); Phase 1 surfaces it in the
  harness corridor printout so the owner can see the labels. Upload/Cypher/contract
  columns ride S1.4d/S1.5a/S1.5b.

  **How this step gets sabotaged.** Spending a model call. The design prices 6.7 as cheap deterministic derivation from name tokens, description and `poi_role`, at $0. Leaving the vocabulary open so "other" silently absorbs everything, which leaves the Phase 3 consumer (category-diverse replacement) with nothing to work with. Folding it into the opening-hours script: one script, one question.

- [x] `[DATA]` **W1.8 — Run the passes on Paris.** `make poi-opening-hours SLUG=paris LIMIT=10`
  → review per the command-doc pattern → full pass → `place_category` pass → sync
  `data/paris/export/*.json` (the mandatory step the visit-duration doc warns gets
  skipped) → upload to the dev graphs → `make test-file
  FILE=tests/test_poi_opening_hours.py` and `FILE=tests/test_export_consistency.py`
  green. This spends roughly a full-corpus model pass (~25 calls) for the AI-sourced
  rows; stated, and done (§1.12). **The kill-criterion measurement happens here:**
  the review marks which POIs are genuinely gated; coverage below the 90 % threshold
  fires the scope-shrink.

  **How this step gets sabotaged.** Skipping the `data/paris/export/*.json` sync — the visit-duration command doc names this as the step that gets skipped, and skipping it means the graph and the committed data disagree. Reviewing a sample and reporting the full pass as reviewed. Asking whether the ~25 model calls are worth it (§0.8 mode 9): state the number in one clause and run it. Declaring the kill-criterion measured without a human actually marking which POIs are genuinely gated.

- [x] `[GATE]` **W1.9 — The panel.** All eleven personas, one message, on the D1 pair (both
  breakdowns + the flagship corridor re-run) — `CLAUDE.md` §1.10: a quality check has
  started blocking (closed places now vanish from days), so the panel rules before the
  phase closes. Report dissents by name.

  **How this step gets sabotaged.** Handing the personas a SUMMARY instead of the real stop lists, walking legs and per-stop minutes — `CLAUDE.md` §1.10 requires the actual numbers. Running fewer than eleven. Running them AFTER the decision instead of as its input. Reporting consensus and burying a dissent: a change every persona likes is rare, and one that breaks a persona is a decision, not a detail.

- [x] `[GATE]` **W1.10 — DEMO D1.** Run the S1.3c harness twice — `--date` a Monday, then the
  Tuesday — on the Orsay corridor. Present both breakdowns side by side; the Tuesday
  run's exclusions section reads, e.g., *"Musée de l'Orangerie — closed Tuesdays
  (hours: OSM); would otherwise have been seated."* The owner reads both. Then
  the PHASE CLOSE BAR (§0.7): the tests Phase 1 wrote, `make lint`, `make
  dedup-review`, the demo watched. **Not `make audit`** — the inherited suite is not
  a gate before Phase 8. Then judge, commit (explicit paths), amend-and-carry this plan.

  **How this step gets sabotaged.** Describing the two runs to the owner instead of showing the two breakdowns. Running `make audit` and treating its red as a blocker — §0.7 removed it from the close bar; the bar is Phase 1's own tests, `make lint`, `make dedup-review`, and this demo. Closing with declared breakage outstanding. Committing with `git add -A` or `git add .`.

---

## 3. PHASE 2 — Party axes and presets. Demo **D2, "six people, one street"**.

> **RE-PLANNED AT STEP LEVEL 2026-08-07, after D1 demoed, against commit `97f4be53`**
> (the plan's own §4 rule). Every file below was re-read or hash-verified at that
> moment; the ledger addendum at the end of this section records the evidence. The
> Phase 1 panel's carry-forwards that belong to THIS phase are folded into the steps
> that answer them: Rosemary's per-leg dissent (both D1 days carried a 17/19-minute
> longest leg) is S2.3's opening citation, and Marcus's "show me one wall-mode day"
> condition is discharged by W2.11's seventh demo run.

**Delivers:** who is walking becomes an input the planner obeys — pace, per-leg cap,
rest/toilet cadence, escape radius, per-stop ceiling (already landed), route surface —
with the five presets as shortcuts over axes (design §2.4, axes are what the planner
reads). Data rows 6.2 (step-free — capability-verified first), 6.3 (toilets and
benches), 6.4 (place judgements).

**Demo D2:** one start, one clock, six party presets (solo, couple, family,
take-it-easy, with-luggage, and solo+take-it-easy as the legitimate pair), six visibly
different days side by side — plus one `wall`-hardness run proving the printed total
never exceeds the ask (the Marcus condition, deviation-registered below).

**Kill criterion:** if step-free routing cannot be obtained from the routing engine
(W2.1 measures this, first), `take-it-easy` ships without surface guarantees **and says
so** — through the existing degradations channel, which exists precisely so a silent
soft-failure is impossible (owner ruling 2026-07-31, quoted in `routes/trips.py`).

**Read evidence for this phase, at re-plan time (2026-08-07, tree `97f4be53`):**
`src/tour/density.py` 531 (c695af8d) — **read end to end this session; no longer an
unread risk**. Findings that shaped steps below: `ELIGIBLE_POI_ROLES` is
`{"stop","setting"}` and density requires active beats, so a beat-less
`poi_role="body"` node is structurally invisible to the tourability gate (S2.5 needs
no density change); density's `assess` computes its own `envelope_radius_m`, so pace
must thread there too or the gate and the planner disagree about reach (S2.4 names
it). `src/tour/ordering.py` 201 (53cf3dcc) — read end to end; `order_stops` is the one
ordering entry point; the cap does NOT need to touch it (rejection happens at the
call sites that price insertions/trials). `src/tour/visit_time.py` 116 (aaae2040) and
`src/tour/routing_client.py` 246 (0df98ca8) — byte-identical to the §1 ledger's full
reads, re-read this session anyway. The eight files Phase 1 changed carry their §1
full-read evidence plus this session's own complete diffs; current hashes:
`contract.py` 6eaf7708, `selection.py` be714650, `routing.py` dd240d4a,
`models/trips.py` fbfe2bfd, `routes/trips.py` 042f5918, `tour_build.py` 402b417b,
`Makefile` 06f6b7b9, `upload_paris.py` 5a4870b5.

**Deviation register for this re-plan** (each owner-visible and cheap to overrule):
(i) W2.11 gains a seventh run under `end_hardness=wall` — the Phase 1 panel's Marcus
condition, discharged in the phase whose demo table can show it; (ii) S2.1 carries
forward Phase 1's un-shipped sub-clause (S1.7 promised category labels in the harness
corridor printout; only the review tables showed them) into the D2 harness step;
(iii) S2.9 makes the export sync a real target — it has now been performed manually
three times (visit-duration, W1.8's scratch script, and the command doc's own "the
step that gets skipped" warning), which is the threshold at which a repeated block
becomes a template (`CLAUDE.md` §1.7); (iv) the audits tag NO inherited test for
deletion at Phase 2 (measured: zero DELETE-AT-PHASE-2 rows across all six audit
files), so this phase's `[DEMOLISH]` slot is explicitly empty rather than silently
missing — the one wire-format test S2.7 touches is audit-ruled LOAD-BEARING with the
instruction to EXTEND it, not delete it; (v) D2's start moves from the original
row's "Rue Royale" to **Place des Vosges** — "Rue Royale" is not a corpus POI (D1
measured this; the flagship start resolves by coordinates), and the six-preset
comparison wants a start with rich clock data and named-POI resolution; (vi) the
API request models and routes do NOT gain the party fields in this phase — D2's
surface is the harness (§10.7 satisfied, exactly as D1's was), and threading the
axes onto `/trips` belongs with Phase 4's one-day-with-dials surface rework rather
than being wired twice.

### Steps

- [ ] `[DEMOLISH]` **D2.0 — Measured no-op, stated so nobody hunts for it.** The six
  audits contain zero rows tagged for deletion at Phase 2; the demolition list is
  empty. Proof (§0.7 survivor form): `make test-file
  FILE="tests/test_tour_visit_time.py::test_a_stop_is_never_shorter_than_what_it_says_or_what_it_is_worth"`
  collects and passes, and `make lint` is clean.

  **How this step gets sabotaged.** Inventing a demolition to fill the slot — deleting
  a red inherited test that belongs to Phase 3/4's audit rows (the five planner-suite
  reds and the preview-contract red are owned by later phases; leave them red).

- [ ] `[BUILD]` **S2.1 — The harness speaks party, and shows a DAY, not a total (§10.9
  measurement-first, + carry-forward ii).** **File:** `scripts/tour_build.py`. Two
  halves, one step, because together they ARE the D2 harness:
  **(a) The flags.** `_build_arg_parser` (the S1.3c extraction) gains `--party`
  (choices = the five presets) and the explicit axis flags `--max-stop-minutes`,
  `--max-leg-minutes`, `--walking-pace`, `--rest-cadence-minutes`,
  `--escape-radius-m`, `--route-surface` — fed onto `TourInput`, then through
  `resolve_party_axes` (S2.2), exactly the flags→fields→resolver shape the clock
  flags used. No flags = today's behaviour, byte-identical.
  **(b) The per-stop table.** Extend `_print_breakdown` with a table printed on
  every run that has a route: one line per stop — name, `place_category` (the
  carried Phase 1 gap), stand/visit minutes from `route.planned_visit_seconds`
  (printing "—" when the route carries no pricing, the four legacy harnesses'
  shape), and the walking leg INTO that stop from `route.transits`. W2.11's
  side-by-side table is assembled from these lines verbatim.
  **Extends:** `_build_arg_parser` and `_print_breakdown` themselves — the one
  parser and the one printer; the printer's own docstring forbids a second.
  **Test** (new file `tests/test_tour_party.py`, the `test_tour_clock.py`
  justification shape — one party-hand per file, every test citing its source):
  the flags parse and a flagless parse carries no party and no axes (identity);
  a hermetic constructed Route through the printer via capsys shows one line per
  stop carrying name + category + minutes; the seven-number block is unchanged
  above the new table (the D1 evidence stays readable).
  **Command:** `make test-file FILE=tests/test_tour_party.py::test_breakdown_prints_one_line_per_stop_with_category_and_minutes`
  RED (no such section) → GREEN. Cites design §9 D2 ("six visibly different days")
  and §10.9. **Declared breakage:** none — additive lines and defaulted flags.
  **Ordering note:** the flag half lands with S2.2 (it needs the fields and the
  resolver); write the parser test RED first, land S2.2, then GREEN both — the same
  interleave S1.4b→S1.5b used.

  **How this step gets sabotaged.** Printing the table only when pricing exists, so a
  legacy-shape route prints a different SHAPE (print the dash). Building a second
  printer or a compare script instead of extending the one printer. Skipping the
  category column because the corpus value is `""` on legacy fixtures — print the
  empty cell; the column is the carry-forward. Wiring the flags straight onto axes
  and skipping `resolve_party_axes` — the harness must exercise the same resolver
  the product will, or D2 demos a code path nothing else uses.

- [ ] `[GATE]` **W2.1 — THE CAPABILITY PROBE, before anything plans on it (design 6.2's own
  order).** Ask the LIVE Valhalla on :8002, with real requests against a known Paris
  stairs-vs-ramp pair, whether pedestrian costing options actually move the route.
  **The concrete pair:** Place Saint-Pierre (48.8837, 2.3433) → Sacré-Cœur basilica
  forecourt (48.8867, 2.3431). The direct pedestrian path climbs the Rue Foyatier /
  Calvaire stair flights; a genuinely step-avoiding route must swing east or west
  around the butte and come out measurably longer. Probe A: plain request (the
  committed `_ROUTING_CONFIG` shape). Probe B: same locations with
  `costing_options.pedestrian` carrying the step-avoiding knobs (`step_penalty` high;
  also record what `max_grade` and `use_hills` do, since Valhalla's docs and its
  behaviour are exactly what nobody has verified). PASS = B's route differs from A's
  (longer distance and different shape polyline) in a direction consistent with
  avoiding the stairs. Record both requests and both responses verbatim in the phase
  ledger. The probe's outcome decides S2.7's shape; NO fires the kill-criterion path.
  **Also record** (one probe, two answers): whether a per-request
  `costing_options` override changes the response at all — S2.7's mechanism depends
  on per-request costing being honoured, and `routing_client.py`'s receipt validator
  already binds whatever config rode the request (config is derived FROM the request,
  so a per-request override binds automatically — verified in
  `contract.ValhallaLegReceipt._canonical_payloads_match_fields`).

  **How this step gets sabotaged.** Reading Valhalla's documentation and reporting
  what it SAYS instead of asking the live engine and recording request + response.
  Probing with a synthetic pair instead of the real stairs. Reporting "it works"
  without showing the route MOVED. Probing through a fresh ad-hoc HTTP client instead
  of the same `RoutingClient` the planner uses — the probe must exercise the client
  that will carry the axis.

- [ ] `[BUILD]` **S2.2 — Party axes and presets on the contract.** **File:**
  `src/tour/contract.py`. `TourInput` gains `party: Literal["solo", "couple",
  "family", "take_it_easy", "with_luggage"] | None = None` and the axes —
  `walking_pace: float | None` (multiplier ≥ 1.0, slow direction only),
  `max_leg_minutes: int | None`, `rest_cadence_minutes: int | None`,
  `escape_radius_m: int | None`, `route_surface: Literal["any", "no_stairs",
  "step_free"] = "any"`, `narration_register: Literal["solo", "warm", "family"] |
  None = None` (`max_stop_minutes` already exists — the time-model work landed it
  with Nadia's citation). The fields sit beside the Phase 1 clock fields, same
  additive comment style. One pure module-level resolver, `resolve_party_axes(input)
  -> TourInput`, expands a preset into axes **with explicit axes winning** — the §2.4
  table transcribed as the one place the mapping lives, returning a new TourInput via
  `model_copy` (the model is frozen).
  **The §2.4 rows, binding:** solo → no ceiling, register solo; couple → register
  warm (**never romantic** — the word appears in the resolver comment); family →
  ceiling ~6 min, pace ~2.0 (half speed), rest cadence on, escape radius on, surface
  no_stairs, register family; take-it-easy → leg cap ~12 min, surface step_free, pace
  slow, **register unchanged** ("slow the walking, never the talking" — Rosemary,
  panel); with-luggage → pace slow, surface no_stairs, register solo.
  **Extends:** considered a new `src/tour/party.py` — rejected: `contract.py` already
  owns input semantics and cross-field validators (`_end_round_trip_mutex` and Phase
  1's `_check_start_datetime` are the precedent), and the resolver is ~20 lines of
  table.
  **New test file** `tests/test_tour_party.py` (S2.1 already opened it), citing the
  §2.4 table row by row: solo sets **no** ceiling (Théo: a preset ceiling under 65
  minutes decapitates his day — panel, locked cost D6); family sets ceiling ~6 min
  (Nadia step 3: "Six minutes is the ceiling here, not the floor"), half pace (step
  4), escape radius, no-stairs surface; take-it-easy sets the ~12-minute leg cap and
  step-free and register stays None; with-luggage sets slow pace + no-stairs (Marcus
  step 2); an explicit axis beats its preset's value; `walking_pace=0.8` is rejected
  (the fast direction is locked).
  **Command:** `make test-file FILE=tests/test_tour_party.py::test_presets_are_shortcuts_over_axes_and_explicit_axes_win`
  RED (fields absent — `extra="forbid"` raises, the same real RED S1.2 used) → GREEN.
  **Declared breakage:** none — every field defaults to today's behaviour, and the
  D1.0 deletion of the exclude_none manifest pin already removed the one test that
  broke on new TourInput fields. The C1.0 certification-hash note still applies to
  the eventual commit (hashes move again; Phase 8 re-seals).

  **How this step gets sabotaged.** Creating `src/tour/party.py`. Letting a preset
  override an explicitly-set axis — explicit always wins. Giving `solo` a per-stop
  ceiling. Letting `narration_register` follow mobility. Making `couple` romantic.
  Allowing `walking_pace` below 1.0 — the fast direction is the pace pin's locked
  half. Replacing `_end_round_trip_mutex` or `_check_start_datetime` instead of
  ADDING beside them.

- [ ] `[BUILD]` **S2.3 — The per-leg cap becomes a constraint.** **File:**
  `src/tour/selection.py`. When `max_leg_minutes` is set, all FOUR admission
  mechanisms refuse any insertion whose route would carry a leg over the cap —
  measured with `path_leg_seconds` (`src/tour/routing.py:484`, the seam the
  time-model work built for exactly this, Rosemary's sentence already quoted at its
  definition). The four sites, as the tree stands at `97f4be53`:
  1. **The greedy** (candidate loop, `selection.py` ~2145–2205): after `extra, idx`
     is priced, the two would-be legs around position `idx` (prev→cand, cand→next;
     for A→B the cand→B leg when idx is last) must each fit the cap, else `continue`.
  2. **The endpoint pull** (`_apply_endpoint_pull`, ~3705): a pulled ordering is
     accepted only if `path_leg_seconds` over its full chain stays under the cap.
  3. **The fill pass** (`_apply_fill_pass`, ~2871): same per-insertion check as the
     greedy.
  4. **The timebox repair** (`_certification_route_trial` already measures
     `max_leg_seconds`, ~3379): a trial over the cap is recorded as ineligible when
     the axis is set — the same filter shape the band uses.
  The **banded longest-leg RANK stays for the unset case** — it is live at `rank()`
  (~3682, `trial.max_leg_seconds // 600`) and is soft by design; the axis is the hard
  version, additive beside it.
  **Test** (`tests/test_tour_party.py`): a corridor where the only cap-respecting
  route walks further in total — it wins under the axis, loses without it. Cites
  `docs/personas/05-step-free-visitor.md` bullet 1 verbatim, **plus the Phase 1
  panel's Rosemary dissent (phase1-ledger.md W1.9 item 7: both D1 days carried a
  17/19-minute longest leg she cannot walk)**.
  **Command:** `make test-file FILE=tests/test_tour_party.py::test_a_leg_cap_prefers_more_walking_in_shorter_pieces`
  RED→GREEN. **Declared breakage:** none (axis unset = today, byte-identical).

  **How this step gets sabotaged.** Writing a new per-leg measurement instead of
  `path_leg_seconds`. Applying the cap in three of the four mechanisms — a cap
  enforced in three of four places is not a cap, and the repair is the easy one to
  miss because its trials LOOK like they already handle legs (they only rank them).
  Deleting the banded soft RANK for the unset case. Checking the whole chain in the
  greedy per candidate (an O(n) sweep per candidate per round is the quadratic the
  local two-leg check exists to avoid — the pull and the repair check whole chains
  because they run once per route, not once per candidate).

- [ ] `[BUILD]` **S2.4 — Pace reaches the clock, in the slow direction.** **Files:**
  `src/tour/routing.py` (the arithmetic), then threading in `src/tour/selection.py`
  and `src/tour/density.py`. A pace multiplier ≥ 1.0 scales leg seconds AND shrinks
  the reach circle — a half-pace family both walks slower and is offered a smaller
  world. Concretely:
  - `routing.py`: `pace_corrected_walk_seconds` and the `LegSecondsFn` path gain the
    multiplier (× on seconds); `envelope_radius_m` gains it (÷ on metres). The
    RAISED-AND-HELD-BACK pin at `PACE_KMH` stays byte-identical — its warning is
    about the FAST direction, which remains locked (multiplier < 1.0 raises).
  - `selection.py`: `select_route` derives the multiplier once from the resolved
    axes and threads it into its `leg_fn` and its reach-envelope call — the same
    single-derivation shape S1.6c used for hardness.
  - `density.py`: `assess` computes its own `envelope_radius_m` (line ~189) — it
    receives the same multiplier via `tour_input`, or the gate offers a circle the
    planner will refuse to walk (found in this re-plan's density read; the gate and
    the planner must shrink together).
  - The Valhalla reach contour: when a multiplier is set, the isochrone request's
    `walking_speed` scales by `REACH_PACE_KMH / multiplier` per request — the road
    polygon must shrink with the circle or the primary admission test contradicts
    the fallback (`routing_client.py` `_REACH_COSTING_OPTIONS` is the default; the
    per-request override rides the same mechanism S2.7 builds).
  **Tests** (`tests/test_tour_party.py`): multiplier 1.0 is byte-identical (identity
  default); multiplier 2.0 doubles a leg's seconds and halves the envelope radius;
  density's assessment for a 2.0-pace request reports the smaller
  `walk_radius_m`; multiplier 0.8 raises. Cites Nadia step 4 ("Pace drops to roughly
  half"), Marcus step 2, §2.4.
  **Command:** `make test-file FILE=tests/test_tour_party.py::test_half_pace_doubles_legs_and_halves_the_circle`
  RED→GREEN. **Declared breakage:** none (multiplier unset/1.0 = today).

  **How this step gets sabotaged.** Allowing a multiplier below 1.0. Scaling leg
  seconds but not the envelope — a slow family offered a full-size circle is offered
  places it cannot reach. Scaling the analytic circle but not the isochrone costing —
  the polygon is PRIMARY, so the shrink would report itself while the real admission
  region stayed full-size (the exact lie the harness's reach-radius note warns
  about). Forgetting density — the gate would pass a pool the planner cannot walk.

- [ ] `[DATA]` **S2.5 — Body places (6.3) and the rest cadence.** Pattern trio, then one
  planner rule.
  **Create** `scripts/poi_body_places.py`: one bulk Overpass query over the registry
  bbox for `amenity=toilets` and `amenity=bench`/`leisure=bench` nodes ($0, no model
  call), written to `data/paris/body-places.json` (NOT into poi-raw.json — these are
  not narrated places and must never enter the beat pipeline), uploaded as POI nodes
  with a new `poi_role="body"`. **Extends:** the Overpass mechanics of
  `scripts/poi_opening_hours.py` (its `assert_ingestable`-then-httpx door, its
  one-retry-then-abort rule, and its descriptive User-Agent — the 406 lesson W1.8
  already paid for); a second fetch is justified because the QUESTION differs
  (unnamed amenity nodes, no name-matching, separate output file) — say so in the
  header, `make dedup-review` reads both.
  **Planner seat:** `POI_ROLE_MULTIPLIER` gains `"body": 0.0` so score can never
  seat one (the dwell-pool filter at `selection.py` ~1805 already ejects zero-weight
  roles — measured in this re-plan: `ELIGIBLE_POI_ROLES` in density is
  `{"stop","setting"}` and body nodes carry no beats, so the tourability gate never
  sees them either; no density change needed). **File:** `src/tour/selection.py` — a
  post-greedy seating rule `_seat_body_stops`: with `rest_cadence_minutes` set, any
  stretch of walking longer than the cadence gets the nearest body place within a
  bounded detour seated as a zero-narration stop. **Extends:** considered
  `_apply_fill_pass` — rejected: fill optimises the dwell target; this satisfies a
  cadence constraint; different question, stated in the docstring, and
  `make dedup-review` will read both. Cites Nadia step 5 ("Ten minutes, zero cultural
  content, entirely non-negotiable"), Rosemary steps 3 and 7, design §3.1 ("a rest
  window with no bench under it is thirteen minutes standing on a stick"). Full
  promise-grade protection arrives with Phase 3's protected class; Phase 2 seats
  them.
  **Structural test** `tests/test_poi_body_places.py` (mirrors the opening-hours
  guard: in-body loop over an allow-list that starts EMPTY — the suite hard-errors
  on pytest skips, the Phase 1 lesson — plus hop tests: upload carries `poi_role`
  for body nodes; a body POI loads through `_snapshot_from_records` with
  `beat_count=0` and seats nowhere without the cadence axis).
  **Command:** `make test-file FILE=tests/test_poi_body_places.py` RED (hops) →
  GREEN at the loader step, exactly the S1.4b→S1.5b shape. Make target
  `poi-body-places` (`$(PRE_PY)` only — no render-key, it spends nothing) + `.PHONY`
  + `docs/MAKE_TARGETS.md` row (the three-way guard is measured drift-red already;
  my rows must be correct in all three lists).

  **How this step gets sabotaged.** Extending `_apply_fill_pass`. Giving body places
  a non-zero score multiplier. Seating a rest window with no bench under it. Writing
  body places into `poi-raw.json`, which would feed them to the beat pipeline and
  the visit-capacity bars. Declaring the allow-list with `@pytest.mark.parametrize`
  over an empty tuple — the suite converts the resulting skip into an ERROR (Phase 1
  measured it); loop in-body.

- [ ] `[DATA]` **S2.6 — Place judgements (6.4).** Pattern trio: **Create**
  `scripts/poi_place_judgements.py` (audited AI pass over poi-raw.json; three
  booleans + one basis sentence each: *children can run here*, *you can sit and talk
  here*, *good to be left after dark*) + `tests/test_poi_place_judgements.py`
  (structural + hop tests, empty allow-list start, in-body loops) + `poi-place-judgements`
  target (`$(PRE_PY) render-key`, the paid shape) + upload/Cypher/contract columns
  in the S1.4d/S1.5a/S1.5b mould (both upload lists, `LOAD_PARIS_POIS_CYPHER`,
  `_snapshot_from_records`, additive `POI` fields defaulting to None/""). The design
  flags 6.4 as the ONLY row with no external source — **sampled hardest in review**:
  W2.9's review samples these at twice the rate. Phase 2 wires ONE consumer per
  judgement where D2 needs the days to differ: family days weight children-can-run
  places up; take-it-easy and couple days weight sit-and-talk up — a bounded,
  test-pinned factor in `poi_score` (which now carries the deliberate-overlap
  cross-comment to `spotlight`; the new factor is added in `poi_score` ONLY, with
  one sentence saying why spotlight does not move: banding is not party-aware in
  this phase). Cites Nadia ("38 of her 55 place-minutes") and Fiona & Dev's two
  green chairs. Dark-finish waits for Phase 3 (it needs the clock priced per leg —
  and the Phase 1 panel's Sofia condition is already recorded against Phase 3).
  **Command:** structural file RED→GREEN at its loader hop, S1.4b-shape. Cost: one
  full-corpus audited pass, ~25 calls, stated and spent.

  **How this step gets sabotaged.** Sampling 6.4's rows at the normal rate. Wiring
  the dark-finish judgement now. Making the family and couple weightings unbounded.
  Adding the factor to `spotlight` too "for consistency" — that re-opens the
  deliberate-overlap ruling without a reason.

- [ ] `[BUILD]` **S2.7 — Route surface (6.2).** **File:** `src/tour/routing_client.py`.
  Per W2.1's answer. YES-path: `RoutingClient.route`/`route_with_receipt`/`leg_seconds`
  accept an optional per-request pedestrian costing override; when the
  `route_surface` axis is set, requests carry the step-avoiding configuration W2.1
  proved. The receipt machinery binds it with NO further work — the receipt's config
  is derived from the request itself (`ValhallaLegReceipt._canonical_payloads_match_fields`
  strips `locations` and hashes the rest), so routed legs remain replayable
  evidence; `VALHALLA_ROUTING_CONFIG_JSON` stays the default. Threading:
  `select_route`'s `leg_fn` and `summarise_route`'s transits carry the override when
  the axis is set. NO-path (kill criterion): the axis is still ACCEPTED, no costing
  changes, and planning records a degradation row — "step-free could not be
  guaranteed on this route" — through `record_routing_degradations`'s channel, which
  both surfaces already render.
  **Test:** extend `tests/test_tour_routing_engine.py::test_requests_use_documented_wire_format`
  with the surface options — **the audit's own ruling for this exact test**
  (05-audit-B: LOAD-BEARING, "Extend this row with the surface options rather than
  writing a second wire-format test"). Plus a `test_tour_party.py` behaviour test:
  axis set → the mock transport sees the override in the request body; axis unset →
  byte-identical body to today. Cites Rosemary step 4 (the riverside stairs "any
  shortest-path router would love"), Marcus step 2.
  **Command:** `make test-file FILE=tests/test_tour_party.py::test_step_free_axis_rides_the_costing_options`
  RED→GREEN. **Declared breakage:** none (axis unset = byte-identical request).

  **How this step gets sabotaged.** Planning on the capability before W2.1 answered.
  A silent soft-failure on the NO path — the axis must be accepted AND disclosed.
  Mutating the module-level `_ROUTING_CONFIG`/`_PEDESTRIAN_COSTING_OPTIONS` instead
  of passing per-request — that would repoint EVERY request (including the reach
  contour) and change `VALHALLA_ROUTING_CONFIG_SHA256` for unrelated tours. Writing
  a second wire-format test.

- [ ] `[BUILD]` **S2.8 — Escape radius.** **File:** `src/tour/selection.py`. With
  `escape_radius_m` set (family), every candidate must sit within the radius of the
  start — a CANDIDATE filter, not a leg rule: "a meltdown 25 minutes from the exit
  means carrying a child for 25 minutes" (design §2.4; Nadia's locked cost D4 —
  distance from exit, not leg length). It sits in the candidate loop beside the
  clock filter S1.6b landed (same admission layer, same identity default), recorded
  nowhere — unlike a closed museum, a too-far place needs no disclosure; it is
  simply out of this family's world.
  **Test** (`tests/test_tour_party.py`): a rich anchor just outside the radius is
  refused on family, seated on solo. RED→GREEN. **Declared breakage:** none.

  **How this step gets sabotaged.** Implementing it as a leg rule. Applying it to
  parties other than family (the axis applies wherever SET — but only the family
  preset sets it). Recording exclusions for it — the clock filter records because a
  closed anchor needs explaining; a far bench does not, and cluttering
  `clock_exclusions` with radius ejections would bury the day's real disclosures.

- [ ] `[BUILD]` **S2.9 — The export sync becomes a target (deviation iii).** **Create:**
  `scripts/sync_poi_exports.py` — propagate a named field list from
  `data/{slug}/poi-raw.json` into every `data/{slug}/export/*.json` chunk, byte-safe
  (the `dump_pois` round-trip guard, imported). **Extends:** three manual
  performances of the same block (the visit-duration doc's mandated hand-sync, W1.8's
  scratch script, and the identical warning now printed by three passes) —
  `CLAUDE.md` §1.7's rule that the third copy becomes the template. Make target
  `sync-poi-exports` (`$(PRE_PY)`, $0) + `.PHONY` + docs row. The three pass scripts'
  "NEXT, AND MANDATORY" trailer lines now name the target instead of describing the
  manual step.
  **Test:** `tests/test_export_consistency.py` already guards the RESULT (drift
  fails); add one hop-style test that the script's field list includes every
  enriched field the three passes write (source-scan, the `test_golden_diff_cli`
  genre). RED→GREEN on the new test.

  **How this step gets sabotaged.** Writing the sync loop inline in W2.9 a fourth
  time. Hardcoding the field list in the script AND in the passes — the script owns
  it; the passes' trailer just names the target.

- [ ] `[DATA]` **W2.9 — Run the passes; review; upload.** `make poi-body-places SLUG=paris`
  ($0 OSM) → `make poi-place-judgements SLUG=paris LIMIT=10` → review per the
  command-doc pattern, **6.4's rows sampled at twice the rate** → full pass (~25
  calls, stated and spent) → `make sync-poi-exports SLUG=paris` → `make deploy
  CITY=paris TARGET=local` → the two structural files + `tests/test_export_consistency.py`
  green, with `paris` added to both new allow-lists as the declaring act.

  **How this step gets sabotaged.** The three from W1.8: the export sync skipped
  (now a one-command target precisely so this cannot happen quietly), a sampled
  review reported as full, and cost raised as a question instead of stated and
  spent. Plus: adding `paris` to an allow-list BEFORE its pass ran, which turns the
  guard vacuous in the other direction.

- [ ] `[GATE]` **W2.10 — The panel.** All eleven personas, one message, on the six D2 days —
  the REAL per-stop tables S2.1 prints (stops, categories, per-stop minutes, walking
  legs, longest leg, rests seated, ceilings applied), never a summary. This phase is
  §1.10's home case: a change to what a stop costs and what the planner will refuse.
  Dissents reported by name — Théo watching the ceiling, Rosemary the leg cap,
  Julien that solo gained no ceiling he didn't ask for.

  **How this step gets sabotaged.** Everything in W1.9's list. Handing the panel
  fewer than the six real days.

- [ ] `[GATE]` **W2.11 — DEMO D2.** One start (**Place des Vosges** — the corpus has no POI
  named "Rue Royale"; the flagship's own start resolved by coordinates in D1, and
  D2's six-preset comparison needs a start every preset can walk, with the Phase 1
  clock data live around it), one clock (`--date 2026-08-12 --time 10:00`), six
  preset runs of the S1.3c harness + **one seventh run under `--end-hardness wall`**
  (the Marcus condition: the printed total never exceeds the asked minutes — read
  straight off the breakdown). One side-by-side table the owner reads, assembled
  from S2.1's per-stop lines verbatim: stops, categories, stand/visit minutes, walk
  minutes, longest leg, rests seated, ceilings applied. **W2.12 —** the PHASE CLOSE
  BAR (§0.7): the tests Phase 2 wrote, `make lint`, `make dedup-review`, the demo
  watched. **Not `make audit`.** Then judge, commit (explicit paths — the
  certification-hash note fires again: `request_sha256`s move with the new TourInput
  fields; declare in the commit message, re-seal stays Phase 8), amend-and-carry
  this plan.

  **How this step gets sabotaged.** Presenting fewer than six days, or six days that
  differ only in stop count — the owner must see six different DAYS. Running `make
  audit` as the close bar. Skipping the wall run because the six presets "already
  show hardness" — they do not; none of them sets it.

---

## 4. PHASES 3–8 — deliverables, seams, demos, kill criteria (re-planned at step level per phase)

Per design §9: **each of these is planned to step level only once the phase before it
has demoed**, against the tree as it then is, with every file its steps touch read end
to end at that moment (§0.2 lists the known unread set). What is fixed NOW is each
phase's deliverable, its demo, its kill criterion, its deletion obligations (§10.8.5:
replaced paths die in the same phase), and the seams that get source-scanning tests.
New deletion guards extend `tests/test_tour_one_engine.py` (the established genre — one
`test_*_is_gone` per deletion, non-vacuity first, tombstone data excluded from its own
sweeps).

### PHASE 3 — Promises and fabric; pins; the queue as a fourth time. Demos **D3 "the rainy day"** and **D4 "pin it"**.

> **Carried from the Phase 1 panel (2026-08-07, verdicts 7 BETTER / 4 MIXED / 0
> WORSE; full record in phase1-ledger.md W1.9):** (i) **delete-vs-demote** — Camille,
> Théo, Greta and Fiona & Dev all ruled that a clock-closed building should become an
> OUTSIDE-ONLY stop (interior and queue zeroed, exterior minutes kept, marked "closed
> today") rather than leave the pool; the D1 Monday run itself starts at a
> Monday-closed Orsay, which makes the point. The visit-shape machinery this needs
> (§3.1 promises carry the SHAPE of the visit) lands in this phase — wire the closed
> case to the outside-only shape here. (ii) **Nadia's concentration rule** — a
> closure-thinned field must not refill into one giant front-loaded stop; every
> prefix decent. (iii) **Sofia's after-dark swap rule** — a closure substitution must
> never trade a lit interior for unlit open ground once legs are priced by hour
> (6.6 lands here). (iv) The Phase 1 kill criterion FIRED (52% gated-hours coverage
> vs the 90% bar): **6.1 completion is its own phase** — plan it alongside or before
> this one; Aiko's "hours unverified" print belongs to it.

- **Delivers:** the plan becomes 2–5 PROMISES on a clock connected by FABRIC (design
  §3); the generalisation is the one already named in §3.5 — `select_route`'s single
  protected endpoint (`_materialize_fixed_end_b`, `protected_end_id` in the timebox
  repair) becomes a SET of protected promises. Visitor pins (§3.2). Queue priced
  separately by hour and season, excluded under `wall` (§3.3, data 6.5). Leg
  properties covered/lit priced at the hour walked (6.6), forecast fetch (6.8, moved
  here from Phase 1 with its consumer). The replanner guardrails §4.5.1–5 land here
  as planner rules (visitor-time pricing, the protected class, drop-re-checks-leg-cap,
  the terminus is not the shock absorber, category-diverse replacement — Greta's
  consumer for 6.7).
- **Seam that must not fork (source-scanning test):** PROMISE PRICING — one definition
  of what a promise costs and when it is at risk, in the `visit_time.py` mould, with a
  test in the `test_one_time_currency.py` genre asserting no second spelling appears.
- **Demo D3:** the same request dry vs rain, side by side — the rainy day's legs are
  covered and the arcade is an anchor (Aiko). **D4:** pin the chapel; watch the day
  rebuild around it (Théo's Conciergerie shape).
- **Kill criterion (design §9):** if promises make planning slower than a stated
  wall-clock budget (set at re-plan time from a measured baseline), promise count is
  capped before anything else is traded.
- **Read preconditions for its re-plan:** `src/tour/density.py`, `generation.py`,
  `beat_select.py`, `ordering.py`, `place_materialization.py` — plus re-reads of any
  §2 file whose hash moved.
- **Panel:** mandatory (§1.10) — this is the largest tourist-visible change in the
  redesign.

> **RE-PLANNED AT STEP LEVEL 2026-08-11, after D2 demoed, against commit `e4a576aa`**
> (the plan's own §4 rule). Every file below was read end to end or hash-verified at
> this moment; the ledger addendum below records the evidence. The Phase 2 panel's
> carry-forwards belonging to THIS phase are folded into the steps that answer them.

**Read evidence for this re-plan (2026-08-11, tree `e4a576aa`)** — path, lines, blob:
`generation.py` 1289 (19274d5c) — read end to end this session; finding: promises
need NO generation change (the closed/outside-only shape rides
`Route.planned_visit_seconds`, which `_flatten_pois` already prices through the one
imported `stop_seconds`; content adaptation is Phase 6's). `beat_select.py` 1165
(4680c3fe) — read end to end; untouched by this phase (audio governance and
keep-exploring unchanged). `place_materialization.py` 750 (7cb5dffc) — read end to
end; untouched; audit G's `tier == 1` review item RESOLVED-KEEP: a synthetic
relocated destination has no own-merit data (no judgements, no category) to score
on, so the no-inherited-gravity floor stays. `ordering.py` 201 (53cf3dcc,
unchanged since the §3 ledger) — re-read; finding: `held_karp_open` under
`round_trip` minimizes a CLOSED loop whose direction is chosen only by
tie-break, which makes Nadia's concentration rule implementable as a cost-free
direction choice. `visit_time.py` 116 (aaae2040) + `tests/test_one_time_currency.py`
101 (a97dd745) — re-read in full; the seam genre exemplar. Phase 2's own files
carry this session's complete diffs; current hashes: `selection.py` 3a0eadfb
(4633), `contract.py` 7c22e1d4 (1085), `routing.py` b29b420c (728),
`routing_client.py` 709ad986 (336), `tour_build.py` c4eff570 (853),
`upload_paris.py` 7b74a22c (640), `density.py` aa148f2b (539), `Makefile` 3acb3ce7.

**Kill-criterion baseline, measured this session (dev graph, live Valhalla, this
machine):** the seven D2 180-minute Place des Vosges runs planned in 3.3–5.6 s
wall-clock; the 300-minute A→B flagship-class run planned in 42.7 s. **The stated
budget: promises may not push either class past 2× its baseline — ≤ 11 s for the
180-minute round trip, ≤ 85 s for the 300-minute A→B.** Over budget → promise
count is capped (5 → 3) before anything else is traded, per the phase's own kill
criterion.

**Deviation register for this re-plan** (each owner-visible and cheap to overrule):
(i) **Data row 6.6 collapses into derivation** — no data pass. Place-level
coveredness follows `place_category`, already priced for all 370 POIs (arcade /
museum / church / gallery = covered; square / garden / street / bridge / park /
market = open; "other" defaults open — the safe direction for rain). "Lit" for the
finish is `good_after_dark` (6.4, already priced) plus a dusk computation.
Per-LEG covered/lit from OSM way tags is DEFERRED with its gap named: the data
does not exist in this corpus, Valhalla exposes no per-request read of it, and the
place-level treatment serves both D3 and Sofia's swap rule; the per-leg form
belongs with Phase 5's live re-pricing. (ii) **Aiko's "hours unverified" print
moves INTO this phase** — the coarse plan filed it under the future 6.1-completion
phase, but the panel has now raised it twice (W1.9 dissent 4, D2 panel finding 4)
and D3/D4 are DATED demos where four confident exclusions beside unchecked doors
would lend exactly the false trust she named. The 6.1 data-completion CAMPAIGN
(52% → 90% coverage) remains its own phase, after this one. (iii) **Meal-window
promises deferred** — §3.1 lists them; the corpus has no restaurant data and
inventing placeholder meals would violate the never-create-empty-nodes
convention. Stated as a cost; the promise model carries a `kind` so meals are an
addition, not a rework. (iv) **Rain prices TIME, not preference:** under rain an
uncovered place's visit worth halves (`RAIN_DWELL_FRACTION = 0.5`, test-pinned) —
people do not linger in wet squares — so selection shifts to covered places
through the existing value model instead of a bolted-on score nudge, and the
covered arcade rises to anchor for free (D3's own bar). The design left the
mechanism open; this is the one that spends no new machinery. (v) **Queue pricing
is estimate-then-exact**, the walk clock's own shape: the greedy prices a queue at
the REQUEST's start-hour band (peak/off-peak), the repair's trials and the final
route re-price at each stop's ordered arrival hour. (vi) **Concentration is a
direction choice on round trips**: a closed loop's two directions cost the same,
so the marquee lands late deliberately (Nadia: "Tuesday's back-loaded anchor was
right by luck; make it deliberate"); on one-ways geometry constrains and the rule
is a preference, stated. (vii) **One Phase 1 test is deleted by panel order, not
audit order**: `test_a_poi_closed_for_the_whole_visit_window_is_excluded_and_recorded`
pins delete-on-closure — the behaviour four personas overruled (W1.9 dissent 1,
"the strongest recurring finding"). Its replacement is written fresh from the
panel finding (closed → OUTSIDE-ONLY stop, interior and queue zeroed, exterior
minutes kept, disclosed); the dateless-identity and Monday-seated tests survive
untouched. (viii) The queue pass reviews at the STANDARD rate with targeted spot
checks (famous queues checked by name), not 6.4's double rate — queues have
external grounding (public tourist knowledge) where 6.4 had none; stated so the
choice is visible.

### Steps (Phase 3)

- [ ] `[DEMOLISH]` **D3.0 — the audit's Phase 3 rows, plus the five standing reds.**
  Delete, with each audit row cited in the commit: `test_tour_certification_selection.py::
  test_bounded_exchange_is_exact_deterministic_and_rejects_slog_and_overmax`,
  `::test_ratio_exceeding_route_is_deterministic_last_resort`,
  `::test_over_ceiling_route_is_repaired_by_dropping_one_stop` (05-audit-F:
  DELETE-AT-PHASE-3; the surviving invariants are re-written fresh by S3.8's
  citation tests); `test_tour_selection.py::test_oneway_endpoint_pull_reaches_far_envelope`
  (05-audit-A: replacement lives in this phase's pin work);
  and the five standing reds Phase 1/2 carried —
  `::test_phase7_fill_pass_concorde_smoke_real_corpus`,
  `::test_demotion_merged_via_select_route_end_to_end`,
  `::test_frozen_end_none_ordered_ids_haversine_path`,
  `::test_frozen_end_none_ordered_ids_routed_path`,
  `::test_end_none_route_records_exempt_anchor_identity` (05-audit-A §4.7/§4.8:
  DELETE / FAKE; this phase's promise work replaces the machinery they pin).
  Also delete `tests/test_tour_clock.py::test_a_poi_closed_for_the_whole_visit_window_is_excluded_and_recorded`
  (deviation vii — replaced fresh by S3.5's test). **Fixture-coupling check first**
  (§0.7): grep every deleted test's private helpers across tests/ before removal.
  Proof (survivor form): the S1.6b siblings
  (`test_the_same_poi_is_seated_on_a_day_it_is_open`,
  `test_no_datetime_means_no_filtering_and_a_byte_identical_pool`) still collect
  and pass, and `make lint` is clean. **Watch list** (§0.3, decision pre-written):
  `test_phase7_fill_pass_respects_walk_budget_cap`,
  `::test_phase7_fill_pass_under_floor_rescue_adds_nearby_stop`,
  `::test_phase7_fill_pass_rescue_rejects_far_walk_slog` are audit-DELETE rows
  currently green; if any turns red during S3.x it is deleted citing its row, not
  nursed.

- [ ] `[BUILD]` **S3.1 — the harness speaks promises (§10.9 measurement-first).**
  **File:** `scripts/tour_build.py`. `--pin <name-or-latlng>` (repeatable,
  resolved through the SAME `_resolve_start` resolver), `--weather dry|rain|auto`
  (auto = live fetch via S3.9; default None = today, byte-identical). The
  per-stop table gains a SHAPE column — `44m in` / `15m out` / `closed—out` —
  and a `queue` column (minutes, `—` when none); a `promises:` line above the
  table names each promise (kind + stop + window); dated runs print Aiko's
  honesty line: "hours unverified for N of the M gated stops on this route"
  (deviation ii). **Extends:** `_build_arg_parser` and `_print_breakdown`, the
  one parser and one printer. **Test file:** `tests/test_tour_promises.py` (one
  hand per file, the clock/party mould; forbid-guard dependency noted in its
  header). RED→GREEN on the parser/printer nodes.
  *Sabotage:* a second printer; a shape column only on promise stops (same shape
  everywhere, dashes when absent); resolving pins with new lookup code instead of
  `_resolve_start`.

- [ ] `[BUILD]` **S3.2 — the contract learns promises.** **File:**
  `src/tour/contract.py`. `TourInput` gains `pinned_poi_ids: tuple[str, ...] = ()`
  and `weather: Literal["dry", "rain"] | None = None` (None = no signal = today).
  `POI` gains the 6.5 columns — `queue_class: Literal["none","short","long",
  "unpredictable"] | None = None` (None = pass not run = never priced, the safe
  default), `queue_minutes_peak: int`, `queue_minutes_offpeak: int`,
  `queue_peak_hours: str` (JSON-encoded hour ranges, the opening_hours precedent),
  `queue_basis: str` — additive, same comment style. New frozen models
  `PromiseShape` (outside_seconds, inside_seconds, queue_seconds, goes_inside,
  closed_today) and `Promise` (kind: anchor|pinned|rest|finish, poi_id, shape);
  `Route.promises: tuple[Promise, ...] = ()` — additive, the vignettes mould.
  **Extends:** TourInput/POI/Route themselves; the §2.4/6.1 field precedents.
  RED (extra_forbidden) → GREEN → UNDO → RESTORE.
  *Sabotage:* a queue default that prices an unpassed corpus; a Promise model that
  carries scoring state (promises are OUTPUT, the planner's obligations — not
  knobs).

- [ ] `[BUILD]` **S3.3 — THE promise pricing (the §10.8.4 seam).** **File:**
  `src/tour/visit_time.py`. `visit_shape(poi, interest, snapshot, *,
  party_ceiling_seconds, clock_hour, closed_today, weather, wall) -> PromiseShape`
  — THE one definition of what standing at a place costs: outside/inside split
  (today's lens-relation arithmetic, extracted), queue seconds by arrival-hour
  band when `goes_inside` (6.5), `closed_today` forces outside-only with queue
  and interior zeroed (the delete-vs-demote fix), `wall` refuses `goes_inside`
  whenever a queue exists (§3.3 "excluded entirely under wall"; §2.3 "no stop
  whose duration is unboundable"), rain halves an UNCOVERED place's dwell worth
  (deviation iv; coveredness derived from `place_category` in ONE helper here).
  `visit_seconds` becomes a delegation to the shape's total — one definition,
  never two. **Seam test:** new `tests/test_one_promise_pricing.py` in the
  `test_one_time_currency.py` genre — a source scan asserting no second spelling
  of queue pricing, coveredness, or the outside/inside split appears anywhere,
  plus behaviour tests citing §3.1/§3.3, Camille's 28+38 (01:77-84), Théo's
  exterior-only visit (panel), Marcus's queue refusal (04:45-47).
  RED→GREEN→UNDO→RESTORE.
  *Sabotage:* pricing the queue into `visit_seconds_inside`(the exact one-number
  folding Camille's bullet forbids); a second coveredness map in selection.py;
  `wall` deleting the STOP instead of its interior (the outside-only shape is the
  whole point).

- [ ] `[BUILD]` **S3.4 — queue columns ride the three closed hops.** **Files:**
  `src/tour/selection.py` (`LOAD_PARIS_POIS_CYPHER` RETURN + `_snapshot_from_records`
  constructor), `scripts/upload_paris.py` (both property lists) — the S2.6 mould
  exactly. Structural test file `tests/test_poi_queues.py` (empty allow-list,
  in-body loops, both-lists scan, hop tests) — authored with the data script by a
  subagent; the hops go green at this step. RED (hops) → GREEN.
  *Sabotage:* the empty-tuple parametrize trap; defaults at upload.

- [ ] `[BUILD]` **S3.5 — closed means outside-only, not gone.** **File:**
  `src/tour/selection.py`. The S1.6b clock filter stops EXCLUDING: a POI closed
  for the whole window stays in the dwell pool re-priced through
  `visit_shape(closed_today=True)` (outside minutes only), and the disclosure
  line becomes "closed today — outside only" (the ClockExclusion channel is
  reused; its reason text now says demoted, not removed). A place with NO
  outside value (`typical_duration_min == 0`) keeps today's exclusion — nothing
  to stand and see is the one honest removal, recorded. **Replaces** the deleted
  Phase 1 exclusion test with a fresh one citing W1.9 dissent 1 by name (Camille,
  Théo, Greta, Fiona & Dev) and the D1 demo's own self-defeating Monday-closed
  start. RED→GREEN→UNDO→RESTORE.
  *Sabotage:* keeping exclusion for SOME closed places (tier-keyed or
  score-keyed); losing the disclosure; pricing the closed interior anyway.

- [ ] `[BUILD]` **S3.6 — promises assembled; the protected set; pins.** **File:**
  `src/tour/selection.py`. After the final ordering, `_assemble_promises` names
  2–5 promises: the marquee anchor (the governor-exempt identity that already
  exists), every pinned stop, every seated body stop (S2.5's — now
  promise-grade, the plan's own carried clause), and the finish (the pulled
  endpoint / materialized B / a round trip's last stop). THE PROTECTED SET:
  `protected_end_id` (one id) generalises to `protected_promise_ids` (a set)
  threaded through the timebox repair's drop enumeration — a drop may not remove
  a protected id (extends `test_timebox_drop_never_removes_the_materialized_fixed_destination`,
  audit C's KEEP-AND-EXTEND ruling, §4.5.2/§4.5.4: rests and the finish are
  never auto-cut; the terminus is not the shock absorber). PINS: a pinned POI is
  force-seated before the greedy (reachability and clock checked; an
  unseatable pin is an honest refusal naming the pin), never dropped by any
  repair, never traded by the pull. **Command:**
  `make test-file FILE=tests/test_tour_promises.py::test_a_pinned_stop_is_seated_and_survives_every_repair`
  RED→GREEN, plus `::test_rests_and_the_finish_are_never_auto_cut`. Citations:
  §3.2 (Théo pins one thing absolutely; Julien pins nothing), §3.5, §4.5.2/4,
  audit C's `test_ab_request_route_ends_at_b` GROW ruling.
  *Sabotage:* protecting by re-adding after the drop (the drop must be refused,
  not repaired); pins as score boosts (a pin is a certainty, not a preference);
  a second protected-id mechanism beside `protected_end_id` instead of
  generalising it.

- [ ] `[BUILD]` **S3.7 — dusk, and the after-dark finish.** **Files:**
  `src/tour/routing.py` (`civil_dusk_local(date, lat, lng)` — ~25 deterministic
  lines, NOAA solar approximation, cited in-comment; Extends: routing.py is the
  clock-arithmetic home and nothing computes sun times today) and
  `src/tour/selection.py`: on a DATED run whose computed finish time lands after
  dusk, a finish with `good_after_dark=False` is re-picked from the candidates
  (rank preference at the endpoint pull / final ordering) and DISCLOSED when no
  passing finisher exists — Sofia's swap rule scoped to what plan-time knows
  (6.4 finally consumed; her panel condition and the D2 panel's "priced but
  consumes nowhere" finding both close). Hermetic test: a dated evening request
  whose only rich finisher is dark-bad ends on the lit alternative instead;
  cites 11-solo-after-dark and §4.3's dusk trigger. RED→GREEN→UNDO→RESTORE.
  *Sabotage:* asking the user anything (Sofia's never-ask rule); consuming
  dark-finish on UNDATED runs (no clock = no dusk = today's behaviour).

- [ ] `[BUILD]` **S3.8 — the trades obey the panel's three rules.** **File:**
  `src/tour/selection.py`. (a) Round trips pick the loop DIRECTION whose marquee
  lands latest (deviation vi — Held-Karp already returns one of the two
  equal-cost directions; choose deliberately). (b) The repair's candidate pool
  ranks category-diverse: a candidate whose `place_category` already dominates
  the seated set is dis-preferred by a bounded, test-pinned factor (§4.5.5,
  Greta's 6.7 consumer). (c) The §4.5.3 citation test, written fresh (audit F
  names it as the deleted drop test's one surviving invariant): a drop that
  merges two legs past the cap is refused — the mechanism S2.3 already built,
  now cited and pinned from the design. Three node-id commands, RED→GREEN each
  (the (c) test may be born green against the existing mechanism — its RED is
  proven by the undo test instead, stated here).
  *Sabotage:* direction choice re-ordering an OPEN walk (loops only); an
  unbounded category penalty (it must never beat a landmark, the §2.4:130
  principle); writing (c) against a new mechanism instead of citing S2.3's.

- [ ] `[BUILD]` **S3.9 — the forecast is fetched, never asked.** **New file:**
  `src/tour/weather.py` (~60 lines): `fetch_rain_likelihood(date, lat, lng)` via
  open-meteo (keyless), returning dry/rain/None-on-failure — fail-open to None
  (no signal = today's planning), 2-try-then-None, descriptive User-Agent (the
  W1.8 lesson). **Extends:** considered `routing_client.py` (it owns HTTP) —
  rejected: that client speaks to OUR Valhalla with receipts and sticky
  degradation; a public one-shot forecast fetch shares none of that contract;
  stated here per §10.8.1. Harness `--weather auto` consumes it; hermetic test
  via MockTransport. Cites §2.5 ("Weather (fetched)"), §6.8, D3.
  RED→GREEN→UNDO→RESTORE.
  *Sabotage:* blocking planning on a fetch failure; a second HTTP door with no
  UA; asking the user.

- [ ] `[DATA]` **W3.1 — the queue pass (6.5).** Script + structural tests authored
  by a subagent in the established trio pattern (`scripts/poi_queues.py`,
  imports the visit-duration door, twice-tried, `--limit` writes nothing);
  ~25 model calls over 370 POIs, stated and spent. Review at standard rate plus
  named spot checks (Louvre, Sainte-Chapelle, Orsay, catacombs-class
  unpredictables if present); `make sync-poi-exports` (the field list grows —
  the S2.9 hop test forces the sync list to keep up); deploy local; parity;
  `paris` onto the allow-list as the declaring act.

- [ ] `[GATE]` **W3.2 — the kill criterion, measured.** Re-run the baseline cells
  (the seven 180-minute D2 requests + the 300-minute flagship) on the
  promise-bearing planner. Over 11 s / 85 s respectively → cap promises 5 → 3
  and re-measure before touching anything else. Numbers into the ledger either
  way.

- [ ] `[GATE]` **W3.3 — Demos D3 and D4.** D3: one dated request near the covered
  passages, `--weather dry` vs `--weather rain`, side by side — the rain day's
  anchors go covered and the arcade anchors (Aiko). D4: a start whose plain day
  omits Sainte-Chapelle, then `--pin "Sainte-Chapelle"` — the day rebuilds
  around the pin, which survives every repair (Théo). Real harness runs, saved
  verbatim under `evidence/`.

- [ ] `[GATE]` **W3.4 — the panel.** All eleven personas, one message, on the real
  D3/D4 tables plus a closed-building day showing the outside-only demotion.
  This phase is §1.10's home case squared — the largest tourist-visible change
  in the redesign. Dissents by name; Nadia checks the concentration rule, rosemary
  the protected rests, Marcus the wall/queue exclusion, Aiko the honesty line,
  Sofia the dusk rule, Théo the pin.

- [ ] `[GATE]` **W3.5 — close.** The phase's own tests + `make lint` +
  `make dedup-review` + the demos watched (§0.7 — not `make audit`). Judge.
  Commit (explicit paths; the TourInput/POI field additions move
  `request_sha256`s again — declared, Phase 8 re-seals). Amend-and-carry this
  plan; re-plan Phase 4 at step level.

### PHASE 4 — One day + dials on both surfaces; **delete pick-one-of-three (8.1)**. Demo **D5 "turn the dial"**.

- **Delivers:** the product stops offering three routes; one day with dials (calmer /
  fewer / shorter / quieter) replans live in the workbench. Greta's "less of THIS
  KIND today" and Rosemary's "shorter walks = shorter LONGEST walk" dial semantics
  (panel locked costs) bind the dial definitions.
- **Deletions in the same phase (§10.8.5):** `select_k_routes`, the diversity
  penalty and Jaccard rejection (`selection.py`), the flavour UI on both surfaces,
  and the option-picking plumbing that exists only to serve three
  (`_preview_plan_fingerprint`'s opt-N selection narrows to one). Each deletion gets
  its tombstone row in `test_tour_one_engine.py`; the existing
  `test_one_planner_produces_the_options_and_one_interleave_builds_them` is
  re-derived at that moment (its clause 3 currently pins `select_k_routes` as a
  live primitive — its rewrite is a written decision citing 8.1, not a quiet edit).
- **Demo D5:** four dial turns, each replanning live in the workbench, watched.
- **Read preconditions:** `frontend/review.html` (6,305 lines — the biggest unread
  surface in the repo), `src/tour/options.py`, `premium_tour.py`,
  `mobile/lib/pages/trip_itinerary_page.dart`, `trip_service.dart`.
- **Risk to carry:** the workbench Playwright suite (`test_workbench_ui.py`,
  `test_workbench_matches_the_app.py`) pins the three-option flow; the Phase 4
  re-plan audits those files under §0.1 before touching the UI.

> **AMENDED AND CARRIED AT CLOSE, 2026-08-18 (W4.13).** All thirteen steps
> executed; the full record is `phase4-ledger.md` (Parts 1 and 2). Deviations
> from the step text, each argued in the ledger: (i) the flavour suite's
> `build_route_option` half MOVED to `tests/test_tour_options.py` instead of
> dying (plan defect §0.2); (ii) `score_penalty` threading SURVIVES as the rain
> channel (plan defect §0.2 — "delete the threading" was measured false);
> (iii) the harness gained no new dial flags — the workbench is the dial surface;
> (iv) `resolve_party_axes` is now called at the API's ONE construction door
> (`_build_tour_input`) — it had been called by the harness alone, so presets and
> the More-stops dial were dead on the wire (found by the W4.12 panel);
> (v) `select_route` plans WITHOUT a leg cap first and returns that day when it
> already honours the cap ("already true", locked semantics 1); (vi) promise
> windows are made COARSE at the wire (5-minute marks), the planner keeps the
> exact minute for Phase 5. The W4.12 closing panel ruled NEEDS-WORK; the
> planner-depth findings it exposed are CARRIED to Phase 5 with numbers (ledger
> Part 2 "CARRIED"), and head Phase 5's step-level re-plan below.
>
> **RE-PLANNED AT STEP LEVEL 2026-08-11, after Phase 3 closed, against commit
> `258933fd`** (the plan's own §4 rule). The §0.1 audit of the Playwright suites
> the coarse block demanded is DONE: **`05-audit-E-workbench-phase4.md`** (83
> tests: 5 DELETE / 16 KEEP-AND-REWRITE / 62 KEEP, four cross-file couplings
> named). D4.0 reads its rows from there, never re-derives them.

**Read evidence for this re-plan (2026-08-11, tree `258933fd`)** — path, lines,
how read: `src/tour/options.py` 357 — read end to end this session; finding:
the ONE interleave (`build_route_option`) is count-agnostic and SURVIVES Phase 4
almost untouched (docstring framing only). `src/api/routes/trips.py` 1,475 —
read end to end; the full opt-N surface mapped (generate flavours loop 493–651,
compose opt-N parse 715–725, `_preview_plan_fingerprint` 1036–1051,
`_plan_options` 1075–1090, preview 1110–1153, author opt-N + 409 1159–1231).
`src/tour/premium_tour.py` 1–640 read end to end (the whole Block-1 planning
half: `plan_premium_options` 562–625 with its `select_k_routes(…, 3)` call at
589, `plan_premium_tour` the one-line chosen-flavour delegate at 628); 640–1036
verified flavour-free by scan (only a docstring + `__all__` mention).
`src/tour/selection.py` — this session's own Phase-3 work, held cold;
`select_k_routes` 1710–1780ish, `DIVERSITY_PENALTY`/`JACCARD_OVERLAP_MAX` 249–250,
`_jaccard` 3067, and `score_penalty` threaded through 26 sites in this file and
imported by NO other src module (grep-verified) — the diversity knob exists
solely for the flavour re-runs. `frontend/review.html` 6,305 — mapped end to end
by a dedicated reader; the full region map with line spans is
**`evidence/phase4-maps/workbench-map.md`** (hash `f53b22d4`); headline facts:
the option flow lives at 1148–1174 + 3245–3328 + 3832–3974, the whole tour
feature at 3244–4031, a 409-driven re-request-and-re-render loop ALREADY exists
(3950–3960), the form carries NONE of the Phase-1–3 request fields (no date, no
party, no hardness, no pace, no weather, no pins), and the workbench renders
ZERO of the Phase-3 promise/queue/closure surface. The mobile pair
(`trip_itinerary_page.dart` 908, `trip_service.dart` 340, plus
`models/trip.dart` 273) — mapped end to end by a dedicated reader:
**`evidence/phase4-maps/mobile-map.md`**; headline facts: the picker is
k-agnostic, `composeTrip` SURVIVES (only the sheet dies), and
`GeneratedTrip.fromJson` HARD-REQUIRES `flavour_count` on the wire.
**Files a step touches that are NOT yet read end to end — each is that step's
own hard read-precondition before it enters the executing ledger (§0.2):**
`src/api/models/trips.py` (474), `mobile/lib/models/trip.dart` (273, mapped
not read), `tests/test_tour_flavours.py` (745), `tests/test_trip_preview_contract.py`
(1,046), `tests/test_premium_workbench_wiring.py` (712),
`tests/test_workbench_preview_wiring.py` (static-source assertions on
review.html — DISCOVERED by this re-plan's map; in no earlier Phase-4 list),
`tests/test_trip_api.py`, `tests/test_tour_one_engine.py` (the two re-derive
anchors: `K_OPTION_PRIMITIVES` :391, `SURVIVING_WORKBENCH_TOUR_TESTS` :1131).

**Kill criterion and its baseline (set here; the design row had none).** The
demo is LIVE dial turns, and a dial turn this phase is a FULL re-plan (no
incrementality — the living session is Phase 5's). Baseline measured this
session on this machine (evidence/phase3/w32-*): dated 180-minute cells
7–47 s wall-clock; the 300-minute flagship 44.42 s; the known driver of the
slow tail is the repair's multi-pass over the demotion-widened pool (the
Phase-3 ledger's carried finding). **The bar: a dial turn on the D5 demo cells
answers in ≤ 15 s.** Over the bar → the ONE permitted trade is bounding the
repair's trial budget on dial RE-plans (a stated, measured cap — quality and
the panel-locked dial semantics are never traded). Numbers into the ledger
either way, at W4.1 (baseline) and W4.9 (the verdict).

**Deviation register for this re-plan** (each owner-visible and cheap to
overrule): (i) **Legacy saved trips keep the opt-N compose contract forever.**
Trips persisted before this phase store multi-option `options_json`, and
`/trips/{id}/compose` must keep serving their stored picks — the opt-N parser
and the length-checked list reader STAY for stored trips; new trips simply
always store one. Stated so no later session "cleans up" the parser and breaks
every pre-Phase-4 trip. (ii) **`flavour_count` survives on the wire.** The
phone hard-requires it (mobile-map: `fromJson:241` throws without it); it is a
per-trip stop-kind stat that predates flavours and is merely mis-named.
Renaming is Phase-8 cleanup at the earliest. (iii) **The workbench form gains
the engine's real request surface in this phase** — date/time, end hardness,
party preset, walking pace, weather, pins. 05-audit-D row `:39` already
expects exactly this at Phase 4 ("replacement asserts the dial controls…
design §2.1–2.4 (new inputs)"), and without it D5's dial turns run against a
corpus whose Phase-1–3 machinery is clock-gated — a demo of nothing. (iv)
**Dial semantics prefer EXISTING TourInput axes** (`max_leg_minutes`,
`max_stop_minutes`, `walking_pace`, `rest_cadence_minutes`, lenses, weather);
a genuinely new field (e.g. a category-minus for Greta's kind-dial) follows
the S3.2 additive mould with its own RED→GREEN. Which mapping is right is the
EARLY PANEL's ruling (W4.2), not this plan's. (v) **Promise/queue/closure
rendering on the workbench day view is proposed TO the panel** at W4.2 — the
workbench shows none of it today (map-verified zero), and Phase 3's panel
raised the honesty line twice; wire sketch: `TripPreviewResponse` gains the
promises line + per-stop shape/queue fields mirroring the harness columns.
The panel decides whether it lands in S4.6 or is carried. (vi) **The
anonymous paid author endpoint stays anonymous this phase** — its closure
needs the workbench identity work another phase owns (the 2026-08-04
approval's own words); restated, not re-decided. (vii) **`plan_premium_options`
collapses INTO `plan_premium_tour`** — the singular delegate already exists
and is the extension point (§10.8.1); no third planner. (viii) **The dial
loop's request replay hazard is real and named:** the workbench replays
`lastTourPlanBody` verbatim on AUTHOR (map: 3948) — every dial field MUST
live in that body or the author call re-derives yesterday's knobs and 409s
(or worse, silently authors the un-dialed day; the fingerprint makes it a
409). The S4.6 test list pins this exact hazard.

### Steps (Phase 4)

- [x] `[DEMOLISH]` **D4.0 — audit E's rows, the flavour suite, and the two
  re-derive anchors.** *(DONE 2026-08-11 — see phase4-ledger.md. AMENDED at
  execution, §0.2 plan defect: `test_tour_flavours.py` was NOT purely "§8.1's
  own suite" — its lines 354–745 are the `build_route_option` assembly suite,
  which SURVIVES Phase 4; that half moved intact to `tests/test_tour_options.py`
  before the file died. Two argued deviations: the payload stubs collapsed to
  one option rather than deleted (a KEEP test calls `_plan_payload` directly;
  S4.8 needs the one-option stub anyway), and the two pick-flow helpers are
  failing tombstone stubs rather than absent names (eight declared-red callers
  + `make lint` F821).)* Read `05-audit-E-workbench-phase4.md` §§1–5 first — the
  rows are measured; do not re-derive. In one step: (a) DELETE the 5
  DELETE-AT-PHASE-4 tests it names in `test_workbench_ui.py` (`:2390`,
  `:2866`, `:3031`, `:3221`, and the pre-pick half of `:2907` inside its
  rewrite); (b) MOVE `_client` and `_dense_snap` OUT of
  `tests/test_tour_flavours.py` into `tests/test_workbench_matches_the_app.py`
  (their only importer, audit E §5.3 — THE hardest coupling; a test that
  cannot import does not fail, it vanishes), then DELETE
  `test_tour_flavours.py` wholesale (§8.1's own suite; §0.1.2); (c) re-derive
  the two one-engine anchors as a WRITTEN DECISION citing §8.1:
  `K_OPTION_PRIMITIVES` (:391) loses `select_k_routes` and the clause-3 pin in
  `test_one_planner_produces_the_options_and_one_interleave_builds_them` is
  rewritten against the one-day planner; `SURVIVING_WORKBENCH_TOUR_TESTS`
  (:1131) keeps pinning the two rewrite-surviving NAMES (the S4.8 rewrites
  keep those names, stated here so the guard never gaps red); (d) sweep the
  flavour-flow module helpers audit E §3 lists (`_route_option`,
  `_plan_payload`, `_generate_options`, `_pick_option`, `_route_two_step`…)
  WITH their dependent deleted tests, re-pointing `_clear_tour_route_pins`
  (used by two KEEP tests) at a one-day stub. **Declared breakage:** the 16
  KEEP-AND-REWRITE tests go red here and stay red until S4.8 (each is on
  audit E's list; a red not on it is a stop). Survivor proof: audit E's KEEP
  rows still collect; `make lint` clean.

- [x] `[GATE]` **W4.1 — measurement first (§10.9): the strawman dial tables
  and the latency baseline.** Using the EXISTING harness axes (no code): for
  three starts (Place des Vosges dated 10:00; a Louvre-adjacent dated start —
  the Phase-3 carried one-giant-stop exhibit; the 300-min flagship), produce
  the base day plus a strawman table per dial — shorter ≝ `--max-leg-minutes`
  down a band (Rosemary's locked semantics), calmer ≝ margin + rest
  (`--end-hardness wall` + `--rest-cadence-minutes`), fewer ≝
  `--max-stop-minutes` UP (fewer, longer stops), quieter ≝ lens narrowing —
  and BOTH directions where an axis allows (Théo's dials point up). Wall-clock
  every cell (the dial-latency baseline against the ≤ 15 s bar). Verbatim
  outputs under `evidence/phase4-dials/`. This gate WRITES NO CODE — it makes
  the panel's tables real and the kill criterion's baseline honest.

- [x] `[GATE]` **W4.2 — THE EARLY PANEL (§1.10; the phase's largest decision,
  taken before any dial is built).** All eleven personas, one message, on
  W4.1's real tables. They rule on: (1) the four dial NAMES, DIRECTIONS and
  mechanical meanings (binding constraints going in: Rosemary shorter ≝
  shorter LONGEST walk; Greta's "less of THIS KIND today" must be expressible;
  labels in plain bodily language — the second-language locked cost; Marcus's
  margin/predictability reading of calm; bidirectionality); (2) **the default
  day-shape question** — the Phase-3 carried finding (the unconstrained dated
  day gravitating to one giant interior) judged against the W4.1 exhibits, so
  the dial defaults and the greedy's default shape are decided TOGETHER by
  the people who walk them; (3) whether the workbench day view must show the
  promise/queue/closure surface this phase (deviation v). Dissents by name in
  the ledger. **The locked semantics BIND S4.3–S4.8; re-opening them
  afterwards is §0.8.10.**

- [x] `[BUILD]` **S4.3 — the engine plans ONE day.** **File:**
  `src/tour/premium_tour.py`. `plan_premium_options` and its K=3 loop are
  DELETED; `plan_premium_tour` becomes the real Block-1 entry (Extends: the
  singular delegate already in the file — §10.8.1): ONE `select_route` call,
  the container-identity refusal kept (`choose_discrete_route([route])`
  semantics inline — with Les Halles already excluded from the dwell pool the
  raise is a can't-happen guard, kept because the one-engine suite pins the
  primitive), `record_routing_degradations` + `_premium_route_refusal` on the
  one route. **Declared breakage:** `src/api/routes/trips.py` imports
  `plan_premium_options` (trips.py:482/1102) and goes red with every API test
  — S4.4 greens them. Test: a fresh one-day node in
  `tests/test_premium_workbench_wiring.py` citing §8.1 ("no persona ever
  wanted to compare routes"). RED→GREEN→UNDO→RESTORE.
  *Sabotage:* keeping `plan_premium_options` as a tuple-of-one shim (a second
  spelling of the one planner — the §10.8 fork); planning twice to "verify".

- [x] `[BUILD]` **S4.4 — the API serves ONE day.** **File:**
  `src/api/routes/trips.py`. Generate: the flavours loop collapses
  (`plans → plan`); `options_json` persists a ONE-element list in the stored
  shape (deviation i — the compose reader, its legacy branch and the opt-N
  parser are UNTOUCHED, so every pre-Phase-4 trip composes forever);
  `route_id` stays `{trip_id}-opt1`. Preview: `_plan_options` renders the one
  option; `_preview_plan_fingerprint` unchanged (it fingerprints a list — now
  of one); author's opt-N range check narrows naturally (`len(plans) == 1`).
  The response models (`src/api/models/trips.py` — READ IT FIRST, §0.2) keep
  `options` as a list-of-one on both wires and keep `flavour_count`
  (deviation ii). Tests: the re-derived nodes in `tests/test_trip_api.py` +
  `tests/test_trip_preview_contract.py` (audit their option-list pins under
  §0.1 at execution — the files are on the read-precondition list).
  RED→GREEN→UNDO→RESTORE per node.
  *Sabotage:* touching the compose legacy branch "while in there"; renaming
  `flavour_count`; a second fingerprint spelling.

- [x] `[BUILD]` **S4.5 — selection.py sheds the flavour machinery.** **File:**
  `src/tour/selection.py`. DELETE `select_k_routes`, `_jaccard`,
  `DIVERSITY_PENALTY`, `JACCARD_OVERLAP_MAX`, and the `score_penalty`/
  `penalty` threading (26 sites; the knob exists solely for flavour re-runs —
  grep-verified this session; re-verify at execution, §0.6). Tombstone rows in
  `tests/test_tour_one_engine.py` (the `test_*_is_gone` genre, non-vacuity
  first). `poi_score` loses its `penalty` parameter — the party/diversity
  factor comment updates. RED (tombstone) → GREEN; survivor: the Phase-3
  suites (promises 16, clock 24, cert 21) still green — they never touched
  flavours.
  *Sabotage:* leaving `score_penalty` "for future use" (dead threading is the
  fork's front door); deleting `choose_discrete_route`'s identity guard along
  with it (that survives — audit B kept it).

- [x] `[BUILD]` **S4.6 — the dials on the wire.** **Files:**
  `src/api/models/trips.py` (+ `src/tour/contract.py` ONLY if W4.2's locked
  semantics demand a new axis — the S3.2 mould, additive, request_sha256 move
  declared). `TripPreviewRequest` gains the dial state per the locked
  semantics (existing-axis mappings preferred, deviation iv) AND the Phase-1–3
  fields the workbench form will send (start_datetime, end_hardness, party,
  walking_pace, weather, pinned names — the preview request today carries
  none of the party axes; verify against the model file at read time).
  Hermetic request-model tests citing the panel's ruling by name.
  RED→GREEN→UNDO→RESTORE.
  *Sabotage:* dial fields that bypass TourInput (a second knob path into the
  planner); inventing a new axis where an existing one serves (deviation iv).

- [x] `[BUILD]` **S4.7 — the workbench turns dials.** **File:**
  `frontend/review.html`, regions per `evidence/phase4-maps/workbench-map.md`
  (re-read the regions before editing — the map is a map, not a read). (a)
  DELETE the option flow: `renderTourOptions` 3832–3933, `authorTourOption`'s
  option indexing (the author call itself survives against the one day),
  `.tour-option-card` CSS 199–203, the `tourOptions` global and its two
  index-addressed listeners (1165–1168), the six stale "three" strings the
  map names (incl. the user-visible 3957). (b) The plan response renders as
  THE DAY via the existing one-day renderer path (`tourOptionMapStops` +
  the card list — places-only per owner ruling 1), with ONE "write the tour"
  action replacing the pick. (c) THE DIALS: four controls (labels = W4.2's
  locked names) + the form gains the engine's real inputs (deviation iii);
  every dial turn updates `lastTourPlanBody` (THE map-named hazard, deviation
  viii) and re-runs `generateTourPreview()` — the 409 loop's own precedent
  (3950–3960) is the mechanism, now user-initiated. (d) If W4.2 ruled for the
  promise surface: render the promises line + shape/queue columns from the
  extended wire (S4.6). Tests: `tests/test_workbench_preview_wiring.py`'s
  static-source assertions re-derived against the new source (its
  two-calls-split and degradations-before-pick invariants SURVIVE; its
  option-specific spellings die — §0.1 audit at execution).
  *Sabotage:* a second render target beside `#tourStops`; a dial that edits
  the DOM without touching `lastTourPlanBody` (the silent-divergence hazard);
  leaving `renderTourStops`'s `data.options[0]` fallback (3747–3751) reading
  a shape that no longer exists.

- [x] `[BUILD]` **S4.8 — the Playwright suites prove the one-day surface.**
  **Files:** `tests/test_workbench_ui.py`,
  `tests/test_workbench_matches_the_app.py`. Rewrite the 16
  KEEP-AND-REWRITE invariants from audit E's rows, each citing its named
  source — keeping the two guard-pinned NAMES
  (`test_tour_preview_generates_and_plays`,
  `test_tour_preview_renders_basic_lane_honestly` — audit E §5.1), keeping
  the unstubbed test UNSTUBBED and outside any routing helper (the
  suite-honesty guard follows the call graph, §5.2), and re-deriving the
  one-planner/one-author `PLAN_BLOCK` trio (:2637/:2704/:2778) against
  `plan_premium_tour`. New stubs: a ONE-option `_plan_payload`. Plus D5's own
  new test: four dial turns each fire a fresh `/trips/preview` with the
  changed field and re-render (the §0.5 harness-first rule made real in the
  suite). Green = `make test-workbench` on the phase's own lane.
  *Sabotage:* stubbing the unstubbed test; renaming the two pinned names;
  asserting the old vocabulary ("audio fill…") back into the rewrites.

- [x] `[BUILD]` **S4.9 — the phone takes the one day.** **Files:**
  `mobile/lib/pages/trip_itinerary_page.dart`,
  `mobile/lib/services/trip_service.dart`, `mobile/lib/models/trip.dart`,
  per `evidence/phase4-maps/mobile-map.md`. DELETE the sheet
  (`_pickFlavour` 160–245, `_FlavourTile` 545–589) and the `RouteOption`/
  `RouteOptionStop` models + `GeneratedTrip.options`; `_confirmAndPrepareAudio`
  calls `composeTrip(tripId, "{tripId}-opt1")` DIRECTLY (composeTrip and
  `ComposeVerificationException` SURVIVE — a single-day refusal surfaces on
  the error card; there is no second flavour to offer and the message says
  so honestly). KEEP `flavour_count` parsing (deviation ii). Rewrite the
  mapped mobile test groups (trip_test 188–386, itinerary 502–931, service
  457–672) from the one-day design. Green = `make flutter-test`.
  *Sabotage:* deleting composeTrip with the sheet (the phone must still
  author); a client-side default pick that hides a compose refusal.

- [x] `[GATE]` **W4.10 — the kill criterion, measured.** Each of the four
  dials turned on the three W4.1 cells against the ≤ 15 s bar, plus the
  W3.2 cells re-run (the carried speed finding stays visible). Over →
  deviation-free application of the ONE trade (repair trial budget on
  replans), re-measure, numbers in the ledger either way.

- [x] `[GATE]` **W4.11 — DEMO D5, "turn the dial".** One dated start in the
  real workbench, four dial turns, each replanning live — real browser,
  screenshots per turn + the before/after tables, saved verbatim under
  `evidence/`. Presented to the owner in the close report (the established
  delivery: the owner's read of it IS the watch, per the W2.11 precedent).

- [x] `[GATE]` **W4.12 — the closing panel.** All eleven personas on the REAL
  dial-turn tables (each dial, both directions where locked) — verdict on
  whether the locked semantics landed as ruled, the day-shape default
  re-judged on the built thing, dissents by name.

- [x] `[GATE]` **W4.13 — close.** The phase's own tests + `make lint` +
  `make dedup-review` + `make test-workbench` + `make flutter-test` + the
  demo (§0.7's close bar). Judge (§2). Commit explicit paths (any
  request_sha256 move from S4.6 declared; Phase 8 re-seals). Amend-and-carry
  this plan; re-plan Phase 5 at step level; delete nothing under `specs/`
  that Phase 5's re-plan still reads.

### PHASE 5 — The living session; **delete the frozen trip (8.2)**. Demo **D6 "the walk that noticed"**.

- **Delivers:** server replan endpoint; the contingency set (§4.6 — precomputed
  answers for late/early bands, skips, promise-at-risk, wrap-up-from-here); alternate
  authoring + prefetch; learned walking pace and listening rate (§4.1); the two-tier
  response rule (fabric silent, promises ask exactly one question, §4.2); pause as
  information (§4.3); the announcement etiquette (§4.4 — queued to natural moments,
  everything spoken also on screen, gift-framing, one sentence).
- **THE structural rule:** the phone SELECTS from the contingency set, it never
  DECIDES (§4.6). **Two source-scanning seams:** the REPLAN BRAIN (no scoring, no
  candidate pool, no policy in `mobile/` — a Dart-tree sweep in the
  `test_the_unreferenced_mobile_audio_surfaces_are_gone` mould) and the SESSION CLOCK
  (the phone's arithmetic re-timing is checked against the server on reconnect; a
  divergence beyond tolerance is a REPORTED DEFECT, per §4.6 — the test asserts the
  comparison exists and reports, not corrects).
- **Deletion in the same phase:** `mark_trip_composed` and the 409 one-compose lock
  (`crud/trips.py`), replaced by the versioned living session — tombstone row +
  `test_refused_flavour_is_422_and_leaves_trip_untouched`'s audit-ruled successor
  (the refusal CONTRACT survives; the frozen-trip mechanics die).
- **Demo D6:** a replayed persona trace (Fiona & Dev's minute-107 resume, or
  Rosemary's 16:35 bench question) where lingering 20 minutes makes the guide ask
  the question, on a device.
- **Kill criterion (design §9):** replan latency over budget on a real device →
  alternates precompute at plan time and the live path narrows to re-timing.
- **Read preconditions:** the whole mobile session surface (`audio_service.dart`,
  `trip_service.dart`, `trip_itinerary_page.dart`), `src/api/crud/trips.py`
  re-read, `artifact.py`.

> **AMENDED 2026-08-18, same day (owner ruling on the test cull — see
> phase4-ledger.md "TEST CULL").** The source-scan MOULDS this section names —
> `tests/test_tour_one_engine.py`, `test_the_unreferenced_mobile_audio_surfaces_are_gone`,
> the `K_OPTION_PRIMITIVES` / `THE_ONE_PLANNER` genre — were RETIRED with the
> deleted-stack tombstones and no longer exist. The two seams (S5.9 REPLAN
> BRAIN, S5.10 SESSION CLOCK) keep their invariants unchanged; write each as a
> BEHAVIOURAL test wherever a behavioural check can exist (the session clock:
> drive a reconnect with a divergent local clock and assert a REPORT row lands
> and the local clock is not overwritten), and as a source scan ONLY where the
> invariant is about source itself (an ABSENCE of scoring/ranking code in
> `mobile/` cannot be proven behaviourally) — and say so in the test's docstring.
> The band-refusal test the section cites lives in
> `tests/test_trip_preview_contract.py` now.
>
> **RE-PLANNED AT STEP LEVEL 2026-08-18, after Phase 4 closed, against the Phase-4 close tree** — `258933fd` (Phase 3's close) **+ the uncommitted Phase-4 work on main** (226 changed paths at read time; `src/tour/selection.py` 5,676 / blob `c82b5a36`, `src/api/routes/trips.py` 1,736 / `d8f1c34d`, `frontend/review.html`, `tests/test_tour_dials.py` + `tests/test_tour_options.py` untracked) **+ the S4.9 phone branch `worktree-agent-a13c7825b523f6552` at `87e0bdfb`**, which W4.13 merges. The plan's own §4 rule. **The Phase-4 close commit is `973982fb`** (on top of the S4.9 phone commit `87e0bdfb`; both on main, unpushed at close): the first act of the executing session is to verify HEAD is that commit and that the blob hashes below still match, and to treat any drift as a plan defect (§0.2). The §0.1 audit this phase reads is **`05-audit-C-trips-serving.md`** (291 lines): its §1 classifies 11 **DELETE-AT-PHASE-5** functions in `tests/test_trip_api.py` by name, with the surviving invariant written out per row. D5.0 reads its rows from there and never re-derives them.

**Read evidence for this re-plan (2026-08-18)** — path, lines, how read, finding.
`04-implementation-plan.md` 1,842 — §§0–1 head (1–300) and 1,400–1,842 read end to end: §0's binding rules, the whole Phase-4 section as the format mould, the Phase-5 stub, and §5's risk table (the "second replan brain grows in the app" row already points at this phase's two seams).
`01-design.md` 642 — §4 (205–293) whole, §8 (427–445), §9 (447–475), §10.1–10.4 (481–506); finding: §4.6's four bullets are already an implementable contract — server decides, phone selects, one arithmetic exception, and that exception is *checked*.
`phase4-ledger.md` 719 — whole file, both parts; the W4.12 verdict (7 better / 4 NO: Théo, Nadia, Marcus, Rosemary), the eleven in-session fixes, and PART 2's twelve CARRIED rows are this phase's inbox.
**The mobile session surface, read in full on `87e0bdfb`:** `audio_service.dart` 251 / `ecdfd638`, `trip_service.dart` 355 / `7505338d`, `trip_itinerary_page.dart` 811 / `3877e21a`, `models/trip.dart` 201 / `79822d95`. **PLAN DEFECT against the stub's own read-precondition list, logged here (§0.2):** the phone's session loop is **`mobile/lib/services/tour_playback_service.dart` (232 / `696d5268`)**, which the stub does not name. Read in full: it holds the 10 m geofence (`:138`, `:151` — design §8.4, Phase 7's deletion, untouched here), the audio-completion auto-advance (`:161–187`), and `haversineDistance` (`:207`) — **the phone's only existing arithmetic**. It carries **no clock at all**: no elapsed, no ETA, no re-timing, no notion of running late. §4.1's learned pace and listening rate are therefore NEW code in this file, not an edit to something. Also read: `location_service.dart` 153 / `d232d3ab` (5 m distance filter, `lowAccuracy` at >25 m — the accuracy signal a re-timer must not trust blindly) and `providers.dart` 28 / `57d4d7d5` (`LocationProvider`/`AudioProvider` — the two interfaces every phone-side test mocks; the extension point for anything new the session needs).
`src/api/crud/trips.py` 384 / `4d878a19` — whole. **The frozen trip is six sites, not a subsystem:** `mark_trip_composed` (`:252–258`, a two-line Cypher `SET`), the 409 (`routes/trips.py:781–785`), its call (`:1034`), `get_trip_compose_inputs`'s `composed` field (`:271`, `:280`), and phone-side `TripAlreadyComposedException` (`trip_service.dart:203–204`, `:350–355`) with its handler (`trip_itinerary_page.dart:164–165`). **`replace_trip_stops` (`:218–249`) IS already the living-session write** — one transaction, fresh item ids, audio nulled, full rollback on a mid-loop failure. The versioned session extends it; it does not replace it.
`src/api/routes/trips.py` 1,736 / `d8f1c34d` — outline whole, `compose_trip` 740–1064 read end to end; the rebuild-from-persisted-pick path, the six fail-open `chosen.get(...)` restores, the Block-2 seam call, and the two 422 refusal arms. Remaining regions (generate 503–739, preview 1,067–1,421, author 1,422–1,703) NOT read end to end — a hard read-precondition on S5.7/S5.8.
`src/tour/selection.py` 5,676 / `c82b5a36` — targeted reads. **Three findings that set three steps:** (a) the 50 % underfill line exists in exactly ONE place, `:4838–4873`, inside the timebox repair's under-fill fallback, on `best_under.elapsed_seconds - best_under.queue_seconds`; the FINAL band check at `:3149–3186` has a hard ceiling and a floor that only *discloses* (`elapsed_shortfall_seconds`). Every pass that runs between them — the concentrate pass `:2870–2917`, co-located demotion `:2922`, twin collapse `:2932`, Held-Karp `:2956`, loop orientation `:2965` — is downstream of the 0.5 line and upstream of a check that does not carry it. That is W4.11's composition hole, and it has one fix site. (b) **The concentrate pass drops and never redistributes** — `:2916` is `selected = trial_set` and nothing re-prices the survivors; carried finding 2's open question ("do the ceilings bind, or is redistribution absent?") is answered by reading: **absent**. (c) `:1755–1780`'s "already true" short-circuit names this phase's work in its own comment: *"The replan-capable repair (drop AND re-fill under a cap) is Phase 5's work."*
`src/tour/routing.py` 833 / `88d00a48` and `routing_client.py` 336 / `709ad986` — `leg_walk_seconds` `:498–517`, `total_walk_seconds` `:520–536`, `_transit` `:663–724`, `leg_seconds`→`route`→`route_with_receipt` `:135–204`. **The finding that makes carried 1 buildable:** every hermetic routing double in the tree returns routed seconds *equal to* the pace-corrected haversine — `_DeterministicRoutingClient` (`tests/test_tour_b_materialization.py:125–145`) and `_FakeRoutingClient` (`tests/test_trip_preview_contract.py:115–172`, whose `route_with_receipt` returns shape `"test-polyline"` so `source == "valhalla"` and `leg_walk_seconds` prefers it). `routing.py`'s own docstrings say the estimate and the exact "agree only by coincidence". **So the estimate-vs-exact gap is structurally invisible to every test in the repo.** That is why carried finding 1 shipped, and S5.4 cannot be written without a new divergent double.
`src/tour/contract.py` 1,256 / `0e47d227` — `Promise` `:755–770`, `Route` `:772–880`. `Route.promises` already says the phase's own sentence: *"carried so downstream phases can protect them through every replan ('fabric may change silently; promises may not', §4.3)"*. The protected class exists as DATA; Phase 5 makes it BINDING. `planned_queue_seconds`/`visit_goes_inside` (`:825–826`) are the currency S5.3's gate subtracts.
`src/tour/artifact.py` 1,002 / `1e28039b` — outline whole; `:1–120` and `:630–860` read. `FinalTourBlueprint`'s validator (`:662–801`) requires `script.inputs == tour_input`, narration chunks equal to the exact partition, and a composition trace covering every routed stop exactly once — the object is frozen and self-consistent. **A replan cannot patch a blueprint; it mints a new one.** That is the structural argument for §8.2's *versions* rather than mutation. Lines 120–630 and 860–1,002 NOT read end to end — a hard read-precondition on any step that touches it.
`src/api/models/trips.py` 568 / `4717f439` — request outline + `:400–568`. `TripPreviewResponse` already carries `promises`/`day_notes`/`slack_minutes`/`longest_walk_minutes` (S4.6 + W4.12 fixes 2, 6, 7); the contingency set extends this shape, it does not invent one.
`tests/test_tour_one_engine.py` 1,896 / `81d52b73` — outline whole; `:1,380–1,896` read end to end. Both moulds confirmed: `test_the_unreferenced_mobile_audio_surfaces_are_gone` (`:1,857`) with `_mentions` over `mobile/lib` + `mobile/test`, non-vacuity FIRST, git-index check, and `SURVIVING_MOBILE_NEIGHBOURS` anti-over-deletion; and the Python genre `K_OPTION_PRIMITIVES` (`:396`) / `THE_ONE_PLANNER` (`:401`, now `plan_premium_tour`) / `FLAVOUR_MACHINERY_NAMES` (`:1,609`) with `_every_referenced_name` + `_call_sites`.
`tests/test_trip_api.py` 1,558 / `b9337491` — name outline whole; `:1,420–1,559` read (`test_second_compose_is_conflict`, `test_refused_flavour_is_422_and_leaves_trip_untouched`, the two opt-N rows). Audit C's ruling on the named successor is exact and is adopted verbatim: **SURVIVES** — a verification failure is a 422 carrying `reason` + `attempts` + `untraceable` and nothing degraded is persisted (quality standard §6b, design §7.2); **DIES** — `rid is None`, "another flavour can be tried", the `-opt1` selector, the single-compose model.
`docs/personas/09-couple-who-would-rather-talk.md` 82 and `05-step-free-visitor.md` 61 — whole. **Both demo anchors verified against the text.** Fiona & Dev: 15:00 start, Dev pauses mid-sentence at step 4 (`:26–28` — *"The pause is not an interruption of the product. It is the product being used correctly"*), and the audio comes back on at **16:47 = minute 107** at the Galerie Vivienne (`:39–41` — *"They restart the tour when the conversation pauses, not when the plan expects them to"*). Rosemary: **16:32–16:45, "Sits. Thirteen minutes"** (`:40`), with a 17:00 finish back at Orsay and a hard 12-minute per-leg limit (`:23`, `:48–50`) — the exact shape of §4.2's one question.

**THE STRUCTURAL RULE, MADE CONCRETE — the phone SELECTS, it never DECIDES (§4.6).**
*The contingency set on the wire.* `GET /trips/{id}/session` and every replan reply return `SessionPlan`: `plan_version` (int, monotonic — every server decision mints one), `stops[]` (today's `GeneratedStop` shape), `promises[]` (each with `promise_id`, `kind`, coarse window, `protected: bool`), `retime_tolerance_seconds`, and `contingencies[]`. Each contingency is `{contingency_id, trigger, plan_version, stops[], promises[], question | null, screen_text, alternate_stop_ids[]}`. **`trigger` is a MATCHER, not a policy:** `{"kind":"running_late","band_minutes":[10,20]}` / `running_early` / `{"kind":"stop_skipped","stop_id":…}` / `{"kind":"promise_at_risk","promise_id":…}` / `{"kind":"wrap_up_from","stop_id":…}`. `question` is non-null **only** when the contingency touches a promise (§4.2's two tiers: fabric silent, promises ask exactly one question); it carries its own safe default and, under `wall`, the wall wins. `screen_text` is mandatory and non-empty whenever `question` is (§4.4.2 — everything spoken also appears on screen).
*Who computes it.* One server-side builder, `build_contingency_set`, in `src/tour/` — called only by the API, only after `plan_premium_tour` has produced a day. No other producer exists and the seam test proves it.
*What the phone MAY do — the exhaustive list the seam test enforces:* (1) arithmetic re-timing (observed pace × remaining routed distance; observed dwell; observed listening rate) over numbers the server gave it; (2) MATCH its measured divergence against the triggers and select the entry — an equality/band lookup, taking the **first in server order** when two match, never a tie-break of its own; (3) ask the ONE question the selected entry carries and apply the answer or the stated default; (4) REPORT a clock divergence beyond `retime_tolerance_seconds`, never correct it; (5) when nothing matches: carry on and re-time (§4.6's arithmetic fallback), and say so on screen. **Anything else is a defect**: no scoring, no candidate pool, no ranking, no "best" of anything, no plan constructed locally.

**Kill criterion and its baseline (set here; the design row §9 states the criterion but no budget).**
Two bars, because §4.6 has two paths. **(a) THE SELECT — ≤ 1 s**, from a position update that crosses a trigger to either the question on screen or the silent re-time applied, measured on the **iOS Simulator**. **(b) THE LIVE REPLAN — ≤ 8 s**, from the phone firing the replan to the new day rendered, measured phone-to-local-API on the simulator. Baseline, measured by W4.10 on the real wire this same tree: a full dated 180-minute plan answers in **4.9–8.7 s**; a replan re-plans only the REMAINING day, so 8 s is a bar the engine sits *on*, not comfortably under — which is the point. **Over the bar → the design's own remedy, no other:** widen the precomputed contingency set to cover that divergence and narrow the live path to re-timing. Quality and the W4.2 locked semantics are never traded.
*Why the simulator and not a physical device.* `make flutter-device` (Makefile `:521–523`) builds with `--dart-define=API_BASE_URL=https://ondoway.com/api/v1` — a phone on a desk cannot reach the local replan endpoint without a new build config this phase does not own. `make flutter-ios` (`:499–518`) boots a simulator, starts the API on :8000 and waits for `/healthz`, which is the whole harness already. **Stated caveat, in the ledger:** the simulator measures compute and loopback, not cellular; the network leg is measured separately as one number (a `curl` of the same replan over the real wire) and both numbers go in the ledger, never one presented as the other.

**The four carried Phase-4 findings, and who owns each.**
1. **The ONE final underfill gate** (W4.11 carried). **Phase 5 owns it, first.** A replan is another pass, so leaving passes to compose un-gated multiplies the hole this phase is about to make bigger. → **S5.3.**
2. **The leg cap certified on EXACT legs** (CARRIED 1; measured: Carnavalet→Place des Vosges `walk_seconds` 473 under a 540 s cap, `leg_seconds` 576 over). **Phase 5 owns it** — the W3.2 mould, tighten-and-retry once. Blocked on a hermetic routing double whose exact ≠ its estimate, which does not exist anywhere in the tree (see read evidence). → **S5.4.**
3. **"More breaks" funds rests by deleting anchors and adding walking** (CARRIED 3; PdV walking 23→39 min, Carnavalet 47-inside → Rue des Rosiers 25-outside, no rest promise). **Phase 5 owns it** — the ledger already rules it *"a replan-RELATIVE constraint (hold the base day's longest leg and anchors while adding cadence) — Phase 5's replan machinery"*, and it is the first customer of `ReplanContext`. → **S5.6.**
4. **"Fewer stops, longer at each" frees minutes but lengthens nothing** (CARRIED 2). **Phase 5 owns it, and the open measurement is already answered by reading**: redistribution is absent (`selection.py:2916`). It belongs here because dropping-and-redistributing is the SAME primitive §4.5.3 demands of every live drop (a drop merges two legs and must re-check the cap) — one construction site serves the dial and the replan. → **S5.5.**
5. **"Skip the queues" deletes the building rather than offering its outside** (CARRIED 4; Notre-Dame vanishes for a 40-min queue when Théo, Camille and Aiko wanted the parvis). **PHASE 5 DOES NOT OWN THIS AND WILL NOT BUILD IT WITHOUT AN OWNER RULING.** The ledger is explicit: *"Owner ruling needed: the W4.2 ruling said queue-minutes penalise stop CHOICE, which is what it does."* The mechanism exists (`ClockExclusion.kept_outside`, W4.12 fix 4) but is wired to the clock, not to queues, so this is a re-opening of a panel-locked semantic — §0.8.10 territory. W5.2 puts it to the panel as an ADVISORY question and W5.15 carries it to the owner with the panel's reading attached. If the owner rules in-phase, it lands as an amendment to S5.5's step text with its own RED→GREEN; otherwise it carries to Phase 6's lens work with CARRIED 6 ("no positive *more of this today*"), which is its natural neighbour.

**Deviation register for this re-plan** (each owner-visible and cheap to overrule).
(i) **The living session is VERSIONED, not mutable.** `artifact.py`'s blueprint is frozen and validator-bound, so a replan mints `plan_version + 1` and a new stop set through the existing `replace_trip_stops`; nothing edits a written day in place. (ii) **`flavour_count` still rides the wire** — `GeneratedTrip.fromJson` hard-requires it (`trip.dart:173`); Phase 4's deviation ii is restated, not re-decided. (iii) **Alternate authoring rides THE one Block-2 seam** (`plan_premium_authoring → execute_premium_plan → finalize_premium_tour`), guarded by the existing `test_breaking_the_one_author_seam_breaks_both_surfaces` (audit D `:118`, ruled REWRITE-AT-BOTH). **Its cost, stated and spent, not asked about (§0.8.9):** one provider call per stop that *differs from the base day*, counted before it is billed at W5.1 and again at S5.7's plan step, which is provider-free. (iv) **Alternates reuse the base day's authored per-stop text where the stop is unchanged**; a *shorter* alternate needs §5.5's two lengths, which Phase 6 owns — declared as a dependency, not smuggled in. (v) **Legacy trips keep composing.** Trips persisted before this phase carry `composed_route_id`; the reader keeps tolerating the property while ignoring it (the Phase-4 deviation-i precedent), so no saved trip breaks. Only the 409 and the writer die. (vi) **The 10 m trigger circle stays.** `tour_playback_service.dart:138`/`:151` is design §8.4, Phase 7's deletion; this phase edits the file and must not take it. (vii) **The workbench gets a read-only session view, not a session driver** — the workbench is not a walker; D6 is on a device. Whether the workbench renders the contingency set at all is W5.2's ruling, defaulting to no. (viii) **A live session re-orders stops, so three certification invariants become per-version rather than global** — audit F names them (`test_reflection_window_is_strictly_before_its_stop` `:95`, INV7's non-decreasing `stop_idx` `:146`, and the C7 walking-audio ruling `:282`, which §4.4.1 collides with and which needs a SEPARATE announcement rule rather than an edit). Each is re-derived in the step that breaks it, never edited to pass.

### Steps (Phase 5)

- [x] `[DEMOLISH]` **D5.0 — audit C's eleven Phase-5 rows, the frozen-trip fixtures, and the Dart 409 tests.** **Files:** `tests/test_trip_api.py`, `mobile/test/services/trip_service_test.dart`, `mobile/test/pages/trip_itinerary_page_test.dart`, `tests/test_trip_crud.py`. Read `05-audit-C-trips-serving.md` §1 FIRST — the rows are measured, with the surviving invariant written per row; do not re-derive. (a) DELETE the eleven DELETE-AT-PHASE-5 functions it names (`test_compose_hands_back_the_flavour_that_was_saved`, `test_compose_plans_and_authors_through_the_shared_premium_seam` — its 0.90/1.10 assertions are §8.3's deleted fill band and **no replacement may carry that number**, `test_compose_authors_per_stop_and_keeps_the_wire_contract`, `TestComposeTripEndpoint::test_compose_persists_marker_narration_with_fresh_stop_ids`, `::test_compose_persists_extra_narration_traceable_to_extra_beats`, `::test_second_compose_is_conflict` — audit C's "purest single row in the set", `::test_refused_flavour_is_422_and_leaves_trip_untouched`, `::test_persists_multi_beat_graph`, `::test_persists_extra_beat_ids_for_keep_exploring`, `test_unknown_trip_returns_none`, and the compose half of `test_generate_and_compose_report_what_degraded` whose generate half SURVIVES as is). (b) DELETE the Dart 409 tests (`trip_service_test.dart:653–…` and the itinerary page's already-composed path). (c) **BEFORE deleting anything, grep `tests/` for every `_helper` name in the deleted region** (§0.7's four measured couplings; `_HallucinatingExecutor`, `_PerStopCountingExecutor`, `_CountingChecker`, `_ColdStartingRoutingClient` and the `fresh_trip`/`cutover_trip` fixtures all live at `test_trip_api.py:636–835` and are used by rows that SURVIVE — move them before the delete, or the surviving tests vanish rather than fail). **Declared breakage:** none expected beyond the deleted rows; the surviving refusal and degradation invariants are rewritten at S5.8. Survivor proof: audit C's LOAD-BEARING rows still collect; `make lint` clean; `make flutter-analyze` clean.

- [x] `[GATE]` **W5.1 — measurement first (§10.9): the before-picture, on real traces and real numbers.** No code. (a) **The two persona traces, replayed against today's product**: Fiona & Dev's Sunday 15:00 Place Dauphine three hours with the pause at 15:44 and the resume at **minute 107**, and Rosemary's Wednesday 14:00 Orsay round trip with the **16:32–16:45 bench**. Record, per trace, exactly what the product does today at each divergence — which is nothing, because there is no session: the frozen trip cannot be re-planned once composed. That "nothing" IS the before-picture and it is what the demo is measured against. (b) **The four carried findings as numbers**: the composed-dial underfill (leg9 + rest40 + fewer → the 2-stop 68-of-180 day, re-fetched); the estimate-vs-exact leg spread across a whole PdV day (`walk_seconds` vs `leg_walk_seconds` per transit, so the gap's size is known, not just its existence); the fewer-stops before/after per-stop minutes (proving redistribution absent on the wire, not only in the source); the more-breaks anchor deletion and walking delta. (c) **The latency baseline against both bars**, and (d) **the alternate-authoring cost counted**: for each demo cell, how many stops a contingency set's alternates would differ by — the number that gets spent at S5.7, stated in one clause. Verbatim outputs under `evidence/phase5-session/`.

- [x] `[GATE]` **W5.2 — THE EARLY PANEL (§1.10; taken before any session code exists).** All eleven personas, one message, on W5.1's real traces and tables. They rule on: (1) **the contingency set's COVERAGE** — which divergences get precomputed answers and at what band widths, and which are allowed to wait for connectivity (binding inputs going in: §4.3's pause suspends the clock and is never lateness — F&D pause five times; Marcus's `wall` wins an unanswered question; Rosemary's bench IS the §4.2 question; Sofia's after-dark rest must be lit-and-peopled or absent); (2) **the ONE question's wording and its safe default** — Paulo's W4.2 wording rulings BIND ("gated", "anchor", "40m", "err-short" all fail plain language), and Nadia's "over a screaming five-year-old, mute beats graceful" binds the escape hatch; (3) **what "a natural moment" is** (§4.4.1) — the panel picks the observable proxy the phone uses, given that a sentence missed on the move is gone forever for Paulo; (4) **whether repeated pauses bias the session to screen-only** (§4.3's own row) and what the screen then says; (5) **ADVISORY ONLY: the queue-avoidance question** (carried 4) — the panel's reading is recorded and carried to the owner at W5.15; nothing is built on it in-phase without a ruling. Dissents by name in the ledger. **The locked rulings BIND S5.6–S5.11; re-opening them afterwards is §0.8.10.**

- [x] `[BUILD]` **S5.3 — ONE underfill line, at ONE final gate.** **File:** `src/tour/selection.py`. The 0.5 check moves OUT of the repair's under-fill fallback (`:4838–4873`) and INTO the final band check (`:3160–3186`), where `final_elapsed` is already computed after every pass — concentrate, demotion, twin collapse, ordering, orientation. Same currency (elapsed minus `planned_queue_seconds`, the panel-ruled experience number), same `open`-hardness exemption by construction (a zeroed floor cannot bind), same named-binding-constraint refusal prose (W4.12 fix 10's three worlds). **Extends:** the existing final band check — it is already the one place every pass has finished, and the ceiling half already lives there; adding a second late gate would be the fork. RED first: a hermetic composed-dial case (leg cap + rest cadence + `stop_density="fewer"`) that ships a sub-half day today and must refuse after. Tombstone clause: exactly ONE occurrence of `UNDERFILL_REFUSAL_FRACTION` under `src/`. **Declared breakage:** the S4.5 starvation node and the preview-contract AC-24 pin both re-run through the new site — they must stay GREEN, and a red in either is a stop. RED→GREEN→UNDO→RESTORE. *Sabotage:* leaving the old check "as a fast path" (two lines, two answers — the §10.8 fork); raising the fraction to make a dial's day survive instead of fixing the dial; measuring the gate on elapsed-with-queue and quietly changing what "half a day" means.

- [x] `[BUILD]` **S5.4 — the leg cap certified on the EXACT legs (CARRIED 1), and the double that can see it.** **Files:** `src/tour/selection.py`, `tests/conftest.py` or a new `tests/routing_doubles.py` for the double (Extends: `_DeterministicRoutingClient` and `_FakeRoutingClient` — considered and rejected as the home, because both are *defined* to make exact equal estimate and changing them in place would silently re-point every suite that imports them). Build a **divergent routing double**: routed `leg_seconds = factor × pace_corrected_walk_seconds(haversine)` on named coordinate pairs, with a real polyline so `source == "valhalla"` and `leg_walk_seconds` prefers the exact number — the only way any test in this repo can tell the two apart. Then, in the W3.2 mould: after `summarise_route` has produced the final routed transits, certify `max(leg_walk_seconds(t))` against `max_leg_minutes`; on a breach **tighten and retry ONCE** at the exceeded value and, if the retry still breaches, refuse with the cap named (never ship a day whose head line contradicts the dial the person turned — W4.12 fix 11's honest note becomes unnecessary rather than load-bearing). RED first: the divergent double + a 9-minute cap on a day whose estimate fits and whose route does not. RED→GREEN→UNDO→RESTORE. *Sabotage:* certifying on `walk_seconds` because it is always present (that IS the bug); an unbounded retry loop instead of tighten-once; editing the existing doubles so "exact" quietly means "estimate" everywhere.

- [x] `[BUILD]` **S5.5 — ONE drop primitive: merge the legs, re-check the cap, redistribute the minutes (CARRIED 2 + §4.5.3).** **File:** `src/tour/selection.py`. One function — drop a stop → **merge its two legs** (Rosemary's 12 + 9 fusing into 21 is §4.5.3's named trap) → re-check the per-leg cap on the merged leg → hand the freed minutes to the surviving **protected and anchor** stops within their shape ceilings, never below a category's entry floor (W4.2 locked semantics 4's drop-not-shave, the 5-minute-museum disease, 11/11 convergent). The concentrate pass (`:2870–2917`) is rewritten to CALL it — its inline drop loop is deleted, with a tombstone clause asserting the loop's absence and asserting the primitive's presence. **Extends:** the concentrate pass itself; a replan's drop and a dial's drop are the same operation priced in the same currency (§4.5.1 — visitor-time, never narration-minutes), so a second spelling is the fork. RED first: a fewer-stops case where a dropped stop's minutes must appear on a surviving anchor, plus a drop whose merged leg breaks the cap and must be refused. RED→GREEN→UNDO→RESTORE. *Sabotage:* redistributing to the *weakest* survivor because it has the most headroom; letting redistribution push a stop past its shape ceiling; dropping a protected item (§4.5.2 — rests, meals, toilets and the finish trigger the question, never a cut).

- [x] `[BUILD]` **S5.6 — the ONE planner replans: `ReplanContext`, and "more breaks" as its first customer (CARRIED 3).** **Files:** `src/tour/contract.py` (additive, S3.2 mould, `request_sha256` move declared), `src/tour/premium_tour.py`, `src/tour/selection.py`. `ReplanContext` carries what makes a replan *relative*: the base day's promises (protected, §4.5.2), the base day's longest leg (a ceiling a replan may not exceed — §4.5.3), the elapsed clock from HERE, the observed pace and listening rate, and the terminus's promise protection (§4.5.4 — Camille's declared destination silently shrinking 22→8 minutes is the named failure). `plan_premium_tour` takes it; **there is no second planner** (the §10.8.1 argument Phase 4 already used to collapse `plan_premium_options`). Carried finding 3 lands here as the first customer: a rest-cadence increase must hold the base day's anchors and longest leg while adding cadence, and where it cannot, it asks rather than deletes. Replacements are drawn category-diverse (§4.5.5). RED first: the PdV more-breaks case from W5.1 — anchors held, walking not lengthened, a rest promise actually present. **Declared breakage:** audit F's three per-version invariants (deviation viii) go red here; each is re-derived in this step as a written decision, never edited to pass. RED→GREEN→UNDO→RESTORE. *Sabotage:* a `replan_route()` beside `select_route` (the fork this phase exists to prevent); letting the terminus absorb the drift; treating a promise as fabric because dropping it is arithmetically cheapest.

- [x] `[BUILD]` **S5.7 — the contingency set, computed once, on the server.** **Files:** a new `src/tour/contingency.py` + `src/tour/contract.py`. `build_contingency_set(route, input, replan_ctx)` produces the entries the W5.2 panel ruled for — late/early bands, per-stop skip, per-promise at-risk, wrap-up-from-here — each by calling `plan_premium_tour` with the matching `ReplanContext`, each carrying its `question`/`screen_text` pair (non-null together or null together) and its `alternate_stop_ids`. **Extends:** `plan_premium_tour` — a contingency IS a replan taken early, so the set is N calls to the one planner, never a second decision procedure. The set's alternates are authored through THE one Block-2 seam (deviation iii), one provider call per differing stop, the count fixed at plan time and printed before it is billed. RED first: a hermetic corpus where a 15-minute lateness band's precomputed answer differs from the base day and its question names the promise at risk in the panel's words. *Sabotage:* a heuristic "close enough" that reuses one band's answer for another (the phone would then be selecting a plan nobody made for it); questions without screen text (§4.4.2); computing the set on the phone "to save a round trip".

- [x] `[BUILD]` **S5.8 — the session on the wire; the frozen trip DELETED (§8.2).** **Files:** `src/api/routes/trips.py`, `src/api/crud/trips.py`, `src/api/models/trips.py`. `GET /trips/{id}/session` returns the current `SessionPlan`; `POST /trips/{id}/session/replan` takes the phone's observed position, pace, listening rate and elapsed clock and returns a new `SessionPlan` at `plan_version + 1`. **DELETE `mark_trip_composed` (`crud/trips.py:252–258`), the 409 (`routes/trips.py:781–785`) and its call (`:1034`)**; `get_trip_compose_inputs` keeps reading the property for legacy trips and ignores it (deviation v). A second write is no longer a conflict — it is version N+1 through the existing `replace_trip_stops`. **The refusal CONTRACT survives verbatim** and gets its audit-ruled successor here: a verification failure is a 422 carrying `reason="compose_verification_failed"` + `attempts` + `untraceable`, and **nothing degraded is persisted** — the trip is left exactly as it was (quality standard §6b, design §7.2; audit C's row for `test_refused_flavour_is_422_and_leaves_trip_untouched` is the spec). The degradation channel's compose half is re-pointed at the session endpoints (audit C, LOAD-BEARING). RED→GREEN→UNDO→RESTORE per node. *Sabotage:* keeping the 409 "for safety" behind a flag; a session endpoint that re-runs selection from scratch and hands back a different day than the one the person is standing in; letting a refusal write a partial version.

- [x] `[BUILD]` **S5.9 — the phone SELECTS, and prefetches. Plus the REPLAN BRAIN seam.** **Files:** `mobile/lib/services/trip_service.dart`, `mobile/lib/services/tour_playback_service.dart`, `mobile/lib/models/trip.dart`, and `tests/test_tour_one_engine.py` for the seam. The phone fetches the `SessionPlan`, holds it, matches its measured divergence against the triggers, and applies the selected entry — the exhaustive five-item list above, and nothing else. `TripAlreadyComposedException` and its handler are deleted with the 409. Alternates prefetch through the EXISTING `audio_service.prefetchAudio` (Extends: `BeatAudioInfo` already keys by the id playback uses, so the offline set is the same cache). **THE SEAM — `test_the_replan_brain_is_only_on_the_server`**, written in the `test_the_unreferenced_mobile_audio_surfaces_are_gone` mould (`_mentions` over `mobile/lib` + `mobile/test`, **non-vacuity first**, git-index check, and a `SURVIVING_MOBILE_NEIGHBOURS`-style anti-over-deletion clause naming `haversineDistance`, `prefetchAudio` and the re-timing helper so an over-eager sweep fails): zero occurrences under `mobile/` of a banned scoring/ranking/candidate vocabulary, plus the positive clause that exactly ONE Dart method changes the current plan and its only decision input is a server `contingency_id`. RED first by mutation: add a local `_bestAlternate()` → the seam goes red. Green = `make flutter-test` + `make test-file FILE=tests/test_tour_one_engine.py::test_the_replan_brain_is_only_on_the_server`. *Sabotage:* a local tie-break "when two triggers match" (that is a decision); a client-side default that hides a server refusal; deleting the 10 m geofence while in the file (deviation vi — Phase 7 owns it).

- [x] `[BUILD]` **S5.10 — the phone's arithmetic: learned pace, learned listening rate, pause as information. Plus the SESSION CLOCK seam.** **Files:** `mobile/lib/services/tour_playback_service.dart`, `mobile/lib/services/audio_service.dart`, and `tests/test_tour_one_engine.py`. Walking pace learned within ~15 minutes and replacing the preset (§4.1 — Marcus's bag stops being a permanent deficit); listening rate learned from replays and playback speed, scaling the remaining day's estimates (§4.1 — Paulo tells the product three times in forty minutes and every candidate treated each overrun as fresh news); **pause suspends the clock and is treated as information, never lateness** (§4.3 — F&D's pause is the product being used correctly), with repeated pauses biasing the session to screen-only per W5.2's ruling. Position accuracy is respected: `location_service.lowAccuracy` (>25 m) fixes do not train the pace. **THE SEAM — `test_the_session_clock_is_checked_against_the_server`**, in the `K_OPTION_PRIMITIVES`/`THE_ONE_PLANNER` genre on the Python side and `_mentions` on the Dart side, following `leg_walk_seconds`'s "THE ONE EXPRESSION" precedent: exactly one re-timing expression each side, the reconnect path COMPARES them, and a divergence beyond `retime_tolerance_seconds` is **REPORTED** — a row on the existing `degradations` channel (`human` + machine registers, `src/tour/degradations.py`) — and never silently corrected. The test asserts the comparison exists and reports; it asserts the *absence* of an assignment from the server's clock back into the local one. RED first by mutation: make the reconnect overwrite the local clock → red. *Sabotage:* correcting the phone from the server because "the server is right" (that is the silent-divergence bug §4.6 exists to prevent); learning pace from a stationary conversation; two re-timing expressions that agree today by coincidence.

- [x] `[BUILD]` **S5.11 — announcement etiquette, all four hard rules (§4.4).** **Files:** `mobile/lib/services/tour_playback_service.dart` (the queue), `src/api/models/trips.py` (the screen-text contract), `src/tour/contingency.py` (the one sentence). Speech **queues to a natural moment** per W5.2's ruled proxy — never into a conversation, never onto a walking leg; everything spoken **also appears on screen** (the new speech this redesign adds is exactly the speech most likely to lack a transcript); framed as a gift, never as debt ("we've been enjoying this square, so I've traded the last stop" — three loss-framed sentences over a family's shared speaker is "a small scold with good manners"); **one sentence, maximum**, and mute beats graceful. The wire enforces what it can: `screen_text` non-empty whenever `question` is, and a sentence-count validator on the question. **Deviation viii's third row lands here:** audit F `:282`'s C7 ruling ("Audio overlaps the walking") holds for stories and NOT for announcements — that is a **separate rule**, written fresh with its own citation, never an edit to the C7 test. RED→GREEN→UNDO→RESTORE. *Sabotage:* announcing on a walking leg because the person is "between stops anyway"; a two-sentence question that explains itself; speaking a line the screen does not carry.

- [x] `[GATE]` **W5.12 — the kill criterion, measured on the iOS Simulator.** `make flutter-ios` (it boots the simulator, starts the local API on :8000 and waits for `/healthz`), the two persona traces driven as scripted position streams. **(a) SELECT ≤ 1 s** — divergence crossing a trigger to question-on-screen / silent re-time applied, ten samples per trace, worst case reported. **(b) LIVE REPLAN ≤ 8 s** — phone-fire to new-day-rendered, on the W5.1 demo cells; plus the same replan timed over the real wire as a separate number so the loopback caveat is visible rather than assumed. Over either bar → the design's own remedy and no other: widen the precomputed set, narrow the live path to re-timing; re-measure; numbers in the ledger either way. The W4.10 dial cells re-run so the carried Phase-3 flagship driver stays visible and no regression hides behind a new bar.

- [x] `[GATE]` **W5.13 — DEMO D6, "the walk that noticed".** On the simulator, both traces, screen-recorded, transcripts saved verbatim under `evidence/phase5-session/demo/`. **Rosemary is the bar sentence:** at **16:32 she sits, and by 16:45 she has lingered thirteen minutes**; the guide asks **exactly one question** — her bench against her 17:00 Orsay finish — she answers, and the day rebuilds around her answer with no leg over twelve minutes and no rest deleted to pay for it. **Fiona & Dev are the silence bar:** Dev pauses at 15:44, the clock suspends, **nothing is announced for sixty-three minutes**, and at **minute 107** the tour resumes into a day that has quietly re-timed itself — no debt language, no catch-up, no scold. Presented to the owner in the close report (the owner's read of it IS the watch, the W2.11 precedent).

- [x] `[GATE]` **W5.14 — the closing panel.** All eleven personas on the REAL session transcripts — both traces, every question asked, every silence held, every screen line — plus the four carried findings re-judged on the built thing (does "more breaks" still delete an anchor? does "fewer stops" now lengthen something? does the cap hold on the street route?). Verdict on whether §4.2's two tiers landed as ruled and whether the ONE question is a question a person would rather answer than be informed of. The four W4.12 NOs (Théo, Nadia, Marcus, Rosemary) are asked directly whether this phase moved them. Dissents by name.

- [x] `[GATE]` **W5.15 — close.** The phase's own tests + `make lint` + `make dedup-review` + `make test-workbench` + `make flutter-test` (with the S4.9 `CHROME_EXECUTABLE` override the Phase-4 ledger flagged, or the launcher fixed) + the demo (§0.7's close bar — **not** `make audit`). Judge (§2). Commit explicit paths (the S5.6 `request_sha256` move declared; Phase 8 re-seals). **Carry to the owner in writing:** the queue-avoidance ruling (carried 4) with the panel's reading attached, and the alternate-authoring spend as a measured number. Amend-and-carry this plan; re-plan Phase 6 at step level, with `generation.py`, `authoring.py`, `glue_client.py`, `render_md.py`, `narration_quality.py` and `premium_tour.py` read in full at that moment; delete nothing under `specs/` that Phase 6's re-plan still reads.


> **AMENDED 2026-08-19 AT CLOSE (W5.15) — what Phase 5 found, built beyond its step list, and
> carries.** Every entry below has its runs, its RED→GREEN→UNDO and its citations in
> `phase5-ledger.md`; this block is the plan's record of them (§0.7: amended, never absorbed).
>
> **Steps added by the gates and executed before close (all [x]):**
> - **S5.16 — the promise tier on the LIVE path; the place the person named is a promise.**
>   W5.14, 11/11 (Q2). `contingency.own_place_ids` (a story stop within 60 m of where the
>   person said the day begins or ends — Rosemary's "start Musée d'Orsay, end Musée d'Orsay";
>   R1.5 otherwise as locked), `question_text` / `at_risk_choice` (the rest first — the
>   thing that can be shortened, R2.3) extracted from the set and shared with
>   `routes._live_question`: a live replan whose remainder still overruns with the
>   protected things kept carries the ONE question as an entry of kind `live`; the phone
>   applies it on hold (default in force, two big buttons). Live-corpus test on Rosemary's
>   own day (UNDO → RED with exactly the D6 failure: "dropped it: ['Bench']").
> - **S5.17 — Rosemary's honest cap.** W5.14, 11/11 (Q1). (a) The street-certified retry
>   may not pay with a rest: a retried day that lost a rest the first had seated is refused
>   with the line naming the street number and her limit. (b) `_say_when_the_walk_limit_
>   binds`: a day of one or two story stops under a cap, below its nominal, is looked at
>   ONCE at a cap 1–3 min longer; a materially fuller day becomes one line on the
>   degradations channel ("With walks of up to 13 minutes this day would have 2 stops and a
>   rest, and run about 126 minutes instead of 90; allow longer walks to get it."). The
>   W4.2 underfill line (50 %) stands.
> - **S5.18 — a FIRM or WALL finish that moved later than the tolerance earns one screen
>   line** (`SessionPlan.end_hardness`; `finishMovedLine`, never spoken; an open day in
>   silence; R1.4 early in silence). W5.14 Q3 majority.
> - **S5.19 — names.** The finish is the PLACE when the day ends at one the person named
>   (`_finish_name(tour_input, route)`); lines and arms say "Musee d'Orsay", not "your
>   finish".
> - **S5.20 — the tour clock starts at the first play or the first step off the square**
>   (R1.3; Fiona & Dev); the wall clock from the tap.
> - **S5.21 — the "different settings" routing label knows every route-surface override
>   this build uses** (`THIS_BUILDS_ROUTING_CONFIG_SHA256S`); a step-free day is no longer
>   labelled (plan defect 17).
> - **S5.10's server half** also consumed `ReplanContext.listening_rate` (S5.6 had
>   threaded it and nothing read it): `visit_time.listened_seconds`, the gate, every trial
>   and `stop_clocks` price `max(visit, audio × rate)`.
>
> **Plan defects found in-phase (numbered in the ledger), all fixed in-session unless
> marked carried:** 1–5 read-precondition drift; 6–11 W5.1's (the workbench band-as-shape
> fix among them); 12 the phone had no playback screen (S5.11 built the minimal
> `SessionPage`); 13 the phone's days were DATELESS (it sends `start_date` + `start_time`,
> never the joined field — generate now joins them; Phase 4's clock reaches the phone for
> the first time); 14 a second, walk-less server clock reached the phone from the CRUD
> adapter (gone — the wire's `start_time` is `stop_clocks`); 15 the entries' finish clock
> was a second sum (now a view of `stop_clocks`); 16 **the phone has no voice** — no TTS
> plugin; every §4.4 rule is built at the etiquette layer through one silent door
> (`AudioProvider.speak`) and the screen carries every line — CARRIED to the owner; 17
> the step-free routing label (fixed, S5.21); 18 a dirty local git tree was a 503 on
> `make api` (an environment condition disguised as a product failure, behind a flag every
> entry point had to remember — gone: a dirty tree stamps HEAD tagged dirty and warns).
> Also: a day that seats a REST 500'd at generate on the app path (`GeneratedStop.beat_id`
> was required; optional on both sides now); pausing audio was read as the piece finishing
> (`AudioProvider.isCompleted`); the phone could not select an open day's minutes-left bands
> (`planned_end_hhmm` on the wire) and matched a late band from the wrong stop
> (`Divergence.atStopId`).
>
> **W5.12 (the kill criterion), measured on an iPhone 16 simulator:** SELECT worst 45 ms /
> 40 ms (bar 1 s); LIVE REPLAN 2.92 s / 2.29 s (bar 8 s) — after the design's own remedy
> (the first measurement was 11.6 s: 8.5 s of it the contingency set; the reply now carries
> the day plus the previous version's still-valid answers and the full set follows ~9 s
> later, persisted as the same version). The dial cells re-run: PDV-leg9 and the stacked
> dials now REFUSE honestly (S5.4's street cap, S5.3's one underfill line) where W5.1 had
> them shipping a 10-minute leg as 9 and a 2-stop 68-of-180 day; PDV-fewer = PDV-base at 5
> stops (carried finding 2's shape again — for Phase 6's panel); both refusals are slow
> (17.6 s / 11.8 s) — for Phase 6.
>
> **D6's bar sentence is amended.** Rosemary's "16:32 she sits, 16:45 lingered thirteen
> minutes, the guide asks about her bench against her 17:00 Orsay finish" is not a day the
> planner produces: her bench is at 14:16 and her day is over by 16:13 on both her days.
> What D6 SHOWS instead (final run, `evidence/phase5-session/demo/`): Fiona & Dev's 63
> silent minutes with the day re-timed and the finish named on screen; Rosemary's
> 50-minute linger at the Orangerie replanned in 2.3 s to a day that KEEPS the Orsay
> ("Next: Bench · 3 min / Musee d'Orsay by 16:57"). The ONE question fires on the live
> path when keeping everything overruns her clock (the live-corpus test shows it).
>
> **CARRIED TO THE OWNER, in writing (W5.15):** (1) the queue-avoidance ruling (carried
> 4) with the panel's R5 reading — 9 of 11 "outside, never delete, never ask"; Rosemary
> "outside only where the outside is worth minutes, else ask once"; Julien "outside by
> default, remove under a hidden-history lens, ask when pinned" — NOT built; (2) the
> alternate-authoring spend, measured: **zero provider calls** — every contingency entry
> is drawn from the planned day (W5.12: `authoring_units` 0 on every set); (3) the phone
> has no voice (defect 16); (4) the phone sends no open/firm — "ask once, at planning,
> whether 18:00 is a table or a guess" (F&D, Camille); the API's default is firm; (5) the
> panel's standing dissents by name (phase5-ledger W5.14): Marcus, Nadia, Julien — told
> default with undo, not two buttons, on their days; Théo, Nadia, Marcus, Sofia, Greta —
> their own days were never replayed on a device; Aiko, Sofia — answers priced for rain
> and dusk not shown; Nadia — no toilet or bakery in the corpus; Greta — a meal never ran
> through the fork; Sofia — the two buttons must work with no signal; F&D — a five-pause
> replay. **The four W4.12 NOs remain NO** (Rosemary: moved, not to yes).

### PHASE 6 — Narration changes. Demo **D7 "wrap it up at minute 14"**.

- **Delivers:** point-first writing (§5.2 — Fiona & Dev walk off at minute eight of
  nine), a written one-line close per named stretch (§5.3 — Nadia's meltdown exit is
  the panel's single most valuable moment), plant fallbacks and paired thread lines
  (§5.4), two lengths per major stop promoted from keep-exploring (§5.5),
  `narration_register` (the Phase 2 axis) finally consumed.
- **Demo D7:** hit wrap-up mid-walk; hear a real close.
- **Gating tests:** every acceptance test cites S1–S10/P1–P7 or the persona line; the
  close-lands-anywhere property is §7.4's "every prefix is decent" made executable.
- **Read preconditions:** `generation.py`, `authoring.py`, `glue_client.py`,
  `render_md.py`, `narration_quality.py`, `premium_tour.py`.

> **RE-PLANNED AT STEP LEVEL 2026-08-19 (the Phase 5 close, W5.15), with the six read
> preconditions read IN FULL at that moment (2026-08-19, tree 94a1fde7 + Phase 5's
> uncommitted work): `generation.py` 1,291 lines, `authoring.py` 780, `glue_client.py`
> 183, `render_md.py` 387, `narration_quality.py` 422, `premium_tour.py` 997; plus design
> §5 and the quality standard's §4 checks (C1–C12, G1–G8) and §2–§3 (S1–S10, P1–P7).**
> What the read established, and the steps below depend on: (a) per-stop authoring is ONE
> seam — `_certification_compose_requests` → `candidate_compose_request_envelope` →
> `finalize_certification_composition` — with the locked voice in `_COMPOSE_SYSTEM` and the
> output shape in `_COMPOSE_OUTPUT_SCHEMA`; **both are hashed into
> `premium_authoring_policy_sha256()` and that hash is sealed into the committed
> certification data**, so every prompt or schema change in this phase is a DECLARED
> BREAKAGE of the certification seal (Phase 8 re-seals; the plan's own "request_sha256
> move declared" precedent); (b) the stitch (`generation.generate`) ends every tour with
> two GENERIC glue lines (`GENERIC_OPEN_TOUR_CLOSING` / the round-trip loop line, then
> `GENERIC_TOUR_SIGNOFF`) — there is no authored close anywhere; (c) "two lengths" already
> exists as machinery (`build_poi_extra_beats` / `build_poi_extra_narration`,
> `overflow_by_poi`, the phone's keep-exploring tap and `/audio/generate-deeper-dive`) but
> as an EXTRA composed on demand; (d) cross-stop plants are ENCOURAGED by the prompt
> ("BUILD MOMENTUM … pay it off at the NEXT one") with no fallback, and Phase 5's
> contingency entries reuse the base day's composed text verbatim — so a dropped payoff
> stop leaves a dangling plant on every replanned day today; (e) `narration_quality` is a
> $0 surface lint whose composite scores are unreliable on one stop and whose G2/G3 proxy
> terms are measured INERT in production — Phase 6 uses it only for the per-stop
> sentence-length floor (C9) and never as a gate; (f) audio overlaps walking for STORIES
> (C7/C7b, `CONCURRENT_GLUE_LABELS`), and Phase 5 wrote the separate announcement rule.
>
> **Carried INTO Phase 6 from Phase 5 (W5.14/W5.15):** the four W4.12 NOs and five more
> personas never saw their own day on a device (W6.12 replays all eleven); the phone has no
> voice (defect 16 — W6.2 rules whether the set's lines and the closes are PRE-VOICED at
> compose time or a device voice is wired); the phone sends no open/firm (S6.10 asks
> once at planning); PDV-fewer = PDV-base (carried finding 2's shape) and the slow honest
> refusals (17.6 s / 11.8 s) go to W6.1's measurement; Greta's meal and Nadia's toilet are
> corpus facts Phase 6 does not own (Phase 1/6.1's enrichment; recorded).
>
> - [x] `[DEMOLISH]` **D6.0 — the tests that stand in front of Phase 6's own deliverables.**
>   Grep FIRST (§0.7's coupling rule), then delete or re-derive: every test that pins the
>   generic closing lines as the tour's ending (`GENERIC_OPEN_TOUR_CLOSING`,
>   `GENERIC_TOUR_SIGNOFF`, `_build_closing`'s two-line shape), every test that pins
>   keep-exploring as an on-demand extra (the `/audio/generate-deeper-dive` round trip as
>   the ONLY way to the full telling), and every test that pins `_COMPOSE_SYSTEM` /
>   `_COMPOSE_OUTPUT_SCHEMA` byte-identity or `premium_authoring_policy_sha256()`'s value.
>   **Declared breakage:** the certification seal (committed candidate data hashes the
>   policy) — recorded as Phase 8's re-seal, never worked around. Survivor proof: the
>   authoring gates (`tests/test_tour_authoring_gates.py`) still collect; `make lint`.
> - [x] `[GATE]` **W6.1 — measurement first (§10.9): narration's before-picture, on real
>   composed days.** No code. On the W5.1 cells and both persona days, composed on the app
>   path: (a) **where the point lands** — per stop, the word offset at which the stop's
>   primary beat (the first beat of its capped plan) is first cited, against the first
>   minute (150 words at `SPOKEN_WPM`); how many stops land their point after the walk-off
>   minute (F&D leave at minute 8 of 9); (b) **closes** — zero authored closes exist; record
>   what the generic two lines say on each day and what a wrap-up at each stop would play
>   today (the Phase 5 set's `wrap_up_from` entries carry no close: measure it); (c) **two
>   lengths** — `extra_beat_ids` per stop, which stops are "major" by tier/promise, and the
>   composed `extra_narration` length where it exists; (d) **dangling plants** — over every
>   Phase 5 contingency entry that drops a stop, whether the previous stop's composed text
>   references the dropped one (the plant left hanging), counted; (e) the register axis:
>   what `narration_register` does today (nothing — prove it); (f) the spend to come: one
>   provider call per authored close, per plant fallback, per thread pair and per second
>   length, counted before it is billed; (g) the two slow honest refusals (W5.12) timed
>   again so Phase 6's measurement keeps them visible. Verbatim under
>   `evidence/phase6-narration/`.
> - [x] `[BUILD]` **S6.1a — AMENDED 2026-08-19 (plan defect 4, found by W6.1's first
>   in-process cell): the route surface rides through compose and finalize.** **Files:**
>   `src/tour/premium_tour.py` (`finalize_premium_tour` stamps
>   `VALHALLA_ROUTING_CONFIG_SHA256_BY_SURFACE[plan.tour_input.route_surface]`, not the
>   default), `src/api/routes/trips.py` (`compose_trip`'s `summarise_route` rebuild carries
>   `costing_options_override=ROUTE_SURFACE_COSTING_OVERRIDES[tour_input.route_surface]`).
>   THE CLASS: the day's routing identity was re-derived as the default downstream of
>   selection — the workbench could not author any step-free/no-stairs day
>   (`FinalTourBlueprint`: "Valhalla receipt routing configuration differs from build
>   fingerprint"), and the phone composed such a day re-routed on the default surface.
>   **Extends:** S2.7/S5.21's surface map. Tests: `test_tour_party.py::
>   test_a_surface_routed_day_finalizes_under_its_own_routing_identity` (hermetic),
>   `test_trip_api.py::TestLivingSession::test_compose_rebuilds_the_day_under_the_surface_it_was_planned_with`
>   (live). RED→GREEN→UNDO→RESTORE in phase6-ledger.md. Two inherited rows re-derived as
>   written decisions (the frozen-trip marker in `test_a_faithful_tour_still_composes`, red
>   since S5.8; S5.16's lateness fixture re-tuned on the corrected clocks).
> - [x] `[GATE]` **W6.2 — THE EARLY PANEL, before any narration code.** All eleven, one
>   brief, on W6.1's numbers and their own persona files. They rule on: (1) **what "the
>   point" of a stop is** and where the first minute ends — the thing point-first protects
>   when Fiona & Dev walk off; (2) **the close's shape** — one line, per named STRETCH:
>   what a stretch is (a stop's story; the day), its register for Nadia's exit and
>   Rosemary's "that was the walk", whether it may name what was skipped (gift, never debt
>   — R2.2's banned words bind); (3) **two lengths** — which stops are "major" (tier,
>   promise, lens match), how the tight telling is chosen (the capped plan as it is today),
>   and the LINGER rule that opens the full telling (R3's seam, never mid-piece; Théo gets
>   twelve, F&D four, from the same material); (4) **plants** — inside the stretch only;
>   the fallback line's shape when the payoff stop is traded; (5) **threads** — the paired
>   line for every adjacency the contingency set can produce, authored at compose time;
>   (6) **the voice** (defect 16) — PRE-VOICE the closes and the set's fixed lines at
>   compose time through the existing per-stop TTS path, or wire a device voice; the
>   clocks in the live question stay screen-first either way; (7) **register** — what each
>   `narration_register` value changes in the one voice (§2.4's "the party sets the
>   voice"); (8) **D7's moment** — what plays at "wrap it up at minute 14": the current
>   stretch's close, then the nav home, and nothing else (§4.4.4). Dissents by name. The
>   rulings BIND S6.3–S6.10.
> - [x] `[BUILD]` **S6.3 — point-first: ONE rule, ONE floor check.** **Files:**
>   `src/tour/authoring.py` (`_COMPOSE_SYSTEM` — the CRAFT block's "OPEN ON A MOMENT / LEAD
>   WITH THE STAKES" gains its measurable form: the stop's point — its primary beat's claim
>   — is voiced in the first minute), `src/tour/compose_gate.py` + `quality_rubric.py` (a
>   new FLOOR check **C13 point-first**: the first 150 words of a stop cite the stop's
>   primary beat; WARN at first, BLOCKER when W6.9 measures its pass rate on real days).
>   **Extends:** the existing per-stop verifier (`build_full_verifier`) — a new check in
>   the one gate, never a second gate. RED first: a hermetic composed stop whose point sits
>   in its last sentence fails C13; the same stop with the point first passes. Declared
>   breakage: the policy hash (D6.0). RED→GREEN→UNDO→RESTORE. *Sabotage:* measuring "the
>   point" by word count of the first beat rather than its claim; a prompt change with no
>   check (the W4.x lesson: prose rules without a floor drift).
> - [x] `[BUILD]` **S6.4 — closes that land anywhere (§5.3).** **Files:**
>   `src/tour/authoring.py` (schema: one `close` sentence per stop, `source_type` glue,
>   `source_id` GLUE_CLOSING, ≤ one sentence, entailed against the stop's own claims by
>   the existing gate; the prompt's CLOSE rule), `src/tour/generation.py`
>   (`_build_closing`'s two generic lines become the FALLBACK when a stop's close is
>   missing), `src/tour/artifact.py` (a close is a stationary line at its stop — playback
>   assignment), `src/api/models/trips.py` + `routes/trips.py` (`ItineraryStop.close_text`
>   on the wire; per-stop audio generation voices it — W6.2 (6)), `mobile/lib/services/
>   tour_playback_service.dart` (the wrap-up entry plays the CURRENT stretch's close at the
>   seam — ONE sentence, screen + the one door — then the nav home; a skip plays nothing).
>   **Extends:** the one authoring seam and the Phase 5 queue; no second closing writer.
>   RED first: a composed stop without a close refuses at finalize; the phone's [Head back
>   now] shows/speaks the close. **"Every prefix is decent" (§7.4) made executable here:**
>   for every k, the day cut at k passes the rubric floor (C5/C6/C8) and ends on k's close.
>   *Sabotage:* a generic templated close ("And that completes the walk") counted as
>   authored; a close that names what was dropped as a loss (R2.2 bans "late", "behind");
>   speaking the close on a leg.
> - [x] `[BUILD]` **S6.5 — plants, payoffs and threads survive adaptation (§5.4).**
>   **AMENDED 2026-08-19 AT CLOSE (W6.2 R4 LOCKED 8/11, R5 LOCKED 11/11 — the panel ruled
>   against this step as written; phase6-ledger.md "Plan-facing consequences" and §S6.5):**
>   the cross-stop plant is DELETED, not fallback-insured — `plants: [{text, payoff_stop_idx,
>   fallback}]` is NOT built and no spoken fallback line exists ("a sentence spoken to mend a
>   sentence" — F&D; with cross-stop promises forbidden there is nothing to fall back from).
>   **As built:** `src/tour/authoring.py` — "NO FORWARD PROMISES" replaces "BUILD MOMENTUM"
>   (plant and payoff inside the stop's own first three minutes; a neighbour NAMED as a fact,
>   never promised; the payoff re-names its subject; never open on a recap); "THE THREAD"
>   replaces the reflection recap (ONE sentence, ≤ 15 words = `THREAD_MAX_WORDS`, one name, a
>   fact of THIS stop binding it to the walk; entailed against visited ∪ OWN — `verify.py`'s
>   GLUE_REFLECTION window widened, Phase 4's recap tests re-derived); "THREADS FROM" in the
>   user prompt asks the writer for one line per SKIP predecessor (`ComposeRequest.thread_from`
>   = stop k-2's name for k ≥ 2 — exactly the adjacency the set makes by construction, R1.2:
>   no adjacency report from contingency.py needed), answered in the schema's optional
>   `threads` field THROUGH THE STOP'S OWN CALL — zero extra spend, not one call per adjacency.
>   `_keep_threads` DROPS AND REPORTS (`thread_dropped` degradation) a two-sentence, over-long
>   or — with the live checker — unentailed thread (measured 2026-08-19, s65-proof: as
>   ValueError these killed 2 of 3 real F&D composes over an optional line; refusal is for
>   missing MANDATORY content, the S6.4 precedent) and still refuses (ValueError) the protocol
>   violation of an unasked-for name; an absent thread is legal (none rather than glue). The
>   mechanical check: `FORWARD_PROMISE_PHRASES` + `FORWARD_SIGHT_PHRASES` (the latter only when
>   the sentence names a LATER stop) scanned over story glue in `validation.
>   _forbidden_phrase_hits` (code `forward_promise:*`, blocking); GLUE_NAV and beat text exempt.
>   The wire: `PremiumTourResult.threads_by_stop` → compose_trip → `thread_lines` per stop
>   (JSON string in the graph, decoded by `GeneratedStop`'s validator), keyed by predecessor
>   NAME on the ARRIVING stop. The phone: `_threadForNewPair` at the one reorder seam — the
>   pair the session MADE gets its line on screen for the whole leg and spoken once at the
>   next STANDING seam via the S6.4 queue (never mid-leg; the question outranks it; wrap-ups
>   thread nothing); the planned pair's thread rides inside the arriving stop's narration.
>   Tests: `tests/test_tour_narration_rules.py` (4), `tests/test_tour_validation.py` (1),
>   `tests/test_tour_verify.py` (3 re-derived), `mobile/test/services/session_thread_test.dart`
>   (4) — RED→GREEN→UNDO→RESTORE in the ledger. POLICY HASH MOVED (declared breakage):
>   `5c9571e65c798f1fb5d952d68c01cfa41bfb52d592976ed606f9efa0736e78ea`.
>   *Sabotage (as ruled):* a fallback line played to mend a promise; a thread that recaps or
>   uses "since we're not going to"; a second thread seam outside the stop's own compose call.
> - [x] `[BUILD]` **S6.6 — two lengths per major stop (§5.5), promoted from an extra.**
>   **AMENDED 2026-08-19 AT CLOSE (W6.2 R3 LOCKED 11/11 — the panel re-ruled this step;
>   phase6-ledger.md §S6.6):** MAJOR is a BUDGET, not a tier: overflow exists AND
>   `planned_visit_seconds >= 2 x tight`; TIGHT ≈ 3 min — `MAX_DWELL_AUDIO_SECONDS`
>   270→180 at the one emission choke point (pricing moves with it; the density dial
>   keeps its shape 90/180/270). The re-cap exposed and fixed two latent planner
>   defects (the ledger's §S6.6.2): the timebox repair could buy the duration band with
>   walking past the walking budget on open days (admission rule added beside the
>   per-leg cap; fixed-B corridors exempt — mandatory walking), and `order_stops`'
>   heuristic could return an order WORSE than its feasible input (never-worse guard in
>   the dispatcher; measured 624 s on a 21-stop pinned chain). A third fix (a rescue
>   walking bound) was added on a misattribution and WITHDRAWN — the rescue's charter
>   is to trade walking-allocation for a viable day below the stop floor. FULL = a
>   second COMPOSED piece from the stop's overflow through the ONE seam
>   (`plan_premium_full_telling` → `plan_premium_authoring(single_stop=…,
>   already_told_by_stop=…)`), point-first with its OWN close, ≤ 3× tight hard cap 12
>   min, repeating nothing of the tight (verbatim echo gate), fact-gated like the day —
>   every miss DROPS AND REPORTS (`full_telling_dropped`), never the day. NOT "adds the
>   overflow beats" as raw text (11/11: "a dump, not a telling"). Wire:
>   `full_narration`/`full_close_text` (audio at S6.8, not `full_audio_url` now);
>   `keep_exploring_stop_audio` voices the authored full telling where one exists — the
>   on-demand route stays for minors. Phone: the LINGER RULE as ruled — an OFFER on
>   screen with its cost, silently, at a standing seam after the tight ended on its
>   own; a TAP plays; auto-play is NOT built (9/11; the panel's four exceptions
>   recorded, not built); "again" is a separate control; the listening rate learns
>   nothing here (that idea died with auto-play). Tests: 5 in
>   `tests/test_tour_narration_rules.py`, 1 in `tests/test_tour_ordering.py`, fixture
>   re-derivations in selection/certification/b-materialization suites (each with its
>   written reason), `mobile/test/services/session_full_telling_test.dart` (3) — all
>   RED→GREEN→UNDO→RESTORE in the ledger. Policy hash UNCHANGED (ALREADY TOLD is
>   per-request, hashed into `compose_input_sha256`, not into the sealed policy).
>   *Sabotage (as ruled):* a third composer; the dump served as the full telling;
>   auto-play on stillness; a full telling that kills its day.
> - [x] `[BUILD]` **S6.7 — `narration_register` consumed.** **AMENDED 2026-08-19 AT
>   CLOSE (W6.2 R7, 11/11; phase6-ledger.md §S6.7):** solo = the locked voice
>   BYTE-IDENTICAL (no delta block); warm/family = user-prompt DELTAS, address only,
>   each carrying the invariants (facts, names, length, identity, point-first, the
>   close; never the hour/weather/mobility); Paulo's density rules bind every register
>   and went into the LOCKED VOICE (one name a sentence, short words, gloss "Jesuit",
>   no idiom) — the policy hash moved to 4c2443da… (declared for Phase 8's re-seal).
>   Hermetic prompt tests + the live measurement both done: one real stop under solo vs
>   family — mean sentence words 23.3 → 15.7, share over twenty 60% → 24%, the child's
>   find in the first minute, same facts (s67-proof.json). *Sabotage (as ruled):* a
>   register that changes nothing measurable; a second voice; a delta that adds
>   sentences.
> - [x] `[BUILD]` **S6.8 — the voice, per W6.2 (6).** **AMENDED 2026-08-19 AT CLOSE
>   (R6a 11/0; OWNER RULING: the tour's own voice, never the robot; phase6-ledger.md
>   §S6.8):** the authored session lines — each stop's close, its thread lines, the
>   full telling's close — are PRE-VOICED by the per-stop voicing pass as their own
>   hash-guarded artifacts (`close_audio_url`, `thread_audio_urls`,
>   `full_close_audio_url`) in the narrator's voice; the set's fixed lines stay
>   SCREEN-ONLY and are never sent to TTS; plant fallbacks do not exist (R4). The
>   phone's queue gained the file door (a line with its file plays through the
>   narrator; file-less lines still speak); a wrap-up mid-FULL-telling finishes the
>   full's own sentence and plays the FULL's close file. No device voice; the live
>   question unchanged (spoken once, clocks screen-first). Tests + UNDO in the ledger.
> - [x] `[BUILD]` **S6.9 — the phone asks once, at planning, whether the end is a table
>   or a guess** (W5.14 F&D/Camille; defect 13's sibling): BUILT 2026-08-19 with the
>   OWNER'S DEFAULT (ruling 3): skipping the question means a HARD DEADLINE. The page
>   asks in plain words ("Is the end time fixed?" — Just a guess / Should end then /
>   Booked — can't be late, firm preselected); `generateTrip` sends `end_hardness`
>   explicitly ('firm' untouched); the API default was already firm. Tests + UNDO in
>   the ledger. *Sabotage:* a fourth value; a default that guesses.
> - [x] `[GATE]` **W6.10 — the kill criterion, measured.** PASSED 2026-08-19 — the numbers and the honest floor reading are in phase6-ledger.md §W6.10 (point-first 0/7 → 4/7 clean with the rest WARN-only; closes 0 → 28/28 authored; 16 full tellings; attempts ≤ 2; spend = stops+majors). On the W5.1 cells composed
>   under the new prompt: the rubric's FLOOR pass rates (C1–C9 + C13) before/after; the
>   point-first pass rate on real days; the close's entailment pass rate; authoring
>   latency and spend per day (closes + fallbacks + threads + second lengths) as numbers.
>   Over budget or quality down → the design's own remedy: fewer authored lines (threads
>   only for adjacencies the set reaches), never a weaker gate.
> - [x] `[GATE]` **W6.11 — DEMO D7, "wrap it up at minute 14".** PASSED 2026-08-19
>   (phase6-ledger.md §W6.11; demo/D7-transcript.txt + frames). AMENDED: the "plant's
>   fallback line" second run is DEAD by R4 (no fallbacks exist) — the second act is THE
>   THREAD: a skip makes a new pair and its authored bridge line shows through the leg and
>   plays once at a standing seam, in the narrator's voice. The demo caught and fixed two
>   real planner defects first ('other' never spends; a keep-constrained tail gets the
>   whole walking budget) and one wire defect (the session GET now overlays the items'
>   live audio). The owner's read is the watch.
> - [x] `[GATE]` **W6.12 — the closing panel, EACH ON THEIR OWN DAY.** CLOSED 2026-08-19 — eleven verdicts verbatim (w612-verdicts.md): 3 yes, 2 telling-yes/day-no, 1 not proven, 5 no; the narration quoted with approval by ten of eleven, every planner-shape finding carried by name (ledger §W6.12). The W5.14 carry: all
>   eleven persona days generated on the app path and replayed on the simulator with their
>   doc's trace (the five-pause F&D replay included); the narration changes judged on the
>   real composed text; the Phase 5 standing dissents re-judged on built evidence (told
>   default + undo for Marcus/Nadia/Julien; Rosemary's cap line and her Orsay; the firm
>   finish line; the voice). The four W4.12 NOs asked again. Dissents by name.
> - [x] `[GATE]` **W6.13 — close.** The phase's own tests + `make lint` + `make
>   dedup-review` + `make test-workbench` + `make flutter-test` + the demo; judge; commit
>   explicit paths (the policy-hash breakage declared for Phase 8's re-seal); carry to the
>   owner in writing; amend-and-carry this plan; re-plan Phase 7 at step level with
>   `audio_service.dart`, `src/audio/*`, `spatial_check.py` and `audio.py` read in full at
>   that moment.
>
> **AMENDED 2026-08-21 (W6.13 done).** Judge ruled PROVE-FIRST first: (1) the W6.12 finding-1 fix had no test that dies without it — closed with the named seam `_resolve_persisted_pick` in routes/trips.py and a red-first guard (`test_compose_corpus_check_rebuilds_the_end_sentinel`); (2) only the phase's files had been run — the WHOLE tests/ tree found 10 failures (five fixtures in other files sized for the 270 s ceiling, one older test asserting the rule W6.12 changed, four red since the Phase 5 commit: its seam import inside a function and its underfill line), all resolved or re-derived with the reason in phase6-ledger.md §W6.13, second run 2622 passed (judge re-ran independently: 2622); (3) a ledger placeholder filled; (4) the owner report posted in chat. Then PROCEED. Commit `2e500468` (53 explicit paths). §0.7 close bar amended: the whole tree on the final code.

> **CARRIED FROM W6.12 (2026-08-19) — the closing panel's planner findings, by name, for the
> owner to slot (they are NOT narration and NOT audio; most belong to the planner's
> selection, i.e. a phase of their own or the W4.12/W5.14 carry lists):**
> 1. ONE-STOP DAYS for four persona shapes — Nadia's family loop, Julien's two-hour
>    hidden-history walk, Rosemary's preset loop (the cap raise alone did not restore her
>    three stops — the art lens thins her pool), Marcus's station loop. A one-stop day also
>    never fires told/undo or the question, so those dissents stay "not proven by
>    construction".
> 2. CAMILLE'S DAY CANNOT COMPOSE — six deterministic refusals, two vignette-shaped Pont
>    Neuf beats untraceable; spun off with the reproduction (task chip; ledger §W6.12).
> 3. THE LENS SERVES THE WRONG STOPS — Théo's dark-history day has one dark stop of six and
>    skips the Conciergerie; Julien's hidden-history opens on Morrison and Piaf; Aiko's
>    visual_art anchor came back "Historic Cuisine".
> 4. HOUR AND WEATHER UNPRICED — Aiko's Tuesday walks into two shut museums, rain prices
>    nothing; Sofia's December day stands her outdoors after dusk.
> 5. GRETA'S SATIATION — built as a mid-walk skip mechanic; yesterday's museums must spend
>    today's category before the day begins; her booked lunch has no seat.
> 6. NARRATION LEAKS (this phase's own, small): four-name sentences (five testers quote
>    one), Paulo's six idioms and five unglossed words, the extras dump still reachable
>    behind "more" where no full telling was authored, the day's close not naming the
>    finish (Marcus, Sofia), fulls landing at minor stops while anchors go without (Aiko,
>    Théo), the family register's <20-word rule leaking (7 of 27 on Nadia's day).
> 7. The sealed certification batch no longer matches the writer's policy hash
>    (4c2443da5f41360930e58a56aa375e908f3a59612968d298f4adb05a912af222) — Phase 8 re-seals.
> 8. Ticket lines — LATER PHASE by owner ruling 2026-08-19.

### PHASE 7 — Audio placement; **delete the 10 m circle (8.4) and per-beat audio (8.5)**. Demo **D8 "stand here"**.

- **Delivers:** per-place trigger geometry (§5.6 — a 140 m courtyard is not a
  point), story-in-the-queue, threshold silence at marquee interiors, segmented
  audio at within-place anchors (6.9 — the corpus already carries them).
- **Deletions in the same phase:** the one-size trigger circle; the per-beat audio
  library and the anonymous paid authoring door (`/audio/generate-trip`'s per-beat
  path and the admin-gated per-beat routes it feeds — `audio.py` read end to end
  today, its per-stop successor already live beside the legacy path). **Seam:** the
  AUDIO PLACEMENT RULE gets a source-scanning test (one definition of
  what-plays-where).
- **Demo D8:** the Notre-Dame segmented walk-through, heard on a device.
- **Kill criterion (design §9):** segmentation degrading listening in review →
  marquee anchors only.
- **Read preconditions:** `audio_service.dart`, `src/audio/*`, `spatial_check.py`,
  re-read `audio.py`.

> **RE-PLANNED AT STEP LEVEL 2026-08-19 (W6.13, the four read preconditions read in full —
> the factual map is in phase6-ledger.md §W6.13; every step cites the file:line it
> touches; §0's rules bind; tests derive from the design; UNDO pasted per step).**
>
> **What the map says today (the facts the steps stand on):** the phone's `speak()` is an
> empty stub (`audio_service.dart:99-105`) — there is NO device voice, by the owner's
> ruling; every session line is a FILE or the screen. `play()` is cache-first
> (`:61-87`), completion is a ChangeNotifier state (`:241-252`), `position`/`duration`
> come from just_audio (`:52-53`); there is NO AudioSession, ducking, interruption,
> lock-screen or spatial handling anywhere under `mobile/lib/` (grep: zero). Server side
> the per-stop voicing path (`audio.py:893-1027`) plus the session-line pass
> (`:800-890`) and the keep-exploring door (`:1055`, prefers `full_narration`) are the
> live paths; `/audio/generate-trip` (`:669`, primary beat only) and the admin per-beat
> routes (`:571`, `:610`) are the LEGACY per-beat library Phase 7 deletes. MP3 DURATION IS
> AN ESTIMATE (`pipeline.py:46-103`: first-frame bitrate × size) — the S6.4 sentence-end
> arithmetic and every clock built on `audio_duration_sec` inherit that error.
> `spatial_check.py` is consumed by nothing but its own test (zero extractions over 9,642
> real sentences; prod ships no `data/`) — a candidate for the demolition list, decided
> at W7.1. The 10 m trigger circle lives at `tour_playback_service.dart:138/151` (Phase 7
> owns its deletion; `prefetchAudio` and `haversineDistance` are protected from
> over-deletion).
>
> - [x] `[DEMOLISH]` **D7.0 — the tests that stand in front of Phase 7's deliverables.** The
>   per-beat audio tests (`tests/test_audio_trip_api.py`'s primary-beat path, the admin
>   per-beat generate/batch tests), the 10-m-circle geofence tests in the playback suite
>   (`test_tour_playback_service*.dart` — the arrival radius), and `tests/test_spatial_
>   check.py` if W7.1 rules the module dead. Tombstones with the reason, never edits to pass.
> - [x] `[GATE]` **W7.1 — measurement first (§10.9): audio's before-picture, on the W6.12 days.**
>   On the eleven persona sessions (evidence/phase6-narration/w612-session-*.json): (a)
>   where each stop's piece would TRIGGER under the 10 m circle vs the place's real footprint
>   (the 140 m courtyard, the 300 m square — §5.6), measured against corpus coordinates and
>   the F&D finding that stops 5–6 narrate ground kilometres from their pins; (b) the
>   duration estimate's error: render ten real pieces, compare `pipeline._get_duration`'s
>   header estimate against `ffprobe`/the player's own `duration` — the number the S6.4
>   sentence-end arithmetic is wrong by; (c) the silence map of each day: seconds of walking
>   with nothing playing, seconds inside a marquee interior with a piece playing (threshold
>   silence — the thing the design wants), seconds of queue with nothing (story-in-the-queue);
>   (d) `spatial_check.py`'s yield on the eleven days (expected zero → demolition ruled);
>   (e) what an interruption does today (a phone call, another app's audio): nothing is
>   handled — measured as the crash/continue behavior on the simulator. Numbers in the
>   ledger before any code.
> - [x] `[GATE]` **W7.2 — THE EARLY PANEL, before any audio code.** All eleven, one brief, on
>   W7.1's numbers and their own W6.12 days: (1) the trigger geometry they want per place
>   kind (a square's edge vs its centre; a courtyard's gate; a bridge's mid-point); (2) what
>   plays in a queue and what never does (Camille's 28 minutes; Théo refuses queues); (3)
>   threshold silence at marquee interiors — who wants the piece to STOP at the door
>   (Greta, Aiko, Rosemary's Orangerie bench) and who wants it to follow them in; (4)
>   segmented audio at within-place anchors (Notre-Dame's portal → nave → rose window): one
>   piece or several, and what re-triggers; (5) interruptions — a call, a photo, a second
>   app: resume where, say what; (6) the duration error's tolerance for the sentence-end
>   seam. Locked rulings bind S7.3–S7.9.
>
>   **DONE 2026-08-22 (phase7-ledger.md §W7.2 — the eleven verdicts verbatim in
>   `evidence/phase7-audio/verdicts/`, the LOCKED RULINGS R1–R6 with every dissent by name).
>   The rulings AMEND the steps below as follows; the step text under each stays as the
>   original intent and the ledger's R1–R6 is the binding form:**
>   - **R1 → S7.3/S7.4:** both one-size circles die (the 10 m trigger AND the 40 m "at the
>     stop"); "at the stop" is the place's own footprint (`trigger_radius`, the field the
>     corpus already holds — plan defect 1); the piece ARMS at the first touch of the
>     footprint (the edge you arrive by, never the pin) and STARTS at arrival — FAMILY starts
>     at the first standstill inside the footprint (Nadia; Paulo and Rosemary dissent by
>     name); told once is told (no replay on re-entry; a tap replays); the A→B finish and a
>     round trip's return take the day's own-place radius, never a 10 m dot (Marcus, Sofia);
>     the rule carries a `kind` field — "circle" this phase; a line/polygon for streets,
>     bridges and the cemetery is a CARRIED data row (Théo, Greta, Sofia, Julien, Camille,
>     Marcus asked; the corpus holds no such geometry).
>   - **R2 → S7.5:** the queue piece is the stop's TIGHT telling, whole, with its close — NOT
>     a queue-cut two-minute piece (nobody asked; Camille against) — starting at its first
>     STORY sentence, never the walking line; auto-started at the first standstill inside the
>     footprint of a stop whose arrival hour prices a line; couple and family get a screen
>     offer and a tap (F&D, Nadia); `wall` prices no queue so has no piece; the full telling
>     by tap (Camille and Julien dissent: the full by default); never the linger offer or a
>     question in a line; Marcus's and Julien's "my legs carry the telling" recorded, not built.
>   - **R3 → S7.6:** a DOOR = the plan's own `goes_inside` (an arcade, passage, courtyard gate
>     or garden is OUTSIDE, by category never by GPS loss); the piece ends at the end of its
>     current sentence when the placed OUTSIDE minutes run out, then the stop's CLOSE plays
>     at the door; inside, the whole transcript with a keep-listening tap that resumes at the
>     cut sentence's start; the linger offer is never spoken at a door; nothing resumes by
>     itself on exit (Camille/Sofia want the close at exit, Marcus/Paulo a resume at exit,
>     Julien the voice in at tier-2 doors — dissents by name).
>   - **R4 → S7.7:** segments only for anchors with a HUMAN-PLACED coordinate (a reviewed anchor
>     table, Notre-Dame first — the demo); outdoor segments auto when the walker STANDS at
>     the anchor, interior segments tap-to-play; couple/family every segment by tap; no
>     re-trigger on wandering back; D8 = Notre-Dame's OUTDOOR segments (parvis → gallery of
>     kings → portal) auto and the nave/rose window by tap; Nadia's walk-off-and-back test;
>     plan defect 7: every stop's LEG LINE becomes its own segment placed on the leg (the
>     stop piece today opens with the walking line the person has already walked — Théo,
>     Greta, Aiko, Marcus).
>   - **R5 → S7.9:** background audio mandatory; call/other voice/Siri pause; resume at the
>     START of the cut sentence, saying nothing, by itself when still inside the footprint
>     (the couple resumes by tap — F&D); off the footprint the missed close goes on screen and
>     is said once at the next standing seam; navigation prompts duck, music pauses, a photo
>     changes nothing; a lock-screen pause control.
>   - **R6 → S7.8:** the seam from the PLAYER'S real length; finish the sentence capped at
>     8 s (family 0 — cut at once; `wall` 5 s); unknown length → cut at once and play the
>     close (Rosemary, Camille, Julien would wait — dissents).
>
> - [x] `[BUILD]` **S7.3 — the AUDIO PLACEMENT RULE, one definition, one test.** **Files:**
>   a new `src/tour/placement.py` (what-plays-where: per place kind, the trigger geometry,
>   the threshold rule, the queue rule, the segment rule — ONE pure function from
>   (place, position, state) to (piece, action)), `mobile/lib/services/tour_playback_
>   service.dart` (the 10 m circle at :138/:151 REPLACED by the rule's geometry — the
>   phone SELECTS from what the server placed, design §4.6), `src/api/models/trips.py` +
>   `crud/trips.py` (each stop carries its trigger geometry on the wire: the polygon/radius
>   the rule assigned). **Seam:** a source-scanning test proves no second definition of
>   what-plays-where exists (a source scan for `kStopCircleM`-class constants outside placement).
>   RED first: a 140 m courtyard triggers at its gate, not 10 m from its centroid; a
>   square triggers at its edge; the old circle constant is gone.
> - [x] `[BUILD]` **S7.4 — per-place trigger geometry in the corpus (§5.6).** **Files:** the
>   POI exports (`scripts/sync_poi_exports.py`, `data/paris/poi-raw.json` — read first) gain
>   `trigger_geometry` (kind + metres, or a polygon where the corpus has one), derived at
>   import from `place_category` + `visit_goes_inside` with a human-reviewed override per
>   marquee; `src/tour/selection.py`'s CorpusSnapshot loads it. RED first: every dwell POI
>   carries a geometry; a marquee interior's is its DOOR, not its centroid.
> - [x] `[BUILD]` **S7.5 — story-in-the-queue (§5.6).** **Files:** `src/tour/contingency.py`
>   / the session wire — a stop with a priced queue (`queue_seconds > 0`) carries a
>   QUEUE piece: the tight telling's first two minutes re-cut to play standing in line, with
>   its own close, authored through the one seam (`plan_premium_authoring(single_stop=…)`,
>   S6.6's mechanism); the phone plays it when the placement rule says "in the queue" (the
>   geometry + stillness), never inside. Camille's ruling (W6.2: she listens through part of
>   the queue) and the owner's ruling on queues (later phase for AVOIDANCE; this is the
>   story FOR a queue the day already priced). RED first: a queued stop carries the piece;
>   an unqueued one does not; the piece is entailed and closed like any telling.
> - [x] `[BUILD]` **S7.6 — threshold silence at marquee interiors.** **Files:** `tour_
>   playback_service.dart` — crossing a marquee's door geometry (S7.4) while a piece plays
>   finishes the SENTENCE (the S6.4 arithmetic) and stops; the screen keeps the transcript;
>   no piece starts inside unless the person taps. Per W7.2's ruling on who wants what.
>   RED first: the door ends the sentence, never the word; nothing auto-plays inside.
> - [x] `[BUILD]` **S7.7 — segmented audio at within-place anchors (6.9).** **Files:** the
>   corpus already carries within-place anchors (`sub_location` / `trigger_address` on
>   beats); `src/tour/render_md.py` + `crud/trips.py` — a marquee stop's telling is SPLIT at
>   its anchors into segments, each voiced by the per-stop path as its own artifact (the
>   session-line mechanism generalised: `segment_audio_urls`), each with the placement rule's
>   geometry; the phone plays the segment whose anchor the person reaches. Demo D8's
>   material. RED first: Notre-Dame's telling ships as N segments with N geometries and N
>   files; a non-marquee stop ships one.
> - [x] `[BUILD]` **S7.8 — the duration is MEASURED, and the clocks trust it.** **Files:**
>   `src/audio/pipeline.py:46-103` — `_get_duration` measures MP3 duration exactly (decode
>   the frame table or probe with the same tool the eval loop already trusts) instead of the
>   first-frame estimate; the phone's `secondsToSentenceEnd` (S6.4) takes the player's own
>   `duration` when the file is loaded, the wire's when not. RED first: a rendered file's
>   stored duration equals its played duration within 0.5 s; the sentence-end wait on a real
>   file lands inside the measured sentence.
> - [x] `[BUILD]` **S7.9 — interruptions: a call, a photo, another app.** **Files:**
>   `audio_service.dart` — an AudioSession (the just_audio session API) with the
>   interruption/ducking policy W7.2 rules; on resume the piece restarts at the last
>   SENTENCE boundary (the S6.4 arithmetic again), never mid-word, and the screen says
>   nothing unless the close was missed. RED first: a simulated interruption pauses without
>   a crash and resumes at the sentence start.
> - [x] `[DEMOLISH]` **S7.10 — the per-beat audio library and the anonymous paid door.**
>   **Files:** `src/api/routes/audio.py` — delete `/audio/generate-trip` (`:669`, primary
>   beat only) and the admin per-beat `generate/{beat_id}` + `generate-batch` (`:571`,
>   `:610`) and their `NarrativeBeat.audio_url` writes; `src/audio/pipeline.py`'s beat
>   key path (`:106-114`); the phone's per-beat status poll (`audio_service.dart:156`). The
>   per-stop path (`:893`) and the keep-exploring door (`:1055`) are the only voicing
>   doors. RED first: the routes are gone (404), the tests tombstoned at D7.0, the
>   preflight/Makefile targets that fed them deleted.
> - [x] `[GATE]` **W7.11 — the kill criterion, measured.** On the W6.12 days re-voiced
>   under the new placement: listening review of segmented vs unsegmented Notre-Dame (the
>   panel, blind); trigger misfires per day (the W7.1 (a) measure after); silence map after;
>   duration error after; interruption behavior after. Segmentation degrading listening →
>   marquee anchors only (the design's remedy).
>
>   **DONE 2026-08-23 (phase7-ledger.md §W7.11). THE KILL CRITERION IS NOT TRIGGERED:** the
>   blind panel (same words, two placements, neither labelled new) chose the chaptered
>   telling **10/11**; the one dissent (Aiko, in rain) is not that it listens worse but that a
>   chapter gated on standing still is lost to someone who never stops — fixed in-session
>   (fix four). Measured after: trigger misfires **11 of 11 stops → 0**; the header duration
>   reader mean error **20.9 s → 0.00 s** (max 73.8 → 0.00) on the same store; the wire's
>   number vs the player itself on the device **max 0.004 s**; a pocketed phone **suspended
>   after 26 s → 111 s unbroken** to the end of the loop. The silence map barely moved
>   (walking 47 → 46 min on one day) because the pieces are SHORT against the gaps — a
>   writing question, carried. **Plan defects 15–18, found by the panel in THIS phase's own
>   code and all fixed in-session with UNDO:** (15) a chaptered stop said its GOODBYE in the
>   story piece — a farewell at hello (11/11); (16) the outdoor anchor circle was sized to the
>   doorstep, not to where people stand to look (11/11; west front 45 → 80 m, east end 40 →
>   55 m, a CLASS guard in tests/test_poi_anchors.py); (17) the anchor cut was applied to the
>   story but not the leg, so an anchored sentence could play while walking toward it;
>   (18) a chapter never heard was invisible off its circle (Aiko) — R4's told-once governs
>   a piece already HEARD, so no ruling was re-opened. Harness defect, owned: one token for
>   a whole batch expired an hour in and two days died on "expired token", recorded as
>   failures that were nothing of the kind — a fresh token per day now.
> - [x] `[GATE]` **W7.12 — DEMO D8, "stand here".** On the simulator with the Notre-Dame
>   segmented walk-through (Théo's and Camille's composed days carry it): the portal segment
>   at the parvis geometry, the door ending the sentence, the nave segment on entry by tap,
>   a simulated call and the sentence-start resume; transcripts and screenshots under
>   `evidence/phase7-audio/demo/`. Heard on a device if the owner can hold one.
>
>   **DONE 2026-08-23 (phase7-ledger.md §W7.12; `evidence/phase7-audio/w712-demo.md`).** Six
>   acts on Camille's day rebuilt on the final code, all correct: the walking line on the
>   leg; Pont Neuf starting 115 m from its pin; the west-front chapter offered at once and
>   auto-playing inside its 80 m circle, no replay on the way back, the goodbye LAST; the
>   Samaritaine door (sentence end → close → keep-listening transcript → nothing inside);
>   a call resuming at the cut sentence's start; the 40-minute line starting the telling at
>   the first standstill. The nave chapter does not appear on this day because no seated
>   beat carried an interior label — the rule cuts only what was told (S7.7's own proof).
> - [x] `[GATE]` **W7.13 — the closing panel, each on their own day**, re-voiced; the W6.12
>   NOs re-asked where the finding was audio's (Rosemary's bench piece, Aiko's arcade
>   silence); the planner findings carried in the block above remain carried — this phase
>   does not absorb them.
>
>   **DONE 2026-08-23 (phase7-ledger.md §W7.13; verdicts under
>   evidence/phase7-audio/verdicts/w713-*.md). Placement on my own day: YES 9 · NOT PROVEN 1
>   (Marcus — his day refuses; the planner's carry) · NO 1 (Paulo — two-thirds the writer's
>   words); silence stance unchanged 11/11. FOUR product defects the panel found were fixed
>   in-session with UNDO (a told chapter replays by tap — R1(c)'s unbuilt half; the door's
>   leave-by clock — Marcus's quoted R3 half; the cap and resume rule moved onto the wire's
>   policy — S7.3's own promise; the A→B finish sentinel silently never stored, so its
>   goodbye could never be voiced — now a real, voiced item, and a wrong POI id fails
>   loudly), plus the two unreviewed footprints (Tuileries 100→300, Samaritaine 20→60,
>   through the pass + sync + deploy) and five corrections to this phase's own evidence.
>   The one carried CLASS the panel kept hitting: THE WRITER'S WORDS vs the geometry they
>   now play in (wrong-compass nav lines, standing sentences on legs, the stop-1 opener at
>   a queued stop, duplicated facts, a mid-line address in a queue) — every instance named
>   in the ledger, all Phase 8 re-seal territory. Plan defects 19 (the sentinel's silent
>   no-op item CREATE — any absent POI id vanished a stop) and 20 (the unreviewed-footprint
>   class: a radius neither default nor reviewed was never looked at) are amended here.**
> - [x] `[GATE]` **W7.14 — close.** The phase's own tests + the whole `tests/` tree once
>   (free tier, §0.7/§0.9.2) + `make lint` + `make dedup-review` + `make test-workbench` +
>   `make flutter-test` + the demo; the cleanup (§0.9.5) and the agent roster closed
>   (§0.9.3); the judge; the commit with explicit paths; the owner's plain-English report;
>   the carry list; re-plan Phase 8.
>
>   **EXECUTED 2026-08-23 (phase7-ledger.md §W7.14): hermetic shard 2584 green; the three
>   free excluded shards run (plan defect 21) with their THIRTEEN reds proven inherited
>   (byte-identical at the parent commit in a judge-approved worktree, or disposed to
>   05-audit-B's OWNER-DECIDES rows) and carried to the Phase 8 re-baseline; workbench 62,
>   flutter 278, lint + analyzer + dedup-review clean; the two phase-touched live audio
>   files 10 green (paid, §0.9.2); demo D8 six-for-six on the final code with its one
>   stated limitation (Act 4's door walked on the stored 20 m, the shipped value is 60);
>   judge PROCEED after two PROVE-FIRSTs; commit `5239839a`, 108 explicit paths; cleanup
>   done; roster closed (three workflow journals, 33/33). NOT called done: the owner has
>   not yet WATCHED D8 (§0.5) — the simulator stays booted. Phase 8's re-plan is next.**

### PHASE 8 — Gates: the rubric starts blocking; persona traces; meet-or-beat. Demo **D9, the blind judging result**.

- **Delivers:** `quality_rubric.score_tour`'s `passed` finally gates serving (§7.2 —
  the standard's own §7 documents that today nothing honours it, and that
  `compose_fixable` must land first so the retry loop cannot burn spend on
  non-convergent blockers); the eleven persona files become replayable
  GPS-and-behaviour traces asserting §7.4's five invariants (no promise silently
  dropped; every drop re-checks the leg cap; protected items never auto-cut;
  announcements never land on walking legs and always carry screen text; every
  prefix decent); the meet-or-beat gate (§7.3) — regenerate the certified reference
  requests, blind side-by-side enjoyment judging through the existing consensus
  machinery, deliberately-diverged sessions included.
- **Demo D9:** the blind judging result, new vs today, with the panel's verdict.
- **Kill criterion — the release gate itself:** losing the blind comparison blocks
  launch. A loss is a finding to fix, not a caveat to ship.
- **Read preconditions:** `quality_certification.py` (2,949 lines),
  `quality_requests.py`, `certification_provider.py`, `quality_rubric.py`,
  `grade.py`, `verify.py`, `provider_text_review.py`.

> **RE-PLANNED AT STEP LEVEL 2026-08-23, after the Phase 7 close (`5239839a`; the owner
> watched D8 the same day — "Demo is fine" — so Phase 7 is DONE under §0.5), on the
> owner's instruction of 2026-08-23: "fold in Phase 7's leftovers and caveats into the
> Phase 8 plan… execute plan." The seven read preconditions were read IN FULL at this
> moment (`quality_certification.py` 2,949 / `quality_requests.py` 509 /
> `certification_provider.py` 198 / `quality_rubric.py` 1,057 / `grade.py` 131 /
> `verify.py` 335 / `provider_text_review.py` 355), plus the quality standard (501),
> the design (642), and audits B (403) and F (426), whole.**
>
> **What the reads established (the facts the steps stand on):**
> (a) The rubric is ADVISORY: `RubricReport.passed` is serialised by `preview_trip` and
> returned 200; the persisted compose path never calls `score_tour`; `compose_fixable`
> has ZERO production callers and 12 exhaustive tests waiting for one (standard §7,
> audit F). (b) The meet-or-beat machinery exists END TO END with no serving caller:
> `certify_quality` = one hash-sealed calibration call (FACT boundary cases + ENJOY
> anchors from the frozen manifests) → primary FACT → primary ENJOY (candidate and
> anchors as NEUTRAL OPAQUE ITEMS) → ONE blind adjudication holding the second slot for
> both axes → server-recomputed decisions; release = aggregate ≥ 7.0 AND no unanimous
> zero axis AND no consensus below-gold axis (`decide_enjoyment_score`;
> `validate_quality_gate_report` replays everything in trusted code). (c)
> `data/certification/tour-batch-v1/` is the CONTROL ARM — audit F: refreshing its
> pinned numbers before the comparison destroys the comparison; the re-seal happens
> deliberately AFTER the gate (C1.0's declared trap, §7.3). (d) The grade dock
> contradiction is real: a failed validation docks 0.10, so a fabricating tour can
> score 0.90 and pass 0.65 — audit F orders the Phase 8 rewrite. (e) Audit B §1.2 is
> the exact five-part golden re-baseline procedure; §1.3 the grade baseline (the
> strictest gate, POI recall weighted 0.40); §1.4 predicted today's reds as the new
> clock's expected consequence; surprise 10: new floors come from a FRESH
> `make golden-probe` measurement of OUTPUT, never from a larger expectation.
>
> **THE FOLDED CARRIES (the owner's 2026-08-23 instruction makes Phase 7's leftovers
> THIS phase's work; each with its source and its step):**
> 1. THE WRITER'S WORDS vs THE GEOMETRY THEY PLAY IN (phase7-ledger W7.13 carry 1,
>    every instance named there) → S8.3.
> 2. The THIRTEEN reds + the golden/grade re-baseline (W7.14; audit B §1.2/§1.3/§1.5;
>    each red proven inherited at parent `2e500468` or disposed to an OWNER-DECIDES
>    row) → W8.6 (+ fixes it spawns) + W8.10.
> 3. Julien's Père-Lachaise wall anchors + the carried anchor list (W7.2 (ii)) → S8.7.
> 4. F&D's lock-screen pause (S7.9 carry) → S8.7; their recorded goodbye-after-chapter
>    dissent → W8.2 re-ask + the owner report (the owner should see that sentence).
> 5. Nested footprints (Vert-Galant inside Pont Neuf), the start square inside stop 1
>    (Place Dauphine), Nadia's 10 m band → S8.7 review rows.
> 6. The silence is a WRITING question — each persona's ask verbatim in W7.11 → W8.2
>    rules on it; S8.3 builds only what they rule.
> 7. Dev graph missing canonical_place_id/aliases/coordinate_provenance/place_plan_id
>    (loader warnings in the shard logs) → S8.7 redeploy.
> 8. D8's Act-4 door walked on the stored 20 m; shipped value 60 — the seam unwalked
>    because the writer's honesty-gate defect blocks Camille's compose (W6.12 carry,
>    verbatim: "two vignette-shaped Pont Neuf beats untraceable") → S8.3 fixes the
>    defect; W8.6 walks the door on a composed day at 60 m.
> 9. NYC export chunks not byte-faithful to the serializer → S8.7.
> 10. Plan defect 21's close-bar amendment stands for phases 1–7; at THIS phase the
>    FULL bar returns (§0.7's own sentence: Phase 8 is the phase whose deliverable IS
>    the gates) → W8.10 runs `make audit`, every shard.
> Plus phase-6 carry 7 (the sealed batch no longer matches the writer's policy hash) →
> S8.9 re-seals, deliberately last. The W6.12 planner day-shape findings the reds
> measure (one-stop days, the lens serving the wrong stops, absurd detours) are
> disposed THROUGH the reds at W8.6 — each disposition names its finding.
>
> **Deviation register for this re-plan (each owner-visible and cheap to overrule):**
> (i) The blind comparison judges the OLD sealed batch tours ("today", the control) and
> the regenerated reference days ("new") as neutral opaque items through the ONE
> `certify_quality` protocol — no bespoke judging lane. (ii) C13 point-first stays WARN
> (W6.10 measured 4/7 clean); the WARN→BLOCKER flip is re-measured at W8.10 and taken
> only if the re-sealed writer clears it on real days. (iii) The §7.2 gate lands on the
> PERSISTED path (compose → 422, nothing persisted — the S5.8 refusal contract
> extended); preview stays 200 + report, the editor's WARN surface (standard §7).
> (iv) Persona traces run OFF-DEVICE (design §11: "persona traces are testable
> off-device") — scripted GPS-and-behaviour streams against the live session endpoints;
> the simulator harness stays the demo surface. (v) The golden re-baseline is executed
> to audit B §1.2 and presented as a DIFF for sign-off (design §8: "re-baselined once,
> with sign-off") — the owner's D9 watch + sign-off closes it. (vi) Meal windows and
> ticket lines stay out (owner rulings 2026-08-19); planner work beyond what the
> thirteen reds demand is NOT smuggled in.
>
> ### Steps (Phase 8)
>
> - [ ] `[DEMOLISH]` **D8.0 — the rows tagged for this phase, and Phase 7's stragglers.**
>   Delete: `test_every_investigation_added_document_is_included_or_explicitly_excluded`
>   (audit F: repository archaeology, DELETE at Phase 8 when §7.3 re-seals the manifest;
>   its supersession sibling keeps-or-drops with it) and, IF still present, the two
>   DELETE-AT-PHASE-7 C8 rows audit F names (`test_c8_cannot_fire_on_engine_output…`,
>   `test_c8_contradicts_the_human_reference_at_declared_stop_granularity`).
>   Coupling check first (§0.9.1 — graphify + whole reads, never grep). Survivor: the
>   rubric suite still collects; `make lint` clean.
> - [ ] `[GATE]` **W8.1 — measurement first (§10.9).** (a) The full-bar before-picture:
>   hermetic shard + the three excluded shards + workbench + flutter on THIS tree — the
>   thirteen reds re-confirmed byte-for-byte; (b) the gating gap proven live: a day
>   carrying a rubric BLOCKER composes and PERSISTS today (pasted); (c) the control arm
>   re-scored untouched (the 8 audio-minutes intact); (d) the trace-harness inventory
>   (what W5.12's scripted-stream runner and W7.12's demo runner already give S8.5);
>   (e) the meet-or-beat spend counted and stated in one clause; (f) Camille's compose
>   refusal reproduced with the server log naming the untraceable sentences (S8.3's RED).
> - [ ] `[GATE]` **W8.2 — THE EARLY PANEL (all eleven, workflow runner §0.9.3), before
>   any writing or gating code.** On W8.1's numbers and their own final W7.11 days:
>   (1) the writer's-words rules, per carried instance class (compass lines, standing
>   sentences on legs, the stop-1 cold-open at a queued stop, duplicated facts, a
>   moving sentence in a priced line, split-as-one paragraphs, directions inside
>   extra_narration, pin-written openings at edge starts); (2) the silence asks (W7.11
>   verbatim) — what, if anything, fills long quiets; (3) the deliberately-diverged
>   session set §7.3/§7.4 judges; (4) the refusal UX — what a gated day tells the
>   editor and the phone; (5) F&D's goodbye dissent re-asked. Locked rulings BIND
>   S8.3–S8.5.
> - [ ] `[BUILD]` **S8.3 — the writer's words match the geometry they play in (carry 1
>   + carry 8's blocker).** **Files:** `src/tour/authoring.py` (the prompts learn
>   placement per W8.2's rules), `src/tour/validation.py` / `verify.py` (each rule gets
>   a floor check in the existing gate genre — never a bare prompt), and the Camille
>   class: untraceable writer-bridge/vignette sentences (mangled beat ids, uncited
>   glue) refuse at AUTHORING time with the bounded retry, so her day composes
>   deterministically. POLICY HASH MOVES (declared; S8.9 re-seals). **Read
>   preconditions:** `authoring.py`, `generation.py`, `validation.py` end to end at
>   execution. RED: W8.1(f)'s exact refusal → GREEN: three clean composes; plus
>   per-rule hermetic REDs. UNDO per rule.
> - [ ] `[BUILD]` **S8.4 — §7.2: `passed` gates serving; `compose_fixable` gets its
>   caller.** **Files:** `src/api/routes/trips.py` (compose runs `score_tour` after
>   composition; BLOCKERs → the 422 refusal contract, trip untouched; `compose_fixable`
>   + `StopMaterial` authorize at most ONE targeted per-stop recompose before the
>   refusal), and the quality standard's §7 gains its dated closure. [PLAN DEFECT 22,
>   amended 2026-08-23: this step originally also named `src/api/dependencies.py`
>   ("its nothing-honours-this comment dies") — that comment no longer exists in the
>   file; the standard §7 was the claim's surviving carrier.]
>   The caller-side test audit F ordered — beside `test_passed_is_false…`, never an
>   edit of it. **Read precondition:** the compose+preview regions of
>   `routes/trips.py` end to end. RED: a blocker-carrying day persists today → GREEN:
>   422 + untouched trip + one bounded recompose on a fixable finding.
> - [ ] `[BUILD]` **S8.4b — the grade hard-zero (audit F's ordered rewrite).**
>   **File:** `src/tour/grade.py` — a failed validation FAILS the grade (passed=False),
>   never a 0.10 dock. The weight test re-derived as a written decision citing D§7.2.
> - [ ] `[BUILD]` **S8.5 — §7.4: the eleven days become replayable traces.** **New:**
>   `tests/test_persona_traces.py` + the trace runner (Extends: W5.12's scripted
>   position-stream mechanism — named precisely at execution after reading it). Each
>   persona file's minute-by-minute day becomes a GPS-and-behaviour trace through the
>   LIVE session endpoints, asserting the five §7.4 invariants with citations: no
>   promise silently dropped (fuzzed across replans); every drop re-checks the leg cap;
>   protected items never auto-cut; announcements never on walking legs and always with
>   screen text; every prefix decent (wrap-up at any minute ends with a close).
>   Free-tier per §0.9.2 (one compose per trace; recorded where a paid call is
>   unavoidable).
>
>   **PLAN DEFECT 23, found at execution 2026-08-24 (§0.2 — logged, amended, then
>   continued).** This step assumed all eleven days can be TRACED at the free tier.
>   Measured on this tree before a line of assertion was written
>   (`evidence/phase8-gates/s85-before-picture.md`): **three serve — camille (5
>   stops), greta (3), rosemary (1) — and eight are refused by name.** Seven die at
>   S8.3's placement floors, and every hit is on a **BEAT sentence** — corpus text
>   the offline lane echoed verbatim; SIX named beats account for all seven days
>   (`fea8ae55…` "built this arcade", `4cfc4c1b…` "step into Café Ma Bourgogne",
>   `c8d646d7…` "began here", `a82b2c66…` "then follow this itinerary",
>   `5f32896b…` "Walk through the arcade", `1024a10b…` "as you enter"). The
>   floors judge the WRITER's output; `OfflinePremiumExecutor` emits the writer's
>   INPUT, and the stitch was never written to W8.2's rulings. The eighth,
>   marcus, dies at the C3 audio floor (3.0 min of audio across 110 min of
>   walking, floor 13.2) — the W8.1(b) class, on the day whose own file says
>   walking IS the product. **AMENDED:** the traces assert §7.4's five invariants
>   over the days that SERVE, with the served count a MEASURED floor and every
>   refusal pinned by name (a day that stops serving fails); the eleven-day trace
>   with a writer in the seat is W8.11's material (the closing panel runs the real
>   writer); and two rows go to W8.6 — the six corpus beats, and Rosemary's day,
>   which cannot today be both served (C3 needs her "more talking" dial) and
>   shaped like her persona (with the dial the Orsay alone prices 100 minutes and
>   her bench and Orangerie are gone).
> - [x] `[GATE]` **W8.6 — the thirteen reds, disposed for real.** GOLDEN + GRADE: the
>   audit-B §1.2 five-part re-baseline off a FRESH `make golden-probe` /
>   `make golden-diff` measurement of the FINAL engine (floors from output, never from
>   expectations; §1.3's grade baseline and the two in-body centrepiece pins re-checked;
>   the contour-clamp reader re-checked; `test_broken_golden_drops_below_baseline`
>   re-run) — prepared as the SIGN-OFF DIFF. INVARIANTS: per-case disposition — a
>   planner day-shape FIX with RED→GREEN, or a fixture re-derived from the design with
>   its written reason — for the named cases: three Paris INV8 detours + one NYC; the
>   two CertificationPlanningInfeasible; the two no-silent-empty-tour; the
>   15022-vs-15000 ceiling case (checked FIRST for a surviving 0.9 fill-band in the
>   certification lane — §8.3 deleted that idea). Each disposition names its W6.12
>   finding. Also here: the D8 Act-4 door walked on a COMPOSED day at Samaritaine 60 m
>   (carry 8; one act of the demo runner).
>
>   **EXECUTED AND CLOSED 2026-08-24 (phase8-ledger.md §W8.6).** The eleven-persona panel ran first (11/11, verdicts under
>   `evidence/phase8-gates/verdicts/w86-*.md`) and its rulings bound the work: R1 a
>   day is worth its PLACES, never its pavement; R2 the walking-worth line is the
>   product's own 2.0x detour gate plus its 1800 s ceiling; R4 "over the ceiling"
>   means materially over; R5 the half line stands; R7 **the C3 floor is NOT bent —
>   Marcus refused the exemption offered in his name** ("voice the legs or refuse
>   honestly"), and Rosemary's alternative bend is blocked by her own ruling against
>   the day-rebuilding dial, so both days stay carried with named remedies.
>   **Nine of the thirteen reds fixed or disposed**, each with RED→GREEN→UNDO or a
>   written §0.1.3 decision: four planner mechanisms landed in `selection.py` (the
>   under-fill choice now ranks by the day's STORY VALUE; ONE `stop_earns_its_walk`
>   predicate at all three add sites, including the ordinary fill arm that had no
>   worth line at all; the materiality tolerance on the final ceiling; and the
>   INV8 gate re-derived into the same currency it judges). `_test-invariants` went
>   **7 failed → 13 passed**. The Samaritaine door was walked at $0 on a genuinely
>   composed day at the shipped 60 m, with what it does NOT show stated plainly.
>   **The four remaining reds are the golden/grade re-baseline, prepared as the
>   sign-off diff at `evidence/phase8-gates/w86-golden-rebaseline-proposal.md` —
>   NOTHING written into a fixture or threshold, per deviation (v).**
>
>   **PLAN DEFECT 24, logged and amended here (§0.2).** This step's text assumed the
>   thirteen reds decompose into "a planner fix or a fixture re-derivation". A third
>   kind was measured and is now on the record: **a GATE that measures the wrong
>   quantity.** INV8 priced a LOOP's window against the short direct line between its
>   own near-adjacent flanks and ignored what the window earns, so it flagged a day
>   whose every stop clears the panel's worth line at 0.05–0.62 against a cap of 2.0
>   (69 min walking / 130 min standing — the persona-typical shape). Its own comment
>   had already named the limitation and invited re-derivation on fresh evidence. The
>   discipline that keeps this from becoming "move the gate until it passes": the
>   check must still catch the defect it was built for (both synthetic true-positive
>   fixtures stay green), and the change carries its own UNDO.
>
>   **THE OWNER SIGNED 2026-08-24 AND THE RE-BASELINE IS APPLIED.** Asked as one
>   plain yes/no, answered "leave the list at 8": hunks 2–7 land, **hunk 1
>   (`expected_pois`) is HELD**. Four files changed, `GRADE_BASELINE` and both
>   centrepiece pins byte-untouched. **`_test-golden` went 2 failed/7 passed → 0
>   failed/9 passed at exit 0** — both overlap reds GREEN by measurement (Île 6 vs a
>   floor of 5, PdV 3 vs 3). `_test-grade` stays 2 failed/14 passed: the Île grade case
>   and its undo twin, carried as named documented reds, which is the signed
>   consequence. Evidence: `w86-evidence-matrix.md` §7.
>
>   **PLAN DEFECT 26, logged and amended here (§0.2). A GATE THAT GRADES OUTPUT THE
>   PRODUCT DOES NOT SHIP.** `tests/test_tour_grade.py::_live_graded` builds its beat
>   plan with `select_poi_beats` — raw, uncapped — while the two golden modules build
>   theirs with `build_poi_beat_plans_capped`, the SHIPPED path, and say why in a
>   comment at the site. Measured with one variable moved: on the Île day the grade
>   harness scores 23 beats (14/17, 0.647) where the product emits 9 (6/17, 0.506).
>   This is the never-build-it-twice class inside a release gate. NOT changed at W8.6:
>   plan defect 24's own discipline requires a gate change to be proven against a green
>   true-positive guard, and this gate's guard
>   (`test_broken_golden_drops_below_baseline`) is red on its own precondition. Unblock:
>   the Île grade case going green. Measured collateral of the correction: Île 0.647 →
>   0.506 (deeper red), PdV 0.857 → 0.743 (still PASS) — no green test goes red.
>   Carried to W8.10.
>
>   **PLAN DEFECT 27, logged, amended and FIXED here (§0.2). THE MEASUREMENT TOOL
>   DECISION D6 DEPENDS ON WAS BROKEN.** `make golden-probe` — which D6 names as the
>   source of every re-derived overlap floor — exited 2 on every run, green goldens
>   included. Its recipe runs pytest `-q -s`, so the progress dots share a line with the
>   test's print, and the filter was start-anchored after an `lstrip()` that strips
>   whitespace and not dots. The in-test guard proves the tests PRINT the marker;
>   nothing tested the Makefile's reader of it. Fixed in the recipe (match the marker
>   anywhere, emit from the marker onward), reason written at the site, proven at exit 0.
>
>   **PLAN DEFECT 25, logged and amended here (§0.2).** This step's text says the
>   NYC cases are "a fixture re-derived from the design". Measured, no duration
>   works: the reach envelope scales WITH the request, so a shorter ask searches a
>   smaller circle and builds proportionally less (43.3% of a 60-minute ask against
>   49.3% of a 150-minute one). Both New York starts are structurally under the half
>   line on the deferred OLD corpus at every duration the product offers. The
>   disposition is therefore neither a fix nor a re-derived duration but a
>   **replaced claim**: they assert the honest refusal they actually produce, under a
>   test that FAILS the moment the corpus upload makes either day buildable.
> - [ ] `[BUILD]` **S8.7 — the small carried estate.** F&D's lock-screen pause control
>   (`mobile/lib/services/audio_service.dart`, the AudioSession remote-command
>   surface); ~~the dev-graph redeploy so the four missing fields land and the loader
>   warnings die (PARITY OK pasted)~~ **[STRUCK — see PLAN DEFECT 28]**; NYC export
>   chunks byte-faithful to the serializer (test extended); the pin/footprint review
>   rows written through the reviewed table with a basis each (nested Vert-Galant,
>   Place Dauphine start-square, Nadia's band, Julien's wall anchors).
>
>   **PLAN DEFECT 28, logged and amended here (§0.2). THE REMEDY THIS STEP NAMES FOR
>   CARRY 7 CANNOT WORK, AND ITS ACCEPTANCE CRITERION CANNOT SEE THAT.** The step says
>   a dev-graph redeploy makes `canonical_place_id` / `aliases` /
>   `coordinate_provenance` / `place_plan_id` "land". Measured 2026-08-24: **nothing
>   writes those four keys.** No file under `scripts/` mentions any of them; 0 of 370
>   Paris POIs and 0 of 402 New York POIs carry any; 0 of 1,562 and 0 of 2,005 beats
>   carry `place_plan_id`. `src/tour/selection.py:749,751,752,787` READS them and no
>   producer exists. A deploy would print `✓ DEPLOY COMPLETE ... parity clean` and the
>   four warnings would fire again on the next load — and `scripts/db_parity.py:186-195`
>   compares four SETS and is structurally blind to property presence, so the step's own
>   "PARITY OK pasted" criterion would certify a carry that is still open.
>
>   **Judge ruling 2026-08-24: STOP**, with a second reason the consult under-described:
>   `scripts/upload_paris.py:249-278` re-SETs 25 planner-read POI properties (`SET x =
>   null` REMOVES, per its own comment at `:186-191`) and `:493` sets
>   `beat.active_status='active'` unconditionally against a loader that filters on it
>   (`selection.py:781`) — a live path to moving the overlap counts the owner signed
>   hours earlier. **Sequencing ruled: after W8.10's full bar, never before**, so a red
>   golden stays attributable to code rather than to a graph that changed underneath it.
>
>   **AMENDED:** carry 7 is re-opened as an undecided question, not a scheduled deploy.
>   It is either **(a)** a corpus gap — a producer that was never built, in which case
>   `poi-raw.json` and BOTH property lists in `upload_paris.py` gain the fields first and
>   the deploy is downstream of a data change — or **(b)** optional-by-design forward
>   fields, in which case the fix is loader-side and touches no graph. The sharpest test
>   is `selection.py:4018-4020` / `:4197-4199`, where `canonical_place_id` gates a
>   de-duplication that can never fire while the field is always None. Settled on
>   evidence before anything is built; recorded in `phase8-ledger.md` §S8.7. Suppressing
>   the warning is not an option under the error-ownership rule.
>
>   **SETTLED 2026-08-24: it is (a), A CORPUS GAP — and it hides a live tour defect.**
>   The producer was never planned, never built and never deferred with a reason: the
>   only statement of intent in the repo is a code comment (`selection.py:1209`, "D2 will
>   persist this canonical JSON shape") and **no `specs/` document defines that D2**.
>   `materialize_corpus_snapshot` — the sole consumer — is unreachable in production, its
>   manifest always `None` (`selection.py:842-844`, `:981`; all four corpus entry points
>   at `routes/trips.py:617,943,1993,2314`). **The consequence, measured on both
>   corpora:** the co-located demotion pass has a brake (`selection.py:4017-4022`, "only
>   equal IDs may collapse") that can never engage, so it folds distinct famous places
>   into one stop — the New York Stock Exchange into Wall Street (identical coordinates,
>   both tier 5), Radio City Music Hall into Rockefeller Center, the Stonewall Inn into
>   Greenwich Village, Sainte-Chapelle into the Conciergerie — while correctly folding
>   Musée Victor Hugo into Place des Vosges and the Flatiron Building into its district.
>   The pass is right on some pairs and wrong on others and the missing field is exactly
>   what tells them apart.
>
>   **NEW PLAN STEP PROPOSED, NOT SLOTTED — an owner call because it is scope and spend.**
>   The remedy is one reviewed `canonical_place_id` pass in the established
>   `scripts/poi_*.py` shape (~772 POIs across two cities, plus the field in BOTH property
>   lists in `upload_paris.py`). **It is deliberately NOT built inside Phase 8**, on the
>   same ground the judge used for the graph: it changes tour OUTPUT, and W8.8's blind
>   meet-or-beat is about to judge that output against a frozen control arm, so landing it
>   now would move the thing being compared and make a loss unattributable. It also
>   reshapes what a tourist experiences, which goes through the eleven-persona panel
>   BEFORE it is decided. No alarm test is added here either: it would be red with no
>   owning step to turn it green, and §0.3 forbids closing a phase on outstanding declared
>   breakage. Carried, named, with its measurement, to the owner report.
> - [ ] `[GATE]` **W8.8 — THE MEET-OR-BEAT (§7.3); D9's material.** Regenerate the
>   certified reference REQUESTS through the app path on the final engine; judge OLD
>   (the frozen batch — the control) vs NEW (the regenerated days) BLIND through the
>   one `certify_quality` protocol; the deliberately-diverged sessions W8.2 ruled for
>   are candidates too (§7.4.5). The verdict table assembled per request with the
>   panel's reading. **Losing blocks launch:** a loss loops back to the responsible
>   step as a finding to fix — never shipped as a caveat.
> - [ ] `[DATA]` **S8.9 — the re-seal, deliberately LAST (§7.3; C1.0's trap closed).**
>   `data/certification/tour-batch-v1/` re-sealed: the new reference batch under the
>   CURRENT policy sha and the moved request_sha256s; the corpus-pinned rubric rows
>   re-derived on the new batch as written decisions (the 8 audio-minutes row becomes
>   the NEW control); recorded beside D8.0's manifest-archaeology deletion.
> - [ ] `[GATE]` **W8.10 — THE FULL BAR RETURNS (§0.7 — only here).** `make audit`:
>   every shard, 0 failures, 0 skips — plus `make test-workbench`, `make flutter-test`,
>   `make lint`, `make dedup-review`. The C13 WARN→BLOCKER decision re-measured and
>   taken only on evidence. Numbers in the ledger.
> - [ ] `[GATE]` **W8.11 — the closing panel.** All eleven on their own final days
>   re-run on the gated engine + the D9 verdict table; the standing dissents re-asked;
>   dissents by name.
> - [ ] `[GATE]` **W8.12 — close.** DEMO D9 (the blind judging result, new vs today,
>   with the panel's verdict) presented with the golden re-baseline diff for sign-off;
>   the judge; commit explicit paths; the owner report (one line per owner act: the D9
>   watch, the re-baseline sign-off, F&D's goodbye sentence); amend-and-carry this
>   plan.

---

## 5. Risks, and the self-review

### Risks (with the design §11 rows this plan adds to)

| Risk | Where this plan meets it |
|---|---|
| **A phase drifts back into nursing the old suite** — the failure that killed Phase 0 | §0.1.5: a green existing suite is never a deliverable, never an acceptance criterion, never a demo. A phase closes on its own demo and the tests it WROTE. An inherited test either earns a citation or is deleted |
| Inherited tests block a deletion the design orders | Found already: one guard asserts the three-route primitives must stay live and fails with "has gone dead". Each phase's first act is to delete the tests that stand in front of its own deliverable (§0.1.2), before writing anything |
| The golden fixtures pin the planner to the pre-redesign clock | They are inherited tests like any other. Whichever phase first moves the planner past them deletes or re-derives them from the design, with the owner shown what changed — not a phase of its own |
| ~~`density.py` (unread) turns out to be load-bearing for Phase 2 body stops or pace~~ RESOLVED at the Phase 2 re-plan (2026-08-07): read end to end; body-role nodes are structurally invisible to the gate (no change needed) and pace MUST thread into `assess`'s envelope (S2.4 names the site) | The re-plan's ledger addendum in §3 records the evidence |
| A second replan brain grows in the app (the §11 headline risk) | Phase 5's two source-scanning seams + §4.6's selects-never-decides structure; `make dedup-review` at every phase close |
| Enriched AI data confidently wrong (6.1/6.4) | Basis sentence per value, structural tests, session-flag corrections from Phase 3 on; 6.4 sampled hardest (W2.9); the D1 kill criterion measures 6.1 coverage before anything plans on it |
| The plan itself goes stale as phases land | Each phase close ends with "amend-and-carry this plan": re-hash §1's ledger, mark the phase done, re-plan the next phase at step level |
| Commit hygiene against the owner's ~172 uncommitted files | Explicit path lists only; `git status` checked after staging; §0.6 forbids every tree-resetting command |

### Self-review (performed against the brief and the skill checklist before delivery)

1. **Spec coverage.** Every §9 phase row from 1 onward has a section with its named demo
   and kill criterion; the three failure classes each have a structural counter (§0.1
   test policy; §0.2 read ledger + plan-defect rule; §0.3 declared breakage + budgets +
   demos). The 8.1/8.2/8.4/8.5 deletions are each assigned to their phase with
   same-phase tombstones. §10.8's four named seams are each assigned a source-scanning
   test (promise pricing → P3, replan brain + session clock → P5, audio placement → P7).
2. **Placeholder scan.** Phases 3–8 are coarse **by the design's own instruction**,
   stated at the top of §4. No "TBD" otherwise; every Phase 1–2 step names its file, its
   command, and its citation.
3. **Consistency.** Field and function names in steps were checked against the read
   files (`_hits`, `LOAD_PARIS_POIS_CYPHER`, `_snapshot_from_records`,
   `route_planning_budget`, `path_leg_seconds`, `POI_ROLE_MULTIPLIER`,
   `_materialize_fixed_end_b`, `build_route_option`) — all exist at the recorded
   hashes. Two corrections this plan makes to its inputs are stated in place: the
   design §9 table's "(a) currently ON" is wrong (code: OFF), and the state doc's §5
   citation list over-included the two tombstone folders.
4. **Deviation register** (decisions this plan makes that the design left open, each
   with its reason): forecast fetch moved P1→P3 (§10.7 vertical slices); 6.7's
   consumer lands P3 while its data lands P1 (design's own row split); the D1 kill
   threshold set at 90 % of reviewer-marked gated POIs; end-hardness `wall` planning
   ceiling set at 0.95 nominal (Marcus's visible-slack request) — each is owner-visible
   here and cheap to overrule.
