# Step A3 — hostile skeptic (negative space)

- **Verified against**: HEAD `c8ec39690030901660c843d46910bedb40e84c13` ("chore(certification): re-stamp the standard's pin after the C11 demotion") plus the UNCOMMITTED working tree of steps A1-A3 (`git status --short` shows 17 modified + 3 untracked files).
- **Angle**: negative space — untested states of the world.
- **What I was allowed to execute**: `make lint` and read-only `git show` / file reads. Every container-touching command below is PROPOSED, not run (two sibling skeptics are live on the shared 7688/7687/Valhalla).
- **Verdict**: **REFUTED** on the claim as written ("wire contract preserved"). AC-3 and AC-7 hold *as literally worded*, but I could not re-run the pinned test, and the sentence "wire contract preserved" is materially false: the endpoint's VERIFY gate lost three of its four live checks and two of the five 422 diagnostic counters are now zero by construction.

---

## F1 (REFUTED, high) — the persisted compose endpoint's anti-hallucination gate silently degraded to citation-traceability only

Executed, read-only:

```
git show HEAD:src/tour/compose.py | sed -n '1363,1375p'
sed -n '599,612p' src/tour/authoring.py
sed -n '314,332p' src/tour/compose_gate.py
sed -n '96,112p' src/tour/validation.py
```

**Before A3** — `POST /trips/{id}/compose` ran `compose_script`, which built its verifier
(`src/tour/compose.py:1368-1374` at HEAD) with:

- `faithfulness_checker=faithfulness_checker` — the **real** `HaikuFaithfulnessChecker`, injected from `get_faithfulness_checker`;
- `expected_claim_ids=claims_realized_by(stitched, ...)` — the **content-loss / coverage baseline**, armed;
- `base_validator` left at its default `validate_script` — traceability **plus** `_forbidden_phrase_hits` (invented proper noun / invented year);
- `_dedup_composed(...)` run on the composed stream **before** verify (`compose.py:1381`).

**After A3** — the route calls `author_prebuilt_route` → `finalize_certification_composition`, whose verifier (`src/tour/authoring.py:608-612`) passes:

- **no** `faithfulness_checker` → `build_full_verifier` falls back to `MockFaithfulnessChecker`, which trusts everything (`compose_gate.py:330`);
- **no** `expected_claim_ids` → the coverage check is a documented **no-op** (`compose_gate.py:326-328`);
- `base_validator=validate_authorized_sources`, which returns `validate_source_traceability` **only** — and `validate_script` is exactly `validate_source_traceability` + `_forbidden_phrase_hits` (`validation.py:96-102`). The forbidden-phrase scan is **gone**;
- no `_dedup_composed` anywhere on the path.

(Provenance was already a no-op on both sides — neither caller passes `chunk_text_by_slug` — so that one is *not* a regression. The other three are.)

The repo already documents this exact hole and names this exact consumer.
`tests/test_compose_gate_forbidden_scan.py:1-26` is a **characterization test for a known-open defect**, and its own docstring says the blind validator means "every downstream consumer of `forbidden_phrase_hits` reads 0 BY CONSTRUCTION rather than by measurement — including … `src/api/routes/trips.py:793`, which puts the count on an API response." Line 793 of the working tree is literally `"forbidden": len(exc.report.forbidden_phrase_hits)` in the compose 422 detail. A3 moved the production endpoint **onto** the path that test exists to flag, and step A1 edited that test file's docstring to re-point it at `authoring.py` without noticing that the endpoint had just joined its blast radius.

**Consequence for the claim.** Of the five fields in the 422 detail the phone reads:
`untraceable` still measures something; `forbidden` and `faithfulness` are now **structurally always 0** (they were measured before); `provenance` was already always 0; `attempts` is a constant. "Wire contract preserved" is true of the JSON *shape* and false of its *content*.

