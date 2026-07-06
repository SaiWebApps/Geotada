-include .env

# The JWT/magic-link signing-secret guard (src/api/auth/config.py) fails CLOSED
# on the production deploy — a missing secret there is a hard startup error, not
# a silent downgrade to a forgeable key. Local dev has no real secret, so opt
# into the deterministic dev placeholder for every make-invoked server (make
# api / api-test / workbench / flutter-ios, and the Playwright fixture, which
# inherits this via os.environ). Render never runs make, so prod stays fail-closed.
export ONDOWAY_ALLOW_INSECURE_AUTH_SECRETS := 1

# ════════════════════════════════════════════════════════════════════════════
#  Ondoway — GPS-triggered audio tour platform
#
#  New here? Run `make doctor`, then `make bootstrap`. `make help` lists
#  everything, grouped by section.
#
#  Fast path from a fresh `git clone`:
#      make doctor       # check prerequisites (uv/docker/flutter/xcode/...)
#      make bootstrap    # env → deps → databases → Valhalla → schema → Paris data
#      make workbench    # see the editorial workbench in your browser
#      make test         # THE bar (Python on local Docker + Flutter)
# ════════════════════════════════════════════════════════════════════════════

# Every target here is phony (no target produces a file of its own name).
# Keep this list in sync with the targets below — `make help` groups them,
# but .PHONY must enumerate them all.
.PHONY: \
	help doctor bootstrap all \
	sync sync-apple requirements env use-local use-cloud which-db \
	lint format lint-fix flutter-analyze \
	test test-unit test-file test-file-local test-local test-cloud \
	test-integration test-functional test-live test-auth test-onboarding \
	test-workbench test-golden golden-probe golden-diff tour-grade \
	tour-audio-gate tour-compose-gate test-all audit \
	db-up db-down db-status db-reset \
	db-test-up db-test-down db-test-reset \
	db-workbench-up db-workbench-down db-workbench-reset \
	valhalla-up valhalla-down valhalla-status valhalla-build-tiles \
	api api-test run workbench dashboard \
	flutter-web flutter-ios flutter-device flutter-pub-get flutter-clean \
	setup verify clean-db upload-paris backfill-provenance backfill-poi-role \
	backfill-name-key \
	wiki-fetch gen-within-edges tour-build measure-planned-audio measure-governor \
	flutter-ipa testflight render-status \
	setup-audio aura-resume-proof flutter-test flutter-test-diag clean

# ════════════════════════════════════════════════════════════════════════════
#  QUICKSTART   —   doctor · bootstrap · all · help
# ════════════════════════════════════════════════════════════════════════════
##@ QUICKSTART

doctor: ## Check prerequisites (uv/docker/flutter/node/xcode/render) — pure diagnostic, changes nothing
	@bash scripts/doctor.sh

bootstrap: ## Fresh clone → working LOCAL dev env (idempotent): env→deps→dbs→valhalla→schema→Paris data
	@echo "── [1/8] Pointing .env at LOCAL Neo4j (bootstrap NEVER touches cloud) ──"
	@$(MAKE) --no-print-directory use-local
	@echo "── [2/8] Installing Python deps (public PyPI) ──"
	@$(MAKE) --no-print-directory sync
	@echo "── [3/8] Resolving Flutter deps ──"
	@$(MAKE) --no-print-directory flutter-pub-get
	@echo "── [4/8] Starting dev Neo4j (7687) ──"
	@$(MAKE) --no-print-directory db-up
	@echo "── [5/8] Starting test Neo4j (7688) ──"
	@$(MAKE) --no-print-directory db-test-up
	@echo "── [6/8] Starting Valhalla routing engine ──"
	@$(MAKE) --no-print-directory valhalla-up
	@echo "── [7/8] Applying schema + seed (make setup) ──"
	@$(MAKE) --no-print-directory setup
	@echo "── [8/8] Loading the full Paris dataset into the LOCAL dev graph (7687) ──"
	@$(MAKE) --no-print-directory upload-paris
	@echo ""
	@echo "✓ You're ready — try:  make workbench   |   make test   |   make flutter-ios"

all: env db-up db-test-up setup test ## Full bootstrap-then-test: env → db → setup → test
	@echo ""
	@echo "✓ All done. Run 'make dashboard' for read-only view, 'make api' for CRUD editor."

# flutter-pub-get is a bootstrap dependency; it lives in RUN's Flutter block below
# but is declared PHONY above and defined once (see FLUTTER section).

