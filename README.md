# Travlr — Neo4j Schema Setup

Graph database schema, seed data, and verification for the Travlr audio tour app.

Implements **Schema_v3**: 7 node types, 11 relationships, 3 domains (Traveler's Vault, Global Atlas, Execution Bridge).

## Quick Start

```bash
# Full bootstrap — install deps, start Neo4j, apply schema, run tests
make all

# Or step by step:
make install      # Install Python deps
make db-up        # Start Neo4j in Docker
make setup        # Apply schema + seed + verify
make test         # Run all tests
make dashboard    # Open web dashboard at http://localhost:8080
```

## Commands

| Command              | Description                            |
|----------------------|----------------------------------------|
| `make help`          | Show all available commands             |
| `make install`       | Install Python dependencies             |
| `make db-up`         | Start Neo4j in Docker                   |
| `make db-down`       | Stop Neo4j                              |
| `make db-reset`      | Stop Neo4j and wipe all data            |
| `make setup`         | Full pipeline: schema → seed → verify   |
| `make verify`        | Run verification only                   |
| `make test`          | Run all tests                           |
| `make test-unit`     | Run unit tests (no Neo4j needed)        |
| `make test-integration` | Run integration tests (needs Neo4j) |
| `make lint`          | Run ruff linter                         |
| `make format`        | Auto-format code                        |
| `make dashboard`     | Start web dashboard on port 8080        |
| `make clean-db`      | Wipe all nodes and relationships        |

## Project Structure

```
src/
├── connection.py          # Neo4j driver factory
├── main.py                # CLI entry point (setup/verify/clean)
├── server.py              # Dashboard HTTP server
├── schema/
│   ├── definitions.py     # Pure data: constraints, indexes, lenses
│   └── constraints.py     # Apply constraints/indexes to Neo4j
├── seed/
│   ├── lenses.py          # 12 MVP lenses + DAG child
│   ├── users.py           # Test user + profiles + lens prefs
│   ├── locations.py       # 3 Paris POIs with GeoPoints
│   ├── narratives.py      # 4 narrative beats
│   ├── trips.py           # Trip + itinerary items
│   └── runner.py          # Orchestrator
└── verify/
    ├── counts.py           # Node/relationship counting
    ├── traversals.py       # Planner, Wanderer, DAG queries
    └── reporter.py         # Formatted output
tests/
├── conftest.py             # Shared fixtures
├── test_definitions.py     # Unit tests (no Neo4j)
├── test_constraints.py     # Integration: constraints
├── test_seed.py            # Integration: seeding + idempotency
└── test_traversals.py      # Integration: traversal patterns
frontend/
└── index.html              # Dashboard UI
```

## What Gets Verified

1. **Planner traversal** — `Trip → ItineraryItem → POI → Beat → Lens` (≥3 rows)
2. **Wanderer traversal** — `Profile → Lens ← Beat ← POI` with spatial filter (≥1 row)
3. **DAG traversal** — `Lens → Lens` via IS_PARENT_OF (≥1 row)
4. **Idempotency** — Running setup twice produces no duplicates
5. **All 11 relationship types** present in the graph
