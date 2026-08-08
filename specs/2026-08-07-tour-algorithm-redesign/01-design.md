# Ondoway — the tour algorithm, redesigned

**Status:** APPROVED IN OUTLINE by the owner, 2026-08-07, section by section.
**Base commit:** `c8a35a75` (tree carries the uncommitted `2026-08-06-tour-time-model` work).
**Provenance:** written after reading the tour engine, the serving paths, the audio pipeline, the
quality standard, all eleven persona files, both reference walks, the Flutter app's tour surfaces
and the in-flight time-model plan **in full** — not from search hits. §10 makes that a rule rather
than a boast.
**Intended lifetime:** PERMANENT reference, like
`specs/2026-07-19-tour-quality-standard/01-standard.md`. It is `git add -f`'d when Stage 0 lands
(`CLAUDE.md` §7 ignores `specs/*/` by default). The implementation ledger that executes it is
scratch and is deleted with the work.

---

## 0. Why this document exists

Two failures have repeated across sessions, and both are addressed structurally here rather than
by resolve.

**Failure 1 — work chased faulty tests, because nobody had defined a good tour.** Five separate
"tour quality root cause" memories were written in eight days (recorded in the quality standard's
own §"Why this exists"). Each session re-derived what good looks like, fixed a local defect, and
moved on. §1 below is the definition, and §7 makes it enforceable: **an acceptance test that cites
no source may not gate anything.**

**Failure 2 — plans were built from `grep` and discovered the real code mid-implementation.** The
in-flight time-model plan records this in its own header: five adversarial rounds found 27 defects
in the grep-built version, "most of them citations pointing at the right symbol in the wrong
place". §10 makes read-before-plan a mechanical precondition with evidence.

A third, quieter failure the owner named on 2026-08-07: **progress was never visible.** Plans
promised phases and then spun on a step for days. §9 replaces "tests pass" with nine demos the
owner watches or hears, and §10 caps how long any step may fight.

---

## 1. What a good tour is

This is the section whose absence caused Failure 1. It has three legs, in priority order.

### 1.1 The eleven days (`docs/personas/`) are the specification

Eleven tourists, each written minute by minute, each breaking a different assumption on purpose.
`docs/personas/00-what-these-are-for.md` states the rule this document adopts verbatim: **a design
is finished when it can represent all eleven days; when it cannot hold one, say which and what it
costs — never edit the persona to fit the algorithm.**

Their five shared truths, which the engine must express:

1. **Standing still is most of the day.** In every persona, time at places exceeds time walking.
2. **The same place costs different people different time.** The Cour Carrée is 33 minutes for
   Camille, 8 for Théo, 16 for a couple who talked through it. *The hardest requirement in the set.*
3. **Silence is normal**, and for one party it must be deliberately scheduled.
4. **Overlap is a default, not a law.** Narration heard while walking is free to most, expensive
   to a second-language listener, unwanted by a couple.
5. **Some constraints are not time at all** — a toilet, a bench, a step, an opening hour, a queue,
   a lit street at half past four in December.

### 1.2 The gold text is the writing bar

The owner's hand-written Le Meurice / Orwell stop
(`specs/2026-07-19-tour-quality-standard/01-standard.md` §1) and its ten derived properties
(orientation before history, motivated transitions, causal chain not list, say-it-once, a dramatic
pivot, a wry non-moralising close) remain the narrative standard. **Nothing in this redesign lowers
it**; §5 adds constraints of the same kind, and §7.3 gates the release on meeting or beating today's
measured output.

### 1.3 A good tour is a good DAY, not a good file

The redesign's own addition, and the reason the architecture changes: a tour is judged by the day
the visitor actually had, including the parts that diverged from the plan. Concretely — **every
prefix of a day must be a decent tour** (`03-family-with-children.md`: the tour ends at 78 % by
design), and a day that ended early, sheltered from rain, or paused for an hour must still be
coherent and must still *finish*.

---

## 2. Inputs and the party

### 2.1 What we ask

| Input | Form | Why |
|---|---|---|
| Start point | Map pin, GPS default | Exists (`trip_duration_page.dart`) |
| End point | Optional pin | Exists in the API (`TourInput.end`) |
| When | Start time (**"not before"**), end time, date | §2.2 |
| **End hardness** | `wall` \| `firm` \| `open` | §2.3 — NEW |
| Interest | Existing lens picker; profile default with override | Exists |
| **Who's walking** | solo \| couple \| family \| take-it-easy \| with-luggage | §2.4 — NEW |
| **Yesterday** | museums \| churches \| mostly walking \| first day | Multi-day visitors only — NEW |