help: ## Show all targets, grouped by section
	@awk 'BEGIN {FS = ":.*?## "} \
		/^##@ / { printf "\n\033[1m%s\033[0m\n", substr($$0, 5); next } \
		/^[a-zA-Z_][a-zA-Z0-9_-]+:.*?## / { printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2 }' \
		$(MAKEFILE_LIST)
	@echo ""

# ════════════════════════════════════════════════════════════════════════════
#  SETUP & DEPS   —   sync · requirements · env · db-selection
# ════════════════════════════════════════════════════════════════════════════
##@ SETUP & DEPS

sync: ## Install Python deps from public PyPI (default — works on any machine)
	uv sync --extra test --extra dev --extra aws
	@echo "✓ Dependencies installed (public PyPI)."

sync-apple: ## Install deps from Apple's internal PyPI mirror — ONLY on Apple VPN when public PyPI is blocked
	@curl -sI --max-time 5 https://pypi.apple.com/simple/ >/dev/null 2>&1 || \
		{ echo "ERROR: pypi.apple.com unreachable — are you on the Apple VPN? Use 'make sync' for public PyPI." >&2; exit 1; }
	@cp uv.lock /tmp/ondoway-uv.lock.public
	@UV_DEFAULT_INDEX=https://pypi.apple.com/simple uv sync --extra test --extra dev --extra aws; ec=$$?; \
		cp /tmp/ondoway-uv.lock.public uv.lock; rm -f /tmp/ondoway-uv.lock.public; \
		if [ $$ec -ne 0 ]; then echo "sync-apple failed; uv.lock restored to public." >&2; exit $$ec; fi; \
		echo "✓ Deps installed from Apple mirror. uv.lock kept public (apple refs now: $$(grep -c pypi.apple.com uv.lock))."

requirements: ## Regenerate requirements.txt (what the Dockerfile pip-installs) from uv.lock. MUST use --no-emit-project: the project self-line ('.') breaks the Docker build (pyproject isn't copied at the pip step) with "Directory '.' is not installable". Run after any dependency change, then commit requirements.txt.
	uv export --no-dev --no-editable --no-emit-project -o requirements.txt
	@grep -q "pypi.apple.com" requirements.txt && { echo "✗ requirements.txt has apple-index refs — re-run off the Apple mirror"; exit 1; } || echo "✓ requirements.txt regenerated (public PyPI, no project self-ref)."

env: ## Create .env from template (won't overwrite)
	@test -f .env || (cp .env.example .env && echo "✓ .env created from template.") || echo "• .env already exists."

use-local: ## Switch to local Neo4j (Docker)
	@cp .env.local .env && echo "✓ Switched to LOCAL Neo4j (bolt://localhost:7687)"

use-cloud: ## Switch to Neo4j Aura (cloud)
	@cp .env.cloud .env
	@echo ""
	@echo "############################################################"
	@echo "##  ⚠  .env NOW TARGETS PRODUCTION NEO4J AURA (CLOUD)  ⚠  ##"
	@echo "############################################################"
	@echo "##  Until you run 'make use-local', these commands hit    ##"
	@echo "##  the LIVE production database:                         ##"
	@echo "##    • make clean-db     → WIPES production               ##"
	@echo "##    • make setup        → seeds/overwrites production     ##"
	@echo "##    • make upload-paris → overwrites live beat fields     ##"
	@echo "##    • pytest / make test → destructive fixtures on prod   ##"
	@echo "##  (CLI guards refuse the first three unless the target   ##"
	@echo "##   is localhost / --allow-cloud is passed — but do NOT   ##"
	@echo "##   rely on that. Switch back with 'make use-local' ASAP.)##"
	@echo "############################################################"
	@echo ""

which-db: ## Show which Neo4j instance is active
	@grep '^NEO4J_URI=' .env | sed 's/NEO4J_URI=/  /'

# ════════════════════════════════════════════════════════════════════════════
#  CODE QUALITY   —   lint · format · flutter-analyze
# ════════════════════════════════════════════════════════════════════════════
##@ CODE QUALITY

lint: ## Run ruff linter
	uv run ruff check src/ tests/

format: ## Auto-format with ruff
	uv run ruff format src/ tests/
	uv run ruff check --fix src/ tests/

lint-fix: ## Auto-fix fixable lint errors only (ruff check --fix; no reformatting)
	uv run ruff check --fix src/ tests/

flutter-analyze: ## Run Dart static analysis on Flutter code
	cd mobile && NO_PROXY=pub.dev,*.pub.dev no_proxy=pub.dev,*.pub.dev flutter analyze

# ════════════════════════════════════════════════════════════════════════════
#  TEST   —   the bar (test) · targeted suites · gates · goldens · grade · test-all
# ════════════════════════════════════════════════════════════════════════════
##@ TEST

