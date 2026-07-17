# Content Redistribution — budget the tour's attention, place each fact where it's heard best

> Status: DESIGN. Nothing built. This synthesizes the product-owner brainstorm
> frame ("five destinations for a POI's content") with the REAL sourced research
> in this folder, maps it honestly onto Ondoway's EXISTING code, and proposes a
> first $0 offline slice. Read alongside `RUBRIC.md` (what a good stop sounds
> like) and `GOOD-TOURS-RESEARCH.md` (the craft evidence base).

The problem, concretely: a dense POI (a 2000-word Conciergerie) dumps ALL of its
beats into one standing stop, blowing past attention. The frame's fix is to
**budget the tour's attention and place each fact where it's heard best**, across
five destinations: CORE, WALK-AWAY, CALLBACK, OPTIONAL deep-dive, CUT.

The research does NOT simply endorse this. It endorses the CAP and the CUT
loudly, endorses two of the three relocation channels in a **bounded** form, and
one channel (opt-in depth between stops) barely at all. The honest headline is
below.

---

## (a) What the research CONFIRMS vs CHALLENGES about redistribution

### The blunt truth: pros mostly CUT. Redistribution is a bounded minority channel, not the spine.

Every one of the five research angles that touches "what do you do with the
overflow" answers **cut it**, not **move it** — and two angles say so
emphatically:

