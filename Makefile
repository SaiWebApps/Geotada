.PHONY: help venv env use-local use-cloud which-db install lint format test test-unit test-integration test-functional test-api setup setup-audio verify clean db-up db-down db-status db-test-up db-test-down db-test-reset dashboard api api-test

PYTHON := .venv/bin/python
PIP    := .venv/bin/pip

# ──────────────────────────────────────────────────────────
# HELP
# ──────────────────────────────────────────────────────────

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ──────────────────────────────────────────────────────────
# SETUP
# ──────────────────────────────────────────────────────────

install: venv env ## Install Python dependencies
	$(PIP) install -r requirements.txt
	@echo "✓ Dependencies installed."

env: ## Create .env from template (won't overwrite)
	@test -f .env || (cp .env.example .env && echo "✓ .env created from template.") || echo "• .env already exists."

use-local: ## Switch to local Neo4j (Docker)
	@cp .env.local .env && echo "✓ Switched to LOCAL Neo4j (bolt://localhost:7687)"

use-cloud: ## Switch to Neo4j Aura (cloud)
	@cp .env.cloud .env && echo "✓ Switched to CLOUD Neo4j (Aura)"

which-db: ## Show which Neo4j instance is active
	@grep '^NEO4J_URI=' .env | sed 's/NEO4J_URI=/  /'

venv: ## Create Python virtual environment
	@if [ ! -d .venv ]; then python3 -m venv .venv && echo "✓ Virtual environment created."; fi

# ──────────────────────────────────────────────────────────
# CODE QUALITY
# ──────────────────────────────────────────────────────────

lint: ## Run ruff linter
	$(PYTHON) -m ruff check src/ tests/

format: ## Auto-format with ruff
	$(PYTHON) -m ruff format src/ tests/
	$(PYTHON) -m ruff check --fix src/ tests/

# ──────────────────────────────────────────────────────────
# TESTING
# ──────────────────────────────────────────────────────────

test: ## Run all tests (unit + integration + functional)
	$(PYTHON) -m pytest tests/ -v

test-unit: ## Run unit tests only (no Neo4j needed)
	$(PYTHON) -m pytest tests/test_definitions.py -v

test-integration: ## Run integration tests (needs Neo4j)
	$(PYTHON) -m pytest tests/test_constraints.py tests/test_seed.py tests/test_traversals.py -v

test-functional: ## Run functional tests (needs OPENAI_API_KEY + network access)
	$(PYTHON) -m pytest tests/test_audio_functional.py -v -s

# ──────────────────────────────────────────────────────────
# DATABASE
# ──────────────────────────────────────────────────────────

db-up: ## Start dev Neo4j in Docker (production data)
	docker compose up -d neo4j
	@echo "Waiting for Neo4j to be healthy..."
	@docker compose exec neo4j bash -c 'until cypher-shell -u neo4j -p travlr_dev_2026 "RETURN 1" 2>/dev/null; do sleep 2; done' 2>/dev/null
	@echo "✓ Neo4j is ready at bolt://localhost:7687"
	@echo "  Browser: http://localhost:7474"

db-down: ## Stop dev Neo4j (data preserved)
	docker compose stop neo4j

db-status: ## Check Neo4j container status
	@docker compose ps

db-reset: ## Stop dev Neo4j and wipe all data (DESTRUCTIVE)
	docker compose down -v --remove-orphans
	@echo "✓ Dev Neo4j stopped and data wiped."

db-test-up: ## Start test Neo4j in Docker (disposable data)
	docker compose up -d neo4j-test
	@echo "Waiting for test Neo4j to be healthy..."
	@docker compose exec neo4j-test bash -c 'until cypher-shell -u neo4j -p travlr_test_2026 "RETURN 1" 2>/dev/null; do sleep 2; done' 2>/dev/null
	@echo "✓ Test Neo4j is ready at bolt://localhost:7688"
	@echo "  Browser: http://localhost:7475"

db-test-down: ## Stop test Neo4j (data preserved)
	docker compose stop neo4j-test

db-test-reset: ## Stop test Neo4j and wipe test data
	docker compose stop neo4j-test
	docker compose rm -f neo4j-test
	docker volume rm -f ondoway_neo4j_test_data
	@echo "✓ Test Neo4j stopped and data wiped."

# ──────────────────────────────────────────────────────────
# APPLICATION
# ──────────────────────────────────────────────────────────

setup: ## Apply schema + seed data + verify (full pipeline)
	$(PYTHON) -m src.main

verify: ## Run verification only (no schema changes)
	$(PYTHON) -c "from src.main import verify_only; verify_only()"

clean-db: ## Wipe all nodes and relationships
	$(PYTHON) -c "from src.main import clean; clean()"

dashboard: ## Start the web dashboard (port 8080)
	$(PYTHON) -m src.server

api: ## Start the FastAPI graph API (port 8000)
	$(PYTHON) -m uvicorn src.api.app:app --host 127.0.0.1 --port 8000 --reload

api-test: ## Start API against test database (port 8000)
	set -a && . .env.test && set +a && $(PYTHON) -m uvicorn src.api.app:app --host 127.0.0.1 --port 8000 --reload

setup-audio: ## Check audio pipeline prerequisites (API keys, connectivity)
	$(PYTHON) scripts/check_audio_setup.py

upload-paris: ## Upload full Paris dataset to active Neo4j instance
	$(PYTHON) -m scripts.upload_paris

# ──────────────────────────────────────────────────────────
# WORKFLOWS
# ──────────────────────────────────────────────────────────

all: install db-up db-test-up setup test ## Full bootstrap: install → db → setup → test
	@echo ""
	@echo "✓ All done. Run 'make dashboard' for read-only view, 'make api' for CRUD editor."
