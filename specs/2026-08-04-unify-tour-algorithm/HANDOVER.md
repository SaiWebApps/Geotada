# Unify tour algorithm — handover

**Status: hard stop called 2026-08-05 09:35.** The unification is done and proven. Four
defects were uncovered; three are fixed and verified, one is open with an executable contract.

**Nothing is committed.** Every change is in the working tree, so all of it is easy to undo.

**Known failing tests: 1** (down from 12 at the last full-suite run, and from 87 at the peak).
That one is `test_fixed_destination_greedy_is_capped_by_the_walk_budget_not_the_total_ceiling`
— a proving test deliberately left RED, which is the contract for Error 1 below.

`make lint`: **All checks passed.** `node .claude/team-engine.test.js`: **91/91.**
No untracked scaffolding; every probe from every lane deleted.

---

## Part 1 — What was accomplished

### The goal, and whether it was met

The phone app and the editorial workbench each built tours from their own copy of the
logic. They agreed by accident, not by construction. The goal was one engine, proven.

**Met.** Measured by static call-graph reachability from each surface's entry point:

| | before | after |
| --- | --- | --- |
| functions both surfaces reach | 189 | **257** |
| reachable only by the phone | 10 | **6** |
| reachable only by the workbench | 65 | **13** |

Divergence fell from 75 functions to 19, and **none of the remaining 19 is tour-building
logic** — six are trip-saving and "keep exploring" extras, thirteen are quality scoring and
the degradation report the workbench shows an editor. Route planning, ordering, stop
selection and script writing are entirely shared.

Reproduce: `python3 scratchpad/callgraph_snapshot.py` (script preserved in the session
scratchpad; it is a diagnostic, not part of the product).

### The proof

Five tests, permanent in the suite, each demonstrated failing before passing, with failures
staged the way a real regression would occur.

| Test | File | What it catches |
| --- | --- | --- |
| `test_the_phone_and_the_workbench_name_one_planner_and_one_author` | `tests/test_workbench_matches_the_app.py` | A second copy of the planner, even byte-identical. Compares object identity, not text. |
| `test_breaking_the_one_planner_breaks_both_surfaces` | same | Sabotage the shared planner; both surfaces must break, each having gone through it exactly once. |
| `test_breaking_the_one_author_seam_breaks_both_surfaces` | same | Same, for the part that writes the words. |
| `test_both_surfaces_plan_the_identical_tour` | same | Same request to both surfaces must give the same places, order and quoted time. |
| `test_one_planner_produces_the_options_and_one_interleave_builds_them` | `tests/test_tour_one_engine.py` | More than one function anywhere deciding which routes to offer, or assembling the stop list. Catches copies that disguise themselves with renamed imports. |

Verified independently by the orchestrator, not just by the builder:
`tests/test_workbench_matches_the_app.py` **19 passed**;
`tests/test_tour_one_engine.py` **11 passed**.

**Why it is proof rather than green tests:** a test that only reads code can be fooled by a
copy; a test that only compares outputs can be fooled by two implementations that agree
today. This removes the shared thing and requires everything claiming to depend on it to
collapse.

**What it does NOT cover, stated plainly:**
- The Dart and JavaScript halves are not executed. The five tests prove the four Python
  handlers converge. What connects the phone and the workbench page to those handlers is the
  address each posts to — verified by reading source (`mobile/lib/services/trip_service.dart:61`
  and `:182`; `frontend/review.html`), not by running it. The browser half belongs to the
  Playwright shard.
- Live content and the live walking-route service are stood in for. Deliberate: it makes
  "both surfaces produced the same tour" a statement about the code rather than about whether
  the corpus moved between two requests. A fault appearing only on real Paris data is outside
  their reach. This limitation is written into the test file itself.

### The ledger

All 17 remaining steps built and individually proven with a red-before/green-after and a
mutation test. Steps 1-3 were already committed before this run.

