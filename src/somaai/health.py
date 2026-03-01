"""Health check endpoint."""

from typing import Any

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from somaai.db.session import async_session_maker
from somaai.modules.knowledge.stores.qdrant import get_qdrant_client
from somaai.settings import settings

health_router = APIRouter(tags=["health"])


@health_router.get("/health")
async def health_check(response: Response) -> dict:
    """Deep health check verifying critical dependencies.

    Checks PostgreSQL and Qdrant connectivity.
    """
    health_status: dict[str, Any] = {
        "status": "healthy",
        "version": settings.version,
        "components": {"database": "unknown", "qdrant": "unknown"},
    }

    # 1. Check PostgreSQL
    try:
        async with async_session_maker() as session:
            # Low-cost ping
            await session.execute(text("SELECT 1"))
            health_status["components"]["database"] = "healthy"
    except Exception as e:
        health_status["components"]["database"] = f"unhealthy: {str(e)}"
        health_status["status"] = "unhealthy"

    # 2. Check Qdrant
    try:
        client = get_qdrant_client(settings)
        # Simple list_collections check is low-cost and verifies API auth+network
        client.get_collections()
        health_status["components"]["qdrant"] = "healthy"
    except Exception as e:
        health_status["components"]["qdrant"] = f"unhealthy: {str(e)}"
        health_status["status"] = "unhealthy"

    # Set 503 if any component is failing (production standard)
    if health_status["status"] != "healthy":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return health_status
