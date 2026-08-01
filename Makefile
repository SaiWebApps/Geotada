export ONDOWAY_ALLOW_INSECURE_AUTH_SECRETS := 1
SHELL := /bin/bash

# ════════════════════════════════════════════════════════════════════════════
#  PREREQUISITES
# ════════════════════════════════════════════════════════════════════════════
# Every target below opens by NAMING the capabilities it needs.  scripts/preflight.py
# resolves that list in dependency order, probes each one for real (a live Cypher
# query, a health endpoint, an installed executable), starts or installs the ones it
# is allowed to, and exits non-zero naming the exact command for the ones it cannot.
# Nothing in a recipe runs until its whole list is satisfied.
#
# This replaced hand-rolled `_ensure-*` helpers whose success message was simply the
# last statement in a chain that ignored failures: with the Docker daemon down, the
# old `db-up` printed "neo4j ready at bolt://localhost:7687" and exited 0, and the
# real failure surfaced two steps later disguised as a data problem.
#
#   make preflight            check everything and repair what is repairable
#   make preflight-list       describe every requirement and how it is restored
#   PREFLIGHT_AUTOFIX=0 ...   report only; never start or install anything
#
# preflight runs on the SYSTEM python3 and imports only the standard library, so it
# can still report that uv or Docker is missing on a machine with nothing set up.
PREFLIGHT := python3 scripts/preflight.py

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
	tests/test_magic_link_live.py
GOLDEN_TEST_FILES := \
	tests/test_narration_coherence.py \
	tests/test_tour_golden_ile.py \
	tests/test_tour_golden_pdv.py
GRADE_TEST_FILES := tests/test_tour_audit.py tests/test_tour_grade.py
INVARIANT_TEST_FILES := tests/test_tour_invariants_live.py

# Reusable prerequisite sets.  A target names one of these, or spells its own list.
PRE_PY := uv python-deps
PRE_LOCAL_GRAPH := uv python-deps db-dev dev-data
PRE_TOUR := uv python-deps db-dev dev-data valhalla
PRE_PYTEST := uv python-deps db-test db-dev dev-data valhalla
PRE_FLUTTER := flutter flutter-deps
# The full union `make test` will need, checked once up front so a missing Render
# credential fails in seconds rather than twenty minutes into the suite.
PRE_FULL_SUITE := uv python-deps db-test db-dev db-workbench dev-data valhalla \
	playwright-browser flutter flutter-deps render-key

DB ?= dev
TARGET ?= local

.PHONY: \
	help doctor setup bootstrap preflight preflight-list \
	render-auth-setup render-auth-status config-status \
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

# A diagnostic, so it exits 0 even when things are missing: a fresh clone is
# MEANT to be missing things, and the first command a new developer runs must not
# look like a broken tool. `make preflight` is the one that fixes them.
doctor: ## Report every prerequisite without starting or installing anything.
	@$(PREFLIGHT) --all --report --label "this machine"

preflight: ## Check every prerequisite and repair everything that is repairable.
	@$(PREFLIGHT) --all --label "the whole project"

preflight-list: ## Describe every requirement a target can declare, and how it is restored.
	@$(PREFLIGHT) --list

setup: ## Set up everything from a fresh clone (same as bootstrap).
	@$(MAKE) --no-print-directory bootstrap

bootstrap: ## Provision a complete local development environment from a fresh clone.
	@$(PREFLIGHT) --label bootstrap uv python-deps docker-daemon \
		db-dev db-test db-workbench dev-data valhalla-tiles valhalla \
		flutter flutter-deps playwright-browser render-key
	@echo ""
	@echo "✓ Local development environment is ready."

# ════════════════════════════════════════════════════════════════════════════
#  CONFIGURATION
# ════════════════════════════════════════════════════════════════════════════
##@ CONFIGURATION

render-auth-setup: ## Store or replace the Render API key in macOS Keychain.
	@$(PREFLIGHT) --label render-auth-setup $(PRE_PY)
	@uv run python scripts/dev_env.py auth-setup

render-auth-status: ## Validate the Keychain Render API key against ondoway-api.
	@$(PREFLIGHT) --label render-auth-status $(PRE_PY) render-key
	@uv run python scripts/dev_env.py auth-status

