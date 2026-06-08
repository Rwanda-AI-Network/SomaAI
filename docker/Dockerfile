# Build stage
FROM python:3.11-slim-bookworm AS builder

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set uv timeout to prevent build failures on heavy dependencies
ENV UV_HTTP_TIMEOUT=300 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copy dependency files first (better layer caching)
COPY pyproject.toml uv.lock* ./

# Install dependencies using cache mounts for faster builds
# We use --no-install-project because we haven't copied the source yet
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project \
    --extra cache \
    --extra vectordb \
    --extra pdf \
    --extra rag \
    --extra tasks \
    --extra scale

# Copy source code and alembic configuration
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY alembic.ini ./

# Install the project and pre-compile bytecode
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev \
    --extra cache \
    --extra vectordb \
    --extra pdf \
    --extra rag \
    --extra tasks \
    --extra scale

# Pre-download HuggingFace model to baked-in cache
ENV HF_HOME=/app/.cache/huggingface
RUN . /app/.venv/bin/activate && \
    python -c "from langchain_huggingface import HuggingFaceEmbeddings; HuggingFaceEmbeddings(model_name='all-MiniLM-L6-v2')"

# Production stage (minimal runtime)
FROM python:3.11-slim-bookworm AS production

WORKDIR /app

# Install only essential runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    tesseract-ocr \
    poppler-utils \
    tesseract-ocr-spa \
    tesseract-ocr-fra \
    tesseract-ocr-ara \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user for security
RUN groupadd --gid 1000 somaai && \
    useradd --uid 1000 --gid somaai --shell /bin/bash --create-home somaai

# Copy the virtual environment and app code from builder
COPY --from=builder --chown=somaai:somaai /app /app

# Set ownership and permissions if needed (already done by --chown in COPY)
# But let's ensure .cache is writable if models need to be updated or added
RUN chmod -R 755 /app/.cache

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    VIRTUAL_ENV="/app/.venv" \
    HF_HOME="/app/.cache/huggingface"

# Switch to non-root user
USER somaai

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose port
EXPOSE 8000

# Run directly with the venv's python/uvicorn
CMD ["uvicorn", "somaai.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
