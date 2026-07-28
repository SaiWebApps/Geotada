# Salvage — preview failure observability (2026-07-27)

**What this is.** An untracked plan folder (`specs/`, dated 2026-07-25, topic
"preview-failure-observability") was written, judge-reviewed, and never run. Its 8 steps
stayed pending and `approved_by_human` stayed false. It was deleted on 2026-07-27 after the
owner approved removal, conditional on salvaging whatever was still live. This file is that
salvage, and it is the only surviving record.

Two judge consults shaped it. The first ruled **STOP** on a two-item salvage list that
missed an unfiled live defect and eight other things. The second ruled **PROVE-FIRST**,
catching that the source folder's central framing had been overtaken by a commit that
landed the day after it was written. Both corrections are folded in below.

**Anchoring.** The source folder cited line numbers as of `930b1e2`; many had drifted by
`a882af1`. Everything here is anchored to **symbol names and error strings**, resolved live
at `a882af1`. Line numbers are a convenience — trust the symbol.

**Vocabulary.** The source was written around "premium", which decision D7 of the approved
convergence plan retires in favour of **full** / **basic**. Prose uses full/basic; code
identifiers keep their real names.

---

## 1. LIVE DEFECT, UNFILED — a validation gate is silently off in the certification path

**Status: open. This is the highest-value item in this file, and it was recorded nowhere
else.** It has an executable home — `tests/test_compose_gate_forbidden_scan.py`, five
characterization tests pinning the current broken behaviour. Read them before this section:

```bash
make test-file FILE="tests/test_compose_gate_forbidden_scan.py"
```

`test_certification_validator_delegates_only_to_traceability` is the alarm. It inspects the
real nested validator with `ast` and fails the moment that body stops being a bare
delegation. **Mutation-proven**: inserting the natural fix into `compose.py` turns it red,
with a message telling the reader to delete the file rather than adjust the assertion.
`test_the_default_verifier_still_runs_the_full_scan` guards the opposite mistake — making
the two paths agree by making both of them blind.

An earlier draft of that test asserted on `validate_source_traceability` directly. A judge
caught that it would have stayed **green** straight through the fix, since the fix edits the
closure and not that function. If you rewrite these tests, keep the mutation check.

`build_full_verifier` (`src/tour/compose_gate.py:314`) accepts a `base_validator` argument
defaulting to `validate_script` (`src/tour/validation.py:96`), and calls it at
`compose_gate.py:335`.

`validate_script` does two things:

```
validate_script  =  validate_source_traceability   (structural provenance)
                 +  _forbidden_phrase_hits         (validation.py:164)
```

`_forbidden_phrase_hits` scans **glue sentences only** (it skips `source_type == "beat"`,
since the corpus is canonical) for three things: a `FORBIDDEN_PHRASES` list, proper nouns
absent from the cited beat text, and years absent from the cited beat text. It is the check
that catches the writer inventing a name or a date in the connective tissue between sourced
facts.

`finalize_certification_composition` overrides that default:

```python
# src/tour/compose.py:975
base_validator=validate_authorized_sources,
```

and `validate_authorized_sources` (`compose.py:962`) returns
`validate_source_traceability(...)` **only**. The forbidden-phrase scan therefore never runs
in the certification path.

**Why it matters.** `forbidden_phrase_hits` is not inert downstream. It is consumed by
`compose_gate.py:68,94`, `compose.py:515,1406,1450`, `compose_correct.py:407`,
`render_md.py:309` (which prints `- Forbidden phrase hits: **N** (gate: 0)`), and
`src/api/routes/trips.py:793` (which puts `"forbidden": len(...)` on an API response). In
the certification path every one of those reads **0 by construction**, not by measurement.
A report saying a check passed when nothing looked is worse than no report.

**Not a cause of the failures in §2** — it is a gate that is off, a separate defect. The
original judge flagged it as "worth its own ticket, out of scope here" and no ticket was
ever filed. This is the ticket.

