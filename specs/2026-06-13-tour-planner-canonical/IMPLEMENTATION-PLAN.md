# Ondoway Tour Planner — Implementation Plan (atomic, test-first)

> Companion to `ALGORITHM-SPEC.md`. **This plan exists to make "lots of untested code" impossible.**
> Every step is ONE specific change shipped with ALL of its tests, proven by a runnable command whose
> output is pasted, and committed on its own so any step can be reverted.

---

## Working agreement (the contract I hold myself to)

1. **One step at a time.** I do exactly one step, then stop. I do not start the next step until the
   current one is green and you've seen the proof.
2. **Test-first / test-with.** No production change lands without its test in the *same* step. If I
   can't describe the test, the step isn't ready and I don't write the code.
3. **Tests at every level the change touches:** unit (pure logic), integration (DB/API wiring),
   functional (end-to-end through the running app), and a manual checklist where a human must look or
   listen. Each step lists exactly which apply and why any are N/A.
4. **Proof is pasted, never claimed.** I run the proof command and paste the real output. "This should
   work" is never evidence — a green run is. If it fails, you see the failure.
5. **Green baseline first** (Step 0). Never start work on a red bar.
6. **Scope is the step.** A step touches only the files it names. No drive-by edits. If I find
   something else, I note it — I don't fix it inside this step.
7. **One commit per step**, message = the change only (no attribution). Revert = `git revert <sha>`.
8. **`make lint` = 0 errors and `make test` green** before any commit. The repo's hooks enforce this;
   so do I.
9. **You can stop me anytime.** If a step's diff or output looks wrong, we revert that one commit and
   nothing else is affected — that's the whole point of atomic steps.

### The bar
- `make test` = full Python (local Neo4j 7688) + Flutter — the commit bar.
- `make test-local` = Python suite (clears `__pycache__`) — the per-step iteration bar.
- `make test-unit` = pure Python, fastest — for pure-logic steps.
- `make test-golden` / `make tour-grade` = live-DB golden + grade gates (separate, not in `make test`).
- Manual/functional = `make flutter-ios` or the dev server, with an explicit observe-this checklist.

### Step template (every step below follows it)
```
Step N.x — <the one change, in a sentence>
  Change:   <exact file(s) + what>. Smallest diff that works.
  Tests:    unit:   <assertion(s)>            (or N/A + why)
            integ:  <assertion(s)>            (or N/A + why)
            funct:  <assertion(s)>            (or N/A + why)
            manual: <what a human verifies>   (or N/A + why)
  Proof:    <make target>
  Done when: proof is green AND pasted (AND manual confirmed where listed).
```

---

## Step 0 — Green baseline (no code)
  Change:   none.
  Bar that MUST be green before per-step work: `make lint` + `make test` (= test-local + flutter-test).
  RESULT (2026-06-13): GREEN — lint clean; 929 Python passed; 177 Flutter passed; 0 failures.

  Tracked-but-NOT-blocking (PRE-EXISTING this session — proven: the only commit, 94436ee, was docs-only):
  - `make test-golden`: test_tour_golden_{ile,pdv} assert 90% beat-overlap vs the HUMAN-IDEAL fixtures
    (currently ~56%). Aspirational targets ("do NOT re-baseline" — prior M0c); they track the
    engine→ideal gap, they are NOT a regression gate.
  - `make tour-grade`: the grade rubric PASSES (both goldens clear baseline 0.65; broken-golden detected),
    but `test_flagship_route_never_swims_the_seine` FAILS — a real, pre-existing routing-geometry red.
    Orthogonal to Phase 1 (narration→audio touches no routing); triage in Phase 2 (corridor/routing) or
    earlier if desired.
  Correction: Step 0 originally listed `make test-golden` as a must-be-green gate — wrong; the
  golden-overlap suite is a target tracker, the regression gate is `make tour-grade`.

---

## Phase 1 — The story reaches the ear (stitched narration → per-stop audio)

> Goal: stop playing one raw beat per stop; play the **stitched per-stop narration** `generate()`
> already produces. This builds the audio plumbing once; Phase 3 later swaps the *source* of the
> sentences from the deterministic stitcher to the LLM compose — same plumbing, reused not thrown away.
> Entirely offline-testable (`MockGlueClient` + mock TTS).

