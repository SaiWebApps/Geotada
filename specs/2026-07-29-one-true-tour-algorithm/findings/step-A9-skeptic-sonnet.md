# Step A9 skeptic review — FIX CORRECTNESS angle (sonnet)

Verified against: working tree at `c8ec3969` (HEAD) with the uncommitted Track-A
in-progress changes (`git status` shows A9's files as staged+unstaged deletions/edits
on top of that commit — this ledger accumulates steps before a single close-gate commit,
per the engine's own model).

## Method

I did not trust the developer's pasted diff excerpts. For every one of the 6 checks
`test_corrector_and_dark_g4_are_gone` performs, I independently re-derived the underlying
fact from the actual tree (source reads, `git diff`, `git grep`, a standalone `ast` scan I
wrote myself rather than reusing the test's own helper) and cross-checked it against the
claim text ("compose_correct, verify_gate, claim_repetition, dead deps hooks, empty
g4/omission response blocks, composed_partial + ChatGPT labels, 3 dead eligibility
functions, dead contract fields").

## What I verified myself

1. **Deleted files** — `src/tour/compose_correct.py`, `verify_gate.py`,
   `claim_repetition.py`, `tests/test_claim_repetition.py` are absent from disk (`ls`
   fails) AND absent from `git ls-files`. Confirmed directly, not via the test's helper.
2. **No surviving importer** — `git grep` across the whole repo for
   `compose_correct|verify_gate|claim_repetition` in `src/api/dependencies.py` and
   `src/api/routes/trips.py` returns nothing.
3. **Dead dependency hooks** — `git diff -- src/api/dependencies.py` shows
   `get_compose_client`, `get_correction_client`, `get_omission_checker`,
   `get_claim_repetition_judge` and their `TYPE_CHECKING` imports (`RedundancyJudge`,
   `CoverageJudge`) fully deleted, not stubbed. `git grep` confirms none of the four names
   appear anywhere else in `src/` or `tests/`.
4. **Dead contract fields** — `git diff -- src/tour/contract.py` shows `StopVerifyStatus`
   and `Script.verify_report` deleted. `git grep -n "verify_report=\|StopVerifyStatus("`
   across `tests/ src/ scripts/` returns zero hits — no orphaned construction site
   anywhere (this is the "plausible neighbouring input" attack: a test elsewhere still
   building a `Script(verify_report=...)` would now hard-fail at import/construction time
   with an unexpected-kwarg error; none exists).
5. **3 dead eligibility functions** — `git diff -- src/tour/candidate_eligibility.py`
   confirms `llm_candidate_rejection`, `llm_candidate_ineligibility`,
   `is_complete_llm_candidate` deleted, `CandidateRejection`/`CandidateRejectionCode`
   (the surviving typed-rejection surface the preview route actually returns) kept, and
   the now-unused `from .contract import Script` import removed too (would have been an
   F401/F821 lint failure otherwise — `make lint` exit 0, confirmed by me).
6. **Empty g4/omission response blocks** — I wrote my own standalone `ast` scan of
   `src/api/routes/trips.py` (independent of the test file's `_string_constants` helper)
   and confirmed none of `"g4"`, `"omission_stops_checked"`, `"omission_findings"`,
   `"coverage_omission"` exist as string constants anywhere in the file. The `git diff`
   shows the whole advisory `"g4": {...}` block and the two `omitted_facts`/
   `omission_stops_checked` locals deleted (not just always-empty), matching the claim
   that these were structurally-unreachable-as-non-empty dead code, not live features.
7. **composed_partial + ChatGPT labels** — `git diff -- frontend/review.html` shows
   `_providerLabel`'s `'openai' -> 'ChatGPT (OpenAI)'` branch and
   `_composeStatusLabel`'s `composed_partial` entry deleted. I then checked whether the
   backend can still *produce* either value post-deletion: `git grep -n
   "composed_partial"` across `src/ tests/` returns zero hits outside the test file's own
   constant list — no code path sets `compose_status="composed_partial"` anymore, so this
   is a real dead-label removal, not cosmetic-only removal of a label a live backend value
   still needs.
8. **conftest.py arms** — `git diff -- tests/conftest.py` confirms the compose-client arm
   (`AnthropicComposeClient`/`OpenAIComposeClient` monkeypatches), the corrector arm
   (`AnthropicCorrectionClient`), and the factcheck/redundancy arms are all deleted. I did
   a **byte-exact** Python substring check (not the test's own AST-derived string) of the
   `PREMIUM_FAITHFULNESS_ARM_SOURCE` literal against the live `tests/conftest.py` source —
   it is an exact substring match, confirming the premium-executor + faithfulness arm
   really is untouched, not just structurally-equivalent-but-reworded.
9. **`make lint`** — ran it myself just now: exit 0, "All checks passed!" on `src/ tests/`
   plus the 9 allowlisted `scripts/` files. This is the one command in the evidence chain
   I could safely execute without touching shared state.

## Attacks tried that did NOT break the claim

- Searched all of `Docs/`, `specs/`, `.claude/agents/` for residual mentions of
  `composed_partial`, `verify_report`, the three eligibility function names, and the dead
  response keys — every hit is historical prose (bug reports, old design docs, the
  ledger's own state.json) or the test file itself, never live code. No trap left behind.
- Checked whether `TripPreviewResponse` (`src/api/models/trips.py`) still *types* any of
  the deleted fields even though `trips.py` no longer populates them — it does not; the
  model's `quality`/`compose_status` fields are untyped-enough that removal was clean at
  the route layer without a schema change needed.
- Checked whether `_providerLabel`'s remaining fallback (`p || '—'`) could still render a
  now-impossible value — `provider_name` can be `"anthropic"` or `"offline"`
  (test-only/`OfflinePremiumExecutor`), never `"openai"` anymore anywhere in `src/`. Not a
  regression A9 introduced (pre-existing "offline" fallback path, out of A9's scope).
- Tried to find a construction site of `Script(verify_report=...)` or
  `StopVerifyStatus(...)` anywhere post-deletion (the "over-deletion broke a caller"
  attack) — none exists.
- Tried to find a surviving importer of `compose_correct`/`verify_gate`/
  `claim_repetition` anywhere under `src/`, `scripts/`, or `tests/` — none exists.

## One non-blocking observation (already disclosed, not a new finding)

The pinned gate command for A9,
`make test-file FILE="tests/test_workbench_review_regressions.py"`, does **not** itself
assert on `_providerLabel`/`_composeStatusLabel` or the removed label strings — I grepped
the file and confirmed zero references to `composed_partial`, `ChatGPT`,
`_providerLabel`, or `_composeStatusLabel`. Its 16 tests cover unrelated defects (POI
merge, beat resolution, TTS click-listener dedup). It still has genuine value as a
regression gate — since all 16 tests load `review.html` end-to-end via Playwright, a JS
syntax error introduced by the `_providerLabel`/`_composeStatusLabel` edit would break
every one of them — but it is not a *targeted* functional proof that the labels are gone
from a rendered page; that proof is only the Python-side AST/string-constant scan in
`test_tour_one_engine.py` (a source-text check, not a rendered-DOM check). This gap is
already explicitly disclosed in `run-context.md` ("the naive derivation of a specific
`tests/test_workbench_ui.py::...` node id was previously PROVEN WRONG... this preflight
does not re-derive a node id it cannot verify"), i.e. it was already surfaced and accepted
by the process before this step ran, not something I'm newly uncovering. Not blocking.

## Verdict

**CONFIRMED** on the FIX CORRECTNESS angle. The red-first test
(`test_corrector_and_dark_g4_are_gone`) encodes the real failure mode for every one of the
8 deletion categories the claim lists — I re-derived each one independently from the
actual diff/tree rather than trusting the test's own logic or the developer's pasted
mutation output, and found no strawman, no orphaned caller, and no over-deletion. I did
not execute the pinned node-id test or the Playwright shard myself (shared-DB/port
constraint per the concurrency rules); those are proposed below for the serial verifier.
