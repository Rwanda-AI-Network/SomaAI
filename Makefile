# Makefile for SomaAI
# Includes versioning, professional build targets, and development tools.

.PHONY: help install dev lint lint-fix format test run clean docker-build docker-push release version seed seed-meta

# --- Configuration ---
PROJECT_NAME := somaai
ORG_NAME := rwandaainetwork
VERSION := $(shell grep -m 1 "version =" pyproject.toml | tr -s ' ' | tr -d '"' | cut -d' ' -f3)
IMAGE_NAME := $(ORG_NAME)/$(PROJECT_NAME)

help:
	@echo "SomaAI Management Commands:"
	@echo "  make install        - Install dependencies using uv"
	@echo "  make dev            - Start development server with reload"
	@echo "  make lint           - Run linting checks (ruff, mypy)"
	@echo "  make lint-fix       - Run linting and auto-fix issues"
	@echo "  make format         - Format code using ruff"
	@echo "  make test           - Run full test suite"
	@echo "  make run            - Run the application directly"
	@echo "  make clean          - Remove build and cache artifacts"
	@echo "  make version        - Display current project version"
	@echo ""
	@echo "Docker Production Commands:"
	@echo "  make docker-build   - Build production Docker image"
	@echo "  make docker-push    - Push image to $(ORG_NAME) on Docker Hub"
	@echo "  make docker-up      - Run the full production stack locally"
	@echo "  make docker-down    - Stop and remove the production stack"
	@echo ""
	@echo "Data Commands:"
	@echo "  make seed-meta      - Seed initial metadata into the database"

# --- Development ---

install:
	@echo "Installing dependencies..."
	uv sync --all-extras

dev:
	@echo "Starting development server..."
	DEBUG=true uv run uvicorn somaai.app:create_app --factory --reload --host 0.0.0.0 --port 8000

lint:
	@echo "Running linting..."
	uv run ruff check .
	uv run mypy src/somaai

lint-fix:
	@echo "Fixing linting issues..."
	uv run ruff check --fix .
	uv run ruff format .

format:
	@echo "Formatting code..."
	uv run ruff format .

test:
	@echo "Running tests..."
	SOMAAI_ENV=test uv run --extra all pytest -v

run:
	@echo "Running application..."
	uv run uvicorn somaai.app:create_app --factory --host 0.0.0.0 --port 8000

clean:
	@echo "Cleaning artifacts..."
	rm -rf .pytest_cache .ruff_cache .mypy_cache .venv dist build *.egg-info
	find . -type d -name "__pycache__" -exec rm -rf {} +

# --- Versioning & Docker ---

version:
	@echo "SomaAI Version: $(VERSION)"

docker-build:
	@echo "Building Docker image: $(IMAGE_NAME):latest and $(IMAGE_NAME):$(VERSION)..."
	uv lock
	docker build -f docker/Dockerfile -t $(IMAGE_NAME):latest -t $(IMAGE_NAME):$(VERSION) .

docker-push:
	@echo "Pushing images to Docker Hub..."
	docker push $(IMAGE_NAME):latest
	docker push $(IMAGE_NAME):$(VERSION)

docker-up:
	@if [ ! -f .env ]; then \
		echo "Initializing .env from deployment/.env.example..."; \
		cp deployment/.env.example .env; \
	fi
	docker-compose -f deployment/docker-compose.yml up -d --build

docker-down:
	docker-compose -f deployment/docker-compose.yml down

docker-clean:
	@echo "Cleaning up all project containers..."
	docker-compose -f deployment/docker-compose.yml down --remove-orphans
	docker-compose -f docker/docker-compose.yml down --remove-orphans
	docker system prune -f --filter "label=com.docker.compose.project=deployment"
	docker system prune -f --filter "label=com.docker.compose.project=docker"

docker-logs:
	docker-compose -f deployment/docker-compose.yml logs -f

logs: docker-logs

# --- Database & Seeds ---

seed-meta:
	@echo "Seeding metadata..."
	uv run python -m scripts.seed_meta

seed: seed-meta
