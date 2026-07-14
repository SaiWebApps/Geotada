#!/usr/bin/env bash
# Run the editorial workbench: start the graph API on the DEV graph (port 8000),
# wait for /api/v1/healthz, then open frontend/review.html pointed at it.
#
# review.html reads ?apiPort= (default 8000) and builds
# http://localhost:<port>/api/v1 — so a plain file:// open works. We open it
# with ?apiPort=8000 explicitly for clarity.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT=8000
HEALTH="http://localhost:${PORT}/api/v1/healthz"
PAGE="file://${ROOT}/frontend/review.html?apiPort=${PORT}"

# Same NO_PROXY prefix as `make api` — hard-won fix, keep in sync.
NP="api.resend.com,resend.com,www.googleapis.com,googleapis.com,api.anthropic.com,anthropic.com,api.github.com,github.com"

echo "==> Workbench: starting graph API on the DEV graph (port ${PORT})..."

# If something already answers healthz on 8000, reuse it. Otherwise start one.
if curl -fs --max-time 2 "$HEALTH" >/dev/null 2>&1; then
  echo "    API already healthy on :${PORT} — reusing it."
  API_PID=""
else
  # Free the port in case a stale uvicorn is lingering (matches make flutter-ios).
  lsof -ti:${PORT} 2>/dev/null | xargs kill 2>/dev/null || true
  cd "$ROOT"
  # The auth signing-secret guard (src/api/auth/config.py) fails closed on an
  # empty/short secret. A direct `bash scripts/workbench.sh` (not via `make
  # workbench`, which exports this) has no real secret and no pytest, so opt
  # into the dev placeholder — a local workbench server is never production.
  # WORKBENCH_API_ENABLED=true: the graph-CRUD gate is now fail-closed (app.py),
  # so the workbench routers this page needs must be opted in explicitly.
  WORKBENCH_API_ENABLED=true NO_PROXY="$NP" no_proxy="$NP" ONDOWAY_ALLOW_INSECURE_AUTH_SECRETS=1 \
    uv run uvicorn src.api.app:app --host 127.0.0.1 --port ${PORT} >/tmp/ondoway-workbench-api.log 2>&1 &
  API_PID=$!
  echo "    API PID ${API_PID} (log: /tmp/ondoway-workbench-api.log)"
fi

echo "==> Waiting for ${HEALTH} ..."
ok=0
for i in $(seq 1 30); do
  if curl -fs --max-time 2 "$HEALTH" >/dev/null 2>&1; then ok=1; break; fi
  sleep 1
done

if [ "$ok" -ne 1 ]; then
  echo "ERROR: API did not become healthy on :${PORT} within 30s." >&2
  echo "       Check the log: /tmp/ondoway-workbench-api.log" >&2
  echo "       Common cause: dev Neo4j not up (make db-up) or port ${PORT} busy." >&2
  exit 1
fi
echo "    API healthy."

echo "==> Opening the workbench: ${PAGE}"
if command -v open >/dev/null 2>&1; then
  open "$PAGE"                       # macOS
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$PAGE"                   # Linux
else
  echo "    Open this URL manually: ${PAGE}"
fi

echo ""
echo "Workbench is live. The API is on http://localhost:${PORT} (dev graph 7687)."
if [ -n "$API_PID" ]; then
  echo "Stop the API when done:  kill ${API_PID}   (or: lsof -ti:${PORT} | xargs kill)"
fi
