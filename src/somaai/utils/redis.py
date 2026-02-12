"""Redis connection utilities for centralized connection management.

Provides singleton Redis clients for different databases with proper configuration.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# Singleton instances
_REDIS_GENERAL: aioredis.Redis | None = None
_REDIS_JOBS: aioredis.Redis | None = None
_REDIS_CACHE: aioredis.Redis | None = None


def parse_redis_url(url: str) -> tuple[str, int, int, str | None]:
    """Parse Redis URL into components.

    Args:
        url: Redis URL (redis://host:port/db or redis://:password@host:port/db)

    Returns:
        Tuple of (host, port, db, password)
    """
    # Handle password in URL
    password = None
    if "@" in url:
        # Format: redis://:password@host:port/db
        auth_part, rest = url.split("@", 1)
        if ":" in auth_part:
            password = auth_part.split(":")[-1]
        url_part = rest
    else:
        # Format: redis://host:port/db
        url_part = url.split("://", 1)[1] if "://" in url else url

    # Parse host:port/db
    if "/" in url_part:
        host_port, db_str = url_part.rsplit("/", 1)
        db = int(db_str)
    else:
        host_port = url_part
        db = 0

    if ":" in host_port:
        host, port_str = host_port.rsplit(":", 1)
        port = int(port_str)
    else:
        host = host_port
        port = 6379

    return host, port, db, password


async def get_redis_client(
    url: str,
    decode_responses: bool = True,
    max_connections: int = 10,
) -> aioredis.Redis:
    """Create Redis client from URL.

    Args:
        url: Redis connection URL
        decode_responses: Decode responses to strings
        max_connections: Max connections in pool

    Returns:
        Redis client instance
    """
    try:
        import redis.asyncio as aioredis
    except ImportError:
        raise ImportError("redis is required. Install with: uv add redis")

    host, port, db, password = parse_redis_url(url)

    return aioredis.Redis(
        host=host,
        port=port,
        db=db,
        password=password,
        decode_responses=decode_responses,
        max_connections=max_connections,
        socket_connect_timeout=5,
        socket_timeout=5,
    )


async def get_general_redis() -> aioredis.Redis:
    """Get singleton Redis client for general use (db/0).

    Returns:
        Redis client
    """
    global _REDIS_GENERAL
    if _REDIS_GENERAL is None:
        from somaai.settings import settings

        logger.info(f"Creating general Redis client: {settings.redis_url}")
        _REDIS_GENERAL = await get_redis_client(settings.redis_url)
    return _REDIS_GENERAL


async def get_jobs_redis() -> aioredis.Redis:
    """Get singleton Redis client for job queue (db/1).

    Returns:
        Redis client for jobs
    """
    global _REDIS_JOBS
    if _REDIS_JOBS is None:
        from somaai.settings import settings

        url = getattr(
            settings, "redis_jobs_url", settings.redis_url.replace("/0", "/1")
        )
        logger.info(f"Creating jobs Redis client: {url}")
        _REDIS_JOBS = await get_redis_client(url)
    return _REDIS_JOBS


async def get_cache_redis() -> aioredis.Redis:
    """Get singleton Redis client for RAG cache (db/2).

    Returns:
        Redis client for cache
    """
    global _REDIS_CACHE
    if _REDIS_CACHE is None:
        from somaai.settings import settings

        url = getattr(
            settings, "redis_cache_url", settings.redis_url.replace("/0", "/2")
        )
        logger.info(f"Creating cache Redis client: {url}")
        _REDIS_CACHE = await get_redis_client(url, decode_responses=True)
    return _REDIS_CACHE


async def close_redis_connections() -> None:
    """Close all Redis connections gracefully."""
    global _REDIS_GENERAL, _REDIS_JOBS, _REDIS_CACHE

    for client in [_REDIS_GENERAL, _REDIS_JOBS, _REDIS_CACHE]:
        if client:
            await client.close()

    _REDIS_GENERAL = None
    _REDIS_JOBS = None
    _REDIS_CACHE = None
    logger.info("Closed all Redis connections")


async def ping_redis(client: aioredis.Redis) -> bool:
    """Check if Redis connection is alive.

    Args:
        client: Redis client

    Returns:
        True if connection is alive
    """
    try:
        await client.ping()
        return True
    except Exception as e:
        logger.error(f"Redis ping failed: {e}")
        return False


async def health_check() -> dict:
    """Check health of all Redis connections.

    Returns:
        Health status dict
    """
    try:
        general = await get_general_redis()
        jobs = await get_jobs_redis()
        cache = await get_cache_redis()

        return {
            "general": await ping_redis(general),
            "jobs": await ping_redis(jobs),
            "cache": await ping_redis(cache),
        }
    except Exception as e:
        return {
            "error": str(e),
            "general": False,
            "jobs": False,
            "cache": False,
        }
