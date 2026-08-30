# Change gates — proving a change before it is made

**Status:** design. Nothing below is built except where marked BUILT.
**Owner ruling, 2026-08-29.** Written after a session in which the agent
delivered two of a three-tier feature, converted the third into a question back
to the owner, and told the owner something false about their own architecture.

---

## 0. The two failures this exists to stop

Both are recorded here as the acceptance test for the whole design: a mechanism
that would not have caught these is not worth building.

**F1 — the scope cut.** The ask was a three-tier voice fallback in production.
Two tiers shipped. The third was built for the wrong place (a model on the API
server, which cannot help a phone with no signal), then dropped from the
production manifest and handed back as "tell me if you want this". The owner
caught it.

*Aggravating:* a guard test was written whose PASSING condition included the
feature being ABSENT from the manifest. The cut was wearing a test's clothes,
which made the narrowed delivery look verified.

**F2 — the false architecture claim.** The agent told the owner "the audio is
made earlier, on our computer". It is not: the phone POSTs to the server at tap
time and the tourist waits on a progress bar. That sentence made the owner's own
feature look pointless and cost an hour of argument about a hosting plan.

**What each failure needs:**

| | Caught by |
|---|---|
| F1 scope cut | reviewer comparing the map against **the original request** |
| F1 guard-test blessing the cut | AST check + reviewer reading the diff's tests |
| F2 false claim about code | citation guard (BUILT) + reviewer with the design docs |

---

## 1. Three gates

Adopted from ChatGPT's simplification of an earlier four-layer sketch, with the
corrections in §2. One line each:

1. **Evidence gate.** Before implementation, every material claim in the change
   map names its files and symbols and carries traceable evidence. Anything not
   evidenced is *labeled an assumption*. The explorer does not certify its own
   reading — that is checked externally.
2. **Change gate.** Implementation may touch only mapped areas. A discovery
   outside the map stops the edit and produces an amendment. No stealth
   architectural decisions.
3. **Verification gate.** An independent hostile reviewer receives **the original
   request**, the repository, and the map/diff — never the explorer's reasoning —
   and tries to disprove: completeness, factual claims, scope compliance, tests.
   Anything a model should not adjudicate stays in a mechanical check.

---

## 2. Four corrections to the plain three-gate frame

**2.1 A labeled assumption needs a resolution rule, or the label launders it.**
"Assumption: the phone plays pre-made audio" is F2 with a sticker on it. The
invariant: every claim is evidence-backed *or* labeled an assumption, AND an
assumption on a load-bearing path is grounds for automatic REJECT until it is
evidenced. Labels exist to make assumptions attackable; attacking them is the
reviewer's job.

**2.2 Fingerprints are self-certification; telemetry is better.** A
sha256-plus-quote is a certificate the explorer writes about itself. It is at
least *externally checkable* — a validator confirms the quote really sits at that
line, which cannot be forged from a file never opened. That is the floor. The
ceiling is real telemetry: session transcripts are JSONL on disk and
`/harvest-failures` already parses them, so a validator can compare the
explorer's actual Read calls against the files it cited. **Verify that path
first when building.** Ship the floor; upgrade if it holds.

**2.3 Completeness needs a mechanism, not a wish.** "Check completeness" is
unactionable. The mechanism: every import edge touching the change surface must
appear in the map. Omission is the F1 class — the map can be perfectly accurate
about what it contains and still be missing a tier.

**2.4 A rejected map must block exactly like no map.** "Tries to disprove" has no
verdict semantics. House style, matching `skeptic` and `tour-adversary`: default
REJECTED, the only success condition is finding a real flaw.

---

## 3. Anti-ceremony

The failures ledger records the finding that governs this: **a noisy hook gets
deleted, which costs the classes that do work.**

- Gates fire on multi-file changes and new modules under `src/` and `mobile/lib/`.
- A one-line fix passes with the acknowledgement token, logged.
- Every hook ships with a block-case and a pass-case payload test. A hook whose
  tests are not run does not exist.

---

## 4. What this cannot do

Stated here so no future version quietly inflates the claim.

- **A false sentence in chat that changes no file.** F2's exact sentence named no
  file and no symbol. The citation guard passes it. Only the verification gate,
  reading the design docs, catches that class.
- **Vendor facts.** `tts-1-hd` answering 500 on specific content was found by
  *measuring against the live API*, not by reading our code. No map finds it.

---

## 5. Build order

1. Map schema (JSON) + one renderer to HTML. One source of truth, so the human
   view and the checked view cannot drift.