### 2.2 The clock is real, and the start is soft

`trip_duration_page.dart` already collects a start date-and-time and an end date-and-time, then
discards everything except the minute count. The planner learns the actual clock: opening days and
hours, daylight, meal windows, and queue-by-hour become planning inputs.

**The start time means "not before", never "at".** Fiona and Dev stood reading a menu for twelve
minutes; Camille put an earbud in and walked. A start treated as an appointment opens every day in
arrears.

### 2.3 End hardness — three values, not a boolean

- **`wall`** — Marcus's 16:40 train. The plan carries visible spare minutes, and **no stop whose
  duration is unboundable is ever offered** (§6.5). He currently lies to the product about his end
  time to manufacture margin; the plan's cleverest arithmetic therefore runs on a falsified number.
- **`firm`** — the default. Honest planning to the clock; the ceiling behaviour the in-flight work
  already built.
- **`open`** — Julien's two-ish hours, and Camille's "is 15:00 a wall or a wish?". A rough length,
  nothing defending a deadline. Camille's report is unambiguous: for a solo traveller with nowhere
  to be, a hard end time is *a preference enforced as a fact*, and it costs her the chapel.

### 2.4 What the party tap sets — unbundled

Rosemary's report caught us shipping a bundle whose parts must travel separately:

| Party sets | solo | couple | family | take-it-easy | with-luggage |
|---|---|---|---|---|---|
| Walking pace | normal | normal | **~half, variable** | slow | **slow** |
| Longest single walk | — | — | short | **hard cap (~12 min)** | medium |
| Rest/toilet cadence | — | — | **yes** | **yes** | — |
| Escape radius | — | — | **yes** | — | — |
| Per-stop **ceiling** | **none** | none | **yes (~6 min)** | **none** | none |
| Route surface | — | — | **no stairs (buggy)** | **step-free** | **no stairs/cobbles** |
| Narration register | solo | warm (**never romantic**) | **family, aloud, may address the child** | **unchanged** | solo |

Load-bearing details:

- **A per-stop ceiling is never set by mobility.** Rosemary's centrepiece is a 46-minute sit;
  Théo's anchor is 65 minutes inside one building. A ceiling tuned for tired families decapitates
  both. It exists for children, and for anyone who asks for it.
- **Register never follows mobility.** "Slow the walking, never the talking."
- **Escape radius** is a family-only constraint on the whole loop, not on a leg: a meltdown 25
  minutes from the exit means carrying a child for 25 minutes.
- A party tap may set several axes at once (`take-it-easy` + `solo` is a legitimate pair); the
  presets are shortcuts over axes, and the axes are what the planner reads.

### 2.5 What we never ask

Weather (fetched), daylight (computed from date and latitude), and street-safety preference
(**inferred** from solo + season + a finish after dark). Sofia would find the question
patronising and would still apply the rule; the system already holds every input needed to infer it
and spends none of them.

---

## 3. The plan — promises and fabric

### 3.1 The shape

A planned day is **a small set of PROMISES on a clock, connected by FABRIC.**

**Promises** (typically 2–5) are the items that define the day:

- the interest anchor, where the promise includes **the shape of the visit** — 65 minutes *inside*
  is a different promise from 15 minutes outside, and the queue is a third number again;
- a **meal window** if the day spans one — a real 40-minute table carrying no narration;
- **body stops** — a toilet at a known time; a bench that is a scheduled item **with its own
  five-minute story**, because a rest window with no bench under it is thirteen minutes standing on
  a stick;
- the **finish** — a place and a time, where a finish after dark must be somewhere rated good to
  be left standing in the dark.

Each promise carries a clock window; the plan prints its spare minutes.

**Fabric** is everything between: a corridor of candidates scored for this party at this hour, with
more candidates than the day will use. Fabric is offered, not sworn, and the presented day says so.
This distinction is the whole announcement policy in miniature: **fabric may change silently;
promises may not** (§4.3).

### 3.2 The visitor pins

The planner proposes the promises; the visitor may pin any offered stop into a promise, or release
one back into fabric. This is the single mechanism that lets one engine serve Théo (pins one thing
absolutely) and Julien (pins nothing, wants an open walk).

### 3.3 Queues are a fourth kind of time

Not walking, not being-at-a-place, not narration. `01-architecture-pilgrim.md` is explicit: 28
minutes of line plus 38 minutes of chapel are two facts, and folding them into one 66 makes the
wait permanent — unskippable by someone who only wants the outside, unshrinkable at opening time.
So: a queue is priced separately, by hour and season, it belongs to the day rather than to the
building, and it is **excluded entirely under `wall`** (§6.5).

