# Ondoway — GPS-triggered audio tour platform

> **IRONCLAD. NO EXCEPTIONS. NO SHORTCUTS. NO RATIONALIZING.**

## Agent Perspectives

This project benefits from all three agent perspectives. Use them:
- `/agent-chat architect` — before designing new features or data model changes
- `/agent-chat reviewer` — before presenting ANY result (mandatory self-verification)
- `/agent-chat implementer` — when setting up builds, running tests, or debugging infra

The reviewer's self-verification checklist (`~/.claude/agents/reviewer.md`) is **mandatory** before presenting results. The Ondoway track record is 100 wrong-approach incidents across 94 sessions. Verify first, present second.

## Ondoway-Specific Rules

### Zero Lint Errors — No Exceptions

> `make lint` must produce ZERO errors before ANY commit, agent spawn, or declaration of done.

- "Pre-existing" is not an exemption. 126 errors = fix 126 errors.
- Run `make lint` at Step 0 of every workflow.
- The lint-enforcer hook mechanically blocks commits and agent spawns when lint is dirty.
- Never pipe `make lint` through `tail` or `head`.

### Never Run Flutter Tests in Background

Flutter buffers stdout completely — background `make flutter-test` produces 0 bytes until finish.
- Always run `make flutter-test` in the foreground.
- Never poll background tasks with `sleep` loops.

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
- Specs live in `specs/{date}-{topic}/` with files: 01-scope -> 02-spec -> 03-scopes (or 03-red-team) -> 04-red-team (or 04-plan) -> 05-plan -> 06-verify
- Use `/spec-pm` to drive the lifecycle. Each stage builds on the prior — don't skip.
- Invoke the challenger agent (`/challenge`) before saving any scope/spec/plan, before committing, and before declaring a scope done
- Multi-scope features track progress in `specs/{date}-{topic}/state.json`
- After implementation, run the full test suite before committing

## Python style (ruff — enforced by PostToolUse hook)

- **Line length:** 100 chars
- **Enabled rule sets:** E, F, I, N, W, UP, B, SIM, RUF
- **Imports:** isort order (stdlib -> third-party -> local). No unused imports (F401). No `import *` (F403).
- **Modern Python (UP):** `dict` not `Dict`, `list` not `List`, `X | None` not `Optional[X]`, f-strings not `.format()`.
- **Bugbear (B):** No mutable default args, no bare `except:`, no `assert` outside tests.
- **Simplify (SIM):** Ternary over trivial if/else, `not in` over `not x in`, merge nested `with`.
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
3. New POIs within 100m of existing -> flag for user review
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
