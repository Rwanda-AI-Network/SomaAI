"""FastAPI application factory."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from somaai.api.router import api_router
from somaai.db.session import close_db, init_db
from somaai.health import health_router
from somaai.middleware import setup_middleware
from somaai.modules.knowledge.stores.qdrant import get_embeddings_model
from somaai.providers.llm import get_llm
from somaai.settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan."""
    # Initialize database tables (for development)
    await init_db()

    # Pre-load embeddings model to avoid first-request latency
    get_embeddings_model(settings)

    ## We create the LLM instance here to ensure it's ready when needed.
    app.state.llm = get_llm(settings)

    try:
        yield
    finally:
        await close_db()
        app.state.llm = None


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
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
