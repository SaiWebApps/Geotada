# Test Strategy

`make test` is the only exhaustive executor. It runs eight shards in order and
a skip counts as a failure — a test that has not run is not a test:

| Shard | What it proves | Needs |
|---|---|---|
| `_test-python` (pure) | Hermetic Python logic, fully parallel | Nothing external |
| `_test-python` (DB) | Neo4j-backed behavior, 3 workers with one test graph each | Docker + local Neo4j |
| `flutter-test` | The mobile app | Flutter |
| `test-workbench` | The editorial workbench in a real browser (Playwright), on its own isolated graph | Docker, Valhalla, Playwright |
| `_test-golden` | Live dev-graph tours against the human-curated targets | Dev data, Valhalla |
| `_test-grade` | Tour scoring against the graded baseline | Dev data, Valhalla |
| `_test-invariants` | Customer-facing regression invariants on live tours | Dev data, Valhalla |
| `test-live` | Real provider calls (TTS, transcription) | Render credential, provider credit |
| `_test-cloud` | Read-only Aura parity | Render credential |

`make audit` is `make lint` followed by `make test`.

## Day-to-day loop

Run the targeted test in the foreground and read the result:

```bash
uv run pytest tests/test_x.py -k <test_name> --tb=short
```

Use `make test-file FILE=tests/test_x.py` when the test needs the database,
Valhalla, or credentials — it provisions those itself. Run the full suite once
per milestone, not inside the loop. The full rules live in
`.claude/rules/testing.md`.

## Fixtures and safety

- `tests/conftest.py` refuses to run against anything but the local test
  graphs (ports 7688/7690/7691) — the suite contains destructive fixtures and
  the cloud database is never wiped by tests.
- Paid provider keys are scrubbed before the API is imported at collection
  time; the live shard alone re-fetches real credentials from Render.
- Each pytest worker owns its own graph; sharing one produces phantom
  failures, which is why the suite must never run concurrently with a sibling
  session's suite.

## Adding tests

Put the test beside the behavior it pins (`tests/test_<module>.py` naming),
mark DB-dependent tests via the fixtures (the `needs_db` marker is applied
automatically), and follow the red-first loop: the new test fails before the
change and passes after.
