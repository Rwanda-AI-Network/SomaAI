"""Cookie-based session middleware for server-controlled identity.

Creates and maintains anonymous sessions via HttpOnly cookies.
Sessions are stored in Redis (production) or an in-memory dict (tests).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

# Cookie configuration
COOKIE_NAME = "somaai_session"
COOKIE_MAX_AGE = 90 * 24 * 60 * 60  # 90 days in seconds

# Routes that skip session middleware entirely
_SKIP_PREFIXES = ("/health", "/docs", "/openapi.json", "/redoc", "/metrics")

# In-memory session store for testing (no Redis dependency)
_memory_store: dict[str, dict[str, Any]] = {}


def _generate_session_token() -> str:
    """Generate a cryptographically random session token."""
    return uuid.uuid4().hex


def _generate_actor_id() -> str:
    """Generate a server-controlled anonymous actor ID."""
    return f"anon_{uuid.uuid4().hex[:12]}"


class SessionMiddleware(BaseHTTPMiddleware):
    """Middleware that manages anonymous sessions via HttpOnly cookies.

    On each request:
    1. Read the ``somaai_session`` cookie
    2. Look up session data in the backing store (Redis or memory)
    3. If valid → hydrate ``request.state`` with session data
    4. If missing/invalid → create new session, set cookie on response

    Attaches to ``request.state``:
        - ``actor_id``: str — server-generated identity
        - ``session_token``: str — opaque session key
        - ``is_authenticated``: bool — always False for MVP
        - ``user_id``: str | None — always None for MVP
    """

    def __init__(
        self,
        app,
        *,
        redis_client=None,
        cookie_secure: bool = True,
        session_ttl_seconds: int = COOKIE_MAX_AGE,
    ) -> None:
        super().__init__(app)
        self._redis = redis_client
        self._cookie_secure = cookie_secure
        self._session_ttl = session_ttl_seconds
        self._use_memory = redis_client is None

        if self._use_memory:
            logger.info("SessionMiddleware using in-memory store (no Redis)")
        else:
            logger.info("SessionMiddleware using Redis store")

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Process request: validate/create session, then continue."""
        # Skip non-API routes
        path = request.url.path
        if any(path.startswith(prefix) for prefix in _SKIP_PREFIXES):
            return await call_next(request)

        token = request.cookies.get(COOKIE_NAME)
        session_data = None

        # Try to load existing session
        if token:
            session_data = await self._get_session(token)

        need_new_cookie = False

        if session_data:
            # Valid session — hydrate request state
            request.state.actor_id = session_data["actor_id"]
            request.state.session_token = token
            request.state.is_authenticated = session_data.get("is_authenticated", False)
            request.state.user_id = session_data.get("user_id")
        else:
            # New session needed
            token = _generate_session_token()
            actor_id = _generate_actor_id()

            session_data = {
                "actor_id": actor_id,
                "is_authenticated": False,
                "user_id": None,
            }
            await self._set_session(token, session_data)

            request.state.actor_id = actor_id
            request.state.session_token = token
            request.state.is_authenticated = False
            request.state.user_id = None
            need_new_cookie = True

            logger.debug(
                "Created new session for actor %s",
                actor_id,
                extra={"actor_id": actor_id},
            )

        # Set actor_id context var for structured logging
        from somaai.utils.logging_ext import set_actor_id

        actor_token = set_actor_id(request.state.actor_id)

        try:
            response = await call_next(request)
        finally:
            from somaai.utils.logging_ext import actor_id_ctx

            actor_id_ctx.reset(actor_token)

        if need_new_cookie:
            response.set_cookie(
                key=COOKIE_NAME,
                value=token,
                max_age=self._session_ttl,
                httponly=True,
                secure=self._cookie_secure,
                samesite="lax",
                path="/api",
            )

        return response

    async def _get_session(self, token: str) -> dict[str, Any] | None:
        """Load session data from backing store."""
        if self._use_memory:
            return _memory_store.get(token)

        raw = await self._redis.get(f"session:{token}")
        if raw is None:
            return None
        import json

        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None

    async def _set_session(self, token: str, data: dict[str, Any]) -> None:
        """Persist session data to backing store."""
        if self._use_memory:
            _memory_store[token] = data
            return

        import json

        await self._redis.set(
            f"session:{token}",
            json.dumps(data),
            ex=self._session_ttl,
        )


def clear_memory_store() -> None:
    """Clear the in-memory session store. Used in tests."""
    _memory_store.clear()
