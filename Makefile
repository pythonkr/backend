MKFILE_PATH := $(abspath $(lastword $(MAKEFILE_LIST)))
PROJECT_DIR := $(dir $(MKFILE_PATH))

# Set additional build args for docker image build using make arguments
IMAGE_NAME := pycon_backend
SERVER_CONTAINER_NAME = $(IMAGE_NAME)_server_container

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

# Docker compose setup
# Below commands are for local development only
docker-compose-up:
	docker compose --env-file envfile/.env.local -f ./infra/docker-compose.dev.yaml up -d

docker-compose-down:
	docker compose --env-file envfile/.env.local -f ./infra/docker-compose.dev.yaml down

docker-compose-rm: docker-compose-down
	docker compose --env-file envfile/.env.local -f ./infra/docker-compose.dev.yaml rm
