"""FastAPI application factory."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from somaai.api.router import api_router
from somaai.db.session import close_db, init_db
from somaai.health import health_router
from somaai.middleware import setup_middleware
from somaai.modules.knowledge.embeddings import get_embeddings as get_embeddings_model
from somaai.providers.llm import get_llm
from somaai.settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan."""
    import logging

    startup_logger = logging.getLogger("somaai.startup")

    # Initialize database tables (for development)
    await init_db()

    # Security audit: warn if API key auth is disabled in non-debug mode
    if not settings.require_api_key and not settings.debug:
        startup_logger.warning(
            "⚠️  API key authentication is DISABLED in non-debug mode. "
            "Set REQUIRE_API_KEY=true for production deployments."
        )

    # Pre-load embeddings model to avoid first-request latency
    # Skip during tests — model download hangs test setup
    import os

    if not os.getenv("TESTING"):
        get_embeddings_model(settings)
        app.state.llm = get_llm(settings)
    else:
        # In tests, use MockLLMProvider to avoid external calls
        from somaai.providers.llm import MockLLMProvider

        app.state.llm = MockLLMProvider()

    # Update feature flag metrics
    try:
        from somaai.monitoring import update_feature_flags

        update_feature_flags(settings)
    except ImportError:
        pass  # Monitoring not available

    try:
        yield
    finally:
        await close_db()
        app.state.llm = None


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    from somaai.logging_conf import setup_logging

    setup_logging()

    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        debug=settings.debug,
        lifespan=lifespan,
    )

    setup_middleware(app)
    app.include_router(health_router)
    app.include_router(api_router, prefix="/api")

    # Add Prometheus metrics instrumentation
    try:
        from prometheus_fastapi_instrumentator import Instrumentator

        Instrumentator().instrument(app).expose(app, endpoint="/metrics")
    except ImportError:
        pass  # Optional dependency

    return app
