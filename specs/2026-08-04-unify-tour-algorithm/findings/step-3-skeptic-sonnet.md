# Step 3 skeptic (fix correctness) — hostile review

Verified against: HEAD `a7df218c0ce3ca28df2e31df895f80e5ea3a7ef5` plus the uncommitted
working tree (`git diff | md5` = `6d5da8e426262f03109ddee1122e084a` — this differs from
the sibling opus skeptic's stamped hash `10625f4025e77638fc86c6d58440429b`, i.e. the tree
moved between the two reviews; see F1-note below). Date 2026-08-04. Angle: is the change
itself right, does the red-first test encode the ORIGINAL failure mode, and would a
plausible neighbouring input still break it.

Executed by me in this session: `make lint` only (exit 0, "All checks passed!", matches
the developer's evidence). Everything else below is read-only `git diff` / `git show` /
`grep` against the actual source — no container needed for any of it.

## F1 (high) — the claim "satisfies AC-8" is false, confirmed by direct reading

AC-8 (verbatim): the composed route's POI ids, order, eta_seconds, vignettes and
tourability must be identical to the chosen option's, "no re-derivation and no
hand-restore, replacing trips.py:583-590 and the always-None tourability."

I diffed `src/api/routes/trips.py` against HEAD myself (`git diff -- src/api/routes/trips.py`).
The block at the cited lines is **still there, unchanged in shape**:

```
    with RoutingClient() as routing_client:
        route = summarise_route(picked, ..., routing_client=routing_client)
    ...
    if anchor_restore:
        route = route.model_copy(update=anchor_restore)
```

The only edit to that block is adding `planning_policy=planning_policy` to the
`summarise_route(...)` call and a routing-version capture. The rebuild-from-poi-ids and
the `anchor_restore` hand-restore are byte-for-byte the same code path as HEAD. I also
grepped for `tourability` across the whole file (`grep -n "tourability"
src/api/routes/trips.py`): it appears at lines 905 (`_tourability_payload` definition),
1023 and 1159 — none of those three are inside `compose_trip` (lines 487-767).
`TripComposeResponse` carries no `tourability` field at all. So the "always-None
tourability" this criterion names as a defect to fix is neither removed nor replaced;
`compose_trip`'s response simply never carries a tourability value, before or after this
diff.

The pinned test itself does not claim otherwise: its own docstring header reads
"AC-10 (in substance)" and says nothing about AC-8. I read all eight of its assertions
(`tests/test_trip_api.py:714-790`) — five source-greps on the handler's text, one env-var
check, one 503-refusal check, one faithfulness-checker-consulted check. None mentions
eta_seconds, vignettes, tourability, or POI order equality to a persisted option. There is
no other test in the repo that does either (I read the sibling
`test_compose_authors_per_stop_and_keeps_the_wire_contract`, which is the other pinned gate
touching this same endpoint, and it checks wire-contract shape and call counts only).

**Root cause, not just a missed line**: `compose_trip` persists only `poi_ids` (plus two
optional anchor ids) at generate time — I read the unpack at trips.py:543-552
(`entry["poi_ids"]`, `start_anchor_poi_id`, `fixed_end_poi_id`). There is no persisted
eta_seconds, vignette set, or tourability score for compose to pass through unchanged; it
is architecturally forced to rebuild the route via `summarise_route`, which is exactly why
AC-10 carries an explicit narrowing note in `run-context.md` ("compose persists only POI
ids, so it must rebuild a route and cannot simply stop summarising one"). AC-8 makes the
same "identical to the chosen option's" demand for eta_seconds/vignettes/tourability, but
received no equivalent narrowing — the run-context locked-decisions section narrows AC-10
only. Either AC-8 needs the same narrowing (and a test asserting whatever the narrowed
claim actually is), or a prior/later step must start persisting that data at generate time
so compose really can pass it through unchanged. As written and as shipped, step 3 does
not touch this gap at all.

Verified by reading, no container needed:

    git diff -- src/api/routes/trips.py
    grep -n "tourability\b" src/api/routes/trips.py
    sed -n '543,552p' src/api/routes/trips.py

## F1-note — the sibling skeptic's F1 (conftest opt-in) appears already resolved

The opus report on record (`findings/step-3-skeptic-opus.md`) found the
`ONDOWAY_ALLOW_DIRTY_LOCAL_BUILD=1` opt-in was a module-scoped fixture inside
`tests/test_trip_api.py` only, not in `tests/conftest.py`, and predicted a 503 regression
in `tests/test_tour_authoring_gates.py`. In the tree I read, `tests/conftest.py:64` already
carries `os.environ.setdefault("ONDOWAY_ALLOW_DIRTY_LOCAL_BUILD", "1")` as a module-level
statement, which every test module under `tests/` inherits at collection time regardless of
which node id is selected — I confirmed pytest always imports the nearest `conftest.py`
ahead of test collection, so this covers `test_tour_authoring_gates.py` without that file
needing any edit itself. The working-tree diff hash moved between the two reviews
(`10625f40...` -> `6d5da8e4...`), so this is very likely a genuine fix landed between the
two runs, not a disagreement about the same code. I did not independently execute
`test_tour_authoring_gates.py` (shared-container rule), so I cannot upgrade this past
"very likely resolved by reading" — proposing the same repro opus proposed, now to confirm
rather than refute:

    make test-file FILE="tests/test_tour_authoring_gates.py::test_a_faithful_tour_still_composes"

Predicted now: exit 0 (green), because conftest.py's setdefault is session-wide.

## What I attacked and could NOT break

- **AC-10's substance (the certification-vs-legacy walk budget).** I checked whether
  `summarise_route`'s `planning_policy` parameter actually defaults to the legacy 0.83
  policy when the caller omits it: `routing.py:409` shows
  `planning_policy: RoutePlanningPolicy = LEGACY_ROUTE_PLANNING_POLICY` as the default. The
  diff's added `planning_policy=certification_planning_policy(policy_id=PREMIUM_MODULE_VERSION)`
  argument therefore does change real behaviour, not just source text — before this change,
  omitting the keyword silently reached the legacy flat budget the run-context's decisions
  say must be deleted, not left reachable by omission. So although the test only source-greps
  for the literal presence of that keyword (a real weakness, already flagged as F3 by the
  sibling review, which I independently confirm by the same reading), the underlying fix is
  substantively real, not cosmetic.
- **`resolve_build_identity()` call placement.** Confirmed it runs in its own `try` block
  before `plan_premium_authoring`/`execute_premium_plan`, so a dirty-tree failure fires with
  zero physical (billable) calls made — matches assertion 3's `unreachable.stop_calls == []`
  claim.
- **`EphemeralReceiptSink()` choice for a persisted, authenticated compose.** It looked like a
  workbench-only convenience being reused somewhere it might drop needed audit/receipt data
  for a billing-relevant persisted trip. Checked: `src/api/routes/trips.py:1052` already uses
  the identical `EphemeralReceiptSink()` at the pre-existing `/trips/generate` premium call
  site (unmodified by this diff), and `EphemeralReceiptSink` is the only concrete
  `PremiumReceiptSink` implementation in the codebase. Not a new or inconsistent choice
  introduced by step 3.
- **Call-signature correctness of `plan_premium_authoring` / `execute_premium_plan` /
  `finalize_premium_tour`.** Read all three definitions in `src/tour/premium_tour.py`; the
  call site's keyword arguments (`snapshot=`, `snapshot_sha256=`, `routing_version=`,
  `policy_version=`, `executor=`, `receipt_sink=`, `faithfulness_checker=`,
  `build_identity=`) match the declared signatures exactly, including the documented dual-
  caller contract at `plan_premium_authoring`'s docstring ("called by `plan_premium_tour`
  ... and by `POST /trips/{trip_id}/compose`").
- **`make lint`** — ran it myself, exit 0, "All checks passed!", matches the developer's
  pasted evidence exactly (AC-28 holds).

## Verdict on the claim

"Step 3 satisfies AC-8, AC-10, proven by the pinned test plus a REAL mutation verdict" —
**AC-8 is REFUTED by direct reading**: the code block AC-8 names as needing replacement
(trips.py's summarise_route rebuild + anchor hand-restore) is unchanged, `compose_trip`
carries no tourability field before or after, and the pinned test's own docstring only
claims AC-10. The mutation evidence (revert trips.py -> red on assertion 1, restore ->
green) is real and I have no reason to doubt it, but a red/green flip on a source-grep
assertion proves the diff changed, not that AC-8's specific demand was met — and no
assertion in the suite touches AC-8's substance at all. AC-10's REASON (no un-policied route
summary reaching the legacy 0.83 budget) is genuinely delivered — confirmed independently
via the default-parameter fact above, not just by trusting the source-grep — though the
test proving it is weaker than "REAL mutation verdict" implies, as the sibling review's F3
also found.