test: test-local flutter-test ## THE bar before any commit (Python on local Docker 7688 + Flutter). Aura is NEVER wiped; `make test-cloud` is a separate read-only smoke.

test-all: ## Run EVERY suite in sensible order (stops on first failure) — the bar + normally-excluded + live gates
	@echo "════════ [1] THE BAR — test-local (Python 7688) + flutter-test ════════"
	@$(MAKE) --no-print-directory test
	@echo "════════ [2] INTEGRATION — test-integration (needs dev/test Neo4j) ════════"
	@$(MAKE) --no-print-directory test-integration
	@echo "════════ [3] GOLDEN — test-golden (dev graph 7687; aspirational RED targets) ════════"
	@$(MAKE) --no-print-directory test-golden
	@echo "════════ [4] GRADE — tour-grade (needs Valhalla up for real routing) ════════"
	@$(MAKE) --no-print-directory tour-grade
	@echo "════════ [5] WORKBENCH UI — test-workbench (Playwright; needs node/npx + :8001 free) ════════"
	@$(MAKE) --no-print-directory test-workbench
	@echo "════════ [6] LIVE AUDIO GATE — tour-audio-gate (needs OPENAI_API_KEY + dev graph) ════════"
	@$(MAKE) --no-print-directory tour-audio-gate
	@echo "════════ [7] LIVE FUNCTIONAL — test-functional (needs OPENAI_API_KEY + network) ════════"
	@$(MAKE) --no-print-directory test-functional
	@echo ""
	@echo "✓ test-all: every suite passed."

audit: ## Deterministic health gate: lint + the bar + workbench UI. For the AGGRESSIVE bug-hunt loop (find→verify→fix→repeat until dry) invoke the 'proactive-audit' workflow (.claude/workflows/proactive-audit.js) via Claude Code.
	@$(MAKE) --no-print-directory lint
	@$(MAKE) --no-print-directory test
	@$(MAKE) --no-print-directory test-workbench
	@echo ""
	@echo "✓ audit gate green. Proactive bug-hunting: run the 'proactive-audit' workflow"
	@echo "  (loops red-team find → adversarial verify → fix + regression test until 2 dry rounds)."

test-unit: ## Run unit tests only (no Neo4j needed) — for quick iteration, NOT the bar
	uv run pytest tests/test_definitions.py tests/test_api_models.py tests/test_api_edge_models.py tests/test_audio_provider.py tests/test_audio_storage.py tests/test_audio_pipeline.py tests/test_audio_eval.py tests/test_connection.py tests/test_audio_api.py tests/test_audio_models.py tests/test_trip_adapter.py tests/test_trip_lens_resolution.py tests/test_trip_models.py tests/test_feedback.py -v

test-file: ## Run ONE pure (no-Neo4j) test file for atomic-step iteration: make test-file FILE=tests/test_x.py. NOT the bar.
	@find tests src -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	uv run pytest $(FILE) -v

test-file-local: db-up db-test-up ## Run ONE Neo4j-backed test file against local test Neo4j (7688) for atomic iteration: make test-file-local FILE=tests/test_x.py. NOT the bar.
	@cp .env.test.example .env.test && echo "  → Testing $(FILE) against LOCAL Neo4j (test instance, port 7688)"
	@find tests src -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	NO_PROXY=api.resend.com,resend.com,www.googleapis.com,googleapis.com no_proxy=api.resend.com,resend.com,www.googleapis.com,googleapis.com uv run pytest $(FILE) -v

test-local: db-up db-test-up ## Run tests against local Neo4j (Docker)
	@cp .env.test.example .env.test && echo "  → Testing against LOCAL Neo4j (test instance, port 7688)"
	@find tests src -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	NO_PROXY=api.resend.com,resend.com,www.googleapis.com,googleapis.com no_proxy=api.resend.com,resend.com,www.googleapis.com,googleapis.com uv run pytest tests/ -v

test-cloud: ## Read-only connectivity smoke against Aura (counts only). NEVER wipes — Aura is the single persistent store; the destructive suite runs only on local Docker (test-local).
	@echo "  → Read-only smoke against Aura (no writes, no wipe)"
	set -a && . .env.cloud && set +a && uv run python -c "from src.connection import create_driver, get_database; d=create_driver(); s=d.session(database=get_database()); n=s.run('MATCH (n) RETURN count(n) AS c').single()['c']; labels=sorted(r['label'] for r in s.run('CALL db.labels() YIELD label RETURN label')); print(f'Aura reachable - {n} nodes; labels: {labels}'); s.close(); d.close()"

