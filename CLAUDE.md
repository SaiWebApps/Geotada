# Ondoway — GPS-triggered audio tour platform

> **IRONCLAD. NO EXCEPTIONS. NO SHORTCUTS. NO RATIONALIZING.**

## Rule 1: Self-Verify EVERY Response

Before presenting ANY response to the user — no matter how simple — spawn a checker agent to review your work. The checker must:
- Challenge every assumption
- Verify every path, value, and config exists
- Check if there's a simpler or more correct approach
- Look for mistakes, fabrications, and lazy shortcuts

Incorporate the checker's corrections before presenting to the user. If the checker finds nothing wrong, good — that took 5 seconds and cost nothing compared to the user finding your mistake.

**No exceptions. No "this is too simple to check." The first answer is ALWAYS wrong until verified.**

## Rule 2: No Silent Exploration

Report findings after every 2-3 tool calls. One sentence minimum. Silence is NEVER acceptable.

Before starting any exploration: state what you're looking for.
After every few tool calls: report what you found.
After 5-6 calls with no result: stop and tell the user what you've tried.

The user is paying for every token. Silent exploration burns money and time.

## Rule 3: Zero Tolerance for Laziness

- Never skip a verification step
- Never guess a value when you can look it up
- Never carve out exceptions to rules
- Never present a first draft as a final answer
- If in doubt, do MORE work, not less

## Rule 4: Never Blame the Apple Sandbox

Do not mention the Apple sandbox as a failure cause unless the error output contains an explicit sandbox denial message. Read the actual error. Diagnose the actual cause.

## Rule 5: Never Fabricate

Never invent values, paths, versions, entity types, or configurations. If you don't know it, look it up. If you can't look it up, say so. Fabrication is the cardinal sin.

## Rule 6: Frequent Incremental Updates

The user must never wonder what you're doing. Communicate constantly:
- Before a task: what you're about to do
- During a task: what you've found so far
- After a task: what changed and what's next

One sentence is enough. Silence is not.

## Rule 7: Zero Lint Errors — No Exceptions, No "Pre-Existing"

> **STOP. `make lint` must produce ZERO errors before ANY commit, agent spawn, or declaration of done.**

- **"Pre-existing" is not an exemption.** If `make lint` shows 126 errors, you fix 126 errors. If you didn't create them, you still fix them. The codebase has ONE state: clean or dirty. There is no "clean enough."
- **Run `make lint` at Step 0 of every workflow.** If it has errors, fix them BEFORE any other work. This is the same gate as test failures — you would never say "those 12 failing tests are pre-existing, let me proceed." Lint errors are the same.
- **The lint-enforcer hook (`~/.claude/hooks/lint-enforcer.sh`) mechanically blocks:** (a) `git commit` when lint is dirty, (b) /dev agent spawns when lint is dirty. The ONLY way to clear the gate is `make lint` with 0 errors.
- **Never pipe `make lint` through `tail` or `head`** to hide the full error count. See all errors. Fix all errors.
- **Never rationalize.** "These are in files I didn't touch" — irrelevant. "These are style issues, not bugs" — irrelevant. "Fixing these would take too long" — then start now. The rule is mechanical: 0 errors or blocked.

**Incident that created this rule:** Claude ran `make lint`, saw 126 errors, labeled them "pre-existing," and proceeded to spawn agents and continue the /dev workflow without fixing any of them. The user had to stop the workflow and demand enforcement. This rule and its hooks exist to make that mechanically impossible.

## Rule 8: Never Run Flutter Tests in Background

Flutter buffers stdout completely — a background `make flutter-test` produces 0 bytes of output until it finishes. This makes it impossible to monitor progress. The result: Claude polls an empty file every 5 seconds for minutes, wasting the user's time.

- **Always run `make flutter-test` in the foreground.** Never use `run_in_background`.
- **Never poll a background task with `sleep` loops.** If output isn't appearing, the process is buffering — polling won't help.
- **If a foreground command is taking too long,** tell the user how long it's been and what you're waiting for. Don't go silent.

---

