# Step A5 — hostile skeptic (NEGATIVE SPACE angle)

Verified against: `c8ec39690030901660c843d46910bedb40e84c13`
("chore(certification): re-stamp the standard's pin after the C11 demotion"),
working tree DIRTY (Track A work is uncommitted; `src/tour/authoring.py`,
`tests/test_tour_authoring_gates.py`, `tests/test_tour_authoring_from_route.py`,
`tests/test_tour_authoring_extraction.py` are UNTRACKED).

Ran myself (allowed under the concurrency constraint): `make lint` -> `All checks
passed!`, exit 0, unpiped. That half of the evidence reconciles exactly.
Everything else below is derived by reading the tree; nothing container-touching
was executed, and no reproduction below is claimed as executed.

## What the mutation drill DOES prove

The undo-test is real. Reverting the `_dedup_composed(...)` call at
`src/tour/authoring.py:631-634` is the only hunk that can produce the quoted
assertion, and the assertion text matches surface 1's `all_texts.count(_DUP_TEXT)
== 1` at `tests/test_tour_authoring_gates.py:712`. The test genuinely drives both
named surfaces (`author_prebuilt_route` at :709 and `finalize_premium_composition`
at :726) rather than arguing parity from a shared callee. I could not break that
part.

## F1 — "satisfies AC-8" is unproven by its own text (evidence gap)

AC-8 (verbatim, run-context:160): "Given /trips/preview after Track A, then
tests/test_premium_workbench_wiring.py and tests/test_trip_preview_contract.py are
green, and the only behavior change on the preview surface is the documented
echo-dedup pass."

The evidence set is four commands: `make lint` plus the same node id three times
(baseline / mutated / restored). Neither file AC-8 names by path was executed.
`state.json` A5 lists `criterion_ids: ["AC-6","AC-8"]`, so this is not my
interpolation. These are not inert files: `test_trip_preview_contract.py:485-495`
drives the real `preview_trip` end to end and asserts
`compose_status == "composed"` / `candidate_eligible is True` — and every
post-planning exception in `preview_trip` (`src/api/routes/trips.py:1147-1195`) is
swallowed into the Basic-tour fallback, which would flip exactly those assertions.
A5 changed what that path produces.

Proposed serial reproduction (I did not run it):
- `make test-file FILE="tests/test_trip_preview_contract.py"`
- `make test-file FILE="tests/test_premium_workbench_wiring.py"`
- `make test-file FILE="tests/test_tour_certification_compose_replay.py"`

## F2 — the dedup is a total NO-OP on a keyless corpus, and London is live

AC-6 is unqualified: "Given an injected cross-stop duplicate sentence, then it is
suppressed ... on BOTH surfaces". The fixture at
`tests/test_tour_authoring_gates.py:553-565` gives both beats non-empty
`key_claims`. Strip them and NOTHING in `_dedup_composed` can fire across stops:

- `suppress_repeated_claims` builds `claim_sigs_by_beat` from `b.key_claims`
  ONLY (`src/tour/claim_dedup.py:165-168`) — not from the keyless-aware
  `_claims_for_coverage` — and bails per sentence with
  `if not claim_sigs: continue` (:190-191).
- `suppress_exact_repeats` is same-STOP only (`seen_by_stop[s.stop_idx]`, :253/:261).
- `suppress_same_beat_near_duplicates` is same-`source_id` only (:321).

So for a corpus whose beats carry no `key_claims`, a cross-stop echo ships on both
surfaces, unchanged. The repo names such a corpus itself:
`src/tour/claim_dedup.py:337-338` — "A KEYLESS corpus (e.g. London — every beat has
`key_claims=()`)". London is an onboarded city. AC-6 therefore holds for Paris/NYC
shape data and is silently false for London shape data; the claim states no such
scope.

Proposed reproduction: parametrize `_cross_stop_echo_fixture` with
`key_claims=()` on `beat0`/`beat1` and re-assert `count(_DUP_TEXT) == 1`. I
predict it fails 2 != 1 on BOTH surfaces. This test does not exist yet, so there
is no command to hand the serial verifier.

## F3 — A5 turned a live provenance guard into a tautology, untested

`src/tour/authoring.py:706-708`:

    source_sentences = provider_source
    if final_sentences != source_sentences:
        raise ValueError("final composed text differs from the provider response")

Before A5, `provider_source = composed_by_stop[stop_index]` held
`unit.parsed_provider_sentences` — the parsed payload of THAT stop's response — so
the check bound the shipped per-stop text to the right provider response. A5 added
:642-645, which REBUILDS `composed_by_stop` by filtering the final deduped stream
on `stop_idx`. Both sides of the comparison are now the identical comprehension
over the same list (`final_script.script` is `tuple(composed_sentences)`, :646-652,
:731), so the branch is unreachable by construction.

`grep -rn "final composed text differs" src tests` returns exactly one hit — the
raise. Zero tests. So nothing went red when the guard died.

What it used to catch is reachable: `_sentences_from_json` (:456-487) coerces
`stop_idx` from the request only for KNOWN beat ids; glue/reflection sentences and
hallucinated beat ids keep the model's own `stop_idx` (:466-467, :475). A stop-1
response emitting a sentence labelled `stop_idx=0` was previously a hard refusal;
it is now silently re-bucketed into stop 0's `CompositionTrace` and attested under
stop 0's `request_sha256`/`response_sha256` with `derivation="provider_response"`.
`artifact.py:389-410,735-771` only checks self-consistency, so the blueprint
validator passes a trace that lies about which response produced the text. That is
the exact property `finalize_certification_composition`'s docstring calls "the
durable replay boundary".

The A5 test pins `response_sha256 == sha256(raw body)` and
`source_sentences == shipped`; neither can see this, because the mis-attribution
is self-consistent.

Proposed reproduction (test does not exist): feed two stops where stop 1's
executor emits an extra glue sentence with `stop_idx=0` and an authorized derived
source id, then assert the finalizer refuses. I predict it returns 200-equivalent
with the sentence attested under stop 0.

## F4 — a third surface reaches the finalizer and does NOT get the dedup

`finalize_certification_composition` is reached from five places, not two:
`authoring.author_prebuilt_route:957`, `premium_tour.finalize_premium_composition:494`
(preview), `premium_tour.finalize_premium_tour:593`, `compose.compose_certification_candidate:540`,
and `scripts/tour_batch_candidate.py:199`.

The batch runner is the interesting one. `scripts/tour_batch_candidate.py:174-199`
builds the SHIPPED artifact — `stops[].sentences`, `ordered_text`,
`customer_text_sha256` — from `_sentences_from_json(...)` (raw provider payload) and
then calls `finalize_premium_composition(...)` purely as a validation replay,
DISCARDING its return value. So the batch/certification artifact that human
reviewers grade, and that `scripts/tour_batch_review.py:344-359` cross-checks,
still carries the cross-stop echo that both AC-6 surfaces now suppress. The
"ONE algorithm" headline does not hold for the artifact the quality anchors are
measured on.

Verified by reading; no runnable reproduction proposed (`make tour-batch` is a
paid/long path and is out of bounds).

## F5 — the ledger's own misattribution remedy is broken for this file

`git status --porcelain` shows `?? src/tour/authoring.py`. Consequences the
evidence itself half-admits ("Since authoring.py is untracked, git diff shows
nothing for it"):

1. A5's diff cannot be reviewed with git at all — the mutation drill's integrity
   rested on a hand-made backup copy, with no git-recoverable baseline. Per
   CLAUDE.md, untracked files are not recoverable.
2. run-context:276-278 prescribes, for the named top risk of this run: "`git stash`
   the step's work and re-run the failing shard". `git stash -h` (run, read-only)
   confirms untracked files require `-u`/`--include-untracked`. A plain `git stash`
   leaves `src/tour/authoring.py` — i.e. ALL of A1-A5 — in the tree. Anyone
   following the written remedy would "clear" the step's work, still see the red,
   and attribute a real A5 regression to the baseline.

## F6 — on preview the dedup has neither a coverage gate nor a fail-open

`premium_tour.finalize_premium_composition:494-500` calls the finalizer with no
`faithfulness_checker` and with `enforce_claim_coverage` left at its `False`
default, while `src/api/routes/trips.py:784-790` passes
`enforce_claim_coverage=True, scan_glue_for_invention=True` on the persisted path.
The ported docstring (`authoring.py:545-547`) concedes the point in a parenthesis:
"Always run BEFORE verify (with the pre-compose coverage baseline, WHEN THE CALLER
ENABLES IT)". Preview does not enable it. Neither does the batch runner, nor
`compose_certification_candidate`.

That matters because `claim_dedup.py:354-356` states the design's whole safety
argument: "Over-gating a bold paraphrase is the tolerable failure direction:
`_prefer_deduped` fail-opens to the complete stitched original — no fact lost".
`_prefer_deduped` lives only in `compose.py` (grep: `compose.py:713`), was NOT
ported into `authoring.py`, and `compose.py` is deleted at A8. So on the three
un-gated surfaces the dedup is now a bare, irreversible delete.

The concrete loss mechanism is `suppress_same_beat_near_duplicates`
(`claim_dedup.py:296-330`): rapidfuzz `token_set_ratio >= 90`, where a sentence
whose token set is a SUPERSET of an earlier same-beat sentence scores 100 — i.e. a
longer sentence that ADDS a fact is dropped as a "near-verbatim restatement". On
the compose path the coverage baseline turns that into a 422; on preview it turns
into silently shipped fact loss, on the surface the editor reviews. Before A5,
preview ran no dedup at all, so this failure mode is NEW.

I did not execute rapidfuzz to demonstrate the superset-scores-100 property; that
is the missing evidence for this item.

## F7 (low) — an emptied stop degrades preview to Basic AFTER the money is spent

`CompositionTrace` requires `sentence_indexes`/`source_sentences` `min_length=1`
(`artifact.py:383-386`). If dedup removes every sentence of a stop, `finish()`
constructs a trace with empty tuples and pydantic raises (a `ValueError` subclass).
On `/trips/{id}/compose` that is caught and becomes a 422 (`trips.py:799-825`) —
acceptable. On `/trips/preview` it lands in the catch-all at `trips.py:1147` and
returns the Basic-tour fallback with reason `llm_generation_failed`, AFTER
`execute_premium_plan` has already billed one call per stop. Reachability is
narrow: only vignette beats are exempt from the never-empty restores
(`claim_dedup.py:206-210`, :267-272), so it needs a stop whose surviving content is
vignette-only. Untested either way; `test_cross_stop_echo_is_suppressed:745-748`
asserts no stop is emptied for its own two-stop fixture only.

## Verdict

The undo-test is REAL and the fix does what its one test says on keyed-corpus,
two-stop, well-formed input. The CLAIM is broader than the evidence:
- AC-8 is UNPROVEN — neither test file it names was run (F1).
- AC-6 is proven for keyed corpora only; it is a no-op on a live keyless corpus (F2).
- The change silently retired an untested provenance guard on the certification
  replay boundary (F3) and left a third finalizer caller un-deduped (F4).