config-status: ## Fetch Render fresh and validate the final local/test/workbench boundaries.
	@$(PREFLIGHT) --label config-status $(PRE_PY) render-key
	@$(RENDER_LOCAL_EXEC) python -c 'import os; assert os.environ["NEO4J_URI"] == "bolt://localhost:7687"; assert os.environ.get("RESEND_API_KEY"); print("local: localhost:7687 + fresh Render credentials")'
	@$(RENDER_TEST_EXEC) python -c 'import os; assert os.environ["NEO4J_URI"] == "bolt://localhost:7688"; assert os.environ.get("RESEND_API_KEY"); print("test: localhost:7688 + fresh Render credentials")'
	@$(ENV_EXEC) --profile workbench --render -- python -c 'import os; assert os.environ["NEO4J_URI"] == "bolt://localhost:7689"; assert os.environ.get("RESEND_API_KEY"); print("workbench: localhost:7689 + fresh Render credentials")'

sync: ## Install Python dependencies from public PyPI.
	@$(PREFLIGHT) --label sync uv
	uv sync --extra test --extra dev --extra aws

sync-apple: ## Install dependencies from Apple's mirror while preserving the public lockfile.
	@$(PREFLIGHT) --label sync-apple uv
	@curl -sI --max-time 5 https://pypi.apple.com/simple/ >/dev/null 2>&1 || \
		{ echo "ERROR: pypi.apple.com unreachable; use make sync." >&2; exit 1; }
	@cp uv.lock /tmp/ondoway-uv-lock-public
	@UV_DEFAULT_INDEX=https://pypi.apple.com/simple uv sync --extra test --extra dev --extra aws; ec=$$?; \
		cp /tmp/ondoway-uv-lock-public uv.lock; rm -f /tmp/ondoway-uv-lock-public; exit $$ec

requirements: ## Regenerate requirements.txt from uv.lock.
	@$(PREFLIGHT) --label requirements $(PRE_PY)
	uv export --no-dev --no-editable --no-emit-project -o requirements.txt
	@! grep -q "pypi.apple.com" requirements.txt

# ════════════════════════════════════════════════════════════════════════════
#  CODE QUALITY
# ════════════════════════════════════════════════════════════════════════════
##@ CODE QUALITY

lint: ## Run the Python linter.
	@$(PREFLIGHT) --label lint $(PRE_PY)
	uv run ruff check src/ tests/ scripts/dev_env.py scripts/ensure_dev_data.py \
		scripts/preflight.py \
		scripts/db_parity.py scripts/check_audio_setup.py \
		scripts/tour_batch_candidate.py scripts/score_saved_tours.py \
		scripts/score_gold_text.py scripts/human_reference_tours.py \
		scripts/tour_golden_diff.py

format: ## Format Python and apply safe lint fixes.
	@$(PREFLIGHT) --label format $(PRE_PY)
	uv run ruff format src/ tests/ scripts/dev_env.py scripts/ensure_dev_data.py \
		scripts/preflight.py \
		scripts/db_parity.py scripts/check_audio_setup.py scripts/human_reference_tours.py \
		scripts/tour_batch_candidate.py
	uv run ruff check --fix-only src/ tests/ scripts/dev_env.py scripts/ensure_dev_data.py \
		scripts/preflight.py \
		scripts/db_parity.py scripts/check_audio_setup.py scripts/human_reference_tours.py \
		scripts/tour_batch_candidate.py

flutter-analyze: ## Run Dart static analysis.
	@$(PREFLIGHT) --label flutter-analyze $(PRE_FLUTTER)
	cd mobile && NO_PROXY=pub.dev,*.pub.dev no_proxy=pub.dev,*.pub.dev flutter analyze

# ════════════════════════════════════════════════════════════════════════════
#  TEST
# ════════════════════════════════════════════════════════════════════════════
##@ TEST

test: ## THE definitive suite: Python, Flutter, browser, tour, live-provider, and cloud parity.
	@$(PREFLIGHT) --label test $(PRE_FULL_SUITE)
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
	@$(PREFLIGHT) --label audit $(PRE_FULL_SUITE)
	@$(MAKE) --no-print-directory lint
	@$(MAKE) --no-print-directory test

