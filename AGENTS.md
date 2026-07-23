# Ondoway agent execution contract

## Commands and configuration

- Run project operations through the owning `make` target. Do not invoke pytest,
  uvicorn, deployment scripts, or database scripts directly.
- `make test` is the one definitive test suite. There is no alternate full-suite
  target. `make test-file FILE=...` is only a focused iteration command.
- Never source, copy, create, or trust `.env`, `.env.local`, `.env.test`, or
  `.env.cloud`. Make constructs a fresh child environment for every command.
- Any target that needs provider or production configuration must fetch the full
  current Render service environment through `scripts/dev_env.py`; do not select
  individual variables or keep a local cache.
- The Render API credential lives in macOS Keychain under service
  `ondoway-render-api-key`, label `ondoway-dev`. Validate it with
  `make render-auth-status`; configure it with `make render-auth-setup`.

## Database safety

- Local profiles are fixed: dev `localhost:7687`, test `localhost:7688`, and
  workbench `localhost:7689`.
- Pytest may connect only to test port 7688. Its fixtures are destructive.
- Aura is never a pytest target and is never reachable from `db-reset`.
- `make db-parity TARGET=cloud` and the cloud shard inside `make test` are
  read-only. They use a Neo4j READ session.
- A cloud data write requires an explicit public command with both
  `TARGET=cloud` and `CONFIRM_CLOUD_WRITE=1`. Never add cloud fallbacks.
- `make db-reset DB=...` deletes only the selected local service volume. Never
  replace it with `docker compose down -v`.

## Verification

- Skips and credential-based deselections are failures.
- After changing Python or test infrastructure, run `make lint`, focused tests,
  the relevant standalone major target, and finally `make test`.
