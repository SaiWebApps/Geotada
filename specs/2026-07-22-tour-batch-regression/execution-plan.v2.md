# Frozen 4 Paris + 4 NYC Tour Regression Plan — Version 2

Status: **NOT YET APPROVED BY HASH**  
Execution rule: prerequisites P1–P10 must be implemented and verified before Step 1.

## Tour Finish Invariant

> TOUR FINISH INVARIANT LOADED: Customer experience is the product. Evaluator failures
> are not tour failures. Only confirmed material customer harm can block shipping. When
> the ship criteria pass, declare SHIP and deliver the tour without inventing new gates.

## Prerequisites

| ID | Required control | Completion evidence |
|---|---|---|
| P1 | Commit this versioned, hash-sealed plan and bind its hash outside the repository. | Commit SHA plus the user's approval of the exact plan hash in chat. |
| P2 | Add a state-machine runner that permits only the next numbered step. | Out-of-order and skipped-step tests fail before side effects. |
| P3 | Require every executable action through its corresponding Make target and the approved plan hash. | Wrong/missing target hash tests fail before action dispatch. |
| P4 | Implement a fail-closed batch paid-call authorization mechanism requiring a sealed manifest of exactly eight unique full request hashes; while unbound, refuse all batch provider construction. | Unbound, missing, 7/9-entry, duplicate, malformed, wrong, or ninth-request cases fail before provider construction; synthetic hashes are labeled mechanism-only. |
| P5 | Keep Anthropic credentials unavailable until the paid-run step. | Credential is externally withheld and released only through the approved paid-run boundary. |
| P6 | Record every completed step and artifact hash in an externally anchored append-only ledger. | Local hash chain verifies and its terminal hash is anchored outside agent-writable storage. |
| P7 | Require every checkpoint to contain Step, Result, Evidence, and Next step. | State transition rejects an incomplete checkpoint. |
| P8 | Stop on any unlisted action or changed input until the user approves a new plan version. | Mutation/unlisted-action tests fail closed and a new approved hash is required. |
| P9 | Make CI and branch protection reject changes unless plan conformance and the full suite pass. | Remote protection requires CI checks and cannot be bypassed by an agent-authored merge. |
| P10 | Require separate independent review for changes to the plan, runner, or guards. | Remote CODEOWNERS/review evidence identifies a reviewer other than the implementing agent. |

## One-minute execution rule

Each numbered action is capped at 60 seconds of active work. Long tests and provider
calls are started asynchronously and checked using a repeated polling action lasting
at most 60 seconds. No hidden deadline is imposed on Anthropic.

## A. Freeze the experiment

| # | Goal | Action | Expected result | Verification | Risks and mitigation |
|---|---|---|---|---|---|
| 1 | Preserve baseline | Record branch, HEAD, and dirty files. | Exact starting state. | Saved baseline artifact. | Never reset or broadly stage unrelated files. |
| 2 | Establish executable entry points | Add empty Make targets for batch planning, testing, authoring, and review. | All later commands follow project policy. | `make help` lists targets. | Targets initially perform no writes or calls. |
| 3 | Define manifest contract | Add typed schema for city, start/end, duration, route mode, and lenses. | Requests are machine-validatable. | Schema unit test passes. | Reject undeclared tuning fields. |
| 4 | Freeze Paris set | Add four diverse Paris request specifications. | Four fixed Paris inputs. | Manifest reports Paris count 4. | Select before seeing output. |
| 5 | Freeze NYC set | Add four diverse NYC request specifications. | Four fixed NYC inputs. | Manifest reports NYC count 4. | Preflight evidence coverage before spending. |
| 6 | Seal and bind inputs | Seal the eight real inputs, hash each, create the canonical manifest, and bind those exact hashes into the P4 authorization before any paid call. | Immutable experiment identity and concrete paid-call roster. | Only those eight actual hashes authorize; provider call count remains zero. | Any edit invalidates prior output and authorization. |
| 7 | Test diversity | Assert 4+4 cities and distinct route/timebox archetypes. | Meaningful coverage. | Deterministic test passes. | Use structural assertions, not lexical lists. |
| 8 | Freeze quality policy | Bind the five ship criteria and golden references by hash. | No moving rubric mid-run. | Policy hashes appear in plan. | Unknown gates are rejected. |