test-file: ## Run one test file safely. Usage: make test-file FILE=tests/test_x.py [LIVE=1].
	@test -n "$(FILE)" || { echo "ERROR: FILE is required." >&2; exit 2; }
	@if [ "$(LIVE)" = "1" ]; then \
		$(MAKE) --no-print-directory test-live FILE="$(FILE)"; \
	else \
		$(PREFLIGHT) --label "test-file" $(PRE_PYTEST) || exit $$?; \
		find tests src -name __pycache__ -exec rm -rf {} + 2>/dev/null || true; \
		$(TEST_EXEC) uv run pytest "$(FILE)" -o addopts= -v; \
	fi

test-live: ## Run every live-provider test with a fresh full Render environment.
	@$(PREFLIGHT) --label test-live $(PRE_PYTEST) render-key
	@$(MAKE) --no-print-directory render-auth-status
	@find tests src -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@$(RENDER_TEST_EXEC) env \
		ONDOWAY_LIVE_TESTS=1 \
		NO_PROXY="$(NO_PROXY_LIST)" no_proxy="$(NO_PROXY_LIST)" \
		uv run pytest $(or $(FILE),$(LIVE_TEST_FILES)) -o addopts= -m live -v $(PYTEST_ARGS)

# Deliberately does NOT declare `valhalla`: this shard drives review.html against the
# isolated 7689 graph and never asks for a route, so requiring map tiles here would
# block a fresh clone from running it. If a workbench test ever needs routing, add
# `valhalla` to this line rather than relying on a sibling shard having started it.
test-workbench: ## Run the Playwright workbench suite against isolated Neo4j 7689.
	@$(PREFLIGHT) --label test-workbench uv python-deps db-test db-workbench playwright-browser
	@find tests src -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@$(TEST_EXEC) env NO_PROXY="$(NO_PROXY_LIST)" no_proxy="$(NO_PROXY_LIST)" \
		uv run pytest tests/test_workbench_ui.py -o addopts= -v --tb=short

golden-probe: ## Print golden overlap counts using provisioned dev data and Valhalla.
	@$(PREFLIGHT) --label golden-probe $(PRE_PYTEST)
	@set -o pipefail; $(TEST_EXEC) uv run pytest $(GOLDEN_TEST_FILES) \
		-o addopts= -m golden -q -s 2>&1 | \
		grep -oE "GOLDEN-OVERLAP .*"

score-saved-tours: ## Score every saved tour artifact against the current rubric. $0, no DB, no containers.
	@$(PREFLIGHT) --label score-saved-tours $(PRE_PY)
	@$(LOCAL_EXEC) uv run python scripts/score_saved_tours.py $(SCORE_ARGS)

score-gold-text: ## Score the owner's own gold text against the rubric — calibration. $0, no DB.
	@$(PREFLIGHT) --label score-gold-text $(PRE_PY)
	@$(LOCAL_EXEC) uv run python scripts/score_gold_text.py --compare

score-human-tours: ## Score the two human-authored reference tours against the rubric. $0, no DB.
	@$(PREFLIGHT) --label score-human-tours $(PRE_PY)
	@$(LOCAL_EXEC) uv run python -m scripts.human_reference_tours

golden-diff: ## Diff one golden fixture. Usage: make golden-diff FIXTURE=pdv_round_trip_60min.
	@test -n "$(FIXTURE)" || { echo "ERROR: FIXTURE is required." >&2; exit 2; }
	@$(PREFLIGHT) --label golden-diff $(PRE_TOUR)
	@$(LOCAL_EXEC) uv run python scripts/tour_golden_diff.py "$(FIXTURE)"

_test-python:
	@$(PREFLIGHT) --label _test-python $(PRE_PYTEST)
	@find tests src -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@$(TEST_EXEC) env NO_PROXY="$(NO_PROXY_LIST)" no_proxy="$(NO_PROXY_LIST)" \
		uv run pytest tests/ -v $(PYTEST_ARGS)

_test-golden:
	@$(PREFLIGHT) --label _test-golden $(PRE_PYTEST)
	@$(TEST_EXEC) uv run pytest $(GOLDEN_TEST_FILES) -o addopts= -m golden -v $(PYTEST_ARGS)

