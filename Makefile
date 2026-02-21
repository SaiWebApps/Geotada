.PHONY: help install lint format test test-unit test-integration setup verify clean db-up db-down db-status dashboard

PYTHON := python3
PIP := pip3

# ──────────────────────────────────────────────────────────
# HELP
# ──────────────────────────────────────────────────────────

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ──────────────────────────────────────────────────────────
# SETUP
# ──────────────────────────────────────────────────────────

install: ## Install Python dependencies
	$(PIP) install -r requirements.txt --break-system-packages
	@echo "✓ Dependencies installed."

env: ## Create .env from template (won't overwrite)
	@test -f .env || (cp .env.example .env && echo "✓ .env created from template.") || echo "• .env already exists."

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

test: ## Run all tests (unit + integration)
	$(PYTHON) -m pytest tests/ -v

test-unit: ## Run unit tests only (no Neo4j needed)
	$(PYTHON) -m pytest tests/test_definitions.py -v

test-integration: ## Run integration tests (needs Neo4j)
	$(PYTHON) -m pytest tests/test_constraints.py tests/test_seed.py tests/test_traversals.py -v

# ──────────────────────────────────────────────────────────
# DATABASE
# ──────────────────────────────────────────────────────────

db-up: ## Start Neo4j in Docker
	docker compose up -d
	@echo "Waiting for Neo4j to be healthy..."
	@docker compose exec neo4j bash -c 'until cypher-shell -u neo4j -p travlr_dev_2026 "RETURN 1" 2>/dev/null; do sleep 2; done' 2>/dev/null
	@echo "✓ Neo4j is ready at bolt://localhost:7687"
	@echo "  Browser: http://localhost:7474"

db-down: ## Stop Neo4j
	docker compose down

db-status: ## Check Neo4j container status
	@docker compose ps

db-reset: ## Stop Neo4j and wipe all data
	docker compose down -v
	@echo "✓ Neo4j stopped and data wiped."

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

# ──────────────────────────────────────────────────────────
# WORKFLOWS
# ──────────────────────────────────────────────────────────

all: install db-up setup test ## Full bootstrap: install → db → setup → test
	@echo ""
	@echo "✓ All done. Run 'make dashboard' to see the graph."