### 3.4 Presentation

The day is presented as **two-to-four named stretches** of the city — Greta's "I can see the
mistake before I've walked a metre". This is presentation only: the adaptation machinery underneath
works item by item and never in all-or-nothing acts, because whole-act amputation was the single
most-reported break in the panel (Rosemary had no legal move at all; Marcus lost 25 minutes to
repay 12; Théo could only choose which limb).

### 3.5 What this reuses

Not a rebuild. `select_route` already prices each stop for the specific visitor
(`visit_time.visit_seconds`), already protects a pinned endpoint through every repair
(`_materialize_fixed_end_b`, `protected_end_id` in the timebox repair), already treats duration as
a hard ceiling with honest shortfall disclosure (`Route.elapsed_shortfall_seconds`), and already
refuses with concrete alternatives (`FeasibilityAlternative`: loop / extend / closer_b). **The
generalisation is one protected endpoint → a set of protected promises.**

---

## 4. The session

### 4.1 The loop

The phone re-times the remaining day continuously from GPS position, measured pace and observed
dwell. Two learned rates, both of which the panel demanded:

- **Walking pace**, learned within the first ~15 minutes, replacing the preset (Marcus's bag stops
  being a permanent deficit that repairs only by spending margin).
- **Listening rate**, learned from replays and playback speed. Paulo tells the product three times
  in forty minutes that he consumes narration at ~1.5× its stated length; every candidate treated
  each resulting overrun as a fresh surprise. The remaining day's estimates scale to the observed
  rate.

### 4.2 Two response tiers

- **Fabric events** — lingering, drifting, sheltering, skipping, a shortcut refused — are absorbed
  **silently**. Nothing is announced, nothing is owed, no debt language appears. This is the single
  behaviour that made Field & Flow the favourite of the three divergent personas, and it is
  imported wholesale.
- **Promise events** — a promise becoming expensive — produce **exactly one behaviour: the
  question.** "Keep your bench and reach the Orsay at 17:10, or skip it and be on time?" Rosemary,
  Théo and Camille all asked to *answer* that sentence rather than be informed of it. A safe
  default applies if unanswered; under `wall`, the wall wins.

### 4.3 Triggers

| Trigger | Response |
|---|---|
| Pace / dwell drift | Silent re-time |
| **Pause** | Suspends the clock; treated as information ("we are talking now"), never lateness. Repeated pauses bias the session toward screen-only updates |
| Closure or refused door | Immediate re-route + one honest line; writes a data-correction flag (§6.1) |
| **Forecast turning** | Re-price covered routes and shelter-worthy stops **mid-walk** — the sky opening at 11:00 fires nothing in any candidate today |
| Approaching dusk | Re-price legs (light) and the finish (§6.4) |
| **Wrap it up** | Written close, then a route to the exit sized to the escape radius |

### 4.4 Announcement etiquette — hard rules

1. Speech **queues to a natural moment** — never into a conversation, never onto a walking leg
   (a sentence missed on the move is gone forever for a second-language listener).
2. Everything spoken **also appears on screen**. The new speech this redesign adds is exactly the
   speech most likely to lack a transcript.
3. Framed as a gift ("we've been enjoying this square, so I've traded the last stop"), never as
   debt. Three loss-framed sentences over a family's shared speaker is "a small scold with good
   manners".
4. **One sentence, maximum.** Over a screaming five-year-old, mute beats graceful.

### 4.5 Replanner guardrails — five, all panel-forced

1. **Price trades in visitor-time, never narration-minutes.** Every arithmetic replanner in the
   test reached first for the quiet items — Rosemary's rest, Nadia's playground, Théo's silent
   memorial, Greta's lunch — because silence looks like zero value. The engine already prices
   per-visitor time (`visit_time.stop_seconds`); the replanner must spend that currency.
2. **A protected class.** Rests, meals, toilets and the finish are never auto-cut; they trigger the
   question instead.
3. **Every drop re-checks the longest-single-walk cap.** Dropping a stop **merges its two legs** —
   drop Rosemary's bench and a 12-minute and a 9-minute leg fuse into 21 continuous minutes,
   double her limit. Without this rule every drop is a trap.
4. **The terminus is not the shock absorber.** Camille drifts 11 minutes doing exactly what she
   came for and her declared destination silently shrinks from 22 minutes to 8, because drift only
   ever rolls downhill. End-of-day items get promise protection.
