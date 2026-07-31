# Skeptic panel — step A1 (sonnet), FIX CORRECTNESS angle

Verified against working tree on top of commit `c8ec39690030901660c843d46910bedb40e84c13`
(clean HEAD; A1's work is uncommitted: `src/tour/authoring.py` and
`tests/test_tour_authoring_extraction.py` untracked, 12 tracked files modified in place).
I ran `git status --short` myself before starting; this matches the evidence bundle's
description of the tree.

## Verdict: CONFIRMED

I re-derived every load-bearing fact myself, hermetically (pure `ast`/`json`/`hashlib` on
file contents, no project import, no DB, no `make test-file`), rather than trusting the
evidence bundle's pasted output or the two sibling reviews already sitting in this folder.
I found and fixed a bug in my OWN first pass (a naive `ast.literal_eval` that didn't
resolve `CERTIFICATION_COMPOSE_MAX_OUTPUT_TOKENS = COMPOSE_MAX_OUTPUT_TOKENS`'s
name-reference indirection, which briefly made it look like the hash inputs differed
pre/post-move — a false alarm from my own script, not a real defect) and a second bug
(not resolving relative-import `level` when replaying the mutation, which made HEAD's
`premium_tour.py` look like it imported nothing at all). Both are recorded below so the
confirmation is falsifiable, not asserted.

## What I independently re-derived (read-only, no shared state)

1. **`make lint`** — ran it myself: exit 0, `All checks passed!`.

2. **Byte-identical policy hash, computed from source, both sides.** Extracted
   `COMPOSE_MODEL`, `CERTIFICATION_COMPOSE_MAX_OUTPUT_TOKENS` (resolving its
   `= COMPOSE_MAX_OUTPUT_TOKENS` indirection), `_COMPOSE_SYSTEM`, `_COMPOSE_OUTPUT_SCHEMA`
   by AST from `git show HEAD:src/tour/compose.py` (pre-move) and the working-tree
   `src/tour/authoring.py` (post-move), reconstructed
   `premium_authoring_policy_sha256()`'s exact payload/canonicalization
   (`{"model","max_tokens","thinking":{"type":"adaptive"},"system","output_schema"}`,
   `json.dumps(ensure_ascii=False, allow_nan=False, separators=(",",":"), sort_keys=True)`,
   sha256) and hashed both sides myself:
   `pre_hash == post_hash == ed5f149e8d9be1dbff74f83f650db115a92cc4a38fa02f16f0f0fa29725611fd`
   — matches `PRE_MOVE_AUTHORING_POLICY_SHA256` pinned in the test file exactly.

3. **All 8 non-policy moved definitions are byte-identical, not just the 4 hashed
   constants.** `ast.get_source_segment` + `difflib.SequenceMatcher` on
   `CertificationComposition`, `CompletedCertificationComposeUnit`, `ComposeRequest`,
   `_certification_compose_requests`, `_sentences_from_json`,
   `candidate_compose_request_envelope`, `compose_input_sha256`,
   `finalize_certification_composition` between `git show HEAD:src/tour/compose.py` and
   `src/tour/authoring.py`: ratio `1.0` on all 8, i.e. byte-identical source text. AC-2's
   text only requires the hash of the 4 policy constants, but the broader "byte-identical
   extraction" framing in the claim covers all 12 names, and I checked the other 8 myself
   rather than take that on faith.

4. **Importer-pin completeness, re-implemented independently.** Wrote my own AST scanner
   (same relative-import resolution as the test) over `src/`, `scripts/`, `tests/`,
   `tools/`: 15 total importers of `src.tour.compose` found, `UNACCOUNTED: []`,
   `STILL_MISSING: []` against `PINNED_COMPOSE_IMPORTERS` (3) +
   `COMPOSE_IMPORTERS_DELETED_BY_A_LATER_STEP` (12).

5. **All 12 files A1 actually touches (not just `premium_tour.py`) resolve their
   `.authoring` imports against real names.** For every file in A1's `files` list
   (`premium_tour.py`, `compose.py`, `provider_text_review.py`, the 4 scripts, the 3 test
   files touching `.authoring`), I collected every name each imports from `.authoring` and
   checked it against the set of names actually defined at module level in
   `authoring.py`: zero missing across all 10 consuming files. This is stronger than what
   the cited gate proves (which only checks `premium_tour.py`'s import *statement*, not
   whether the names it lists really exist, and says nothing about the other 9 files).

6. **`compose.py` re-exports what it needs.** The working-tree `compose.py` re-imports
   14 names (including the non-premium `_compose_user_prompt`, `COMPOSE_MAX_OUTPUT_TOKENS`)
   from `.authoring`, so every surviving external `from src.tour.compose import X` for a
   moved name still resolves through `compose.py`'s own re-export — the 8 A8-scheduled
   test files and `tests/conftest.py`'s compose-client arm are not broken today.

