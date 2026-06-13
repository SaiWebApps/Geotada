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
  Tests:    run the bar.
  Proof:    `make test` and `make test-golden`.
  Done when: both green, output pasted. If red, we fix/triage the baseline *before* anything else.

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
            Signature: route_script_to_stops(selected_pois, beats_by_id, start_time, *, script: Script);
            the caller passes the Script and the fn calls stop_narration_text(script) internally.
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

Step 1.4c — Mobile polls + plays the per-stop narration audio.
  Change:   point the itinerary player's poll/play at the per-stop url from 1.4b (instead of per-beat).
  Tests:    funct: dev server end-to-end → the app receives a per-stop narration url for every stop.
            manual: YOU run make flutter-ios, generate a Paris trip, tap Confirm & Prepare, and CONFIRM
                    each stop plays multi-sentence narration (cold-open → beat → transit → beat →
                    closing), not a lone fact. (I run the app + paste logs; the listen is yours.)
  Proof:    make flutter-test + the manual checklist above.
  Done when: funct green + pasted AND you confirm the listen.
```

**Phase 1 delivers:** a real, continuous, audible tour — the single biggest gap — with no new
algorithm, no LLM, no destination work. The stitched narration is a genuinely shippable interim (a
real story, voiced); Phase 4 swaps the *source* of the sentences to the LLM compose using the *same*
audio plumbing.

---

## Phase 2 — A→B corridor (destination, B optional)

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

- **Phase 3 — Spotlight model.** Replace the tier gate + lens-miss exclusion with the continuous
  `gravity × lens × proximity` spotlight (LENS_FLOOR, no gates); emit the vignette band; measure
  per-corridor lens coverage. **The preview's `lens_coverage_note` and the `band`/`spotlight` contract
  fields ship here (not Phase 2).** Tests: unit per scoring rule + the matrix cells; golden re-baseline
  with a reviewed, explained diff.
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