_test-grade:
	@$(PREFLIGHT) --label _test-grade $(PRE_PYTEST)
	@$(TEST_EXEC) uv run pytest $(GRADE_TEST_FILES) -o addopts= -m grade -v $(PYTEST_ARGS)

_test-invariants:
	@$(PREFLIGHT) --label _test-invariants $(PRE_PYTEST)
	@$(TEST_EXEC) uv run pytest $(INVARIANT_TEST_FILES) -o addopts= -m invariants -v $(PYTEST_ARGS)

_test-cloud:
	@$(PREFLIGHT) --label _test-cloud $(PRE_PY) render-key
	@$(MAKE) --no-print-directory render-auth-status
	@echo "→ Aura parity: read-only session; pytest and reset targets never receive Aura."
	@$(CLOUD_EXEC) uv run python -m scripts.aura_ensure_running
	@$(CLOUD_EXEC) env ONDOWAY_CLOUD_READ_ONLY=1 uv run python -m scripts.db_parity

# ════════════════════════════════════════════════════════════════════════════
#  PAID TOUR OPERATIONS
# ════════════════════════════════════════════════════════════════════════════
##@ PAID TOUR OPERATIONS

tour-batch-plan: ## Build the sealed Premium plan without constructing a paid client.
	@$(PREFLIGHT) --label tour-batch-plan $(PRE_TOUR)
	@$(LOCAL_EXEC) uv run python -m scripts.tour_batch_candidate $(if $(CASE),--case "$(CASE)",)

tour-batch-live: ## Execute an approved Premium plan with fresh Render credentials.
	@test -n "$(PLAN_SHA256)" || { echo "ERROR: PLAN_SHA256 is required." >&2; exit 2; }
	@$(PREFLIGHT) --label tour-batch-live $(PRE_TOUR) render-key
	@$(RENDER_LOCAL_EXEC) env ONDOWAY_TOUR_BATCH_APPROVED=1 \
		uv run python -m scripts.tour_batch_candidate --live \
		--approve-plan-sha256 "$(PLAN_SHA256)" --max-workers "$(or $(MAX_WORKERS),4)"

tour-batch-review-plan: ## Rebuild a sealed semantic-review plan without provider calls.
	@$(PREFLIGHT) --label tour-batch-review-plan $(PRE_TOUR)
	@$(LOCAL_EXEC) uv run python -m scripts.tour_batch_review \
		$(if $(BATCH_ROOT),--batch-root "$(BATCH_ROOT)",) \
		$(if $(REVIEW_ROOT),--review-root "$(REVIEW_ROOT)",)

tour-batch-review-live: ## Execute an approved semantic-review plan with fresh Render credentials.
	@test -n "$(REVIEW_PLAN_SHA256)" || { echo "ERROR: REVIEW_PLAN_SHA256 is required." >&2; exit 2; }
	@$(PREFLIGHT) --label tour-batch-review-live $(PRE_TOUR) render-key
	@$(RENDER_LOCAL_EXEC) env ONDOWAY_TOUR_BATCH_REVIEW_APPROVED=1 \
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

# Starting a database IS the preflight requirement `db-<name>`: it starts the
# service if needed and then proves readiness by running a real Cypher query
# inside the container. It cannot report success on a database that is absent.
db-up: ## Start one local Neo4j service. Usage: make db-up DB=dev|test|workbench.
	@case "$(DB)" in dev|test|workbench) ;; \
		*) echo "ERROR: DB must be dev, test, or workbench; never cloud." >&2; exit 2 ;; esac
	@$(PREFLIGHT) --label "db-up DB=$(DB)" db-$(DB)

db-down: ## Stop one local Neo4j service without deleting data. Usage: make db-down DB=...
	@case "$(DB)" in dev|test|workbench) ;; \
		*) echo "ERROR: DB must be dev, test, or workbench; never cloud." >&2; exit 2 ;; esac
	@$(PREFLIGHT) --label "db-down DB=$(DB)" docker-daemon
	@case "$(DB)" in dev) service=neo4j ;; test) service=neo4j-test ;; \
		workbench) service=neo4j-workbench ;; esac; \
	docker compose stop "$${service}"