```
Step 1.1 — Pure: group a Script's sentences into per-stop narration text.
  Change:   new pure fn stop_narration_text(script) -> dict[int,str] in src/tour/ (concatenate
            Script.script Sentences by stop_idx, in order, glue included). No DB, no audio.
  Tests:    unit: fixture sentences [(s0a,stop0),(s0b,stop0),(s1a,stop1)] → returns
                  {0: "s0a s0b", 1: "s1a"} (within-stop order preserved, joined with single space,
                  glue sentences included verbatim); empty Script → {}; single-stop → one entry.
            integ/funct/manual: N/A (pure function).
  Proof:    make test-unit
  Done when: green, pasted.

Step 1.2 — Persist per-stop narration alongside beat_ids.
  Change:   extend route_script_to_stops (src/api/crud/trips.py) to carry narration per stop (from
            1.1); add narration:str to ItineraryItem write in create_trip_with_stops. Additive —
            beat_ids/primary_beat_id untouched. (Neo4j is schemaless for node properties — no migration.)
            Signature: route_script_to_stops(selected_pois, beats_by_id, start_time, *,
            script: Script | None = None) — back-compatible (existing positional callers unaffected);
            when script is passed the fn calls stop_narration_text(script) and attaches per-stop narration.
  Tests:    unit:  route_script_to_stops returns narration per stop from a hand-built Route/Script
                   (no DB), aligned to sort_order.
            integ: create_trip_with_stops writes narration; read-back equals input (local Neo4j).
            funct/manual: N/A (no UI yet).
  Proof:    make test-local
  Done when: green, pasted.

Step 1.3 — TTS a stop's narration (not the lone beat).
  Change:   add generate_stop_audio(narration_text, ...) reusing src/audio/provider + storage +
            pipeline; MockProvider stays the test default.
  Tests:    unit:  with MockTTSProvider, the text passed to provider.generate == the stop narration
                   (assert exact string); returns a stored url + duration.
            integ: 2-stop trip via local storage + mock provider → 2 artifacts, each from its stop's
                   narration text.
            funct/manual: N/A (endpoint wiring is 1.4).
  Proof:    make test-local
  Done when: green, pasted.

Step 1.4a — Generate per-stop narration audio, keyed by STOP (not beat).
  Change:   in the prepare-trip audio path, iterate ItineraryItems and call
            generate_stop_audio(item.narration), storing each artifact keyed by the stop's
            itinerary-item id (today audio is keyed by beat_id — this re-keys to stop). Server-side only.
  Tests:    integ: POST generate → POST prepare-trip-audio (mock provider) → one artifact per stop;
                   each artifact's source text == that stop's narration; count == number of stops.
  Proof:    make test-local
  Done when: green, pasted.

Step 1.4b — Serve per-stop audio status + url by STOP.
  Change:   the audio status/serve lookup returns has_audio + audio_url per stop (itinerary-item id),
            alongside (not breaking) the existing per-beat lookup.
  Tests:    integ: after 1.4a, the per-stop status lookup → has_audio true + a url; before generation →
                   has_audio false.
  Proof:    make test-local
  Done when: green, pasted.

Step 1.4c — Backend: surface stop_id + per-stop audio in GET /trips.  [DONE 165f252]
  Change:   list_trips_for_profile returns item.id AS stop_id and coalesce(item.audio_url, pb.audio_url)
            (+ duration); GeneratedStop gains stop_id — so the client can ADDRESS a stop and read its
            per-stop narration audio. (Discovered mid-1.4: the read path exposed neither.)
  Tests:    integ: after generate-trip-stops, GET /trips exposes stop_id + the per-stop 'stops/...' url.
  Proof:    make test-local → 948 passed, 0 failed.

Step 1.4d — Mobile polls + plays the per-stop narration audio.  [CODE-COMPLETE 2026-06-14 — on-device listen pending]
  Change:   point the itinerary flow at the per-stop endpoints (POST generate-trip-stops + GET
            stop-status/{stop_id}) and play the per-stop url, instead of per-beat.
  Atomic sub-steps (each one change + its tests; make flutter-test green + pasted):
    i   — ItineraryStop.stopId parsed from GET /trips. [af5da10]
    ii  — TripService.confirmTripStopAudio -> POST /audio/generate-trip-stops/{tripId}. [a647bd1]
    iii — AudioService.checkStopAudioStatus -> GET /audio/stop-status/{stopId}. [7c2cf55]
    iv  — TourPlaybackService plays/keys by stopId ?? beatId (one helper feeds play + completion). [cf3dd42]
    v   — trip_itinerary_page prepare flow: confirm + poll + prefetch all per-stop; page test now
          authenticates so it actually verifies both per-stop endpoints are hit. [5f6f6f2]
  Bar at close: make test -> 958 Python + 186 Flutter, 0 fail; make lint clean.
  REMAINING (user gate): make flutter-ios -> generate a Paris trip -> Confirm & Prepare -> CONFIRM
  each stop plays the multi-sentence stitched narration (cold-open -> beat -> transit -> beat ->
  closing), not a lone fact.
  Tests:    funct: dev server end-to-end → the app receives a per-stop narration url for every stop.
            manual: YOU run make flutter-ios, generate a Paris trip, tap Confirm & Prepare, and CONFIRM
                    each stop plays multi-sentence narration (cold-open → beat → transit → beat →
                    closing), not a lone fact. (I run the app + paste logs; the listen is yours.)
  Proof:    make flutter-test + the manual checklist above.
  Done when: funct green + pasted AND you confirm the listen.
```

