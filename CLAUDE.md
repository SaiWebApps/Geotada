# Travlr — GPS-triggered audio tour platform

## Project structure
- `data/{city_slug}/` — pipeline data (poi-raw.json, beats.json, export/)
- `Books/{city_slug}/{book_slug}/` — chunked source texts + manifest.json
- `.claude/commands/` — 14 pipeline skills (beat-from-book, pipeline-batch, etc.)
- `.claude/agents/challenger.md` — adversarial reviewer, invoke at checkpoints
- `tests/` — pytest suite
- Launch city: Paris (`data/paris/`)

## Key docs (read before related work)
- @Docs/Markdown Docs/NORTHSTAR.md — product north star, locked decisions, Neo4j schema v3
- @specs/NORTHSTAR.md — same as above, canonical location
- Tour-builder design: the prior rule-forward design at `Docs/tour-builder/design.md` is DEPRECATED as of 2026-04-22. Restarting learn-by-example from Paris guidebooks. Do not auto-load.

## Active work (2026-04-28)
- **Tour-builder Phase 2 + 2.5 + 2.6 landed locally** (commits b2c7cfc + 794f284). Phase 3 (`generation.py` + `validation.py` + Haiku-glue prompt) is the next start. See `Docs/tour-builder/phase-1-design.md` for the spec.
- **Push to origin/main is DEFERRED** — local diverged from remote (3 line-level conflicts in `frontend/review.html`, `src/api/routes/graph.py`, `src/seed/narratives.py`; remote's TTS commit and local both added `sort_order` independently). Full audit + resolution plan in `data/paris/.pipeline-state.json` under `backlog.push_divergence`. Trigger to resolve: before Phase 5 ships the `/tour-build` skill.

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