db-status: ## Show all local Neo4j service states.
	@$(PREFLIGHT) --label db-status docker-daemon
	@docker compose ps neo4j neo4j-test neo4j-workbench

db-reset: ## Delete exactly one local Neo4j volume. Usage: make db-reset DB=dev|test|workbench.
	@case "$(DB)" in dev|test|workbench) ;; \
		*) echo "ERROR: DB must be dev, test, or workbench; Aura is unreachable here." >&2; exit 2 ;; esac
	@$(PREFLIGHT) --label "db-reset DB=$(DB)" docker-daemon
	@case "$(DB)" in \
		dev) service=neo4j; volume=ondoway_neo4j_data ;; \
		test) service=neo4j-test; volume=ondoway_neo4j_test_data ;; \
		workbench) service=neo4j-workbench; volume=ondoway_neo4j_workbench_data ;; \
	esac; \
	docker compose stop "$${service}"; \
	docker compose rm -f "$${service}"; \
	docker volume rm -f "$${volume}"; \
	echo "✓ Deleted only local volume $${volume}."

db-parity: ## Compare committed data with local dev or read-only Aura. Usage: make db-parity TARGET=local|cloud.
	@case "$(TARGET)" in \
		local) $(PREFLIGHT) --label "db-parity TARGET=local" uv python-deps db-dev && \
			$(LOCAL_EXEC) uv run python -m scripts.db_parity $(CITY) ;; \
		cloud) $(PREFLIGHT) --label "db-parity TARGET=cloud" $(PRE_PY) render-key && \
			$(CLOUD_EXEC) env ONDOWAY_CLOUD_READ_ONLY=1 \
			uv run python -m scripts.db_parity $(CITY) ;; \
		*) echo "ERROR: TARGET must be local or cloud." >&2; exit 2 ;; \
	esac

# ════════════════════════════════════════════════════════════════════════════
#  ROUTING
# ════════════════════════════════════════════════════════════════════════════
##@ ROUTING

VALHALLA_ROOT = $(shell dirname "$$(git rev-parse --git-common-dir)")

# `valhalla` declares `valhalla-tiles`, so a clone with no map data is told to run
# valhalla-build-tiles immediately, instead of polling a doomed endpoint for ten
# minutes and then failing.
valhalla-up: ## Start Valhalla and wait for a healthy routing endpoint.
	@$(PREFLIGHT) --label valhalla-up valhalla

valhalla-down: ## Stop Valhalla without deleting tiles.
	@$(PREFLIGHT) --label valhalla-down docker-daemon
	docker compose -f "$(VALHALLA_ROOT)/docker-compose.yml" \
		--project-directory "$(VALHALLA_ROOT)" stop valhalla

valhalla-status: ## Check the Valhalla health endpoint.
	@curl -fs --max-time 3 http://localhost:8002/status >/dev/null && echo "✓ Valhalla healthy."

# Download to a temporary name and move into place only on success. Writing
# straight to the final path meant that interrupting this at 50 MB of 465 MB left
# a truncated extract, which the `valhalla-tiles` probe then reported as
# satisfied — a green report on broken data, in the one target exempted from the
# preflight mechanism. The tile build would consume it and produce a quietly
# wrong road network. preflight's own repair already does it this way.
valhalla-build-tiles: ## Download Paris and New York OSM extracts for tile building.
	@mkdir -p "$(VALHALLA_ROOT)/valhalla/custom_files"
	@set -e; dir="$(VALHALLA_ROOT)/valhalla/custom_files"; \
	download() { \
		echo "→ downloading $$1"; \
		curl -L --fail -o "$$dir/$$1.partial" "$$2" || { rm -f "$$dir/$$1.partial"; exit 1; }; \
		mv "$$dir/$$1.partial" "$$dir/$$1"; \
	}; \
	download ile-de-france-latest.osm.pbf \
		https://download.geofabrik.de/europe/france/ile-de-france-latest.osm.pbf; \
	download new-york.osm.pbf \
		https://download.bbbike.org/osm/bbbike/NewYork/NewYork.osm.pbf; \
	echo "✓ OSM extracts downloaded. The first routing start builds tiles from them."

