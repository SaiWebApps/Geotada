# Test Strategy

## Overview

177 tests covering the Ondoway Neo4j graph backend — schema definitions, data seeding, graph traversals, the full CRUD API, and trip generation.

All tests run with pytest. No Selenium or browser tests; the editor UI is a static HTML file served by FastAPI.

## Running Tests

```bash
make test               # All 177 tests (needs Neo4j running)
make test-unit          # Unit tests only (no Neo4j needed)
make test-integration   # Integration tests only (needs Neo4j)
```

## Test Breakdown

| File                        | Tests | Type        | What It Covers                        |
|-----------------------------|-------|-------------|---------------------------------------|
| test_definitions.py         | 11    | Unit        | Schema definitions are well-formed    |
| test_api_models.py          | 11    | Unit        | Node Pydantic models validate correctly |
| test_api_edge_models.py     | 10    | Unit        | Edge Pydantic models validate correctly |
| test_trip_models.py         | 17    | Unit        | Trip generation Pydantic models       |
| test_trip_adapter.py        | 7     | Unit        | route_script_to_stops engine adapter  |
| test_trip_lens_resolution.py | 3    | Unit        | Lens precedence (request → profile → none) |
| test_constraints.py         | 4     | Integration | Constraints and indexes applied to Neo4j |
| test_seed.py                | 8     | Integration | Data seeding + idempotency            |
| test_traversals.py          | 7     | Integration | Planner, Wanderer, DAG traversals     |
| test_api_create.py          | 16    | Integration | Node creation via API (all 7 types)   |
| test_api_endpoints.py       | 19    | Integration | Node listing, retrieval, pagination   |
| test_api_update_delete.py   | 12    | Integration | Node update + delete + cascade        |
| test_api_edges.py           | 25    | Integration | Edge CRUD (all 11 relationship types) |
| test_api_schema_nodes.py    | 17    | Integration | Node schema introspection endpoints   |
| test_api_schema_edges.py    | 12    | Integration | Relationship schema introspection     |
| test_trip_api.py            | 8     | Integration | Trip generation endpoint (201/404/422)|
| **Total**                   | **177** |           |                                       |

## What Each Category Validates

### Unit Tests (49 tests)

Run without Neo4j. Test pure Python logic:

- **Schema definitions**: Every node type has required fields, correct types, and valid constraints. Every relationship type is defined. No duplicate property names.
- **Pydantic models**: Node create models enforce required fields, reject invalid types, apply defaults. Edge create/update models validate source/target structure.
- **Trip models**: TripGenerateRequest validates coordinate ranges, radius/max_stops caps, HH:MM time format, and defaults. GeneratedStop and TripGenerateResponse enforce required fields.
- **Trip generation logic**: Golden ratio algorithm selects ~20% anchors (gravity 5) and ~80% flavour (gravity 1–4), deduplicates by POI, respects max_stops and duration budget. Schedule computation assigns sequential start times.

### Integration Tests (128 tests)

Require a running Neo4j instance. Use pytest fixtures that skip automatically when Neo4j is unavailable.

- **Constraints** (4): Unique constraints created, duplicate inserts rejected, indexes applied, idempotent re-application.
- **Seeding** (8): All 7 node types created with correct counts. All 11 relationship types present. Running seed twice produces no duplicates.
- **Traversals** (7): Planner path (Trip → ItineraryItem → POI → Beat → Lens) returns rows. Wanderer path (Profile → Lens ← Beat ← POI) with spatial filter works. DAG path (Lens → Lens via IS_PARENT_OF) returns rows.
- **API CRUD** (84): Full create/read/update/delete lifecycle for all 7 node types and 11 edge types. Pagination, 404 handling, constraint violation (409), validation errors (422), cascade deletes.
- **Schema introspection** (29): All node schemas returned with correct properties, constraints, and indexes. All relationship schemas returned. Individual type lookups work. Invalid labels return 422.
- **Trip generation** (8): POST /trips/generate runs the real tour engine against the LIVE local Paris dev graph (port 7687, disposable test profiles cleaned up in teardown). Stop order equals select_route's POI order. Every beat_id is traceable to a route POI. lens_coverage present. Multi-beat persistence verified (one PLAYS_BEAT edge per beat). Lens precedence (request → profile). Non-existent profile returns 404. Sparse origin (Sydney) returns 422 from the density gate.

## Test Fixtures

Key fixtures in `tests/conftest.py`:

- **Neo4j auto-skip**: Integration tests check for a live Neo4j connection. If unavailable, they skip with a clear message rather than failing.
- **Database cleanup**: Tests that create data clean up after themselves.
- **FastAPI test client**: API tests use `TestClient` from Starlette — no real HTTP server needed.

## Adding New Tests

1. **Unit tests**: Add to `test_definitions.py` (schema), `test_api_models.py` / `test_api_edge_models.py` (Pydantic), or `test_trip_models.py` / `test_trip_adapter.py` (trip logic).
2. **Integration tests**: Add to the appropriate `test_api_*.py` or `test_trip_api.py` file. Use the existing Neo4j fixtures.
3. **New node/edge type**: Add schema in `src/schema/definitions.py`, create model in `src/api/models/`, then add tests covering create, read, update, delete, and schema introspection.

## CI Expectations

- All 177 tests should pass on every commit
- Unit tests run in < 1 second
- Integration tests require Docker + Neo4j (started via `make db-up`)
- Full suite runs in ~10 seconds
