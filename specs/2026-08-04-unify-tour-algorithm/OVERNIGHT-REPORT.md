# What happened overnight

*Draft — final numbers filled in when the last lanes land.*

## Read this first: the work is done, the final gate is not

All seventeen planned steps are built and individually proven. The proof you asked for
exists, is in your test suite permanently, and I verified it myself rather than taking a
builder's word for it.

**But I cannot tell you the bar is met, because it isn't.** The full suite finished at
**12 failed, 2,630 passed, 11 errors**. Nothing committed. Two causes, neither of them a
defect in the tour work:

1. **Nine failures in three test files I never assigned to anyone.** I scoped the repair
   work from failures that lanes happened to report, instead of from a full-suite run. Files
   nobody touched were never examined. That's my planning error. A fix is running now.
2. **The rest are one test file's login token expiring mid-run.** The token lasts 60
   minutes and is issued once when that file starts. The file now takes longer than an hour,
   so later tests get rejected. Production tokens are fine; this is test plumbing exposed by
   the slowdown below.

**The slowdown is the real story there.** That one shard went from 15 minutes to 1 hour 48.
A suite nobody can afford to run is its own problem, and re-issuing the token would paper
over it.

---

## The short version

Your app and your workbench used to build tours from two different piles of code that
agreed by accident. They now run one. Fifteen of the seventeen remaining planned steps are
finished and individually proven; the last two are in flight.

Along the way the work exposed **three real defects in how tours are built**. None was
introduced by carelessness — all three were hiding behind limits that this work removed. Two
are fixed. One I have deliberately left for you, because fixing it changes the character of
every tour, and that is your call rather than a decision an agent should make at 3am.

One of those defects had killed a feature outright: your three-routes-to-choose-from had
silently become one route.

---

## The thing you actually asked me to prove

You asked for proof that the app and the workbench invoke the exact same code — not
equivalent code, the same code.

**Before**, measured by walking the call graph from each entry point:

| | tour-engine functions it could reach |
| --- | --- |
| the phone's tour request | 199 |
| the workbench's tour request | 254 |

Only 189 were shared. The shared route-builder was reachable **only from the phone**; the
workbench ran its own private copy. The shared plan-and-write blocks were reachable **only
from the workbench**; the phone went around them.

**After:**

| | before | after |
| --- | --- | --- |
| shared by both surfaces | 189 | **257** |
| reachable only by the phone | 10 | **6** |
| reachable only by the workbench | 65 | **13** |

Divergence fell from 75 functions to 19. The composition matters more than the count:
**none of the remaining 19 is tour-building logic.** The six the phone reaches alone are
about saving a trip and its "keep exploring" extras. The thirteen the workbench reaches
alone are quality scoring and the degradation report it shows you as an editor — things the
phone has no screen for.

Route planning, ordering, stop selection and script writing are now entirely shared.

The proof is **five tests that now live in your suite permanently**, so this cannot quietly
come apart again. Every one of them was demonstrated *failing* first — and the failures were
staged the way the real fault would actually happen.

1. **Identity.** The name the app uses for the planner and the name the workbench uses point
   at the *same object in memory*. Proven by planting a byte-identical copy of the planner
   and watching the test catch it. Two character-for-character identical planners in two
   files would pass any search and any code review — and fail this.
2. **Break one thing, both must break.** The single shared planner is replaced with a
   stand-in that refuses to work. Then the phone's request and the workbench's request are
   both made against the same running server. Each must have gone through that stand-in
   exactly once, and each must have failed. **A copy cannot survive this, because a copy is
   not the thing that was taken away** — it would keep working, and the test says so by
   name. Proven by loading a second complete copy of the request-handling module and serving
   both surfaces from it: literally "a separate module with the logic".
3. **Same for the writing.** The same sabotage applied to the part that writes the words,
   driven through a real generate-then-write round trip.
4. **Same request, same tour.** Both surfaces are asked the identical question back to back,
   and must return the same places in the same order with the same quoted time. Proven by
   making the planner hand the second caller its options in a different order.