**Verified twice at `a882af1`**, independently rather than transcribed: `grep -rn
"base_validator" src/` returns exactly the three sites above, and nothing else.

---

## 2. Five causes behind one message, plus one that now names itself

**Read the date on this section.** The source folder described a world that ended on
2026-07-26, when commit **`f169b78`** — *"feat(api): say why a premium preview failed
instead of blaming the model"* — landed (+98 in `src/api/routes/trips.py`, +1 in
`src/tour/candidate_eligibility.py`, +34 in `tests/test_trips_spend_and_authz.py`).
Everything below is stated against `a882af1`, **after** that commit.

The workbench Generate button POSTs `/trips/preview` (`preview_trip`,
`src/api/routes/trips.py:1022`), which runs the certification path only.

### What is and is not still blind

The source folder claimed the reason was destroyed at three layers — traceback, frontend,
and log. **That is now one layer, not three.** Corrected:

- **Server log: fine.** `trips.py:6` imports `logging`; `trips.py:1142` gets
  `logging.getLogger("ondoway.api")`; `trips.py:1143` calls `_log.exception(...)`, so the
  traceback is preserved, not destroyed. `trips.py:1158` emits one `_log.error` per
  untraceable sentence.
- **Frontend: still blind.** `grep -rn "candidate_rejection" frontend/` returns zero hits.
  The workbench never reads the code or the detail. **This is the only remaining
  unshipped half.** Anchors in §6.

### The dirty-tree cause now names itself

`resolve_build_identity` is caught in its **own** try/except at `trips.py:1104-1113`,
outside the bare-except block, and returns
`CandidateRejectionCode.BUILD_FINGERPRINT_UNAVAILABLE` with `detail=str(exc)` and
`reason="llm_candidate_ineligible"`. The comment above it is explicit: *"it must never be
folded into the generic provider-failure branch below."*

**So do not go hunting the dirty tree first.** A build-fingerprint failure today already
comes back labelled. Earlier advice to "rule out cause A first" is stale and would send a
reader after a cause the system already excludes.

### The five that still share one message

All live inside the same `try` and all still produce `generation_failed`.

| # | Symbol | Cause | Cost when it fires |
|---|---|---|---|
| B | `remap_provider_playback_assignments` (`artifact.py:551`) | raises `"provider sentence cites no frozen playback source"` (`:626`) for any provider sentence whose `(source_id, stop_idx)` is not in the frozen source. **This is what the tester described as "rejects any glue sentences added"** | after spend |
| C | `ComposeVerificationError` (`compose_gate.py:38`) | `authorized_derived_source_ids` + `validate_source_traceability` reject a glue `source_id` absent from that stop's stitched source | after spend |
| D | `verify.py:199` | a `GLUE_REFLECTION` sentence at a slot with **no visited claims** fails closed — `support=None` means no checker call, so `MockFaithfulnessChecker`'s blanket True does not rescue it | after spend |
| E | `compose.py` replay checks | eight pure-replay `ValueError`s: request differs from grounded source, hash inconsistent, responses differ from candidate stops, model mismatch, repeated stop, … | varies |
| F | `derive_playback_assignments` (`artifact.py:524`) / `validate_llm_composed_blueprint` (`artifact.py:971`) | `"one fused sentence cannot cross stop and leg playback contexts"`, raised at **`artifact.py:534`** inside `derive_playback_assignments`. **Beware:** the identical string is also raised at `artifact.py:472` inside `partition_final_script` — a different function. Match on the enclosing `def`, not the string. Note the compose prompt actively *encourages* the cross-beat fusion that trips this | after spend |

Plus: any provider-side exception outside the `anthropic.APIError` tree falls past
`_upstream_provider_errors` (`trips.py:128`) into the bare except.

---

## 3. Correction to a wrong diagnosis — do not let this one come back

The tester's guess was *"an old rule from pre-merge times that will reject any glue
sentences added."* Directionally right about the mechanism, **wrong about the origin**, and
the wrong part is dangerous.