**Phase 1 status:** 1.1 (e54dbb9) → 1.2 (2b9686c) → 1.3 (7e04c40) → 1.4a (9ad2f82) → 1.4b (7551e2b)
→ 1.4c (165f252) → 1.4d-i (af5da10, mobile model: stopId) DONE.
**Phase 1.5 status (2026-06-14):** 1.5a (691e5fc) → 1.5b (fff4120) → 1.5d (60c6443 preview endpoint +
f4b2ce8 standalone page) → 1.5c (d5be060, live audio-says-the-story gate `make tour-audio-gate`) DONE.
NOTE: 1.5c landed AFTER 1.5d (preview built first; the Whisper gate followed). Audio-infra fix during
1.5: 4659643 (chunk long narration for TTS). REMAINING: 1.5e (workbench integration) — in progress.
**REORDER (2026-06-13, user):** verify narration **WEB-FIRST** (Phase 1.5 below) before finishing the
mobile cluster — the narration is backend output; web verification is hours + agent-drivable vs days of
mobile build + a human on-device listen. Mobile **1.4d-ii/iii/iv are PAUSED** pending Phase 1.5.

**Audio-infra fixes (surfaced during 1.4 while getting the bar green — root-caused, not skipped):**
- d8d5b59 — TTS providers retry transient timeouts (real resilience gap + intermittent functional failure).
- 8c0ee75 — WER `_normalize` folds accents (Whisper strips diacritics; fair eval, threshold unchanged).

**Phase 1 delivers:** a real, continuous, audible tour — the single biggest gap — with no new
algorithm, no LLM, no destination work. The stitched narration is a genuinely shippable interim (a
real story, voiced); Phase 4 swaps the *source* of the sentences to the LLM compose using the *same*
audio plumbing.

---

## Phase 1.5 — Web-first narration verification (reorder, decided 2026-06-13)