## B. Generalize the algorithm

| # | Goal | Action | Expected result | Verification | Risks and mitigation |
|---|---|---|---|---|---|
| 9 | Remove Paris hardcoding | Extract city-neutral corpus loading. | Paris and NYC use one path. | Loader tests pass for both. | Prohibit city-specific authoring branches. |
| 10 | Generalize route construction | Accept one frozen manifest request. | Deterministic route plan. | Same input produces same route identity. | Preserve Valhalla receipts and hashes. |
| 11 | Generalize source assembly | Bind selected beats to repository evidence. | Grounded narration requests. | Evidence IDs resolve to actual text. | Exclude Apple-proxy material at data boundaries. |
| 12 | Generalize authoring plan | Produce stop-level Anthropic requests for any city. | One reusable path. | Eight dry plans validate. | Provider text remains immutable. |
| 13 | Preserve model policy | Retain proven Anthropic model and adaptive thinking. | No provider deviation. | Request-envelope test. | No automatic downgrade for latency. |
| 14 | Enforce Premium lane | Require complete provider-authored narration. | Stitched output cannot enter evaluation. | Typed provenance test rejects fallback. | No regex or phrase lists. |
| 15 | Preserve Basic separately | Record fallback availability outside Premium artifacts. | Fallback cannot affect grades. | Premium scorecard has no Basic fields. | Separate types and directories. |
| 16 | Add durable receipts | Save requests and responses atomically. | Safe resume. | Resume test makes zero duplicate calls. | Request hash is idempotency key. |
| 17 | Bound provider retries | Retry only missing customer content, once after diagnosis. | No spending loop. | Retry-count test. | Reviewer errors never trigger regeneration. |
| 18 | Separate statuses | Store tour status independently from evaluation status. | Infra errors cannot reject good tours. | State-transition and mutation tests. | Enforce separate typed fields. |
| 19 | Build tour renderer | Assemble exact customer-visible narration. | One readable artifact per tour. | Stop/text hashes match receipts. | Completeness assertion prevents truncation. |
| 20 | Build scorecard renderer | Emit five criteria plus both statuses. | Clear SHIP or BLOCKED_MATERIAL. | Schema test. | Exhaustive schema rejects extra vetoes. |

## C. Make it permanent

| # | Goal | Action | Expected result | Verification | Risks and mitigation |
|---|---|---|---|---|---|
| 21 | Test orchestration | Add deterministic provider fixtures for all eight requests. | Full zero-spend workflow. | Eight test artifacts. | Assert exact request hashes. |
| 22 | Test material blocking | Inject one materially false claim fixture. | Only that tour blocks. | Exact customer harm appears. | Require semantic structured verdict. |
| 23 | Test evaluator failure | Inject malformed reviewer output. | Tour status remains independent. | Evaluation INFRA_ERROR without invented tour failure. | Regression test prevents coupling. |
| 24 | Test geographic failure | Inject impossible routed leg. | Correct material block. | Route evidence fails criterion. | Require routed receipt. |
| 25 | Test timebox failure | Inject required activity exceeding duration. | Correct material block. | Time arithmetic proves overrun. | Optional time stays excluded. |
| 26 | Test enjoyment comparison | Score fixtures against frozen gold. | Reproducible gold-relative result. | Calibration hashes and axes match. | Hash mismatch fails. |
| 27 | Add permanent test target | Attach deterministic 4+4 workflow to `make test`. | Every full suite checks it. | Test collection includes batch tests. | Fixtures keep it zero-API. |
| 28 | Add live gate | Add explicit paid 4+4 target using identical code. | Scheduled/release model-drift test. | Dry/test hashes match. | Assert shared implementation. |
| 29 | Run focused tests | Start batch regression asynchronously. | Focused suite begins. | PID recorded. | Poll via Step 30. |
| 30 | Poll tests | Read output for no more than 60 seconds; repeat as needed. | Visible progress. | Exit status and log. | Diagnose after two actual failures, not silence alone. |
| 31 | Run full suite | Start `make test` asynchronously. | Repository proof begins. | PID recorded. | Report unrelated failures separately. |
| 32 | Poll full suite | Repeat Step 30 for full suite. | Final suite result. | Exact counts and exit status. | No completion claim before exit. |

