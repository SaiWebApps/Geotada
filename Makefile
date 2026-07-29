export ONDOWAY_ALLOW_INSECURE_AUTH_SECRETS := 1
SHELL := /bin/bash

ENV_EXEC := uv run python scripts/dev_env.py exec
LOCAL_EXEC := $(ENV_EXEC) --profile local --
TEST_EXEC := $(ENV_EXEC) --profile test --
WORKBENCH_EXEC := $(ENV_EXEC) --profile workbench --
RENDER_LOCAL_EXEC := $(ENV_EXEC) --profile local --render --
RENDER_TEST_EXEC := $(ENV_EXEC) --profile test --render --
CLOUD_EXEC := $(ENV_EXEC) --profile cloud --render --
NO_PROXY_LIST := api.resend.com,resend.com,www.googleapis.com,googleapis.com,api.anthropic.com,anthropic.com,api.github.com,github.com
LIVE_TEST_FILES := \
	tests/test_audio_functional.py \
	tests/test_audio_says_story.py \
	tests/test_magic_link_live.py \
	tests/test_tour_compose_live.py
GOLDEN_TEST_FILES := \
	tests/test_narration_coherence.py \
	tests/test_tour_golden_ile.py \
	tests/test_tour_golden_pdv.py
GRADE_TEST_FILES := tests/test_tour_audit.py tests/test_tour_grade.py
INVARIANT_TEST_FILES := tests/test_tour_invariants_live.py

DB ?= dev
TARGET ?= local

.PHONY: \
	help doctor bootstrap render-auth-setup render-auth-status config-status \
	sync sync-apple requirements lint format flutter-analyze \
	test audit test-file test-live test-workbench golden-probe golden-diff \
	score-saved-tours score-gold-text score-human-tours \
	tour-batch-plan tour-batch-live tour-batch-review-plan tour-batch-review-live \
	db-up db-down db-status db-reset db-parity \
	valhalla-up valhalla-down valhalla-status valhalla-build-tiles \
	api workbench dashboard \
	flutter-web flutter-ios flutter-device flutter-pub-get flutter-clean \
	survey-area-candidates fix-area-radii backfill-provenance backfill-poi-role \
	backfill-name-key wiki-fetch gen-within-edges validate-beats deploy prune-orphans \
	fetch-boundary geocode-pois tour-build measure-planned-audio measure-governor \
	onboard-city flutter-ipa testflight render-watch render-status setup-audio \
	aura-resume-proof flutter-test clean \
	_ensure-dev-db _ensure-test-db _ensure-workbench-db _ensure-dev-data \
	_test-python _test-golden _test-grade _test-invariants _test-cloud

# ════════════════════════════════════════════════════════════════════════════
#  QUICKSTART
# ════════════════════════════════════════════════════════════════════════════
##@ QUICKSTART

help: ## Show the supported public targets.
	@awk 'BEGIN {FS = ":.*?## "} \
		/^##@ / { printf "\n\033[1m%s\033[0m\n", substr($$0, 5); next } \
		/^[a-zA-Z][a-zA-Z0-9_-]+:.*?## / { printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2 }' \
		$(MAKEFILE_LIST)
	@echo ""

doctor: ## Check prerequisites without changing anything.
	@bash scripts/doctor.sh

bootstrap: ## Provision a complete local development environment from a fresh clone.
	@$(MAKE) --no-print-directory sync
	@$(MAKE) --no-print-directory flutter-pub-get
	@$(MAKE) --no-print-directory db-up DB=test
	@$(MAKE) --no-print-directory db-up DB=workbench
	@$(MAKE) --no-print-directory valhalla-up
	@$(MAKE) --no-print-directory _ensure-dev-data
	@echo "✓ Local development environment is ready."

# ════════════════════════════════════════════════════════════════════════════
#  CONFIGURATION
# ════════════════════════════════════════════════════════════════════════════
##@ CONFIGURATION

render-auth-setup: ## Store or replace the Render API key in macOS Keychain.
	@uv run python scripts/dev_env.py auth-setup

render-auth-status: ## Validate the Keychain Render API key against ondoway-api.
	@uv run python scripts/dev_env.py auth-status

