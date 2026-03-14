MKFILE_PATH := $(abspath $(lastword $(MAKEFILE_LIST)))
PROJECT_DIR := $(dir $(MKFILE_PATH))

# Set additional build args for docker image build using make arguments
IMAGE_NAME := pycon_backend
LAMBDA_CONTAINER_NAME = $(IMAGE_NAME)_lambda_container
SERVER_CONTAINER_NAME = $(IMAGE_NAME)_server_container

ifeq ($(DOCKER_DEBUG),true)
	DOCKER_MID_BUILD_OPTIONS = --progress=plain --no-cache
	DOCKER_END_BUILD_OPTIONS = 2>&1 | tee docker-build.log
else
	DOCKER_MID_BUILD_OPTIONS =
	DOCKER_END_BUILD_OPTIONS =
endif

AWS_LAMBDA_READYZ_PAYLOAD = '{\
  "resource": "/readyz/",\
  "path": "/readyz/",\
  "httpMethod": "GET",\
  "requestContext": {\
    "resourcePath": "/readyz/",\
    "httpMethod": "GET",\
    "path": "/readyz/"\
  },\
  "headers": {"accept": "application/json"},\
  "multiValueHeaders": {"accept": ["application/json"]},\
  "queryStringParameters": null,\
  "multiValueQueryStringParameters": null,\
  "pathParameters": null,\
  "stageVariables": null,\
  "body": null,\
  "isBase64Encoded": false\
}'

# =============================================================================
# Local development commands

# Setup local environments
local-setup:
	@uv sync

# Run local development server
local-api: local-collectstatic
	@ENV_PATH=envfile/.env.local uv run python app/manage.py runserver 8000

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
	@ENV_PATH=envfile/.env.local cd app && uv run pytest -v

# Devtools
hooks-install: local-setup
	uv run pre-commit install

hooks-upgrade:
	uv run pre-commit autoupdate

hooks-lint:
	uv run pre-commit run --all-files

lint: hooks-lint  # alias


# =============================================================================
# Zappa related commands
zappa-export:
	uv run zappa save-python-settings-file

# =============================================================================
# Docker related commands (Lambda)

# Lambda Docker image build
docker-lambda-build:
	@docker build \
		-f ./infra/lambda.Dockerfile -t $(IMAGE_NAME):lambda \
		--build-arg GIT_HASH=$(shell git rev-parse HEAD) \
		--build-arg IMAGE_BUILD_DATETIME=$(shell date +%Y-%m-%d_%H:%M:%S) \
		$(DOCKER_MID_BUILD_OPTIONS) $(PROJECT_DIR) $(DOCKER_END_BUILD_OPTIONS)

docker-lambda-run: docker-compose-up
	@(docker stop $(LAMBDA_CONTAINER_NAME) || true && docker rm $(LAMBDA_CONTAINER_NAME) || true) > /dev/null 2>&1
	@docker run -d --rm \
		-p 48000:8080 \
		--env-file envfile/.env.local --env-file envfile/.env.docker \
		--name $(LAMBDA_CONTAINER_NAME) \
		$(IMAGE_NAME):lambda

docker-lambda-readyz:
	curl -X POST http://localhost:48000/2015-03-31/functions/function/invocations -d $(AWS_LAMBDA_READYZ_PAYLOAD) | jq '.body | fromjson'

docker-lambda-test: docker-lambda-run docker-lambda-readyz

docker-lambda-build-and-test: docker-lambda-build docker-lambda-test

docker-lambda-stop:
	docker stop $(LAMBDA_CONTAINER_NAME) || true

docker-lambda-rm: docker-lambda-stop
	docker rm $(LAMBDA_CONTAINER_NAME) || true

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
