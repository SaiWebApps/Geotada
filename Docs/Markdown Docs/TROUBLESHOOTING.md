# Troubleshooting

Common issues and fixes for the Travlr Neo4j development environment.

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
docker logs travlr-neo4j  # View Neo4j logs
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

The password in `.env` doesn't match `docker-compose.yml`. Both should use `travlr_dev_2026`:

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
