# Ondoway — GPS-triggered audio tour platform

> **Scope:** This filename is retained for compatibility, but this document applies to
> every coding agent, model, subagent, reviewer, and orchestrator—not only Claude.
> `AGENTS.md` supplies the vendor-neutral entry point and the highest-priority Tour
> Finish Doctrine. For tour-quality work, agents must read and obey both files.

## Judge Protocol (mandatory — installed 2026-07-02)

Claude has repeatedly rushed ahead and caused expensive damage: killed the
live Valhalla container via an unexamined worktree compose invocation, OOMed
dockerd by adding an uncapped third database, pruned a sibling session's live
worktree, and claimed fixes without functional proof. The user does not
extend trust; it is re-earned per checkpoint. Two mechanisms enforce this:

**No mechanical command guard exists — do not assume one.** A regex
PreToolUse hook (`guard.sh`, with a `guard-log.txt` audit trail, both under
`.claude/hooks/`) once claimed to block high-consequence commands
(container/volume/worktree/branch destruction, force-push, hard reset,
`rm -rf`, DB wipes) until re-run with an inline `: JUSTIFY: …;` prefix. It
was REMOVED in 643d0d9 as measured-ineffective: 0/70 genuinely destructive
commands blocked, 16/20 harmless ones blocked. Nothing replaced it. No
destructive command is intercepted, and no audit log is written — an absent
`guard-log.txt` is NOT a clean record. (`.claude/hooks/team-gate.sh` is NOT a
command guard: it only checks that a `/team` ledger is human-approved before an
agent spawn, and it fails open. It intercepts no Bash command whatsoever.) Destructive-command safety now rests
entirely on mechanism 1 below, which is therefore load-bearing: the judge
consult before a state-changing action is the ONLY thing standing between a
bad command and a live resource. Skipping it has no backstop.

1. **The judge agent** (`.claude/agents/judge.md`, runs on opus) MUST be
   consulted before: any state-changing infra action, every commit, every
   "fixed/done" claim to the user, and every phase transition. It rules
   PROCEED / PROVE-FIRST / STOP. Paste its ruling into the conversation.
2. **Skeptic panels** (`.claude/agents/skeptic.md`) — for milestone claims,
   spawn 2-4 hostile skeptics (different models via the Agent tool's model
   parameter) whose only success condition is refuting the claim. A claim is
   "proven" only after an adversarial panel failed to break it.

