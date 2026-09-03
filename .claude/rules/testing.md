---
paths:
  - "tests/**/*.py"
  - "Makefile"
  - "scripts/preflight.py"
---

# Tests and preflight

## The loop

Write or update the targeted test → make the change → confirm that test passes →
`make lint`. That is the whole loop. Repeat it until the milestone is done, then run
`make test` once.

Run the targeted test in the foreground and read what it prints:

```
uv run pytest tests/test_x.py -k <test_name> --tb=short
```

Use `make test-file FILE=tests/test_x.py [LIVE=1]` when the test needs the database,
Valhalla or live credentials — it resolves those prerequisites first.

Never redirect test output to a background `.log` and poll it in a loop. Never write a
mutation proof, an UNDO/restore cycle, or a staged re-verification ladder. If you doubt a
test is real, read it.

## The full suite

`make test` is the definitive suite: local pytest, Flutter, workbench browser, golden tours,
tour grade, tour invariants, live-provider tests, read-only cloud parity. It needs the
matching live credentials, and it declares its prerequisites up front (`PRE_FULL_SUITE`), so
a missing credential or Playwright browser fails in seconds rather than twenty minutes in.
`make audit` is `make lint` then `make test`. `test-live` sets `ONDOWAY_LIVE_TESTS=1`.

Run it once at milestone completion, not inside the iteration loop.

**A skip is a failure.** Skips and credential-based deselections count as failures, not as
passes. A test that has not been run is not a test.

## Preflight

Every public target opens with `@$(PREFLIGHT) --label <name> <requirements...>`.
`scripts/preflight.py` resolves that list in dependency order, probes each capability for
real, starts or installs what it may, and refuses the recipe otherwise, naming the exact
remedy. `make preflight-list` prints the vocabulary. Reusable sets (`PRE_PY`,
`PRE_LOCAL_GRAPH`, `PRE_TOUR`, `PRE_PYTEST`, `PRE_FLUTTER`, `PRE_FULL_SUITE`) sit at the top
of the Makefile.

Two rules bind new code in `scripts/preflight.py`:

- **A probe reports evidence it observed itself.** Never infer success from another command's
  silence. Database readiness is a real Cypher query returning 0, not an inspection of the
  container list. A probe searches only the real PATH, because a tool preflight can see and
  the recipe cannot is the same lie.
- **Every requirement can restore itself.** New requirements get a `repair`;
  `tests/test_preflight.py` fails any that does not unless it is listed in
  `REQUIREMENTS_THAT_CANNOT_SELF_REPAIR`. Mark a slow repair `announce`. Mark one needing a
  human `interactive` — those skip without a TTY rather than hang.