5. **Replacements are drawn category-diverse** (§6.7), so a repair never offers a third gallery
   before 10:30 to someone who spent yesterday in the Louvre.

### 4.6 One replan brain — the phone SELECTS, it never DECIDES

The largest duplication risk in this design is a second replanner growing inside the app, because
the session must keep working with no signal. It is closed **by construction**, not by discipline:

- **The server is the only place a plan decision is made.** At plan time and after every replan it
  emits a **contingency set** alongside the plan: precomputed answers to the divergences that
  matter — running late or early by bands, a stop skipped, a promise at risk, wrap-up from here —
  each with its alternates and their audio.
- **The phone selects from that set.** It holds no scoring, no candidate pool, no policy.
- **The one thing the phone computes is arithmetic re-timing** (observed pace × remaining
  distance) — and even that is *checked*: on every reconnect the phone's clock and the server's are
  compared, and a divergence beyond tolerance is a **reported defect**, not a silent correction.
  This is `CLAUDE.md` §1.7's rule for two things that must agree and cannot import each other.
- **A divergence the contingency set does not cover** waits for connectivity, or falls back to
  "carry on and re-time", which is arithmetic rather than policy. The phone never invents a plan.

### 4.7 Offline

The phone carries the current plan, its contingency set (§4.6), the fabric alternates and their
audio, prefetched during walks. Offline it can still re-order, drop, re-time and close gracefully
with canned transitions — **acting only from the contingency set it already holds**, never by
computing a new plan. It cannot add narration it does not hold, and it says so rather than going
quiet.

---

## 5. Narration and audio

### 5.1 Unchanged

Per-stop authoring, the locked narrator voice, the fact-gates (traceability, entailment,
claim-coverage, provenance), the storyteller lane with the stitched-corpus lane as its fallback,
and **stories written and voiced before the walk**. Marcus asked us to lock the last one harder: a
pre-voiced file has a known length, and his day is a defence of known lengths.

### 5.2 Point first

Every piece is written with its point in the **first** minute. Fiona and Dev walk off at minute
eight of nine, routinely, not accidentally; today the payoff is authored, fact-checked, voiced,
paid for, and heard by nobody.

### 5.3 Closes that land anywhere

Every named stretch carries a **written one-line close** that can play wherever the stretch actually
ends. This is what "wrap it up" plays, and it is why quitting early feels like finishing. Nadia's
meltdown exit — where the eight-year-old has heard two complete stories and retells the duel on the
walk home — is the panel's single most valuable moment, and it costs one authored sentence per
stretch.

### 5.4 Plants, payoffs and threads survive adaptation

- A plant may only promise a payoff **inside its own stretch**, and ships with a written fallback
  line for the case where its payoff stop is traded away.
- When the session swaps in an alternate, the sentence binding it to the day's theme — "this
  courtyard held prisoners of the same tribunal" — is **pre-authored as a pair at authoring time**.
  Threads are content, not logistics, and the live model still writes only logistics.

### 5.5 Two lengths per major stop

The default telling is the tight one; the full telling is one tap — or one lingering visitor —
away. This is the existing keep-exploring machinery (`build_poi_extra_beats` /
`build_poi_extra_narration`, `overflow_by_poi`) **promoted from an extra to a core behaviour**.
Fiona and Dev get four minutes and Théo gets twelve from the same authored material.

### 5.6 Placement by moment

- **The queue is the best listening slot in the day** — eyes free, feet still, the building minutes
  away. A promise with a wait plays its story *in the wait*.
- **Arrival at a marquee interior triggers silence, not speech.** Story before the threshold, quiet
  under the glass.
- **Legs carry only losable content** — colour, walk-past one-liners — never a thesis.
- **Trigger zones follow real geometry.** A 10 m circle mistakes a 140 m courtyard for a point;
  walking out to Perrault's colonnade must not read as leaving the stop.
- **Segmented audio at marquee anchors.** The corpus already carries within-place anchors — sixteen
  distinct ones at Notre-Dame, addresses around Place des Vosges (`sub_location`,
  `trigger_address`, `physical_cues`). Segmenting a stop's audio lets the guide walk a visitor spot
  to spot: "stand here; he faced the Madeleine". For a lens where four of ten stops have nothing
  left standing, that choreography *is* the product.

### 5.7 Register and access

The party sets the voice (§2.4). **Every word ever spoken exists as on-screen text** — stories,
transitions, replan questions, closes. Foreign terms get a one-breath gloss at first use.

---

## 6. What the city must learn

