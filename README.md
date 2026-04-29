# Ondoway — Neo4j Graph API & Editor

Graph database schema, CRUD API, seed data, and interactive editor for the Ondoway audio tour app.

Implements **Schema_v3**: 7 node types, 11 relationships, 3 domains (Traveler's Vault, Global Atlas, Execution Bridge).

## Prerequisites

| Tool          | Version | Check                    | Install (macOS)              |
|---------------|---------|--------------------------|------------------------------|
| Python        | 3.11+   | `python3 --version`      | `brew install python@3.11`   |
| Docker Desktop| any     | `docker --version`       | `brew install --cask docker` |

> **Claude Code users**: Run `/setup-check` to verify prerequisites automatically.

## New Developer Setup

Follow these steps to go from a fresh clone to a running app:

### 1. Clone and enter the repo

```bash
git clone <repo-url> && cd ondoway
```

### 2. Bootstrap everything

```bash
make all
```

This single command runs the full pipeline:

1. **`make venv`** — Creates a Python virtual environment at `.venv/`
2. **`make env`** — Copies `.env.example` to `.env` (won't overwrite an existing `.env`)
3. **`make install`** — Installs Python dependencies into the venv
4. **`make db-up`** — Pulls the Neo4j 5 Docker image and starts it on ports 7474 (browser) and 7687 (Bolt)
5. **`make setup`** — Applies the graph schema (constraints + indexes), seeds test data, and verifies traversals
6. **`make test`** — Runs all 152 tests

If any step fails, see [Troubleshooting](Docs/Markdown%20Docs/TROUBLESHOOTING.md).

### 3. Start the app

```bash
make api
```

Then open:

- **Graph editor**: http://localhost:8000/editor — create, edit, delete nodes and edges visually
- **API docs (Swagger)**: http://localhost:8000/docs — interactive API explorer
- **Read-only dashboard**: run `make dashboard` for a dashboard at http://localhost:8080

### 4. (Optional) Activate the venv for manual commands

All `make` targets use the venv automatically. To run Python commands directly:

```bash
source .venv/bin/activate
```

## Documentation

| Document | Description |
|----------|-------------|
| [Graph Editor Guide](Docs/Markdown%20Docs/GRAPH_EDITOR.md) | How to use the interactive graph editor — UI layout, creating nodes/edges, keyboard shortcuts, working with test data |
| [API Reference](Docs/Markdown%20Docs/API_REFERENCE.md) | All 15 REST endpoints with parameters, request/response bodies, status codes, and examples |
| [Test Strategy](Docs/Markdown%20Docs/TEST_STRATEGY.md) | 152-test breakdown, unit vs integration, fixtures, adding new tests |
| [Troubleshooting](Docs/Markdown%20Docs/TROUBLESHOOTING.md) | Docker, Neo4j, Python venv, API, and editor issues with fixes |
| [Security & Privacy](Docs/Markdown%20Docs/SECURITY_PRIVACY_PRACTICES.md) | Non-negotiable security and privacy constraints for development |

## Make Commands

| Command                 | Description                                      |
|-------------------------|--------------------------------------------------|
| `make all`              | Full bootstrap: venv + install + db + setup + test |
| `make install`          | Install dependencies (creates venv + .env)       |
| `make db-up`            | Start Neo4j in Docker                            |
| `make db-down`          | Stop Neo4j                                       |
| `make db-status`        | Check Neo4j container status                     |
| `make db-reset`         | Stop Neo4j and wipe all data                     |
| `make setup`            | Full pipeline: schema + seed + verify            |
| `make test`             | Run all tests                                    |
| `make test-unit`        | Run unit tests (no Neo4j needed)                 |
| `make test-integration` | Run integration tests (needs Neo4j)              |
| `make api`              | Start FastAPI on port 8000                       |
| `make dashboard`        | Start read-only dashboard on port 8080           |
| `make lint`             | Run ruff linter                                  |
| `make format`           | Auto-format code                                 |
| `make clean-db`         | Wipe all nodes and relationships                 |
| `make help`             | Show all available commands                      |

## Project Structure

```
src/
├── connection.py              # Neo4j driver factory
├── main.py                    # CLI entry point (setup/verify/clean)
├── server.py                  # Dashboard HTTP server
├── schema/
│   ├── definitions.py         # Pure data: constraints, indexes, lenses
│   └── constraints.py         # Apply constraints/indexes to Neo4j
├── seed/
│   ├── lenses.py              # 12 MVP lenses + DAG child
│   ├── users.py               # Test user + profiles + lens prefs
│   ├── locations.py           # 3 Paris POIs with GeoPoints
│   ├── narratives.py          # 4 narrative beats
│   ├── trips.py               # Trip + itinerary items
│   └── runner.py              # Orchestrator
├── verify/
│   ├── counts.py              # Node/relationship counting
│   ├── traversals.py          # Planner, Wanderer, DAG queries
│   └── reporter.py            # Formatted output
└── api/
    ├── app.py                 # FastAPI app factory
    ├── dependencies.py        # Neo4j driver injection
    ├── models/                # Pydantic models (nodes, edges, schema)
    ├── crud/                  # Cypher operations + schema introspection
    └── routes/                # API endpoint handlers
frontend/
├── index.html                 # Read-only dashboard
└── editor/
    └── index.html             # Interactive graph editor
tests/                         # 152 tests — see Test Strategy doc
```