**Visibility contract:** never operate silently for long stretches. Post a
one-line user-visible status at least every 2-3 tool calls (existing rule)
AND a substantive checkpoint (what was proven, what is next, current risk)
at every phase transition. Any user-facing behavior claim ("the workbench
now does X") requires functional proof the user can SEE: an automated
real-browser run with screenshots, or a live reproduction transcript —
code reading and unit tests alone are not sufficient.

**Automated review before human review:** anything queued for human sign-off
(data corrections, tier changes, spec decisions) first passes an automated
review suite — independent researcher + hostile judge per item — so the
human reviews verdicts with evidence, never raw candidates.

### Agentic Team & Rigor Tiers (the full separation-of-duties team)

The Judge Protocol above is the BACK half (QA/Skeptic/Judge — stops us shipping
a broken thing). The full team adds a FRONT half (Product Owner/Planner — stops
us confidently building the WRONG thing) and sizes rigor to the change so
quality never means slow. No one blesses their own work.

**`/team <task>` is the ONLY command the user types.** The approval gate is a
turn boundary in chat, not a second command:

1. **`/team <task>`** (`.claude/commands/team.md`) — Product Owner + Planner
   produce an atomic step ledger at `specs/{date}-{slug}/state.json` (contract:
   `specs/_templates/team-state.schema.json`) with `approved_by_human: false`,
   present the plan + cost estimate, and **end the turn**. ~3 agents, no code.
2. **The human says "go" in chat** (or asks for changes — amend and re-present).
3. **The same session** transcribes that approval into the ledger and invokes
   `.claude/team-engine.js` via the Workflow tool. Per step: Build → $0
   Gate (undo-test) → tier-sized skeptic panel → Judge → persist. It **refuses
   to fan out** while `approved_by_human` is not true, and it never commits.

The engine registers as `team-engine-internal`. **Never tell the user to invoke
it**, and never ask them to hand-edit `state.json` — direct invocation exists
only for resuming a partially-run ledger (`retryBlocked: true`). A Workflow
script cannot pause mid-run for input; that constrains the *script*, not the
user-facing command surface — the main agent is what waits.

Rules the back half enforces in JS rather than prose, because prose caps were
tried and died (`/dev`'s loop counters call a `dev-state.sh` hook that does not
exist):

- **Atomic step** = one file-scoped change proven by exactly ONE executable
  command that goes RED before and GREEN after. `make test-file
  FILE="tests/test_x.py::TestY::test_z"` — a pytest **node id**, never `-k`
  (`Makefile:139-149` has no `$(PYTEST_ARGS)` passthrough, so make eats `-k` as
  `--keep-going` and the selector becomes a make goal).
- **The cost ladder.** Per step: derived lint + the step's own node-id test +
  the mutation test (seconds, no provider spend). Per phase: `_test-python`,
  `flutter-test`, `test-workbench`, `_test-golden` — **serial**, they share the
  7688 DB, dev data and Valhalla. Run close: `make audit` **exactly once** (that
  is the only paid command; `test-live` sets `ONDOWAY_ENABLE_PAID_LLM_CALLS=1`).
  Never run the paid bar inside a loop.
- **"$0" means zero provider spend, NOT read-only.** `make test-file` pulls in
  `_ensure-test-db`/`_ensure-dev-data`/`valhalla-up` (`Makefile:144-146`), so
  even the cheapest rung starts the shared Neo4j containers, **writes to the
  shared 7687 dev graph**, and `docker compose up`s Valhalla. The engine
  therefore assumes exclusive use of the local containers — never run it
  alongside `make test` or a sibling session's suite.
- Skeptics run in parallel, so they may only execute `make lint` and
  `make flutter-analyze` themselves; any container-touching reproduction is
  *proposed* and re-run once by a single serial verifier. Otherwise two panel
  members racing on 7688 or :8001 manufacture phantom blockers from a collision
  the design caused.
- **An objection blocks only with a verified reproduction** it actually ran, on
  an allowlisted cheap target. No repro → advisory, logged, no rework cycle.
  This is what stops the skeptic panel spinning forever.
- Hard caps: per-step `maxAttempts` (default 2), a FAKE mutation is terminal,
  empty diffs short-circuit, ping-pong detection, one phase-repair per run, an
  infra circuit breaker, and a weighted agent budget printed **before** any
  fan-out (`estimateOnly: true` prints it and spawns nothing).
- `.claude/hooks/team-gate.sh` (PreToolUse/Agent) is a *second* gate, and it
  covers **main-agent spawns only**. Measured 2026-07-25 both ways: it DOES
  refuse a real main-agent Agent call naming an unapproved ledger, and it does
  NOT fire for agents spawned inside the Workflow runtime. It is deliberately narrow
  (it fires only when a prompt names a `specs/` dir whose `state.json` says
  `approved_by_human: false`) and fails open, because the removed `guard.sh`
  proved a broad hook blocks harmless work. The load-bearing check is
  the engine's own preflight.

For open-ended "find + fix whatever's wrong" use `Skill(proactive-audit)`
instead — `/team` needs a defined change.

Roles (each = a real agent or mechanism):
- **Product Owner** (`.claude/agents/product-owner.md`) — request → smallest
  slice + TESTABLE acceptance criteria. Front gate for Tier 2+.
- **Planner** — the built-in `Plan` agent, or a parallel judge-panel of N
  approaches scored + synthesized from the winner.
- **Developer** — general-purpose agent, ONE per file (parallel builders never
  collide; `isolation:'worktree'` only if they'd otherwise conflict).
- **QA** (`.claude/agents/qa.md`) — the undo-test (mutation: revert the fix →
  the test must go RED) + `make lint`/`make test` + real workbench/emulator
  screenshots. Never accepts a green claim on faith.
- **Skeptics** (`.claude/agents/skeptic.md`) — 2-4 hostile reviewers on
  DIFFERENT models; kill a finding if a majority refute.
- **Judge** (`.claude/agents/judge.md`) — PROCEED / PROVE-FIRST / STOP before
  every commit / "done" / infra action.
- **Acceptance/User** (`.claude/agents/acceptance.md`) — build the real tour /
  open the real screen; is it actually GOOD for the tourist/editor, not just
  correct?
- **Manager** — the orchestrator (a Workflow script and/or the human gate);
  keeps roles in sync, re-delegates on conflict, loops to consensus.

Rigor tiers — run the SMALLEST pipeline that fits; when unsure, go up one:
- **Tier 0** (docs/mechanical): Developer → Gate.
- **Tier 1** (bugfix/small change): +Planner(light) +QA(undo-test) +Judge.
- **Tier 2** (feature / user-facing / tour-engine): +Product Owner +Skeptic
  panel +Acceptance.
- **Tier 3** (milestone / infra / prod / data / deploy): full + real-device or
  -browser proof + human sign-off.

Speed comes from (a) right-sizing the tier and (b) running independent roles in
PARALLEL (fan out builders / skeptic panels / planner options), never serial.
For open-ended "find + fix whatever's wrong", use the proactive-audit loop
(`Skill(proactive-audit)`): it finds → adversarially verifies → fixes with a
test until 2 dry rounds, and hands you the batch to gate + commit (it never
commits itself).

---

## Behavioral Rules

### Diagnosis Before Action

When anything fails:
1. Read the exact error message and stack trace
2. Identify root cause with evidence (not "it might be X")
3. Fix with the minimal change
4. Re-run to verify

Never blame the sandbox, infrastructure, or external systems without explicit evidence in the error output. When a command fails with a connection error: check `docker ps`, check env vars, check the target port. These take seconds and are almost always the actual cause.

### Build System Enforcement

Every command must go through Makefile targets. Never use raw `uv run pytest`, `uv run python`, `flutter test`, or any direct invocation. The Makefile encodes correct env setup, container checks, port selection, and cache clearing.

If no target exists for what you need, add one to the Makefile first.

### Test Discipline

- The bar is `make test` — full suite, 0 failures, 0 skipped
- Never report partial results as success (unit-only is not the bar)
- Skipped tests are failures in disguise — diagnose why they skip
- Never split composite targets to work around failures
- Never use `--ignore` or `-k "not ..."` to omit tests from `make test`.
  Environment-specific shard routing is valid only when `make test` invokes every shard.
- A test that hasn't been run is not a test — always execute after writing
- Step 0 baseline must be green before starting work

### Zero Lint Errors

`make lint` must produce ZERO errors before ANY commit, agent spawn, or declaration of done. "Pre-existing" is not an exemption. Never pipe `make lint` through `tail` or `head`.

**This rule is NOT mechanically enforced — do not assume it is.** A "lint-enforcer hook" was documented here for months and never existed in `.claude/settings.json` or `.claude/hooks/`; the claim was removed 2026-07-25. The only hooks that exist are `render-deploy-watch.sh` (PostToolUse/Bash) and `team-gate.sh` (PreToolUse/Agent), and neither checks lint. Running `make lint` yourself is the whole enforcement.

### No Guessing

- Never offer "try this" fixes without evidence from the codebase
- For iOS/Xcode/simulator errors: read the actual source code and project config immediately
- For email issues: read the raw email source first (Show Original in Gmail)
- For GUI workflows (Apple portal, Xcode, App Store Connect): list ALL prerequisites upfront, caveat what you cannot see, never abandon a correct diagnosis under pushback

### Workaround Spirals

When the same approach fails twice: STOP. The approach is wrong. Diagnose WHY before trying any more variations. Run `<tool> --help` before building workarounds — the tool may already have the flag you need.

### Communication

- Report findings every 2-3 tool calls. One sentence is enough, silence is not.
- When spawning background agents, state expected completion time
- Never chain more than 3 tool calls without a visible update

### Flutter-Specific

- Never run Flutter tests in background (Flutter buffers stdout completely)
- `make flutter-clean` is required after ANY asset change
- `FlutterDeepLinkingEnabled` must remain `false` while using `app_links`
- New `.swift` files must be added to `Runner.xcodeproj/project.pbxproj` (filesystem alone is invisible to the build)

### Worktree Cleanup

After cherry-picking from a worktree: immediately remove the worktree directory, delete the feature branch, and remove orphaned Docker networks/volumes.

---

## Project Structure

- `data/{city_slug}/` — pipeline data (poi-raw.json, beats.json, export/)
- `Books/{city_slug}/{book_slug}/` — chunked source texts + manifest.json
- `.claude/commands/` — pipeline skills (beat-from-book, pipeline-batch, tour-build, etc.)
- `tests/` — pytest suite
- `mobile/` — Flutter iOS app
- Launch city: Paris (`data/paris/`)

## Key Docs

- `specs/NORTHSTAR.md` — product north star, locked decisions, Neo4j schema v3
- Tour-builder design: prior rule-forward design at `Docs/tour-builder/design.md` is DEPRECATED as of 2026-04-22
- `specs/2026-07-19-tour-quality-standard/01-standard.md` — the tour quality standard: the gold-text example, S1-S10/P1-P7 narrative and prose checks, and the mechanical FLOOR/GATE (C1-C12/G1-G8) checks
- `specs/2026-07-16-tour-craft/` — externally-researched good-tour examples (Rick Steves transcripts, VoiceMap, Tilden, NAI) backing the standard above

## Test Infrastructure

```bash
make test                         # THE definitive executor — every shard
make test-file FILE=tests/test_x.py
make test-live                    # Standalone live-provider shard
make test-workbench               # Standalone Playwright shard on 7689
make flutter-test
make flutter-ios
make db-up DB=dev                 # 7687
make db-up DB=test                # 7688
make db-up DB=workbench           # 7689
make db-parity TARGET=cloud       # Read-only Aura parity
```

`make test` runs, in order: local pytest, Flutter, workbench browser, golden tours,
tour grade, tour invariants, live-provider tests, and read-only cloud parity. It
requires the corresponding live credentials and may incur provider cost.

**The `/team` engine's guard is NOT in `make test`** — it is agent tooling, not product,
so it does not live in `tests/` and Node.js is not a `make test` prerequisite. Run it
yourself after touching `.claude/team-engine.js`:

```bash
node .claude/team-engine.test.js
```

It loads the real engine and drives its control flow with stubbed agents across 17
pathological shapes, guarding the termination caps, the paid-bar one-shot, the
`depends_on` live-status resolution, and the pre-fan-out gate ORDER (an estimate must be
answerable on the still-unapproved ledger `/team` prices, while a real run on it is still
refused). Hermetic — no DB, no container, no provider, ~50ms — and it exits nonzero with
a named failing check. The header lists, per guard, the exact mutation that must turn it
red; adding a cap means adding its row.

**You are not the only thing that runs it.** Because it is outside `make test`, the engine
runs it ITSELF: preflight executes it and sets `infra.engine_guard`, and the engine aborts
`engine_guard_red` rather than fan out on caps it cannot prove still hold. The gate is
`!== true`, so an unanswered guard counts as a failed one. That is the last point before
fan-out where a broken cap still costs nothing — and it catches breakage the current
session never saw (a sibling session's edit, a hand edit, a fresh clone). Never edit the
guard to make it pass.

**Port mapping:** Test Neo4j = 7688, Dev Neo4j = 7687, Workbench Neo4j = 7689.
The definitive suite starts each required local service through its shard target.

**Isolation invariant (2026-07-02):** the workbench Playwright suite runs ONLY against the dedicated 7689 instance and pre-wipes it each run. It must never point at 7688: the pytest suite full-wipes 7688 per-module, so any suite asserting exact DB state there is broken by residue or by a concurrent `make test`. Concurrent `make test-workbench` runs are unsupported (:8001 must be free; the suite fails fast).

Skips and credential-based deselections are test failures. The supported test
targets clear stale Python caches before collection.

## Config Layering

Make owns configuration. Never source or copy `.env*` files. Local non-secret
profiles are committed under `config/profiles/`. Targets that need credentials
fetch the complete Render service environment fresh for each process and then
atomically overlay the exact local profile.

The Render API key is stored in macOS Keychain under service
`ondoway-render-api-key`, label `ondoway-dev`. Use `make render-auth-status` to
validate it or `make render-auth-setup` to replace it.

Aura is never passed to pytest and cannot be selected by `db-reset`. Cloud
parity is read-only. A cloud data write requires both `TARGET=cloud` and
`CONFIRM_CLOUD_WRITE=1`.

## Python Dependency Index (regular vs Apple)

The project pins **public PyPI** as the default index in `pyproject.toml` (`[[tool.uv.index]]`), so `uv.lock` is reproducible on any machine — the committed lock must always contain only `files.pythonhosted.org` URLs (never `pypi.apple.com`). The pin overrides any machine-level `~/.config/uv/uv.toml` default.

- **Regular (default, everyone): `make sync`** — installs from public PyPI. This is what non-Apple machines use; zero config. Verified 2026-06-03: public PyPI is reachable on this user's Apple VPN too (no proxy env set), so `make sync` works whether the VPN is on or off.
- **Apple corp: `make sync-apple`** — fallback for a network that blocks public PyPI. It backs up `uv.lock`, re-resolves+installs from `pypi.apple.com` via `UV_DEFAULT_INDEX`, then restores the backed-up (public) `uv.lock` from the working tree — it does NOT use `git checkout`, so it is safe even when the public lock is uncommitted.

**Auto-detect rule (for Claude):** default to `make sync`. Only switch to `make sync-apple` if a `uv` command fails reaching public PyPI **and** `curl -sI --max-time 3 https://pypi.apple.com/simple/` returns a response. (In practice this rarely triggers, since public PyPI reaches fine on the VPN.) Re-locking (`uv lock`, after a dependency change) must be done where public PyPI is reachable so the committed lock stays public.

## Feature Development Workflow

- Specs live in `specs/{date}-{topic}/` with stages: 01-scope → 02-spec → 03-scopes → 04-red-team → 05-plan → 06-verify
- Use `/spec-pm` to drive the lifecycle. Each stage builds on the prior.
- Invoke the challenger agent before saving any scope/spec/plan, before committing, and before declaring done
- Multi-scope features track progress in `specs/{date}-{topic}/state.json`

## Python Style (ruff)

- **Line length:** 100 chars
- **Rule sets:** E, F, I, N, W, UP, B, SIM, RUF
- **Imports:** isort order. No unused (F401). No `import *` (F403).
- **Modern Python (UP):** `dict` not `Dict`, `list` not `List`, `X | None` not `Optional[X]`, f-strings not `.format()`.
- **Bugbear (B):** No mutable default args, no bare `except:`, no `assert` outside tests.
- **Ignored:** B008 (FastAPI `Depends()`), E402 (conftest import ordering), E741 (`l` for Lens in Cypher).

## Deployment

- **Backend:** Render (ondoway-api)
- **FRONTEND_URL** env var must be `https://ondoway.com` — used only in `email.py` to build magic link URLs
- **API_BASE_URL** is separate — compiled into the Flutter IPA via `--dart-define`
- **TLS cert issue pattern:** If Let's Encrypt HTTP-01 challenge fails on Render, check Namecheap for URL Redirect Records that intercept HTTP traffic

## Pipeline Guardrails

1. Two-source minimum for auto-corrections
2. Source passage must exist in chunk text
3. New POIs within 100m of existing → flag for user review
4. Never auto-resolve: living people, superlatives, story deletions
5. Log every auto-correction with source URLs

## Data Conventions

- All queries scoped to city geofence, never global
- MERGE keys must be multi-city safe (include city_slug)
- Never create empty placeholder nodes — only when content exists
- poi-raw.json is the canonical POI source of truth per city

## Clean Up After Yourself (owner ruling, 2026-07-27)

Finishing a piece of work includes deleting its scaffolding. A stale document is worse
than no document — the next session reads it as current and acts on it. A document that
contradicts the shipped code is an active trap, and a dead `specs/` folder also arms
`team-gate.sh` against any agent prompt that names its path.

- Delete scratch output, probe scripts and resolved-output dumps you generated. They are
  yours; do not ask the owner to adjudicate obvious rubbish.
- Before deleting a folder that once held a plan: check what of it actually shipped,
  carry any live un-shipped gap forward in a sentence or two, then delete the folder.
  Do not keep a whole document for two live lines inside it.
- Untracked files are not recoverable from git — judge-consult first and state what is
  being lost. Tracked files are recoverable, so the bar is lower.
- A doc that contradicts the code gets corrected or deleted. Never left.

## Pre-commit Checklist

- [ ] `make test` passes every local, Flutter, browser, tour, live-provider, and cloud shard
- [ ] Read the diff (`git diff --staged`) — every change is intentional
- [ ] No hardcoded colors (use `Theme.of(context).colorScheme.*`)
- [ ] No fabricated values — every field name, ID, and property comes from a verified source
- [ ] No scaffolding left behind — scratch files, superseded specs, stale docs are deleted