config-status: ## Fetch Render fresh and validate the final local/test/workbench boundaries.
	@$(RENDER_LOCAL_EXEC) python -c 'import os; assert os.environ["NEO4J_URI"] == "bolt://localhost:7687"; assert os.environ.get("RESEND_API_KEY"); print("local: localhost:7687 + fresh Render credentials")'
	@$(RENDER_TEST_EXEC) python -c 'import os; assert os.environ["NEO4J_URI"] == "bolt://localhost:7688"; assert os.environ.get("RESEND_API_KEY"); print("test: localhost:7688 + fresh Render credentials")'
	@$(ENV_EXEC) --profile workbench --render -- python -c 'import os; assert os.environ["NEO4J_URI"] == "bolt://localhost:7689"; assert os.environ.get("RESEND_API_KEY"); print("workbench: localhost:7689 + fresh Render credentials")'

sync: ## Install Python dependencies from public PyPI.
	uv sync --extra test --extra dev --extra aws

sync-apple: ## Install dependencies from Apple's mirror while preserving the public lockfile.
	@curl -sI --max-time 5 https://pypi.apple.com/simple/ >/dev/null 2>&1 || \
		{ echo "ERROR: pypi.apple.com unreachable; use make sync." >&2; exit 1; }
	@cp uv.lock /tmp/ondoway-uv-lock-public
	@UV_DEFAULT_INDEX=https://pypi.apple.com/simple uv sync --extra test --extra dev --extra aws; ec=$$?; \
		cp /tmp/ondoway-uv-lock-public uv.lock; rm -f /tmp/ondoway-uv-lock-public; exit $$ec

requirements: ## Regenerate requirements.txt from uv.lock.
	uv export --no-dev --no-editable --no-emit-project -o requirements.txt
	@! grep -q "pypi.apple.com" requirements.txt

# ════════════════════════════════════════════════════════════════════════════
#  CODE QUALITY
# ════════════════════════════════════════════════════════════════════════════
##@ CODE QUALITY

lint: ## Run the Python linter.
	uv run ruff check src/ tests/ scripts/dev_env.py scripts/ensure_dev_data.py \
		scripts/db_parity.py scripts/check_audio_setup.py \
		scripts/tour_batch_candidate.py scripts/score_saved_tours.py \
		scripts/score_gold_text.py scripts/human_reference_tours.py

format: ## Format Python and apply safe lint fixes.
	uv run ruff format src/ tests/ scripts/dev_env.py scripts/ensure_dev_data.py \
		scripts/db_parity.py scripts/check_audio_setup.py scripts/human_reference_tours.py \
		scripts/tour_batch_candidate.py
	uv run ruff check --fix-only src/ tests/ scripts/dev_env.py scripts/ensure_dev_data.py \
		scripts/db_parity.py scripts/check_audio_setup.py scripts/human_reference_tours.py \
		scripts/tour_batch_candidate.py

flutter-analyze: ## Run Dart static analysis.
	cd mobile && NO_PROXY=pub.dev,*.pub.dev no_proxy=pub.dev,*.pub.dev flutter analyze

# ════════════════════════════════════════════════════════════════════════════
#  TEST
# ════════════════════════════════════════════════════════════════════════════
##@ TEST

test: ## THE definitive suite: Python, Flutter, browser, tour, live-provider, and cloud parity.
	@$(MAKE) --no-print-directory _test-python
	@$(MAKE) --no-print-directory flutter-test
	@$(MAKE) --no-print-directory test-workbench
	@$(MAKE) --no-print-directory _test-golden
	@$(MAKE) --no-print-directory _test-grade
	@$(MAKE) --no-print-directory _test-invariants
	@$(MAKE) --no-print-directory test-live
	@$(MAKE) --no-print-directory _test-cloud
	@echo "✓ Every definitive test shard passed."

audit: ## Run lint and then the definitive test suite.
	@$(MAKE) --no-print-directory lint
	@$(MAKE) --no-print-directory test