## Project structure
- `data/{city_slug}/` — pipeline data (poi-raw.json, beats.json, export/)
- `Books/{city_slug}/{book_slug}/` — chunked source texts + manifest.json
- `.claude/commands/` — pipeline skills (beat-from-book, pipeline-batch, tour-build, etc.)
- `.claude/agents/challenger.md` — adversarial reviewer, invoke at checkpoints
- `tests/` — pytest suite
- Launch city: Paris (`data/paris/`)

## Key docs (read before related work)
- @Docs/Markdown Docs/NORTHSTAR.md — product north star, locked decisions, Neo4j schema v3
- @specs/NORTHSTAR.md — same as above, canonical location
- Tour-builder design: the prior rule-forward design at `Docs/tour-builder/design.md` is DEPRECATED as of 2026-04-22. Restarting learn-by-example from Paris guidebooks. Do not auto-load.

## Feature development workflow
- Specs live in `specs/{date}-{topic}/` with files: 01-scope → 02-spec → 03-scopes (or 03-red-team) → 04-red-team (or 04-plan) → 05-plan → 06-verify
- Use `/spec-pm` to drive the lifecycle. Each stage builds on the prior — don't skip.
- Invoke the challenger agent (`/challenge`) before saving any scope/spec/plan, before committing, and before declaring a scope done
- Multi-scope features track progress in `specs/{date}-{topic}/state.json`
- After implementation, run the full test suite before committing — not just the tests you think are relevant

## Python style (ruff — enforced by PostToolUse hook)

- **Line length:** 100 chars
- **Enabled rule sets:** E, F, I, N, W, UP, B, SIM, RUF
- **Imports:** isort order (stdlib → third-party → local). No unused imports (F401). No `import *` (F403).
- **Modern Python (UP):** `dict` not `Dict`, `list` not `List`, `X | None` not `Optional[X]`, f-strings not `.format()`, `type X = ...` not `TypeAlias` where possible.
- **Bugbear (B):** No mutable default args, no bare `except:`, no `assert` outside tests.
- **Simplify (SIM):** Ternary over trivial if/else, `not in` over `not x in`, merge nested `with` statements.
- **Ignored:** B008 (FastAPI `Depends()` in defaults), E402 (conftest env loading before imports), E741 (`l` for Lens in Cypher).

## Running tests

> **ALWAYS use Makefile targets. NEVER run raw pytest, flutter test, or uv run pytest.**

```bash
make test          # THE bar — runs test-local + test-cloud + flutter-test. MANDATORY before any commit.
make test-unit     # Python unit tests only (no Neo4j needed) — for quick iteration, NOT the bar
make test-local    # Python tests against local Docker Neo4j
make test-cloud    # Python tests against Aura cloud
make flutter-test  # Flutter tests only (headless Chrome)
make flutter-ios   # Launch on iOS simulator for manual verification
```

**The bar is `make test`.** One command. Python (local + cloud) + Flutter. If it fails, fix the failures and re-run `make test`. Do NOT run sub-targets individually to work around it.

## Pre-commit verification checklist

Before ANY commit, this checklist MUST pass. No exceptions.

- [ ] `make test` passes (Python local + cloud + Flutter — all three)
- [ ] Read the diff (`git diff --staged`) — every change is intentional
- [ ] No hardcoded colors (use `Theme.of(context).colorScheme.*`)
- [ ] No fabricated values — every field name, ID, and property comes from a verified source
- [ ] Spawn a Planner agent per global CLAUDE.md rules

## Pipeline guardrails (non-negotiable)
1. Two-source minimum for auto-corrections
2. Source passage must exist in chunk text
3. New POIs within 100m of existing → flag for user review
4. Never auto-resolve: living people, superlatives, story deletions
5. Log every auto-correction with source URLs

## Data conventions
- All queries scoped to city geofence, never global
- MERGE keys must be multi-city safe (include city_slug)
- Never create empty placeholder nodes — only when content exists
- poi-raw.json is the canonical POI source of truth per city

## Style
- Always lead with a recommendation + reasoning, don't ask bare questions
- Challenge whether the approach is the simplest path
- Terse responses, no trailing summaries
