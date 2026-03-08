# SomaAI

RAG-powered educational assistant for Rwandan students and teachers. Transforms curriculum PDFs into searchable knowledge and generates grounded, cited answers.

**Stack**: FastAPI · Qdrant (384d) · PostgreSQL 16 · Redis 7 · Groq (Llama 3.2)

---

## Architecture

```mermaid
graph LR
    Client["Client"] -->|POST /chat/ask| API["FastAPI<br/>Gateway"]
    API --> RAG["RAG Pipeline"]
    RAG --> Q["Qdrant<br/>Vectors"]
    RAG --> LLM["Groq<br/>Llama 3.2"]
    RAG --> Cache["Redis<br/>Cache"]
    API --- PG["PostgreSQL<br/>Metadata"]
    Ingest["Ingestion<br/>Pipeline"] --> Q
    Ingest --> PG
```

**How it works**: Curriculum PDFs are ingested through a 7-stage pipeline (extract → chunk → embed → store). Student/teacher queries hit the RAG pipeline, which classifies, retrieves, generates, and validates citations.

---

## Quick Start

```bash
git clone https://github.com/Rwanda-AI-Network/SomaAI.git
cd SomaAI
cp .env.example .env
# Set GROQ_API_KEY in .env (or LLM_BACKEND=mock with TESTING=1 for dev)
uv sync
make docker
```

App runs at http://localhost:8000 · Swagger at http://localhost:8000/docs

---

## Documentation

| Document | Description |
|----------|-------------|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design, module breakdown, data flow, request lifecycles |
| [INGESTION_PIPELINE.md](docs/INGESTION_PIPELINE.md) | 7-stage ingestion: extract → chunk → embed → store |
| [RETRIEVAL.md](docs/RETRIEVAL.md) | Dense retrieval, fallback strategy, reranker/BM25 status |
| [DEVELOPMENT.md](docs/DEVELOPMENT.md) | Local setup, environment variables, debugging, testing |
| [ROADMAP.md](docs/ROADMAP.md) | MVP status, prioritized improvements |
| [monitoring.md](docs/monitoring.md) | Prometheus metrics, alerts, and Grafana dashboards |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Branch strategy, commit conventions, PR process |
| [docs/api.md](docs/api.md) | API endpoint reference |
| [CHANGELOG.md](CHANGELOG.md) | Release history |
| [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) | Community guidelines |
| [SECURITY.md](SECURITY.md) | Security policy |

---

## API Overview

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/chat/ask` | POST | Ask a question (returns AI answer + citations) |
| `/api/v1/chat/messages/{id}` | GET | Get message details |
| `/api/v1/chat/messages/{id}/citations` | GET | Get source citations |
| `/api/v1/ingest` | POST | Upload and ingest a document |
| `/api/v1/ingest/jobs/{id}` | GET | Check ingestion job status |
| `/api/v1/quiz` | POST | Generate a quiz |
| `/api/v1/meta` | GET | Grades, subjects, topics (curriculum metadata) |
| `/api/v1/teacher` | CRUD | Teacher profile management |
| `/api/v1/feedback` | POST | Submit response rating |
| `/api/v1/docs/{id}/view` | GET | View document page |

---

## Project Structure

```bash
src/somaai/
├── api/v1/endpoints/   # FastAPI route handlers
├── contracts/          # Pydantic request/response schemas
├── db/                 # SQLAlchemy models, migrations
├── modules/
│   ├── chat/           # Chat service, citations, memory
│   ├── ingest/         # 7-stage ingestion pipeline
│   ├── knowledge/      # Embeddings, Qdrant store, BM25
│   ├── meta/           # Curriculum metadata service (cached)
│   ├── quiz/           # Quiz generation
│   └── rag/            # RAG pipeline, retriever, generator
├── providers/          # LLM, storage adapters
├── cache/              # Redis caching (embedding + response)
├── jobs/               # ARQ background job queue
├── monitoring.py       # Prometheus metrics
└── settings.py         # Environment config (pydantic-settings)
```

---

## License

[MIT](./LICENSE)
