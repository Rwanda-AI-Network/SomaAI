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

    # --- Automated Database Management ---
    if not settings.is_testing:
        from somaai.db.migrations.auto import run_auto_migrations
        from scripts.seed_meta import main as seed_main

        # Run Alembic migrations (Sync)
        run_auto_migrations()

        # Run Seeding (Async)
        await seed_main()
        startup_logger.info("Database schema and metadata are up to date.")
    else:
        # In tests, we still use create_all for speed (with aiosqlite memory)
        await init_db()

    # Security audit: warn if API key auth is disabled in non-debug mode
    if not settings.require_api_key and not settings.debug:
        startup_logger.warning(
            "⚠️  API key authentication is DISABLED in non-debug mode. "
            "Set REQUIRE_API_KEY=true for production deployments."
        )

    if not settings.is_testing:
        get_embeddings_model(settings)
        # Use fallback_to_mock in debug mode to avoid startup crashes
        app.state.llm = get_llm(settings, fallback_to_mock=settings.debug)
    else:
        # In tests, use MockLLMProvider to avoid external calls
        from somaai.providers.llm import MockLLMProvider

        app.state.llm = MockLLMProvider()

    # Initialize Prometheus metrics (gated by enable_metrics setting)
    if settings.enable_metrics:
        from somaai.monitoring import setup_metrics

        setup_metrics(settings)

    try:
        yield
    finally:
        await close_db()
        # Close Qdrant connection pool
        try:
            from somaai.modules.knowledge.stores.qdrant import close_qdrant_client

            close_qdrant_client()
        except Exception:
            pass
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

    # Add custom error handlers
    _setup_error_handlers(app)

    app.include_router(health_router)
    app.include_router(api_router, prefix="/api")

    # Add Prometheus metrics instrumentation (only when enabled)
    if settings.enable_metrics:
        try:
            from prometheus_fastapi_instrumentator import Instrumentator

            Instrumentator().instrument(app).expose(app, endpoint="/metrics")
        except ImportError:
            pass  # Optional dependency

    return app


def _setup_error_handlers(app: FastAPI) -> None:
    """Setup custom error handlers for the application."""
    from fastapi.responses import JSONResponse
    from starlette.requests import Request

    # Rate limit error handler
    try:
        from slowapi.errors import RateLimitExceeded

        @app.exception_handler(RateLimitExceeded)
        async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
            """Custom handler for rate limit errors."""
            return JSONResponse(
                status_code=429,
                content={
                    "detail": (
                        "Too many requests. Please wait a moment before trying again. "
                        "This helps us maintain quality service for all users."
                    )
                },
            )
    except ImportError:
        pass  # slowapi not installed