7. **Reproduced the actual RED and GREEN states of the cited assertion myself, without
   `make`/`pytest`.** Replayed `test_premium_imports_authoring_not_compose`'s exact logic
   (its own relative-import resolver) against `git show HEAD:src/tour/premium_tour.py`
   (the pre-fix state the developer's `git stash` mutation reproduces): imports exactly
   the 12 names from `.compose`, 0 from `.authoring` — the assertion would fail exactly as
   claimed. Replayed the same logic against the current working-tree `premium_tour.py`:
   imports 0 names from `.compose`, all 12 from `.authoring` — the assertion passes. This
   independently corroborates the mutation-test result without trusting the pasted pytest
   output.

8. **No circular import.** `authoring.py` imports `.artifact`, `.candidate_authoring`,
   `.compose_gate`, `.contract`, `.generation`, `.reflection`, `.validation`, `.verify`.
   `compose_gate.py` imports only `.claim_dedup`, `.contract`, `.validation`, `.verify` —
   no path back to `.authoring` or `.compose`.

9. **Ledger cross-check.** Loaded `state.json` myself: A1's own `test_command` field is
   literally the single node id
   (`test-file FILE="tests/test_tour_authoring_extraction.py::test_premium_imports_authoring_not_compose"`)
   — this is the ledger's own atomic-step design (CLAUDE.md: "one file-scoped change proven
   by exactly ONE executable command"), not the developer cherry-picking a weak gate.
   Independently re-derived the "12/12 matched" claim: every entry in
   `COMPOSE_IMPORTERS_DELETED_BY_A_LATER_STEP` appears in the `files` scope of the step
   the test says deletes it. 0 unbacked.

## A real, independently-confirmed gap — advisory, does not block

`tests/test_tour_authoring_extraction.py` holds 4 tests. The cited gate command runs
exactly 1 (`test_premium_imports_authoring_not_compose`), which only parses
`premium_tour.py`'s import statement — it does not run
`test_authoring_policy_hash_is_byte_identical_after_the_move` or
`test_remaining_compose_importers_are_pinned` (the two tests that formally encode AC-2's
own two clauses), nor `test_authoring_module_exports_the_moved_names` (which would catch
a copy-paste rename that a pure-AST import check cannot). Two of the evidence bundle's own
line items are honestly labeled "manual, NOT a pytest run" — so the bundle does not
overstate what it ran, but the mutation-tested "REAL" QA verdict is scoped to one narrow
assertion (a missed-importer edit on one specific file), not to AC-2 as a whole. I closed
this gap through independent hermetic re-derivation (items 2-6 above) rather than trusting
either side's ad-hoc script, and every one of the three un-run assertions holds on the real
tree. This matches what the two sibling reviews in this folder independently found; I
re-derived it myself with different tooling (my own scanner/hasher, plus the two catches
in my own first-pass bugs noted above) rather than copying their conclusion.

**Recommendation to the serial verifier:** run the whole file, which is a strictly
stronger proof of AC-2 than the single node id:
`make test-file FILE="tests/test_tour_authoring_extraction.py"` (not run by me — shared
7688/7687/Valhalla state, concurrent skeptics).

## Corroborated, non-blocking findings from other angles

- **Pre-existing lint gap, not caused by A1.** `make lint`'s target hardcodes an
  allowlist of `scripts/*.py` files that does not include 3 of the 4 `scripts/` files A1
  edits (`tour_batch_review.py`, `tour_text_candidate.py`, `tour_text_candidate_review.py`
  — only `tour_batch_candidate.py` is covered). I ran `ruff check` directly on all three:
  4 violations (UP035 + RUF022 in `tour_batch_review.py`; I001 + F401 — an actually-unused
  `ADJUDICATION_PROMPT_SHA256` import — in `tour_text_candidate_review.py`). I then ran the
  identical check against `git show HEAD:<path>` for both files: same 4 violations,
  byte-for-byte — pre-existing, not introduced by A1's import-repointing edit. Does not
  falsify the claim; does mean "All checks passed!" is not a statement about 3 of the 7
  `src`/`scripts` files this step touches.
- **`compose.py:689` self-imports `src.tour.compose as _self`** for `compose_client_for`'s
  monkeypatch resolution. I checked whether this is load-bearing for
  `test_remaining_compose_importers_are_pinned` passing (it is not currently — `compose.py`
  is independently pinned because `src/api/dependencies.py` and `src/api/routes/trips.py`
  import it directly today), but flagging: if A2/A3's engine swap removes those two
  direct-import sites as part of "swaps only its engine to the per-stop path," the
  self-import alone would keep `compose.py` in the pinned set — worth a one-line note for
  whoever verifies A2/A3, not an A1 defect.

## Attacks tried that did not break the claim

- Recomputed the policy hash from both trees independently (caught and fixed my own
  extraction bug along the way) — matched the pin exactly on both sides.
- Byte-diffed all 8 non-policy moved definitions — 0 differ.
- Re-ran an independently-written importer scanner — 0 unaccounted, 0 missing.
- Checked every one of the 10 files consuming `.authoring` (not just `premium_tour.py`)
  for a name that doesn't actually exist in `authoring.py` — 0 missing.
- Checked `compose.py` re-exports every name the 8 A8-scheduled test files and the
  conftest money-guard arm still need from it — all present.
- Hunted an import cycle `authoring -> compose_gate -> ... -> compose` — none.
- Replayed the cited test's own logic against both the pre-fix (HEAD) and post-fix
  (working tree) `premium_tour.py` by hand — reproduces RED then GREEN exactly as claimed.
- Checked whether the 4 pre-existing lint errors on unlinted `scripts/` files were
  introduced by A1 — refuted against `git show HEAD:<path>`, identical violations exist
  before A1's edit.
- Checked the ledger's 12/12 deleted-later allowlist against `state.json`'s `files` field
  directly (not the evidence bundle's own claim of having done so) — 0 unbacked.

## Not run myself (propose to the serial verifier)

- `make test-file FILE="tests/test_tour_authoring_extraction.py"` (all 4 tests) — would
  replace my hermetic AST/hash substitutes with the real pytest execution, including the
  one test (`test_authoring_module_exports_the_moved_names`) that requires actually
  importing `src.tour.authoring` through the real Python import machinery rather than
  static analysis.
