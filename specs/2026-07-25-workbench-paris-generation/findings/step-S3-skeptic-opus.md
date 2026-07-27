# S3 hostile skeptic — NEGATIVE SPACE angle (opus)

- Verified against commit **930b1e2** (`refactor: make test and env targets self-contained`),
  working tree DIRTY as described in run-context Baseline; `src/tour/selection.py` and
  `tests/test_tour_corpus_loader.py` present as unstaged modifications (the S3 diff).
- Ran concurrently with 2 sibling skeptics; per the panel contract I executed **`make lint` only**.
  Everything else is PROPOSED with an exact command for the serial verifier.

## What I could re-derive myself

| Evidence item | Re-derived? | Result |
|---|---|---|
| `make lint` → 0 errors | YES, I ran it | exit 0, `All checks passed!` |
| S3 diff is exactly the 3 claimed edits (`b.audio_url` column, `_is_unadopted_placeholder_beat`, call site) | YES, `git diff` | matches the claim, 25 added lines in `src/tour/selection.py` |
| Test logic actually encodes the exclusion | YES, by reading | `b-placeholder` (no stable id + placeholder URL) is dropped; `b-adopted` survives on `_clean(stable_beat_id) is not None`; `b-corpus` survives on the URL half; `beat_count == 2` follows from `selection.py:749 beat_count = len(beats)` — the count is derived from the SAME filtered list, so there is no filtered-list/unfiltered-count skew |
| `make test-file …::test_placeholder_beats_without_stable_ids_are_excluded` RED/GREEN | NO — barred (shared 7688/7687/Valhalla) | claim not independently executed |
| The dev graph's real twins match the asserted shape | NO — barred | rests entirely on decision D4's earlier measurement, not on anything re-run in S3 |

## Attacks that FAILED to break the fix (so the confirmation means something)

1. **Alternate loader.** `_snapshot_from_records` has exactly one production caller
   (`load_paris_corpus`, `selection.py:665`); `load_paris_corpus` has exactly three product call
   sites (`trips.py:467` generate, `:726`, `:1040` preview). Both preview lanes — premium
   (`trips.py:1148`) and the `llm_generation_failed` basic fallback (`trips.py:1097`) — build their
   stops from the SAME filtered `snapshot`. No second snapshot builder exists
   (`place_materialization.py:723` derives from an already-filtered snapshot).
2. **Query-text pinning.** `tests/test_trip_preview_contract.py:82-98` raises on an unrecognised
   corpus query. It keys on substrings (`HAS_BEAT`), not on the full text, so adding the
   `b.audio_url` RETURN column does not trip it. Its fake beat records omit `audio_url` entirely →
   the new filter fails OPEN (keeps the beat) → no hidden behaviour change in that suite.
3. **Beat-count skew / density gate.** `poi.beat_count` and `beats_by_poi` are both built from the
   post-filter list, so the density gate, `_is_filler_stub` and the rubric all see one consistent
   corpus. No "count says 3, list has 2" inconsistency.
4. **Certification replay.** `BuildFingerprint` / `PremiumBuildIdentity` pin no corpus hash
   (`grep corpus_fingerprint|snapshot_hash src/tour/artifact.py src/tour/premium_tour.py` → empty),
   and no test pins a live-corpus `snapshot_sha256`. Excluding beats cannot break a replay contract.
5. **Seeded-graph test breakage.** Only 4 beats are seeded (`src/seed/narratives.py`), all Paris, on
   3 POIs. No test that seeds via `src.seed` also calls `load_paris_corpus`, so the "every seeded
   beat is now invisible to the loader" side effect breaks no existing hermetic test.
