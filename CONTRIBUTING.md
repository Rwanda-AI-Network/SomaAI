# Contributing to SomaAI

Thank you for your interest in contributing to SomaAI. This document explains branching strategy, pull request process, coding standards, and commit conventions.

For local setup instructions, see [DEVELOPMENT.md](DEVELOPMENT.md).

---

## Project Philosophy

- **Contracts first** — Pydantic schemas are the source of truth for API boundaries
- **Database-backed features** — State belongs in PostgreSQL, not in memory
- **Mock-first development** — No API keys required (`LLM_BACKEND=mock`)
- **Small, focused pull requests** — One issue = one PR
- **Document-backed answers** — Educational content must come from ingested REB materials

---

## Issue Workflow

All work must start from an issue.

1. Find an existing issue or open a new one describing the change
2. Get assigned (comment on the issue to claim it)
3. One issue = one pull request
4. Reference the issue number in your PR title

---

## Branching Strategy

### Branch Naming

Use the format `type/short-description`:

| Type | Use Case | Example |
|------|----------|---------|
| `feature/` | New functionality | `feature/quiz-generation` |
| `fix/` | Bug fixes | `fix/retrieval-accuracy` |
| `docs/` | Documentation updates | `docs/api-reference` |
| `refactor/` | Code restructuring | `refactor/pipeline-stages` |
| `test/` | Adding or fixing tests | `test/chat-endpoint` |

### Workflow

```
main
 └── feature/add-quiz-generation   ← your branch
      └── (squash merge back to main)
```

1. Create a branch from `main`
2. Make your changes
3. Open a PR targeting `main`
4. After review and CI pass, squash-merge

---

## Commit Conventions

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description> (#issue)
```

### Types

| Type | When to Use |
|------|-------------|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `refactor` | Code change that neither fixes a bug nor adds a feature |
| `test` | Adding or updating tests |
| `chore` | Build, CI, or tooling changes |
| `perf` | Performance improvement |

### Scopes

Use the module name as scope: `chat`, `rag`, `ingest`, `quiz`, `meta`, `teacher`, `feedback`, `docs`, `api`, `db`, `cache`, `jobs`.

### Examples

```
feat(chat): implement ask endpoint (#12)
fix(rag): correct fallback filter logic (#45)
docs(readme): add architecture diagram
refactor(ingest): extract quality filter to stage
test(quiz): add generation edge cases (#33)
chore(ci): add lint step to workflow
```

---

## Pull Request Process

### Before Submitting

- [ ] Code follows project style guidelines (`make lint` passes)
- [ ] All tests pass locally (`make test`)
- [ ] New functionality includes tests
- [ ] Documentation is updated if needed
- [ ] PR description clearly explains the changes and links the issue

### PR Title Format

```
type(scope): description (#issue-number)
```

Example: `feat(chat): implement ask endpoint (#12)`

### Review Process

1. Open your PR — CI runs automatically (lint + tests)
2. A maintainer will review within 48 hours
3. Address review feedback with fixup commits
4. Once approved, the PR will be squash-merged by a maintainer

> **Note:** Copilot code review may leave automated suggestions on PRs. These are advisory and do not replace human review.

---

## What You May and May Not Change

### You MAY change without prior approval

- Business logic in `modules/`
- Endpoint implementations in `api/v1/endpoints/`
- Tests
- Documentation

### You MUST get maintainer approval before changing

- API contracts (`contracts/`) — these are shared interfaces
- Database models (`db/models.py`) — requires migration coordination
- Global settings structure (`settings.py`)
- CI/CD workflows (`.github/workflows/`)

---

## Coding Standards

### Tooling

| Tool | Purpose | Command |
|------|---------|---------|
| [Ruff](https://docs.astral.sh/ruff/) | Linting + formatting | `make lint` |
| [MyPy](https://mypy.readthedocs.io/) | Type checking | `uv run mypy src/` |
| [pytest](https://docs.pytest.org/) | Testing | `make test` |

### Style Rules

- Use type hints on all function signatures
- Use `from __future__ import annotations` for forward references
- Prefer `async` functions for I/O-bound operations
- Use structured logging (`logger.info(...)`) over `print()`
- Follow existing module patterns — check a similar module before creating a new one

### Adding a New Module

```
modules/new_module/
├── __init__.py      # Exports
├── service.py       # Business logic
└── (other files)    # As needed
```

Then:

1. Create request/response schema in `contracts/`
2. Create service in `modules/{module}/service.py`
3. Create endpoint in `api/v1/endpoints/{module}.py`
4. Register the router in `api/v1/router.py`
5. Add tests in `tests/test_{module}.py`

### Adding a New Endpoint

Follow the same 5-step process above. The contract (Pydantic schema) always comes first.

---

## Educational Content Guidelines

When contributing features that affect educational content:

- Ensure alignment with Rwanda Education Board (REB) curriculum standards
- Avoid hallucinated facts — prefer document-backed answers
- Test with both English and Kinyarwanda content where applicable
- Be age-appropriate for the target grade level (P6 through S6)

---

## Reporting Issues

When reporting bugs, include:

- Steps to reproduce
- Expected vs actual behavior
- Environment details (OS, Python version, Docker version)
- Relevant logs or error messages (use `docker logs somaai-app` for container logs)

---

## License

By contributing, you agree that your contributions will be licensed under the [Apache-2.0 license](LICENSE).
