.PHONY: help install dev lint test run clean docker docker-stop

help:
	@echo "Available commands:"
	@echo "  make install     - Install dependencies with uv"
	@echo "  make dev         - Run development server"
	@echo "  make lint        - Run linting"
	@echo "  make test        - Run tests"
	@echo "  make run         - Run the application"
	@echo "  make clean       - Clean up build artifacts"
	@echo "  make docker      - Run with Docker"
	@echo "  make docker-stop - Stop Docker containers"
	@echo "  make seed        - Seed meta data"
	@echo "  make seed-meta   - Seed meta data"

install:
	uv sync

dev:
	uv run uvicorn somaai.main:app --reload --host 0.0.0.0 --port 8000

lint:
	uv run ruff check src/
	uv run ruff format --check src/
	uv run mypy src/

test:
	uv run pytest

run:
	uv run python -m somaai.main

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .coverage htmlcov dist build *.egg-info .ruff_cache

docker:
	docker-compose -f docker/docker-compose.yml up --build

docker-stop:
	docker-compose -f docker/docker-compose.yml down

seed-meta:
	PYTHONPATH=src .venv/bin/python -m scripts.seed_meta

seed:
	make seed-meta