# ════════════════════════════════════════════════════════════════════════════
#  RUN
# ════════════════════════════════════════════════════════════════════════════
##@ RUN

api: ## Start the local API with dev data and fresh Render provider credentials.
	@$(PREFLIGHT) --label api $(PRE_LOCAL_GRAPH) render-key
	@$(RENDER_LOCAL_EXEC) env NO_PROXY="$(NO_PROXY_LIST)" no_proxy="$(NO_PROXY_LIST)" \
		uv run uvicorn src.api.app:app --host 127.0.0.1 --port 8000 --reload

workbench: ## Start the local editorial workbench with dev data and fresh Render credentials.
	@$(PREFLIGHT) --label workbench $(PRE_TOUR) render-key
	@$(RENDER_LOCAL_EXEC) bash scripts/workbench.sh

dashboard: ## Start the local dashboard with the validated dev profile.
	@$(PREFLIGHT) --label dashboard $(PRE_LOCAL_GRAPH)
	@$(LOCAL_EXEC) uv run python -m src.server

flutter-web: ## Run the Flutter web app on port 3000.
	@$(PREFLIGHT) --label flutter-web $(PRE_FLUTTER)
	cd mobile && flutter run -d chrome --web-port=3000

SIM ?= 46F0E608-943E-48F4-9EDB-8925855D0069
SIM_BOOTED = $(shell xcrun simctl list devices booted 2>/dev/null | grep -oE '[0-9A-Fa-f-]{36}' | head -1)
SIM_TARGET = $(if $(filter command line,$(origin SIM)),$(SIM),$(if $(SIM_BOOTED),$(SIM_BOOTED),$(SIM)))

flutter-ios: ## Run the Flutter app in an iOS simulator with a local API.
	@$(PREFLIGHT) --label flutter-ios $(PRE_LOCAL_GRAPH) render-key $(PRE_FLUTTER) xcode
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
	@$(PREFLIGHT) --label flutter-device $(PRE_FLUTTER)
	cd mobile && flutter run --dart-define=API_BASE_URL=https://ondoway.com/api/v1

flutter-pub-get: ## Resolve Flutter dependencies.
	@$(PREFLIGHT) --label flutter-pub-get flutter
	cd mobile && NO_PROXY=pub.dev,*.pub.dev no_proxy=pub.dev,*.pub.dev flutter pub get

flutter-clean: ## Clean Flutter build artifacts and resolve dependencies.
	@$(PREFLIGHT) --label flutter-clean flutter
	cd mobile && flutter clean
	@$(MAKE) --no-print-directory flutter-pub-get

# ════════════════════════════════════════════════════════════════════════════
#  DATA AND PIPELINE
# ════════════════════════════════════════════════════════════════════════════
##@ DATA AND PIPELINE

survey-area-candidates: ## Survey undersized physical-extent POIs. Usage: make survey-area-candidates CITY=x.
	@$(PREFLIGHT) --label survey-area-candidates $(PRE_PY)
	@$(LOCAL_EXEC) uv run python scripts/survey_area_candidates.py --city "$(CITY)" $(ARGS)

fix-area-radii: ## Correct reviewed trigger radii locally. ARGS="--apply" writes.
	@$(PREFLIGHT) --label fix-area-radii $(PRE_PY)
	@$(LOCAL_EXEC) uv run python scripts/fix_area_trigger_radii.py --city "$(CITY)" $(ARGS)

backfill-provenance: ## Backfill beat provenance on the local dev graph.
	@$(PREFLIGHT) --label backfill-provenance uv python-deps db-dev
	@$(LOCAL_EXEC) uv run python -m scripts.upload_paris --provenance-only

backfill-poi-role: ## Apply reviewed POI roles. ARGS="--apply --neo4j" writes locally.
	@$(PREFLIGHT) --label backfill-poi-role $(PRE_PY)
	@$(LOCAL_EXEC) uv run python scripts/backfill_poi_role.py $(ARGS)

backfill-name-key: ## Backfill missing POI name keys on the local dev graph.
	@$(PREFLIGHT) --label backfill-name-key uv python-deps db-dev
	@$(LOCAL_EXEC) uv run python scripts/backfill_name_key.py $(ARGS)