- `GLUE_LABELS` (in `validate_source_traceability`) does predate certification — origin
  commit `a24535a`.
- But `allowed_derived_source_ids` / `authorized_derived_source_ids` were added in
  `d3f3998`, *as* the certification contract. Deliberately stricter.

**The risk if this is lost:** a future session reads the tester's guess, greps, finds
`GLUE_LABELS` predates certification, concludes it is legacy cruft, and deletes a rule that
is actively enforcing the certification contract.

### The real asymmetry: one path recovers, the other does not

- `/trips/generate` → `compose_script` (`compose.py:1341`) — **splices and reverts** around
  an offending sentence.
- `/trips/preview` → `finalize_certification_composition` (`compose.py:890`) — certification
  *"never splices or reverts"* (`compose.py:904`). **One** offending sentence fails the
  **whole** tour.

The workbench Generate button hits the strict one. `Docs/Markdown Docs/API_REFERENCE.md`
compares these two endpoints in detail and does not mention this, so a reader doing exactly
the comparison that section exists for gets the wrong model. A pointer has been added there.

---

## 4. The open product decision — nobody has made this call

**This is the only unresolved *decision* in the source folder, and the stop-index work
cannot be implemented without it.**

When a tour is refused, what goes on the wire to the client?

- **Option A** (what the original plan recommended and all its criteria assumed): the client
  gets `code` + `detail` + `stop_index` + `source_id`. The offending provider **sentence
  text** goes to the server log only.
- **Option B**: put the ungraded provider prose on the wire too.

Option A preserves a contract that is live and documented at
**`src/api/models/trips.py:344-346`**: *"This exposes provenance failure without leaking or
grading the discarded mixed narration."* (The source folder cited this as
`src/api/routes/trips.py` — **wrong file**. Corrected here.)

If the owner picks B, the stop-index and no-leak goals in §5 both change.

---

## 5. Open work — the honest list

