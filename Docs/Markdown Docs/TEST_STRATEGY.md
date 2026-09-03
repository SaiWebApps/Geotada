# Test Strategy

`make test` is the only exhaustive executor. It runs FIVE CONCURRENT TRACKS —
grouped so no two tracks share mutable state — and a skip counts as a failure;
a test that has not run is not a test. The longest track (db+live) streams to
the terminal; the others buffer and print below it, and any red track fails
the bar:

| Track | What it proves | Owns |
|---|---|---|
| `_track-db-live` | Neo4j-backed behavior (3 workers, one test graph each), then real provider calls (TTS, transcription) | The 7688/7690/7691 test graphs; Render credential + provider credit for the live half |
| `_track-pure` | Hermetic Python logic, 8 parallel workers | CPU only |
| `_track-devgraph` | The trip API, the eleven persona traces and the authoring gates on the live corpus | Dev graph (7687) writes + Valhalla |
| `_track-surfaces` | The mobile app (Flutter), the editorial workbench in a real browser (Playwright) on its own isolated graph, and read-only Aura parity | Dart VM; workbench graph 7689; Aura reads |
| `_track-tour-quality` | Golden tours against the human-curated targets, tour scoring against the graded baseline, and customer-facing regression invariants — serialized within the track | Dev graph (7687) reads + Valhalla |

The goldens refuse an UNROUTED walk by name (a Valhalla outage or contention
fails as itself, never as a mystery overlap dip), which is what makes running
the tracks concurrently safe.

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