test-integration: ## Run integration tests (needs Neo4j)
	uv run pytest tests/test_constraints.py tests/test_seed.py tests/test_traversals.py -v

test-functional: ## Run functional tests (needs OPENAI_API_KEY + network access)
	uv run pytest tests/test_audio_functional.py -v -s

test-live: ## Run live external-service tests (needs real creds, e.g. RESEND_API_KEY) — NOT in the default bar
	uv run pytest -m live -v

test-auth: ## Run auth tests only (Python)
	uv run pytest tests/test_auth_*.py -v

test-onboarding: ## Run onboarding tests only
	@cp .env.test.example .env.test
	@find tests src -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	uv run pytest tests/test_onboarding_api.py -v --tb=long

test-workbench: db-up db-workbench-up ## Real-browser Playwright UI suite for the workbench (review.html). Excluded from `make test` via the pyproject --ignore; this target clears addopts to run it. Auto-starts the API on :8001 against the DEDICATED workbench Neo4j (7689) — never the shared 7688, which concurrent `make test` runs full-wipe per-module. Concurrent test-workbench runs are unsupported (:8001 must be free; the suite fails fast if not).
	@cp .env.test.example .env.test
	@find tests src -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	NO_PROXY=api.resend.com,resend.com,www.googleapis.com,googleapis.com no_proxy=api.resend.com,resend.com,www.googleapis.com,googleapis.com uv run pytest tests/test_workbench_ui.py -o addopts= -v --tb=short

test-golden: db-up ## Run the golden tour-quality gate against the live dev graph (port 7687). Excluded from `make test`; the fixtures are the human-ideal TARGET to reach as the engine gains walk-by/spine features — do NOT re-baseline them to current output.
	uv run pytest -m golden -v

golden-probe: db-up valhalla-up ## Print ONLY the golden perturbation-probe hit counts (Île/PdV). Run before AND after a selection/emission change: unchanged counts = the change didn't perturb which beats seat; a moved count is a REAL signal (the goldens are aspirational RED targets, never a green/red flip). Requires Valhalla — routed legs reshape the route, so a haversine fallback moves the counts (Île 16->21) and gives a FALSE signal; this target guarantees product-parity routing so the numbers are stable.
	@uv run pytest -m golden -q 2>&1 | grep -oE "(Île|PdV) golden overlap [0-9.]+% .* Hit [0-9]+/[0-9]+" \
		|| echo "no hit counts — is the dev graph (7687) up? try: make db-up"

golden-diff: db-up ## Per-POI/beat diagnostic diff vs a golden fixture (live dev graph 7687). Usage: make golden-diff FIXTURE=pdv_round_trip_60min (or ile_oneway_90min). Exit 1 = overlap below 0.90 (expected until the golden gap closes). Routing state changes the route: run `make valhalla-up` first for product-parity legs (haversine fallback reshapes the PdV route; see GOLDEN-GAP-DIAGNOSTIC.md).
	@test -n "$(FIXTURE)" || { echo "Usage: make golden-diff FIXTURE=pdv_round_trip_60min | ile_oneway_90min"; exit 2; }
	uv run python scripts/tour_golden_diff.py $(FIXTURE)

tour-grade: db-up valhalla-up ## M8 GRADE regression gate: score each golden tour against the rubric on the live dev graph (port 7687). Excluded from `make test`. Requires Valhalla — without real routing the engine falls back to haversine (straight lines), which cross water and trip the never-swim-the-Seine audit with a FALSE red.
	uv run pytest -m grade -v

tour-audio-gate: db-up ## Live "audio says the story" gate (Step 1.5c): voice a real Paris tour's stitched per-stop narration (OpenAI TTS) + Whisper-eval each vs its narration → WER < 0.15. Live (OpenAI + dev graph 7687); excluded from `make test`. Needs OPENAI_API_KEY in .env.
	uv run pytest tests/test_audio_says_story.py -m live -v -s

tour-compose-gate: db-up ## Live COMPOSE gate (Phase 4 Step 4.5): real Paris tour → fire-once Anthropic compose behind the M7 gate, verified by the REAL Haiku faithfulness checker. Live (Anthropic + dev graph 7687); excluded from `make test`. Needs ANTHROPIC_API_KEY in .env.
	NO_PROXY=api.anthropic.com,anthropic.com no_proxy=api.anthropic.com,anthropic.com uv run pytest tests/test_tour_compose_live.py -m live -v -s

# ════════════════════════════════════════════════════════════════════════════
#  DATABASE   —   dev (7687) · test (7688) · workbench (7689)
# ════════════════════════════════════════════════════════════════════════════
##@ DATABASE