The source folder had **18** acceptance criteria. **Seven of its eight planned test node ids
do not exist anywhere in `tests/`** (only step 1's, which was pre-existing).

**Shipped and proven:** the dirty-tree refusal returns its own code with zero provider spend
— asserted at `tests/test_trips_spend_and_authz.py:214-250` (checks
`code == "build_fingerprint_unavailable"`, the detail substring, `executor.calls == 0`,
`reason != "llm_generation_failed"`, with a written undo clause). The same test plus the
shipped logging also cover parts of the log-record and unanticipated-exception goals.

Still open:

| Goal | State |
|---|---|
| Traceability failures get their own reason code | **Not shipped.** `UNCERTIFIED_PROVIDER_TRACE` is defined at `candidate_eligibility.py:19` and emitted nowhere in `src/` — the path still returns `generation_failed` |
| The reason names the offending stop and source | **Not shipped**, and blocked on §4. `CandidateRejection` is `code` + `detail` only, frozen, `extra="forbid"` |
| No traceback / no file path / no API key in the response body | **Not proven, and the surface widened.** `detail=str(exc)` puts an unbounded exception message on the wire with no guard, and zero leak assertions exist |
| The log record carries the rejection code | **Partly.** A logger exists and `_log.exception` preserves the traceback (§2), but the build-fingerprint branch at `trips.py:1104-1113` logs nothing at all, and no record carries the assigned code |
| Exactly one ERROR per request | **Contradicted by shipped code** — `trips.py:1158` emits one per untraceable sentence. An unresolved design conflict, not a missing feature |
| Successful preview logs zero ERRORs | Not proven — no test |
| Response key set is pinned on success | Not shipped |
| Workbench shows the editor the reason | **Not shipped** — see §6 |
| `resolve_build_identity` proven against a temp git repo, not the live tree | Not shipped |

### Negative guards — the regressions a fix could cause

Easy to drop, and they are what stop the fix breaking something else:

- The two existing honest-basic-lane tests (`test_tour_preview_renders_basic_lane_honestly`,
  `test_standalone_tour_preview_renders_basic_lane_honestly`) must keep passing
  **unmodified** — that is what proves the frontend degrades cleanly when the field is absent.
- No element sourced from the rejection block may carry the tour-stop class, and the block
  must not render inside the quality-rubric or narration-quality panels. Same contract as
  §4: ungraded provider prose is never rendered as tour content.
- Already-mapped HTTP errors must still not be swallowed: a provider throttle yields 503 +
  `Retry-After`, a provider fault yields 502, per `_upstream_provider_errors`, with the
  `except HTTPException: raise` short-circuit intact.

**Flake warning, preserved from the original judge ruling:** a test calling the real
`resolve_build_identity()` against the live `REPO_ROOT` passes only while this repo is
dirty, and inverts the moment it is clean. Any such test must drive a **temporary** git repo
and assert both branches.

---

## 6. Where to fix the workbench — the only remaining unshipped half

All live at `a882af1`, all in `frontend/review.html`:

| What | Where |
|---|---|
| The click handler | `:1148` — `if (e.target.closest('#tourGenerateBtn')) { generateTourPreview(); ... }` |
| The button | `:2182` |
| The request | `:3154` — `async function generateTourPreview()` |
| The render, which must show the reason | `:3419` — `function renderTourStops(data, requestedMinutes)` |

`renderTourStops` currently checks only `candidate_eligible === false && data.basic_tour`
and paints a fixed lane. It never reads `candidate_rejection`.

---

## 7. Structural conflict in the `/team` step contract — will recur

The `/team` ledger schema requires every step's `test_command` to be
`make test-file FILE="<path>::<node id>"`. That is **structurally incompatible with any
frontend step**, because the browser suite (`tests/test_workbench_ui.py`) must run only
against the dedicated pre-wiped 7689 instance via `make test-workbench` — which takes no
`FILE` argument and always runs the whole file. Routing it through `make test-file` sends it
at the shared 7688 test DB and breaches the 2026-07-02 isolation invariant.

So for a frontend step there is **no cheap, fully automatic per-step gate**. `make lint`
covers only Python syntax of the touched files. The behavioural proof must be one serial
`make test-workbench` run by a single verifier, outside the atomic ladder — never looped,
never run by parallel skeptics.

`grep test-workbench specs/_templates/team-state.schema.json` returns nothing, and the
approved convergence ledger contains zero references to the browser suite. **This will bite
the next frontend step** — and §6 is a frontend step.

---

## 8. Judge rulings and corrections, preserved

The original plan was ruled **PROVE-FIRST**. Three corrections were made to the planner's
diagnosis before it was written:

1. **False** — "traceability is the ONLY live gate". `verify.py:199` is a second live
   deterministic $0 gate (cause D).
2. **Overstated** — "the suite is blind to the dirty-tree path".
   `tests/test_trips_spend_and_authz.py` covers the *consequence*; the *trigger* and the
   `basic_tour.reason` string are what is uncovered.
3. **Flake by construction** — the `resolve_build_identity` issue in §5.

The judge's stated most-likely failure mode of that plan still applies to anyone picking
this up: *presenting the first two causes as "the" diagnosis, shipping, and discovering the
tester's real cause was E or F.* Name them all; fix none until a real run says which fires.

**Founding-case baseline:** commit `930b1e2`, working tree dirty with 14 entries, both
build-SHA env vars unset.

**Deliberately not preserved** (checked, judged worthless): the 2026-07-25 infra probe, the
lint baseline string, the blast-radius paragraph (already in CLAUDE.md's cost ladder), the
seven never-written test node-id names, the tier-rule derivation, and "do not clean the
tree" — moot, since the shipped test monkeypatches `resolve_build_identity`.

---

## 9. Residuals, known and deliberately deferred

1. If `_preview_stops` itself raises **inside the fallback**, the endpoint still returns 500.
2. `basic_tour.reason` is `"llm_generation_failed"` while `candidate_rejection.code` is
   `"generation_failed"` — an outward contract wart with a live frontend consumer.