test-file: ## Run one test file safely. Usage: make test-file FILE=tests/test_x.py [LIVE=1].
	@test -n "$(FILE)" || { echo "ERROR: FILE is required." >&2; exit 2; }
	@if [ "$(LIVE)" = "1" ]; then \
		$(MAKE) --no-print-directory test-live FILE="$(FILE)"; \
	else \
		$(MAKE) --no-print-directory _ensure-test-db; \
		$(MAKE) --no-print-directory _ensure-dev-data; \
		$(MAKE) --no-print-directory valhalla-up; \
		find tests src -name __pycache__ -exec rm -rf {} + 2>/dev/null || true; \
		$(TEST_EXEC) uv run pytest "$(FILE)" -o addopts= -v; \
	fi

test-live: ## Run every live-provider test with a fresh full Render environment.
	@$(MAKE) --no-print-directory render-auth-status
	@$(MAKE) --no-print-directory _ensure-test-db
	@$(MAKE) --no-print-directory _ensure-dev-data
	@$(MAKE) --no-print-directory valhalla-up
	@find tests src -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@$(RENDER_TEST_EXEC) env \
		ONDOWAY_LIVE_TESTS=1 ONDOWAY_ENABLE_PAID_LLM_CALLS=1 \
		NO_PROXY="$(NO_PROXY_LIST)" no_proxy="$(NO_PROXY_LIST)" \
		uv run pytest $(or $(FILE),$(LIVE_TEST_FILES)) -o addopts= -m live -v $(PYTEST_ARGS)

test-workbench: ## Run the Playwright workbench suite against isolated Neo4j 7689.
	@$(MAKE) --no-print-directory _ensure-test-db
	@$(MAKE) --no-print-directory _ensure-workbench-db
	@find tests src -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@$(TEST_EXEC) env NO_PROXY="$(NO_PROXY_LIST)" no_proxy="$(NO_PROXY_LIST)" \
		uv run pytest tests/test_workbench_ui.py -o addopts= -v --tb=short

golden-probe: ## Print golden overlap counts using provisioned dev data and Valhalla.
	@$(MAKE) --no-print-directory _ensure-test-db
	@$(MAKE) --no-print-directory _ensure-dev-data
	@$(MAKE) --no-print-directory valhalla-up
	@set -o pipefail; $(TEST_EXEC) uv run pytest $(GOLDEN_TEST_FILES) \
		-o addopts= -m golden -q 2>&1 | \
		grep -oE "(Île|PdV) golden overlap [0-9.]+% .* Hit [0-9]+/[0-9]+"

score-saved-tours: ## Score every saved tour artifact against the current rubric. $0, no DB, no containers.
	@$(LOCAL_EXEC) uv run python scripts/score_saved_tours.py $(SCORE_ARGS)

score-gold-text: ## Score the owner's own gold text against the rubric — calibration. $0, no DB.
	@$(LOCAL_EXEC) uv run python scripts/score_gold_text.py --compare

score-human-tours: ## Score the two human-authored reference tours against the rubric. $0, no DB.
	@$(LOCAL_EXEC) uv run python -m scripts.human_reference_tours

golden-diff: ## Diff one golden fixture. Usage: make golden-diff FIXTURE=pdv_round_trip_60min.
	@test -n "$(FIXTURE)" || { echo "ERROR: FIXTURE is required." >&2; exit 2; }
	@$(MAKE) --no-print-directory _ensure-dev-data
	@$(MAKE) --no-print-directory valhalla-up
	@$(LOCAL_EXEC) uv run python scripts/tour_golden_diff.py "$(FIXTURE)"

_test-python: _ensure-test-db _ensure-dev-data valhalla-up
	@find tests src -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@$(TEST_EXEC) env NO_PROXY="$(NO_PROXY_LIST)" no_proxy="$(NO_PROXY_LIST)" \
		uv run pytest tests/ -v $(PYTEST_ARGS)

_test-golden: _ensure-test-db _ensure-dev-data valhalla-up
	@$(TEST_EXEC) uv run pytest $(GOLDEN_TEST_FILES) -o addopts= -m golden -v $(PYTEST_ARGS)

_test-grade: _ensure-test-db _ensure-dev-data valhalla-up
	@$(TEST_EXEC) uv run pytest $(GRADE_TEST_FILES) -o addopts= -m grade -v $(PYTEST_ARGS)