6. **Type/empty degradation.** `isinstance(audio_url, str)` + `_clean` mean a missing key, `None`,
   an empty string or a non-str Neo4j value all fail OPEN (beat kept). Empty-string `beat_id`
   is treated as unadopted → excluded, which is the safe direction (though it disagrees with
   `db_parity.py`'s `beat_id IS NOT NULL`, which counts `''` as adopted).

## Findings (all advisory — none has an executed reproduction)

### N1 (medium) The exclusion is defeated by an existing pipeline that is *designed* to overwrite the field it keys on

`src/audio/pipeline.py:392` selects beats to voice with `if force or not url or "placeholder" in url`
and `:243-258` then **overwrites `audio_url`** with the real storage URL. That predicate selects
*exactly* the set S3 depends on. One admin call to `POST /api/v1/audio/generate-batch`
(`src/api/routes/audio.py:657`, "matches EVERY NarrativeBeat in the connected graph"), or one
per-beat generate from the workbench beat editor, permanently un-hides the unadopted twins:
`beat_id` stays NULL (nothing writes it), `audio_url` no longer starts with the prefix,
`_is_unadopted_placeholder_beat` returns False, and the duplicate re-enters every Paris tour —
still invisible to `db_parity.py:113` and `prune_orphan_pois.py:48`. A structural key
(`beat_id IS NULL` + provenance) would be durable; the audio-URL conjunction is not, and no test
pins "after audio generation, the twin is still excluded". The conjunction was a deliberate
data-loss guard, so the counter-design is not free — but the invariant is one operator action from
silently lapsing, with no alarm.

*Proposed check (serial verifier, read-only):*
`docker exec ondoway-neo4j cypher-shell -u neo4j -p ondoway_dev_2026 "MATCH (p:POI {city_name:'paris'})-[:HAS_BEAT]->(b:NarrativeBeat) WHERE b.beat_id IS NULL AND b.active_status='active' RETURN p.name, b.id, b.audio_url ORDER BY p.name"`
— any row whose `audio_url` does NOT start with `s3://ondoway-audio/placeholder/` is a beat AC-26
intends to exclude that S3 keeps.

### N2 (medium) Different entry point: the seeder itself binds a placeholder twin into a real Trip, bypassing the loader

`src/seed/trips.py:33-47`:

```
MATCH (poi:POI {name: $poi_name, city_name: $city_name})
MATCH (poi)-[:HAS_BEAT]->(beat:NarrativeBeat)
WITH t, prof, poi, beat LIMIT 1          -- no ORDER BY, no beat_id filter, no active filter
MERGE (item)-[:PLAYS_BEAT]->(beat)
```

The three seeded stops (`trips.py:60-82`) are **Eiffel Tower, Café de Flore, Shakespeare and
Company** — precisely the three POIs D4 measured as carrying NULL-`beat_id` placeholder twins. The
picked beat is arbitrary, and because `MERGE` is on the pattern, a reseed that picks the other twin
*adds a second* `PLAYS_BEAT` edge. `src/api/crud/trips.py:320-346` then returns
`{id, script_body, audio_url, …}` for every `PLAYS_BEAT` beat and sets
`primary_id = coalesce(item.primary_beat_id, beats[0].id)` — so `GET /trips` can serve
`s3://ondoway-audio/placeholder/eiffel_tower.mp3` as a stop's **primary** audio. `ensure_dev_data`
runs `python -m src.main` → `seed_all` → `seed_trip` (`src/seed/runner.py:27`) whenever parity
fails, i.e. on the demo machine, every run. AC-26's headline sentence ("No beat with beat_id NULL
and placeholder audio can be **selected into a Paris tour**") is therefore not true system-wide
after S3; only its second sentence ("the loaded corpus snapshot excludes them") is. S4's file scope
already includes `src/seed/trips.py`, so this is closable there.

*Proposed check (serial verifier, read-only):*
`docker exec ondoway-neo4j cypher-shell -u neo4j -p ondoway_dev_2026 "MATCH (t:Trip)-[:HAS_STOP]->(i:ItineraryItem)-[:PLAYS_BEAT]->(b:NarrativeBeat) WHERE b.beat_id IS NULL AND b.audio_url STARTS WITH 's3://ondoway-audio/placeholder/' RETURN t.name, i.sort_order, b.id, b.audio_url"`

### N3 (medium) No corpus-consuming shard was run, and the AC's own "given the dev graph" clause is untested

S3 changes what EVERY Paris/NY/London tour loads, yet the whole gate was `make lint` + one fully
synthetic hermetic test. Nothing in the evidence re-ran a shard that builds from the live corpus:
`tests/test_tour_golden_ile.py` asserts a beat-ID overlap floor of `20/47` and a fixed spine area
from `load_paris_corpus(live)`, `test_tour_grade.py` / `test_tour_invariants_live.py` build
per-city snapshots, and `test_tour_selection.py:1569` runs a live-corpus route smoke. Shakespeare
and Company (~500 m from the Île golden's Pont Neuf start) loses an active beat under S3, which
moves its `beat_count` and therefore its candidate scoring. I do not claim these go RED — I claim
nobody looked, on a Tier-3 step.

*Proposed (serial, one at a time):* `make _test-golden`, then `make _test-grade`, then
`make _test-invariants`. Also: the AC says "**Given the dev graph's** placeholder beats on Eiffel
Tower and Shakespeare and Company, the loaded corpus snapshot excludes them" — no executed evidence
touches the dev graph at all; that half of AC-26 is asserted, not measured, in this step.

### N4 (low) Prefix-exact vs substring: two definitions of "placeholder" now disagree, and a legacy prefix provably existed

`selection.py:702` uses `startswith("s3://ondoway-audio/placeholder/")`; `audio/pipeline.py:159,209,392`
uses `"placeholder" in url`. Git history shows the seeder wrote
`s3://travlr-audio/placeholder/{poi_slug}.mp3` from 594cf36 until the rename in 70d4653
(`git show 70d4653 -- src/seed/narratives.py`). Any long-lived node still carrying the old prefix
(or any hand-edited variant) is "placeholder" to the audio pipeline but corpus content to S3.
The seeded `script_body` texts never changed, so a reseed overwrites `audio_url` on the same
MERGE-keyed nodes — this is only reachable for nodes orphaned by a POI re-keying (e.g. the
pre-`city_name` era). Unproven on the live graph; the N1 probe above also answers it.

### N5 (low, process) The step's own gate mutates the shared graph it is being judged against

`make test-file` pulls `_ensure-dev-data` (`Makefile:144-146`), which — when parity fails, which D2
says is *always* — runs `src.main` → `seed_all`, **re-creating** the placeholder twins, the
Café de Flore fork and the demo Trip. The QA evidence ran that target three times (baseline, undo,
restore) and even recorded an `:8000` false positive mid-run. The verdict is not invalidated by
this (the test itself is pure), but "hermetic test, 0.04 s" understates what the gate command did
to shared state, and the recorded anomaly means one of the three runs was not a clean invocation.

## Verdict

- **Narrow claim** (the loader excludes NULL-`beat_id` + placeholder-audio beats): survived every
  static attack above. I could not execute the test, so I do not stamp it CONFIRMED.
- **AC-26 as written in its headline sentence** ("never selectable into a tour"): not satisfied by
  S3 alone — see N2, a code-verified second entry point on the same three POIs.
- **Overall: UNPROVEN.** Missing, specifically: (a) any execution against the real dev graph
  proving the two measured twins are excluded, (b) any corpus-consuming shard re-run, (c) closure
  or explicit deferral of the seed_trip path and the audio-pipeline lapse.
