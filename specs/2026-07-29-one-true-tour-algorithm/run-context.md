# One True Tour Algorithm — run context

## Tier

**Tier 3**, set mechanically: the ledger touches `Makefile` (LIVE_TEST_FILES), `render.yaml`
(deploy config), and `.claude/commands/report-tour-issue.md` — all Tier 3 rows. Panel P=3,
acceptance runs, real-browser proof + human sign-off at close. **No step touches `mobile/`**
— AC-3 pins `git diff --stat mobile/` empty, so `make flutter-analyze` is not a per-step
gate anywhere (flutter shards still run at phase gates and close, inside `make audit`).

## Approval state

**approved_by_human: false** (verbatim from state.json). This ledger has NOT been approved.
The engine must refuse a real run until the owner says go in chat and the flag is
transcribed by the same session. This run-context write does not change that flag.

## Supersession

**Supersedes** `specs/2026-07-26-tour-engine-convergence/` (owner repudiated it in chat
2026-07-29 after three failed executions; step A10 deletes it, and
`specs/2026-07-26-tour-rubric-recalibration/` too). Nothing from its facade/firewall/rename/
SHADOW design is built here. Its two live un-shipped ideas are carried forward as plain
steps: the compose→per-stop cutover (A2/A3, its old D4 "next slice") and retained-per-stop
robustness concerns (folded into D3 gate parity only — retry/cost-recording are OUT of this
ledger).

## The one-sentence design

`/trips/{id}/compose` keeps its exact wire contract and swaps its engine to the per-stop
path via a new author-a-prebuilt-route seam in `src/tour/authoring.py` (the byte-identical
extraction of compose.py's shared primitives); then five deletion steps remove the
whole-tour composer, the author-engine track, the corrector, the dark G4, and the compose
scoreboard — ~9 src/tour modules and ~17 test files — leaving ONE algorithm behind
`/trips/generate`, `/trips/preview`, `/trips/{id}/compose`, the batch runner, and the tests.

## Decisions (verbatim from state.json)

- **D1-endpoint-shape**: POST /trips/{id}/compose KEEPS its exact wire contract (200 fresh
  stop ids + extra_narration; 409 already_composed; 404; 422 detail {reason:
  compose_verification_failed, attempts}) and swaps only its engine to the per-stop path via
  a new author-a-prebuilt-route seam. The phone parses detail['attempts']
  (mobile/test/services/trip_service_test.dart:453,467). Zero mobile/ changes; the flavour
  picker survives (flavours are route planning, which is shared). The prior
  owner-repudiated ledger's facade/firewall/rename/SHADOW machinery is explicitly NOT built.
- **D2-422-stays**: Authoring failure on the persisted path stays a 422 refusal, never a
  200-with-stitch: the 422 is the only thing keeping a failed tour out of Neo4j (a
  2026-07-19 unification that returned 200 was reverted same-day for persisting degraded
  tours marked composed). The phone's existing fallback UX (refused flavour -> try another
  -> generate-time stitch narration) is preserved unchanged. /trips/preview keeps its
  labeled Basic-tour 200 fallback unchanged.
- **D3-gate-parity**: The persisted path keeps the anti-hallucination gates it has today:
  real HaikuFaithfulnessChecker entailment + claims_realized_by coverage baseline + full
  validate_script (forbidden-phrase/proper-noun/year scan), wired as injectable params into
  the per-stop finalize. /trips/preview stays structural-only (offline speed, editor sees
  rubric warnings). Cross-stop echo dedup (_dedup_composed port) runs on BOTH surfaces.
  Parity with today only — NO new checks (anti-spin).
- **D4-extraction-before-deletion**: premium_tour.py imports 12 names from compose.py;
  provider_text_review.py, scripts/tour_batch_candidate.py, scripts/tour_batch_review.py,
  scripts/tour_text_candidate.py, scripts/tour_text_candidate_review.py and 3 test files
  import moved names too. They are extracted BYTE-IDENTICALLY into src/tour/authoring.py
  first (premium_authoring_policy_sha256 must not move), then compose.py is deleted as a
  file. A1's gate asserts the only remaining src.tour.compose importers are {compose.py,
  src/api/dependencies.py, src/api/routes/trips.py} so a missed importer fails at A1, not A8.
- **D5-seam-tolerances**: The author-a-prebuilt-route seam must accept what persisted trips
  actually contain: round-trip transit shape (len(transits)==len(pois)+1), 1..15 stops (the
  8-stop pins in authoring._certification_compose_requests and
  candidate_authoring.AuthoringCandidatePlan/ResponseSet are relaxed to 15 =
  selection.HARD_ANCHOR_CAP), and receiptless/haversine-degraded legs (authoring needs no
  Valhalla receipts; the compose path stops at Script level and never builds the
  certification blueprint).