wiki-fetch: ## Pin Wikipedia text. Usage: make wiki-fetch POI=x [TITLE=x] [CITY=paris].
	@$(PREFLIGHT) --label wiki-fetch $(PRE_PY)
	@$(LOCAL_EXEC) python3 scripts/wiki_fetch.py --city "$(or $(CITY),paris)" \
		--name "$(POI)"$(if $(TITLE), --title "$(TITLE)",)

gen-within-edges: ## Regenerate one city's within_edges.json.
	@$(PREFLIGHT) --label gen-within-edges $(PRE_PY)
	@$(LOCAL_EXEC) uv run python scripts/generate_within_edges.py --slug "$(or $(CITY),paris)"

validate-beats: ## Validate one city's committed beats before upload.
	@$(PREFLIGHT) --label validate-beats $(PRE_PY)
	@$(LOCAL_EXEC) uv run python scripts/validate_beats.py data/$(or $(CITY),paris)/beats.json

deploy: ## Deploy one city. Local by default; cloud requires TARGET=cloud CONFIRM_CLOUD_WRITE=1.
	@test -n "$(CITY)" || { echo "ERROR: CITY is required." >&2; exit 2; }
	@case "$(TARGET)" in \
		local) $(PREFLIGHT) --label "deploy TARGET=local" uv python-deps db-dev && \
			$(LOCAL_EXEC) uv run python -m scripts.deploy --slug "$(CITY)" ;; \
		cloud) test "$(CONFIRM_CLOUD_WRITE)" = "1" || \
			{ echo "ERROR: add CONFIRM_CLOUD_WRITE=1 for Aura." >&2; exit 2; }; \
			$(PREFLIGHT) --label "deploy TARGET=cloud" $(PRE_PY) render-key && \
			$(CLOUD_EXEC) uv run python -m scripts.aura_ensure_running && \
			$(CLOUD_EXEC) uv run python -m scripts.deploy --slug "$(CITY)" --allow-cloud ;; \
		*) echo "ERROR: TARGET must be local or cloud." >&2; exit 2 ;; \
	esac

prune-orphans: ## Find or delete orphaned records. Cloud requires explicit TARGET and confirmation.
	@test -n "$(CITY)" || { echo "ERROR: CITY is required." >&2; exit 2; }
	@case "$(TARGET)" in \
		local) $(PREFLIGHT) --label "prune-orphans TARGET=local" uv python-deps db-dev && \
			$(LOCAL_EXEC) uv run python -m scripts.prune_orphan_pois --slug "$(CITY)" \
				$(if $(APPLY),--apply,) ;; \
		cloud) test "$(CONFIRM_CLOUD_WRITE)" = "1" || \
			{ echo "ERROR: add CONFIRM_CLOUD_WRITE=1 for Aura." >&2; exit 2; }; \
			$(PREFLIGHT) --label "prune-orphans TARGET=cloud" $(PRE_PY) render-key && \
			$(CLOUD_EXEC) uv run python -m scripts.prune_orphan_pois --slug "$(CITY)" \
				--allow-cloud $(if $(APPLY),--apply,) ;; \
		*) echo "ERROR: TARGET must be local or cloud." >&2; exit 2 ;; \
	esac

fetch-boundary: ## Fetch an OSM boundary polygon.
	@$(PREFLIGHT) --label fetch-boundary $(PRE_PY)
	@$(LOCAL_EXEC) uv run python -m scripts.fetch_city_boundary --slug "$(SLUG)" \
		--relation "$(RELATION)"$(if $(FORCE), --force,)

geocode-pois: ## Geocode POIs through Nominatim.
	@$(PREFLIGHT) --label geocode-pois $(PRE_PY)
	@$(LOCAL_EXEC) uv run python -m scripts.geocode_pois --slug "$(SLUG)"$(if $(ALL), --all,)

# Who writes the transition sentences. scripts/tour_build.py now REFUSES to run
# without being told, because canned transitions printed under a "validation:
# PASS" header, with nothing naming them, is how part-fixed-string tours read as
# finished ones. --canned keeps this target free and unchanged in behaviour; it
# is stated rather than assumed. Override for real glue (spends money):
#   make tour-build GLUE=--haiku ARGS="..."
GLUE ?= --canned

