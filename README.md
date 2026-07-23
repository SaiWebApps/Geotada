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
make bootstrap
```

This installs dependencies, starts the three isolated local Neo4j services and
Valhalla, and additively provisions the committed city data. It never touches
Aura.

If any step fails, see [Troubleshooting](Docs/Markdown%20Docs/TROUBLESHOOTING.md).

### 3. Start the app

```bash
make api
```

Then open:

- **Graph editor**: http://localhost:8000/editor — create, edit, delete nodes and edges visually
- **API docs (Swagger)**: http://localhost:8000/docs — interactive API explorer
- **Read-only dashboard**: run `make dashboard` for a dashboard at http://localhost:8080

### 4. Configure Render access

Commands that need provider credentials fetch the complete current Render
environment on every run. Store the API key once with `make render-auth-setup`
and verify it with `make config-status`. Secrets are not copied into project
files.

## Documentation

| Document | Description |
|----------|-------------|
| [Graph Editor Guide](Docs/Markdown%20Docs/GRAPH_EDITOR.md) | How to use the interactive graph editor — UI layout, creating nodes/edges, keyboard shortcuts, working with test data |
| [API Reference](Docs/Markdown%20Docs/API_REFERENCE.md) | All 16 REST endpoints with parameters, request/response bodies, status codes, and examples |
| [Test Strategy](Docs/Markdown%20Docs/TEST_STRATEGY.md) | 177-test breakdown, unit vs integration, fixtures, adding new tests |
| [Troubleshooting](Docs/Markdown%20Docs/TROUBLESHOOTING.md) | Docker, Neo4j, Python venv, API, and editor issues with fixes |
| [Security & Privacy](Docs/Markdown%20Docs/SECURITY_PRIVACY_PRACTICES.md) | Non-negotiable security and privacy constraints for development |

## Make Commands

| Command                 | Description                                      |
|-------------------------|--------------------------------------------------|
| `make bootstrap`        | Provision a complete local development environment |
| `make sync`             | Install Python dependencies                      |
| `make db-up DB=dev`     | Start dev Neo4j on 7687                          |
| `make db-up DB=test`    | Start test Neo4j on 7688                         |
| `make db-up DB=workbench` | Start workbench Neo4j on 7689                 |
| `make db-down DB=...`   | Stop one selected local Neo4j                    |
| `make db-status`        | Check Neo4j container status                     |
| `make db-reset DB=...`  | Delete only one selected local database volume   |
| `make test`             | Run every test shard (the definitive executor)   |
| `make test-file FILE=...` | Run one focused test file safely               |
| `make test-live`        | Run the standalone live-provider shard           |
| `make api`              | Start FastAPI on port 8000                       |
| `make dashboard`        | Start read-only dashboard on port 8080           |
| `make lint`             | Run ruff linter                                  |
| `make format`           | Auto-format code                                 |
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
    ├── models/                # Pydantic models (nodes, edges, schema, trips)
    ├── crud/                  # Cypher operations + schema introspection + trip generation
    └── routes/                # API endpoint handlers (nodes, edges, schema, audio, trips)
frontend/
├── index.html                 # Read-only dashboard
└── editor/
    └── index.html             # Interactive graph editor
tests/                         # 177 tests — see Test Strategy doc
```