db-up: ## Start dev Neo4j in Docker (production data)
	@if docker ps --format '{{.Names}}' | grep -q '^ondoway-neo4j$$'; then \
		echo "✓ Neo4j already running at bolt://localhost:7687"; \
	else \
		docker compose up -d neo4j; \
		echo "Waiting for Neo4j to be healthy..."; \
		docker compose exec neo4j bash -c 'until cypher-shell -u neo4j -p ondoway_dev_2026 "RETURN 1" 2>/dev/null; do sleep 2; done' 2>/dev/null; \
		echo "✓ Neo4j is ready at bolt://localhost:7687"; \
		echo "  Browser: http://localhost:7474"; \
	fi

db-down: ## Stop dev Neo4j (data preserved)
	docker compose stop neo4j

db-status: ## Check Neo4j container status
	@docker compose ps

db-reset: ## Stop dev Neo4j and wipe all data (DESTRUCTIVE)
	docker compose down -v --remove-orphans
	@echo "✓ Dev Neo4j stopped and data wiped."

db-test-up: ## Start test Neo4j in Docker (disposable data)
	@if docker ps --format '{{.Names}}' | grep -q '^ondoway-neo4j-test$$'; then \
		echo "✓ Test Neo4j already running at bolt://localhost:7688"; \
	else \
		docker compose up -d neo4j-test; \
		echo "Waiting for test Neo4j to be healthy..."; \
		docker compose exec neo4j-test bash -c 'until cypher-shell -u neo4j -p ondoway_test_2026 "RETURN 1" 2>/dev/null; do sleep 2; done' 2>/dev/null; \
		echo "✓ Test Neo4j is ready at bolt://localhost:7688"; \
		echo "  Browser: http://localhost:7475"; \
	fi

db-test-down: ## Stop test Neo4j (data preserved)
	docker compose stop neo4j-test

db-test-reset: ## Stop test Neo4j and wipe test data
	docker compose stop neo4j-test
	docker compose rm -f neo4j-test
	docker volume rm -f ondoway_neo4j_test_data
	@echo "✓ Test Neo4j stopped and data wiped."

db-workbench-up: ## Start workbench Neo4j (port 7689) — dedicated to test-workbench/api-test, never touched by the pytest suite's 7688 wipes
	@if docker ps --format '{{.Names}}' | grep -q '^ondoway-neo4j-workbench$$'; then \
		echo "✓ Workbench Neo4j already running at bolt://localhost:7689"; \
	else \
		docker compose up -d neo4j-workbench; \
		echo "Waiting for workbench Neo4j to be healthy..."; \
		docker compose exec neo4j-workbench bash -c 'until cypher-shell -u neo4j -p ondoway_workbench_2026 "RETURN 1" 2>/dev/null; do sleep 2; done' 2>/dev/null; \
		echo "✓ Workbench Neo4j is ready at bolt://localhost:7689"; \
		echo "  Browser: http://localhost:7476"; \
	fi

db-workbench-down: ## Stop workbench Neo4j (data preserved)
	docker compose stop neo4j-workbench

db-workbench-reset: ## Stop workbench Neo4j and wipe its data
	docker compose stop neo4j-workbench
	docker compose rm -f neo4j-workbench
	docker volume rm -f ondoway_neo4j_workbench_data
	@echo "✓ Workbench Neo4j stopped and data wiped."

# ════════════════════════════════════════════════════════════════════════════
#  ROUTING / VALHALLA   —   the walking-route engine (port 8002)
# ════════════════════════════════════════════════════════════════════════════
##@ ROUTING / VALHALLA

# Valhalla's tiles live in a BIND MOUNT relative to the compose file, so its
# compose operations must always run against the MAIN checkout: run from a
# .claude/worktrees/* worktree, a plain `docker compose up -d valhalla`
# re-anchors the mount to the worktree's EMPTY valhalla/custom_files and
# recreates the container tile-less (observed 2026-07-02: exited(1), grade
# gate red). `git rev-parse --git-common-dir` resolves the main checkout
# from anywhere.
VALHALLA_ROOT = $(shell dirname "$$(git rev-parse --git-common-dir)")

valhalla-up: ## Start the Valhalla routing engine (always anchored to the main checkout's tiles; first start builds tiles from valhalla/custom_files)
	docker compose -f "$(VALHALLA_ROOT)/docker-compose.yml" --project-directory "$(VALHALLA_ROOT)" up -d valhalla
	@echo "Valhalla starting on http://localhost:8002 — first start with a new"
	@echo "PBF builds tiles (minutes). Check readiness: make valhalla-status"

