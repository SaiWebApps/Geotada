# Troubleshooting

Common issues and fixes for the Ondoway Neo4j development environment.

---

## Docker & Neo4j

### "Cannot connect to the Docker daemon"

Docker Desktop is not running.

```bash
open -a Docker          # Start Docker Desktop (macOS)
```

Wait 10-15 seconds for it to finish starting, then retry.

### "Forbidden" error from Docker commands

The Docker CLI is pointing to the wrong context (likely `vessel`, an Apple-internal system).

```bash
docker context ls       # Check which context has the *
docker context use desktop-linux
```

### Neo4j container won't start

```bash
make db-status          # Check container state
docker logs ondoway-neo4j  # View Neo4j logs
```

Common causes:
- Port 7474 or 7687 already in use: `lsof -i :7687` to find the process
- Previous data volume corrupted: `make db-reset` to wipe and restart

### Neo4j container is running but app can't connect

Check the port in `.env` matches `docker-compose.yml`:

```bash
grep NEO4J_URI .env
# Should be: NEO4J_URI=bolt://localhost:7687
```

If the port is wrong (e.g., `17687`), fix it:

```bash
cp .env.example .env    # Reset to defaults
```

### Authentication failed

The password in `.env` doesn't match `docker-compose.yml`. Both should use `ondoway_dev_2026`:

```bash
grep NEO4J_PASSWORD .env                    # App password
grep NEO4J_AUTH docker-compose.yml          # Container password
```

If they're out of sync, the simplest fix is to reset:

```bash
make db-reset           # Wipe data volume (resets password)
cp .env.example .env    # Reset env to defaults
make db-up              # Restart with matching credentials
```

---

## OSRM Routing

### OSRM first-run setup

`make osrm-up` needs a one-time graph prep before it works — the server refuses
to start without the customized `.osrm` graph files. The orchestrator already ran
this for Paris; reproduce it as follows (Île-de-France foot profile, MLD pipeline):

```bash
# 1. Download the OSM extract (~318MB) — pinned date so reruns are reproducible:
mkdir -p data/osrm
curl -fSL -o data/osrm/ile-de-france.osm.pbf \
  https://download.geofabrik.de/europe/france/ile-de-france-latest.osm.pbf   # extract date used: 2026-06-03

# 2. One-time prep (extract → partition → customize) with the foot profile:
docker run --rm -v "${PWD}/data/osrm:/data" osrm/osrm-backend osrm-extract   -p /opt/foot.lua /data/ile-de-france.osm.pbf
docker run --rm -v "${PWD}/data/osrm:/data" osrm/osrm-backend osrm-partition  /data/ile-de-france.osrm
docker run --rm -v "${PWD}/data/osrm:/data" osrm/osrm-backend osrm-customize  /data/ile-de-france.osrm

# 3. Start the server + build the Paris matrix:
make osrm-up
make matrix-build paris
```

The `data/osrm/` graph files and `data/paris/distance_matrix.sqlite` are large
build artifacts — generated, not committed. The matrix is already covered by the
`*.sqlite` rule in `.gitignore`; the `data/osrm/` graph files (`.osm.pbf`,
`.osrm.*`) are not yet ignored, so add a `data/osrm/` rule before committing.

### `make osrm-up` reports "did not become healthy" (HTTP 403 on localhost)

Symptom: `make osrm-up` reports the server "did not become healthy" even though
`docker logs ondoway-osrm` shows `running and waiting for requests`.

Cause: the corporate proxy intercepts the hostname `localhost` and returns
HTTP 403, but passes the literal loopback IP `127.0.0.1`. A `curl http://localhost:5000`
healthcheck therefore 403s while the container is perfectly healthy.

Fix: always probe `127.0.0.1`, never `localhost` (the make targets already do),
and set:

```bash
export NO_PROXY=localhost,127.0.0.1
```

The Python distance client (`src/tour/distance.py`) builds its httpx client with
`trust_env=False`, so it never consults the proxy regardless of env.

---

## Python & Dependencies

### "command not found: python3" or Python version too old

```bash
python3 --version       # Need 3.11+
brew install python@3.11
```

### "pip: command not found" or wrong pip

The Makefile uses `.venv/bin/pip`. If the venv doesn't exist:

```bash
make venv               # Creates .venv/
make install            # Installs deps into venv
```

### Import errors after pulling new code

Dependencies may have changed. Reinstall:

```bash
make install
```

### "No module named 'dotenv'" (or similar)

You're running system Python instead of the venv. Either:

```bash
source .venv/bin/activate   # Then run your command
# or
.venv/bin/python your_script.py
```

---

## API & Editor

### API returns 500 errors

Check the terminal where `make api` is running for the full traceback. Common causes:

- Neo4j not running: `make db-up`
- Schema not applied: `make setup`
- Wrong `.env` port: see "Neo4j container is running but app can't connect" above

### Editor shows "connection failed"

The API server isn't running or isn't reachable:

```bash
make api                # Start the API server
curl http://localhost:8000/api/v1/schema/nodes  # Test connectivity
```

### Editor shows empty canvas (no nodes)

The database has no data. Seed it:

```bash
make setup              # Apply schema + seed data + verify
```

### Port 8000 already in use

```bash
lsof -i :8000           # Find what's using the port
kill <PID>              # Kill it
make api                # Restart
```

---

## Tests

### Tests fail with "Neo4j not available"

Integration tests need a running Neo4j instance:

```bash
make db-up              # Start Neo4j
make test               # Run all tests
```

To run only unit tests (no Neo4j needed):

```bash
make test-unit
```

### Tests fail after schema changes

The database may have stale schema or data:

```bash
make clean-db           # Wipe all data
make setup              # Re-apply schema + seed
make test               # Run tests
```

---

## macOS Sandbox (Claude Code)

If running commands through Claude Code and getting network errors:

Check `~/.claude/apple/sandbox/claude-spawned-process.sb`. It should contain:

```
(allow network*)
```

If it has `(deny network*)`, change it to `(allow network*)` and restart Claude Code.

---

## Full Reset

If nothing else works, a complete reset:

```bash
make db-reset           # Stop Neo4j + wipe data volume
cp .env.example .env    # Reset environment
make all                # Full bootstrap from scratch
```
