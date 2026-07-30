# Skeptic write-up: step B1 (FIX CORRECTNESS angle)

Verified against: `ondoway-rubric` HEAD `b542af0b` (fix(deps): restore the public-PyPI
lock and give the index invariant an executable guard), with the B1 diff present
UNCOMMITTED in the working tree (`git status --short` shows the same 12 files, `git diff
--stat` shows 1099 insertions(+)/595 deletions(-), matching the evidence bundle exactly).

## What I independently reproduced (no `make test-file`, no DB — pure file/git reads)

1. **`make lint`** — ran it myself: exit 0, `All checks passed!`. Matches the claim.
2. **All six invariants of `test_fixture_ids_are_durable_slugs_and_internally_consistent`**,
   re-implemented from scratch in standalone Python (not importing the test module, so no
   `pytest` dependency, no Makefile bypass) and run directly against the two fixture JSONs
   and the two source `.md` documents:
   - Zero UUID-shaped strings anywhere in either fixture (0/0, confirmed).
   - Every `expected_stable_beat_ids` entry exists in `data/paris/beats.json` (1562 slugs
     loaded from the real corpus file) — 0 missing for both fixtures.
   - `expected_stable_beat_ids` is unique and sorted for both (31 ile / 21 pdv).
   - `expected_beat_count` equals `len(expected_stable_beat_ids)` for both (31/21).
   - `reachable(expected_tag_resolution, structurally_unreachable) == sorted(expected_stable_beat_ids)`
     exactly, for both fixtures (no malformed `structurally_unreachable` groups either).
   - `document_tags(doc) == resolved ∪ unresolved` exactly for both documents (70 ile tags,
     26 pdv tags/25 unique) — zero unaccounted, zero invented, zero tags double-counted as
     both resolved and unresolved.
   This is a full, independent re-derivation of the pinned test's logic against the actual
   fixture bytes — not a re-read of the developer's pasted output. All six pass. The pinned
   gate is not gamed by a malformed loophole (e.g., a `structurally_unreachable` group with
   an empty `tags` list, which the test explicitly guards against and I confirmed is absent).
3. **Pre-fix HEAD state** (`git show HEAD:fixtures/tour_golden/ile_oneway_90min.json`):
   confirmed the committed-before-this-change fixture keys on `expected_beat_ids` (ephemeral
   UUID field name, not `expected_stable_beat_ids`) with `expected_beat_count: 41` — this is
   the real pre-fix shape the red-first mutation evidence describes, not a strawman rebuilt
   to look bad.
4. **The two "known-conflicting" repair-input mappings were genuinely re-adjudicated, not
   inherited** (this is nominally AC-2/B2 territory, but the data lives in B1's fixture, so
   I checked it as evidence the resolution work behind B1 is sound, not just structurally
   well-formed). `fixtures/tour_golden/repair-input/README.md` documents two prior wrong
   picks: similarity 0.909 misrouted `cavaille_coll_organ` to the wrong beat, and similarity
   1.000 tied `judgement_day_central_portal` across two source books. I traced the actual
   document line (`Docs/tour-builder/empirical-tours/02-ile-de-la-cite-notre-dame.md:141`)
   and found BOTH tags legitimately co-occur on one blended paragraph
   (`**[F:capacity_rose_windows_organ + RG:cavaille_coll_organ]**`), and the shipped fixture
   resolves each to its own exact-suffix-matching beat (Frommers beat for the F: tag, Rough
   Guide beat for the RG: tag) rather than force-picking either of the earlier tool's
   guesses. Same pattern confirmed at line 128 for the judgement-day pair. This is a correct,
   non-lazy re-adjudication.

## Finding: stale engine constants inside the fixture's own exclusion reasoning

`fixtures/tour_golden/ile_oneway_90min.json`'s `structurally_unreachable` block justifies 4
of its 15 groups by citing `DEFAULT_FLAT_MAX`/`PAUSE_BEATS_MAX` values from a superseded
calibration round:

- `"Transits (narrative_function='transition')"` (NOT marked RECOVERED — actively excludes
  `F:transit_pont_neuf_to_palais` and `F:transit_lutece_to_parvis` from
  `expected_stable_beat_ids`): *"trimmed at DEFAULT_FLAT_MAX=6"*.
- `"Sainte-Chapelle narrative_function (Phase 4 recovered)"`, `"Île de la Cité
  narrative_function (Phase 4 recovered)"`: *"Recovered by Phase 4 DEFAULT_FLAT_MAX bump
  6→8. No longer unreachable."*
- `"Vert-Galant pause-tier (Phase 4 recovered)"`: *"Recovered by Phase 4 PAUSE_BEATS_MAX
  bump 2→3. No longer unreachable."*

I checked the actual current constants (`src/tour/beat_select.py:61,70` at this HEAD):

```
DEFAULT_FLAT_MAX: int = 12
PAUSE_BEATS_MAX: int = 4  # tier-3 stop
```

`git log --all -p -- src/tour/beat_select.py` shows the real history:

- `b2c7cfc8d` (2026-04-27): `DEFAULT_FLAT_MAX=6`, `PAUSE_BEATS_MAX=2` (the fixture's
  "baseline").
