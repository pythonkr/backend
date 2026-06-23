MKFILE_PATH := $(abspath $(lastword $(MAKEFILE_LIST)))
PROJECT_DIR := $(dir $(MKFILE_PATH))

# Set additional build args for docker image build using make arguments
IMAGE_NAME := pycon_backend
SERVER_CONTAINER_NAME = $(IMAGE_NAME)_server_container
MCP_CONTAINER_NAME = $(IMAGE_NAME)_mcp_container

ifeq ($(DOCKER_DEBUG),true)
	DOCKER_MID_BUILD_OPTIONS = --progress=plain --no-cache
	DOCKER_END_BUILD_OPTIONS = 2>&1 | tee docker-build.log
else
	DOCKER_MID_BUILD_OPTIONS =
	DOCKER_END_BUILD_OPTIONS =
endif

# =============================================================================
# Local development commands

# Setup local environments
local-setup:
	@uv sync

# Run local development server
local-api: local-collectstatic
	@ENV_PATH=envfile/.env.local uv run python app/manage.py runserver 8000

# One-time: install the Chromium binary the mdx_preview tool drives (python deps come via `uv sync --group mcp`).
local-mcp-setup:
	@uv run --group mcp playwright install chromium

# Run the standalone MCP server (Django-free, calls the backend API; needs the API running).
local-mcp: local-mcp-setup
	@uv run --group mcp python -m mcp_app

# Run local Celery worker (requires `make docker-compose-up` for redis)
local-worker:
	@cd app && ENV_PATH=../envfile/.env.local uv run celery -A core worker -l INFO --concurrency=4

# Run django collectstatic
local-collectstatic:
	@ENV_PATH=envfile/.env.local uv run python app/manage.py collectstatic --noinput

# Run django shell
local-shell:
	@ENV_PATH=envfile/.env.local uv run python app/manage.py shell

# Run django shell plus
local-shell-plus:
	@ENV_PATH=envfile/.env.local uv run python app/manage.py shell_plus

# Run django db-shell
local-dbshell:
	@ENV_PATH=envfile/.env.local uv run python app/manage.py dbshell

# Run django makemigrations
local-makemigrations:
	@ENV_PATH=envfile/.env.local uv run python app/manage.py makemigrations

# Run django migrate
local-migrate:
	@ENV_PATH=envfile/.env.local uv run python app/manage.py migrate

# Show django makemigrations
local-showmigrations:
	@ENV_PATH=envfile/.env.local uv run python app/manage.py showmigrations

# Create admin superuser
local-createsuperuser:
	@ENV_PATH=envfile/.env.local uv run python app/manage.py createsuperuser

# Reverse django migrations
local-reverse-migrations:
	@ENV_PATH=envfile/.env.local uv run python app/manage.py migrate $(app) $(number)

# Run pytest
local-test:
	@cd app && ENV_PATH=../envfile/.env.local uv run pytest -v

# Run pytest with coverage
local-test-cov:
	@cd app && ENV_PATH=../envfile/.env.local uv run pytest \
		--cov \
		--cov-config=../pyproject.toml \
		--cov-report=term-missing \
		--cov-report=html:../htmlcov \
		--cov-report=xml:../coverage.xml

# Run pytest with coverage, scoped to shop-related code (CI 검증용: 100% 미만 시 exit 1)
# - 테스트 범위는 shop/ + admin_api/test/ — admin shop serializers/filtersets 가 admin_api 테스트로만 커버되므로 필수.
# - cov 범위는 shop/ 전체 + admin_api/{views,serializers,filtersets}/shop 만.
local-test-cov-shop:
	@cd app && ENV_PATH=../envfile/.env.local uv run pytest shop/ admin_api/test/ \
		--cov=shop \
		--cov=admin_api/views/shop \
		--cov=admin_api/serializers/shop \
		--cov=admin_api/filtersets/shop \
		--cov-config=../pyproject.toml \
		--cov-report=term-missing \
		--cov-fail-under=100

