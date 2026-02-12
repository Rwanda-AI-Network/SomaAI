"""Health check endpoint."""

from fastapi import APIRouter

health_router = APIRouter(tags=["health"])


@health_router.get("/health")
async def health_check() -> dict:
    """Check application health."""
    return {"status": "healthy"}