Almost everything the panel found missing is data, not algorithm. Each row ships in the established
style: **every enriched value carries a one-sentence justification a non-visitor can judge**,
structural tests catch absurdity, and the planner may not read an unaudited field
(`.claude/commands/poi-visit-duration.md` and `tests/test_poi_visit_duration.py` are the pattern).

| # | Data | Source | Serves |
|---|---|---|---|
| 6.1 | **Opening days + hours** | OSM + audited AI pass; corrected by session flags | Aiko's locked door, Rosemary's Tuesday |
| 6.2 | **Step-free / stairs / cobbles** | The routing engine is believed to answer this and is never asked (`05-step-free-visitor.md`: "Valhalla can be asked for this; the planner never does"). **Verify against its pedestrian costing options before Phase 2 plans on it** — §10.1 applies to capability claims, not only to files | Rosemary, Marcus, Nadia's buggy |
| 6.3 | **Body places** — toilets, benches | OSM | Nadia, Rosemary, Fiona & Dev |
| 6.4 | **Place judgements** — *children can run here*; *you can sit and talk here*; *good to be left after dark* | Audited AI pass | Nadia's invisible best quarter-hour; the couple's two green chairs; Sofia's finish |
| 6.5 | **Queues** — none / short / long / **unpredictable**, with peak hours | Audited AI pass | Camille (priced), Marcus (excluded under `wall`) |
| 6.6 | **Leg properties** — covered, lit — **priced at the hour walked** | OSM + daylight | Aiko, Sofia |
| 6.7 | **Category per place** — gallery, church, square, arcade, market, park | Cheap derivation | Greta's satiation; category-diverse replacement |
| 6.8 | **Forecast** | Live fetch | Aiko |
| 6.9 | **Within-place anchors** | **Already in the corpus** | §5.6 |

Two notes with teeth. **Aiko's finding stands: clock-native planning is "a promise without a table
under it" until 6.1 exists** — it is the highest-leverage row in the product. And 6.4's three
judgements are the only rows with no external source; they are the ones to sample hardest in review.

---

## 7. Quality gates

### 7.1 Unchanged

Fact-gates on every authored piece; the deterministic mechanical exam (`quality_rubric.score_tour`)
on every tour; golden reference tours pinning the planner; the paid certification lane (independent
fact review + enjoyment consensus) guarding the reference corpus.

### 7.2 The mechanical exam starts blocking

The quality standard's §7 records the gap plainly: the rubric is advisory, nothing honours
`passed`, and the persisted compose path never calls it. That closes. A day failing the floor is
not served, with `compose_fixable` deciding whether a re-compose can converge or the plan itself
must change.

### 7.3 The meet-or-beat release gate

**The new engine ships only when it meets or beats today's output, judged blind.** Regenerate the
certified reference requests (`data/certification/tour-batch-v1/`), run side-by-side enjoyment
judging through the existing consensus machinery, include deliberately-diverged sessions (§7.4).
Losing is a finding to fix, not a caveat to ship.

### 7.4 The eleven days become executable tests

Each persona file is a minute-by-minute script, so each becomes a replayable GPS-and-behaviour trace
through the session loop. Asserted:

1. **No promise is ever silently dropped** — fuzzed across replans as an invariant.
2. Every drop re-checks the longest-leg cap (§4.5.3).
3. Protected items are never auto-cut.
4. Announcements never land on walking legs and always carry screen text.
5. **Every prefix is decent** — wrap-up at any minute of any simulated day ends with a close.

### 7.5 Test provenance — the fix for Failure 1

**Every acceptance test cites its source**: a persona file and line, a rule in the quality standard,
or a named panel finding. A test citing nothing may not gate. **A test is never edited to make it
pass** — a wrong test is a written decision with a reason, escalated, not a quiet edit.

### 7.6 The panel is standing infrastructure

Any future change that reshapes tours goes through the eleven readers before it is decided.
`CLAUDE.md` §1.10 already requires this; it now has a permanent bench and a document to read.

---

## 8. What we delete

| # | Deleted | Why |
|---|---|---|
| 8.1 | **Pick-one-of-three route options** (`select_k_routes`, diversity penalty, Jaccard rejection, the flavour UI on both surfaces) | No persona ever wanted to compare routes. One day, dials, pins |
| 8.2 | **The frozen trip** — a stop list written once, narrated once, refusing a second compose (`mark_trip_composed`, the 409) | Structurally hostile to §3–§4. Becomes a living session with versions, promises, alternates, history |
| 8.3 | **Fill-the-requested-time, completely** | The in-flight work made duration a ceiling; `open` (§2.3) finishes the thought |
| 8.4 | **The one-size 10 m trigger circle** | Replaced by per-place geometry (§5.6) |
| 8.5 | **Per-beat audio library; the anonymous paid authoring door** | Audio's unit is the stop and its segments; the workbench moves onto the authenticated session flow |