## D. Execute the live 4+4 run

| # | Goal | Action | Expected result | Verification | Risks and mitigation |
|---|---|---|---|---|---|
| 33 | Preflight without spend | Generate sealed live plan and cost estimate. | Exact requests/call count/exposure. | Zero provider receipts. | Estimate only; no invented cost cap. |
| 34 | Audit adherence | Independent guard checks hashes, lanes, and policy. | PROCEED or exact correction. | Ruling saved. | Process audit cannot invent quality gates. |
| 35 | Launch authoring | Submit eight Anthropic tours with controlled concurrency. | Generation begins. | Eight request IDs. | Bounded workers handle rate limits. |
| 36 | Poll authoring | Poll no more than 60 seconds; repeat. | Incremental completion. | Receipts and provider IDs. | Durable visible progress. |
| 37 | Recover missing output | Diagnose and retry only genuinely missing narration once. | Text or explicit provider failure. | Retry cause/count. | Two-attempt anti-loop rule. |
| 38 | Assemble tours | Render complete provider outputs unchanged. | Eight full-tour documents. | Hashes match receipts. | No hand polishing before grading. |
| 39 | Launch evaluation | Submit factual and enjoyment reviews. | Semantic assessment begins. | Review request IDs. | Provenance assertion excludes stitched text. |
| 40 | Poll evaluation | Poll no more than 60 seconds; repeat. | Incremental completion. | Durable review receipts. | Malformed response affects evaluation state only. |
| 41 | Compute route/time | Evaluate geography and active time. | Two criteria per tour. | Receipts and arithmetic. | Only required activities count. |
| 42 | Compute statuses | Apply exactly five criteria. | SHIP or BLOCKED_MATERIAL per tour. | Decision trace uses only frozen criteria. | Five passes force SHIP. |
| 43 | Correct material defects only | Change smallest shared algorithm rule, never narration. | General correction. | Changed hashes identify affected tours. | No regex, lexical lists, or POI exceptions. |
| 44 | Rerun affected requests | Regenerate only hash-invalidated output. | Honest post-fix evidence. | Unaffected hashes unchanged. | Hash dependencies prevent cherry-picking. |
| 45 | Freeze accepted output | Store successful live artifacts as fixtures. | Future replay regression. | Fixture/live hashes match. | Scheduled live gate still tests model drift. |
| 46 | Final adversarial check | Audit provenance, hashes, statuses, and deliverables. | No process violation. | Evidence checklist. | Only material harm may block. |
| 47 | Deliver results | Show eight full tours and scorecard. | Direct customer evaluation. | Eight working artifact links. | Lead with tours and outcomes. |

## Version history

Version 2 supersedes Version 1 solely to remove the P4/Step 6 dependency cycle. P4 installs the unbound fail-closed mechanism; Step 6 binds the eight real request hashes. Every other prerequisite and numbered step is unchanged.

## Current enforcement state

All P1–P10 are pending. GitHub branch protection is disabled. The Anthropic key is
present in `.env`, though absent from the current shell. No external immutable ledger
or independent protected reviewer is configured. This document is not enforcement.

## Dirty-worktree baseline before this file

- HEAD: `6805c50cffa5df4a9b1a45b1e8da5ef79107edc3`
- Branch: `main`, one commit ahead of `origin/main`
- Modified tracked files: 56
- Untracked paths: 174
- Tracked diff: 6,597 insertions and 3,664 deletions
- `git status --porcelain=v1` SHA-256:
  `7195c92652308e65d336436fce608266e1d94e11b3c612be02a6c2da4b185e4e`
- No broad staging, reset, cleanup, or rollback is authorized.

## Incident record

During the prerequisite audit, a judge's unsafe shell quoting accidentally invoked
`make test`, starting the existing Neo4j dev and test containers. The exact spawned
make/pytest processes were terminated. The containers were left running to avoid an
unapproved shared-infrastructure stop. No Anthropic calls occurred.
