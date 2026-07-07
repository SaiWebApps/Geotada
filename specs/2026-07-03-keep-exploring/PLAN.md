# "Keep exploring here" — feature plan (agentic-loop, 2026-07-03)

Product owner ratified this feature in session 2026-07-03 (see
`specs/2026-07-02-dwell-audio-reconciliation/DESIGN-AND-CRITIQUE.md` §"HUMAN
SIGN-OFF" → NEW SCOPE). An explicit in-tour control surfaces a dwell stop's
remaining (capped-out) narration ON DEMAND, off the promised time budget.
EXPLICIT tap only — NO auto-inference from GPS/dwell.

Full 75-agent plan (requirements + per-item test/QA/PM + manager audit) is in
`workflow-plan.json`. This file is the executive summary.

## HARD SEQUENCING: blocked on C9

The manager audit's central finding: **the whole feature is unbuildable until
C9 lands.** "Extra beats" = a POI's active beats beyond what the tour budget
allowed. Today the only cap is the flat `DEFAULT_FLAT_MAX=8` trim
(`beat_select.py`), NOT the budget share-cap the feature is written against
(KE-R2/KE-R4). That share-cap is exactly C9 (floor-less planned-audio currency
+ domination/share-cap, ratified decision 3). Until C9 is green on main,
every live-corpus "non-empty extras" claim (KE1/KE3/KE9/KE10) is unprovable.

**Only KE0 (pure synthetic uncapped-beat helper) may start before C9** — and
only after its own corrections (below).

## Checklist (12 items, dependency-ordered)

| id | title | depends on |
|---|---|---|
| KE0 | Uncapped beat-plan helper in beat_select (pure, no cap) | — |
| C9-GATE | HARD PREDECESSOR: C9 share-cap must land first; add `make gate-c9` asserting selection consumes planned-audio + has a no-collapse guard, and a Rue-Cler check that capped-out extras genuinely exist | C9 |
| KE1 | Persist extra_beat_ids + extra_narration on ItineraryItem at generation | KE0, C9-GATE |
| KE2 | Compose the extra-beats narration via the existing compose+VERIFY gate | KE0 |
| KE3 | On-demand endpoint: TTS-serve the persisted extra_narration for one stop | KE1, KE2, C9-GATE |
| KE4 | Expose extra fields on GeneratedStop API model + generate/GET responses | KE1, KE3 |
| KE5 | Mobile: parse extra fields + TripService.generateDeeperDiveAudio | KE4 |
| KE6 | Mobile playback guard: deeper-dive audio NEVER auto-advances the tour | KE5 |
| KE7 | Mobile: "Keep exploring here" button in _StopCard | KE5, KE6 |
| KE8 | Mobile end-to-end proof: widget test + simulator smoke + screenshots | KE6, KE7 |
| KE9 | Workbench: surface deeper-dive signal on the preview stop + badge | KE0, **+C9-GATE (audit fix)** |
| KE10 | Workbench proof: Playwright run showing the badge + screenshots | KE9 |

PM: 4 aligned, 8 needs-revision. Manager: NOT on-track (spine sound; four
holes below must be fixed before scheduling).

## Required corrections before implementing (from the manager audit)

1. **Schedule C9 first**; make C9-GATE a committed `make gate-c9` that asserts
   against `main:src/tour/selection.py`: (a) greedy break + fill consume
   planned-audio (not bare tier dwell), (b) a greedy no-collapse guard exists
   (decision 3, DESIGN-AND-CRITIQUE.md), (c) a Rue-Cler functional check that
   `planned_audio(voiced) <= budget < planned_audio(full)`.
2. **KE0 corrections:** drop the "spatial strategy full returns all beats per
   bucket" tests — `_order_by_sub_location`/`_order_by_trigger_address` are
   already one-per-bucket (full == capped for spatial; the delta is only in the
   flat/narrative_function trim). Fix `_beat_score` calls to the MODULE function
   `_beat_score(beat, interest)`, not a `BeatRef` method. Synthetic beats must
   set `word_count` for deterministic score ordering.
3. **KE2 fixes:** the forbidden-phrase fail-closed test cannot fire on a beat
   (validation.py: `source_type=="beat" → continue`); exercise fail-closed via a
   glue/reflection or the faithfulness/untraceable path. A single-POI deep dive
   has <2 stops → `reflection_slots` returns () → no glue; model the deep dive
   accordingly (no "stop-local glue reflections" assertion).
4. **KE9 gains C9-GATE dep**; KE1 moves the `select_poi_beats_full` +
   compose call OUT of `crud/trips.py:route_script_to_stops` (which lacks
   POI/Route/generate) to the call site (`trips.py` generate/compose); KE1/KE6
   split their bundled changes to stay atomic; KE4 targets `test_trip_models.py`
   (real home of `TestGeneratedStop`) + `trip.dart`; compose RECOMPUTES
   extra_beat_ids (replace_trip_stops), never "preserves".
5. **Strike fabricated tests from every item's test_plan** (KE3's Playwright on a
   UI-less endpoint; KE3's 500 that `audio.py` never raises — it returns a 200
   with `status='failed'`; KE5/KE8's non-existent `mobile/integration_test/`).
   Dart single-file iteration is `cd mobile && flutter test --platform chrome
   test/...`, not `make test-file` (Python-only).

## Resume point

After C9 (+C10) land green on main: re-run the planning loop on this checklist
with the corrections applied (or hand-correct per §"Required corrections"),
then implement KE0→KE10 atomically, judge-gated, with real device/browser
screenshots per the trust contract.