_test-invariants: _ensure-test-db _ensure-dev-data valhalla-up
	@$(TEST_EXEC) uv run pytest $(INVARIANT_TEST_FILES) -o addopts= -m invariants -v $(PYTEST_ARGS)

_test-cloud:
	@$(MAKE) --no-print-directory render-auth-status
	@echo "→ Aura parity: read-only session; pytest and reset targets never receive Aura."
	@$(CLOUD_EXEC) uv run python -m scripts.aura_ensure_running
	@$(CLOUD_EXEC) env ONDOWAY_CLOUD_READ_ONLY=1 uv run python -m scripts.db_parity

# ════════════════════════════════════════════════════════════════════════════
#  PAID TOUR OPERATIONS
# ════════════════════════════════════════════════════════════════════════════
##@ PAID TOUR OPERATIONS

tour-batch-plan: ## Build the sealed Premium plan without constructing a paid client.
	@$(MAKE) --no-print-directory _ensure-dev-data
	@$(MAKE) --no-print-directory valhalla-up
	@$(LOCAL_EXEC) uv run python -m scripts.tour_batch_candidate $(if $(CASE),--case "$(CASE)",)

tour-batch-live: ## Execute an approved Premium plan with fresh Render credentials.
	@test -n "$(PLAN_SHA256)" || { echo "ERROR: PLAN_SHA256 is required." >&2; exit 2; }
	@$(MAKE) --no-print-directory _ensure-dev-data
	@$(MAKE) --no-print-directory valhalla-up
	@$(RENDER_LOCAL_EXEC) env ONDOWAY_ENABLE_PAID_LLM_CALLS=1 ONDOWAY_TOUR_BATCH_APPROVED=1 \
		uv run python -m scripts.tour_batch_candidate --live \
		--approve-plan-sha256 "$(PLAN_SHA256)" --max-workers "$(or $(MAX_WORKERS),4)"

tour-batch-review-plan: ## Rebuild a sealed semantic-review plan without provider calls.
	@$(MAKE) --no-print-directory _ensure-dev-data
	@$(MAKE) --no-print-directory valhalla-up
	@$(LOCAL_EXEC) uv run python -m scripts.tour_batch_review \
		$(if $(BATCH_ROOT),--batch-root "$(BATCH_ROOT)",) \
		$(if $(REVIEW_ROOT),--review-root "$(REVIEW_ROOT)",)

tour-batch-review-live: ## Execute an approved semantic-review plan with fresh Render credentials.
	@test -n "$(REVIEW_PLAN_SHA256)" || { echo "ERROR: REVIEW_PLAN_SHA256 is required." >&2; exit 2; }
	@$(MAKE) --no-print-directory _ensure-dev-data
	@$(MAKE) --no-print-directory valhalla-up
	@$(RENDER_LOCAL_EXEC) env ONDOWAY_ENABLE_PAID_LLM_CALLS=1 ONDOWAY_TOUR_BATCH_REVIEW_APPROVED=1 \
		uv run python -m scripts.tour_batch_review --live \
		--approve-review-plan-sha256 "$(REVIEW_PLAN_SHA256)" \
		--max-workers "$(or $(MAX_WORKERS),4)" \
		$(if $(BATCH_ROOT),--batch-root "$(BATCH_ROOT)",) \
		$(if $(REVIEW_ROOT),--review-root "$(REVIEW_ROOT)",) \
		$(if $(CALIBRATION_REUSE_ROOT),--calibration-reuse-root "$(CALIBRATION_REUSE_ROOT)",)

# ════════════════════════════════════════════════════════════════════════════
#  DATABASE
# ════════════════════════════════════════════════════════════════════════════
##@ DATABASE