tour-build: ## Build one local tour and render it to Markdown. GLUE=--haiku for real glue (paid).
	@$(PREFLIGHT) --label tour-build $(PRE_TOUR)
	@$(LOCAL_EXEC) uv run python scripts/tour_build.py $(GLUE) $(ARGS)

measure-planned-audio: ## Measure voiced audio against tier dwell.
	@$(PREFLIGHT) --label measure-planned-audio $(PRE_LOCAL_GRAPH)
	@$(LOCAL_EXEC) uv run python scripts/measure_planned_audio.py $(ARGS)

measure-governor: ## Compare uncapped and governed emitted audio.
	@$(PREFLIGHT) --label measure-governor $(PRE_LOCAL_GRAPH)
	@$(LOCAL_EXEC) uv run python scripts/measure_governor.py $(ARGS)

onboard-city: ## Onboard a fixture-backed city. Usage: make onboard-city CITY=x MODES=x.
	@$(PREFLIGHT) --label onboard-city $(PRE_PY)
	@$(LOCAL_EXEC) env ONBOARD_PROVIDER="$${ONBOARD_PROVIDER:?set ONBOARD_PROVIDER=anthropic (real) — there is no default}" \
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
	@$(PREFLIGHT) --label flutter-ipa $(PRE_FLUTTER) xcode
	cd mobile && flutter build ipa --dart-define=API_BASE_URL=https://ondoway.com/api/v1

testflight: ## Bump the build number, build the new IPA, then upload it.
	@$(PREFLIGHT) --label testflight $(PRE_PY) render-key $(PRE_FLUTTER) xcode
	@$(RENDER_LOCAL_EXEC) bash -ceu '\
		test -n "$${APP_STORE_API_KEY_ID:-}" || { echo "ERROR: APP_STORE_API_KEY_ID missing." >&2; exit 2; }; \
		test -n "$${APP_STORE_ISSUER_ID:-}" || { echo "ERROR: APP_STORE_ISSUER_ID missing." >&2; exit 2; }; \
		cd mobile/ios && agvtool next-version -all; cd ../..; \
		$(MAKE) --no-print-directory flutter-ipa; \
		xcrun altool --upload-app --file mobile/build/ios/ipa/*.ipa --type ios \
			--apiKey "$$APP_STORE_API_KEY_ID" --apiIssuer "$$APP_STORE_ISSUER_ID"'

# The deploy watcher is the ONLY thing in this repo that uses the Render CLI, and
# the CLI carries its own browser sign-in, separate from the Keychain API key that
# every other Render-backed target uses. Declaring both is what turns "render CLI
# not installed — deploy NOT monitored" into an installable, signed-in CLI.
render-watch: ## Watch the latest Render deployment to a terminal state.
	@$(PREFLIGHT) --label render-watch render-cli render-cli-auth
	@RENDER_WATCH_FORCE=1 bash .claude/hooks/render-deploy-watch.sh </dev/null

render-status: ## Show the latest Render deploy using the Keychain API credential.
	@$(PREFLIGHT) --label render-status $(PRE_PY) render-key
	@uv run python scripts/dev_env.py deploy-status

setup-audio: ## Validate audio providers using a fresh Render environment.
	@$(PREFLIGHT) --label setup-audio $(PRE_PY) render-key
	@$(RENDER_LOCAL_EXEC) uv run python scripts/check_audio_setup.py

aura-resume-proof: ## Explicitly test Aura resume and connectivity; never writes graph data.
	@$(PREFLIGHT) --label aura-resume-proof $(PRE_PY) render-key
	@$(CLOUD_EXEC) uv run python scripts/aura_resume_proof.py

flutter-test: ## Run Flutter tests with the project hang detector.
	@$(PREFLIGHT) --label flutter-test $(PRE_FLUTTER)
	@bash scripts/flutter_test.sh

clean: ## Remove build/test caches; never touch any database.
	@find . -type d -name __pycache__ -not -path '*/.venv/*' -exec rm -rf {} + 2>/dev/null || true
	@rm -rf .pytest_cache .ruff_cache 2>/dev/null || true
	@echo "✓ Cleared local caches. No database was touched."
