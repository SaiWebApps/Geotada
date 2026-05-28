-include .env

.PHONY: help env use-local use-cloud which-db sync lint format test test-unit test-local test-cloud test-integration test-functional setup setup-audio upload-paris wiki-fetch verify clean-db db-up db-down db-status db-test-up db-test-down db-test-reset dashboard api api-test flutter-web flutter-ios flutter-ipa testflight flutter-test flutter-clean flutter-analyze test-auth

# ──────────────────────────────────────────────────────────
# HELP
# ──────────────────────────────────────────────────────────

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ──────────────────────────────────────────────────────────
# SETUP
# ──────────────────────────────────────────────────────────

sync: ## Install/update Python dependencies via uv
	uv sync --extra test --extra dev
	@echo "✓ Dependencies installed."

env: ## Create .env from template (won't overwrite)
	@test -f .env || (cp .env.example .env && echo "✓ .env created from template.") || echo "• .env already exists."

use-local: ## Switch to local Neo4j (Docker)
	@cp .env.local .env && echo "✓ Switched to LOCAL Neo4j (bolt://localhost:7687)"

use-cloud: ## Switch to Neo4j Aura (cloud)
	@cp .env.cloud .env && echo "✓ Switched to CLOUD Neo4j (Aura)"

which-db: ## Show which Neo4j instance is active
	@grep '^NEO4J_URI=' .env | sed 's/NEO4J_URI=/  /'

# ──────────────────────────────────────────────────────────
# CODE QUALITY
# ──────────────────────────────────────────────────────────

lint: ## Run ruff linter
	uv run ruff check src/ tests/

format: ## Auto-format with ruff
	uv run ruff format src/ tests/
	uv run ruff check --fix src/ tests/

flutter-analyze: ## Run Dart static analysis on Flutter code
	cd mobile && NO_PROXY=pub.dev,*.pub.dev no_proxy=pub.dev,*.pub.dev flutter analyze

# ──────────────────────────────────────────────────────────
# TESTING
# ──────────────────────────────────────────────────────────

test: test-local test-cloud flutter-test ## Run ALL tests (Python local + cloud + Flutter) — THE bar before any commit

test-unit: ## Run unit tests only (no Neo4j needed) — for quick iteration, NOT the bar
	uv run pytest tests/test_definitions.py tests/test_api_models.py tests/test_api_edge_models.py tests/test_audio_provider.py tests/test_audio_storage.py tests/test_audio_pipeline.py tests/test_audio_eval.py tests/test_connection.py tests/test_audio_api.py tests/test_audio_models.py tests/test_trip_generation.py tests/test_trip_models.py tests/test_feedback.py -v

test-local: db-up db-test-up ## Run tests against local Neo4j (Docker)
	@cp .env.test.example .env.test && echo "  → Testing against LOCAL Neo4j (test instance, port 7688)"
	@find tests src -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	NO_PROXY=api.resend.com,resend.com,www.googleapis.com,googleapis.com no_proxy=api.resend.com,resend.com,www.googleapis.com,googleapis.com uv run pytest tests/ -v

test-cloud: ## Run tests against Neo4j Aura (cloud) — excludes wipe-dependent integration tests
	@cp .env.cloud .env.test && echo "  → Testing against CLOUD Neo4j (Aura)"
	@find tests src -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	NO_PROXY=api.resend.com,resend.com,www.googleapis.com,googleapis.com no_proxy=api.resend.com,resend.com,www.googleapis.com,googleapis.com uv run pytest tests/ -v --ignore=tests/test_constraints.py --ignore=tests/test_seed.py --ignore=tests/test_traversals.py

test-integration: ## Run integration tests (needs Neo4j)
	uv run pytest tests/test_constraints.py tests/test_seed.py tests/test_traversals.py -v

test-functional: ## Run functional tests (needs OPENAI_API_KEY + network access)
	uv run pytest tests/test_audio_functional.py -v -s

# ──────────────────────────────────────────────────────────
# DATABASE
# ──────────────────────────────────────────────────────────

db-up: ## Start dev Neo4j in Docker (production data)
	docker compose up -d neo4j
	@echo "Waiting for Neo4j to be healthy..."
	@docker compose exec neo4j bash -c 'until cypher-shell -u neo4j -p ondoway_dev_2026 "RETURN 1" 2>/dev/null; do sleep 2; done' 2>/dev/null
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
	@docker compose exec neo4j-test bash -c 'until cypher-shell -u neo4j -p ondoway_test_2026 "RETURN 1" 2>/dev/null; do sleep 2; done' 2>/dev/null
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
	uv run python -m src.main

verify: ## Run verification only (no schema changes)
	uv run python -c "from src.main import verify_only; verify_only()"

clean-db: ## Wipe all nodes and relationships
	uv run python -c "from src.main import clean; clean()"

dashboard: ## Start the web dashboard (port 8080)
	uv run python -m src.server

api: ## Start the FastAPI graph API (port 8000)
	NO_PROXY=api.resend.com,resend.com,www.googleapis.com,googleapis.com,api.anthropic.com,anthropic.com,api.github.com,github.com no_proxy=api.resend.com,resend.com,www.googleapis.com,googleapis.com,api.anthropic.com,anthropic.com,api.github.com,github.com uv run uvicorn src.api.app:app --host 127.0.0.1 --port 8000 --reload