db-up: ## Start one local Neo4j service. Usage: make db-up DB=dev|test|workbench.
	@case "$(DB)" in \
		dev) service=neo4j; container=ondoway-neo4j; port=7687; password=ondoway_dev_2026 ;; \
		test) service=neo4j-test; container=ondoway-neo4j-test; port=7688; password=ondoway_test_2026 ;; \
		workbench) service=neo4j-workbench; container=ondoway-neo4j-workbench; port=7689; password=ondoway_workbench_2026 ;; \
		*) echo "ERROR: DB must be dev, test, or workbench; never cloud." >&2; exit 2 ;; \
	esac; \
	if docker ps --format '{{.Names}}' | grep -q "^$${container}$$"; then \
		echo "✓ $${service} already running at bolt://localhost:$${port}"; \
	else \
		docker compose up -d "$${service}"; \
		echo "Waiting for $${service}..."; \
		docker compose exec "$${service}" bash -c \
			"until cypher-shell -u neo4j -p '$${password}' 'RETURN 1' >/dev/null 2>&1; do sleep 2; done"; \
		echo "✓ $${service} ready at bolt://localhost:$${port}"; \
	fi

db-down: ## Stop one local Neo4j service without deleting data. Usage: make db-down DB=...
	@case "$(DB)" in dev) service=neo4j ;; test) service=neo4j-test ;; \
		workbench) service=neo4j-workbench ;; \
		*) echo "ERROR: DB must be dev, test, or workbench; never cloud." >&2; exit 2 ;; esac; \
	docker compose stop "$${service}"

db-status: ## Show all local Neo4j service states.
	@docker compose ps neo4j neo4j-test neo4j-workbench

db-reset: ## Delete exactly one local Neo4j volume. Usage: make db-reset DB=dev|test|workbench.
	@case "$(DB)" in \
		dev) service=neo4j; volume=ondoway_neo4j_data ;; \
		test) service=neo4j-test; volume=ondoway_neo4j_test_data ;; \
		workbench) service=neo4j-workbench; volume=ondoway_neo4j_workbench_data ;; \
		*) echo "ERROR: DB must be dev, test, or workbench; Aura is unreachable here." >&2; exit 2 ;; \
	esac; \
	docker compose stop "$${service}"; \
	docker compose rm -f "$${service}"; \
	docker volume rm -f "$${volume}"; \
	echo "✓ Deleted only local volume $${volume}."

db-parity: ## Compare committed data with local dev or read-only Aura. Usage: make db-parity TARGET=local|cloud.
	@case "$(TARGET)" in \
		local) $(MAKE) --no-print-directory _ensure-dev-db; \
			$(LOCAL_EXEC) uv run python -m scripts.db_parity $(CITY) ;; \
		cloud) $(CLOUD_EXEC) env ONDOWAY_CLOUD_READ_ONLY=1 \
			uv run python -m scripts.db_parity $(CITY) ;; \
		*) echo "ERROR: TARGET must be local or cloud." >&2; exit 2 ;; \
	esac

_ensure-dev-db:
	@$(MAKE) --no-print-directory db-up DB=dev

_ensure-test-db:
	@$(MAKE) --no-print-directory db-up DB=test

_ensure-workbench-db:
	@$(MAKE) --no-print-directory db-up DB=workbench

_ensure-dev-data: _ensure-dev-db
	@$(LOCAL_EXEC) uv run python scripts/ensure_dev_data.py

# ════════════════════════════════════════════════════════════════════════════
#  ROUTING
# ════════════════════════════════════════════════════════════════════════════
##@ ROUTING

VALHALLA_ROOT = $(shell dirname "$$(git rev-parse --git-common-dir)")

valhalla-up: ## Start Valhalla and wait for a healthy routing endpoint.
	docker compose -f "$(VALHALLA_ROOT)/docker-compose.yml" \
		--project-directory "$(VALHALLA_ROOT)" up -d valhalla
	@for i in $$(seq 1 300); do \
		curl -fs --max-time 3 http://localhost:8002/status >/dev/null 2>&1 && \
			{ echo "✓ Valhalla ready."; exit 0; }; \
		sleep 2; \
	done; echo "ERROR: Valhalla did not become ready within 10 minutes." >&2; exit 1

valhalla-down: ## Stop Valhalla without deleting tiles.
	docker compose -f "$(VALHALLA_ROOT)/docker-compose.yml" \
		--project-directory "$(VALHALLA_ROOT)" stop valhalla

