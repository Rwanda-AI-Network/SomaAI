# Development Guide

Everything you need to set up, run, debug, and test SomaAI locally.

---

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.10+ | Runtime |
| [uv](https://github.com/astral-sh/uv) | Latest | Package management |
| Docker + Docker Compose | Latest | Infrastructure services |
| Git | Latest | Version control |

---

## Local Setup

#### Option 1: Full Stack with Docker (Production Ready)

```bash
git clone https://github.com/Rwanda-AI-Network/SomaAI.git
cd SomaAI
cp deployment/.env.example .env
# Edit .env with your GROQ_API_KEY
make docker-up
```

Services started:

| Service | Address | Purpose |
|---------|----------|---------|
| App | http://localhost:8000 | FastAPI application |
| Swagger UI | http://localhost:8000/docs | Interactive API docs |
| PostgreSQL | `localhost:5432` | Relational database (somaai-db) |
| Redis | `localhost:6379` | Cache + job queue (somaai-redis) |
| Qdrant | `localhost:6333` | Vector database (somaai-qdrant) |
| MinIO | `localhost:9000` | Local S3 storage (somaai-minio) |
| Worker | (background) | ARQ job processor (somaai-worker) |

### Option 2: Local Python Native Development

```bash
# Start infrastructure only
make docker-up # (then stop the 'api' and 'worker' containers manually if desired)
# OR use existing infrastructure
make install
make seed-meta
make dev
```

---

## Environment Variables

All configuration is loaded from `.env` via `pydantic-settings`. See `src/somaai/settings.py` for the authoritative list of settings fields.

### Core Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `SOMAAI_DATABASE_URL` | `sqlite+aiosqlite:///./somaai.db` | Async database URL |
| `SOMAAI_REDIS_URL` | `redis://localhost:6379/0` | Cache/Queue URL |
| `SOMAAI_CORS_ALLOWED_ORIGINS` | `["*"]` | Allowed CORS origins (list) |
| `SOMAAI_REQUIRE_API_KEY` | `false` | Enable API key protection |

---

## Makefile Reference

| Command | Description |
|---------|-------------|
| `make install` | Sync production + dev dependencies with uv |
| `make dev` | Run FastAPI with --reload |
| `make lint-fix` | Auto-fix linting and formatting (Ruff) |
| `make test` | Run pytest suite |
| `make docker-build` | Build versioned production images |
| `make docker-push` | Push images to Docker Hub (rwandaainetwork) |
| `make docker-up` | Start full production compose stack |
| `make docker-down` | Stop compose stack |
| `make version` | Show version from pyproject.toml |

---

## Docker Architecture (Production-Grade)

The production stack defined in `deployment/docker-compose.yml` uses pre-built images and relies on health checks for orchestration.

| Service | Image | Role |
|---------|-------|------|
| `api` | `rwandaainetwork/somaai` | FastAPI web service |
| `worker` | `rwandaainetwork/somaai` | Background processing (ARQ) |
| `db` | `postgres:16-alpine` | PostgreSQL Metadata |
| `redis` | `redis:7-alpine` | Cache / Rate Limit / Queue |
| `qdrant` | `qdrant/qdrant` | Vector Store |
| `minio` | `minio/minio` | Local S3-compatible storage |