| Step | What landed |
| --- | --- |
| 4 | Second authoring seam deleted (−297 lines) |
| 5 | Stop ceilings removed; cheapest-insertion ordering fallback built from scratch |
| 5.5 | Authoring-side and quality-scorer ceilings removed |
| 6 | Legacy flat walk budget deleted, not deprecated; q3 refusal made structured |
| 6.5 | Saved-tour scorer re-pointed at the new ceiling |
| 7 | Planning returns three options and makes no paid AI call |
| 8 | Fourth copy of the stop-builder deleted; one shared builder |
| 9 | Phone plans through the shared block |
| 10 | Preview is plan-only and free |
| 11 | Separate build endpoint writes exactly the route picked |
| 12 | Workbench two-step pick-then-build with three option cards |
| 13 | Duplicate standalone preview page deleted with its dead route |
| 14 | Estimated walking times become a labelled warning, not a refusal |
| 15 | That warning reaches the API responses |
| 16 | And the phone screen |
| 17 | Preview audio character cap deleted |
| 18 | Stop audio gains a content hash so edited narration re-voices |

### The user-facing defect this fixed

The phone planned tours on an old, shrunken budget while the workbench used the correct one
— **about 20% less walking and audio for the identical request**. A tourist asking for 60
minutes got roughly 50, while the workbench showed the full 60.

### Defects uncovered along the way

| # | Defect | Status |
| --- | --- | --- |
| 1 | The repair pass could add or swap a stop but never **drop** one, so an over-long route had no way back into range | Fixed |
| 2 | The repair would take a route already in range and replace it with one walking further | Fixed (symptom); root cause below |
| 3 | The planner **certified one route and built a different, longer one** — it priced routes without the destination pinned, then shipped them pinned. This had collapsed three-routes-to-choose-from down to one | Fixed; live Paris flagship 1 → 3 options |
| 4 | Fixed-destination tours: the cap on **walking** was set to the ceiling for **total** tour time | *(status at hard stop)* |

Golden reference tours did **not** move: 9 of 9 pass, plus 15 of 15 grade checks.

---

## Part 2 — Remaining errors, with hard contracts

### ERROR 1 — Fixed-destination (A-to-B) tours are refused. A units error.

**Status at hard stop: OPEN — but the contract is already executable in your tree.**

A fix lane was dispatched and killed at the hard stop. It had done the right thing in the
right order: **written the proving test and got it RED**, then was stopped before writing the
fix. So the contract below is not prose you have to interpret — it is a failing test with a
name that states the requirement:

```
tests/test_tour_certification_selection.py::
    test_fixed_destination_greedy_is_capped_by_the_walk_budget_not_the_total_ceiling
```
Current state: **1 failed, 14 passed** in that file. `make lint` clean.

That test pins the correct number: at 90 minutes the walking allowance is **2160 s**, and the
broken line hands the greedy **6000 s**. It measures UNITS — it captures the stop set the
greedy hands to the fill pass and prices the walking that implies — rather than asserting a
magic total, which is the right shape for a units bug.

**Make that test green without weakening it, and Error 1 is fixed.**

**Symptom.** Every A-to-B request refuses with
`CertificationPlanningInfeasibleError: ... required 4860-5940s, best eligible bounded route 7267s`.
Failing test: `tests/test_trip_api.py::TestTripGenerateFixedDestination::test_ab_request_route_ends_at_b`.

**Evidence, all measured on the live Paris dev graph at 90 minutes (band 4860-5940 s):**

| | stops | walk | narration | total | in band |
| --- | --- | --- | --- | --- | --- |
| open route, no fixed end | 9 | 3452 s | 1921 s | **5373 s** | yes |
| fixed end to that route's OWN last stop | 15 | 5258 s | 2579 s | **7837 s** | no |
| the open route's 9 stops, priced WITH the destination pinned last | 9 | 3452 s | 1921 s | **5373 s** | **yes** |

The third row is decisive: **pinning the destination costs nothing.** A valid in-band A-to-B
route exists and the engine already knows it.

The fixed-end stop set is a strict SUPERSET of the open one — all nine plus six bolted on
(La Samaritaine, Saint-Germain-l'Auxerrois, Tour Saint-Jacques, Théâtre de la Ville,
Square Jean XXIII, BHV), costing 1806 extra seconds of walking. Nothing is dropped or swapped.

**The killer number:** a 90-minute walk asked to end **27 metres from its start** (Pont Neuf)
seats 15 stops and 5787 s of walking, then refuses its own answer. Not destination-specific:
Notre-Dame 7028 s, Conciergerie 6850 s, Hotel de Ville 7267 s — all refuse.

**Root cause, three linked facts, each verified:**

1. `src/tour/selection.py:1454` now reads `certification_fixed_end = input.end is not None`.
   It previously read `input.end is not None and not planning_policy.is_legacy`, **and the
   default policy WAS legacy**, so ordinary A-to-B requests took the other branch everywhere
   this flag is consulted. Deleting the legacy policy silently moved every A-to-B request onto
   a branch only certification callers had reached.