**Kept deliberately** — the leverage: the corpus and its pipeline, the fact-gates, the routing
engine and its receipts, honest refusal with alternatives, the visit-time model now in flight, the
quality standard and its goldens (re-baselined once, with sign-off), per-stop speech synthesis, the
keep-exploring machinery, and the eleven personas.

**Sequencing rule: nothing is deleted until Stage 0 lands.** The in-flight time model is the pricing
engine under promises-and-fabric.

---

## 9. The build — demo-anchored phases

**A phase is not done when tests pass. It is done when the owner has watched or heard something.**
Each phase: a measurement harness first, a vertical slice through data → engine → API → surface, a
demo, then the bar.

| Phase | Delivers | **DEMO the owner sees** | Kill criterion |
|---|---|---|---|
| **0** | Land the in-flight time model. Its two open owner decisions, named: **(a)** whether a place may be seated for being worth visiting though it says nothing (step 3B.14 — currently ON; measured cost on the flagship corridor: walking 85 → 108 min, longest leg 30 → 51 min, furthest off the direct line 527 → 1,146 m); **(b)** the golden re-baseline (step 3B.16, a hard stop). Then `make audit`, then commit | **D0** — the flagship Rue Royale → Notre-Dame 300-minute tour plans end to end; the owner reads the tour and hears one stop | If the golden diff is unacceptable, the time model is revised before anything here starts |
| **1** | Clock-native planning: end-hardness, daylight, forecast fetch. Data 6.1, 6.7 | **D1 — "the Tuesday proof"**: the same request on Monday and on Tuesday, side by side; the closed museum is absent on Tuesday, with a printed reason | If audited opening-hours coverage lands below a threshold the phase sets, clock-native planning is scoped to daylight + meals only, and 6.1 becomes its own phase |
| **2** | Party axes and presets. Data 6.2, 6.3, 6.4 | **D2 — "six people, one street"**: one start, one clock, six party presets, six different days side by side | If step-free routing cannot be obtained from the routing engine, `take-it-easy` ships without surface guarantees and says so |
| **3** | Promises and fabric in the planner; pins; queue as a fourth time; data 6.5, 6.6, 6.8 | **D3 — "the rainy day"** (same request, dry vs rain) and **D4 — "pin it"** (pin the chapel; watch the day rebuild around it) | If promises make planning slower than a stated wall-clock budget, promises are capped in number before anything else is traded |
| **4** | One day + dials on both surfaces; delete 8.1 | **D5 — "turn the dial"**: calmer / fewer / shorter / quieter, each replanning live in the workbench | — |
| **5** | The living session: server replan endpoint, alternate authoring, prefetch; delete 8.2 | **D6 — "the walk that noticed"**: a replayed persona trace where lingering 20 minutes makes the guide ask the question, on device | If replan latency exceeds the budget on a real device, alternates are pre-computed at plan time and the live path narrows to re-timing |
| **6** | Narration changes: point-first, closes, plant fallbacks, paired thread lines, two lengths | **D7 — "wrap it up at minute 14"**: hit the button mid-walk; hear a real close | — |
| **7** | Audio placement: per-place geometry, queue placement, threshold silence, segmented anchors; delete 8.4, 8.5 | **D8 — "stand here"**: the Notre-Dame segmented walk-through, heard on device | If segmentation degrades listening in review, it ships for marquee anchors only |
| **8** | Gates: blocking rubric, persona traces, meet-or-beat | **D9 — the blind judging result**, new vs today, with the panel's verdict | **Losing the blind comparison blocks launch** |

**One ledger per phase, never nine at once.** Each phase is planned only when the phase before it
has demoed — its files read in full at that moment (§10.1), against the tree as it then is. A plan
written today for Phase 7 would be a plan written from memory of code that will have changed, which
is Failure 2 wearing a different hat.

Fast-follows, with seams designed in now: per-member family audio on a shared route (§App. B);
cross-day memory and satiation decay (launch carries only the yesterday question — Julien's full
need waits, stated plainly); mid-walk story rewriting; a true wander mode (a small step once fabric
exists); transit legs; queue models learned from real sessions.

---

## 10. The execution contract

Binding on every session that implements this. It exists because of the three failures in §0.

### 10.1 Read before plan, with evidence

