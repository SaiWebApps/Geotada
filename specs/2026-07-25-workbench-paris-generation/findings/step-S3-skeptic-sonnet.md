# S3 skeptic review — FIX CORRECTNESS angle (sonnet)

Verified against: working tree at HEAD 930b1e201d8528cd9ae493df5111127715d12d6b
(dirty tree, per run-context.md baseline), diff under review in
`src/tour/selection.py` and `tests/test_tour_corpus_loader.py`
(`test_placeholder_beats_without_stable_ids_are_excluded`).

## Verdict: CONFIRMED (advisory notes below, none blocking)

## What I did

1. Read `src/tour/selection.py` diff in full: added `b.audio_url AS audio_url`
   to `LOAD_PARIS_BEATS_CYPHER`, added `_PLACEHOLDER_AUDIO_PREFIX`,
   `_is_unadopted_placeholder_beat(record)` (conjunction: `stable_beat_id` is
   None/blank AND `audio_url` starts with the placeholder prefix), and a
   `continue` in the `_snapshot_from_records` beat loop.
2. Read the new test and its fixtures (`placeholder`, `adopted_twin`,
   `corpus_beat`) plus the two negative-control assertions.
3. Traced the AC-26 mechanism claim independently rather than trusting the
   code comment:
   - `src/seed/narratives.py:17-31` (`_MERGE_BEAT`) sets `b.id`, `version`,
     `active_status`, `audio_url`, `duration_sec`, `kid_friendly` — **never**
     `b.beat_id`. `_build_beat_params` (line 95) always stamps
     `audio_url = f"s3://ondoway-audio/placeholder/{poi_slug}.mp3"`. This is
     the only writer in the repo that leaves `beat_id` NULL.
   - `scripts/upload_paris.py:224-272,328` (real corpus content) always
     `MERGE (beat:NarrativeBeat {beat_id: b.beat_id})` and explicitly
     **refuses** to write a beat with an empty `beat_id` (comment at line
     266-272: "an empty beat_id is a bug").
   - `src/onboard/beat_draft.py:193` (onboarding/authoring path) also always
     stamps a city-prefixed `beat_id`, never leaves it null.
   - So in the current codebase, "`beat_id` NULL AND placeholder audio" is
     satisfied **only** by the seed-artifact class the fix targets — there is
     no known legitimate-content writer that produces that conjunction. This
     directly supports the claim's rationale, not just the comment's say-so.
   - `scripts/db_parity.py:113` and `scripts/prune_orphan_pois.py:48` both
     filter `WHERE b.beat_id IS NOT NULL` — confirmed verbatim, so the
     "parity/prune are structurally blind to these" claim in the code
     comment and D4 decision is accurate, not decorative.
4. Confirmed `_snapshot_from_records`/`load_paris_corpus` is the **only**
   choke point feeding tour generation: `src/api/routes/trips.py` imports
   `load_paris_corpus` and calls it at all three tour-producing entry points
   (`generate_trip` :467, `compose_trip` :726, `preview_trip` :1040). The
   only other `HAS_BEAT`-matching Cypher in the repo is
   `src/api/routes/graph.py` (the `/graph` vis.js debug endpoint — not a tour
   path) and `src/audio/pipeline.py:216` (fetches a single named beat by
   `id`, not a selection query). `_primary_beat_audio` in trips.py:403 only
   re-fetches metadata for `beat_ids` that already survived selection — it
   is not an independent selection path, so it cannot reintroduce an
   excluded beat.