2. **`src/tour/selection.py:1742` — `greedy_walk_budget = certification_total_ceiling`. THE
   PRIMARY BUG, and a units error on its face.** That ceiling bounds TOTAL ACTIVE TIME
   (walking + narration) = 6000 s at 90 minutes, and it is used as a cap on WALKING ALONE. The
   greedy may therefore spend 100 minutes walking to build a 90-minute tour before one second
   of narration is counted, so anything near the cap breaches the ceiling by construction. The
   open path caps the same quantity at `walk_budget * 0.75` = 1620 s.
3. `src/tour/selection.py:1548` derives the reach radius from that same total-time ceiling,
   giving 3704 m instead of the 1333 m walk envelope — hence a 95-POI candidate pool on the
   fixed path against 47 on the open one.

Amplifier (do NOT change it): `selection.py:1790` credits each stop the true 270 s on the
fixed path, so the greedy seats ~12 stops before believing the narration target is met and the
6000 s cap never stops it. The open path credits up to 1080 s — the known, deliberately
unfixed over-credit — so it stops at ~3 and lets the repair top up.

#### HARD CONTRACT — what "fixed" means

**Change:** make the walking cap a WALK budget, not a total-active-time ceiling, and derive the
reach radius from the walk envelope rather than the total-time ceiling. Fix the units at
source; do not re-introduce a caller-type flag unless a caller genuinely needs the wider reach
(check the frozen batch runner before deciding).

**Must NOT do:** widen the band; re-introduce any stop ceiling; change
`MAX_DWELL_AUDIO_SECONDS`; alter the 270-vs-1080 narration credit; weaken any assertion.

**Acceptance, all four required:**

1. A 90-minute A-to-B request to the open route's own last stop returns a route **in band**.
   Report stops / walk / narration / total. Expected shape: 9 stops, ~3452 s walk, ~1921 s
   narration, ~5373 s total.
2. The 27-metres-away case (Pont Neuf as destination) returns a route in band, not a refusal.
3. **The open path is byte-identical.** `tests/test_tour_golden_*.py` — all 9 golden tours
   pass unchanged, and the grade shard stays 15 of 15.
4. `make test-file FILE="tests/test_trip_api.py::TestTripGenerateFixedDestination" TEST_PROFILE=test2`
   passes.

**Proving test:** in `tests/test_tour_certification_selection.py` (free file, thematically
right). RED before, GREEN after, then MUTATION — revert the fix, confirm RED, restore, confirm
GREEN. All four pasted.

**KNOWN TRAP, handle explicitly.** `test_ab_request_route_ends_at_b` also asserts the API's
stop order equals a bare `select_route` call, while the API plans through
`plan_premium_authoring`/`plan_premium_options`. The diagnosis proved only that the REFUSAL is
wrong. It did NOT prove that equality assertion passes once the refusal is gone. If it still
fails for that second reason, that is a SEPARATE question — do not weaken the assertion to get
green; report it.

---

### ERROR 2 — The test suite is roughly ten times slower. Not a test bug.

**Status:** OPEN. No fix attempted; it needs a product decision first.

**Measured:**

| | before | after |
| --- | --- | --- |
| full Python shard | ~15 min (899 s) | **1 h 48 min (6509 s)** |
| `tests/test_trip_api.py` alone, idle machine | — | **33 min 53 s** |
| `tests/test_tour_flavours.py` | < 2 s | ~4 min 30 s |
| `tests/test_tour_b_materialization.py` | < 1 s | ~1 min |

**Cause.** Two changes compound. Stop ceilings were removed by owner ruling, so routes seat
more stops and the ordering and repair passes price much larger candidate sets. Separately,
test fixtures had to be enriched to fill a real hour under the two-sided budget, which enlarges
every planning test's corpus.

**A consequence already fixed, recorded so it is not rediscovered:** the slowdown made
`tests/test_trip_api.py` outlive its own auth token. `ACCESS_TOKEN_EXPIRE_MINUTES` is 60
(`src/api/auth/config.py:121`) and that module's `client` fixture minted ONE token at module
setup. Later tests got `401 Invalid or expired token` while asserting 422 — 3 failures and 11
fixture errors, none of them a product fault. Fixed by minting a fresh bearer per request via
an httpx request event hook. **Any other module-scoped authenticated fixture has the same
latent bug.**

