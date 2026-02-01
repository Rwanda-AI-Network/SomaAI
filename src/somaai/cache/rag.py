"""RAG-specific caching for embeddings and responses.

Integrates with existing cache infrastructure but adds RAG-specific logic.
Uses Decimal for precise confidence score handling.
"""

from __future__ import annotations

import hashlib
import json
import logging
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)


class EmbeddingCache:
    """Cache for query embeddings to avoid re-embedding identical queries.

    Uses existing Redis infrastructure with RAG-specific TTL.
    """

    def __init__(self, redis_client=None, ttl: int = 3600):
        """Initialize embedding cache.

        Args:
            redis_client: Redis client (will use get_cache_redis if None)
            ttl: Time-to-live in seconds (default: 1 hour)
        """
        self.ttl = ttl
        self._redis = redis_client
        self._enabled = True

    async def _get_redis(self):
        """Get Redis client lazily."""
        if self._redis is None:
            try:
                from somaai.utils.redis import get_cache_redis
                self._redis = await get_cache_redis()
            except Exception as e:
                logger.warning(f"Failed to initialize embedding cache: {e}")
                self._enabled = False
        return self._redis

    def _make_key(self, query: str) -> str:
        """Generate cache key from query."""
        query_hash = hashlib.sha256(query.encode()).hexdigest()[:16]
        return f"rag:emb:{query_hash}"

    async def get(self, query: str) -> list[float] | None:
        """Get cached embedding for query."""
        if not self._enabled:
            return None

        try:
            redis = await self._get_redis()
            if not redis:
                return None

            key = self._make_key(query)
            cached = await redis.get(key)

            if cached:
                logger.debug(f"Embedding cache HIT: {query[:50]}...")
                return json.loads(cached)

            return None

        except Exception as e:
            logger.warning(f"Embedding cache get failed: {e}")
            return None

    async def set(self, query: str, embedding: list[float]) -> None:
        """Store embedding in cache."""
        if not self._enabled:
            return

        try:
            redis = await self._get_redis()
            if not redis:
                return

            from somaai.utils.serialization import json_serializer

            key = self._make_key(query)
            await redis.setex(key, self.ttl, json.dumps(embedding, default=json_serializer))

        except Exception as e:
            logger.warning(f"Embedding cache set failed: {e}")


class ResponseCache:
    """Cache for complete RAG responses.

    Caches by query + grade + subject, only for high-confidence responses.
    """

    def __init__(self, redis_client=None, ttl: int = 86400, min_confidence: Decimal = Decimal("0.7")):
        """Initialize response cache.

        Args:
            redis_client: Redis client (will use get_cache_redis if None)
            ttl: Time-to-live in seconds (default: 24 hours)
            min_confidence: Minimum confidence to cache (Decimal for precision)
        """
        self.ttl = ttl
        self.min_confidence = min_confidence
        self._redis = redis_client
        self._enabled = True

    async def _get_redis(self):
        """Get Redis client lazily."""
        if self._redis is None:
            try:
                from somaai.utils.redis import get_cache_redis
                self._redis = await get_cache_redis()
            except Exception as e:
                logger.warning(f"Failed to initialize response cache: {e}")
                self._enabled = False
        return self._redis

    def _make_key(self, query: str, grade: str, subject: str) -> str:
        """Generate cache key from query parameters."""
        data = f"{query}|{grade}|{subject}".encode()
        key_hash = hashlib.sha256(data).hexdigest()[:16]
        return f"rag:resp:{key_hash}"

    async def get(
        self,
        query: str,
        grade: str,
        subject: str,
    ) -> dict[str, Any] | None:
        """Get cached response."""
        if not self._enabled:
            return None

        try:
            redis = await self._get_redis()
            if not redis:
                return None

            key = self._make_key(query, grade, subject)
            cached = await redis.get(key)

            if cached:
                logger.info(f"Response cache HIT: {query[:50]}...")
                response = json.loads(cached)
                response["from_cache"] = True
                return response

            return None

        except Exception as e:
            logger.warning(f"Response cache get failed: {e}")
            return None

    async def set(
        self,
        query: str,
        grade: str,
        subject: str,
        response: dict[str, Any],
    ) -> None:
        """Store response in cache.

        Only caches high-confidence, grounded responses.
        """
        if not self._enabled:
            return

        # Quality check - use Decimal for precise comparison
        confidence_raw = response.get("confidence", 0)
        confidence = Decimal(str(confidence_raw))
        is_grounded = response.get("is_grounded", True)

        if confidence < self.min_confidence or not is_grounded:
            logger.debug(f"Skipping cache: confidence={confidence}, grounded={is_grounded}")
            return

        try:
            redis = await self._get_redis()
            if not redis:
                return

            key = self._make_key(query, grade, subject)

            # Don't cache large fields
            response_copy = {k: v for k, v in response.items()}
            response_copy.pop("citations", None)

            from somaai.utils.serialization import json_serializer
            await redis.setex(key, self.ttl, json.dumps(response_copy, default=json_serializer))
            logger.info(f"Cached response: {query[:50]}...")

        except Exception as e:
            logger.warning(f"Response cache set failed: {e}")

    async def invalidate_pattern(self, pattern: str = "rag:resp:*") -> int:
        """Invalidate cache entries matching pattern."""
        if not self._enabled:
            return 0

        try:
            redis = await self._get_redis()
            if not redis:
                return 0

            keys = []
            async for key in redis.scan_iter(match=pattern):
                keys.append(key)

            if keys:
                deleted = await redis.delete(*keys)
                logger.info(f"Invalidated {deleted} cache entries")
                return deleted

            return 0

        except Exception as e:
            logger.error(f"Cache invalidation failed: {e}")
            return 0


# Singleton instances
_embedding_cache: EmbeddingCache | None = None
_response_cache: ResponseCache | None = None


def get_embedding_cache() -> EmbeddingCache:
    """Get singleton embedding cache instance."""
    global _embedding_cache
    if _embedding_cache is None:
        from somaai.cache.config import get_cache_config
        config = get_cache_config()
        _embedding_cache = EmbeddingCache(ttl=config.embedding_ttl)
    return _embedding_cache


def get_response_cache() -> ResponseCache:
    """Get singleton response cache instance."""
    global _response_cache
    if _response_cache is None:
        from somaai.cache.config import get_cache_config
        config = get_cache_config()
        _response_cache = ResponseCache(
            ttl=config.query_ttl,  # Use query_ttl for responses
            min_confidence=Decimal("0.7"),
        )
    return _response_cache
