# Step A2 — hostile skeptic (NEGATIVE SPACE angle)

- **Verified against commit:** `c8ec3969` ("chore(certification): re-stamp the standard's pin
  after the C11 demotion"), plus the UNCOMMITTED working tree that holds A1+A2
  (`src/tour/authoring.py` and `tests/test_tour_authoring_from_route.py` are untracked).
- **Claim under test:** step A2 satisfies AC-4, proven by
  `make test-file FILE="tests/test_tour_authoring_from_route.py::test_prebuilt_route_authors_without_replanning"`
  plus a QA mutation verdict of REAL.
- **What I was allowed to execute:** `make lint` only (two sibling skeptics running
  concurrently; every container-touching target is PROPOSE-ONLY per the panel protocol).
  Everything else below is derived by reading the actual source at the line numbers cited.

## Ruling

**CONFIRMED for AC-4 as written.** I attacked the seam from eight directions and every
attack failed. Two advisories below are real but sit OUTSIDE AC-4; neither blocks A2.

I did NOT re-execute the pinned node id myself. What I could re-derive: the mutated lines
(`src/tour/authoring.py:757-758`), the assertion the mutation lands on
(`tests/test_tour_authoring_from_route.py:334`), and the exact refusal string all reconcile
with the tree, and I proved the mutated guard is load-bearing rather than a strawman (see
"Attack 2"). `make lint` I ran unpiped: exit 0, `All checks passed!`.

## Attacks that FAILED (this is what the confirmation is worth)

1. **Negative `stop_idx` wrapping `route.pois[-1]`.** The pair of guards is
   `stops[-1] >= len(route.pois)` then `len(stops) != len(route.pois)`. If a sentence could
   carry a negative `stop_idx`, `stops = [-1, 0, 1]` against a 3-POI route satisfies BOTH
   and `route.pois[-1]` silently names the wrong POI while the tail stop goes unauthored.
   REFUTED: `Sentence.stop_idx` is `Field(..., ge=0)` (`src/tour/contract.py:515`). With
   `stops` sorted+unique and non-negative, `max < n` and `len == n` force
   `stops == range(n)`. The guard pair is complete.
2. **The mutation is a strawman — something downstream already catches a dropped stop.**
   REFUTED. `AuthoringCandidatePlan._plan_is_complete_and_single_candidate`
   (`src/tour/candidate_authoring.py:155-165`) rejects only a NON-contiguous index tuple, so a
   dropped TAIL stop (`[0,1,2]` for a 4-POI route) passes it, and
   `finalize_certification_composition` re-derives `stops` from the SAME stitch
   (`src/tour/authoring.py:545`) so its `set(units_by_stop) != set(stops)` check
   (`:558`) cannot see the gap either. The mutated line really is the only thing standing there.
3. **A transitive planner import defeating the AST guard.** REFUTED: none of
   artifact / candidate_authoring / certification_provider / compose_gate / contract /
   generation / premium_authorities / reflection / validation / verify imports `selection`;
   `generation` reaches only `routing`. The `AUTHORING_MAX_STOPS = 15` duplication rationale
   at `src/tour/authoring.py:120-128` ("selection is heavyweight") therefore holds.
4. **Certification spend blow-out from the 8 -> 15 cap relax.** REFUTED at three layers:
   `RoutePlanningPolicy.__post_init__` still hard-caps certification planning at 8
   (`src/tour/routing.py:77`), `certification_planning_policy` passes `max_stops=8`
   (`src/tour/premium_tour.py:232`), and `compose_certification_candidate` independently
   refuses any stop set differing from the frozen authorization call plan
   (`src/tour/compose.py:482`).
5. **Touching `candidate_authoring.py` invalidating committed certification data.** REFUTED:
   `PREMIUM_AUTHORITIES` hashes spec DOCUMENTS, not module source
   (`src/tour/premium_authorities.py`), and `premium_authoring_policy_sha256` hashes only the
   frozen prompt/schema/model constants, which A2 did not touch.
6. **A stop vanishing from a REAL stitch, turning the new guard into an HTTP 500.** NOT
   REPRODUCED: for `stop_idx > 0`, `_build_transit` always emits at least a nav-glue sentence
   (`src/tour/generation.py:897-926`), and both dedup passes are beat-only and never empty a
   beat (`src/tour/claim_dedup.py:249, 267-282`). I could not construct a reachable vanishing
   stop.
7. **The new test file quietly excluded from the hermetic shard.** REFUTED: the
   `addopts` ignore list (`pyproject.toml:70-82`) does not name it.
8. **Thread-unsafe counting in the test's executor.** REFUTED: `list.append` is atomic under
   the GIL, and `Executor.map` preserves input order so the `zip(..., strict=True)` in
   `author_prebuilt_route` cannot mis-pair.

## Advisories (real, but outside AC-4 — do not block A2)

### A. The seam ships D3's anti-hallucination gates DARK, and A3 lands before A4 can fix it

`author_prebuilt_route` (`src/tour/authoring.py:808-878`) calls
`finalize_certification_composition(plan.source, plan.sequence, plan.route,
completed_units=..., model=COMPOSE_MODEL)` — and `finalize_certification_composition`
(`:527-535`) has NO `faithfulness_checker` and NO `expected_claim_ids` parameter at all. It
builds its verifier as `build_full_verifier(..., chunk_text_by_slug=None,
base_validator=validate_authorized_sources)` (`:608-613`). Following that into
`src/tour/compose_gate.py`:

- `:331` `checker = faithfulness_checker or MockFaithfulnessChecker()` -> entailment is MOCKED
- `:341-345` `expected_claim_ids is None` -> the coverage baseline is a NO-OP
- `:340` empty chunks -> provenance is a NO-OP
- `base_validator` is `validate_source_traceability` (`src/tour/validation.py:105`), which
  omits the `_forbidden_phrase_hits` scan that `validate_script` (`:96-102`) runs

Today the persisted endpoint passes the REAL checker
(`src/api/routes/trips.py:784`, `faithfulness_checker=faithfulness_checker`). A3 cuts that
endpoint over to the seam, and A3's `files` scope is
`{src/api/routes/trips.py, tests/test_trip_api.py, tests/test_trips_spend_and_authz.py}` —
it cannot add an injection point to `authoring.py`. Its criteria are AC-3/AC-7, neither of
which asserts anything about the gates. So between A3 and A4 the user-facing
`/trips/{id}/compose` runs with mocked entailment, no coverage, no provenance and no
forbidden-phrase scan, gated only by `make lint`. A4 is scoped to fix exactly this
(`files` includes `src/tour/authoring.py`), so the correct mitigation is: do not stop the
run between A3 and A4, and do not treat A3's green as a shippable state.

No reproduction is possible today — the A3 tree does not exist yet. UNPROVEN, forward-looking.

### B. AC-4's tolerance proofs use a stitch no production surface emits

Every fixture is `_prebuilt()` (`tests/test_tour_authoring_from_route.py:160-262`), whose
`script` is BEAT sentences only: no `GLUE_NAV` / `GLUE_STAGING` / `GLUE_CLOSING` /
`GLUE_REFLECTION`, no vignette one-liners, no synthesized cold open, and no reflection slot —
so `all_slots` is empty in every single test and the `GLUE_REFLECTION` /
`visited_claims_by_slot` branch (`src/tour/authoring.py:517-520, 597`) is NEVER taken. The
`BeatSequence` carries no `vignette_beats` and no `overflow_by_poi`. The real persisted path
builds its stitch with `generate(seq, route, tour_input)` after `build_poi_beat_plans_capped`
+ `select_vignette_beats` (`src/api/routes/trips.py:762-773`). D5's premise — "the seam must
accept what persisted trips ACTUALLY contain" — is therefore measured against something no
persisted trip contains. I could not turn this into a failure by reading alone; it is a
coverage gap, not a demonstrated defect. Cheap closure: have A3's or A4's test drive the seam
from a `generate()` output rather than a hand-built Script.

### C. Two small ones

- `src/tour/authoring.py:823` uses `ThreadPoolExecutor(max_workers=min(max_workers,
  len(plan.units)))`, dropping the `max(1, ...)` the extracted original carries
  (`src/tour/compose.py:508`). Empty `units` is unreachable through
  `plan_prebuilt_route_authoring` (`_certification_compose_requests` enforces
  `1 <= len(stops)`, `:496`), but `PrebuiltRouteAuthoringPlan` is an unvalidated public frozen
  dataclass and `author_prebuilt_route` is in `__all__`, so a hand-built plan raises a stdlib
  `ValueError: max_workers must be greater than 0` instead of a domain error.
- `src/tour/quality_rubric.py:176-180` still reads "INHERITED. The engine composes at most
  eight stops", and `MAX_COMPOSED_STOPS: int = 8` caps the C3 audio floor
  (`c3_audio_floor_seconds`, `:254-279`). After A2 the authoring layer accepts 15, and after
  A3 the seam is the ONE engine behind a persisted trip that may already carry
  `HARD_ANCHOR_CAP` = 15 stops. The rubric's NUMBER is unchanged by A2 and its direction is
  under-blocking (a lower floor), so this is a doc-truth defect, not a behaviour change — but
  `quality_rubric.py` appears in NO step's `files`, so nothing in this ledger will correct it.
- `src/tour/candidate_authoring.py.__all__` omits the new public `MAX_CANDIDATE_STOPS`
  even though `tests/test_tour_candidate_authoring.py` imports it.

## Evidence I re-derived myself

```
$ make lint
uv run ruff check src/ tests/ scripts/dev_env.py ...
All checks passed!
exit 0
```