**Scheduling is not a defence, but it is context.** AC-5 (step A4) does promise "the real faithfulness checker, the coverage baseline, and full validate_script provably run per-stop", and AC-6 (step A5) promises the dedup. So the ledger intends to restore all four. The problems are that (a) the A3 developer's own docstring discloses only the entailment third of the loss and calls the remainder "the structural half only", (b) nothing in the A3 evidence set mentions the coverage baseline, the forbidden-phrase scan, or `_dedup_composed` at all, and (c) if this commit lands on `main` and the run stalls at A4 (the ledger permits exactly one phase-repair), production ships a **paid** LLM endpoint whose only check on model-authored prose is "did it cite a beat id that exists". A model can invent any fact, date or proper noun it likes and pass.

Proposed executable confirmation (I could not run it):
`make test-file FILE="tests/test_compose_gate_forbidden_scan.py::test_that_delegation_is_why_invented_content_survives"` — it is GREEN, and **green is the demonstration**: same script, `validate_script` finds forbidden hits, `validate_source_traceability` finds none.

## F2 (evidence-chain attack, high) — the one executable proof that this endpoint entails its narration was deleted in the same diff that is claimed as proof

`git show HEAD:tests/test_trip_api.py | sed -n '704,728p'` — the pre-A3
`test_refused_flavour_is_422_and_leaves_trip_untouched` injected `_RejectAllChecker` into
`get_faithfulness_checker` and asserted `detail["faithfulness"] > 0`. The working-tree
version injects `_HallucinatingExecutor` and asserts `detail["untraceable"] > 0` instead
(the docstring explains why, honestly). Net effect: the repo no longer contains a single
executable assertion that the persisted compose path entails anything.

The new pinned test asserts `detail["untraceable"] > 0` — the **one** counter that can still
be nonzero. It is therefore structurally incapable of noticing F1. And the QA "REAL" mutation
verdict was measured against the AC-7 reservation assertion (`assert 1 == 7`) and the coarse
`git checkout` revert. Neither mutation touches the gate. **The mutation verdict is real for
what it tested and says nothing at all about the gate loss.**

## F3 (advisory, medium) — the cheap early rejection is gone: the rate limiter now fires after a full corpus load, a Valhalla route and the stitch

Before A3 `_spend_precheck` was the first statement after the ownership check
(`git show HEAD:src/api/routes/trips.py`, immediately after the 404). It is now at
`src/api/routes/trips.py:773`, i.e. **after** `get_trip_compose_inputs`,
`load_paris_corpus`, `RoutingClient()` + `summarise_route` (Valhalla HTTP per leg),
`build_poi_beat_plans_capped` and `generate()`. An authenticated caller looping on one owned
trip now drives unbounded Neo4j + Valhalla + CPU work per request and only meets the 429 at
the very end.

This was avoidable: the dwell-stop count is `len(poi_ids)`, known at line 698 — before the
corpus load. The reservation could have sat right after the 409 (line 677) and still satisfied
AC-7's "runs AFTER the 409" clause. No test covers request volume on this endpoint.

## F4 (advisory, medium) — concurrency: a 429-busy burns up to 15 reserved calls having spent nothing, and compose now competes with the *unauthenticated* preview for the same pools

`_spend_precheck` (line 773) records the reservation and *then* `_concurrency_slot`
(line 774) may raise 429 when `_inflight >= _PREVIEW_MAX_CONCURRENCY` (2). Nothing releases
the reservation. Pre-A3 that leaked 1 call per busy-429; now it leaks up to
`AUTHORING_MAX_STOPS` = 15. With `_PREVIEW_GLOBAL_RATE_LIMIT_MAX = 20`, two burst-rejected
requests can lock out every user for the rest of the hour with **zero** provider spend.

