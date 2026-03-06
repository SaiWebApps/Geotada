# Travlr — Neo4j Graph API & Editor

Graph database schema, CRUD API, seed data, and interactive editor for the Travlr audio tour app.

Implements **Schema_v3**: 7 node types, 11 relationships, 3 domains (Traveler's Vault, Global Atlas, Execution Bridge).

## Prerequisites

- **Python 3.11+**
- **Docker** (for Neo4j)

## Quick Start

```bash
# Full bootstrap — create venv, install deps, start Neo4j, apply schema, run tests
make all

# Or step by step:
make install      # Create venv, copy .env, install Python deps
make db-up        # Start Neo4j in Docker
make setup        # Apply schema + seed + verify
make test         # Run all tests (152 tests)
```

All `make` targets use the virtualenv automatically (`.venv/bin/python`).
To run commands manually, activate it first:

```bash
source .venv/bin/activate
```

## Running the App

```bash
make api          # FastAPI CRUD API at http://localhost:8000
                  # Graph editor UI at http://localhost:8000/editor
make dashboard    # Read-only dashboard at http://localhost:8080
```

## Commands

| Command              | Description                                |
|----------------------|--------------------------------------------|
| `make help`          | Show all available commands                |
| `make venv`          | Create Python virtual environment          |
| `make install`       | Install dependencies (creates venv + .env) |
| `make db-up`         | Start Neo4j in Docker                      |
| `make db-down`       | Stop Neo4j                                 |
| `make db-status`     | Check Neo4j container status               |
| `make db-reset`      | Stop Neo4j and wipe all data               |
| `make setup`         | Full pipeline: schema + seed + verify      |
| `make verify`        | Run verification only                      |
| `make test`          | Run all tests                              |
| `make test-unit`     | Run unit tests (no Neo4j needed)           |
| `make test-integration` | Run integration tests (needs Neo4j)     |
| `make lint`          | Run ruff linter                            |
| `make format`        | Auto-format code                           |
| `make api`           | Start FastAPI on port 8000                 |
| `make dashboard`     | Start read-only dashboard on port 8080     |
| `make clean-db`      | Wipe all nodes and relationships           |
| `make all`           | Full bootstrap: venv + install + db + setup + test |

## API Endpoints

### Node CRUD (`/api/v1/nodes`)

| Method | Path | Description |
|--------|------|-------------|
| GET    | `/nodes/{label}` | List nodes by label (paginated) |
| GET    | `/nodes/{label}/{id}` | Get single node |
| POST   | `/nodes/{label}` | Create node |
| PUT    | `/nodes/{label}/{id}` | Update node properties |
| DELETE | `/nodes/{label}/{id}` | Delete node + connected edges |

### Edge CRUD (`/api/v1/edges`)

| Method | Path | Description |
|--------|------|-------------|
| GET    | `/edges/{rel_type}` | List edges by type (paginated) |
| GET    | `/edges/{rel_type}/{id}` | Get single edge |
| POST   | `/edges/{rel_type}` | Create edge between two nodes |
| PUT    | `/edges/{rel_type}/{id}` | Update edge properties |
| DELETE | `/edges/{rel_type}/{id}` | Delete edge |

### Schema Introspection (`/api/v1/schema`)

| Method | Path | Description |
|--------|------|-------------|
| GET    | `/schema/nodes` | List all node type schemas |
| GET    | `/schema/nodes/{label}` | Get schema for one node type |
| GET    | `/schema/relationships` | List all relationship type schemas |
| GET    | `/schema/relationships/{type}` | Get schema for one rel type |

### Graph (`/api/v1/graph`)

| Method | Path | Description |
|--------|------|-------------|
| GET    | `/graph` | Full graph data for visualization |

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
    ├── models/
    │   ├── nodes.py           # Node Pydantic models
    │   ├── edges.py           # Edge Pydantic models
    │   └── schema.py          # Schema introspection models
    ├── crud/
    │   ├── nodes.py           # Node Cypher operations
    │   ├── edges.py           # Edge Cypher operations
    │   └── schema.py          # Schema introspection (pure Python)
    └── routes/
        ├── nodes.py           # Node API endpoints
        ├── edges.py           # Edge API endpoints
        ├── schema.py          # Schema API endpoints
        └── graph.py           # Graph visualization endpoint
frontend/
├── index.html                 # Read-only dashboard
└── editor/
    └── index.html             # Interactive graph editor
tests/
├── conftest.py                # Shared fixtures, Neo4j auto-skip
├── test_definitions.py        # Unit tests (no Neo4j)
├── test_constraints.py        # Integration: constraints
├── test_seed.py               # Integration: seeding + idempotency
├── test_traversals.py         # Integration: traversal patterns
├── test_api_create.py         # API: node creation
├── test_api_endpoints.py      # API: listing + retrieval
├── test_api_models.py         # API: Pydantic model unit tests
├── test_api_update_delete.py  # API: update + delete
├── test_api_edges.py          # API: edge CRUD (integration)
├── test_api_edge_models.py    # API: edge model unit tests
├── test_api_schema_nodes.py   # API: node schema introspection
└── test_api_schema_edges.py   # API: rel schema introspection
```

## What Gets Verified

1. **Planner traversal** — `Trip -> ItineraryItem -> POI -> Beat -> Lens` (>=3 rows)
2. **Wanderer traversal** — `Profile -> Lens <- Beat <- POI` with spatial filter (>=1 row)
3. **DAG traversal** — `Lens -> Lens` via IS_PARENT_OF (>=1 row)
4. **Idempotency** — Running setup twice produces no duplicates
5. **All 11 relationship types** present in the graph