valhalla-status: ## Check the Valhalla health endpoint.
	@curl -fs --max-time 3 http://localhost:8002/status >/dev/null && echo "✓ Valhalla healthy."

valhalla-build-tiles: ## Download Paris and New York OSM extracts for tile building.
	mkdir -p "$(VALHALLA_ROOT)/valhalla/custom_files"
	curl -L -o "$(VALHALLA_ROOT)/valhalla/custom_files/ile-de-france-latest.osm.pbf" \
		https://download.geofabrik.de/europe/france/ile-de-france-latest.osm.pbf
	curl -L -o "$(VALHALLA_ROOT)/valhalla/custom_files/new-york.osm.pbf" \
		https://download.bbbike.org/osm/bbbike/NewYork/NewYork.osm.pbf

# ════════════════════════════════════════════════════════════════════════════
#  RUN
# ════════════════════════════════════════════════════════════════════════════
##@ RUN

api: ## Start the local API with dev data and fresh Render provider credentials.
	@$(MAKE) --no-print-directory _ensure-dev-data
	@$(RENDER_LOCAL_EXEC) env NO_PROXY="$(NO_PROXY_LIST)" no_proxy="$(NO_PROXY_LIST)" \
		uv run uvicorn src.api.app:app --host 127.0.0.1 --port 8000 --reload

workbench: ## Start the local editorial workbench with dev data and fresh Render credentials.
	@$(MAKE) --no-print-directory _ensure-dev-data
	@$(MAKE) --no-print-directory valhalla-up
	@$(RENDER_LOCAL_EXEC) bash scripts/workbench.sh

dashboard: ## Start the local dashboard with the validated dev profile.
	@$(MAKE) --no-print-directory _ensure-dev-data
	@$(LOCAL_EXEC) uv run python -m src.server

flutter-web: ## Run the Flutter web app on port 3000.
	cd mobile && flutter run -d chrome --web-port=3000

SIM ?= 46F0E608-943E-48F4-9EDB-8925855D0069
SIM_BOOTED = $(shell xcrun simctl list devices booted 2>/dev/null | grep -oE '[0-9A-Fa-f-]{36}' | head -1)
SIM_TARGET = $(if $(filter command line,$(origin SIM)),$(SIM),$(if $(SIM_BOOTED),$(SIM_BOOTED),$(SIM)))

flutter-ios: ## Run the Flutter app in an iOS simulator with a local API.
	@$(MAKE) --no-print-directory _ensure-dev-data
	@xcrun simctl boot "$(SIM_TARGET)" 2>/dev/null || true
	@open -a Simulator 2>/dev/null || true
	@PORT_KILL_PIDS=$$(lsof -tiTCP:8000 -sTCP:LISTEN 2>/dev/null); \
	if [ -n "$$PORT_KILL_PIDS" ]; then \
		for pid in $$PORT_KILL_PIDS; do \
			cmd=$$(ps -p $$pid -o comm= 2>/dev/null | tail -1); \
			echo "    Freeing :8000 — killing stale listener PID $$pid ($${cmd:-unknown})"; \
		done; \
		kill $$PORT_KILL_PIDS 2>/dev/null || true; \
	fi
	@$(RENDER_LOCAL_EXEC) env NO_PROXY="$(NO_PROXY_LIST)" no_proxy="$(NO_PROXY_LIST)" \
		uv run uvicorn src.api.app:app --host 127.0.0.1 --port 8000 &
	@sleep 2
	cd mobile && flutter run -d "$(SIM_TARGET)"

flutter-device: ## Run the Flutter app on a physical device against production.
	cd mobile && flutter run --dart-define=API_BASE_URL=https://ondoway.com/api/v1

flutter-pub-get: ## Resolve Flutter dependencies.
	cd mobile && NO_PROXY=pub.dev,*.pub.dev no_proxy=pub.dev,*.pub.dev flutter pub get

flutter-clean: ## Clean Flutter build artifacts and resolve dependencies.
	cd mobile && flutter clean
	@$(MAKE) --no-print-directory flutter-pub-get

# ════════════════════════════════════════════════════════════════════════════
#  DATA AND PIPELINE
# ════════════════════════════════════════════════════════════════════════════
##@ DATA AND PIPELINE

