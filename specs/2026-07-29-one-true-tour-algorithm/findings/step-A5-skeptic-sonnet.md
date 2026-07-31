# Step A5 skeptic review (fix correctness) — sonnet

Verified against commit `c8ec39690030901660c843d46910bedb40e84c13` (tree dirty with the
in-flight ledger work; `src/tour/authoring.py`, `tests/test_tour_authoring_gates.py` and
others untracked/modified as listed by `git status --short`).

## What I independently verified

1. **`make lint`** — ran it myself: exit 0, "All checks passed!" across
   `src/ tests/ scripts/...`. Matches the claimed evidence.

2. **Byte-for-byte port confirmed by direct comparison.** `src/tour/authoring.py:533-551`
   (`_dedup_composed`) and `src/tour/compose.py:696-710` (`_dedup_composed`) call the exact
   same three functions in the exact same order (`suppress_repeated_claims(...,
   include_same_beat=True)` -> `suppress_exact_repeats` -> `suppress_same_beat_near_duplicates`),
   sourced from the same `src/tour/claim_dedup.py`. Not a re-implementation that could drift.

3. **Single shared choke point, not two parallel copies.** `author_prebuilt_route`
   (`src/tour/authoring.py:957`) and `premium_tour.finalize_premium_composition`
   (`src/tour/premium_tour.py:494`) both call the literal same
   `finalize_certification_composition` function (imported, not duplicated) — confirmed by
   reading both call sites and premium_tour.py's import line 47. There is no post-processing
   after `finalize_certification_composition` in `author_prebuilt_route` (it returns
   `composition.script` directly at line 967) that could reintroduce a duplicate on one
   surface but not the other.

4. **Ordering (dedup before verify) matches D3 and matches `compose.py`'s own established
   pattern.** In `finalize_certification_composition`, `composed_sentences =
   _dedup_composed(...)` runs, then `verifier(composed)` runs against a coverage baseline
   derived from the PRE-compose `stitched` script (`claims_realized_by(stitched,
   beats_by_id)`) — same order/baseline-source as `compose.py:788-812`'s
   `compose_script`/`compose()` closure. Parity confirmed, not just claimed.

5. **Independently re-ran the red/green mutation myself, by a different mechanism than the
   QA's file-edit-and-restore** (so it doesn't depend on trusting their diff-restore
   procedure): imported `tests.test_tour_authoring_gates.test_cross_stop_echo_is_suppressed`
   directly (bypassing pytest/Makefile/DB entirely — no fixtures needed, this test uses no
   `live_neo4j`/`needs_neo4j`), called it directly with `_dedup_composed` monkeypatched to
   identity (`lambda sentences, beat_sequence: sentences`, functionally equivalent to
   reverting the dedup call to the raw undeduped assembly). Result:
   - With the real fix (no monkeypatch): test passes.
   - Mutated (`_dedup_composed` = identity): `AssertionError: the cross-stop echo was not
     suppressed: 'The span was finished in the winter of 1400.' appears 2 times in
     [...]` — same duplicate-count assertion text the QA evidence quotes.
   - Un-mutated again: passes.
   This is a genuine, independently-reproduced confirmation that the pinned test exercises
   the real fix, not a coincidence of the QA's specific file-diff procedure.
   Commands run (read-only, in-process Python only, no DB/container touched):
   `uv run python <scratch>/probe_direct_test.py` and
   `uv run python <scratch>/probe_mutation.py` (both exit 0, output as above).

6. **Fixture fidelity check.** Walked `suppress_repeated_claims` by hand against the pinned
   fixture (`_cross_stop_echo_fixture`, stop 0: beat `b0` = pure DUP sentence; stop 1: beat
   `b1` = DUP + NOVEL sentence, same beat) and confirmed the drop/restore bookkeeping
   produces exactly the asserted result (DUP survives once at stop 0, NOVEL survives at
   stop 1, `stop0_texts == [DUP]`). The red-first assertion text (`2 == 1`,
   `'...' appears 2 times`) matches what the raw undeduped concatenation actually produces.
   Not a strawman: it directly encodes the documented original failure mode ("the shared
   finalizer never called the pass").

## Finding: a genuine gap in AC-6's literal wording — but it is PRE-EXISTING parity, not a
   regression from this step, and is explicitly out of this step's scope per D3

**Reproduced independently** (`uv run python`, pure in-process computation, no DB/containers
touched — safe per the concurrency rules):

```python
# stop 1's ONLY beat (b1) is a pure single-sentence restatement of stop 0's fact,
# with NO novel sentence riding along (unlike the pinned fixture, where stop 1's
# beat always has a second, novel sentence).
_dedup_composed([DUP@stop0/b0, DUP@stop1/b1], sequence)
# -> count(DUP_TEXT) == 2   (echo NOT suppressed)
```

I ran this against **both** the new `src/tour/authoring.py::_dedup_composed` and the
original `src/tour/compose.py::_dedup_composed` and got the identical result (2, not 1) from
both. Root cause: `suppress_repeated_claims`'s "never empty a beat" restore
(`claim_dedup.py:206-226`) tracks survival **per beat id**, not per stop — if a beat's *only*
sentence is dropped as a pure restatement, it is unconditionally restored so the beat isn't
emptied. When a stop's entire authored content is a single beat that is itself a pure
cross-stop echo (no novel claim anywhere in that beat), the restore puts the duplicate right
back, and it ships on both surfaces.

**Why this doesn't block A5:** it is not a regression introduced by the port — I confirmed
byte-identical behavior on `compose.py`'s pre-existing dedup, so today's whole-tour composer
has exactly the same gap. D3 explicitly scopes this step as "parity with today only — NO new
checks (anti-spin)". A5 was never asked to close pre-existing dedup gaps, only to port the
existing pass to the per-stop seam. AC-6's literal text ("Given an injected cross-stop
duplicate sentence, then it is suppressed") reads as a universal claim that isn't quite true
of the underlying mechanism in this one corner case, but that's an AC-wording imprecision
inherited from an existing, accepted limitation — not something this step's fix got wrong.

Flagging it because the docstring for `_dedup_composed` itself observes cross-stop echoes are
"now most often cross-STOP since each stop is authored independently" — i.e. the ledger's own
per-stop cutover plausibly makes single-beat, fully-duplicate stops MORE likely to occur in
practice than they were under the whole-tour composer (each per-stop LLM call sees less
context and may lean harder on restating what little content a thin stop has). That's a
product-risk observation for a later step/backlog item, not a fix-correctness defect in A5.

## Verdict

FIX CORRECTNESS: CONFIRMED for what A5 claims (AC-6/AC-8 as the ledger scopes them — parity
port to a shared choke point on both surfaces). The red-first test is not a strawman; I
reproduced its red/green cycle myself by an independent mechanism. `make lint` reproduced
clean. One non-blocking advisory: AC-6's universal wording overstates a pre-existing,
byte-for-byth-parity dedup gap (single-beat pure-echo stops) that neither this fix nor
`compose.py` today actually closes — worth a one-line scope note in AC-6 or a backlog item,
not a rework of A5.