# Git worktree helpers — per-branch worktree with its own Postgres DB.
# Worktrees default to .worktrees/<slug> inside the repo (gitignored).
# See scripts/dev-worktree.sh.
#   make local-worktree-add branch=feat/foo [dir=.worktrees/foo]
#   make local-worktree-remove dir=.worktrees/feat_foo
local-worktree-add:
	@$(if $(branch),,$(error branch=<name> is required))
	@./scripts/dev-worktree.sh add "$(branch)" "$(dir)"

local-worktree-remove:
	@$(if $(dir),,$(error dir=<worktree-path> is required))
	@./scripts/dev-worktree.sh remove "$(dir)"

# Regenerate pyconkr.code-workspace (main repo + every .worktrees/<slug> as roots)
local-worktree-sync:
	@./scripts/dev-worktree.sh workspace


# Devtools
hooks-install: local-setup
	uv run pre-commit install

hooks-upgrade:
	uv run pre-commit autoupdate

hooks-lint:
	uv run pre-commit run --all-files

lint: hooks-lint  # alias


# =============================================================================
# Docker related commands (Server)

# Server Docker image build
docker-server-build:
	@docker build \
		-f ./infra/server.Dockerfile -t $(IMAGE_NAME):server \
		--build-arg GIT_HASH=$(shell git rev-parse HEAD) \
		--build-arg IMAGE_BUILD_DATETIME=$(shell date +%Y-%m-%d_%H:%M:%S) \
		$(DOCKER_MID_BUILD_OPTIONS) $(PROJECT_DIR) $(DOCKER_END_BUILD_OPTIONS)

docker-server-run: docker-compose-up
	@(docker stop $(SERVER_CONTAINER_NAME) || true && docker rm $(SERVER_CONTAINER_NAME) || true) > /dev/null 2>&1
	@docker run -d --rm \
		-p 8000:8000 \
		--env-file envfile/.env.local --env-file envfile/.env.docker \
		--name $(SERVER_CONTAINER_NAME) \
		$(IMAGE_NAME):server

docker-server-readyz:
	curl -s http://localhost:8000/readyz/ | jq '.'

docker-server-test: docker-server-run docker-server-readyz

docker-server-build-and-test: docker-server-build docker-server-test

docker-server-stop:
	docker stop $(SERVER_CONTAINER_NAME) || true

docker-server-rm: docker-server-stop
	docker rm $(SERVER_CONTAINER_NAME) || true

# Smoke-test the server image's MCP role: deps import (fastmcp + mcp_app) and the
# bundled Chromium actually launches (catches container sandbox issues). build()
# itself needs the API, so it's not exercised here.
docker-mcp-smoke: docker-server-build
	@docker run --rm $(IMAGE_NAME):server \
		python -c "import fastmcp, mcp_app.server; from playwright.sync_api import sync_playwright; \
p=sync_playwright().start(); b=p.chromium.launch(); print('mcp ok:', fastmcp.__version__, b.version); b.close(); p.stop()"

# Run the MCP server from the same server image (CMD override). Needs the API
# container up (docker-server-run); reaches it via host.docker.internal:8000.
docker-mcp-run: docker-server-run
	@(docker stop $(MCP_CONTAINER_NAME) || true && docker rm $(MCP_CONTAINER_NAME) || true) > /dev/null 2>&1
	@docker run -d --rm \
		-p 9000:9000 \
		-e MCP_HOST=0.0.0.0 \
		-e MCP_API_BASE_URL=http://host.docker.internal:8000 \
		--name $(MCP_CONTAINER_NAME) \
		$(IMAGE_NAME):server python -m mcp_app

docker-mcp-stop:
	docker stop $(MCP_CONTAINER_NAME) || true

docker-mcp-rm: docker-mcp-stop
	docker rm $(MCP_CONTAINER_NAME) || true

# Docker compose setup
# Below commands are for local development only
docker-compose-up:
	docker compose --env-file envfile/.env.local -f ./infra/docker-compose.dev.yaml up -d

docker-compose-down:
	docker compose --env-file envfile/.env.local -f ./infra/docker-compose.dev.yaml down

docker-compose-rm: docker-compose-down
	docker compose --env-file envfile/.env.local -f ./infra/docker-compose.dev.yaml rm