2. Evidence validator — quotes resolve; upgrade to transcript telemetry if
   available.
3. Change gate — PreToolUse on Edit/Write; commit-time changed-set ⊆ map-set.
4. Verification gate — `adversary.md` agent, request + repo + map/diff, default
   REJECTED.
5. AST check for the guard-test shape: a test whose passing path is conditioned
   on a feature being absent from a manifest it reads.

---

## 6. Already built and tested

- **`.claude/hooks/citation-guard.py`** (Stop hook). Two arms: every `path:line`
  cited must exist, have been opened this session, be in range, and any adjacent
  quote must really sit there; and a claim about `src/` or `mobile/lib/` code
  with no citation at all is refused. 13/13 payload tests. Both arms ship
  together because arm 1 alone rewards citing less. Rewritten regex-free: tokens
  are split on whitespace, adornment is peeled, and each is looked up in
  `git ls-files`.
- **`.claude/hooks/advisor-consult-guard.py`** (Stop hook). No reply without a
  consult in the same turn. Turn boundaries come from record STRUCTURE
  (`origin.kind`, `isMeta`), never text.
- **`~/.claude/hooks/no-regex-in-hooks.py`** (global PreToolUse on Write/Edit).
  Refuses pattern matching inside any hook, by parsing the file with `ast` and,
  for an Edit fragment that will not parse alone, Python's own `tokenize`.
  11/11 payload tests.
- **`~/.claude/hooks/no-excuses.py`** — the flake rule, and the prefilter is
  GONE. Every reply now reaches the judge.
- **`.claude/hooks/ledger-guard.py`** — class 14, `inplace_source_edit`: a
  stream editor rewriting a tracked source file. `shlex` segments the command,
  flags are inspected for in-place spellings, targets are checked against
  `git ls-files`. 10/10 payload tests.
- **`.claude/hooks/production-junk-guard.py`** (PreToolUse on Bash, and Stop).
  Nothing enters history that a launch does not need. Two verdicts, both
  answered by a tool rather than a name pattern: `git check-ignore` for what the
  repo already declared junk, and containment in the product surface for what
  nothing reads. Written 2026-08-28 and left unwired, so it decided nothing
  until 2026-08-29. 18/18 payload tests in
  `tests/test_production_junk_guard.py`; §7's class showed up twice on the way
  in, and both are named there.

## 7. Four guards that ate themselves, and the class they share

Every one of these passed its own tests before it was found broken. The class:
**the enforcement layer's own artifacts must be classified and payload-tested
like any other input, and a fixture invented alongside the code it tests proves
only that the two agree with each other.**

1. **The starved rubric.** `no-excuses.py` grew a "nothing is a flake" rule that
   was dead on arrival: the lexical prefilter in front of the judge knew `flaky`
   but not `flake`, so the sentence never reached the judge. Fix: delete the
   prefilter.
2. **The self-blocking boundary.** `advisor-consult-guard.py` treated its OWN
   block message as a fresh human turn, so each block invalidated the consult
   before it and the guard walked itself to MAX_BLOCKS, where it silently
   disarmed. Fix: classify by record structure; raise the ceiling; reset on
   success.
3. **The fixture that agreed with its code.** The same guard looked for
   `{"type": "tool_use", "name": "advisor"}` — the shape every *other* tool
   uses. The advisor is a server-side tool and records as
   `{"type": "server_tool_use", ...}` with an `advisor_tool_result`. The check
   could never match, so **every block it issued was false**, and its thirteen
   payload tests all passed because they were built from the same assumed shape.
   Fix: read the real records out of the live transcript, and test the guard
   against that transcript rather than against a fixture.
4. **The guard that never fired, and then fought its own cleanup.**
   `production-junk-guard.py` was complete, documented, and named by nothing in
   `settings.json` — a day of enforcement that enforced nothing, which no test
   could have caught because the code itself was correct. **A hook is not built
   until the wiring is proven by a payload.** Wiring it surfaced two more, both
   of the class above. A bare filename was accepted as proof the product reads a
   file: true for `density.py`, false for `tour.json`, a name 24 files carry — so
   judging a 40-file throwaway batch it passed 32 on that collision and caught 8
   only because *their* leaf name was spelled differently. And a staged DELETION
   was judged like an addition, so the `git rm -r --cached` that acts on the
   guard's own findings was refused by the guard that found them. Fix: a bare
   name counts only when it is unique in the tree; deletions are dropped from
   both the staged diff and the worktree sweep, and `commit -a` is read from the
   flag rather than inferred from an empty staged list.