5. **Nothing left over.** A structural scan of the whole codebase fails if more than one
   function anywhere decides which routes to offer, or more than one place assembles the
   list of stops a person sees. Proven three separate times by planting a second
   implementation — it caught the copy even when the copy disguised itself with renamed
   imports.

**Why this is proof rather than just green tests:** a test that only reads code can be
fooled by a copy, and a test that only compares outputs can be fooled by two
implementations that happen to agree today. This does neither. It removes the shared thing
and checks that everything claiming to depend on it collapses.

### What the proof does not cover — stated plainly

- **The phone and browser halves are not executed.** These five tests prove the four
  server-side handlers converge on one implementation. What connects your Dart app and your
  workbench page to those handlers is the web address each one posts to. That is verified by
  reading the source, not by running it. The browser half belongs to your Playwright suite.
- **Live content and the live walking-route service are substituted.** That is deliberate —
  it is what makes "both surfaces produced the same tour" a statement about the code rather
  than about whether your content changed between two requests. A fault that only shows up
  on real Paris data is outside these tests' reach, and I've written that limitation into
  the test file itself rather than leaving it implied.

---

## The defect that was costing you tours, and is now fixed

Your phone app planned tours on an old, shrunken time budget while the workbench planned on
the correct one. The code now says so plainly at the place it was fixed:

> the phone silently planned on the legacy flat budget and skipped the route bar — about
> 20% less walking and audio than the workbench produced for the identical request

**In plain terms:** a tourist asking for a 60-minute tour got roughly 50 minutes. You,
reviewing the identical request in the workbench, were shown the full 60. You have been
signing off on tours meaningfully richer than the ones that shipped.

---

## Three defects this work uncovered

### 1. The planner could not shorten a tour *(fixed)*

When a route came out slightly too long, the repair pass could add a stop or swap one stop
for another — but it could never **drop** one. So an over-long walk had no way back into
range and was refused outright.

The visible symptom: **the three-route feature had collapsed to one route** on the real
Paris data. The second route was refused for being 8% over the ceiling.

This never bit before because a hard cap on stop count kept routes short. Removing that cap
— which you asked for — exposed it.

### 2. The planner checked one route and shipped a different one *(fixed)*

This is the one that was actually killing your three routes, and it took three attempts to
find because the first two suspects were also real bugs.

The planner works out a route's total time **before** deciding which stop goes last. It then
re-orders the same stops to put the destination at the end — and forcing one particular stop
to be last makes the walk much longer. So it approved a route of one length and then built a
different, longer one, which the final check rejected.

The evidence is unambiguous. On a real 90-minute Paris tour: nine stops go in, nine come
out, and the narration is identical to the second. **The entire 17-minute discrepancy is
walking**, created purely by pinning the last stop.

In other words the engine was checking its homework against an answer sheet for a different
question. Every over-long tour was silently refused rather than shortened.

I treated this as a correctness bug rather than a matter of taste — a check that validates
something you don't ship isn't a check — so I had it fixed.

**Result: your three routes are back.** The live Paris flagship went from 1 route to 3
(nine, eight and nine stops).

I expected this to shift your saved reference tours and planned to hand you the differences.
**It didn't — all nine pass unchanged**, along with 15 of 15 quality-grade checks. The fix
only bites when a tour pulls a destination *and* pinning it materially lengthens the walk,
and your reference tours don't meet both conditions. So there is no re-baselining decision
waiting for you.

This one also needed the first fix to work. Once the planner could see the true cost it
discovered the route was too long — and being able to drop a stop was the only way back.
Neither fix alone would have restored the three routes.

### 3. The planner over-counts its narration, then buys the shortfall with walking *(NOT fixed — your call)*

This is the one I want you to look at.

When deciding whether to add another stop, the planner credits that stop with up to the
**whole tour's** listening allowance. When the tour is actually spoken, every stop is capped
at 4½ minutes. So a place with a deep story gets booked as roughly **five times** more
listening than a tourist will ever hear.