#### HARD CONTRACT — what "fixed" would mean

**The most likely single lever is ERROR 3 below**, because fewer bogus stops means smaller
candidate sets. Try that first and re-measure before optimising anything else.

**Acceptance:** the full Python shard returns under 30 minutes, with zero tests deleted,
skipped, or deselected to achieve it, and no fixture made thinner than the two-sided band
requires. Report the before and after for all four rows above.

---

### ERROR 3 — The planner over-credits narration and buys the shortfall in walking

**Status:** OPEN BY DECISION. This is the owner's call, not a defect to fix unilaterally,
because it changes the shape of every tour.

**Mechanism.** Deciding whether to seat another stop, the planner credits that stop with up to
the PER-TOUR narration allowance (720 s at 60 minutes, 1440 s at 120). When the tour is spoken,
every stop is capped at `MAX_DWELL_AUDIO_SECONDS` = 270 s. A rich place is booked at up to
**five times** what a tourist will hear. The planner believes the listening budget is full after
about a third of the stops and stops adding. The tour lands short, and the repair closes the gap
the only way it can — by reaching for distant stops. The repair has no walking limit of its own
and no walking term in what it optimises.

**Measured, sixteen configurations from 30 to 120 minutes:** the pre-repair route was inside the
walking allowance **every time**; the post-repair route exceeded it **every time**, by 4% to
37%. One case: pre-repair 1168 s against a 1440 s allowance and already in band, replaced by the
repair with 1638 s.

**Product consequence: tours have less narration and more walking than they were designed to
have.**

**Already done (symptom only):** the repair may no longer replace a route that is ALREADY
within the band with one that walks materially further. That removes the measured harm without
touching the arithmetic.

#### HARD CONTRACT — if the owner decides to fix the root cause

**Change:** credit a stop at what it can actually deliver (the per-stop cap) rather than the
per-tour allowance, so the planner's two prices for a stop agree.

**Expect and plan for:** more stops seated per tour, and **the golden tours WILL move.** That is
a re-baselining decision with editorial judgement in it — do not re-baseline silently. Produce
the diff and have a human accept it.

**Acceptance:**
1. The planner's two prices for a stop agree — assert it directly, do not infer it.
2. Golden tour diff produced and explicitly accepted by a human, not auto-updated.
3. Re-measure ERROR 2's four timing rows; state whether this helped.
4. The repair's strict-improvement guard stays in place.

---

### ERROR 4 — Unverified surfaces

**Status:** OPEN. Not failures — things never executed, listed so nobody assumes they passed.

| Not verified | Why | Contract for closing it |
| --- | --- | --- |
| Real-browser screenshots of the new workbench flow | The browser shard sits behind the failing Python shard in `make test`, so it never ran in the final pass | Run `make test-workbench` **in isolation** — nothing else touching containers. Earlier in isolation it was 65 of 66, and the single failure was container contention I caused, not a defect. Capture screenshots of the three option cards and of the degradation banner appearing before any card is clickable (AC-21). |
| Phone screen on a simulator | Proven by a widget test that mounts the real page and finds the sentence, not by a device | Build and run the iOS app, generate a tour with the routing service stubbed down, screenshot the warning card. |
| The full bar green | Best run: 12 failed, 2630 passed, 11 errors. Since then 9 fixed + token group fixed → 1 known failure | `make audit` once, clean. It is the only paid command. |

---

## Part 3 — Decisions taken without you, all reversible

1. **Planning makes no paid AI calls.** The written contract recommended keeping them; your
   locked ruling and the acceptance criterion both said otherwise, so I overrode the
   contract. This *reduces* cost — the phone previously paid for AI glue three times per
   request at planning time.
2. **Thin neighbourhoods now refuse rather than shorten.** One walk budget means one floor as
   well as one ceiling. Matches what your density check already did.
3. **A one-stop tour with a warning is now unreachable** — by arithmetic, not policy. Such a
   tour can deliver at most 40% of its length in walking plus one stop's 4½-minute speech
   limit; the budget demands 90%. Those overlap only below about nine minutes.
4. **The two extra test databases stay.** This run used all three simultaneously to keep
   parallel work from wiping each other's data.
5. **Four corrections to the workbench contract**, including a wrong endpoint URL and a
   response shape that would have rendered an empty tour.