- **D6-deletion-order**: Deletions are sequenced so the suite COLLECTS at every step:
  author-engine track (minus factcheck.py) at A6; compose scoreboard (compose_metrics + its
  eval + tools/compose_snapshot.py + craft_score) at A7 BEFORE compose_gate's _bad_stops
  dies; compose.py + factcheck.py + compose_gate ladder + their tests + Makefile
  LIVE_TEST_FILES at A8 in one step; corrector + dark G4 + dead scaffolding at A9. conftest
  arms: :91-115 (compose clients) out at A8, :137-152 (corrector) out at A9, :117-135
  (premium executor + faithfulness) UNTOUCHED, author/factcheck/tour_consistency arms out at
  A6/A8. tests/test_compose_gate_forbidden_scan.py is repointed at A1 and deleted at A4 (its
  own docstring orders deletion when the gate is fixed).
- **D7-tour-build**: scripts/tour_build.py (make tour-build, the /tour-build skill) is
  stripped to the $0 deterministic stitch + render_markdown editorial harness; its whole-tour
  compose stage dies with compose_script. The skill doc is updated to match.
- **D8-kept-modules**: Explicitly KEPT and untouched: selection.py, generation.py (+
  glue_client.py, a hard dependency of generate()), beat_select.py, density.py, ordering.py,
  options.py, fixtures.py, render_md.py, validation.py, verify.py (HaikuFaithfulnessChecker
  is reused by D3), claim_dedup.py, routing.py, routing_client.py, anthropic_client.py,
  certification_provider.py, quality_certification.py, quality_requests.py,
  provider_text_review.py, grade.py, audit.py, batch_regression_manifest.py,
  quality_rubric.py (sibling ledger's file), contract.py (minus the dead
  verify_report/StopVerifyStatus), artifact.py, corpus_places.py, place_materialization.py,
  premium_tour.py, candidate_authoring.py (cap relax only), premium_authorities.py,
  scripts/tour_text_candidate.py (load-bearing, D5 of the old ledger still true).
