# How the two efforts separate — the scoped plan

The judge asked for this instead of a commit. It answers one question: can the
mock-removal work land on its own, and if not, what is the order?

**Answer: no, and it must land SECOND.** This work sits on top of the
one-true-tour-algorithm campaign, structurally and by dependency. There is no
ordering in which it goes first.

## Measured: my edits are interleaved, not adjacent

Per-file diff vs `HEAD` for the 20 paths this work touched:

| file | in HEAD | hunks | +/- | whose |
|---|---|---|---|---|
| `src/tour/authoring.py` | **no** | — | new | campaign's file, I edited it |
| `tests/test_tour_authoring_gates.py` | **no** | — | new | campaign's file, I edited it |
| `src/tour/compose_gate.py` | yes | 4 | +55/**−280** | campaign gutted it; my ~30 lines sit inside |
| `tests/conftest.py` | yes | 4 | +50/**−146** | campaign rewrote it; my ~20 lines sit inside |
| `tests/test_workbench_ui.py` | yes | **13** | +374/−72 | campaign's; my change is a 7-line lint fix |
| `frontend/review.html` | yes | 4 | +26/−12 | **all four hunks are the campaign's** |
| `scripts/tour_build.py` | yes | 6 | +82/−30 | mixed |
| `src/api/routes/audio.py` | yes | 3 | +19/−8 | mostly mine |
| `src/onboard/beat_draft.py` | yes | 2 | +53/−9 | mine |
| `src/api/models/audio.py` | yes | 4 | +4/−4 | mine |
| `src/tour/contract.py` | yes | 1 | +12/0 | mine |
| `src/api/routes/onboard.py` | yes | 1 | +7/0 | mine |
| `Makefile` | yes | 2 | +11/−4 | mine |
| test files (5 others) | yes | 1–2 each | additive | mine |
| 2 new test files | — | — | new | mine |

Note `frontend/review.html`: my only change to it was reverting one line to what
`HEAD` already said, so it contributes **zero** hunks. Every hunk in that file is
the campaign's — including the spend-dialog removal, which is an intentional,
test-enforced ruling but not mine.

## Why the order is forced

Four hard dependencies, all one-directional — mine on theirs:

1. `src/tour/authoring.py` does not exist in `HEAD`. My edit to it cannot be
   committed without committing their new module.
2. My audio work assumes their `src/audio/provider.py` change (deregistering the
   silent WAV, `get_provider()` failing closed). Without it, my model-default
   guard asserts against a registry that still contains `mock`.
3. My `conftest.py` glue seam exists *because of* their
   `src/tour/generation.py:339` real-by-default change. Landed alone it would
   patch a name that still resolves to the mock anyway — a no-op that looks like
   a fix.
4. My compose-gate change lives inside a file they reduced by 280 lines.

Nothing of theirs depends on anything of mine. The graph has one direction.

## The recommendation

**Land the campaign first, then this.** Its own ledger
(`specs/2026-07-29-one-true-tour-algorithm/state.json`) reports 9 of 10 steps
complete with one partial, so it is close. Concretely:

1. Finish the campaign's last step and get its bar green.
2. Commit it. That also clears the one remaining test failure here —
   `test_tour_certification_contract.py::test_reference_manifest_has_replayable_per_document_provenance`
   fails because a manifest pins the sha256 of a spec document that campaign
   edited. Re-stamping the hash alone cannot fix it: the test also compares
   content read from the pinned `source_commit`, so the stamp must name a commit
   that already contains the new bytes. `HEAD` (`c8ec3969`) is itself exactly
   that kind of standalone re-stamp commit. It is their edit-then-restamp loop,
   mid-cycle — not a defect in this work and not fixable from here.
3. Then this work commits cleanly on top, and `make test` is a meaningful gate
   for it rather than a mixed signal.

The alternative — one commit containing both — is defensible only if the owner
decides the campaign is finished. It cannot be decided from inside this work: it
needs a judgement about that campaign's remaining step, which nothing here has
reviewed.

## What is NOT a viable option

`git add -p` surgery to carve out "just the mock files". Ruled out on measurement,
not preference: `src/tour/authoring.py` is theirs and new, so no path-based subset
exists; and in `compose_gate.py`, `conftest.py`, `tour_build.py` and
`test_workbench_ui.py` the two efforts' hunks are interleaved in the same files.
A partial stage would also strand the campaign's changes in the working tree for
the next session to commit blind — including the workbench spend-dialog removal,
which deserves to be seen by whoever commits it.