## Part 4 — Costs and regressions you should know about

1. **The test suite is far slower.** One test file went from under 2 seconds to 4½ minutes;
   another module now takes **34 minutes alone**. The full Python shard went from about 15
   minutes to 1 hour 48. Cause: no stop ceilings plus fixtures enriched enough to fill a real
   hour means the planner explores much larger candidate sets.
2. **A one-time audio bill.** Stop audio now carries a content fingerprint so edited words
   re-voice. Existing stops have no fingerprint, so the first non-forced run after deploy
   re-voices every existing stop once.
3. **The narration over-credit, deliberately unfixed.** The planner books each stop for up to
   the whole tour's speech allowance while a stop can only ever speak 4½ minutes — up to a
   fivefold over-credit. Tours therefore come out short and the repair buys the difference in
   walking. Measured across sixteen configurations: before repair, inside the walking
   allowance every time; after repair, over it every time, by 4% to 37%. **Fixing it changes
   the shape of every tour, so it is your call — and it is the most likely single lever on
   the slowdown above.**

## Part 5 — The visibility failure, and how to not repeat it

**What went wrong.** For roughly an hour at the end of this run I could not report what a
working agent was doing. I polled a clock and reported "still running" over and over. When I
finally killed it, its partial result showed it had spent ~50 minutes **re-reproducing a bug
the diagnostic had already proved**, and had written no fix. With visibility I would have
caught that in five minutes and redirected it.

**Two separate causes, two separate fixes.**

### Cause 1 — long shell commands piped through `tail`

`make audit 2>&1 | tail -80` buffers everything until the command exits. The 1h48m audit
therefore produced a zero-byte output file for its entire run, and its `-v` per-test progress
was lost forever.

**Fix — always `tee` to a log, then tail:**

```bash
make audit 2>&1 | tee logs/audit-$(date +%H%M).log | tail -80
```

The log fills line by line, so it can be read at any moment for real progress and per-test
timing. Applied from now on.

### Cause 2 — background agents report only on completion

The Agent tool gives a completion notification and nothing before it, and reading an agent's
raw transcript is explicitly disallowed (it would flood context). So a long-running agent is a
black box by default.

**Fix — require a heartbeat file in the agent's brief.** Every dispatched agent must be told:

> Append ONE line to `<scratchpad>/progress-<lane>.log` after each meaningful step, in the
> form `HH:MM | what I just did | result`. Write it before you start any command expected to
> take more than two minutes, and again when it returns. Never buffer this — one line, one
> append, immediately.

The orchestrator then polls that file instead of a clock, and sees "reproducing the BEFORE
case (3rd attempt)" rather than "process alive".

**Escalation rule to go with it:** if a lane's heartbeat shows no *new kind* of step for two
consecutive checks, message it and ask what it is blocked on. Do not wait a third time.

### Cause 3 — no time budget in the brief

None of the eleven agents was given a deadline or a checkpoint obligation. A lane that spends
50 minutes reproducing a known fact is behaving reasonably given its brief.

**Fix — put a budget and a checkpoint in every brief:**

> If you have not reached <specific milestone> within <N> minutes, STOP and report what you
> have, including what you tried and what blocked you. Do not keep going silently.

For a fix lane whose diagnosis is already handed to it, the milestone is "the change is
written and the proving test is RED" — reproducing the bug again is explicitly NOT required
when the diagnosis already contains the reproduction with numbers.

## Part 6 — Process lessons

1. **I scoped repair rounds from whatever failures a lane happened to report, instead of
   running the full suite early.** That is why the suite kept revealing files nobody had
   examined, and it is the single thing that made this take as long as it did. Run the full
   bar once as soon as a large batch lands, then scope from it.
2. **Defect 4 was foreseen and mis-rated.** `findings/contracts-caps-and-policy.md:1099`,
   branch-collapse table row 1, names the exact consequence — "the greedy walk budget becomes
   the total elapsed ceiling instead of walk_budget × 0.75. A→B tours get materially more
   reach" — and records the risk as **"none"**. The analysis was right; the risk rating was
   wrong, and nobody re-read it when that branch actually collapsed.
3. **A step's declared file list is not its blast radius.** Four separate steps needed files
   the ledger never listed; each time the contract's own collateral table did name them.
4. **Piping a long run through `tail` destroyed the progress output.** The 1h48m audit gave
   no per-test timing because of it. Use a log file.
