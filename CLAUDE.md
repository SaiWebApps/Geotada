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

## Running tests
```bash
pytest tests/                              # full suite
pytest tests/test_gravity_distribution.py  # after /poi-gravity
pytest tests/test_export_consistency.py    # after /export-validate
pytest tests/test_lens_drift.py            # before /upload
pytest tests/test_tour_*.py                # tour-builder suite
```

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
