# Contributing to SomaAI

Thank you for your interest in contributing to SomaAI.
This document explains how to work on the project safely and efficiently.


## Project Philosophy

- Contracts first (Pydantic schemas are the source of truth)
- Database-backed features
- Mock-first development (no API keys required)
- Small, focused pull requests
- One issue = one PR



## Getting Started

### Prerequisites

- Python 3.10 or higher
- [uv](https://github.com/astral-sh/uv) package manager
- Docker (recommended for full development environment)

### Local Development Setup

**Option 1: Full Stack with Docker (Recommended)**

```bash
# Clone and enter the repository
git clone https://github.com/Rwanda-AI-Network/SomaAI.git
cd SomaAI

# Copy environment variables
cp .env.example .env

uv sync

# Start all services (postgres, redis, qdrant, app)
make docker
```

This starts:
- PostgreSQL on `localhost:5432`
- Redis on `localhost:6379`
- Qdrant on `http://localhost:6333`
- App on `http://localhost:8000`

**Option 2: Local Python Development**

```bash
# Install dependencies
make install

# Or with all optional dependencies
uv sync --extra all

# Start external services separately, then:
make dev
```

### Initial Setup (After Clone)

```bash
# Apply database migrations
.venv/bin/python -m alembic upgrade head

# Seed grades and subjects
make seed-meta
```

This creates the initial data (P6, S1-S6 grades and subjects like Computer Science, Mathematics, etc.).

### Mock LLM Mode

The project runs in mock mode by default:

```bash
# Set LLM_BACKEND=mock in .env
```
No LLM API keys are required for development.

### MVP Identification (No Auth)

For MVP development, we use headers instead of authentication:

| Role | Header | Usage |
|------|--------|-------|
| Student | `X-Actor-Id` | Optional, frontend-generated UUID |
| Teacher | `X-Teacher-Id` | Required for teacher endpoints |

Example:
```bash
curl -X POST http://localhost:8000/api/v1/chat/ask \
  -H "Content-Type: application/json" \
  -H "X-Actor-Id: student_abc123" \
  -d '{"query": "What is a variable?", "grade": "S1", "subject": "computer_science", "user_role": "student"}'
```

### Issue Workflow (IMPORTANT)

   - All work must start from an issue
   - One issue = one pull request
   - Reference the issue number in your PR title

Example:

```bash
feat(chat): implement ask endpoint (#12)
```


<!-- ### Branch Naming

   - feature/chat-service
   - feature/quiz-generator
   - fix/citation-order
   - docs/readme-update -->

### Development Rules

- You MAY change

   - Business logic in modules/
   - Endpoint implementations
   - Tests
   - Documentation

- You MUST NOT change without approval

   - API contracts (contracts/)
   - Database models (db/models.py)
   - Global settings structure


### Development Workflow

#### Branch Naming

Use descriptive branch names:
- `feature/add-quiz-generation` - New features
- `fix/retrieval-accuracy` - Bug fixes
- `docs/api-documentation` - Documentation updates

### Making Changes

1. Create a new branch from `main`
2. Make your changes
3. Run linting and tests:

   ```bash
   make lint
   make test
   ```
4. Commit your changes with a clear message
5. Push and open a Pull Request


### Adding a New Endpoint

1. Create schema in `contracts/`
2. Create service in `modules/{module}/service.py`
3. Create endpoint in `api/v1/endpoints/{module}.py`
4. Register router in `api/v1/router.py`
5. Add tests in `tests/test_{module}.py`

### Code Style

We use Ruff and MyPy.

```bash
# Check linting
make lint

# Or directly
uv run ruff check src/
uv run ruff format src/
```

### Testing

```bash
# Run all tests
make test

# Run specific test file
uv run pytest src/somaai/tests/test_chat.py -v

# Run with coverage
uv run pytest --cov=somaai
```

### Database Migrations

We use Alembic.

```bash
uv run alembic revision --autogenerate -m "Add new table"
uv run alembic upgrade head
```

### Adding a New Feature

   - Check existing API contracts
   - Implement logic in modules/
   - Wire endpoint in api/v1/endpoints/
   - Add tests
   - Open a pull request

Note: Copilot code review may leave automated suggestions on pull requests. These are advisory and do not replace human code review or approval.

### Educational Content Rules

   - Must align with REB curriculum
   - Avoid hallucinated facts
   - Prefer document-backed answers
   - Be age-appropriate


### Adding a New Module

```
modules/new_module/
├── __init__.py      # Exports
├── service.py       # Business logic
└── (other files)    # As needed
```

## Pull Request Guidelines

Before submitting a PR:

- [ ] Code follows the project style guidelines (ruff passes)
- [ ] All tests pass locally
- [ ] New functionality includes tests
- [ ] Documentation is updated if needed
- [ ] PR description clearly explains the changes

### Educational Content Guidelines

When contributing features that affect educational content:

- Ensure alignment with Rwanda Education Board (REB) curriculum standards
- Test with both English and Kinyarwanda content where applicable
- Consider accessibility for all students and teachers

## Reporting Issues

When reporting bugs, please include:

- Steps to reproduce the issue
- Expected vs actual behavior
- Environment details (OS, Python version, Docker version)
- Relevant logs or error messages

### Available Make Commands

| Command | Description |
|---------|-------------|
| `make help` | Show all available commands |
| `make install` | Install dependencies with uv |
| `make dev` | Run development server |
| `make lint` | Run linting (ruff + mypy) |
| `make test` | Run tests |
| `make docker` | Run with Docker (postgres + redis + qdrant) |
| `make docker-stop` | Stop Docker containers |
| `make seed-meta` | Seed grades and subjects |
| `make clean` | Clean build artifacts |

## Database Strategy

| Environment | Database |
|-------------|----------|
| Development | PostgreSQL (Docker) |
| Production | NeonDB (serverless Postgres) |

Both use the same SQLAlchemy models and Alembic migrations.

## Questions?

For questions or discussions, please open an issue or reach out to the maintainers.

## License

By contributing, you agree that your contributions will be licensed under the Apache-2.0 license.