valhalla-down: ## Stop Valhalla (tiles preserved in valhalla/custom_files)
	docker compose -f "$(VALHALLA_ROOT)/docker-compose.yml" --project-directory "$(VALHALLA_ROOT)" stop valhalla

valhalla-status: ## Host-side health check against Valhalla's /status endpoint
	@curl -fs --max-time 3 http://localhost:8002/status && echo " ← Valhalla OK" \
		|| echo "Valhalla not responding on :8002 (engine falls back to haversine)"

valhalla-build-tiles: ## Download the Île-de-France OSM extract (~500MB) for tile building on next start (into the MAIN checkout's mount)
	mkdir -p "$(VALHALLA_ROOT)/valhalla/custom_files"
	curl -L -o "$(VALHALLA_ROOT)/valhalla/custom_files/ile-de-france-latest.osm.pbf" \
		https://download.geofabrik.de/europe/france/ile-de-france-latest.osm.pbf
	@echo "✓ PBF downloaded. Run 'make valhalla-up' (restart if already running) to build tiles."

# ════════════════════════════════════════════════════════════════════════════
#  RUN   —   the API, the workbench, the dashboard, the mobile app
# ════════════════════════════════════════════════════════════════════════════
##@ RUN

api: ## Start the FastAPI graph API (port 8000)
	NO_PROXY=api.resend.com,resend.com,www.googleapis.com,googleapis.com,api.anthropic.com,anthropic.com,api.github.com,github.com no_proxy=api.resend.com,resend.com,www.googleapis.com,googleapis.com,api.anthropic.com,anthropic.com,api.github.com,github.com uv run uvicorn src.api.app:app --host 127.0.0.1 --port 8000 --reload

api-test: db-workbench-up ## Start API against the WORKBENCH database (port 8001 → Neo4j 7689; coexists with `make api` on 8000; workbench: review.html?apiPort=8001). `make test-workbench` needs :8001 free — stop this first.
	set -a && . .env.test && set +a && NEO4J_URI=bolt://localhost:7689 NEO4J_PASSWORD=ondoway_workbench_2026 NEO4J_DATABASE=neo4j NO_PROXY=api.resend.com,resend.com,www.googleapis.com,googleapis.com,api.anthropic.com,anthropic.com,api.github.com,github.com no_proxy=api.resend.com,resend.com,www.googleapis.com,googleapis.com,api.anthropic.com,anthropic.com,api.github.com,github.com uv run uvicorn src.api.app:app --host 127.0.0.1 --port 8001 --reload

run: api ## Alias for `make api` — start the graph API for local development (port 8000)

workbench: db-up ## RUN the editorial workbench: start the API on the dev graph (8000), wait for health, open review.html
	@bash scripts/workbench.sh

dashboard: ## Start the web dashboard (port 8080)
	uv run python -m src.server

# ── Flutter mobile app ──────────────────────────────────────────────────────

flutter-web: ## Run Flutter web app on port 3000 (Brave)
	cd mobile && flutter run -d chrome --web-port=3000

# iOS simulator UDID resolution (works on any machine, no hardcoded UDID in the
# recipe body). Precedence:
#   1. An explicit `make flutter-ios SIM=<udid>` on the command line always wins.
#   2. Else the currently-Booted simulator, if one is running.
#   3. Else the default UDID below.
# List UDIDs with:  xcrun simctl list devices
SIM ?= 46F0E608-943E-48F4-9EDB-8925855D0069
SIM_BOOTED = $(shell xcrun simctl list devices booted 2>/dev/null | grep -oE '[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}' | head -1)
# Explicit command-line SIM= wins; otherwise prefer a booted sim; otherwise SIM default.
SIM_TARGET = $(if $(filter command line,$(origin SIM)),$(SIM),$(if $(SIM_BOOTED),$(SIM_BOOTED),$(SIM)))

flutter-ios: db-up ## Run Flutter app on iOS Simulator (boots sim + starts API automatically). Uses booted sim, else SIM=<udid>.
	@echo "  → iOS simulator: $(SIM_TARGET)"
	@xcrun simctl boot "$(SIM_TARGET)" 2>/dev/null || true
	@open -a Simulator 2>/dev/null || true
	@echo "  → Starting API server in background (port 8000)..."
	@lsof -ti:8000 | xargs kill 2>/dev/null || true
	@NO_PROXY=api.resend.com,resend.com,www.googleapis.com,googleapis.com,api.anthropic.com,anthropic.com,api.github.com,github.com no_proxy=api.resend.com,resend.com,www.googleapis.com,googleapis.com,api.anthropic.com,anthropic.com,api.github.com,github.com uv run uvicorn src.api.app:app --host 127.0.0.1 --port 8000 &
	@sleep 2
	cd mobile && NO_PROXY=pub.dev,*.pub.dev no_proxy=pub.dev,*.pub.dev flutter run -d "$(SIM_TARGET)"