- **CUT is the dominant, universal move.** "If they can see it, cut it";
  tours "go dull when they're built on names, dates and facts", so cut ~20% of
  the script after the first draft
  (https://blog.voicemap.me/2026/03/how-to-tell-a-story-15-script-tips-from-tom-darbyshire/).
  Precise numbers and measurements are cut outright — a canvas size in
  centimetres "may be appropriate ... next to an exhibit, but not for an audio
  guide script"
  (https://www.nubart.eu/audio-guides/content-production/writing-museum-guide-scripts.html).
  Round off numbers, one idea per sentence
  (https://studylib.net/doc/7759271/rules-for-radio-grammar). Simple short
  sentences, no complicated concepts a listener can't rewind
  (https://mediahelpingmedia.org/basics/tips-for-writing-radio-news-scripts/).
- **The binding constraint is per-MOMENT cognitive load, not a per-stop quota
  you can rebalance.** This is the core challenge to the whole redistribution
  premise: "cramming biography, period, technique and provenance into one stop"
  is named as the failure, and the remedy is that the extra facts *don't appear
  at all* — not that they get pushed downstream
  (https://www.look2innovate.com/articles/audio-guides/museum-audio-guide-script-best-practices).
  Moving a dropped ledger-fact from a dense stop to a thin one just relocates
  the overload.
- **The pure-storytelling reflex is kill-don't-move.** Ira Glass: "you have to
  be a killer about getting rid of the boring parts"
  (https://brendan-miller.medium.com/the-creative-wisdom-of-ira-glass-3034e96f1c6b).
- **No source names "relocate a rich stop's leftover FACTS to a thin stop."**
  Across all five angles, the documented techniques that DO move content move
  narrative *reference* (setups, threads, callbacks, reflections) — never raw
  fact-overflow.

### What the research genuinely CONFIRMS

1. **CAP the core, hard, and make each stop do one job.** Universal. VoiceMap:
   keep every location below 750 words / 5 minutes because "most people's
   attention wanders if you speak for longer", and the audio must have *ended*
   before the walker reaches the next trigger
   (https://docs.voicemap.me/tour-publishers/word-counts/); a stop past ~3
   minutes loses them
   (https://docs.voicemap.me/tour-publishers/deciding-on-a-route/). Nubart:
   ~250 words / ~2 minutes per track, "select strategically, not exhaustively"
   (https://www.nubart.eu/audio-guides/content-production/writing-museum-guide-scripts.html).
   look2innovate: "Each stop should do one job"
   (https://www.look2innovate.com/articles/audio-guides/museum-audio-guide-script-best-practices).
   Interpretation doctrine: pick one theme, "provoke rather than instruct"
   (https://en.wikipedia.org/wiki/Heritage_interpretation).

2. **WALK-AWAY narration is real — but time-BOUNDED.** VoiceMap explicitly
   weaves "your narrative that builds ... in between the directions" as the
   walker moves
   (https://docs.voicemap.me/tour-publishers/giving-directions/), and sizes it
   with a formula: talk time = distance ÷ ~5 km/h, target words = talk time ×
   ~150 wpm (https://docs.voicemap.me/tour-publishers/word-counts/). Detour
   delivered continuous story synced to the path so you never stopped to press
   pause (https://www.wired.com/2015/12/detour-audio-tour/). **The bound is
   hard**: the segment must fit the walk or it overruns the next GPS trigger and
   the next audio won't fire — and Detour's dominant overflow move was to mark
   content OPTIONAL and *skip* it when the walker moved fast
   (https://medium.com/detour-dot-com/engineering-at-detour-c3e42aceaad5).

3. **CALLBACK / seed-and-payoff is a real, documented tour technique — but it
   moves narrative REFERENCE, not facts.** VoiceMap tells publishers to "come
   back to something you've already described" and to weave a thread through the
   whole tour
   (https://docs.voicemap.me/tour-publishers/the-ingredients-of-a-perfect-audio-tour/),
   to use each transition to "set the scene for what's coming ... or weave a
   thread through the whole tour"
   (https://docs.voicemap.me/tour-publishers/writing-scripts-that-make-listeners-feel-something/),
   and to build the route so "the final stop is also the conclusion of the story
   you started at the beginning"
   (https://docs.voicemap.me/tour-publishers/deciding-on-a-route/). This is the
   spatial version of Ira Glass's engine: "constantly be raising questions and
   answering them" then land a moment of reflection
   (https://medium.com/@DanlWebster/ira-glass-on-storytelling-1-of-4-rough-transcript-9bb2dc8e27f7).
   A second firm corroborates: a guide "might reference what the visitor missed
   or weave it in later"
   (https://www.musa.guide/en/resources/visitor-journey-mapping-audio-guide).

4. **OPTIONAL "tap for more" depth is validated — but only at STATIONARY
   stops.** The museum-app model relocates overflow into opt-in layers so a
   visitor can "dive deeper ... without overwhelming them"
   (https://www.museumnext.com/article/smartify-at-the-van-abbemuseum-creating-a-multi-layered-visit/),
   and can size the whole visit to a stated time budget
   (https://www.trendwatching.com/innovation-of-the-day/smartify-uses-ai-to-generate-a-personalized-audio-tour-for-every-museum-visitor).
   This works because a physical object lets you dwell and choose. It is NOT
   endorsed for between-stop walking audio.

### What the research CHALLENGES / caps

- **Between-stop channels are directions, not overflow history, on some
  platforms.** izi.TRAVEL's between-stop "navigational story" is defined
  narrowly as wayfinding that "will warn tourists of any upcoming route changes"
  (https://izi.travel/en/help/production/create-a-navigational-story) — a
  partial contradiction to using the walk to carry a site's surplus narration.
- **The sparse-stretch fix is NOT importing a neighbor's content.** For a thin
  stretch the pros re-route (deliberately longer and more circuitous), use the
  walk as connective narration, and allow deliberate silence — explicitly
  warning against padding "a single location that doesn't say much followed by
  five minutes of silence". The only redistribution-like move is *temporal
  clustering within a leg* ("Talk for 15 minutes across four or five locations,
  then have ten minutes of silence")
  (https://docs.voicemap.me/tour-publishers/deciding-on-a-route/).

### Net design stance (honest)

> Redistribution is **NOT** the engine's job for most overflow. The spine is
> **CAP the core hard + CUT ledgers/enumerations/visible/tertiary detail.** Two
> bounded relocation channels are legitimate because a GPS tour physically
> cannot delete a stop the tourist is standing at the way a podcast editor
> deletes a boring minute: (2) a *bounded amount of STORY* rides the walk-away,
> sized to that leg's time budget, and (3) a *narrative REFERENCE / callback
> thread* seeds a later stop. Both move NARRATIVE, never a fact-dump. A fourth
> channel — (4) opt-in deep-dive — is validated only for the STATIONARY tap, and
> Ondoway already has it. Everything that fits none of these is (5) CUT.

This reframes the frame's "five destinations" from "spread the overflow around"
to "**cap + cut is the spine; two narrow narrative channels absorb what a tour —
unlike a podcast — can't delete.**"

---

## (b) The content-tier model

Each of a POI's beats is assigned exactly one tier. Ordering of assignment:
CUT first (remove what can't survive one listen), then CORE (fill the cap with
the best), then the remainder competes for WALK-AWAY (fits the following leg's
budget) → CALLBACK (a later thin slot) → OPTIONAL (the tap). Anything unplaced
falls to CUT.

| Tier | Rule | Source |
|---|---|---|
| **1. CORE** (~150 words, stays at the stop) | The hook + the single best story. One job per stop; hard cap ≤ ~750 words / 5 min, ideally ~3 min, and the audio must end before the next GPS trigger. Names/dates hang off human stakes, not a ledger. | https://docs.voicemap.me/tour-publishers/word-counts/ · https://docs.voicemap.me/tour-publishers/deciding-on-a-route/ · https://www.look2innovate.com/articles/audio-guides/museum-audio-guide-script-best-practices |
| **2. WALK-AWAY** (secondary story rides the leg AFTER the stop) | Continuing narrative woven between the walking directions, sized to the leg: words ≤ (distance ÷ ~5 km/h) × ~150 wpm. STORY, not a fact-list. If it doesn't fit the walk, it does NOT ride further — it drops to a later channel or is cut (must not overrun the next trigger). | https://docs.voicemap.me/tour-publishers/giving-directions/ · https://docs.voicemap.me/tour-publishers/word-counts/ · https://medium.com/detour-dot-com/engineering-at-detour-c3e42aceaad5 |
| **3. CALLBACK / reflection** (a rich early stop seeds a later thin one) | A narrative REFERENCE — "come back to something you've already described" — placed on a long, audio-deficit leg to build momentum and fill a sparse stretch. Moves a *thread/payoff*, not raw facts; the route should build so the last stop resolves the first. | https://docs.voicemap.me/tour-publishers/the-ingredients-of-a-perfect-audio-tour/ · https://docs.voicemap.me/tour-publishers/writing-scripts-that-make-listeners-feel-something/ · https://docs.voicemap.me/tour-publishers/deciding-on-a-route/ |
| **4. OPTIONAL deep-dive** (tap for more) | Exhaustive tertiary detail (ledgers, long lists) becomes opt-in at the STATIONARY stop, so the walker chooses depth "without overwhelming them" — the museum multi-layer model. Not delivered between stops. | https://www.museumnext.com/article/smartify-at-the-van-abbemuseum-creating-a-multi-layered-visit/ · https://www.trendwatching.com/innovation-of-the-day/smartify-uses-ai-to-generate-a-personalized-audio-tour-for-every-museum-visitor |
| **5. CUT** (the default for overflow) | Number/ledger dumps, exact measurements, exhaustive enumerations, and anything the walker can already SEE — none survive one listen. Round off; select strategically, not exhaustively; cut ~20%. This is where MOST overflow goes. | https://blog.voicemap.me/2026/03/how-to-tell-a-story-15-script-tips-from-tom-darbyshire/ · https://www.nubart.eu/audio-guides/content-production/writing-museum-guide-scripts.html · https://studylib.net/doc/7759271/rules-for-radio-grammar |

**Place-bound caveat (from the frame, confirmed by the research):** content is
place-bound, so overflow can only redistribute WITHIN a tour — a dense stop feeds
its OWN following walk (tier 2) and a later callback (tier 3), never another
city, and per the research not even a neighbor's fact-load. Sparse tours (London)
lean on tier 3 synthesis-reflections + walk-and-talk to feel full **without
padding** — the pros' explicit warning against dead-air after a thin stop
(https://docs.voicemap.me/tour-publishers/deciding-on-a-route/).

---

## (c) How each tier maps onto EXISTING Ondoway machinery vs what's new

Verified against the current source. Line references are indicative.

| Tier | Existing machinery it hangs on (real code) | Genuinely NEW work |
|---|---|---|
| **1. CORE cap** | `MAX_DWELL_AUDIO_SECONDS = 420` and the C9 governor `govern_route_beats` (src/tour/selection.py) already impose a per-stop ceiling by trimming whole beats; the marquee/domination logic already picks a "best" stop. `overflow_by_poi` (`BeatSequence.overflow_by_poi`, src/tour/contract.py:314) already carries the trimmed beats. | Tighten the ceiling toward the sourced budget: **420 s ≈ 7 min is looser than the 750 w / 5 min (300 s) research cap.** New: a ~150-word CORE target distinct from the 7-min ceiling, and beat-level ordering that guarantees the hook + best story fill it (today the cap is audio-seconds only, not "one job"). |
| **2. WALK-AWAY** | The leg-audio slot exists: `route.vignettes` (leg_idx → walk-past POIs; leg i = the walk INTO stop i, src/tour/options.py:73) and `GLUE_NAV` transit already ride that leg; `vignette_one_liner_text` (src/tour/generation.py:224) already caps a one-liner. | **The content source is new.** Today the walk INTO stop i carries a *different* POI's one-liner or nav glue — never the *previous* stop's overflow beats. New: route a dense stop's tier-2 beats onto its following leg, sized by the leg's walk-time budget (distance ÷ 5 km/h × 150 wpm), woven as story. New leg word-budget function; new "walk-away" beat band. |
| **3. CALLBACK** | Directly on `reflection_slots` (src/tour/reflection.py) + `GLUE_REFLECTION` (src/tour/generation.py:68) + `visited_claims_by_slot` (`ComposeRequest`, src/tour/compose.py:81). Placement is already deterministic: a leg into stop k with walk − leg-audio ≥ `REFLECTION_MIN_DEFICIT_SECONDS` (90 s), cap `max(1, stops//2)`, never two consecutive. | Today a reflection synthesizes ALL *visited* key_claims generically ("worth holding onto ..."). New: make it a **targeted callback to a specific rich early stop** ("remember the executioner from the Conciergerie?"). Subtle but real: `visited_claims_by_slot` today only admits claims **already voiced** strictly before the slot; a rich stop's tier-2/tier-3 material may be UNvoiced overflow, so its claims aren't in the visited set. Extending the callback to reference unvoiced overflow needs a VERIFY-safe way to admit those claims. |
| **4. OPTIONAL deep-dive** | **Already built.** `overflow_beat_ids` → `has_deeper_dive` (src/api/routes/trips.py:675) → Flutter `generateDeeperDiveAudio` (mobile/lib/services/trip_service.dart:251) → keep-exploring endpoint, whose narration is stitched DETERMINISTICALLY from `build_poi_extra_narration` (trips.py ~549), bypassing the LLM VERIFY gate. | Little new. Just the classifier deciding which overflow beats are *tertiary* (→ tap) vs *story* (→ tier 2/3) vs *ledger* (→ cut). Today ALL overflow lands here indiscriminately. |
| **5. CUT** | The governor already *trims* whole beats past the cap — but it routes 100% of them to tier 4 (deeper-dive), i.e. nothing is truly cut today. | New: a **deterministic ledger/enumeration/number-dump detector** (belongs in src/tour/narration_quality.py — see `PROPOSED-lint-signals.md`) that marks a beat "does not survive one listen" so it is dropped from the plan entirely, not merely demoted to the tap. |

**One-line summary of new vs reuse:** tiers 1, 3, 4 largely *re-point* existing
machinery (`MAX_DWELL`, `overflow_by_poi`, `reflection_slots`/`GLUE_REFLECTION`/`visited_claims_by_slot`,
`generateDeeperDiveAudio`); the genuinely new pieces are (2) walk-away *content
routing* + a leg word-budget, (3) *targeted* callbacks over possibly-unvoiced
overflow, and (5) a *CUT* classifier so overflow can actually die instead of all
piling into the tap.

---

## (d) First $0 slice — buildable + testable OFFLINE (no live compose)

**Build the measurement + the CAP/CUT half first — the part the research
unanimously endorses — as a pure function, and prove it on the REAL Paris
corpus.** Rationale: (i) it's what every source agrees on, so it's the
lowest-controversy, highest-confidence increment; (ii) it's pure and offline, so
$0 and hermetic; (iii) it *quantifies the actual overflow problem on real data*,
which tells us whether tiers 2/3 are even worth wiring or whether — as the
research predicts — the honest answer is "mostly cut."

### Slice: `src/tour/content_budget.py` — a pure, deterministic tier partition

Signature (pure; no I/O, no LLM, no network):

```
partition_poi_content(
    plan: POIBeats,              # a POI's selected beats (from select_poi_beats)
    core_word_budget: int,       # ~150 words, sourced
    hard_cap_seconds: int,       # MAX_DWELL_AUDIO_SECONDS (or the tighter 300s)
    leg_walk_seconds: int | None,# following leg's walk time -> tier-2 word budget
) -> ContentBudget               # {core_ids, walkaway_ids, callback_ids, optional_ids, cut_ids}
```

Rules implemented in this slice (only the unanimous half is *active*; tiers 2/3
are *computed as candidates* but not yet composed):

1. **CUT detector** (tier 5): flag a beat as "does not survive one listen" when
   its text is number/ledger/enumeration-dense (e.g. ≥ N numerals or list
   markers per 100 words, exact measurements, long proper-noun enumerations).
   Deterministic, regex/heuristic — no model. Sourced by the cut rules above.
2. **CORE fill** (tier 1): greedily fill `core_word_budget` with the
   highest-value non-cut beats (hook + best story), respecting `hard_cap_seconds`.
3. **Remainder routing (candidates only):** compute the following leg's word
   budget `(leg_walk_seconds / (5000/3600)) × 150 / 60` and mark how many
   remaining beats would *fit* as tier-2 walk-away; mark 1 as a tier-3 callback
   candidate; the rest tier-4 optional; ledger beats tier-5 cut.

### What we build with it (the SEEN artifact — the $0 proof)

A `make`-target report (extends `scripts/tour_build.py` / `demo_full_tour.py`,
which already read the live Paris corpus) that runs `partition_poi_content` over
every POI in `data/paris/` and prints, per dense POI:

```
Conciergerie  34 beats / 2140 words
  CORE      150 w  (hook + best story)
  WALK-AWAY  Xw    (fits the 220 m leg to Sainte-Chapelle -> ~Yw budget)
  CALLBACK   1 thread candidate
  OPTIONAL   12 beats  -> tap
  CUT         6 beats  (ledger/number-dump)     <- would DIE, not relocate
Tour-wide: 71% of overflow words -> CUT, 18% -> optional tap, 9% -> walk-away, 2% -> callback
```

That last line is the honest test of the whole idea: if the corpus says most
overflow is cut, we've *confirmed the research on our own data* before spending a
cent, and tiers 2/3 are scoped to the small real residue.

### Tests (offline, in the bar)

- **Unit** (`tests/test_content_budget.py`): fixtures — a dense POI overflows the
  cap; a ledger beat lands in `cut_ids`; a short leg shrinks `walkaway_ids`; a
  long leg admits more; every beat lands in exactly one tier; total words in
  tier 1 ≤ budget.
- **Undo-test (mutation):** revert the CUT detector → a known ledger beat leaves
  `cut_ids` and the Conciergerie CORE blows `hard_cap_seconds` → a test goes RED.
- **Corpus assertion:** run over real `data/paris/beats.json` (no compose) and
  assert invariants (partition is total + disjoint; no beat both core and cut).
- Wire into `make tour-invariants` / `make test-unit`; **no live compose, $0.**

This slice touches selection-adjacent pure code only. It does not change
compose, does not call an LLM, does not alter what today's tours emit — it adds a
*classifier + a report*. Wiring tiers 2/3/5 into generation/compose is a later,
tier-3 slice gated by what this report reveals.

---

## (e) Open risks

1. **The premise may be mostly wrong on our data.** The research says CUT
   dominates. If the corpus report shows ~70%+ of overflow is ledger/cut, the
   ambitious relocation (tiers 2/3) is a small residue and we should invest in
   the CUT detector + core cap, not the plumbing. This slice is designed to
   surface that before we build the plumbing. Treat a "redistribution wins"
   result as the surprising one requiring proof.
2. **Fact-loss is the standing Tier-3 hazard** (memory: `tour-quality-root-cause.md`,
   `tour-gen-overhaul-2026-07.md`). A CUT that silently drops a beat that WAS the
   POI's best fact is a regression. Mitigation: CUT only removes beats the
   detector marks ledger/enumeration AND that are not the beat CORE would have
   picked; everything else demotes to the tap (tier 4), never vanishes. The
   `overflow -> keep-exploring` "never silently dropped" invariant must hold for
   tiers 2–4; only tier 5 truly removes, and only for ear-hostile content.
3. **Walk-away overrun is mechanical, not aesthetic.** If tier-2 audio exceeds
   the leg, it overruns the next GPS trigger and the next stop's audio won't fire
   (https://docs.voicemap.me/tour-publishers/word-counts/). The leg word budget
   must be a hard ceiling with margin, and tier-2 content must degrade to
   tier-4/5 when the leg is short — mirroring Detour's skip-when-fast
   (https://medium.com/detour-dot-com/engineering-at-detour-c3e42aceaad5).
4. **Callback over UNvoiced overflow breaks the VERIFY contract.**
   `visited_claims_by_slot` today admits only claims cited strictly before the
   slot; a callback to a rich stop's *overflow* references material the walker
   never heard, which is both a provenance question (VERIFY) and a comprehension
   question (a callback to something never said isn't a callback). Tier 3 must
   reference claims that WERE voiced in that stop's CORE, or explicitly seed the
   thread in CORE first.
5. **Tighter cap = live-compose validation cost.** Lowering 420 → 300 s changes
   emitted tours; proving it improved anything needs a money-gated live A/B
   (memory: `feedback-never-waste-anthropic-credits.md`). The $0 slice
   deliberately does NOT change emitted output — it measures — so the cap change
   is a separate, cost-estimated decision.
6. **Sparse tours need synthesis, and reflections can go flat.** Leaning on
   tier-3 to fill London risks the "reading Wikipedia aloud" monotone the rubric
   exists to kill (`RUBRIC.md`). Reflections must carry a narrative thread, not
   a recap of facts — the exact line the callback research draws
   (https://docs.voicemap.me/tour-publishers/the-ingredients-of-a-perfect-audio-tour/).
7. **Determinism of the CUT detector.** A regex/heuristic ledger detector will
   have false positives (a beat whose one great fact is a number) and negatives.
   It must be conservative (bias to demote-to-tap, not cut) and belongs beside
   the existing signals in `src/tour/narration_quality.py` so it's tuned with the
   same offline harness (`PROPOSED-lint-signals.md`).
