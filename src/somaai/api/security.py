"""API security middleware for authentication and rate limiting.

Provides:
- API key authentication
- Rate limiting per client
- Request logging
"""

from __future__ import annotations

import hashlib
import time
from collections import defaultdict
from collections.abc import Callable
from functools import wraps

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader

# API key header
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


class RateLimiter:
    """In-memory rate limiter for API endpoints.

    Uses sliding window algorithm for accurate rate limiting.
    For production, consider Redis-based implementation.
    """

    def __init__(self):
        """Initialize rate limiter."""
        # {client_id: [(timestamp, count), ...]}
        self._requests: dict[str, list[tuple[float, int]]] = defaultdict(list)
        self._window_size = 60  # 1 minute window

    def is_allowed(
        self,
        client_id: str,
        limit: int,
        window_seconds: int = 60,
    ) -> tuple[bool, int]:
        """Check if request is allowed under rate limit.

        Args:
            client_id: Unique client identifier (IP or API key hash)
            limit: Maximum requests per window
            window_seconds: Window size in seconds

        Returns:
            Tuple of (is_allowed, remaining_requests)
        """
        now = time.time()
        window_start = now - window_seconds

        # Clean old entries
        self._requests[client_id] = [
            (ts, count) for ts, count in self._requests[client_id] if ts > window_start
        ]

        # Count requests in window
        total = sum(count for _, count in self._requests[client_id])

        if total >= limit:
            return False, 0

        # Record this request
        self._requests[client_id].append((now, 1))

        return True, limit - total - 1

    def reset(self, client_id: str) -> None:
        """Reset rate limit for a client."""
        self._requests.pop(client_id, None)


# Global rate limiter instance
_rate_limiter = RateLimiter()


def get_rate_limiter() -> RateLimiter:
    """Get the global rate limiter instance."""
    return _rate_limiter


class APIKeyAuth:
    """API key authentication handler.

    Validates API keys against configured keys.
    """

    def __init__(self):
        """Initialize auth handler."""
        self._valid_keys: set[str] = set()
        self._key_metadata: dict[str, dict] = {}

    def add_key(self, key: str, metadata: dict | None = None) -> None:
        """Add a valid API key.

        Args:
            key: The API key
            metadata: Optional metadata (user_id, permissions, etc.)
        """
        key_hash = self._hash_key(key)
        self._valid_keys.add(key_hash)
        if metadata:
            self._key_metadata[key_hash] = metadata

    def validate_key(self, key: str | None) -> dict | None:
        """Validate an API key.

        Args:
            key: The API key to validate

        Returns:
            Key metadata if valid, None if invalid
        """
        if not key:
            return None

        key_hash = self._hash_key(key)
        if key_hash in self._valid_keys:
            return self._key_metadata.get(key_hash, {"valid": True})

        return None

    def _hash_key(self, key: str) -> str:
        """Hash an API key for storage."""
        return hashlib.sha256(key.encode()).hexdigest()


# Global auth instance
_api_key_auth = APIKeyAuth()


def get_api_key_auth() -> APIKeyAuth:
    """Get the global API key auth instance."""
    return _api_key_auth


def get_client_id(request: Request) -> str:
    """Get unique client identifier from request.

    Uses API key if present, otherwise IP address.
    """
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return f"key:{hashlib.sha256(api_key.encode()).hexdigest()[:16]}"

    # Fall back to IP
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    else:
        ip = request.client.host if request.client else "unknown"

    return f"ip:{ip}"


async def verify_api_key(
    request: Request,
    api_key: str | None = Security(API_KEY_HEADER),
) -> dict:
    """Dependency for API key verification.

    Args:
        request: FastAPI request
        api_key: API key from header

    Returns:
        Key metadata if valid

    Raises:
        HTTPException: If key is missing or invalid
    """
    from somaai.settings import settings

    # Skip auth if disabled (development mode)
    if not settings.require_api_key:
        return {"user": "anonymous", "authenticated": False}

    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="API key required. Include X-API-Key header.",
        )

    auth = get_api_key_auth()
    metadata = auth.validate_key(api_key)

    if not metadata:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key",
        )

    return metadata


def rate_limit(
    limit: int = 60,
    window_seconds: int = 60,
    key_func: Callable[[Request], str] = get_client_id,
):
    """Rate limiting decorator for FastAPI endpoints.

    Args:
        limit: Maximum requests per window
        window_seconds: Window size in seconds
        key_func: Function to extract client identifier

    Returns:
        Decorator function
    """

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            client_id = key_func(request)
            limiter = get_rate_limiter()

            allowed, remaining = limiter.is_allowed(client_id, limit, window_seconds)

            if not allowed:
                raise HTTPException(
                    status_code=429,
                    detail=(
                        f"Rate limit exceeded. Try again in {window_seconds} seconds."
                    ),
                    headers={
                        "Retry-After": str(window_seconds),
                        "X-RateLimit-Limit": str(limit),
                        "X-RateLimit-Remaining": "0",
                    },
                )

            # Add rate limit headers to response
            response = await func(request, *args, **kwargs)
            return response

        return wrapper

    return decorator


async def check_rate_limit(
    request: Request,
    limit: int = 60,
    window_seconds: int = 60,
) -> None:
    """Check rate limit for a request.

    Args:
        request: FastAPI request
        limit: Maximum requests per window
        window_seconds: Window size in seconds

    Raises:
        HTTPException: If rate limit exceeded
    """
    client_id = get_client_id(request)
    limiter = get_rate_limiter()

    allowed, remaining = limiter.is_allowed(client_id, limit, window_seconds)

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=(f"Rate limit exceeded. Try again in {window_seconds} seconds."),
            headers={
                "Retry-After": str(window_seconds),
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
            },
        )