- A step may not enter the ledger until **every file it will change has been read end to end**.
- The plan records, per file: path, line count read, commit sha.
- **A discovery made during implementation that the plan did not know is a PLAN DEFECT**: stop,
  log it, amend the plan, then continue. Never absorb it silently.
- **Files not yet read in full at the time of writing** — these are a hard precondition on
  planning any step that touches them: `src/tour/quality_certification.py`, `src/tour/artifact.py`,
  `src/tour/place_materialization.py`, `src/tour/corpus_places.py`, `src/tour/claim_dedup.py`,
  `src/tour/validation.py`, `src/tour/degradations.py`, `src/tour/spatial_check.py`,
  `src/api/routes/audio.py`, `src/api/crud/trips.py`, `src/api/models/trips.py`,
  `frontend/review.html`, `mobile/lib/pages/trip_itinerary_page.dart`,
  `mobile/lib/services/trip_service.dart`, `mobile/lib/services/audio_service.dart`.

### 10.2 Atomic steps

One file-scoped change, proven by exactly one executable command that goes RED before and GREEN
after (`make test-file FILE=<node id>`; never `-k`). Unchanged from `CLAUDE.md` §4.

### 10.3 The undo test is mandatory

Revert the change → the new test goes RED → restore → GREEN. All four runs pasted. A step with no
undo test did not happen.

### 10.4 Declared breakage

Each step declares, in advance: **which tests it expects to turn red, and which later step turns
them green.**

- A red test **not** on that list is an immediate stop.
- **A phase may not close with any declared breakage outstanding.**

This is what makes a broken intermediate state legible rather than alarming, and it is the owner's
own requirement from 2026-08-07.

### 10.5 The step budget

- Two attempts at one mechanism. Three mechanisms maximum. Then **stop and report all three errors
  verbatim.** There is no fourth attempt (`CLAUDE.md` §1.3).
- A step exceeding its wall-clock budget is **decomposed or escalated**, never silently continued.
- The engine's existing caps (per-step `maxAttempts`, ping-pong detection, empty-diff
  short-circuits, the infra circuit breaker) are the enforcement, not prose.

### 10.6 Progress is visible

One line per step in the ledger: state, attempts, declared breakage outstanding. The owner can read
where the work is without asking.

### 10.7 Vertical slices only

No phase whose deliverable is a layer. Every phase reaches a surface, so every phase can be
demonstrated.

### 10.8 Never build it twice — the failure this project has already paid for

The tour algorithm once existed **twice**: one path serving the app, one serving the workbench.
They shared no lines, no names and no structure, so no pattern scan could ever have seen it; they
diverged silently; the owner discovered it a month later; consolidating them became its own project
(`c8a35a75`). These rules exist because that cost is not payable again — and because **this
redesign creates exactly the two conditions that grow a fork**: a new surface behaviour (the
session, §4) and migration windows in which a replaced path could linger beside its replacement
(§8).

1. **Every step names what it extends.** A ledger step that creates a new file, module or function
   carries a mandatory field: *the existing thing it considered, and why that thing could not be
   extended*. No answer, no step. `CLAUDE.md` §1.7 states the rule; this makes it a field the
   engine can refuse.
2. **One question, one answer — declared.** Any new function computing a quantity either declares
   in a comment that it is **the** one definition of that quantity, or names the existing
   definition it delegates to. The engine is already written this way — `total_walk_seconds` ("THE
   ONE EXPRESSION"), `path_walk_seconds` (whose comment records that the same sum had been written
   five times), `stop_seconds`, `served_elapsed_seconds`, `option_eta_seconds`,
   `build_route_option`, `build_poi_beat_plans_capped`. New code matches that discipline or does
   not land.
3. **`make dedup-review` gates every PHASE close, not just commits.** It is a semantic reviewer,
   not a lint rule: it asks what code is *for*, which is the only question that can find a fork
   sharing no text. Its first real run found four duplicated responsibilities nobody had planted,
   including four separate definitions of "a valid point on Earth".
4. **A seam that must not fork gets a SOURCE-SCANNING test.** The biggest finding of the in-flight
   release — that the walking clock had *five* spellings, not the two its plan claimed — came from
   a test that reads the source, and its author's conclusion is the rule: **a behaviour test cannot
   see a duplicate.** Two numbers agree right up until someone edits one. Precedent exists
   (`tests/test_workbench_matches_the_app.py` and the one-engine guards, which parse call sites and
   imported modules). Seams that get one here: the replan brain (§4.6), promise pricing, the audio
   placement rule, and the session clock.