flutter-device: ## Run Flutter app on physical iOS device (points at production API)
	cd mobile && NO_PROXY=pub.dev,*.pub.dev no_proxy=pub.dev,*.pub.dev flutter run --dart-define=API_BASE_URL=https://ondoway.com/api/v1

flutter-pub-get: ## Resolve Flutter dependencies (pub get only)
	cd mobile && NO_PROXY=pub.dev,*.pub.dev no_proxy=pub.dev,*.pub.dev flutter pub get

flutter-clean: ## Clean Flutter build cache and re-resolve dependencies
	cd mobile && flutter clean
	cd mobile && NO_PROXY=pub.dev,*.pub.dev no_proxy=pub.dev,*.pub.dev flutter pub get

# ════════════════════════════════════════════════════════════════════════════
#  DATA & PIPELINE   —   schema · seed · Paris data · backfills · tour building
# ════════════════════════════════════════════════════════════════════════════
##@ DATA & PIPELINE

setup: ## Apply schema + seed data + verify (full pipeline)
	uv run python -m src.main

verify: ## Run verification only (no schema changes)
	uv run python -c "from src.main import verify_only; verify_only()"

clean-db: ## Wipe all nodes and relationships
	uv run python -c "from src.main import clean; clean()"

upload-paris: ## Upload full Paris dataset to active Neo4j instance
	uv run python -m scripts.upload_paris

backfill-provenance: ## Backfill ONLY source_passage/source_chunk_slug/key_claims onto existing beats (safe on live graphs)
	uv run python -m scripts.upload_paris --provenance-only

backfill-poi-role: ## Apply reviewed poi_role classifications to poi-raw.json. Dry-run by default; ARGS="--apply" to write; ARGS="--apply --neo4j" to also update the dev graph.
	uv run python scripts/backfill_poi_role.py $(ARGS)

backfill-name-key: ## Backfill name_key on POIs missing it (dedup key for defect #3). Dry-run by default; ARGS="--apply" to write; ARGS="--apply --allow-cloud" for a deliberate cloud run.
	uv run python scripts/backfill_name_key.py $(ARGS)

wiki-fetch: ## Pin a Wikipedia article's raw plain text for /beat-from-wikipedia. Usage: make wiki-fetch POI="Saint-Sulpice" [TITLE="Saint-Sulpice, Paris"] [CITY=paris]
	@python3 scripts/wiki_fetch.py --city "$(or $(CITY),paris)" --name "$(POI)"$(if $(TITLE), --title "$(TITLE)",)

gen-within-edges: ## Regenerate data/paris/within_edges.json (POI→Area staging) from areas.json + poi-raw.json
	uv run python scripts/generate_within_edges.py

tour-build: db-up ## Build one real audio tour from the live Paris graph and render it to markdown. ARGS="--start '48.8566,2.3522' --duration 60 [--lenses historic_arch,...] [--round-trip]".
	uv run python scripts/tour_build.py $(ARGS)

measure-planned-audio: db-up ## Per-POI planned voiced audio vs tier-dwell proxy (dwell/audio spec pre-measurement). ARGS='--pois "Pont Neuf,..." --duration-min 90'
	uv run python scripts/measure_planned_audio.py $(ARGS)

measure-governor: db-up ## Per-stop uncapped vs v3-capped emitted audio for a live tour (C9 governor before/after proof). ARGS="--start '48.8530,2.3499' --duration 60 --round-trip"
	uv run python scripts/measure_governor.py $(ARGS)

# ════════════════════════════════════════════════════════════════════════════
#  DEPLOY   —   iOS IPA · TestFlight · Render · requirements
# ════════════════════════════════════════════════════════════════════════════
##@ DEPLOY

flutter-ipa: ## Build IPA for TestFlight (points at production API)
	cd mobile && NO_PROXY=pub.dev,*.pub.dev,cdn.cocoapods.org,cocoapods.org,cdn.jsdelivr.net,jsdelivr.net no_proxy=pub.dev,*.pub.dev,cdn.cocoapods.org,cocoapods.org,cdn.jsdelivr.net,jsdelivr.net flutter build ipa --dart-define=API_BASE_URL=https://ondoway.com/api/v1

