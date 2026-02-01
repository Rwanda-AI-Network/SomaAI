
# SomaAI

SomaAI is an open-source, AI-powered learning platform designed to improve teaching and learning across Rwanda.

It helps **students** understand curriculum topics using official learning materials, and helps **teachers** generate quizzes, explanations, and teaching support faster and more accurately.

The platform is built around **Retrieval-Augmented Generation (RAG)** using official curriculum documents (REB materials).

---

## Project Status

🚧 **Active MVP Development**

- Core architecture is in place
- API contracts are being stabilized
- Mock LLM mode is supported (no API keys needed)
- Business logic modules are under active development
- Expect breaking changes until `v1.0`

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Features

### Student Mode
- Grade + subject-aware question answering
- AI-generated explanations with citations (document + page numbers)
- Optional analogies and real-world examples
- Designed for self-study and exam preparation

### Teacher Mode
- Teacher-optimized defaults (analogies + real-world examples enabled by default)
- Quiz generation from curriculum topics
- Difficulty and number-of-questions control
- Download quizzes (questions only or with answer keys)
- Feedback system to improve answer quality

### Core Capabilities
- RAG-based retrieval from official curriculum documents
- Caching for repeated questions
- Multi-language support (English now, Kinyarwanda & French in progress)

---

## Tech Stack

| Component | Technology |
|---------|------------|
| Backend | FastAPI (Python 3.10+) |
| Database | PostgreSQL |
| Vector Store | Qdrant |
| Cache / Queue | Redis |
| Package Manager | uv |
| Migrations | Alembic |

---

## Quick Start

### Prerequisites
- Python 3.10+
- uv package manager
- Docker (recommended)

### Installation

```bash
git clone https://github.com/Rwanda-AI-Network/SomaAI.git
cd SomaAI

cp .env.example .env
uv sync
```

### Mock LLM Mode (No API Keys Required)

- By default, SomaAI runs with a Mock LLM provider.

- Set `LLM_BACKEND=mock` in your `.env` file.


- This allows:
    - Local development
    - CI execution
    - Contributor onboarding without paying for LLM tokens.


### Running with Docker (Recommended)

```bash
# Start all services (app + postgres + redis + qdrant)
make docker # Recommended

# Or use docker-compose directly
docker-compose -f docker/docker-compose.yml up --build
```

**Services started:**
- App: http://localhost:8000
- PostgreSQL: localhost:5432
- Redis: localhost:6379
- Qdrant: http://localhost:6333/dashboard

### Running Locally

```bash
# Ensure external services are running (postgres, redis, qdrant)
# Then start the dev server
make dev
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/chat/ask` | POST | Ask a question (student/teacher) |
| `/api/v1/chat/messages/{id}` | GET | Get message details |
| `/api/v1/chat/messages/{id}/citations` | GET | Get source citations |
| `/api/v1/meta/grades` | GET | List grade levels |
| `/api/v1/meta/subjects` | GET | List subjects |
| `/api/v1/meta/topics` | GET | List curriculum topics |
| `/api/v1/teacher/profile` | GET/POST | Teacher profile settings |
| `/api/v1/quiz/generate` | POST | Generate quiz |
| `/api/v1/quiz/{id}` | GET | Get quiz details |
| `/api/v1/quiz/{id}/download` | GET | Download quiz as PDF |
| `/api/v1/docs/{id}` | GET | Get document metadata |
| `/api/v1/docs/{id}/view` | GET | View document page |
| `/api/v1/ingest` | POST | Upload curriculum document |
| `/api/v1/feedback` | POST | Submit response feedback |

## Development

Run `make help` to see all available commands.
```bash
    make help
```

## Project Structure

```
src/somaai/
├── api/v1/endpoints/  # REST API endpoints
├── contracts/         # Pydantic request/response schemas
├── cache/             # Redis caching layer
├── db/                # SQLAlchemy models & migrations
├── jobs/              # Background job queue
├── modules/
│   ├── chat/          # Chat with citations
│   ├── docs/          # Document viewing
│   ├── feedback/      # Response ratings
│   ├── ingest/        # Document ingestion
│   ├── meta/          # Grades, subjects, topics
│   ├── quiz/          # Quiz generation
│   ├── rag/           # Retrieval & generation
│   ├── teacher/       # Teacher profiles
│   └── knowledge/     # Embeddings & vector storage
├── providers/         # LLM, storage adapters
└── tests/             # Test suite
```

## Database

**Development:** PostgreSQL via Docker
```bash
# Included in docker-compose
make docker
```

**Production:** [NeonDB](https://neon.tech) (Serverless PostgreSQL)
```bash
# Set in .env
DATABASE_URL=postgresql+asyncpg://user:pass@ep-xxx.neon.tech/somaai
```

## Documentation

- [API Documentation](docs/api.md) or (Swagger UI: http://localhost:8000/docs)
- [Architecture Overview](docs/architecture.md)
- [Contributing Guide](CONTRIBUTING.md)

## License

Apache-2.0 license - see [LICENSE](LICENSE) for details.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines.