survey-area-candidates: ## Survey undersized physical-extent POIs. Usage: make survey-area-candidates CITY=x.
	@$(LOCAL_EXEC) uv run python scripts/survey_area_candidates.py --city "$(CITY)" $(ARGS)

fix-area-radii: ## Correct reviewed trigger radii locally. ARGS="--apply" writes.
	@$(LOCAL_EXEC) uv run python scripts/fix_area_trigger_radii.py --city "$(CITY)" $(ARGS)

backfill-provenance: ## Backfill beat provenance on the local dev graph.
	@$(MAKE) --no-print-directory _ensure-dev-db
	@$(LOCAL_EXEC) uv run python -m scripts.upload_paris --provenance-only

backfill-poi-role: ## Apply reviewed POI roles. ARGS="--apply --neo4j" writes locally.
	@$(LOCAL_EXEC) uv run python scripts/backfill_poi_role.py $(ARGS)

backfill-name-key: ## Backfill missing POI name keys on the local dev graph.
	@$(MAKE) --no-print-directory _ensure-dev-db
	@$(LOCAL_EXEC) uv run python scripts/backfill_name_key.py $(ARGS)

wiki-fetch: ## Pin Wikipedia text. Usage: make wiki-fetch POI=x [TITLE=x] [CITY=paris].
	@$(LOCAL_EXEC) python3 scripts/wiki_fetch.py --city "$(or $(CITY),paris)" \
		--name "$(POI)"$(if $(TITLE), --title "$(TITLE)",)

gen-within-edges: ## Regenerate one city's within_edges.json.
	@$(LOCAL_EXEC) uv run python scripts/generate_within_edges.py --slug "$(or $(CITY),paris)"

validate-beats: ## Validate one city's committed beats before upload.
	@$(LOCAL_EXEC) uv run python scripts/validate_beats.py data/$(or $(CITY),paris)/beats.json

deploy: ## Deploy one city. Local by default; cloud requires TARGET=cloud CONFIRM_CLOUD_WRITE=1.
	@test -n "$(CITY)" || { echo "ERROR: CITY is required." >&2; exit 2; }
	@case "$(TARGET)" in \
		local) $(MAKE) --no-print-directory _ensure-dev-db; \
			$(LOCAL_EXEC) uv run python -m scripts.deploy --slug "$(CITY)" ;; \
		cloud) test "$(CONFIRM_CLOUD_WRITE)" = "1" || \
			{ echo "ERROR: add CONFIRM_CLOUD_WRITE=1 for Aura." >&2; exit 2; }; \
			$(CLOUD_EXEC) uv run python -m scripts.aura_ensure_running; \
			$(CLOUD_EXEC) uv run python -m scripts.deploy --slug "$(CITY)" --allow-cloud ;; \
		*) echo "ERROR: TARGET must be local or cloud." >&2; exit 2 ;; \
	esac

prune-orphans: ## Find or delete orphaned records. Cloud requires explicit TARGET and confirmation.
	@test -n "$(CITY)" || { echo "ERROR: CITY is required." >&2; exit 2; }
	@case "$(TARGET)" in \
		local) $(MAKE) --no-print-directory _ensure-dev-db; \
			$(LOCAL_EXEC) uv run python -m scripts.prune_orphan_pois --slug "$(CITY)" \
				$(if $(APPLY),--apply,) ;; \
		cloud) test "$(CONFIRM_CLOUD_WRITE)" = "1" || \
			{ echo "ERROR: add CONFIRM_CLOUD_WRITE=1 for Aura." >&2; exit 2; }; \
			$(CLOUD_EXEC) uv run python -m scripts.prune_orphan_pois --slug "$(CITY)" \
				--allow-cloud $(if $(APPLY),--apply,) ;; \
		*) echo "ERROR: TARGET must be local or cloud." >&2; exit 2 ;; \
	esac

fetch-boundary: ## Fetch an OSM boundary polygon.
	@$(LOCAL_EXEC) uv run python -m scripts.fetch_city_boundary --slug "$(SLUG)" \
		--relation "$(RELATION)"$(if $(FORCE), --force,)

