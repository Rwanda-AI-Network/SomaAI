# Build stage
FROM python:3.11-slim AS builder

WORKDIR /app

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set uv timeout to prevent build failures on heavy dependencies
ENV UV_HTTP_TIMEOUT=300

# Copy dependency files first (better layer caching)
COPY pyproject.toml uv.lock* alembic.ini ./

# Create virtual environment and install dependencies
# Using selective extras instead of --all-extras for lighter builds
RUN uv venv /app/.venv && \
    . /app/.venv/bin/activate && \
    uv sync --frozen --no-dev --no-install-project \
    --extra cache \
    --extra vectordb \
    --extra pdf \
    --extra rag \
    --extra tasks

# Copy source code
COPY src/ ./src/

# Install the project itself
RUN . /app/.venv/bin/activate && \
    uv sync --frozen --no-dev --all-extras

# Production stage (minimal runtime)
FROM python:3.11-slim AS production

WORKDIR /app

# Install only essential runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    tesseract-ocr \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user for security
RUN groupadd --gid 1000 somaai && \
    useradd --uid 1000 --gid somaai --shell /bin/bash --create-home somaai

# Copy only the virtual environment from builder (no uv needed at runtime)
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=builder /app/alembic.ini /app/alembic.ini

# Set ownership to non-root user
RUN chown -R somaai:somaai /app

# Switch to non-root user
USER somaai

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    VIRTUAL_ENV="/app/.venv"

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose port
EXPOSE 8000

# Run directly with the venv's python/uvicorn - no uv needed
CMD ["uvicorn", "somaai.main:app", "--host", "0.0.0.0", "--port", "8000"]