- **D9-explicit-losses**: Deliberate losses the owner consents to by approving: (1)
  Opus-vs-ChatGPT compose comparison (OpenAIComposeClient + COMPOSE_PROVIDER + render.yaml
  OPENAI_API_KEY); (2) the whole-tour narrative-arc ceiling (per-stop authoring never sees
  sibling stops' text); (3) the never-shipped author-engine track incl. its calibrated
  factcheck judges; (4) compose_certification_candidate (the C3/C8 calibration-anchor
  generator; the anchor DATA stays committed); (5) the compose-metrics scoreboard +
  craft_score + /report-tour-issue skill; (6) compose response attempts becomes constant 1.

## Acceptance criteria (verbatim from state.json)

- **AC-1** (negative): Given the tree after Track A, then src/tour/compose.py,
  compose_correct.py, verify_gate.py, author.py, content_budget.py, tour_consistency.py,
  factcheck.py, claim_repetition.py, compose_metrics.py, scripts/author_tour.py,
  scripts/tour_text_candidate_review.py, tools/compose_snapshot.py and
  .claude/commands/report-tour-issue.md are absent from git ls-files, and the one-engine
  boundary test is green: no compose_script/compose_script_per_chapter import edge anywhere
  in src/ or scripts/, and in src/ the only narration-provider construction is the premium
  executor path.
- **AC-2**: Given the A1 extraction, then premium_authoring_policy_sha256() equals the value
  recorded from the live tree BEFORE the move (byte-identical prompt/schema/model
  constants), and the only remaining importers of src.tour.compose are exactly
  {src/tour/compose.py, src/api/dependencies.py, src/api/routes/trips.py}.
- **AC-3**: Given POST /trips/{id}/compose after cutover, then it returns 200 with fresh
  stop ids and persisted extra_narration, 409 {reason: already_composed}, 404 on unknown
  trip/route, and 422 whose detail carries BOTH reason == compose_verification_failed AND
  attempts — and git diff --stat mobile/ is empty across all of Track A.
- **AC-4** (negative): Given the author-a-prebuilt-route seam driven by a counting offline
  executor, then select_k_routes is never called, exactly one authoring unit is built per
  dwell stop, and a round-trip-shaped route, a 15-stop route, and a receiptless
  (haversine-degraded) route each author successfully.
- **AC-5** (negative): Given an injected unfaithful or coverage-losing mock authoring output
  on the persisted path, then compose returns 422 and the trip's stops in Neo4j are
  byte-unchanged — the real faithfulness checker, the coverage baseline, and full
  validate_script provably run per-stop.
- **AC-6** (negative): Given an injected cross-stop duplicate sentence, then it is suppressed
  in the assembled output of BOTH /trips/{id}/compose and /trips/preview.
- **AC-7** (negative): Given the rewritten compose route, then the spend precheck reserves
  planned_calls == n_stops and runs AFTER the 409 already_composed check (a duplicate
  compose is 409 with zero provider calls and zero reservation), and the conftest
  money-guards still arm: the non-live suite makes zero paid calls.
- **AC-8**: Given /trips/preview after Track A, then tests/test_premium_workbench_wiring.py
  and tests/test_trip_preview_contract.py are green, and the only behavior change on the
  preview surface is the documented echo-dedup pass.
- **AC-9** (negative): Given tests/conftest.py after Track A, then the compose-client arm
  (:91-115) and corrector arm (:137-152) and author/factcheck/tour_consistency arms are
  gone, the premium-executor + faithfulness arm (:117-135) is byte-untouched, and
  src/api/dependencies.py holds no get_compose_client, get_correction_client,
  get_omission_checker, or get_claim_repetition_judge.
- **AC-10**: Given the docs and config after Track A, then Docs/Markdown
  Docs/API_REFERENCE.md describes the per-stop compose engine, standard 01-standard.md's §6b
  (whole-tour-vs-per-chapter divergence) is deleted, specs/2026-07-26-tour-engine-convergence/
  and specs/2026-07-26-tour-rubric-recalibration/ are deleted, render.yaml's OPENAI_API_KEY
  and test_render_manifest's openai entries and pyproject's openai dependency are removed
  (iff zero remaining importers), and make tour-build runs the $0 stitch+render harness.
- **AC-11**: Given make audit at the close (run exactly once), then every shard — lint,
  python, Flutter, workbench, golden, grade, invariants, live, cloud parity — is green with
  0 failures and 0 skips. paid_gate_runs == 1. **Not cited by any step's criterion_ids** —
  it is the whole-run close gate, not an atomic-step outcome; see criteria_uncovered below.

## Baseline (verbatim from state.json, re-confirmed 2026-07-29)

- `make lint -> All checks passed!` — re-ran during this preflight, still clean.
- Commit: `a4043112` (dirty: specs/2026-07-26-tour-engine-convergence/run-context.md
  modified; that folder is deleted by step A10).
- `make _test-golden` is RED at HEAD (golden fixtures pin per-DB ephemeral UUIDs; 0/65 exist
  in data/paris/beats.json). That is the SIBLING ledger's job
  (specs/2026-07-29-tour-rubric-truth), which runs AFTER this one from a worktree branched
  off this ledger's final commit. No step here cites _test-golden.

## Infra probe (read-only, this preflight)

- `docker ps`: `ondoway-valhalla` healthy (:8002), `ondoway-neo4j-workbench` healthy
  (:7689), `ondoway-neo4j-test` healthy (:7688), `ondoway-neo4j` (dev, :7687) healthy — all
  four containers the ladder needs are up.
- `make lint`: `All checks passed!`
- `node .claude/team-engine.test.js`: exit 0, "all 91 checks passed across 17 pathological
  shapes" — the engine's own termination-cap / paid-bar-one-shot / pre-fan-out-gate-order
  guard is currently green.
- Caveat honestly: container-up is not proof of routing (a service answering `docker ps` is
  not necessarily one `make test-file` can reach through env/port config) — this was not
  independently re-verified beyond the containers being healthy and lint/engine-guard
  actually executing against them.

## Pinned gate commands

Every step's files are within `src/` | `scripts/` | `tests/` | `frontend/` | `Docs/` |
`specs/` | `Makefile` | `render.yaml` | `pyproject.toml` | `.claude/` | `tools/`. No step
touches `mobile/`, so `make flutter-analyze` is never a per-step gate.

- A1: `make lint`
- A2: `make lint`
- A3: `make lint`
- A4: `make lint`
- A5: `make lint`
- A6: `make lint`
- A7: `make lint`
- A8: `make lint`
- A9: `make lint` + `make test-file FILE="tests/test_workbench_ui.py::TestDetailViewAndEditing::test_tour_preview_generates_and_plays"` (targeted frontend probe — A9 touches `frontend/review.html`, deleting the corrector's composed_partial/ChatGPT labels; this existing node id exercises the tour-preview rendering path in review.html without invoking the full minutes-long `test-workbench` shard)
- A10: `make lint`

Never put `make test`, `make audit`, `make test-live` or `make test-workbench` in a per-step
gate — those run at phase gates / close only, and `make audit` runs exactly once at the very
end (`paid_gate_runs == 1`).

## Criteria coverage

All of AC-1..AC-10 are cited by at least one step's `criterion_ids`. **AC-11 is uncovered by
design** — it is the close-gate criterion (`make audit`, run once at the end of the whole
ledger), not an atomic step outcome, so no step lists it.

## Notes for later agents

- `make test-file` is NOT read-only: it starts the shared 7687/7688 containers and Valhalla,
  and writes to the shared 7687 dev graph. Exclusive use assumed; never alongside another
  suite (`make test`, a sibling `/team` run, etc.).
- The sibling ledger `specs/2026-07-29-tour-rubric-truth` runs AFTER this one, from a
  worktree branched off this ledger's final commit. `_test-golden` stays RED until then — no
  step here cites it, and no agent may "fix" the golden fixtures in this run.
- Read this file by path — it is the substitute for having the full ledger pasted into every
  agent's prompt.