- `92ca7df18` — the actual "Phase 4" commit (2026-04-29): bumped to `DEFAULT_FLAT_MAX=8`,
  `PAUSE_BEATS_MAX=3` — this is exactly what the fixture's "recovered" reasoning cites.
- `c8729516a` (**2026-07-09**, three weeks before this ledger, already on `main` at the
  session's own HEAD): bumped AGAIN to `DEFAULT_FLAT_MAX=12`, `PAUSE_BEATS_MAX=4`.

So the fixture's exclusion reasoning is anchored to the Phase-4-era numbers and never
accounts for the later `c8729516a` bump that has been live for three weeks. For the three
`RECOVERED` groups this is harmless bookkeeping staleness — their tags are already included
in `expected_stable_beat_ids` regardless of the exact cap value, so no data is wrong. But
for the one **non-recovered** group ("Transits"), the exclusion of 2 tags rests entirely on
an unverified claim that the transition beats get trimmed by a cap that is actually double
what's cited. Whether those 2 tags are truly unreachable under the CURRENT
`DEFAULT_FLAT_MAX=12` was never re-checked against the live algorithm — the reasoning was
carried over from an old calibration round without re-deriving it.

**Why this matters even though it does not break the literal AC-1 gate:** AC-1's wording
("every `expected_stable_beat_id` is a slug that exists in the corpus... internal-consistency
... over the resolved subset is green") is a self-consistency contract, and the pinned test
only checks the fixture against itself — it never audits `structurally_unreachable`'s
free-text reasons against `src/`. So this does NOT refute the claim that B1 satisfies AC-1
as literally scoped, and the pinned test + mutation evidence for that narrow claim hold up
under independent re-derivation (see above). But `expected_stable_beat_ids` is exactly the
set later used as the numerator/denominator for the live overlap test (B3,
`test_ile_golden_overlap`) and for D6's floor recalibration ("85% of the resolved-tag
overlap measured at repair time") — both trust this partition is the TRUE reachable set. If
the Transit tags are in fact reachable today under the higher cap, `expected_stable_beat_ids`
is silently short 2 legitimate beats, which understates what the fixture asks the engine to
prove and could produce an artificially low D6 floor baseline — the same "never lower a
floor to whatever the run produced" failure mode the run-context explicitly warns against,
just one level upstream of where the ledger is watching for it.

## Attacks tried that did NOT find a break

- Tried to find a malformed `structurally_unreachable` group (empty/missing `tags` list)
  that would let a tag be silently excluded without triggering invariant 5's `malformed`
  check — none exists in either fixture.
- Tried to find fixture-declared tags that don't exist in the source document (fabricated
  tags) or document tags missing from both `expected_tag_resolution` and `unresolved_tags`
  (silently dropped) — zero on both counts, both fixtures.
- Tried to find a resolved-and-unresolved double-booked tag — zero on both fixtures.
- Tried to falsify the "genuine repair, not laundering" framing by checking whether the two
  known-conflicting repair-input mappings were blindly inherited from either candidate — they
  were not; both source-book tags were separately, correctly, exact-match resolved.
- Confirmed the pre-fix HEAD fixture genuinely used the ephemeral-UUID `expected_beat_ids`
  key (not a strawman rebuild of a "worse" fixture) that the red-first mutation targets.

I did not re-run `make test-file FILE="tests/test_tour_golden_consistency.py::test_fixture_ids_are_durable_slugs_and_internally_consistent"`
myself (propose-only per the concurrency constraint — it starts the shared 7688/7687/Valhalla
containers via the Makefile wrapper even though this specific test needs none of them). My
independent re-implementation of its six invariants against the real fixture bytes is a
faithful substitute for the assertion logic, but the actual pytest run (env, collection,
node-id addressing) should still be confirmed once by the serial verifier.

## Verdict

- **AC-1 as literally scoped: CONFIRMED.** The pinned test's six invariants all hold on
  independent re-derivation; the mutation evidence (revert fixtures → RED with the same
  failure shape as the pre-existing HEAD content → restore → GREEN) is genuine, not
  fabricated, and matches what HEAD actually contained.
- **One MEDIUM, non-blocking correctness gap:** the Île fixture's `structurally_unreachable`
  reasoning cites superseded `DEFAULT_FLAT_MAX`/`PAUSE_BEATS_MAX` values (Phase-4-era 6→8 /
  2→3) instead of the actual current values (12 / 4, live since `c8729516a`, 2026-07-09).
  One non-recovered group ("Transits") uses the stale figure to justify excluding 2 tags
  from `expected_stable_beat_ids` without re-verifying against the current, much higher cap.
  This doesn't fail B1's pinned gate (which never audits reasons against `src/`), but it is
  an unverified, potentially-wrong exclusion that downstream B3/D6 work will inherit as
  ground truth. Recommend: before D6's floor number is finalized, re-run/re-derive whether
  the two Transit tags are reachable under `DEFAULT_FLAT_MAX=12` and either move them into
  `expected_stable_beat_ids` or add an "algorithm-shape, cap-independent" justification (like
  the sub_location-duplicate groups already have) instead of the stale cap citation.