5. **A replaced path is deleted in the SAME phase that replaces it** — never "later". Where a
   temporary coexistence is genuinely unavoidable, exactly one is marked the only writer and a
   source-scanning test asserts the other has no callers, so the window is visible and shrinking
   rather than quiet and permanent.

### 10.9 Measurement first

The first step of every phase builds or extends the harness that shows the before and the after.
This is the one thing the in-flight plan did that visibly worked (its Phase 0), generalised into a
rule.

---

## 11. Risks

| Risk | Mitigation |
|---|---|
| **Adapted days lose narrative coherence** — the genuinely new quality risk | §5.3–5.4 (closes, stretch-local plants with fallbacks, paired thread lines); §7.4 judges diverged sessions |
| Audited AI data is confidently wrong | Justification sentence per value, structural tests, session-flag corrections; 6.4 sampled hardest |
| The session loop lands in the app, the least-developed layer (~4,400 lines) | Phase 5 is its own phase with a latency kill criterion; persona traces are testable off-device |
| Authoring spend concentrates where the visitor does not go | Category-diverse reserve per stretch (§4.5.5); prefetch follows the live plan, not the original |
| Promise-heavy days slow planning | Phase 3 kill criterion caps promise count |
| The tree is mid-surgery | Stage 0 first; nothing deleted before it lands |
| **A second implementation grows silently** — the failure already paid for once | §4.6 makes one replan brain structural (the phone selects, never decides); §10.8 makes extension a ledger field, `make dedup-review` a phase gate, and source-scanning tests the guard on every seam that must not fork |

---

## Appendix A — the panel

Eleven personas walked their documented days through three candidate architectures on 2026-08-07:
**Timeline & Ledger** (a self-repairing clock-stamped schedule), **Field & Flow** (continuously
recomputed best continuation), **Chapters** (a day in acts adapting internally).

| Architecture | First | Last |
|---|---|---|
| Timeline & Ledger | 5 — Camille, Théo, Marcus, Rosemary, Sofia | 1 — Julien |
| Chapters | 3 — Nadia, Paulo, Greta | 2 — Aiko, Fiona & Dev |
| Field & Flow | 3 — Julien, Aiko, Fiona & Dev | 8 |

**The split is the finding.** Personas with a fixed point (a shrine, a train, a knee, a child, a
dark finish) require promises with clock stamps and call continuous recomputation unlivable ("a
probabilistic Conciergerie is my day's obituary"; "'very likely' is what one says about weather").
Personas who live by divergence require silence and no debt framing. Personas who need the day to
*end* require closes that land anywhere. The synthesis in §3–§5 takes each one's winning organ.

Findings promoted into the design, with their source: pause-as-information and scheduled silence
(Fiona & Dev) → §4.3, §4.4; legs priced by hour and a rateable dark finish (Sofia) → §6.6, §6.4;
child-value and the escape radius (Nadia) → §6.4, §2.4; duration-versus-distribution and
`wall` (Marcus) → §2.3, §3.3, §6.5; step-free routing, leg-merge on drop, and the protected class
(Rosemary) → §6.2, §4.5.2–3; the queue as the best listening slot and threshold silence (Camille) →
§5.6; sub-stop choreography and per-visitor visit shape (Théo) → §5.6, §3.1; listening rate and
transcripts everywhere (Paulo) → §4.1, §5.7; category satiation and the yesterday question (Greta)
→ §2.1, §6.7; fame-inversion and memory (Julien) → §4.5.5, §9 fast-follows (**stated as a cost, not
solved at launch**).

---

## Appendix B — family profiles: why the route brain comes first

The owner's original vision: one family, one shared trip, each member hearing the walk through their
own interest. **The vision is right and the order was wrong.** The personas show a family's needs
diverge mostly in the *route and the clock*, not the narration — Camille and Théo make the identical
request with one word changed and spend 33 versus 8 minutes at the same courtyard. Different audio
over a route shaped for one member does not fix the route.

So: **launch** plans for the party as a unit with merged constraints and speaks in one register
(and a family listens out loud on one speaker, where a single well-written shared track genuinely
beats three private streams). **The family release** keeps the shared route and authors each
member's audio separately, fitted to the *same stop clock* so nobody stands waiting, using the
per-member profiles the data model already anticipates (`src/seed/users.py` seeds one account with
"Mom" and "Kid" profiles carrying real lens edges).

Three seams are built now so that release is an addition, not a rewrite:

1. The planner takes a **party** (a set of listener profiles with merged constraints), not a lens.
2. The narration authoring path takes a **listener** parameter, defaulted to the party.
3. A saved session keeps **the plan separate from its audio tracks**.