testflight: flutter-ipa ## Bump build number, build IPA, and upload to TestFlight
	@test -n "$(APP_STORE_API_KEY_ID)" || (echo "ERROR: APP_STORE_API_KEY_ID not set. Add it to .env" >&2; exit 1)
	@test -n "$(APP_STORE_ISSUER_ID)" || (echo "ERROR: APP_STORE_ISSUER_ID not set. Add it to .env" >&2; exit 1)
	@echo "==> Bumping build number..."
	cd mobile/ios && agvtool next-version -all
	@echo "==> Building IPA (via flutter-ipa dependency)... done."
	@echo "==> Uploading to App Store Connect..."
	NO_PROXY=contentdelivery.itunes.apple.com,itunesconnect.apple.com \
	no_proxy=contentdelivery.itunes.apple.com,itunesconnect.apple.com \
	xcrun altool --upload-app \
		--file mobile/build/ios/ipa/*.ipa \
		--type ios \
		--apiKey $(APP_STORE_API_KEY_ID) \
		--apiIssuer $(APP_STORE_ISSUER_ID)
	@echo "==> Upload complete. Check TestFlight in App Store Connect (~15 min for processing)."

render-status: ## Latest Render deploy status for ondoway-api. RUN AFTER EVERY PUSH: 'live' = green; a '*_failed' means dig in with `render logs -r srv-d7qnivjbc2fs73fr6tqg --type app --limit 60 -o text --confirm`. Needs `render login`.
	@render deploys list srv-d7qnivjbc2fs73fr6tqg -o json --confirm 2>/dev/null \
		| python3 -c "import json,sys; e=json.load(sys.stdin)[0]; d=e.get('deploy',e); c=d.get('commit') or {}; \
print('ondoway-api latest deploy:', d.get('status'), '|', d.get('id'), '|', (c.get('message') or '').splitlines()[0][:56])" \
		|| echo "render CLI not authed? try: render login"

# `requirements` regenerates requirements.txt (see SETUP & DEPS above); it is a
# deploy-time step (the Dockerfile pip-installs it) but the recipe lives once
# in SETUP & DEPS. Run: make requirements

# ════════════════════════════════════════════════════════════════════════════
#  DIAGNOSTICS   —   audio setup · Aura resume · golden probes · flutter test · clean
# ════════════════════════════════════════════════════════════════════════════
##@ DIAGNOSTICS

setup-audio: ## Check audio pipeline prerequisites (API keys, connectivity)
	uv run python scripts/check_audio_setup.py

aura-resume-proof: ## Human/verify-agent proof that Aura auto-resume works: print status → resume() if paused → poll paused→resuming→running (≤5min) → verified create_driver(). Needs live AURA_CLIENT_ID/SECRET + NEO4J_URI (or AURA_INSTANCE_ID); no-op exit 0 if creds unset. NOT for CI.
	uv run python scripts/aura_resume_proof.py

flutter-test: ## Run Flutter tests (headless Chrome). Early-exits on the verdict; retries ONLY on the intermittent flutter_tools finalize hang, never on a real failure. Logic: scripts/flutter_test.sh
	@bash scripts/flutter_test.sh

flutter-test-diag: ## Diagnostic: run flutter-test with timeout and process logging
	@echo "==> PRE-TEST: Chrome/Dart processes"
	@pgrep -lf "Chrome for Testing|dart|flutter" 2>/dev/null || echo "(none)"
	@echo "==> Running flutter test with 120s timeout..."
	cd mobile && NO_PROXY=pub.dev,*.pub.dev no_proxy=pub.dev,*.pub.dev CHROME_EXECUTABLE="$(HOME)/Library/Caches/ms-playwright/chromium-1200/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing" timeout 120 flutter test --platform chrome 2>&1; EXIT=$$?; echo "==> flutter test exited with code $$EXIT"; echo "==> POST-TEST: Chrome/Dart processes"; pgrep -lf "Chrome for Testing|dart|flutter" 2>/dev/null || echo "(none)"; pkill -f "Google Chrome for Testing" 2>/dev/null || true; exit $$EXIT

clean: ## Remove Python build junk (__pycache__/.pytest_cache/.ruff_cache) — safe, NEVER touches any database
	@find . -type d -name __pycache__ -not -path '*/.venv/*' -exec rm -rf {} + 2>/dev/null || true
	@rm -rf .pytest_cache .ruff_cache 2>/dev/null || true
	@echo "✓ Cleared Python caches (__pycache__/.pytest_cache/.ruff_cache). Databases untouched."
	@echo "  For Flutter build caches, run: make flutter-clean"