> The narration is BACKEND output; mobile + web are both consumers. Verifying the stitched per-stop
> story on web is hours (mostly agent-drivable) vs days of mobile build + a human on-device listen.
> Web-first catches stitcher/TTS bugs once, before mobile. It does NOT replace on-device mobile
> verification (GPS, background audio, the real walk) — it precedes it.
> Decisions (user): build a STANDALONE preview page first (POC); if it works, integrate into the
> WORKBENCH (the human tester's surface). **Automate as much as possible** — keep the human to the one
> subjective call (does it sound like a tour).

Step 1.5a — Expose narration text in GET /trips.  [DONE 691e5fc] [enabler — nothing can show the story without it]
  Change:   add narration:str|None to GeneratedStop; add `item.narration AS narration` to
            list_trips_for_profile RETURN.
  Tests:    integ: after create_trip_with_stops(narration=...), GET /trips returns each stop's narration.
  Proof:    make test-local.

Step 1.5b — Automated narration-coherence check (agent-drivable).  [DONE fff4120]
  Change:   a test that generates a real Paris trip and asserts each stop's narration is well-formed —
            non-empty, multi-sentence, opens (cold-open/SYNTHESIZED_OPENER) and closes (GLUE_CLOSING):
            the stitcher didn't drop/empty/mis-order stops.
  Tests:    the check IS the test (live Paris graph; mark golden-style if it would dirty the hermetic bar).
  Proof:    make test-local (or a dedicated target).

Step 1.5c — Automated "audio says the story" gate (live OpenAI; functional).  [DONE d5be060 — landed after 1.5d; `make tour-audio-gate`, WER<0.15 on real stitched stops]
  Change:   voice a sample tour's stops → Whisper-eval each MP3 vs its narration (reuse src/audio/eval.py)
            → WER gate. The strongest automation; runs unattended.
  Tests:    functional (live key); marked live/opt-in, not in the hermetic bar.
  Proof:    the functional run, output pasted.

Step 1.5d — Minimal standalone preview page (POC; the one human-facing piece).  [DONE 60c6443 + f4b2ce8]
  Change:   frontend/tour-preview.html: form (lat/lng/duration/profile) → POST /trips/generate →
            POST /audio/generate-trip-stops → GET /trips → render per-stop narration text + <audio>.
  Tests:    thin UI smoke (loads + wires the already-tested endpoints); the subjective listen is YOURS in
            a browser tab (seconds, not an iOS build).
  Proof:    page loads + plays; you confirm it sounds like a tour.

Step 1.5e — Workbench integration (AFTER the POC validates; for the human tester).  [DONE 2026-06-14]
  Reuses review.html's existing TTS audio player + the Phase-1.5 endpoints.
  Atomic sub-steps, each one change + its real-browser tests (Playwright via `make test-workbench`):
    0 — make the suite bite: fatal _safe_assert + de-vacuumed stale guards (caught real upload bug). [c72ba0c]
    2 — extract shared ttsPlay core from ttsPlayBeat (tour stops reuse it). [37e4357]
        + parallel bug-fixes folded in: beats-fetch city_name + Eiffel conflict seed. [b2e5ece, 6e54dbc]
    3 — Tour Preview view: toolbar button + native tour form in the existing detail pane. [6f13179]
    4 — Generate -> POST /trips/preview -> render stops -> play each via shared ttsPlay (real decode);
        422 surfaces an error toast. [2aac9c3]
    5 — playback edges: cache replay (no refetch) + no listener stacking + long narration (chunked). [4d3046f]
    6 — seamless (tour view <-> POI, no state leak) + full-bar regression. [bfbb2bf]
  Bar at close: make test-workbench -> 33 passed, 0 xfailed; make test -> 958 Py + 178 Flutter, 0 fail.

Then RESUME mobile 1.4d-ii/iii/iv, where the on-device listen is a final smoke test, not the QA gate.

---

## Phase 2 — A→B corridor (destination, B optional)  [DONE 2026-06-30]

> **STATUS: COMPLETE.** 2.0a Seine-gate valhalla dep (05515ce) · 2.0d end=None identity baseline
> (377f488) · 2.1 TourInput.end (98e3d97) · 2.2a feasibility refusal gap+loop+extend (7bf4079) ·
> 2.2b closer_b wedge (034325f) · 2.3 corridor time-ellipse (1a36cf5) · 2.4 feed-B hybrid
> snap/sentinel (d742398) · 2.5 open-walk B* proof (4708ee6) · 2.6 API end_lat/lng + structured 422
> (c768193). Workbench: destination input + route-on-map + structured refusal (de9cdfb, ff00f1b).
> The Seine "red" was a Valhalla-down/haversine artifact — resolved. Live-proven: a 120-min A→B
> returns a directional route ending exactly at B; a 90-min A→B returns 422 {gap, loop, extend,
> closer_b}. Gates: make test 1048; test-workbench 36; tour-grade 4; make lint clean.

> Pure engine + input. Unit- and golden-testable without audio or LLM. Each step keeps existing
> behavior identical when `end is None` (proven by Jaccard==1.0 against current goldens). NOTE: these
> steps ADD the `end` field + corridor logic that do not exist in the code today — that absence is the
> work to be done here, not a defect in this plan.
>
> **Gate phasing (important):** Phase 2 adds A→B *geometry only*. The hard tier gate
> (`ANCHOR_TIERS={3,4,5}`) and lens-miss exclusion are **still active** through Phase 2 — the
> spotlight / "never exclude" model removes them in **Phase 3**. So a Phase-2 A→B tour still excludes
> tier-1/2 and off-lens POIs; that is expected and not a contradiction with the spec's target §3.

```
Step 2.1 — Add end to TourInput.
  Change:   end: tuple[float,float] | None = None on TourInput (+ latlng validator); frozen/extra=forbid.
  Tests:    unit: valid end ok; out-of-range lat/lng raises; None ok; round_trip+end raises (mutually
                  exclusive); model_dump round-trips; lenses edge cases (empty list → None; duplicates +
                  whitespace normalized) still hold.
  Proof:    make test-local
  Done when: green, pasted.

Step 2.2 — Feasibility refusal + COMPUTED alternatives when t(A,B) > budget.
  Change:   in select_route, if end set and routed t(A,B) exceeds the walk budget → raise
            TourabilityRefusedError carrying the gap AND three computed alternatives:
            extend_to = max_supportable_duration_min; loop_from_A; closer_B (highest-spotlight anchor
            toward the A→B bearing with t(A,B')<=budget). BEFORE selection. Alternatives are computed,
            not canned strings.
  Tests:    unit: far A→B + short budget → raises; the raised error carries extend_to (== the density
                  max_supportable_duration_min), a loop option, and a closer_B whose t(A,B')<=budget;
                  within budget → proceeds; end=None → never triggers.
  Proof:    make test-local
  Done when: green, pasted.

Step 2.3 — Corridor (time-ellipse) reach filter when end is set.
  Change:   candidate predicate uses t(A,poi)+t(poi,B) ≤ budget bound (haversine fallback now;
            isochrone reuse later). end=None path unchanged.
  Tests:    unit: POI on the A–B line admitted; far-off-axis POI rejected; end=None → identical pool
                  to today on a fixture.
            golden: existing goldens unchanged with end=None (Jaccard==1.0).
  Proof:    make test-local + make test-golden
  Done when: green, pasted; any golden delta is end!=None only and explained.

Step 2.4 — Feed B as fixed_end to the ORDER step.
  Change:   select_route passes end (or synthesized B*) as held_karp_open(fixed_end=...).
  Tests:    unit: directional route's last stop == B; round_trip ends at A; open walk ends at far B*.
            golden: end=None goldens unchanged.
  Proof:    make test-local + make test-golden
  Done when: green, pasted.

Step 2.5 — Open-walk endpoint B* (no destination, no loop) = the EXISTING endpoint-pull.
  Change:   verify the existing _apply_endpoint_pull already feeds its far anchor as
            held_karp_open(fixed_end=B*) for end=None / non-loop; thread it explicitly ONLY if a gap is
            found. No new selection algorithm — this step proves endpoint-pull serves as B* and composes
            with 2.3/2.4.
  Tests:    unit: open walk (end=None, round_trip=false) → route ends at the far high-spotlight anchor;
                  loop (round_trip=true) → ends at A; the corridor filter from 2.3 is inactive when
                  end=None (pool identical to today — Jaccard==1.0).
            golden: end=None goldens unchanged.
  Proof:    make test-local + make test-golden
  Done when: green, pasted.

Step 2.6 — API accepts end_lat/end_lng + structured 422 refusal body.
  Change:   TripGenerateRequest gains optional end_lat/end_lng; thread into TourInput. Serialize
            TourabilityRefusedError to a 422 body {reason, gap_minutes, alternatives:[{kind:
            "extend"|"loop"|"closer_b", ...}]} (today the handler at src/api/routes/trips.py:138-143
            returns a PLAIN STRING — this replaces it). (lens_coverage_note is NOT added here — Phase 3.)
  Tests:    integ: A→B request → route ends at B; over-budget A→B → 422 whose JSON body matches
                   {reason, gap_minutes, alternatives} with the kind enum enforced; no end → unchanged.
            funct: dev server A→B Paris request returns an A→B route whose LAST stop == B.
            manual: N/A until the preview UI (Phase 4) — noted.
  Proof:    make test-local
  Done when: green, pasted.
```

**Phase 2 delivers:** real directional A→B tours (and the loop/open cases), proven not to regress the
existing non-directional behavior.

---

## How the phases map to the canonical UX examples

The four canonical UX examples describe the **complete product**. No single phase delivers all of any
one example — that is by design, not a gap:

- **Phase 1** — audible stitched narration per stop (a real, continuous, voiced story).
- **Phase 2** — A→B / open / loop geometry (the corridor + feasibility refusal).
- **Phase 3** — spotlight model: vignettes, lens-as-genre, per-corridor coverage note, `band`/`spotlight` fields.
- **Phase 4** — LLM-composed narration, reflections, two-step preview/compose, flavour picker.

So Example 1 (Eiffel→Arc *with a mid-walk reflection*) is fully realized only **after Phase 4**; Example 4
(refusal) lands in **Phase 2**; Examples 2–3 (open/loop) in **Phase 2**, gaining texture in Phase 3.

## Deferred clarifications (lock these when atomizing the named phase)
From the adversarial review — non-blocking for Phase 1–2, resolve at the phase that owns them:
- **Reflection placement (Phase 4):** which long leg gets the reflection when several qualify
  (rule: prefer the longest leg / the one after the highest-spotlight cluster; never two in a row).
- **Vignette temporal placement (Phase 3):** a vignette fires as the walker passes within ~Xm of the
  POI on the polyline; voiced inside the leg's narration. Lock the radius + dedup at Phase 3.
- **Lens-coverage-note content (Phase 3):** the note states, per requested lens, how many corridor
  stops carry a matching beat (and the broaden-the-lens prompt). Lock the exact copy at Phase 3.

## Phases 3–5 — milestones (atomized on arrival)

> Deliberately NOT pre-atomized to the same line-level detail yet: doing so now would churn a plan for
> work that sits behind Phase 1–2, and the right step boundaries depend on what we learn there. Each
> milestone WILL be broken into the same one-change-+-all-tests steps **before any code in it is
> written**, with your sign-off on the step list. That is a commitment, not a corner cut.

- **Phase 3 — Spotlight model.  [DONE 2026-06-30]** Replaced the tier gate + lens-miss exclusion with
  the continuous `gravity × lens × proximity` spotlight (LENS_FLOOR, no gates); emit the vignette band;
  measure per-corridor lens coverage. Atomized + shipped: 3.1 pure spotlight scoring (95048e2) · 3.2
  band classifier (78b0841) · 3.3 band/spotlight/lens_coverage_note contract fields (efa70b7) · 3.4
  populate them on stops (ba87d83) · 3.5 gate removal + **calibrated golden re-baseline** (6d0a409).
  **Calibration decision (user-approved "tune"):** the dwell floor `BAND_THRESHOLD_SHORT` sits at
  tier-3 gravity (3.0) so no-lens tours preserve the tier≥3 anchors the human-ideal goldens were built
  on — the goldens HELD (Île 53.2%, PdV 66.7%), tour-grade 4/0. Low-tier/off-genre POIs are eligible
  VIGNETTES, not dwell stops (§3 "allocate scarce dwell-minutes"). Workbench surfaces lens_coverage_note
  + per-stop spotlight (7112be0). Also fixed a transient live-audio flake with regenerate-on-degraded
  retry (13bfe3a, complements the earlier 0860da9 network retry). Gates: make test 1048; test-workbench
  36; test-golden held; tour-grade 4; make lint clean.
- **Phase 4 — Reflections + LLM compose + two-step API.** `GLUE_REFLECTION` + audio-deficit placement;
  swap the narration source to fire-once Anthropic compose behind VERIFY (Mock stays the test default);
  split `preview` / `compose`; mobile flavour picker. Tests: recompose-once-then-block control flow,
  fabricated-sentence caught, compose called exactly once on the pick, audio fires only after VERIFY
  passes, manual listen for reflections on long legs.
- **Phase 5 — Grading honesty (optional, off critical path).** Keep the regression gate; optionally add
  an LLM-judge satisfaction rubric on a held-out set. Tests: gate fails on a deliberately-broken
  golden, passes on the corpus.

---

## Disposition of superseded docs
Pending user confirmation (recorded here once decided): `ondoway-tour-algorithm.html`,
`specs/2026-05-23-tour-planning-algorithm/*`, `specs/2026-06-10-tour-5phase-engine/05-plan.md`,
`specs/2026-06-12-tour-algorithm-decision/*`. All git-tracked (deletion recoverable via history).
`ondoway-journey-wireframes.html` and `ondoway-lens-defaults-spec.md` are **separate concerns — kept**.
