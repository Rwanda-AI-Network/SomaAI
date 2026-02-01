"""Application middleware."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)


def setup_middleware(app: FastAPI) -> None:
    """Set up application middleware."""
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Rate limiting with slowapi (Redis-backed for horizontal scaling)
    try:
        from slowapi import Limiter, _rate_limit_exceeded_handler
        from slowapi.errors import RateLimitExceeded
        from slowapi.middleware import SlowAPIMiddleware
        from slowapi.util import get_remote_address

        # Try to use Redis storage for distributed rate limiting
        try:
            from slowapi.extension import LimiterMiddlewareWithStorage

            from somaai.settings import settings

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

