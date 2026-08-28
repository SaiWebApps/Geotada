# Batch API Migration Plan

Scope: route the certification compose and review calls through the Anthropic
Batch API for 50% cost reduction. The other cost options (cheaper review model,
compose caching, effort dial, Sonnet 5 compose) stay in the artifact for later.

Ordered safest to riskiest. Each step names the files it touches, its
verification command, and its commit message.

---

## Step 1 — Written ruling on attempt semantics (doc-only)

An expired batch unit did not run and billed nothing. It does NOT consume
its reserved physical attempt. A resubmission runs under the original
PLAN_SHA256, since the request bytes are unchanged. A canceled batch can
still bill units that finished processing before the cancel landed —
those are reconciled at collect time as succeeded or errored, never
silently dropped.

**Files:** this document only.
**Verify:** read it.
**Commit:** `docs(cert): written ruling on batch-attempt semantics`

---

## Step 2 — Probe batch (prove the API works)

A throwaway script that submits one compose-shaped request to the Batch
API — adaptive thinking, json_schema output, Opus 4.8 — polls to
completion, and asserts the result carries `model`, `stop_reason`,
`usage.input_tokens`, `usage.output_tokens`, `usage.cache_creation_input_tokens`,
`usage.cache_read_input_tokens`, and `id`. Costs cents. Run it, don't ask.

**Files:** `scripts/batch_api_probe.py` (new, disposable).
**Verify:** `make test-file FILE=scripts/batch_api_probe.py LIVE=1` or direct run.
**Commit:** `test(cert): probe batch confirms adaptive thinking + json_schema in Batch API`

---

## Step 3 — New module for batch transport + money-guard

Batch transport lives in a NEW module (`src/tour/batch_transport.py`),
never in `tour_batch_candidate.py` (its own SHA is sealed into plans —
editing it invalidates every existing sealed plan).

The conftest money-guard (`_money_guard_no_live_compose`) extends to
cover the new module's batch-submission function IN THE SAME COMMIT.
The hermetic shard must not grow a paid path.

**Files:** `src/tour/batch_transport.py` (new), `tests/conftest.py` (edit).
**Verify:** `make _test-python` — the hermetic shard must pass with the
new module importable but guarded.
**Commit:** `feat(cert): batch transport module with hermetic money-guard`

---

## Step 4 — Receipts schema v2

Batch receipts carry `batch_id` and `result_type` (`succeeded` /
`errored` / `canceled` / `expired`). No `latency_ms` — never backfill
a fake number into a sealed receipt. Bump `schema_version` to
`ondoway-text-candidate-stop-v2`.

The existing receipt reader must accept BOTH v1 (synchronous, has
`latency_ms`) and v2 (batch, has `batch_id` + `result_type`). The
v1 frozen control arm is never rewritten.

**Files:** `src/tour/batch_transport.py` (edit), receipt-reading code.
**Verify:** `make _test-python` — existing receipt tests still pass,
new v2 shape tests added.
**Commit:** `feat(cert): receipt schema v2 for batch results (no latency_ms)`

---

## Step 5 — Submit/collect split with durable batch_id

The batch submission persists `batch_id` to disk the instant
`batches.create()` returns, BEFORE polling starts. A laptop closing
or terminal dying during the poll loop must not orphan the money.

A resume-by-poll path can collect results from a prior submission.
Collection is idempotent — running it twice on the same batch_id
produces the same receipts.

**Files:** `src/tour/batch_transport.py` (edit), `scripts/tour_batch_candidate.py` (minimal — call the new module).
**Verify:** submit a real 1-unit batch, kill the process during poll,
resume and collect. Receipts match.
**Commit:** `feat(cert): submit/collect split with crash-safe batch_id persistence`

---

## Step 6 — Sequencing: calibration-first, then facts, then enjoyment

Calibration runs as its own batch (1 request, fast). If it fails, the
run stops without spending money on review calls. Then the canary fact
unit. Then the remaining fact units. Then enjoyment.

Non-succeeded results (errored / canceled / expired) map into the
existing durable-failure recording — same coordinator machinery,
new result-type mapping.

**Files:** `scripts/tour_batch_review.py` (edit to use batch transport),
`src/tour/batch_transport.py` (may need sequencing helpers).
**Verify:** `make tour-batch-review-plan` still produces a valid plan.
A live run with a small subset succeeds.
**Commit:** `feat(cert): batch review with calibration-first sequencing`

---

## Step 7 — Wire the live targets and run the full bar

New Makefile targets or flags that route through batch transport.
Requires a new `OUTPUT_ROOT` (the frozen v1 control arm is untouched).

Run the full batch. Then run the whole test tree (`make test`) —
the close bar is ALL of `tests/`, not just the new files.

**Files:** `Makefile` (edit), any wiring needed.
**Verify:** `make audit` (lint + full test suite).
**Commit:** `feat(cert): batch API wired for tour-batch-live and tour-batch-review-live`
