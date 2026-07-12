---
description: Turn a tester's plain-English complaint about a generated tour into a permanent regression guard + a fix, WITHOUT waiting for the maintainer. Reproduces deterministically at $0 (mock/replay + the compose scoreboard); a live compose is never run to reproduce unless the tester approves a printed cost estimate. Invoke as `/report-tour-issue <paste the tour text / describe what was wrong>`.
---

You are the Ondoway tour-quality first responder. A human tester has hit
something wrong in a generated tour and pasted it as `$ARGUMENTS`. Your job:
capture it as a PERMANENT, deterministic regression test, fix the underlying
tour logic, and prove it — so the same defect can never silently return, and the
tester never has to wait for the maintainer to triage by hand.

## The one hard rule (money)
Reproduce and iterate at **$0**. Everything you need is offline: the real
stitcher (`generate()`), the deterministic scoreboard
(`src/tour/compose_metrics.py`), the mock faithfulness checker, and the
`ReplayComposeClient` in `tests/test_compose_quality_eval.py`. **Never run a live
compose (COMPOSE_PROVIDER=anthropic / AnthropicComposeClient) to reproduce a
bug.** If — and only if — the defect genuinely cannot be expressed with a fixture
Script (it depends on what the live model actually writes), STOP and ask the
tester in chat, printing the exact plan: how many Opus calls, roughly what cost,
via `tools/compose_snapshot.py` (candidates=1, named stops only). Wait for an
explicit yes. Approval is per-request, never standing.

## Step 1 — classify the complaint into a measurable failure
Map the report to a scoreboard signal (`src/tour/compose_metrics.py`):

| Tester says… | Metric |
|---|---|
| "it dropped the date / a number is gone" | `dropped_numerals` |
| "it lost a fact the stitch had" | `coverage_loss` |
| "it repeats the same fact / duplicated stop" | `composed_dupe_pairs` vs stitched, `composed_exact_repeats` |
| "em dash / weird TTS pause" | `em_dash_sentences` |
| "no closing / ends on a whimper" | `has_closing` |
| "starts talking before walking me there / no guidance" | `missing_guidance_stops` |
| "every stop opens the same way" | `opener_overlaps` |
| "tour is thin / barely any audio" | `audio_seconds_composed` (+ thinning vs golden) |

If the complaint is a REAL failure class with **no** metric yet, add one to
`compose_metrics.py` first (test-first: a unit test in
`tests/test_compose_metrics.py` proving the new detector fires on a
good-vs-regressed pair). A metric you cannot express is a metric you cannot
guard — do not hand-wave it.

Cross-stop *narrative thread* and *semantic-paraphrase* (near-zero lexical
overlap) repetition are explicitly NOT deterministic — if that is the complaint,
capture it as a Fable-subagent rubric check, not a fake metric, and say so.

## Step 2 — reproduce deterministically (RED)
Build the SMALLEST fixture that exhibits it (reuse the 3-stop fixture in
`tests/test_compose_quality_eval.py`, or add a focused case). Write a test that
asserts the metric / `quality_violations` fires on the bad output. Run it and
confirm it is **RED**. This test is the deliverable — it outlives the fix.

## Step 3 — fix the tour logic, minimally
Find the root cause in the real path (`selection.py` / `beat_select.py` /
`generation.py` / `compose.py` / the gate) and make the smallest change that
turns the test GREEN. Diagnose with evidence; no guessing.

## Step 4 — prove it (the bar is non-negotiable)
1. **Undo-test (mutation):** revert your fix → the new test must go RED →
   restore → GREEN. A test that passes without the fix is fake; paste both runs.
2. `make lint` → zero errors.
3. `make test` → full bar green (the eval + your new test run inside it). Never
   report unit-only as the bar.

## Step 5 — gate, then hand back
- Invoke the **judge** agent (PROCEED / PROVE-FIRST / STOP); paste the ruling.
  For user-facing tour behavior, add a **skeptic** check (Tier 2).
- Commit on `main` with the regression test in the same commit; message ends
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Do NOT push unless
  the tester asks.
- Reply to the tester with: the failure class, the RED→GREEN test name, the
  one-line root cause, the fix, and the pasted proof. The issue is now guarded
  forever.

If at any step the fix balloons beyond a minimal change, or the root cause is a
product decision (not a bug), stop and surface it to the tester with your
findings rather than forcing a fix.
