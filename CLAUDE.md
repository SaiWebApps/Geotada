# Ondoway — GPS-triggered audio tour platform

## Agent Perspectives

This project benefits from all agent perspectives. Use them:
- `/agent-chat architect` — before designing new features or data model changes
- `/agent-chat reviewer` — before presenting ANY result (mandatory self-verification)
- `/agent-chat implementer` — when setting up builds, running tests, or debugging infra

The reviewer's self-verification checklist is **mandatory** before presenting results.

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
```

**Port mapping:** Test Neo4j = 7688, Dev Neo4j = 7687. Both must be running for full suite.

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
