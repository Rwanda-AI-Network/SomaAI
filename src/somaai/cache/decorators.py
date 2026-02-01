"""Caching decorators using aiocache.

aiocache provides:
- Multi-backend support (Redis, Memcached, in-memory)
- Async-first design
- Key builders and serializers
- Decorator-based caching

Install: uv add aiocache[redis]
"""

from collections.abc import Callable
from functools import wraps

try:
    from aiocache import Cache, cached
    from aiocache.serializers import JsonSerializer

    AIOCACHE_AVAILABLE = True
except ImportError:
    AIOCACHE_AVAILABLE = False
    cached = None

from somaai.cache.config import get_cache_config


def _ensure_aiocache():
    """Raise ImportError if aiocache is not installed."""
    if not AIOCACHE_AVAILABLE:
        raise ImportError(
            "aiocache is required for caching decorators. "
            "Install with: uv add aiocache[redis]"
        )


def _build_key(func_name: str, *args, **kwargs) -> str:
    """Build a cache key from function name and arguments."""
    config = get_cache_config()
    key_parts = [config.namespace, func_name]

    # Add positional args (skip 'self' if present)
    for arg in args:
        if hasattr(arg, "__class__") and arg.__class__.__name__ in ("self", "cls"):
            continue
        key_parts.append(str(arg)[:50])  # Truncate long args

    # Add keyword args
    for k, v in sorted(kwargs.items()):
        key_parts.append(f"{k}={str(v)[:50]}")

    return ":".join(key_parts)


def cached_query(
    ttl: int | None = None,
    key_builder: Callable | None = None,
):
    """Cache decorator for query responses.

    Usage:
        @cached_query(ttl=3600)
        async def generate_response(query: str, context: list) -> str:
            ...
    """
    _ensure_aiocache()
    config = get_cache_config()

    return cached(
        ttl=ttl or config.query_ttl,
        cache=Cache.REDIS,
        endpoint=config.redis_url.split("://")[1].split(":")[0]
        if "://" in config.redis_url
        else "localhost",
        port=int(config.redis_url.split(":")[-1].split("/")[0])
        if ":" in config.redis_url
        else 6379,
        namespace=f"{config.namespace}:query",
        serializer=JsonSerializer(),
        key_builder=key_builder
        or (lambda f, *a, **kw: _build_key(f.__name__, *a, **kw)),
    )


def cached_embedding(
    ttl: int | None = None,
    key_builder: Callable | None = None,
):
    """Cache decorator for embedding operations.

    Usage:
        @cached_embedding()
        async def embed_text(text: str) -> list[float]:
            ...
    """
    _ensure_aiocache()
    config = get_cache_config()

    return cached(
        ttl=ttl or config.embedding_ttl,
        cache=Cache.REDIS,
        endpoint=config.redis_url.split("://")[1].split(":")[0]
        if "://" in config.redis_url
        else "localhost",
        port=int(config.redis_url.split(":")[-1].split("/")[0])
        if ":" in config.redis_url
        else 6379,
        namespace=f"{config.namespace}:embed",
        serializer=JsonSerializer(),
        key_builder=key_builder
        or (lambda f, *a, **kw: _build_key(f.__name__, *a, **kw)),
    )


def cached_retrieval(
    ttl: int | None = None,
    key_builder: Callable | None = None,
):
    """Cache decorator for retrieval results.

    Usage:
        @cached_retrieval(ttl=1800)
        async def retrieve_documents(query: str, top_k: int = 10) -> list[dict]:
            ...
    """
    _ensure_aiocache()
    config = get_cache_config()

    return cached(
        ttl=ttl or config.retrieval_ttl,
        cache=Cache.REDIS,
        endpoint=config.redis_url.split("://")[1].split(":")[0]
        if "://" in config.redis_url
        else "localhost",
        port=int(config.redis_url.split(":")[-1].split("/")[0])
        if ":" in config.redis_url
        else 6379,
        namespace=f"{config.namespace}:retrieval",
        serializer=JsonSerializer(),
        key_builder=key_builder
        or (lambda f, *a, **kw: _build_key(f.__name__, *a, **kw)),
    )


# Fallback in-memory cache for development without Redis
class SimpleCache:
    """In-memory cache fallback with TTL eviction.
    
    Prevents unbounded memory growth by:
    - Storing expiration times with entries
    - Evicting expired entries on access
    - Limiting max entries (LRU eviction)
    """

    MAX_ENTRIES = 1000  # Prevent unbounded growth

    def __init__(self):
        self._cache: dict[str, tuple[float, any]] = {}  # {key: (expires_at, value)}
        self._access_order: list[str] = []  # For LRU eviction

    def _evict_expired(self) -> None:
        """Remove expired entries."""
        import time
        now = time.time()
        expired = [k for k, (exp, _) in self._cache.items() if exp < now]
        for key in expired:
            self._cache.pop(key, None)
            if key in self._access_order:
                self._access_order.remove(key)

    def _evict_lru(self) -> None:
        """Evict least recently used if over limit."""
        while len(self._cache) >= self.MAX_ENTRIES and self._access_order:
            oldest = self._access_order.pop(0)
            self._cache.pop(oldest, None)

    def cached(self, ttl: int = 3600):
        """Caching decorator with TTL."""
        import time

        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                self._evict_expired()

                key = _build_key(func.__name__, *args, **kwargs)
                now = time.time()

                if key in self._cache:
                    expires_at, value = self._cache[key]
                    if expires_at > now:
                        # Update access order
                        if key in self._access_order:
                            self._access_order.remove(key)
                        self._access_order.append(key)
                        return value
                    else:
                        # Expired
                        self._cache.pop(key, None)

                result = await func(*args, **kwargs)

                # Evict LRU if needed
                self._evict_lru()

                # Store with expiration
                self._cache[key] = (now + ttl, result)
                self._access_order.append(key)

                return result

            return wrapper

        return decorator

    def clear(self):
        """Clear all cached items."""
        self._cache.clear()
        self._access_order.clear()


# Fallback cache instance
fallback_cache = SimpleCache()