5. Confirmed `BeatRef` (`src/tour/contract.py:139`) has no `audio_url`
   field — the column is fetched from Cypher purely to drive the filter,
   confirming the mutation evidence ("revert `b.audio_url` cypher column"
   is a real, load-bearing revert, not padding) is coherent: without that
   column, `record.get("audio_url")` is always `None` in a live-DB run and
   the filter's second conjunct is silently unsatisfiable — a real, subtle
   regression class the test's own `assert "b.audio_url" in
   LOAD_PARIS_BEATS_CYPHER` line specifically guards against.
6. Checked `beats_by_poi_acc` construction: the `continue` happens **before**
   `BeatRef` construction and before `beats_by_poi_acc.setdefault(...)`, so
   `POI.beat_count` (fed from `len(beats)` at line 749) reflects only kept
   beats — matches the test's `snap.pois[0].beat_count == 2` assertion.
7. Checked `_clean()` (line 803): empty-string `stable_beat_id` normalizes to
   `None`, so an empty-string beat_id (which `upload_paris.py` refuses to
   write anyway) would still correctly count as "no stable id" — no
   edge-case gap there.
8. Grepped for other test fixtures across the repo that construct beat
   records with `ondoway-audio` placeholder URLs feeding
   `_snapshot_from_records`/`load_paris_corpus` — only
   `tests/test_tour_corpus_loader.py` does; `tests/test_audio_pipeline.py`
   and `tests/test_audio_storage.py` also reference the S3 URL scheme but
   never call `_snapshot_from_records`, so this change cannot silently flip
   an unrelated test's expected beat count. Other `_beat_record()` calls in
   the same file omit `audio_url`/`stable_beat_id` entirely (default `None`
   from `.get`), so `isinstance(None, str)` is `False` and they are
   unaffected by the new filter — confirmed by reading the full file, not
   just the diff hunk.
9. Ran `make lint` myself (safe, no shared state): **exit 0**, "All checks
   passed!" — matches the claimed evidence.

## Does the test encode the real failure mode, or a strawman?

Real. The fixture's `stable_beat_id=None` / `audio_url=".../placeholder/..."`
combination for `b-placeholder` is not an invented shape — it is exactly the
shape `src/seed/narratives.py` produces on every re-seed, which is exactly
what D4 measured on the live dev graph (Eiffel Tower / Shakespeare and
Company placeholder twins). The two negative controls
(`adopted_twin`: real `stable_beat_id` + placeholder audio;
`corpus_beat`: no `stable_beat_id` + non-placeholder audio) are not
decorative — they positively prove the AND is load-bearing, matching AC-26's
literal wording ("beat_id NULL **and** placeholder audio").

## Attacks tried (all failed to break the fix)

- Searched for any current writer of `NarrativeBeat` nodes that could
  legitimately produce `beat_id` NULL + placeholder audio outside the seed
  script (upload pipeline, onboarding/beat_draft path) — none found; both
  always stamp a real `beat_id` or refuse to write.
- Searched for a second tour-selection code path that bypasses
  `load_paris_corpus`/`_snapshot_from_records` — none found; the only other
  `HAS_BEAT` Cypher is a debug graph-viz endpoint and a single-beat audio
  lookup, neither of which selects beats into a tour.
- Checked whether `beat_count` (feeds the density/refusal gate) is computed
  before or after the filter — after, correctly.
- Checked case-sensitivity / trailing-slash drift between the seed script's
  literal prefix and the filter's constant — identical literal.
- Checked whether adding the `b.audio_url` column could silently break an
  unrelated consumer of `LOAD_PARIS_BEATS_CYPHER`'s column set — no other
  caller of that constant besides `load_paris_corpus` and the pinned test.
- Checked whether other existing hermetic tests in the same file could have
  their beat counts silently changed by the new filter — no, none of them
  set `audio_url`/`stable_beat_id` in a way that would trip it.
- Ran `make lint` myself: exit 0, zero errors, matches claimed evidence.

## Not run (per concurrency restriction — proposed to the serial verifier)

- `make test-file FILE="tests/test_tour_corpus_loader.py::test_placeholder_beats_without_stable_ids_are_excluded"` —
  I did not execute this myself (instructed not to; it touches the shared
  7688 test DB / Valhalla / dev-data machinery). My review of the diff makes
  me confident in the claimed RED-then-GREEN mutation result, but I did not
  independently reproduce the pytest run — that half of the evidence chain
  is UNPROVEN by me specifically and rests on the serial verifier / the
  original QA claim.

## Advisory (non-blocking) observations

- The filter's second conjunct requires `audio_url` to be a `str`; a
  hypothetical future beat with `beat_id` NULL and `audio_url` `None` (not
  yet stamped placeholder at all) would NOT be excluded by this filter. This
  is outside AC-26's literal text ("beat_id NULL **and** placeholder audio")
  and no current writer produces that shape, so it is not a reproducible
  defect today — flagging only as a watch-item if a future seed/authoring
  path ever creates a beat before assigning any audio_url.
- I did not independently re-verify the D4 decision's live-graph MEASURED
  claim (Eiffel Tower / Shakespeare and Company placeholder twins existing
  on the actual dev graph) — that was supplied as already-established
  context per the task instructions ("run-context.md ... do not re-derive
  that context"), and I did not query the live 7687 graph myself.
