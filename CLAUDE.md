# Ondoway — GPS-triggered audio tour platform

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
`guard-log.txt` is NOT a clean record. Destructive-command safety now rests
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
quality never means slow. Entry point: `/team <task>` (`.claude/commands/team.md`).
No one blesses their own work.

Roles (each = a real agent or mechanism):
- **Product Owner** (`.claude/agents/product-owner.md`) — request → smallest
  slice + TESTABLE acceptance criteria. Front gate for Tier 2+.
- **Planner** — the built-in `Plan` agent, or a parallel judge-panel of N
  approaches scored + synthesized from the winner.
- **Developer** — general-purpose agent, ONE per file (parallel builders never
  collide; `isolation:'worktree'` only if they'd otherwise conflict).
- **QA** (`.claude/agents/qa.md`) — the undo-test (mutation: revert the fix →
  the test must go RED) + `make lint`/`make test` + golden/tour-grade + real
  workbench/emulator screenshots. Never accepts a green claim on faith.
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
- Never use `--ignore` or `-k "not ..."` to exclude tests
- A test that hasn't been run is not a test — always execute after writing
- Step 0 baseline must be green before starting work

### Zero Lint Errors

`make lint` must produce ZERO errors before ANY commit, agent spawn, or declaration of done. "Pre-existing" is not an exemption. The lint-enforcer hook mechanically blocks operations when lint is dirty. Never pipe `make lint` through `tail` or `head`.

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
make test          # THE bar — test-local + flutter-test (Aura is never wiped)
make test-unit     # Python unit only (for quick iteration, NOT the bar)
make test-local    # Python against local Docker Neo4j (port 7688)
make test-cloud    # Read-only connectivity smoke against Aura (no writes)
make flutter-test  # Flutter (headless Chrome, foreground only)
make flutter-ios   # Launch on iOS simulator
make db-test-up    # Start test Neo4j (port 7688)
make db-up         # Start dev Neo4j (port 7687)
make db-workbench-up  # Start workbench Neo4j (port 7689 — test-workbench/api-test only)
make test-workbench   # Playwright workbench suite (dedicated 7689; NOT in the bar)
```

**Port mapping:** Test Neo4j = 7688, Dev Neo4j = 7687, Workbench Neo4j = 7689. 7688 + 7687 must be running for the full suite; 7689 only for `make test-workbench` / `make api-test` (its target starts it automatically).

**Isolation invariant (2026-07-02):** the workbench Playwright suite runs ONLY against the dedicated 7689 instance and pre-wipes it each run. It must never point at 7688: the pytest suite full-wipes 7688 per-module, so any suite asserting exact DB state there is broken by residue or by a concurrent `make test`. Concurrent `make test-workbench` runs are unsupported (:8001 must be free; the suite fails fast).

**Common issue:** Tests skip unexpectedly → stale `__pycache__` caches a False result for `_neo4j_available()`. Fix: `make test-local` (clears cache automatically) or manually `find tests src -name __pycache__ -exec rm -rf {} +`.

## Config Layering

Precedence: shell environment → process environment → `load_dotenv()` → defaults.

Shell env vars override `.env` file values. Changing `.env.test` alone does not help if the shell already has a stale export. `pytest.mark.skipif` conditions are cached in `.pyc` files — changing .env.test does NOT re-evaluate them without clearing `__pycache__`.

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
- **Ignored:** B008 (FastAPI `Depends()`), E402 (conftest env loading), E741 (`l` for Lens in Cypher).

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

## Pre-commit Checklist

- [ ] `make test` passes (Python local + Flutter); `make test-cloud` is a separate read-only Aura smoke
- [ ] Read the diff (`git diff --staged`) — every change is intentional
- [ ] No hardcoded colors (use `Theme.of(context).colorScheme.*`)
- [ ] No fabricated values — every field name, ID, and property comes from a verified source
