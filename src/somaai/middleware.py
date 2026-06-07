"""Application middleware."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from somaai.settings import settings

logger = logging.getLogger(__name__)


def setup_middleware(app: FastAPI) -> None:
    """Set up application middleware."""

    # Handle CORS with an architectural decision for development vs production:
    # If allow_origins contains "*", we use allow_origin_regex to support credentials.
    cors_params = {
        "allow_credentials": True,
        "allow_methods": ["*"],
        "allow_headers": ["*"],
    }

    if "*" in settings.cors_allowed_origins:
        # Standard FastAPI/Starlette CORSMiddleware doesn't allow "*" with allow_credentials=True.
        # We use a broad regex but explicitly allow local origins for Swagger/tools.
        cors_params["allow_origin_regex"] = "https?://(localhost|127\.0\.0\.1)(:[0-9]+)?.*"
        cors_params["allow_origins"] = ["http://localhost", "http://localhost:8000", "http://127.0.0.1:8000"]
    else:
        cors_params["allow_origins"] = settings.cors_allowed_origins

    app.add_middleware(CORSMiddleware, **cors_params)

    # Rate limiting with slowapi (Redis-backed for horizontal scaling)
    try:
        from slowapi import Limiter, _rate_limit_exceeded_handler
        from slowapi.errors import RateLimitExceeded
        from slowapi.middleware import SlowAPIMiddleware
        from slowapi.util import get_remote_address

        # Try to use Redis storage for distributed rate limiting
        try:
            import os

            if os.getenv("TESTING"):
                raise ImportError("Skip Redis in tests")

            # Redis-backed storage for horizontal scaling
            limiter = Limiter(
                key_func=get_remote_address,
                storage_uri=settings.redis_url,
                default_limits=["200/minute"],
            )
            logger.info("Rate limiting enabled with Redis storage")
        except Exception as e:
            # Fallback to in-memory if Redis unavailable
            limiter = Limiter(
                key_func=get_remote_address,
                default_limits=["200/minute"],
            )
            logger.warning(f"Rate limiting using in-memory storage: {e}")

        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
        app.add_middleware(SlowAPIMiddleware)

    except ImportError:
        logger.info("slowapi not installed, rate limiting disabled")

    # Architectural Hardening: Request ID for log correlation
    @app.middleware("http")
    async def add_request_id(request, call_next):
        import uuid

        from somaai.utils.logging_ext import request_id_ctx, set_request_id

        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        token = set_request_id(request_id)

        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            request_id_ctx.reset(token)

    logger.info("Operational hardening: Middleware chain complete")
