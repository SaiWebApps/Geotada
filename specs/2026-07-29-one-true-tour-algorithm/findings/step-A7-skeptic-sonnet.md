# Skeptic panel — step A7 (compose scoreboard deletion) — FIX CORRECTNESS angle

Verified against working tree at HEAD `c8ec39690030901660c843d46910bedb40e84c13`
(staged A6/A7-in-progress changes on top, `git status` confirmed clean-otherwise).

## Verdict: CONFIRMED (advisory-only findings, none block)

## What I re-derived myself (read-only)

1. `make lint` — ran it myself: exit 0, "All checks passed!" (matches claim).
2. Confirmed the RED-mutation is genuine, not fabricated: `git show
   HEAD:src/tour/compose_metrics.py` succeeds (file exists at HEAD c8ec3969,
   i.e. the deletion is currently only staged/uncommitted), so `git checkout
   HEAD -- <5 files>` in the claim's mutation step really does restore the
   files and really would flip the test RED.
3. The exact assertion strings quoted in the evidence
   (`f"{on_disk} still exist on disk; A7 must delete them."`) match the
   literal test source at `tests/test_tour_one_engine.py` verbatim — not a
   paraphrase, not fabricated.
4. Repo-wide grep for `compose_metrics`, `compose_snapshot`,
   `report-tour-issue` across `.py/.sh/.yml/.yaml/.json/.toml/.cfg/.ini` and
   the Makefile: zero live importers/references remain outside the deleted
   files themselves and historical `specs/*/state.json` planning records.
   No dynamic (`importlib`) or non-Python (Makefile target, shell) reference
   exists that the test's AST-only import scan (which cannot see dynamic
   imports) would miss.
5. `craft_score`'s only surviving caller is `src/tour/compose.py:84`
   (`from .narration_quality import craft_score`) — confirmed by grep. The
   updated `narration_quality.py` docstring's claim ("craft_score's ONLY
   surviving caller as of A6... the author.py:416 comparative gate ... was
   deleted at A6") is accurate: `src/tour/author.py` is confirmed absent
   (`git status --short` shows `D  src/tour/author.py`, staged from A6).
6. `compose_gate.py` (home of `_bad_stops`, the thing D6 says A7 must
   precede) has zero references to `compose_metrics` — the D6 ordering
   constraint is not masking a real import coupling; deleting
   `compose_metrics.py` at A7 cannot break `compose_gate.py`.
7. Cross-checked the AC-2 amendment allowlist
   (`tests/test_tour_authoring_extraction.py:87-100`,
   `COMPOSE_IMPORTERS_DELETED_BY_A_LATER_STEP`) against A7's actual scope:
   `tools/compose_snapshot.py` and `tests/test_compose_quality_eval.py` are
   both mapped to `"A7"`, consistent with `run-context.md`'s AC-2 text and
   with what the diff actually deletes. `tests/test_compose_metrics.py` is
   correctly absent from that allowlist because it imports
   `compose_metrics` directly, not `compose.py` — it isn't a
   "compose.py importer deferred to a later step," it's just deleted
   alongside its subject at A7.

## Does the red-first test encode the original failure mode, or a strawman?

Not a strawman. `test_compose_scoreboard_is_gone` does two real things, not
one: (a) file-existence + git-index-membership for the 5 named paths (catches
a plain `rm` that forgot `git rm`, or a revert), and (b) a real AST parse of
every `.py` file under `src/, scripts/, tests/, tools/` to catch any
surviving `ImportFrom`/`Import` of `src.tour.compose_metrics` or
`tools.compose_snapshot` — this is the actual failure mode D6 is guarding
against ("BEFORE compose_gate's `_bad_stops` dies," i.e. don't delete a
module something else still imports). It is not lexical/string matching
(the codebase's "no regex/lexical shortcuts" rule), and I independently
confirmed via grep that the offender set it computes is currently empty.

## Would a plausible neighbouring input still break it?

Tried and failed to find one:
- A file deleted from disk but not `git rm`'d (still tracked) — caught by
  the `still_tracked` check.
- A surviving Python-level import of the deleted modules anywhere in the
  scanned roots — caught by the AST scan; repo-wide grep confirms zero
  candidates today (so the check is not vacuously passing on an empty
  possibility space, there genuinely are none to catch, but the mechanism
  is real).
- A non-Python reference (Makefile, shell, config) to the deleted paths —
  outside what the AST scan covers, but I grepped for it separately and
  found none; not a gap in the test, just a gap the test doesn't claim to
  cover, and nothing exploits it today.
- A dynamic/`importlib` import of the deleted modules — none exist in the
  repo today (verified by grep), so the AST-scan blind spot is currently
  unexploited, but this IS a real (if currently inert) limitation: the test
  provably cannot catch a future `importlib.import_module("src.tour.compose_metrics")`.
  This is a generic limitation of every AST-based "importer" check in this
  ledger (A1's and A6's tests share it, per those steps' own proofs, which
  explicitly flagged it as advisory), not something specific to A7 or newly
  introduced — advisory, not a new hole this step opens.

## Things I did NOT independently verify (propose-only, shared-state)

- `make test-file FILE="tests/test_tour_one_engine.py::test_compose_scoreboard_is_gone"`
  itself was not re-executed by me (concurrent-session constraint). I did
  not fabricate a pass/fail; instead I re-derived correctness structurally
  from the test source + repo grep, which is enough to rule on fix
  correctness without running it, but the actual green/red bit should still
  be confirmed once by the serial verifier.
- The mutation re-run (`git checkout HEAD -- <5 files>` then
  `make test-file ...`) — not re-executed by me for the same reason; the
  evidence's quoted assertion text is byte-identical to the real source, so
  it is very unlikely to be fabricated, but I did not watch it run.

## One pre-existing repo hygiene note (not an A7 defect)

`.claude/worktrees/ecstatic-hawking-d4f171` is a stray linked worktree
(detached HEAD at `b542af0b`, an older commit) that still has copies of
`tools/compose_snapshot.py`, `.claude/commands/report-tour-issue.md`, and
this ledger's `state.json`/`run-context.md`. It does not affect A7's test
(`SCANNED_ROOTS = ("src", "scripts", "tests", "tools")` is resolved relative
to `REPO_ROOT` in the primary worktree only, and `git ls-files` in the
primary worktree does not see it), so it is not a correctness bug in this
step. Flagging per this repo's own "clean up after yourself" rule — it
predates this session and isn't A7's mess to inherit silently.
