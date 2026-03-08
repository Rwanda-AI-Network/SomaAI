"""Application middleware."""

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)


def _get_actor_id_or_ip(request: Request) -> str:
    """Rate-limit key function: actor_id if available, else IP.

    This ensures rate limits apply per-user when the session middleware
    has run, and falls back to IP for pre-session routes.
    """
    actor_id = getattr(request.state, "actor_id", None)
    if actor_id:
        return actor_id
    return request.client.host if request.client else "unknown"


def setup_middleware(app: FastAPI) -> None:
    """Set up application middleware."""

    # 1. Session middleware (must be first so actor_id is available)
    from somaai.middleware.session import SessionMiddleware
    from somaai.settings import settings

    app.add_middleware(
        SessionMiddleware,
        cookie_secure=settings.security.session_cookie_secure,
        session_ttl_seconds=settings.security.session_ttl_days * 24 * 60 * 60,
    )

    # 2. CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=".*",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 3. Rate limiting with slowapi (Redis-backed for horizontal scaling)
    try:
        from slowapi import Limiter, _rate_limit_exceeded_handler
        from slowapi.errors import RateLimitExceeded
        from slowapi.middleware import SlowAPIMiddleware

        # Try Redis storage for distributed rate limiting
        try:
            from somaai.settings import AppEnv, settings

            if settings.env == AppEnv.TESTING:
                raise ImportError("Skip Redis in tests")

            limiter = Limiter(
                key_func=_get_actor_id_or_ip,
                storage_uri=settings.redis.url,
                default_limits=["100/minute"],
            )
            logger.info("Rate limiting enabled (Redis, actor_id key)")
        except Exception as e:
            # Fallback to in-memory if Redis unavailable
            limiter = Limiter(
                key_func=_get_actor_id_or_ip,
                default_limits=["100/minute"],
            )
            logger.warning("Rate limiting in-memory: %s", e)

        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
        app.add_middleware(SlowAPIMiddleware)

    except ImportError:
        logger.info("slowapi not installed, rate limiting disabled")

    # 4. Global error handler
    from somaai.middleware.error_handler import register_error_handlers

    register_error_handlers(app)

    # 5. Request ID for log correlation
    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
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

    logger.info("Middleware chain complete")