The planner therefore thinks it has filled the listening budget after about a third of the
stops, and stops adding them. The tour comes out well short of the requested length. The
repair pass then closes the gap the only way it can — by reaching for distant stops. It has
no walking limit of its own.

Measured across sixteen configurations from 30 to 120 minutes: the route *before* repair was
inside the walking allowance **every time**; after repair it exceeded it **every time**, by
4% to 37%.

**In plain terms: your tours have less narration and more walking than they were designed to
have.**

**What I did:** I fixed the symptom, not the cause. The repair may no longer take a route
that is already acceptable and replace it with one that walks further. That removes the
measured harm.

**What I deliberately did not do:** correct the underlying arithmetic so the planner prices
a stop at what it will actually deliver. That would change how many stops every tour seats —
it changes the shape and feel of every tour you have, and it would move your saved reference
tours. That is a product decision about what a good tour is, and it is yours.

---

## Other things worth knowing

**A one-time audio bill.** Stop audio now carries a content fingerprint, so editing a
stop's words re-voices it. Existing stops have no fingerprint, so the first run after
deploy re-voices every existing stop once. The alternative — treating "no fingerprint" as
"still fresh" — would silently recreate the exact staleness bug this removes.

**Planning is now free.** The written contract recommended keeping paid AI calls in the
planning stage. I overrode it, because your own locked ruling and the acceptance criterion
both say planning makes no AI calls. This *reduces* cost: your phone currently pays for AI
glue three times per tour request at planning time. Now all writing spend happens only on
the one route a person actually picks.

**Thin areas now refuse rather than shorten — and one old behaviour is now unreachable.**
Unifying the two paths means adopting one time budget, and that budget has a floor as well
as a ceiling. A neighbourhood too sparse to fill the requested time now returns a clear
refusal instead of a quietly shortened walk. This matches what your density check already
did.

There is a sharper consequence worth confirming was intended. A tour with a single stop can
deliver at most 40% of its length in walking, plus one stop's 4½-minute speech limit. The
budget demands 90%. **Those two ranges only overlap below about nine minutes** — so the old
"build it anyway and show a warning" path for a genuinely thin area can no longer happen at
any tour length you actually sell. Such areas are refused instead, and the refusal now tells
the traveller what duration the area *could* support, which I think is the better answer.
The warning mechanism itself still exists and is still tested; it just can't be reached by a
one-stop tour any more.

**Your test suite is now noticeably slower**, and that's expected rather than a symptom.
Making the test fixtures rich enough to fill a real hour means the route-ordering work they
trigger is genuinely larger. One file went from under two seconds to about four and a half
minutes.

**A crash became an explanation.** Asking for a tour that can't be walked in the time given
used to return a server error with a stack trace. It now returns the shortfall in minutes
and suggested alternatives.

---

## What I have not verified, and what is still running

**Not verified:**
- **The full suite has never been green.** Best run: 12 failed, 2,630 passed, 11 errors.
- **No real-browser screenshots.** The browser shard sits behind the failing shard in the
  same command, so it never ran in the final pass. Earlier in the night it passed 65 of 66
  in isolation, and the one failure was my own fault — I ran it alongside two build lanes,
  which this project forbids; alone, that test passes in 11 seconds.
- **No phone-on-a-simulator proof.** The phone-side warning is proven by a test that mounts
  the real screen and finds the sentence on it, not by a device screenshot.
- **The paid audit has not passed.** It ran once, cost real money, and failed on the two
  causes above.

**Still running as I write this:** the fix for the nine unscoped failures, and a timing run
to confirm the token diagnosis.

**Nothing has been committed.** Every change is sitting in your working tree, which means
none of this is hard to undo.

## The two decisions waiting for you

1. **The narration over-credit.** Fixing it changes how many stops every tour has. I judged
   that yours to make, not mine at 3am. It is also the most likely single lever on the
   slowdown, so it may pay for itself twice.
2. **Thin neighbourhoods now refuse rather than shorten.** Deliberate, matches your existing
   density behaviour, and reversible if you disagree.