geocode-pois: ## Geocode POIs through Nominatim.
	@$(LOCAL_EXEC) uv run python -m scripts.geocode_pois --slug "$(SLUG)"$(if $(ALL), --all,)

tour-build: ## Build one local tour and render it to Markdown.
	@$(MAKE) --no-print-directory _ensure-dev-data
	@$(MAKE) --no-print-directory valhalla-up
	@$(LOCAL_EXEC) uv run python scripts/tour_build.py $(ARGS)

measure-planned-audio: ## Measure voiced audio against tier dwell.
	@$(MAKE) --no-print-directory _ensure-dev-data
	@$(LOCAL_EXEC) uv run python scripts/measure_planned_audio.py $(ARGS)

measure-governor: ## Compare uncapped and governed emitted audio.
	@$(MAKE) --no-print-directory _ensure-dev-data
	@$(LOCAL_EXEC) uv run python scripts/measure_governor.py $(ARGS)

onboard-city: ## Onboard a fixture-backed city. Usage: make onboard-city CITY=x MODES=x.
	@$(LOCAL_EXEC) env ONBOARD_PROVIDER="$${ONBOARD_PROVIDER:-mock}" \
		ONDOWAY_ONBOARD_HTTP="$${ONDOWAY_ONBOARD_HTTP:-fixture}" \
		ONBOARD_DATA_ROOT="$${ONBOARD_DATA_ROOT:-/tmp/ondoway-onboard}" \
		ONBOARD_REGISTRY_PATH="$${ONBOARD_REGISTRY_PATH:-/tmp/ondoway-onboard/cities.json}" \
		uv run python -m src.onboard.cli --city "$(CITY)" --modes "$(MODES)" \
		$(if $(DRY_RUN),--dry-run,) $(if $(CONFIRM_COST),--confirm-cost,)

# ════════════════════════════════════════════════════════════════════════════
#  DEPLOYMENT AND DIAGNOSTICS
# ════════════════════════════════════════════════════════════════════════════
##@ DEPLOYMENT AND DIAGNOSTICS

flutter-ipa: ## Build an IPA against the production API.
	cd mobile && flutter build ipa --dart-define=API_BASE_URL=https://ondoway.com/api/v1

testflight: ## Bump the build number, build the new IPA, then upload it.
	@$(RENDER_LOCAL_EXEC) bash -ceu '\
		test -n "$${APP_STORE_API_KEY_ID:-}" || { echo "ERROR: APP_STORE_API_KEY_ID missing." >&2; exit 2; }; \
		test -n "$${APP_STORE_ISSUER_ID:-}" || { echo "ERROR: APP_STORE_ISSUER_ID missing." >&2; exit 2; }; \
		cd mobile/ios && agvtool next-version -all; cd ../..; \
		$(MAKE) --no-print-directory flutter-ipa; \
		xcrun altool --upload-app --file mobile/build/ios/ipa/*.ipa --type ios \
			--apiKey "$$APP_STORE_API_KEY_ID" --apiIssuer "$$APP_STORE_ISSUER_ID"'

render-watch: ## Watch the latest Render deployment to a terminal state.
	@RENDER_WATCH_FORCE=1 bash .claude/hooks/render-deploy-watch.sh </dev/null

render-status: ## Show the latest Render deploy using the Keychain API credential.
	@uv run python scripts/dev_env.py deploy-status

setup-audio: ## Validate audio providers using a fresh Render environment.
	@$(RENDER_LOCAL_EXEC) uv run python scripts/check_audio_setup.py

aura-resume-proof: ## Explicitly test Aura resume and connectivity; never writes graph data.
	@$(CLOUD_EXEC) uv run python scripts/aura_resume_proof.py

flutter-test: ## Run Flutter tests with the project hang detector.
	@bash scripts/flutter_test.sh

clean: ## Remove build/test caches; never touch any database.
	@find . -type d -name __pycache__ -not -path '*/.venv/*' -exec rm -rf {} + 2>/dev/null || true
	@rm -rf .pytest_cache .ruff_cache 2>/dev/null || true
	@echo "✓ Cleared local caches. No database was touched."
