# Founding case — measured, before any change

Per the FOUNDING-CASE EFFICACY rule: the real case that motivates this work,
measured first, so every step can report a before/after number against it.

## Measurement 1 — the live workbench API offers a fake to a human

Command (read-only, free) against the workbench/dev API process that was
already running on :8000 (started 21:03, i.e. before the in-flight
`src/audio/provider.py` edits):

```
curl -s http://127.0.0.1:8000/api/v1/audio/providers
```

Result:

```json
{"providers": [
  {"name": "elevenlabs", "available": false},
  {"name": "mock",       "available": true},
  {"name": "openai",     "available": true}
]}
```

`frontend/review.html`'s `loadTtsProviders()` wipes the static `<select>` and
repopulates it from exactly this response. So on the running workbench, a
silent-WAV fake is one click away from an editor judging what a tourist will
hear. That is the never-mock-in-the-workbench rule being violated live, not
hypothetically.

**Target after fix:** the `providers` array contains only implementations that
send text to a real speech service. `mock` must be absent.

## Measurement 2 — the workbench never even honours the dropdown

`frontend/review.html:3127`:

```js
body: JSON.stringify({ text, provider: 'mock' }),
```

This is inside `ttsPlay()`, the ONE shared TTS implementation used by both beat
TTS and the tour-preview stops (comment at :3088-3090). The page tracks the
selected provider correctly — default `'openai'` at :3045, synced to the
dropdown at :3082 and :3086, and used in BOTH cache keys at :3163 and :3630 —
but the request body ignores `ttsProvider` entirely.

Consequences, both true at once:
1. Every workbench "play" was answered by the silent fake regardless of what
   the editor selected. The dropdown was decorative.
2. Now that `_PROVIDERS` no longer registers `mock` (in-flight edit), this same
   line asks for a provider that cannot resolve, so workbench audio is broken
   outright rather than silently fake.

**Target after fix:** the request body carries the selected real provider, and a
test goes RED if a fake provider name is ever hardcoded in the page again.

## Measurement 3 — no guard exists

Seven test files reference `review.html`:

```
tests/test_upload_api.py
tests/test_workbench_ui.py
tests/test_workbench_matches_the_app.py
tests/test_workbench_preview_wiring.py
tests/test_workbench_deprecate_guard.py
tests/test_tour_one_engine.py
tests/test_workbench_review_regressions.py
```

None asserts that the page does not hardcode a fake provider. That absence is
why Measurement 2 survived. A guard that does not exist cannot go red — so each
fix step below must ship a test that is demonstrated RED before the fix.

## Measurement 4 — the workbench onboarding page drafts with a fake

`frontend/onboard.html:482` calls `POST /onboard/jobs/{id}/draft-beats`.
That route (`src/api/routes/onboard.py:287`) calls `draft_all(...)`, which
resolves `get_drafter()` (`src/onboard/beat_draft.py:320-325`). It returns
`MockBeatDrafter()` unless `ONBOARD_PROVIDER == "anthropic"`; the default is
`"mock"` (`beat_draft.py:51`) and `scripts/workbench.sh` does not set it.

The route mounts ONLY under `WORKBENCH_API_ENABLED` (`src/api/app.py:193-196`),
so it is a workbench-only surface. A human onboarding a city through the
workbench is shown mock-drafted beats.

**Target after fix:** the workbench cannot resolve a fake drafter; the free
CLI/test path must opt in explicitly rather than be the default.

## Baseline

- `make lint` — green. One pre-existing SIM114 at
  `tests/test_workbench_ui.py:450` was fixed first (semantics-preserving
  combine of two branches that both did `value = node.value`, rewritten to the
  `if not (...): continue` idiom used directly below it). Re-run: "All checks
  passed!"
- Containers: `ondoway-neo4j` (7687), `-test` (7688), `-workbench` (7689),
  `ondoway-valhalla` (8002) all healthy. No pytest/make run in progress.
- Working tree is heavily modified by a SEPARATE in-flight campaign
  (`specs/2026-07-29-one-true-tour-algorithm`, tier 3, 9/10 steps completed):
  ~3.3k insertions / ~13.6k deletions staged across 42 test files. Anything
  that runs the full bar here can fail for reasons unrelated to mocks.
