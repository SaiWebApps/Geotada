# Phase 4 ledger — one day + dials on both surfaces; delete pick-one-of-three (D5)

Executing session: 2026-08-11, tree at `258933fd` (Phase 3's last commit; the
re-plan's own base — verified at session start: HEAD matches, review.html hash
f53b22d4 matches the workbench map, no src/tests/scripts/mobile modifications).
Owner's go: "Execute Phase 4 per the plan."

## D4.0 [DEMOLISH] — DONE

Audit E's rows executed (05-audit-E-workbench-phase4.md §§1–5, read first):

- **Deleted whole from `test_workbench_ui.py`:** `test_tour_preview_view_opens`
  (:2390 — pins the old input set), `test_tour_preview_surfaces_spotlight_and_coverage`
  (:2866 — pins the old value scalar), `test_tour_preview_yellow_tourability_renders_warning_banner`
  (:3031 — pins §8.3's deleted fill vocabulary), `test_tour_feedback_thumbs_send_context_and_toast`
  (:3221 — its first assertion IS the two-screen flow), and the pre-pick half of
  `test_tour_preview_vignette_renders_tag_and_hollow_pin` (:2907 — the option-card
  count assertions).
- **Fixture move (audit E §5.3, THE hardest coupling):** `_client` (renamed
  `_mock_routing_client`, its setattr-target name in the importer) + `_dense_snap`
  + their private deps (`_grid_pois`, `_rich_beats`, `_flavour_mock_handler`)
  moved INTO `tests/test_workbench_matches_the_app.py`, the only importer; the two
  function-scoped `from tests.test_tour_flavours import …` lines deleted.
- **`tests/test_tour_flavours.py` deleted** (git rm; §8.1's own suite).
- **Anchors re-derived as a WRITTEN DECISION citing §8.1** in
  `tests/test_tour_one_engine.py`: `K_OPTION_PRIMITIVES` drops `select_k_routes`
  (comment records the decision + the invariant that survives); clause-3 prose
  re-worded to "the offered day"; `THE_ONE_PLANNER` stays `plan_premium_options`
  with an in-place note that S4.3 flips it to `plan_premium_tour` in the same step
  that moves the call — the guard never gaps red. `SURVIVING_WORKBENCH_TOUR_TESTS`
  untouched: both pinned names still exist (their bodies are declared-red).
- **Helper sweep:** `_generate_options` / `_pick_option` are TOMBSTONE STUBS that
  fail naming §8.1 and S4.8 (see deviation ii below); `_plan_payload` collapsed to
  a ONE-option default (see deviation i below); module docstring block rewritten to
  the one-day flow; `_clear_tour_route_pins` comment re-pointed (its explicit
  `options=[]` stub was already one-day-safe).

**PLAN DEFECT (§0.2, logged + plan amended in place):** the plan ordered
"DELETE `test_tour_flavours.py` wholesale (§8.1's own suite)" before that file had
been read end to end (it was on the plan's own read-precondition list). Read in
full this session: lines 354–745 — 12 tests + 2 fixtures — are the
`build_route_option` assembly suite, and that interleave explicitly SURVIVES
Phase 4 (the re-plan's own read evidence: "count-agnostic and SURVIVES"). Deleting
wholesale would have stranded the surviving module with zero coverage. Amendment:
that half moved intact to **`tests/test_tour_options.py`** (new file, named for
the module it tests; Extends: considered leaving in place — impossible, the file
dies; considered `test_tour_selection.py` — wrong module and 3.2k lines). The
flavour half (10 tests + `_sweep_snap` + `_INPUT` + jaccard/select_k_routes
imports) died with the file.

**Argued deviations from the step text (owner-visible):**
(i) `_plan_payload`/`_route_option`/`_authored_payload`/`_route_two_step` were NOT
deleted — the KEEP test `test_tour_generate_sends_clicked_coords` (:3170) calls
`_plan_payload` directly and is not on the declared-red list, and S4.8's step text
itself orders "New stubs: a ONE-option `_plan_payload`". Collapsing the builder to
one option now IS the demolition of "plumbing that exists only to serve three",
and the two-call plan/author flow survives Phase 4 by audit E's own rulings.
(ii) `_generate_options`/`_pick_option` could not be plain-deleted: eight
KEEP-AND-REWRITE bodies reference them and `make lint` (F821) rejects undefined
names — the plan's own proof requires lint clean. They are tombstone stubs that
fail with "Phase 4 deleted the pick-one-of-three flow (design §8.1); rewritten at
S4.8". The declared red stays red, now with an honest message.

**Declared breakage standing:** audit E's 16 KEEP-AND-REWRITE tests red until
S4.8. Nothing else.

**Proof:** `tests/test_tour_options.py` 12 passed (the moved suite, unedited
assertions). One-engine anchor
`test_one_planner_produces_the_options_and_one_interleave_builds_them` 1 passed.
Collection + a KEEP node per Playwright file:
`TestApiServerGuard::test_guard_rejects_dev_pointed_server` passed,
`test_the_served_app_has_no_dependency_overrides` passed. `make lint`: All checks
passed.

## W4.1 [GATE] — DONE. 24 cells, evidence/phase4-dials/

Three starts × 8 strawman cells, serial, canned glue, dated Wed 2026-08-12 10:00
(Louvre OPEN — the gravity exhibit must be able to show it). Full outputs +
INDEX.tsv in `evidence/phase4-dials/`; runner cells:
base · leg12 · leg6 (shorter) · wall40 · wall25 (calmer = wall + rest cadence) ·
stop90 (fewer) · stop20 (more) · lens=dark_history (quieter strawman).

**Latency vs the ≤15 s bar (the kill-criterion baseline):**
- BOTH dated 180-min starts, all 16 cells: **1.78–12.44 s — under the bar as-is.**
- The 300-min flagship A→B class: **30.7–120.5 s — 2–8× over.** Worst:
  stop20 120.5 s (the stop-ceiling dial widens the pool the repair enumerates —
  exactly Phase 3's carried driver). wall cells ~74 s.
- Two flagship cells REFUSED under a leg cap (c-leg12, c-leg6): honest structured
  refusal, best bounded route 75 min vs 270–300 required, wall clock ~11 s.

**Day-shape exhibits for the panel (the Phase-3 carried finding, now in tables):**
- a-base (PdV 180 dated): **3 stops, 24 min walk, 10 min audio** — the
  giant-interior day (Carrousel + Louvre pair) live in the base cell.
- a-leg6 / b-leg6: the "shorter walks" strawman at 6 min **collapses the day to
  ONE stop, 0 walking** — a three-hour stand.
- a-wall40 (calmer): **7 stops, 55 min walk** — the wall ceiling + rest reserve
  incidentally breaks the giant-interior gravity that the base day has.
- b-stop20: 7 stops; c-stop20: 12 stops at 120 s planning.
- Lens narrowing (quieter strawman) SHIFTS the day (a-base 3 → a-lens 5 stops):
  it changes which places, not how loud the day is.

**DEFECT FOUND (logged for in-session fix at S4.5, same file):** the band-refusal
message template is wrong when the day UNDERRUNS: c-leg12's refusal prose says
"every route … overruns the requested duration; the shortest one found is still
longer than asked for" while its own numbers say best 4527 s vs required
16200–18000 s — the day was too SHORT. The workbench renders this prose to a
human (and the phone shows it), so the sentence contradicts its numbers.

## Standing carry-forwards into W4.2 (the panel's input)

Phase 3's carried findings head the panel payload: the one-giant-interior default
day (now measured in a-base), the dial semantics (locked costs: Rosemary shorter ≝
shorter LONGEST walk; Greta "less of THIS KIND today"; plain bodily labels;
Marcus's margin reading of calm; Théo's dials point up), and deviation v (whether
the promise/queue/closure surface lands on the workbench this phase).

## W4.2 — THE EARLY PANEL — DONE. All eleven, one message, on the real tables.

By name: Camille (architecture pilgrim), Théo (dark history), Nadia (family),
Marcus (layover), Rosemary (step-free), Julien (resident), Aiko (rainy Tuesday),
Paulo (second language), Fiona & Dev (couple), Greta (day two of five), Sofia
(solo after dark). Full verdicts in the task transcripts; payload =
evidence/phase4-dials/w42-panel-payload.txt.

### LOCKED DIAL SEMANTICS (bind S4.3–S4.8; re-opening is §0.8.10)

1. **"Shorter walks"** (subtitle: "No single walk longer than N minutes") =
   cap the LONGEST leg. Bidirectional. As it tightens it re-plans into nearer
   stops / bench-chains; when a turn cannot bind it SAYS "already true"; when
   nothing fits it REFUSES with a reason — it never silently under-delivers.
2. **"More breaks"** = rest cadence + slack. It may NEVER lengthen the longest
   leg, never fund a rest by shaving an anchor, never append toilets/benches as
   numbered micro-stops (fold the sit into a sit-and-talk stop; after dusk a
   rest is lit-and-peopled or absent — Sofia). Bench/toilet PRESENCE is a floor
   at every dial position (Phase 3's promise); the dial moves cadence only.
3. **"Finish by HH:MM — hard/soft" is its own field**, not a tenant of a mood
   word (Marcus). Maps to end_hardness + the clock; the plan shows slack as a
   number ("ends 16:18, 22 min before your train").
4. **"Fewer stops / More stops"** (subtitle: "Fewer places, longer at each") =
   stop count with freed minutes flowing to the anchors. The bare stop-minutes
   ceiling is REJECTED as the fewer-mechanism (stop90 was a placebo in 2 of 3
   starts and inverted in the third). "More" direction = shorter stop ceiling
   (the proven a-stop20 shape). Below a category's entry floor a stop is
   DROPPED and backfilled, never shaved (the 5-minute-museum disease — 7
   panelists, verified: a-wall25 Carnavalet 47→5).
5. **"Less talking / More talking"** = narration SUPPLY (shorter pieces, silent
   legs, fewer beats per stop), never topic. (Fiona & Dev's dial; Camille's
   meaning; Paulo's label.)
6. **"Quieter" as a word is RETIRED** (sound word — Paulo; dangerous after dark
   if it means empty streets — Sofia). The crowd/queue need becomes
   **"Skip the queues"** — queue-minutes penalize stop choice (queues are
   already budgeted-never-credited; this adds avoidance).
7. **Topic/lens narrowing is a REQUEST-TIME PICKER ("today's stories"), not a
   dial** — unanimous. **Kind-exclusion must exist** (Greta's "not what I did
   yesterday", Julien's "zero museums today"): category chips that SWAP places
   in (the lens behaviour), never starve them (the stop20 behaviour).

### THE DEFAULT DAY — ruled

The a-base shape (3 stops, one long anchor, short legs, ~1/3 slack) STANDS as
the default: right for 6 of 11 as-is; the five it fails (Nadia, Marcus, Théo,
Julien, Greta) are each fixed by their own dial/preset, not by re-cutting the
greedy. NO selection re-cut this phase. Two unanimous conditions on the
default surface: the unaccounted minutes are NAMED ("122 of 180 planned; 58
min is yours"), and a default day's longest leg stays near 12–15 min.

### DEVIATION v — RULED: the honesty surface LANDS THIS PHASE

Pre-commit day view must show: timed promise WINDOWS (coarse, not
minute-fiction — F&D), per-stop queue minutes written "40 min wait" (never
"40m" — Paulo), closed-today lines, the unverified-hours doubt NAMING the stop
("We could not confirm opening times for Musée Carnavalet"), in/out shape per
stop, forced-vs-chosen exterior marking (Greta), and named slack.
Paulo's wording rulings bind: "err-short", "gated", "(hours: OSM)", "anchor",
"40m" all FAIL plain language; market closures must not read "seated outside
only".

### MEASURED DEFECTS the panel exposed (fix in this phase's builds)

- **(D-i) THE CLIFF, unanimous worst:** a-leg6/b-leg6 deliver a 1-stop,
  0-walk, 30-minute day against a 180-minute request — stamped planned-180,
  tourability GREEN — while the A→B twin correctly REFUSES. The round-trip
  path fails to enforce the band floor under a binding leg cap. Fix + regression.
- **(D-ii) The refusal template lies:** "overruns … longer than asked" printed
  over numbers showing 75 min built vs 270 required; raw DB warnings leak above
  it; seconds shown to humans. Fix the template (name the binding cap, speak
  minutes, offer both remedies).
- **(D-iii) Drop-not-shave:** interiors shaved below any plausible entry floor
  (5-min Carnavalet, 8-min Bourse) by rest/ceiling pressure. Below floor →
  DROP + backfill. (Panel-mandated behaviour change; 11/11 convergent — §1.10
  satisfied by this panel.)
- **(D-iv) Queue pricing vanishes on shaved/re-planned stops:** c-wall25 seats
  Sainte-Chapelle 15 min INSIDE at ~13:15 (peak; hour-priced 30 min in Phase 3
  evidence) with queue "—", so the finish promise is unpriced by ~30 min.
  Confirmed in tables; root cause to be proven in code at the S4.6c fix.
- **(D-v) Dead-notch honesty:** a turn that changes nothing must say "already
  true" (surface behaviour, S4.7).

### Dial → request mapping (deviation iv applied)

Existing axes: shorter walks ⇄ max_leg_minutes; more breaks ⇄
rest_cadence_minutes (+ the D-iii/D-i fixes that make it honest); finish-by ⇄
end_hardness + clock; more-stops ⇄ max_stop_minutes (proven at 20).
NEW additive TourInput axes (S3.2 mould, request_sha256 move declared):
`stop_density` ("fewer" = concentrate: drop weakest + redistribute within
shape ceilings), `narration_density` ("less"/"more" beats-per-stop bias; full
point-first mechanics remain Phase 6), `avoid_queues` (rank penalty on
queue minutes), `category_minus` (kind chips; excluded from dwell seating,
disclosed on the exclusions channel like the clock).

## S4.3 — DONE (main, me)

plan_premium_options + the K=3 loop DELETED; plan_premium_tour IS Block 1: one
select_route call, choose_discrete_route([route]) kept as the container-identity
refusal (the one-engine suite pins the primitive), record_routing_degradations
component renamed to its new home. Fresh node
test_block_one_plans_one_priced_free_day (cites §8.1 + the W4.2 panel) written
RED first (source assertion: the delegate was not the one-day planner) → GREEN;
the prebuilt-seam test's delegate clauses re-derived as a written decision
(§8.1) — the one-construction-site invariant unchanged. THE_ONE_PLANNER flipped
to plan_premium_tour in the same step (guard never gapped red; anchor node
re-ran green). UNDO: scoped stash of premium_tour.py → node RED → pop → GREEN.

## S4.4 — DONE (main, me)

generate + _plan_preview call plan_premium_tour; one-element lists kept
list-shaped (deviation i — compose reader, legacy branch, opt-N parser all
untouched); route_id stays {trip_id}-opt1; models' options descriptions updated.
Re-derived: test_generate_plans_through_the_shared_block_one (one day,
byte-identical to Block 1; the Jaccard diversity clause died with the flavours —
written §0.1.2 decision), test_options_surface_k_flavours →
test_options_surface_the_one_day (fresh, §8.1), the fixed-destination refusal
derives via select_route, preview-contract's "three_options" name and the
degradation component string re-derived. Proof: wiring 7 passed;
preview-contract 7 of 8; LIVE dev-graph nodes green (32.9 s + 16.1 s). UNDO:
scoped stash of trips.py → collect-error RED → pop → GREEN.

## DISCOVERY + FIX en route (§0.2 logged): the S2.7 surface kwarg broke the
## legacy-client contract on route_with_receipt

The preview-contract suite (inherited red at HEAD, "owned by later phases") was
red because routing._transit passed costing_options_override to
route_with_receipt UNCONDITIONALLY — the Phase-3 ledger's compatibility
contract ("the kwarg rides ONLY when a real override is set") was honoured for
leg_seconds and isochrone but never for route_with_receipt. Fixed in
routing.py per the contract; 5 of the 6 inherited reds cleared; routing 56 +
party 26 re-ran green (the surface machinery still threads when set).

## DISCOVERY (the panel's D-i, reproduced HERMETICALLY):
test_preview_returns_the_plan_and_spends_nothing's AC-24 half now exposes the
cliff in-process: a lone-anchor 60-min request answers 200 with an 8-minute
one-stop day (dwell 477 s vs the 3,240 s band floor), disclosed only via
elapsed_shortfall_seconds + YELLOW — where the file's own docstring records
that since 2026-08-05 this exact input was a 422 naming "required 3240-3960s".
The starved-pool rescue path ships under-floor days without the final band
check — the same mechanism as W4.1's a-leg6/b-leg6 cells (1 stop, 30 min,
"planned 180", GREEN). DECLARED RED until S4.5b (below) lands the fix.

## S4.5 — DONE (main, me): flavour machinery deleted + D-i/D-ii landed

**Deleted:** select_k_routes, _jaccard, DIVERSITY_PENALTY, JACCARD_OVERLAP_MAX.
**PLAN DEFECT (§0.2):** the plan's "score_penalty exists solely for flavour
re-runs — delete the threading (26 sites)" was measured FALSE: Phase 3's rain
pricing RIDES that channel (commit 71654c97 dims uncovered stops through the
same per-place dict). The threading SURVIVES as the rain channel; its comments
re-pointed; the tombstone asserts poi_score keeps its penalty parameter
(anti-over-deletion). A private _jaccard in beat_select.py is an UNRELATED
same-named helper (beat overlap) — the tombstone's sweep is public-names
across src/ + module-scoped for the private name.

**D-i (the panel's unanimous cliff):** the under-fill fallback gained its own
floor — UNDERFILL_REFUSAL_FRACTION = 0.5. The soft floor STAYS for honest
near-misses (§8.3; the well-liked 62-68% base days ship disclosed); a
best-possible day under HALF the ask now REFUSES naming what binds. `open`
end-hardness (zeroed band floor) is exempt by construction. Proven three ways:
the new hermetic starvation node (rich far corpus + 6-min leg cap → refusal
naming "walking-leg cap"; open → ships), the resurrected preview-contract
AC-24 pin (lone anchor at 60 min → 422 again), and the near-miss arm shipping.
**D-ii:** the repair's empty-exit refusal distinguishes starved from overrun —
with a leg cap set and everything under the floor, the reason names the cap
and reports the LONGEST day that fits (max, not min); the false "overruns"
sentence can no longer print over undershoot numbers.

**Written decisions:** the preview-contract "required 3240-3960s" literal
updated to 3240-3600s (the repair's ceiling is THE REQUEST; the old number was
the deleted 1.10 band). Two certification pins re-derived — the ship-short pin
now proves BOTH arms (65% ships disclosed / 22% refuses honestly) on one
corpus; the ceiling pin's fixture remainder raised from 5 min (17%, collateral
refusal) to ~60% so it tests the ceiling again.

**Proof:** tombstone + starvation nodes RED→GREEN; undo (scoped stash of
selection.py) → RED → pop → GREEN. Suites: preview-contract 8, promises 16,
clock 24, party 27, feasibility 15, one-engine 12, authoring-from-route 7,
cert 21, visit-time 11, routing 56, lint clean. test_one_time_currency.py's 3
reds are INHERITED (proven: zero occurrences in this session's diffs; same 3
fail at clean HEAD via full stash cycle) — a name-hygiene guard hitting
legacy-schema mappings + historical comments; owned by a later phase's
re-derivation, left red. Full test_tour_selection.py sweep running at
close-of-step; result recorded below.

## S4.6 — DONE (main, me): the dials on the wire, engine to edge

**Engine (contract + selection + options):** four additive TourInput axes per
the W4.2 rulings — stop_density ("more" resolves to the proven 20-min stop
ceiling in resolve_party_axes, explicit wins; "fewer" = the bounded concentrate
pass after the repair: drop weakest unprotected stops, never <3, never below
0.55× nominal so a dial can't steer into its own underfill refusal, promises
never dropped), narration_density (scales the ONE emission ceiling at
build_poi_beat_plans_capped — 135s/270s/405s — threaded into
served_dwell_seconds at all three pricing sites so certified and served stay
one quantity; trimmed beats land in keep-exploring overflow), avoid_queues
(TWO tiers, measured in this step's own test: a 0.4 score dim LOSES to a 10×
proximity edge, so peak ≥20 min queues leave the dwell pool entirely — Théo
refuses the stand, not asks it be less likely — while 10–19 min doors dim
through the rain's score channel), category_minus (dwell-pool exclusion beside
the clock filter; vignettes untouched; disclosed at the wire). Route gained
planned_queue_seconds + visit_goes_inside, priced at THE one arrival
accumulation — which was widened in place to yield the minute-precise arrival
clock (4-tuple; 8 unpack sites updated), giving Promise its
arrives_hhmm/departs_hhmm windows with no second arithmetic.

**Wire (models + routes + interleave):** both request models gained the full
dial + party surface (S1.3a precedent; hyphenated wire presets and weather
"auto" normalized at the edge — the S4.7 agent's flagged mismatch);
_dial_kwargs is the ONE mapping for all three construction sites; "auto"
weather resolves through the fail-open forecast door; RouteOptionStop carries
queue_minutes + goes_inside off the Route's own maps; TripPreviewResponse
carries promises (TripPreviewPromise: kind/name/window/door-side/wait),
day_notes (closed doors verbatim + dial exclusions said back from the request
+ unverified hours NAMING the stops, Paulo's wording), slack_minutes.

**Proof:** tests/test_tour_dials.py 7 passed (carry, resolver, category swap,
queue flip incl. its measured proximity finding, concentrate incl. the
no-shaving assert, emission ceiling incl. overflow, wire normalization);
preview-contract 8 passed (exhaustive key set extended as a written decision);
promises 16, clock 24, one-promise-pricing 21 (two comment rewordings after
its text-needle guard rightly barked); lint clean. UNDO: scoped stash of
contract.py → carry node RED → pop → GREEN.

**Deliberate scope notes:** the harness gained no new dial flags — the
workbench is the dial surface this phase (the harness keeps its Phase 1–3
axes); promise windows are coarse HH:MM (F&D's ruling), computed only on dated
days. The S4.7 workbench agent shipped in parallel (21/21 static-wiring tests,
mutation-proven; ten dials, one-body replay, honesty surface rendering).

## S4.9 — DONE (worktree track, commit 87e0bdfb on its branch, merge at close)

The phone takes the one day: flavour sheet + RouteOption models deleted;
compose {tripId}-opt1 direct; flavour_count parsing kept; typed 409
(already-composed proceeds — the agent's argued deviation, test-pinned);
refusal message "This day couldn't be written. Try generating again." on the
existing error card. make flutter-test 208 passed / 0 failed / 0 skipped;
flutter-analyze clean. ENVIRONMENT LANDMINE flagged by the track: today's
Playwright self-repair installed Chrome-for-Testing 145, which hangs
flutter_tools' launcher; green bar ran under the documented
CHROME_EXECUTABLE=<playwright chrome-headless-shell> override — the close
bar's flutter-test on main needs the same override (or the launcher fix).

## W4.10 — THE KILL CRITERION: MET ON THE DEMO CELLS. And it caught a real bug.

Measured on the REAL wire (POST /trips/preview, live Paris corpus, the exact
call a workbench dial turn makes; evidence/phase4-dials/w410-dial-latency.tsv):

- **FIRST RUN found a product bug my S4.3 inherited and armed:** every dated
  ROUND TRIP refused 422 ("could not be routed on the street network") in
  ~5-8 s while the identical cells planned through the harness. Root cause,
  probed in-process: the premium gate's sanity check demanded exactly one leg
  per stop; a round trip carries the loop-home leg (legs = stops + 1). The
  old K=3 flow shared the predicate — NO test had ever pushed a round trip
  through the premium door (the harness plans without it; the API fixtures
  are one-way). Fixed (legs ∈ {stops, stops+1}); regression clause added to
  the one-day wiring node; wiring 7 passed.
- **Post-fix, all 16 dated 180-min dial cells: 4.9–8.7 s — UNDER the 15 s
  bar.** Two honest refusals where a 9-min leg cap genuinely starves a
  corridor (pr-shorter9 4.9 s, the new named-cap message). The 300-min A→B
  flagship class runs 33.6–42.2 s — over the bar, the KNOWN carried Phase-3
  driver, no regression (baseline 44.4 s); outside the demo cells, so the
  criterion's one permitted trade stays unspent.
- The dials visibly reshape days on the live corpus: skip-the-queues turns
  the 5-stop PdV day into 10 stops; no-museums into 9.

## W4.11 — DEMO D5 "turn the dial" — DONE (evidence/phase4-dials/demo/)

Real browser, real corpus, dated PdV start: city connect → dated form → plan
→ four dial turns (Shorter walks 9 · More breaks 40 · Fewer stops · Less
talking), each auto-replanning live; 6 screenshots + the final day text. The
honesty surface is LIVE on screen: "Promises: Place des Vosges", "About 111
minutes unplanned — yours.", per-stop "inside · 1 min wait"/"outside", and
the dead-notch note ("already true of this day") fired on the fifth turn,
whose replan returned a stop-identical day — exactly the panel's ruling.

**CARRIED FINDING (owner-visible):** COMPOSED extreme dials can duck under
the 50% underfill line through pass-composition (leg9+rest40+fewer lands a
2-stop 68-of-180 day): each pass respects its own floor, but they do not
compose into one final line. It lands DISCLOSED (the slack line names the
111 minutes — never the silent a-leg6 cliff), so it is carried to Phase 5's
replan work: unify the underfill line at one final gate.

## S4.8 — GREEN (resolved 2026-08-18, Part 2). Root cause was NOT the provider.

**THE HANG: an undrained pipe, not a paid retry loop.** `api_server` started
uvicorn with `stdout=PIPE, stderr=PIPE` and NOTHING ever read either — no
`communicate()`, no reader thread, `proc.stdout` referenced nowhere in the file.
Once the ~64 KB pipe buffer filled with access-log lines plus the planner's
warnings, the server BLOCKED FOREVER on its next write, mid-request. That is a
hang, not a crash: no error, no traceback, and it surfaces several steps later
as a client timeout that looks like a planner or provider fault. It is exactly
why Part 1's `curl` during the window took 79 s and why the class failed one
step earlier in a full run than it did alone (more preceding output = the
buffer fills sooner).

Fixed: the server's output goes to a FILE (`_ONBOARD_TMP/api-server.log`), which
never applies back-pressure, and the startup-failure path now PASTES the log tail
into the pytest failure — previously that output was write-only and discarded, so
a server that died at boot said nothing about why.

**Measured, same command, same tree:** before 58 passed / 3 failed with 180 s
timeouts; after **60 passed / 1 failed in 139 s**. The leading hypothesis from
Part 1 (a real billing client retrying with backoff in the subprocess) is
DISPROVEN: the premium executor is zero-retry (`sdk_max_retries: 0`) and the
blank key fails in ~1 s. The whole degraded-tour test now runs in 7.3 s.

**The 61st test was a DIFFERENT, INHERITED failure the hang had been hiding.**
`test_a_degraded_tour_shows_the_problem_panel_with_a_copy_button` asserted the
degrade would be `glue_call_failed` from `HaikuGlueClient`. It cannot be, and
never could: walk-transition glue is written at PLAN time and Block 1 plans with
`SilentGlueClient` by default (planning is free); the real `HaikuGlueClient` is
defaulted only in `generation.py`, on the compose path. On preview→author the
first thing needing the provider is per-stop authoring, which fails to
authenticate and raises, so the request falls to the Basic lane before any
transition is written. The honest degrade is `premium_unit_failed` —
"A stop failed to compose…" — component `execute_premium_plan.invoke`, carrying
the provider's own authentication error, and the panel renders all of it.

**PROVEN INHERITED, not caused by Phase 4** (§1.11 — measured, not reasoned):
scoped-stash probe back to `258933fd` (Phase 3's tree) with ONLY the pipe fix
applied — the identical assertion fails identically, same degradation row, same
auth message. Working tree restored and verified byte-identical afterwards
(22 files, 2417 insertions, 1871 deletions, before and after). The author impl
itself is one line different across Phase 4 (`**_dial_kwargs(body)`).

Test RE-DERIVED from what the path actually does (memory: tests derive from the
new design). Scenario and invariant unchanged — a REAL, uninjected degrade must
reach the screen in plain English with the technical half and a one-click copy.
Only the name of the honest failure is corrected, and the false docstring
premise ("every walk transition falls back to a template") is replaced with the
measured mechanism. Assertions now pin the kind AND the provider's own
authentication error, so it cannot pass on an unrelated degradation.

**UNDO TEST:** both `buildDegradationPanel(data)` call sites in `review.html`
mutated to `null` → RED; restored → GREEN (`review.html` verified back to
397 insertions / 142 deletions).

**CARRIED FINDING for a later phase (not Phase 4's scope, unchanged by it):**
the workbench's "Write the tour" path never exercises the real walk-transition
narrator at all — its transitions are silent by construction — while the phone's
compose path uses the real `HaikuGlueClient`. `tests/test_workbench_matches_the_app.py`
contains zero occurrences of "glue" or "transition", so nothing checks that the
two agree on transition text. This is the audio/script-parity question the owner
has raised twice, in a place no test looks.

## S4.8 — Part 1's record (superseded above, kept for the trail)

The agent's rewrite landed (its report never reached me; verified by reading
the files and running them). `make test-workbench`: **58 passed, 3 failed** —
all three in TestRealTourGeneration, the class that drives the REAL API
unstubbed.

DIAGNOSED SO FAR (each measured, not inferred):
- PLANNING IS FINE. The engine plans that exact request against the seeded
  workbench corpus in **1.0 s** (in-process probe). The page fires exactly ONE
  /trips/preview request with no console errors (replicated the test's own
  direct-.value-write interaction against the live API). The live API returns
  a correct one-day plan.
- THE FAILURE IS THE WRITE STEP. Run ALONE, the test gets past planning and
  times out waiting for /trips/preview/author at 180 s. In the full suite the
  same class fails one step earlier (at plan), consistent with the later tests
  queueing behind the first test's very slow author call on the shared
  per-class API server.
- A curl of the test API's /trips/preview during that window took 79 s and
  returned an empty-corpus refusal — the queueing symptom, not a planner
  fault (the graph is wiped when the run ends).

LEADING HYPOTHESIS, NOT YET CONFIRMED: the API the suite starts is a SUBPROCESS,
so pytest's conftest money-guard (which swaps the billing executor for the
offline one) does not apply inside it. With ANTHROPIC_API_KEY blanked, it
builds a real billing client and retries per stop with backoff — minutes.
The tests' own docstrings assume the Basic grounded lane instead.

NEXT EXPERIMENT (one, decisive): time a single author call against a seeded
test API and count provider attempts; if retries dominate, the fix is to make
the subprocess resolve the offline executor (an env pin the launcher already
has precedent for), not to loosen the test.

PHASE 4 IS THEREFORE NOT CLOSED. W4.12 (closing panel) and W4.13 (gates,
judge, commit) remain, and no commit may happen on a red bar.

# ── PART 2 (2026-08-18) — the close ─────────────────────────────────────────

Executing session resumed at the same tree (258933fd + the uncommitted Phase 4
work; verified 22→23 changed files, HEAD unchanged). Part 1's own report of the
S4.8 red is superseded above. Everything below is Part 2.

## Two wording defects found while building the panel's input (fixed, tested)

- The closure note printed "(hours: OSM)" and "closed today — seated outside
  only" — BOTH ruled failures by the W4.2 panel (Paulo). Live on the wire:
  "Marché Bastille — closed all day Wednesday (hours: OSM); closed today —
  seated outside only". Fixed at `_clock_exclusion_reason` (the doubt a
  provenance tag encoded is now said in WORDS when the table is unverified:
  ", though we could not confirm its hours"; a verified table states the
  closure plainly). New node `test_a_closure_is_disclosed_in_plain_words_and_keeps_its_doubt`
  pins the banned vocabulary out and the doubt in; UNDO (tag restored) → RED.
- The breaks dial's subtitle read "Benches and toilet stops on the plan",
  promising presence as the dial's gift; the panel locked presence as a FLOOR
  at every position. Now "How often the day pauses to sit". (workbench wiring
  21 passed.)

## W4.11 — DEMO D5 re-shot TWICE (evidence/phase4-dials/demo/, every-turn.txt)

Once after the two wording fixes, once more at the close after the panel's
fixes below (the day notes and windows had never rendered — see W4.12 fix
list). The final transcript shows, per turn: the head line WITH the longest
single walk, "Promises: Place des Vosges 11:30-12:05" (coarse), the closure
note in its honest form, the doubt naming Carnavalet, the slack line, and the
dead-notch line. NOTE for the reader: "already true of this day" prints on the
FIRST plan too — filling the dated form auto-replans (the live replan fires on
'change'), so clicking Plan the day re-requests a day the page had just
planned. Honest, not a defect.

## W4.12 — THE CLOSING PANEL. All eleven, on 34 REAL days. VERDICT: NEEDS-WORK.

Payload = evidence/phase4-dials/w412-panel-payload.txt (the panel's INPUT,
kept verbatim): 34 cells — three starts × (base + ten dial positions, BOTH
directions where locked) + the demo's stacked turns — fetched over the real
wire, live Paris corpus, dated Wed 2026-08-12 10:00. Full verdicts in the
task transcripts. By name:

- **Better off than pick-one-of-three — YES:** Camille (needs-work), Julien
  ("marginally, and it hangs on one cell"), Aiko (needs-work), F&D ("barely,
  and not because of our dial"), Greta ("narrowly, because of one cell"),
  Sofia (needs-work), Paulo ("narrowly — a yes on the default, not the
  dials").
- **NO:** Théo, Nadia, Marcus, Rosemary.
- The three new honesty elements every persona credited: `inside`/`outside`
  per stop, waits in words ("40 min wait"), and the named doubt ("We could not
  confirm opening times for Musee Carnavalet"). The Place-des-Vosges base day
  was judged the best day in the payload by six of them.

### MEASURED by me on the payload before believing the panel (§1.11)

- 17 of 30 dial turns returned a day BYTE-IDENTICAL to base (7/10 PdV, 6/10
  PR, 4/10 flagship). The wire has no "already true" flag; the workbench
  detects identity itself and prints the note (proven in the demo). So the
  screen was not silent — but a control that never moves is not a control.
- 18 of 34 cells printed no slack number ("None") — including 170-of-180 and
  270-of-300 days (10 and 30 real spare minutes).
- FLAGSHIP "Less of this today: museums": stops IDENTICAL to base, note "Left
  out today, as asked: museum." FLAGSHIP "Skip the queues": La Samaritaine
  3 min wait → 10 min wait, note "Places with long waits were left out, as
  asked." Both notes were printed FROM THE REQUEST (`_preview_day_notes`),
  never from the day.
- FLAGSHIP "Fewer stops, longer at each": freed 100 min (Vert-Galant 20 +
  Notre-Dame 80), NOT ONE surviving stop a minute longer (Tuileries 40,
  Carrousel 10, Samaritaine 38, Pont Neuf 12 — identical), 129 min to slack,
  and the day ended at "- Destination: 0 min · outside" counted as stop 5 of 5,
  promised as `finish Destination 12:50-12:50`.
- FLAGSHIP refused under a 9-min leg cap AND a 25-min leg cap with the SAME
  numbers ("about 555 minutes … 33327s") — while the un-capped day plans (6
  stops, longest walk 18 min, 47 s). And the sentence contradicted itself:
  "the longest day that fits the cap is about 555 minutes — loosen the cap,
  or ask for a shorter day" against a 300-minute request.
- PdV "More stops, shorter at each": IDENTICAL to base, Carnavalet still 47
  min — while an EXPLICIT max_stop_minutes=20 on the same request reshaped
  the day (6 stops of ≤20). ROOT CAUSE: `resolve_party_axes` (which maps
  "more" → the 20-min ceiling and expands EVERY party preset) was called by
  scripts/tour_build.py ALONE — never on the API path. The Party dropdown and
  the More-stops dial were dead on the wire while the harness worked. The
  workbench-matches-the-app suite never caught it because it stubs the plan.
- Two things the panel read as product wording were MY payload script's
  formatting, not the screen: the bracketed `promise[anchor]` tags (the real
  screen prints "Promises: Place des Vosges 11:32-12:02" — no tag, no
  "anchor") and the `REFUSED (422):` prefix. Not counted against the build.
  Paulo (re-run) was told so and re-judged on product wording only.

### FIXED IN THIS SESSION — every one RED→GREEN with an UNDO test

1. **The wire RESOLVES presets and the "more" dial like the harness**
   (`_build_tour_input` → `resolve_party_axes`; ONE door for generate /
   preview / author). Test: `test_the_api_resolves_presets_and_the_more_dial_exactly_as_the_harness_does`
   (bare construction → RED). LIVE: PdV "More stops" now 6 stops of ≤20 min
   (was byte-identical to base). Take-it-easy / family / with-luggage presets
   now expand on the wire for the first time.
2. **Slack is `asked − taken`, always an integer, zero included** (was the
   planner's under-FLOOR shortfall, null when tight). Wire + UI ("The day is
   full — no unplanned minutes."). Test: arithmetic pin in the preview
   contract (old channel restored → RED).
3. **Dial notes describe the BUILT day, never the request:** "No museum stops
   in this day, as asked." / "You asked for no museum stops; still in this
   day: Musée X." (a pin can outrank the dial); "Nothing with a wait over 20
   minutes at its busiest was considered, as asked; the longest wait left in
   this day is 10 min, at La Samaritaine." / "…; no waits in this day." Three
   tests in test_tour_dials.py; old request-based notes restored → all RED.
4. **Closure notes are true off-route:** `ClockExclusion.kept_outside` (the
   planner's pool DECISION as a FLAG — the harness had been string-matching
   "outside only" in the sentence and went silently blank when the wording was
   made plain); the wire composes the traveller's sentence from route
   membership: on-route → "we will see it from the outside"; off-route → "so
   it is not in your day". Julien's "Lapin Agile … we will see it from the
   outside" on a Tuileries→Notre-Dame day is gone. Test in test_tour_dials.py.
5. **The A→B waypoint is a finish point, not a stop:** ONE definition
   (`contract.END_B_SENTINEL_PREFIX/NAME`, read by selection, generation,
   options — it was spelled twice); the card carries `is_finish_point=True`
   and the name "Your finish point"; the screen renders "Ends at your finish
   point · about 12:50." and does not count it. Test in test_tour_options.py
   (flag dropped → RED).
6. **The longest single walk is on the wire and the head line**
   (`longest_walk_minutes`, from THE per-leg expression). Rosemary's "a
   walking budget is not one number", finally a number on the screen. Pinned
   in the preview contract's exhaustive key set + type (computation removed → RED).
7. **Promise windows are COARSE on the wire** (F&D own the ruling and
   re-judged: 11:32 is minute-fiction): arrival DOWN, departure UP to
   5-minute marks; a finish point stays one time; the planner keeps the exact
   minute for Phase 5. `_coarse_window` unit-pinned incl. midnight wrap;
   `_preview_promises` pinned to use it (verbatim copy → RED).
8. **THE SCREEN NEVER RENDERED THE NOTES OR THE WINDOWS.** `renderTourDay`
   read `p.window` (a key that never existed) and `n.text` off plain strings —
   so every closed-today line, every doubt line and every promise window the
   panel ruled for was on the wire and never on the workbench. The D5 demo had
   none of them and nobody noticed. Fixed; the browser test that let it
   through (it asserted the promise NAME only) now pins the window AND the
   note text on screen.
9. **"Already true" for the leg cap — the ruling made real.** A cap the
   un-capped day already honours cannot bind: `select_route` plans WITHOUT the
   cap first and returns that day if it fits. ROOT CAUSE of the flagship
   refusing at 25: the capped path's timebox repair can only DROP stops, and
   dropping a middle stop merges two walks into one longer walk that breaks
   the cap, so it cannot shrink an over-long day into band. Test with a
   tripwire on the bounded search's own admission check (`_insertion_legs_fit_cap`
   with a real cap = the bounded search running); short-circuit removed → RED.
   LIVE: FLAGSHIP cap 25 → 200, the same 6-stop day, 47 s (was 422 in 16 s).
10. **The refusal sentence, three worlds and plain words** (D-ii re-derived):
    starved-under-cap / band-has-a-GAP (the flagship's actual case: candidates
    on both sides of the band, none in it — now says both numbers and both
    remedies) / overrun. "walking-leg cap … binds" → "the 9-minute limit on
    any single walk is what stops it — allow longer walks, or ask for a
    shorter day". `_refusal_detail` sends the plain clause as `reason` and the
    whole engineer's line (policy id, seconds) as `technical`; the workbench
    shows `technical` small below the sentence. AC-24 pin moved to `technical`
    (the budget is still named where an operator reads it) + a ban-list on
    `reason`. Party suite's wording pin re-derived.
11. **The dead-notch line is truthful about the cap** (UI): when the day is
    identical AND the routed longest walk exceeds the cap you set, it says
    "the closest day — its longest walk is 10 min by the street route, over
    the 9-minute limit" instead of "already true". (See CARRIED 1.)

Post-fix evidence: evidence/phase4-dials/w412-panel-payload-after-fixes.txt
(the same 34 cells, re-fetched after the fixes; compare side by side).

### CARRIED — planner-depth findings the panel exposed, with the numbers

1. **The leg cap is enforced on ESTIMATED legs; the street-routed leg can land
   over.** Measured in-process on the PdV day: Carnavalet→Place des Vosges
   walk_seconds 473 (estimate, under the 540 s cap) but leg_seconds 576
   (Valhalla, over). So "Shorter walks 9" hands back the identical day with
   "longest single walk 10 min" on the head line. Fix in the W3.2 mould: certify
   the cap on the EXACT legs after routing (tighten-and-retry once). Needs a
   hermetic routing double whose exact differs from its estimate — not built
   at close; the screen tells the truth meanwhile (fix 11).
2. **"Fewer stops, longer at each" frees minutes but lengthens nothing.** The
   concentrate pass drops the weakest stops and hands the minutes to slack;
   nothing flows to the anchors (Tuileries 40/Carrousel 10/Samaritaine 38/Pont
   Neuf 12 identical before and after; 129 min unplanned). Whether the shape
   ceilings bind or redistribution is simply absent must be measured; either
   way the subtitle over-promises. Ruled behaviour (locked semantics 4):
   freed minutes flow to the anchors within shape ceilings.
3. **"More breaks" funds rests by deleting anchors and adding walking:** PdV
   walking 23→39 min, Carnavalet (47, inside) → Rue des Rosiers (25, outside),
   NO rest promise; flagship deletes the 40-min Tuileries for Hôtel Le Meurice
   15 min + an 8-min Bench. Locked semantics 2 says never lengthen the longest
   leg, never fund a rest by shaving an anchor. A replan-RELATIVE constraint
   (hold the base day's longest leg and anchors while adding cadence) — Phase
   5's replan machinery.
4. **"Skip the queues" deletes the building rather than offering its outside**
   (Théo, Camille, Aiko): Notre-Dame vanishes for a 40-min queue when the
   persona wanted the parvis; the outside-only mechanism exists (closures use
   it) but is wired to the clock, not to queues. Owner ruling needed: the W4.2
   ruling said queue-minutes penalise stop CHOICE, which is what it does.
5. **The queue and museum turns land on the same day at Palais-Royal** —
   evidence the small pool has one alternative route; the swap "worked by
   luck" (Julien, Greta).
6. **Kind-exclusion is subtractive only; no positive "more of this today"**
   (Théo, Camille). Phase 6 lens work.
7. **The talking dial is invisible on the plan reply by design** (no narration
   on THE PLAN — models/trips.py:469); "silent legs" are Phase 6's point-first
   work (selection.py comment says so). F&D/Paulo/Julien: put a talking number
   on the plan screen.
8. **Bench and toilet PRESENCE — the Phase 3 floor — is invisible on the
   surface** ("toilet" appears zero times in 34 days; "Bench" as a place name
   in a walk-past list AND as a rest promise on the same day, no location).
9. **A round trip never shows when you are back** (Marcus); the finish
   promise exists only for A→B. Finish-by hardness was not exercised by the
   payload (my cells, not the product).
10. **Closure notes for far-off places are noise** (Lapin Agile on a
    Tuileries day — now honest but still present). Filter to route-adjacent.
11. **The density refusal's own message** ("Tour density RED: fill_ratio=0.34
    …") is engineer-speak too; no persona hit it this phase.
12. **The 5-minute museum under an explicit stop ceiling** — with
    max_stop_minutes=20 (and now under "More stops"), Carnavalet seats at 5 min
    OUTSIDE (goes_inside False) — the outside price, honest, but the panel's
    "drop-not-shave" instinct will read it as a stub. Measure whether the
    outside stand at Carnavalet is worth 5 min or should drop.

### The kill criterion after the fixes
A capped turn now costs an extra plan ONLY when the cap binds (the un-capped
plan is the first answer): pr-shorter9 4.9 s → ~10 s (5.4 uncapped + capped);
pdv-shorter9 6.7 s → 14 s measured (the cap binds on the estimate); flagship
cap cells 16 s → 47 s (already outside the demo class). Under the 15 s bar on
the demo cells; the flagship class remains the carried Phase-3 driver.

## W4.13 — THE CLOSE BAR (2026-08-18), judged, then closed

**Judge (§2), first ruling: merge PROCEED after the running shard exits; commit
STOP.** Three grounds, all fair and all acted on: (1) the D5 demo on disk
predated fix 11 (the "closest day" dead-notch line) — RE-SHOT on the final
build; turn 2 now reads "the closest day — its longest walk is 10 min by the
street route, over the 9-minute limit" (evidence/phase4-dials/demo/every-turn.txt,
6 PNGs); (2) two of my inherited-red CAUSES were wrong — corrected below;
(3) two paths a "named files" commit could drop — `tests/test_tour_flavours.py`
(a DELETION) and `tests/browser_launch.py` (Part 1's shared launcher, imported by
three committed test files, untracked) — both named in the commit.

**Bar results on the final tree:**
- `make lint` — All checks passed.
- `make test-workbench` — 61 passed (148 s), workbench-final.log.
- `make flutter-test` on the phone branch's tree (`.claude/worktrees/agent-a13c7825b523f6552`
  = main's mobile/ after the fast-forward) — all tests passed (attempt 2/3;
  attempt 1 hit the Chrome launcher flake the S4.9 track flagged, the hang
  detector's retry handled it). Re-run on main after the merge — see below.
- `make dedup-review` — "No duplicated responsibility survived review."
- `make _test-python` — first full pass: 15 failed / 2872 passed (24 min).
  Triage PROVEN by scoped stash of src/ tests/ scripts/ frontend/ back to
  258933fd (the judge checked the boundary: every file this session touched is
  in those four dirs; untracked new files stayed and could only ADD reds, and
  none of the 11 is one): **11 INHERITED** — fail identically at Phase 3's
  tree: `test_claude_md_hook_claims.py` ×3 (CLAUDE.md is DELETED in the working
  tree — see the owner question below), `test_one_time_currency.py` ×3 (Part 1
  had already proven these inherited), `test_paid_test_isolation.py` ×3 (they
  read the MAKEFILE only, and the Makefile is byte-identical to the committed
  tree — so they are red AT 258933fd ITSELF; my first note blamed uncommitted
  compose changes, which the judge showed was wrong: docker-compose.yml is
  never read there), `test_tour_b_materialization.py::test_one_story_fixed_end_corpus_is_refused_not_padded_with_a_sentinel`
  (asserts "TIME band" in a refusal message that has not carried it since the
  soft-floor change), `test_tour_certification_contract.py::test_reference_manifest_has_replayable_per_document_provenance`
  (reads `specs/2026-07-13-compose-correct-dont-reject/05-plan.md`, deleted in
  the working tree). **4 PHASE-4-OWNED, re-derived as written decisions and
  re-run GREEN individually:** `test_tour_selection.py::test_fixed_end_red_start_circle_defers_to_routed_fixed_end_checks`
  (the panel's D-i cliff ruling now REFUSES a 6-min day for a 60-min ask instead
  of shipping it disclosed — deferral is proven by WHICH refusal arrives,
  certification's, naming the shortfall — the test's own first proof before the
  2026-07 softening), `test_tour_contract.py` (Promise carries its window,
  S4.6), `test_tour_promises.py::test_shape_column_renders_in_out_and_closed_out`
  (fixture sets `kept_outside=True` — the harness reads the flag), and
  `test_trip_models.py::test_preview_response_carries_only_what_planning_knows`
  (the exhaustive field set = the honesty surface: promises, day_notes,
  slack_minutes, longest_walk_minutes). A full re-run of the shard on the final
  tree was started before the judge and its result is recorded below.

**OWNER QUESTION (raised, not acted on):** `CLAUDE.md` and `AGENTS.md` are
deleted in the working tree. On 2026-08-11 (this session's first process) both
were MODIFIED, not deleted; at this process's start (2026-08-18 11:08) both were
deleted, and the judge measured the repo root's mtime at 11:08:32 today. This
session never deleted them. I have NOT restored them (three inherited reds in
`test_claude_md_hook_claims.py` are the visible consequence). **OWNER RULED
(2026-08-18): deleted deliberately — the files were written for Opus 4.8 and
with Opus 5 "only caused Claude to spin and lie". Not to be restored; the three
tests that read CLAUDE.md pin a retired artefact and go with it.**

**Judge (§2), second ruling (a fresh judge; the first stalled after a grep,
its last note "partially staged files would commit a half-state" — checked:
`comm -12` of unstaged-vs-staged was empty): PROCEED, two binding conditions —
commit the INDEX ONLY (no -a, no paths; the tree carries 181 unstaged
deletions including CLAUDE.md and AGENTS.md), and do not push. It verified
lint itself, the 31-path staged set, the launcher + its three importers, the
count reconciliation (2872+15 = 2876+11 = 2887), and the demo's freshness by
the source mtimes (my "after 13:00" was wrong — 12:51, still after the 12:37
fix boundary; noted so I stop guessing timestamps).

**COMMITTED: `973982fb`** — 31 paths (10 src/scripts/frontend, 21 tests incl.
the flavours→options move and the launcher), on top of the fast-forwarded
S4.9 phone commit `87e0bdfb`. `git status --porcelain -- CLAUDE.md AGENTS.md`
still prints two ` D` lines: deleted in the tree, NOT in the commit. NOT
pushed (the judge's condition; the owner pushes).

**Amend-and-carry:** all thirteen Phase 4 boxes ticked in
04-implementation-plan.md with an "AMENDED AND CARRIED AT CLOSE" note (six
deviations); **Phase 5 re-planned at step level** (D5.0 → W5.15, ~70 long
lines under the PHASE 5 stub), against `973982fb`, with the whole mobile
session surface read in full at that moment (a plan defect logged there: the
stub's read list omitted `tour_playback_service.dart`, the phone's actual
session loop). Nothing under specs/ deleted.

PHASE 4 CLOSED (2026-08-18).

## TEST CULL (2026-08-18, owner ruling: "Act on this" — the keep/remove table)

Applied to the 186 test files, exactly per the table:
- **Removed — tests of Claude's own instruction files:** `test_extract_refuse.py`
  (5, the wording of a slash-command prompt), `test_render_deploy_watch_hook.py`
  (5, an agent hook script), and the one preflight node that read that hook.
  (`test_claude_md_hook_claims.py` went in the previous commit.)
- **Removed — pins on research artefacts under specs/:** `test_tour_batch_review_runner.py`
  (14), `test_tour_live_route_summary.py` (5), `test_tour_batch_regression_manifest.py`
  (3), `test_tour_live_request.py` (1), `test_premium_authorities.py` (1),
  `test_tour_certification_contract.py` (10 — incl. the inherited red that read a
  deleted plan), `test_tour_authoring_extraction.py` (5 — a one-time refactor proof
  plus a ledger read). The two calibration manifests the 99-test certification
  suite reads MOVED `specs/2026-07-21-tour-certification/` → `fixtures/tour-certification/`
  (the reference-tours precedent); suite repointed (117 nodes passed) and
  `scripts/tour_batch_review.py` repointed.
- **Tooling & hygiene, split:** removed the Makefile-SHAPE checks
  (`test_make_test_is_the_only_exhaustive_executor`, `test_makefile_has_no_legacy_environment_or_split_database_targets`,
  `test_every_make_target_is_phony_and_documented`; suite-shape
  `test_every_test_file_is_reachable_from_the_definitive_suite`,
  `test_no_test_file_is_empty_of_tests`); KEPT the incident guards — never spend
  (paid_test_isolation's live-shard/scrubbed-keys/no-dotenv nodes), never wipe
  (`test_database_reset_cannot_address_cloud_or_all_compose_volumes` RE-DERIVED to
  the current one-local-DB recipe instead of its stale volume literals — it is a
  data-loss guard, and it was red only because the recipe got safer), the lock
  file, conftest isolation, dev-env, `test_launchers_kill_only_listening_sockets`.
  `test_preflight.py`: SPLIT the same way on the owner's "try again" — 14
  Makefile-declaration checks removed (every ## target declares a preflight
  line, every declared name is real, render-key declared, server targets
  declare ports, routing targets declare valhalla, exempt/conditional targets,
  the PREFLIGHT command spelling, the reusable-set contents, the full-suite
  union); 57 behaviour tests of the tool kept (probes never infer success from
  silence, repairs that do nothing are caught, a live server is never killed,
  a foreign process is named not killed, the CLI resolves a target, it runs on
  the system interpreter). Same rule applied to the two Makefile-shape reads I
  had first kept: `test_golden_probe_marker_is_emitted_by_both_goldens` and
  `test_manual_workbench_starts_routing_for_the_preview` — removed. The
  `.claude/rules/testing.md` paragraph and the preflight file header that
  described the removed guards were corrected (prose must not promise a guard
  that is not there).
- **Deploy incident guards:** untouched.
- **"Grep the source" guards:** `test_tour_one_engine.py` RETIRED (nine
  deleted-stack tombstones + a name sweep); its ONE behavioural test (a band
  refusal reaches both surfaces as a 422 with alternatives) rehomed in
  `tests/test_trip_preview_contract.py` — parts 1–2 behavioural, part 3 kept
  structural with its reason stated (no hermetic generate path exists), part 4
  dropped because the same invariant is now proven on a REAL 422 by the
  ban-list on `reason`. `test_one_time_currency.py` retired (pure name-grep,
  the 3 inherited reds). `test_premium_workbench_wiring.py`: the four
  `inspect.getsource` greps removed, the launcher-kill guard, the routing-
  provisioning check and the Block-1 behavioural test kept. `test_workbench_preview_wiring.py`:
  14 static HTML scans removed where a real-browser twin exists (checked one by
  one against `test_workbench_ui.py`); the five lens-validator unit tests, the
  provider-registry test and the plan-time-degradations check (no twin) kept;
  the two `city_slug` scans replaced by ONE assertion on the real request the
  browser sends (`test_tour_preview_ab_destination_sends_end_and_renders`).
  KEPT as incident guards with no behavioural twin: `test_no_doubles_on_human_surfaces.py`
  (doubles reached humans — the founding incident), `test_lens_drift.py`,
  `test_area_conventions.py`, `test_workbench_deprecate_guard.py` (real browser).
- **The one genuine product test with a stale message** (`test_tour_b_materialization::test_one_story_fixed_end_corpus_is_refused_not_padded_with_a_sentinel`,
  asserted "TIME band") re-derived to the plain refusal.
- Four comments in src/tests that claimed a now-retired test "pins"/"prevents
  drifting" corrected — prose promising a guard that is not there is the exact
  pattern the CLAUDE.md test was born from.
- Phase 5's step-level plan amended: the two seams no longer cite the retired
  moulds; behavioural where possible, source scan only for an absence-of-code
  invariant, stated in the docstring.

Net: 11 test files gone, ~71 nodes removed from 7 more, 1 test moved, 2
manifests moved, 2 tests re-derived. Bar after the cull: recorded below
(the second pass — preflight, golden, wiring — re-ran its three files green:
57 + 3 + 2; deletions only, no other file touched).
Bar after the cull: `make lint` clean · `make _test-python` **2594 passed, 0 failed**
(the first fully-green shard in the project's record; 2887 → 2594 nodes) ·
`make test-workbench` 61 passed (with the new real-request city_slug pin) ·
`test_tour_quality_certification.py` 117 passed against the moved manifests.