Related, same pools: `/trips/preview` is deliberately unauthenticated and draws from the same
`_global_hits` / `_daily_hits`. A crawler previewing can now 429 every authenticated user's
paid compose, because compose needs `n_stops` free slots rather than 1.
`test_default_per_ip_budget_admits_one_maximum_size_premium_plan` was correctly updated to pin
`_PREVIEW_RATE_LIMIT_MAX >= AUTHORING_MAX_STOPS`; **no equivalent pin exists for the global or
daily ceiling**, and no test exercises the concurrency path at all (TestClient is synchronous).

## F5 (advisory, medium) — `except ValueError` turns an unrecoverable shape error into a "try another flavour" refusal that will never succeed

`src/api/routes/trips.py:786` catches `ValueError` and returns
`422 {reason: compose_verification_failed, attempts: 1, untraceable: 0, forbidden: 0,
provenance: 0, faithfulness: 0}`. Three sources of `ValueError` land there:

1. `_certification_compose_requests` (`authoring.py:496-497`) — `not 1 <= len(stops) <= 15`.
   The route's own comment at line 697 says pre-C9f trips are "legacy bare id list … **fail
   open (uncapped)**". A persisted legacy option holding 16+ POIs composed fine before A3 and
   is now permanently un-composable — and the phone is told it is a *flavour* refusal, so its
   documented D2 fallback ("try another flavour") retries forever, every flavour failing
   identically. No test covers an oversized persisted option.
2. `plan_prebuilt_route_authoring:750/758` — corpus/stitch drift.
3. `_spend_precheck` itself raises `ValueError("planned provider call count must be
   positive")` and is **inside the same `try`**, so a guard's own contract violation is
   laundered into a verification failure. Currently unreachable (the 1..15 bar fires first),
   but it is a guard swallowing its own alarm.

## F6 (advisory, low) — the 409 is a read-then-write race, now 15× more expensive

`inputs["composed_route_id"]` (line 673) and `mark_trip_composed` (line 839) are separate
statements with no lock or transaction. Two concurrent composes of the same trip both pass the
409 and both author. Pre-existing, but the spend per loser went from 1 call to `n_stops`, and
`replace_trip_stops` + `mark_trip_composed` are two unbatched writes.

---

## Attacks that FAILED to break the claim

- `make lint` re-run by me at this tree: exit **0**, `All checks passed!` (captured to a file,
  not piped through `tail`). The claim's lint evidence re-derives exactly.
- Tried to make `_spend_precheck` run before the 409: it does not — the 409 is at line 673-677
  and the precheck at 773. AC-7's ordering clause holds by reading.
- Tried to find a path where the reservation is not `len(plan.units)`: `plan_prebuilt_route_authoring`
  enforces `len(stops) == len(route.pois)` (`authoring.py:757`) and `author_prebuilt_route`
  submits every unit via `pool.map` (line 823-824), so reserved == billed on the success path.
- Tried to make the conftest money-guard miss the new dependency:
  `get_premium_compose_executor` resolves `premium_tour.AnthropicPremiumExecutor` as a module
  attribute at call time, which is exactly what the conftest arm monkeypatches, and
  `test_product_authoring_factory_is_offline_in_the_non_live_suite` pins it. Held.
- Tried to break duck-typing between `OfflinePremiumExecutor.execute(PremiumComposeUnit)` and
  the new `PrebuiltRouteComposeUnit`: both expose `authorized_request.stitched.script`. Held.
- Tried `git diff --stat mobile/`: empty. AC-3's mobile pin holds.
- Tried to find a second entry point into the deleted whole-tour composer from the API: the
  only remaining `compose_script` caller in `src/` is `compose.py` itself.

## Commands I propose for the serial verifier (I did NOT run these)

1. `make test-file FILE="tests/test_compose_gate_forbidden_scan.py::test_that_delegation_is_why_invented_content_survives"` — expect GREEN; green proves F1's forbidden-phrase half.
2. `make test-file FILE="tests/test_trip_api.py::test_compose_authors_per_stop_and_keeps_the_wire_contract"` — the claim's own gate, never re-derived by any skeptic in this run.