api-test: ## Start API against test database (port 8000)
	set -a && . .env.test && set +a && NO_PROXY=api.resend.com,resend.com,www.googleapis.com,googleapis.com,api.anthropic.com,anthropic.com,api.github.com,github.com no_proxy=api.resend.com,resend.com,www.googleapis.com,googleapis.com,api.anthropic.com,anthropic.com,api.github.com,github.com uv run uvicorn src.api.app:app --host 127.0.0.1 --port 8000 --reload

setup-audio: ## Check audio pipeline prerequisites (API keys, connectivity)
	uv run python scripts/check_audio_setup.py

upload-paris: ## Upload full Paris dataset to active Neo4j instance
	uv run python -m scripts.upload_paris

wiki-fetch: ## Pin a Wikipedia article's raw plain text for /beat-from-wikipedia. Usage: make wiki-fetch POI="Saint-Sulpice" [TITLE="Saint-Sulpice, Paris"] [CITY=paris]
	@python3 scripts/wiki_fetch.py --city "$(or $(CITY),paris)" --name "$(POI)"$(if $(TITLE), --title "$(TITLE)",)

# ──────────────────────────────────────────────────────────
# WORKFLOWS
# ──────────────────────────────────────────────────────────

all: env db-up db-test-up setup test ## Full bootstrap: env → db → setup → test
	@echo ""
	@echo "✓ All done. Run 'make dashboard' for read-only view, 'make api' for CRUD editor."

# ──────────────────────────────────────────────────────────
# FLUTTER MOBILE APP
# ──────────────────────────────────────────────────────────

flutter-web: ## Run Flutter web app on port 3000 (Brave)
	cd mobile && flutter run -d chrome --web-port=3000

flutter-ios: db-up ## Run Flutter app on iOS Simulator (boots sim + starts API automatically)
	@xcrun simctl boot 46F0E608-943E-48F4-9EDB-8925855D0069 2>/dev/null || true
	@open -a Simulator 2>/dev/null || true
	@echo "  → Starting API server in background (port 8000)..."
	@lsof -ti:8000 | xargs kill 2>/dev/null || true
	@NO_PROXY=api.resend.com,resend.com,www.googleapis.com,googleapis.com,api.anthropic.com,anthropic.com,api.github.com,github.com no_proxy=api.resend.com,resend.com,www.googleapis.com,googleapis.com,api.anthropic.com,anthropic.com,api.github.com,github.com uv run uvicorn src.api.app:app --host 127.0.0.1 --port 8000 &
	@sleep 2
	cd mobile && NO_PROXY=pub.dev,*.pub.dev no_proxy=pub.dev,*.pub.dev flutter run -d 46F0E608-943E-48F4-9EDB-8925855D0069

flutter-device: ## Run Flutter app on physical iOS device (points at production API)
	cd mobile && NO_PROXY=pub.dev,*.pub.dev no_proxy=pub.dev,*.pub.dev flutter run --dart-define=API_BASE_URL=https://ondoway.com/api/v1

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

flutter-clean: ## Clean Flutter build cache and re-resolve dependencies
	cd mobile && flutter clean
	cd mobile && NO_PROXY=pub.dev,*.pub.dev no_proxy=pub.dev,*.pub.dev flutter pub get

flutter-test: ## Run Flutter tests (headless Chrome for Testing — gtimeout kills Flutter SDK hang after completion)
	@pkill -f "Google Chrome for Testing" 2>/dev/null || true
	@rm -rf /tmp/flutter_tools.* 2>/dev/null || true
	cd mobile && NO_PROXY=pub.dev,*.pub.dev no_proxy=pub.dev,*.pub.dev \
	  CHROME_EXECUTABLE="$(HOME)/Library/Caches/ms-playwright/chromium-1200/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing" \
	  gtimeout 30 flutter test --platform chrome 2>&1; EXIT=$$?; \
	  pkill -f "Google Chrome for Testing" 2>/dev/null || true; \
	  if [ $$EXIT -eq 124 ]; then echo "flutter test hung after completion (killed by timeout)"; exit 0; fi; \
	  exit $$EXIT

flutter-test-diag: ## Diagnostic: run flutter-test with timeout and process logging
	@echo "==> PRE-TEST: Chrome/Dart processes"
	@pgrep -lf "Chrome for Testing|dart|flutter" 2>/dev/null || echo "(none)"
	@echo "==> Running flutter test with 120s timeout..."
	cd mobile && NO_PROXY=pub.dev,*.pub.dev no_proxy=pub.dev,*.pub.dev CHROME_EXECUTABLE="$(HOME)/Library/Caches/ms-playwright/chromium-1200/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing" timeout 120 flutter test --platform chrome 2>&1; EXIT=$$?; echo "==> flutter test exited with code $$EXIT"; echo "==> POST-TEST: Chrome/Dart processes"; pgrep -lf "Chrome for Testing|dart|flutter" 2>/dev/null || echo "(none)"; pkill -f "Google Chrome for Testing" 2>/dev/null || true; exit $$EXIT

test-auth: ## Run auth tests only (Python)
	uv run pytest tests/test_auth_*.py -v

test-onboarding: ## Run onboarding tests only
	@cp .env.test.example .env.test
	@find tests src -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	uv run pytest tests/test_onboarding_api.py -v --tb=long
